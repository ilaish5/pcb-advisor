# Plan: a smooth agent — nothing blocks the student before they see a result

Branch `feat/smooth-agent-turns` (from main `34ebe5e`). Repo root = this clone. Python `.venv/bin/python`.
This file is the plan AND the progress log (section 5). The orchestrator updates it after every verified task.

Goal, in the owner's words: fewer demands and blocking steps before the student sees a result; the agent never
gets stuck. Out of scope for now: a hot (long-lived) engine session via the Agent SDK — next stage.

## 1. How the work runs
- The orchestrator (Opus) plans, briefs, verifies. Each task goes to a Sonnet subagent with a brief = its section
  below + section 2 + section 3.
- Subagents in the same wave own DISJOINT files (listed per task). A file not on your list is read-only for you.
  If you need a change there, write it under "Requests to the orchestrator" in your report.
- Hard limits for every subagent: no git, no installs (pip/npm/winget), no `pcb.py serve` on port 8931, no browser,
  no edits to `.venv`, no network except a real `claude -p` probe when your brief says so. Scratch files in your
  system temp dir.
- Done = your own tests green AND `.venv/bin/python -m pytest -q -p no:warnings` green. A failure in a file
  you do not own: report it, do not fix it.
- Report (≤ 15 lines): what changed (file list), the contract you implemented (if you diverged from section 3,
  say exactly how), tests added, the full-suite result line, anything you could not do.
- Verification by the orchestrator, per task: read the diff, run the full suite, run the live checks named in
  the task (real `claude` CLI on this Mac, a temp `PCB_ADVISOR_HOME`, a browser pass on a demo server).
- Windows matters: most students run Windows. Every process/file change must say how it behaves there.

## 2. Existing code to know
- Chat turn: `ui/js/chat.js send()` → POST `/api/chat` (`scripts/serve.py`, synchronous, holds the HTTP request)
  → `agent.respond()` (`scripts/agent.py`) → `gateway.route()` → `ClaudeCodeProvider.complete()`
  (`scripts/gateway/claude_code.py`, `subprocess.run`, prompt on stdin, `--output-format json`) → `_parse` →
  `apply_actions()` → `introspect.record()` → `compact_if_due()` → reply.
- `compact_if_due` runs INSIDE the request, before the reply: every `agent.memory_every` (10) messages the student
  waits for one or two extra engine calls (`agent.timeout_seconds` 180 each).
- Antigravity provider (`scripts/gateway/antigravity.py`) already uses stream-json and has `meta["denied"]`.
- Config: `config/defaults.json`; workspace config deep-merges over it (`scripts/workspace.py _merge`, lists
  replace). `ClaudeCodeProvider._tool_problem` rejects unknown keys under `tools`.
- UI conventions: `ui/js/kit.js` (`btn`, `tag`, `metaLine`, `viewHeader`), `core.js api()`; English UI text.
- Tests: fixtures `home`, `lte`, `empty` in `tests/conftest.py`; engine tests fake `subprocess.run`
  (`tests/test_gateway.py`). Faking `subprocess.Popen` will be needed now.

### Measured CLI facts (claude 2.1.304, 2026-10-20)
- `claude -p - --output-format stream-json --verbose` prints one JSON object per line:
  `{"type":"system","subtype":"init"}`, `{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Bash",
  "input":{"command":"...","description":"..."}} | {"type":"text","text":"..."} | {"type":"thinking"}]}}`,
  `{"type":"user","message":{"content":[{"type":"tool_result","content":"...","is_error":true}]}}`,
  `{"type":"system","subtype":"permission_denied","tool_name":"Bash","tool_use_id":"...","decision_reason_type":
  "subcommandResults","message":"This Bash command contains multiple operations. The following part requires
  approval: ls /tmp"}`, `rate_limit_event`, `{"type":"system","subtype":"thinking_tokens"}`, and last
  `{"type":"result", "result":"...", "is_error":bool, "usage", "total_cost_usd", "num_turns", "duration_ms",
  "permission_denials":[{"tool_name","tool_use_id","tool_input":{...}}], "terminal_reason", "stop_reason"}`.
- A denial does not fail the turn: `is_error:false`, the model usually ends with "needs approval".
- Not logged in: exit 1, result `{"is_error":true,"result":"Not logged in · Please run /login",
  "terminal_reason":"api_error"}`. Expired OAuth (seen on the VPS): "OAuth session expired and could not be
  refreshed" / "Failed to authenticate". Usage limit: text contains "usage limit" (often "…|<epoch seconds>").

## 3. Contracts (wave 1 builds against these in parallel)

### 3.1 Engine (gateway) → caller
`Request.options` gains three optional keys; a provider that does not support one ignores it:
- `on_event(ev: dict)` — called from the reader thread for each step. `ev = {"kind": "tool"|"text"|"thinking"|
  "denied", "label": str, "tool": str?, "ts": float}`. `label` is human, short (≤ 80 chars), English, built by
  `gateway.events.label(tool_name, tool_input)`: Bash running `<repo>/scripts/X.py args` → "Running X.py args";
  Read → "Reading <basename>"; Grep/Glob → "Searching for <pattern>"; WebSearch → "Searching the web: <q>";
  WebFetch → "Opening <host>"; Skill → "Opening skill <name>"; Edit/Write → "Editing <basename>"; else the name.
  "text" events are throttled (at most one per 2 s, label "Writing the answer").
