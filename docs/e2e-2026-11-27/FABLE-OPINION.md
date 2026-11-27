# Independent opinion: pcb-advisor after the 27/11 end-to-end run

Read in full: PROTOCOL, RUN-STATE, DECISIONS, the student log, designer-SUMMARY, producer-S8, engineer S5-S7, Alti S6-S7. Read in part: the other engineer, Alti and lecturer reports (findings and verdicts), about 30 of the 138 confusion entries, three screenshots, notes.md, the manifest. Every source line cited below was opened by me. REPORT.md was not read.
Limits: one board, one night; student and reviewers are LLM roles; 8 GB RAM with six sessions (some waits are harness artefacts); nothing was fabricated; JLC's DFM verdict and PCBA matching were never seen.

## 1. Judgment

**Not yet trustworthy to order an assembled board from.**
- Front half (idea, BOM, stock, sources, netlist, schematic): transcription is trustworthy. Datasheet quotes were real, "unknown" was said when AN2606 could not be fetched, and Altium's compiled netlist equalled the system netlist (alti-S4: 224/224 pins, 0 split, 0 merged). Design content was not: the first BOM had Qty 1 everywhere, an LSE crystal that fails gm_crit, an LDO at its package limit and no VDDA 1 uF (engineer-S2). All were fixed only because the lecturer asked. A real student has no lecturer.
- Back half (library geometry, placement, routing, DRC triage, order package): alpha. The Gerbers are consistent and JLC parses them (4 layers, 60 x 45), but that is not "safe to order". This board ships with 83 merged mask openings at untented vias on HASL, a full 5.5 mm paste opening under the QFN, VCAP1 17 mm from its cap, a via and signals under the 25 MHz crystal, pours 0.16 mm from NPTH, a CPL point 0.66 mm off on U5, and unverified MCU pins. The Outputs page showed only the last one (S7-03).
- As a final project: scope and discipline are well above B.Sc. level (about 54k lines, tests, guard, lineage hashes, a blocker fixed with a test in minutes mid-run). The risk is the headline. "Idea to manufacturable PCB" is not demonstrated; "idea to a schematic that matches its netlist, plus a first-pass layout with an honest risk list" is.

## 2. Five root causes

**R1. The system reports what it intended, not what it read back.**
Evidence: `scripts/serve.py:463` says "updated in the BOM, on the schematic label and in the library" on every approval, with no library or schematic in existence. `scripts/altium/bridge/AdvisorBridge.pas:2721-2724` has the four JLC stack calls commented out while the header comment promises JLC04161H and only the layer count is checked. notes.md says "Tent vias" while the mask Gerber opens all 157. "The BOM now has 51 parts" after no-op cards. "None of my Altium actions change layers" while Place parts adds them.
Fix: every write returns post-conditions read from the saved file. Banners, canned texts, the order note and the agent's statements about system state are built only from those facts. A read-back that differs is a failure.

**R2. Checks fail open: no evidence renders as green.**
Evidence: `ui/js/views/pages.js:78` falls through to `['ok', 'Pins: nothing to verify']` for scanned datasheets. `scripts/checks/requirements.py:98` skips `in_component` copper, so keep-outs that were Top copper read "met, no copper inside". `scripts/checks/board.py:249-294` measures cap to nearest load, so a pin with no cap is never flagged. The board side of the output gate checks unrouted nets only (`scripts/store.py:4074-4087`). A tick sits over 421 DRC lines (S6-27). No BOM check exists for crystal margin or regulator dissipation.
Fix: three states (verified / not checked / failed), default "not checked"; each check declares its coverage; gates and colours consume coverage, not "the step ran".

**R3. Design intent does not survive between stages.**
Evidence: "VCAP1 capacitor", "VDDA bulk", "SD card bulk" exist only as BOM role text; the placer matches roles by pattern and never targets connectors (`scripts/altium/layout.py:1683`, `:1773`); a second placement made several distances worse; the router has no crystal handling; `scripts/altium/netcurrent.py:99` (`w = max(need, wmin)`) makes a rail narrower once the student enters a current.
Fix: a typed constraint record written at BOM/schematic time (cap bound to pin, crystal bound to pins with a no-route zone, net class with width) that placer, router and checks consume. If it cannot be met, refuse with the number.

