#!/usr/bin/env sh
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { echo "Run ./install.sh first (it sets everything up)."; exit 1; }
exec .venv/bin/python pcb.py serve