- `cancel: threading.Event` — when set, the process TREE is killed within 1 s.
- `idle_timeout: int` seconds — kill when no stdout line arrived for that long. `Request.timeout` stays the total
  ceiling.

`Result` on every path keeps `text` = all assistant text seen so far (partial on stop/timeout) and sets
`meta` keys:
- `error_kind`: one of `not_installed | not_logged_in | usage_limit | stopped | idle_timeout | total_timeout |
  engine_error` (absent when ok). `error` stays a human string. `meta["retry_at"]` (ISO) when a usage-limit reset
  time is parseable.
- `steps`: list of the tool labels run, in order (all, not throttled).
- `denied`: `[{"tool": str, "input": dict, "reason": str, "compound": bool}]` — from the stream event + the
  result's `permission_denials` (merge by tool_use_id). `compound` = `decision_reason_type == "subcommandResults"`.
  Antigravity's existing list is normalised to the same shape (`input` = {} when unknown).
- `partial: true` when the turn did not finish (stop or timeout).
- existing `usage`, `cost_usd`, `turns`, `models` unchanged.

### 3.2 Server → UI
- `POST /api/chat` unchanged in shape. The agent record it appends gains: `steps` (list), `stopped` /
  `timed_out` (bool), `error_kind`, `retry_at`, `denied` (list as above + `"id"` index), `partial` (bool).
  On a partial turn NO actions are applied (a half-written json block is not trusted); the text is kept.
- `GET /api/chat/progress?project=&session=` → `{"running": bool, "seconds": n, "idle_seconds": n,
  "steps": [{"label", "ts"}] (last 12), "current": label|null}`. Cheap: no model build.
- `POST /api/chat/stop` `{}` (project/session from the query as usual) → `{"ok": true}` or 409 when nothing
  runs. The running `/api/chat` request then returns normally with the partial record.
- `POST /api/chat/allow` `{"turn_ts": <agent record ts>, "index": n}` → adds one rule for that denial (built by the
  server from the RECORDED denial, never from client text) to the workspace config key
  `agent.providers.claude_code.tools.allowed_extra` (list, deduped), then 200 `{"rule": "..."}`. Refuses (400)
  compound denials, and any write to `*.jsonl`, `idea.json`, `bom.json`, `netlist/*.json` or the library manifest
  (constitution rule). Rules: Bash → `Bash(<exact command>)`; Read/Edit/Write → `<Tool>(<exact path>)`;
  WebFetch → `WebFetch(domain:<host>)`; other → the tool name.
- Config keys: `agent.idle_timeout_seconds` (default 180), `agent.timeout_seconds` raised to 900 (total ceiling).
  `allowed_extra` is appended to `allowed` by the engine (`_tool_argv`) and is a known `tools` key.

## 4. Tasks

### Wave 1 — the turn itself (parallel: E, S, C)

