# ALTI - Stage 7 (Outputs from Altium)

## Video highlights
- alti/S7-gerber-top.png | Gerbers from the zip match route #3: 60x45, 4 copper layers, M3 holes.
- alti/S7-gerber-bottom-paste.png | U1 exposed pad gets one 5.5 mm paste opening: S3 defect now in fab data.
- alti/S7-gerber-inner.png | Mid-1 GND and Mid-2 +3V3 pours are real copper in G1/G2.
- (no image) | CPL puts U5 0.66 mm off its body centre; Altium's own Pick Place disagrees.

## Scope and method
Read-only. I looked at `C:\...\Final-E2E-4L\Project Outputs for Final-E2E-4L\` (OutJob run 07:23:10, the log says 21
files) and `projects/Final-E2E-4L/exports/` (gerbers.zip 07:24:37, order_manifest, BOM_jlc.csv, cpl.csv). The zip
was unpacked into `alti/S7-zip/` and parsed with the repo's `gerber_check.parse_excellon/parse_gerber_extent`. I
rendered it with my own small Gerber/Excellon rasteriser (PIL; C/R/O apertures, G36 regions, arcs). The CPL was
compared with the PcbDoc of route #3 (`alti/S6p5-pcbdoc.json`) and with Altium's own Pick Place file. Numbers are in
`alti/S7-analysis.txt`. No Altium command was run.

## Findings

- [WRONG] The CPL uses pad centres, not the part centre. `scripts/skills/export_cpl.py` writes "Mid = the centre of
  the part's pads". For U5 (SOT-223) the big tab pulls that point 0.655 mm off: the CPL says (43.000, 43.345). The
  footprint origin, the 3D body centre and Altium's own Pick Place "Center" all say (43.000, 44.000). For J1 the CPL is
  0.150 mm from the footprint origin (30.84 vs 30.99). For J2 it is 0.245 mm off (75.56 vs 75.315), and Altium's own file says
  75.46. All other 52 parts agree within 0.05 mm. Why it matters: the footprints come from EasyEDA/LCSC, whose
  origin is the point JLC's own models are centred on. A 0.66 mm shift of a SOT-223 shows up as a misplaced part in
  JLC's preview, or as a placement error if nobody corrects it. Lecturer condition L3 (J1/J2 origin) is met only
  to 0.15-0.25 mm. Generic cause: the pad-centroid rule in `export_cpl.py`. Its own docstring says it was tuned on one
  board (148/149 parts), and asymmetric packages (SOT-223, DPAK, connectors with shell tabs) break it.
- [WRONG] The exposed-pad paste is a full opening in the fab data. GTP flashes aperture D38 `R 0.2165 x 0.2165 in`
  (5.50 x 5.50 mm) at U1's centre (54.0, 41.5) (`alti/S7-gerber-bottom-paste.png`). This is the S3 finding, now in
  the stencil file. IPC-7093 practice is a windowpane at 50-80 %, to avoid a floating or bridged QFN. There is no
  paste rule in the board or the library (PasteMaskExpansion 0 mil for all).
- [WRONG] The S6 real issues are faithfully in the Gerbers.
  - Every via has a mask opening on both sides: GTS has 391 flashes and GBS 169, which includes the 157 vias. So they ship untented.
  - In G1 and G2 the pours come to about 0.16 mm from the four 3.2 mm M3 holes (`alti/S7-gerber-inner.png`).
  - Signals run under Y1 and Y2.
  None of these is an output error: the outputs match the board. They are listed so that S8 does not order them unseen.
- [FRICTION] Nothing in the exports carries the stack-up. `order_manifest.json` holds only verification data
  (warning, accepted risks, unverified U1, board_check). There is no layer count, thickness or "JLC04161H". The PcbDoc
  stack is still Altium's 1.10 mm default (S5). The layer count is clear from G1/G2, but the 1.6 mm JLC04161H
  stack has to be picked by hand on the order form at S8.
- [FRICTION] CPL rotations are the PcbDoc rotations unchanged for all 55 parts (no `cpl_rotation` offsets set). This is
  right only if every converted footprint kept EasyEDA's zero orientation (likely, since the source is EasyEDA). It is
  unverified until JLC's 3D preview, especially for U1 (S3: pins 1-12 along the bottom), J1 (270 deg), J2 (90 deg),
  U5 (90 deg) and Y1 (270 deg).
- [FRICTION] C10 and C11 are the same part (4.7 uF 0603, C19666) on two BOM lines, because their roles differ (VCAP1 /
  MCU bulk). JLC's BOM tool groups by part, so it may flag or merge them. Grouping by LCSC number with the roles in a
  note is the usual form.
- [COSMETIC] The Gerbers and the drill files are inch 2:4 (Altium's default, 2.54 um resolution). JLC accepts this.
  Metric 4:6, or inch 2:5, is the more usual choice for 0.5 mm pitch parts. The units are consistent across all files.

## What is correct (checked)
- **Layer set and extensions as JLC expects for Altium:** GTL, G1, G2 and GBL (Layer_Physical_Order 1-4), GTO/GBO,
  GTS/GBS, GTP/GBP, and GM1 as the outline. Three Excellon files: plated round, plated slots and non-plated. All share
  `TF.SameCoordinates` and Board_Origin 0|0. Reports, apertures and the drill drawing stay out of the zip.
- **Outline:** GM1 extent is 60.000 x 45.001 mm. The inner pours are 59.38 x 44.38 mm (0.3 mm back from the edge).
- **Drill = PcbDoc route #3:** 157 plated 0.305 mm (vias, 157 in the PcbDoc), 4 plated 0.8 mm slots (J1 shell),
  non-plated 4 x 3.2 mm (M3, H1-H4), 2 x 0.6 mm (J1 pegs) and 2 x 1.0 mm (J2 pegs). They are INCH, LZ, 2:4, the same
  units as the Gerbers.
- **Not stale:** the Gerbers were written 07:23:06, after the PcbDoc save at 07:12:58. The manifest's pcb_sha256
  `30f07740...` equals the current file's SHA-256. The via count and the rendered copper match route #3.
- **BOM:** 31 lines and 55 designators. That includes R15 from S4 round 2, so it is 55, not 54. Every line has an LCSC
  C-number, there are no duplicate designators, and every placed part is in it (H1-H4 correctly left out). The exports
  copy is identical to Altium's `BOM/Final-E2E-4L_BOM_jlc.csv`.
- **CPL:** 55 rows, all Top, in the same absolute origin as the Gerbers (board 25.4..85.4 mm). H1-H4 are excluded.
  Only U5, J1 and J2 are off, as above.
- Bottom silk and paste are empty (no bottom parts). Top silk holds the designators and outlines.
