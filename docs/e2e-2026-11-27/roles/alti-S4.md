# ALTI - Stage 4 (Schematic in Altium)

## Video highlights
- S4-51-draw-warnings-d1-a3.jpg | The system warns D1 pins 2 and 5 are shorted; they are not.
- alti/S4-main-U1.jpg | Good: U1 SDIO, SPI1, I2C1, USB and SWD on the correct STM32F411 pins.
- alti/S4-main-D1-U5.jpg | USBLC6, TVS and LDO are wired correctly, but power nets mix labels and ports.
- S4-50-altium-drawn-54-parts-38-nets.jpg | All 54 parts are in Altium, and the sheets match the netlist pin for pin.

## Scope and method
Checked the 3 SchDocs the system wrote in `C:\Users\Public\Documents\Altium\Final-E2E-4L\` (Main A3, 02 A3, 03 A4),
which are all listed in `Final-E2E-4L.PrjPcb` with the IntLib. All work was read-only:
- `dump.py --full` of each sheet: `alti/S4-dump-*.json`.
- `scripts/checks/schematic.py` on the PrjPcb, compared with the same check on the system's netlist:
  `alti/S4-schcheck.json` and `alti/S4-netlist-tool.json`.
- My own geometry pass over the wires: T-joins, crossings, labels on wires, nets with two names.
- `preview_sch.py` SVGs, viewed in tiles in the browser pane: `alti/S4-*.jpg`. The sheet 03 SVG would not open in the
  pane, so sheet 03 was checked from the data only.

The live Altium instance was not touched, and the system has no Altium compile or ERC command (see FRICTION).

## Findings

- [WRONG] A false short warning on D1. The draw step reports "D1: pins 2 and 5 are one terminal in library symbol
  USBLC6-2SC6 (a line joins them) but the netlist puts them on different nets (+5V, GND)" (S4-51; `altium-log.jsonl`
  03:59:26). The SchLib reader marks USBLC6 `joined: [1,6], [3,4], [2,5]`. Pins 1-6 and 3-4 really are pass-through
  pairs, but the 2-5 "line" has the TVS zener drawn on it, so pins 2 and 5 are GND and VBUS, as in the datasheet.
  Why it matters: a wrong technical claim about a correct part. It cost the student a chat round (S4-52/53), and the
  agent then advised editing the SchLib by hand, which is not needed. System cause: the `joined` detection in the SchLib
  reader, used by `scripts/altium/draw.py:172-176`, takes any polyline between two pin ends as a wire. It ignores a
  diode, zener or other graphic drawn on that line.
- [FRICTION] No ERC run by Altium. "Checked against the netlist" (S4-50) is the system's own SchDoc reader, and
  `bridge.py` has no compile or Validate PCB Project step, so the agent told the student to run it by hand (S4-53).
  I checked the geometry instead: 0 T-joins without a junction, 0 wire crossings, 0 floating labels, 0 nets with two
  names, 0 pins without a connection apart from the 17 with No ERC. Altium's compile should therefore give the same
  nets, but this is not confirmed by Altium. It will be confirmed by the ECO at S5.
- [FRICTION] The sheet notes contradict the pin confirmations. The text frames on the sheets say "pins not checked
  against a datasheet: U2" (sheet 02) and "U4, J2" and "D3, D4" (sheet 03). The BOM says U2 and U4 are accepted and
  J2, D3 and D4 are verified (`bom.json` pins_status), and the student confirmed them before the draw (S4-30..S4-37).
  System cause: when the agent split the design into 3 sheets, `netlist/02.json` and `03.json` were rewritten with
  `pins_source: agent`, and the frame text in `draw.py:1061-1081` reads that field and not the BOM's pins_status.
- [COSMETIC] Power nets are drawn two ways. GND, +3V3, +5V and VBUS appear as purple net labels 47 times and as
  power ports 64 times; for example, U5 pin 1 and J1 pin GND use the net label "GND" (S4-main-D1-U5.jpg,
  S4-main-J1.jpg). Electrically this is fine (one name, one net), but a reviewer expects power ports only.
- [COSMETIC] The layout is label-stub style. Every pin gets a stub and a label, and Y1 and its load caps C15/C16,
  Y2 and C17/C18, and each decap sit in separate islands joined only by name. This is correct, but the crystal and its
  caps, or a decap and its VDD pin, cannot be read as a group. The Main sheet is A3 with much empty space.

## Requirements and lecturer conditions (net by net, from the Altium sheets)
- U1 EP pin 49 is on GND. VSSA (8) is on GND, and VDDA (9) and VBAT (1) are on +3V3. VCAP1 (22) has C10 4.7 uF to
  GND.
- Decoupling: C1-C5 100 nF, C11 4.7 uF, and C22 1 uF + C23 10 nF are all on +3V3/GND. The link of each cap to its
  pin is only a placement note in `netlist/Main.json` (watch at S5).
- PB2/BOOT1 (20) has R13 10k to GND. BOOT0 (44) has R5 10k to GND and SW2 to +3V3. NRST (7) has C14 100 nF, SW1 to
  GND and J3-10.
- Crystals: HSE PH0/PH1 to Y1-1/Y1-3 with C15/C16 5.6 pF, and Y1-2/4 on GND. LSE PC14/PC15 to Y2 with C17/C18 2 pF.
- USB: CC1 and CC2 each have 5.1k to GND (R1, R2). DP/DN go to PA12/PA11 through D1 1-6 and 3-4, with D1-2 on GND and
  D1-5 on +5V. SBU1 and SBU2 are NC with No ERC.
- Power path: VBUS goes through F1 to +5V. D2 has its cathode (pin 1) on +5V and pin 2 on GND. C12 10 uF is on +5V.
  U5 has VIN on +5V, VOUT/tab on +3V3, GND on pin 1, and C13 22 uF.
- SDIO: CK PB15, CMD PA6, D0 PB7, D1 PA8, D2 PA9, D3 PB5. I checked each pin against the alternate-function rows of
  DS10314 Table 8. CMD and D0-D3 have 47k pull-ups (R6-R10), and CK has none, which is correct.
- SPI1: SCK PA5, MOSI PA7, MISO PB4, shared by U2 (CS PA4) and U4 (CS PB1 with the R14 10k pull-up). U4 /WP (3) and
  /HOLD (7) are on +3V3.
- I2C1: SCL PB8 and SDA PB9 with 4.7k pull-ups (R11, R12). On U3, CSB is on +3V3 (I2C mode) and SDO is on GND.
- U2: SDx and SCx are on GND, and OCS_Aux, SDO_Aux and INT2 are NC. Both are allowed by the LSM6DSO pin table
  ("Connect to VDDIO or GND", "Leave unconnected").
- SWD J3 (Cortex 10-pin): 1 VTref, 2 SWDIO PA13, 4 SWCLK PA14, 6 SWO PB3, 10 nRESET, 3/5 GND, and 7/8/9 NC. Pin 9 is
  GNDDetect in the ARM pinout and is usually tied to GND (a lecturer call, not a system error).
- LEDs: PB14 to R3 360 to D3 to GND, and PB13 to R4 680 to D4 to GND. The cathode (pin 2) is on GND.
- microSD CD (J2-9) goes to PB12 without an external pull-up, so it needs the internal pull-up in firmware (watch).

## What is correct (checked)
- The 3 sheets give 54 parts and 55 nets (38 named plus 17 NC singles with No ERC). They match the system's netlist
  pin for pin: 224 of 224 pins, the same nets and the same names, 0 differences.
- Cross-sheet links use global net labels, with no ports and no sheet symbols. The PrjPcb has `HierarchyMode=0`
  (Automatic), which Altium treats as global net labels when a project has no ports or sheet entries. The system's
  reader agrees (`net_scope: global`), and the Kiln run confirmed this behaviour on a board. An Altium-native check
  comes at the S5 ECO.
- The 54 placed parts equal the 54 BOM designators, with no duplicates. MPN, LCSC and footprint match the BOM and the
  library on every part.

## Watch notes
- S5: the ECO must import 55 nets, and Footprint Not Found must be 0 now that the IntLib is back in the project
  (03:52 build).
- S5: the decap-to-pin assignment lives only in the notes, so check that C1-C5, C22 and C23 land beside VDD and VDDA.
- The S3 library findings (3D bodies of J1/J2, no courtyard, EP paste) are still valid after the 03:52 rebuild: the
  same footprints were rebuilt, and only C23 was added. A new PcbLib dump (`alti/S4-pcblib-full.txt`) has 21 footprints
  with pads and extents identical to S3.

## Follow-up: inter-sheet connectivity (04:40)

**Verdict: CONNECTED.** Altium compiled the project itself, and every cross-sheet net is one net. The compiled
netlist equals the system's netlist exactly.

Evidence:
- **Net identifier scope.** `Final-E2E-4L.PrjPcb` line 3 says `HierarchyMode=0`, which is Automatic. There is no
  `NetIdentifierScope` override. The project has no sheet symbols and no ports: each `S4-dump-*.json` shows
  `ports: 0`, and no sheet holds a sheet symbol. With that content, Automatic resolves to Global, so net labels and
  power ports are project-wide.
- **How names cross sheets.** All cross-sheet signal names are net labels: Main 64, sheet 02 48, sheet 03 29. GND and
  +3V3 are drawn both as net labels and as power ports, which are also global. The app's note in S4-46 ("does not
  yet draw nets that need ports") is true, but no ports are needed with this scope.
- **Native compile.** I ran a read-only DelphiScript (`alti/S4-AltiNets.pas`) in the shared Altium. It calls
  `DM_Compile`, reads `DM_DocumentFlattened`, and writes `alti/S4-altium-compiled-nets.txt`. It saves nothing to the
  project. The compile saw all 6 documents (3 SchDocs, PcbDoc, IntLib, ActiveBOM).
  - Result: `NETCOUNT 55` and 224 pins.
  - Compared with the system's netlist: 0 nets split, 0 nets merged, 0 name differences.
  - 29 nets span at least two sheets: SWDIO, SWCLK, SWO, SPI1_SCK, SPI1_MOSI, SPI1_MISO, SDIO_CK, SDIO_CMD,
    SDIO_D0..D3, SD_CD, NRST, HSE_IN, HSE_OUT, LSE_IN, LSE_OUT, LED1, LED2, IMU_CS, IMU_INT1, I2C1_SCL, I2C1_SDA,
    FLASH_CS, BOOT0, BOOT1, GND and +3V3.
  - Sample nets:
    - `HSE_IN: C15-1 U1-5 Y1-1` (Main to 02)
    - `NRST: C14-1 J3-10 SW1-1 SW1-2 U1-7`
    - `SPI1_SCK: U1-15 U2-13 U4-6` (3 sheets)
    - `SDIO_D0: J2-7 R7-2 U1-43`
    - `I2C1_SDA: R12-2 U1-46 U3-3`
    - `BOOT1: R13-1 U1-20`
    - `GND`: 62 pins on all 3 sheets
- **"NC" is not a net.** The netlist JSON gives 17 pins the net "NC" (Main 11, sheet 02 6). On the sheets these are
  17 No ERC markers (Main 11, 02 6, 03 0), and no net label is named NC. Altium compiled them as 17 separate
  single-pin nets: NetU1_2, NetU1_10..13, NetU1_21, NetU1_31, NetU1_38, NetU1_42, NetU2_9..11, NetJ3_7..9,
  NetJ1_A8 and NetJ1_B8. Nothing joins them.
- **Side effect, recovered.** My first launch attempt left an Altium "Select Item To Run" box and a message box open,
  which blocked the bridge (`executor: blocked`). I closed them: the dialogs through `bridge.release_executor()`, and
  the script selector with WM_CLOSE, which is the same as its close button. `bridge.py status` is `executor: ok`
  again. A Windows "Sign in required" (work account) prompt is on screen. It does not belong to Altium, and I did not
  touch it.
- Still not run: Altium's ERC messages (violations). The compile ran, but I did not read the violation list.

## Round 2: Main redrawn with R15 (05:33), native compile again (05:40)

**Verdict: still CONNECTED and identical to the system netlist. Nothing was lost in the redraw.**
- **Native compile.** I ran the same read-only `S4-AltiNets.pas`, writing to `alti/S4-altium-compiled-nets.txt`.
  Round 1 is kept as `alti/S4-altium-compiled-nets-r1.txt`.
  - Result: `NETCOUNT 55` and 226 pins (round 1 had 224).
  - Compared with the system netlist (`alti/S4r2-netlist-tool.json`): 0 pin differences, 0 nets split, 0 nets
    merged, 0 name differences.
- **Changes from round 1.** Only these changed:
  - R15-1 and R15-2 were added.
  - U1-31 (PA10) moved from the NC single `NetU1_31` to the new net `PA10: R15-2 U1-31`.
  - R15-1 is on +3V3.
  Every other pin keeps its round-1 net, so the 29 cross-sheet nets are unchanged and each is still one net.
  The net count stays 55 because the PA10 net replaces NetU1_31.
- **Parts per sheet** (round 1 to round 2, from new `dump.py` runs):
  - Main: 19 to 20 (only R15 added), No ERC markers 11 to 10.
  - Sheet 02: 20 to 20, No ERC 6 to 6. Its file was not rewritten (still 03:59).
  - Sheet 03: 15 to 15, No ERC 0 to 0. Its file was not rewritten (still 03:59).
  - No ports on any sheet.
  - R15 on the sheet: 0402WGF1002TCE, 10k, R0402, LCSC C25744, which matches the BOM line R5/R13/R14/R15.
- **Checks.** The system's check on the Altium sheets and on its netlist reports 0 errors, 0 single-pin nets, and
  16 pins with No ERC.
- **Draw warnings (05:33 log).** The only warnings are A3 for Main and the same false D1 "pins 2 and 5 one
  terminal" warning. There is nothing new.
- **Executor.** `bridge.py status` gives `executor: ok` after the run, with no dialogs left open.
