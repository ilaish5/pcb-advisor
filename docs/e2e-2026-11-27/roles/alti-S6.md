# ALTI - Stage 6 (Routing and DRC in Altium)

## Video highlights
- alti/S6-crystal.png | IMU_CS via in the middle of the 25 MHz crystal; SWD lines under 32 kHz.
- alti/S6-routing.png | Student set 0.5 A; +5V/VBUS drawn 0.127 mm, thinner than every signal.
- alti/S6-routing.png | 421 DRC: 83 real (untented vias by pads), 5 borderline (J3), rest noise/silk.
- alti/S6-mid-planes.png | Good: solid GND pour on Mid-1, no open nets, no shorts, no clearance errors.

## Scope and method
Read-only on `Final-E2E-4L.PcbDoc` (06:36, route-pcb second try, 730 tracks, 153 vias). Placement is identical to S5
(0 parts moved). KO1-KO4 are gone: the first route at 06:24 gave 4 Short-Circuits "Pad H1 ... And Region ... Top Layer",
which confirms the S5 finding that the keep-outs were Top copper. The route was rolled back. At 06:30 the board was re-placed
without the KO parts (the log does not say whether the app or the student dropped them), then routed again. I ran Altium's DRC through the bridge's read-only `DRC` command
(`alti/S6-drc.txt`, 421 violations, report complete). The executor was ok before and after. Afterwards the PcbDoc still had its 06:36:00 timestamp, and no new file was in the
Altium project folder (the report went to `alti/`).
`dump.py --full` gives `alti/S6-pcbdoc.json`. The geometry checks are in `alti/S6-analysis.txt`.
The images are PIL renders of the dump.

## DRC table (421)

| Rule (Altium) | Count | What it is | Class |
|---|---|---|---|
| Minimum Solder Mask Sliver, pad-via, dam < 0.10 mm | 71 | untented via next to an SMD pad; JLC drops a dam below 0.10 mm, so pad and via share one opening | **REAL** (assembly) |
| Minimum Solder Mask Sliver, via-via, dam < 0.10 mm | 12 | two untented vias, merged opening | **REAL** (same cause) |
| Minimum Solder Mask Sliver, pad-via / via-via, >= 0.10 mm | 54 | below Altium's 6 mil rule, above JLC's 0.10 mm | rule noise |
| Minimum Solder Mask Sliver, pad-pad inside one part | 115 | U1 92, J1 13, U2 10: 0.5 mm pitch pads with 2 mil mask expansion; only J1's 11 are under 0.10 mm (0.098) | footprint/rule noise |
| Silk To Solder Mask (6 mil) | 157 | 72 designators + 85 silk outline pieces over via openings or pad openings; the fab clips the silk | cosmetic (side-effect of untented vias + designator placement) |
| Board Clearance, pad | 5 | J3 pads 1,3,5,7,9 at 0.30 mm from the bottom edge (rule 12 mil = 0.3048 mm; JLC asks > 0.3 mm for assembly, JLCDFM warns only below 0.2 mm) | borderline (S5 placement) |
| Board Clearance, text | 2 | designators "H3", "H4" cross the top edge | cosmetic |
| Minimum Annular Ring (8 mil, IsPad) | 4 | J1 shell tabs: ring 0.200 mm = 7.874 mil; JLC multilayer recommends 0.20 mm, min 0.15 | rule noise (8 mil = 0.2032 mm; meets JLC) |
| Silk to Silk | 1 | designators C10 / R3 | cosmetic |
| Clearance, Short-Circuit, Un-Routed, Width, Hole Size, Hole-to-Hole, Net Antennae, Modified Polygon | 0 | clean | - |

One test for every row: JLC's own figure, not the Altium rule value. Totals: 83 REAL (one cause), 5 borderline, 173 rule
or footprint noise, 160 cosmetic. The 4 shorts of the first try (KO copper)
are gone because the keep-outs were dropped, not fixed. Nothing is left from the stack defect in this DRC, since DRC
does not check the stack.

## Findings

- [WRONG] The crystals are routed against ST AN2867. Y1 (HSE 25 MHz) has an IMU_CS via exactly in its centre
  (61.0, 39.5), 0.18 mm from all four pads. IMU_CS (Top and Mid-2), SDIO_CMD (Mid-2) and BOOT1 (Bottom) run under its
  body. HSE_IN is 23.6 mm, 14.6 mm of it on Bottom, with 2 vias. HSE_OUT is 10.9 mm, 3.9 mm of it through the Mid-2 +3V3
  plane layer, with 2 vias. Y2 (LSE 32 kHz, very high impedance) has SWDIO on Top and SWCLK/SWO on Bottom under it
  (`alti/S6-crystal.png`). Why it matters: crosstalk into the oscillator, startup or jitter problems, and a 48 MHz USB
  clock taken from a noisy HSE. AN2867 asks for short traces with no vias, a GND guard and no signals under the crystal.
  Probable system cause: a grep of `scripts/altium/route.py` and `negotiate.py` finds no crystal/xtal handling.
  The router has no keep-out under crystal bodies and no rule against vias or layer changes on crystal nets. This adds to the S5 placement (Y1 8 mm from U1).
