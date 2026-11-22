# Phase 2 evidence checklist

Keep original Phase 1 evidence unchanged. Add real Phase 2 results here. No four-Mac screenshots,
packet captures or faculty challenge results have been invented or prefilled.

| ID | Demonstration | Required evidence |
|---|---|---|
| A | Backup DNS | Both client DNS entries, primary stopped, backup answer, client-to-backup query packet/log, working domain HTTPS |
| B | TTL/cache | Initial A answer and TTL 30, changed direct answer, old cached answer with remaining TTL, post-expiry new answer, explicit cache flush |
| C | Firewall | Both backends running, Mac 1 direct access denied, Mac 2 direct access allowed, domain works, PF counters, rollback completed |
| D | Backend HA | A/B before failure, A stopped with all successful B responses, A restarted and A/B resumes |
| E | Edge migration | Standby readiness and TLS, both DNS servers updated, old cached client vs new target, domain request showing X-Edge standby |
| F | Troubleshooting | Injected fault, layer-by-layer commands, reason for diagnosis, fix and verification |

For each demonstration record date/time, physical host/IP, exact command, expected result, observed
result, screenshot/recording filename, PCAP/log filename and rollback result. Save failures too.

`cn.py verify` saves timestamped JSON with real commands, exit codes and observations.
`cn.py diagnose` saves diagnostic text. `cn.py capture --interface en0` saves PCAP files until Ctrl+C.
Select lo0 for same-host traffic; an en0 capture may not include a local query. Take screenshots
of the actual terminals/browser during each demonstration. A typed transcript alone is not a
packet capture or screenshot.

One-Mac rehearsal results are under `Phase2/LOCAL_TEST_RESULTS.json`; label them as local rehearsal.
Do not use them as proof of physical PF filtering, macOS resolver selection or DNS-based client
migration. Review generated evidence before committing; private keys and runtime backups must
never be included in the public repository.
