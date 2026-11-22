# Phase 1 + Phase 2 — stepwise setup

Poora project ek hi `CN_PROJECT_` folder mein hai. GitHub ka final Phase 1 preserve hai.
Phase 2 isi project ke andar add hua hai. Purane Downloads folder ko is setup mein use na karein.

## Pehle isi Mac par test

Terminal mein repository folder ke andar yeh command chalao:

```bash
PYTHONDONTWRITEBYTECODE=1 CN_RUN_INTEGRATION=1 python3 -u -m unittest discover -s Phase2/tests -v
```

Lagbhag ek minute. `Ran 6 tests` ke baad `OK` chahiye. Directory ka path akela command nahi hai;
folder mein jaane ke liye `cd "folder ka path"` use karo. `chmod` ki zaroorat nahi.

## Chaar Macs milne par

1. Har Mac par `ipconfig getifaddr en0` chalao. Chaar current IPs note karo.
2. Har Mac par `networksetup -listallhardwareports` se active interface check karo.
3. Ek Mac par `python3 Phase2/cn.py configure` chalao. `Phase2/site.json` mein current IPs,
   router DNS aur interface set karo. Ya README ka `configure --mac1 ...` command use karo.
4. Same `site.json` sab Macs par copy karo. Private keys aur `runtime` folder copy mat karo.
5. Mac 2 par pehle se deployed Phase 1 ke certificates/keys rakho. Agar nahi hain, README ke TLS
   steps follow karo. Mac 3 standby ke liye alag key aur signed certificate chahiye.
6. Existing Phase 1 service terminal mein Ctrl+C se listener stop karo; same port par do services
   ek saath start mat karo.
7. Alag terminals mein yeh roles start karo:

   | Mac | First Terminal | Second Terminal |
   |---|---|---|
   | 1 | `python3 Phase2/cn.py run dns-primary` | Client demo commands |
   | 2 | `python3 Phase2/cn.py run edge-primary` | Edge verification commands |
   | 3 | `python3 Phase2/cn.py run backend-a` | `python3 Phase2/cn.py run edge-standby` |
   | 4 | `python3 Phase2/cn.py run backend-b` | `python3 Phase2/cn.py run dns-backup` |

8. Clients par `python3 Phase2/cn.py client-dns apply --service Wi-Fi` chalao.
9. Public CA certificate trust karo. Private CA key sirf Mac 2 par rakho.
10. `python3 Phase2/cn.py verify baseline` chalao. Sab PASS ke baad six demos karo.

## Demo order

1. Primary DNS stop, client cache flush, `verify dns-backup`; backup query ka packet/log dikhana hai.
2. TTL cache prime, dono DNS records badlo, old/new answer aur expiry dikhana hai.
3. Backend hosts par firewall apply, client block aur Mac 2 allow dono prove karo.
4. Backend A stop, `verify b-only`; A restart aur 6 seconds baad `verify balanced`.
5. Standby ready, firewall mein standby allow, dono DNS par cutover, client par `verify migrated`.
6. Faculty fault par `diagnose`; DNS, TCP, TLS, Nginx aur backend order mein check karo.

Exact commands aur rollback [Phase 2 README](README.md) mein hain. Firewall aur actual four-Mac
results abhi collect karne hain; one-Mac test pass ko unka proof mat likhna.
