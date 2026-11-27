# Lecturer – Stage 5 (Placement)

## Video highlights
- S5-14-placement-full-view.jpg | First placement: USB-C and microSD on the long edges, decaps far from their pins.
- S5-22-new-distance-table-route-or-not.jpg | The student's distance table: VCAP1 cap 15.7 mm away, SD-slot caps 23–28 mm away.
- S5-23-second-answer-contradicts-table.jpg | The agent's follow-up says "only C10 is over 5 mm", contradicting its own table.
- S5-26-final-placement-fit.jpg | Lecturer round 1: PASS with conditions. Four net-critical moves must be done in Altium before routing.

# Round 1

Evidence: `roles/student.md` (S5), confusions C99–C109, `screens/S5-01..27`, and `alti/S5-pcbdoc.json` (Alti's dump of the placed PcbDoc, 06:04).
I recomputed every distance from that dump, pad centre to pad centre, **and by net**. As the orchestrator asked, the student is judged on what the tool lets a student do (Place
parts with holes, edge parts, keep-apart distances, keep-outs and heat/RF tags; no per-part moves, no near-a-pin option, no stack). Tool limits are system findings.

## What is good
- You measured instead of trusting the banner. You asked for a distance table twice, compared it with my M2 list item by item, and caught that the
  second answer contradicted the table (C108). That is exactly the attitude this course wants.
- You used the tool's levers where it had them: edge constraints for J1/J2 (now on the opposite short edges, M3 ✓), keep-out cards for the 4 M3 holes, and a
  second placement.
- You reported honestly what could not be done (stack, hand moves, keep-out rectangles), without pretending.
- Carried conditions: M1 ✓ (Alti re-compiled after the Main redraw: 55 nets, 226 pins, 16 No-ERC). Outline 60×45 ✓. All parts on TOP ✓ (top-side assembly).

## My re-measurement: which misses actually matter (net-aware)
Your table rightly applies the per-designator rule. But a cap only decouples a pin **on its own net**, and several U1/U2/U3/U4 pins have *another* 100 nF of the
same +3V3 net within about 2–3 mm. So not all of your 13 "FAIL"s are equal:
- **Critical (the only cap on that net, or no local cap at all):** **C10 VCAP1**, 15.7 mm from pin 22. It is the only part on the VCAP1 net, and ST requires 4.7 µF with ESR < 1 Ω
  at the pin. **J2 microSD VDD (pin 4)**: no cap of any net within 8 mm; C19 (10 µF) is 28.4 mm away and C21 (100 nF) 23.2 mm. The 200 mA SD bursts (K3) have no local
  storage. **Y1 HSE**: 7.3 and 8.1 mm from pins 5/6, so the 25 MHz traces are about 8 mm long, an EMI and start-up risk. **VDDA pin 9**: the 1 µF C22 is 20.9 mm away and the 10 nF C23 is 7.0 mm away
  (a 100 nF, C20, does sit at 2.6 mm).
- **Acceptable as is (only designators swapped):** U1 pins 1/24/36/48 each have a 100 nF at 2.1–2.9 mm (C21, C2, C1, C21). U2 pin 8 has C4 at 1.9 mm, and pin 5 has C22 1 µF
  at 3.0 mm. U3 has C7/C6 at 2.2–2.9 mm. U4 has C3 at 2.6 mm. C12/C13 are at the U5 pins (2.9/4.9 mm to the tab). Y2 at 3.6–3.9 mm is acceptable for a 32 kHz crystal.

## Questions you must answer (round 1)
1. **Triage.** Out of your 13 FAILs, which few would actually make the board misbehave? Give the minimal, net-aware move list someone must do in Altium (my
   answer is above: C10, the SD-slot caps C19+C21, Y1, C22/C23). Note that your table and the agent's both measure to the nearest pad **of any net**. "J2-4 nearest cap
   8.4 mm" is C15, the HSE load cap, and "VCAP1 nearest 2.3 mm" is C2 on +3V3. How did you tell which numbers count?
2. **BME280 heat.** Your confirmed requirement says "BME280 … away from the regulator and MCU". It sits **10.7 mm from U5** (0.46 W peak) and 12 mm from U1, while the
   right third of the board is empty (C102). The placer **has** keep-apart distances and heat tags. Why did you not use them? That was in your hands.
3. **Is the stack real?** "4 copper layers" on the Layout page is the project setting, not read from the PcbDoc (C109). Before routing: is the PcbDoc stack Top / GND / +3V3 /
   Bottom with planes defined, and which JLC stack-up (thickness, prepreg) did it take? Ask Alti for the file's layer list. Routing on a 2-layer PcbDoc would invalidate everything.
4. **Keep-outs survive?** H1–H4/KO1–KO4 exist only as long as nobody accepts Altium's "remove" in Update PCB, and the corner keep-out rectangles are hand-drawn. How do you
   make sure the router starts with all 8 present, and that you re-check after any later Update PCB?
5. **Protection placement.** D1 (USBLC6) is 8 mm from J1, which is acceptable. But the TVS D2 is about 15 mm from J1 and after F1. A surge enters at the connector. Is that where you want the
   clamp? (No move is required for a USB-powered prototype, but say whether you accept it.)

## Verdict round 1: **PASS with conditions** (gate before routing)
The remaining failures are things the tool does not let a student fix (per-part moves, near-a-pin placement, stack setup, keep-out objects). The student did
everything the tool allows, measured honestly, and documented. Q2 was in the student's hands; it is carried as a condition rather than a FIX, because re-running Place
would reshuffle the decaps again.
- **N1 (gate: before S6 routing starts):** someone with Altium access moves, at least: **C10 to VCAP1 pin 22**, **C19 + C21 to J2 pin 4**, **Y1 tight to U1 pins 5/6** (load caps
  C15/C16 with it, no signal under it), **C22 + C23 to VDDA pin 9**. Alti measures again, by net. Routing before these moves means re-routing.
- **Note: N1 waived by orchestrator ruling (`DECISIONS.md`) and carried as a system finding.** Routing goes ahead on the system's placement. In S6 the routing is
  judged knowing that C10 (VCAP1), C19/C21 (SD slot), Y1 and C22/C23 (VDDA) are far from their pins.
- **N2 (with N1):** move U3 BME280 away from U5 and U1 (for example into the empty right third, away from the J2 slot), or record the decision to accept warm readings.
- **N3 (before S6):** Alti confirms the PcbDoc layer stack (4 copper, L2 GND, L3 +3V3), and that H1–H4/KO1–KO4 and the keep-out rectangles are present. Nobody accepts their removal in Update PCB (L4).
- **N4 (S6):** the USB D+/D− pair goes J1 → D1 → U1 PA11/PA12 short and together. No trace under Y1/Y2. The keep-outs are honoured (L4). The 3D/origin offsets J1/J2 stay for S7 (L3).
- Still carried: K2/K4/M4 (S7 README, LCSC codes, firmware notes), L2 (EP vias and paste), L3 (CPL origin), L5 (JLC DFM items), K5 (DFU test on the real board).

---

## System findings (the TOOL)
- [WRONG] The placer is not pin-aware or net-aware for decoupling and crystals. Evidence: two placements, and both leave **C10 (the only part on VCAP1) 15.7–23.3 mm** from pin 22, the SD slot
  with no cap within 8 mm, Y1 at 7–8 mm, and VDDA's 1 µF at 21 mm (S5-16, S5-22; my net-aware recomputation from `alti/S5-pcbdoc.json`). The second run made C10/C19/C22
  **worse** (C107). Why it matters: VCAP1 far from its pin is a datasheet violation, and local decoupling is missing at the 200 mA SD load. Generic cause: no cap-to-pin association
  (S4 finding) and no "near pin X" constraint, only keep-apart, edge and keep-out (C105).
- [WRONG] A false "checked" banner, and contradictory numbers. Evidence: "55 parts placed, outline kept, saved and **checked against the netlist**" while 4 of 8 warnings are
  real failures (S5-12, C101). The follow-up says "C10 is the ONLY decap over 5 mm … all others within 5 mm of the nearest pad on their own net", contradicting the table it
  had just given (C19 28.5, C6/C7 18–22) (S5-23, C108). Why it matters: a student who reads only the banner or the short answer routes a bad placement. Generic cause: "checked" means
  netlist equality, not placement quality, and the follow-up path answers without the action results.
- [WRONG] Wrong instruction about keep-outs. Evidence: "the project library has no footprint MECH_KO… run library.build, then place again", later corrected to "Altium
  dropped Keep-Out objects from the footprints, draw the four 7×7 mm rectangles yourself" (S5-13, S5-16, C101, C104). Generic cause: the S3 keep-out gap (stored only
  in the sidecar), plus the agent's advice not checked against what the build does.