**E — engine: streaming, stop, idle timeout, denials, error kinds** (list 1: #2 #3 #5 #6 engine side)
Files: `scripts/gateway/claude_code.py`, `scripts/gateway/antigravity.py`, `scripts/gateway/base.py`,
new `scripts/gateway/stream.py` (shared Popen runner), new `scripts/gateway/events.py` (labels + error
classification), `config/defaults.json` (claude_code args → `["-p","-","--output-format","stream-json",
"--verbose"]`, `allowed_extra: []`, the two agent timeout keys), new `tests/test_gateway_stream.py`,
`tests/test_gateway.py` and `tests/test_antigravity.py` (adapt fakes from `run` to `Popen`), `docs/gateway.md`.
- `stream.run(argv, stdin_text, cwd, env, total_timeout, idle_timeout, cancel, on_line) -> (returncode, stderr,
  ended)` with `ended` in `done|stopped|idle_timeout|total_timeout`. Reader threads for stdout and stderr (no
  `select` — Windows). UTF-8 (`oscompat.TEXT`). Write stdin then close it.
- Kill the tree: Windows `taskkill /T /F /PID <pid>` (start with `CREATE_NEW_PROCESS_GROUP`); POSIX start with
  `start_new_session=True` and `os.killpg(pid, SIGTERM)`, SIGKILL after 2 s.
- `_parse` must accept both the old single JSON object and stream-json lines (the result is the last
  `type == "result"` line). Keep plain-text passthrough.
- Error classification from result text + stderr + exit code: map the strings in section 2 "Measured CLI facts";
  `FileNotFoundError` / not on PATH → `not_installed`.
- Live check you may run once: a real `claude -p` with `--model haiku` through `ClaudeCodeProvider.complete`
  with an `on_event` that prints, and one with `cancel` set after 3 s. Report both outputs (shortened).

**S — server: background memory, turn registry, progress, stop, allow** (list 1: #1 #2 #3 #5 #6 server side)
Files: `scripts/serve.py`, `scripts/agent.py`, `scripts/session.py` (only `write_memory` → atomic tmp+replace),
`runtime/AGENTS.md` (one rule, below), new `tests/test_chat_turns.py`, `docs/configuration.md`.
- #1: after the reply is built, `compact_if_due` runs in a daemon thread; one compaction per (project, session)
  at a time (a lock dict); exceptions are printed, never raised. The explicit "rewrite memory now" endpoint stays
  synchronous.
- Turn registry `TURNS[(project, session)] = {"started", "last", "steps", "cancel": Event}` created before
  `agent.respond`, removed in `finally`. `agent.respond` forwards `on_event`, `cancel`, `idle_timeout` into
  `Request.options` and returns `steps`, `denied`, `error_kind`, `retry_at`, `partial` from `res.meta`, and the
  partial text as `reply` on a partial turn.
- Endpoints and record fields exactly as section 3.2. Partial turn → no `apply_actions`.
- AGENTS.md, HOW TO ANSWER: add one line: "A command that is denied: run it again as one plain command (no pipe,
  no &&, no cd); never end your turn on a denial without saying which command and why." Keep
  `python pcb.py skills lint` green.
- Tests: fake `gateway.route` / provider to emit events, block until cancel, return partial; assert progress
  endpoint, stop endpoint (thread + real ThreadingHTTPServer on port 0 like existing server tests), allow
  endpoint (writes config, refuses compound and protected paths), compaction does not delay the reply.

**C — chat UI: progress, Stop, queue, denial and error cards** (list 1: #2 #3 #4 #5 #6 UI side)
Files: `ui/js/chat.js`, the chat stylesheet under `ui/styles/` (find it), new `tests/test_chat_ui.py`
(static checks in the style of `tests/test_checks_ui.py` / `test_parts_ui.py`).
- While pending: poll `GET /api/chat/progress` every 1 s; the working line shows `current` + seconds; a small
  collapsible list shows the last steps. The Send button becomes **Stop** (POST `/api/chat/stop`).
- #4 queue: while pending, Enter/Send adds the text to a client-side queue drawn under the thread as muted
  bubbles "Queued" with × to remove. When the turn ends OK or stopped, the queue is sent as ONE message (texts
  joined by a blank line). When it ends in an error, the queue stays and is not sent.
- A partial record: its text, then a muted line "Stopped after N s · steps: a, b, c" (or "No output for N s —
  stopped"), with **Continue** (sends "Continue from where you stopped. Steps already done: …") and **Retry**.
- Denials: a card per entry in `denied`: "The advisor wanted to run: `<label>`" + reason; non-compound →
  **Allow and retry** (POST `/api/chat/allow`, then resend the last student message); compound → text "It tried
  a combined command; Retry asks it to run them one by one" + **Retry**.
- Error kinds → one friendly card each, replacing the raw "[claude_code] …" line:
  `not_logged_in` "Claude Code is not signed in. Open a terminal, run `claude`, type `/login`, then press Retry.";
  `not_installed` "Claude Code is not installed" + link to the install section of the README + Settings › Engine;
  `usage_limit` "Your Claude plan limit is reached" + "resets at <retry_at local time>" when present +
  "Switch engine" (opens Settings › Engine); `idle_timeout` / `total_timeout` as a partial record.
  Every card keeps Retry. Unknown kinds fall back to today's error line.

### Wave 2 — the idea stage without gates (parallel: I, O)

**I — idea: Accept all, a Confirm button, live draft with Save / Revert, draft-first** (list 2: #1 #2 #3)
Files: `scripts/store.py` (idea + diagram draft), `scripts/serve.py` (idea endpoints and `apply_actions` idea
branches only), `scripts/model.py` (draft in state), `ui/js/views/idea.js`, the diagram editor file(s) only for
draft display, `ui/js/chat.js` (only the confirm button in an agent reply), `runtime/AGENTS.md` (stage 1 text),
`runtime/skills/idea-and-requirements/*`, tests for each.
- **Draft mode.** While the student and the agent work on the idea, every agent change to requirements,
  description and diagram applies LIVE to a draft that is visible at once (no per-item cards). A bar on the Idea
  view: "Draft · N changes since your last save" with **Save** (the draft becomes the idea version, one log
  entry, undo-able) and **Revert** (back to the last saved version). A version history keeps the saved versions
  (at least the last 10) so "back to the previous version" is always one click. Student edits go into the same
  draft. The diagram's existing `idea.diagram.edit` live path joins the draft instead of writing the saved idea.
- **Confirm idea** is enabled whenever there is at least one requirement; pressing it saves the draft and
  confirms. No "accept or dismiss the proposals first".
- **Accept all / Dismiss all** for any proposed items that still exist (back-compat with old projects).
- **Confirm button in the reply** instead of the quote check: the agent emits `{"type": "idea.ready"}` (new
  action) when it believes the idea is agreed; the reply shows a **Confirm idea** button; pressing it calls the
  existing confirm endpoint. `idea.confirm` with a quote keeps working but a failed quote is no longer shown as
  "(Not applied …)": it is downgraded to `idea.ready`.
- **Draft first, then ask** (AGENTS.md THE THREE STAGES #1 + the idea skill): on the first message about a new
  board the agent writes a full first draft at once — description, block diagram, requirements, each assumption
  marked "(assumed)" — and asks at most the 1–3 questions whose answers would change the draft most.
  Update the skill's evals to match; `python pcb.py skills lint` green.

**O — outputs: one-click "Make again"** (list 2: #6)
Files: `ui/js/views/outputs.js`, `ui/js/views/checks.js`, `ui/styles/outputs.css`, `scripts/serve.py` only if no
endpoint exists to regenerate one output kind (then one endpoint `POST /api/outputs/remake {"kind"}`), tests.
- Next to every STALE / EDITED output and in the DFM "Outputs out of date" section: **Make again** that reruns the
  exporter that made it (lineage record `tool` → exporter). An EDITED file asks first ("This file was edited by
  hand; making it again replaces your edits"). Gerber zip whose PcbDoc changed: the button says "Generate the
  outputs in Altium first" with the `altium.run_outjob` action when the bridge is available.
- **Make all again** in the DFM header when more than one is stale.

### Wave 3 — background work and install (parallel: B, D)

**B — checks in the background, never before the answer** (list 2: #5)
Files: new `scripts/background.py` (job queue: one worker thread, dedupe by key, results into the project
state), `scripts/serve.py` (only hook calls: after a chat reply, after a BOM change), `ui/js/markdown.js` (citation
chip states), `runtime/AGENTS.md` (CITING + rule 4/5 wording), the parts-and-stock skill, tests.
- Citations: the agent no longer runs `sources.py verify` before answering. After the reply is stored the server
  verifies every `{{src:file|locator}}` quote in the background; the chip shows ✓ / ⚠ ("quote not found in
  file") / … while checking. Results are stored on the record.
- Stock: a BOM line added or its MPN changed → a background `check_availability` for that line. The agent reads
  stock from CURRENT STATE and runs the script only when the state says the check is missing or older than 24 h.
  Rule 4 stays true (the numbers still come from a script run, with its time).
- Never two jobs for the same key; JLC rate limits respected (reuse what `check_availability` does).

**D — install: one command, or hand the repo to a CLI agent** (list 2: #7)
Files: `install.sh`, `install.bat` (and/or new `install.ps1`), `start.sh`, `start.bat`, `pcb.py` (a `doctor`
command), new `scripts/doctor.py`, `README.md` (install section first), new `INSTALL-AGENT.md` (the prompt a CLI
agent follows), `.github/workflows/*` (an install job on windows + macos runners), the Settings › Engine view
only for a "Run checks" button, tests.
- Step 1 is a decision memo (in this file, section 6) the orchestrator reviews before building: what a student
  needs (git? Python version? Claude Code CLI + sign-in? Altium only on Windows? network for JLC), what can be
  installed for them, what can only be checked, and the three entry points:
  1. one command in a terminal: Windows `powershell -c "irm https://raw.githubusercontent.com/ilaish5/pcb-advisor/main/install.ps1 | iex"`,
     macOS `curl -fsSL …/install.sh | bash` — clone (git; fall back to the ZIP with a warning that Update needs
     git), venv, requirements, `doctor`, start;
  2. open Claude Code / any CLI agent and paste one prompt ("Install pcb-advisor from
     https://github.com/ilaish5/pcb-advisor following INSTALL-AGENT.md");
  3. point the agent at the repo (the README's first lines tell an agent what to do).
- `pcb.py doctor`: each check prints ok / fix (one command or one click): Python version, venv, requirements,
  git + upstream (for Update), `claude` on PATH, `claude` signed in (a cheap probe, no paid turn if avoidable),
  Altium path (Windows), workspace writable, port free. Exit 1 on a blocking failure. The UI's first-run screen
  and Settings › Engine show the same list.
- Idempotent: running the installer again repairs, never duplicates.

## 5. Progress log
| Task | Wave | Agent | Status | Verified by orchestrator |
|---|---|---|---|---|
| E engine streaming/stop/denials/errors | 1 | sonnet E | done | ✓ diff read, live claude |
| S server background memory/progress/stop/allow | 1 | sonnet S | done | ✓ diff read, live claude |
| C chat UI progress/Stop/queue/cards | 1 | sonnet C | done | ✓ browser pass |
| Wave 1 integration (live claude, browser) | 1 | orchestrator | done | ✓ see log |
| Windows hand-off document | end | orchestrator | done, waves 1-3 (`windows-verification.md`) | — |
| I idea draft/Save/Revert/Confirm/draft-first | 2 | sonnet I | done | ✓ diff, live claude, browser |
| O outputs Make again | 2 | sonnet O | done | ✓ diff, browser |
| B background verify + stock | 3 | sonnet B | done | ✓ diff, live claude, browser |
| D install + doctor | 3 | sonnet D | done | ✓ diff, real install.sh runs, browser; install.ps1 unparsed (CI/Windows) |
| Docs (ARCHITECTURE, README) + PR | end | orchestrator | done | ✓ CI on the PR |

Baseline before work: full suite green on main `34ebe5e` (2026-10-20).

### Log
- 2026-10-20 — plan written; branch `feat/smooth-agent-turns` created.
- 2026-10-20 — wave 1 launched: E, S, C in parallel (disjoint files, shared contract section 3).
- C reported: chat.js + chat.css + tests/test_chat_ui.py (8 tests, node --check). Choices: a timeout keeps the
  queue (only Stop/OK flush it); Stop goes through the form submit (an old test forbids `data-act="stop"`);
  denial cards only on the newest record. Asked S to put `seconds` / `idle_seconds` on the record.
  6 server/engine tests red mid-wave (E/S still editing) — re-run after both report.
- E reported: `gateway/stream.py` (Popen runner, reader threads, tree kill), `gateway/events.py` (labels,
  classify), claude_code + antigravity on the runner, 22 tests in `test_gateway_stream.py`. Live (haiku):
  a Read turn emitted "Reading README.md" at 4.6 s; cancel at 3 s → `error_kind: stopped, partial`.
  agy: only a throttled "text" event (its step events are undocumented), no `steps`. Windows kill path untested
  (CI will run the unit tests; a real Windows run is still needed). Orchestrator review of stream/events/
  claude_code diff: OK. Orchestrator did `gateway/__init__.py` (route: idle_timeout default, total 900,
  `not_installed` kind when the engine is missing) and `docs/ENGINES.md` timeout row.
- S reported: TURNS registry, progress/stop/allow endpoints, background compaction (lock per session), atomic
  `write_memory`, record fields + `seconds` / `idle_seconds`. Divergences accepted: a second `/api/chat` for a
  conversation that is already answering → 409 (the UI queues anyway); the AGENTS.md denial rule is appended to
  an existing bullet (AGENTS.md is capped at 150 lines by a test).
- **Wave 1 verification (orchestrator, real claude 2.1.304 + haiku, demo workspace, Chrome):**
  - Full suite green, `skills lint` ok, `node --check chat.js` ok.
  - Progress live: "Running check_availability.py …", "Opening skill schematic-review", "Reading checklist.md".
  - Stop at 8 s → partial record "Stopped after 9 s · steps: …" with Continue/Retry; the engine tree was gone
    a few seconds later.
  - Queue: typed during a run → "Queued" bubble → sent by itself when the turn ended, answered.
  - Denial: "git --version" → card → Allow and retry → rule `Bash(git --version)` in the workspace config → ran.
  - Error cards: `not_logged_in` (CLI with an empty config dir) and `not_installed` (missing binary) both drawn
    with their instructions and Retry.
- **Found and fixed during verification:**
  1. Pre-existing, serious: `AGENTS.md` and 11 skills write `python <repo>/scripts/…`; the allow-list uses the
     machine's command (`python3` on a Mac, `py` on some Windows). The engine copied `python`, so EVERY script
     run was denied on such machines (live: trace_width denied twice, no answer). Fix: `runtime_pack.render()`
     writes this machine's command into the pack and `agent.rules()`; test added. After the fix: answered in 8 s.
  2. The engine started the student's own MCP servers (here desktop-commander) on every turn → added
     `--strict-mcp-config` to the claude_code args (the advisor uses no MCP).
  3. A command refused twice drew two identical cards → `serve.unique_denials()`; test added.
- Seen, not fixed (minor): on page load the thread does not scroll to the very last record.
- Seen, not ours: haiku cited Mouser/DigiKey stock against rule 3 (model quality; default model is not haiku).
- **Wave 2 reports.** I: `idea.json` stays the SAVED idea; `idea-draft.json` `{started, updated, idea}`;
  `idea-versions.json` (newest 20). Endpoints `/api/idea/draft/save|revert`, `/api/idea/version/restore {n}`,
  `/api/idea/items/accept-all|dismiss-all`; `state.idea` = working idea, `state.idea_draft` = `{active, changes,
  since, marks, versions}`. New action `idea.ready`; a failed `idea.confirm` quote downgrades to it. O: no new
  endpoint (existing exporters cover every lineage `tool`); Make again / Make all again with an in-page confirm.
- **Wave 2 verification (orchestrator, real claude + haiku, Chrome):**
  - Draft-first live on two new boards: description + diagram + 5-6 requirements "(assumed)" + 2-3 questions
    in one turn (15-18 s). Save → "Saved · version 2"; Previous version → draft; Revert → back to v2.
  - Agreement turn → `idea.confirm` with a valid quote → the draft was saved first (versions 1/2/3) and confirmed.
  - Confirm-idea button in a reply carrying `idea.ready` → confirmed, stage moves to "Next: BOM".
  - Make again: a hand-edited CPL asks "Replace your edits?" then turns Current; a stale BOM turns Current;
    Make all again in DFM asks once and clears the "Outputs out of date" section.
- **Fixed by the orchestrator in wave 2:**
  1. Deviation from the spec: agent `idea.propose` / `idea.describe` still created "Proposed" items with per-item
     Accept/Dismiss on top of the draft. Now they go straight into the draft (Save is the only gate); the UI tags
     unsaved items "New" / "Changed" (`state.idea_draft.marks`). Old proposed items keep Accept all / Dismiss all.
  2. `store._atomic_write_json` used one shared `.tmp` name (two threads clobber it) and had no Windows retry on
     `os.replace` → per-thread temp name + 10× retry, like `session.write_memory`.
  3. `S.idea_draft` was not in the render key (`core.js`) → the bar could stay stale after Save.
  4. Diagram labels from the model arrived as literal `\n` ("Coin cell\nCR2032") → normalised in
     `apply_diagram_edit`.
  5. Make again was hover-only (like Download) → always visible on a row that needs it.
  6. The DFM header without reports (the common case) had no Make all again → shared `dfmRemakeAll()`.
  7. `workspace.py` file list: `idea.json` described as the last SAVED idea, the draft named.
- Full suite after wave 2: 1196 passed, 14 skipped; skills lint ok; `node --check` on every UI file ok.
- Not testable here (→ Windows brief): the Altium "Generate the outputs in Altium first" path.
- **Wave 3 reports.** B: new `scripts/background.py` (one daemon worker, dedupe by key, `wait_idle`). Citations
  are checked after each reply and stored in `chats/<session>.cites.json` by record ts; `state.chat[i].cites` is
  `{"state":"checking"}` until done, and the 4 s state poll brings the result. Stock: one job per BOM line
  (`stock:<project>:<line>`, 1 s apart), queued after a reply, a chat action, `decide_and_note` and a BOM import;
  `serve.recheck_async` goes through the queue; `agent._summary` tells the agent `stock_check` per row
  (`missing|stale|fresh|checking`, `checked_at`). D: memo in section 6, then `scripts/doctor.py`, `install.sh`
  (rewritten), new `install.ps1`, `install.bat` → `install.ps1`, `INSTALL-AGENT.md`, `SETUP-PROMPT.md` stub,
  README install-first, `GET /api/doctor` (30 s cache), Settings › Engine "Run checks", Run checks link on the
  not_installed / not_logged_in cards, CI `install` job (`.github/workflows/install.yml`, `ci_doctor_expect.py`).
- **Wave 3 verification (orchestrator, real claude + haiku, Chrome):**
  - Live turn quoting a project source: chip ✓ "quote found in file". Seeded record: fabricated quote ⚠ "Quote not
    found", missing PDF ⚠ "not in Sources", real quote ✓. The agent itself refused to cite a PDF that was absent.
  - `install.sh` real runs: ZIP route into a folder with a space and Hebrew (`my pcb תיקייה`) → venv, requirements,
    init, doctor "Ready" with the git and folder-name warnings; second run = repair ("keeping it", same result);
    git-clone route from a local repo (`PCB_REPO`) → `main` tracking `origin/main`; a full run without
    `PCB_NO_START` started the server (HTTP 200 in 5 s, `/api/doctor` answered).
  - Settings › Engine › Run checks lists every check (Altium "skip" on macOS); the cards' Run checks link opens
    Settings and runs them.
- **Fixed by the orchestrator in wave 3:**
  1. B patched `fmt` from `markdown.js` at load time → replaced by real code in `core.js` (`fmt(text, cites)`,
     `citeState`, `chip` draws …/✓/⚠); the renderThread key includes the cites.
  2. No test guarded against the network → autouse `no_network` fixture in `tests/conftest.py` (non-loopback
     `connect` raises).
  3. Pre-existing: a locator with quotation marks (`{{src:f|"…"}}`) rendered as `&quot;…&quot;` and its check never
     attached (the key is the raw text; `inline()` only un-escaped `&amp;`) → `unesc()` before `chip()`.
  4. Agents also write the quote without quotation marks where the place goes → a sentence-length locator is tried
     as a quote; a match upgrades "file found" to "quote found", a miss never marks it wrong.
  5. A chip the server checked as ✓ was still drawn "broken" when the file was not in the client's Sources list →
     the server's verdict wins.
  6. Doctor said "Run the installer again to get a clone", and the in-app Update said "download the new ZIP" —
     neither was true (the repair run kept the ZIP copy, and a new folder strands `projects/`, which live in the
     repo). Now both installers offer to turn a ZIP copy into a clone in place (`git init` + fetch + `reset --hard
     FETCH_HEAD` + upstream; untracked `projects/`, `config.json`, `.venv` untouched; on failure `.git` is removed
     and the ZIP copy stays). Verified: stale tracked edit reset, project and venv kept, `update.check` then saw a
     new upstream commit (`behind 1, can_update`), and the next repair pulled it. `install.ps1` also offers winget
     git on a ZIP copy now.
  7. The folder-name warning named `C:\pcb-advisor` on macOS → `~/pcb-advisor` there.
- Full suite after wave 3: 1244 passed, 15 skipped; skills lint ok; `node --check` on every UI file ok.
- Not testable here (→ Windows brief): every line of `install.ps1` (no PowerShell on this Mac; the CI job is the
  first parse), winget, `irm | iex`, `install.bat`, `claude.exe` in `%USERPROFILE%\.local\bin`.

## 6. Decision memo — install (filled by D, reviewed by the orchestrator)
**Status: built (see the wave 3 log). Orchestrator review, applied: prompts default to [Y/n] and read `/dev/tty`; the installer offers `claude auth login` then starts the server anyway; `oscompat.which/resolve` probes `~/.local/bin/claude` and doctor never writes config (supersedes the table's "sets ... command"); winget `-e --id --scope user --accept-*`; `PCB_REPO`/`PCB_REF` for CI; the non-ASCII path check is a warning; the repo is public. Later change: ZIP → git IS converted in place (see wave 3 fix 6), superseding the last bullet of section 2.** Memo as written by D: Facts used: Python floor 3.10 (install.sh/bat; CI runs 3.11); `claude`'s official installer is a native binary, no Node needed (ENGINES.md: `irm https://claude.ai/install.ps1 | iex`, `curl -fsSL https://claude.ai/install.sh | bash`, lands in `~/.local/bin`, PATH applies to NEW terminals); `claude auth status` measured by the orchestrator (exit 0 signed in / 1 not, 0.22 s, no paid turn; shows only that credentials exist).

### 1. What a student needs
| Item | Req? | Detect | Install for them? |
|---|---|---|---|
| git | optional (needed for Update only) | `shutil.which("git")`, `update.kind()` = git / zip / no-git | Win: `winget install Git.Git` (ask first). Mac: `xcode-select --install` opens a GUI dialog, so only explain. No git = ZIP install, doctor says "ok, updates off" (warn, not blocking) |
| Python >= 3.10 | required | `sys.version_info`; on Windows skip `WindowsApps` stub (reuse `oscompat._is_store_stub`) and run `<py> -c pass` | Win: `winget install Python.Python.3.12` (fallback: python.org link). Mac: `brew install python@3.12` only if brew exists, else link. The Store stub counts as "missing", and the message says "turn off App execution aliases or install from python.org" |
| venv + requirements | required | `.venv` python runs, `pip --version`, `import pypdf, olefile, PIL` | yes, always (installer step; doctor fix = rerun installer) |
| Claude Code CLI | required unless Antigravity is the active engine | `oscompat.resolve("claude")` + `claude --version` (2 s timeout) | yes: official installer (no Node). Do it by default in the installer only after one y/N line (`-Yes` / `PCB_YES=1` skips it). PATH is stale in the same shell, so doctor also probes `~/.local/bin/claude(.exe)` and sets `agent.providers.claude_code.command` to the full path when found there |
| Claude sign-in | required | `claude auth status --json` (exit code + `loggedIn`). Expired OAuth still shows up only at turn time (wave-1 `not_logged_in` card) | NO: `claude auth login` opens a browser. We print/launch it, never automate the login |
| Antigravity `agy` | alternative engine | `pcb.py engines` data | check and explain only (ENGINES.md section 2) |
| Altium | optional, Windows only | `altium.install_path` config or `X2.EXE` found by `bridge._exe()`; skipped (not shown as a problem) on macOS | no |
| Network to JLC | optional (parts/stock only) | HEAD `https://jlcpcb.com` with 3 s timeout; failure = warn "stock checks will not work" | no |
| Free port | required to start | bind-test of `server.port` (8931, `PCB_ADVISOR_PORT`); if taken by our own server, ok ("already running") | no; fix text: `--port N` |
| Writable workspace | required | create+delete a temp file in `workspace.home()` and `projects/` | no (explain: do not install into Program Files / OneDrive-locked folder) |

### 2. Entry points
All three end in the same code: `install.py`-free, the repo's own `install.sh` / `install.ps1` + `pcb.py doctor`.
1. **One command.** Win: `powershell -NoProfile -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/ilaish5/pcb-advisor/main/install.ps1 | iex"`. Mac: `curl -fsSL .../install.sh | bash`. Steps: find/install Python, find git, then clone to `~/pcb-advisor` (Win `%USERPROFILE%\pcb-advisor`; override `PCB_DIR` / `-Dir`), else download the ZIP of main to the same folder and print "Update needs git; install git then run the command again"; venv; requirements; `pcb.py init`; offer Claude CLI; run `pcb.py doctor`; print the one next step, then start the server (`start.sh` / `start.bat`) only when doctor has no blocking failure.
2. **Prompt for any CLI agent** (README + `INSTALL-AGENT.md`): "Install pcb-advisor from https://github.com/ilaish5/pcb-advisor following INSTALL-AGENT.md". The file replaces SETUP-PROMPT.md (kept as a stub that links). It tells the agent: run the one-command installer for this OS, then `doctor --json`, fix each "fix" item with the command given, ask the human ONLY for the browser sign-in and for sudo/admin or the y/N on installing things, never edit tracked files, never print tokens, finish by opening the URL.
3. **Point an agent at the repo**: the first 6 lines of README.md are an `<!-- for AI agents -->`-style plain section "If you are an AI agent: read INSTALL-AGENT.md and do it". Humans see it as one sentence.
- **Twice = repair.** Clone exists and is this repo: `git pull --ff-only` only if the tree is clean (else skip with a note); venv kept when its python works (existing rule), pip install is a no-op; `init` is already idempotent; the CLI install is skipped when `claude` exists. Never delete `projects/` or `config.json`. A different non-empty folder at the target: stop and say so.
- ZIP -> git later: not converted; the doctor line for git says to rerun the installer after installing git (it would clone beside, so we only print the instruction; no automatic migration).

### 3. `pcb.py doctor`
New `scripts/doctor.py`: `run() -> {"checks":[{"id","title","status":"ok|warn|fix|skip","detail","fix":{"command","click":"<ui action>"|null},"blocking":bool}], "ok":bool}`. Text output: one line per check (`ok   Python 3.12`, `fix  Claude Code: not found`, indented `-> irm https://claude.ai/install.ps1 | iex`). Flags `--json`, `--engine ID`. Exit 0 = no blocking `fix`; 1 = a blocking fix (python, venv/requirements, workspace, port, the ACTIVE engine missing or signed out); warns (git, JLC, Altium path unset) never fail. Pure functions with injected `which`/`run`/`socket` so tests fake them. The server gets `GET /api/doctor` (same JSON, engine part cached 30 s; a `?refresh=1` reruns). The UI first-run screen (shown when `claude` is missing or signed out, replacing the current not_installed card text) and Settings › Engine "Run checks" render the same list with `kit.js`, and each `fix.command` gets a copy button. Doctor never installs anything; installers call it, it only reports.

### 4. Risks, and what we will NOT automate
- `irm | iex` and execution policy: `-ExecutionPolicy Bypass` on the pasted command line only (no persistent policy change); it still fails under Constrained Language Mode or AppLocker, so the README also has the 3-step manual path (git clone / ZIP + `install.bat`).
- PATH not refreshed after winget in the same session: after any winget install the installer re-reads PATH from the registry (`[Environment]::GetEnvironmentVariable`) and also probes the known install folders; if still not found it says "open a new terminal and rerun this command" (rerun is safe, see repair).
- Antivirus / SmartScreen can flag a downloaded .ps1; we point to the raw GitHub URL and the repo file so the owner can read it first. Corporate proxy: honours `HTTPS_PROXY`; failure messages name the host that failed. Paths with spaces or Hebrew: quote every path, run venv/pip with explicit quoted paths, `PYTHONUTF8=1`; doctor warns on a non-ASCII home path (known pip/venv trouble) and on OneDrive-synced target folders. Windows ARM64 works with the 3.12 x64/ARM installers.
- NOT automated: Claude sign-in (browser), admin/UAC prompts, Xcode CLT, Altium install, changing Defender/AV, disabling the Store alias, installing Homebrew, anything with sudo, writing the user's PATH by hand (only the official installers do it).

### 5. Files and tests
Touch/create: `install.sh` (idempotent repair + curl-safe: works from a pipe, no `$0` dir assumption), new `install.ps1`, `install.bat` (thin: calls `install.ps1` when PowerShell exists, else old path), `start.sh` / `start.bat` (message: "run doctor"), `pcb.py` (`doctor`), new `scripts/doctor.py`, `scripts/serve.py` (`/api/doctor` only), `ui/js/chat.js` + `ui/js/views/pages.js` (Run checks button, first-run list), `README.md` (install first, agent lines on top), new `INSTALL-AGENT.md`, `SETUP-PROMPT.md` (stub), `.github/workflows/install.yml`, `tests/test_doctor.py`, `tests/test_install_scripts.py` (shellcheck-free: parse `install.ps1` tokens, assert `--yes` flags exist, assert no `rm -rf` outside `.venv`).
CI job `install` on windows-latest and macos-latest: run the REAL installer in a temp dir with `PCB_DIR=$RUNNER_TEMP/pcb` and `PCB_NO_CLAUDE=1` (skip engine install, no network beyond GitHub/pip), `PCB_NO_START=1`; then `pcb.py doctor --json` must report `claude` as `fix` with a command, everything else ok/warn, exit code 1 only because of it; run the installer a second time (repair) and assert identical doctor JSON and an untouched `projects/`; also a "ZIP" variant with git hidden from PATH expects the git check as warn and Update off. Unit tests fake which/run for: store stub, Python 3.9, missing venv, port in use, `loggedIn:false`, expired token not detected (documented limit).

## 7. Windows hand-off (owner's request)
At the end the orchestrator writes `docs/next-tasks/windows-verification.md`: a self-contained brief for a Claude
Code agent running on the owner's Windows PC, covering everything that cannot be checked on the Mac. Items
collected so far:
- Stop kills the whole engine tree (`taskkill /T /F`, `CREATE_NEW_PROCESS_GROUP`): no `claude.exe` / `node` /
  `python` left in Task Manager after Stop, and after an idle timeout.
- Reader threads + UTF-8: a Hebrew prompt and a Hebrew answer come through intact; progress labels appear.
- `runtime_pack.render()`: on a machine where `python_cmd()` is `py`, the engine home's AGENTS.md says
  `py <repo>/...` and a script run is not denied; where it is `python`, the files are unchanged.
- Allow and retry writes a rule that works with the PowerShell twin (`PowerShell(...)`).
- `not_logged_in` / `not_installed` cards with the Windows wording (terminal = PowerShell).
- `start.bat` restart after the in-app Update (exit code 75) — carried over from the previous PR.
- Everything waves 2–3 add (install.ps1 one-liner, doctor, Altium bridge parts of "Make again").
