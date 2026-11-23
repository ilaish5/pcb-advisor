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
`stages` (the six stage states, the gate reason, the next step), `pin_decisions` (parts whose pins wait for the student),
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
No documented kind is missing on the server (checked by grep; a parity test follows).

## 4. Findings, ranked by impact on output quality

| # | impact | finding | evidence | status |
|---|---|---|---|---|
| 1 | high | **The agent never sees where the project stands**: no stages, gate reasons, unverified pins, open pins. AGENTS.md asks it to "end with the one next action in the student's current stage" and lists a "checklist" in CURRENT STATE that is not there | `_summary`, `ext.SUMMARY` only constraints | **to fix**: compact `stages` + `pins_waiting` in CURRENT STATE |
| 2 | high | **WORKSPACE contradicts the rules**: "sources.py verify ... Run it BEFORE you quote" vs CITING "Do not run `sources.py verify` before answering"; "NEVER state stock or price without running this" vs rule 4 (run only when `missing`/`stale`) | `workspace.describe` scripts | **to fix** |
| 3 | high | `idea.constrain` shape undocumented | section 3 | **to fix** (AGENTS.md action line) |
| 4 | high (tokens) | AGENTS.md reaches the engine twice per turn (~7300 tokens): in the prompt and via `CLAUDE.md`/`AGENTS.md` in the engine home. `agent.py`'s own comment says the prompt copy is for engines without hands | `agent.respond`, `runtime_pack` | **proposal** (P1): needs `pcb.py probe` + evals on both engines, because where the rules sit changes their weight |
| 5 | medium (tokens) | CURRENT STATE waste: diagram twice (idea.diagram + diagram), `agreed` rows carry `ts` and `prev_text`, 41 shared course file names every turn, 9 absolute slice paths, indent JSON | measured above | **to fix** |
| 6 | medium | Stale text: "checklist" in CURRENT STATE; skills table "placement-and-routing-plan ... (the student routes)" though the agent may route on request; `trace_width.py` arguments differ between WORKSPACE and SCRIPTS | AGENTS.md:36, :129; `workspace.describe` | **to fix** |
| 7 | medium | Two script lists with different wording (AGENTS.md SCRIPTS and WORKSPACE Scripts, ~1900 tokens together) | both | **proposal** (P2) |
| 8 | medium | Follow-up and retry rounds re-send the whole prompt; a retry only needs the refusals, the state and the rules | `start_followup` -> `agent.respond` | **proposal** (P3) |
| 9 | low | `Request.system` / `Request.history` are built and never sent by either engine | `claude_code.complete`, `antigravity.complete` | **proposal** (P4): drop or use |
| 10 | low | The on-demand pointer `model.py <project>` prints the whole model incl. the chat (~120 KB) | `model.py` main | **proposal** (P5): a `--state` view |
| 11 | low | AGENTS.md line 101 (draw/place/route consent) is one 3400-char line; hard to read, easy to mis-weight | AGENTS.md | **proposal** (P6): split into sub-bullets; consent text, so not changed here |
| 12 | low | No test tied the server's action kinds to the docs, or the named scripts to the allow-list | tests | **to fix**: `tests/test_agent_context.py` |

Skill-level findings are in section 6.

## 5. Proposals (not done here)
- **P1 rules once**: send `rules()` in the prompt only when `not provider.has_workspace()` (the engine already loads AGENTS.md), keep one line "Your instructions are AGENTS.md (loaded)". Saves ~7300 tokens a turn (~11% of a typical turn's input). Gate: `python pcb.py probe` on claude_code and antigravity, plus the chat evals, before and after.
- **P2 one script list**: WORKSPACE keeps paths only (repo, project, places); the script catalog lives in AGENTS.md SCRIPTS with `<repo>`.
- **P3 short retry prompt**: retry rounds send rules pointer + refusals + CURRENT STATE, not the conversation again.
- **P4** remove `Request.system`/`history` or make the engines use them.
- **P5** `model.py <project> --state` printing the agent summary plus stages, without chat.
- **P6** split AGENTS.md line 101 into one bullet per Altium action, words unchanged.

## 6. Skills review
(filled in below after the per-skill review)
