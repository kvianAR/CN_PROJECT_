#!/usr/bin/env python3
"""Phase 2 tools for the existing four-Mac CN project. Python standard library only."""
import argparse
import datetime as dt
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]
BASELINE = '52a46de198702b146ec60a2e5d6398dc92ab0def'
ROLES = ('dns-primary', 'dns-backup', 'edge-primary', 'edge-standby', 'backend-a', 'backend-b', 'cache')


def env_file(path):
    result = {}
    for line in path.read_text().splitlines():
        line = line.split('#', 1)[0].strip()
        if '=' in line:
            k, v = line.split('=', 1)
            result[k.strip()] = v.strip()
    return result


def defaults(root=PROJECT):
    # Phase 2 owns its deployment addresses. Reading its template first avoids
    # inheriting historical Phase 1 IPs on a fresh clone or reconfiguration.
    template = root / 'Phase2/site.example.json'
    if template.exists():
        return validate(json.loads(template.read_text()))
    # Compatibility for a Phase 1-only export that has no Phase 2 template yet.
    dns = env_file(root / 'Mac 1 - DNS/settings.env')
    edge = env_file(root / 'Mac 2 - Edge/settings.env')
    return dict(domain=dns['DOMAIN'], mac1=dns['MAC1_IP'], mac2=edge['MAC2_IP'],
                mac3=edge['MAC3_IP'], mac4=edge['MAC4_IP'], upstream_dns=dns['UPSTREAM_DNS'],
                interface='en0', dns_port=53, backup_dns_port=53, cache_port=1053,
                https_port=int(edge['HTTPS_PORT']), standby_https_port=int(edge['HTTPS_PORT']),
                backend_a_port=3001, backend_b_port=3002, ttl=30, active_edge='primary')