- [WRONG] VCAP1 is routed 17.4 mm (15.6 mm on Bottom) with 2 vias from C10 to U1 pin 22. That is the S5 placement defect
  (C10 15.7 mm away) now made physical. ST asks for VCAP1's cap at the pin (low ESR). A long, via-laden path risks
  instability of the 1.2 V core regulator.
- [WRONG] Vias are untented next to pads. The SolderMaskExpansion rule has `EXPANSION=2mil, ISTENTINGTOP=FALSE`, and the
  DRC sliver lines show vias with mask openings. The tenting flag was not read via by via. 68 distinct vias (71 pad-via pairs)
  are within 0.16-0.20 mm of an SMD pad (decap vias,
  which is good for inductance). Their mask dam is below JLC's 0.10 mm, so pad and via share one opening. In addition, 9 distinct
  bare vias sit within 0.2 mm of a pad of a DIFFERENT real net: the IMU_CS via in Y1, U2-12 vs SPI1_SCK at 0.168 mm,
  U2-14 vs SPI1_MISO, U4-7 +3V3 vs SDIO_D0, J1-B5 CC2 vs VBUS, R12-2 vs +3V3, R6-2 vs IMU_INT1, C20-1 vs NRST, and U1-35 vs SWDIO. JLC's own rule for bare vias with HASL is >= 0.2 mm from exposed copper. Why it
  matters: solder wicks into the via (starved 0402 joints, tombstones), and there is a bridge risk where the nets
  differ. System cause: the rule setup leaves vias untented. Tenting the vias (or a via-to-pad rule of 0.2 mm) fixes all 83
  DRC lines and the 9 at once.
- [WRONG] The power traces are thinner than the signals. The student set +3V3 0.3 A, +5V 0.5 A and VBUS 0.5 A at
  06:16. `net_current_rows` says "IPC-2221 ... needs 0.115 mm, board minimum 0.127 mm used". All +5V (22.5 mm) and
  VBUS (10.4 mm) are 0.127 mm (5 mil), while every signal is 0.2032 mm. Thermally it passes (IPC-2221, 10 C rise).
  The drop is about 43 mV on +5V at 0.5 A. But this is a fab-minimum trace for the USB input feeding the LDO and the
  TVS path, and it leaves no etch margin. Generic cause: `netcurrent.net_widths` sets `w = max(need, wmin)`
  (the IPC width or the board minimum). The rail default (`RAIL_DEFAULT` in `netcurrent.py`, `POWER_WIDTH = 0.3` at `route.py:41`; used only when no
  current is set) is lost once a current is set. So entering a current made the rails narrower than leaving it blank.
- [WRONG] The inner pours are closer than JLC allows to the M3 holes. Both the Mid-1 GND and the Mid-2 +3V3 pour stop
  about 0.16 mm from the 3.2 mm NPTH wall of H1-H4. That is the 6 mil Clearance rule (0.152 mm), and 0.161 mm
  at the polygon vertices. JLC asks NPTH to copper >= 0.2 mm and removes 0.2 mm around NPTHs, so this is a DFM miss,
  not a short. Cause: the S5
  keep-outs (7 x 7 mm, the right size) never became keep-outs and were then removed, so nothing pushes copper away.
  The Top and Bottom layers are clear: no track or via within 3.5 mm of any hole centre.
- [FRICTION] USB D+/D- are not routed as a pair. D+ is 33.4 mm, all Top. D- is 36.0 mm, with 5.8 mm on Mid-2 (+3V3
  plane layer) and 2 vias. They run within 0.6 mm of each other for only 9.8 mm. Both are 0.2032 mm. The
  DiffPairsRouting rule (10 mil) is in the board but no diff-pair class is used. At USB Full-Speed (the F411's only
  mode) and 36 mm, this works. It is not a 90 ohm coupled pair (a checklist item, not a request found in `idea.json`). Any width Altium computed
  would be for the wrong stack: re-read now, it is still 4 x 1.4 mil Cu and 3 x 12.6 mil FR-4, the S5 defaults.
