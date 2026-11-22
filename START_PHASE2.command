#!/bin/zsh
set -e
cd "$(dirname "$0")"
if [[ ! -f Phase2/site.json ]]; then
  echo 'Importing final Phase 1 settings. Update current LAN IPs before a live demo.'
  python3 Phase2/cn.py configure
fi
printf '\nChoose this Terminal service:\n1 Primary DNS (Mac 1)\n2 Primary edge (Mac 2)\n3 Backend A (Mac 3)\n4 Backend B (Mac 4)\n5 Backup DNS (Mac 4, second Terminal)\n6 Standby edge (Mac 3, second Terminal)\n7 Client cache (optional TTL demo)\n'
read 'choice?Number: '
case "$choice" in
  1) role=dns-primary ;;
  2) role=edge-primary ;;
  3) role=backend-a ;;
  4) role=backend-b ;;
  5) role=dns-backup ;;
  6) role=edge-standby ;;
  7) role=cache ;;
  *) echo 'Choose 1 through 7.'; exit 1 ;;
esac
python3 Phase2/cn.py run "$role"
