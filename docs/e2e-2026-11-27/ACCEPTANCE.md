# Acceptance metrics for the 27/11 E2E findings

Every failure found in the 27/11/2026 end-to-end run ([REPORT.md](REPORT.md), [FABLE-OPINION.md](FABLE-OPINION.md)) gets a success
metric here. A finding counts as fixed only when its metric passes **under the rules in Part A**, run by someone other than the fixer.
The rules exist for one reason: an agent that fixes a finding must not be able to pass by bending the measurement instead of the system.

Owner: the project owner. This file, `tests/acceptance/` and the thresholds they cite are frozen (A3). A fixer reads them, never edits them.

---

## Part 0. Priority 0: the four invariants (owner, 27/11: "this is the biggest problem"; P0-4 added the same day)

These hold for the whole system, every page, both engines, every Altium step. They are checked on every acceptance run before any
per-finding metric, and a failure here fails the run regardless of the rest. They are system-wide invariants, not per-feature fixes:
a fix that satisfies them for one page or one step only does not pass.

**P0-1. Nothing disappears silently.** No item the student created or decided (requirement, BOM line, note or decision, rule, constraint,
file, Altium object the system placed) may vanish, be skipped, be reverted or be overwritten without a visible record naming that item and
the reason.
- *Metric:* for every agent turn and every action, the oracle diffs the project state and the Altium documents before and after
  (by item id). Every removed, changed, skipped or not-applied item must have a matching visible event: a UI message on the page where the
  item lives + an entry in the project log, both naming the item id and the reason. Unmatched removals/skips = 0.
- *Red on 27/11:* `tool_guard` deleted the student's C18 entry and S1-08 (and called it "the agent edited"); the rule importer skipped the
  PlaneClearance rule while the Rules badge turned clear; a requirement was deleted so the keep-out check would pass; notes.md dropped the
  student's decisions (C135); an Altium project was created after Stop.
- *Anti-gaming:* random canary actions that must be refused or partly applied (an unsupported rule kind, a write the guard reverts, a
  requirement the agent is asked to drop) on random items; the oracle checks the event names that exact item. Logging everything as one
  generic "some items skipped" line does not count: each item needs its own record.

**P0-2. Nothing waits silently.** The student always knows that work is running, what it is doing, roughly how long it takes, and how it ended.
- *Metric:* for every operation that can take more than 3 s (agent turn, library build, schematic draw, placement, route, DRC, outputs,
  JLC/stock calls; both engines): within 2 s a visible running state with the phase name; an update at least every 10 s (phase, elapsed
  time, and step k/n or an expected-time range from measured history); if the backend reports no progress for 60 s, the page says so in
  words instead of spinning; an explicit end message (done / failed with reason / cancelled) that is still there after a page reload and
  after the server restarts. Measured from the server event stream and DOM timestamps over a scripted run of every long operation.
  Pass = 0 gaps over 10 s, 0 operations without an end message.
