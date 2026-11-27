# Lecturer – Stage 6 (Routing + DRC)

## Video highlights
- S6-17-route-rejected-4-short-circuits.jpg | Route rejected: the tool's own corner keep-outs were top copper and shorted the M3 holes.
- alti/S6-crystal.png | A via sits in the middle of the 25 MHz crystal, with SWD lines under the 32 kHz one.
- S6-56-r3-routed-424-widths-0.4.jpg | After the student's Extra rule and the trip current, +5V and VBUS are 0.4 mm.
- S6-43-r2-apply-1-added-2-skipped.jpg | The hole-clearance rule is silently skipped while the Rules badge turns clear.
- S6-28-routed-board-preview.jpg | Lecturer round 1: FIX. Power widths, hole clearance and via tenting not tried through the Rules page.
- S6-57-r3-check-board-424.jpg | Lecturer round 2: PASS with conditions. The student used every lever; the rest is tool limits carried to DFM.

# Round 1

Evidence: `roles/student.md` (S6), confusions C110–C122, `screens/S6-01..36`, `roles/alti-S6.md` (DRC classified line by line, geometry from
`alti/S6-pcbdoc.json`), and `roles/engineer-S6.md` (logs, `netcurrent.py`, gate code). I rely on their measurements and did not re-measure.
The stage-5 ruling stands: the decaps and Y1 are far from their pins because of placement, and that is not held against the student. I judge what the student
questioned and whether he used what the app offers (Rules page: preset, net currents, **Extra rules form** with Name/Kind/Scope/Min/Preferred/Max; Route board;
Check board; chat).

## What is good
- You entered **real currents** (0.3/0.5/0.5 A) instead of leaving them on default, and you asked for the **90 Ω USB pair** before routing. Both are the right instincts.
- You applied the JLC preset, and you noticed that two rules had been Altium defaults below JLC's minimum (C110).
- When the first route was rejected you got the cause from the app (KO footprints as top copper) instead of retrying blindly.
- You noticed that the power tracks came out 0.127 mm and that C10 is far from VCAP1, and you wrote both down. You stopped instead of hand-editing Altium.
- The result is complete: 39/39 nets, a solid GND pour on Mid-1 and a +3V3 pour on Mid-2, 0 shorts, 0 clearance, 0 unrouted (Alti and the engineer agree).

## Questions you must answer (round 1)
1. **Power widths: you noticed but did not challenge.** After your 0.5 A, +5V and VBUS were drawn at **0.127 mm**, the thinnest copper on the board and thinner than
   every 0.203 mm signal. The VBUS path must survive the polyfuse **trip** current (about 1 A for nSMD050) during a fault. The engineer's IPC-2221 figure is about 40 °C rise at
   that current. The Rules page has an **Extra rules** form: why no `Width` rule on `InNet('+5V') or InNet('VBUS') or InNet('+3V3')` with preferred 0.4 mm, or the trip
   current entered instead of the hold current? Try it and re-route.
2. **You deleted your own requirement to make the tool pass.** Idea v13 removed the four M3 keep-outs because the tool's keep-out footprints turned out to be top
   copper. Now the inner GND and +3V3 pours stop about **0.16 mm from the 3.2 mm NPTH walls** (Alti). JLC asks for 0.2 mm or more, and nothing protects the corners on a re-route. A
   requirement removed to work around a tool bug is a design regression. Can the Extra rules form restore it (for example a clearance or polygon-clearance rule
   for H1–H4 of 0.5 mm or more)? If not, say so, and carry it as a written risk for S8.
3. **Did you look at your crystals?** Alti found an **IMU_CS via in the centre of Y1**, IMU_CS, SDIO_CMD and BOOT1 under Y1, and SWD lines under Y2. HSE_IN is 23.6 mm long with
   2 vias across two layers, and HSE_OUT is 10.9 mm with 2 vias, so they are unequal and via-hopping on 5.6 pF load caps. ST AN2867 asks for short, symmetric, via-free traces with nothing underneath. What
   can you do in the tool (a keep-out or rule around Y1/Y2, then a re-route)? If nothing, write it as a known risk with a bring-up test: HSE start-up, frequency, USB
   enumeration, and LSE start-up in high-drive.
