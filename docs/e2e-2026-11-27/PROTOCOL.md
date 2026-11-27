# Run protocol (read by every role)

Run folder: `docs/e2e-2026-11-27/` (call it RUN). Plan: `RUN/PLAN.md` (Hebrew, the board and stage table are there).
Project under test: `projects/Final-E2E-4L/` created by the student through the UI at http://localhost:8931.

## Board the student builds
STM32F411 USB-C sensor hub, 4 layers (Top / GND / PWR / Bottom), about 70 parts:
STM32F411CEU6 (UFQFPN48), 25 MHz HSE crystal + 32.768 kHz LSE crystal, 3.3 V LDO from USB 5 V, USB-C 2.0 receptacle with ESD protection
and CC 5.1k pull-downs, W25Q128 SPI flash, SPI IMU (e.g. ICM-42688-P or LSM6DSO), BME280 on I2C, microSD socket (SPI),
SWD 2x5 1.27mm header, 2 LEDs, RESET and BOOT0 buttons, decoupling per datasheet.

## Stages and engine (the student switches in the app's Settings at the stage start)
1 Idea+requirements: Claude Code | 2 BOM+stock: Claude Code | 3 Library: Antigravity | 4 Schematic: Antigravity |
5 Placement: Claude Code | 6 Routing+DRC: Antigravity | 7 Outputs: Claude Code | 8 JLC DFM: producer role.

## Files
- Screenshots: `RUN/screens/S<stage>-<NN>-<slug>.jpg` (e.g. `S2-03-stock-check.jpg`). Take them with the Chrome tool
  (`computer` screenshot, `save_to_disk: true`, scale about 0.7); the result names the saved file
  (under `~/.claude/projects/.../tool-results/`), then copy it to that name with `cp`. Take one at every meaningful screen,
  every error, every agent answer. Use `zoom` with `save_to_disk` for small details.
- Student action log: `RUN/roles/student.md`: one line per action: time, stage, what I clicked or wrote, what happened, screenshot name.
- Student confusion log: `RUN/roles/student-confusions.md`, THE MOST VALUABLE OUTPUT OF THE RUN (owner, 27/11: "the system will
  stand or fall on user experience"). Write it the moment something confuses you, looks wrong, makes you hesitate, wait without
  knowing why, or guess what to click; do not save it for the end. One entry each: `C<n> | S<stage> | what I saw | what I expected |
  what I did | screenshot`. Small things count. The designer answers every entry, and the final report lists them all.
- Each reviewer writes `RUN/roles/<role>-S<stage>.md` (lecturer, designer, engineer, alti, producer).
- Orchestrator state: `RUN/RUN-STATE.md`. Disputes and rulings: `RUN/DECISIONS.md`.

## Demo video (owner request)
At the end the orchestrator builds an MP4 demo of the whole run from the screenshots, with the review moments cut in.
- Student: screenshot densely, before AND after every action, while the agent is working (progress states), every answer. Aim for
  15-30 per stage. Names keep strict order (`S<stage>-<NN>`).
- The video is animated (Remotion style): a cursor moves to each click with a click ripple, typed text fills in letter by letter,
  the camera zooms to where the action is. For that the student also writes `RUN/roles/student-actions.jsonl`, one JSON line per action:
  `{"t":"01:23:45","stage":2,"before":"S2-04-x.jpg","after":"S2-05-y.jpg","kind":"click|type|key|scroll|wait","x":812,"y":440,
  "frame_w":1424,"frame_h":715,"text":"what was typed or the key","label":"what the element was"}`. x/y are in the screenshot
  coordinate frame the Chrome tool reported (frame_w/frame_h), exactly as passed to the click. For "type", x/y is the field clicked before typing.
  For a long agent answer add `{"kind":"wait","before":..,"after":..,"secs":65}`.
- Every reviewer report starts with `## Video highlights`: 1-4 lines, each `screenshot-name | one-sentence callout (max 15 words)`,
  the moments a viewer must see (a catch, a mistake, a good result). The lecturer adds the verdict line per round.

## Who judges what (owner, 27/11 02:10)
- Lecturer: the only one who judges the STUDENT's decisions (requirements, part choices, design calls).
- Designer: only what the student SEES in the browser: is the UI/UX good (clarity, flow, text load, feedback, consistency, look).
  Not the board, not the student's choices.
- Engineer: the SYSTEM's work, not the student's choices. Two questions: did the system implement what the student asked, and is what
  it produced or claimed professionally correct? Student asked X, system did Y or did X wrong = finding. Student decided something
  weak = not the engineer's finding (the lecturer covers it), unless the system should have warned and did not.
  The engineer covers the system's side IN THE BROWSER: what the app shows, claims and produces in its pages and chat (requirements,
  BOM, stock/LCSC, datasheet claims, checks, previews, DFM page, exported files listed there) and the project data behind those pages.
- Alti: the same two questions, for what the system created IN ALTIUM (libraries, schematic, PCB, routing, outjob outputs).
  The engineer does not inspect Altium documents; Alti does not judge the web pages.

## Finding format (reviewers)
`- [SEVERITY] title: evidence (screenshot name or file:line or Altium object), why it matters, the generic system cause if visible`
SEVERITY is one of BLOCKER (cannot continue), WRONG (technically or professionally wrong output, the worst kind for this project),
FRICTION (works but slow, confusing, too many clicks or questions, too much text), COSMETIC.
Judge the SYSTEM (pcb-advisor), not the board. A finding is about what the tool did or showed.
Priorities of the project owner: (1) zero technical errors, no hallucinations, rather refuse than be wrong;
(2) effortless use, short chat answers, one-click batchable gates, no needless questions.

## Flow rules
- The orchestrator is the hub: roles report by ending their turn with a short summary; the orchestrator sends the next instruction.
- Lecturer gate: at most two confrontation rounds per stage. After that the orchestrator rules (in `DECISIONS.md`) and the run moves on.
- Alti and the product share ONE Altium instance. Alti works only while the student is parked at a gate, uses the system's own
  scripts read-only where possible (`scripts/altium/bridge.py status`, `scripts/altium/dump.py`, `scripts/preview_sch.py`,
  `scripts/preview_pcb.py`, `pcb.py check|show|outputs`), and exports any PDF or image it needs into `RUN/alti/`, never into the project.
- Code fixes (blocking bugs only): the orchestrator gives the fixer session a brief; the fixer fixes in its own worktree with a test;
  an Opus review passes; the orchestrator merges into `main` here, pushes, restarts `pcb.py serve`; the student reloads the page.
  Non-blocking findings are only recorded.

## Hard rules for everyone
- Nobody edits product code, `config/`, or other projects. Only the orchestrator decides on code fixes.
- Only the student and (stage 8) the producer touch Chrome, never at the same time.
- JLC: upload and read the DFM/quote only. Never add to cart, never order or pay.
- Do not delete anything. Do not change security or account settings.
- Report what you saw, not what you expect. If unsure, say unverified.
