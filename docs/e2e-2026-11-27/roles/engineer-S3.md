# Engineer review, Stage 3 (Library), system side in the browser

## Video highlights
- S3-10-j1-pins-tab.jpg | Green "Checked: nothing to verify", yet no pin of any part was ever verified.
- S3-08-j1-footprint-preview.jpg | Preview says "pitch 0.65 mm"; the USB-C signal pads are at 0.50 mm.
- S3-45-u1-ep-answer.jpg | Honest "No": cannot add EP vias or paste window. Every cited source checks out.
- S3-53-origin-3d-answer.jpg | Origin and 3D offsets: app admits only a manual Altium fix exists.

Scope: what the app showed and claimed (BOM page, part preview tabs, chat) and the data behind it
(library/manifest.json, library/easyeda/*/lib.kicad_sym and lib.pretty, library/build/*_spec.txt, bom.json, library-log,
turns-log, cites.json, ui/js/views/pages.js, scripts/model_preview.py). I did not judge the Altium files themselves
(Alti's job). Engine: Antigravity / Gemini.

## Verdict
The library content itself is good. Every footprint matches its BOM package. The IC symbol pin maps match the
datasheets: I checked STM32F411 against Table 8, all 48 pins plus EP, and LSM6DSO, BME280, W25Q128JV, LDL1117 and
USBLC6 against theirs. Connector pinouts follow the USB-C and microSD standards, and the custom-shaped USB-C GND and
VBUS pads survive conversion to Altium (0.6 x 1.3 mm in footprints_spec). What is wrong is what the page and the
agent tell the student about verification. The Pins tab shows a green "Checked" for parts whose pins nobody
checked; the preview computes a wrong pitch; and the agent cites a datasheet drawing for LED polarity that it had
no way to read.

## System findings

- [WRONG] The Pins tab says "Checked - Pins: nothing to verify for this part" (green) on parts whose pins were never
  checked (S3-10 J1, S3-21 Y1, S3-25 D3). The cause is in ui/js/views/pages.js:70-78 `libPinsState`: when
  `pins_status` is empty, the function falls through to `['ok', 'Pins: nothing to verify for this part']`, and
  `pins_status` is empty on all 30 lines (bom.json). The system's own data says the opposite: library_entry.verify
  is `unchecked` on U1-U5, F1, J1-J3, Y1, Y2, with reasons like "no pins of this part on a sheet to check" and
  "has no text to read (a scan?)". D3 and D4 carry "polarity of a diode/LED is confirmed by the student". So the
  same green "Checked" appears on the 49-pin STM32 symbol as on a resistor. On a part where a wrong pin map would
  kill the board, the student is told there is nothing to check. Fix direction: an empty status must read
  "Not checked yet (checked when the part is on the schematic)" in amber, and the page should show library_entry
  issues.
- [WRONG] The preview shows a wrong pad pitch. The J1 caption says "18 pads, pitch 0.65 mm" (S3-08), and the
  student recorded "pitch 0.65" as fact in K1 (student.md). The footprint file has the 8 signal pads at 0.50 mm
  (B8 -1.75, A5 -1.25 ... B5 +1.75; easyeda/C165948/lib.pretty), with the combined GND/VBUS pads at 0.65 and 0.8
  spacing. Cause: scripts/model_preview.py:239-248 `_pitch` takes the median nearest-neighbour distance (`mid =
  near[len(near)//2]`), while its docstring promises "the commonest". On mixed-pitch parts that gives a number that
  is no pad pitch at all. The same function snaps Y1's real 1.76 mm to "1.778 mm" (S3-19), a standard value the
  part does not have.
- [WRONG] The LED polarity claim cites a source the agent could not read. "Pin 1 is + (A), pin 2 - (K), matching the
  library {{src:KT-0805G.pdf|p. 2, Package Profile & Soldering PAD Suggested}}" (chat 02:30:01). The text of that
  page has no polarity mark (the polarity is only in the drawing; KT-0805G.pdf.txt page 2 is just headings and
  notes, and its quality file says "mostly Chinese ... state poor"). The turn's `read_file` on both LED PDFs
  returned `None` (turns-log 02:30:01). What the agent did read is the library symbol itself (C2297/lib.kicad_sym:
  A = 1, K = 2), so "matching the library" checks the library against itself. cites.json marks both citations
  `file_only` ("claim not compared"), but the chat shows them as sources. For the record, the library is
  self-consistent: pad 2 (K) is at -x and the silk triangle points at it. The real part's polarity remains
  unverified. The closing line "Confirm polarity before ordering" helps, but the citation should not be there.
- [FRICTION] The preview labels the fab/body outline "courtyard". Captions read "courtyard 3.2 x 2.5 mm" for Y1, whose
  pads span 3.6 x 2.96, and the same holds for D3, D4 and SW1 (C53, C55). The KiCad F.CrtYd is mapped to Mechanical 15
  and drawn as "courtyard" (model_preview.py LAYER_KIND). EasyEDA draws it at body size, so it is not an IPC
  courtyard. The agent's answer is TRUE ("placement uses pads (+0.25 mm)": layout.py:19 `COURT_MM = 0.25`,
  footprint_box(fp, margin=COURT_MM) builds pads + margin), but the page never says so. Rename it "body outline" or
  compute the courtyard the placer really uses.
- [FRICTION] Several symbols have numbers instead of pin names. D1 USBLC6-2SC6 has pins "1".."6"; the datasheet
  roles are I/O1, GND, I/O2, I/O2, VBUS, I/O1 (C7519/lib.kicad_sym). J3 SWD has "1".."10" (C52), and SW1, Y2, D2 and
  F1 are the same. For D1 that means the schematic stage must wire GND (2) and VBUS (5) by number only, which is
  exactly where a mix-up hides, and the Pins tab still shows green. The build should name the pins from the
  datasheet or flag the line.
- [FRICTION] 3D offsets: the build keeps (0,0,0) and only warns above 0.5 mm (manifest issues for J1 2.2 mm, J2 2.8 mm,
  J3 1.0 mm; agent 02:27 and 02:30 TRUE). The only remedy offered is "shift the PcbLib 3D offset in Altium by hand"
  (C57), outside the web UI. The likely cause is that the converter ignores EasyEDA's own model translation (my
  reading; I did not confirm it). It only affects the 3D view and STEP export, not copper, and the system should say
  that plainly.
- [COSMETIC] The preview puts the pin-1 marker on a USB-C shield tab ("1"), because the code takes the first pad named
  "1" or "A1" (model_preview.py:271). A USB-C receptacle has no pin 1, and the real A1 is the combined pad "A1B12".
- [COSMETIC] Symbol vs pad counts (C52): J1 has 16 pins vs 18 pads and J2 13 vs 15. In both, the difference is 2
  unnumbered NPTH locating holes (pads with empty number in the footprint files), so it is not an error. The preview
  should say "+2 NPTH holes".
- [COSMETIC] Source naming: the chat says "from EasyEDA" (manifest `source: easyeda`), while the preview says "Drawn
  from the KiCad footprint file of the part" (modelpreview.js:159). Both are true, because the EasyEDA part is
  converted through a .kicad_mod, but a student reads them as two sources (C56).
- [COSMETIC] The build banner (S3-06) mentions "a radio module's antenna area", which is generic text that does not
  apply to this board.
- [COSMETIC] The footprint name "LED0805-R-RD" for the green LED is not a red-LED footprint (C54). "-RD" is EasyEDA's
  orientation suffix, the same one used on D2 SOD-123F_...-RD. Only the naming confuses.

## Claims and data checked (TRUE)
- "None: all 30 BOM lines have a symbol, footprint and 3D model from EasyEDA (27 ok, 3 warnings)": matches
  library/manifest.json (30 entries, `source: easyeda`, `built: true`, 27 ok plus J1, J2, J3 warn with 2.2, 2.8 and
  1.0 mm).
- Footprint vs BOM package: all 30 consistent. Examples: U1 UFQFPN-48_L7.0-W7.0-P0.50 EP; U2 LGA-14 3.0 x 2.5 P0.50;
  U3 LGA-8 BME280; U4 SOIC-8 5.3 mm (208 mil); U5 SOT-223-4; D1 SOT-23-6; D2 SOD-123F; F1 1206; Y1 3225-4P;
  Y2 3215-2P; 0402, 0603 and 0805 passives as in the BOM.
- U1 symbol vs F411 Table 8 (UFQFPN48): pins 1-48 identical in name and number (VBAT 1, PC14/15 3/4, PH0/1 5/6,
  NRST 7, VSSA 8, VDDA 9, PA0-PA7 10-17, PB0-PB2 18-20, PB10 21, VCAP1 22, VSS/VDD 23/24, PB12-PB15 25-28, PA8-PA12
  29-33, PA13 34, VSS/VDD 35/36, PA14 37, PA15 38, PB3-PB7 39-43, BOOT0 44, PB8/9 45/46, VSS/VDD 47/48), plus EP 49
  "PAD". The EP net is for S4 to check.
- LSM6DSO symbol vs datasheet pin table (txt 214-286): 1 SDO/SA0, 2 SDx, 3 SCx, 4 INT1, 5 VDDIO, 6/7 GND, 8 VDD,
  9 INT2, 10 OCS_Aux, 11 SDO_Aux, 12 CS, 13 SCL, 14 SDA. Identical. BME280 1 GND, 2 CSB, 3 SDI, 4 SCK, 5 SDO, 6 VDDIO,
  7 GND, 8 VDD: identical. W25Q128JV SOIC-8 (/CS, DO, IO2, GND, DI, CLK, IO3, VCC) and LDL1117 (GND 1, VOUT 2, VIN 3,
  tab VOUT): correct.
- J1 TYPE-C-31-M-12 symbol: CC1 A5, CC2 B5, DP1 A6 / DN1 A7, DP2 B6 / DN2 B7, SBU1 A8 / SBU2 B8, VBUS A4B9 and B4A9,
  GND A1B12 and B1A12, shield EH 1-4. This is the USB-C 16-pin standard. The custom GND/VBUS pads (KiCad `custom`
  with gr_poly, 0.6 x 1.3 mm) are converted with real size: build/footprints_spec.txt:208, 210 "23.621 x 51.188 mil".
- J2 TF-01A: 1 DAT2, 2 CD/DAT3, 3 CMD, 4 VDD, 5 CLK, 6 VSS, 7 DAT0, 8 DAT1, 9 CD, 10-13 shell GND. This matches the
  microSD pinout.
- J3 2x5 1.27: odd pads in one row (y +1.95), even in the other, 1.27 mm pitch, 0.74 x 2.4 pads.
- Y1 footprint vs the JGHC S32 drawing (S3225000081040.pdf, which I read as an image): pad 1 at bottom-left (`-BL`),
  crystal on 1 and 3, GND on 2 and 4; pads 1.4 x 1.2 mm, 0.8 mm gap in x, matching the suggested layout. The y gap
  is 0.56 vs 0.5 mm, which does not matter.
- LED footprints: pad 1 = A at +x, pad 2 = K at -x, and the silk triangle tip points to pad 2. This agrees with the
  symbols (A = 1, K = 2). It is self-consistent, but the real part's polarity is unverified (see WRONG 3).
- Courtyard claim: TRUE (layout.py COURT_MM 0.25, footprint_box = pads + margin).
- verify_part on D3 and D4 returned "polarity of a diode/LED is confirmed by the student, not by text matching"
  (turns-log 02:28:54). That is honest, but the page shows green "Checked" anyway (WRONG 1).

## For S4 (carried)
EP 49 to GND; D1 USBLC6 pin roles by number (2 GND, 5 VBUS); J3 Cortex-debug pin assignment (1 VCC, 2 SWDIO,
4 SWCLK, 6 SWO, 10 nRESET, 3/5/9 GND); LSM6DSO CS pull-up and SDx/SCx to GND or VDDIO; BME280 CSB to VDDIO and SDO
strap; card-detect pin 9 and its pull-up.

---

# Round 2 (chat 02:45-02:57, student questions on U1 EP, U2/U3, J1, LED, 3D/origin/courtyard)

Checked against: F411 datasheet (text, Figure 49 p.124); shared/reference/jlc/assembly-capabilities.en.md A19 and
pcb-capabilities.en.md P1/P5; LSM6DSO datasheet p.6 (Figure 3, read as an image); TYPE-C-31-M-12.pdf (HRO drawing,
read as an image); library/easyeda/C165948/lib.pretty and library/build/footprints_spec.txt; scripts/altium/route.py,
scripts/jlc_preset.py; screens S3-37..S3-53; student.md "Answers to lecturer S3".

## Verdict (round 2)
The app was honest. Every time the student asked for a fix it could not make (EP paste window, thermal vias, 3D
rotation and offset, origin, courtyard), it said "No" plainly and named the manual Altium route. It did not claim a
change it had not made, and it did not offer an action that does not exist. The cited facts I could check are true:
the EP-to-GND quote, the JLC rules, LSM6DSO pin 1 in the bottom view, the J1 0.50 mm pitch (which corrects the
preview's 0.65 from round 1) and the J1 hole span. The weak spots are two pieces of advice. The first is "add thermal
vias in Altium", which collides with the system's own via-in-pad rule and was not needed. The second is a "fine
as-is" on the BME280 pads that rests on no source.

## System findings (round 2)

- [FRICTION] The advice to add EP thermal vias by hand in Altium (02:47:37, S3-45) does not mention that the system's
  own router and rules forbid via-in-pad: scripts/altium/route.py:1866 "via-in-pad is never allowed, whatever the
  net", jlc_preset.py:225 "No via in an SMD pad", and JLC P5 (no ink plugging on 4 layers, resin fill free only from
  6 layers, which the agent itself cited). Hand-placed vias in the EP would then be flagged by the system's own DRC
  and preset, or wick solder at assembly if left open. They are also not needed. U1 dissipates about 0.1 W
  (about 30 mA x 3.3 V), and ST asks only that the EP be soldered to ground (p.124), not for thermal vias. The
  honest "I cannot add vias" is right. The suggestion to do it by hand is the problem. Generic cause: the
  advisor's answer text is not checked against the project's own rule set.
- [FRICTION] The BME280 pads are called "fine as-is, or edit in PcbLib" (02:51:44, S3-47) without a source. The agent
  quoted library pads of 0.77 x 0.36 mm against Bosch's 0.50 x 0.35, which makes the library pads 54% longer than
  the maker's land pattern. "Fine" may well be true, since longer toes on LGA are common, but the answer gives no
  reason or citation for it. I could not open BME280.pdf (AES-encrypted; the system's text extract is what the
  agent read), so the Bosch figures themselves are unverified by me.
- [COSMETIC] The J1 slot answer (02:54:07, S3-49) compares the library's 0.80 x 1.50 and 0.80 x 1.20 slots with one
  drawing slot, "0.60 x 1.40". The HRO drawing has two slot sizes: 0.60 x 1.70 at the front (pad 0.90 x 2.00) and
  0.60 x 1.40 at the rear (pad 0.90 x 1.70). The library slots are 0.20 mm wider and 0.20 mm shorter than both. The
  tabs (about 1.10 and 0.80 long in the side view, as I read it) still fit with margin, so the conclusion "the tab
  fits" holds, but the comparison quoted only half the drawing.
- [COSMETIC] The J1 locating holes are "unplated 0.60" (TRUE for the Altium build: footprints_spec field 7 = 0, while
  the shield tabs are 1). The KiCad source has them as plated thru_hole pads with empty numbers, so the converter
  changes them. For plastic pegs, unplated is the right choice, and the drawing shows no plating. The converter
  should say so in the library log, so that nobody has to reverse-engineer it.

## Claims checked (round 2)
- TRUE: "EP is GND. Connect and solder to PCB ground" is quoted from Figure 49 note 3, p.124. I found it in the text
  (cite `ok`).
- TRUE: "I cannot add a paste window pattern or vias; the library build has no step for it" (honest). The library
  build has no paste-window or via step. A19 (JLC stencil from its own data) and P5/P1 are quoted correctly.
- TRUE: "U2 3D not turned; pin 1 is top-right in Figure 3" is correct, because Figure 3 of the LSM6DSO is a BOTTOM VIEW
  with pin 1 SDO/SA0 at top-right. The C2655100 footprint pads (top view) mirror it correctly. Whether the STEP
  model is rotated is unverified (Alti's side).
- TRUE: "J1 pitch 0.50 inner, 0.65 step to A4B9": the drawing gives 0.50 pitch with 8 x 0.30 pads and 4 x 0.60 outer
  pads, and the library matches (0.30 x 1.30 mm at 0.50). This answer contradicts the preview caption "pitch 0.65"
  (round-1 WRONG 2), which is still shown.
- TRUE: J1 hole span 5.80 vs drawing 5.78. The difference is 0.02 mm, inside the drawing's ±0.05 PCB-layout
  tolerance. The hole is 0.60 in both.
- TRUE (honest): "No, I cannot regenerate courtyards or 3D offsets; rebuilding overwrites the .PcbLib", which matches the
  build design (library build writes the whole PcbLib). It points to manual Altium editing, cited to the m27 PCB
  library guide 27.3.3.
- UNVERIFIED: the J1/J2 origin offsets of 1.42 and 2.32 mm and the 3D body offsets of +1.35 and +3.10 mm. They are
  plausible against the manifest 3D warnings (2.2 and 2.8 mm), but I did not measure them. Alti's side.
- LED cathode "on page 2": the student opened the drawing (S3-50, S3-51). Whether the agent read the drawing itself
  this time is not shown. Round-1 WRONG 3 (citation to text that has no polarity) stands for 02:30.

## Status of my round-1 findings
WRONG 1 (green "Checked" on the Pins tab) and WRONG 2 (median pitch in the preview) are unchanged in the UI. The agent's
chat answer now gives the right J1 pitch, but the page still shows 0.65. WRONG 3 is unchanged. The FRICTION items
(courtyard label, numeric pin names, 3D offsets only fixable in Altium) are unchanged, and the app now says honestly
that it cannot fix them.