4. **DRC triage: you took the app's word.** The app said all 252 mask slivers "come with the part". In fact **137 are pad-to-via**: the router's vias are **untented**
   (`ISTENTINGTOP=FALSE`) on a HASL board, 83 dams are below JLC's 0.10 mm, and 9 bare vias sit within 0.2 mm of a *different* net's pad (Alti). Which of the 421
   actually matter for JLC, and which **single** change removes them (tent the vias, or a via-to-pad 0.2 mm rule)? Can the Rules page or Extra rules set via tenting? Also,
   the app told you to disable a 10 mil silk rule that has **0** violations (engineer). Did you check that claim before planning to act on it?
5. **What you accept, and what you write down.** With N1 waived, VCAP1 is a **17.4 mm path with 2 vias**. USB D− hops to the Mid-2 (+3V3) layer with 2 vias, and Mid-2 carries 36
   signal segments that slot the +3V3 pour. J3 pads sit 0.30 mm from the edge. For a USB Full-Speed prototype, which of these do you accept, and which go into the README as
   bring-up risks? For example: measure about 1.2 V and its ripple on VCAP1 at first power-up.

## Verdict round 1: **FIX**
Most of the four real defects (crystal area, VCAP1 path, untented vias, pours near the holes) come from the tool. The student is not held to fix them by hand. But the
student did **not** use the one lever the app gives him for exactly these cases, the Extra rules form on the Rules page. He also accepted a narrowing of the power tracks
he had noticed, deleted a requirement instead of replacing it, and adopted the app's DRC explanation without checking it. Round 2: try Q1, Q2 and Q4 through the
Rules page and re-route. Write Q3 and Q5 as risks. If the tool cannot do Q1/Q2/Q4, show that, and round 2 becomes PASS with conditions.

**Note for the orchestrator (reviewer conflict):** Alti says the PcbDoc stack "is still 4 × 1.4 mil Cu and 3 × 12.6 mil FR-4, the S5 defaults". The engineer says
"the stack IS JLC04161H-7628 (AdvisorBridge.pas:2673-2676)". One of them read the file and one read the code. Please rule on this in `DECISIONS.md` before outputs: the
stack in the Gerbers and the JLC order must agree. This is also my N3.

---

## System findings (the TOOL); see alti-S6 and engineer-S6 for the full evidence
- [WRONG] Entering a current makes power tracks narrower. Evidence: before applying, +3V3/+5V/VBUS were planned at 0.254 mm. After the student's 0.3/0.5 A they were drawn at 0.127 mm, while signals are
  0.203 mm (S6-09, C112; altium-log `drawn_widths`). Generic cause: `netcurrent.py:99` `w = max(need, wmin)` rounds the IPC result up to the board **minimum**, not the
  preferred width, and the rail default is dropped once a current exists. Doing the diligent thing made the board worse.
- [WRONG] The router ignores crystal layout rules. Evidence: a via in the centre of Y1, three signals under Y1, SWD under Y2, HSE nets 23.6/10.9 mm with 2 vias each (alti-S6). Generic cause: no
  crystal or oscillator handling in `route.py`/`negotiate.py` (no keep-out under the body, no via ban on crystal nets). This compounds the S5 placement.
- [WRONG] Vias are untented on HASL, and the cause is misattributed to the footprints. Evidence: `ISTENTINGTOP=FALSE`, 137 of 252 slivers are pad-to-via, 83 dams are under 0.10 mm, and 9 bare
  vias sit within 0.2 mm of another net's pad. The app said "It is the fine pitch of the footprint (comes with the part), not the routing" (S6-27, S6-32). Generic cause: the preset leaves via
  tenting off, the router has no via-to-pad rule, and the explanation text is fixed, not derived from the DRC lines (which `parse_drc` already has).
- [WRONG] A fix that cannot work. Evidence: "disable the extra 10 mil SilkToSolderMaskClearance rule … to clear 157", while that rule has 0 violations and all 157 belong to the preset's 6 mil JLC rule
  (S6-34, S6-36, engineer). Generic cause: the advice is not checked against the per-rule counts the system holds.
- [WRONG] The remedy for a tool bug deletes a student requirement. Evidence: the corner keep-out footprints (S3/S5 cause: keep-outs not kept in the PcbLib) landed as top copper. The first route shorted on them
  and was correctly rejected. The agent's fix was "remove ko_bl, ko_br, ko_tl, ko_tr" (Idea v13, S6-20/21). Result: inner pours 0.16 mm from the NPTH (JLC 0.2 mm). Generic cause: the KO footprint is
  unfixed since S3, and the agent removes requirements to get past a failed check instead of flagging the tool defect.
