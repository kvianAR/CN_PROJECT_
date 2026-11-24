# Mac 3 viva handbook

[Project overview](../../README.md) · [Phase 2 runbook](../README.md) · [Troubleshooting](TROUBLESHOOTING.md)

Read in this order: project flow, Mac 3 roles, six extensions, then the mock viva questions.
Explain the idea in your own words before memorizing a command.

## 1. Your 45-second introduction

> Our project demonstrates private DNS resolution, trusted HTTPS at Nginx and load balancing
> across two Python backends. Phase 1 established that request path. Phase 2 adds backup DNS,
> TTL experiments, backend isolation, passive recovery and a standby edge. My machine is Mac 3:
> it runs Backend A on port 3001 and a separate standby Nginx edge on port 8443. The standby uses
> its own key and a certificate signed by the existing local CA. Local and CI tests validate
> service behavior; physical network evidence has a separate scope.

## 2. Machine map

| Machine | Supplied IP | Responsibility |
|---|---|---|
| Mac 1 | `10.7.31.54` | Primary DNS and client |
| Mac 2 | `192.168.1.7` | Primary HTTPS edge and CA |
| **Mac 3** | **`10.7.19.86`** | **Backend A and standby edge** |
| Mac 4 | `10.7.27.236` | Backend B and backup DNS |

Addresses alone do not establish connectivity. The supplied Mac 2 host is remote; its private
address did not answer the earlier Mac 3 ping. Do not claim this is a completed four-Mac LAN demo.

## 3. Request flow

1. Client asks a project DNS resolver for `app.team1.test`.
2. DNS returns the active edge address. DNS does not forward the HTTP request.
3. Client connects to TCP 8443 and validates the edge's TLS certificate.
4. Nginx selects Backend A or B and forwards HTTP to TCP 3001 or 3002.
5. Backend responds through Nginx; the client receives the response over HTTPS.

**Yaad rakho:** DNS edge ka IP batata hai; backend Nginx select karta hai.
The internal edge-to-backend segment is HTTP, so this is not end-to-end application encryption.

## 4. Your two Mac 3 processes

| Process | Listener | Function | Identity |
|---|---|---|---|
| Python Backend A | TCP 3001 | Return JSON and HTTP cache validators | `X-Backend: A` |
| Standby Nginx | TCP 8443 | Terminate TLS and proxy to either backend | `X-Edge: standby` |

Alag process aur port hone se dono ek machine par chal sakte hain. Stopping Python A does not
stop the separate Nginx process. Losing the whole Mac 3 makes both services unavailable.

The backend binds to `0.0.0.0` so other machines can reach it. `127.0.0.1` would restrict it to
local connections. PF controls remote access; `0.0.0.0` is not a client destination address.

## 5. Six Phase 2 extensions

| Extension | What to explain | What not to confuse |
|---|---|---|
| Backup DNS | Mac 4 independently serves the same project records | A cached page is not proof that backup DNS was queried |
| TTL/cache | TTL 30 bounds cached DNS answer reuse; compare source vs cache | TTL is not a delay on every HTTP request |
| Isolation | PF allows the edge source and blocks ordinary direct clients | A stopped backend also makes a connection fail |
| Backend recovery | Nginx detects eligible failures through requests and retries | Passive detection is not periodic active health probing |
| Edge migration | Prepare standby, authorize it, change both DNS copies | Standby readiness is not automatic instant DNS failover |
| Troubleshooting | Isolate DNS, TCP, TLS, proxy and backend evidence | A bypassed-layer success is not an end-to-end success |

## 6. Nginx values you should know

| Setting | Value | Meaning |
|---|---|---|
| `max_fails` | 1 | Eligible failed attempts contribute to temporary exclusion |
| `fail_timeout` | 5 seconds | Failure-counting/unavailable window for passive handling |
| `proxy_next_upstream_tries` | 2 | Bound upstream attempts per eligible request |
| Connect timeout | 2 seconds | Bound the attempt to establish an upstream connection |
| Read/send timeout | 5 seconds | Bound waits between upstream I/O operations |
| `proxy_bind` | Edge's configured IP | Make source-IP firewall matching predictable |

