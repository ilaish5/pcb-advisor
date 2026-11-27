# Engineer review, Stage 4 (Schematic), system side in the browser

## Video highlights
- S4-20-u4-conflict-explained.jpg | Red "Pins conflict" on U4 is false: on this -IQ part, pin 7 is IO3.
- S4-40-build-library-error-intlib-not-written.jpg | Library build failed; app tells the student to restart Altium and edit the project.
- S4-50-altium-drawn-54-parts-38-nets.jpg | Drawn sheets match the netlist exactly: 54 parts, cross-sheet labels joined.
- S4-53-erc-answer-d1-not-shorted.jpg | "0 errors" checks connections only; decoupling, pull-ups and EP were never machine-checked.

Scope: the Schematic page, BOM/DFM pages, chat 03:03-04:05 and the data behind them: netlist/Main.json, 02.json, 03.json,
bom.json, library-log, altium-log, turns-log, cites.json, sources/*.txt, library/easyeda. I also re-ran the read-only
check scripts/checks/schematic.py on the netlist and on the drawn PrjPcb. I did not judge the drawing itself (Alti's
job). Engine: Antigravity / Gemini.

## Verdict
The netlist is good engineering. It implements every item the student asked for. Every MCU pin is on a valid
alternate function of F411 Table 8, and the sensor straps match their datasheets. The drawn project is identical to
the netlist. I compared both with the system's own check: 55 net groups and 224 pins, the same in both, and the
cross-sheet labels join. What is wrong is around the netlist, not in it:
- a false red "Pins conflict" on a part whose pin map is correct;
- a library build that failed silently, could not restore the old library, and then asked the student for Altium
  hand steps;
- "0 errors" results whose scope is never stated. None of them checks decoupling, pull-ups, EP or crystals; only the
  model's own reading did that.

## System findings

- [WRONG] U4 "Pins conflict" is a false mismatch, and the app offers to replace a correct part. verify_part marks
  U4 `mismatch`: "pin 7 IO3: the datasheet calls pin 7 /HOLD or /RESET" (library-log 03:16:42, 03:23:16). The BOM row
  turns red, and clicking it opens an Alternatives panel listing other flash parts and Keystone parts that are not
  flash at all (S4-17, S4-18, C75). For the ordered part, IO3 is the right name. The W25Q128JV datasheet says that for
  ordering options "IQ/IN" and "JQ" the QE bit is factory fixed at 1, so IO2 and IO3 are quad I/O pins and /WP and
  /HOLD are not available (W25Q128JVSIQ.pdf.txt 891-895). The agent's explanation (03:23:44, S4-20) repeats the
  generic table name and never mentions QE. Its conclusion, "wiring pin 7 to +3V3 is valid for standard SPI", is
  true, because the F411 has no QSPI and single-SPI commands never drive IO2/IO3. The student had to accept a
  "mismatch" on a correct part. Generic cause: the pin-name compare reads the first name in a multi-function cell and
  ignores ordering-code notes. A naming difference should never open "Alternatives".
- [WRONG] The first C23 library build failed with no message, and the old library could not be put back.
  altium-log 03:28:54 retry and 03:32:01 error: "Altium stopped in the middle of the script ... Dialogs:
  [TMessageForm] Error". Then "The earlier library could not be put back ([WinError 1224] ... user-mapped section
  open); it is in ...\.advisor-backup\20261127-032526". The page showed no error. After a reload, the BOM said
  "Ready to build" and "31 to verify" (S4-22, S4-39, C78, C85). So the student was told nothing while the installed
  library was in an unknown state. The 03:46 run then showed a true message (intlib_fresh false, in_project false), but
  its remedy is "restart Altium and build again ... Projects panel, right-click the project, Add Existing to Project"
  (S4-40). Those are hand steps in Altium, which a student of this tool should not need. After fix #1, the 03:52:30
  build is clean and its message is honest: built 31 of 31, IntLib fresh, in project, no issues, about 90 s (S4-43,
  C87). Generic cause: a failed build with a failed restore must reach the page as an error, not disappear on reload.
- [FRICTION] The "0 errors" results do not say what they cover. Three different answers report counts in the same
  format:
  - "Check power and ground", 03:12: tool `Check schematic`, "0 power or ground errors".
  - "Review this sheet", 03:19: tools `[]`, a model-only review written as "0 errors, 3 warnings".
  - Schematic check, 04:01 and 04:05: "0 errors, 0 warnings", right after a draw that gave 3 warnings, and while the
    03:19 LED and C13 warnings were still unchanged.

  The script behind them (scripts/checks/schematic.py, docstring lines 8-14) checks only single-pin nets, unconnected
  power pins, dangling labels or ports, and power-named pins on the wrong net. Its power-name test is blind on parts
  with numeric pin names: D1, D2, F1, J3, SW1 and SW2. That is exactly where a VBUS/GND swap on D1 would hide (S3
  FRICTION). Decoupling, EP, pull-ups and crystal caps were checked only by the model's reading, and they happen to be
  right (see TRUE). The 03:12 text "matching U2-U4 and J1-J3" claims more than was checked; its own next line says
  J1 and J2 were not text-checked. Each result should name what it checked and what it did not.
- [FRICTION] The 03:19 model review missed VDDA 10 nF, then reversed itself 2 minutes later. The turn looked up Figure
  43 at 03:15:40 (turns-log) and still reported "0 errors". At 03:21 it said "No, VDDA ... without the 10 nF" and
  added C23 (C71, C73). Electrically this is minor (see the note for the lecturer). The issue is that the same question
  gets two answers depending on how it is asked.
- [FRICTION] Two engineering points that no review raised; both are firmware or README notes:
  - The LSM6DSO shares SCK and MOSI with the flash. While its CS is high (flash traffic), its I2C block is listening on
    the same lines. The datasheet says "In order to disable the I2C block, (I2C_disable) = 1 must be written in
    CTRL4_C (13h)" (LSM6DSOTR.pdf.txt 625). This is not on sheet 02 and not in the notes.
  - SD_CD (J2 pin 9 to PB12) has no pull-up and no note that firmware must enable the internal one. This condition
    was carried from S3. The TF-01A drawing is a scan, so the switch's other side is unverified.
- [FRICTION] The verify messages are wrong or unhelpful, and the stale warnings send the student to dead ends:
  - verify_part on U2 says "pin 12 CS: exposed pad ... pin 13 SCL: exposed pad ... pin 14 SDA: exposed pad"
    (library-log 03:16:38). The LSM6DSO LGA-14 has no exposed pad.
  - On U1 it says "no pin table ... names 6 of its 49", but Table 8 lists all 48 UFQFPN48 pins (I matched them in S3).
  - The Confirm pins dialog opened U1 on p.190 (blank) and p.37 (UFBGA100), not on Table 8 (C80).
  - After the 3-sheet rewrite, the chat said pins of "J3, U2 / U4, J2, D3, D4 are a guess ... confirm in DFM"
    (03:58:48). U2, U4 and J3 had been confirmed at 03:35-03:37, and J2, D3 and D4 are never listed in DFM (S4-56),
    so the student cannot act on it (C89).
- [FRICTION] The citation checker marks the course manuals "not in Sources", although they are in the tool. cites.json
  03:58:36 and 04:01:48 give `missing_file` for m04-navigating-schematics.en.md 4.3.4 and m09-compiling.en.md 9.4.
  Both sections exist in shared/reference/course/ad20-essentials/. scripts/background.py:154-157 looks only in the
  project's Sources folder, so every citation to a GENERAL source is shown to the student as missing (C89).
- [FRICTION] The D1 draw warning is a library-graphic false positive, and the fix the app proposes is a hand edit. The
  C7519 symbol has a polyline from (-11.43, 0) to (11.43, 0) (lib.kicad_sym:163-165) that touches the inner ends of
  pin 2 (GND) and pin 5 (VBUS) and runs through the zener drawing. The draw check reads it as "one terminal".
  Agent 04:01:48: "not shorted, it is a symbol graphic". TRUE: in the drawn connectivity D1-2 is in GND and D1-5 is
  in +5V. The fix it offers ("delete that line in the .SchLib ... Update From Libraries") is a manual Altium step on
  a symbol that the system itself built, and that line also forms the zener's connection. Until the library build
  handles it, the warning will come back on every draw (C90, C91).
- [COSMETIC] The C13 warning "22 uF exceeds the 4.7 uF suggested output cap" (03:19). LDL1117 6.2 (p.10) calls 1 uF
  in and 4.7 uF out "a good compromise" and asks for minimum C and ESR in the stability region. 4.7 uF is not a
  maximum. A 22 uF X5R ceramic is fine, so the word "exceeds" misleads.
- [COSMETIC] The counts disagree:
  - The draw says "38 nets"; the check says "55 nets". 55 is 38 real nets plus the 17 NC pins counted as one-pin nets.
  - At 03:09 the chat said "8 parts" but listed 9 refs; DFM showed 7 (S4-24).
  - The BOM shows "Accepted risk" on U1, U2, U4 and U5, which DFM lists as "Checked by you" (S4-38, C84).
  - library-log keeps `pins_accepted: false` next to an accepted `pin_decision`.
- [COSMETIC] J3 pin 9 (GNDDetect) is left open, and the agent says none of the 17 unused pins must be connected
  (04:05). The Cortex 10-pin convention ties pin 9 to GND on the target. ST-Link does not need it, so this is harmless.
  Y2 is typed `res` in the netlist.
- [FRICTION] Building one new 0402 cap rebuilds and re-flags all 31 lines ("31 to verify", U3 back to "Ready to build",
  C77). A one-line change should not reset the library state of the whole BOM.

## Claims and data checked (TRUE)
- Request at 03:03 vs netlist. All present:
  - EP 49 to GND.
  - VBAT to +3V3, as chosen in Idea: no coin cell, PC sets the time over USB.
  - Decoupling as F411 Figure 17 and Figure 43 ask: C1-C5 5 x 100 nF for VDD 24/36/48 + VDDA 9 + VBAT 1; C11 4.7 uF;
    VDDA C22 1 uF + C23 10 nF; VCAP1 C10 4.7 uF (Table 16 p.64 exists). All caps are on one +3V3 net. Which cap sits at
    which pin is a placement note, not netlist data, so check it in S5.
  - HSE Y1 + C15/C16 5.6 pF; LSE Y2 + C17/C18 2 pF, with the high-drive note on sheet 02.
  - CC1 and CC2 with separate 5.1k resistors (R1, R2).
  - USBLC6 pins 1/6 USB_DP, 3/4 USB_DN, 2 GND, 5 +5V. This matches Figure 1 (USBLC6-2SC6.pdf.txt 50-60).
  - F1 on VBUS, then D2 SMF5.0A with its cathode on pin 1 (+5V). The datasheet gives "Color band denotes cathode"
    (txt 296), and the footprint's silk bar is at pad 1 (C151296 lib.pretty, bar at x -0.51, pad 1 at -1.65).
  - BOOT0: R5 10k pull-down + SW2 to +3V3. BOOT1/PB2: R13 10k pull-down.
  - NRST: C14 100 nF + SW1 + J3 pin 10.
  - SDIO: R6-R10 47k on CMD and D0-D3, none on CLK (within the SD 10-100k range).
  - J3 exactly as asked: 1 +3V3, 2 SWDIO, 3/5 GND, 4 SWCLK, 6 SWO, 10 NRST.
- Pin functions against F411 Table 8:
  - SDIO: CK PB15, CMD PA6, D0 PB7, D1 PA8, D2 PA9, D3 PB5. All are listed SDIO alternates (f411 txt 2305-2675).
  - SPI1: SCK PA5, MOSI PA7, MISO PB4. I2C1: SCL PB8, SDA PB9.
  - USB: PA11/PA12. SWD: PA13/PA14, with SWO on PB3.
  - PA9 used as SDIO_D2 means no VBUS sensing. This is consistent with the Idea text.
- Sensors:
  - LSM6DSO in SPI mode: SCL = SPC, SDA = MOSI, SDO = MISO. CS needs no external pull-up, because "Default: input with
    pull-up" (Table 19). SDx and SCx to GND is allowed ("Connect to VDDIO or GND"). OCS_Aux and SDO_Aux may be left
    unconnected (Table 1, p.7; the agent's 04:05 citation is right).
  - BME280: CSB to VDDIO (I2C), SDO to GND (0x76), 4.7k pull-ups. Each sensor supply pin has 100 nF.
  - W25Q /CS pull-up R14: the quote "If needed a pull-up resister on the /CS pin..." exists (txt 528).
- Draw and cross-sheet claims. "54 parts and 38 nets drawn ... checked against the netlist" and "matching Net Labels
  join globally" are TRUE. schematic.py on netlist/Final-E2E-4L and on Final-E2E-4L.PrjPcb gives the same 55 groups,
  224 pins, 0 single-pin nets apart from the 17 No-ERC pins. BOOT0, BOOT1, FLASH_CS, HSE, I2C and IMU_CS are all
  joined across sheets.
- D1 not shorted: TRUE (above). The D1 and D2 pin answers at 03:37 are TRUE. The cites are `file_only`, but the text
  matches.
- The F411 citations exist: p.77 "Any floating input pin can also settle to an intermediate voltage level" (txt
  4406), and VBAT "should be connected to VDD" (txt 1085).
- The board-area note, "about 1008 mm2 of 1575 = 64%", is arithmetically right. I did not check the 1008 mm2 itself.

## For the lecturer (student decisions, not system faults)
C23 10 nF is harmless, but it was not needed. The existing 100 nF on the same net already gives the high-frequency
part of Figure 43's "1 uF // 10 nF". D3 at about 1.9 mA may be dim; that is a choice. The board size of 45 x 35 mm at
64% fill is carried to S5.

## For S5 and S7 (carried)
- S5: place C1-C5 one per VDD/VDDA/VBAT pin, C22+C23 at pin 9, and C10 at pin 22.
- S7 firmware notes:
  - LSM6DSO I2C_disable.
  - PB12 internal pull-up for card detect.
  - LSE high-drive.
  - Unused GPIO set to analog.
- S7 README: USB DFU is still unverified (AN2606 not in Sources; PA9/PA10 use).