- *Red on 27/11:* a 20-minute silent library build that ended in a hidden Altium modal; 5-7 minute routes; agent turns with no end message (theme A, 15 confusions).
- *Anti-gaming:* the oracle stalls a random operation on purpose (pauses Altium, blocks the agent's output) and requires the
  "no progress for 60 s" message; a heartbeat that ticks while nothing progresses (a timer only) fails, because the phase/step must come
  from the work itself. An Altium modal dialog must be detected and shown in words.

**P0-3. Nothing is called OK unless it was checked, on this file, completely.** A green tick, "Checked", "done", "updated", "passes",
"no issues", or an agent sentence that says a thing is fixed or fine, is allowed only when a check really ran on the current version of
the artifact and covered every item in its scope.
- *Metric:* every positive status and every success claim in UI or chat carries an evidence record (A10): which check, on which file
  (sha256 equal to the file on disk now), how many items in scope, how many examined, how many failed. Green only if examined = in scope
  and failed = 0. Otherwise the status is "not checked", "partly checked (k of n)" or "stale (file changed since)". The oracle scans every
  agent final message for success claims (frozen phrase list + an LLM judge run by the oracle, not by the product) and requires a linked
  evidence record for each. Unbacked claims = 0; green over unchecked, partial or stale = 0.
- *Red on 27/11:* green "Checked" on pins nobody verified; "The BOM now has 51 parts"; a fixed approval text "updated on the schematic
  label and in the library"; green tick over 421 DRC violations; Outputs silent over 424 DRC; the agent saying the keep-outs have no copper
  and that it cannot change the stack; "Tent vias" in the order note over 157 open vias; a false D1 short and a false U4 conflict.
- *Anti-gaming:* randomized canaries (A5) remove the evidence, make one item in scope unchecked, or change the file after the check
  (stale); each must turn the status away from green within one refresh. Rewording the claim, hiding the tick, or removing the status
  entirely does not pass: the status must still exist and be correct (`not checked` is a required, visible state).

**P0-4. Every failure is readable at a glance, and nothing in it is lost.** (Owner, 27/11: error messages must be clear; a bold
title that says what failed, and a button that expands the full detail.)
- *Scope:* every failure or warning the student can see: page banners, toasts, cards, the end message of a long operation (P0-2), and a
  failed agent turn in the chat. Both engines.
- *Metric, collapsed view (what the student sees first):*
  - a **bold title on one line** (≤ 70 characters at 1366 px) that names in plain words the action that failed and the object it failed on,
    e.g. "Route stopped: +3V3 cannot reach U1 pin 9";
  - at most one plain sentence under it: what this means for the student's work (what was kept or not changed) and the next step;
  - one button for that next step where one exists, and a **"Details" control, collapsed by default**;
  - none of these in the collapsed view: file paths, exception or error-class names, WinError/HRESULT/hex codes, script or file names
    (`.py`, `.pas`, `.js`), internal ids, raw Altium text, numbers with float noise (0.299999 mm). Frozen regex list in `tests/acceptance/`,
    plus the T-E list. Hits = 0;
  - the collapsed view is at most 3 lines of text at 1366 x 768.
- *Metric, expanded view:* the full original text, word for word (the oracle compares it with the server's event or log record), plus the
  step, the time and the file it concerns, with a copy button. Still there after a page reload. Details missing or shortened = 0.
- *Measurement:* the oracle triggers every failure path from a frozen list (at least 12: library build with the IntLib locked, Altium
  closed mid-step, an Altium modal, a width rule that cannot fit a pin, an unsupported rule kind, a URL source that returns 404, JLC and
  LCSC unreachable, the agent engine killed, a bridge timeout, a route that creates shorts, outputs with a missing layer, a guard revert),
  in a random order and on random objects. For each: DOM checks above, plus an oracle-run LLM judge that answers "does the title name the
  action and the object that were made to fail?" from the title alone.
- *Red on 27/11:* `S4-40` the IntLib banner is 5 lines with two full Windows paths and no title or details control; `S6-48` "no tracks
  drawn: could not route +3V3 (pad U1-9 is too close to other copper for a 0.299999 mm track …)" with no title; `S6-17/18` raw Altium text
  and "437"; `S1-12` the fetch error vanished after about 70 s; WinError 1224 never reached the page.
- *Anti-gaming:* a generic title ("Something went wrong", "Error") fails, because the title must name the injected action and object, and
  those are random. Cutting the detail fails, because the expanded view must hold the original text word for word (P0-1: nothing is
  dropped). Removing or auto-hiding the message fails P0-2 (the end message must stay).
- *Findings that are instances:* B1 (d), W1 (guard message), U4, U6, F-H (b), F-LIM, and the raw-text entries in F-C and F-E.

---

## Part A. Rules that make the proof hard to fake

**A1. Measure the artifact, never the claim.** A metric reads what the system produced: PcbDoc/SchDoc streams, Gerber and drill files,
the CSVs, the project JSON, HTTP responses, the rendered page. It never accepts the system's own log line, status flag, banner or chat
sentence as proof. A system message is only ever an input that is checked *against* the artifact.

**A2. Independent oracle.** The checker must not import or call the code being fixed.
- PcbDoc facts: raw `olefile` + a reader under `tests/acceptance/oracle/`, not `scripts/altium/pcbdoc.py` / `ole.py`.
- Gerber/drill facts: an oracle reader under `tests/acceptance/oracle/` (or a third-party parser), not `gerber_check.py`, `outputs_check.py`, `order_check.py`.
- Where Altium itself is the judge (DRC, compile, stack, ERC), the file is saved, closed, reopened from disk and Altium's report is read
  from the file it writes, not from the bridge's summary of it.
- UI facts: the rendered DOM in a real browser on a live server (Playwright or Claude in Chrome), plus the HTTP API response behind it.

**A3. The oracle is frozen and runs from outside the fix branch.**
- `tests/acceptance/` (checkers, synthetic fixtures, thresholds) and this file are frozen by the owner at git tag `acceptance-v1`.
- The acceptance run checks out the oracle **from the tag** (`git worktree add <tmp> acceptance-v1`) and runs it against the fix branch's
  artifacts. The branch's own copy of `tests/acceptance/` is never executed for acceptance.
- Gate: `git diff --name-only acceptance-v1...HEAD -- tests/acceptance docs/e2e-2026-11-27/ACCEPTANCE.md shared/reference` must be
  empty in a fix branch. Non-empty = FAIL, unless the owner approved that exact change in writing (a separate commit by the owner, then a new tag).

**A4. Red before green.** Each metric must FAIL on the frozen 27/11 artifacts before it can be used. A checker that passes on the
known-bad state proves nothing and is rejected.
Frozen evidence: `local/acceptance-fixtures/final-e2e-4l-1127/` (git-ignored; published by the owner's decision on 27/11 as the
GitHub release asset `fixture-final-e2e-4l-1127`, zip sha256 `21c89904…a07477`, fetched by `tests/acceptance/fetch_fixture.py`)
(`project/` = `projects/Final-E2E-4L`, `altium/` = the Altium project folder incl. `.advisor-backup/`), read-only,
`MANIFEST.sha256` of 422 files, manifest sha256 `423530bb3cdefa11906cc7741d9748191ea4e22299dea10c8766801707519e27`.
Key files: `altium/Final-E2E-4L.PcbDoc` `30f07740…fa7664`, `project/bom.json` `50e09ce8…8b53a`, `project/exports/Final-E2E-4L_gerbers.zip`
`0d12c2e1…c1b8a`. Before every acceptance run the manifest is re-verified; a changed fixture = the run is void.

**A5. Randomized canaries.** For every metric of the form "the system must notice X", the oracle injects X at a place chosen at run time
from a fresh random seed (printed in the log, different every run): an unverified pin on a random IC, a random decap moved far from its
pin, a random via left untented, a random BOM quantity changed, a random requirement deleted, a random stored value made stale.
The system must flag exactly the injected item (right object, right reason), and must not flag the untouched copy. A fix that recognises
fixture names, designators or coordinates fails this.

**A6. Hidden boards.** Final acceptance also runs on at least one board the fixer never saw (owner-held, local, not in the repo; a second
4-layer design and one 2-layer design). Metrics are written as rules from standards, so they apply to any board.

**A7. Thresholds come from cited sources and are not tunable.** Every number cites IPC-2221 / IPC-7351 / IPC-2152,
`shared/reference/jlc/pcb-capabilities.en.md`, or the part's datasheet. A fix may not move a threshold, widen a tolerance, add an
exception list, or downgrade a severity. Only the owner changes thresholds, in a separate commit and a new tag.

**A8. No source-grep proof.** A test that asserts a string exists in `ui/js/*.js` or `scripts/*.py` (the `tests/ui_source.py` style) is
not proof of a fix. It may stay as a unit test, but acceptance is behaviour on a running system.

**A9. No special-casing.** CI greps the product code (`scripts/`, `ui/`, `pcb.py`, `config/`) for fixture-only literals used in logic
(`Final-E2E-4L`, fixture refdes or net names inside conditionals, the canary seed variable, the oracle's file names). Any hit = FAIL.
A metric is also re-run with the board renamed and its refdes renumbered; the result must not change.

**A10. Claims carry evidence (the mechanism for root cause R1).** Every success message for a write action (UI banner, chat sentence,
approval text, order note) must carry an evidence record produced by re-reading the artifact after the write: `{path, sha256, fields
read back}`. The oracle recomputes the hash and re-reads the fields; a claim whose evidence does not match the file on disk = FAIL. A
claim with no evidence record = FAIL.

**A11. Tri-state status (the mechanism for root cause R2).** Every check reports `pass | fail | not_checked` plus the number of evidence
items it looked at. Green requires evidence count > 0 and zero open fails. The oracle removes the evidence (deletes the datasheet, skips
the rule, empties the netlist) and asserts the status turns `not_checked`, never green.

**A12. Final proof = the same E2E, rerun.** The 27/11 protocol ([PROTOCOL.md](PROTOCOL.md)), the same board brief and roles, plus one hidden
board. Pass = zero WRONG findings in the fixed classes, no reviewer finds a false claim, and the confusion themes drop by the targets in Part C.

**A13. The fixer does not judge itself.** Acceptance is run by a different session (a different model from the fixer when possible) from the
frozen tag, and its log (seed, fixture manifest hash, oracle tag, per-metric red/green values) is attached to the PR. The fixer's own test
run is not acceptance.

**A14. One metric, one number.** Each metric states the exact measured quantity, the pass condition, and the 27/11 value it starts from.
"Improved", "mostly", "should" are not pass conditions.

**A15. Every frozen corpus has a hidden half.** Each pool or corpus a metric draws from (probe questions, contradiction pairs, pin-table
parts, phrasings, MCU families, synthetic footprints) is split by the owner: the half in `tests/acceptance/` is visible to the fixer, the
other half is owner-held like the hidden boards (A6). Acceptance draws from both. A pass on the visible half with a fail on the hidden
half = FAIL (the fix learned the test, not the rule).

### Order of work
1. Build `tests/acceptance/` (oracle readers, synthetic fixtures, canary injectors, the A3 gate script). Prove every metric RED on the
   frozen 27/11 fixture. The owner reviews and tags `acceptance-v1`. No fix starts before the tag.
2. Fix by root cause (R1-R5 below), not by symptom. Each fix PR lists the metric IDs it claims to turn green.
3. Acceptance run (A13) per PR; full E2E rerun (A12) at the end.

### Root causes (from FABLE-OPINION.md, used to group the metrics)
- **R1** the system reports what it intended, not what it read back.
- **R2** checks fail open: no evidence renders as green.
- **R3** design intent does not survive between stages (decap-to-pin, crystal keep-out, power width, requirements).
- **R4** imported geometry and fab limits are trusted, not normalised (courtyard, paste, origin, tenting, keep-outs, hole clearance).
- **R5** a finding has no lifecycle (open / fixed / accepted with reason), and free chat text is the control surface.

---

## Part B. Metrics per finding

**Before the owner tags `acceptance-v1`:**
- Counts: Part B has 57 entries. That is B1, W1-W37, U1-U8, FRICTION A-J and the unlettered tool-limits table (F-LIM). Nothing was merged. COSMETIC is left out because you did not ask for it. Tagged with P0: 38 (P0-1: 11, P0-2: 4, P0-3: 29); 19 untagged.
- Six thresholds had no source in `shared/reference`. The owner set them on 27/11 (below, "Owner decisions"). All six are now set; sources are
  in `shared/reference` (courtyard, AN2867, CPL).
- "Red" comes in three kinds. **Artifact-red** was read by me from the fixture (olefile, Gerber zip, JSON). **Behaviour-red** needs a scripted replay on the pre-fix commit 2dcd691; B1 replays on dbf3635^. Two values are taken from the role reports until the oracle reader recomputes them from the Gerbers: mask webs (86 per Alti, about 112 per the producer) and pour-to-NPTH (0.161 mm per Alti). The system's own logs (drawn_widths, board-facts, outputs-check) are used only as corroboration (A1).

Conventions:
- **Levels:** U = unit test on a synthetic fixture; L = live Altium (saved, closed, reopened); B = browser DOM + HTTP API; E = A12 E2E rerun.
- **Fixture paths:** `F/` = `local/acceptance-fixtures/final-e2e-4l-1127/`.
- **Pre-fix commit:** 2dcd691.
- **P0 tags:** they refer to Part 0. Each metric adds only what is specific to the finding; the Part 0 metric also applies to it.
- **Retracted or narrowed in REPORT, with no metric here:**
  - Engineer S5/S6 "stack IS JLC04161H";
  - Lecturer S3 r1 "J1 zero ring";
  - Lecturer S4 r1 "inter-sheet connectivity";
  - Engineer S1 C24 (SDIO D0);
  - Designer S1 C14 (data loss);
  - Engineer S3 J1 chat pitch (only the preview caption survives, in W15);
  - Engineer S2 r1 BOM data errors (only the generic causes survive, in W13).

### Owner decisions (27/11, frozen with the tag)
| ID | Threshold | Decision |
|---|---|---|
| OD-1 | Decap to supply pin | Datasheet / app note value per IC; otherwise 3.0 mm, labelled general knowledge |
| OD-2 | Crystal | From ST AN2867 (`shared/reference/appnotes/st-an2867-crystal-layout.en.md`): crystal as close to the MCU as possible (the nearest part to its pins), no foreign net under the crystal and its load caps (outer + adjacent layer, which AN2867 reserves for a local ground plane). General knowledge, labelled so (AN2867 gives no number and no via rule): length ≤ 10 mm, no vias MCU pin to crystal |
| OD-3 | Courtyard excess | IPC-7351B Level B (nominal), 0.25 mm |
| OD-4 | Exposed-pad paste coverage | Part datasheet stencil recommendation; otherwise 50-80 % (IPC-7525 range); 100 % fails |
| OD-5 | CPL reference point and tolerance | Pad bounding-box centre (JLC asks for the geometric centre, not pin 1 or origin; `shared/reference/jlc/cpl-reference-point.en.md`; "pad box" is our reading). Flag at > 0.25 mm between pad centre, origin and body, labelled "our choice, JLC states no tolerance"; a flagged part gets a "check in JLC's placement preview" item |
| OD-6 | Chat message length | ≤ 10 lines per message; longer answers split into several messages; tables and long lists to a page link |

### R1. Reports intent, not read-back

### B1 · Library rebuild hangs and fails silently; residuals (R1) [P0-2, P0-1]
- **Failure (27/11):**
  - The S4 build ran 15-20 min; the Altium modal "Could not create integrated library" was hidden, and the page showed "Building" for 20+ min.
  - altium-log 03:32:01: the restore failed with WinError 1224, and this never reached the DOM.
  - Fixed by dbf3635. Residuals: one new part resets all 31 lines (C77); `libBusy` is client-side only (`ui/js/views/bom.js:151`).
- **Metric:**
  - (a) Part 0 P0-2 applies to `library.build`.
  - (b) Every Altium modal raised during a bridge step is shown in words in the DOM within 15 s (the dbf3635 contract). Undetected modals = 0.
  - (c) A build after k lines changed alters the SchLib/PcbLib component streams of exactly those k lines. The pins/verify status of every other line is unchanged: count = 0.
  - (d) A failed restore produces an item-level DOM message plus a log entry (P0-1).
- **Oracle:** L + B.
  - Lock the installed IntLib with an open handle, and inject a modal.
  - Hash each component's streams with olefile before and after.
  - Read the DOM and the server event stream.
- **Red on 27/11:**
  - (b) on dbf3635^: 20 min silent.
  - (c) on 2dcd691: adding C23 reset 31/31 lines (S4-21).
  - (d) WinError 1224 never appeared in the DOM.
- **Anti-gaming:**
  - The changed line is random; so are the modal (one of 3 texts) and the step it appears at.
  - Defeats matching one hard-coded Altium error string, and "never reset anything" (a changed line must be rebuilt).

### W1 · The tool guard reverts or deletes files the agent did not write, and blames the agent (R1) [P0-1]
- **Failure (27/11):**
  - Chat 01:19:25: "the agent edited system files: …student-confusions.md, …S1-08…". Both files were written by another process, and both were deleted.
  - Code: `scripts/tool_guard.py` ~155-171 (restore/unlink) and ~239 (fixed "the agent edited" text).
- **Metric:**
  - A file written during an agent turn by a process other than the agent's tools is byte-identical after the turn (sha256). Pass = 20/20 trials.
  - A file that the agent's own tool wrote outside its scope is reverted, and the message names that file and the tool call.
  - Files of others reverted or deleted = 0.
- **Oracle:** E.
  - A background writer with its own PID writes during the turn; sha256 before and after.
  - Tool calls are taken from the engine transcript, not the guard's log.
- **Red on 27/11:** behaviour-red on 2dcd691: 2 of 2 foreign files deleted (C18, S1-08).
- **Anti-gaming:**
  - Random repo path, extension and moment within the turn.
  - A canary agent write outside scope must still be reverted.
  - Defeats excluding `docs/e2e-*` and disabling the guard.

### W2 · Goal, description and diagram drift while the agent says "Updated" (R1) [P0-3]
- **Failure (27/11):**
  - `F/project/idea.json` (final) still contains "45 x 35 mm" while board = 60 x 45, and still names "ME6211" while bom.json U5 = LDL1117S33R.
  - idea-versions n=5-7: the goal names ME6211 after the 02:12 swap.
  - The chat said "Updated the draft with all your fixes".
- **Metric:**
  - After every write to the idea or BOM, each entity is checked: board size, layer count, every MPN in bom.json, the bus per device.
  - Wherever the entity appears in the goal, description or diagram, it equals the saved value, or that text is marked "stale" in the API and the DOM.
  - Unmarked mismatches = 0.
  - "Updated" claims carry an A10 record with the text hashes.
- **Oracle:** U (synthetic ideas) + B.
  - Entities are extracted with a frozen regex set: `\d+ ?x ?\d+ mm`, `\d-layer`, the MPN set from bom.json.
- **Red on 27/11:** 2 unmarked stale entities in the final idea.json.
- **Anti-gaming:**
  - A canary changes a random entity (random MPN swap, random size).
  - Deleting the goal or description does not pass: the text must still exist and name the current values.

### W8 · False "The BOM now has 51 parts"; no-op cards approved (R1) [P0-3, P0-1]
- **Failure (27/11):**
  - `F/project/proposals.jsonl`: 8 cards at 01:39:21 (p…921721 to p…921929) with `changes == before`, all approved (6 by "auto", 2 by the student). The count field was dropped.
  - Chat 01:39:22 "51 parts" while bom.json had 28.
- **Metric:**
  - (a) Cards with no effective change, or with a field the server drops, are refused at propose time with an item-level reason. No-op approvals = 0.
  - (b) Every number the agent states about project state (parts, lines, qty) equals bom.json at message time (A10). Mismatches = 0.
- **Oracle:** B.
  - Proposals and bom.json from the API.
  - Numbers extracted from the chat by an oracle-run regex plus an LLM judge.
- **Red on 27/11:** 8 no-op cards approved; claimed 51 vs actual 28.
- **Anti-gaming:**
  - A canary no-op card on a random line, and a random qty canary.
  - A scripted "how many parts now?" requires a number, which defeats silence.

### W9 · A fixed approval text names schematic and library updates that did not happen (R1) [P0-3]
- **Failure (27/11):**
  - `scripts/serve.py:463`. `F/project/chats/2026-11-27-0103.jsonl` has 2 such lines:
    - 02:12:16 U5, when no library existed;
    - 05:24:58 R5, while Main.SchDoc still had PA10 NC.
- **Metric:**
  - Every destination named in an approval (bom.json line, SchDoc label/parameter, SchLib/PcbLib component) holds the new value on read-back (A10).
  - Named but unchanged = 0; changed but unnamed = 0.
- **Oracle:** B + L: bom.json, and olefile reads of SchDoc/SchLib.
- **Red on 27/11:** 2/2 approval texts name at least 1 unchanged destination.
- **Anti-gaming:**
  - Canary approvals run in 3 random project states: no Altium project, project without a library, full.
  - Defeats a generic "updated" text (changed-but-unnamed fails).

### W16 · LED polarity cites a page the agent could not read (R1) [P0-3]
- **Failure (27/11):**
  - Chat 02:30:01 `{{src:KT-0805G.pdf|p. 2}}`, while `read_file` returned None.
  - cites.json says `file_only`, but the chat renders it as a page cite.
- **Metric:**
  - A page cite renders as a source only if the oracle finds its quote on that page of the source text (whitespace-normalised).
  - Otherwise it renders as "file only, not read".
  - Page cites without a matching quote = 0.
- **Oracle:** B: sources/*.txt by page, and the chat DOM.
- **Red on 27/11:** at least 1 (02:30:01).
- **Anti-gaming:**
  - A canary source with a blank (scanned) page N, plus a twin with text.
  - Removing all page numbers fails on the twin.

### W26 · The agent denied what the tool does to the layer stack (R1) [P0-3]
- **Failure (27/11):**
  - S5-07: "None of my Altium actions change layers". S5-27: "the stack is unknown".
  - In fact `place_on()` calls `ensure_stack` (`scripts/altium/bridge.py:1837-1839`), and STACKINFO exists (`:290`).
- **Metric:**
  - For a frozen set of 5 questions (does placing change layers; layer count; per-layer thickness; Er; stack code), the agent's answer equals the oracle's PcbDoc read and the tool's actual action list.
  - Wrong answers = 0/5.
- **Oracle:** B + L: olefile Board6 `V9_STACK_*`.
- **Red on 27/11:** 2/2 wrong (S5-07, S5-27).
- **Anti-gaming:**
  - The canary rewrites one dielectric of a copy to random values before asking.
  - Defeats a canned "JLC04161H" answer.

### W27 · The stack is Altium defaults, not JLC04161H-7628 (R4 cause, listed under R1: the claim) [P0-3]
- **Failure (27/11):**
  - `F/altium/Final-E2E-4L.PcbDoc` Board6:
    - Cu 4 x 1.4 mil;
    - dielectrics 3 x 12.6 mil, Er 4.8;
    - total 43.4 mil = 1.10 mm.
  - `AdvisorBridge.pas:2721-2724`: the StackLayerProps calls are commented out.
  - `ensure_stack` (`bridge.py:1434`) checks the copper count only.
- **Metric:**
  - After the stack step (file reopened), the values equal `pcb-capabilities.en.md` "Impedance control and stack-ups":
    - L1-L2 and L3-L4 prepreg 0.2104 mm, Er 4.4;
    - core 1.065 mm;
    - outer 1 oz, inner 0.5 oz (P16 model values).
  - Tolerance: ±0.001 mm (Altium mil rounding).
  - `ensure_stack` returns fail on any difference.
  - The manifest names the same stack code.
- **Oracle:** L: olefile Board6, and the manifest JSON.
- **Red on 27/11:** prepreg 0.320 vs 0.2104 mm; Er 4.8 vs 4.4; manifest stack field absent.
- **Anti-gaming:**
  - The canary corrupts one random dielectric; `ensure_stack` must fail.
  - A hidden 2-layer board must not receive a 4-layer stack.

### W30 · The silk fix the agent gave cannot work (R1) [P0-3] (disputed: Eng WRONG; Lect downgraded to FRICTION in r2; no ruling)
- **Failure (27/11):** "disable the extra 10 mil SilkToSolderMaskClearance … to clear 157", while that rule had 0 violations and the 6 mil JLC rule had 157 (S6-36).
- **Metric:**
  - Every DRC fix advice names rules whose violation count in Altium's DRC report file is > 0, and quotes that count.
  - Advice blaming a rule that has 0 violations = 0.
  - The predicted after-fix count equals the re-run count.
- **Oracle:** L: parse the DRC report file Altium writes.
- **Red on 27/11:** 1.
- **Anti-gaming:** the canary toggles a random rule to shift the per-rule counts. Defeats fixed advice texts.

### W35 · The order note says "Tent vias" over open vias (R1) [P0-3]
- **Failure (27/11):**
  - `F/project/notes.md:43` "Tent vias (all vias 0.3048 mm hole…)".
  - In the exported zip, GTS and GBS each flash 157 x C 0.028 in (0.711 mm) via openings.
- **Metric:**
  - Every fab statement in the generated order note (tenting, stack code, thickness, finish, layer count) agrees with the files:
    - tented ⇔ via openings in GTS/GBS = 0;
    - stack ⇔ Board6 values (W27).
  - Contradictions = 0. The note carries an A10 record.
- **Oracle:** U + B, with the oracle Gerber reader.
- **Red on 27/11:** 1 contradiction (157 openings).
- **Anti-gaming:**
  - The canary toggles tenting on a copy, and the note must flip.
  - A tenting statement is required, so deleting the line fails.

### W36 · The notes agent dropped recorded decisions (R1) [P0-1] (disputed: Eng says these were never recorded in the app; no ruling)
- **Failure (27/11):**
  - The first notes.md missed 8 recorded risks (VCAP1, +3V3 0.127 mm, crystals, pours near M3, untented vias, J3 edge, tunable caps, RTC).
  - After the 2nd pass the SD-slot and VDDA decap risks were still missing (Lect S7).
- **Metric (surviving, dispute-neutral):**
  - Every item recorded in the project is listed by id in the README/order-note export:
    - open findings;
    - accepted risks;
    - lecturer conditions entered as requirements;
    - DRC open items.
  - Missing = 0. Chat-only statements are out of scope unless ledgered.
- **Oracle:** B: the ledger/requirements API vs the export text.
- **Red on 27/11:** 2 recorded items missing after the 2nd pass; no ledger exists.
- **Anti-gaming:** the canary adds a random ledger item with a random id. Defeats a fixed template.

### F-A · Long waits with no sign of life (R1) [P0-2]
- **Failure (27/11):**
  - Agent answers 30 s-6.5 min with only "Working… N s".
  - Antigravity shows no step list.
  - Routes 5-7 min while the text says "a couple of minutes" (`ui/js/views/previews.js:333`).
  - `libBusy` is client-only.
- **Metric:**
  - Part 0 P0-2 for both engines and every Altium step.
  - Every stated estimate falls within the measured history range (p10-p90 of the last 20 runs, held by the server).
  - The running state survives a reload and a server restart: 10/10 trials.
- **Oracle:** B + E: server event stream, DOM timestamps, a reload mid-operation.
- **Red on 27/11:** 15 theme-A confusions; 20-min build; route "a couple of minutes" vs 5-7 min measured.
- **Anti-gaming:** P0-2 stall canary; random reload time. A bare timer fails.

### F-B · The page, the chat and the numbers disagree (R1) [P0-3]
- **Failure (27/11):**
  - "28 lines / 51 parts" (C36).
  - BOM "Accepted risk" vs DFM "Checked by you" (C84).
  - Layout at 2 layers / 152.4 x 101.6 mm (C99).
  - Rules +3V3 "board rule 0.4 mm" after leaving the scope (C128).
  - Sheet frames "pins not checked" after confirmation (`draw.py:1061-1081`).
  - 38 vs 55 nets.
- **Metric:** Part C T-B consistency metric (N = 20 random fields; DOM = file = agent). Plus every on-page count is the length of a list the page can show.
- **Oracle:** B.
- **Red on 27/11:** at least 6 field disagreements (listed above).
- **Anti-gaming:** see T-B.

### F-D · Agent answers contradict or overreach (R1) [P0-3]
- **Failure (27/11):**
  - The VDDA 10 nF answer reversed itself (C73); the DRC explanation was reversed (C130).
  - "Fine as-is" for BME280 pads 54% long, without a source (C63).
  - "Checked: D1, D2, F1, J3" vs the verify data (C44).
  - Fees $33.77 to $49.12 unmentioned.
  - The "at 5 boards" price used the 10-piece break.
- **Metric:**
  - Every factual claim about project or part state in a final message has an A10/P0-3 evidence link, or it is phrased as unverified.
  - Unbacked claims = 0.
  - Repeat consistency: for 10 scripted questions asked twice with no state change between, the facts in the two answers agree 10/10 (oracle LLM judge).
  - A price is labelled with the qty break actually used (equal to supply-log).
- **Oracle:** B + E.
- **Red on 27/11:** at least 6 instances (listed above).
- **Anti-gaming:**
  - Questions are drawn at random from a frozen pool of 40.
  - A canary changes state between the two asks, and the answer must change.

### F-I · Outputs and ordering (R1)
- **Failure (27/11):**
  - No README/order-note export; deliverables below the fold.
  - Two export paths and two CPLs.
  - Stack not in the manifest.
  - The DFM page is silent that JLC's verdict needs sign-in.
  - C10 and C11 are the same C19666 on two lines.
- **Metric:**
  - (a) The export contains an order note generated per W35.
  - (b) The manifest has a `stack` field equal to Board6 (W27).
  - (c) Exactly 1 CPL is in the upload set, and outputs-check validates that file (sha256).
  - (d) BOM lines sharing an LCSC code with identical value and footprint are merged or flagged: 0 unflagged.
  - (e) The DFM page states the sign-in limit and asks for the report PDF (F-LIM rule).
  - (f) At 1366 x 768, the files table and full path are visible without scrolling.
- **Oracle:** B + Gerber/CSV oracle.
- **Red on 27/11:**
  - (b) absent;
  - (c) 2 CPLs, and outputs-check found "Pick Place for Final-E2E-4L.txt" rather than `exports/_cpl.csv`;
  - (d) C10/C11 = 1 unflagged pair.
- **Anti-gaming:** the canary splits a random line into two identical lines.

### R2. Checks fail open

### W5 · The confirmation state does not reflect the content (R2) [P0-3]
- **Failure (27/11):**
  - `F/project/idea-versions.json` v2-v3: 5 items `confirmed, by: agent` whose text contains "(assumed)" (REPORT says 6).
  - `confirmed_at 01:08:13` is unchanged across 10 later saves (n=4-13).
- **Metric:**
  - (a) An item marked assumed (a field, not text) is confirmed only by a student action on that item id. Violations = 0.
  - (b) A save that changes at least 1 agreed item after `confirmed_at` sets the state to "changed since confirm" (API + DOM) and shows "Confirm again". Violations = 0.
- **Oracle:** B: idea-versions diffs and the DOM.
- **Red on 27/11:** (a) 5; (b) 10.
- **Anti-gaming:**
  - The canary edits a random item.
  - A no-op save must keep "confirmed" (twin), which defeats resetting on every save.
  - The oracle reads the assumed field, so deleting the word "(assumed)" does not pass.

### W10 · An approved card created a duplicate designator (R2)
- **Failure (27/11):** bom-log.jsonl 02:09:03 R4 got its own line while still on line R3 (01:44:07), until 02:14:39 (5.6 min). The header read 53 parts.
- **Metric:**
  - After every BOM write, refs are unique across lines.
  - A duplicating card is refused and both line keys are named.
  - Persisted duplicate states = 0.
- **Oracle:** U + B (bom-log replay).
- **Red on 27/11:** 1 duplicate state.
- **Anti-gaming:** the canary card reuses a random existing ref.

### W12 · The datasheet binding is not refreshed on an MPN change (R2) [P0-3]
- **Failure (27/11):**
  - bom-log U5 01:44:07: mpn → ME6211C33M5G-N while the datasheet stayed AMS1117-3.3.pdf until 02:00:55.
  - 02:02:24: mpn → ME6211A33PG-N, datasheet ME6211C33M5G-N.pdf until 02:10:48.
  - The 01:39 budget used the AMS1117 Iq.
- **Metric:**
  - In the same write that changes mpn/lcsc, the datasheet is rebound to a file whose text names the new MPN (oracle search, ordering code normalised), or it is unbound with pins/verify = not_checked.
  - Derived numbers (Iq, Pd) computed afterwards cite the new file.
  - Stale bindings shown as checked = 0.
- **Oracle:** U + B; sources/*.txt.
- **Red on 27/11:** 2 stale windows (16.8 min and 8.4 min).
- **Anti-gaming:** the canary swaps a random line's MPN within its family.

### W14 · Green "Pins: nothing to verify" on unchecked parts (R2) [P0-3]
- **Failure (27/11):**
  - `ui/js/views/pages.js:70-78` falls through to `['ok','Pins: nothing to verify']` when `pins_status` is empty.
  - `F/project/bom.json`: 19/31 lines have an empty status, including F1, Y1 and Y2 (datasheets bound) and SW1 (4 pins).
  - U1 issue text "names 6 of its 49" is wrong (S7 Eng).
  - At S3: 30/30 empty.
- **Metric:**
  - The server status is one of verified | mismatch | accepted | not_checked | not_applicable.
  - not_applicable applies only to unpolarised 2-terminal passives.
  - verified needs evidence: {datasheet sha256, page, pins compared = symbol pin count}.
  - Lines with polarity or more than 2 pins whose status is not verified or accepted = 0.
  - Any "names k of n" equals the oracle's k.
- **Oracle:** U (oracle pin-table parser on a frozen corpus) + B.
- **Red on 27/11:** 4 lines (F1, Y1, Y2, SW1) would be green.
- **Anti-gaming:**
  - The canary deletes a random IC's evidence or datasheet, and it must turn not_checked.
  - The verified twin must stay green, which defeats making everything amber.

### W20 · A false U4 "Pins conflict" (R2) [P0-3]
- **Failure (27/11):**
  - bom.json U4 `verify = mismatch`.
  - On the -IQ ordering code, IO3 is correct (W25Q128JVSIQ.pdf.txt 891-895).
  - The first name of a multi-function cell is taken, and ordering-code notes are ignored.
- **Metric:**
  - On a frozen corpus of 10 parts with multi-function cells and ordering-code notes: false conflicts = 0.
  - Injected true renames are found 10/10.
- **Oracle:** U with an oracle-labelled corpus.
- **Red on 27/11:** 1 false conflict.
- **Anti-gaming:** a random pin is renamed in a random part, with an untouched twin. Suppressing all conflicts fails.

### W21 · A false "D1 pins 2 and 5 are one terminal" (R2) [P0-3]
- **Failure (27/11):**
  - `scripts/altium/draw.py:172-176` reads the polyline through the zener as a wire (C7519 `lib.kicad_sym:163-165`).
  - It was raised on every draw (altium-log 03:59:26).
- **Metric:**
  - "Pins joined" is reported only when Altium's compile of a test sheet connects them (report file read).
  - False joins on a corpus with diode, TVS and zener graphics = 0.
  - True joins (pins stacked at one location) are found 100%.
- **Oracle:** L (compile), U.
- **Red on 27/11:** 1 false join per draw.
- **Anti-gaming:** random graphics, plus a true-join twin. Defeats ignoring all polylines.

### W22 · "Review this sheet: 0 errors" without a stated scope (R2) [P0-3]
- **Failure (27/11):**
  - S4-13 missed:
    - the LSM6DSO I2C/I3C on shared SPI (LSM6DSOTR.pdf.txt:625, 1663);
    - VDDA 10 nF.
  - Three "0 errors" results had different scopes, one of them with tools `[]`.
  - `scripts/checks/schematic.py` checks connectivity and power names only.
- **Metric:**
  - Every check result carries the Part 0 P0-3 record.
  - A model-only review cannot render "0 errors".
  - On synthetic schematics, 5 frozen required rule classes are injected at random: datasheet decap missing, I3C-capable device on a shared bus without disable, open-drain bus without pull-up, EP not on GND, crystal without load caps.
  - Detected 5/5; clean twin 0.
- **Oracle:** U.
- **Red on 27/11:** 2 missed; 3/3 results without scope.
- **Anti-gaming:** random injection site and part. Marking the required classes "not checked" fails, because they are required.

### W23 · The decoupling check gives a false pass (R2) [P0-3]
- **Failure (27/11):**
  - `scripts/checks/board.py:249-294` measures each cap to the nearest supplied pad of any part, so J2 (microSD) is never flagged. Nearest cap 10.9 mm (Eng/Alti).
  - "C10 is the only cap over the limit" came 16 s after a table showing C19 at 28.5 mm.
- **Metric:**
  - For each supply pin of every IC and card connector, the oracle takes the nearest same-net cap.
  - The flagged set must equal the oracle set {pin: distance > D_decap}. Set difference = 0.
  - Agent statements equal that set.
  - D_decap (owner 27/11): the IC's datasheet or application note value where it gives one (cited by page); otherwise 3.0 mm, labelled "general knowledge, no course source". The product's 5.0 mm is not used.
- **Oracle:** U + L (olefile pads).
- **Red on 27/11:** at least 2 pins unflagged (J2 supply; U1 VDDA per W24 figures).
- **Anti-gaming:** a random decap is moved far away (A5), and a random connector gets a supply pin.

### W33 · Outputs pass with 424 DRC open, and nothing says so (R2) [P0-3]
- **Failure (27/11):**
  - `F/project/exports/Final-E2E-4L_order_manifest.json` warning names only U1.
  - board-facts drc_total 424.
  - `scripts/store.py:4024-4087` route_block checks only unrouted nets.
- **Metric:**
  - The Outputs page and the manifest show DRC counts by class (JLC-reject / JLC-accept / cosmetic, per F-H) for the current PcbDoc sha256.
  - Generating outputs with a JLC-reject item open requires a per-run "make anyway" that records the open item ids.
  - Outputs with open items not mentioned = 0.
- **Oracle:** B + L (DRC report file).
- **Red on 27/11:** 0 of 424 mentioned.
- **Anti-gaming:** the canary adds one random violation to a copy, and the count and its class must change.

### W37 · Pre-order checks are blind to mask webs and copper-to-NPTH (R2) [P0-3]
- **Failure (27/11):**
  - `gerber_check.py`, `outputs_check.py` and `order_check.py` read no mask flashes.
  - The DRC summary says "Board Clearance Gap=0mil" vs a 12 mil rule.
- **Metric:**
  - Synthetic Gerber sets are injected with 4 defects:
    - mask web < 0.10 mm;
    - copper < 0.2 mm from an NPTH wall;
    - copper < 0.2 mm from the routed edge (thresholds: pcb-capabilities "Solder mask", "Traces and spacing", "Outline");
    - DRC summary rule value ≠ the Rules6 value.
  - Reported with location 4/4; clean twin 0.
- **Oracle:** U (the oracle builds the Gerbers).
- **Red on 27/11:** 0/4.
- **Anti-gaming:** random defect positions and sizes.

### U1 · "Pins: nothing to verify" shown green (R2) [P0-3]
- **Failure (27/11):** S3-10 (DOM side of W14).
- **Metric:** in the DOM, the pins chip has the ok class only where the W14 server status is verified, accepted or not_applicable. Violations = 0.
- **Oracle:** B on the fixture BOM.
- **Red on 27/11:** 4.
- **Anti-gaming:** the W14 canary. The chip must exist (hiding it fails).

### U2 · The placement banner says "checked against the netlist" over failing warnings (R2) [P0-3]
- **Failure (27/11):** S5-12 shows 8 warnings under "checked" (`previews.js:330-340`).
- **Metric:**
  - The banner tone equals the worst open placement finding.
  - The wording states its scope (netlist equality) next to the count of open findings.
  - Green with open warnings = 0.
- **Oracle:** B.
- **Red on 27/11:** 1 (8 open).
- **Anti-gaming:** the canary moves a random part off the outline.

### U3 · Check board shows 421 violations under a green tick (R2) [P0-3]
- **Failure (27/11):** `previews.js:587` takes the tone from warnings, not from `drcSummary` (:357).
- **Metric:** green only if JLC-reject = 0 and unclassified = 0 (F-H classes). Violations = 0.
- **Oracle:** B + L.
- **Red on 27/11:** 421 under green.
- **Anti-gaming:** a random single violation must turn the tone.

### U6 · A skipped rule is reported as success (R2) [P0-1, P0-3]
- **Failure (27/11):** S6-43 "1 added, 0 updated, 2 skipped" as a toast, and the Rules badge cleared.
- **Metric:**
  - Each skipped rule shows on its own row with its reason and stays there after a reload.
  - The page status is not clear while any skip exists.
  - Unmarked skips = 0.
- **Oracle:** B vs Rules6 (W32a).
- **Red on 27/11:** 2 unmarked.
- **Anti-gaming:** a random unsupported rule kind is submitted.

### U7 · No readiness summary; the Outputs nav dot is green with risks open (R2) [P0-3]
- **Failure (27/11):** S7-02/03 (`ui/js/shell.js:101-104`, `ui/js/views/outputs.js`).
- **Metric:**
  - The dot is green only when open = 0 across DRC JLC-reject, unverified parts and open conditions.
  - A "Before you order" card lists each count with links.
- **Oracle:** B.
- **Red on 27/11:** green with 424 DRC lines and U1 open.
- **Anti-gaming:** a random open item is injected.

### F-F · Previews cannot be judged (R2)
- **Failure (27/11):**
  - Unreadable schematic and U1 symbol, no zoom.
  - No paste or mask layers.
  - Labels sit away from their parts.
  - 16 vs 18 pads unexplained.
  - The datasheet viewer list shifts under the click.
  - Confirm-pins opens a blank p.190 (C80).
- **Metric:** Part C T-G (DOM geometry vs oracle). Additionally:
  - Confirm-pins opens the page whose text contains the part's pin table (oracle page search). Wrong page = 0.
  - Symbol pin count vs pad count differences are explained per pad (NPTH pegs listed).
- **Oracle:** B.
- **Red on 27/11:** C80 wrong page; J1 16 vs 18 and J2 13 vs 15 unexplained.
- **Anti-gaming:** a random part is chosen.

### R3. Design intent does not survive between stages

### W3 · Contradictory requirements are accepted without warning (R3)
- **Failure (27/11):** idea-versions n=3 has "USB-C only … no battery" with "LSE runs the RTC for the timestamps", and Confirm succeeded at 01:08:13.
- **Metric:**
  - A needs-vs-provisions cross-check runs before Confirm.
  - On 10 frozen contradiction pairs (paraphrased), each conflict is shown naming both item ids: 10/10. False conflicts on the consistent twins = 0.
- **Oracle:** U + B.
- **Red on 27/11:** 0/1 flagged.
- **Anti-gaming:** random pair, wording and item order. Defeats keyword matching.

### W4 · An unsourced claim survived the MCU change (R3) [P0-3]
- **Failure (27/11):** "USB DFU via BOOT0" was cited only to the AN2606 L4 tables (01:04:46), was still confirmed after the F411 swap (n=3-4), and has no cite in cites.json.
- **Metric:**
  - When a part an item depends on changes, every item whose cite does not mention the new part (oracle text search) becomes "unverified" with a reason, in the same write.
  - Stale confirmed items = 0.
- **Oracle:** U + B.
- **Red on 27/11:** 1.
- **Anti-gaming:**
  - The canary swaps the MPN of a random cited item.
  - An untouched twin must stay confirmed, which defeats "unverify everything".

### W6 · The DFU pin plan omits BOOT1/PB2 (R3)
- **Failure (27/11):** pin table 01:25:16 (S1-15): PB2 is neither assigned nor tied, while F411 Table 8 requires BOOT1 = 0.
- **Metric:**
  - The pin plan, and later the netlist, assign or tie at a stated level every boot/strap pin that the MCU datasheet's boot table lists for the chosen boot mode.
  - Missing = 0.
- **Oracle:** U on 3 MCU families (datasheet excerpts in the oracle fixtures) + the netlist JSON.
- **Red on 27/11:** 1 (PB2).
- **Anti-gaming:** the hidden board uses another MCU family, and one strap is randomly removed from a correct plan. Defeats hard-coding PB2.

### W7 · The first BOM has Qty 1 on every multi-part role (R3)
- **Failure (27/11):** S2-08: 28 lines / 28 refs vs about 70 expected; warned, but "Approve all" applied it.
- **Metric:**
  - A card whose role or reason implies N > 1 parts ("x2", "per LED" with k LEDs, ref ranges) but carries refs ≠ N is refused at propose time, not merely warned.
  - After the schematic, lines whose refs count ≠ the netlist count for that role = 0.
- **Oracle:** U + B.
- **Red on 27/11:** first approved BOM 28 refs vs 55 final (bom-log replay).
- **Anti-gaming:** random phrasing forms and counts.

### W13 · Parts are selected without datasheet-mandated checks (R3)
- **Failure (27/11):**
  - LSE gm_crit 2.16 µA/V vs F411 Table 38 max 1.50.
  - HSE 1.11 mA/V vs 1 mA/V.
  - No VDDA 1 µF (F411 Fig. 43).
  - ME6211 0.29 W vs Pd 0.30 W.
  - All fixed only after reviewers asked.
- **Metric:** the following run automatically on every card:
  - crystal gm_crit (from ESR, C0 and CL in the crystal datasheet) ≤ the MCU datasheet gm_crit_max;
  - regulator Tj = Tamb_max (from the requirements; if none, not_checked) + Pd·θJA ≤ Tj_max from its datasheet;
  - every supply pin in the MCU decoupling figure has the datasheet values.
  - A failing part is refused or flagged with the numbers. Missed on canaries = 0.
- **Oracle:** U (synthetic crystals, LDOs and MCU figure tables).
- **Red on 27/11:** r1 bom-log state: crystals 2 misses, VDDA 1 miss. LDO: to measure, because Tamb is not in idea.json, which gives not_checked rather than pass.
- **Anti-gaming:** a hidden-board MCU and crystal; a random high-ESR crystal swap.

### W24 · The placer is not pin-aware for decaps and crystals (R3) [P0-1] [LIMIT stated]
- **Failure (27/11):**
  - C10 is 15.7 mm from U1 pin 22 (routed 17.4 mm, 2 vias).
  - C22 is 20.9 mm away; C19 is 28.4 mm from J2-4; Y1 is 7.3 / 8.1 mm from pins 5/6.
  - The 2nd placement was worse and replaced the 1st silently.
  - Code: `layout.py:1773` `decap_hints`, `:1683` `_DECAP_IC`.
- **Metric:**
  - Typed constraint records (cap→pin, crystal→pins) are written at the BOM/schematic stage.
  - After placement, each record has distance ≤ D_decap / D_xtal (owner decisions OD-1, OD-2), or an open item with the measured number (R5, refused explicitly).
  - Unmet and unflagged = 0.
  - A re-placement that increases a constrained distance names that record (P0-1).
- **Oracle:** L (olefile) + U.
- **Red on 27/11:** 4 records unflagged (C10, C22, C19, Y1). The 2nd-run regressions (C13, C19, C22) were not announced.
- **Anti-gaming:** hidden board; random cap. Defeats moving only C10.

### W28 · Entering a current narrows power tracks (R3) (dispute carried: FABLE says 0.127 mm meets IPC-2221; the surviving defect is non-monotonicity)
- **Failure (27/11):**
  - Planned 0.254 mm. After 0.3 / 0.5 / 0.5 A were entered, +3V3, +5V and VBUS were drawn at 0.127 mm (signals 0.2032).
  - Final +3V3 0.127 mm.
  - Code: `scripts/altium/netcurrent.py:99` `w = max(need, wmin)`; `POWER_WIDTH = 0.3` (`route.py:41`).
- **Metric:**
  - For every net, the minimum drawn width (oracle from Tracks6 per net) ≥ max(IPC-2221 width for the entered current, rise and oz; the width the net gets with no current entered).
  - Nets narrower after a current is entered = 0.
- **Oracle:** L + U.
- **Red on 27/11:** 1 net (+3V3) on the final PcbDoc (3 at route 2; corroborated by altium-log drawn_widths).
- **Anti-gaming:** random rail net and current (0.1-1 A). Defeats hard-coding 0.4 mm for +5V.

### W31 · The router ignores crystal layout rules (R3) [LIMIT stated when asked]
- **Failure (27/11):**
  - Route 3: SDIO_CMD, IMU_CS, BOOT1 and SDIO_D0 run under Y1; SWDIO, SWCLK and SWO under Y2.
  - HSE_IN is 13.1 mm with 3 vias.
  - There is no crystal handling in `route.py` or `negotiate.py`.
- **Metric:**
  - Tracks and vias of other nets (excluding the crystal's own nets and GND) that intersect the crystal courtyard on the outer layer and the adjacent inner layer = 0.
  - Vias between the MCU pin and the crystal pad on crystal nets = 0.
  - Crystal rules (owner 27/11, OD-2; AN2867 for nearness and keep-out, general knowledge for the number and the via rule): the crystal is the nearest part to its MCU pins; track length MCU pin to crystal pad ≤ 10 mm (labelled general knowledge); no vias on that path.
  - Otherwise the route is refused with the numbers (R5).
- **Oracle:** L (olefile geometry).
- **Red on 27/11:** 7 foreign nets; 3 vias on HSE_IN.
- **Anti-gaming:** hidden board; a canary track through a random crystal on a copy.

### F-J · Data and library plumbing (R3) [P0-1]
- **Failure (27/11):**
  - Building one part re-flags 31 lines (C77).
  - The WinError 1224 restore failure was silent.
  - `lcsc` is empty while `code` is set on 8 lines (U5, Y1, Y2, R3, C15, C17, C22, R4 in bom.json).
  - NC is a magic net name; decaps are not bound to pins.
  - The citation checker flags course manuals "not in Sources" (`background.py:154-157`).
  - The U2 verify message claims exposed pads it does not have.
- **Metric:**
  - (a) Partial rebuild and restore failures per B1 (c) and (d).
  - (b) One LCSC field per line: lines where lcsc ≠ code = 0.
  - (c) NC is a pin attribute in the netlist; a net literally named "NC" on a hidden board stays a real net.
  - (d) Files in `shared/reference` cited in chat resolve to an openable source. Unresolvable = 0.
  - (e) Every verify message's factual claims (EP present, pin count) equal the oracle's PcbLib read.
- **Oracle:** U + B + L.
- **Red on 27/11:** (b) 8; (d) C67 instances; (e) 1 (U2).
- **Anti-gaming:** a random line's code is cleared; a hidden board has a net named "NC".

### R4. Imported geometry and fab limits are trusted, not normalised

### W15 · The footprint preview reports a wrong pad pitch (R4)
- **Failure (27/11):**
  - J1 "pitch 0.65 mm" while the signal pads are at 0.50; Y1 shows 1.778 vs 1.76.
  - `scripts/model_preview.py:239-248` `_pitch` uses the median nearest-neighbour distance.
- **Metric:**
  - The displayed pitch equals the oracle's centre spacing of the largest row of equal, equally spaced pads, ±0.01 mm (display rounding).
  - Every distinct pitch is shown.
  - Mismatches over all footprints = 0.
- **Oracle:** U + B (olefile PcbLib from `F/altium/Library`).
- **Red on 27/11:** 2 (J1, Y1).
- **Anti-gaming:** synthetic footprints with random pitch (0.4-2.54) and distractor pads (shield tabs, EP).

### W17 · The library has no real courtyard (R4)
- **Failure (27/11):**
  - Mech 15 holds the EasyEDA body outline, which lies inside the pads on 20/20 footprints (Alti S3).
  - `partlib_convert.py:20` copies it; `model_preview.py:26` labels it "courtyard".
- **Metric:**
  - Every built footprint has a closed courtyard enclosing all pad copper and the 3D body outline plus the IPC-7351B Level B excess (0.25 mm, owner 27/11; `shared/reference/standards/ipc-7351b-courtyard.en.md`).
  - Failing footprints = 0.
- **Oracle:** U + L (olefile PcbLib).
- **Red on 27/11:** 20/20.
- **Anti-gaming:** synthetic sources with the body larger than the pads. Defeats "pad bbox + 0.25" alone.

### W18 · J1/J2 3D bodies and origin are offset; reported as cosmetic (R4) (the 1.42 / 2.32 mm origin figure is the agent's own claim, UNVERIFIED: no metric on it)
- **Failure (27/11):** manifest warnings say "3D offset" J1 2.2, J2 2.8 and J3 1.0 mm, shown only as "Built, check".
- **Metric:**
  - For each footprint, the system reports the origin-to-pad-centre and body-to-pad-centre offsets equal to the oracle's within 0.05 mm (measurement resolution).
  - Any offset that moves the CPL point (W34) is classed as a production finding in DFM, not as 3D. Misclassified = 0.
- **Oracle:** U + L.
- **Red on 27/11:** 2 misclassified (J1, J2); the origin offsets are to measure by the oracle (the claim is not trusted).
- **Anti-gaming:** synthetic STEP/footprint pairs with random offsets.

### W19 · The U1 exposed pad gets a full paste opening, and it reaches the stencil Gerber (R4) [LIMIT stated]
- **Failure (27/11):** GTP has D38 R 0.2165 x 0.2165 in (5.50 mm), flashed once over the 5.5 mm EP; PasteMaskExpansion 0.
- **Metric:**
  - For each exposed or thermal pad, paste coverage (paste area / pad area in GTP/GBP) lies within the part datasheet's stencil recommendation, or else 50-80 % (IPC-7525 range, owner 27/11, labelled general knowledge).
  - 100% coverage = fail.
- **Oracle:** U + Gerber oracle.
- **Red on 27/11:** 1 pad at 100% (30.25 / 30.25 mm²).
- **Anti-gaming:** a hidden-board QFN/DFN of another size. Defeats one hard-coded window.

### W25 · The corner keep-outs are Top copper; the requirement was deleted to pass (R4) [P0-3, P0-1]
- **Failure (27/11):**
  - Backup `F/altium/.advisor-backup/20261127-061631/*.PcbDoc` Regions6 has 4 regions `V7_LAYER=TOP|KIND=0`.
  - board-facts said ko_* "met, no copper inside".
  - Requirements ko_bl / ko_br / ko_tl / ko_tr are present in idea-versions n=11-12 and gone in n=13 (06:29:55).
  - Code: `partlib_generate.py:425-430`; `AdvisorBridge.pas` `LayerOf` ~797; `requirements.py:98`.
- **Metric:**
  - (a) Each keep-out requirement yields keep-out objects (keep-out layer, or the keep-out flag set) with 0 copper of any net inside on all copper layers.
  - (b) Agent-originated deletion of a requirement whose check is failing = 0 (only an explicit student request names it).
  - (c) The requirement check counts component-owned copper.
- **Oracle:** L (olefile) + B (idea-versions diff).
- **Red on 27/11:** (a) 4 copper regions; (b) 4 requirements deleted.
- **Anti-gaming:**
  - The canary places random copper in a random keep-out, and asks the agent to "make the route pass".
  - Defeats deleting the requirement and excluding the rule.

### W29 · Untented vias next to pads on HASL; slivers blamed on the footprints (R4) [P0-3] [LIMIT stated]
- **Failure (27/11):**
  - GTS/GBS: 157 via openings each (C 0.711 mm), `ISTENTINGTOP=FALSE`.
  - Alti DRC route 3: 86 dams < 0.10 mm, and 10 bare vias < 0.2 mm from a different-net pad (producer: about 112).
  - The fixed explanation said "fine pitch of the footprint".
- **Metric (from the Gerbers):**
  - (a) Mask webs < 0.10 mm (pcb-capabilities "Solder mask", 1 oz green) = 0, or each is listed as JLC-reject.
  - (b) With untented vias on HASL, bare via copper is ≥ 0.2 mm from other exposed copper (Via covering table, P5).
  - (c) Each sliver explanation names the object pair (pad-via, via-via, pad-pad) the oracle finds. Misattributed = 0.
- **Oracle:** U + Gerber oracle.
- **Red on 27/11:** (a) to recompute by the oracle (86 per Alti); (b) 10; (c) 137 of 252 misattributed (Eng route 2).
- **Anti-gaming:**
  - The canary moves a random via next to a pad on a copy.
  - Raising the sliver rule or excluding it from DRC does not help, because the Gerbers are measured.

### W32 · The hole-clearance rule was skipped silently; pours end 0.16 mm from the M3 holes (R4) [P0-1, P0-3] (severity dissent: Lect WRONG vs Eng COSMETIC on the reassurance; no ruling. The metric covers the skip and the geometry, which are undisputed.)
- **Failure (27/11):**
  - `F/project/rules.json` has M3_Holes_Plane_Gap (PlaneClearance 19.685 mil), but Rules6 in the PcbDoc has no rule of that name.
  - The toast said "2 skipped" with no reason.
  - G1/G2 pours are 0.161 mm from the NPTH walls (Alti S6).
- **Metric:**
  - (a) Every rule in rules.json is in Rules6 (name, kind, values), or its own row shows it skipped (P0-1).
  - (b) In the Gerbers, copper on any layer, pours included, is ≥ 0.2 mm from an NPTH wall (pcb-capabilities "NPTH to track 0.2 mm"; inner via/PTH hole to copper 0.2 / 0.3 mm). Violations = 0.
  - (c) The Extra rules form kinds are a subset of the kinds the importer can write.
- **Oracle:** L + U + Gerber oracle.
- **Red on 27/11:** (a) 1 missing; (b) to recompute (0.161 per Alti); (c) 2 extra kinds (PlaneClearance, Differential pair).
- **Anti-gaming:** a random unsupported kind; a random hole on a hidden board.

### W34 · The CPL centroid rule is unstated and wrong for asymmetric parts (R4) [P0-3] (dispute settled by the owner's OD-5: pad bounding-box centre, after the JLC source check)
- **Failure (27/11):**
  - `F/project/exports/Final-E2E-4L_cpl.csv`: U5 43.345 vs 44.000 (origin, body and Altium Pick Place); J1 30.84 vs origin 30.99; J2 75.56 vs 75.315 (Altium 75.46).
  - outputs-check validated "Pick Place for Final-E2E-4L.txt", not the uploaded `_cpl.csv`.
- **Metric:**
  - (a) The CPL holds the pad bounding-box centre of every part (OD-5; JLC: geometric centre, not pin 1 or origin, `jlc/cpl-reference-point.en.md`), and the manifest states that rule. Parts whose CPL point ≠ oracle pad-box centre ± 0.01 mm = 0.
  - (b) Every part whose pad centre, origin and body centre differ by more than T_cpl = 0.25 mm (OD-5) is flagged. Unflagged = 0.
  - (c) outputs-check validates the uploaded CPL by sha256.
- **Oracle:** U + B + olefile.
- **Red on 27/11:** (a) not stated; (b) 3 (U5, J1, J2); (c) the wrong file.
- **Anti-gaming:** synthetic parts with random asymmetric pad sets.

### F-H · Rules, route and DRC presentation (R4)
- **Failure (27/11):**
  - "2 below JLC minimum" were Altium defaults.
  - An infeasible width rule failed the route after about 5 min at U1-9.
  - 421 lines shown as paragraphs with no class.
  - J3 pads 0.30 mm from the edge vs assembly "> 0.3 mm" were unreported.
  - No USB pair.
- **Metric:**
  - (a) DRC lines are classed JLC-reject / JLC-accept / cosmetic against pcb-capabilities values; the class counts equal the oracle classifier.
  - (b) A width rule infeasible at any pin is reported before routing, naming the pin. Detection time < 10 s (owner UX).
  - (c) Copper to a routed edge is < 0.2 mm, or a component is ≤ 0.3 mm from the edge (assembly-capabilities A4 #14): flagged.
  - (d) Each Rules badge equals the number of listed items.
- **Oracle:** L + B.
- **Red on 27/11:** (a) unclassified 421; (b) 1 late failure; (c) J3 0.30 mm unflagged.
- **Anti-gaming:** a random infeasible width; a random edge part.

### R5. No finding lifecycle; chat as the control surface

### W11 · A review chip started a build and an Altium project; Stop did not stop the plan (R5) [P0-1]
- **Failure (27/11):**
  - The chip said "28 open … how do I fix it".
  - Filesystem: a new project was created at 01:50:11 and a skeleton at 01:50:19, after Stop.
  - The chat said only "(Not applied: library.build …)".
- **Metric:**
  - (a) Side-effecting actions started from review or read-only chips = 0 (they produce proposals only).
  - (b) Side effects executed after Stop in that turn = 0.
  - (c) The turn's end message lists every side effect, item by item.
- **Oracle:** B + L. A filesystem watcher on the Altium folder (new .PrjPcb/.SchDoc), plus Altium's open-document list read by a read-only script.
- **Red on 27/11:** 2 side effects after Stop.
- **Anti-gaming:**
  - Stop at a random point in a random multi-step plan.
  - Chips must still answer (at least 1 read-only answer), which defeats removing them.

### U4 · A rejected route is a dead end (R5) [P0-2]
- **Failure (27/11):** S6-17/18 show raw Altium text and "437"; "board put back" is hidden under details (`previews.js:588`).
- **Metric:** the end message
  - names the cause in words as object pairs (count = oracle DRC);
  - says "restored from backup", with the backup sha256 equal to the current PcbDoc;
  - offers at least 1 action.
- **Oracle:** B + L.
- **Red on 27/11:** 0 of 3 elements.
- **Anti-gaming:** a random short is injected so the route is rejected.

### U5 · No way to accept or waive a finding the fab allows (R5)
- **Failure (27/11):** C121 (421 never clears). The manifest `accepted_risks` has `reason: ""` on 6/6.
- **Metric:**
  - Every finding class has "Accept with reason". A non-empty reason is required.
  - An accepted item leaves the blocking count and appears in the manifest with its reason.
  - Accepted with an empty reason = 0.
- **Oracle:** B + manifest JSON.
- **Red on 27/11:** 0 accept controls on DRC; 6 empty reasons.
- **Anti-gaming:**
  - A random JLC-reject item cannot be accepted silently: it needs the reason plus "make anyway" (W33).
  - A file change after acceptance (stale) re-opens it.

### U8 · Outputs shows the Layout chips and an old answer under the wrong engine footer (R5)
- **Failure (27/11):** "What is wrong in the layout (424 open)" on Outputs; an Antigravity answer under a "Claude Code" footer (`ui/js/chat.js:588`, `:608-617`).
- **Metric:**
  - Chips act only on the current page's objects.
  - Each message's engine label equals the engine recorded for that turn in turns-log.
  - Mismatches = 0.
- **Oracle:** B.
- **Red on 27/11:** 1 + 1.
- **Anti-gaming:** a random page and engine switch between turns.

### F-C · Fixes leave the app as Altium hand steps with no tracked state (R5)
- **Failure (27/11):**
  - Every DRC fix, the 3D offsets, the D1 SchLib edit, ERC and decap moves were hand steps.
  - "Unknown, inspect in Altium" was shown while board-log had the details.
  - The EP thermal-vias advice contradicts "via-in-pad never" (`route.py:1866`, `jlc_preset.py:225`).
  - Dead D1/D2 rows and the "Check datasheets" control.
- **Metric:**
  - (a) Every hand-step advice creates a ledger item (open → student fixed → re-checked on the file → closed, or accepted). Advice without an item = 0.
  - (b) "Done, check again" re-runs the check on the current sha256.
  - (c) "Unknown" is shown only where the oracle finds no detail.
  - (d) Advice that violates the system's own rules = 0.
  - (e) Controls with no effect (click → no DOM or API change) = 0.
- **Oracle:** B + E.
- **Red on 27/11:** (a) all of them; (c) 2 groups; (d) 1; (e) 3 controls.
- **Anti-gaming:** a random finding is fixed by hand on a copy, and only the re-check may close it.

### F-E · Chat format and consent (R5)
- **Failure (27/11):**
  - 40-line answers and wide tables.
  - Internal leaks ("bom.propose", "student_said", "chat.ask", raw ids, `.py` names).
  - "yes, replace the placement…" was refused after the agent had already announced the replacement (C105).
- **Metric:** see Part C T-E. Additionally:
  - Affirmative replies with extra text are accepted 20/20 (frozen phrasing set).
  - An action announced as done before consent = 0.
- **Oracle:** B.
- **Red on 27/11:** 1 refused yes; 1 pre-announced replacement.
- **Anti-gaming:** phrasings are drawn at random; negations ("yes, but don't") must not count as consent.

### F-G · Start-up and navigation (R5)
- **Failure (27/11):**
  - The app opens on an old project; "New project" is at the bottom of about 30 projects.
  - A new project silently defaults to 2 layers.
  - The "not linked" banner is unexplained.
  - Chips that cannot run yet are shown.
- **Metric:** Part C T-H.
- **Oracle:** B.
- **Red on 27/11:** C1, C4, C6, C29, C68.
- **Anti-gaming:** see T-H.

### F-LIM · Tool limits, said or unsaid (R5) [P0-1, P0-2]
- **Failure (27/11):** 15 limits in REPORT's table:
  - 3 silent: URL fetch vanishes after about 70 s (`pages.js:544`); PlaneClearance; JLC DFM sign-in.
  - 1 false claim: "cannot change layers" (W26).
  - The rest were stated only when asked.
- **Metric:** for each of the 15 (frozen list), a scripted attempt yields either:
  - the artifact change, verified by the oracle; or
  - an explicit refusal at the control in the DOM plus an open ledger item.
  - Silent = 0. False limit claims = 0.
  - A limit stated only in chat and not at the control = fail.
- **Oracle:** B + L + E.
- **Red on 27/11:** 3 silent, 1 false, 11 chat-only.
- **Anti-gaming:** the order of limits and the trigger wording are random. Removing a control so that nothing is refused fails: the list is frozen and each item needs a result.

### Coverage table

| ID | R | P0 | Level | Canary |
|---|---|---|---|---|
| B1 | R1 | 2,1 | L,B | yes |
| W1 | R1 | 1 | E | yes |
| W2 | R1 | 3 | U,B | yes |
| W3 | R3 | - | U,B | yes |
| W4 | R3 | 3 | U,B | yes |
| W5 | R2 | 3 | B | yes |
| W6 | R3 | - | U | yes |
| W7 | R3 | - | U,B | yes |
| W8 | R1 | 3,1 | B | yes |
| W9 | R1 | 3 | B,L | yes |
| W10 | R2 | - | U,B | yes |
| W11 | R5 | 1 | B,L | yes |
| W12 | R2 | 3 | U,B | yes |
| W13 | R3 | - | U | yes |
| W14 | R2 | 3 | U,B | yes |
| W15 | R4 | - | U,B | yes |
| W16 | R1 | 3 | B | yes |
| W17 | R4 | - | U,L | yes |
| W18 | R4 | - | U,L | yes |
| W19 | R4 | - | U | yes |
| W20 | R2 | 3 | U | yes |
| W21 | R2 | 3 | L,U | yes |
| W22 | R2 | 3 | U | yes |
| W23 | R2 | 3 | U,L | yes |
| W24 | R3 | 1 | L,U | yes |
| W25 | R4 | 3,1 | L,B | yes |
| W26 | R1 | 3 | B,L | yes |
| W27 | R1 | 3 | L | yes |
| W28 | R3 | - | L,U | yes |
| W29 | R4 | 3 | U | yes |
| W30 | R1 | 3 | L | yes |
| W31 | R3 | - | L | yes |
| W32 | R4 | 1,3 | L,U | yes |
| W33 | R2 | 3 | B,L | yes |
| W34 | R4 | 3 | U,B | yes |
| W35 | R1 | 3 | U,B | yes |
| W36 | R1 | 1 | B | yes |
| W37 | R2 | 3 | U | yes |
| U1 | R2 | 3 | B | yes |
| U2 | R2 | 3 | B | yes |
| U3 | R2 | 3 | B,L | yes |
| U4 | R5 | 2 | B,L | yes |
| U5 | R5 | - | B | yes |
| U6 | R2 | 1,3 | B | yes |
| U7 | R2 | 3 | B | yes |
| U8 | R5 | - | B | yes |
| F-A | R1 | 2 | B,E | yes |
| F-B | R1 | 3 | B | yes |
| F-C | R5 | - | B,E | yes |
| F-D | R1 | 3 | B,E | yes |
| F-E | R5 | - | B | yes |
| F-F | R2 | - | B | yes |
| F-G | R5 | - | B | no |
| F-H | R4 | - | L,B | yes |
| F-I | R1 | - | B | yes |
| F-J | R3 | 1 | U,B,L | yes |
| F-LIM | R5 | 1,2 | B,L,E | yes |

**Count:**
- REPORT has 57 findings (B1 + W1-W37 + U1-U8 + FRICTION A-J + the tool-limits table); this table has 57 entries. Nothing was merged.
- The W/U overlaps (W14/U1, W32/U6, W33/U7, W29/F-H) are kept separate: W measures the data and the server, U measures the DOM.
- COSMETIC is not catalogued (not requested).
- Root causes: R1 15, R2 16, R3 9, R4 9, R5 8.
- P0 counts (a finding can carry several tags, and is counted once per class):
  - P0-1: 11 (B1, W1, W8, W11, W24, W25, W32, W36, U6, F-J, F-LIM);
  - P0-2: 4 (B1, U4, F-A, F-LIM);
  - P0-3: 29;
  - tagged at least once: 38; untagged: 19.

---

## Part C. UX metrics (student confusion themes)

**Rules for every theme:**
- **What is counted:** confusion entries in the A12 rerun, classified into themes by an oracle-run judge using the frozen designer rubric (`designer-SUMMARY.md` theme definitions), not by the fixer or the product.
- **Fixed opportunities (quietness guard):** the student role prompt, the board brief and a frozen set of 30 probe questions are taken from the `acceptance-v1` tag. The student must ask every probe question (about 4 per stage). A rerun with fewer than 30 probes asked is void.
- **Rate:** counts are also reported per hour of run time.
- **27/11 baseline:** 138 entries; K (32, not UI) is excluded.

### T-A · Silent or long waits (27/11: 15)
- **Behaviour:** Part 0 P0-2 for every operation of both engines and every Altium step, plus F-A's estimate rule.
- **Measurement:** server event stream plus DOM timestamps over a scripted run of every long operation, plus a reload and a server restart mid-run.
- **Target:** 0 T-A confusions; 0 gaps > 10 s; 0 operations without an end message.
- **Anti-gaming:** the P0-2 stall canary. A timer-only heartbeat fails. "You can leave this page" text without a server-held state fails the reload test.

### T-B · Page, chat and numbers disagree (27/11: 19)
- **Behaviour (consistency):**
  - Each run, 20 fields are drawn at random (seeded) from a frozen list of 40: BOM line count, part total, qty per line, unverified-part count, accepted-risk count, layer count, board size, per-net width wanted, per-net width drawn, DRC total, DRC per class, Rules badge, requirement status per id, confirmation state, engine per message, stack code, net count, outputs readiness counts, and others.
  - For each field: DOM value = artifact value (project JSON, PcbDoc via olefile, Gerber oracle) = the value the agent states when asked a scripted question.
  - After any write, unsaved fields are marked stale in the DOM within one refresh.
- **Target:** 20/20 equal in each of 3 checkpoints (after BOM, after route, after outputs); at most 3 T-B confusions.
- **Anti-gaming:** the canary changes a random field in the file, and the DOM must update or say stale. Hiding a field fails: all 40 fields are required to be present.

### T-C · Green or "done" over unverified, failed or ungated state (27/11: 6)
- **Behaviour:** Part 0 P0-3 over all statuses, plus W14, U1-U3, U6, U7.
- **Target:** 0 T-C confusions; green over not_checked, partial or stale = 0 across a DOM scan of all pages at each checkpoint.
- **Anti-gaming:** the P0-3 evidence-removal and staleness canaries. Removing statuses fails, because `not checked` is a required visible state.

### T-D · The tool cannot do it; manual Altium step; no tracked state or accept (27/11: 14)
- **Behaviour:**
  - Every finding the tool cannot fix is a ledger item with state (F-C) and "Accept with reason" (U5).
  - Limits are refused at the control (F-LIM).
  - Hand-step advice without a ledger item = 0.
- **Target:** at most 4 T-D confusions; every open item in the final ledger is in state fixed, accepted (non-empty reason), or open and listed on Outputs.
- **Anti-gaming:** a random hand-fix canary must be closed only by re-check on the file. Accepting everything silently fails W33/U5 (JLC-reject needs "make anyway").

### T-F · Agent answers contradict earlier ones or drop decisions (27/11: 13)
- **Behaviour:**
  - F-D repeat-consistency (10/10).
  - Ledger carry-over (W36): no decision in the ledger is contradicted by a later agent message (oracle LLM judge over all final messages vs the ledger).
- **Target:** 0 contradictions found by the judge; at most 2 T-F confusions.
- **Anti-gaming:** the canary changes state between two asks (the answer must change); the probe questions are random from the pool.

### T-G · Previews cannot be judged (27/11: 13)
- **Behaviour:**
  - In the DOM, the footprint preview shows pitch (W15), pin-1, pad names, courtyard (W17), paste and mask layers, and the EP paste outline. Geometry is read from the SVG/canvas model and compared with the oracle PcbLib ±0.01 mm.
  - The schematic preview zooms to at least 400% and lets the student select a net by name. A selected net highlights all of its pins (count = netlist).
  - Text contrast ≥ 4.5:1 (WCAG 2.x 1.4.3).
  - Text stays usable at 200% zoom (WCAG 1.4.4).
- **Target:** 0 geometry mismatches; at most 5 T-G confusions.
- **Anti-gaming:** random part and random net per run. A static legend without geometry fails the comparison.

### T-E · Chat format, internal leaks, consent (27/11: 10)
- **Behaviour:**
  - Internal identifiers in the rendered chat (frozen regex list: `bom\.propose`, `student_said`, `chat\.ask`, `p20\d{12,}`, `\w+\.py\b`, `checks/`) = 0.
  - Tables wider than the chat column = 0; they move to a page link.
  - Each chat message ≤ 10 lines (owner 27/11). A longer answer is split into 2 or more messages, each ≤ 10 lines and each able to stand alone; tables and long lists go to a page link.
  - Consent per F-E (20/20).
  - The guard's messages name the actual writer (W1).
- **Target:** 0 leaks; at most 3 T-E confusions.
- **Anti-gaming:** the canary triggers each internal error path. A regex-scrubbing filter that also drops the item names fails P0-1 (items must still be named).

### T-H · Start-up, navigation, first use (27/11: 7)
- **Behaviour:**
  - At 1366 x 768 with 30 projects, "New project" is visible without scrolling: 1 click.
  - New project asks for the layer count, with no silent default.
  - Every empty page shows exactly one runnable first step.
  - Chips or buttons whose action would be refused for an unmet precondition: enabled count = 0.
  - The "not linked" banner shows iff `project.json` has no Altium project path.
  - URL-source fetch per F-LIM.
- **Target:** at most 2 T-H confusions; precondition violations = 0.
- **Anti-gaming:** random project count (10-60) and a random empty stage.

### T-I · Rules, route results and numbers that need explaining (27/11: 7)
- **Behaviour:**
  - Every badge or count on Rules, Route and DRC equals the length of a list shown on click (F-H d).
  - Pre-route feasibility check (F-H b).
  - The current-to-width row shows the IPC-2221 basis and the monotonic result (W28).
  - The replace banner counts by object type.
- **Target:** count-list mismatches = 0; at most 2 T-I confusions.
- **Anti-gaming:** a random rule set produces random badge counts.

### T-J · Missing output and export features (27/11: 2)
- **Behaviour:** an order note / README export generated from the files (W35, F-I) and listed in the Outputs files table.
- **Target:** 0 T-J confusions; the export exists and the W35 contradiction count is 0.
- **Anti-gaming:** the W35 tenting toggle canary.

### Summary target for A12
- Themes A-J: 106 on 27/11, at most 21 in the rerun (A 0, B 3, C 0, D 4, E 3, F 2, G 5, H 2, I 2, J 0).
- Per-hour rate at most 20% of the 27/11 rate (106 in about 6.5 h).
- Each target is checked separately; one theme above its target = FAIL.
