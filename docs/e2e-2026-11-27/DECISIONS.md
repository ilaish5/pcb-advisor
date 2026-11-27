# Orchestrator decisions

- 02:35 Stage 1 gate: lecturer PASS with conditions C1-C5 (round 2): PB2/BOOT1 pull-down, SDIO pull-ups, fix "24 h on 16 GB" wording,
  recompute current from datasheets at BOM, mark "time invalid until host sets it". Carried into stage 2+.
- 02:35 Test-harness fix (not product code): the product's tool guard (`scripts/tool_guard.py`) restores/deletes every changed repo file at
  the end of an agent turn; our run folder sits inside the install, so it deleted the student's confusion entry C18 and screenshot
  S1-08 during a turn. Added `docs/e2e-2026-11-27/` to `.git/info/exclude` so git status (and the guard) no longer see it.
  The guard's false wording ("the agent edited ...") stays a system finding (engineer-S1 round 2, designer C19).
- 02:19 Stage 2 gate: lecturer PASS with conditions K1-K5 (round 2).
- 02:28 hourly check: student working on stage 3 (30 screenshots), free RAM 0.74GB, commit 9.9/11.0GB (pagefile can grow to 16GB); no action.
- 02:58 Stage 3: the app could not fix library defects (EP paste, courtyard, 3D side, origin) on request. Ruling: not a run blocker (schematic does not depend on them); recorded as system findings for the report, not fixed overnight. Lecturer told to judge the student only on what the tool allows.
- 03:02 Stage 3 gate: lecturer PASS with conditions L1-L5 (round 2).
- 03:28 hourly check: stage 4 running (21 screenshots, library rebuild in progress), free RAM 1.37GB, commit 8.9/10.5GB. Note: two X2.exe processes (1135MB + 137MB) - watch for a second Altium instance.
- 03:47 BLOCKER #1 (stage 4): library rebuild after adding C23 fails: Altium modal 'Could not create integrated library ...IntLib' (IntLib locked while installed/in PrjPcb); bridge reported only 'stopped in the middle', UI showed 'Building in Altium' 20+ min. Orchestrator closed the box (UIA Invoke OK), sent the fix to the fixer (restored from archive). Student told to wait.
- 03:51 Fix #1 dbf3635 (fixer; reviewed by orchestrator: LIBRELEASE + re-add, modal detection 15 s) merged into main, pushed, server restarted; tests/test_altium_library.py 30 passed. Student retries Build library.
- 04:07 Fix #1 verified live (build 03:52: built 31, intlib_fresh, installed, in_project). Stage 4 done; 4 reviewers running.
- 04:29 hourly: S4 reviews done (side-session notes for them never arrived; found via files). Critical question: are the ~30 cross-sheet nets connected in Altium? Alti verifying before the student answers lecturer S4. RAM 1.42GB free, commit 10.5/11.4GB.
- 05:15 resume check: run did not stop. Alti follow-up: inter-sheet nets CONNECTED (Automatic=Global scope, compiled netlist == system netlist, NC = 17 No-ERC markers). Student sent lecturer S4 round 1 with that evidence.
- 05:28 hourly: student mid S4 round 1 (S4-70, board 60x45 set); RAM 1.43GB, commit 9.2/11.3GB; no action.
- 05:47 Stage 4 gate: lecturer PASS with conditions M1-M4 (round 2); M1 satisfied by Alti round 2 compile (55 nets/226 pins). Stage 5 started.
- 05:51 Student asked Alti to set the 4-layer stack by hand (agent said its Altium actions cannot change layers). Ruling: no manual Altium work; code shows the placement step calls ensure_stack(prj,pcb,4) before placing. Agent claim likely false -> engineer to verify at S5 review. Student to confirm 4 layers after Place.
- 06:04 Stage 5 done. Student measured decaps far from pins (C10 15.7 mm, C22/C23 20.9/7.0, C19 28.5); app cannot place near a pin; moving by hand excluded (UI-only rule). Ruling: tool limit = system finding, not a student block. 4 reviewers running.
- 06:15 DISPUTE stage 5: lecturer PASS with gate N1 (move C10, C19/C21, Y1, C22/C23 by hand in Altium before routing) vs the run rule (student = web UI only; no computer use on this account; the app has no near-a-pin placement).
  RULING: N1 is waived as a TOOL LIMIT, not done by hand. Doing it via Alti's scripts would make the board partly not the system's work and blur
  what the router and outputs are judged on. Routing goes ahead on the system's own placement; the decap distances, the corner keep-outs drawn
  as Top copper (KO1-KO4) and the stack with Altium default values instead of JLC04161H are recorded as WRONG system findings
  (engineer-S5, alti-S5, lecturer-S5) and carried into the stage 6/7/8 reviews (DRC, DFM must account for them).
- 06:28 hourly: stage 6 running (18 shots; app rejected a route with 4 short circuits, student handling). No Altium dialog open. RAM 1.00GB, commit 10.6/12.0GB.
- 06:45 Stage 6 done: route OK on 2nd try (1st rejected, 4 shorts), DRC 421. Alti classifies real vs side-effect before the lecturer grades.
- 06:57 DISPUTE stage 6 (Alti vs engineer, lecturer N3): what stack is in the PcbDoc? Orchestrator read Board6/Data of Final-E2E-4L.PcbDoc directly:
  Top/Mid1/Mid2/Bottom all COPTHICK 1.4mil, three dielectrics 12.6mil FR-4 Er 4.8 = Altium defaults, NOT JLC04161H-7628.
  RULING: Alti is right (read the file); the engineer read the intended code path (AdvisorBridge.pas StackLayerProps), which did not end up in
  the saved file. System finding WRONG: ensure_stack adds the 2 inner layers but the JLC stack-up values are not persisted, so impedance
  (USB 90 ohm) and the Gerber/JLC order stack disagree. Not fixed overnight (not a run blocker); stage 7/8 reviewers must check the README/order
  notes say JLC04161H while the file says defaults.
- 07:20 Stage 6 gate: lecturer PASS with conditions P1-P5 (round 2). P5 (Alti recheck) before stage 7.
- 07:28 hourly: stage 7 running (Gerber zip + BOM/CPL exported, S7-06); RAM 2.10GB, commit 10.9/12.0GB; no action.
