# ALTI - Stage 5 (Placement in Altium)

## Video highlights
- alti/S5-stack.png | Asked JLC04161H 1.6 mm; PcbDoc holds Altium defaults: 3 x 0.32 mm FR-4, 1.10 mm.
- alti/S5-placement.png | Corner "keep-outs" are unnetted TOP copper squares, not keep-outs.
- alti/S5-placement.png | VCAP1 cap 15.7 mm, VDDA 1uF 20.9 mm, SD bulk 28.4 mm away.
- alti/S5-placement.png | Good: USB-C and microSD on opposite short edges, nothing overlaps, all on top.

## Scope and method
Read-only on `C:\Users\Public\Documents\Altium\Final-E2E-4L\Final-E2E-4L.PcbDoc` (saved 05:58 by place-pcb, replace=true).
`dump.py --full` gives `alti/S5-pcbdoc.json`. `pcbdoc.read_pcbdoc(geometry=True)` gives 3D body and outline boxes
(`alti/S5-bodies.txt`). Board6 and Regions6 records were read raw for the stack and the keep-outs. Distances are
pad centre to pad centre (`alti/S5-analysis.txt`). Images are PIL renders of those numbers (`alti/S5-placement.png`,
`alti/S5-stack.png`). No Altium command was run and nothing was moved. `checks/board.py --json` was run on the file (`alti/S5-boardcheck.json`).

## Findings

- [WRONG] The layer stack is 4 copper layers but not JLC04161H. Board6 `LAYER_V8_*` holds Top, Mid-Layer 1,
  Mid-Layer 2 and Bottom, all with Cu 1.4 mil (35.6 um), and three dielectrics of 12.6 mil (0.32 mm) FR-4, Er 4.8.
  There is no core or prepreg distinction, and copper plus dielectric totals 1.10 mm. JLC04161H-7628 is 35 / 15.2 /
  15.2 / 35 um copper, 0.2104 mm 7628 prepreg (Er 4.4), and a 1.065 mm core (Er 4.6), about 1.6 mm in all
  (`alti/S5-stack.png`). Why it matters: Altium's impedance calculator, the board thickness in 3D and STEP, and any fab
  drawing all use 1.10 mm and the wrong dielectrics. If S6 derives USB D+/D- widths for 90 ohm from this stack, they will be wrong. The order
  itself is less affected: JLC builds its own stack when JLC04161H is chosen. System cause: in `PcbStack`
  (`scripts/altium/bridge/AdvisorBridge.pas`, the four `StackLayerProps(...)` lines just before the final `StackWalk`),
  the calls that set the JLC numbers are commented out. Only `InsertInStackBelow` runs, so Altium's default layer
  properties stay. Yet the procedure's header and `ensure_stack`'s docstring (`bridge.py:1434`) both promise
  JLC04161H. `ensure_stack` checks only the copper count (`copper_layer_count`), so this is never detected.
