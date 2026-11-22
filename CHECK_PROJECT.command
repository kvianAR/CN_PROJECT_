#!/bin/zsh
set -e
cd "$(dirname "$0")"
PYTHONDONTWRITEBYTECODE=1 python3 Phase2/run_checks.py
