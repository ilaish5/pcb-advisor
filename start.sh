#!/usr/bin/env sh
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { echo "Run ./install.sh first (it sets everything up)."; exit 1; }
.venv/bin/python pcb.py serve
rc=$?
# the exit code goes out unchanged (75 = restart after an update, as before); only a real error says where the log is
[ "$rc" -eq 0 ] || [ "$rc" -eq 75 ] || echo "The server stopped with an error. Details are saved in the logs folder: ${PCB_ADVISOR_HOME:-$(pwd)}/logs"
exit "$rc"
