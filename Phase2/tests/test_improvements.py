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