- [FRICTION] The DRC is shown under a green tick, with no triage and no waiver, and the gate looks at unrouted nets only. Evidence: "Check board" shows 421 under a green tick (S6-29). There is no
  "JLC will make this / must fix" grouping and no accept-as-JLC-OK action (C121). Every fix is an Altium hand step (S6-36). `manufacturing_block` passes when Un-Routed = 0 (engineer:
  `store.py:4024-4077`). Two groups were reported as "unknown, inspect in Altium" although the log had the details (engineer).
- [FRICTION] No USB pair. Evidence: "the router doesn't target 90 Ω … uncoupled 0.203 mm" (S6-11), and D− hops to Mid-2 with 2 vias (alti). Low risk at Full-Speed and 35 mm, but the Idea says USB and the Rules page offers
  no pair rule (C111, C113).
- [FRICTION] The +3V3 plane layer is used as a signal layer. Evidence: 36 signal segments on Mid-2 slot the +3V3 pour, and Bottom signals reference the cut pour (alti).
- [FRICTION] A 6-minute blind wait, then a raw rejection. Evidence: no progress shown during the route (C114, C118). The rejection banner gave the raw DRC line and "437" with no next step (C115). The system's own
  pre-route board-facts check had passed the KO copper as "met" (engineer).
- Good tool behaviour worth keeping: it rejected the shorted route and restored the board from backup. The final route has 0 shorts, 0 clearance and 0 unrouted, real GND and +3V3 pours, and
  short decap-to-plane vias. Its "no 90 Ω pair" answer was honest. Its J1 annular ring explanation (0.200 mm against the 0.203 rule, JLC 0.15) was correct.

---

# Round 2 (last)

Evidence: `roles/student.md` "Answers to lecturer S6", confusions C123–C130, `screens/S6-37..58`, and `DECISIONS.md` 06:57 (stack ruling: the PcbDoc holds Altium
default values, 1.4 mil Cu and 12.6 mil FR-4, **not** JLC04161H-7628; Alti was right). Route #3: 39 nets, 762 tracks, 157 vias, 0 short, 0 clearance, 0 unrouted,
DRC 424. I did not re-measure route #3 geometry; where it matters that is a condition for Alti.

## Answers checked
1. **Power widths: fixed through the tool.** Trip current 1 A on +5V/VBUS plus an Extra rule `Power_Width` (min 0.3, pref 0.4 mm) gives +5V and VBUS at **0.4 mm** (S6-56).
   The first try with +3V3 in scope was refused ("U1-9 too close to other copper for a 0.3 mm track"). The student narrowed the scope instead of giving up. +3V3 stays 0.127 mm
   for short stubs off the Mid-2 pour at 0.3 A, which is within IPC and acceptable, and is written as a risk. Owning the round-1 miss ("my miss") is to his credit.
2. **Hole clearance: tried, and the tool refused it.** The Plane clearance rule (InComponent H1..H4, 0.5 mm) was "skipped": the importer cannot write PlaneClearance. Correctly carried as a
   risk for S8. My note: the agent's comfort line, "the board already has a 20 mil PlaneClearance rule", does **not** cover this board. The Mid-1/Mid-2 copper is **polygon pours** (Alti: "real
   poured polygons"), which follow the Clearance rule (6 mil), not PlaneClearance. That is why Alti measured 0.16 mm.
3. **Crystals: honest.** The student had not looked, admits it, confirmed that the form has no crystal keep-out or via ban, and wrote the right bring-up tests (OSC_OUT scope, USB
   enumeration, LSE high-drive start, a layer view before ordering).
4. **DRC triage: done.** The student re-asked the app and got the corrected story (160 silk all from the 6 mil rule, slivers partly from routing vias, tenting removes them). He
   noticed that it contradicts the earlier advice (C130), and ranked the JLC-relevant items: U1 dam 0.054 mm below 0.1, J1 dam 0.098 borderline, J1 ring OK, U2 OK. Tenting is
   manual-only and recorded as a tool limit.
5. **Accept or write down: a sound list.** The accepted items (no 90 Ω pair at FS over 35 mm, D− hop, Mid-2 signals, J3 edge) are reasonable for a prototype. The not-accepted items
   go into the README with measurable bring-up checks (VCAP1 ≈ 1.2 V and its ripple, crystals, +3V3 stubs, pour-to-hole distance, untented vias).

