# JLCPCB file requirements: Gerber, drill, BOM, CPL (pick and place), stencil

> Source: JLCPCB help-center articles and JLC's own sample BOM/CPL spreadsheets in the table below, all read 2026-10-14. Condensed to the rules; screenshots are not reproduced (their captions are only cited when the text says the same). Other EDA tools (KiCad, Eagle, Proteus, ORCAD) trimmed except where a rule is general. Altium menu names are JLC's (Altium Designer 24-26).

Covers: the upload archive, Gerber format and layer names, the board outline layer, NC drill files, JLC's Altium export settings, the BOM
and CPL formats, rotation and origin problems, stencil/paste files, and what JLC's checker or CAM rejects or silently changes.
Capabilities: `pcb-capabilities.en.md`. Ordering steps: `ordering-workflow.en.md`.

## Sources
All read 2026-10-14. "Page date" is the "Last updated" stamp on the page.

| ID | Page | URL | Page date |
|---|---|---|---|
| F1 | How to Generate Gerber Files in Altium Designer 26 | https://jlcpcb.com/help/article/how-to-export-altium-pcb-to-gerber-files | 2026-09-28 |
| F2 | How to export PCB to gerber files in Altium24 | https://jlcpcb.com/help/article/how-to-export-pcb-to-gerber-files-in-altium24 | 2026-09-09 |
| F3 | How to Prepare Gerber Files Before Placing Orders? | https://jlcpcb.com/help/article/gerber-files-preparation | 2026-09-09 |
| F4 | Suggested Naming Patterns | https://jlcpcb.com/help/article/suggested-naming-patterns | 2026-09-09 |
| F5 | Misidentified Layers - Why Not Follow Gerber X2 Standards | https://jlcpcb.com/help/article/misidentified-layers-why-not-follow-gerber-x2-standards | 2024-08-09 |
| F6 | Manually Adding Tool List for a Drill File | https://jlcpcb.com/help/article/manually-adding-tool-list-for-a-drill-file | 2025-04-24 |
| F7 | DFM Drill Layer Format Adjustment | https://jlcpcb.com/help/article/dfm-drill-layer-format-adjustment | 2025-04-24 |
| F8 | Why Are Drill Holes Not Aligned with the Copper Layer? | https://jlcpcb.com/help/article/why-are-drill-holes-not-aligned-with-the-copper-layer | 2024-06-24 |
| F9 | Ordering Instructions for PCB Manufacturing | https://jlcpcb.com/help/article/instructions-for-ordering | 2026-09-09 |
| F10 | Bill of Materials (BOM) File for PCB Assembly | https://jlcpcb.com/help/article/bill-of-materials-for-pcb-assembly | 2026-09-09 |
| F11 | Pick & Place File for PCB Assembly | https://jlcpcb.com/help/article/pick-place-file-for-pcb-assembly | 2026-09-09 |
| F12 | Recommendations for BOM / CPL File Preparation | https://jlcpcb.com/help/article/advice-for-bom-and-cpl-files-preparation | 2026-09-09 |
| F13 | Common BOM / CPL Matching Issues and Explanations | https://jlcpcb.com/help/article/common-bom-and-cpl-matching-issues-and-explanations | 2026-09-09 |
| F14 | How to generate BOM and Centroid File from Altium | https://jlcpcb.com/help/article/how-to-generate-bill-of-materials-and-centroid-file-from-altium | 2026-09-09 |
| F15 | JLC sample BOM (linked from F10) | https://s3.amazonaws.com/helpscout.net/docs/assets/59f1de7804286313cffbb22c/attachments/60ee4acd9e87cb3d0124d284/Sample-BOM_JLCSMT.xlsx | file |
| F16 | JLC sample CPL (linked from F11) | https://s3.amazonaws.com/helpscout.net/docs/assets/59f1de7804286313cffbb22c/attachments/5d83250e04286364bc8f4c5e/Sample-CPL_JLCSMT.xlsx | file |
| F17 | PCB Assembly FAQ (Part 2) | https://jlcpcb.com/help/article/pcb-assembly-faqs-part-2 | 2026-09-09 |
| F18 | Instructions for Stencil order | https://jlcpcb.com/help/article/instructions-for-stencil-order | 2026-07-13 |
| F19 | In what cases will there be charged extra? (stencil part) | https://jlcpcb.com/help/article/in-what-cases-will-there-be-charged-extra | 2026-09-09 |
| F20 | Common Mistakes When Using Altium Designer | https://jlcpcb.com/help/article/common-mistakes-when-using-altium-designer | 2026-09-09 |
| F21 | Common Compatibility Issues with Altium Designer and PADS | https://jlcpcb.com/help/article/common-compatibility-issues-with-altium-designer-and-pads-software | 2025-04-24 |
| F22 | JLC cart File Manager (older upload page) | https://cart.jlcpcb.com/client/template/mine/fileManager.html | none shown |
| F23 | JLCDFM home | https://jlcdfm.com/ | none shown |
| F24 | How Is SMT Stencil Data Prepared for JLCPCB SMT Orders? | https://jlcpcb.com/help/article/smt-stencil-data-prepared-for-smt-orders | 2026-09-09 |
| F25 | Difference and Tolerance Between Via and Pad Holes | https://jlcpcb.com/help/article/difference-and-tolerance-explanation-between-via-and-pad-holes | 2025-04-24 |

