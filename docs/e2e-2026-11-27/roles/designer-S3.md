# Designer review: Stage 3 (Library), UI/UX only, engine Antigravity

## Video highlights
S3-03-build-library-started.jpg | Building: one grey button and one line, no progress per part.
S3-06-library-built.jpg | 30 of 30 built; a long green banner mixes keep-out notes with the result.
S3-10-j1-pins-tab.jpg | Green "Checked: nothing to verify" for a part whose datasheet is a scan.
S3-19-y1-footprint.jpg | Preview shows courtyard smaller than pads; caption says so in tiny text.
S3-32-agent-answer-courtyard-led.jpg | Antigravity answer is short, but the fix is "do it by hand in Altium".
S3-53-origin-3d-answer.jpg | Tool cannot fix J1/J2 origin; answer ends with the same cheerful "Next: Draw in Altium".
S3-45-u1-ep-answer.jpg | "No, I cannot make a paste window": honest, but only a sentence in chat.
S3-39-u1-symbol.jpg | MCU symbol with 49 pins drawn too small to read, no zoom.

Reviewed: S3-01..S3-36 (all opened), roles/student.md S3, confusions C49-C59. Source greps in `ui/js/`.
Flow: switch engine -> Build library (about 2 min) -> open preview tabs (Symbol / Footprint / 3D / Pins) for J1, J2, J3, Y1, D3, D4, SW1 (about 25 screenshots) -> 2 chat questions -> Sources viewer. Building needed one click, which is excellent; checking needed about 40.

## Findings

- [FRICTION] Build has no progress: S3-03..S3-05. After the click the button turns grey "Building..." and one info line says "Building in Altium. It can take a few minutes and Altium may flash while it works." for about 2 min. No count (12/30), no current part, no estimate. Source ui/js/views/bom.js:151 (`libBusy === 'build'` banner). Fix: "Building 12 of 30 parts" with a bar; the Models icons already flip per row, so update them live.
- [WRONG-looking state (UI)] The Pins tab shows a green "Checked" with "Pins: nothing to verify for this part" for parts whose datasheet is a scan or missing: J1 (S3-10), Y1 (S3-21), D3 (S3-25: "No datasheet linked"). Cause: ui/js/views/pages.js:78, the fall-through `return ['ok', 'Pins: nothing to verify...']` applies when nothing was verified. To a student "Checked" in green reads as "the pinout was verified". Fix: that fall-through must be a neutral/amber "Not checked: no readable datasheet pin table. Compare by eye" and only `verified`/`accepted` states are green (pages.js:70-78). This is the most important UI finding of the stage: a green label that says more than the system knows.
- [FRICTION] "Built, check" does not say what to check: S3-07, S3-29 (J1, J2, J3). The reason (3D body offset 2.2/2.8/1.0 mm) exists only in the chat answer (S3-29); the row and the preview show nothing. Fix: the status tag opens the reason on click, and the 3D tab shows "Body is 2.2 mm off the pads (limit 0.5)". Source bom.js status cell (`st.say`, bom.js:71-81) and ui/js/views/modelpreview.js.
- [FRICTION] The suggested fix leaves the app: S3-32 "Check in Altium's 3D view and shift the PcbLib offset". For a student working in the browser this is a dead end with no button. Fix: a verdict in the UI ("only affects 3D view / STEP, not routing: ignore" or an app action). Source: the answer text; no UI control exists.
- [FRICTION] Two source names for the same library item: S3-08/S3-19 captions say "Drawn from the KiCad footprint file of the part" (modelpreview.js:150,159) while the agent says "from EasyEDA" (S3-29). Fix: preview caption names the real source of the stored model, and the chat answer reads it from the same data.
- [FRICTION] Preview captions carry the real warnings in tiny grey text: S3-08 (J1: "pads span 9.86 x 6.49 mm - courtyard 8.94 x 7.35 mm"), S3-19 (Y1: pads 3.6 x 2.96 vs courtyard 3.2 x 2.5). The viewer sees the courtyard drawn through the pads but the UI does not flag it. Fix: a small amber tag "Courtyard smaller than the pads" in the preview header when it is true (4 of 4 small parts in this run). Also mark which pad is pin 1 in words ("pin 1 = A1/shield tab" on J1 shows two naming schemes in one drawing, C51).
- [FRICTION] Symbol 13 pins vs footprint 15 pads (J2, S3-15, C52) and the J3 symbol with numbers only (S3-18) are shown side by side with no note; the Pins tab does not compare counts. Fix: Pins tab shows "Symbol 13 pins, footprint 15 pads (2 shield tabs)" or "pin names missing" as an explicit line.
- [FRICTION] Long result banner: S3-06/S3-36 green box of 4 lines: "Library built 30 of 30 ... Altium did not keep objects on the Keep-Out layer ... Protected: ... Not protected: ..." The result (30/30, 3 with issues) is lost in a paragraph about keep-outs that belongs on the Layout page. Fix: banner = "Library built: 30 of 30. 3 need a look (J1, J2, J3)" with a link; the keep-out note goes to Layout. Source ui/js/views/bom.js banner near :151 and the build result text.
- [FRICTION] The checking itself is a long click path: each part needs a click on the row icon, then 4 tabs (Symbol / Footprint / 3D / Pins), about 4-5 screens per part and 35+ screenshots for 8 parts. There is no "review all" or side-by-side symbol + footprint + datasheet view (C59). Fix: one panel per part with all four views at once and the datasheet page next to it; "next part" arrow.
- [FRICTION] Datasheet viewer: S3-34. Opening the PDF squeezes the Sources list so the file the student clicked moves (C59), and a watermarked low-resolution drawing is unreadable at the viewer size; no zoom control visible. Fix: viewer in an overlay or wider pane with zoom; keep the list stable. Source ui/js/viewer.js and the Sources view in views/pages.js.
- [FRICTION] Polarity confirmation has no control: S3-32 says polarity "is confirmed by the student, not by text matching" (chip is green though "unchecked"). The student has no "Confirm polarity" button (C58). Fix: the Pins tab of a diode offers "Confirm A = pin 1" next to the datasheet page; and the chip must not be green when unchecked (same tone problem as stage 2, ui/js/chat.js:451).
- [COSMETIC] Left menu: Rules badge "6" red dot still there with no board (S3-06, S3-36) (C39/C45 again). BOM nav badge 30.
- [COSMETIC] Preview "pin 1" legend, courtyard and silkscreen chips are small but good; the zoomed PNGs the student made (S3-09, S3-14) show that default zoom is too small for 0.65 mm pitch pads: add a zoom control or a bigger default for fine-pitch parts.
- Good: one-click Build library; per-line icons for Symbol / Footprint / 3D / Pins with a legend; footprint preview with pin-1 highlight, courtyard, silk and dimensions caption is the right idea (it showed the courtyard problem); "Next: Schematic" appears in the header and the chip "Draw in Altium" is the correct next step (S3-36).

