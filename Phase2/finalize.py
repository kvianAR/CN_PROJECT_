#!/usr/bin/env python3
"""Audit and present the complete CN code/configuration bundle without inventing live evidence."""
import argparse
import ast
import datetime as dt
import hashlib
import html
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    'Mac 1 - DNS/render_dns.py', 'Mac 1 - DNS/start_dns.command',
    'Mac 2 - Edge/render_nginx.py', 'Mac 2 - Edge/create_certificate.command',
    'Mac 3 - Backend A/backend_a.py', 'Mac 4 - Backend B/backend_b.py',
    'Shared/CN_Project_Doc.pdf', 'Shared/verify_phase1.command',
    'Phase2/cn.py', 'Phase2/tests/test_phase2.py', 'Phase2/run_checks.py',
    'Phase2/README.md', 'Phase2/REPORT.md', 'Phase2/docs/TROUBLESHOOTING.md',
    'Evidence/Phase2/README.md', 'START_PHASE2.command', 'CHECK_PROJECT.command',
    'RUN_CN.command', 'Phase2/finalize.py', 'Phase2/site.example.json',
    'Phase2/QUICKSTART_HI.md', '.github/workflows/phase2.yml']
FEATURES = [
    ('Phase 1', 'Private DNS, two REST services, Nginx round robin, trusted TLS, HTTP caching and original evidence'),
    ('Phase 2 A', 'Independent backup DNS plus client DNS configuration and restore'),
    ('Phase 2 B', 'TTL 30, real caching resolver, record changes and explicit cache flush'),
    ('Phase 2 C', 'Backend PF isolation, strict edge allowlist, saved rules and rollback'),
    ('Phase 2 D', 'Passive backend failover, retry limits, recovery and upstream logging'),
    ('Phase 2 E', 'Separate standby key, same-CA certificate and DNS-based edge cutover'),
    ('Phase 2 F', 'Layered diagnosis, controlled failures, command transcripts and packet capture')]