After the failure window, a new request can try the backend again. There is no background
periodic probe in this configuration. Tests observe successful B-only service after stopping A,
then A/B after restarting it. Timeouts can add delay; do not promise zero downtime in every fault.

## 7. Standby certificate workflow

1. Mac 3 generates a private key and CSR.
2. Only the public CSR goes to Mac 2.
3. Mac 2's local CA signs a server certificate for both project hostnames.
4. The signed certificate returns to Mac 3; its private key stays on Mac 3.
5. Clients trust the public CA certificate and verify the requested hostname.

**Same CA does not mean same private key.** The CA signing key remains on Mac 2.
A trusted issuer does not excuse a hostname mismatch or expired certificate.
TLS uses negotiated session keys for application traffic; the certificate helps authenticate the server.

## 8. Isolation and cutover order

Strict isolation initially permits only Mac 2 as the remote backend client. Before migration,
explicitly authorize Mac 3 as an additional edge on backend hosts. Then verify standby readiness,
update records on both DNS servers and observe fresh clients reach the standby.

Mac 3's connection to its own backend may stay local. It does not prove that a different machine
is blocked. Use Mac 1 for remote-client denial and Mac 2 for allowed-edge evidence.
Keep old edge available while DNS answers expire. Existing connections may last beyond DNS TTL.

## 9. Commands to recognize

Run from repository root. First two services need separate Terminals:

```bash
python3 Phase2/cn.py run backend-a
python3 Phase2/cn.py run edge-standby
```

Local backend health:

```bash
curl -i http://127.0.0.1:3001/api/status
```

Diagnosis from an edge:

```bash
python3 Phase2/cn.py diagnose --from-role edge
```

Firewall preview/rollback on the correct host:

```bash
python3 Phase2/cn.py firewall render --backend a
python3 Phase2/cn.py firewall restore --backend a
```

Rollback requires a saved matching session. Do not apply rules merely to answer a conceptual viva question.
For DNS source TTL checks, use `python3 Phase2/cn.py verify dns-ttl` on the connected deployment.

## 10. Fault table

| Fault | Expected distinction |
|---|---|
| Primary DNS stops | Backup can answer; actual client resolver use needs fresh query evidence |
| Backend A process stops | Both edges may continue through B if network/allowances are correct |
| Both backend processes stop | Edge TLS can validate while the tested setup returns HTTP 502 |
| Primary edge stops | DNS/traffic must be directed to the standby; a cached old IP may still fail |
| Whole Mac 3 stops | Backend A and standby edge are both lost |
| Client directly reaches backend | Recheck source/interface/rules and distinguish local from remote access |

## 11. Rapid questions and answers

1. **Reverse proxy kya hai?** Client-facing server that forwards requests to an upstream application.
2. **Load balancing vs failover?** Distribution across instances vs continuation after a failure.
3. **Why two DNS servers?** To remove dependence on one DNS process/host for project answers.
4. **Why update both DNS copies?** Clients may use either; inconsistent records create inconsistent targets.
5. **Does DNS choose A or B?** No. It identifies the edge; Nginx selects a backend.
6. **Does HTTPS prove the backend is healthy?** No. Valid TLS can carry an upstream error response.
7. **502 vs 504?** Unusable upstream response vs an upstream timeout.
8. **Why can an ETag request return 200?** The other backend may have a different representation/ETag.
9. **What is the edge failure point?** Primary edge availability until the controlled recovery path is used.
10. **How do you prove PF worked?** Running backends, denied remote client, allowed edge, domain success and rollback evidence.
11. **Can you share the CSR?** Yes; do not share the corresponding private key.
12. **Is a ping timeout proof that every service is blocked?** No; test routing and the actual TCP listener too.

## 12. Evidence wording for the viva

Use **implemented**, **locally tested**, **CI-tested** and **physically demonstrated** precisely.
The retained local record passed six original tests; newer regression checks extend the suite.
Read the latest CI result for the current count. Four-Mac PF, OS resolver selection, natural DNS
cutover and the faculty challenge are not proven by one-host loopback tests.

Practice answering each question in two sentences, then explain the command or packet that would
support it. If you cannot identify the evidence, describe it as a planned verification step.