- [FRICTION] The stage cannot do its own first step. Evidence: Layout opened with 2 copper layers and a 152.4×101.6 mm board (S5-03). "Set board" worked silently (C99). The agent: "none of my
  Altium actions change layers … Layer Stack Manager by hand" (S5-07, C100). Later the page shows "4 copper layers", but the agent says the real stack is unknown and the 4 is
  only the project setting (S5-27, C109). Generic cause: no stack read-back or stack action exposed to the agent (the orchestrator reports that `ensure_stack(4)` exists inside
  placement, but nothing shows the result).
- [FRICTION] An Altium-only instruction for a web student. Evidence: "Update PCB will offer to remove H1–H4/KO1–KO4: do not accept" (S5-20, C106), and "Next: move Y1 and C13 in Altium" (C106). Generic
  cause: the mechanical parts and keep-outs are not protected by the tool's own ECO path, and there is no move action.
- [FRICTION] A verbatim-quote gate on placement. Evidence: "student_said must be a verbatim quote of ONE student message … that message must tell you to place" refused a "yes, replace the
  placement…" sentence, and only a bare "yes" worked (S5-17/18, C105). Generic cause: a consent check that is too literal for a natural answer. It is safe, but needs one extra round trip.
- [FRICTION] The preview cannot be used for checking. Evidence: designators drawn away from their footprints (C102), the page re-lays out under a click (C108), and no per-part distance
  overlay. The student needed two chat round trips to get distances.
- Good tool behaviour worth keeping: it produced an honest per-part distance table on request. It applied the edge constraints correctly on the second run. It refused to place
  without explicit consent. It said plainly that it cannot set the stack or move parts.