## The upload archive
- One .zip or .rar, files at the top level, no nested folder [F1]. Size: JLCDFM takes up to 50 MB [F23]; the older cart file manager says
  "Only accept zip or rar, Max 10 M" [F22]; the limit of the current quote page was not found.
- The board is built from the Gerber files only: notes, PDF, DXF or Excel in the archive are ignored (put what matters in the remark). If
  the archive holds both a PCB design file and Gerbers, the Gerbers are used [F9 #2, #3].
- Extra layers (via-fill "sk" layer, stiffener, heatsink pads, a second GM layer) need a remark saying what they are, or they may be
  ignored [F3]. Export the Gerbers from the same Altium version the board was designed in [F21].
- A drill map / drill drawing is "highly recommended" so hole positions and attributes can be checked [F3, F4].

## Gerber format and layer names
- Format: RS-274X (extended Gerber with embedded apertures). In Altium use File > Fabrication Outputs > Gerber Files, not Gerber X2 Files;
  X2 output "may be rejected at CAM review" [F1]. JLC's DFM reads X2 layer attributes before the file name, so a mislabelled X2 set is
  misidentified (all files as copper, for example); this also applies to RS-274X files that carry X2 attributes as G04 comments [F5].
- Names Altium produces (Protel extensions) are read directly [F1, F4]:

| Layer | Altium extension | JLC suggested name [F3, F4] |
|---|---|---|
| Top / bottom copper | .GTL / .GBL | same |
| Inner copper (4+ layers) | .G1, .G2 ... (signal); GP1/GP2 negative planes are not looked for | .G2L, .G3L |
| Top / bottom silkscreen | .GTO / .GBO | same |
| Top / bottom solder mask | .GTS / .GBS | same |
| Top / bottom paste | .GTP / .GBP | (stencil) |
| Board outline | .GM (mechanical) or .GKO (keep-out; only if no GM outline is plotted) | .GKO or .GM1 |
| NC drill | .TXT (Excellon), PTH and NPTH files | .XLN |

- Altium's drill files end in .TXT; several .TXT files can raise "Drill files have been merged", which can generally be ignored [F4].
- Plane layers: JLC's site does not look for GP1/GP2 files, "typically generated as 'negative' polarity gerbers which our system may not
  process correctly" [F4]. (Advisor's note: with Altium plane layers, check the inner layers in the production file.)
- Board outline rules (which layer JLC picks, slots and V-cuts on the outline layer, 0.15 mm line width): `pcb-capabilities.en.md` §
  "Outline, board size and thickness". Keep one outline layer only [F3, F9 #12].

## JLC's Altium Gerber and drill recipe [F1 unless noted]
Applies to Altium Designer 24, 25 and 26 (written on 26.1.1).
- Gerber Setup, General: Units Millimeters; Decimal 0.0001 mm (4:4); output file names "FileName.Extension"; "Include unconnected mid-layer
  pads" ticked; "Generate Reports" ticked; "Merge regions and pads inside Footprint" unticked.
- Layers to plot: Board Outline (.GM), Top/Bottom Layer, Top/Bottom Overlay, Top/Bottom Solder, Top/Bottom Paste (plus inner layers).
- Advanced: aperture tolerances +/-0.00013 mm; suppress leading zeroes; plotter type Unsorted (raster); "Optimize change location
  commands" ticked; "Use software arcs" unticked (true arcs). Then check the result in CAMtastic and close it without saving.
- NC Drill Setup: Units Inches; Format 2:5; keep leading and trailing zeroes; "Reference to absolute origin"; "Optimize change location
  commands" ticked; separate files for plated and non-plated holes ticked; separate files for via features unticked. The output is three
  drill files plus a report.
- Gerbers in mm with the drill in inches is safe: every Excellon file declares its own units and format in its header [F1].
- The older Altium 24 article sets the drill precision to 2:4, plots "Select Used", and includes drill drawing and drill guide [F2]. It also
  offers a customer-made "JLCPCB Milti_Layer Rules.rul" (sic) and 4/6-layer stack-up files that JLC says are "not exhaustively validated" [F2].
- Output goes to "Project Outputs for <ProjectName>" next to the .PrjPcb; zip those files flat [F1].
- The Gerber position setting (relative or absolute origin) is not stated in F1 (gap): keep Gerber and drill on the same origin and check
  the drill hits against the pads in a viewer.

## NC drill files [F6, F7, F8]
- JLC expects a self-contained Excellon file: header (M48) with units, zero suppression and the tool list (T1C0.45...). Missing header, tool
  list, units or zero mode are the common faults; the article shows how to add a tool list by hand [F6].
- Excellon 2 is assumed. An Excellon 1 file read as Excellon 2 gives wrong (extra) holes: say so in a remark [F6].
- JLC's DFM guesses missing format data and is right "in 99% of cases"; when holes appear shrunk into a corner or spread past the board,
  fix it in JLCDFM with Drill Format (absolute/relative, leading/trailing zero, digits, metric/imperial) [F7].
- Alignment of drills to copper needs pads drawn as single flashed objects (about 80 % of pads is enough; round via pads usually suffice);
  boards with only NPTH holes, or pads made of line segments, may not align [F8].
- Plated slots must be in the drill data with the holes; non-plated slots on the outline layer [F9 #7]. Drill bits are metric: design hole
  sizes in mm with one decimal (32 mil = 0.812 mm is drilled 0.8 mm) [F25].

## BOM format
- Required columns: Comment (value, tolerance, voltage...), Designator (R1, C100...), Footprint (0402, SSOP-8...). File types .csv, .xls,
  .xlsx [F10].
- JLC's sample header: `Comment | Designator | Footprint | JLCPCB Part #（optional）`, with the part number as a C-code (C16133) and
  several designators in one cell (`R5,R6`) [F15]. JLC's Altium article adds an Altium parameter "LCSC Part #" to each library part and
  includes it as a BOM column [F14]. A matched part can always be searched by MPN or C-code on the matching page [F13].
- Designators are upper-cased for production: never tell two parts apart by letter case only [F10]; BOM and CPL must use the same case
  ("R1" is not "r1"), or the part lands in "Unselected Parts" [F12].
- At most 200 designators per BOM line; each designator once in the whole BOM; use standard prefixes (C capacitors, R resistors) [F12].
- Remove Excel's green error triangles; if problems persist paste the data into a fresh sheet [F12].
- The matching page unticks and flags (yellow mark) a line when: the matched model does not exactly equal the BOM model (case and spaces
  ignored), the package differs, the same part is matched on several rows, or one row mixes component types (by designator prefix) [F13].

## CPL (pick and place) format
- Columns: Designator, Mid X, Mid Y, Layer, Rotation. Mid X/Y = component centroid, units mm (required); Layer = Top/Bottom; Rotation in
  degrees, positive counter-clockwise. File types .csv, .xls, .xlsx [F11].
- JLC's sample: `Designator | Mid X | Mid Y | Layer | Rotation`, values like `95.0518mm`, Layer `T` or `B`, rotation `270` [F16].
- One CPL for both sides, Layer as T/B or Top/Bottom; all coordinates in one unit; different designators > 0.2 mm apart [F12, F13].
- Only designators that appear in both BOM and CPL are recognised; on a mismatch the upload asks to Continue (leave them unplaced) or
  re-upload [F12, F13].
- Rename column headers to JLC's field names if your tool writes others [F12]. Whether JLC's parser also accepts Altium's default Pick and
  Place headers is not stated in the pages read (gap).
- Panelized orders: choose "Single Piece, please help me repeat the data" for a one-board BOM/CPL, or "Complete File, just proceed with my
  own files" if the files already describe the panel [F13].

## Rotation and origin problems
- JLC's 0 degrees: "Zero orientation for PCB library should match the component orientation in the packaging (tape/reel)". Datasheets or
  the maker's tape-and-reel document show it; the same package can sit differently in the tape for different parts [F17 #3].
- Your 0 degrees can differ from JLC's while the direction of rotation is the same, so some parts show turned in the placement preview. Fix
  the rotation in the CPL, or place the order and JLC engineers fix rotation and polarity from the silkscreen [F17 #2].
- When the silkscreen polarity mark and the CPL disagree, JLC places by the silkscreen [F17 #10]. Without a silkscreen mark JLC asks by
  email (delay) [F17 #10]. Mark diodes with a cathode bar or a triangle [F17 #10].
- In the preview the red dot is an orientation mark, not "pin 1"; it should meet the dot on the PCB silkscreen [F17 #1]. In DFM views "+"
  is the anode of a diode or polarised capacitor, "-" the cathode [F17 #8].
- Not documented in the pages read (gaps): how bottom-side rotations are expected (mirrored or not), and which origin the CPL coordinates
  must use relative to the Gerbers.

## Stencil and paste files
- Stencil orders follow the paste layer when present; pads in mask but not in paste raise an engineering question unless the remark says
  "Please follow the solder paste layer only..." [F18 #2]. IC, BGA and 0805-and-larger apertures get JLC's standard processing unless the
  remark asks for 1:1 [F18 #1].
- Stencil thickness free: 0.10, 0.12, 0.15, 0.18, 0.20 mm; 0.03-0.08 and 0.25-0.5 mm at extra cost [F18 #3]. Fiducials on the stencil:
  choose "Etched Through" or "Etched Half" and include them in the file [F18 #6]. More than 5000 apertures: +$1.5 per 1000 [F19].
- On an assembly order JLC generates the stencil from its own SMT data, not from your paste layer, and only for the parts selected [F24].

## What JLC rejects or changes
| Situation | What happens | Src |
|---|---|---|
| No outline or no drill file | order cancelled (remark if the board truly has no holes) | F9 |
| Design beyond the capabilities | order cancelled, reason by email | F9 |
| Mask layer missing or empty | whole board covered in mask | F9 #19 |
| Silkscreen over a mask opening or exposed copper | silk dropped unless the remark asks | F9 #9, F20 |
| Text thinner than 0.15 mm | may be widened to 0.15 mm | F9 #9 |
| Several outline layers | GM preferred, lowest GM number used, others ignored | F9 #12 |
| Slots, V-cuts, cutouts not on the outline layer | missed | F9 #7 |
| Several hole sizes drawn in the outline layer | smallest size drilled | F20 |
| X2 attributes wrong | layers misidentified | F5 |
| Extra layers without a remark (sk, stiffener, extra GM...) | may be ignored | F3 |
| The website Gerber viewer | preview only, may not show the file exactly | F9 #8 |

Altium mistakes JLC lists [F20]: "Plated" unticked on a hole (it becomes NPTH); slots drawn on Drill Guide / Drill Drawing layers (not
output); slot length and width swapped; text on copper; thermal reliefs on close pads; zero-size top/bottom pads (keep the PTH ring > 0.18 mm);
slots and outline on different mechanical layers; board cutouts only in the 3D view; a negative mask expansion.

## Conflicts between JLC sources
| Topic | One source | The other | Satisfies both (advisor's reading) |
|---|---|---|---|
| Gerber X2 | F1 (2026): use Gerber Files, not X2; X2 "may be rejected at CAM review" | F5 (2024): X2 is the coming standard; either output correct X2 attributes or RS-274X | RS-274X |
| Drill format in Altium | F1 (AD26): inches 2:5, keep leading and trailing zeroes, absolute origin | F2 (AD24): precision 2:4, other settings left default | either works when the header declares the format; check the hits against the pads |
| BOM part-number column | F15 sample: "JLCPCB Part #（optional）" | F14: parameter and column "LCSC Part #" | both are JLC's; the column is optional, the C-code in it is what matches |
| Board outline layer | F1: .GM, use .GKO only if no GM is plotted | F3: keep only one GKO, delete other GM layers; F4: GKO or GM1 | exactly one outline layer, whichever name |
| CPL Layer values | F11: Top / Bottom | F16 sample: T / B | F12 accepts both |
