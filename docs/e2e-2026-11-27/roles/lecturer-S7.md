# Lecturer – Stage 7 (Manufacturing outputs)

## Video highlights
- S7-03-outputs-generated-21-files-2-warnings.jpg | 21 files in 40 s while 424 DRC lines and U1 unchecked stay open.
- S7-07-agent-says-no-readme-added-notes.jpg | There is no README output, so the agent writes the bring-up notes into notes.md.
- S7-08-agent-added-all-to-notes.jpg | After the student's second ask, all risks and the JLC04161H-7628 note are in.
- S7-08-agent-added-all-to-notes.jpg | Lecturer round 1: PASS with conditions. Fab set complete; CPL and tenting checks at S8.

# Round 1

Evidence: `roles/student.md` (Stage 7), confusions C131–C137, `screens/S7-01..08`, `projects/Final-E2E-4L/exports/` (gerbers.zip, BOM_jlc.csv, cpl.csv,
order_manifest.json) and `projects/Final-E2E-4L/notes.md`. I opened the Gerber, drill and CSV files myself. As before, the student is judged on what the web UI allows.

## What is good
- You produced and exported the full set (Gerber zip, JLC BOM, CPL) and listed exactly what is inside, file by file.
- You did **not** click "Confirm" on U1 just to make the banner go away. That is correct: a 49-pin MCU without a pin check is a real risk, not a formality.
- You read notes.md yourself, saw that the first version had dropped most of your decisions (C135), and made the agent add them. That is reviewer behaviour, not passenger behaviour.
- You said plainly what you did **not** verify (CPL rotation and origin), instead of assuming the export is right.
- You caught the C136 contradiction yourself.

## My own checks of the files
- **Outline (GM1):** a rectangle 2.3622 × 1.7717 in = **60.0 × 45.0 mm** ✓ (M3 decision kept).
- **Layers:** GTL / G1 / G2 / GBL (all positive, so the inner planes are poured copper, not negative-plane files), GTS/GBS, GTP/GBP, GTO/GBO. That is complete for a 4-layer JLC order.
- **Drills:**
  - Plated round holes: one tool only, 0.3048 mm (the vias).
  - Plated slots: 4 × 0.80 mm (J1 shell).
  - NPTH: 2 × 0.60 mm (J1 pegs), 2 × 1.00 mm (J2 pegs), and 4 × 3.20 mm (M3), 3.5 mm from the edges ✓.
  - No unexpected plated pegs (my S3 claim stays withdrawn).
