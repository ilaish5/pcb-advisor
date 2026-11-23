---
name: manufacturer-and-dfm
description: Prepares the JLC manufacturing package (OutJob, Gerber zip, BOM, CPL), checks it before upload and triages JLC DFM reports. Use when the student asks for "gerbers", "OutJob", "pick and place", "pre-upload check", "run JLC DFM", "I exported the report", "DFM shows red", "CPL rotation wrong" (Hebrew - "קבצי ייצור", "גרברים", "DFM אדום"). Price and stock quotes belong to parts-and-stock.
---

# Manufacturer files and JLC DFM

`<repo>` is the repo path given in the WORKSPACE section of the prompt. JLC (JLCPCB/LCSC) is the only supplier.

## When to use
- The student asks how to export Gerber, drill, pick and place, BOM from Altium, or for a ready OutJob.
- Before the student uploads to JLC: a pre-upload check of the files.
- JLC DFM or the assembly (SMT) preview shows red items and the student asks "is this a problem?".
- Not for: DRC and layout review (board-review), how a menu works in Altium (altium-help), ordering (the student does it).

## Steps
1. The board passed DRC: `drc_total` in `board_facts` or the route result says so, else ask the student (board-review; the
   physical checks are `python <repo>/scripts/checks/board.py <pcbdoc> --design <project>`). Every fitted BOM line has an LCSC number.
   Parts in `pins_waiting` (CURRENT STATE) hold the OutJob and the Gerber zip: say so first.
   Run `python <repo>/scripts/lineage.py <project> status` before files go out.
2. OutJob. With a linked Altium project send `altium.run_outjob` (adds the OutJob and generates Gerber, NC Drill, Pick and Place,
   BOM). Without one run `python <repo>/scripts/outjob.py <project>` (writes `projects/<project>/exports/`; the student copies it
   into the Altium project and clicks Generate content), or the manual recipe {{src:m25-fabrication-files.en.md|25.4 Output Job File}}.
3. Pre-upload check of the generated files (read them, do not trust the dialog):
   a. Outline: the board outline is on its own mechanical layer and appears only in the outline Gerber. It must not be
      in the "add to all plots" list, or every layer gets the outline and JLC reports trace to board edge.
   b. Drill: NC Drill units and format match the Gerber (metric or inch, same digits); plated and non-plated split.
   c. All layers present: every copper layer, both overlays, both paste, both solder mask, outline, drill files.
   d. BOM columns JLC expects: Comment, Designator, Footprint, LCSC Part # (one line per value group). DNP parts and
      test points are left out on purpose and listed. No LCSC number on two lines. Run export_bom.py for the check.
   e. CPL columns: Designator, Mid X, Mid Y, Layer, Rotation. Same designators as the BOM. Units in mm.
   f. Produce the files before naming them: run export_bom.py (jlc) for the BOM and export_cpl.py for the CPL, then list
      `exports/`. Tell the student to upload only files that exist there, by their real names. No CPL file: say so, never name one.
4. Parts: stock, price and Basic/Extended type only from the stored JLC checks, with their time; run
   `check_availability.py` only for lines whose `stock_check` is `missing` or `stale` (rule 4).
   Zero or low stock: say the JLC signal, and propose an in-stock drop-in for the student to approve. Same
   package is not enough: at ordering a swap is free only on the same FOOTPRINT (step 9).
5. The JLC check, done with the student at the end. The account is theirs: never log in, never ask for a password,
   never upload for them. Go one step at a time, as the DFM view lists them (header menu, "How to check at JLC"):
   a. The Gerber zip: action `jlc.gerber_zip` (the same as Outputs > Export > Gerber zip for JLC). It reads the newest
      Gerber and NC drill set of the linked Altium project and writes `exports/<project>_gerbers.zip`. Say what its line
      reports: files, when they were written, what is missing. No outline (or an outline file with no drawing in it:
      draw the board shape on Mechanical 1), no drill file or no top mask is a fix in Altium
      (OutJob, Generate content) before any upload. For assembly the BOM and CPL are in Outputs (checked in step 3).
   b. The student opens jlcdfm.com and signs in.
   c. They upload the zip, run PCB DFM (and SMT DFM with the BOM and CPL), and export the PDF report.
   d. When they say the report is exported: `jlc.pickup`. It adds the JLCDFM PDFs that arrived in Downloads since the last
      report (the DFM view also finds them when the student comes back to the window). Refused with "no new report":
      ask them to export it again, or name the file with `name`. `kind` only if the header was unclear.
   An action is applied after your reply. When you need the result in this turn run `scripts/dfm.py gerber-zip <project>`
   or `scripts/dfm.py pickup <project>`: they print it.
