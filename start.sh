#!/usr/bin/env sh
cd "$(dirname "$0")"
exec .venv/bin/python pcb.py serve
