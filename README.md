# pcb-advisor

> **If you are an AI agent asked to install this:** read [INSTALL-AGENT.md](INSTALL-AGENT.md) and follow it. It is
> one command, then `pcb.py doctor`; ask the person only for the browser sign-in or a yes to installing a program.

An AI co-pilot for your PCB project (Altium Designer + JLCPCB). You chat with an agent in the browser:
it helps you refine the idea, pick parts that are in stock at JLC, check the schematic and layout against
datasheets, prepare Altium rules and outputs, and understand the manufacturer's DFM report.

It reads your Altium files and can create the Altium project for you (project, empty PCB, sheets with a skeleton, through `scripts/altium/bridge.py`). When you choose it, the agent also draws the schematic, places the parts and routes the board in Altium; you can do any of these yourself instead. It never places the order: that is yours.

## What you need

- **Windows 10 or 11** with **Altium Designer** (tested on AD26), opened and signed in once. Without Altium (or on macOS / Linux)
  everything except the Altium steps works: idea, parts, the planned schematic, checks, DFM.
- **An AI engine account:** Claude Pro/Max or an Anthropic Console account (for Claude Code), or Google (for Antigravity). The installer asks which one.
- Internet for the install, for JLC stock and prices, and for datasheets. No administrator rights.

## Install (about 5 minutes)

**One command**, in a terminal. It installs what is missing (Python, git, an AI engine: it detects Claude Code or Antigravity and asks which to install), sets everything
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

## Try it (about 15 minutes)

1. Open http://localhost:8931, press **New project**, and describe a small board in the chat, for example: *"A 30 x 20 mm
   board with an NE555 blinking a red LED twice a second, 5 V from a 2-pin header, SMD parts. You decide the rest."*
2. **Idea:** the agent drafts the requirements; Save, then tell it the idea is ready.
3. **BOM:** it picks JLC parts with live stock and price; approve the cards.
4. **Schematic:** ask it to create the Altium project and write the schematic. The planned sheet shows here; **Draw in
   Altium** draws it (Altium opens by itself; the parts library is built first when needed).
5. **Layout:** **Place parts**, then **Route board**. The JLC rules are imported first, the result is checked with
   Altium's DRC, and a GND pour is added.
6. **Outputs:** **Generate outputs in Altium**, then *Export > Gerber zip for JLC*. **DFM** walks you through the free
   check at jlcdfm.com and reads its report back.

Every Altium step copies the file to `.advisor-backup` first. Parts whose pins no datasheet confirmed are listed under
DFM > Unverified parts; the Altium outputs and the Gerber zip are not made until each one is verified against its datasheet or you accept it there.

## Run

Double-click `start.bat` (macOS/Linux: `./start.sh`); the installer already started it the first time. The browser opens at http://localhost:8931.
Create a project, describe your board in the chat, and follow the tabs from left to right:
Idea, BOM, Schematic, Layout, Rules, Outputs, DFM.

The install comes with an example project, "LED chaser" (USB-C, NE555, CD4017, 10 LEDs): idea, BOM and a schematic sheet, no Altium files yet.

**Updates.** At every start the tool checks GitHub. When there is a new version, an **Update** button shows at the bottom left: it lists what changed, updates, and restarts by itself (your projects and settings are not touched; if the new version does not start, it goes back). This needs the `git clone` install; a ZIP install shows the download link instead. From a terminal: `.venv\Scripts\python pcb.py update`.

Want to see a finished example first? Run `.venv\Scripts\python pcb.py seed` and open the project `lte-tracker`.

## Capabilities and limits

**What it does.** Draws the schematic, places the parts and routes the board in Altium, on two copper layers, up to about 60 parts.
Placement keeps each decoupling capacitor within 3 mm of its supply pin and a crystal within 5 mm of its MCU pins. The router sets
track width by the current you give a net (IPC-2221, neck-down at fine-pitch pads), routes a USB differential pair coupled when the
clearances allow, adds a GND pour and checks it for islands and unjoined pads. The Altium DRC list is read in full: a report that
is truncated or unreadable counts as "unchecked", never as clean.

**What it refuses, and says so before routing:** copper on inner layers, BGA packages, pads of different nets closer than 0.4 mm,
impedance or length-matching rules (other than the USB pair), and a board too big for the router.

**Known limits.**
- A 3x3 BGA is not recognised as a BGA, and a board with an empty inner layer is not detected as multilayer.
- On the synthetic 60-part STM32 test board all 45 nets are routed with GND dropped to the pour (see
  [docs/SUBMISSION.md](docs/SUBMISSION.md)). The USB pair is routed and tied but not coupled on that board.
- Automatic split of a design over several schematic sheets and multi-part symbols are not done.
- A synthetic 26-part STM32 test board was also placed and routed live in Altium (18/18 nets with the GND pour, Altium DRC 0 clearance / 0 short / 0 un-routed); see [docs/SUBMISSION.md](docs/SUBMISSION.md) section 5.
- A part whose pins no datasheet confirmed is drawn and marked "unverified"; the manufacturing files wait until you verify or accept it.

## Problems?

- `.venv\Scripts\python pcb.py doctor` checks the whole setup (Python, packages, git, Claude Code and its sign-in, port).
- `.venv\Scripts\python pcb.py probe` (macOS/Linux: `.venv/bin/python`) checks that your AI engine works with the tool.
- `.venv\Scripts\python pcb.py list` shows your projects. Projects live in the `projects/` folder, all on your machine.

## Logs and reporting a problem

The app keeps local logs in the `logs/` folder: what ran and what failed, and for each project `usage-log.jsonl` (what you clicked and were answered). Nothing is sent anywhere.
To report a problem: Settings > **Save diagnostic report** (or `.venv\Scripts\python pcb.py report`). It makes one zip in `logs/`; attach it to your report.
The zip holds the logs, your chat with the advisor, the setup check and your settings without secrets. No datasheets or Altium files.
`pcb.py timeline <project>` reads a project's usage log as a timeline.

## For developers

```
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q        # includes the static gates: JS syntax, ruff, UI file references, AdvisorBridge.pas (tests/test_static_gates.py)
```

Code: `scripts/serve.py` (server), `scripts/store.py` (project state), `scripts/agent.py` (agent actions), `ui/index.html` (UI).
Docs: [submission summary](docs/SUBMISSION.md), [architecture](docs/ARCHITECTURE.md), [engines](docs/ENGINES.md), [product plan](docs/PRODUCT-PLAN.md), [benchmark](docs/BENCHMARK.md), [status](docs/STATUS-2026-11-11.md).
Windows verification still open: [docs/next-tasks/windows-verification.md](docs/next-tasks/windows-verification.md)
(a brief for an agent on a Windows PC: everything that could only be checked there, with the results file it writes).
Commands: `.venv\Scripts\python pcb.py --help` (macOS/Linux: `.venv/bin/python`). License: [MIT](LICENSE).

Credits: the way `scripts/altium/bridge.py` starts Altium scripts and exchanges files with them is adapted from [altium-mcp](https://github.com/coffeenmusic/altium-mcp) (MIT, Copyright (c) 2025 Siddharth Ahuja; licence kept in `scripts/altium/bridge/LICENSE-altium-mcp`).
