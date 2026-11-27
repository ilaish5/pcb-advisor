# Engineer review, Stage 7 (Outputs), system side in the browser

## Video highlights
- S7-03-outputs-generated-21-files-2-warnings.jpg | Gerbers made with 424 DRC lines open; the page names only U1. Outputs dot green.
- S7-08-agent-added-all-to-notes.jpg | The order note says "Tent vias", but the mask Gerber has 157 open vias.
- S7-07-agent-says-no-readme-added-notes.jpg | No README output: bring-up and stack notes live only in notes.md.
- S7-06-bom-and-cpl-exported-toast.jpg | All 55 parts with an LCSC code; CPL and Gerber share one frame.

Scope:
- Outputs page (S7-01..08) and chat 06:59-07:29 (entries 133-145).
- `roles/student.md` S7 and confusions C131-C137.
- `exports/` (BOM_jlc.csv, cpl.csv, gerbers.zip, order_manifest.json), outputs-check.json, notes.md and bom.json.
- Altium's own "Project Outputs" folder.
- The PcbDoc stack fields (Board6, read-only).
- scripts/skills/export_cpl.py, stages.outputs_stage, store.manufacturing_block, AdvisorBridge.pas PcbStack.

Engine: Claude Code / Opus for this page; Antigravity for chat 133-140.

## Correction to my S5 and S6 reports
In S5 (WRONG 1 about the stack) and S6 (USB finding) I wrote that the board file stack IS JLC04161H-7628. That was wrong.
I read the code comment at AdvisorBridge.pas:2673-2676, which says the STACK step writes the 7628 values. The four
`StackLayerProps(...)` calls that would do it are commented out (lines 2721-2724).

The PcbDoc today has the Altium default stack:
- 3 dielectrics of 12.6 mil FR-4, Er 4.8
- 1.4 mil copper on every layer

So the S6 agent line "doesn't use JLC's 4-layer stack-up" was TRUE, and the notes.md order note "the layer stack in the
board file is the Altium default ... you MUST select JLC04161H-7628" is TRUE.

My S5 point still stands: Place parts adds the 2 inner layers itself, and the agent denied that. Only the "with
JLC values" part was wrong. My S6 impedance estimate (about 65-70 ohm) still holds for the board JLC will build if
7628 is chosen. It does not hold for the file's own stack.

## Verdict
The files are complete and consistent:
- 14 Gerber and drill files.
- The BOM has 55 parts on 31 lines, every line with an LCSC code (K4 met).
- The CPL has 55 parts, all Top, and is in the same absolute frame as the Gerber outline (25.4-85.4 x 25.4-70.4 mm).
- outputs-check found every expected kind.

What is wrong is what travels with the files:
- The gate lets outputs through with 424 DRC lines, and the Outputs page never mentions them (by design: only
  unrouted nets block).
- The only order note is a hand-written section in notes.md, which is not exported.
- That note tells the student to "Tent vias" while the mask Gerber leaves all 157 vias open.
- The CPL for J1 and J2 still uses the pad centre near the faulty footprint origin. Condition L3 is not resolved and
  nothing warns about it.

## System findings