## Antigravity vs Claude Code chat (stages 1-2 vs stage 3)
Evidence: S3-28..S3-32 (Antigravity, gemini-4-hydrogen-high) against S1-02/S1-13 and S2-13/S2-18 (Claude Code, Opus).
- Length: Antigravity answers are 8-12 lines, one short list, no table (S3-29, S3-32). Claude Code answers were 30-40 lines with tables of 6 columns and 11-14 rows (S2-13, S2-18, S1-15). Antigravity is much closer to the owner's "short answers" rule.
- Waiting: Antigravity shows "Working... 54 s" (S3-31) and answers in about a minute; Claude Code waited 3-6 min with "Thinking/Searching JLC" (S2-33, S2-34). Antigravity feels far more responsive in the UI. (I have no exact stopwatch values for S3; unverified beyond the 54 s screenshot.)
- Formatting: same renderer, so same look. Antigravity writes a "Next: press Draw in Altium on the Schematic page, redraw it by hand in Altium, or tell me to draw it" (S3-29): a good one-line next step that matches the visible chip. Claude Code's "Next:" lines often disagreed with the buttons (stage 1 C28, stage 2).
- Chips and tags: the same set of green datasheet chips appears with both ("unchecked" in green, S3-32); chips are not engine-specific. The thread is shared across engines (same title "I want a small USB-C sensor board..."), and only the footer changes ("Antigravity CLI - gemini-4-hydrogen-high"): good continuity, but a divider line "Engine changed to Antigravity" in the thread would explain a change in tone/length.
- Depth: the short answer trades detail: the 3D offset was reported but the fix was "do it in Altium"; Claude Code's longer answers carried more verified numbers but buried them. UI recommendation: keep the short style as the default for every engine and move detail to the page.

