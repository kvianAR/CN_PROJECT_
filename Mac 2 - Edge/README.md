# Mac 2 · Primary HTTPS edge

[Project overview](../README.md) · [TLS setup](../Phase2/README.md#2-preserve-certificate-trust-and-issue-the-standby-certificate) · [Troubleshooting](../Phase2/docs/TROUBLESHOOTING.md)

Mac 2 accepts trusted HTTPS requests, terminates TLS, selects a backend and returns its response.
Phase 2 adds explicit upstream source binding, bounded retries and diagnostic upstream logs.

| Item | Value |
|---|---|
| Listener | HTTPS **8443**, TCP |
| Names | `app.team1.test`, `api.team1.test` |
| Backends | Mac 3 **3001**, Mac 4 **3002** |
| Strategy | Round robin; passive failure detection |
| Failure window | `max_fails=1`, `fail_timeout=5s` |
| Identity header | `X-Edge: primary` |
| Runtime logs | `Phase2/runtime/edge-primary/` |

## Before starting

Install Nginx if missing: `brew install nginx`. Use the current shared `Phase2/site.json` and confirm
both backends are running/reachable. All commands below run from the **repository root**.

### Keep the existing trust chain

The deployed primary's TLS files belong under `Mac 2 - Edge/certs/`. Private material is deliberately
excluded from Git. A fresh clone does not contain pre-generated trusted certificates.

| File | Share it? |
|---|---|
| `local-ca.crt` | Yes: public CA certificate for clients |
| `server.crt` | Public server certificate |
| `local-ca.key` | **No:** CA signing key stays on Mac 2 |
| `server.key` | **No:** primary server key stays on Mac 2 |

If no keys/certificates exist, generate the primary material once:

```bash
python3 Phase2/cn.py tls init-primary
```

Existing keys are preserved. For standby TLS, sign Mac 3's public CSR using the
[certificate workflow](../Phase2/README.md#2-preserve-certificate-trust-and-issue-the-standby-certificate).
Do not move the CA private key to the standby.

## Start and verify

```bash
python3 Phase2/cn.py run edge-primary
```

In another Terminal, after client DNS/trust are ready:

```bash
python3 Phase2/cn.py verify balanced
```

If using an explicit CA file:

```bash
python3 Phase2/cn.py verify balanced --ca "Mac 2 - Edge/certs/local-ca.crt"
```

The verifier checks HTTP status and backend identifiers. Trust validation stays enabled.

## Failure and isolation checks

| Scenario | Check |
|---|---|
| Backend A stopped | Client runs `verify b-only` |
| A restarted | Wait at least 6 seconds; client runs `verify balanced` |
| Both backends stopped | Expect upstream HTTP **502** while edge TLS may still work |
| Backend PF enabled | Run `verify firewall-edge` here; direct backend access must succeed |
| Need layer-by-layer diagnosis | Run `diagnose --from-role edge` here |

The `access.log` records edge identity, selected upstream, upstream status and timings.
`error.log` supplies connection/timeout details. This is **passive failover**, not periodic active
health probing. There is no configured Nginx proxy micro-cache; the backends supply HTTP cache
headers and conditional responses.

## Original Phase 1 startup

Set this folder's `settings.env` to the actual IPs and matching domain, then:

```bash
zsh "Mac 2 - Edge/start_edge.command"
```

The script regenerates `nginx.conf` from settings before starting. Never run the Phase 1 and Phase 2
edge listeners together on the same address/port. Stop only the relevant foreground Terminal.