def validate(c, rehearsal=False):
    if not isinstance(c, dict):
        raise ValueError('Configuration must be a JSON object')
    required = {'domain', 'mac1', 'mac2', 'mac3', 'mac4', 'upstream_dns', 'interface',
                'dns_port', 'backup_dns_port', 'cache_port', 'https_port',
                'standby_https_port', 'backend_a_port', 'backend_b_port', 'ttl', 'active_edge'}
    missing = required - c.keys()
    if missing:
        raise ValueError('Missing configuration fields: ' + ', '.join(sorted(missing)))
    for key in ('mac1', 'mac2', 'mac3', 'mac4', 'upstream_dns'):
        ip = ipaddress.IPv4Address(c[key])
        if ip.is_unspecified or ip.is_multicast or ip == ipaddress.IPv4Address('255.255.255.255'):
            raise ValueError('Invalid service IPv4: ' + key)
        if not rehearsal and key != 'upstream_dns' and ip.is_loopback:
            raise ValueError('Physical machine addresses cannot be loopback: ' + key)
    if not rehearsal and len({c[k] for k in ('mac1', 'mac2', 'mac3', 'mac4')}) != 4:
        raise ValueError('Four-Mac deployment requires four distinct IPv4 addresses')
    if (not isinstance(c['domain'], str) or len(c['domain']) > 253 or
            not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+test', c['domain'])):
        raise ValueError('Use a valid lowercase .test domain')
    if not re.fullmatch(r'[a-z][a-z0-9]{0,15}', c['interface']):
        raise ValueError('Invalid network interface')
    for key in ('dns_port', 'backup_dns_port', 'cache_port', 'https_port', 'standby_https_port',
                'backend_a_port', 'backend_b_port'):
        if type(c[key]) is not int or not 1 <= c[key] <= 65535:
            raise ValueError('Invalid port: ' + key)
    if type(c['ttl']) is not int or not 1 <= c['ttl'] <= 3600:
        raise ValueError('TTL must be an integer from 1 to 3600')
    if c['active_edge'] not in ('primary', 'standby'):
        raise ValueError('active_edge must be primary or standby')
    if not rehearsal:
        if c['dns_port'] != 53 or c['backup_dns_port'] != 53:
            raise ValueError('Physical client DNS settings require port 53 on both resolvers')
        if c['https_port'] != c['standby_https_port']:
            raise ValueError('Physical edges must use the same HTTPS port: DNS cannot change URL ports')
        if c['standby_https_port'] == c['backend_a_port']:
            raise ValueError('Standby edge and Backend A share Mac 3; choose different TCP ports')
        if c['backup_dns_port'] == c['backend_b_port']:
            raise ValueError('Backup DNS and Backend B share Mac 4; choose different TCP ports')
        if c['upstream_dns'] in (c['mac1'], c['mac4']):
            raise ValueError('Ordinary DNS upstream must not point back to either project resolver')
    return c


def binary(name):
    paths = [shutil.which(name), '/opt/homebrew/bin/' + name, '/opt/homebrew/sbin/' + name,
             '/usr/local/bin/' + name, '/usr/local/sbin/' + name, '/sbin/' + name, '/usr/sbin/' + name]
    for path in paths:
        if path and os.access(path, os.X_OK):
            return path
    raise RuntimeError('Missing ' + name + '. Install required tools using Homebrew.')


def run(command, check=True, timeout=20, **kwargs):
    p = subprocess.run([str(x) for x in command], capture_output=True, text=True,
                       timeout=timeout, **kwargs)
    if check and p.returncode:
        raise RuntimeError(shlex.join([str(x) for x in command]) + '\n' + p.stdout + p.stderr)
    return p


def write(path, text, private=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.new')
    temporary.write_text(text)
    if private:
        temporary.chmod(0o600)
    temporary.replace(path)


def nginx_quote(path):
    return '"' + str(path).replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$') + '"'


class Lab:
    def __init__(self, config, root=PROJECT, runtime=None, rehearsal=False):
        self.c = validate(config.copy(), rehearsal)
        self.root = Path(root).resolve()
        self.runtime = Path(runtime or self.root / 'Phase2/runtime').resolve()
        self.runtime.mkdir(parents=True, exist_ok=True)

    def role_ip(self, role):
        return self.c[{'dns-primary': 'mac1', 'dns-backup': 'mac4', 'edge-primary': 'mac2',
                       'edge-standby': 'mac3', 'backend-a': 'mac3', 'backend-b': 'mac4'}[role]]

    def role_port(self, role):
        return self.c[{'dns-primary': 'dns_port', 'dns-backup': 'backup_dns_port', 'cache': 'cache_port',
                       'edge-primary': 'https_port', 'edge-standby': 'standby_https_port',
                       'backend-a': 'backend_a_port', 'backend-b': 'backend_b_port'}[role]]

    def cert_dir(self, role):
        return (self.root / 'Mac 2 - Edge/certs' if role == 'edge-primary'
                else self.root / 'Phase2/certs/standby')

    def dns_config(self, role):
        c = self.c
        folder = self.runtime / role
        folder.mkdir(parents=True, exist_ok=True)
        if role == 'cache':
            return f'''# Client-side caching resolver; no system DNS settings are changed.
port={c['cache_port']}
pid-file={folder / 'dnsmasq.pid'}
listen-address=127.0.0.1
bind-interfaces
no-resolv
no-hosts
server=/{c['domain']}/{c['mac1']}#{c['dns_port']}
local=/#/
cache-size=100
no-negcache
log-queries
log-facility=-
'''
        active = c['mac2'] if c['active_edge'] == 'primary' else c['mac3']
        write(folder / 'records.hosts', f"{active} app.{c['domain']} api.{c['domain']}\n")
        return f'''# Same project records on primary and independent backup DNS.
port={self.role_port(role)}
pid-file={folder / 'dnsmasq.pid'}
listen-address=127.0.0.1,{self.role_ip(role)}
bind-interfaces
no-resolv
no-hosts
server={c['upstream_dns']}
domain-needed
local=/{c['domain']}/
addn-hosts={folder / 'records.hosts'}
local-ttl={c['ttl']}
log-queries
log-facility=-
'''

    def edge_config(self, role):
        c = self.c
        folder = self.runtime / role
        folder.mkdir(parents=True, exist_ok=True)
        certs = self.cert_dir(role)
        identity = 'primary' if role == 'edge-primary' else 'standby'
        # Explicit source binding makes the pf allowlist independent of route selection.
        return f'''# Phase 2 standalone Nginx. Original Phase 1 config is preserved.
worker_processes 1;
pid {nginx_quote(folder / 'nginx.pid')};
error_log {nginx_quote(folder / 'error.log')} info;
events {{ worker_connections 512; }}
http {{
    log_format phase2 '$time_iso8601 client=$remote_addr edge={identity} '
                      'status=$status upstream=$upstream_addr upstream_status=$upstream_status '
                      'connect=$upstream_connect_time response=$upstream_response_time';
    access_log {nginx_quote(folder / 'access.log')} phase2;
    client_body_temp_path {nginx_quote(folder / 'client_temp')};
    proxy_temp_path {nginx_quote(folder / 'proxy_temp')};
    upstream backend_pool {{
        server {c['mac3']}:{c['backend_a_port']} max_fails=1 fail_timeout=5s;
        server {c['mac4']}:{c['backend_b_port']} max_fails=1 fail_timeout=5s;
    }}
    server {{
        listen {self.role_ip(role)}:{self.role_port(role)} ssl;
        server_name app.{c['domain']} api.{c['domain']};
        ssl_certificate {nginx_quote(certs / 'server.crt')};
        ssl_certificate_key {nginx_quote(certs / 'server.key')};
        ssl_protocols TLSv1.2 TLSv1.3;
        add_header X-Edge {identity} always;
        location / {{
            proxy_pass http://backend_pool;
            proxy_bind {self.role_ip(role)};
            proxy_http_version 1.1;
            proxy_set_header Connection "";
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto https;
            proxy_next_upstream error timeout invalid_header http_502 http_503 http_504;
            proxy_next_upstream_tries 2;
            proxy_next_upstream_timeout 15s;
            proxy_connect_timeout 2s;
            proxy_send_timeout 5s;
            proxy_read_timeout 5s;
        }}
    }}
}}
'''

    def reload_dns(self, role):
        folder = self.runtime / role
        pid = int((folder / 'dnsmasq.pid').read_text().strip())
        if pid <= 1:
            raise RuntimeError('Invalid DNS PID; no signal sent.')
        command = run([binary('ps'), '-p', str(pid), '-o', 'command=']).stdout
        if 'dnsmasq' not in command or '--conf-file=' + str(folder / 'dnsmasq.conf') not in command:
            raise RuntimeError('PID does not belong to this DNS configuration; no signal sent.')
        sudo = [] if os.geteuid() == 0 else [binary('sudo')]
        run(sudo + [binary('kill'), '-HUP', str(pid)])
        print('Reloaded hosts records and flushed this dnsmasq cache:', role)

    def render(self, role):
        folder = self.runtime / role
        folder.mkdir(parents=True, exist_ok=True)
        if role.startswith('dns') or role == 'cache':
            target = folder / 'dnsmasq.conf'
            write(target, self.dns_config(role))
        elif role.startswith('edge'):
            target = folder / 'nginx.conf'
            write(target, self.edge_config(role))
        else:
            target = folder / 'settings.env'
            write(target, f'BACKEND_HOST=0.0.0.0\nBACKEND_PORT={self.role_port(role)}\n')
        return target

    def serve(self, role):
        if role != 'cache':
            self.require_local_role(role)
        target = self.render(role)
        if role.startswith('dns') or role == 'cache':
            cmd = [binary('dnsmasq'), '--keep-in-foreground', '--conf-file=' + str(target)]
            run([binary('dnsmasq'), '--test', '--conf-file=' + str(target)])
            if self.role_port(role) < 1024 and os.geteuid() != 0:
                cmd.insert(0, binary('sudo'))
            env = None
        elif role.startswith('edge'):
            cmd = [binary('nginx'), '-e', 'stderr', '-p', str(target.parent) + '/', '-c', str(target)]
            run(cmd + ['-t'])
            cmd += ['-g', 'daemon off;']
            env = None
        else:
            letter = 'a' if role == 'backend-a' else 'b'
            folder = 'Mac 3 - Backend A' if letter == 'a' else 'Mac 4 - Backend B'
            cmd = [sys.executable, str(self.root / folder / ('backend_' + letter + '.py'))]
            env = dict(os.environ, BACKEND_HOST='0.0.0.0', BACKEND_PORT=str(self.role_port(role)))
        print('Foreground service; Ctrl+C stops only this service.\n' + shlex.join(cmd), flush=True)
        # A foreground child shares the terminal's SIGINT. Never kill unrelated processes by name.
        try:
            return subprocess.call(cmd, env=env)
        except KeyboardInterrupt:
            return 130

    def require_local_role(self, role):
        info = run([binary('ifconfig'), self.c['interface']]).stdout
        addresses = re.findall(r'\binet\s+(\d+\.\d+\.\d+\.\d+)\b', info)
        if self.role_ip(role) not in addresses:
            raise RuntimeError(f"{role} expects {self.role_ip(role)} on {self.c['interface']}. "
                               'Update site.json or run this role on its assigned Mac.')

    def firewall_rules(self, backend, standby=False):
        c = self.c
        host = c['mac3'] if backend == 'a' else c['mac4']
        edges = c['mac2'] + (', ' + c['mac3'] if standby else '')
        return f'''# Loaded under the existing com.apple/* filter anchor. No global pf.conf rewrite.
pass in quick on {c['interface']} inet proto tcp from {{ {edges} }} to {host} port {{ {c['backend_a_port']}, {c['backend_b_port']} }} flags S/SA keep state
block drop in quick on {c['interface']} inet proto tcp from any to {host} port {{ {c['backend_a_port']}, {c['backend_b_port']} }}
block drop in quick on {c['interface']} inet6 proto tcp from any to any port {{ {c['backend_a_port']}, {c['backend_b_port']} }}
'''

    def firewall(self, action, backend, standby=False):
        folder = self.runtime / 'firewall'
        folder.mkdir(parents=True, exist_ok=True)
        folder.chmod(0o700)
        rules = folder / ('backend-' + backend + '.pf')
        if action == 'render':
            write(rules, self.firewall_rules(backend, standby))
            print(rules)
            print(rules.read_text())
            return
        pf = binary('pfctl')
        sudo = [] if os.geteuid() == 0 else [binary('sudo')]
        def call(*args, **kw):
            return run(sudo + [pf, *args], **kw)
        state = folder / 'active.json'
        anchor = 'com.apple/cn_phase2'
        if action == 'status':
            print(call('-s', 'info').stdout)
            print(call('-a', anchor, '-v', '-s', 'rules').stdout)
            return
        if action == 'restore':
            if not state.exists():
                raise RuntimeError('No saved firewall session; refusing to guess previous rules.')
            saved = json.loads(state.read_text())
            call('-a', anchor, '-f', saved['prior_rules'])
            # Release only our enable reference, never globally disable PF.
            if saved.get('token'):
                call('-X', saved['token'])
            state.rename(folder / ('restored-' + str(time.time_ns()) + '.json'))
            print('Restored previous project anchor; released only this session\'s PF reference.')
            return
        if state.exists():
            raise RuntimeError('An active session exists. Restore before applying another rule set.')
        self.require_local_role('backend-' + backend)
        root_rules = call('-s', 'rules').stdout
        if not re.search(r'anchor "com\.apple/\*"', root_rules):
            raise RuntimeError('Active root rules do not call com.apple/*. No changes made. Consult faculty.')
        previously_enabled = bool(re.search(r'Status:\s+Enabled', call('-s', 'info').stdout))
        stamp = str(time.time_ns())
        backup = folder / ('backup-' + stamp)
        backup.mkdir(mode=0o700)
        write(backup / 'root-rules.txt', root_rules)
        prior = call('-a', anchor, '-s', 'rules').stdout
        prior_path = backup / 'anchor.pf'
        write(prior_path, prior)
        shutil.copy2('/etc/pf.conf', backup / 'pf.conf')
        write(rules, self.firewall_rules(backend, standby))
        call('-n', '-a', anchor, '-f', str(rules))
        saved = dict(anchor=anchor, prior_rules=str(prior_path), token=None,
                     previously_enabled=previously_enabled, backend=backend)
        write(state, json.dumps(saved, indent=2), private=True)
        try:
            # An already enabled firewall needs no additional enable reference.
            # This preserves its pre-existing enable state on project rollback.
            if not previously_enabled:
                enabled = call('-E')
                match = re.search(r'Token\s*:\s*(\d+)', enabled.stdout + enabled.stderr)
                if not match:
                    raise RuntimeError('PF returned no enable token. Saved rules retained; inspect pfctl status.')
                saved['token'] = match.group(1)
                write(state, json.dumps(saved, indent=2), private=True)
            call('-a', anchor, '-f', str(rules))
        except Exception:
            call('-a', anchor, '-f', str(prior_path), check=False)
            if saved.get('token'):
                released = call('-X', saved['token'], check=False)
                if released.returncode == 0:
                    saved['token'] = None
                    write(state, json.dumps(saved, indent=2), private=True)
            # Keep active.json for inspection/recovery after a partial failure.
            raise
        print('Applied project rules. Use new TCP connections for tests; existing states are preserved.')
        print('Rollback: python3 Phase2/cn.py firewall restore --backend ' + backend)

    def tls(self, action, csr=None, output=None):
        primary = self.cert_dir('edge-primary')
        standby = self.cert_dir('edge-standby')
        openssl = binary('openssl')
        domain = self.c['domain']
        if action == 'init-primary':
            settings = env_file(self.root / 'Mac 2 - Edge/settings.env')
            if settings['DOMAIN'] != domain:
                raise RuntimeError('Phase 1 DOMAIN differs from Phase 2. Align settings before issuing certificates.')
            if any((primary / n).exists() for n in ('local-ca.key', 'server.key')):
                raise RuntimeError('Existing TLS material preserved. Use it; do not regenerate the CA.')
            p = run([binary('zsh'), self.root / 'Mac 2 - Edge/create_certificate.command'])
            print(p.stdout)
        elif action == 'csr':
            standby.mkdir(parents=True, exist_ok=True)
            key = standby / 'server.key'
            request = standby / 'server.csr'
            if key.exists() or request.exists():
                raise RuntimeError('Standby key/CSR already exists; preserved.')
            run([openssl, 'genrsa', '-out', key, '2048'])
            key.chmod(0o600)
            run([openssl, 'req', '-new', '-key', key, '-out', request,
                 '-subj', '/CN=app.' + domain])
            print('Send only this public CSR to Mac 2:', request)
        elif action == 'sign':
            request, output = Path(csr).resolve(), Path(output).resolve()
            if output.exists():
                raise RuntimeError('Output certificate already exists; preserved.')
            extensions = self.runtime / 'standby-server.ext'
            write(extensions, f'basicConstraints=critical,CA:FALSE\nsubjectAltName=DNS:app.{domain},DNS:api.{domain}\nextendedKeyUsage=serverAuth\nkeyUsage=digitalSignature,keyEncipherment\n')
            run([openssl, 'req', '-in', request, '-verify', '-noout'])
            output.parent.mkdir(parents=True, exist_ok=True)
            run([openssl, 'x509', '-req', '-in', request, '-CA', primary / 'local-ca.crt',
                 '-CAkey', primary / 'local-ca.key', '-CAserial', self.runtime / 'standby-ca.srl',
                 '-CAcreateserial', '-out', output, '-days', '365', '-sha256', '-extfile', extensions])
            run([openssl, 'verify', '-CAfile', primary / 'local-ca.crt', output])
            print('Return only the signed certificate and public local-ca.crt to Mac 3:', output)

    def curl(self, edge=None, host=None, ca=None):
        c = self.c
        host = host or 'app.' + c['domain']
        port = c['standby_https_port'] if edge == 'standby' else c['https_port']
        if edge is None and c['active_edge'] == 'standby':
            port = c['standby_https_port']
        cmd = [binary('curl'), '--noproxy', '*', '--silent', '--show-error', '--http1.1',
               '--connect-timeout', '3', '--max-time', '18', '--dump-header', '-', '--output', '/dev/null']
        if ca:
            cmd += ['--cacert', str(ca)]
        if edge:
            ip = c['mac2'] if edge == 'primary' else c['mac3']
            cmd += ['--resolve', f'{host}:{port}:{ip}']
        return cmd + [f'https://{host}:{port}/api/status']

    def dig(self, resolver, host=None):
        if resolver == 'cache':
            ip, port = '127.0.0.1', self.c['cache_port']
        else:
            role = 'dns-primary' if resolver == 'primary' else 'dns-backup'
            ip, port = self.role_ip(role), self.role_port(role)
        return [binary('dig'), '@' + ip, '-p', str(port), host or 'app.' + self.c['domain'],
                'A', '+time=2', '+tries=1', '+noall', '+answer', '+comments', '+stats']

    def verify(self, mode, ca=None, count=12):
        checks = []
        def check(name, cmd, predicate):
            try:
                p = run(cmd, check=False, timeout=22)
                result = dict(name=name, command=shlex.join([str(x) for x in cmd]),
                              returncode=p.returncode, output=p.stdout + p.stderr)
                result['pass'] = bool(predicate(p))
            except (OSError, subprocess.TimeoutExpired) as e:
                result = dict(name=name, command=str(cmd), output=str(e), returncode=-1, **{'pass': False})
            checks.append(result)
            print(('PASS ' if result['pass'] else 'FAIL ') + name)
            print(result['output'].strip())
            return result
        expected = self.c['mac2'] if self.c['active_edge'] == 'primary' else self.c['mac3']
        def answer_ok(p):
            return p.returncode == 0 and bool(re.search(r'\sIN\s+A\s+' + re.escape(expected) + r'\s*$', p.stdout, re.M))
        if mode in ('baseline', 'dns-records', 'dns-backup'):
            for resolver in ('primary', 'backup'):
                for label in ('app', 'api'):
                    name = label + '.' + self.c['domain']
                    if mode == 'dns-backup' and resolver == 'primary':
                        check('Primary DNS is stopped: ' + name, self.dig(resolver, name), lambda p: p.returncode != 0)
                    else:
                        check(resolver + ' DNS correct answer: ' + name, self.dig(resolver, name), answer_ok)
        if mode in ('baseline', 'balanced', 'b-only', 'migrated', 'dns-backup'):
            seen = set()
            for i in range(count):
                def valid(p):
                    backend = re.search(r'^X-Backend:\s*([AB])\s*$', p.stdout, re.I | re.M)
                    edge = re.search(r'^X-Edge:\s*(primary|standby)\s*$', p.stdout, re.I | re.M)
                    if backend:
                        seen.add(backend.group(1))
                    return p.returncode == 0 and bool(re.search(r'^HTTP/1\.1 200', p.stdout, re.M)) and bool(backend) and bool(edge) and (mode != 'b-only' or backend.group(1) == 'B') and (mode != 'migrated' or edge.group(1) == 'standby')
                # Natural OS DNS path is intentional: --resolve would hide a failed DNS cutover.
                check('HTTPS request ' + str(i + 1), self.curl(ca=ca), valid)
            if mode in ('baseline', 'balanced', 'migrated'):
                checks.append(dict(name='Both backends observed', output=','.join(sorted(seen)), **{'pass': seen == {'A', 'B'}}))
        if mode in ('firewall-client', 'firewall-edge'):
            for role in ('backend-a', 'backend-b'):
                ip, port = self.role_ip(role), self.role_port(role)
                cmd = [binary('nc'), '-z', '-G', '3', ip, str(port)]
                wanted = mode == 'firewall-edge'
                check(role + (' reachable from edge' if wanted else ' blocked from client'), cmd,
                      lambda p, wanted=wanted: (p.returncode == 0) == wanted)
            check('Application through domain remains usable', self.curl(ca=ca),
                  lambda p: p.returncode == 0 and 'HTTP/1.1 200' in p.stdout)
        okay = all(item['pass'] for item in checks)
        folder = self.root / 'Evidence/Phase2'
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ') + '-' + mode + '.json')
        record = dict(time_utc=dt.datetime.now(dt.timezone.utc).isoformat(), host=socket.gethostname(),
                      baseline=BASELINE, mode=mode, overall_pass=okay, checks=checks,
                      scope='Live commands on this host; attach packet evidence and physical-machine details separately.')
        write(path, json.dumps(record, indent=2))
        print(('PASS' if okay else 'FAIL') + ' overall. Evidence: ' + str(path))
        return 0 if okay else 1

    def diagnose(self, ca=None, origin='client'):
        print('DNS first; then TCP; then TLS/HTTPS; then upstream. Failures are observations, not repairs.')
        commands = [['scutil', '--dns'], self.dig('primary'), self.dig('backup')]
        for role in ('edge-primary', 'edge-standby'):
            commands.append([binary('nc'), '-z', '-G', '3', self.role_ip(role), str(self.role_port(role))])
        commands += [self.curl(ca=ca), self.curl('primary', ca=ca), self.curl('standby', ca=ca)]
        if origin == 'edge':
            for role in ('backend-a', 'backend-b'):
                commands.append([binary('curl'), '--noproxy', '*', '-i', '--max-time', '5',
                                 f'http://{self.role_ip(role)}:{self.role_port(role)}/api/status'])
        else:
            print('Direct backend denial is expected from a client after isolation.')
        lines = []
        for cmd in commands:
            try:
                p = run(cmd, check=False, timeout=22)
                text = '$ ' + shlex.join(cmd) + '\nexit=' + str(p.returncode) + '\n' + p.stdout + p.stderr
            except (OSError, subprocess.TimeoutExpired) as e:
                text = '$ ' + shlex.join(cmd) + '\n' + str(e)
            print(text)
            lines.append(text)
        path = self.root / 'Evidence/Phase2' / ('diagnose-' + str(time.time_ns()) + '.txt')
        write(path, '\n\n'.join(lines))
        print('Saved:', path)


def client_dns(lab, action, service):
    """Back up and restore the service's exact manual DNS list; empty restores DHCP."""
    tool = binary('networksetup')
    file = lab.runtime / 'client-dns.json'
    if action == 'show':
        print(run([tool, '-getdnsservers', service]).stdout)
        return
    sudo = [] if os.geteuid() == 0 else [binary('sudo')]
    if action == 'apply':
        if file.exists():
            raise RuntimeError('Existing DNS backup preserved. Restore before applying again.')
        p = run([tool, '-getdnsservers', service])
        lines = [x.strip() for x in p.stdout.splitlines() if x.strip()]
        if len(lines) == 1 and 'aren\'t any DNS Servers' in lines[0]:
            previous = []
        else:
            previous = [str(ipaddress.ip_address(x)) for x in lines]
        write(file, json.dumps(dict(service=service, previous=previous)), private=True)
        run(sudo + [tool, '-setdnsservers', service, lab.c['mac1'], lab.c['mac4']])
    else:
        saved = json.loads(file.read_text())
        run(sudo + [tool, '-setdnsservers', saved['service'], *(saved['previous'] or ['Empty'])])
        file.rename(file.with_name('client-dns-restored-' + str(time.time_ns()) + '.json'))
    print(run([tool, '-getdnsservers', service]).stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=PROJECT / 'Phase2/site.json')
    sub = parser.add_subparsers(dest='command', required=True)
    setup = sub.add_parser('configure', help='Create Phase 2 settings from its template; override LAN addresses.')
    for k in ('mac1', 'mac2', 'mac3', 'mac4', 'upstream-dns', 'interface', 'domain'):
        setup.add_argument('--' + k)
    for k in ('ttl', 'https-port'):
        setup.add_argument('--' + k, type=int)
    render = sub.add_parser('render')
    render.add_argument('role', choices=ROLES + ('all',))
    serve = sub.add_parser('run')
    serve.add_argument('role', choices=ROLES)
    cut = sub.add_parser('set-edge')
    cut.add_argument('edge', choices=('primary', 'standby'))
    firewall = sub.add_parser('firewall')
    firewall.add_argument('action', choices=('render', 'apply', 'status', 'restore'))
    firewall.add_argument('--backend', choices=('a', 'b'), required=True)
    firewall.add_argument('--allow-standby', action='store_true')
    tls = sub.add_parser('tls')
    tls.add_argument('action', choices=('init-primary', 'csr', 'sign'))
    tls.add_argument('--csr', type=Path)
    tls.add_argument('--out', type=Path)
    dns = sub.add_parser('client-dns')
    dns.add_argument('action', choices=('show', 'apply', 'restore'))
    dns.add_argument('--service', default='Wi-Fi')
    query = sub.add_parser('query')
    query.add_argument('resolver', choices=('primary', 'backup', 'cache'))
    reload_dns = sub.add_parser('reload-dns')
    reload_dns.add_argument('role', choices=('dns-primary', 'dns-backup', 'cache'))
    capture = sub.add_parser('capture')
    capture.add_argument('--interface', required=True, help='Use en0 for LAN or lo0 for local traffic.')
    flush = sub.add_parser('flush-os-cache')
    verify = sub.add_parser('verify')
    verify.add_argument('mode', choices=('baseline', 'dns-records', 'dns-backup', 'balanced', 'b-only',
                                        'migrated', 'firewall-client', 'firewall-edge'))
    verify.add_argument('--ca', type=Path)
    verify.add_argument('--count', type=int, default=12)
    diag = sub.add_parser('diagnose')
    diag.add_argument('--ca', type=Path)
    diag.add_argument('--from-role', choices=('client', 'edge'), default='client')
    sub.add_parser('inventory')
    args = parser.parse_args()
    if args.command == 'configure':
        c = json.loads(args.config.read_text()) if args.config.exists() else defaults()
        for k in c:
            if getattr(args, k, None) is not None:
                c[k] = getattr(args, k)
        if args.https_port is not None:
            c['standby_https_port'] = args.https_port
        validate(c)
        write(args.config, json.dumps(c, indent=2) + '\n')
        print('Saved', args.config)
        print('Copy this same site.json to all four Macs. Verify current IPs before starting services.')
        return 0
    if not args.config.exists():
        raise RuntimeError('Run configure first. Phase 1 files are left unchanged.')
    lab = Lab(json.loads(args.config.read_text()))
    c = lab.c
    if args.command == 'render':
        for role in ROLES if args.role == 'all' else (args.role,):
            print(lab.render(role))
    elif args.command == 'run':
        return lab.serve(args.role)
    elif args.command == 'set-edge':
        c['active_edge'] = args.edge
        write(args.config, json.dumps(c, indent=2) + '\n')
        for role in ('dns-primary', 'dns-backup'):
            lab.render(role)
        print('Records updated on this copy only. Repeat on BOTH DNS Macs, then restart their DNS services.')
        print('Keep old edge running for at least TTL plus a grace period. Existing HTTPS sessions may live longer.')
    elif args.command == 'firewall':
        lab.firewall(args.action, args.backend, args.allow_standby)
    elif args.command == 'tls':
        if args.action == 'sign' and (not args.csr or not args.out):
            parser.error('tls sign requires --csr and --out')
        lab.tls(args.action, args.csr, args.out)
    elif args.command == 'client-dns':
        client_dns(lab, args.action, args.service)
    elif args.command == 'query':
        p = run(lab.dig(args.resolver), check=False)
        print(p.stdout + p.stderr)
        return p.returncode
    elif args.command == 'reload-dns':
        lab.reload_dns(args.role)
    elif args.command == 'capture':
        if not re.fullmatch(r'[a-z][a-z0-9]{0,15}', args.interface):
            parser.error('Invalid capture interface')
        target = lab.root / 'Evidence/Phase2' / ('capture-' + str(time.time_ns()) + '.pcap')
        target.parent.mkdir(parents=True, exist_ok=True)
        hosts = ' or '.join('host ' + c[k] for k in ('mac1', 'mac2', 'mac3', 'mac4'))
        ports = ' or '.join('port ' + str(c[k]) for k in ('dns_port', 'backup_dns_port',
                           'https_port', 'standby_https_port', 'backend_a_port', 'backend_b_port'))
        cmd = [binary('sudo'), binary('tcpdump'), '-i', args.interface, '-s', '0', '-U', '-w',
               str(target), '(' + hosts + ') and (' + ports + ')']
        print('Capture started. Ctrl+C saves and closes:', target, flush=True)
        try:
            return subprocess.call(cmd)
        except KeyboardInterrupt:
            return 130
    elif args.command == 'flush-os-cache':
        run([binary('sudo'), binary('dscacheutil'), '-flushcache'])
        run([binary('sudo'), binary('killall'), '-HUP', 'mDNSResponder'])
        print('macOS DNS cache flushed. The optional dnsmasq cache is separate; restart its terminal to flush it.')
    elif args.command == 'verify':
        if not 2 <= args.count <= 100:
            parser.error('--count must be 2..100')
        return lab.verify(args.mode, args.ca, args.count)
    elif args.command == 'diagnose':
        lab.diagnose(args.ca, args.from_role)
    elif args.command == 'inventory':
        for role in ROLES:
            ip = '127.0.0.1' if role == 'cache' else lab.role_ip(role)
            print(f'{role:15} {ip:15} port={lab.role_port(role)}')
        for cmd in (['networksetup', '-listallhardwareports'], ['ifconfig', c['interface']],
                    ['route', '-n', 'get', 'default']):
            print(run(cmd, check=False).stdout)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, KeyError, RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        print('ERROR:', error, file=sys.stderr)
        sys.exit(1)