**R4. Imported geometry and fab limits are trusted, not normalised.**
Evidence: EasyEDA body outline labelled courtyard, full exposed-pad paste, 3D offsets and origins passed through (alti-S3), then a pad-centroid CPL (`scripts/skills/export_cpl.py:41-42`). The preset measures 6 mil where JLC's floor is 0.10 mm, so 424 lines hide 83 real ones. Tenting is in no preset or rule kind. No local check reads mask or hole-to-copper from the Gerbers (the producer wrote one in 80 lines).
Fix: a footprint normaliser at library build (generated courtyard, windowed EP paste, origin at body centre, real keep-out objects) and a DRC classifier against JLC's numbers: rejects / accepts / cosmetic.

**R5. A finding has no lifecycle, and free chat text is the control surface.**
Evidence: every library and DRC fix ended in "by hand in Altium", and a rebuild would overwrite the hand fix. To pass a failed route the agent deleted the student's keep-out requirement (Idea v13). No accept or waive exists. A review chip triggered `library.build` and an Altium project creation; Stop did not stop the plan (C38, C41). A clear "yes" was refused (C105). Two answers 16 seconds apart contradicted each other (C108).
Fix: a findings ledger (tool fixes / student fixes then re-check / accepted with reason) that the agent edits instead of prose; review prompts read-only; Stop cancels the plan; the agent never removes a requirement to pass a check.

## 3. Where the reviewers were off

- **Engineer**: in S5 and S6 asserted "the stack IS JLC04161H" from a code comment, the product's own R1 mistake; retracted in S7.
- **Lecturer**: the sharpest reviewer (round-1 FIX forced the crystal, LDO, VDDA and power-width fixes; net-aware triage cut the student's 13 decap "fails" to 4 real ones). But every tool-limit item was carried, not closed: L2 (EP paste), L3 (CPL origin), N1 (waived), P3 (DFM items). The gate judged the student, so nothing gated the board.
- **Orchestrator**: waiving hand fixes was right for judging the system. Calling stage 8 "done" with no DFM verdict and no PCBA check is generous.
- **Designer**: 5.4/10 is fair. Bucket K ("not UI", 32 entries) hides trust failures (C38, C41, C101, C107, C108), and fixes 2 and 4 are assigned to `ui/` files although the cause is server truth (R1, R2).
- **"WRONG: 0.127 mm power tracks"**: the width meets IPC-2221. The defect is the non-monotonic rule.
- **Too harsh**: the 45 s freeze and some wait times, given the RAM pressure. The 20-minute silent build was real.

## 4. UX verdict

138 entries in about 6.5 hours is one doubt every three minutes. The student rarely asked "where do I click"; the question was "can I believe this". Counts below regroup the designer's table.
- **Which one is true?** Page, chat and numbers disagree, or the agent contradicts itself: 32, the largest group.
- **Is it alive?** Silent waits of 5 to 20 minutes, sometimes with no end message: 15.
- **Now what?** A problem the tool cannot fix and will not let the student accept: 14, plus 6 of green over open items.
- **I cannot judge this.** Schematic and footprint previews are not inspectable: 13.
- **Chat as cockpit.** Long tables, leaked internals (`student_said`, `chat.ask`), consent by typed sentence: 10.

"Effortless" holds through the BOM. From the library on, the student needs an Altium expert beside them.

## 5. Keep

- Sourced answers with quote verification and honest "unknown".
- Netlist-first schematic with compile equivalence.
- Route rejection on new shorts with automatic restore.
- Lineage hash, outputs completeness check, JLC-format BOM and CPL with identical designator sets.
- Stock check with timestamp and extended-part fees.
- One-click proposal cards, Replace / Keep consent, "Checked by you" versus "Accepted risks" with Revoke.
- The tool guard idea and the fixer loop (bug, test, review, merge) that worked at 03:51.

## 6. Two weeks, in order

1. **Days 1-2, the one-line defects cited in R1-R4:** approval text from the applied diff; `max(need, preferred)`; default "not checked"; write and assert stack values; tent vias in the preset; real keep-out objects; CPL from the footprint origin; decap check per supply pin.
2. **Days 3-5, R1 and R2 as mechanisms**, including a DRC summary and an order note generated from the files into the Outputs page and manifest.
3. **Days 6-8, R4 classifier and R5 ledger:** JLC-classified DRC, local Gerber checks, accept/waive.
4. **Days 9-10, R3:** pin-bound decaps and crystals; via-to-pad 0.2 mm; BOM checks for crystal margin and regulator dissipation.
5. **Day 11:** footprint normaliser.
6. **Day 12:** phase and end message on every long step; read-only review chips; Stop cancels the plan.
7. **Days 13-14:** freeze, rerun this same E2E, count WRONG against tonight's, have the owner export a signed-in JLCDFM report, and present the claim the evidence supports.
