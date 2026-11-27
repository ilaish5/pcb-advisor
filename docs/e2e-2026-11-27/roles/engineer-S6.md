# Engineer review, Stage 6 (Routing + DRC), system side in the browser

## Video highlights
- S6-27-routed-banner-421-drc.jpg | "Comes with the part, not the routing": 137 of 252 slivers are router vias next to pads.
- S6-36-agent-cannot-fix-only-walk-through.jpg | "Disable the 10 mil silk rule to clear 157": that rule had 0 violations.
- S6-11-answer-no-90ohm.jpg | Entering currents made power tracks 0.127 mm, narrower than every signal track.
- S6-20-answer-keepouts-are-top-copper.jpg | Rejection was right: the corner "keep-outs" were top copper. The fix just deletes them.

Scope: the Rules and Layout pages and chat 06:16-06:44, plus the data behind them:
- board-log, altium-log (import-rules, both route-pcb runs and the DRC)
- the routed PcbDoc, read with pcbdoc.read_pcbdoc (read-only)
- scripts/altium/netcurrent.py, stages.py, store.py route_state / manufacturing_block
- shared/reference/jlc/pcb-capabilities.en.md

Engine: Antigravity / Gemini.

## Verdict
The routing itself is complete and the main claims are true:
- 39 nets, Altium's Un-Routed Net check reports 0, and there are 0 clearance and 0 short-circuit violations.
- One GND pour on Mid-Layer 1 and one +3V3 pour on Mid-Layer 2, each pulled back 0.31 mm from the edge.
- The first route was rejected correctly, and the board was put back.

What is wrong is how the app explains and sizes things:
- It blames all 252 mask slivers on the footprints, but more than half are vias the router put next to pads, left
  untented on a HASL board.
- It sends the student to disable a silk rule that has no violations.
- A current entered by the student makes power tracks narrower than signals.

The 421 DRC findings are listed with "way forward" texts, which is good. Two problems with how they are shown: the
"Check board" banner shows them under a green tick, and the outputs gate ignores everything except unrouted nets.

## System findings

- [WRONG] The app misattributes the mask slivers, and the cause is a real HASL risk. The route warnings (06:36:11, S6-27,
  S6-33) and the agent's table (06:40:38, S6-32) present all 252 "Minimum Solder Mask Sliver" violations as footprint
  pitch: "It is the fine pitch of the footprint (comes with the part), not the routing", with the fix "shrink pad mask
  expansion". The DRC list in board-log 06:38:18 says otherwise:
  - 137 of the 252 are between a pad and a via, on 47 parts (C10-2 to a via at 3.685 mil, C13-2 at 1.833 mil; 83 of
    them are under 4 mil).
  - Only about 117 are pad pairs inside U1, J1 and U2.

  The vias are untented: the SolderMaskExpansion rule has `ISTENTINGTOP=FALSE`, so all 153 vias are open. The project
  finish is HASL (project.json). JLC's own guidance for untented vias with HASL is "keep bare vias >= 0.2 mm from other
  exposed copper" (pcb-capabilities.en.md:119). Here the copper gaps are about 0.14-0.19 mm, which risks solder wicking
  and bridges at 0402 pads. Shrinking the footprint mask expansion does not touch any of these. Fix direction: tent vias
  in the preset, or keep the router's vias at least 0.2 mm (copper) from pads, and split the warning into footprint and
  routing parts.
- [WRONG] The silk fix the agent gives cannot work. At 06:42:10 and 06:43:58 it says to "disable the extra 10mil
  SilkToSolderMaskClearance rule ... To clear 157 violations first" (S6-34, S6-36). The DRC counts show
  `Silk To Solder Mask (Clearance=10mil) (IsPad),(All): 0` and `Silk To Solder Mask (Clearance=6mil) (All),(All): 157`.
  All 157 belong to the JLC 6 mil rule that the preset itself added (SilkToSolderMaskClearance_JLC, scope All, which
  counts silk over tracks and open vias). Disabling the 10 mil rule clears nothing. The 157 are mostly silk lines over
  routed copper and untented vias. JLC drops silk on openings by itself (pcb-capabilities.en.md:107-108), so they are
  cosmetic. That is what the app should have said.
