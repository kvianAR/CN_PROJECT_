# Evidence index

[Project overview](../README.md) · [Phase 2 report](../Phase2/REPORT.md) · [Collection checklist](Phase2/README.md)

Find the proof for a claim before presenting it. Original Phase 1 material and new Phase 2 local
results have separate scope; neither is silently relabeled as a new physical-network demonstration.

## Phase 2 · Verified local run

| Artifact | What it records |
|---|---|
| [Full test summary](Phase2/20261123T043836.040132Z-full-test-summary.json) | **6/6 tests passed**, no failures/errors/skips, source hashes and timestamp |
| [Complete transcript](Phase2/20261123T043836.040132Z-full-test-transcript.txt) | Actual test execution and observed service results |
| [Integration findings](../Phase2/LOCAL_TEST_RESULTS.json) | Eleven real DNS, cache, TLS, balancing and failure/recovery findings |
| [GitHub CI](https://github.com/kvianAR/CN_PROJECT_/actions) | Automated configuration/TLS/loopback checks on a hosted runner |
| [Physical collection checklist](Phase2/README.md) | What still needs real cross-Mac captures, screenshots and challenge observations |

Reproduce and save a fresh transcript with:

```bash
python3 Phase2/run_checks.py
```

The command runs from the repository root and writes timestamped results under `Evidence/Phase2/`.
A skipped or failed test does not count as a complete pass.

## Phase 1 · Original submitted artifacts

These files are retained from the final Phase 1 baseline. Their original timestamps and capture
interfaces determine what each observation proves.

| Area | Representative artifact |
|---|---|
| LAN inventory | [Mac 2 network information](01-LAN/01_mac2_network_info.png) |
| Connectivity | [Ping to Mac 1](02-Ping/02_ping_mac1_dns.png) |
| Private DNS | [DNS query](03-DNS/05_dns_query_mac1.png) |
| Backend A | [API response](04-Backend-A/06_backend_a_curl.png) |
| Backend B | [API response](05-Backend-B/07_backend_b_curl.png) |
| Reverse proxy | [Nginx config](06-Nginx/08_nginx_config_render.png) |
| TLS | [Certificate verification](07-HTTPS-TLS/09_tls_cert_verify.png) |
| Load balancing | [A/B alternation](08-Load-Balancing/10_load_balancing_alternation.png) |
| HTTP caching | [Conditional 304](09-Caching/11_caching_304_not_modified.png) |
| Packet analysis | [Capture](10-Wireshark/dns-tls-loadbalancing.pcap) · [Packet view](10-Wireshark/12_wireshark_packet_capture.png) |
| Failure recovery | [Failover check](11-Failure-Cases/13_failover_recovery_test.png) |
| Original final summary | [Verification matrix](FINAL/14_full_verification_pass_matrix.png) |

## Reading the evidence correctly

**Local rehearsal proves:** real service behavior between processes on one host, including TTL
expiry, TLS validation and backend failure/recovery.

**Physical evaluation additionally needs:** cross-Mac firewall enforcement/rollback, client-to-backup
DNS traffic, natural client DNS cutover, macOS cache observations and faculty fault diagnosis.

New screenshots and recordings must show actual execution. Captures may use loopback or a LAN
interface; name the interface and host in the evidence description. Do not commit private keys,
CA signing material or runtime rollback state.
