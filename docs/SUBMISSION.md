# pcb-advisor: project summary for the graders

B.Sc. final project. An AI design advisor for printed circuit boards, tied to Altium Designer and the JLCPCB manufacturer.
Every number below can be checked in the code, the tests, `docs/BENCHMARK.md` or `git log`. Where something is not done or not
yet measured, it says so.

## 1. The problem and the goal

A student building a first board loses most of the time on mistakes that a datasheet or the manufacturer's rules would have
caught: a wrong footprint, a part out of stock, a capacitor on the wrong pin, a connector facing the wrong way, a board outline
plotted into every Gerber layer. A general chat model can talk about these, but it also states wrong pin numbers and values with
the same confidence as right ones.

The goal is a tool where the AI helps and the code decides:
- the agent helps refine the idea, pick parts that are in stock at JLC, and explain what it finds;
- every technical fact shown to the student is computed by code, quoted from a checked source, or marked "unverified";
- the same tool can draw the schematic, place the parts and route the board in Altium, and prepares the files for JLC.

The two priorities, in order: technical accuracy with no errors (it is better to do nothing than to act with a chance of being
wrong), and ease of use from install to manufacturing files.

## 2. Architecture

```
 Browser UI (ui/index.html, English)
        | HTTP, localhost
        v
 scripts/serve.py  -- the single writer of project state (store.py, model.py, project.py)
        |
        +--> scripts/altium/  reader of SchDoc / PcbDoc / PrjPcb / .RUL files
        |         |             bridge.py -> Altium scripts (draw, place, route, DRC, outputs)
        |         |             layout.py (placement), route.py (router), pair.py, netcurrent.py, pourcheck.py
        +--> scripts/jlc.py   JLC public API client (stock, price, datasheets), cache, no login
        +--> scripts/gateway/ the one door to the AI engine: claude -p | agy -p
        |         ^
        |         +-- runtime pack (runtime/AGENTS.md + skills) -> skill scripts run BY the engine
        +--> projects/<name>/ the project's files and logs (usage-log.jsonl, chats)
```

- **One writer.** Only the server changes project state. The agent proposes actions; the server executes them and writes the
  result text, so the agent's words cannot claim a success that did not happen.
- **Two engines.** Claude Code (main) and Antigravity (`agy`) are supported through one gateway; see `docs/ENGINES.md`.
- **Altium.** Altium files are read directly (OLE compound files). Drawing, placing, routing, DRC and outputs go through Altium
  scripts started by `scripts/altium/bridge.py`. The student's click on a step button is the consent for that step; every Altium
  step first copies the file to `.advisor-backup`.
- **Local only.** Logs and chats stay on the machine; nothing is sent anywhere.

Fuller description: `docs/ARCHITECTURE.md` (written at the start of the rebuild; where it says the tool never routes, the
README and this file are the current statement).

## 3. Main features by phase

The phases are those of `docs/SPEC-2026-11-11.md`; the running record is `docs/STATUS-2026-11-11.md`.

**Phase 0: correctness fixes (done).**
- Generated footprints: SOT-23-3 pad spacing fixed (1.90 mm, was 0.95 mm), and a test pins the dimensions of every generated package.
- No guessing: a transistor without pin names from a datasheet gets no symbol; BJT versus MOSFET is decided by the pin names.
- One trace-width calculator (IPC-2221, with its validity range and warnings); via current as an annulus, flagged as an estimate.
- Changes that affect the circuit (value, package, MPN, footprint) wait for the student's approval (`classify_proposal`).

**Phase 1: trust in content (done).**
- Pins are checked against the pin table of the datasheet (`scripts/pintable.py`): number and name in one row, pin count versus
  pads, datasheet matched to the MPN. Any doubt gives "not checked", never "passed".
- Quotes turn green only when at least 20 characters match a source word for word.
- Broken action blocks are shown as rejected; one automatic follow-up turn lets the agent correct what it wrote.
- Gerber and drill files are compared with the PcbDoc (holes, diameters, outline, copper layer count); new schematic checks
  (reversed flyback diode, LED without resistor, reversed polarised capacitor).
- "Unverified" shows on the drawn sheet, in the BOM and in the Library tab, and blocks the manufacturing files (OutJob, Gerber zip) until the student verifies or accepts it.

**Phase 2: workflow and convenience (done).**
- Step buttons: Draw in Altium, Place parts, Route board, Import rules, Generate outputs. Each runs its own preparations (library,
  PcbDoc, JLC rules, OutJob), shows a live step list, resumes after a page refresh and has Stop.
- Readiness banner at start, an installer that announces each wait, a server that explains a busy port.
- Non-ASCII net names are transliterated by a fixed per-project table (`net-names.json`).
- U9: one command per tool call, so the engine does not reject compound commands; U11: limits are shown in empty tab states.

**Phase 3: router and placement for a microcontroller board (done, with limits).**
- Track width by current (`netcurrent.py`, IPC-2221, neck-down at fine-pitch pads).
- USB differential pair (`pair.py`): coupled routing, USB-C connector ties, fallbacks that give a reason.
- Placement (`layout.py`): decoupling capacitor within 3 mm of the supply pin, crystal within 5 mm of the MCU pins; a fan-out band
  keeps pin escapes open.
- Pour check (`pourcheck.py`): islands and unjoined pads of the pour net.
- Full DRC list in absolute numbers with a complete/clean gate (`bridge.parse_drc`).
- Explicit refusals (`route.capability_check`): inner layers, BGA, pitch under 0.4 mm, impedance and length rules, board too big.
- Deterministic router budget: the same board gives the same result on every run.

