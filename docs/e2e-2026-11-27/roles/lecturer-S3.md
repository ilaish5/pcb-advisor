# Lecturer – Stage 3 (Component library)

## Video highlights
- S3-10-j1-pins-tab.jpg | Green "Checked – nothing to verify" on a USB-C whose datasheet is an unreadable scan.
- S3-45-u1-ep-answer.jpg | EP = GND with a quoted datasheet note; the tool admits it cannot add a paste window or vias.
- S3-53-origin-3d-answer.jpg | J1/J2 origin is 1.4/2.3 mm off the body, so the JLC CPL centroid would be wrong.
- S3-51-led-package-drawing-zoom.png | The student confirms the LED cathode by eye on the datasheet drawing.
- S3-36-bom-final.jpg | Lecturer round 1: FIX. MCU and LGA footprints never reviewed; J1 holes and LED polarity unverified.
- S3-53-origin-3d-answer.jpg | Lecturer round 2: PASS with conditions. The library defects the tool cannot fix are carried to placement and outputs.

# Round 1

Evidence: `roles/student.md` (S3), confusions C49–C59, `screens/S3-01..36`, `library/manifest.json`, `library/easyeda/*/lib.kicad_sym` and
`lib.pretty/*.kicad_mod` (the source files the PcbLib was built from), `bom.json` `library_entry`, and `sources/STM32F411CEU6.pdf.txt` Table 8.
I checked the U1 pins and the key footprints myself. I did not look at the Altium PcbLib (that is Alti's job), so any statement about the Altium copy is marked unverified.

## What is good
- You did go through the K1 list, part by part: J1, J2, J3, Y1, D3/D4, SW1/2, with a screenshot of every tab.
- **J1 pad order is correct** against the USB-C receptacle standard: A1B12, A4B9, B8, A5, B7, A6, A7, B6, A8, B5, B4A9, B1A12. CC1 = A5, CC2 = B5.
- **J2 pin numbering is correct** for microSD (1 DAT2 … 8 DAT1, 9 CD), and the pitch in the file is 1.1 mm as the standard requires.
- **Y1** 1/3 = crystal and 2/4 = GND agree between symbol and footprint.
- You admitted plainly that the dimensions were **not** verified (S3-34/35). An honest "unverified" beats a fake "checked".
- You found the systematic courtyard defect yourself (4 of 4 small parts).

## Questions you must answer (round 1)
1. **You never opened U1, the most important part.** I did. Symbol pins 1–48 match Table 8: VBAT 1, NRST 7, VSSA 8, VDDA 9,
   VCAP1 22, VSS/VDD 23/24, 35/36 and 47/48, BOOT0 44. The footprint numbering runs counter-clockwise with 0.5 mm pitch. But **pin 49 is named "PAD"**, not VSS.
   Which net does the exposed pad go to, and which line of the datasheet says so? The EP is a **5.5 × 5.5 mm solid paste** opening with **no thermal
   vias** (`C60420/…EP.kicad_mod:69`). What is your paste-window and via plan for JLC reflow, so the QFN does not float and bridge?
2. **U2 (LSM6DSO) and U3 (BME280) are LGA: no leads, no visual inspection, no hand rework. You did not open either.** The U2 footprint is
   named `LGA-14_L3.0-W2.5` but its 3D model is `L2.5-W3.0`. Is the model rotated 90° against the pads? Where is pin 1 against the datasheet's "pin connections"
   figure? The BME280 pads are 0.364 × 0.767 mm at 0.65 mm pitch. Do they match Bosch's recommended land pattern?
3. **J1 dimensions.** You wrote "pitch 0.65". The file says **0.5 mm** (8 inner pads, 0.3 mm wide). You wrote "2 NPTH", but in the source
   footprint the two locating holes are **plated, 0.6 mm drill in a 0.6 mm pad, so a zero annular ring** (`C165948/…kicad_mod:66-67`). What did Altium
   get, and what will JLC's DFM do with it? The shield slots are 0.8 × 1.2 and 0.8 × 1.5 mm. Do they fit the TYPE-C-31-M-12 legs? If the LCSC scan cannot be read,
   where will you get a readable drawing or an independent second footprint?
4. **LED polarity.** Symbol and footprint agree with each other (A = 1, K = 2, silk triangle at pad 2), but nothing ties them to the **real**
   KT-0805G / KT-0603R cathode mark. The LED datasheets are attached "file only, not verified", and the green LED footprint is called `LED0805-R-RD`.
   Which page shows the cathode? JLC orients LEDs by your footprint, so if it is wrong both LEDs are mounted backwards on all 5 boards.
5. **3D offsets, courtyards and keep-outs.** J1, J2 and J3 have their 3D body 2.2, 2.8 and 1.0 mm off the pads. Is that only the model, or is the footprint
   **origin** off the body centre? If it is the origin, the JLC CPL centroid for the connectors will be off. The courtyards are smaller than the pads, and Altium's
   component-clearance DRC does not know about the tool's "pads + 0.25 mm" rule. The keep-outs under USB-C and microSD are **not kept in the PcbLib** (S3-06 banner).
   What stops a manual track or Altium DRC from missing them?

## Verdict round 1: **FIX**
K1 was only half done. The coarse pin order of J1/J2/Y1 is right, but no dimension was checked. The three ICs where an error is fatal
(QFN MCU, two LGAs) were not opened, the EP net and paste plan are open, and LED polarity has no source. Answer Q1–Q5 and fix what you
can through the app (EP net and paste, J1 holes, courtyards). Leave what only Altium can fix as named conditions.

---

## System findings (the TOOL)
- [WRONG] A green "Checked" is shown where nothing was checked. Evidence: the Pins tab reads "Checked – Pins: nothing to verify for this part" on J1 (datasheet a scan, S3-10),
  Y1 (scan, S3-21) and D3 ("No datasheet linked", S3-25), while `bom.json` `library_entry.verify` = **"unchecked"** for J1 and Y1. U1–U4
  have `verify: unchecked – "no pins of this part on a sheet to check"` but their rows show plain **"Built"**. So at the library stage no IC
  pinout is checked against its datasheet, and the UI reads as if it were (C50, C53, C54). Why it matters: false assurance on exactly the parts
  where a pin error scraps the board. Generic cause: "no pin table to compare" and "pin check deferred to the schematic" both map to a
  success state. The library step has no symbol-against-datasheet pin check of its own.
- [WRONG] Courtyards smaller than the pads, on every small part. Evidence: Y1 courtyard 3.2×2.5 against pads 3.6×2.96, D3 2×1.25 against 3.1×1.4,
  D4 1.6×0.8 against 2.3×0.8, SW1/2 5.2×5.2 against a 7.58×4.5 span (S3-19, S3-23, S3-26, S3-27, C55). The agent answered "placement uses pads + 0.25 mm,
  leave them" (S3-32). Why it matters: Altium's own clearance DRC, a manual move, and the JLC DFM all trust the courtyard or body. Generic cause: the
  EasyEDA→KiCad→Altium conversion takes the body outline as the courtyard, and the build does not regenerate an IPC courtyard around the pads.
- [WRONG] An imported land pattern is passed through with DFM-relevant defects and no warning (verified in the source files, **unverified in the
  Altium PcbLib**). Evidence: J1 locating holes are plated with 0.6 drill = 0.6 pad, a zero annular ring (`C165948/lib.pretty/…kicad_mod:66-67`). The U1 EP has 100% paste on 5.5×5.5 mm
  and no vias (`C60420/…EP.kicad_mod:69`). Why it matters: JLC DFM flags or reflow risk. Generic cause: the build checks the 3D offset and the pin count, but
  has no rule for annular ring, NPTH against PTH, or EP paste coverage.
- [FRICTION] The library row does not say what "Built, check" means. Evidence: the 3D offset warnings (J1 2.2, J2 2.8, J3 1.0 mm) appear only in the chat answer.
  The row shows "Built, check", and the only fix offered is "shift the offset in Altium by hand" (S3-29, S3-32, C56, C57). Generic cause: the issue text is not carried
  onto the row or the preview, and the app has no offset fix.
- [FRICTION] The keep-outs are dropped from the PcbLib. Evidence: the S3-06 banner says keep-outs are not stored, and only the tool's own placer, router and pour honor them.
  Why it matters: a later manual edit or Altium DRC will not protect the area under the connectors. The banner is honest, which is good, but it is a silent gap for the
  outputs. Generic cause: the keep-out geometry lives only in the tool's sidecar, not in the library.
- [FRICTION] Symbols that make the S4 pin check impossible. Evidence: the J3 symbol is a bare 1..10 box with no SWDIO/SWCLK/nRESET names. J2 has 13 symbol
  pins against 15 pads with no explanation (S3-15, S3-18, C52). The green LED footprint is named `LED0805-R-RD` (C54). Generic cause: generic connector
  symbols are imported without role names from the BOM line, and mismatched pin and pad counts are not explained.
- [COSMETIC] Two names for one source. Evidence: the agent says "from EasyEDA" while the preview caption says "Drawn from the KiCad footprint file" (C56). Both are true (EasyEDA
  converted to KiCad in `library/easyeda/*/lib.pretty`), but the student cannot tell. The datasheet viewer cannot zoom a small LCSC drawing (C59).
- Good tool behaviour worth keeping: one click built 30/30 in about 2 minutes and installed the IntLib. J1–J3 were flagged "Built, check" by a numeric 3D offset check. The
  keep-out limitation was stated up front. LED datasheets were attached but honestly marked "file only, polarity confirmed by the student". The U1 symbol it
  imported is correct against Table 8.

---

# Round 2 (last)

Evidence: `roles/student.md` "Answers to lecturer S3", confusions C60–C67, `screens/S3-37..53`, `roles/alti-S3.md` and
`roles/engineer-S3.md` (Altium PcbLib checks), and `sources/STM32F411CEU6.pdf.txt:6698` ("solder this back-side pad to PCB ground", which I confirmed).
As the orchestrator asked, the student is judged on what a student can do with this tool. The library defects only the tool (or Altium by hand) can fix go
to the system findings and conditions, not against the student.

**Correction to my round 1:** my Q3 point "J1 locating holes are plated with zero ring" came from the KiCad **source** file. Alti confirms that the Altium
PcbLib holds them as **unplated NPTH** (`alti-S3.md:60`), so the converter handles it. The student and the agent were right on this point, and I withdraw that part of
my round-1 system finding. The EP paste part stands (Alti confirms it: `alti-S3.md:39`).

## Answers checked
1. **U1 EP: answered.** Net = GND, from a quoted datasheet note (verified at `:6698`). Paste window and thermal vias: the tool cannot do them. The student proposed
   a reasonable plan (50–80% windowed paste, via grid at layout, ask JLC about open via-in-pad on 4 layers) and marked it unverified. That is the right attitude.
   The U1 symbol is unreadable in the preview (C60). The engineer and I checked all 48 pins against Table 8, and they match.
2. **U2/U3: answered.** U2 pin 1 was worked out correctly from a **bottom-view** figure to top-left from above, matching the footprint, and the 3D model is not rotated. That is a good catch,
   because bottom-view confusion is a classic LGA mistake. The U3 pads are 0.77 against Bosch's 0.50 mm. The student cannot judge it and says so, so it is carried as a condition.
3. **J1: answered.** 0.5 mm inner pitch understood (0.65 is the step to A4B9), NPTH pegs correct. The shield slots of 0.80 mm against a 0.60 mm drawn leg width are
   unverified, so this is carried.
4. **LED polarity: answered by the student's own reading** of the KT-0805G drawing (cathode left = pad 2 = silk triangle). D4 rests on the agent's citation only.
   That is acceptable, with a check on the JLC assembly preview.
5. **Origin, 3D and keep-outs: answered, and the most valuable finding of the stage.** The student found that J1/J2 **origin** is 1.42/2.32 mm off the body centre,
   which is a CPL problem, not only a 3D one. Courtyards and keep-outs: the student correctly concludes that only the tool's placer, router and pour protect them, and Altium does not.

## Verdict round 2: **PASS with conditions**
- **L1 (S4 schematic):** U1 pin 49 (EP) on the GND net (datasheet Figure 49 note 3). The J3 symbol has no names, so map the 10-pin Cortex-debug
  pinout (1 VCC, 2 SWDIO, 3 GND, 4 SWCLK, 5 GND, 6 SWO, 7 KEY/NC, 8 NC, 9 GND-detect, 10 nRESET) explicitly and get it checked.
- **L2 (S5/S6):** U1 EP: a via grid to the GND plane and a paste decision (windowed in Altium, or rely on JLC stencil optimisation and say so in the order note).
  Record the decision, and the producer checks it in the JLC DFM at S8.
- **L3 (S7 outputs):** J1/J2 origin offset. Fix the component origin in Altium before generating the CPL, **or** check and correct J1/J2 on the
  JLC placement preview. The producer at S8 must check J1, J2 position, D3/D4 polarity and U1/U2/U3 pin 1 in the JLC assembly preview.
- **L4 (S5/S6):** no hand placement or hand routing near the USB-C/microSD keep-outs, and no reliance on Altium's component-clearance DRC
  (courtyards are body outlines). Use the tool's placer, router and post-route check only.
- **L5 (S8):** the U3 pad length (0.77 against 0.50 mm recommended) and the J1 shield slot width (0.80 against 0.60) go to the JLC DFM. Note in the report what JLC says.

---

## System findings, round 2 (new)
- [WRONG] A production-relevant origin error was reported as a cosmetic 3D warning. Evidence: round 1 flagged only "3D body 2.2 / 2.8 mm off the pads" (S3-29).
  In round 2 the agent found that J1/J2 **origin (0,0) is 1.42/2.32 mm off the body centre**, and the 3D body is offset the other way (S3-53, C66). The rows
  still show only "Built, check". Why it matters: the CPL centroid for both connectors will be wrong at JLC. Generic cause: the build's offset check compares the 3D body
  with the pads but never the origin with the pad or body centroid, and the converter does not normalise the origin. Nothing blocks the Outputs step on it.
- [FRICTION] The tool detects library defects but can fix none of them, and its rebuild would wipe a manual fix. Evidence: the agent says "the tool builds pad 49 as one
  solid pad and cannot edit footprints or place vias", "copies EasyEDA's courtyards and (0,0,0) 3D offsets as-is, and rebuilding overwrites the
  PcbLib" (S3-45, S3-53, C62, C66). The overwrite is the agent's claim, unverified by me. Why it matters: a student in the web UI has no path, and the only path (hand edit
  in Altium) is undone by the next Build library. Generic cause: no footprint-edit actions (paste reduction, EP via grid, origin to centroid,
  IPC courtyard), and the rebuild does not preserve or detect manual library edits.
