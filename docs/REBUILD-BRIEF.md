# Rebuild brief: PCB Advisor v2

For the agent rebuilding pcb-advisor. Written 2026-10-09 from the decisions Ilai
made while reviewing the mock. Read this whole file, then open the mock, before
touching code.

- **Mock (the visual and behavioural spec):** `docs/mock/pcb-advisor-mock.html`.
  Open it in a browser and click through it. It is self-contained; its data is
  sample data.
- **Published copy of the same mock:** https://claude.ai/artifact/HJvr4Q8yJwedoXoZXJF7E3
- **Branch you inherit:** `wip/antigravity-ide-ui`. It has uncommitted work,
  including the Windows/macOS fixes in `scripts/oscompat.py`. Commit that as it
  is before you start, so your rebuild diff stays readable.

---

## 1. What changes, in one paragraph

v1 was a decision cascade: the system asked questions from YAML graphs and the
student answered. Ilai found the cascade hard to understand and did not see its
value, so **it is removed**. v2 is a co-pilot: **the chat with an agent is the
main interface**. The agent has skills (check stock, compare prices, download
models, build parts, build an Altium library, verify against datasheets, render
a schematic) and cites a knowledge base (course material + project sources).
The student arrives with a rough idea. The agent helps refine it, then helps
with everything about parts. The student leaves the first stage with three
outputs:

1. **A BOM.** Editable, with stock, price and manufacturer for every line.
2. **An example schematic.** Rendered from a netlist, in the style of the mock's
   sheet 03, for the student to redraw in Altium.
3. **An Altium library (.IntLib).** Only the parts that are *not* in Altium's
   default libraries, each marked verified or not.

Out of scope for v2: layout, routing, Gerbers, manufacturer DFM, the written
report, and a dark theme.

---

## 2. Layout (from the mock)

Three columns, **English UI**, **light theme only** (do not ship dark CSS yet).

| Left | Center | Right |
|---|---|---|
| **Chat.** Header button opens the conversation list. "+ New" starts one. | **Main screen.** Tabs: **Idea · BOM · Schematic**. A part-detail drawer slides in from the right edge of this column. | **Navigation.** Projects; Workspace (→ Idea / BOM / Schematic); Altium library; Sources; Skills; Settings. |

Behaviours the mock demonstrates, and v2 must keep:

- **Conversations.**
  - Two kinds: *project conversations*, and *part conversations* anchored to a
    BOM line (refdes).
  - "Discuss this part" opens or creates the part conversation. Its first
    message is a context card: MPN, sheet/block, nets, datasheet.
- **Agent turn rendering.**
  - Prose.
  - A compact list of tool/skill runs with status (ok / warning / running).
  - Citation chips (`file name · locator`). Clicking a chip opens Sources and
    highlights that file.
- **BOM change proposals.**
  - A BOM change from the agent is a **diff card** with Approve / Reject.
  - Nothing changes until the student approves.
  - Approving updates the BOM, the schematic label and the library together.
- **BOM tab.**
  - KPIs: lines, parts to place, cost per board, out of stock, to verify.
  - A table where MPN and Note are editable inline. Editing an MPN marks the
    line "checking" until the agent re-checks stock.
  - Each line shows which schematic block(s) it appears in.
- **Part drawer.**
  - Where the part is used (refdes → sheet → block), its nets, and stock/price
    per supplier with the check time.
  - Library status (symbol / footprint / 3D, model source, verified) and the
    datasheet.
  - Buttons: "Discuss this part" and "Show on schematic".
- **Schematic tab.**
  - Rendered from the netlist.
  - Clicking a part selects its BOM line. Selecting a BOM line highlights its
    parts and dims the rest.
  - Sheet tabs; sheets not yet drawn are disabled.
- **Idea tab.**
  - "Agreed" items, each with who proposed it and its status.
  - A block diagram, and a checklist against the final-project rules, citing
    `final-project-guidelines.pdf`.
- **Sources page.**
  - Two groups: *Shared library* (every project) and *Project sources*.
  - Columns: file, type, size, origin, sha256, text extracted, used for.
  - Upload and Add-from-URL.
- **Altium library page.**
  - Non-standard parts only, with symbol / footprint / 3D / model source /
    status. "Export for Altium" warns when something is still unverified.
  - Install instructions citing AD20 Essentials Module 29.
- **Hebrew in chat.** The UI is English, but students may type Hebrew. Message
  bubbles and inputs use `dir="auto"`.

