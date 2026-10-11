---
name: manufacturer-and-dfm
description: Prepares the manufacturing package for JLC and walks the student through the JLC DFM and assembly preview, then triages every red item as real or false alarm with a fix. Use when the student asks for "gerbers", "OutJob", "BOM and CPL for JLC", "pre-upload check", "run JLC DFM", "DFM shows red", "CPL rotation wrong", "pick and place", "files for the factory", "quote" (Hebrew - "קבצי ייצור", "גרברים", "DFM אדום", "סיבוב רכיבים").
---

# Manufacturer files and JLC DFM

`<repo>` is the repo path given in the WORKSPACE section of the prompt. JLC (JLCPCB/LCSC) is the only supplier.

## When to use
- The student asks how to export Gerber, drill, pick and place, BOM from Altium, or for a ready OutJob.
- Before the student uploads to JLC: a pre-upload check of the files.
- JLC DFM or the assembly (SMT) preview shows red items and the student asks "is this a problem?".
- The student wants the stock or price of a part: run the parts script, never answer from memory.
- Not for: DRC and layout review (board-review), how a menu works in Altium (altium-help), ordering (the student does it).

## Steps
1. Confirm the board passed the batch DRC (board-review) and the BOM has an LCSC number on every fitted line.
2. OutJob. Give the student the OutJob file when the generator exists, else the manual recipe from
   {{src:m25-fabrication-files.en.md|25.4 Output Job File}}: Gerber (plot layers: copper, overlays, paste, solder mask,
   the outline layer), NC Drill, Pick and Place, BOM. Use a fixed output folder (for example `Outputs/Fabrication`,
   `Outputs/Assembly`) so the files can be read back. The student adds the OutJob to the project, clicks Generate content.
3. Pre-upload check of the generated files (read them, do not trust the dialog):
   a. Outline: the board outline is on its own mechanical layer and appears only in the outline Gerber. It must not be
      in the "add to all plots" list, or every layer gets the outline and JLC reports trace to board edge.
   b. Drill: NC Drill units and format match the Gerber (metric or inch, same digits); plated and non-plated split.
   c. All layers present: every copper layer, both overlays, both paste, both solder mask, outline, drill files.
   d. BOM columns JLC expects: Comment, Designator, Footprint, LCSC Part # (one line per value group). DNP parts and
      test points are left out on purpose and listed. No LCSC number on two lines. Run export_bom.py for the check.
   e. CPL columns: Designator, Mid X, Mid Y, Layer, Rotation. Same designators as the BOM. Units in mm.
4. Parts: run the availability script for every BOM line; take stock, price and Basic/Extended type only from it, with
   its time. Zero or low stock: say the JLC signal, and propose an in-stock drop-in (same package) for the student to approve.
5. PCB DFM at JLC: the student opens the free JLC DFM tool, uploads the Gerber zip, presses the DFM check, and sends a
   screenshot or the exported report of every red item (name, value, location).
6. SMT preview: BOM/CPL upload in the JLC assembly flow, then the Component Placements view. The student checks pin 1
   mark and the body outline of each part against the pads, and sends the list of parts that look rotated.
7. Triage each item. Real: outline on every layer, silk narrower than the JLC minimum, copper too near the edge, wrong
   footprint, a rotated part. Probably false: JLC DFM reads Gerbers with no nets, so same-net spacing, NPTH annular ring,
   connector slots, tiny mask dams and silk over tented vias are often by design. Prove "false" with a measurement or a
   datasheet, not with a guess.
8. Fix at the source: copper or silk in the board; rotation in the CPL offset table (not in the board); LCSC number
   in the BOM. Regenerate and re-upload. A re-uploaded CPL may be ignored by the preview: upload the Gerber zip again too.

## Scripts
- `python <repo>/scripts/skills/export_bom.py <project> jlc` writes the JLC BOM csv; lists lines left out and lines
  that need an LCSC number.
- `python <repo>/scripts/skills/check_availability.py ...` stock and price from JLC, with query time. Quote the time.
- (planned, stage I5) `scripts/outjob.py` ready OutJob.
- (planned, stage I5) `scripts/checks/board.py` outline layers, drill units, CPL rotation vs JLC models.
- (planned, stage I5) `scripts/dfm.py` DFM guide and triage table.
- Until those exist say "not automated yet" and do steps 2-3 by reading the generated files the student shares.
- Never run Altium or log in to JLC for the student.

## References
- `<repo>/shared/reference/course/ad20-essentials/m25-fabrication-files.en.md` (OutJob, BOM, Gerber setup)
- `<repo>/shared/reference/course/altium-education/unit3-pcb-layout.en.md` ([03] process, [06] Preparing for Manufacturing)
- `<repo>/docs/PRODUCT-PLAN.md` (section 8, export rules)
- JLC limits and DFM pages are not in the repo: give the student the link and ask for the number, or say unknown.

## Pitfalls
- Outline on every Gerber: it looks like a real copper fault at the edge. Check the plot list, not only the outline layer.
- JLC DFM has no netlist: most red items are same-net or deliberate. Triage one by one; do not "fix" a pad that is
  correct. Real faults seen: outline everywhere, silk too thin, pads and vias touching.
- CPL rotation: JLC 3D models are often 90 or 180 degrees off footprints built from other sources. Check pin 1 in the
  preview, correct with a per-part rotation offset in the CPL, then verify by rotating the part in the preview.
- Do not "fix" through-hole offsets blind: a JLC model mismatch can show a hole error at the true centre.
- BOM lines can stay unselected even with an LCSC number: same number on two lines, a part with several types, or a
  difficult-part fee. The next button should not say unselected parts remain.
- Some modules (LGA) are Standard assembly only; a drop-in keeps the footprint, and the reason is written down.
- Stop at the quote. Never place the order or save to cart for the student.
- After any copper change near pads, re-run the PCB DFM: it checks same-net via to pad and mask opening to trace,
  Altium DRC does not.

## Output
Pre-upload table: `File | Check | Result (OK / problem / not checked) | Fix`. DFM triage table, one row per red item:
`Item | Where | Real or false | Why (proof) | Fix`. Stock/price lines carry `JLC query <time>`. Max 15 rows, then 3 lines
of next steps. Cite `{{src:<file>|<heading>}}`; say unknown for JLC limits you were not given.
