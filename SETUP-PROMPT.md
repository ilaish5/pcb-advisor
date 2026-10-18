# Set everything up with an AI agent

Open a terminal in any folder, start a coding agent (`claude` or `agy`), paste the prompt below, and answer its few questions.
If you have no agent yet, install one first: [docs/ENGINES.md](docs/ENGINES.md) sections 1-2 (one command, one sign-in).

---

```text
Set up pcb-advisor on this computer and get it running. Do every step yourself, run the commands, and
check each result before the next step. Ask me only when you truly need me (a browser sign-in, or a choice).
Report in a few short lines at the end.

1. Python: check `python --version` (or `py -3 --version`) is 3.10+. If missing, install it (Windows:
   `winget install Python.Python.3.12`), then open a new shell so PATH updates.
2. Get the code: if the current folder is not already pcb-advisor (no pcb.py), run
   `git clone https://github.com/ilaish5/pcb-advisor.git` and work inside it. If git is missing, install it
   (`winget install Git.Git`) or download the ZIP from the GitHub page.
3. Install: run `install.bat` (Windows) or `./install.sh` (macOS/Linux). It creates .venv, installs
   requirements.txt and runs `pcb.py init`. Fix any error you see and re-run.
4. AI engine: pcb-advisor needs ONE of Claude Code (`claude`) or Antigravity (`agy`) installed and signed in.
   - Use the one you are running as, if it is one of these. Otherwise check `claude --version` and `agy --version`.
   - If neither exists, ask me which I prefer, then install it per docs/ENGINES.md and tell me to sign in
     (`claude` or `agy`, finish the browser login, exit). Wait for me to confirm.
5. Connect: from the repo folder run
   `.venv\Scripts\python pcb.py config agent.provider <claude_code|antigravity>`
   (macOS/Linux: `.venv/bin/python`). If the CLI is not found on PATH, set its full path with
   `pcb.py config agent.providers.<provider>.command "<full path>"` (see docs/ENGINES.md section 4).
6. Verify: run `pcb.py engines` (the chosen one must have `*` and say ready), then `pcb.py probe`.
   If probe fails, read the error, fix the cause (sign-in, PATH, timeout) and run it again.
7. Optional: ask me whether to run `pcb.py seed` (a finished example project).
8. Start: run `start.bat` (or `./start.sh`) in the background, check http://localhost:8931 answers, and tell me
   to open it. Then tell me how to start it next time.

Do not change any file in the repo. Do not store or print any password or token.
```
