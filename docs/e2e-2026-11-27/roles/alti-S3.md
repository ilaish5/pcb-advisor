# ALTI - Stage 3 (Library in Altium)

## Video highlights
- alti/S3-footprints-2.png | J1/J2 3D bodies sit behind the contact rows, not at the mating edge.
- alti/S3-footprints-1.png | Yellow "courtyard" (Mech 15) lies inside the pads on every footprint.
- S3-32-agent-answer-courtyard-led.jpg | Agent honestly says Mech 15 is body size and placement uses pads+0.25.
- alti/S3-symbols.png | Good: U1, USB-C, ESD, LDO symbols match datasheet pin tables.

## Scope and method
Inspected the files the system wrote in `C:\Users\Public\Documents\Altium\Final-E2E-4L\Library\`
(SchLib 29 symbols, PcbLib 21 footprints incl. MECH_HOLE_3p2, IntLib, 3D folder 20 STEP) and the project
`Final-E2E-4L.PrjPcb` (IntLib is listed as Document, line 1158). Read-only: `dump.py` on SchLib/PcbLib
(`alti/schlib-dump.txt`, `alti/pcblib-full.txt`), the build spec `library/build/altium/*_spec.txt`, the EasyEDA sources
`library/easyeda/C*/`, and the datasheet text in `sources/`. The live Altium instance was not touched.
The PNG renders in `alti/` are drawn from the build spec. All 159 pads were cross-checked against the PcbLib dump
(name, x, y, size, rotation, layer, hole, plated) with 0 differences, so the spec is what Altium holds.
(The renderer draws every silk ARC as a full circle: the circles on F1206/LGA-8 are a render artifact, not library objects.)

## Findings

- [WRONG] J1 (USB-C) and J2 (microSD) 3D bodies are on the wrong side of the footprint. Evidence: the PcbLib body extent
  vs the footprint's own Mech 15 outline and front silk line. J1: body y -2.60..+5.30 mm, outline -5.09..+2.26 mm.
  J2: body y -4.40..+10.60 mm, outline -9.57..+4.93 mm. Each body reaches about 3 mm behind the contact row and stops
  2.5 to 5 mm short of the mating edge (render `alti/S3-footprints-2.png`). Whether it is an offset or a 180 degree turn
  is unverified. Why it matters: the 3D view, the STEP export and any enclosure check show the connector reversed or
  shifted. Credit: the system flagged it in `library/manifest.json` (J1 2.2 mm, J2 2.8 mm, J3 1.0 mm, "Built, check")
  and told the student. It still shipped the bodies as built, and the app cannot correct them ("fix in Altium by hand",
  S3-29). System cause: easyeda2kicad writes a 3D offset of 0,0,0 and `partlib_convert` takes it as is. The converter
  could take the offset from the body vs Mech 15 or silk outline, which it already measures for the warning.
- [WRONG] The library has no real courtyard. Mech 15, which the system maps from KiCad F.CrtYd
  (`scripts/partlib_convert.py:20`) and labels "courtyard" (`scripts/model_preview.py:26`), holds EasyEDA's body
  outline, and it lies inside the pads on all 20 footprints. Examples: C0402 pads +/-0.67 mm vs Mech 15 +/-0.50;
  SOT-223 pads x +/-4.06 vs +/-1.75; SOIC-8 pads y +/-4.65 vs +/-2.64; U1 pads +/-3.90 vs +/-3.50 (render
  `alti/S3-footprints-1.png`). Why it matters: anyone placing or checking by hand in Altium has no IPC courtyard.
  Only the system's own placer is protected, because it uses pads + 0.25 mm (`scripts/altium/layout.py:19`). The agent
  explained this correctly to the student (S3-32: "Mechanical Layer 15 shows body size... leave them"). System cause:
  EasyEDA's F.CrtYd is a body outline. The converter should generate the courtyard (pads + silk + body + 0.25 mm)
  instead of copying it.
- [WRONG] U1 exposed pad 49 is one 5.5 x 5.5 mm copper pad with no paste reduction: the build spec has no paste
  override, so Altium uses the default full opening. The same is true in the source kicad_mod (`easyeda/C60420`,
  pad 49 `F.Cu F.Paste F.Mask`). Why it matters: a solid 30 mm2 stencil opening under a 0.55 mm thick QFN is the classic
  cause of a floating part, bridging and voids. Common practice (IPC-7093) is a windowpane at about 50 to 80%.
  Unverified against ST's own land drawing (Figure 50 is an image), and paste/mask is not readable by `dump.py`.
  System cause: no rule for exposed-pad paste in `partlib_convert`.
- [COSMETIC] SW1/SW2 3D model height is 1.55 mm (STEP `KEY-SMD_4P-L5.2-W5.2-H1.5`), but the MPN is the 5.2x5.2x2.0H
  part. Enclosure checks would be off by 0.5 mm.
- [COSMETIC] The 0402/0603/0805 passive footprints (R0402, C0402, C0603, C0805) have no silkscreen in Altium,
  although the EasyEDA source has outlines. The silk-to-pad clearance clipping removes everything. This is acceptable
  on a dense board, noted only.
- [COSMETIC] Pin names that hide a function, to watch at S4. U1 pin 49 is named "PAD" (Power); DS10314 line 6697 says
  to connect the exposed pad to ground, so S4 must tie it to GND. W25Q128 pins 3 and 7 are named IO2 and IO3, without
  /WP and /HOLD or /RESET, so S4 must pull them high in plain SPI. USBLC6 and J3 have number-only pins
  (USBLC6 2 = GND, 5 = VBUS; SWD pinout is decided at S4).

## Watch notes for later stages
- S5: `checks/board.py` derives a connector's opening from the 3D body centre first. The placer
  (`layout.opening_guess`) uses the outline first: I ran it on this PcbLib and got 270 degrees (-y, correct) from
  "outline" for J1 and J2. With the bodies above, the board check and the placer may disagree on J1 and J2.
- S7: the J1 shield tabs are slots in the spec (hole_type 2, 0.8 x 1.5 and 0.8 x 1.2 mm), but `dump.py` shows only the
  round hole size. Verify the slots in the NC drill file. The 2 + 2 unnamed J1/J2 locating pegs are unplated holes
  (0.6 and 1.0 mm), which is correct.
- S7: U1's footprint is turned 90 degrees from the IPC zero orientation (pin 1 bottom-left, pins 1-12 along the
  bottom, counter-clockwise). Check the CPL rotation for U1 against JLC. The 3D pin-1 orientation of U1, D1 and U5
  is unverified (their bodies are symmetric boxes).

## What is correct (checked)
- All 30 BOM lines have a symbol and footprint. Symbol pin numbers equal footprint pad names on all 29 symbols (only the
  unnamed NPTH pegs of J1/J2 have no pin). MPN and LCSC parameters equal the BOM line and its LCSC code on all 30 lines.
- U1 STM32F411CEU6: the 49 pins match DS10314 Table 8, UFQFPN48 column (VCAP1 22, VSS 23/35/47, VDD 24/36/48,
  BOOT0 44, VSSA 8, VDDA 9). Pitch 0.50 mm, pads 0.28 x 0.90 mm, numbering counter-clockwise, pin-1 marker by pad 1.
  The EP land of 5.5 mm fits D2/E2 of 5.6 mm typical.
- U3 BME280: the land pattern numbers pins clockwise in top view, exactly as the datasheet's note says (line 2233).
  The pad rotation of 90 degrees survived into Altium (0.767 x 0.364 mm at 0.65 mm pitch, no overlap).
- U2 LSM6DSO LGA-14 (1-4 left, CCW, 0.5 pitch), U4 W25Q128 SOIC-8 208 mil (CCW), U5 LDL1117 SOT-223
  (GND 1, VOUT 2, VIN 3, tab VOUT, not mirrored), and D1 USBLC6 SOT-23-6 pin order match their datasheets.
- J1 TYPE-C-31-M-12 signal row order: A1B12, A4B9, B8, A5, B7, A6, A7, B6, A8, B5, B4A9, B1A12, plus 4 plated shell
  tabs. The CC, DP and DN assignment is correct.
- D3/D4 LEDs and D2 TVS: the cathode is consistent between symbol (bar side) and footprint (silk chamfer/triangle on
  the same pad). Y1: OSC on the diagonal 1/3, GND 2/4.
- 3D heights match the packages (U1 0.61, BME280 0.94, SOIC-8 2.07, USB-C 3.25, header 5.5 mm), except SW above.

## Unverified (no readable datasheet text)
J1, J2 and Y1 datasheets are scans or vector-only. The LED datasheets give no polarity text, and SW1 has no datasheet
in Sources. For these, the parts are consistent with the EasyEDA/LCSC source and the microSD/USB-C standard pinout,
not checked against the datasheet.