- [FRICTION] Judgments with no support. Evidence: "fine as-is" for BME280 pads 50% longer than Bosch's recommended land, with no reason. "0.80 mm tab fits" a 0.60 × 1.40 mm
  drawn slot, with no tolerance. Both are read from scans and marked "File only, claim not verified: no quote" (S3-47, S3-49, C63, C64). Why it matters:
  priority 1 is to refuse rather than guess. These should be "unverified, check with the JLC DFM". Generic cause: the agent may give a verdict where only a
  measurement or citation would justify one.
- [FRICTION] The preview cannot show what the student must check. Evidence: no paste or mask layer toggle (the EP paste is invisible), the 49-pin U1 symbol is
  unreadable with no zoom, and citations to Altium docs are flagged "is not in Sources" and cannot be opened (S3-39, C60, C61, C67). There is no "Confirm polarity" or "Confirm
  pins" action, so the student's checks live only in his notes (C65).
- Status of the round-1 findings: green "Checked – nothing to verify" (stands; the student confirmed it on U1, J1, J2, Y1, D3). Courtyards (stands; Alti
  confirms Mech 15 = body outline). The zero-ring part is **withdrawn** (Altium has NPTH). EP paste (stands). Keep-outs not in the PcbLib (stands).
- Good tool behaviour worth keeping: the EP net came with an exact datasheet quote. The bottom-view pin-1 reasoning for the LSM6DSO was correct. It said plainly that it cannot
  fix footprints and pointed to the Altium step. On request, it located the real origin problem precisely.
