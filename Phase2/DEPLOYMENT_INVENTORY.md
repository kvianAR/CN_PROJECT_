# Deployment inventory — 23 November 2026

Addresses supplied by the team. Local workstation is Mac 3.

| Mac | IPv4 | Services |
|---|---|---|
| 1 | 10.7.31.54 | Primary DNS, client |
| 2 | 192.168.1.7 | Primary Nginx edge and existing CA |
| 3 | 10.7.19.86 | Backend A, standby edge |
| 4 | 10.7.27.236 | Backend B, backup DNS |

Mac 2 uses a different IPv4 range. Routed connectivity has not been demonstrated.
Verify connectivity from each participating Mac before configuring clients or firewall rules.
The router resolver 10.7.0.1 and interface en0 remain inherited settings; confirm them locally
on each machine. No OS DNS or firewall changes were applied during this configuration update.
Only this workstation's site.json and generated runtime configs have been updated so far.
