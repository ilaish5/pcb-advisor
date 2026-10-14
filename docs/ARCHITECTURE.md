# Architecture (stage I0 output; stages I1-I11 follow this)

What is built: `docs/PRODUCT-PLAN.md` (Hebrew). Order and method: `PLAN.md`. This file: how the parts fit and which v2
code survives. Uncertain points are marked "(decide in Ix)".

## 1. Overview

pcb-advisor is a local tool for a student's PCB project. A browser UI talks to a local Python server (`scripts/serve.py`,
the only writer of project state). The server uses a read-only Altium file reader (SchDoc, PcbDoc, PrjPcb, `.RUL`), a
JLC public-API client (stock, price, datasheets, DFM data), and an AI engine CLI (Claude Code or `agy`) reached only
through the gateway (`scripts/gateway/`). The engine runs in an engine home that holds the runtime pack (AGENTS.md +
12 skills); skills call the repo's scripts. The tool prepares what goes into Altium and checks what comes out; it never
drives Altium, routes, orders or logs in (PLAN section 2).

## 2. Components

```
 Browser UI (ui/index.html, English) --HTTP, localhost--> scripts/serve.py  (single writer)
                                                            |  workspace.py (paths, config)   project.py / store.py / model.py
          +-------------------+------------------+----------+-----------------+
          |                   |                  |                            |
   scripts/altium/      scripts/jlc.py     scripts/gateway/              projects/<name>/  (logs = truth)
   read-only reader     JLC client+cache   route() -> provider                shared/ (reference, datasheets)
   (SchDoc/PcbDoc/RUL)  (no login)            |
          ^                   ^           claude -p | agy -p   (stdin prompt, cwd = engine home, --add-dir repo + project)
          |                   |                  |
          +---- skill scripts (python scripts/skills/*.py) run BY the engine -----+
                                   runtime/ --runtime_pack.py--> engine home (outside any git repo)
```

## 3. Keep / change / replace / delete map of v2 code

Verdicts: keep = untouched except bug fixes; change = same role, edited; replace = rewritten, same slot; delete = removed.

| file | verdict | reason | stage |
|---|---|---|---|
| `scripts/agent.py` | change | action-channel adapter stays; cwd becomes engine home, add `--add-dir` repo + project (T2) | I0 |
| `scripts/gateway/__init__.py` | change | `route()`/registry stay; Request gains `add_dirs`; one-door rule kept | I0 |
| `scripts/gateway/base.py` | change | Provider/Request/Result contract; add `add_dirs` field | I0 |
| `scripts/gateway/claude_code.py` | change | prompt via stdin kept; add `--add-dir`; no developer CLAUDE.md leak | I0 |
| `scripts/gateway/antigravity.py` | change | fix: send model or `--effort`, not both; long prompt via stream-json stdin (ENGINES.md section 5) | I0 |
| `scripts/gateway/external.py` | keep | "no engine, something else drives the folder"; harmless | - |
| `scripts/gateway/planned.py` | keep | honest slots for codex etc.; no new engines planned (decide in I11) | - |
| `scripts/workspace.py` | change | add `engine_home`, Altium install/recent-project settings, JLC cache dir | I0, I3 |
| `scripts/oscompat.py` | keep | Windows-first + macOS differences in one file (PLAN rule 12) | - |
| `scripts/serve.py` | change | single writer stays; add endpoints per stage: settings/Altium (I3), parts (I4), checks (I5-I6), rules (I7), previews (I9) | I3-I10 |
| `scripts/project.py` | change | project = folder; add link to a local Altium project folder + `project.json` fields | I3 |
| `scripts/store.py` | change | append-only logs stay; supply-log becomes JLC-only with query time; add decision-log folding | I4, I10 |
| `scripts/model.py` | change | derived state; add Altium-read data (components, nets, rules) and the new checklist | I3, I5 |
| `scripts/session.py` | keep | conversations + memory are independent of the rebuild | - |
| `scripts/sources.py` | change | sha256 cache kept; add JLC datasheet download and link-and-return filing | I4 |
| `scripts/verify_sources.py` | keep | every citation must resolve; becomes part of skill lint and evals | I2 |
| `scripts/seed.py` | replace | lte-tracker mock data does not match the new flow; fixtures come from the device incidents (decide in I1: keep a small demo or drop) | I1 |
| `scripts/reset.py` | keep | wipe project state | - |
| `scripts/trace_width.py` | change | IPC-2221 stays; moves into the calculators module next to impedance/divider | I7 |
| `scripts/validate_netlist.py` | replace | checks hand-written sheet JSON vs BOM; netlists now come from PcbDoc/SchDoc readers | I6 |
| `scripts/skills/__init__.py` | keep | package marker | - |
| `scripts/skills/registry.py` | change | generate the "available" list from `runtime/skills/*/SKILL.md` frontmatter, not a hand list | I2 |
| `scripts/skills/check_availability.py` | replace | multi-source LCSC search -> JLC client with cache, risk flag, alternatives | I4 |
| `scripts/skills/compare_prices.py` | replace | multi-supplier compare is out of scope (JLC only); becomes cost-per-board column in the parts table | I4 |
| `scripts/skills/export_bom.py` | change | keep JLC format; drop pcbway/generic (decide in I5); add OutJob generator beside it | I5 |
| `scripts/skills/render_sheet.py` | change | stub+net-label renderer kept as the schematic preview engine; input from netlist model | I9 |
| `scripts/skills/verify_part.py` | change | pin-vs-datasheet text check kept; extend to package variant vs datasheet | I8 |
| `ui/index.html` | change | single-file UI stays, English only; add settings, parts table, rules tab, check/preview views; split files if too large (decide in I3) | I3-I10 |
| `templates/project/AGENT.md` | delete | project-level agent notes superseded by runtime `AGENTS.md`; leaking into engine context | I2 |
| `templates/project/{project.json,idea.json,notes.md,README.md}` | change | project.json gains Altium path; README/idea fields follow new checklist | I3, I10 |
| `templates/project/{bom,library,supply}-log.jsonl, proposals.jsonl` | keep | append-only log seeds | - |
| `templates/project/{chats,netlist,sources}/.gitkeep` | keep | empty folder markers | - |
| `pcb.py` | change | add `probe` (both engines load the pack, I0), `bench` (I1), `rules`/`check` subcommands as stages land | I0, I1 |
| `config/defaults.json` | change | add `agent.engine_home`, `altium.*`, `jlc.*`; remove per-provider tool lists that the pack makes redundant (decide in I2) | I0, I3, I4 |
| `.agents/rules/*.md`, `.claude/skills/pcb-design-advisor/` (repo root, v2 runtime rules) | delete | repo root must carry no engine-visible instructions; good content migrated into `runtime/AGENTS.md` | I0 (done) |