- [FRICTION] The Mid-2 +3V3 "plane" also carries 36 signal segments (BOOT0 7, SDIO_D0 6, USB_DN 4, LED2 4,
  SDIO_CMD 4, IMU_CS 3, IMU_INT1 3, HSE_OUT 3, SWDIO 2), which slot the pour (`alti/S6-mid-planes.png`). Mid-1 GND
  is clean, with no signal tracks. The planes are real poured polygons: 2 polygons give 2 regions, so each pour is
  one connected piece (GND 266 cut-outs, +3V3 200), with remove-dead on, 0.3 mm back from the edge. Signals on Bottom reference the cut +3V3 pour, not GND.
- [FRICTION] The app only gives a manual checklist for 421 DRC lines, of which 88 matter. The system already parses
  every line (`parse_drc`). Sorting them like the table above (dam below JLC 0.10 mm, J3 edge) would let the student
  act without reading 421 lines.
- [FRICTION] J3 SMD pads are 0.30 mm from the bottom edge (5 DRC lines, rule 0.3048 mm). That is at JLC's assembly limit
  ("> 0.3 mm") and above JLCDFM's 0.2 mm warning, so it is borderline, not a fab stop. It comes from the S5 placement
  that treated a vertical header as an edge connector.
- [FRICTION] Some via counts are high for 2-pin nets: IMU_CS and IMU_INT1 have 4 vias each, LED2 3, and the SDIO, SPI and
  SWD nets 2 each. These are extra layer changes, mostly forced by the dense middle.
- [COSMETIC] There are at least 4 true acid traps (counting end-to-end joins only) (45 degree joins on +3V3 at 48.8,51.9 and on GND at 41.9,53.7 / 44.4,51.6 /
  47.7,35.6). There are also 9 identical duplicate GND segments stacked at 54.8-55.0, 37.1-37.5 (U1 bottom),
  which is redundant copper. The U1 exposed pad has no via in it. It reaches GND through 5 Top tracks to vias
  outside, which works electrically but gives no thermal via field.

## What is correct (checked)
- 39/39 nets routed. DRC has 0 shorts, 0 clearance, 0 un-routed, 0 width and 0 hole violations. The Hole Size rule is now
  12-248 mil (the S5 watch note is fixed).
- GND: a solid poured polygon on Mid-1 under all Top routing, with 47 GND vias. +3V3: a pour on Mid-2 with 37 vias.
  Most decaps have their own plane via 0.16-0.5 mm from each pad, a short loop (`S6-analysis.txt`). The exceptions
  are C1, C9, C20 and C21 by U1, whose vias are 1.0-1.9 mm away, so they reach the plane after the pin. That is
  acceptable.
- Vias are 0.3/0.6 mm (JLC standard), and none are in pads.
- LSE traces are 4.5 / 6.6 mm, Top only, with no vias. No copper is within 3.5 mm of the hole centres on Top and Bottom.

## REAL issues: 4
1. Crystal area: via in Y1, signals under Y1 and Y2, HSE nets through 2 layers.
2. VCAP1 path 17.4 mm with 2 vias.
3. Untented vias: 83 DRC dams below 0.10 mm, plus 9 bare vias by a different-net pad.
4. Inner pours about 0.16 mm from the M3 holes (JLC 0.2 mm; there is no keep-out).

J3 at the edge is borderline, not counted.

The 0.127 mm power traces are WRONG as practice but not counted as real: they pass IPC-2221 at the set current.

## Round 2 (re-route 07:13 with the student's Rules)
Read-only check of the PcbDoc saved at 07:12:58 (`alti/S6r2-pcbdoc.json`). I ran a new DRC through the read-only bridge
command (`alti/S6r2-drc.txt`) and geometry checks (`alti/S6r2-analysis.txt`). The board's timestamp did not change, no
new file appeared in the project folder, and the executor was ok before and after.

- **Widths:** +5V 0.400 mm (13 segments, 22.8 mm) and VBUS 0.400 mm (11 segments, 10.8 mm) are fixed, under the new
  rule `Power_Width` (InNet('+5V') or InNet('VBUS'), min 0.30, preferred 0.40, max 0.60 mm). **+3V3 is still
  0.127 mm** (68 segments, 40.9 mm). It mostly runs pad-to-via to the Mid-2 pour, so this matters less, but it is still
  thinner than the 0.2032 mm signals. GND is 0.2032 mm.
- **Connectivity:** 0 shorts, 0 un-routed, 0 clearance and 0 width violations. 762 tracks and 157 vias. Mid-2 +3V3 is now
  two regions: the main pour plus a 1.8 x 6.7 mm island at 57.1-58.8 x 38.2-44.9 by U1. Remove-dead is on and nothing is
  un-routed, so the island is connected.
- **DRC 424, classified as before.** One test for every row: JLC's own figure.