The mock's JavaScript is a reasonable starting point for `ui/index.html`,
especially `buildSchematic()` and its helpers (`ic`, `resH`, `capV`, `tvs`,
`tp`, `netEnd`). Move the hard-coded data out to files the server serves.

---

## 3. Keep, remove, change

**Keep (it works and is tested):**

- `scripts/gateway/`: engines behind one interface (Claude Code CLI, Antigravity).
- `scripts/oscompat.py`: every macOS/Windows difference. New platform-specific
  code goes here, nowhere else.
- `scripts/sources.py` and `scripts/verify_sources.py`: the sources format (file
  + `.json` sidecar `{name, url, sha256, bytes}` + extracted `.txt`), the shared
  cache, and verbatim-quote verification. **This is the knowledge base**, and
  its format does not change.
- `scripts/session.py`: per-conversation `chats/<id>.jsonl`, `index.json`, and
  memory files. Add an optional `anchor` (refdes) to a conversation.
- `scripts/workspace.py`: folder layout and config. Extend it; do not rewrite it.
- The action channel: prose, then a fenced `{"actions":[...]}` block that the
  **server** applies. The agent never writes state files directly.
- The principle: **append-only logs are the truth, everything else is derived.**
- `scripts/trace_width.py`.

**Remove:**

- `cascade/*.yaml`, `scripts/validate_cascade.py`, `scripts/render_constraints.py`,
  and `reference/*.md` (the human copy of the cascade).
- In `scripts/model.py`: the cascade engine (questions, answers, constraints,
  defaults, conflicts, graph).
- In `scripts/serve.py` (`apply_actions`): the `answer` and `retract` actions.
- Their tests. Also remove the "the corpus validates" CI step.
- `update_bom_read.py` (an untracked one-off patch script) and `scratch/`.
- In the rule pack (`.agents/rules/*.md`) and
  `.claude/skills/pcb-design-advisor/SKILL.md`: rewrite whatever talks about
  cascades, nodes or constraints.

**Change:**

- `sketch.json` becomes `idea.json` (see §4). Migrate existing projects.
- `scripts/render_schematic.py`: the schemdraw block diagram becomes the Idea
  tab's diagram. The sheet schematic is a separate renderer that works from
  the netlist (§4).
- `ui/index.html`: rebuild it from the mock.

---

## 4. Data, per project

```
projects/<name>/
  project.json
  idea.json            goal, agreed items [{topic, text, by: student|agent, status}],
                       blocks, links, confirmed
  bom-log.jsonl        APPEND-ONLY. One line per applied change:
                       {at, by: student|agent-approved, line, before, after, reason, sources[]}
  bom.json             DERIVED from bom-log.jsonl. Never hand-edited
  netlist/<sheet>.json sheet id + title, sections [{id, title}],
                       parts [{ref, section, symbol, pins:[{name, num, net}]}], notes
  library/             symbols, footprints, STEP; library.json manifest;
                       <Project>.IntLib output
  sources/             project sources, same format as the shared library
  chats/               <id>.jsonl, index.json (now with anchor), <id>.memory.md
  notes.md
```

**BOM line fields:**

- `key`, `refs[]`, `value`, `description`, `mpn`, `manufacturer`, `package`,
  `dnp`, `nobuy`, `note`.
- `supply`: `{supplier: {stock, unit_price, qty_break, checked_at}}`.
- `library`: `std | ok | review | missing`, plus `model_source` and
  `parts {symbol, footprint, step}`.
- `datasheet`: the source id.

The netlist's `ref` must exist in the BOM, and every pin needs a net or an
explicit `NC`. A script checks both before a sheet renders.

**Shared library.** Keep `workspace.datasheets_dir()` (`shared/datasheets/`) as
the path, even though it now holds course material too. The UI calls it
"Shared library". Seed it with:

- `AD20 Essentials Course Exercises.pdf`
- `PCB Design Lecture 3 - Schematic Simulation.pdf`
- the final-project guidelines PDF, as `final-project-guidelines.pdf`
- `unit1..unit4 *.md`
- `altium_schematic_guide.md`

All of these sit one folder up from the repo, in `../`, `../altium/` and
`../פרויקט סיום/`. They are copyrighted course material: do not commit the
PDFs. Commit their sidecars only, the way vendor PDFs are handled today.

---

## 5. Agent actions (new)

Keep the existing reply format. Replace the cascade action types with:

| type | effect |
|---|---|
| `idea.propose` | Proposes or changes an agreed item. The student confirms in the Idea tab or the chat. |
| `idea.confirm` | Only after the student says yes in chat. Marks the idea confirmed. |
| `bom.propose` | `{line or new, changes, reason, sources[]}`. Renders a diff card. Applied only when the student approves, by appending to `bom-log.jsonl`. |
| `netlist.write` | Writes `netlist/<sheet>.json` through the validating script. |
| `library.add` | Adds a manifest entry. It stays `verified: false` until the verify skill passes **and** the student accepts. |
| `thread.open` | Opens a part conversation anchored to a refdes. |
| `sheet` / `ask` | Keep `ask` (anchored note). Anchors are now refdes or sheet ids. |

**Citations.**

- Every factual claim about a part cites a source id + locator.
- A quoted sentence must pass `sources.py verify` before it is shown.
- Stock and price are never stated from memory. They always come from a
  skill run, with a time.

---

## 6. Skills

A separate agent already built and ran these successfully. It is writing them
up as reusable skills: availability check, price comparison, model download
(SnapEDA / Ultra Librarian), build part from datasheet, convert to Altium
(SchLib + PcbLib → IntLib), fix and verify against the datasheet.

- **TODO (Ilai):** give the path or repo of those skills. Do not re-implement
  them before checking.
- **Placement:** in `.claude/skills/<name>/SKILL.md` with their scripts in
  `scripts/skills/`.
- **Invocation:** through the allow-list as `Bash({python} scripts/skills/<x>.py *)`.
  Add each one to `config/defaults.json`.
- **Hard requirement: every skill must run on Windows and macOS.**
  - Python only.
  - No bash-only tools (`sed`, `grep`, `curl`, `unzip` from the shell).
  - Paths via `pathlib`; text I/O with `encoding="utf-8"`; subprocesses
    through `oscompat`.
  - Altium itself is Windows-only, so any step that drives Altium (a
    DelphiScript, say) has to run on the Windows machine.

New skills for v2:

- **Render schematic from netlist.**
- **Export BOM for a manufacturer** (PCBWay / JLC columns).

---

## 7. Cross-platform rules (do not regress)

- Never add `text=True` to a subprocess without `encoding`. Use `**oscompat.TEXT`.
- Never put a bare `"python3"` in a command the engine runs. Use `{python}` in
  config, or `oscompat.py(...)` in code.
- Run CLIs through `oscompat.resolve(cmd)`.
- Paths shown to the engine use `.as_posix()`.
- File names from users or the web go through the same sanitising as
  `workspace.safe_name` / the upload handler.
- Add a `.gitattributes` with `* text=auto eol=lf`, so the Windows checkout
  does not rewrite `.jsonl`, `.json` and `.md` to CRLF.
- The CI matrix runs on Windows, macOS and Linux. Keep it green on all three.

---

## 8. Seed project and definition of done

Create `projects/lte-tracker`, using the mock's data as the seed (sheet 03 Modem:
U4 A7670G, U5 TXS0104E, Q3, D30, D31, J6, J7, the passives, TP12–TP18).

v2 is done when all of this works in the real app, not just in tests:

1. A new conversation refines an idea and confirms it, and the Idea tab fills.
2. The agent produces a BOM. A stock/price check runs. One `bom.propose` diff
   is approved, and the BOM, schematic label and library all update.
3. Editing an MPN in the table marks the line "checking", and the agent
   re-checks it.
4. Sheet 03 renders from `netlist/03.json`, with click-through both ways
   between the schematic and the BOM.
5. "Discuss this part" opens an anchored conversation with the context card.
6. Every citation chip resolves to a file in Sources.
7. `<Project>.IntLib` is produced, and unverified parts are flagged on export.
8. `python -m pytest` passes and CI is green on all three OSes.
9. `docs/WINDOWS-HANDOFF.md` is updated with anything new to verify, then
   executed on the Windows machine.

---

## 9. Suggested order

1. Commit the inherited work. Add `.gitattributes`.
2. Remove the cascade and its tests, and get the suite green again.
3. Data layer: `idea.json`, `bom-log.jsonl` → `bom.json`, netlist plus its
   validator, and the migration.
4. New action types in the server, plus the rule pack rewrite.
5. UI rebuild from the mock, against real data.
6. Skills import (§6), library manifest and IntLib output.
7. Seed `lte-tracker`, walk the definition of done, then hand off to Windows.