Judged "delete": `templates/project/AGENT.md` (superseded, and a second source of agent instructions) and the repo-root
`.agents/rules/` + `.claude/skills/` (both engines load them from the git root, which leaks developer context; migrate
first, then remove).

## 4. Runtime pack layout

```
runtime/                      (in git; source of truth; not auto-loaded by any engine)
  AGENTS.md                   constitution: student, hard rules, citing, answer style, skill routing
  skills/<name>/SKILL.md      12 skills (+ scripts refs, evals); names in PLAN section 3
scripts/runtime_pack.py   -->  engine home  (agent.engine_home; default per-OS app-data dir, outside any git repo)
  AGENTS.md   CLAUDE.md (= "@AGENTS.md")   .agents/skills/*   .claude/skills/*
```

| decision | why (probe facts, PLAN section 7) |
|---|---|
| materialize into an engine home outside git | `agy` loads AGENTS.md + `.agents/skills` from cwd and the enclosing git root; Claude Code also picks up the git root's `.claude/skills`. Any file at the repo root leaks into the student's agent |
| both skill dirs generated | `agy` reads only `.agents/skills`; Claude Code reads only `.claude/skills` (+ `CLAUDE.md`, `@AGENTS.md` import works) |
| cwd = engine home, `--add-dir` repo and project | skills and the project files stay readable; the pack is not inside the repo |
| repo root: no AGENTS.md/CLAUDE.md/.agents/.claude | developer instructions live in `PLAN.md` only |
| headless `agy` without skip-permissions auto-denies command tools | skills that run scripts need the flag or a read-only design (decide in I2) |
| pack synced before every engine turn (`runtime_pack.sync`, idempotent) and by `scripts/runtime_pack.py sync` | engine home is derived state, never hand-edited |

## 5. Modules (stages I0-I10)