- **BOM (31 lines):** every line has an LCSC code, including the 8 that were empty at S2 (C435835, C479202, C2692145, C270607, C1574, C1558, C52923, C25130) and C15195 for C23. **K4 ✓, P4 (codes) ✓.**
- **CPL frame:** the CPL uses the same absolute frame as the Gerbers (Board_Origin 0|0; the outline runs x 25.4–85.4 mm, y 25.4–70.4 mm), so JLC will overlay it correctly ✓.
- **CPL origin (L3/P4), still open:** I compared the CPL with the footprint origin (the same positions in Alti's S5 and S7 data) and with Altium's own `Pick Place for Final-E2E-4L.txt` (Center-X/Y):
  - J1: CPL 30.84, origin and Altium centre 30.99, a 0.15 mm difference.
  - J2: CPL 75.56, origin 75.315 (0.245 mm), Altium centre 75.46 (0.10 mm).
  - U5: CPL y 43.345 against 44.0, a 0.655 mm difference.
  - The rotations are equal. The CPL rule is neither the origin nor Altium's centre, and nothing states it. More important: for J1/J2 the CPL lies within 0.25 mm of the footprint origin, which S3 measured as **1.42 / 2.32 mm off the body centre**. So the library-origin error is most likely **carried into the CPL**.
  - The J1 slot pattern is centred at x ≈ 30.61 mm, and the body extends towards the edge, which also points that way. JLC will place J1/J2 off by about 1–2 mm unless the preview is corrected.
- **notes.md against my conditions:**
  - **M4 ✓:** CS lines high first; I2C_disable in CTRL4_C 13h, then I3C_disable in CTRL9_XL 18h, before any flash access; LSE high-drive; PB12 internal pull-up; VBUS sensing off; SWD first, DFU only as a backup.
  - **K2 ✓:** load-cap tuning (C15/C16, C17/C18) and RTC smooth calibration.
  - **P1 ✓ in content (not word for word, which I accept):** VCAP1 17.4 mm with 2 vias, "measure ≈1.2 V and ripple"; HSE/LSE start-up tests with signals under Y1/Y2; +3V3 at 0.127 mm; pours 0.16 mm from the M3 holes; untented vias; J3 0.30 mm from the edge.
  - **P2 ✓:** "the file stack is the Altium default … you MUST select JLC04161H-7628" is in bold and correct.

## Questions you must answer (round 1)
1. **The decap line is incomplete.** Open Risks names C10, Y1 and C13 only. My S5 net-aware list had two more items that are still true:
   - The **microSD slot has no local cap**: C19 (10 µF) is 28 mm away and C21 is 23 mm away, while the SD card draws 200 mA bursts (K3).
   - **VDDA's 1 µF (C22) is 21 mm away.**

   Add both, with a measurable bring-up check (for example, SD write bursts while you watch +3V3 at J2 pin 4).
2. **C136: tented or not?** Write one sentence the JLC operator cannot misread: "Vias are open in the Gerber mask. On the order page select Via Covering = *Tented*", or "accept untented vias on HASL". Then delete the other line. Which one do you choose, and why? Remember that untented 0.3 mm vias next to U1/U2 pads under HASL are a solder-wicking risk.
3. **CPL is not the origin, so what is it?** Before you place the order, compare the JLC assembly preview with the CPL for **J1, J2, U5 (SOT-223), U1 (EP)** and the two LGAs U2/U3: position and rotation. What tolerance do you accept, and what do you do if J1 sits 1 mm into the board edge?
4. **424 DRC lines: which are real?** Your note says "fix before ordering", yet you are about to order. Split them:
   - 252 mask slivers: most go away if the vias are tented. Which ones are pad-to-pad on U1/J1 (the 0.054 / 0.098 mm dams, P3)?
   - 160 silk-to-mask: JLC clips these.
   - 7 board clearance: is that J1/J2 overhanging the edge on purpose, or J3 at 0.30 mm?
   - 4 J1 annular ring: per Alti S6 these are the 4 plated shell slots, with a 0.200 mm ring against an 8 mil (0.203 mm) rule. They meet JLC's 0.15 mm minimum, so they are rule noise; say so.

   Write the triage into notes.md. "424" with no breakdown helps nobody at the board house.
5. **The pour-to-hole distance is a DFM fail, not just a number.** The inner GND and +3V3 pours are 0.16 mm from the 3.2 mm NPTH, and JLC asks for 0.2 mm or more (P3). Does your note tell the reader that JLC may reject or modify the board, and who fixes it? Also: USB D− hops to Mid-2 (+3V3 plane) with 2 vias. Add that to the USB risk line.

## Verdict round 1: **PASS with conditions** (gate: S8 JLC order)
The outputs are complete and consistent: the outline, 4 copper layers, drills, the BOM with all LCSC codes, and the CPL in the Gerber frame. The README items I required (M4, K2, P1, P2) are present
in notes.md. The remaining items are either order-time checks that only the JLC preview can close, or wording fixes. The missing README output and the missing gate before outputs are
tool limits (see below), not the student's fault.
- **Q1 (before order):** add the SD-slot and VDDA decap risks to notes.md.
- **Q2 (before order):** one unambiguous via-tenting line, matched by the same choice on the JLC order page.
- **Q3 = P4 rest (S8):** check the CPL against the JLC preview for J1/J2/U5/U1/U2/U3, both position and rotation; record the offsets.
- **Q4/Q5 (S8):** DRC triage in notes.md; JLC DFM must report on pour-to-NPTH 0.16 mm, U1 dam 0.054 mm, J1 dam 0.098 mm, J3 0.30 mm from the edge, J1 slots, U3 pads, and EP paste (P3, L2, L5).
- **Order page (P2):** JLC04161H-7628 selected; 4 layers, 1.6 mm, HASL, top-side assembly.
- Still carried: K5 (DFU on the real board), U1 pins unchecked (accept on record, or check at S8).

---

## System findings (the TOOL)
- [FRICTION] There is no README / order-note output. Evidence: the Export menu offers only BOM (JLC), BOM (generic), CPL and Gerber zip (S7-04, C133). The agent: "no README button", so the notes went into notes.md (S7-07, C134). Why it matters: the bring-up notes, the stack-up choice and the tenting decision do not travel with the Gerbers to the person who orders. Generic cause: outputs cover only fab/assembly files, and project knowledge stays in notes.md.
- [WRONG] The notes agent dropped the student's recorded decisions on the first pass. Evidence: the first notes.md had none of VCAP1 17.4 mm, +3V3 0.127 mm, signals under Y1/Y2, pours near M3, untented vias, J3 edge, tunable load caps or RTC calibration, and its stack note did not say "Altium default" (C135). All of these were already in the S6/S4 chat and conditions. Even after the second pass, the S5 decap list (C19/C21 SD slot, C22 VDDA) is still missing. Why it matters: a student who does not re-read notes.md orders without the risk list. Generic cause: the README is built from the agent's memory of the chat, not from a structured list of open conditions and risks.
- [WRONG] notes.md contradicts itself on tenting. Evidence: JLC Order Note "Tent vias (all vias 0.3048 mm hole, within JLC's 0.4 mm tented limit)" against Open Risks "Vias are NOT tented in the board file" (C136). In the board file the vias are open: per Alti S6, the SolderMaskExpansion rule has `ISTENTINGTOP=FALSE`, and 71 pad-to-via plus 12 via-to-via mask slivers come from it. Why it matters: the operator may assume tenting is in the files, or the student may skip the order-page option. Generic cause: the order-note template writes a capability line ("can be tented") as if it were an instruction or a fact.
- [FRICTION] Outputs are not gated, and DRC is not shown on the Outputs page. Evidence: "Warning (the outputs are still made)", then 21 files are written with Layout at 424 DRC and U1 unverified, and the page never mentions the DRC (S7-02/03, C131, C132, C137). The manifest does record the 07:14 DRC under `board_check`, so the data exists. Why it matters: Gerbers look "done" while the board has known DFM items. Generic cause: no "before you order" summary (DRC by rule, unverified parts, open conditions) with one explicit "make anyway" click.
- [FRICTION] The CPL basis is not stated. Evidence: CPL J1/J2/U5 differ from the footprint origin by 0.15 / 0.245 / 0.655 mm, and J2 differs from Altium's Pick Place centre by 0.10 mm (my comparison; also in `alti/S7-analysis.txt`). So the CPL follows neither rule, and nothing states which it uses. For J1/J2 it stays near the origin, which S3 found 1.42 / 2.32 mm off the body centre. Why it matters: the library-origin error is most likely carried to JLC unseen, and a 1–2 mm offset on USB-C/microSD is a scrapped assembly. Generic cause: the CPL export does not report its centroid rule and does not flag parts whose origin and body centre differ (the S3 data already knew it).
- [COSMETIC] "Altium wrote no BOM" next to a "BOM 1 file" folder (C132). Generic cause: the message refers to the OutJob BOM, while the folder holds the advisor's copy. Say which file is which.
- [COSMETIC] The accepted risks in the manifest have empty `reason` for all six entries (D1/D2 "polarity", J3 "blind"). This is acceptable under the low-friction rule, but the "blind" acceptance of J3 should at least be shown on the Outputs page next to the file list.
- Good tool behaviour worth keeping:
  - The Gerber set is complete and well-formed (4 positive copper layers, separate PTH, NPTH and slot drill files).
  - The JLC BOM is fully populated with LCSC codes.
  - The CPL is in the Gerber frame.
  - The U1 warning is specific and points to the exact place to fix it.
  - The JLC04161H-7628 note came out correct and in bold.
