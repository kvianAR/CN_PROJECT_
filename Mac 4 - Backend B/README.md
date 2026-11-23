# Mac 4 · Backend B and backup DNS

[Project overview](../README.md) · [Backup DNS demo](../Phase2/README.md#demonstration-a--independent-backup-dns) · [Full runbook](../Phase2/README.md)

Mac 4 combines a Python backend, an independent backup resolver and an optional test client.

| Service | Port | Identity / purpose |
|---|---|---|
| Backend B | TCP **3002** | `X-Backend: B` |
| Backup dnsmasq | UDP/TCP **53** | Same project records as primary DNS |
| Client tools | Outbound requests | DNS, HTTPS and capture observations |

## Start the services

Use the current shared `Phase2/site.json`. Run all commands from the **repository root**.
Python 3 is required for the backend; install dnsmasq if missing with `brew install dnsmasq`.

**Terminal 1 — backend:**

```bash
python3 Phase2/cn.py run backend-b
```

**Terminal 2 — independent DNS:**

```bash
python3 Phase2/cn.py run dns-backup
```

Leave both terminals open. Port 53 requests administrator access. The resolver serves the project
records independently; stopping primary DNS does not stop this process.

## Verify and update

```bash
curl -i http://127.0.0.1:3002/api/status
python3 Phase2/cn.py query backup
```

Expect HTTP **200** and `X-Backend: B`. DNS should return the configured active edge.
For a standby cutover:

```bash
python3 Phase2/cn.py set-edge standby
python3 Phase2/cn.py reload-dns dns-backup
```

Make the same record change and matching reload on Mac 1. Update both resolvers for rollback too.

## Backend isolation

```bash
python3 Phase2/cn.py firewall render --backend b
python3 Phase2/cn.py firewall apply --backend b
```

Use Mac 1 for the remote-client denial test and Mac 2 for allowed edge access. Mac 4's own
loopback connection to B is a local health check, not proof that PF blocks a different machine.

Restore after testing:

```bash
python3 Phase2/cn.py firewall restore --backend b
```

## Optional client role

After preserving existing DNS settings and trusting the public CA:

```bash
python3 Phase2/cn.py client-dns apply --service Wi-Fi
python3 Phase2/cn.py verify baseline
```

Restore the saved client configuration afterward:

```bash
python3 Phase2/cn.py client-dns restore --service Wi-Fi
```

A query from this Mac to its own backup resolver may use loopback. Capture the correct interface
and show an actual client-to-backup query when demonstrating DNS failover.

## Original Phase 1 backend

```bash
zsh "Mac 4 - Backend B/start_backend_b.command"
```

The original Python source and settings are retained. Stop any other port-3002 listener first.
