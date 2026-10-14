# The JLCDFM report PDF (jlcdfm.com, "DFM analysis report_JLCDFM_<gerber zip>.pdf")

## Shape
- ONE very tall page; the whole report is a single embedded JPEG (about 2400 x 15000 px). There is NO text layer:
  `pdftotext` returns nothing. Read it as images: extract the JPEG, cut it into slices of about 1400 px height, read
  each slice. Never ask the student to retype it.
- Header: file name (the Gerber zip), generation time, PCB layers, PCB size, which analyses ran (PCB DFM, SMT DFM),
  then three board renders (copper, top, bottom).
- Sections, each a table: `PCB DFM>Routing layer analysis`, `PCB DFM>Soldermask layer analysis`,
  `PCB DFM>Silkscreen layer analysis`, `PCB DFM>Drill layer analysis`, `SMT DFM>Component assembly analysis`.
- Columns: `Analyze project` (check name + one-line description) | `Analysis results` (the WORST value + level
  Danger / Warning / Good, or `No` = nothing to check, `null` = no number) | `PCB screenshot` (one crop of the worst
  case only) | `Layer distribution` (Gerber/drill file names, or `component_+_top` in SMT) | `Statistics`
  (Danger: n, Warning: n, Good: n).

## Reading it
- Only the worst case of each check is shown, with no designator in text. Find the part from the silkscreen in the
  crop, or ask the student to open the same check in the online JLCDFM viewer and click through the items.
- The same check name can appear in several rows (e.g. "Component through-hole", "Unconnected via"): different
  sub-checks or layers. Keep them as separate rows.
- Triage by Statistics, not by the headline: a row with Danger 0 / Warning 1 is one item to look at.
- Spelling in the report is JLC's (e.g. "Coponent pad spacing"); quote it as written.

## SMT section: what usually is real and what is usually the model
- Pin left / right / inner / outer edge, "Pin without pad", "Lead area overlapping pad" with tens of Danger items are
  usually JLC's own 3D/lead model not matching the footprint (rotation, wrong package variant, or offset), not a
  copper fault. Check the rotation in the SMT preview first; then compare the package variant with the datasheet.
  A few items on one part (e.g. 2 outer-edge, 5 overlap on an SC-70/SOT part) = check that footprint's pad length.
- "Component collision" Danger: a real overlap of two bodies/courtyards, or a tall through-hole body model. Look at
  the crop and the 3D view in Altium before moving parts.
- "Component to board edge" Warning below about 0.6 mm: real for edge connectors only if the plug must clear the edge.
- "Component through-hole" misalignment with negative values: JLC model vs hole centre; do not move a correct hole.

## Output
A triage table: `Section | Check | Worst value | D/W/G counts | Real / model / by design / unknown | Fix | Evidence`.