- [WRONG] The four "keep-outs" KO1-KO4 are not keep-outs. Each is saved as an unnetted copper region on the TOP layer.
  Regions6 record: layer byte 1, `V7_LAYER=TOP`, `KIND=0` (copper), keep-out flag byte 0. The 7 x 7 mm squares cover
  each corner, and the 3.2 mm hole of H1-H4 goes through them. Their four outline tracks are on layer 0 (no layer):
  the track's V7 layer id is 16973824, the null id the stack uses for an empty NEXT/PREV, not 16973837 (Keep-Out Layer).
  Board6 also says `Keep-Out Layer USEDBYPRIMS=FALSE`: no primitive in the file is on the keep-out layer
  (`alti/S5-placement.png`, orange). Why it matters: inside Altium (native DRC, polygon pours, manual or Altium
  routing) nothing keeps copper and vias away from the screw heads on Mid-1, Mid-2 and Bottom. Whether the system's own
  router honours its `ko_*` constraints is unverified. Top gets four floating copper islands, which DRC and the pour will treat as copper, not
  as forbidden area. The placer did keep parts out of the squares, so the problem is invisible in the app. System
  cause: the spec says `REGION|Keep-Out Layer` and `TRACK|...|Keep-Out Layer` (`library/build/altium/footprints_spec.txt`
  lines 397-420). `LayerOf` (`AdvisorBridge.pas` ~line 797) passes that name to `String2Layer`. That this gives 0 is inferred from the
  saved result, not run in isolation. The function's own comment says this already happened with 'Multi-Layer'. The tracks keep layer 0, and the region
  ends on Top (most likely the default; not traced further). A real keep-out needs `eKeepOutLayer` (or the
  primitive's keep-out flag on each copper layer).
- [WRONG] C10 (4.7 uF, BOM role "VCAP1 capacitor") is 15.7 mm from U1 pin 22 (VCAP1), on the far side of U4. The
  place-pcb log gives no warning for it, but `checks/board.py`, run by me on the saved board, does report it
  (`decap_distance_excessive`, limit 5 mm, `alti/S5-boardcheck.json`). So the placer and the board check disagree. ST asks for this cap at the pin; with a long trace the core regulator can be unstable.
  Generic cause, partly verified: `decap_hints` (`scripts/altium/layout.py:1773`) ties a cap to a pin only when its role
  names a PART or a regulator. "VCAP1" is a pin name, so the cap got no hint. `_SUPPLY_PIN` (`layout.py:90`) does
  count VCAP as a supply pin, and 4.7 uF is below `BULK_F` (10 uF). Why the fallback neither placed C10 by pin 22
  nor warned about it is unverified.
- [WRONG] VDDA (U1 pin 9): C22 (1 uF, role "VDDA bulk") is 20.9 mm away beside U2, and C23 (10 nF, role "VDDA
  high-frequency") is 7.0 mm away. Only C20 (100 nF) is close, at 2.6 mm. The student asked for 1 uF + 10 nF at
  VDDA, and the analog supply of the ADC and oscillators is not decoupled as designed. No warning was given. Cause:
  the same role-to-part matching. The roles name the pin, so C22 was used as an ordinary +3V3 cap for the nearest
  free supply pin (U2-5, 3.0 mm).
- [WRONG] The microSD supply has no decoupling nearby. C19 (10 uF, BOM line "LDO input / SD card bulk") is 2.9 mm from
  U5 VOUT and 28.4 mm from J2 pin 4 (VDD). The nearest 100 nF to J2-4 is C2, at 10.9 mm. SD cards draw current peaks of
  about 100 mA or more when written, so the bulk cap belongs at the socket. Cause: one BOM line carries two jobs for
  C12 and C19. The "LDO input" clause matches the regulator hint, so C19 (on +3V3, with no LDO input pin there) falls
  back to U5's output pin. Also, a connector (J) is never a decap target (`_DECAP_IC = ^(?:U|IC|M|MOD)\d`, `layout.py:1683`), so "SD" in the role cannot win.
- [WRONG] The HSE crystal Y1 (25 MHz) is 7.3 / 8.1 mm from U1 pins 5 and 6, on the right of U1. Its load caps C15 and
  C16 are about 10 mm from the MCU. The LSE crystal Y2 got the spot right under pins 3 and 4 (3.6 / 3.9 mm). ST AN2867
  says to keep HSE traces short with the load caps by the crystal. The system did warn at 5 mm ("Y1 is 8.1 mm from U1
  pin 6"), but it still saved this plan.
- [FRICTION] The app's agent cannot see the stack. The agent told the student it does not know the PcbDoc stack, although
  `STACKINFO` (READ_ONLY in `bridge.py:290`) and `pcbdoc.copper_layer_count` exist. Only `preview_pcb.py` and
  `jlc_upload.py` use them, and no agent tool exposes them. A student cannot confirm "4 layers, JLC04161H" from the
  app (and would see the problem above if one did).
- [FRICTION] The J3 warning asks the student to confirm in 3D which way the connector opens. J3 is a vertical 2x5
  1.27 mm SMD header (`HDR-SMD_10P-P1.27-V-M`, 5.5 mm tall): it opens upward and has no side to turn. The placer
  treated it as an edge connector and put it on the bottom edge with its pads 0.30 mm from the board edge. That is
  below `checks/board.py`'s own 0.5 mm outline check and at JLC's "> 0.3 mm" assembly limit. It is not in the place-pcb warnings, and `checks/board.py` run on the saved board
  does not report it either.
  Its 3D body is correct: centred on the pads (body 52.45..58.80 x 26.10..31.60 vs pads 52.71..58.53 x 25.70..32.00),
  ROTZ 0, 5.5 mm high.
- [FRICTION] C14 (NRST 100 nF) is 9.3 mm from U1 pin 7 and 6.5 mm from J3 pin 10. C13 (22 uF LDO output) is 4.9 mm from U5
  VOUT. The C13 case was warned, and C19 sits 2.9 mm from that pin, so the LDO output is covered.
- [COSMETIC] The J1 and J2 3D bodies (S3 finding) now show in place. The J1 body is at x 28.39..36.29, 2.5 mm inside
  the board, while the real outline is at 25.90..31.35 (0.5 mm from the left edge). The J2 body is at x 64.71..79.72,
  about 5 mm inside, while the real outline is at 69.81..84.89 (0.5 mm from the right edge). The 3D view and STEP show
  both sockets sunk into the board. The copper is right.

## What is correct (checked)
- 4 copper layers in the right order (Top, Mid-Layer 1, Mid-Layer 2, Bottom), with component placement allowed on
  Top and Bottom only.
- Outline: Mech 1 rectangle 25.4..85.4 x 25.4..70.4 mm = 60 x 45 mm. The BoardRegions shape is the same box.
- H1-H4: NPTH 3.2 mm (M3 clearance) at 3.49-3.51 mm from both edges, in all four corners. A 7 x 7 mm area is the right
  size for an M3 head with washer, if it were a real keep-out (see above).
- USB-C J1 on the left short edge, and microSD J2 on the right short edge, both openings facing out. The real
  outlines end 0.5 mm inside the edge. D1 (USBLC6) is 2-3 mm from J1, and F1 and D2 are on the VBUS/+5V path near J1.
- All 63 components (55 parts + H1-H4 + KO1-KO4) are on TOP. All pads and 3D bodies are inside the outline. No two
  parts' pad boxes are closer than 0.5 mm. No 3D bodies overlap. The board carries 39 named nets, PA10 (round 2) included; a full net-by-net compare with S4 was not done.
- Every U1 VDD pin (1, 24, 36, 48) and pin 9 has a 100 nF within 2.1-2.9 mm. U3 and U4 have a 100 nF at 2.2-2.7 mm of
  every supply pin. U2 pin 8 has C4 at 2.7 mm, but U2 pin 5 is served only by C22 (the misplaced VDDA 1 uF, 3.0 mm). Its
  nearest 100 nF is C4, at 4.4 mm. C12 is 2.9 mm from U5 VIN. Y2 (LSE) is 3.6 / 3.9 mm from U1 pins 3 and 4.

## Watch notes for later stages
- S6/S7: the rules are still Altium's new-board defaults. HoleSize max is 100 mil (2.54 mm), so the four 3.2 mm holes
  will fail DRC unless the system sets its own rules. Width and DiffPairs are 10 mil fixed, and Clearance is 10 mil.
- S6: if the keep-outs are not fixed, check that no via or pour goes under the screw heads. Also check that the four
  floating Top squares do not turn up as DRC or "dead copper" items.
- S7: the board thickness in the fab outputs and 3D comes from the stack above (1.10 mm), not 1.6 mm.
