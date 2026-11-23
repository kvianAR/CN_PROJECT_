# Mac 3 · Backend A and standby edge

[Project overview](../README.md) · [Standby TLS](../Phase2/README.md#2-preserve-certificate-trust-and-issue-the-standby-certificate) · [Migration demo](../Phase2/README.md#demonstration-e--controlled-edge-migration)

Mac 3 runs the unchanged Phase 1 Python service and, in a separate Terminal, the Phase 2 standby edge.

| Service | Port | Identity |
|---|---|---|
| Backend A | TCP **3001** | `X-Backend: A` |
| Standby HTTPS edge | TCP **8443** | `X-Edge: standby` |

The backend uses Python's standard library. It listens on `0.0.0.0`, serves JSON and supplies
`Cache-Control` plus ETag validation. Nginx handles the standby HTTPS role.

## Start Backend A

Use the current shared `Phase2/site.json`. Run from the **repository root**:

```bash
python3 Phase2/cn.py run backend-a
```

Keep the Terminal open. Verify in a second Terminal:

```bash
curl -i http://127.0.0.1:3001/api/status
```

Expect HTTP **200**, `X-Backend: A` and `{"backend":"A","status":"ok"}`.
For failure/recovery, stop only this backend Terminal with **Ctrl+C**, then run the same start command
again. The standby edge has its own process and Terminal.

## Prepare the standby edge

1. Install Nginx if missing: `brew install nginx`.
2. Create a local standby key and public request:

   ```bash
   python3 Phase2/cn.py tls csr
   ```

3. Send **only** `Phase2/certs/standby/server.csr` to Mac 2.
4. Receive the signed certificate as `Phase2/certs/standby/server.crt`. Keep `server.key` on this Mac.
5. Start the standby in a separate Terminal:

   ```bash
   python3 Phase2/cn.py run edge-standby
   ```

The primary CA remains on Mac 2. Standby readiness requires certificate trust and access to both
backends before any DNS cutover. See the [full TLS workflow](../Phase2/README.md#2-preserve-certificate-trust-and-issue-the-standby-certificate).

## Backend firewall

Preview before applying on this Mac:

```bash
python3 Phase2/cn.py firewall render --backend a
python3 Phase2/cn.py firewall apply --backend a
```

Mac 1 should fail to reach backend ports while Mac 2 succeeds. The domain must continue working.
For the edge migration stage, the runbook explicitly adds the standby as another permitted edge.
Local loopback checks on Mac 3 do not prove remote-client isolation.

Restore the saved project rules after the demonstration:

```bash
python3 Phase2/cn.py firewall restore --backend a
```

See the [isolation runbook](../Phase2/README.md#demonstration-c--backend-service-isolation-with-rollback)
for prerequisites, paired checks and recovery.

## Original Phase 1 backend

```bash
zsh "Mac 3 - Backend A/start_backend_a.command"
```

This uses the original `settings.env` and backend source. Use either the original launcher or the
Phase 2 launcher for port 3001, not both at once.
