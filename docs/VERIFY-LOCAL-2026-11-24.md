# Local verification of 4c713e1 on Windows, 2026-11-24

Branch `claude/verify-local-ef0f06` (cut from `phase0-correctness` at 4c713e1). Not merged.

## What could not be done as asked

- **Claude in Chrome was not usable.** The only connected Chrome was a macOS one ("Browser 1"), not the Windows
  "ILAISHALEMD950". Its 127.0.0.1 would be another machine, so nothing was run there (the one empty tab it opened was closed).
  All browser checks below ran in the **built-in browser pane** (Chromium) against this machine.
- **The built-in browser does render PDFs** (its own PDF viewer, with toolbar). The earlier belief that it cannot was wrong,
  so check 3a below is a real rendering check, with the caveat that it is not Chrome.
- Altium tests: `PCB_ADVISOR_ALTIUM=1` was set by me (X2.EXE was running). The server now runs as a detached hidden process
  from the main checkout, not in the "pcb-advisor server" terminal tab. A second server (worktree code, same data,
  `PCB_ADVISOR_HOME` = main checkout, port 8932) was used for the fixed code and has been stopped.

## 1. CI for 4c713e1

| Workflow | `main` | `phase0-correctness` |
|---|---|---|
| tests (`-m "not windows and not altium"`) | success | success |
| install | success | success |
| check | still running when last looked (success on `phase0-correctness`) | success |

The earlier failure (`test_no_view_draws_a_next_button_outside_the_slot`) is gone. Nothing failed, so no
real / platform / flaky classification was needed. Check once more for `main`/`check` before merging.

## 2. Windows / Altium test set, local

