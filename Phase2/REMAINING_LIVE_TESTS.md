# Remaining physical work

The final Phase 1 and all Phase 2 implementation files are in this single project.
The user has confirmed the corrected six-test local suite passes. The local integration results
contain eleven successful real service checks. Four physical Macs are required for the remaining
proofs; those results cannot be inferred from the local rehearsal.

## Step 1: collect current device information

On each of the four Macs, run in Terminal:

```bash
hostname
networksetup -listallhardwareports
ifconfig en0
route -n get default
```

If the active Wi-Fi interface is not en0, substitute the actual interface. Record the Mac number,
current IPv4 address, subnet, gateway and interface. Do not reuse old DHCP addresses blindly.
Send these details to the person preparing the common `site.json`. If the interfaces differ
between machines, set each copy's `interface` field to its own active interface; keep IPs, domain,
ports and active DNS target consistent.

## Step 2: validate roles and trust

Use `Phase2/QUICKSTART_HI.md` and `Phase2/README.md`. Keep all services in their own terminals.
Mac 2 needs its existing primary certificate/key/CA. Mac 3 needs the separate standby key and
same-CA signed certificate. No remote login, credentials or private-key transfers are assumed.

## Step 3: run and save full local checks

Double-click the root `CHECK_PROJECT.command`, or run:

```bash
python3 Phase2/run_checks.py
```

This writes a complete transcript and machine-recorded unittest summary under `Evidence/Phase2/`.
The original unittest invocation remains supported. No system DNS or firewall settings are changed
by the local tests. A skipped check is reported as incomplete, not as a pass.

## Step 4: collect physical proof

| Required proof | Run on | What must be visible |
|---|---|---|
| Resolver failover | Client with both DNS servers listed | Primary stopped, actual client query reaches backup, normal domain HTTPS works |
| TTL and OS flush | Client plus both DNS hosts | Old cache answer, changed direct answer, expiry/new answer, manual OS cache flush |
| PF isolation | Mac 3, Mac 4, Mac 1 and Mac 2 | Client denied, edge allowed, both apps running, PF counters and exact rollback |
| Backend HA | Client plus Backend A host | A/B before; B-only after stopping A; A/B after recovery |
| Real edge cutover | Client plus both DNS hosts and standby | Both source DNS records change; normal URL reaches standby; old cached path observed |
| Troubleshooting | Whole team | Actual injected fault, commands/reasoning, fix and successful recheck |

Start packet capture before requests. Take real terminal/browser screenshots or recordings.
Use the existing verifier and capture commands. See `Evidence/Phase2/README.md` for the evidence
matrix and `Phase2/README.md` for the exact commands and rollback.

## Step 5: finish report and Git submission

Replace pending rows in `Phase2/REPORT.md` with observed results and evidence filenames. Review
selected evidence before adding it to a public repository. Never commit `Phase2/runtime/`, private
keys or CA signing material. No remote Git push has been performed by this task.
