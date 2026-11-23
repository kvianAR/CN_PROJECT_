# Mac 1 · Primary DNS and test client

[Project overview](../README.md) · [Full runbook](../Phase2/README.md) · [Troubleshooting](../Phase2/docs/TROUBLESHOOTING.md)

Mac 1 maps the private application names to the active edge. In Phase 2 it returns a visible
**30-second TTL** and supports controlled record changes. Mac 4 supplies an independent backup.

| Item | Value |
|---|---|
| Service | dnsmasq |
| Listener | UDP/TCP **53** |
| Names | `app.team1.test`, `api.team1.test` |
| Phase 2 configuration | `Phase2/site.json` |
| Generated config | `Phase2/runtime/dns-primary/dnsmasq.conf` |
| Record source | `Phase2/runtime/dns-primary/records.hosts` |

## Before starting

Install `dnsmasq` if missing: `brew install dnsmasq`. Configure current team addresses using the
[shared setup steps](../Phase2/README.md#1-configuration-and-startup). Verify this Mac's active
interface and IP. Historical `settings.env` addresses are not today's detected network state.

All Phase 2 commands below run from the **repository root**.

## Start and verify

```bash
python3 Phase2/cn.py run dns-primary
```

Leave that Terminal open. The launcher requests administrator access for port 53. In another Terminal:

```bash
python3 Phase2/cn.py query primary
python3 Phase2/cn.py query backup
```

Both resolvers should return the configured active edge. Direct queries test those resolvers;
a normal application lookup is needed to demonstrate the client's actual resolver behavior.

## Change the active edge

```bash
python3 Phase2/cn.py set-edge standby
python3 Phase2/cn.py reload-dns dns-primary
```

Repeat the matching change and reload on Mac 4's backup DNS. Changing one copy does not update the
other Mac. `reload-dns` verifies the process identity before rereading records.

For rollback, use `set-edge primary` on both DNS hosts and reload their matching services.

## Backup DNS demonstration

1. Confirm clients list both DNS servers and trust the edge CA.
2. Start packet capture and flush the client's OS cache.
3. Stop this primary DNS with **Ctrl+C** in its own Terminal.
4. Run `python3 Phase2/cn.py verify dns-backup` from a client.
5. Show the query arriving at Mac 4, then restart primary DNS.

See the [complete backup-DNS demo](../Phase2/README.md#demonstration-a--independent-backup-dns)
for commands, evidence and cache caveats.

## Original Phase 1 startup

Edit this folder's `settings.env`, then run from the repository root:

```bash
zsh "Mac 1 - DNS/start_dns.command"
```

It regenerates the original config and starts DNS. Stop the Phase 2 listener before using the
original one on the same address/port. A wrong listening IP causes an address error; changing file
permissions does not repair network addressing.