- [WRONG] A current the student enters makes power tracks narrower than signal tracks. Before "Apply rules", +3V3, +5V
  and VBUS were planned at 0.254 mm. After the student entered 0.3/0.5 A and applied the preset, all three were drawn at
  0.127 mm (5 mil), while every signal net got 0.2032 mm (altium-log 06:36:11 `drawn_widths`; on the board: 79 top and 2
  bottom power tracks at 0.127 mm). The cause is in scripts/altium/netcurrent.py:99, `w = max(need, wmin)`. The IPC-2221
  result (0.115 mm for 0.5 A at 10 C) is rounded up to the board's MINIMUM width, not to the preferred 8 mil that nets
  without a current get. 0.127 mm is within IPC for 0.5 A. But by my IPC-2221 arithmetic, at the polyfuse trip current
  (nSMD050: hold 0.5 A, trip about 1 A) it rises about 40 C. A reviewer would mark VBUS and +5V as the thinnest tracks on
  the board as wrong practice. Fix direction: max(IPC width, preferred width), and say so on the Rules page (C112).
- [FRICTION] Two DRC groups were reported as "unknown, inspect in Altium" although the app had the details. The 06:40
  table says Board clearance (7) and Silk to silk (1) are "Unknown (inspect in Altium)". board-log 06:38:18 lists them:
  - Board clearance: five J3 pads at 11.811 mil (0.300 mm) against the 12 mil (0.3048 mm) rule. The placer's own
    edge_copper_mm is 0.3, so two parts of the system disagree by 0.005 mm.
  - Board clearance: the H3 and H4 designators lie over the board edge.
  - Silk to silk: the "C10" and "R3" designators.

  All 8 are harmless. JLC needs at least 0.2 mm copper to a routed edge (0.3 mm for economic assembly). The student was
  sent to Altium for items the page could have named and closed.
- [FRICTION] The route was rejected correctly, but the advice that followed drops a requirement. The first route
  (06:24:02) found 4 new Short-Circuits: H1-H4 against "Region (0 hole(s)) Top Layer". The board was restored from
  backup. The agent's diagnosis at 06:28:40 is right ("KO1-KO4 sit on Top Layer (copper) ... no-net Top Layer copper
  overlapping mounting holes"; this was my S5 WRONG 1). But:
  - The rejection banner gave the raw DRC line and the total 437 with no next step (C115).
  - The remedy removed the four keep-out requirements (Idea v13) instead of fixing the KO footprint. The student's M3
    keep-out requirement is gone, and nothing protects the corners on a later reroute. Today the nearest top copper is
    6.1-13.6 mm from each hole, so this board is fine.
  - The system's own pre-route check (board-facts "ko_*: met, no copper inside") had passed the copper, so 6 minutes of
    routing were spent before Altium caught it.
- [FRICTION] USB and HSE routing quality is not checked. The answer at 06:19:00 is honest: no 90 ohm pair, "uncoupled
  0.203 mm". It was routed as follows:
  - USB_DP: 33.4 mm, all on top.
  - USB_DN: 30.3 mm top + 5.8 mm on Mid-Layer 2, the +3V3 pour layer, with 2 vias. The pair is split across layers.
  - With w = 0.203 mm over the 0.21 mm 7628 prepreg to GND, single-ended Z0 is about 65-70 ohm by my estimate, not 45.

  For USB full speed at about 35 mm this is a low risk. The agent's line "doesn't ... use JLC's 4-layer stack-up" is
  inaccurate: the stack IS JLC04161H-7628 (AdvisorBridge.pas:2673-2676). Only the impedance is not targeted.

  The crystal is worse. HSE_IN runs 8.9 mm top + 14.6 mm bottom with 2 vias, and HSE_OUT 6.9 mm top + 3.9 mm on
  Mid-Layer 2 with 2 vias. That is about 23.5 vs 10.8 mm of unequal, via-hopping trace on 5.6 pF load caps. This
  shifts the load and the frequency, and it goes against ST AN2867 (short, symmetric, no vias). The app warns only
  "Y1 is 8.1 mm from U1 pin 6". VCAP1 likewise runs 17.4 mm with 2 vias to C10.