## Confusions C49-C59: answers
- C49 REAL. No progress, no source per part (bom.js:151); see the first finding.
- C50 REAL. "Checked" in green when nothing was verified (pages.js:78). Fix as above. "Built, check" needs a reason on click.
- C51 PARTLY. Pin naming A1B12 vs shield tab "1" is how the KiCad footprint is drawn; UI should say "pin 1 = shield tab" in the legend. Whether the footprint matches the datasheet is for the engineer.
- C52 REAL (UI side). Pin count mismatch and unnamed J3 pins are not flagged. Fix in the Pins tab.
- C53 REAL (UI side). Y1 shows plain "Built" and a green Pins check although its datasheet is a scan: the status logic ignores the scan (pages.js:78, bom.js status).
- C54 REAL. Polarity shown as green "Checked - No datasheet linked": contradictory text in one chip. Fix: amber "Polarity unverified (no datasheet)". The footprint name "LED0805-R-RD" for a green LED is content (engineer).
- C55 / C55b REAL (UI side). The preview prints the numbers but does not flag a courtyard smaller than the pads; systematic on 4 of 4. Fix: amber tag. Whether placement uses pads (+0.25 mm) is for the engineer.
- C56 REAL. Two source names (modelpreview.js:150-159 vs the agent text), and the 3D warning is only in the chat.
- C57 REAL. The only fix offered is manual work in Altium; add a verdict or an in-app action.
- C58 REAL. Caption "courtyard" with no explanation of what the placer uses; no Confirm polarity control; green chip for unchecked.
- C59 REAL. Viewer shifts the list, watermarked drawing unreadable, no zoom or side-by-side compare.

## Score and fixes
Score S3 (UI/UX only): 6/10. Up from stage 2 because the build is one click, answers from Antigravity are short and fast, and the previews are useful. Held back by the green "Checked" that overstates what was verified, no build progress, and about 40 clicks to review 8 parts.

Top 3 fixes:
1. Never show green "Checked / nothing to verify" when nothing was verified: use amber "Not checked: no readable datasheet" and show the reason behind "Built, check" (ui/js/views/pages.js:70-78, ui/js/views/bom.js:71-81, ui/js/views/modelpreview.js).
2. Show build progress and a short result banner: "30 of 30 built, 3 need a look", with the keep-out paragraph moved to Layout (ui/js/views/bom.js:151 and the build result text).
3. One review panel per part: symbol, footprint, 3D and pins together with the datasheet next to them, flags for "courtyard smaller than pads" and "pin counts differ", and a Confirm polarity button (ui/js/views/modelpreview.js, ui/js/viewer.js).

## Round 2 (S3-37..S3-53, confusions C60-C67), UI/UX only

### Main question: how does the UI tell the student that the tool cannot fix something, and what to do instead?
Today: it does not, structurally. The limit appears only as a sentence inside one chat answer ("No, I cannot make a paste window", S3-45; "No - the tool copies EasyEDA courtyards and (0,0,0) 3D offsets as-is ... Edit them in Altium", S3-53). Evidence of the gap:
- Every one of those answers ends with the same "Next: press Draw in Altium on the Schematic page" line and the same chip "Help me with the next step: Draw in Altium" (S3-45, S3-47, S3-49, S3-53), even while a production-relevant problem is open (J1/J2 origin off by 1.42/2.32 mm, so the CPL centroid is wrong). The next-step chip does not know about open library issues (it comes from the server stage state, ui/js/chat.js:608-617).
- The BOM row keeps the vague "Built, check" (S3-36), with no reason; after the student learned the reason in chat, nothing on the page records it. Chat is the only place the "cannot fix" fact lives, so it is lost on reload and invisible at Layout and Outputs.
- The advice "Edit in Altium (Edit > Set Reference > Component Origin)" cites two docs marked "is not in Sources" with a warning triangle (S3-53), so the student cannot open the source of the instruction (C67).
- The student works in the browser (UI-SPEC principle: planning outside Altium, then implement in Altium), so "do it in Altium" is allowed in principle, but it arrives with no checklist and no tracking.

Proposed generic UI pattern (one for the whole product): each open item has one of three visible states, shown on the row and in a "Needs you" list in the header: (1) "Tool can fix" with a button; (2) "You fix in Altium" with 2-3 numbered steps and a "Done" checkbox; (3) "Ignore, safe because ..." with a one-line reason. Items of kind (2) warn at the next gate ("2 library items still need your Altium step") and appear in the Outputs "Before you order" list. The "Next:" line must be derived from open items first, then from the stage. Sources: row status ui/js/views/bom.js:71-81; chips ui/js/chat.js:608-617; "Before you order" in ui/js/views/pages.js (Outputs).

