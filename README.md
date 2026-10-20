# pcb-advisor

> **If you are an AI agent asked to install this:** read [INSTALL-AGENT.md](INSTALL-AGENT.md) and follow it. It is
> one command, then `pcb.py doctor`; ask the person only for the browser sign-in or a yes to installing a program.

An AI co-pilot for your PCB project (Altium Designer + JLCPCB). You chat with an agent in the browser:
it helps you refine the idea, pick parts that are in stock at JLC, check the schematic and layout against
datasheets, prepare Altium rules and outputs, and understand the manufacturer's DFM report.

It reads your Altium files and can create the Altium project for you (project, empty PCB, sheets with a skeleton and no components, through `scripts/altium/bridge.py`); it never places components, routes or orders.

## Install (about 5 minutes)

**One command**, in a terminal. It installs what is missing (Python, git, the Claude Code AI engine), sets everything
up, checks it, and starts the app. It asks before installing anything (Enter = yes) and needs no administrator rights.

- **Windows** (PowerShell):
  ```
  powershell -NoProfile -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/ilaish5/pcb-advisor/main/install.ps1 | iex"
  ```
- **macOS / Linux**:
  ```
  curl -fsSL https://raw.githubusercontent.com/ilaish5/pcb-advisor/main/install.sh | bash
  ```

It puts the tool in `pcb-advisor` in your home folder. Run the same command again any time to repair or update it.

**Or let an AI agent do it.** Open Claude Code (or any CLI agent) and paste:
`Install pcb-advisor from https://github.com/ilaish5/pcb-advisor following INSTALL-AGENT.md`

**Or by hand:** `git clone https://github.com/ilaish5/pcb-advisor.git` (or *Code > Download ZIP* and unzip; for the in-app
Update, install git later and run the installer again: it turns the folder into a clone and keeps your projects), then double-click `install.bat` (macOS/Linux: `./install.sh`). Install and sign in to an AI
engine once: [docs/ENGINES.md](docs/ENGINES.md).

Something not working? `.venv\Scripts\python pcb.py doctor` (macOS/Linux: `.venv/bin/python`) lists what is missing and
the one command that fixes each item; the same list is in the app under Settings > Engine > Run checks.

## Run

Double-click `start.bat` (macOS/Linux: `./start.sh`); the installer already started it the first time. The browser opens at http://localhost:8931.
Create a project, describe your board in the chat, and follow the tabs from left to right:
Idea, BOM, Schematic, Placement, Rules, Altium outputs, Final checks.

The install comes with an example project, "LED chaser" (USB-C, NE555, CD4017, 10 LEDs): idea, BOM and a schematic sheet, no Altium files yet.

**Updates.** At every start the tool checks GitHub. When there is a new version, an **Update** button shows at the bottom left: it lists what changed, updates, and restarts by itself (your projects and settings are not touched; if the new version does not start, it goes back). This needs the `git clone` install; a ZIP install shows the download link instead. From a terminal: `.venv\Scripts\python pcb.py update`.

Want to see a finished example first? Run `.venv\Scripts\python pcb.py seed` and open the project `lte-tracker`.

## Problems?

- `.venv\Scripts\python pcb.py doctor` checks the whole setup (Python, packages, git, Claude Code and its sign-in, port).
- `.venv\Scripts\python pcb.py probe` (macOS/Linux: `.venv/bin/python`) checks that your AI engine works with the tool.
- `.venv\Scripts\python pcb.py list` shows your projects. Projects live in the `projects/` folder, all on your machine.

## For developers

```
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q
```

Code: `scripts/serve.py` (server), `scripts/store.py` (project state), `scripts/agent.py` (agent actions), `ui/index.html` (UI).
Docs: [architecture](docs/ARCHITECTURE.md), [engines](docs/ENGINES.md), [product plan](docs/PRODUCT-PLAN.md).
Windows verification still open: [docs/next-tasks/windows-verification.md](docs/next-tasks/windows-verification.md)
(a brief for an agent on a Windows PC: everything that could only be checked there, with the results file it writes).
Commands: `.venv\Scripts\python pcb.py --help` (macOS/Linux: `.venv/bin/python`). License: [MIT](LICENSE).

Credits: the way `scripts/altium/bridge.py` starts Altium scripts and exchanges files with them is adapted from [altium-mcp](https://github.com/coffeenmusic/altium-mcp) (MIT, Copyright (c) 2025 Siddharth Ahuja; licence kept in `scripts/altium/bridge/LICENSE-altium-mcp`).
