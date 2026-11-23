# Agent context map - 2026-11-23

מה סוכן הצ'אט מקבל בכל הודעה, מה הוא מקבל רק כמצביע (וקורא לבד כשצריך), ואיפה האיכות נפגעת.
נמדד על `phase0-correctness` ב-commit `5094db2`, פרויקט `UX-E2E-ESP32C3` (עותק בתיקייה זמנית; נתיבים נורמלו לנתיב התקנה טיפוסי).
המדידה: `agent.respond` הורץ עם `gateway.route` מוחלף (בלי מנוע), והפרומפט שנשלח נשמר כמו שהוא.

## 1. Turn pipeline (one student message)

| # | stage | code | what happens |
|---|---|---|---|
| 1 | input | `serve.py` `/api/chat` | text saved to `chats/<id>.jsonl`; `model.build(project, session)`; `ask` = text, prefixed by file content (`[this conversation is about file ...]`, up to 12000 chars), an `about` context (`about_context`) or a part thread context (`model.part_context`) |
| 2 | prompt | `agent.respond` | `rules()` + MEMORY + WORKSPACE + CURRENT STATE + CONVERSATION SO FAR + STUDENT SAYS + `Reply language:` line, joined into ONE string |
| 3 | engine | `gateway.route` -> `claude_code.py` / `antigravity.py` | prompt on stdin (claude: raw text; agy: one stream-json `user` line). `Request.system` and `Request.history` are built but **neither engine sends them**. cwd = engine home; `--add-dir` = repo, project, workspace, linked Altium folder |
| 4 | engine context | engine home (`runtime_pack.sync`) | Claude Code auto-loads `CLAUDE.md` = `@AGENTS.md`; agy loads `AGENTS.md`; skills in `.claude/skills` / `.agents/skills` (descriptions listed, body on demand via the Skill tool) |
| 5 | tools | `config/defaults.json` `tools.allowed` | Read, Grep, Glob, Skill, WebSearch, WebFetch, `Bash(python <repo>/scripts/<x>.py *)` for a fixed list, Edit on notes/BOM.md/sources md. agy: `--dangerously-skip-permissions` (all tools) |
| 6 | parse | `agent._parse` | the ```json block -> `actions` + claimed `tools`; unreadable/cut block -> `parse_refused` |
| 7 | guards | `tool_guard`, `project_guard` | edits to tool files or server-written project data are restored and reported as refused |
| 8 | apply | `serve._apply_actions` + `ext.ACTIONS` | each action validated, consent-checked (draw/place/route/NC/sheet edits), applied or refused; proposals auto-approved per autonomy |
| 9 | reply | `turn_truth.closing_lines`, `msg("not_applied")` | server lines appended under the agent's text in the student's language |
| 10 | follow-up | `start_followup` | text-only correction turn (`FOLLOWUP_WAIT`) or up to 2 retry rounds (`FOLLOWUP_RETRY`, whitelisted kinds, same consent). **Each round re-sends the full prompt** (rules + state + history) |
| 11 | memory | `compact_async` -> `agent.compact` | separate call rewrites `<id>.memory.md` (<= 2000 chars) |

## 2. What is sent every turn (measured)

chars/4 is a rough token estimate (Hebrew and JSON run denser). Calibration: the project's `turns-log.jsonl` records 59k-68k `input_tokens` for a one-engine-turn chat reply (Sonnet); the rest is Claude Code's own system prompt, tool schemas and skill list.

| piece | source (file:function) | when | chars | ~tokens | more on demand |
|---|---|---|---|---|---|
| RULES = runtime/AGENTS.md | `agent.rules()` | always, in the prompt | 29194 | 7300 | - |
| AGENTS.md again, via CLAUDE.md `@AGENTS.md` / agy AGENTS.md | `runtime_pack._desired` | always, loaded by the engine | 29194 | 7300 | - |
| MEMORY | `session.read_memory` via `model["memory"]` | when the memory file is non-empty | 1730 | 430 | `chats/<id>.memory.md` |
| WORKSPACE | `agent._workspace_section` <- `workspace.describe` | engine with tools (claude_code, agy) | 7546 | 1890 | every path listed is readable with Read/Grep |
| CURRENT STATE | `agent._summary` + `ext.SUMMARY` (constraints only) | always | 13487 | 3370 | `python <repo>/scripts/model.py <project>` (full model, ~120 KB incl. chat) |
| - state.idea (goal, goal_status, agreed, confirmed, **diagram again**) | `_summary` | always | 4243 | 1060 | `idea.json`, `idea-draft.json` |
| - state.diagram | `_compact_diagram` | always | 1615 | 400 | - |
| - state.bom (12 lines) | `_summary` + `background.stock_state` | always | 2966 | 740 | `bom.json`, `jlc.py`, `check_availability.py` |
| - state.sources (45 names, 41 of them shared course/JLC/IPC docs) | `model.sources` | always | 2152 | 540 | `sources.py list`, `shared/reference/AGENTS.md` |
| - state.dfm_checks (9 absolute slice paths) | `_summary` | when DFM reports exist | ~1300 | 330 | `checks/<stem>/` |
| - state.totals, sheets, pending_proposals | `_summary` | always | ~380 | 95 | - |
| - state.constraints, board_facts | `constraints._summary` (ext.SUMMARY) | always | ~40 | 10 | `board-facts.json` |
| CONVERSATION SO FAR | `agent.history_lines` (last 8 turns, clipped 600/900, 2 notes) | always | 4170 | 1040 | `chats/<id>.jsonl` |
| STUDENT SAYS + `Reply language:` | `respond`, `reply_language_line` | always | 143+ | 36+ | - |
| file / about / part context | `serve` (`sources.text_of` <=12000, `about_context`, `part_context`) | a file, pointed-at item or part thread | 0-12000 | 0-3000 | - |
| **stdin prompt total** | | | **56270** | **~14000** | |
| skills (12 SKILL.md + 9 references) | `runtime/skills` -> engine home | descriptions always (engine), body on demand | 3952-12017 each, 152 KB total | 1000-3000 each | Skill tool / Read |

### Not sent at all (the model builds it, the agent never sees it)
Only `constraints.py` registers an `ext.SUMMARY`; `stages`, `pin_decisions`, `board_results` are MODEL-only. So the agent does not see:
`stages` (the seven stage states idea, bom, sch, pcb, rules, outputs, checks; the gate reason, the next step), `pin_decisions` (parts whose pins wait for the student),
`sheet_gaps` (open pins), `altium_ok` (what was drawn/placed/routed), `autonomy`, `requirements`, `board` settings.
On the measured project the Outputs stage was blocked by 26 open pins, and the agent had no way to know it without running `model.py`.

## 3. Action catalog: server vs docs

Server kinds (`serve._apply_actions` built-ins + `ALTIUM_ACTIONS` + `ext.ACTIONS`):
`idea.propose, idea.describe, idea.confirm, idea.ready, chat.ask, bom.propose, net.set_current, idea.diagram, idea.diagram.edit,
netlist.write, netlist.remove, netlist.rename, library.add, library.build, part.attach_datasheet, thread.open,
altium.draw_schematic, altium.place_pcb, altium.route_pcb, altium.create_project, altium.add_sheet, altium.skeleton, altium.add_pcb,
altium.open, altium.import_rules, altium.run_outjob, jlc.gerber_zip, order.check, jlc.pickup, dfm.triage` + ext `idea.constrain`.

| kind | AGENTS.md | problem |
|---|---|---|
| `idea.constrain` | named once ("propose them with `idea.constrain`"), no fields | **op / item / kinds (mounting_hole, edge, keep_apart, keepout, attr) documented nowhere in runtime/**; the agent must guess the shape |
| `chat.ask` | ok (`question`, `yes`, `no`) | - |
| `idea.diagram.edit` | ok (`ops`), `reason` documented but ignored by the server | minor |
| `library.build`, `altium.*` (7), `idea.confirm` | backticks only, inside one 3400-char line | correct but hard to find |
| all others | documented with an example | - |
No documented kind is missing on the server. `tests/test_agent_context.py` now checks both directions (AST over `_apply_actions` + ext modules).

## 4. Findings, ranked by impact on output quality

| # | impact | finding | evidence | status |
|---|---|---|---|---|
| 1 | high | **The agent never sees where the project stands**: no stages, gate reasons, unverified pins, open pins. AGENTS.md asks it to "end with the one next action in the student's current stage" and lists a "checklist" in CURRENT STATE that is not there | `_summary`, `ext.SUMMARY` only constraints | **fixed**: compact `stages` + `pins_waiting` in CURRENT STATE |
| 2 | high | **WORKSPACE contradicts the rules**: "sources.py verify ... Run it BEFORE you quote" vs CITING "Do not run `sources.py verify` before answering"; "NEVER state stock or price without running this" vs rule 4 (run only when `missing`/`stale`) | `workspace.describe` scripts | **fixed** |
| 3 | high | `idea.constrain` shape undocumented | section 3 | **fixed** (AGENTS.md action line) |
| 4 | high (tokens) | AGENTS.md reaches the engine twice per turn (~7300 tokens): in the prompt and via `CLAUDE.md`/`AGENTS.md` in the engine home. `agent.py`'s own comment says the prompt copy is for engines without hands | `agent.respond`, `runtime_pack` | **proposal** (P1): needs `pcb.py probe` + evals on both engines, because where the rules sit changes their weight |
| 5 | medium (tokens) | CURRENT STATE waste: diagram twice (idea.diagram + diagram), `agreed` rows carry `ts` and `prev_text`, 41 shared course file names every turn, 9 absolute slice paths, indent JSON | measured above | **fixed** |
| 6 | medium | Stale text: "checklist" in CURRENT STATE; skills table "placement-and-routing-plan ... (the student routes)" though the agent may route on request; `trace_width.py` arguments differ between WORKSPACE and SCRIPTS | AGENTS.md:36, :129; `workspace.describe` | **fixed** |
| 7 | medium | Two script lists with different wording (AGENTS.md SCRIPTS and WORKSPACE Scripts, ~1900 tokens together) | both | **proposal** (P2) |
| 8 | medium | Follow-up and retry rounds re-send the whole prompt; a retry only needs the refusals, the state and the rules | `start_followup` -> `agent.respond` | **proposal** (P3) |
| 9 | low | `Request.system` / `Request.history` are built and never sent by either engine | `claude_code.complete`, `antigravity.complete` | **proposal** (P4): drop or use |
| 10 | low | The on-demand pointer `model.py <project>` prints the whole model incl. the chat (~120 KB) | `model.py` main | **proposal** (P5): a `--state` view |
| 11 | low | AGENTS.md line 101 (draw/place/route consent) is one 3400-char line; hard to read, easy to mis-weight | AGENTS.md | **proposal** (P6): split into sub-bullets; consent text, so not changed here |
| 12 | low | No test tied the server's action kinds to the docs, or the named scripts to the allow-list | tests | **fixed**: `tests/test_agent_context.py` |

Skill-level findings are in section 6.

## 5. Proposals (not done here)
- **P1 rules once**: send `rules()` in the prompt only when `not provider.has_workspace()` (the engine already loads AGENTS.md), keep one line "Your instructions are AGENTS.md (loaded)". Saves ~7300 tokens a turn (~11% of a typical turn's input). Gate: `python pcb.py probe` on claude_code and antigravity, plus the chat evals, before and after.
- **P2 one script list**: WORKSPACE keeps paths only (repo, project, places); the script catalog lives in AGENTS.md SCRIPTS with `<repo>`.
- **P3 short retry prompt**: retry rounds send rules pointer + refusals + CURRENT STATE, not the conversation again.
- **P4** remove `Request.system`/`history` or make the engines use them.
- **P5** `model.py <project> --state` printing the agent summary plus stages, without chat.
- **P6** split AGENTS.md line 101 into one bullet per Altium action, words unchanged.

## 6. Skills review (12 skills, ranked)

Verified against the files before fixing; the rest is listed for a later pass.

| # | skill | finding | status |
|---|---|---|---|
| S1 | manufacturer-and-dfm | step 4 "run the availability script for every BOM line" and a When-to-use line contradict rule 4 (run only when `missing`/`stale`) | **fixed** |
| S2 | manufacturer-and-dfm | step 2 never names `altium.run_outjob`; no pin gate (`pins_waiting`), no `lineage.py status`; bare `scripts/outjob.py` (no `<repo>`, denied from the engine home) | **fixed** |
| S3 | manufacturer-and-dfm, AGENTS.md | `outjob.py <project> [output_dir]`: argparse has `--out`, no positional | **fixed** |
| S4 | rules-and-calcs | step 7 teaches the manual Import Rules dialog; never `altium.import_rules` | **fixed** |
| S5 | placement-and-routing-plan, AGENTS.md skills table | "for the student to carry out by hand" / "(the student routes)" while the agent places and routes on request; a second, different offer wording ("or will you (Update PCB)?") | **fixed** |
| S6 | placement-and-routing-plan | `idea.constrain` named without a shape | **fixed** (example + pointer to AGENTS.md) |
| S7 | schematic-review | "No datasheet: ask the student" vs rule 11 (fetch it yourself) | **fixed** |
| S8 | board-review | step 1 asks the student for board facts before reading `board_facts`/`constraints`; bare `scripts/checks/board.py`; `requirements` cited as if in CURRENT STATE | **fixed** |
| S9 | project-library | "Then Update PCB" after the build, against "never send to Update PCB unasked" and place_pcb's double-parts guard | open |
| S10 | schematic-preview | step 7 writes JSON and opens a rendered image in the same turn; the netlist exists only after `netlist.write` applies | open |
| S11 | placement-and-routing-plan | `preview_pcb.py --plan <plan.json>`: no path or schema for the plan, and the engine cannot write it | open |
| S12 | altium-help | "do not drive Altium, you only explain" while draw/place/route/import_rules/run_outjob exist; Output asks for a plain "Source:" line instead of a `{{src:}}` chip | open |
| S13 | all | duplicates of AGENTS.md (draw/place quote rules in schematic-preview and placement, stage gating in idea-and-requirements, the order-swap paragraph twice, dump.py described 3 times) | open (token cost; consent text is copied, so trim with care) |
| S14 | several | decap distance 2-3 mm (placement) vs 2-5 mm (board-review) vs 5.0 mm default in `checks/board.py` | open |
| S15 | descriptions | overlaps that can load the wrong skill: altium-help (OutJob, rules, libraries) vs manufacturer/rules/project-library; "quote" in manufacturer vs parts-and-stock | open |
| S16 | project-library, project-keeping, part-models | dead "(planned, stage I8)" text, "exists today", `keeping.py log` without its real arguments, design docs (PRODUCT-PLAN, ARCHITECTURE) as agent references | open |

## 7. Before / after (same project, same message, exact prompt)

| piece | before chars | after chars | change |
|---|---|---|---|
| RULES (AGENTS.md) | 29194 | 30149 | +955 (idea.constrain fields, CURRENT STATE keys) |
| WORKSPACE | 7546 | 7803 | +257 (corrected script lines) |
| CURRENT STATE | 13487 | 6708 | **-6779 (-50%)**, now including `stages` (891 chars) |
| stdin prompt total | 56270 | 50703 | **-5567 (~-1400 tokens)** |
| AGENTS.md loaded by the engine | 29194 | 30149 | +955 |
| net per turn (and per follow-up/retry round) | | | about -4600 chars, ~-1150 tokens |

CURRENT STATE after: diagram once; `agreed` rows {topic, text, by, status}; `stages` (7 rows) [{id, state, why (<=240, head and tail), next, blocked, current}];
`pins_waiting` [{line, refs, status unverified|mismatch}] = `store.pins_to_resolve`, what the manufacturing gate waits on; project sources by name + one `reference_library` pointer line; DFM slices as folder + file names; compact JSON.
P1 (rules once) would take another ~7500 tokens a turn.

## 8. Tests
- `tests/test_agent_context.py`: server kinds <-> AGENTS.md / skills parity, `idea.constrain` fields, named scripts exist and are allowed
  for claude_code, CURRENT STATE has stages and no duplicate diagram, stage clip/gate, waiting pins and reference pointer, WORKSPACE no
  longer contradicts CITING / rule 4.
- Ran: runtime pack, skills lint, agent guards/retry, chat experience/follow-up/turns, diagram agent, background, idea description,
  ext shim, constraints, altium settings, wave3 review, docs, evals, memory, pin decisions; `ruff check scripts tests` clean.
  One failure, pre-existing on the unmodified base too: `test_wave3_review.py::test_one_failing_action_is_refused_and_the_turn_goes_on`
  (expects "failed unexpectedly", serve.py says "could not be applied").