| module | purpose | stage |
|---|---|---|
| `scripts/runtime_pack.py` | pack source and materializer | I0 |
| `scripts/bench/runner.py` | device replay (12 incidents), Q&A eval, behaviour evals | I1 |
| `scripts/skills/lint.py` | frontmatter, triggers, references, pitfalls present per skill | I2 |
| `scripts/altium/ole.py` | OLE compound document parser | I3 |
| `scripts/altium/schdoc.py` | read-only SchDoc reader (components, pins, wires, labels, ports) | I3 |
| `scripts/altium/pcbdoc.py` | read-only PcbDoc reader (components, nets, pads in mm, rules) | I3 |
| `scripts/altium/prjpcb.py` | Altium PrjPcb project file reader | I3 |
| `scripts/altium/rul.py` | Altium .RUL design rules file reader | I3 |
| `scripts/altium/registry.py` | Windows registry lookup for Altium installs and recent projects | I3 |
| `scripts/altium/dump.py` | CLI dump and inspect tool for Altium documents | I3 |
| `scripts/jlc.py` | JLC client: parts search, stock/price/library type, datasheet download, disk cache | I4 |
| `scripts/outjob.py` | OutJob generator (Gerber, NC drill, JLC BOM, CPL, schematic PDF) | I5 |
| `scripts/checks/board.py` | board checks: connector side, decap distance, outline layers, CPL rotation | I5 |
| `scripts/skills/export_cpl.py` | JLC CPL export from linked PcbDoc with BOM fallback | I5 |
| `scripts/dfm.py` | JLC DFM PDF report ingest, slice extractor, and triage table | I5 |
| `scripts/checks/schematic.py` | schematic checks: wire netlist, single-pin nets, unconnected IC power, rail mismatch | I6 |
| `scripts/rules.py` | rules model, .RUL writer, read-back diff against PcbDoc | I7 |
| `scripts/jlc_preset.py` | the JLC preset numbers by layer count, copper weight and mask colour: fab floors, JLCDFM limits | |
| `scripts/calc.py` | IPC-2152 trace width, voltage divider, LED resistor, via current, microstrip impedance | I7 |
| `scripts/library.py` | model search links, package variant check vs datasheet, IntLib build script | I8 |
| `scripts/preview_sch.py` | SchDoc to interactive SVG preview with click-to-ask anchors | I9 |
| `scripts/preview_pcb.py` | PcbDoc to SVG preview with placement plan overlay | I9 |
| `scripts/keeping.py` | folder order, decision log, change impact, final file organization | I10 |


## 6. Data layout

| where | what | in git |
|---|---|---|
| `projects/<name>/` | idea.json, `*-log.jsonl` (append-only truth), derived bom.json, proposals, `netlist/`, `chats/`, `sources/`, `exports/` (BOM, `.RUL`, OutJob, library script), notes.md; plus a link to the student's local Altium folder (read-only) | no (user data) |
| engine home | generated pack (section 4); per-OS app-data dir | no |
| `shared/reference/` | course material + `AGENTS.md` topic index; AD20 Essentials manual is the "how do I" guide | yes |
| `shared/datasheets/` | GENERAL documents only (application notes, design guides, standards): sha256 metadata, re-fetched by URL. A part's datasheet is in `projects/<name>/sources/` | no (metadata JSON only; PDFs ignored) |
| JLC cache | query results with timestamp (path decide in I4: under `shared/` or workspace cache dir) | no |
| `tests/fixtures/altium/` | AD20 SchDoc/PcbDoc/libs/OutJob parser fixtures | yes |
| `config/defaults.json`, `config.json` | defaults in git; user overrides local; env `PCB_ADVISOR_HOME` moves the workspace | defaults only |
| device project (`real-project`) | read-only evidence base for incident fixtures and skill knowledge; never git there | n/a |

## 7. Testing and evals

| layer | tool | what | stage |
|---|---|---|---|
| unit/integration | `.venv\Scripts\python -m pytest -q` (110 green at I0 start) | gateway, store, server, workspace, sources, skills, oscompat; new: readers vs fixtures, JLC client (recorded responses), `.RUL` round trip | all |
| skill lint | `scripts/skills/lint.py` via pytest | every skill has when/steps/scripts/references/pitfalls/output + evals | I2 |
| device replay benchmark | `python pcb.py bench` -> `docs/BENCHMARK.md` | 12 incidents: caught / stage / earlier than reality; deterministic checks run without an engine, engine-based ones marked and run once per stage | I1, every stage |
| Altium Q&A eval | `scripts/bench/qa_eval.py` | ~25 real questions; scores citation (expected file/section) and answer length | I1-I2, I10 |
| behaviour evals | `scripts/bench/behaviour.py` | user's language, short, no stock/price without a skill run, no invented part numbers | I1, I11 |
| engine probe | gateway probe (both engines answer a question needing a skill file) | pack loads in Claude Code and `agy` | I0 |

Targets: I1 baseline recorded (expected low); 12/12 incidents by I11, most earlier than in reality. Orchestrator
verifies every task by running pytest plus the stage's checks (PLAN section 1).
