# 4-layer boards (E9)

Owner decision 2026-11-24: the tool builds real 4-layer boards, end to end. Default stack-up: **JLC04161H-7628**
(signal / GND plane / power plane / signal). 2 and 4 are the only layer counts; every other value is refused.

## The one setting

`project.json` `board.layers` is 2 or 4. The only validator is `scripts/board_layers.py`; every writer goes through it:

| writer | how |
|---|---|
| Idea page | "Copper layers" select next to the board size, `POST /api/idea/layers` |
| agent / student requirement text | `store.propose_idea` / `update_idea_item` read "4 layers", "4-layer", "four layers", "4 שכבות" out of text that is about the board and store it (`sync_layers_from_text`) |
| project meta endpoint | `board.layers` is checked by the same function |

Any other count (1, 3, 6, 8, 4.5, "four" through the API) is refused with the same message ("... is not something this tool
builds: it makes 2 or 4 layer boards ..."), HTTP 400, and nothing is written. `project.layers(name)` reads it (2 when none).
The JLC preset (`jlc_preset.variant`) already follows `board.layers`, so the rules imported for a 4-layer project are the
JLC 4-layer ones (name "JLC 4-layer 1 oz"): same 0.15 / 0.25 mm via, JLC multilayer limits.

## The stack-up in Altium

`AdvisorBridge.pas` has two new commands:

* `STACKINFO path` (read only): logs `stacklayer <name>` per copper layer and `stack <n>`.
* `STACK path 4`: a 2-layer board gets **Mid-Layer 1** and **Mid-Layer 2** under the top layer
  (`LayerStack_V7.InsertInStackBelow(Top, FirstAvailableSignalLayer)` twice). A board that has 4 is left alone; a board that has any
  other count is refused (this tool never takes layers out).

The inner layers are **signal layers carrying a polygon pour**, not negative internal planes: the pour is the same object the
bottom ground pour always was (same net rule, thermal relief by the board's polygon-connect rule, `RemoveDead`), the router and
the pour check (`pourcheck`) read it with the code they have, and Gerber writes `.G1` / `.G2`.

`bridge.ensure_stack(prj, pcb, 4)` runs before anything is placed or routed, after the backup of the board
(`.advisor-backup`): `STACK` + `PCBSAVE`, board closed, the file read back; **the file must hold 4 copper layers** or the
step raises and puts the board back. `bridge.stack_mismatch(layers, have)` is the one refusal text: project 2 / file 4,
project 4 / file 6, a stack that cannot be read.

Thicknesses and dielectrics (7628 prepreg 0.2104 mm Er 4.4 on L1-L2 and L3-L4, core 1.065 mm Er 4.6 on L2-L3, copper 1.6 mil
outside / 0.6 mil inside): **the Altium scripting API does not set them**. Setting `CopThickness` / `Dielectric.*` from the
script stopped the executor with an error dialog every time, and that error cannot be caught in DelphiScript. The layers
therefore get Altium's own default stack numbers; the layer COUNT is what the copper, the Gerbers and JLC use. JLC builds the
stack-up it sells from the order, not from the file. For impedance, set the dielectrics in Altium (Design > Layer Stack Manager) from
`shared/reference/jlc/pcb-capabilities.en.md`.

## Planes and the router

`route.plane_nets_for(doc)` picks the plane nets: **GND on Mid-Layer 1** (the ground net with at least 3 pads, as the old
bottom pour) and the **main supply on Mid-Layer 2** (the rail-named net, not ground, with the most pads, at least 3; `3V3`,
`+5V`, `VCC` ...). A board with only one of them gets one plane; none is invented; the choice is in the route result
(`planes`) and in the summary. Everything else stays signal.

The router stays a two-layer grid router (top 1, bottom 32). A plane net is not routed by tracks: it is **dropped**:

* a through-hole pad is in the plane by itself;
* an SMD pad on **either** outer layer gets a short stub (exact-geometry, `_drop_exact`) or a grid path (`astar`
  `goal_layer`) to a via cell where a via is legal (the via clearance rules of the board) and a via goes through to the plane. The
  A\* goal is "arrive on the other outer layer at a via" so the search is the same for top and bottom pads;
* plane nets are laid **first** (`order`), short stubs, and the signals route round them. A plane net that is ripped up by the
  signal rounds is laid again as a plane net (never as a web of tracks).

No signal track is ever drawn on an inner layer. The commands then end with one `POLY mid1 GND ...` and `POLY mid2 <supply> ...`
per rectangle of the board (less the antenna keep-outs, `pour_rects`), after the tracks and vias.

`capability_check(doc, layers=4)` allows the inner pours (a polygon on Mid-Layer 1 or 2) and still refuses any other inner copper.

## Checks, fail closed

After drawing and saving (`route_on`):

1. `layout.unrouted` does not read pours, so plane-net pads show as open; they are taken out of that list and checked below.
2. For each plane: `poured_copper(pcb, layer=2|3)` must be > 0 (Altium filled the pour), else a problem
   ("the GND plane on Mid-Layer 1 was drawn but is not in the saved board as copper").
3. `pourcheck.check(saved, net=plane net)`: every pad / via of the net must touch its pour piece; unjoined pads are problems, cut-off
   islands are warnings.
4. Altium's design rule check: no new Clearance / Short-Circuit / Width violations over the check made before routing, and **0
   Un-Routed Net** (Altium counts a net joined through a polygon as routed).

Any problem puts the backed-up board back (`_restore`). The board shape Altium holds must be the outline for a pour to fill; when it
cannot be set, the planes are refused with the Altium menu path (no silent empty plane).

## Outputs

The OutJob's Gerber configuration already plots layer ids 16777218 / 16777219 (Mid-Layer 1 / 2), so a 4-layer board gets
`.G1` and `.G2` with no change; `jlc_upload.classify` knows `.G<n>` (inner copper) and `.GP<n>` (inner plane) and
`gerber_check.copper_problems` compares the copper files with `copper_layer_count(PcbDoc)`. The outputs gate itself is untouched.

## Tests and the live run

`tests/test_four_layer.py` (validation, endpoints, text sync, router plane nets, commands, capability check, stack mismatch).
The live run on a scratch project is in the results section below.

## Live run, 2026-11-24

Scratch project `FourLayer-Live-2026-11-24b` made with the app's own stores and bridge actions (new project, library.build,
draw_schematic, place_pcb, import_rules, route_pcb; `board.layers` = 4; 11 parts: NE555, a 2-pin header, 0603/0805 passives, an LED;
60 x 45 mm). The first scratch project of that name, `FourLayer-Live-2026-11-24`, was stopped before placing: its sheet (the LED
chaser) did not fit one A4 sheet. Nothing of it is used.

* `place_pcb` set the stack-up before placing (backup first): the file has **4 copper layers** (`copper_layer_count` = 4, layers
  Top, Mid-Layer 1, Mid-Layer 2, Bottom).
* `route_pcb`: 7 nets routed, 51 tracks, 8 vias, `planes: GND on mid1, +5V on mid2`, no open nets.
* Reader on the saved PcbDoc: poured copper on layer 2 (GND) and layer 3 (+5V), none on top / bottom; **0** tracks, vias-as-copper
  or pads of anything else on the inner layers; tracks only on top / bottom; `pourcheck` GND and +5V: ok, 0 islands, 0 unjoined pads.
* Altium's own DRC: Clearance 0, Short-Circuit 0, Un-Routed Net 0, Width 0, Minimum Annular Ring 0, Hole To Hole 0, Board Clearance
  0, Net Antennae 0 (12 total: 7 solder-mask slivers and 5 silk-to-mask items of the footprints, the same kind the 2-layer route reports).
* `run_outjob`: Gerbers `.GTL .GBL .G1 .G2 ...` and drills are written, the inner layers as `.G1` / `.G2`.

What the live run did not exercise: a board with an unfilled inner pour, a board shape that differs from the outline, and a
re-route of a board that already has the planes (`replace`).
