#!/bin/zsh
# Complete local CN rehearsal; leaves physical network/DNS/firewall settings untouched.
set -u
cd "$(dirname "$0")" || exit 1
PYTHONDONTWRITEBYTECODE=1 python3 Phase2/finalize.py --run-tests
result=$?
if [[ -f CN_REPORT.html ]]; then
  open CN_REPORT.html
fi
if [[ "$result" -ne 0 ]]; then
  echo 'A check failed or was skipped. Inspect the saved transcript; the report does not mark it passed.'
fi
exit "$result"