## Verdict round 2: **PASS with conditions** (for outputs and DFM)
The student used every lever the app offers (net currents, Extra rules, scope narrowing, re-route, DRC re-query) and documented every limit. What remains is
system-caused, and per the S5/S6 rulings it is carried as system findings and DFM checks.
- **P1 (S7 README):** the student's bring-up risk list from Q5, verbatim, plus M4/K2 (firmware notes: IMU I2C/I3C disable order, LSE high-drive, PB12 pull-up, VBUS
  sensing off, tunable load caps, RTC calibration).
- **P2 (S7/S8 stack):** the file stack is Altium defaults. The JLC order must **select JLC04161H-7628** (or another explicit 4-layer stack-up), and the README and order note must not
  claim the file defines it. The Gerbers carry no dielectric, so the order form decides. No impedance control is claimed.
- **P3 (S8 JLC DFM, the producer maps each one):** untented vias next to pads (dams under 0.1 mm, 9 bare vias by other-net pads), U1 mask dam 0.054 mm, J1 dam 0.098 mm, inner pour to NPTH
  distance (≥ 0.2 mm), J3 pads 0.30 mm from the edge, J1 shield-slot width (L5), U3 pad length (L5), U1 EP paste and vias (L2).
- **P4 (S7):** CPL origin of J1/J2 (L3) and the 8 LCSC codes (K4) checked in the exported BOM/CPL.
- **P5 (Alti, before S7):** on route #3, re-check the crystal area (is the via still in Y1?), the pour-to-hole distance, and that the 0.4 mm +5V/VBUS widths are continuous.

---

## System findings, round 2 (new or changed)
- [WRONG] A rule is silently skipped, the page shows green, and the agent offers a false reassurance. Evidence: "Apply rules: 1 added, 0 updated, **2 skipped (PlaneClearance,
  M3_Holes_Plane_Gap)**" with no reason, and the Rules badge goes from amber to clear (S6-43, C125). The agent then says "your board already has a 20 mil PlaneClearance rule" (S6-44, C126). But the
  inner copper is polygon pours, governed by Clearance (6 mil), and Alti measured 0.16 mm to the NPTH on route #2. Why it matters: the student believes the holes are protected and they are
  not. Generic cause: the rule importer has no PlaneClearance or polygon-clearance writer, the skip is not surfaced as a failure, and the agent's claim is not checked against the board's object
  kinds.
- [WRONG] (per DECISIONS 06:57, recorded here for completeness) The stack is not persisted. `ensure_stack` adds the inner layers, but the PcbDoc keeps Altium default thicknesses and dielectric, not JLC04161H-7628.
  So the file, any impedance calculation and the JLC order disagree. The S6 agent's "doesn't use JLC's stack-up" was accidentally true for the file.
- [FRICTION] An infeasible width rule fails the whole route after minutes. Evidence: Power_Width min 0.3 mm including +3V3 led to about 5 min of routing and then "no tracks drawn: could not route +3V3 (pad U1-9 too close … for a
  0.299999 mm track)" (S6-48, C127). The old routing was kept, which is good. Generic cause: no pre-route feasibility check of width rules against pin pitch, and no neck-down at fine-pitch
  pins (the rule min applies to the whole net).
- [FRICTION] Via tenting is one flag the app will not set. Evidence: the agent confirms that "all 153 vias … meet JLC's ≤ 0.4 mm tented limit", but tenting is Altium-only (Find Similar Objects) and the Extra
  rules "Solder mask expansion" kind has no tenting option (S6-42, S6-44, C126). Fixing it would remove most of the 252 slivers and the HASL via risk in one step (round-1 WRONG). Generic cause: the preset
  and rule writer expose no via tenting.
- [FRICTION] Stale and contradictory displays. Evidence: Net currents still shows +3V3 "board rule 0.4 mm" after +3V3 was removed from the scope (S6-51, C128). The DRC explanation in round 2 contradicts round 1
  (C130). It is now correct, but the student cannot know which answer to trust. "Width wanted" equals the IPC figure rounded to the board minimum, with no hint to use the fault or trip current (C123). The round-1
  WRONG on `netcurrent.py:99` stands.
- Status of the round-1 findings: crystal routing (stands, unverified on route #3, P5). Untented vias (stands, P3). Silk advice (corrected in round 2, so it becomes FRICTION). Requirement-deleting
  remedy (stands; the student could not restore it, P3). DRC green tick and the gate on unrouted nets only (stands).
- Good tool behaviour worth keeping: the refused route kept the previous good routing. The Extra rules form worked for Width. The round-2 DRC explanation was accurate and per rule. It confirmed tenting
  eligibility with JLC's own limit.