### Confusions C60-C67: answers
- C60 REAL. U1 gets the same green "Checked - nothing to verify" (S3-38, pages.js:78) although nothing was compared for the MCU, the most important part; the 49-pin symbol is unreadable at default size with no zoom (S3-39). Fix: amber "Not compared with the datasheet", zoom/scroll in the symbol preview, and a pin list table next to the drawing (ui/js/views/modelpreview.js:150).
- C61 REAL. The footprint preview has no layer toggle (paste, mask), so the student cannot see the EP paste or LGA paste. UI-SPEC tab 4 already asks for a layer toggle on the PCB preview; the model preview needs the same. Fix: Copper / Paste / Mask / Silk toggles in modelpreview.js.
- C62 REAL (UI side). The honest "cannot" is correct behaviour; the problem is that it ends as prose. Use the pattern above: item "U1 EP: single solid paste pad, no thermal vias" as "You fix in Altium" with steps, or "Ignore: JLC optimises stencil apertures" with the cited source. The source-backed GND quote (DS10314 p.124, S3-45) is the right inline tag: good.
- C63 REAL. About 4 min with only "Working... N s" and no steps (S3-46). The Antigravity run shows no step list at all, while Claude Code showed "Steps (n)" and named steps: inconsistent between engines. The U3 pad-length verdict "fine as-is" without a reason is content (engineer). UI: when an answer departs from a cited datasheet value, show both numbers in a small table with the verdict and the reason.
- C64 REAL (UI side). Two claims carry "File only, claim not verified: no quote given" in small grey text (S3-49) while the verdict "0.80 mm tab fits" looks equally certain. Fix: unverified claims get an amber tag, and a crop of the datasheet drawing sits next to the claim. The plated/unplated discrepancy is for the engineer.
- C65 REAL. The PDF viewer says "Text hard to read" and a wheel tick jumps a full page (overshot to page 4 twice, S3-50); the drawing is a tiny region; no "Confirm polarity" button. Fix: open at the cited page and highlight the cited region (the citation already says "p. 2, Package Profile"), page arrows instead of wheel scroll, and a polarity confirm button on the Pins tab of diodes. Source ui/js/viewer.js.
- C66 REAL, important. J1/J2 origin off the body centre (wrong CPL centroid) was hidden behind the warning "3D body 1.0-2.8 mm off the pads"; the row text stayed "Built, check" and the next step was "Draw in Altium". A production-relevant finding was shown as cosmetic. Fix: classify library issues by consequence (3D only / affects production files) and show the second kind in red on the row and in Before you order. UI cause: bom.js status uses one amber tag for all issues. (Whether the origin is truly wrong is for the engineer/alti.)
- C67 REAL. Citations marked "is not in Sources" cannot be opened (S3-53). Fix: offer "Add to Sources", or label it as the tool's built-in help with a link; never cite a file the student cannot open.

### New round 2 findings
- [FRICTION] The long green banner "Library built: 30 of 30 ... keep-out" is still on the BOM page in S3-45 and S3-53 and covers the top of the table. Make it short and dismissable (round 1 finding stands).
- [FRICTION] Engine difference: the Antigravity chat shows only "Working... N s" (S3-44, S3-46) while Claude Code showed "Steps (n)" with named steps; the student sees less of what the agent does on one engine. Fix: the same step list for both engines (progress block in ui/js/chat.js).
- [COSMETIC] Inline source tags with a quote and a tick (S3-45) are the right pattern; keep.

Round 2 score (UI/UX only): 5.5/10 (down from 6). The honest answers are good, but there is no place where "the tool cannot fix this, you must" lives, the next-step line ignores open problems, and the production-relevant origin problem was shown as a cosmetic "check".

Top 3 fixes for round 2:
1. A persistent per-item state "Tool can fix / You fix in Altium (steps + Done) / Ignore (reason)", on the row and in Before you order; "Next:" derived from open items (ui/js/views/bom.js:71-81, ui/js/chat.js:608-617, Outputs checklist in ui/js/views/pages.js).
2. Classify library issues by consequence (3D-only vs production), red plus a gate warning for production ones, and replace the green "nothing to verify" (ui/js/views/pages.js:70-78, bom.js status cell).
3. Make the evidence readable: viewer opens at the cited page/region with page arrows, never cite an unopenable source, and add zoom, layer toggles and a pin list to the model preview (ui/js/viewer.js, ui/js/views/modelpreview.js).