| Rule | Round 1 | Round 2 | Class |
|---|---|---|---|
| Mask sliver pad-via / via-via, dam < 0.10 mm | 71 + 12 = 83 | 71 + 15 = **86** | **REAL** (untented vias) |
| Mask sliver pad-via / via-via, >= 0.10 mm | 54 | 51 | rule noise |
| Mask sliver pad-pad inside one part (U1, J1, U2) | 115 | 115 | footprint/rule noise |
| Silk To Solder Mask | 157 | 160 | cosmetic |
| Board Clearance J3 pads | 5 | 5 | borderline |
| Board Clearance H3/H4 text | 2 | 2 | cosmetic |
| Annular ring J1 (0.200 mm vs 8 mil) | 4 | 4 | rule noise |
| Silk to Silk | 1 | 1 | cosmetic |

  The REAL DRC count rose from 83 to 86 (same single cause). The number of real issues is unchanged at **4**.
- **Hole clearance rule: none.** The board has HoleSize (12-248 mil), HoleToHole (8 mil, 18 mil pad-pad) and
  BoardOutlineClearance (12 mil). The Clearance rule is a plain 6 mil with no object-specific clearances, and there is no
  keep-out at H1-H4. Both inner pours are still about 0.16 mm from the M3 hole walls (JLC asks 0.2 mm). Real issue 4
  stands.
- **Via tenting: still untented.** SolderMaskExpansion is `EXPANSION=2mil, ISTENTINGTOP=FALSE`, unchanged. 10 distinct
  bare vias sit within 0.2 mm of a pad of a different real net. New ones include a VBUS via beside J1-B6 (USB D+), a
  BOOT0 via by C8-2, SPI1_MOSI by U1-24 (VDD), SDIO_D3 by J3-10, and SDIO_D0 beside Y1-4.
- **Crystal area, better but not fixed.** The via in the middle of Y1 is gone. Under Y1 there are still IMU_CS (Mid-2),
  SDIO_CMD (Top), and BOOT1 and SDIO_D0 (Bottom). Under Y2 are SWDIO (Top) and SWCLK/SWO (Bottom). HSE_IN is now 13.1 mm on
  three layers with 3 vias (was 23.6 mm, 2 vias). HSE_OUT is 10.7 mm with 2 vias. VCAP1 is unchanged: 17.4 mm, 2 vias.
  USB D+ and D- each have 2 vias now, and D- still runs 5.1 mm on Mid-2.

**Round 2 verdict:** +5V and VBUS are fixed at 0.4 mm, and +3V3 is still 0.127 mm. There are still 0 shorts and 0
un-routed. The REAL DRC lines went from 83 to 86. The 4 real issues remain: the crystal area, the VCAP1 path, untented
vias, and the M3 hole clearance with no rule.

## P5 (lecturer condition, before S7) - route #3
Route #3 is the PcbDoc saved at 07:12:58. Its dump is byte-identical to Round 2 (`alti/S6p5-pcbdoc.json`, checks in
`alti/S6p5-analysis.txt`). Read-only, and the executor is ok.

- **(a) Crystal area: NOT met.** No via is inside either crystal's pad area anymore (the Round 1 IMU_CS via in Y1 is gone).
  Foreign signals still run under the crystals:
  - Y1 (HSE): SDIO_CMD on Top, IMU_CS on Mid-2, and BOOT1 and SDIO_D0 on Bottom.
  - Y2 (LSE): SWDIO on Top, and SWCLK and SWO on Bottom.
  - Y1-4 (GND) has a bare SDIO_D0 via within 0.2 mm.
- **(b) Pour to M3 NPTH: NOT met.** At all four holes H1-H4, the Mid-1 GND pour and the Mid-2 +3V3 pour edge are 0.161 mm
  from the 3.2 mm hole wall (polygon vertices, from the 6 mil Clearance rule). JLC asks >= 0.2 mm, and there is no
  keep-out or hole-specific rule. Top and Bottom have no copper near the holes.
- **(c) +5V / VBUS continuity: met.** Every routed segment is 0.400 mm: +5V has 13 and VBUS 11, with no arcs and no
  0.127 mm or other necks. +5V is one connected piece: F1-2, U5-3, C12-1, D1-5 and D2-1, with 2 vias. VBUS runs J1-A4B9
  and J1-B4A9 → 2 vias → Bottom → F1-1. One joint at (34.3-34.4, 50.5-50.6) is two 0.4 mm segments that overlap rather
  than share an endpoint, so the copper is continuous. DRC reports 0 un-routed.

**P5 verdict:** (c) is met, and (a) and (b) are not. The crystal via is fixed, but signals still pass under Y1 and Y2, and
the inner pours are still 0.16 mm from the M3 holes.