def inline(text):
    text = html.escape(text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    return text


def markdown(text):
    """Render the report's limited Markdown syntax without external dependencies."""
    lines = text.splitlines()
    output, paragraph = [], []
    def flush():
        if paragraph:
            output.append('<p>' + inline(' '.join(paragraph)) + '</p>')
            paragraph.clear()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            flush(); index += 1; continue
        if line.startswith('```'):
            flush(); block = []; index += 1
            while index < len(lines) and not lines[index].startswith('```'):
                block.append(lines[index]); index += 1
            output.append('<pre><code>' + html.escape('\n'.join(block)) + '</code></pre>')
        elif line.startswith('#'):
            flush(); match = re.match(r'^(#{1,6})\s+(.+)', line)
            if match:
                level = len(match[1]); output.append(f'<h{level}>' + inline(match[2]) + f'</h{level}>')
            else:
                paragraph.append(line)
        elif line.startswith('|'):
            flush(); rows = []
            while index < len(lines) and lines[index].startswith('|'):
                row = [x.strip() for x in lines[index].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?', x) for x in row):
                    rows.append(row)
                index += 1
            table = '<table>'
            for n, row in enumerate(rows):
                tag = 'th' if n == 0 else 'td'
                table += '<tr>' + ''.join(f'<{tag}>' + inline(cell) + f'</{tag}>' for cell in row) + '</tr>'
            output.append(table + '</table>'); continue
        elif line.startswith('- '):
            flush(); items = []
            while index < len(lines) and lines[index].startswith('- '):
                items.append('<li>' + inline(lines[index][2:]) + '</li>'); index += 1
            output.append('<ul>' + ''.join(items) + '</ul>'); continue
        else:
            paragraph.append(line)
        index += 1
    flush()
    return '\n'.join(output)


def build():
    missing = [name for name in REQUIRED if not (ROOT / name).is_file()]
    if missing:
        raise RuntimeError('Required files missing: ' + ', '.join(missing))
    for path in ROOT.rglob('*.py'):
        if not any(part in {'.git', 'runtime', '__pycache__'} for part in path.parts):
            ast.parse(path.read_text(), filename=str(path))
    validation = json.loads((ROOT / 'Phase2/VALIDATION_STATUS.json').read_text())
    integration = json.loads((ROOT / 'Phase2/LOCAL_TEST_RESULTS.json').read_text())
    suite = validation.get('full_suite', {})
    fingerprint = suite.get('source_sha256')
    current = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
               for name in ('Phase2/cn.py', 'Phase2/tests/test_phase2.py')}
    if fingerprint:
        suite_state = ('Machine-recorded suite matches current sources' if fingerprint == current
                       else 'Saved full-suite result predates source changes; rerun CHECK_PROJECT.command')
    else:
        suite_state = '6/6 previously confirmed by the user; full transcript/fingerprint was not recorded for that run'
    rows = ''.join('<tr><td>' + html.escape(name) + '</td><td>' + html.escape(description)
                   + '</td><td>Implemented</td></tr>' for name, description in FEATURES)
    findings = ''.join('<li>' + html.escape(item) + '</li>' for item in integration.get('passed', []))
    report = markdown((ROOT / 'Phase2/REPORT.md').read_text())
    document = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>CN Project — Phases 1 and 2</title>
<style>body{font:16px/1.65 system-ui,sans-serif;color:#172a3a;background:#f1f5f9;margin:0}
main{max-width:1060px;margin:32px auto;background:white;padding:42px;border-radius:12px}
h1,h2,h3{line-height:1.25}h2{margin-top:34px;color:#124b64}p{max-width:90ch}
table{border-collapse:collapse;width:100%;margin:20px 0;font-size:14px}td,th{padding:12px;border:1px solid #d9e1e8;text-align:left;vertical-align:top}th{background:#eaf2f7}
code,pre{font-family:ui-monospace,monospace}code{background:#edf2f7;padding:2px 4px;border-radius:3px}pre{padding:16px;background:#edf2f7;overflow:auto}
.notice{border-left:5px solid #d08b19;padding:14px 20px;background:#fff8e8}.ready{border-left:5px solid #168060;padding:14px 20px;background:#edf9f3}
a{color:#135f91}small{color:#536776}@media print{body{background:white}main{padding:0;margin:0;max-width:none}h2{break-after:avoid}tr{break-inside:avoid}}</style>
<main><small>COMPUTER NETWORKS · LOCAL COURSE PROJECT</small><h1>CN Project — Phase 1 + Phase 2</h1>
<div class="ready"><strong>Source/configuration bundle implemented in one repository.</strong><br>
Final Phase 1 baseline preserved; all six Phase 2 extensions have code, launch instructions and recovery procedures.</div>
<div class="notice"><strong>Implementation and demonstration have separate status.</strong><br>
The saved service checks are one-Mac loopback evidence. Physical Mac firewall enforcement, normal client DNS failover/cutover,
faculty troubleshooting and physical screenshots/recordings have not been completed. Mac 2 is remote and its supplied private IP did not answer the client's ping.</div>
<h2>Start</h2><p>Double-click <code>RUN_CN.command</code> for the local test/demo sequence and updated report.
Use <code>START_PHASE2.command</code> for individual services on the physical network.</p>
<p><a href="Phase2/QUICKSTART_HI.md">Stepwise setup</a> · <a href="Phase2/README.md">Full runbook</a> ·
<a href="Phase2/docs/TROUBLESHOOTING.md">Troubleshooting</a></p>
<h2>Delivered implementation</h2><table><tr><th>Area</th><th>Delivered behavior</th><th>Source status</th></tr>''' + rows + '''</table>
<h2>Validation</h2><p>''' + html.escape(suite_state) + '''</p>
<p>Saved real service findings: ''' + str(len(integration.get('passed', []))) + '''. Source: <code>Phase2/LOCAL_TEST_RESULTS.json</code>.</p><ul>''' + findings + '''</ul>
<h2>Academic report</h2>''' + report + '''<hr><small>This report is generated from project files and saved observations. No physical results are inferred from local tests.</small></main></html>'''
    (ROOT / 'CN_REPORT.html').write_text(document)
    manifest = {'generated_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                'scope': 'Static source audit; does not execute network services or firewall rules',
                'required_files_present': len(REQUIRED), 'python_sources_parse': True,
                'current_source_sha256': current, 'suite_status': suite_state,
                'implementation': [{'area': area, 'behavior': behavior, 'status': 'implemented'} for area, behavior in FEATURES],
                'physical_demonstration': 'Not completed; source implementation is delivered separately from physical validation.'}
    (ROOT / 'Phase2/DELIVERY_STATUS.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Source audit passed. Report:', ROOT / 'CN_REPORT.html')
    print('Physical demonstrations remain marked accurately in the report.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-tests', action='store_true')
    args = parser.parse_args()
    code = 0
    if args.run_tests:
        code = subprocess.call([sys.executable, str(ROOT / 'Phase2/run_checks.py')], cwd=ROOT)
    build()
    return code


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, SyntaxError) as error:
        print('ERROR:', error, file=sys.stderr)
        sys.exit(1)
