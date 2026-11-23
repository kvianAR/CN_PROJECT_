# Phase 2 — Harden, Recover and Troubleshoot

This extends the exact final Phase 1 commit `52a46de198702b146ec60a2e5d6398dc92ab0def`.
Original Phase 1 application/configuration files and evidence remain in this single repository.
The machine guides are refreshed; backends are reused, not rewritten. There are no Python package dependencies. Install Python 3, dnsmasq, Nginx,
OpenSSL and zsh. On Macs, use Homebrew for missing tools.

[Project overview](../README.md) · [Stepwise quick start](QUICKSTART_HI.md) · [Evidence](../Evidence/README.md) · [Report](REPORT.md)

## Start with your goal

| Goal | Go to |
|---|---|
| Prepare machines and shared settings | [Configuration and startup](#1-configuration-and-startup) |
| Configure trusted primary/standby HTTPS | [TLS setup](#2-preserve-certificate-trust-and-issue-the-standby-certificate) |
| Demonstrate backup DNS | [Demo A](#demonstration-a--independent-backup-dns) |
| Demonstrate TTL, expiry and flushing | [Demo B](#demonstration-b--real-dns-ttl-cache-expiry-and-cache-flush) |
| Restrict direct backend access | [Demo C](#demonstration-c--backend-service-isolation-with-rollback) |
| Stop and recover a backend | [Demo D](#demonstration-d--backend-failure-and-recovery) |
| Move traffic to the standby edge | [Demo E](#demonstration-e--controlled-edge-migration) |
| Diagnose an injected fault | [Demo F](#demonstration-f--troubleshooting) |
| Save results and restore settings | [Evidence](#evidence-and-tests) · [Rollback](#restore-the-demonstration-network) |

## Verification status

The saved macOS local run passed **6/6 tests without skips**. Its source hashes match the current
implementation. It covers independent DNS, UDP/TCP queries, real 30-second cache expiry/flush,
trusted TLS on both edges, A/B balancing, backend failure/recovery, HTTP 304 and upstream HTTP 502.

- [Complete test summary](../Evidence/Phase2/20261123T043836.040132Z-full-test-summary.json)
- [Full execution transcript](../Evidence/Phase2/20261123T043836.040132Z-full-test-transcript.txt)
- [Eleven service findings](LOCAL_TEST_RESULTS.json)

Cross-Mac PF enforcement/rollback, OS resolver selection, natural DNS cutover, macOS cache
observations and the faculty challenge need their own physical evidence. A successful local
rehearsal does not substitute for those observations.

## Four-Mac service map

| Machine | Preserved role | Phase 2 addition | Ports |
|---|---|---|---|
| Mac 1 | Primary DNS and client | Primary DNS TTL and record changes | UDP/TCP 53 |
| Mac 2 | HTTPS edge | Passive backend failover and upstream logging | TCP 8443 |
| Mac 3 | Backend A | Standby HTTPS edge | TCP 3001 and 8443 |
| Mac 4 | Backend B and client | Independent backup DNS | TCP 3002; UDP/TCP 53 |

Mac 1 is the preferred firewall test client. Mac 3 and Mac 4 also host services, so local
loopback access on those hosts does not prove cross-machine firewall isolation.

## 1. Configuration and startup

Run all commands from the repository root, the directory containing this README's parent folder.
Copy this same project to each Mac. Do not copy generated runtime state or private keys between
machines. Keep existing deployed primary CA/server material on Mac 2.

```bash
python3 Phase2/cn.py configure
python3 Phase2/cn.py inventory
```

`configure` imports the final Phase 1 settings. Those historical IPs may have changed. Obtain each
Mac's current IP with `ipconfig getifaddr en0`; confirm its active interface with
`networksetup -listallhardwareports`. Update all four addresses and the actual router resolver:

```bash
python3 Phase2/cn.py configure --mac1 192.168.1.101 --mac2 192.168.1.102 --mac3 192.168.1.103 --mac4 192.168.1.104 --upstream-dns 192.168.1.1 --interface en0
```

The addresses above are examples, not detected settings. Copy the resulting `Phase2/site.json`
to the other Macs. Do not independently choose different domains, backend addresses or TTLs.
If active interface names differ, set each copy's `interface` to its own local interface.
The program refuses to start a role on a Mac whose configured interface lacks that role's IP.

The original inventory includes Mac 1 in `10.3.3.x` and other hosts in `10.7.x.x`. Do not assume
these are one subnet merely because historical campus routing allowed ping. Confirm actual
routing and device-to-device access on the demonstration network.

Stop old Phase 1 services in their own terminals before starting the replacement listener on the
same port. Do not use broad `killall nginx` or `killall dnsmasq` commands.
Start these services in separate Terminal windows and leave each window open:

```bash
# Mac 3
python3 Phase2/cn.py run backend-a
# Mac 4, first Terminal
python3 Phase2/cn.py run backend-b
# Mac 2, after TLS setup below
python3 Phase2/cn.py run edge-primary
# Mac 1
python3 Phase2/cn.py run dns-primary
# Mac 4, second Terminal
python3 Phase2/cn.py run dns-backup
# Mac 3, second Terminal, after standby TLS setup below
python3 Phase2/cn.py run edge-standby
```

Alternatively, double-click `START_PHASE2.command` and choose one role per Terminal.
The port-53 DNS services request administrator permission. Backends and port-8443 edges do not.
Ctrl+C stops the foreground service. Rendered configs and logs are in `Phase2/runtime/<role>/`.
No original Phase 1 configuration is overwritten.

## 2. Preserve certificate trust and issue the standby certificate

On the actual Mac 2, restore its existing deployed `local-ca.crt`, `local-ca.key`, `server.crt`
and `server.key` under `Mac 2 - Edge/certs/`. Keep keys private. Git intentionally excludes them.
If no CA/certificates exist, create them once on Mac 2:

```bash
python3 Phase2/cn.py tls init-primary
```

The command refuses to overwrite existing keys. The Phase 1 and Phase 2 domains must match.
Share only `local-ca.crt` with client Macs. Trust this CA in the System keychain using Keychain
Access. `curl --cacert /path/to/local-ca.crt` is also valid certificate verification; `curl -k`
is not acceptable for the final demonstration.

On Mac 3, generate a separate standby private key and public signing request:

```bash
python3 Phase2/cn.py tls csr
```

Send only `Phase2/certs/standby/server.csr` to Mac 2. On Mac 2, sign the received request:

```bash
python3 Phase2/cn.py tls sign --csr /path/to/received/server.csr --out Phase2/certs/signed-standby.crt
```

Return the signed certificate to Mac 3 as `Phase2/certs/standby/server.crt`. Share the public CA
certificate as needed. Never send the primary CA private key to Mac 3. The signed certificate
covers both `app.team1.test` and `api.team1.test` with the configured domain substituted.

## Demonstration A — independent backup DNS

On client Macs, save their old DNS configuration and list both project DNS servers:

```bash
python3 Phase2/cn.py client-dns apply --service Wi-Fi
python3 Phase2/cn.py client-dns show --service Wi-Fi
python3 Phase2/cn.py verify baseline
```

Use `--ca /path/to/local-ca.crt` on `verify` when the command-line client uses an explicit CA file.
Start packet capture before the failure; see the evidence section. Stop only primary DNS using
Ctrl+C in Mac 1's DNS terminal. On a client, flush the OS cache and verify:

```bash
python3 Phase2/cn.py flush-os-cache
python3 Phase2/cn.py verify dns-backup
```

The check requires primary queries to fail, backup queries for both names to return the configured
edge, and HTTPS requests through the ordinary OS DNS path to succeed. Attach a capture or backup
DNS query log showing the actual client query reached Mac 4. A cached HTTP success alone is not
proof of DNS failover. macOS may choose either listed resolver and failover may involve a delay.
Restart Mac 1's primary DNS after collecting evidence.

## Demonstration B — real DNS TTL, cache expiry and cache flush

The generated primary and backup configurations use `local-ttl=30`. Both serve the same
`records.hosts` content. `dig @SERVER` directly queries a resolver and does not demonstrate the
macOS application's DNS cache. The optional client-side dnsmasq below provides a controlled,
real caching resolver without changing system DNS settings.

On the client, in a separate Terminal:

```bash
python3 Phase2/cn.py run cache
```

In another client Terminal, prime the cache and inspect the TTL:

```bash
python3 Phase2/cn.py query primary
python3 Phase2/cn.py query backup
python3 Phase2/cn.py query cache
```

While the 30-second entry is fresh, change the record on BOTH DNS hosts. Keep the standby edge
ready so the new answer leads to a working service. On Mac 1:

```bash
python3 Phase2/cn.py set-edge standby
python3 Phase2/cn.py reload-dns dns-primary
```

On Mac 4:

```bash
python3 Phase2/cn.py set-edge standby
python3 Phase2/cn.py reload-dns dns-backup
```

`reload-dns` checks that the PID belongs to this project's exact dnsmasq configuration before
signalling it. SIGHUP rereads the hosts file and clears that resolver's cache. Updating a generated
`address=` directive would instead require a restart; this project deliberately uses a hosts file.

On the client, query primary and backup directly to show the new answer. Query `cache` before
expiry to show the old answer with a decreasing TTL. Repeat after 30 seconds to observe the new
answer. If both source updates took longer than the remaining TTL, re-prime and repeat; do not
claim the old answer persisted if it did not.

For immediate cache invalidation, repeat a record change while the local cache holds the old answer:

```bash
python3 Phase2/cn.py query cache
python3 Phase2/cn.py reload-dns cache
python3 Phase2/cn.py query cache
```

This flushes the separate dnsmasq cache. Also demonstrate the macOS cache with a normal application
lookup, `python3 Phase2/cn.py flush-os-cache`, then a fresh application request. Browser caches and
existing HTTPS connections can behave differently; record the actual observation.

Restore `set-edge primary` on both DNS Macs and reload both DNS services after this demonstration,
unless immediately continuing into the edge migration demonstration.

## Demonstration C — backend service isolation with rollback

First prove both backends work from Mac 2 and that both A/B are healthy through Nginx. Then preview
and apply rules on the correct backend host:

```bash
# Mac 3
python3 Phase2/cn.py firewall render --backend a
python3 Phase2/cn.py firewall apply --backend a
# Mac 4
python3 Phase2/cn.py firewall render --backend b
python3 Phase2/cn.py firewall apply --backend b
```

The default rules allow only Mac 2 as the remote backend client. They block other inbound IPv4
sources and IPv6 access to the backend ports on the configured LAN interface. Local loopback
health checks are separate from this cross-machine test. The edge explicitly binds upstream
connections to its configured source IP so the allowlist matches predictably.

The helper requires an existing active `com.apple/*` filter anchor. If absent, it refuses to modify
the global ruleset; consult faculty rather than replacing `/etc/pf.conf`. Before applying, it saves
root rules, `/etc/pf.conf`, and prior project-anchor rules. If PF is disabled, it acquires its own
enable token; if already enabled, it leaves the existing enable state untouched. It never disables
PF globally. Existing connection states are preserved; use fresh TCP connections.

Run these paired checks while both backends remain running:

```bash
# Mac 1: direct backend access must fail; application through Nginx must work
python3 Phase2/cn.py verify firewall-client
# Mac 2: direct backend access and application through Nginx must work
python3 Phase2/cn.py verify firewall-edge
```

A stopped backend can also produce a connection failure, so a client denial alone is insufficient.
Collect the paired Mac 2 check and PF counters:

```bash
python3 Phase2/cn.py firewall status --backend a
```

Use `--backend b` on Mac 4. Restore on EACH backend host after the demo:

```bash
# Mac 3
python3 Phase2/cn.py firewall restore --backend a
# Mac 4
python3 Phase2/cn.py firewall restore --backend b
```

This restores the saved project anchor and releases only its own PF reference. Other system rules
are not replaced. If an apply fails partway through, retain the runtime backup and inspect it.
Do not delete `active.json` to bypass the recovery guard.

## Demonstration D — backend failure and recovery

From the client, with both backends running:

```bash
python3 Phase2/cn.py verify balanced
```

Stop Backend A using Ctrl+C on Mac 3, leaving its standby edge terminal separate. Then:

```bash
python3 Phase2/cn.py verify b-only
```

Restart A with `run backend-a`. Allow at least 6 seconds for the 5-second passive failure period,
then rerun `verify balanced`. The verifier requires successful HTTP 200 responses and the expected
`X-Backend` values, not merely a successful curl process exit. Requests use fresh curl invocations.

Nginx uses passive failure detection, retries on connection/timeout/selected 5xx errors, and tries
at most two upstreams. A black-holed connection may add timeout delay. This is not an active health
check service. Do not enable automatic retry of non-idempotent writes without discussing duplicate
side effects. This project's endpoints are GET/HEAD.

When both backends stop, show that DNS/TLS still work but Nginx returns HTTP 502. Restart both.
Mac 2 remains a single edge failure point until the controlled migration is performed; DNS migration
is not automatic zero-downtime edge failover.

## Demonstration E — controlled edge migration

1. Verify the standby TLS chain and service using an explicit connection to Mac 3 while preserving
   the domain/SNI. This is a readiness check, not migration proof:

   ```bash
   curl --noproxy '*' --cacert /path/to/local-ca.crt --resolve app.team1.test:8443:MAC3_IP https://app.team1.test:8443/api/status -i
   ```

   Replace `MAC3_IP`. Expect `X-Edge: standby` and backend A or B.
2. If firewall rules are active, restore them on both backend hosts, then reapply with
   `--allow-standby`. This authorizes Mac 2 and Mac 3 as edge sources. Repeat the client denial
   and edge access checks. The initial strict isolation demo permits only Mac 2; the migration
   step intentionally adds the standby edge.
3. Prime a client DNS cache while records still point to Mac 2. Keep both edges running.
4. Run `set-edge standby` and the matching `reload-dns` on BOTH DNS hosts as shown above.
5. On the client, update its expected active target with `set-edge standby` as well. This only
   updates local config/unused DNS files; it does not change the remote DNS servers.
6. Show direct DNS queries returning Mac 3 while a fresh client request may still use cached Mac 2.
   Inspect `X-Edge` to distinguish the edges. After expiry or flushing, use the domain normally:

   ```bash
   python3 Phase2/cn.py verify migrated
   ```

   This check deliberately does not use `--resolve`. It requires standby response headers, valid
   HTTPS and both backend identifiers. Attach DNS and packet/log evidence separately.
7. Keep the old edge for at least one TTL plus a grace period. Existing connections may persist
   beyond DNS expiry. Stop old edge only after the standby path works for clients.
8. Roll back by setting `primary` on both DNS servers, reloading them, and restoring client
   expectations. Keep the old trusted primary certificate and configuration available.

Use the same HTTPS port on both physical edges: DNS records map addresses, not URL ports.
Different standby ports exist only to support local rehearsal tests.

## Demonstration F — troubleshooting

```bash
python3 Phase2/cn.py diagnose
# On an edge, where backend access should be permitted:
python3 Phase2/cn.py diagnose --from-role edge
```

Add `--ca /path/to/local-ca.crt` if needed. Diagnostics save actual command output and return codes
under `Evidence/Phase2/`. The two explicit-edge HTTPS probes bypass DNS only to isolate that layer;
the normal domain probe remains the test of the complete path. See
[the fault and recovery table](docs/TROUBLESHOOTING.md).

## Evidence and tests

```bash
# On the client, before generating traffic; choose its actual interface
python3 Phase2/cn.py capture --interface en0
# Use lo0 in a separate capture for local-to-local traffic
python3 Phase2/cn.py capture --interface lo0
```

Captures are limited to configured project hosts/service ports. Ctrl+C finalizes the PCAP.
TLS 1.3 may hide certificate handshake messages in an ordinary capture; use curl/openssl to inspect
certificates or force a TLS 1.2 client for a teaching capture when needed. Never claim encrypted
application data is readable without decryption.

Read the [evidence checklist](../Evidence/Phase2/README.md). Live verification files are excluded
from Git by default; review and deliberately add selected evidence before a public submission.
Never add private keys or runtime backups.

```bash
# Fast checks; full networking rehearsal is explicitly opt-in
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s Phase2/tests -v
# Real 30-second cache and failure rehearsal; about one minute
PYTHONDONTWRITEBYTECODE=1 CN_RUN_INTEGRATION=1 python3 -u -m unittest discover -s Phase2/tests -v
```

Integration tests create temporary services and credentials, use dynamic loopback ports, terminate
only their own child processes, and leave system DNS/firewall settings untouched. They do not prove
cross-Mac isolation, OS resolver selection, or natural client migration. The CI workflow runs the
same rehearsal on Linux; macOS PF enforcement remains a physical Mac test.

## Restore the demonstration network

1. Restart any backend/DNS/edge stopped for failure tests.
2. Restore primary DNS records on both resolvers and reload them.
3. Restore firewall sessions separately on Mac 3 and Mac 4.
4. On each client, run `client-dns restore --service Wi-Fi` to restore its saved DNS list, including
   DHCP mode when it originally had no manual servers.
5. Stop only this project's foreground terminals. Preserve evidence and rollback backups.