`PCB_ADVISOR_ALTIUM=1 pytest -q -rfEs -m "windows or altium"` (stdin from NUL, main checkout's venv): **4 passed, 0 failed,
0 skipped** (tests/test_altium_live.py 2, test_dfm_wave3.py 1, test_review_fixes_server_lib.py 1). No full suite was run locally.
After my fixes I ran only the touched files: test_pin_decisions, test_pin_waiting, test_sources_reference, test_ui_pins,
test_viewer, test_ui_model_icons: all pass (one pre-existing skip).

## 3. Browser checks (built-in browser, 1440x900, server on 4c713e1 then worktree)

| Item | Result | Evidence |
|---|---|---|
| 3a Confirm pins dialog size | pass | dialog 1408x868 in a 1440x900 window |
| 3a PDF at pin page, width-fit, sidebar closed, table beside it | pass | UX-E2E-ESP32C3 U1: opens at `#page=33&zoom=page-width&view=FitH&pagemode=none&navpanes=0`, no sidebar, 27-row pin table beside it (`img/verify-2026-11-24/a-pins-dialog-esp32-p33.jpg`). lte-tracker D31 after fix: `a-pins-dialog-pdf-after-fix.jpg` |
| 3a Readable | pass, with a note | page-width zoom shows ~87-127 %; text is legible. Open: page 33 of that datasheet is a mechanical-dimensions page, not the pin table (see open defects) |
| 3a lte-tracker D31 (before fix) | **fail, fixed** | iframe showed `{"error": "not in the library"}` (`a-pins-dialog-missing-pdf-before.jpg`); see defect 1 |
| 3b Library icons render, four per row | pass | 60+ rows, all four icons present |
| 3b Colours green/grey/red | **fail, fixed** | the 25 "Missing" rows of ceramic-controller were all green; defect 2. After: red symbol/footprint, grey pins (`b-library-missing-row-fixed.jpg`) |
| 3b Click opens quick preview: symbol, footprint, 3D, pins | pass | C2: symbol (2 pins), footprint (C1206, 2 pads), 3D, pins tabs all draw |
| 3b 3D from a STEP/WRL model | pass | C2 (VRML C1206) and ESP32-C3-MINI-1 U1 render with orbit hint (`b-library-3d-wrl.jpg`, `b-library-3d-esp32.jpg`); a part with no model says so with a Build library button (`b-library-3d-none.jpg`) |
| 3b No network outside 127.0.0.1 | pass | resource entries after loading and opening 3D: three.js, OrbitControls, VRMLLoader, chevrotain, `/api/library/model` all `http://127.0.0.1`; 0 external of 109 |
| 3c Nav collapse / expand | pass | real click on Collapse |
| 3c Chat hide (button) and restore (Ctrl J) | pass | |
| 3c Chat resize | pass | drag splitter 1062 to 806 px, double-click resets to 1062 |
| 3c Next button top-right | pass | at y=21, right edge 1037-1038 px on Idea, BOM, Schematic, Layout, Rules, Library; 1027 on Sources and Outputs (list scrollbar). Outputs shows "Resolve the blocker" in the slot while blocked; DFM shows "Upload report" (end of the path) |
| 3c Compact preview pages | pass | schematic and layout previews fill the sheet with their action row above (screenshots under E2E) |
| 3c Chat steps above composer | pass | "Checking the part library - 16 s / Steps (3)" sits above the fixed composer |

## 4. Two-board walk (real clicks on the nav and Next; Altium was not driven)

**ceramic-controller** (status done): every stage had content.

| Stage | Worked | Blocked / friction |
|---|---|---|
| Idea | requirements, block diagram, "confirmed", Next: BOM | none |
| BOM | 127 parts, prices, stock; Next: Schematic | Next goes to Schematic: **Library is not on the Next path** (BOM, Schematic, Layout, Rules, Outputs, DFM). Library's own Next points back to BOM |
| Library | 69 lines, 35 built, 25 missing; icons + previews | 25 Missing rows end in raw tool output (easyeda2kicad "getaddrinfo failed", URLs to SnapEDA, Ultra Librarian). No network on this machine, so it is the honest state, but it is a wall of text per row. Row said "no symbol was made" while icons were green (fixed) |
| Schematic | 4 sheets drawn (previewed, zoom bar) | none |
| Layout | real 4-layer board, 100x80 mm | none |
| Rules | rules table with several rows marked "Below JLC minimum" | Apply in Altium / Download IRA offered |
| Outputs | file list, `BOM_jlc.csv` marked "Out of date" with "Make again" | not clicked (writes files) |
| DFM | findings list with some marked "Real issue" | none |

**UX-E2E-ESP32C3** (a draft-level board, Hebrew idea text).

| Stage | Worked | Blocked / friction |
|---|---|---|
| Idea | diagram, requirements, confirmed 23 Nov | none |
| BOM | 12 lines, 19 parts, $4.99 per board; Next: Schematic | none |
| Library | 12 of 12 built, 3D renders for the ESP32 module | none |
| Schematic | banner: "Not made yet: 2 pins have no net..." with "Mark as 26 as NC" and "Open Schematic" | the banner mixes "2 pins" and "26 pins"; the one-click NC is good, nothing was pressed (it writes) |
| Layout | board, "Board DRC: 21 violations, 18 h ago" with Dismiss | none |
| Rules | board matches the JLC preset | fine |
| Outputs | "Resolve the blocker" in the Next slot (went to Schematic), accepted risks list, Gerber zip "Out of date" | the button is the right idea, the click lands on Schematic and not on the blocking item |
| DFM | 9 findings, accepted risks (6), unfinished schematic J1 SBU1/SBU2 | none |
| Chat | question "What blocks the outputs, in one sentence?" answered in about 25 s | answer: "Nothing is blocking the outputs ... only the Gerber zip is out of date". The DFM page and Outputs banner show an unfinished schematic (J1 SBU1/SBU2 open pins). The answer contradicts the UI (`d-ux-chat-answer-vs-dfm.jpg`) |

## Defects fixed (this branch)

1. **2ac2a0c, Confirm pins dialog opened an empty/404 PDF when the linked datasheet had no file** (lte-tracker D31: BOM says
   `esda6v1w5.pdf`, only a sidecar `.json` is on disk, the real `ESDA6V1W5_datasheet.pdf` sits beside it). The dialog's
   iframe showed raw JSON, said "no text could be extracted (a scan)", and "Pins match" would send a datasheet page as
   evidence for a page nobody saw. Fix: `sources.document_path` is now the one resolver for `/api/source` and the dialog;
   `confirm_data` falls back to the same part's local document, else returns `missing_doc` and the dialog says the file is
   not on this computer; `accept` drops evidence whose file does not exist and carries no hash. Test:
   `test_a_linked_datasheet_with_no_file_is_not_offered_as_a_page`. Verified in the browser (iframe loads the real PDF).
2. **e4cafa2, Library icons showed green for lines the build made nothing for.** `r.symbol` is true when the Altium project
   holds a symbol, so 25 Missing rows had green symbol/footprint/pins icons while their preview said "There is no symbol to
   draw yet". Symbol and footprint are now red, pins grey, with words. Test assertion added in `test_ui_model_icons.py`.

## Defects left open

1. **Empty pin numbers** in lte-tracker D31's stored sheet (`netlist/03.json`: every pin has `num: ""`), so the Pin column of
   the dialog is blank and every "wrong" checkbox shares an empty key. Legacy data, same key as the code reads
   (`num`); not a code mismatch. A board whose parts have no pin numbers has nothing to compare with a datasheet.
2. **Pin page heuristic**: ESP32-C3-MINI-1 (the Chinese datasheet file) opens at page 33, a dimensions page. The page list
   comes from text matching, which a CJK datasheet defeats. The dialog does not warn that this document is not English.
3. **Chat answer vs UI**: asked what blocks the outputs, the agent said nothing blocks them while the UI shows an unfinished
   schematic. Agent-context issue, not touched.
4. **Library is off the Next path** (BOM goes straight to Schematic; Library's Next goes back to BOM). A design choice, noted
   as friction.
5. **Library Missing rows** print raw converter output; a short human sentence with the details folded would read better.
6. **Chrome not verified**: everything above ran in the built-in browser, not Chrome on ILAISHALEMD950.
7. `main`/`check` workflow was still running at the last look.
