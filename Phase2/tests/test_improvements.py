"""Regression checks for deployment guards and reliable evidence handling."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cn


class DeploymentGuards(unittest.TestCase):
    def test_configuration_shape_and_domain_limits(self):
        for invalid in ([], {}, dict(cn.defaults(), domain=123),
                        dict(cn.defaults(), domain='a.' * 123 + 'team.test')):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                cn.validate(invalid)

    def test_loopback_requires_explicit_rehearsal(self):
        config = dict(cn.defaults(), mac1='127.0.0.2')
        with self.assertRaisesRegex(ValueError, 'loopback'):
            cn.validate(config)
        self.assertEqual(cn.validate(config, rehearsal=True)['mac1'], '127.0.0.2')


class AtomicWrites(unittest.TestCase):
    def test_concurrent_writers_leave_a_complete_document(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'state.json'
            documents = [json.dumps({'writer': n, 'payload': str(n) * 1000}) for n in range(20)]
            with ThreadPoolExecutor(max_workers=8) as workers:
                list(workers.map(lambda document: cn.write(path, document), documents))
            self.assertIn(path.read_text(), documents)
            self.assertEqual(list(Path(folder).glob('*.tmp')), [])

    def test_failed_replacement_preserves_original_and_private_permissions(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'state.json'
            cn.write(path, 'original', private=True)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with patch('cn.os.replace', side_effect=OSError('write failed')):
                with self.assertRaises(OSError):
                    cn.write(path, 'replacement')
            self.assertEqual(path.read_text(), 'original')
            self.assertEqual(list(Path(folder).glob('*.tmp')), [])


class FirewallRecoveryGuards(unittest.TestCase):
    def test_wrong_backend_and_missing_backup_cannot_change_pf(self):
        with tempfile.TemporaryDirectory() as folder:
            lab = cn.Lab(cn.defaults(), root=folder)
            state = lab.runtime / 'firewall/active.json'
            cn.write(state, json.dumps({'backend': 'b', 'prior_rules': str(Path(folder) / 'missing.pf')}))
            with patch('cn.binary', side_effect=lambda name: name), patch('cn.run') as execute:
                with self.assertRaisesRegex(RuntimeError, 'belongs to backend b'):
                    lab.firewall('restore', 'a')
                with self.assertRaisesRegex(RuntimeError, 'backup is missing'):
                    lab.firewall('restore', 'b')
                execute.assert_not_called()
            self.assertTrue(state.exists(), 'Recovery state must remain available after a guard failure')


class DnsTtlVerification(unittest.TestCase):
    def test_both_transports_and_wrong_ttl_detection(self):
        for ttl, wanted in ((30, 0), (7, 1)):
            with self.subTest(ttl=ttl), tempfile.TemporaryDirectory() as folder:
                lab = cn.Lab(cn.defaults(), root=folder)
                output = f'app.team1.test. {ttl} IN A {lab.c["mac2"]}\n'
                with patch('cn.binary', side_effect=lambda name: name), \
                     patch('cn.run', return_value=subprocess.CompletedProcess([], 0, output, '')) as execute, \
                     contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(lab.verify('dns-ttl'), wanted)
                self.assertEqual(execute.call_count, 8)
                self.assertEqual(sum('+tcp' in call.args[0] for call in execute.call_args_list), 4)


class VerificationGuards(unittest.TestCase):
    def test_empty_or_invalid_programmatic_checks_cannot_report_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            lab = cn.Lab(cn.defaults(), root=folder)
            with patch('cn.run') as execute:
                for mode, count in (('typo', 12), ('b-only', 0), ('balanced', 101), ('b-only', True)):
                    with self.subTest(mode=mode, count=count), self.assertRaises(ValueError):
                        lab.verify(mode, count=count)
                execute.assert_not_called()
            self.assertFalse((Path(folder) / 'Evidence').exists())


class EvidenceProvenance(unittest.TestCase):
    def test_verification_saves_exact_public_configuration_without_extra_keys(self):
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            lab = cn.Lab(dict(cn.defaults(), unrelated_secret='do-not-copy'), root=folder)
            output = f'app.team1.test. 30 IN A {lab.c["mac2"]}\n'
            with patch('cn.binary', side_effect=lambda name: name), \
                 patch('cn.run', return_value=subprocess.CompletedProcess([], 0, output, '')), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(lab.verify('dns-records'), 0)
            record = json.loads(next((Path(folder) / 'Evidence/Phase2').glob('*.json')).read_text())
            config = record['configuration']
            self.assertEqual(config['mac4'], lab.c['mac4'])
            self.assertNotIn('unrelated_secret', config)
            expected = hashlib.sha256(json.dumps(config, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            self.assertEqual(record['configuration_sha256'], expected)


class RunnerFailureEvidence(unittest.TestCase):
    def test_discovery_failure_and_interrupt_save_incomplete_results(self):
        import run_checks
        for error, expected in ((ImportError('broken discovery'), 1), (KeyboardInterrupt(), 130)):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                (root / 'Phase2/tests').mkdir(parents=True)
                (root / 'Phase2/cn.py').write_text('# fixture\n')
                (root / 'Phase2/tests/test_phase2.py').write_text('# fixture\n')
                previous_cwd = Path.cwd()
                try:
                    with patch.object(run_checks, 'ROOT', root), patch.dict(os.environ), \
                         patch.object(sys, 'path', list(sys.path)), \
                         patch.object(unittest.defaultTestLoader, 'discover', side_effect=error), \
                         contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(run_checks.main(), expected)
                finally:
                    os.chdir(previous_cwd)
                summary = next((root / 'Evidence/Phase2').glob('*-summary.json'))
                record = json.loads(summary.read_text())
                self.assertFalse(record['all_passed_without_skips'])
                self.assertTrue((root / record['transcript']).is_file())
                if expected == 130:
                    self.assertTrue(record['interrupted'])
                else:
                    self.assertIn('broken discovery', record['runner_error'])