- [WRONG] The order note contradicts the Gerber on via tenting, on a HASL board. Two lines of notes.md disagree:
  - The JLC Order Note says "Tent vias (all vias 0.3048 mm hole, within JLC's 0.4 mm tented limit)".
  - The Open Risks list (at the student's request) says "Vias are NOT tented in the board file".

  The exported top mask (GTS) flashes 157 round 0.028 in (0.711 mm) openings, one per via (the via is 0.61 mm plus
  2 x 0.05 mm expansion). So the files ask for bare vias. JLC's options are Tented, Untented, Plugged or Filled
  (pcb-capabilities.en.md:115-120). Whether the order-page choice overrides openings drawn in the mask Gerber is not in
  the app's reference: unverified.

  If the student picks "Untented" to match the files, the S6 problem ships: 137 pad-to-via slivers, bare vias about
  0.14-0.19 mm from pads, against JLC's "HASL: >= 0.2 mm". If they pick "Tented", the result depends on JLC's
  handling. Either way the app leaves it open (C136).

  Generic cause: via tenting is neither a rule the importer writes (07:01 answer) nor an output option. The agent's
  notes text is not checked against the files. Fix direction: tent vias in the preset or add an OutJob option, and
  derive the order note from the file.
- [WRONG] Outputs pass with 424 DRC lines, and the Outputs page never says so. The page shows:
  - "Warning (the outputs are still made)" for U1 pins only, shown twice: in the result banner and the sticky banner
    (S7-02, S7-03).
  - A green Outputs dot, while Layout is red 424.

  The order manifest's `warning` field also names only U1. The DRC counts sit deep in `board_check`, with no warning
  text. This is the design: stages.outputs_stage blocks exactly on store.manufacturing_block, which is
  manufacturing_warning + route_block, and route_block checks only unrouted nets (store.py:4024-4087). A student who
  goes straight to Outputs is not told that the board has 252 mask slivers and 160 silk findings.

  Allowing outputs is defensible: most of the 424 are JLC-acceptable, and Clearance and Short-Circuit are 0. Saying
  nothing is not. Fix direction: one line on the Outputs page and in the manifest warnings, "Altium DRC: 424 open
  (0 clearance / 0 short); see Layout", plus the via-to-pad item as a must-decide.
- [FRICTION] There is no README or order-note output, so conditions M4, P1 and P2 are met only by hand.
  - The Export menu offers BOM (JLC), BOM (generic), CPL and the Gerber zip only (S7-04).
  - The agent wrote the bring-up steps, the risks and a JLC Order Note into notes.md, which says of itself "Yours.
    Nothing derives from this file". It is not in exports/, not in the zip and not in the manifest.

  Content check of notes.md:
  - Bring-up steps 1-7 are correct and specific: the CS lines high before SPI1; the LSM6DSO I2C/I3C disable,
    register addresses correct per the cited pages; PB12 pull-up; LSE high-drive; no VBUS sensing (PA9 = SDIO_D2);
    SWD first; tunable load caps; RTC calibration.
  - The stack line is TRUE (see the correction above).
  - "1 oz outer / 0.5 oz inner, HASL" matches JLC04161H.

  The first round (07:26) left out the student's S6 risk list and K2 (C135). Those were never said to the app, so
  this is not an app error. But the agent's "I added the missing parts" sounded complete.

  Generic cause: there is no generated order/README artifact built from board facts (stack, finish, tenting, DRC
  summary, accepted risks).
- [FRICTION] The CPL for J1 and J2 does not resolve L3, and nothing warns about it. export_cpl.py uses the centre of
  the pads' bounding box, not the footprint origin. From the PcbDoc, that point is 0.15 mm (J1) and 0.245 mm (J2) from
  the origin. S3 found the origin 1.42 mm (J1) and 2.32 mm (J2) from the body centre. So the CPL point is still about
  1.3-2.1 mm from the body centre on the two connectors, by my arithmetic.

  JLC asks for the component centre. Its preview may snap to pads: unverified until the JLC DFM preview. The student
  noted they did not verify rotation or origin. The app shows no L3 warning even though the S3 answer flagged exactly
  this.

  Altium's own Pick Place output disagrees with the advisor's CPL on the same parts:
  - J1: 30.99 vs 30.84
  - J2: 75.46 vs 75.56
  - Its Comment column reads the literal "Comment".

  outputs-check counts Altium's file as "the CPL" (outputs-check.json), while the notes say to upload `_cpl.csv`. There
  are two different CPLs and one check.
- [FRICTION] The most important part is the one the checker cannot verify. U1 (STM32F411CEU6) stays "unverified". The
  issue text says "no pin table of the datasheet lists this part's pins (the best names 6 of its 49)". The pin checker
  cannot parse the STM32 pin table, so the 49-pin MCU is left to a one-click "Confirm" on the banner, with no
  datasheet page required. Fix direction: parse the STM32 pinout table format (UFQFPN48 column), or route U1 to a
  page-cited manual check.
- [COSMETIC] Labels in the outputs:
  - The order manifest lists U2, U4 and U5 under `accepted_risks` with basis `datasheet_page`, while the page shows
    them as "Checked by you". Only D1, D2 and J3 are accepted risks.
  - "Altium wrote no BOM, so BOM/... is the advisor's JLC BOM" appears next to a folder named "BOM 1 file" (C132). It
    is correct, but reads as a contradiction.
  - BOM lines C10 and C11 are both 4.7 uF 0603 C19666 but are two lines, because their roles differ. JLC accepts it.
- [COSMETIC] The 06:59 rule import says "PlaneClearance skipped". The agent's answer that the board already has a
  20 mil PlaneClearance is not wrong. But PlaneClearance applies only to Plane layers, and this tool's planes are pours
  on Mid-Layer signal layers. That rule has no effect on the pours, so the hole-to-pour gap is set by the polygon
  clearance. I did not measure the 0.16 mm the student lists: unverified.

## Claims and data checked (TRUE)
- BOM_jlc.csv vs bom.json:
  - 31 lines with 55 designators: U1-U5, D1-D4, F1, J1-J3, Y1-Y2, SW1-SW2, R1-R15, C1-C23.
  - The quantities match the refs.
  - Every line has an LCSC code. The 8 K4 lines whose `lcsc` field is empty take the code from the checked
    `supply.LCSC.code`: U5 C435835, Y1 C479202, Y2 C2692145, R3 C270607, C15 C1574, C17 C1558, C22 C52923,
    R4 C25130. All match the K4 list.
  - H1-H4 are correctly absent.
- CPL:
  - 55 rows, all Top.
  - The board origin is 0,0, so the coordinates are absolute. The Gerber outline (GM1) spans 25.4-85.4 x
    25.4-70.4 mm, 60 x 45 mm as asked. U1 at 54.0/41.5 is inside, so the CPL and Gerber frames agree.
  - The rotations are the PcbDoc rotations; no cpl_rotation offsets were applied.
- Gerber zip (14 files):
  - Layers: GTL, G1, G2, GBL, GTS, GBS, GTO, GBO, GTP, GBP, GM1.
  - Drill files: plated round, non-plated round and plated slot.
  - The outline is on GM1, which JLC reads (files-and-formats.en.md:64).
  - Gerber in inches, 2.4 format.
- "Altium wrote 21 files", "every expected output is there": TRUE (outputs-check.json, 07:23:10).
- The +3V3 0.127 mm line in notes.md: TRUE. At 07:13, +3V3 was drawn at 0.127 mm. +5V and VBUS are now 0.4 mm,
  because the student set 1 A and a PcbDoc width rule of 0.4 mm won. My S6 WRONG 3 still applies to +3V3.
- The 07:17 answer: "all 160 silk-to-mask from the 6 mil JLC rule; disabling the 10 mil clears nothing; slivers are
  pad-to-pad AND pad/via-to-via; tenting removes the via slivers". TRUE, and it corrects the S6 advice (C130).
- The 07:01 answer: "153 vias of 0.3048 mm hole fit JLC's <= 0.4 mm tented limit". TRUE (pcb-capabilities.en.md:118).
  "No course source for the checkbox" is honestly said.
- The manifest `board_check` carries the 07:13 route (39 nets, 762 tracks, 157 vias, open_nets []) and the 07:14
  DRC. It matches the chat.

## For the lecturer
The student stopped before JLC as instructed and checked the BOM codes and CPL rows. They caught that the first
notes.md missed their risk list, and they flagged the "Tent vias" contradiction instead of guessing. Not verifying the
CPL origin against JLC's preview is acceptable at this stage. It must be done before ordering.

## For S8 (carried)
- Decide via covering explicitly. Either tent the vias in Altium and regenerate, or choose the option on the JLC page
  and confirm in its DFM how the mask openings are treated.
- Select JLC04161H-7628 on the order page. The file stack is the Altium default.
- In JLC's preview, check the J1 and J2 positions and rotations (L3) and the J3 opening direction.
- Check U1 pins against the datasheet (DFM > Unverified parts) before ordering. Do not use the one-click Confirm.
- Open DRC items to accept or fix: the U1 mask dam (0.054 mm), the J1 dam (0.098 mm), and the J1 ring (0.200 mm, OK
  for JLC).
- Upload `exports/Final-E2E-4L_cpl.csv`, not Altium's Pick Place txt.
