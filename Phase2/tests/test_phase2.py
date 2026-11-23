"""Real local integration tests plus configuration/rollback guard checks."""
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'Phase2'))
from cn import Lab, defaults, validate, run, binary


class ConfigTests(unittest.TestCase):
    def test_deployment_requires_distinct_machines_and_safe_values(self):
        c = defaults()
        for key, bad in [('mac1', '0.0.0.0'), ('domain', 'team.test;bad'), ('ttl', 0),
                         ('https_port', 65536), ('interface', 'en0\nblock all')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate(dict(c, **{key: bad}))
        with self.assertRaises(ValueError):
            validate(dict(c, mac4=c['mac1']))
        for changed in (dict(standby_https_port=9443), dict(backend_a_port=c['standby_https_port']),
                        dict(backend_b_port=c['backup_dns_port']), dict(upstream_dns=c['mac1'])):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                validate(dict(c, **changed))

    def test_phase1_source_is_reused_and_firewall_limits_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('Mac 1 - DNS', 'Mac 2 - Edge', 'Phase2'):
                (root / name).mkdir()
            first = root / 'Mac 1 - DNS/settings.env'
            second = root / 'Mac 2 - Edge/settings.env'
            first.write_text('MAC1_IP=192.0.2.1\nMAC2_IP=192.0.2.2\nDOMAIN=team1.test\nUPSTREAM_DNS=192.0.2.254\n')
            second.write_text('MAC2_IP=192.0.2.2\nMAC3_IP=192.0.2.3\nMAC4_IP=192.0.2.4\nDOMAIN=team1.test\nHTTPS_PORT=8443\n')
            before = (first.read_bytes(), second.read_bytes())
            current = defaults()
            current['mac4'] = '10.7.27.236'
            template = root / 'Phase2/site.example.json'
            template.write_text(json.dumps(current))
            self.assertEqual(defaults(root)['mac4'], '10.7.27.236')
            self.assertEqual((first.read_bytes(), second.read_bytes()), before)
            template.unlink()
            self.assertEqual(defaults(root)['mac4'], '192.0.2.4')
        with tempfile.TemporaryDirectory() as folder:
            lab = Lab(defaults(), root=folder)
            text = lab.firewall_rules('b')
            self.assertIn('from { ' + lab.c['mac2'] + ' }', text)
            self.assertNotIn(lab.c['mac3'], text)
            self.assertIn(lab.c['mac3'], lab.firewall_rules('b', True))
            self.assertIn('inet6', text)
            self.assertIn('block drop in quick', text)
            with patch('cn.run') as mocked:
                with self.assertRaises(RuntimeError):
                    lab.firewall('restore', 'b')
                mocked.assert_not_called()
        # Test transaction ownership without changing the host firewall.
        for already_enabled in (True, False):
            with self.subTest(already_enabled=already_enabled), tempfile.TemporaryDirectory() as folder:
                lab = Lab(defaults(), root=folder)
                commands = []
                def fake_run(command, **kwargs):
                    command = [str(x) for x in command]
                    commands.append(command)
                    if command == ['pfctl', '-s', 'rules']:
                        output = 'anchor "com.apple/*" all\n'
                    elif command == ['pfctl', '-s', 'info']:
                        output = 'Status: ' + ('Enabled' if already_enabled else 'Disabled') + '\n'
                    elif command == ['pfctl', '-E']:
                        output = 'Token : 12345\n'
                    else:
                        output = ''
                    return subprocess.CompletedProcess(command, 0, output, '')
                with patch('cn.run', side_effect=fake_run), patch('cn.binary', side_effect=lambda name: name), \
                     patch('cn.os.geteuid', return_value=0), patch.object(lab, 'require_local_role'), \
                     patch('sys.stdout', new_callable=io.StringIO), \
                     patch('cn.shutil.copy2', side_effect=lambda src, dst: Path(dst).write_text('# Original PF fixture\n')):
                    lab.firewall('apply', 'b')
                    lab.firewall('restore', 'b')
                if already_enabled:
                    self.assertNotIn(['pfctl', '-E'], commands)
                    self.assertFalse(any('-X' in command for command in commands))
                else:
                    self.assertIn(['pfctl', '-E'], commands)
                    self.assertIn(['pfctl', '-X', '12345'], commands)


class NativeSyntaxTests(unittest.TestCase):
    def test_real_dnsmasq_configs_parse(self):
        with tempfile.TemporaryDirectory(prefix='cn-phase2-syntax-') as folder:
            lab = Lab(defaults(), root=folder)
            for role in ('dns-primary', 'dns-backup', 'cache'):
                target = lab.render(role)
                p = run([binary('dnsmasq'), '--test', '--conf-file=' + str(target)])
                self.assertIn('syntax check OK', p.stderr + p.stdout)

    def test_real_ca_standby_certificate_and_nginx_configs(self):
        with tempfile.TemporaryDirectory(prefix='cn-phase2-tls-') as folder:
            root = Path(folder)
            primary = root / 'Mac 2 - Edge'
            primary.mkdir()
            shutil.copy2(PROJECT / 'Mac 2 - Edge/create_certificate.command', primary)
            (primary / 'settings.env').write_text('DOMAIN=team1.test\n')
            lab = Lab(defaults(), root=root)
            lab.tls('init-primary')
            lab.tls('csr')
            standby = lab.cert_dir('edge-standby')
            lab.tls('sign', standby / 'server.csr', standby / 'server.crt')
            ca = lab.cert_dir('edge-primary') / 'local-ca.crt'
            p = run([binary('openssl'), 'verify', '-CAfile', ca, standby / 'server.crt'])
            self.assertIn('OK', p.stdout)
            text = run([binary('openssl'), 'x509', '-in', standby / 'server.crt', '-noout', '-text']).stdout
            self.assertIn('DNS:app.team1.test', text)
            self.assertIn('DNS:api.team1.test', text)
            certificate_public_key = run([binary('openssl'), 'x509', '-in', standby / 'server.crt', '-noout', '-pubkey']).stdout
            private_public_key = run([binary('openssl'), 'pkey', '-in', standby / 'server.key', '-pubout']).stdout
            self.assertEqual(certificate_public_key, private_public_key)
            with self.assertRaises(RuntimeError):
                lab.tls('init-primary')
            with self.assertRaises(RuntimeError):
                lab.tls('csr')

    def test_real_nginx_configuration_syntax(self):
        with tempfile.TemporaryDirectory(prefix='cn-phase2-nginx-') as folder:
            root = Path(folder)
            primary = root / 'Mac 2 - Edge'
            primary.mkdir()
            shutil.copy2(PROJECT / 'Mac 2 - Edge/create_certificate.command', primary)
            (primary / 'settings.env').write_text('DOMAIN=team1.test\n')
            # nginx -t may bind listeners on macOS. A syntax fixture must not
            # depend on the Phase 1 team's historical LAN addresses or ports.
            c = defaults()
            c.update(mac1='127.0.0.1', mac2='127.0.0.1', mac3='127.0.0.1', mac4='127.0.0.1')
            listeners = []
            try:
                for key in ('https_port', 'standby_https_port'):
                    listener = socket.socket()
                    listeners.append(listener)
                    listener.bind(('127.0.0.1', 0))
                    c[key] = listener.getsockname()[1]
            except PermissionError:
                self.skipTest('Host sandbox blocks selecting local listening ports')
            finally:
                for listener in listeners:
                    listener.close()
            lab = Lab(c, root=root, rehearsal=True)
            lab.tls('init-primary')
            standby = lab.cert_dir('edge-standby')
            standby.mkdir(parents=True)
            for name in ('server.crt', 'server.key'):
                shutil.copy2(lab.cert_dir('edge-primary') / name, standby / name)
            for role in ('edge-primary', 'edge-standby'):
                config = lab.render(role)
                p = run([binary('nginx'), '-t', '-e', 'stderr', '-p', str(config.parent) + '/', '-c', config], check=False)
                if 'sysctlbyname(net.inet.tcp.sendspace) failed (1: Operation not permitted)' in p.stderr:
                    self.skipTest('Host sandbox blocks Nginx OS socket introspection, including nginx -t')
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertIn('test is successful', p.stderr + p.stdout)


class RealIntegration(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('CN_RUN_INTEGRATION') == '1',
                         'Set CN_RUN_INTEGRATION=1 on a host that permits local listening sockets')
    def test_real_dns_tls_failover_cache_and_migration(self):
        results = []
        def passed(name):
            print('PASS:', name, flush=True)
            results.append(name)
        with tempfile.TemporaryDirectory(prefix='cn-phase2-') as tmp:
            root = Path(tmp)
            for folder in ('Mac 3 - Backend A', 'Mac 4 - Backend B', 'Mac 2 - Edge'):
                (root / folder).mkdir()
            for folder, name in [('Mac 3 - Backend A', 'backend_a.py'),
                                 ('Mac 4 - Backend B', 'backend_b.py'),
                                 ('Mac 2 - Edge', 'create_certificate.command')]:
                shutil.copy2(PROJECT / folder / name, root / folder / name)
            (root / 'Mac 2 - Edge/settings.env').write_text('DOMAIN=team1.test\n')
            ports = []
            # Select unused ports for TCP services and both UDP/TCP DNS listeners.
            for _ in range(7):
                while True:
                    with socket.socket() as tcp:
                        tcp.bind(('127.0.0.1', 0)); port = tcp.getsockname()[1]
                    try:
                        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                            udp.bind(('127.0.0.1', port))
                    except OSError:
                        continue
                    if port not in ports:
                        ports.append(port); break
            c = defaults()
            c.update(mac1='127.0.0.1', mac2='127.0.0.1', mac3='127.0.0.1', mac4='127.0.0.1',
                     upstream_dns='127.0.0.1', dns_port=ports[0], backup_dns_port=ports[1],
                     cache_port=ports[2], https_port=ports[3], standby_https_port=ports[4],
                     backend_a_port=ports[5], backend_b_port=ports[6], ttl=30)
            lab = Lab(c, root=root, rehearsal=True)
            lab.tls('init-primary')
            lab.tls('csr')
            lab.tls('sign', lab.cert_dir('edge-standby') / 'server.csr',
                    lab.cert_dir('edge-standby') / 'server.crt')
            ca = lab.cert_dir('edge-primary') / 'local-ca.crt'
            procs, handles = {}, []
            def start(role):
                target = lab.render(role)
                if role.startswith('dns') or role == 'cache':
                    cmd = [binary('dnsmasq'), '--keep-in-foreground', '--conf-file=' + str(target),
                           '--pid-file=' + str(target.parent / 'dnsmasq.pid')]
                elif role.startswith('edge'):
                    cmd = [binary('nginx'), '-p', str(target.parent) + '/', '-c', str(target), '-g', 'daemon off;']
                    run(cmd[:-2] + ['-t'])
                else:
                    folder = 'Mac 3 - Backend A' if role == 'backend-a' else 'Mac 4 - Backend B'
                    name = 'backend_a.py' if role == 'backend-a' else 'backend_b.py'
                    cmd = [sys.executable, '-c',
                           'import os,runpy;os.environ["BACKEND_HOST"]="127.0.0.1";'
                           'os.environ["BACKEND_PORT"]=' + repr(str(lab.role_port(role))) + ';runpy.run_path(' + repr(str(root / folder / name)) + ',run_name="__main__")']
                log = open(lab.runtime / (role + '.log'), 'a'); handles.append(log)
                procs[role] = subprocess.Popen(cmd, stdout=log, stderr=log)
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if procs[role].poll() is not None:
                        log.flush()
                        self.fail(role + ' exited: ' + Path(log.name).read_text())
                    try:
                        with socket.create_connection(('127.0.0.1', lab.role_port(role)), timeout=.1):
                            return
                    except OSError:
                        time.sleep(.05)
                self.fail('Startup timeout: ' + role)
            def stop(role):
                p = procs[role]
                p.terminate()
                try: p.wait(timeout=5)
                except subprocess.TimeoutExpired: p.kill(); p.wait(timeout=3)
            def dns(resolver, tcp=False):
                cmd = lab.dig(resolver) + (['+tcp'] if tcp else [])
                p = run(cmd)
                records = re.findall(r'\S+\s+(\d+)\s+IN\s+A\s+(\d+\.\d+\.\d+\.\d+)', p.stdout)
                return records, p.stdout
            def request(edge):
                p = run(lab.curl(edge, ca=ca))
                self.assertRegex(p.stdout, r'HTTP/1.1 200')
                self.assertIn('Cache-Control:', p.stdout)
                self.assertIn('ETag:', p.stdout)
                self.assertRegex(p.stdout, r'X-Edge: ' + edge)
                return re.search(r'X-Backend: ([AB])', p.stdout).group(1)
            try:
                for role in ('backend-a', 'backend-b', 'dns-primary', 'dns-backup', 'cache',
                             'edge-primary', 'edge-standby'):
                    start(role)
                for resolver in ('primary', 'backup'):
                    for tcp in (False, True):
                        records, _ = dns(resolver, tcp)
                        self.assertEqual(records, [('30', '127.0.0.1')])
                passed('Primary and independent backup DNS answer over UDP and TCP with TTL 30')
                for edge in ('primary', 'standby'):
                    self.assertEqual({request(edge) for _ in range(8)}, {'A', 'B'})
                passed('Both edges serve A/B over HTTPS with the same trusted CA and correct names')
                p = run([binary('curl'), '--noproxy', '*', '-sSI', '--cacert', ca,
                         '--resolve', f"app.team1.test:{c['https_port']}:127.0.0.1",
                         f"https://app.team1.test:{c['https_port']}/api/status"])
                etag = re.search(r'ETag: ([^\r\n]+)', p.stdout).group(1)
                found = False
                for _ in range(4):
                    cmd = lab.curl('primary', ca=ca)
                    p = run(cmd[:-1] + ['-H', 'If-None-Match: ' + etag, cmd[-1]])
                    found |= 'HTTP/1.1 304' in p.stdout
                self.assertTrue(found)
                passed('Original backend ETag conditional HTTP 304 behavior is preserved')
                stop('backend-a')
                for edge in ('primary', 'standby'):
                    self.assertEqual({request(edge) for _ in range(8)}, {'B'})
                passed('Backend A stopped: both edges retry to B with zero failed requests')
                start('backend-a')
                time.sleep(6)
                for edge in ('primary', 'standby'):
                    self.assertEqual({request(edge) for _ in range(8)}, {'A', 'B'})
                passed('Backend A restarted: passive fail_timeout expires and A/B load balancing resumes')
                stop('dns-primary')
                self.assertEqual(dns('backup')[0], [('30', '127.0.0.1')])
                failed = run(lab.dig('primary'), check=False)
                self.assertNotEqual(failed.returncode, 0)
                passed('Primary DNS stopped: backup still resolves project domain')
                start('dns-primary')
                self.assertEqual(dns('cache')[0], [('30', '127.0.0.1')])
                # Use a distinct loopback answer to prove a real DNS record change.
                records = lab.runtime / 'dns-primary/records.hosts'
                records.write_text('127.0.0.2 app.team1.test api.team1.test\n')
                # SIGHUP rereads addn-hosts, unlike address= configuration directives.
                import signal
                procs['dns-primary'].send_signal(signal.SIGHUP)
                time.sleep(.2)
                self.assertEqual(dns('primary')[0][0][1], '127.0.0.2')
                self.assertEqual(dns('cache')[0][0][1], '127.0.0.1')
                passed('After record change: source DNS serves new IP while real caching resolver serves old IP')
                deadline = time.monotonic() + 33
                while time.monotonic() < deadline:
                    answer, _ = dns('cache')
                    if answer and answer[0][1] == '127.0.0.2': break
                    time.sleep(1)
                self.assertEqual(answer[0][1], '127.0.0.2')
                passed('Real 30-second DNS TTL expiry refreshes cached old IP to new IP')
                records.write_text('127.0.0.3 app.team1.test api.team1.test\n')
                procs['dns-primary'].send_signal(signal.SIGHUP); time.sleep(.2)
                self.assertEqual(dns('cache')[0][0][1], '127.0.0.2')
                procs['cache'].send_signal(signal.SIGHUP); time.sleep(.2)
                self.assertEqual(dns('cache')[0][0][1], '127.0.0.3')
                passed('Flushing the actual dnsmasq cache immediately fetches the changed answer')
                # Stop old edge and prove the already configured standby independently serves HTTPS.
                stop('edge-primary')
                self.assertEqual({request('standby') for _ in range(8)}, {'A', 'B'})
                passed('Original edge stopped: standby independently serves both backends over valid HTTPS')
                stop('backend-a'); stop('backend-b')
                p = run(lab.curl('standby', ca=ca))
                self.assertRegex(p.stdout, r'HTTP/1.1 502')
                passed('Both backends stopped: TLS still validates and Nginx returns HTTP 502')
                record = dict(scope='One Mac loopback rehearsal using real dnsmasq, Nginx, Python and OpenSSL. '
                                    'Not four-Mac LAN, OS resolver failover, pf enforcement or natural DNS cutover evidence.',
                              passed=results, physical_tests_pending=['Cross-Mac pf isolation and rollback',
                              'Client OS resolver failover with packet evidence', 'Natural DNS edge cutover and macOS cache flush'])
                target = PROJECT / 'Phase2/LOCAL_TEST_RESULTS.json'
                target.write_text(json.dumps(record, indent=2) + '\n')
            finally:
                for role, p in procs.items():
                    if p.poll() is None: stop(role)
                for log in handles: log.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
