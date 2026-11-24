#!/usr/bin/env python3
"""Run the full local rehearsal and save the complete test summary and transcript."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Tee:
    def __init__(self, terminal, log):
        self.terminal, self.log = terminal, log
    def write(self, text):
        self.terminal.write(text)
        self.log.write(text)
        self.flush()
        return len(text)
    def flush(self):
        self.terminal.flush()
        self.log.flush()
    def isatty(self):
        return False


def main():
    os.environ['CN_RUN_INTEGRATION'] = '1'
    sys.dont_write_bytecode = True
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT / 'Phase2/tests'))
    sys.path.insert(0, str(ROOT / 'Phase2'))
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    folder = ROOT / 'Evidence/Phase2'
    folder.mkdir(parents=True, exist_ok=True)
    transcript = folder / (stamp + '-full-test-transcript.txt')
    summary = folder / (stamp + '-full-test-summary.json')
    stdout, stderr = sys.stdout, sys.stderr
    result = unittest.TestResult()
    runner_error = None
    interrupted = False
    with transcript.open('w') as log:
        try:
            sys.stdout, sys.stderr = Tee(stdout, log), Tee(stderr, log)
            suite = unittest.defaultTestLoader.discover(str(ROOT / 'Phase2/tests'))
            result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
        except KeyboardInterrupt:
            interrupted = True
            print('INTERRUPTED: the run is incomplete; its transcript and summary will be retained.')
        except Exception:
            runner_error = traceback.format_exc()
            print(runner_error)
        finally:
            sys.stdout, sys.stderr = stdout, stderr
    status = {
        'time_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
        'tests_run': result.testsRun,
        'failed': [{'test': t.id(), 'traceback': tb} for t, tb in result.failures],
        'errors': [{'test': t.id(), 'traceback': tb} for t, tb in result.errors],
        'skipped': [{'test': t.id(), 'reason': reason} for t, reason in result.skipped],
        'all_passed_without_skips': (result.testsRun >= 6 and result.wasSuccessful() and
                                     not result.skipped and not interrupted and runner_error is None),
        'interrupted': interrupted,
        'runner_error': runner_error,
        'transcript': str(transcript.relative_to(ROOT)),
        'scope': 'One-Mac local rehearsal. Not proof of physical firewall, OS resolver failover, natural DNS cutover or faculty fault recovery.'
    }
    status['source_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in (ROOT / 'Phase2/cn.py', ROOT / 'Phase2/tests/test_phase2.py')}
    summary.write_text(json.dumps(status, indent=2) + '\n')
    print('Transcript:', transcript)
    print('Summary:', summary)
    if status['all_passed_without_skips']:
        validation_path = ROOT / 'Phase2/VALIDATION_STATUS.json'
        previous = json.loads(validation_path.read_text()) if validation_path.exists() else {}
        previous.update(updated_at_utc=status['time_utc'], full_suite={
            'passed': result.testsRun, 'total': result.testsRun,
            'source': str(summary.relative_to(ROOT)), 'machine_recorded': True,
            'transcript': status['transcript'], 'source_sha256': status['source_sha256']})
        validation_path.write_text(json.dumps(previous, indent=2) + '\n')
        print(f'PASS: {result.testsRun}/{result.testsRun}. Physical LAN checks remain separate.')
        return 0
    print('NOT COMPLETE: inspect failures or skipped checks in the saved summary.')
    return 130 if interrupted else 1


if __name__ == '__main__':
    sys.exit(main())
