# Computer-use round (private account)

Checks that need control of the Windows desktop: Altium windows, native file dialogs, a clean install. Everything else was
already checked in the browser or by tests (`docs/VERIFY-LOCAL-2026-11-24.md`, CI). Both prerequisites are in `main`
(4773f40): the draft schematic and the merged parts table (the Library page is now part of the BOM page: Models, Supply and
Status columns; Build library and Check stock in its header).

## How to run

1. In the Claude desktop app on this Windows machine, signed in to the **private account** (computer use is on), open a
   Code session in `C:\Users\Public\Documents\Altium\pcb-advisor`.
2. Paste the brief below as the first message.
3. When it ends, its report is `docs/COMPUTER-USE-2026-11-24.md`; the orchestrator folds it into the final report.

## Brief to paste

```
Run the computer-use verification round of pcb-advisor, following docs/COMPUTER-USE-ROUND.md (section "Checks").

Setup:
- git pull on main. Start the server: .venv\Scripts\python.exe pcb.py serve --no-browser (port 8931), open
  http://127.0.0.1:8931 in Chrome. Altium Designer must be running.
- Work ONLY on a scratch copy: in the app's project menu make a copy of UX-E2E-ESP32C3 named CU-2026-11-24
  (or copy projects\UX-E2E-ESP32C3 to projects\CU-2026-11-24 and its Altium folder). Never change the student's real projects.
- Drive Altium only through the system's buttons and chat. Use computer use to LOOK at Altium (screenshots, open the
  SchDoc/PcbDoc/libraries, read the Messages panel) and for native dialogs; never edit the design in Altium by hand, except
  where a check below says so (the unsaved-changes check).
- Never order, pay or add to cart at JLC; do not touch any JLC tab or account.

For each check: do it, take a screenshot into docs/img/computer-use-2026-11-24/, and write pass / fail / blocked with one line
of evidence. Fix nothing; list defects. Commit the report and screenshots on a branch computer-use-2026-11-24 and push it.
Report in short Hebrew, every line starting with a Hebrew word.
```

## Checks

Ledger numbers refer to `docs/LEDGER-2026-11-23.md`.

| # | Check | What passes | Ledger |
|---|---|---|---|
| A1 | **Build library** (BOM page header) | The project IntLib exists and Altium lists it. Open the SchLib and PcbLib: every built part has a symbol and a footprint; 3D bodies sit on the footprint (not offset, not floating) | 9 |
| A2 | **Draw schematic**, draft mode (some parts without a symbol) | Sheets open in Altium; parts with a symbol drawn, the rest as marked placeholders; every pin has a wire stub to a net label or power port; NC pins carry a No-ERC cross; the UI says draft and lists the placeholders | draft-schematic |
| A3 | Schematic readability | No overlapping labels; sheet titles from the plan (not a bare "Main"); SW1/SW2 have their nets | 35, 33, 11 |
| A4 | **Redraw** after the parts get symbols | Placeholders replaced by real symbols; the old SchDoc is in `.advisor-backup`; nothing the student added by hand is lost silently | draft-schematic, 70 |
| A5 | **Unsaved changes**: move one part in an open SchDoc in Altium, do not save, press Draw again | The system saves or stops with a clear message; nothing is lost | 70 |
| A5b | **Place while the schematic is a draft** | Place is refused with one clear next step (build the library, draw again); the Layout stage says so. Note whether this feels too strict | draft-schematic |
| A6 | **Place** (after a full, non-draft draw) | Mounting holes H1-H4 on the board; keep-out under the ESP32 antenna; SHT40 kept away from the module; J1 at the board edge facing out; no duplicate designators | 1, 2, 3, 6, 10 |
| A7 | **Place on a routed board** | A warning names what will be lost, with one confirmation | 12 |
| A8 | **Route and pour** | No copper inside the antenna keep-out; widths follow current | 3 |
| A9 | **Check board (DRC)** | Altium's DRC count and categories match the UI's DRC line and DFM list (slivers, annular ring, silk) | 7, 8, 51 |
| A10 | **Rules: Apply in Altium** | The PCB Rules editor holds the JLC preset values the Rules page shows | 51 |
| A11 | **Outputs while blocked** | Gerber / OutJob buttons disabled with the reason; no files written | 23, 24 |
| A12 | **Outputs when clear** (after Mark all NC and pin decisions) | OutJob runs; Gerber zip, drill, pick-and-place, BOM and PDF exist in the project outputs; the UI lists them, none missing | 68, 69 |
| A13 | **Progress while Altium works** | The elapsed clock (m:ss) runs; an update request during a step is refused (409) and the UI says why | 65, 67 |
| B1 | **Datasheet: Choose file** (part panel) | The Windows file dialog opens; the chosen PDF is stored and opens in the Confirm pins dialog at the pin page | 16 |
| B2 | **Export / downloads** | Files land in the real Windows Downloads folder; the UI shows that path at once | 27, 28 |
| B3 | **DFM: Upload report** | The file dialog opens; the JLC DFM report is read into the DFM page | 25 |
| C1 | **Clean install, as the examiner** | Fresh clone into a new folder, follow `README` / `docs/SUBMISSION.md` install steps; time from clone to the first page and to a first drawn schematic; every prompt and error noted | priority 2 |
| C2 | **Chrome on Windows, real display** | BOM page (merged table, Supply card, model icons, 3D preview), chat composer and steps, Next slot render right at 1280 and 1920 px | UI |
| C3 | **Chat answers match the screen** | Ask "What blocks the outputs?" while the Outputs banner shows a block: the answer names the same reason | draft-schematic task 2 |

## After the round

The orchestrator merges the report branch, marks the ledger rows `verified` or `open`, and writes the final report
(`docs/FINAL-REPORT-2026-11-24.md`) that combines: `VERIFY-LOCAL-2026-11-24.md`, `BRAIN-EVAL-COMPARE-2026-11-23.md`,
`FRICTION-AUDIT-2026-11-23.md`, `TEST-RUN-2026-11-23-cloud.md`, the draft-schematic and Parts-table docs, this round,
and the final ledger.