- [FRICTION] The DRC presentation does not separate what matters, and the outputs gate looks only at unrouted nets.
  - The "Check board" result shows the 421 total under a green tick (S6-29). The Layout badge says 421 in red.
  - The per-footprint "way forward" texts are good. But there is no grouping into "JLC will make this / must fix", and
    no way to accept an item as JLC-OK (C121). Every fix is an Altium hand step that the agent says it cannot do
    (06:43:58).
  - stages.outputs_stage uses store.manufacturing_block, and route_block passes as soon as Un-Routed is 0
    (store.py:4024-4077). Short-Circuit and Clearance counts are not part of the gate. They are 0 here, so allowing
    outputs is defensible today. But the gate would also let a hand-shorted board through, and nothing gates the
    via-to-pad HASL issue above.
- [COSMETIC] Two descriptions on the Rules page are inaccurate:
  - It says "Your board matches the preset / every rule matches the JLC preset or is stricter" (S6-09), while the
    preset itself creates the 157 silk and part of the 252 sliver findings. For example, "SolderMaskExpansion" was
    updated to 2 mil by the import (altium-log 06:16:34), and that value turns the U1 dam into 0.054 mm.
  - The rule is labelled "Board Clearance Constraint (Gap=0mil)" in the DRC summary, but it is actually set to 12 mil.
- [COSMETIC] Routing shows no progress: 5-7 minutes with a timer only and no tracks or net count until the end (C114,
  C118).

## Claims and data checked (TRUE)
- Route 2 report: "39 nets routed with 730 tracks and 153 vias, planes: GND on mid1, +3V3 on mid2; own check: no open
  nets". This is TRUE:
  - altium-log 06:36:11 lists 39 routed (38 netlist nets + PA10), with failed [] and open_nets [].
  - Altium DRC Un-Routed Net 0, Clearance 0, Short-Circuit 0, Width 0.
  - The PcbDoc has 2 polygons, GND/MID1 and +3V3/MID2. Each is one region (85.09 x 25.71..70.09 mm, 0.31 mm in from
    the edge) with 266 and 200 cut-outs, so there are no unpoured islands.
  - The vias are 0.305 / 0.610 mm, which gives a 0.152 mm ring.
- First-route rejection: TRUE and correct. drc_after counts Short-Circuit 4 (H1-H4 pad vs Top-Layer region), the
  restore is true, and route 2 has Short-Circuit 0.
- The rules against JLC (4-layer, 1 oz) are stricter or equal:
  - clearance 6 mil vs 3.5 mil
  - width min 5 mil
  - via 0.3/0.6 mm with a 6 mil ring
  - PTH ring 8 mil vs 0.15 mm
  - hole-to-hole 8 mil (via) and 18 mil (pad) vs 0.2 / 0.45 mm
  - board outline 12 mil vs 0.2 mm
  - silk to pad 6 mil vs 0.15 mm
  - ViasUnderSMD not allowed

  The exceptions are the untented vias on HASL (WRONG 1) and power widths at the minimum (WRONG 3).
- J1 annular ring: 0.200 mm against the 0.203 mm rule ("JLC itself needs 0.15 mm"). TRUE and correctly called "accept".
- USB answer: "no 90 ohm rule; default DiffPairsRouting 15 mil / 10 mil" is TRUE (PcbDoc rule DiffPairsRouting
  15 / 10 mil, unused).
- Mounting holes after removing the keep-outs: nearest top copper 6.1 mm (H1), 10.9-13.6 mm (H2-H4). No copper under
  the screw heads.

## For the lecturer
The student did the right things: entered real currents, asked for the USB pair, did not hand-edit Altium, and stopped
at 421. Their reading that most of the 421 is "footprint noise" came from the app's own text, and more than half of it
is not.

## For S7 (carried)
- Do not generate the Gerber until the via-to-pad gaps are fixed: tent the vias, or reroute so vias are at least
  0.2 mm from pads.
- C10 to U1-22 (VCAP1 17.4 mm of trace).
- Y1 and the HSE routing.
- A cap at J2-4.
- Power widths of at least 0.2 mm.
- Check the J1 annular ring and the U1/J1 mask dams in the JLC DFM preview.
