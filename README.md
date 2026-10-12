# pcb-advisor

A local AI co-pilot for a student's PCB design project (Altium Designer + JLCPCB manufacturing).
The chat with an agent is the main interface. The student arrives with a rough idea; the agent helps
refine requirements, pick and verify parts, review schematic and layout, configure rules, generate
manufacturing packages, and triage manufacturer DFM reports.

Altium files are read **read-only** from a local folder. The tool prepares what goes into Altium and
checks what comes out; it never drives Altium's GUI, never routes, never orders, and never logs in for the student.

## Capabilities and Workspace Tabs

Seven tabs guide the design across the product lifecycle:

1. **Idea** - agreed requirements, interactive mouse-editable block diagram (drag, rename, link, domain colors, board outline), and agent architecture proposals.
2. **BOM** - interactive parts table with live JLC availability, unit pricing, cost per board, risk tags, role notes, datasheet links, and in-stock alternatives.
3. **Schematic** - Python-rendered interactive preview from SchDoc or netlist; one-click questions on any part or connection ("Ask about this").
4. **Placement & routing** - interactive board preview (outline, pads, layer toggle), placement plan overlay, and critical-net routing plan.
5. **Rules** - JLC manufacturing capability preset, custom rules, diff of board rules against preset, `.RUL` export with a 4-step Altium import guide, and engineering calculators (IPC-2152 trace width, voltage divider, LED resistor, via current, microstrip impedance).
6. **Altium outputs** - ready OutJob generator (Gerber RS-274X, NC drill, JLC BOM, CPL, schematic PDF), CPL exporter, and IntLib library build script.
7. **Final manufacturer checks** - JLCDFM report PDF ingest (slice extraction + triage table: severity, counts, layer) and triage chat to distinguish real faults from false alarms.

Cross-cutting features:
- **In-app file viewer** - view PDF datasheets, images, text/markdown, CSV, and Altium document summaries directly in the app without leaving the workspace. Citation chips open files directly.
- **Settings with Altium link** - link local Altium projects (PrjPcb, PcbDoc, sheets, output folder) with detected installs from the Windows registry.
- **Knowledge base (Sources)** - manage course references and project datasheets with automated quote verification.

## Setup and Running

Requires Python 3.10+ (Pillow is required for preview rendering and DFM report slicing).

```bash
pip install -r requirements-dev.txt   # includes Pillow and test dependencies
python pcb.py init                    # create folders and config.json
python pcb.py seed                    # worked example: projects/lte-tracker
python pcb.py serve                   # start the server and open http://localhost:8931
```

## CLI Commands

`pcb.py` is the single entry point for workspace management:

```bash
python pcb.py init                                      # create workspace folders and config.json
python pcb.py serve                                     # start the server, open browser (also: run)
python pcb.py new "usb sensor"                          # start a new project from template
python pcb.py list                                      # list all projects in the workspace
python pcb.py show [project]                            # show project state (BOM, stock, proposals, checklist)
python pcb.py seed                                      # initialize worked example (projects/lte-tracker)
python pcb.py engines                                   # list configured AI engines (* = active)
python pcb.py tools [--apply|--clear]                   # view or set engine tool permission policies
python pcb.py probe [--engine X]                        # verify engine loads the runtime pack and skills
python pcb.py bench [--engine X] [--evals] [--only 1,5] # run device replay benchmark
python pcb.py skills lint [--only NAME]                 # lint runtime skills format and consistency
python pcb.py chats [project]                           # list conversations and memory status
python pcb.py config [key] [value]                      # read or set configuration values
python pcb.py check [project]                           # validate sheets against BOM and verify citations
python pcb.py reset [project]                           # wipe project state
python pcb.py trace 1.5                                 # calculate IPC-2221 trace width
python pcb.py rules diff|export|preset                  # diff rules vs JLC preset, export .RUL, show preset
python pcb.py calc trace-width|divider|led|via|microstrip # engineering calculators
python pcb.py library search|check-package|build-script # model search, package check, IntLib script
```

## AI Engines

pcb-advisor connects to external AI CLIs via `scripts/gateway/`:
- **Claude Code** (`claude`)
- **Antigravity CLI** (`agy`)

See [docs/ENGINES.md](docs/ENGINES.md) for installation and setup.

## Tests

```bash
python -m pytest -q
python scripts/skills/lint.py
```

## Layout

| path | what |
|---|---|
| `pcb.py` | CLI entry point |
| `config/defaults.json` | default settings |
| `scripts/serve.py` | HTTP server and single state writer |
| `scripts/store.py` | append-only logs and derived state |
| `scripts/model.py` | project state model |
| `scripts/agent.py` | prompt construction and action dispatcher |
| `scripts/workspace.py` | workspace paths and environment |
| `scripts/oscompat.py` | cross-platform helpers (Windows & macOS) |
| `scripts/runtime_pack.py` | syncs runtime pack to engine home |
| `scripts/sources.py` | document caching, retrieval, and quote verification |
| `scripts/jlc.py` | JLC parts API client and cache |
| `scripts/rules.py` | JLC rules preset, .RUL exporter, and board diff |
| `scripts/calc.py` | IPC-2152 trace width and engineering calculators |
| `scripts/library.py` | model search links, package check, and IntLib build script |
| `scripts/outjob.py` | Altium OutJob file generator |
| `scripts/dfm.py` | JLCDFM PDF report slicer and triage table |
| `scripts/keeping.py` | decision log, change impact, and file organization |
| `scripts/preview_sch.py` | SchDoc interactive SVG preview renderer |
| `scripts/preview_pcb.py` | PcbDoc interactive SVG preview renderer |
| `scripts/altium/` | read-only Altium document readers (SchDoc, PcbDoc, PrjPcb, .RUL) |
| `scripts/checks/` | layout and schematic review checks |
| `scripts/skills/` | skill-specific scripts run by the engine |
| `scripts/gateway/` | AI engine CLI abstraction layer |
| `runtime/` | AGENTS.md constitution and skill definitions |
| `ui/index.html` | browser UI |
| `tests/` | automated test suite |
| `docs/` | architecture, engines guide, and product specs |
