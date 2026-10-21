# Install pcb-advisor (instructions for an AI agent)

You are a CLI coding agent (Claude Code, Antigravity, or similar) asked to install pcb-advisor for the person at the
keyboard. Do every step yourself, run the commands, and check each result. Ask the person ONLY for: a browser
sign-in, an administrator/UAC prompt, or a yes/no on installing a program. Report in a few short lines at the end.

Rules: do not edit tracked files in the repo (only `.venv`, `projects/`, `config.json` change). Never print or store a
password or token. The installer is safe to run twice: it repairs and never deletes projects or config.

1. Run the one-command installer for this OS (it does steps Python, code, venv, requirements, AI engine, sign-in,
   doctor, start). It detects Claude Code or Antigravity (`agy`) and, if neither is there, asks which one the person has
   an account for (`PCB_ENGINE=claude|agy` answers it; `PCB_YES=1` alone means Claude). Answer the other questions yes;
   the person finishes the sign-in in the browser.
   - Windows (PowerShell): `powershell -NoProfile -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/ilaish5/pcb-advisor/main/install.ps1 | iex"`
   - macOS / Linux: `curl -fsSL https://raw.githubusercontent.com/ilaish5/pcb-advisor/main/install.sh | bash`
   - Already inside a clone (a `pcb.py` is here): run `./install.sh` or `install.bat` instead.
   - A non-interactive shell cannot answer prompts: set `PCB_YES=1`, and `PCB_NO_START=1` if you want to start the
     server yourself in the background.
2. If the installer stopped, run the doctor from the install folder and fix every line that says `FIX` with the
   command printed under it, then run it again until it says Ready:
   - Windows: `.venv\Scripts\python pcb.py doctor` (add `--json` for machine-readable output)
   - macOS / Linux: `.venv/bin/python pcb.py doctor`
   Exit code 0 = ready, 1 = something blocking. `warn` lines are fine to report and leave (no git = no in-app
   Update; no network to jlcpcb.com = no stock checks; Altium is optional and Windows only).
3. A tool the installer just added may not be on PATH in this shell yet (winget, the Claude installer). Open a new
   shell or use the full path; pcb-advisor itself finds `claude` in `~/.local/bin` (`%USERPROFILE%\.local\bin`).
4. Sign-in. Claude: `claude auth login` (the person completes it in the browser), then `claude auth status`
   must exit 0. Antigravity: the person runs `agy` once and signs in with Google (no status command). The installer
   already sets `agent.provider`; to switch later: `pcb.py config agent.provider antigravity` (see docs/ENGINES.md).
5. Start the server (`./start.sh` or `.\start.bat`, in the background), check that http://localhost:8931 answers,
   and tell the person to open it. Tell them how to start it next time (double-click `start.bat` / `./start.sh`).
6. Optional: offer `pcb.py seed` (a finished example project).
