# Computer Networks Project — Phase 2 Final Report

**Team:** Abhijeet Dey, Aditya Ranjan, Samriddhi Shah, Satwik Mani Triphati.

**Baseline:** final Phase 1 commit `52a46de198702b146ec60a2e5d6398dc92ab0def`.

**Report status:** implementation and local rehearsal documented. Physical LAN demonstration
results, screenshots/recordings and faculty challenge findings must be filled after those tests.
This report does not claim all six extensions have been demonstrated on four physical Macs.

## Changes from Phase 1

The existing `.test` DNS names, Python REST applications and four-machine architecture are retained.
Phase 2 adds independent backup DNS, explicit 30-second project-record TTL, a controlled caching
resolver for reproducible observation, backend PF isolation with rollback, source-bound Nginx
upstreams, passive failure recovery, standby TLS issuance under the existing CA, DNS-based edge
cutover, diagnostics and evidence collection. Generated configs remain separate from the original
Phase 1 files. Both backends are executed from their unchanged Phase 1 source files.

| Machine | Phase 2 services | Purpose |
|---|---|---|
| Mac 1 | Primary dnsmasq and client | Name service and client observation |
| Mac 2 | Primary Nginx/TLS edge | Client HTTPS entry and upstream selection |
| Mac 3 | Backend A and standby Nginx | Application instance and controlled edge recovery |
| Mac 4 | Backend B and backup dnsmasq | Application instance and independent DNS availability |

Confirm current IP/interface/service inventory before final evaluation. Historical repository IPs
are retained as defaults, not assumed to be today's DHCP leases.

## Extension A — backup DNS

Mac 4 runs a second dnsmasq process with the same project records. Clients list both DNS servers.
The backup does not forward project queries to the primary. The local rehearsal stopped the
primary process and successfully resolved through the backup. Physical client resolver selection
must still be verified after flushing caches, with a packet capture or backup query log.

**Learning:** DNS availability and application availability are independent. A working cached page
does not prove DNS redundancy. Resolver ordering and retry timing depend on the client's resolver.

## Extension B — TTL and controlled record change

Both project DNS servers return a TTL of 30 seconds. Records are stored in reloadable hosts files.
A separate client dnsmasq cache demonstrates a real cached old answer, a changed source answer,
expiry-based refresh and immediate refresh after an explicit flush. All these cases passed in the
one-Mac rehearsal using real dnsmasq instances. macOS application cache behavior and flushing
remain physical demonstration steps.

**Learning:** TTL bounds reuse by a compliant DNS cache; it does not terminate existing HTTP/TLS
sessions. `dig @source` observes the source resolver rather than the application's DNS cache.
HTTP `Cache-Control` and DNS TTL control different objects.

## Extension C — service isolation

PF rules restrict new inbound backend connections on the configured LAN interface. Strict
isolation permits the primary edge source only. During edge migration the standby is explicitly
added as another authorized edge. The helper checks the expected local backend role, requires an
existing Apple wildcard filter-anchor call, snapshots prior rules, validates proposed rules and
loads a dedicated subanchor. It records its own PF enable reference and restores only its saved
anchor/reference. It does not replace the global ruleset or globally disable PF.

**Demonstration result:** pending on Mac 3 and Mac 4. Both direct-client denial and simultaneous
edge access must be recorded with backends running, followed by successful rollback.

**Learning:** a failed client connection alone does not identify a firewall; a stopped service or
wrong route can give the same symptom. Source address, interface, stateful filtering and the
actual backend listener must be checked together.

## Extension D — backend failure and recovery

Nginx retains passive failure detection (`max_fails=1`, `fail_timeout=5s`) and retries eligible GET
requests against the remaining upstream. It adds explicit connection source binding, bounded
connection/read timeouts and upstream-address/status logging. The local rehearsal observed both
A/B, stopped A, observed successful B-only responses, restarted A and observed both again. Both
backends down produced HTTP 502 while edge TLS still worked.

**Learning:** passive health knowledge comes from requests and failures. It is not equivalent to
periodic active health probes. Retrying writes can create duplicate effects, so non-idempotent
retry is not enabled. A primary edge machine remains a failure point absent an edge recovery plan.

## Extension E — controlled edge migration

The standby edge runs on Mac 3 with a separate private key and a server certificate signed by the
primary's existing CA. Both edges identify themselves through `X-Edge`. DNS records on both
resolvers are changed to the standby address, while the primary remains available during cache
expiry. The local rehearsal validated trusted TLS on both edges and continued standby service
after stopping the primary. Its explicit local connection mappings are readiness/rehearsal tests,
not proof that real client DNS cutover has occurred.

**Demonstration result:** natural-domain migration, two-server record consistency and physical
client TTL effects remain pending.

**Learning:** DNS cutover is a controlled recovery procedure with propagation/cache/session timing.
It is not automatic zero-interruption edge HA. Backend firewall permissions and TLS trust must be
ready before directing clients to the standby.

## Extension F — troubleshooting

The diagnostic command records resolver state, independent DNS answers, edge TCP probes, normal
HTTPS and explicit-edge HTTPS. An edge-specific mode also probes both backends. The fault table
maps observations to DNS, address/port, TLS, proxy, firewall and application checks. The faculty's
actual fault, reasoning, fix and post-fix verification must be added during evaluation.

**Learning:** bypassing one layer can isolate a fault, but a successful bypass is not a successful
end-to-end test. State the exact layer tested and return to the ordinary domain path after repair.

## Validation and evidence status

| Check | Observed status |
|---|---|
| Configuration validation and firewall rollback guards | Passed local automated checks |
| Real primary/backup/cache dnsmasq config parsing | Passed |
| Actual CA, separate standby certificate, SAN names and matching key | Passed |
| Real loopback DNS, TLS, cache, failover, standby and 502 integration | Passed in user's Terminal; machine-written results saved |
| Standalone Nginx syntax test | Historical-IP fixture corrected; user confirmed the complete six-test suite passed |
| Four-Mac PF enforcement and exact rollback | Pending |
| OS resolver failover with client-to-backup packet evidence | Pending |
| Natural client DNS migration and macOS cache-flush evidence | Pending |
| Faculty-injected fault and recovery | Pending |
| Four-Mac screenshots/recordings and final integrated demonstration | Pending |

Use [the evidence checklist](../Evidence/Phase2/README.md) to fill the pending rows. Preserve the
actual result, including delays or failures, rather than substituting expected behavior.

## Final evaluation sequence

Show current topology and inventory; confirm LAN reachability; resolve the domain; use trusted
HTTPS; show A/B load balancing; explain DNS/TCP/TLS captures; demonstrate HTTP caching; stop and
recover a backend; demonstrate Phase 2 DNS, isolation and migration; diagnose the injected fault;
then answer individual viva questions. Every member should explain the whole request path.

## Completion record for physical tests

- Test date and network: PENDING.
- Four current device addresses/interfaces: PENDING.
- A/B/C/D/E/F evidence filenames and measured outcomes: PENDING.
- Injected fault, diagnosis, repair and post-fix result: PENDING.
- DNS/firewall/service rollback confirmed on all affected hosts: PENDING.
