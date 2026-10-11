# pcb-advisor

A co-pilot for a student's PCB project. The chat with an agent is the main interface. The student
arrives with a rough idea; the agent helps refine it, then helps with everything about parts, and the
student leaves the first stage with three outputs:

1. **A BOM** - editable, with stock, price and manufacturer for every line.
2. **An example schematic** - drawn from a netlist, for the student to redraw in Altium.
3. **An Altium library package** - only the parts Altium does not ship, each marked verified or not.

Out of scope for now: layout, routing, Gerbers, manufacturer DFM, the written report.

```bash
pip install -r requirements.txt
python3 pcb.py init                       # folders + config.json
python3 pcb.py seed                       # the worked example: projects/lte-tracker
python3 pcb.py serve --project lte-tracker   # opens http://localhost:8931
```

Everything else:

```bash
python3 pcb.py new "usb sensor board"   # start a project from the template
python3 pcb.py list                     # what is in the workspace
python3 pcb.py show lte-tracker         # where it stands: BOM, stock, pending proposals, checklist
python3 pcb.py check                    # every sheet validates against the BOM, every citation resolves
python3 pcb.py engines                  # which LLM engine is wired up
python3 pcb.py tools                    # what that engine may touch on your machine
python3 pcb.py config user.language he  # read or set any setting
python3 pcb.py trace 1.5                # IPC-2221 trace width
```

## The screen

Three columns, English UI, light theme.

| Left | Centre | Right |
|---|---|---|
| **Chat.** A conversation list, "+ New". A part conversation is anchored to a BOM line. | **Idea · BOM · Schematic**, and a part drawer that slides in. | Projects, Workspace, Altium library, Sources, Skills, Settings. |

- **Idea** - the agreed items (each with who proposed it and its status), the block diagram, and a checklist
  against the final-project rules computed from the BOM.
- **BOM** - KPIs, an editable table (MPN and note), stock and price per supplier. Editing an MPN marks the
  line "checking" until a skill run answers for the new part.
- **Schematic** - drawn from `netlist/<sheet>.json` and the BOM. Click a part to open its BOM line; select a
  BOM line to light up its parts.
- **A BOM change from the agent is a diff card** with Approve / Reject. Nothing changes until the student
  approves; approving updates the BOM, the schematic label and the library together.
- **Altium library** - non-standard parts with symbol / footprint / 3D / model source / status. A part is
  "verified" only when a skill checked it against its datasheet **and** the student accepted it.
- **Sources** - the shared library (course material) and the project's documents, each with a `.json`
  sidecar (url, sha256, bytes) and extracted text. Every citation chip in the chat opens a file here.

## Where things live

```
projects/<name>/
  project.json
  idea.json            goal, agreed items, blocks, links, checklist        (server-written)
  bom-log.jsonl        APPEND-ONLY, one line per applied change
  bom.json             DERIVED from the logs. Never hand-edited
  supply-log.jsonl     APPEND-ONLY stock and price checks, with supplier and time
  proposals.jsonl      APPEND-ONLY agent proposals and the student's decisions
  library-log.jsonl    APPEND-ONLY library parts, model source, verification
  netlist/<sheet>.json one sheet, validated against the BOM before it is written
  chats/               <id>.jsonl, index.json (with anchors), <id>.memory.md
  sources/             the project's documents (file + .json + .txt)
  exports/             BOM exports and the library package
  notes.md
shared/datasheets/     fetched once, sha256'd, reused by every project
```

The principle: **append-only logs are the truth, everything else is derived.** The server is the only
writer; an agent proposes actions and the server validates and applies them
(see [docs/gateway.md](docs/gateway.md)).

## Skills

Python, cross-platform, in `scripts/skills/`. The agent runs them; the BOM page buttons run the same code.

| skill | what |
|---|---|
| `check_availability.py` | stock and price: LCSC (JLCPCB parts search); Mouser with `MOUSER_API_KEY` |
| `compare_prices.py` | cost per board by supplier, from the stored checks |
| `verify_part.py` | a part's pins against its datasheet text |
| `export_bom.py` | JLC, PCBWay and generic CSV |
| `render_sheet.py` | a sheet drawn from its netlist |

Not built yet: download models, build a part from a datasheet, compile an IntLib. See
[docs/archive/V2-STATUS.md](docs/archive/V2-STATUS.md).

## Windows and macOS

Both are supported. The commands above say `python3`, which is what macOS calls
it; on Windows type `python` (or `py`) instead - everything else is the same.

What differs between the two lives in `scripts/oscompat.py`, nowhere else:

- every child process is spoken to in UTF-8, so Hebrew survives a Windows console;
- the engine CLI is run by its full path, because npm installs `claude.cmd` on
  Windows and subprocess cannot start a `.cmd` by its bare name;
- the commands the engine may run are written `{python} scripts/...` in
  `config/defaults.json` and filled in per machine, so the allow-list matches
  what its shell actually types;
- paths handed to the engine use forward slashes on both.

CI runs the suite on Windows, macOS and Linux. `docs/archive/WINDOWS-HANDOFF.md` is the checklist for verifying a
build on a Windows machine.

## One workspace folder

`PCB_ADVISOR_HOME` moves your work (`projects/`, `shared/`, `config.json`) somewhere else; the program
(`scripts/`, `ui/`, `templates/`) stays with the install. Nothing is hardcoded: every path, the port, the
default project and the LLM engine come from the config. See [docs/configuration.md](docs/configuration.md).

## Any engine behind one gateway

`scripts/gateway/` routes a turn to whichever LLM you configured. A provider is a transport and nothing
more: text in, text out. Claude Code and Antigravity (`agy`) route today; the rest are registered but not
implemented. See [docs/gateway.md](docs/gateway.md).

**Install and sign in to an engine first:** [docs/ENGINES.md](docs/ENGINES.md) - Claude Code or the
Antigravity CLI (`agy`) on Windows, then `python pcb.py config agent.provider <id>`.

## Layout

| path | what |
|---|---|
| `pcb.py` | the entry point |
| `config/defaults.json` | every setting, with its shipped value |
| `scripts/store.py` | the logs and their derived views; netlist validation |
| `scripts/model.py` | the whole project as one dict, for the UI and the agent |
| `scripts/serve.py` | the HTTP server and the only writer |
| `scripts/agent.py` | the reply protocol and the prompt |
| `scripts/gateway/` | LLM routing |
| `scripts/skills/` | what the agent can run |
| `scripts/sources.py` | fetch, cache, extract, verify a quote word for word |
| `scripts/seed.py` | the lte-tracker example |
| `.agents/rules/*.md`, `.claude/skills/` | the agent's rules |
| `ui/index.html` | the screen |
| `docs/archive/mock/` | the visual and behavioural spec the UI was built from |
| `tests/` | the defects that reached a student once, and the contract of the write path |
| `tests/fixtures/altium/` | real Altium files (AD20 course exercises) for the read-only reader |
| `shared/reference/` | course material the agent answers from; map and topic index in its `AGENTS.md` |
| `PLAN.md` | the implementation plan: single source of truth for the build |
| `docs/PRODUCT-PLAN.md` | what the tool does and why (pain points, capabilities, decisions, feasibility) |
| `docs/ENGINES.md` | install and configure Claude Code / Antigravity |
| `docs/feasibility/` | the probes that proved the Altium, JLC and .RUL formats |
| `docs/archive/` | history of the v2 rebuild |