6. Read the new report: its slices are listed under `dfm_checks` in the project state. View them, list what you read
   with `dfm.triage` (rows start unknown, the verdict is the student's), and explain any step or finding when asked:
   screens and levels in `jlcdfm.en.md`, files and rotation in `files-and-formats.en.md`, SMT items in `references/jlcdfm-smt.md`.
   In the JLC assembly flow Component Placements view, check pin 1 mark and body outlines.
7. Triage each item. Real: outline on every layer, silk narrower than the JLC minimum, copper too near the edge, wrong
   footprint, a rotated part. Probably false: JLC DFM reads Gerbers with no nets, so same-net spacing, NPTH annular ring,
   connector slots, tiny mask dams and silk over tented vias are often by design. Prove "false" with a measurement or a
   datasheet, not with a guess.
8. Fix at the source: copper or silk in the board; rotation via the BOM line's `cpl_rotation` (bom.propose, multiple of 90); LCSC number
   in the BOM. Regenerate and re-upload. A re-uploaded CPL may be ignored by the preview: upload the Gerber zip again too.

9. The order step, after the Gerber zip and a clean DFM: action `order.check` (`"recheck": true` asks JLC again first).
   Its line says, per bought line, ok, swap_free, design_change or no_alternative. Design and ordering are separate: the
   design fixes value, package and pins and the library is built from it; at ordering the MPN or LCSC code may change
   FREELY when the new part has the same footprint (same land pattern and pins), with no schematic, library or board
   change. For a swap_free line propose `bom.propose` with `changes` `{mpn, lcsc, manufacturer, footprint_lock}` (the
   footprint name from the Order check panel), reason "order-only swap: same footprint". The server re-proves the
   footprint AND the pin functions (or value and kind of a plain passive) and drops the lock otherwise; the student still
   approves. After a swap Altium's own part parameters still show the old MPN/code until the next library build: the JLC
   BOM comes from the advisor's `export_bom`, never from Altium's BOM (order.check lists such lines in `params_stale`).
   A design_change line (other or unproven footprint)
   needs a library rebuild and a PCB update in Altium: say so, never present it as a plain swap. Export the BOM again after.

## Scripts
- `python <repo>/scripts/order_check.py <project> [--recheck]` per line: stock class and up to 3 alternatives with the footprint match.
- `python <repo>/scripts/skills/export_bom.py <project> jlc` writes the JLC BOM csv; lists lines left out and lines
  that need an LCSC number.
- `python <repo>/scripts/skills/export_cpl.py <project> [pcb_file]` writes `exports/<project>_cpl.csv` (JLC pick and place).
  Without a linked PcbDoc the positions are a stub from the BOM: say so.
- `python <repo>/scripts/skills/check_availability.py ...` stock and price from JLC, with query time. Quote the time.
- `python <repo>/scripts/outjob.py <project> [--out <dir>]` writes an Altium OutJob text file (Gerber, NC drill, JLC BOM, CPL, schematic PDF).
- `python <repo>/scripts/checks/board.py <pcb_file>` checks outline clearances, connector orientation, decap distances, and CPL rotation sanity.
- `python <repo>/scripts/dfm.py gerber-zip <project>` builds the Gerber + drill zip from the linked Altium outputs (read only); prints the files and gaps.
- `python <repo>/scripts/dfm.py pickup <project> [--kind pcb|smt|both] [--name FILE]` adds the new JLCDFM report PDFs from Downloads.
- `python <repo>/scripts/dfm.py ingest <project> <pdf_path> [--kind pcb|smt|both|auto]` ingests a PDF the student gave you by path.
- Never run Altium, never log in to JLC and never ask for the student's password.

## References
- `<repo>/shared/reference/course/ad20-essentials/m25-fabrication-files.en.md` (OutJob, BOM, Gerber setup)
- `<repo>/shared/reference/course/altium-education/unit3-pcb-layout.en.md` ([03] process, [06] Preparing for Manufacturing)
- `<repo>/docs/PRODUCT-PLAN.md` (section 8, export rules)
- `references/jlcdfm-report.md` - layout of the JLCDFM report PDF and how to triage its SMT section.
- `references/jlcdfm-smt.md` - JLCDFM SMT assembly DFM checks, common findings, fixes, and triage.
- `<repo>/shared/reference/jlc/files-and-formats.en.md` - JLC's Gerber/drill/BOM/CPL rules, rotation, rejections; order steps: `ordering-workflow.en.md`.
- `<repo>/shared/reference/jlc/jlcdfm.en.md` - JLCDFM screens, levels, known false reports; limits: `pcb-capabilities.en.md`, `assembly-capabilities.en.md`.

## Pitfalls
- Outline on every Gerber: it looks like a real copper fault at the edge. Check the plot list, not only the outline layer.
- JLC DFM has no netlist: most red items are same-net or deliberate. Triage one by one; do not "fix" a pad that is
  correct. Real faults seen: outline everywhere, silk too thin, pads and vias touching.
- CPL rotation: JLC 3D models are often 90 or 180 degrees off footprints built from other sources. Check pin 1 in the
  preview, only after the preview shows it turned, propose `cpl_rotation` on its BOM line; re-export the CPL, check the preview again.
- Do not "fix" through-hole offsets blind: a JLC model mismatch can show a hole error at the true centre.
- BOM lines can stay unselected even with an LCSC number: same number on two lines, a part with several types, or a
  difficult-part fee. The next button should not say unselected parts remain.
- Some modules (LGA) are Standard assembly only; a drop-in keeps the footprint, and the reason is written down.
- Stop at the quote. Never place the order or save to cart for the student.
- After any copper change near pads, re-run the PCB DFM: it checks same-net via to pad and mask opening to trace,
  Altium DRC does not.

## Output
Lead with the verdict in one line (ready to upload / N things to fix first). Pre-upload: only the rows that are a problem
or not checked, as `File | Problem | Fix`; what passed is one line with the count. DFM triage, one row per red item that
is real or uncertain: `Item | Where | Real? (why) | Fix`; items that are clearly false are one line together, with the
reason. Max 8 rows, the real ones first; when more are real or uncertain, add "N more to look at: see the DFM page" (the DFM page
holds the full table). Stock/price lines carry `JLC query <time>`. Cite
`{{src:<file>|<heading>}}`; say unknown for JLC limits you were not given. End with the one next step.
