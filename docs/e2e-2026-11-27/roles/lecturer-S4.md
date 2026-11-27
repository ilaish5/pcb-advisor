# Lecturer – Stage 4 (Schematic)

## Video highlights
- S4-46-draw-error-details-3-sheets.jpg | Draw refused: the app cannot draw nets between sheets, so the design is split into three.
- S4-50-altium-drawn-54-parts-38-nets.jpg | 54 parts and 38 nets drawn in Altium on 3 sheets in 55 seconds.
- S4-40-build-library-error-intlib-not-written.jpg | Adding one 10 nF cap hangs the library build for 20 minutes (system bug, fixed mid-stage).
- S4-68-q3-answer-firmware-note.jpg | Firmware bring-up order: disable the IMU's I2C/I3C before the first flash access.
- S4-55-unused-pins-table.jpg | Lecturer round 1: FIX. Cross-sheet nets unverified, shared-SPI IMU I2C risk, board size undecided.
- S4-78-main-redrawn-20-parts-37-nets.jpg | Lecturer round 2: PASS with conditions. Compile proved by Alti; re-check after the Main redraw.

# Round 1

Evidence: `roles/student.md` (S4), confusions C68–C92, `screens/S4-01..58`, `netlist/Main.json`, `02.json`, `03.json` (I read every pin of every part),
`sources/LSM6DSOTR.pdf.txt`, `STM32F411CEU6.pdf.txt`, `SMF5.0A.pdf.txt`. Altium itself was not inspected by me (that is Alti's job).
The library-rebuild blocker (C77–C87) was a system bug and is not held against the student.

## What is good: I checked the netlist and these are correct
- **U1:** VBAT, VDDA and VDD 24/36/48 on +3V3. VSSA, VSS and **EP 49 on GND** (L1 ✓). VCAP1 with C10 4.7 µF. BOOT0 has R5 10k down and SW2 to +3V3. **PB2/BOOT1 has R13 10k
  down** (C1 ✓). NRST has C14, SW1 and J3.10. PA11/PA12 = USB DN/DP. SWO is on PB3. The SDIO pins match the stage-1 plan, and SDIO pull-ups R6–R10 are present (C2 ✓).
- **J1:** A6/B6 = D+, A7/B7 = D−, CC1/CC2 each with 5.1k to GND, shell to GND. **D1 USBLC6:** 1/6 = D+, 3/4 = D−, 2 = GND, 5 = +5V, which matches the
  datasheet. **U5 LDL1117 SOT-223:** 1 GND, 2/tab VOUT, 3 VIN. F1 comes before D2, and D2 pin 1 (band = cathode) is on +5V.
- **U4 W25Q128:** IO2 (/WP) and IO3 (/HOLD) tied high, with R14 pull-up on FLASH_CS (good that you asked for it). **U3 BME280:** CSB high for I2C, SDO to GND (0x76), and both
  are written as a sheet note. **J3** is the 10-pin Cortex-debug map (K1 ✓). The LEDs are active-high through R3/R4.
- You added the **10 nF on VDDA** (C23, Figure 43) yourself, which the tool's review missed. You read the D1 warning and asked whether it was a short instead of ignoring it.

## Questions you must answer (round 1)
1. **Are your 3 sheets one circuit?** The tool itself said it "does not yet draw the nets that run between sheets (nets that need ports)" (S4-46).
   After the split it reports "38 nets drawn… checked against the netlist". About 30 nets cross sheets: HSE_IN/OUT, LSE_IN/OUT, NRST, BOOT0/1, SWDIO/SWCLK/SWO,
   SPI1 ×3, IMU_CS, IMU_INT1, FLASH_CS, I2C ×2, SDIO ×6, SD_CD, LED1/2, +3V3 and GND. What joins them in Altium (global net labels? power ports?), and how
   do you **prove** each one is a single net? Ask the app or Alti for a compiled-project net list, or the ECO net count. While you are there, show that D1 pin 2 (GND) and pin 5 (+5V) are separate nets
   after compile. Until this is shown, "0 errors" says nothing about the inter-sheet wiring.
2. **What is the "NC" net?** In the netlist all 17 unused pins sit on **one net literally named "NC"**: J1 SBU1/2, J3 7/8/9, U2 INT2/OCS_Aux/SDO_Aux, and
   U1 PC13, PA0–PA3, PB10, PA10, PA15, PB6. The draw count (38 = 39 names − NC) suggests the drawer drops it, but confirm in Altium that these are
   No-ERC/no-connect pins and **not** one shared net. Otherwise the PCB will short them all together. Separately, PA10 (USART1_RX) floats, and condition K5 (bootloader detection with
   a floating RX) is still unverified. Leave it NC with that risk written down, or give it a pull-up?
3. **Shared SPI1 and the LSM6DSO's I2C/I3C block.** With CS high the LSM6DSO is in "SPI idle mode / I²C communication enabled". Its SCL/SDA pins are
   your SPI1_SCK and SPI1_MOSI, so every flash transfer is also seen by the IMU's I2C/I3C block. What stops it from ever acknowledging and driving SDA,
   which is your MOSI? The datasheet answer is "(I2C_disable) = 1 in CTRL4_C (13h)" and "I3C_disable = 1 in reg 18h" (`LSM6DSOTR.pdf.txt:625, 1663`).
   Put it in the firmware bring-up note **in order**: disable the IMU's I2C/I3C before the first flash access.
4. **Decoupling is bound to nothing.** C1–C5, C22, C23 and C11 all sit on +3V3/GND, with only a note saying "place next to their pins". Nothing ties a cap to U1 pin 1, 9, 24,
   36 or 48, and the same goes for C6/C7 (U2), C8/C9 (U3) and C19/C20/C21. How will you make sure in S5 that each supply pin gets its own 100 nF within about 1–2 mm, with C22+C23 at pin 9 and
   C19 at the microSD slot (K3)? And SD_CD has no pull-up on the board: is PB12's internal pull-up your decision? Write it in the firmware note.
5. **Board size, decided now.** The app says the 54 parts need about 1008 mm², which is 64% of 45×35 mm, and suggests 60×45. Your confirmed requirement is still 45×35. With a QFN, two LGAs,
   USB-C, microSD, a 2×5 header and 4×M3 holes, on 4 layers with 0402 parts, which size do you choose and why? Update the Idea requirement before
   placement. The S5 placer will otherwise decide it for you.

## Verdict round 1: **FIX**
The schematic content is good, and better than most student first drafts: every IC pinout I checked is right and the stage 1–3 conditions are met. But Q1 and Q2 are
connectivity questions that can make a correct netlist into a wrong PCB, Q3 is a real bus-contention risk, and Q5 must be decided before
S5. All of it can be done through the chat, Alti's check and the Idea page.

Carried conditions status: C1 ✓, C2 ✓ (CD pull-up → Q4), K1 ✓ (J3 by the standard map), K2 partly (high-drive note on sheet 02; tunable pads and RTC calibration →
S7 README), K3 → S5, K4 → S7, K5 open (Q2), L1 ✓, L2–L5 → S5–S8.

---

## System findings (the TOOL)
- [BLOCKER, fixed mid-stage] Adding one capacitor broke the library. Evidence: Build library for C23 reset all 31 lines to "Ready to build" (C77). It ran 15–20 min and ended
  silently twice (C78, C85). Altium showed the modal "Could not create integrated library…" (installed IntLib locked), and the app then said "restart Altium… add the IntLib in the
  Projects panel" (S4-40, C86), which a web-UI student cannot do. It was fixed by a code change at 03:52, after which the build took about 90 s (C87). Generic cause: the rebuild is all-or-nothing on a
  locked installed IntLib, and hangs and modals are not detected or surfaced.
- [WRONG] (pending Alti's compile) "Checked" is claimed for inter-sheet connectivity the tool says it cannot draw. Evidence: "The tool does not yet draw the
  nets that run between sheets (nets that need ports)" (S4-46, C88), then "54 parts and 38 nets drawn on 3 sheets, saved and checked against the netlist" (S4-50).
  Why it matters: about 30 nets cross sheets, and a dropped one (for example HSE or BOOT0) is a dead board. Generic cause: no ports or off-sheet connectors in the drawer.
  The check appears to compare each sheet with its own netlist file, not the compiled project.
- [WRONG] The review missed a real functional risk and a datasheet requirement. Evidence: "Review this sheet: 0 errors, 3 warnings" (S4-13). It did not mention the LSM6DSO
  I2C/I3C block listening on the shared SPI1 lines (datasheet I2C_disable/I3C_disable). It also missed the VDDA 10 nF until the student asked (C71, C73). Generic cause: the review has no
  rule for "multi-protocol slave on a shared bus", and no rule that compares decoupling with the MCU power-supply figure.
- [FRICTION] Unused pins are modelled as a net called "NC". Evidence: all three netlist files put 17 pins on `net: "NC"`. The check reports "55 nets, 0
  single-pin nets" against "38 nets drawn" (S4-53), and the agent says "marked NC with No ERC markers" (C92). Why it matters: one tool in the chain that treats NC as an
  ordinary net shorts 17 pins together, and the numbers shown do not let the student tell. Generic cause: no-connect is a magic net name, not a pin attribute.
- [FRICTION] Decoupling is not bound to pins. Evidence: the `Main.json` note "Place C1-C5 … next to their respective MCU pins", with every cap on +3V3. Why it matters: the placer
  and the review cannot check "a cap at each supply pin". Generic cause: the netlist format has no cap-to-pin association.
- [FRICTION] The netlist writer does not know the drawer's limits. Evidence: the agent wrote one sheet with 54 parts, Draw refused ("does not fit … needs about 3 sheets"), and the student had
  to ask for a split (S4-45/46, C88). The board-area warning (64%, try 60×45) first appeared at S4 (C74), although the size and parts had been known since S2. Generic cause:
  no sheet-capacity or board-area check at the moment of writing the netlist or confirming the BOM.
- [FRICTION] A library symbol defect shows up only at draw time. Evidence: D1 USBLC6 symbol has a line joining pins 2 and 5, which gives a draw warning "GND and +5V are one terminal" (S4-51, C90).
  The tool cannot fix its own symbol ("edit the .SchLib by hand", S4-53). The library stage showed D1 as plain "Built". Generic cause: no symbol-graphics lint at build.
- [FRICTION] Stale or contradictory messages. Evidence: after the 3-sheet rewrite the agent again says "pins of J3, U2/U4 … are a guess, confirm in DFM", while DFM shows the
  confirmations kept (S4-48, S4-56, C89). The first netlist answer gave two different lists of unverified parts (C69). The BOM shows "Accepted risk" for parts DFM lists
  as "Checked by you" (C84). The Confirm-pins dialog opens on a blank p.190 and the UFBGA page, not the UFQFPN48 table (C80). The D1/D2 rows open nothing (C82).
- [COSMETIC] The crystal is classed as a resistor. Evidence: `02.json` Y2 `kind: "res"` (Y1 is "ic"). Any effect on the symbol, placer rules or keep-out is unverified.
- Good tool behaviour worth keeping: every IC pinout it wrote that I checked is correct, including the bottom-view LSM6DSO and the SOT-223 tab. It flagged FLASH_CS without a pull-up. It
  wrote the BME280 strap choices as a sheet note. DFM separates "Checked by you" from "Accepted risks", and lists J3 honestly as "accepted without a datasheet". Its power-and-ground check
  and its refusal to draw a sheet that does not fit were both correct.

---

# Round 2 (last)

Evidence: `roles/student.md` "Answers to lecturer S4", confusions C93–C98, `screens/S4-59..78`, `roles/alti-S4.md` "Follow-up: inter-sheet
connectivity" (native Altium `DM_Compile` at 04:40), `netlist/Main.json` (rewritten 05:32: R15 PA10→+3V3), `idea.json` v10 (60×45), `notes.md`
"Firmware Bring-Up", and the LSM6DSO datasheet lines checked in round 1.

## Answers checked
1. **Cross-sheet connectivity: proven, by Alti.** Automatic scope resolves to Global because there are no ports or sheet symbols. The native compile gives 55 nets and 224 pins, with 0 split,
   0 merged and 29 cross-sheet nets each one net. D1 pin 2 and pin 5 are separate, so the D1 warning is a false alarm. The student did not get the proof from the tool, but did ask the right question and cited
   the evidence honestly as Alti's. **But the compile was run at 04:40, and Main was redrawn at 05:32** for R15, so it has to be repeated (M1).
2. **NC: resolved.** There are 17 No-ERC markers giving 17 separate single-pin nets, not one net. **PA10: decided** to use a 10k pull-up (R15). That is the defensive choice. The AN2606
   citations are unverified (C94), so K5 stays open until a real DFU test, with SWD primary. Accepted.
3. **Shared SPI1: fixed in the firmware note**, with the correct order: CS lines high, then `I2C_disable` in CTRL4_C (13h), then `I3C_disable` in CTRL9_XL (18h), and only then flash access.
   This matches the datasheet lines I cited. IMU_CS has no external pull-up, but the LSM6DSO CS has an internal pull-up by default, so it stays deselected at reset. That is fine. SD_CD uses
   PB12's internal pull-up, decided and written down.
4. **Decoupling: honest answer and a sound plan.** The tool cannot pair caps with pins, so the student will check by hand at placement, pin by pin. That is the right call, because the student found
   that the tool's board check would pass a cap 4.9 mm away or on the wrong chip. Carried as M2.
5. **Board size: decided, 60×45**, with reasons: 37% fill, JLC price tier unchanged, connector edges, holes, routing room. The Idea board field, the goal and the requirement now agree
   (v10).

## Verdict round 2: **PASS with conditions** (for placement and routing)
- **M1 (before S5 Update PCB):** Alti re-runs the native compile on the redrawn Main. Expect 55 nets, 226 pins (224 + R15), 16 No-ERC markers, and the 29 cross-sheet nets still single.
  Also read Altium's ERC violation list once, which was not done yet. The S5 ECO must show 55 parts and no "Footprint Not Found".
- **M2 (S5):** decoupling by hand. C1–C5 within about 1–2 mm of U1 pins 1, 9, 24, 36 and 48, with C22+C23 at pin 9. C6/C7 at U2, C8/C9 at U3, C20 at U4. **C19 10 µF at J2** (K3).
  C10 at VCAP1 pin 22. C12 and C13 at the U5 pins. The student writes the checklist at S5 and Alti measures it.
- **M3 (S5):** the 60×45 outline, 4×M3 holes with keep-outs, USB-C and microSD on the opposite short edges, crystals Y1 and Y2 tight to U1 pins 5/6 and 3/4 with no
  signal under them, and the LSE kept short (6 pF crystal, 2 pF caps). No hand placement near the connector keep-outs (L4).
- **M4 (S7 outputs):** the README carries the `notes.md` Firmware Bring-Up items (IMU I2C/I3C disable order, LSE high-drive, PB12 pull-up, VBUS sensing off), plus
  K2 (tunable load caps, RTC calibration) and K4 (8 LCSC codes). L2/L3/L5 stay as written in S3.

---

## System findings, round 2
- **Correction to my round-1 finding:** the "[WRONG] (pending Alti's compile) 'checked' claimed for inter-sheet connectivity" is **withdrawn as WRONG**. Alti's native
  compile shows that the drawn project equals the tool's netlist exactly (55/224, 0 split or merged). What remains is the FRICTION below. The "NC" net
  representation also compiled correctly (17 single-pin nets), so that finding stays FRICTION only as a fragility of the representation.
- [WRONG] The decoupling check gives a false pass. Evidence: the agent states the board check flags only "a ceramic cap more than 5 mm from ANY IC or connector pad on +3V3".
  Auto-placement "ignores pin names like VDDA" and "cannot split C1-C9 reliably across U1/U2/U3" (S4-74, C97). Why it matters: a green board check
  with VDDA undecoupled, or a 100 nF sitting by the wrong chip, is a hidden technical error. The tool was honest when asked, but the check itself passes it. Generic cause: no
  cap-to-pin association in the netlist (round-1 finding) and a distance rule against any pad instead of the paired supply pin.
- [FRICTION] Connectivity can be proven only by Altium hand steps. Evidence: asked "how do I prove it", the app answers "Validate PCB Project … Navigator > Flattened
  Hierarchy" with citations "not in Sources" (S4-60, C93). The web UI shows no compiled net count. Generic cause: the system does not read back the compiled netlist
  from Altium to compare it with its own, even though Alti's read-only script shows it is possible (`alti/S4-AltiNets.pas`).
- [FRICTION] A one-resistor change forces a full sheet rewrite and a "replace Main? this wipes what is drawn" redraw. Evidence: S4-76, C94, C98. It also invalidates the
  earlier compile proof (M1). Generic cause: no incremental schematic update (add a part or wire to a drawn sheet).
- [FRICTION] The board size has two sources of truth. Evidence: "Board size 60×45, Set" shows a toast, while the Idea text and requirement still say 45×35 until the agent is asked and
  the draft is saved by hand (S4-69..72, C96). This is the fourth stale-text case in this run (S1 sensors, S2 IMU, S2 LDO, S4 board). Generic cause: as before, the goal
  and requirements are not regenerated from structured fields.
- [FRICTION] Important firmware facts live only in a free-text file. Evidence: the bring-up order is written to `notes.md`, whose own header says "Nothing derives from this file". The chat
  shows only the path (S4-68, C95). Why it matters: nothing carries it into the outputs README (see M4). Generic cause: no structured "firmware requirements" item
  in the project data.
- [FRICTION] Unreadable citations. Evidence: AN2606 is cited as untranslated Chinese sentences marked "claim not verified: no quote given" (C94). Generic cause: the source
  copy in use is a non-English mirror, so the quote matching fails.
- Good tool behaviour worth keeping: a correct, sourced firmware bring-up order. It recommended the PA10 pull-up. It said plainly that it cannot pair decoupling. It asked before wiping
  Main and kept a backup. And its netlist is exactly what Altium compiles.
