# Fault isolation and recovery

Check one layer at a time and state the observed evidence aloud. Save output before changing
anything. The configured project uses `.test`, DNS UDP/TCP 53, HTTPS TCP 8443 and backend TCP
3001/3002 unless `site.json` says otherwise.

| Observation | Likely layer | Next check | Recovery |
|---|---|---|---|
| Private name does not resolve; edge IP reachable | DNS | Query primary and backup individually; inspect client DNS list and `scutil --dns` | Restart affected DNS; correct client resolver list |
| Primary and backup return different A records | DNS consistency | Compare both hosts' `site.json` and generated `records.hosts` | Set identical active edge and reload BOTH resolvers |
| Source DNS gives new IP, client reaches old edge | DNS/application caching | Compare direct DNS answer, cache TTL, response `X-Edge`, established connections | Wait expiry or flush the affected cache; establish a new connection |
| Name resolves but TCP connection fails | Address, route, port or firewall | Confirm current IP, Nginx listener, route, interface and port | Correct inventory/listener; restore relevant project firewall rules if incorrect |
| `Can't assign requested address` on service start | Listener IP | Compare configured role IP with local interface addresses | Start on the assigned Mac or update current addresses; do not chmod the folder |
| TLS chain or hostname error | TLS | CA file, SAN names, dates, server certificate/key match | Install correct signed certificate and trust public CA; never use `-k` as final fix |
| Valid TLS, HTTP 502 | Upstream/backend | From edge, curl both backends; inspect upstream address/status in Nginx log | Start backend or fix upstream IP/port/firewall allowance |
| Only B appears while A runs | Passive HA state or route | Wait more than 5 seconds; curl A from edge; inspect error log | Correct access; allow passive probe after fail timeout |
| Backend accessible directly from client | Service isolation | Confirm client is a separate Mac, new TCP flow, correct interface, PF enabled and project anchor called | Apply correct backend rules; do not rely on local loopback tests |
| Backend blocked even from edge | Firewall source address | Compare `proxy_bind`, allowlist and interface; inspect PF counters | Correct source IP/allowlist; restore project anchor if necessary |
| Standby fails after migration | Standby TLS or backend allowance | Probe standby by domain/SNI with explicit IP; test standby-to-backend paths | Install same-CA certificate; permit standby edge on backend hosts |
| Both DNS services work but application fails | Edge/backend | TCP and TLS checks, then Nginx upstream logs | Repair edge/backend; changing DNS alone does not repair the application |

## Useful commands

From repository root:

```bash
python3 Phase2/cn.py inventory
python3 Phase2/cn.py client-dns show --service Wi-Fi
python3 Phase2/cn.py query primary
python3 Phase2/cn.py query backup
python3 Phase2/cn.py diagnose
```

On an edge, add `--from-role edge` to diagnosis. On backend hosts, inspect firewall status using
`firewall status --backend a` or `--backend b`. Use the role's `Phase2/runtime/<role>/error.log`
and `access.log`. Nginx access logs record the actual upstream address and retry status list.

## Safe practice faults

- Stop primary DNS; identify the stopped listener and verify backup query traffic.
- Change active DNS target on one DNS host only; identify inconsistent answers, then restore both.
- Stop Backend A; identify passive rerouting, then restore A.
- Use a wrong HTTPS destination port in a client command; separate resolution from TCP failure.
- Stop both backends; explain successful TLS plus upstream HTTP 502.

Do not damage the trusted certificate store, replace global firewall rules, or remove unrelated
files to create a fault. Keep every original value and restore after each exercise.

## Recovery order

Restore backend processes, valid edge configuration/certificates, project firewall allowances,
consistent DNS records, then client DNS/cache settings. A firewall backup belongs to its original
Mac and should not be copied to a different machine. The helper restores only its saved project
anchor and its own PF reference. If recovery reports an error, retain its backup/state files and
inspect the reported command; do not blindly clear global states or disable PF.
