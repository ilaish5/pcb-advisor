---
name: placement-and-routing-plan
description: Plans where parts go and how to route the critical nets (power, USB pair, crystal, ground return), and places or routes the board when the student asks. Use when the student asks "where do I place the parts", "what first", "which side should the connector face", "how do I route USB / the crystal", "plan my layout" (Hebrew - איפה למקם רכיבים, איך לנתב USB, תוכנית ראוטינג).
---

# Placement and critical-net routing plan

`<repo>` is the repo path from the WORKSPACE section of the prompt. You place or route only when the student says so (see Offer
to place; the agent's own router, not Altium's autorouter). The plan comes first: show it BEFORE the student touches the board.

## Offer to place
Right after the schematic is drawn (`altium.draw_schematic`) the next offer is placing. Never send the student to Design > Update PCB unasked.
Who places and who routes, the `student_said` quote and the replace / partial rules: AGENTS.md, REPLY FORMAT AND ACTIONS
(`{"type": "altium.place_pcb", "student_said": "<most of their message>"}`, then
`{"type": "altium.route_pcb", "student_said": "<their words>"}`). After the plan, unless they already said who places, ask ONE question in their language:
"Place the parts in Altium yourself, press Place parts on the Layout page, or should I?" Then stop and wait.
`altium.place_pcb` places the netlist parts from the project library with their nets, creates the board outline from the idea's
board size when the PcbDoc has none (an existing outline is kept), saves, and reads the file back against the netlist. It needs
`library.build` and Altium open, with no unsaved changes in the PcbDoc. Routing is a separate question, asked after the parts are
placed: "route the board yourself, press Route board on the Layout page, or should I?" Send `altium.import_rules` before
`altium.route_pcb` (routing is refused on Altium's default rules). The router (top and bottom for signals; on a 4 layer board, chosen in the Idea, the ground net is a plane on Mid-Layer 1 and the main supply a plane on Mid-Layer 2:
their pads get a stub and a via, never tracks; the stack-up is set in Altium before placing; widths, clearances and vias from the
board's rules) draws tracks and vias, saves, reads the file back and runs Altium's design rule check: it counts as done only
with 0 open nets and no new clearance/short/width errors. When a net cannot be routed nothing is drawn: tell the student which
nets and why (tighter rules, more room, or 4 layers in the Idea); a partial result only when they agree to keep it. Never say the board
is routed when it reports a failure. Then use board-review.
Track width follows the current of each net (IPC-2221, 1 oz, 10 C rise). Before routing, propose the current of every supply net the idea
or a datasheet states (regulator output, USB VBUS 0.5 A, a motor) with `{"type": "net.set_current", "net": "+5V", "amps": 0.5, "sources": [...]}`
and cite the source; no source, no guess: the net keeps 0.3 mm and the result says "rail default". The route result lists "track widths"
per supply net: tell the student which nets were drawn narrower than wanted or are outside the IPC-2221 range (Rules tab > Net currents).

## When to use
- Update PCB / ECO is done (parts sit beside the board) and the student asks how to arrange them.
- The student asks about one rule of thumb: connector side, decap distance, crystal, antenna, heat, board zones.
- The student asks for the routing order or how to route power, USB, a clock, or the return path.
- A re-plan is needed after parts were added, removed or swapped.
- Not for: checking a finished layout (`board-review`); the rule values (`rules-and-calcs`).

## Steps
1. Read the data: the board outline (size, mounting holes), the part list with footprints, and the nets from the PcbDoc
   (pads carry nets). No PcbDoc yet: use the BOM and the schematic and say the plan is approximate.
2. Group parts into zones by function and noise: power input and regulators, MCU with its crystal and decaps, analog or sensor,
   RF/antenna, USB and other connectors, user interface, switching/relay loads. Keep noisy zones away from sensitive ones.
3. Place anchors first (course m20 20.4, unit3 [28]): board-edge connectors, mounting holes, the big IC, inductors, bulk caps.
   Then the parts that must be close to a pin, then everything else next to the pad it connects to.
4. Connectors: the opening where the cable or plug enters must face OUT, at the board edge. Pads of a 2-pin terminal block are
   almost symmetric, so check the real orientation in the 3D view (press 3 in the PCB editor, then tilt the view) and tell the student to do the same.
5. Decoupling: one cap per supply pin, on the same side as the IC, aim for 2-3 mm from the pin (`checks/board.py` flags above 5 mm),
   smallest value closest, the cap's path to the pin before the plane via. A pin with a special cap (core regulator, reference, bootstrap) goes first.
6. Crystal: two load caps and the crystal touching the oscillator pins, short and equal traces, ground under, no other track
   nearby. Antenna or RF module: keep-out for copper and parts under and around the antenna as the module datasheet says.
7. Thermal: regulators, power stages and any part the datasheet marks need copper area and vias; keep heat sources away from
   sensitive analog parts and from electrolytic caps. Cite the datasheet page for the thermal pad layout.
8. Render the board with `preview_pcb.py` (outline, holes, every part with its designator) and give the zones and the table of
   anchors with edge and rotation in the reply (you cannot write a plan file). Wait for the student's OK before the routing plan.
9. Routing plan, in this order, each as one row: (1) critical short loops (switcher hot loop, RF line), (2) power and ground
   (widths from `rules-and-calcs`), (3) differential pair, (4) crystal and clocks, (5) sensitive analog, (6) the rest. State layer,
   width, spacing, via count and the ground return path for each critical net.
10. Ground return: keep one unbroken ground plane under fast signals; do not route across a plane split; add ground vias next to a
    layer-changing signal via. Pour polygons last (course m22).

## Scripts
- `python <repo>/scripts/preview_pcb.py <pcbdoc_or_project>` - renders the PcbDoc to SVG, with the project's saved placement plan
  overlay when there is one (you do not write plan files).
- `python <repo>/scripts/trace_width.py <amps> --layer external --oz 1` - width for a power net (IPC-2221).

## References
- `<repo>/shared/reference/course/ad20-essentials/m20-pcb-placement.en.md` - 20.4 placement within rooms.
- `<repo>/shared/reference/course/ad20-essentials/m21-pcb-routing.en.md` - 21.4 interactive routing, widths, vias.
- `<repo>/shared/reference/course/ad20-essentials/m22-polygons-and-power-planes.en.md` - pours and planes.
- `<repo>/shared/reference/course/altium-education/unit3-pcb-layout.en.md` - [27]-[30] layout process, which parts first.
- `<repo>/shared/reference/course/altium-education/unit4-routing-signal-integrity.en.md` - [14] differential pairs, [19] return path,
  [22] strategies, [26] practices to watch, [38]-[43] EMI.
- `<repo>/shared/reference/AGENTS.md` - decoupling and thermal are not in the course; cite the datasheet.

## Pitfalls
- Connector placed backwards: the pad pattern looks the same both ways, and the error shows only in 3D, after the board is built.
  Rule: opening to the edge. Check each connector in 3D, not by numbers.
- A decap near the wrong pin: on a big supply net the nearest pad belongs to the wrong IC. Make a cap -> IC pin table and measure
  pad to pin. If a large part blocks the pin side, move that part, not the cap.
- Plan before moving: re-running an automatic arrangement reshuffles everything after one small change. Keep the approved positions
  and add only the new parts; say this when the student adds parts later.
- Designator text is part of the footprint's room: long names do not fit and cause silk overlaps. Use short designators, hide
  what does not fit on the silkscreen (it stays in the assembly drawing). JLC needs silk text at least 1.0 mm high, 0.15 mm stroke.
- Signal tracks under a module with an LGA/QFN pad field or under an antenna break the keep-out or short pads. Draw the keep-out first.
- The autorouter does not connect SMD pads to planes reliably and ignores your return path. Fan out power/ground pads yourself
  (short stub + via, clear of other nets, never on an SMD pad) and route critical nets by hand.
- Two same-net vias almost touching pass Altium's DRC but the fab's check flags them (it does not know nets). Keep at least about
  0.15 mm copper between vias or merge them.
- A power net wider than the pin pitch cannot enter the pin; neck down at the pad, widen after.
- Do not split ground to "isolate" noise unless asked; a split under a fast trace forces a long return loop.
- USB full speed: pair routed short and together, no stubs, same length within a few mm, over solid ground. High speed or RF: ask
  for the stack-up and compute the width in `rules-and-calcs`.

## Physical constraints
Mounting holes (M3: 3.2 mm, 3.5 mm in from the corners),
a part that must sit at an edge, a distance between a heat source and a sensor (SHT40 away from the module and regulator),
a keep-out under an antenna: propose each with `idea.constrain` instead of only writing it in the plan, for example
`{"type": "idea.constrain", "op": "add", "item": {"id": "h1", "kind": "mounting_hole", "diameter_mm": 3.2, "inset_mm": 3.5}}`
(fields per kind: AGENTS.md, REPLY FORMAT AND ACTIONS).
Antenna module: edge, antenna facing out, no copper under it.

## Output
- The preview path (top view) when you rendered it, then the plan in the order the student will do it, one line per zone or anchor: what goes
  where (mm from lower-left, edge, rotation) and the reason in a few words. A table (`Parts | Position | Why`) only for
  five or more zones.
- Routing plan: only the nets that need care (power, clock, USB, sensitive), one line each: net, layer, width, what to
  watch. "Everything else: default width, any layer" is one line. Max 8 lines.
- Source = `{{src:<course file>|<heading>}}` or `{{src:<datasheet>|p.N}}`; a rule of thumb with no source is labelled "practice".
- End with the first thing the student does in Altium. Student's language; Altium names in English.