**Phase 4: proof (in progress).** Benchmark re-run on both engines tonight; live runs of the reference boards pending (section 6).

## 4. Quality measures

### Tests
- `pytest --collect-only -q` collects 2241 tests in `tests/` (1866 `def test_` functions, the rest from parametrisation).
- The last full run recorded in the status document, before the phase 3 work: 1792 passed, 15 skipped. A full run of the current
  code is not recorded in this file.
- Phase 3 tests: `tests/test_altium_netcurrent.py`, `test_altium_route.py` (includes the USB pair), `test_altium_layout_decap_xtal.py`,
  `test_altium_pourcheck.py`, `test_altium_pourcheck_holes.py`, `test_altium_route_bridge.py` (capability refusals),
  `test_altium_place.py` (DRC parsing), `test_stm32_board_offline.py`.

### Replay of real incidents (`docs/BENCHMARK.md`)
Twelve real faults from a real design (a ceramic-kiln controller): wrong footprint, parts out of stock, an over-limit capacitor,
a connector facing the board centre, the outline in every Gerber layer, CPL rotations, and others. Each is replayed against the
deterministic checks and against the engine.

Last run recorded in `docs/BENCHMARK.md`: 2026-10-18, commit b51642b, `engine:antigravity`:
- deterministic caught 12/12, engine caught 10/12, earlier than reality 7;
- the two engine misses: incident 7 (the engine answered without the expected point) and incident 12 (timed out after 300 s);
- evals: qa score 0.92 over 25, behaviour score 1.00 over 13.

From the same file's history: on `engine:claude_code`, 2026-10-13 21:57 (bd68c2e), deterministic caught 12/12, engine caught 12/12,
earlier than reality 7. The history also records runs with lower scores, which were kept in the file.

<!-- BENCHMARK-TONIGHT -->
*(Tonight's re-run of both engines goes here.)*

### Offline STM32 board (`tests/test_stm32_board_offline.py`, 9 tests)
A synthetic board of 60 parts, two layers, 50 x 40 mm, placed by `layout.py` and routed by `route.py` with no Altium. The tests
assert what the tool really reports, and where it cannot do something they assert the stated reason instead of loosening the check.
- Placement: 8 of 8 decoupling capacitors within the limit, crystal at 4.96 mm, 0 findings.
- Routing: 43 of 45 nets (96%), 0 violations, about 23 s CPU, deterministic (commit `b84b58d`).
- Budgets in the test are CPU time (15 s placement, 30 s routing), so a busy machine does not fail it.

### The strictness principle: fail closed, no false findings
- Any doubt is reported as "not checked" or "unverified", never as "passed". Examples: a pin table row that lacks the number or the
  name, a datasheet that does not mention the MPN, a DRC report that is truncated.
- A DRC result is "clean" only when the report's own Total line exists and equals the sum of the rules (`bridge.parse_drc`).
- The router refuses what it cannot do before it starts, with the next step, rather than produce a board that looks routed.
- A router result is exact-checked: the offline benchmark has 0 violations; a net that cannot be routed is listed with a reason.
- The agent cannot approve for the student: manufacturing-file blocks and unverified-pin releases need the student's action.
- A rule whose scope cannot be resolved is a "not checked" warning, not a silent pass and not a false refusal.

## 5. Known limits

- GND on the offline STM32 board falls back to tracks because the pour is cut off from several pads, and fails there.
- IO_PA7 has no way out through the congested LQFP fan-out.
- The USB pair is not coupled on that board (clearance 0.085 mm versus the 0.127 mm rule near J1-B6), but both nets are routed and tied.
- A 3x3 BGA is not refused.
- A board with an empty inner layer is not detected.
- Automatic split into several sheets and multi-part symbols are deferred (the draw step refuses with a ready split plan).
- Two copper layers only; USB at 90 ohm differential impedance is not guaranteed in two layers.
- The live Altium run of the STM32 board is not done yet; its numbers are from the offline test only.
- Clean-computer installation (no Python, no Claude) has not been tested end to end.
- Windows is the supported platform for the Altium steps.

## 6. How to run and verify

Install (Windows, PowerShell), or give the line in `INSTALL-AGENT.md` to a coding agent:
```
powershell -NoProfile -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/ilaish5/pcb-advisor/main/install.ps1 | iex"
```
Start: `start.bat` (http://localhost:8931). Check the setup: `.venv\Scripts\python pcb.py doctor` (with Altium open:
`pcb.py doctor --altium`). Engine check: `pcb.py probe`.

Tests (from the repository root, after `pip install -r requirements-dev.txt`):
```
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m pytest -q tests/test_stm32_board_offline.py -s     # prints the offline benchmark numbers
.venv\Scripts\python -m pytest --collect-only -q                          # the test count
```
The offline STM32 test takes about half a minute of CPU; do not run it beside another timing-sensitive job.

Walk-through (about 15 minutes): create a project, describe a small board, approve the BOM cards, press Draw in Altium, Place
parts, Route board, Generate outputs; the README "Try it" section lists the steps.

To read the history: `git log --oneline`, `docs/STATUS-2026-11-11.md` (decisions and closed work), `docs/SPEC-2026-11-11.md`
(phases and acceptance targets), `docs/BENCHMARK.md` (incident replay).
