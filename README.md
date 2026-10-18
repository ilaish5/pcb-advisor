# pcb-advisor

An AI co-pilot for your PCB project (Altium Designer + JLCPCB). You chat with an agent in the browser:
it helps you refine the idea, pick parts that are in stock at JLC, check the schematic and layout against
datasheets, prepare Altium rules and outputs, and understand the manufacturer's DFM report.

It never drives Altium, never routes, never orders. It reads your Altium files (read-only) and tells you what to do.

## Install (about 5 minutes)

You need **Python 3.10+** and **one AI engine** (Claude Code or Antigravity).

1. **Get the tool**
   ```
   git clone https://github.com/ilaish5/pcb-advisor.git
   cd pcb-advisor
   ```
   (or click *Code > Download ZIP* on GitHub and unzip it)
2. **Install** - double-click `install.bat` (macOS/Linux: run `./install.sh`).
3. **Install and sign in to an AI engine, once** - follow [docs/ENGINES.md](docs/ENGINES.md)
   (two commands for Claude Code or Antigravity).

**Easier:** open any AI agent in a terminal and paste the prompt from [SETUP-PROMPT.md](SETUP-PROMPT.md) - it does all the steps above and connects the engine for you.

## Run

Double-click `start.bat` (macOS/Linux: `./start.sh`). The browser opens at http://localhost:8931.
Create a project, describe your board in the chat, and follow the tabs from left to right:
Idea, BOM, Schematic, Placement, Rules, Altium outputs, Final checks.

The install comes with an example project, "LED chaser" (USB-C, NE555, CD4017, 10 LEDs): idea, BOM and a schematic sheet, no Altium files yet.

Want to see a finished example first? Run `.venv\Scripts\python pcb.py seed` and open the project `lte-tracker`.

## Problems?

- `.venv\Scripts\python pcb.py probe` (macOS/Linux: `.venv/bin/python`) checks that your AI engine works with the tool.
- `.venv\Scripts\python pcb.py list` shows your projects. Projects live in the `projects/` folder, all on your machine.

## For developers

```
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q
```

Code: `scripts/serve.py` (server), `scripts/store.py` (project state), `scripts/agent.py` (agent actions), `ui/index.html` (UI).
Docs: [architecture](docs/ARCHITECTURE.md), [engines](docs/ENGINES.md), [product plan](docs/PRODUCT-PLAN.md).
Commands: `.venv\Scripts\python pcb.py --help` (macOS/Linux: `.venv/bin/python`). License: [MIT](LICENSE).
