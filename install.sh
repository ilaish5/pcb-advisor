#!/usr/bin/env sh
# One-step setup on macOS / Linux. Run once, then ./start.sh
set -e
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo "Python 3.10 or newer is required"; exit 1; }
python3 -c "import sys; sys.exit(sys.version_info < (3,10))" || { echo "Python 3.10 or newer is required (found $(python3 --version))"; exit 1; }
if [ -d .venv ] && ! .venv/bin/python -m pip --version >/dev/null 2>&1; then rm -rf .venv; fi
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt
.venv/bin/python pcb.py init
echo "Done. Install and sign in to ONE AI engine (see docs/ENGINES.md), then run ./start.sh"
