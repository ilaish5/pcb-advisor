# Designer review - Stage 7 (Outputs, before-you-order, exports, notes, chat on Claude Code) - UI/UX only

## Video highlights
- S7-03-outputs-generated-21-files-2-warnings | Same orange warning twice; Layout still red 424.
- S7-04-export-menu | Four exports; no README, no "send these to JLC" bundle.
- S7-06-bom-and-cpl-exported-toast | Toast has Download, but the file list is below the fold.
- S7-02-outputs-page-warning-U1-unchecked | Outputs dot is green with a risk banner and 424 open.

## Score: 5 / 10 (UI/UX only)
Good: Generate takes ~40 s with a Stop button, rows say Current / Out of date / No record, the CPL toast has a Download link, Checked-by-you and Accepted-risks cards each have Revoke, the "What do I send to JLC?" chip exists. Weak: the page never tells the student in one place "ready / risky / what to do next", the deliverables (the files) are pushed below two big cards, the path is only "exports/", and the chips and the nav dot disagree with the page.

## Findings (PROTOCOL format)

- [WRONG] No readiness summary; the student cannot tell what is ready to order and what is risky: S7-02/03. The only risk text is the U1 pin warning; the 424 DRC findings (red "424" on Layout in the same screenshot), the 3 accepted risks and the untented vias appear nowhere on Outputs. The nav dot for Outputs is green (S7-02/03) while the banner is orange and Layout is red (shell.js:101-104 `stageStatus` takes the server's stage state; Outputs is "clean" once files exist). Why it matters: green = "go order" is read literally. Generic cause: the Outputs stage state reflects "files exist", not "what is known to be open before ordering". Fix: one card at the top, "Before you order", with 3 rows: Files (4 current) / Parts (1 unchecked: U1, Check in DFM) / Board (424 findings: which block ordering, which are accepted or stricter than JLC, Open Layout), each with a tone; the Outputs dot takes the worst row's tone. Files: `ui/js/views/outputs.js` (:253 meta line, :314-317), `ui/js/shell.js` (:101), `scripts/stages.py` (state derivation, server).

- [FRICTION] The same warning twice, stacked: S7-03 (the result banner lists "Warning (the outputs are still made): 1 part has pins nobody checked ... U1" and directly below a second banner repeats the identical sentence with Confirm / Open DFM). Also "Altium wrote no BOM, so BOM/..._BOM_jlc.csv is the advisor's JLC BOM" next to a folder row "BOM 1 file" reads as a contradiction (C132). Fix: the step-result banner shows only what the step did ("Altium wrote 21 files"); the standing risks live only in the Before-you-order card; file-provenance notes become a tooltip or a "Made by" column. Files: `ui/js/views/previews.js` (:587 outputs warnings listed from 0), `ui/js/views/outputs.js`.

- [FRICTION] The deliverables are below the fold and their location is vague: S7-02 (single file row at the bottom, under two tall cards), S7-06 (after Export the list is not visible at all, only a toast). The header says "4 files in exports/" (outputs.js:253), never the full path; the student had to find `projects/Final-E2E-4L/exports/` on their own (C133). No "Open folder", no "Copy path", no "Download all". Fix: files table first, risk cards after it (collapsed with a count); header line "Files are in <full path> [Open folder] [Copy path]"; "Download JLC package (zip: Gerber + BOM + CPL + notes)" as one primary button. Files: `ui/js/views/outputs.js` (:253 meta, list :285), `ui/js/views/pins.js` (:22 cards, collapsed by default).

- [FRICTION] Two export paths with overlapping names and no "what do I send": "Generate outputs in Altium" writes 21 files in Altium folders (Gerber 14, NC Drill 4, Pick Place, BOM, Documentation); the Export menu writes Gerber zip, BOM (JLC), BOM (generic), CPL (S7-04). The student cannot tell which set to upload. "Gerber zip for JLC - from Altium" vs "BOM (JLC)" have different origins with no explanation; "BOM (generic)" is not for JLC and sits between the JLC items. Fix: group the menu by purpose ("For the JLC order": zip, BOM, CPL; "Other": BOM generic, OutJob) and mark the Altium folders "Altium's raw outputs - not needed for the order". Files: `ui/js/views/outputs.js` (:250-261 `outExportItems`).

- [FRICTION] No README / order note output; what the agent writes goes somewhere the page does not list: S7-07 ("The tool has no README or order-note button, so I added ... to your project notes.md"). C134-C136: the notes are in `notes.md` at the project root, not in `exports/`, not in the Outputs list, not previewable; the first version lost most of the student's risks (C135), and the final text has "Tent vias" next to "Vias are NOT tented" (C136). The student cannot review the order note from the Outputs page. Fix: an "Order note (README)" row in the Outputs list, previewable, exported with the package; when the agent edits it the row shows it changed. Files: `ui/js/views/outputs.js` (list and preview), `ui/js/viewer.js` (md preview).

- [FRICTION] "Confirm" on the warning banner is ambiguous (S7-02/03: "Confirm | Open DFM"): it is not clear if it marks U1 verified (which needs a datasheet page) or accepts the risk. The same word is used for "Confirm idea" and for pins. Fix: "Check pins in DFM" as the only action, or "Accept risk" with its own wording and tooltip. Files: `ui/js/views/pins.js`, `ui/js/views/outputs.js`.

- [WRONG] The chat chips on the Outputs page are the Layout ones: S7-02/03/06/07 ("What is wrong in the layout (424 open), and how do I fix it?", "Help me with the next step: Fix the board", and only third "What do I send to JLC?"). The chat also shows the previous Antigravity answer while the footer says "Claude Code CLI - opus", plus raw cards "Outjob generate" / "Altium run outjob: ..." (S7-03). Generic cause: chip order follows the server's primary stage (chat.js:608-617), not the page the student is on. Fix: on Outputs the first chip is "What do I send to JLC?"; raw "Altium run ..." cards become one human line. Files: `ui/js/chat.js` (:588 CHAT_PROMPTS, :608-617).

- [FRICTION] Nothing is confirmed or gated: C137 / S7-03 (outputs made with 424 open and U1 unchecked, a warning only). Given the owner's low-friction rule I do not ask for a blocking dialog. The UI gap is the status, not the gate: the Export button should carry the state ("Export - 2 things open") so a student who exports and goes to JLC knows what they take with them. The server already refuses at unrouted nets (outputs.js:10 `outBlockWhy`), which is the right kind of block. File: `ui/js/views/outputs.js`.

- [COSMETIC] "No record" on the manifest (S7-02) is unexplained; for a file the tool itself wrote the label should be "Made by the tool" (outputs.js:132 `OUT_LIN`, :163). The sticky header covers the top of the list while scrolling (student note C131).

## Answers to every confusion entry (C131-C137)
- C131: Real UI problem. The page has one warning and no "before you order" list; the sticky header hides the top. Cause: outputs.js:314-317 and pins.js:22. Fix: Before-you-order card.
- C132: Real. Duplicate warning and "no BOM" vs "BOM 1 file" wording; outputs are made with 424 open and the page does not mention it. Cause: previews.js:587 outputs warnings listed from 0.
- C133: Real. Export menu works but has no "what to upload" grouping, no full path, no README entry. Cause: outputs.js:250-261. Positive: "Gerber zip written, 14 files" and the CPL toast with Download.
- C134: Real (missing in the UI): an order-note row; the agent's notes.md is invisible on the page.
- C135: Mostly content (agent dropped earlier risks); the UI cause is that the student must open notes.md outside the browser to find out. Preview the note on Outputs.
- C136: Content wording; a preview that separates "Risks" from "Ordering instructions" would make it visible. Out of scope as a text edit.
- C137: Real as status, not as gate (see finding). Low-friction rule: show, do not block.

## Top 3 fixes (generic, ui/ files)
1. "Before you order" card at the top of Outputs (Files / Parts / Board rows with tones, one next action each), nav dot = worst row, risk cards below the files, duplicate banner text removed. Files: `ui/js/views/outputs.js` (:250-317), `ui/js/shell.js` (:101), `ui/js/views/pins.js` (:22), `scripts/stages.py` (server).
2. Make deliverables findable: files table first, full path + Open folder + Copy path in the header, one "Download JLC package" button, Export menu grouped by purpose, an "Order note (README)" row that is previewable. Files: `ui/js/views/outputs.js`, `ui/js/viewer.js`.
3. Page-aware chat: chips follow the page (Outputs: "What do I send to JLC?" first), raw "Altium run ..." cards become human lines, engine label per message. Files: `ui/js/chat.js` (:588, :608-617).

## Out of scope
- The 424 DRC findings, the unchecked U1 pins, the untented vias and the content of notes.md are board/engineering matters; the student choosing not to confirm U1 is not judged. The only UI requirement: they are visible on Outputs in one place.
