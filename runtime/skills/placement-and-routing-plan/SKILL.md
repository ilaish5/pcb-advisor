---
name: placement-and-routing-plan
description: Produces a placement plan (order, zones, connector edges, decoupling positions, crystal, antenna keep-out, thermal) as a top-view picture and a table, then a routing plan for the critical nets (power, USB differential pair, crystal, ground return), for the student to carry out by hand in Altium. Use when the student asks "where do I place the parts", "what do I place first", "which side should the connector face", "how close must the decoupling cap be", "how do I route USB / the crystal / power", "plan my layout" (Hebrew - איפה למקם רכיבים, סדר פלייסמנט, איך לנתב USB, תוכנית ראוטינג).
---

# Placement and critical-net routing plan

`<repo>` is the repo path from the WORKSPACE section of the prompt. The tool plans and draws; the student places and routes in
Altium. You move parts only when the student says so (see Offer to place); you route only when the student says so (see Offer to place:
the agent's own router, not Altium's autorouter). Show the plan picture BEFORE the student touches the board.

## Offer to place
Right after the schematic is drawn (`altium.draw_schematic`) the next offer is this one: "Should I place the parts on the board,
or will you (Update PCB)?" Never send the student to Design > Update PCB unasked.
After the plan, ask ONE question in the student's language: "Do you place the parts in Altium yourself, or should I place them?"
Stop and wait. Only on their answer: "you" = run `{"type": "altium.place_pcb", "student_said": "<most of their message>"}`
(refused when they say they do it themselves, or the quote is a fragment). It places the netlist parts from the project library
with their nets, creates the board outline from the idea's board size when the PcbDoc has none (an existing outline is kept),
saves, and reads the file back against the netlist. Needs `library.build` and Altium open, no unsaved changes in the PcbDoc. Refuses a
board that already has parts or tracks; `"replace": true` only with `"replace_said"` = their words (replace/redo/מחדש). Routing is a
separate question, asked after the parts are placed: "route the board yourself, or should I?" Only on their answer (a route word in their
quote) run `{"type": "altium.route_pcb", "student_said": "<their words>"}`. Run `altium.import_rules` before it (routing is
refused on Altium's default rules). It uses its own router (2 layers, widths, clearances and vias from the board's rules), draws
tracks and vias, saves, reads the file back and runs Altium's design rule check:
it counts as done only with 0 open nets and no new clearance/short/width errors. When a net cannot be routed nothing is drawn and
you tell the student which nets and why (tighter rules, more room, a third layer); `"partial": true` + `"partial_said"` only when they agree to
keep a partial result. Existing tracks: refused unless `"replace": true` + `"replace_said"`. Never say the board is routed when it reports a
failure. Then use board-review.

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
5. Decoupling: one cap per supply pin, on the same side as the IC, pad-to-pin about 2-3 mm, smallest value closest, the cap's
   path to the pin before the plane via. A pin with a special cap (core regulator, reference, bootstrap) goes first.
6. Crystal: two load caps and the crystal touching the oscillator pins, short and equal traces, ground under, no other track
   nearby. Antenna or RF module: keep-out for copper and parts under and around the antenna as the module datasheet says.
7. Thermal: regulators, power stages and any part the datasheet marks need copper area and vias; keep heat sources away from
   sensitive analog parts and from electrolytic caps. Cite the datasheet page for the thermal pad layout.
8. Produce the placement picture (to scale: outline, holes, zone rectangles, every part with its designator) and the table of
   anchors with edge and rotation. Wait for the student's OK before moving to the routing plan.
9. Routing plan, in this order, each as one row: (1) critical short loops (switcher hot loop, RF line), (2) power and ground
   (widths from `rules-and-calcs`), (3) differential pair, (4) crystal and clocks, (5) sensitive analog, (6) the rest. State layer,
   width, spacing, via count and the ground return path for each critical net.
10. Ground return: keep one unbroken ground plane under fast signals; do not route across a plane split; add ground vias next to a
    layer-changing signal via. Pour polygons last (course m22).

## Scripts
- `python <repo>/scripts/preview_pcb.py <pcbdoc_or_project> [--plan <plan.json>]` - renders PcbDoc with placement plan overlays to SVG.
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

## Output
- Picture path (top view) and a table: `Zone | Parts | Position (mm from lower-left) | Why`; anchors table: `Ref | Edge | Rotation | Check`.
- Routing plan: `Order | Net | Layer | Width / spacing | Vias | Return path | Source`. Max 15 rows each.
- Source = `{{src:<course file>|<heading>}}` or `{{src:<datasheet>|p.N}}`; a rule of thumb with no source is labelled "practice".
- End with the three things the student does first in Altium. Student's language; Altium names in English.
