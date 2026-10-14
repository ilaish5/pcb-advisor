# JLCPCB bare-board capabilities (rigid FR-4; flex and metal core in brief)

> Source: the JLCPCB capabilities page and help-center articles in the table below, all read 2026-10-14. Condensed to numbers and rules; marketing text and the HDI, backdrill and blind-slot detail are trimmed (read [P1] for those). JLC changes these pages: re-read the page before you give a number as current, and quote it with the page and the date.

Covers: minimum geometry per process (trace/space, drills, vias, annular ring, spacing to holes and edges), solder mask, silkscreen,
board size, thickness, outline, slots, castellations, V-cut, copper weight, surface finish, impedance stack-ups, panelization, and the
options that change a limit or the price. Assembly limits: `assembly-capabilities.en.md`. File formats: `files-and-formats.en.md`.

## Sources
"Page date" is the "Last updated" stamp the page shows (most help pages carry Sep 09, 2026, a site-wide restamp). All read 2026-10-14.

| ID | Page | URL | Page date |
|---|---|---|---|
| P1 | Rigid PCB Manufacturing Capabilities | https://jlcpcb.com/capabilities/pcb-capabilities | none shown |
| P2 | Ordering Instructions for PCB Manufacturing | https://jlcpcb.com/help/article/instructions-for-ordering | 2026-09-09 |
| P3 | JLCPCB Copper Weight (Thickness) Guide | https://jlcpcb.com/help/article/jlcpcb-copper-weight | 2026-09-09 |
| P4 | PCB Dimensions | https://jlcpcb.com/help/article/pcb-dimensions | 2026-09-09 |
| P5 | Via Covering: Tented, Untented, Plugged, Filled | https://jlcpcb.com/help/article/pcb-via-covering | 2026-09-09 |
| P6 | Difference and Tolerance Between Via and Pad Holes | https://jlcpcb.com/help/article/difference-and-tolerance-explanation-between-via-and-pad-holes | 2025-04-24 |
| P7 | Common Mistakes When Using Altium Designer | https://jlcpcb.com/help/article/common-mistakes-when-using-altium-designer | 2026-09-09 |
| P8 | What is Castellated holes / half-holes? | https://jlcpcb.com/help/article/what-is-castellated-holes | 2026-09-09 |
| P9 | PCB Design Instructions for Edge Plating | https://jlcpcb.com/help/article/pcb-design-instructions-for-edge-plating | 2026-09-09 |
| P10 | PCB Panelization | https://jlcpcb.com/help/article/pcb-panelization | 2026-09-09 |
| P11 | How do I order a panel? | https://jlcpcb.com/help/article/how-do-i-order-a-panel | 2026-09-09 |
| P12 | How JLCPCB Defines Different PCB Designs | https://jlcpcb.com/help/article/different-design-in-your-pcb-files | 2026-09-09 |
| P13 | In what cases will there be charged extra? | https://jlcpcb.com/help/article/in-what-cases-will-there-be-charged-extra | 2026-09-09 |
| P14 | Introduction to JLCPCB Surface Finishes | https://jlcpcb.com/help/article/jlcpcb-surface-finish | 2026-09-09 |
| P15 | Multi-Layer PCB Standard Laminated Structures | https://jlcpcb.com/help/article/multi-layer-pcb-standard-laminated-structures | 2026-09-09 |
| P16 | User Guide to the JLCPCB Impedance Calculator | https://jlcpcb.com/help/article/User-Guide-to-the-JLCPCB-Impedance-Calculator | 2026-09-16 |
| P17 | Controlled Impedance PCB Layer Stackup (older page, still served) | https://jlcpcb.com/impedance | none shown |
| P18 | Flexible PCB Manufacturing Capabilities | https://jlcpcb.com/capabilities/flex-pcb-capabilities | none shown |
| P19 | How to Order Boards with Solder Mask Defined Pads | https://jlcpcb.com/help/article/how-to-order-boards-with-solder-mask-defined-pads | 2025-04-24 |
| P20 | Suggested Naming Patterns | https://jlcpcb.com/help/article/suggested-naming-patterns | 2026-09-09 |
| P21 | How to mark on PCB? | https://jlcpcb.com/help/article/how-to-mark-on-pcb | 2026-05-22 |
| P22 | Specifications for Adding Process Edges and Positioning Holes | https://jlcpcb.com/help/article/specifications-for-adding-process-edges-and-positioning-holes | 2026-09-09 |
| P23 | How to Prepare Gerber Files Before Placing Orders? | https://jlcpcb.com/help/article/gerber-files-preparation | 2026-09-09 |
| P24 | PCB Assembly FAQ (Part 2) | https://jlcpcb.com/help/article/pcb-assembly-faqs-part-2 | 2026-09-09 |

## How to read these numbers
- A JLC minimum is not a design value; design above it (margins: `runtime/skills/rules-and-calcs`). "Absolute minimum" is JLC's word.
- Pick the column for the board: "1-2 layer" = single/double sided FR-4, "multilayer" = 4 layers and up. Copper weight changes the limits too.
- Values marked "(costs more)" are possible but add a surcharge or need an order option. Where JLC pages disagree see "Conflicts".

## Traces and spacing
| Item | 1-2 layer | Multilayer | Notes | Src |
|---|---|---|---|---|
| Min track / space, 1 oz | 0.10 / 0.10 mm (4 / 4 mil) | 0.09 / 0.09 mm (3.5 / 3.5 mil) | multilayer: 3 mil acceptable in BGA fan-outs | P1 |
| Min track / space, 2 oz | 0.16 / 0.16 mm (6.5 mil) | 0.15 / 0.15 mm (6 mil) | P3 lists 0.16 mm for 2 oz on any layer count | P1, P3 |
| Min track / space, 2.5 / 3.5 / 4.5 oz | 0.20 / 0.25 / 0.30 mm | not offered | heavy copper is 2-layer only | P1, P3 |
| Track width tolerance | ±20 % | ±20 % | 0.10 mm drawn gives 0.08-0.12 mm | P1 |
| Pad to track (1 oz) | 0.1 mm | 0.1 mm | "stay well above if possible"; 0.09 mm locally at BGA pads | P1 |
| SMD pad to pad, different nets | 0.15 mm | 0.15 mm | min SMD pad 0.25 x 0.25 mm | P1 |
| Same-net track spacing | 0.25 mm | 0.25 mm | hatched pour grid width/spacing 0.25 mm | P1 |
| Via hole to track | 0.2 mm | 0.2 mm | | P1 |
| PTH (hole) to track | 0.28 mm min, 0.35 mm recommended | same | | P1 |
| NPTH to track | 0.2 mm | 0.2 mm | | P1 |
| Inner layer: via hole / PTH hole to copper | - | 0.2 mm / 0.3 mm | | P1 |
| Trace coils | 0.15 / 0.15 mm under mask; 0.25 / 0.25 mm bare (ENIG only) | same | bare coils with HASL risk shorts | P1 |
| BGA | pad 0.2-0.25 mm needs ENIG; pad to trace >= 0.1 mm | pad to trace min 0.09 mm | via in BGA pad only as filled and plated-over via | P1 |

- Multilayer trace/space of 3.0-3.5 mil is charged as a difficult process: +20 % of the order for 4-8 layers, +30 % for 10+ layers [P13].
- Long narrow dangling traces can short through dry-film bridging: delete them or connect the end at 5 mil or wider [P7].

## Drills, vias and annular ring
| Item | Value | Src |
|---|---|---|
| Drill diameter range | 1-layer 0.3-6.3 mm; 2-layer and multilayer 0.15-6.3 mm. Holes >= 6.3 mm are CNC-routed from a smaller drill | P1 |
| Smallest drill | 0.1 mm on 2+ layers (costs more; only board thickness <= 1 mm with ENIG/OSP); aluminium core 0.65 mm; copper core 1.0 mm | P1 |
| PTH hole tolerance | +0.13 / -0.08 mm (0.6 mm drawn gives 0.52-0.73 mm); press-fit +/-0.05 mm (finished 0.55-2.0 mm, multilayer ENIG, round holes, name them in the PCB Remark) | P1 |
| Via hole tolerance | not controlled: JLC may merge or shrink via drills; vias must not hold component leads | P6, P5 |
| Recommended PTH size | >= 0.5 mm, so mask or tin does not stick in the hole | P1 |
| Hole position tolerance / plating | +/-0.075 mm / 18 um average copper in the barrel | P1 |
| Min via hole / diameter | 0.15 / 0.25 mm (2-layer and multilayer); 0.1 / 0.2 mm only for <= 1 mm thick boards with ENIG/OSP; 1-layer (NPTH only) 0.3 / 0.5 mm | P1 |
| Via diameter rule | diameter >= hole + 0.1 mm (+0.15 mm preferred); preferred min via hole 0.2 mm | P1 |
| Via price steps | 0.1 or 0.15 mm hole (any diameter), or 0.2 / 0.25 mm hole with diameter < 0.45 mm, costs more: choose the matching via option at order | P1 |
| PTH annular ring | headline >= 0.20 mm. 2-layer 1 oz: 0.25 mm recommended, 0.18 mm absolute min; 2 oz: >= 0.254 mm. Multilayer 1 oz: 0.20 mm recommended, 0.15 mm absolute min; 2 oz: >= 0.254 mm | P1 |
| NPTH pad ring | >= 0.45 mm recommended (0.2 mm of copper is removed around the hole for the sealing film) | P1 |
| Min non-plated hole | 0.50 mm; draw NPTHs on the mechanical or keep-out layer | P1 |
| Hole to hole | via-to-via 0.2 mm; pad-to-pad 0.45 mm | P1 |
| Plated slot | min width 2-layer 0.5 mm, multilayer 0.35 mm; length >= 2 x width; drawn with a pad; drilled, tolerance +0.13 / -0.08 mm | P1, P2 |
| Non-plated slot | min width 1.0 mm; draw its outline on GM1 or GKO (the outline layer); CNC-routed, tolerance +/-0.2 mm | P1, P7 |
| Rectangular holes or slots | not supported without rounded corners | P1 |
| Via in pad | epoxy- or copper-paste-filled and capped, via diameters 0.15-0.55 mm; default (free) on 6+ layer boards | P1, P5 |

Note: the ring figures are for plated component holes. A via at the 0.15 / 0.25 mm minimum has a 0.05 mm ring: via rings follow the via
diameter rule, not the PTH ring rule. Altium's single MinimumAnnularRing rule covers both, so scope it if vias and pads need different values.

## Solder mask
- LPI mask, colours Green, Purple, Red, Yellow, Blue, White, Black [P1].
- Expansion: pad-to-opening 1:1 is possible since the LDI upgrade of June 2025 (a reorder follows its old production file). Keep
  >= 0.09 mm between a mask opening and a neighbouring trace [P1]. P7 calls 0.1 mm the generally recommended expansion and warns that a
  negative expansion covers the pad.
- Mask bridge (dam between pads), 1 oz copper: 0.10 mm for green, red, yellow, blue, purple; 0.13 mm for black and white. 2 oz: 0.20 mm,
  any colour [P1]. The colour therefore changes the minimum pad gap that keeps a dam.
- No mask layer, or an empty one, means the whole board is covered [P2 #19]. Where silkscreen overlaps an opening, the opening wins and
  the silk is dropped unless a remark asks otherwise [P2 #9].
- Mask dielectric constant 3.8; ink >= 10 um [P1]. For impedance JLC models mask as 1.2 mil on laminate, 0.6 mil on copper, 1.2 mil
  between traces [P15, P16].
- Solder-mask-defined pads (mask smaller than copper): leave >= 3 mil (0.076 mm) of mask on every side. There is no order option: write a
  PCB Remark naming the parts and choose Confirm Production File, otherwise CAM enlarges the openings to NSMD [P19].
- Altium pitfalls JLC lists: "Force complete tenting" covers pads; through-hole pads drawn as vias get tented with "tented vias" [P7].

### Via covering options [P5, P1]
| Option | What it is | Limits |
|---|---|---|
| Tented (most common) | vias covered with mask, no finish on them | via holes ideally <= 0.4 mm, max 0.5 mm; larger ones not guaranteed covered; yellow/brown rings are normal |
| Untented | vias bare, same finish as pads | with HASL keep bare vias >= 0.2 mm from other exposed copper (use ENIG to go closer) |
| Plugged | mask ink pushed into the hole, then tented | holes <= 0.5 mm; no opening on either side; >= 0.35 mm from other mask openings; via-in-pad cannot be ink-plugged |
| Epoxy-filled and capped | resin fill, plated over | holes <= 0.5 mm recommended; say which vias (diameter or image) in the remark; resin filling free on 6+ layers [P5] |
| Copper-paste-filled and capped | conductive fill (8 W/m.K), plated over | as above |

## Silkscreen (legend)
| Item | Value | Src |
|---|---|---|
| Min line width | >= 0.15 mm ("less than 0.15 mm will be unidentifiable") | P1 |
| Min text height | 1.0 mm (40 mil) | P1 |
| Width : height | 1:6 preferred (also for hollow characters) | P1 |
| Pad to silkscreen | 0.15 mm | P1 |
| Letter spacing; outline fonts | >= 0.15 mm between letters; fill lines >= 0.15 mm, hollow part > 0.2 mm | P2 #9 |

- JLC does not check silkscreen and may widen thin text to 0.15 mm; complaints about unreadable non-standard text are not accepted [P2 #9].
- Top text upright, bottom text mirrored in the design; slots drawn only in silkscreen are not made; silk on exposed copper is not
  printed unless asked [P7].
- No mark is added to the board by default. The order-number service ended in May 2026: do not put "JLCJLCJLCJLC" on the silkscreen.
  An optional 2D barcode / serial number (5x5, 8x8 or 10x10 mm) can be placed via a solid silkscreen square of that size [P21].
- Aluminium boards: white silkscreen on green or black mask, black silkscreen on white mask [P2 #9].

## Outline, board size and thickness
- Outline layer [P2 #7, #12, #17]: V-cut lines, slots, cutouts and milling must be on the same layer as the outline, or they are missed.
  If several layers hold a complete outline, the GM layer wins; among GM, GM1, GM3... the lowest number is used and the rest ignored.
  Keep exactly one outline layer. Draw outline lines 0.15 mm wide; wider lines are cut on their centre line.
- Copper to edge: routed edge or routed slot >= 0.2 mm; V-cut edge >= 0.4 mm; non-mouse-bite edges of a mouse-bite panel >= 0.2 mm [P1].
  For Economic assembly JLC asks > 0.3 mm from traces and components to the edge (depanel tolerance about 0.2 mm) [P24 #14].
- Edge tolerance: routed +/-0.2 mm regular, +/-0.1 mm high precision (board >= 50 x 50 mm and >= 3 tooling holes of >= 1.5 mm on
  different corners); V-cut +/-0.4 mm; general dimension tolerance +/-0.1 mm [P1].
- Size [P1, P4]:

| Material | Min | Max |
|---|---|---|
| FR-4 | 3 x 3 mm (P1: for thickness >= 0.6 mm, thinner needs manual review; P4: 3 x 3 for >= 0.8 mm, 5 x 5 for < 0.8 mm) | 1-layer 606 x 510; 2-layer 670 x 600 (up to 1020 x 600 at 1.0-2.0 mm, 1-2 oz); 4-layer 663 x 593 (up to 1016 x 596); 6+ layers 656 x 586; any board < 0.8 mm thick 599 x 497 mm |
| Castellated / plated edges | 10 x 10 mm | as FR-4 |
| Aluminium / copper core | 5 x 5 mm | 602 x 506 / 480 x 286 mm |
| Rogers / PTFE | 3 x 3 mm | 590 x 438 mm |

- Boards <= 50 x 50 mm are hard to mill cleanly: panelize them [P2 #18]. Boards > 200 x 250 mm: if not enough good boards come out, JLC
  ships the good ones and refunds the rest [P2 #16]. JLC does not make 3-layer boards; a 4-layer file with one inner layer is built as
  4-layer after a confirmation [P2 #10].
- Thickness: 0.4-4.5 mm overall; FR-4 options 0.4 / 0.6 / 0.8 / 1.0 / 1.2 / 1.6 / 2.0 mm (2.5 mm and up only for 12+ layers).
  Tolerance +/-10 % at >= 1.0 mm (1.6 mm gives 1.44-1.76 mm), +/-0.1 mm below 1.0 mm [P1].

## Castellated holes, plated edges
- Castellated (plated half holes): hole >= 0.5 mm, hole to board edge >= 1 mm, hole to hole >= 0.5 mm, board >= 10 x 10 mm and >= 0.6 mm
  thick [P1]. P8 says hole size and spacing >= 0.6 mm (see Conflicts). Design: copper pad on top and bottom, mask opening on both
  sides, a drill hit, outline crossing the hole. Order option "Yes" = special process at extra cost; "No" = ordinary process, quality not
  promised [P8]. OSP is a poor finish for castellated modules [P14].
- Plated edges: ENIG only (no HASL), board >= 10 x 10 mm and >= 0.6 mm thick, >= 3 breaks in the plating for support tabs [P1]; leave
  3-4 unplated segments >= 3 mm long, supply a marked drawing or layer, select Edge Plating and describe it in the PCB Remark [P9].
- Economic assembly does not accept gold fingers, castellated holes or edge plating (`assembly-capabilities.en.md`).

## Copper weight
- 1 oz = 35 um [P3]. Finished outer copper: 2-layer 1 / 2 / 2.5 / 3.5 / 4.5 oz; multilayer 1 / 2 oz. Inner: 0.5 oz (default) / 1 / 2 oz
  [P1, P3]; availability depends on layer count and thickness, check the order page [P3]. Finished inner 0.5 oz is 15.2 um, not 17.5 um [P15, P16].

## Surface finish
| Finish | Where it is (not) offered | Notes | Src |
|---|---|---|---|
| HASL leaded / lead-free | not on FR-4/HDI with 6+ layers, boards <= 0.4 mm, high-frequency, copper core, FPC; aluminium is HASL only | coating ~1-40 um, not flat: poor for fine pitch and BGA; leaded is not RoHS | P1, P14 |
| ENIG | all; required for 0.2-0.25 mm BGA pads, 0.1 mm microvias (or OSP), bare trace coils, plated edges | Ni 3-6 um, Au 1 or 2 u-inch, flat; extra cost if exposed area > 30 % | P1, P13, P14 |
| OSP | not on single-sided FR-4, FPC, aluminium | flat, no extra charge, ~3 months shelf life unopened; not for gold fingers or castellated modules | P1, P14 |

ENIG area surcharge: above 30 % exposed copper (top + bottom, out of 200 %), $0.8992/m2 per % (1 u-inch) or $1.7985/m2 per % (2 u-inch) [P13].

## Impedance control and stack-ups
- Controlled impedance on 4-32 layers, tolerance +/-10 % [P1]; 2-layer boards are not in the list. P1's FAQ adds +/-5 % on request;
  P15 mentions free standard impedance testing at +/-20 % (see Conflicts).
- Calculator: https://jlcpcb.com/pcb-impedance-calculator. Inputs: layers, finished thickness, inner copper 0.5 or 1 oz only, outer 1 oz
  only, 20-90 ohm single-ended, 50-150 ohm differential, coplanar or not, reference layers. The first stack-up it proposes is the cheapest
  and fastest [P16].
- Model values [P16]: outer 1 oz 1.6 mil; inner 0.5 oz 0.6 mil; inner 1 oz 1.2 mil; mask 1.2 / 0.6 / 1.2 mil, Er 3.8; trace top width =
  base width - 0.7 mil; core material NP-155F for 4-8 layers, S1000-2M for 10+. Prepreg Er: 7628 4.4, 3313 4.1, 2116 4.16 [P1], 1080 3.91;
  core Er 4.6 [P17]; FR-4 2-layer Er 4.5 [P1].
- 4-layer 1.6 mm, 1 oz outer / 0.5 oz inner, single-prepreg stacks from the older stack-up page [P17] (JLC now lists over 200
  structures [P15]; confirm the code on the order page or in the calculator before using it):

| Stack code | L1-L2 and L3-L4 prepreg | Core (L2-L3) |
|---|---|---|
| JLC04161H-7628 | 7628 x1, 0.2104 mm, Er 4.4 | 1.065 mm |
| JLC04161H-2116 | 2116 x1, 0.1164 mm, Er 4.16 | 1.265 mm |
| JLC04161H-3313 | 3313 x1, 0.0994 mm, Er 4.1 | 1.265 mm |
| JLC04161H-1080 | 1080 x1, 0.0764 mm, Er 3.91 | 1.265 mm |

A thinner prepreg gives a narrower 50 ohm trace. The 3313 prepreg replaced 2313 with the same thickness and Er [P15, P16].

## Panelization and V-cut
- V-cut [P1, P10, P11]: copper >= 0.4 mm from the cut; tolerance +/-0.4 mm; board >= 0.6 mm thick (not on 0.4 mm); panel 70 x 70 to
  475 x 475 mm; groove angle 25 degrees; zero gap between boards by default; >= 2 mm between two parallel cuts (3 mm recommended);
  straight lines that cross the whole panel; at most 25 V-cut lines per axis; a single board < 15 mm on a side costs extra [P13].
- Mouse bites [P1]: edge clearance >= 0.2 mm; board spacing 1.6 or 2 mm; bite holes 0.5-0.8 mm, 0.2-0.3 mm apart; breakaway tab >= 4 mm
  (>= 5 mm with mouse bites); tooling edge >= 3 mm. For JLC SMT: 5 mm tooling edges, 2 mm tooling holes, 1 mm fiducials centred 3.85 mm
  from the panel edge [P1, P22]. Boards in a routed panel >= 2 mm apart [P1].
- Panel by JLCPCB: give rows x columns; a 5 mm board edge is added by default; JLC panels with V-cut and only rectangular or round
  boards; complex outlines must be panelized by the customer [P2 #14, P11]. A customer panel ordered as "Single PCB" may hold <= 5
  designs, as "Panel by Customer" <= 10 [P2 #14].
- Different designs in one Gerber cost extra. Anything separable by V-cut, milling or holes counts as a separate design. Free trick:
  several designs inside one rectangular outline, split by silkscreen lines only, cut apart by you; more than 5 designs is still charged,
  max 10 [P10, P12].

## Options and features that change the bare-board price [P13 unless noted]
Different designs in one file; V-cut on boards < 15 mm; routing fee when 0.8-1.0 mm slots reach 80 m/m2 of path or > 1.0 mm slots reach
120 m/m2 (mixed widths are charged at the 0.8-1.0 mm rate, so widen slots above 1.0 mm); holes below the 0.3 mm "standard"; ENIG > 30 %;
uncommon option sets ("special process", warned at order); > 150,000 holes/m2; >= 8,000 test points per piece; board length >= 60 cm
($31.43 per design); 3.0-3.5 mil multilayer trace/space; boards > 650 cm2; keyboard PCBs ($16.41 + $49.25/m2); small boards (<= 3 cm side
delivered as single PCB); deburring of 1.5-3 cm boards $0.02/pc and < 1.5 cm $0.05/pc. A single board <= 102 x 102 mm has a special
price that does not apply once it is panelized [P13 #7]. Remarks in English slow the audit [P2 #15].

## Metal core and flex (brief)
- Aluminium: 1-layer, HASL only, min drill 0.65 mm, min slot 1.6 mm, 5 x 5 to 602 x 506 mm [P1]. Copper core: 1-layer with direct
  heatsink pads (>= 1 x 1 mm [P1]; heatsink pad width >= 1 mm, separate from other pads [P23]), min drill 1.0 mm [P1].
- Flex [P18]: 1, 2 or 4 layers, no rigid-flex; trace/space 3/3 mil (12 um copper, 2/2 mil absolute), 3.5/3.5 mil (18 um), 4/4 mil
  (35 um); regular via 0.3 / 0.55 mm; PTH ring 0.25 mm recommended, 0.18 mm absolute; ENIG only; max 234 x 490 mm. Full table in [P18].

## Conflicts between JLC sources
The last column is the value that satisfies both pages (the advisor's reading, not a JLC statement).

| Topic | One source | The other | Satisfies both |
|---|---|---|---|
| Max thickness | P1 table: 0.4-4.5 mm | P1 FAQ: 0.4-3.2 mm | FR-4 options stop at 2.0 mm below 12 layers anyway |
| Heavy copper | P1 table: up to 4.5 oz (2-layer) | P1 FAQ: "up to 3oz" | <= 3 oz, or confirm with JLC |
| Impedance tolerance | P1: +/-10 % (FAQ: +/-5 % on request) | P15: free standard impedance test at +/-20 % | ask JLC which tolerance the chosen test option guarantees |
| Mask bridge | P1: 0.10 mm (1 oz, green etc.) for any layer count | P2 #1: pad gap >= 0.2 mm on 1-2 layer, 0.1 mm multilayer, and a remark "solder mask bridge is required" | 2-layer: >= 0.2 mm gap plus the remark |
| Castellated hole | P1: hole >= 0.5, hole to hole >= 0.5 mm | P8: hole size and spacing >= 0.6 mm | >= 0.6 mm |
| Min board size | P1: 3 x 3 mm at >= 0.6 mm thick | P4: 3 x 3 at >= 0.8 mm, 5 x 5 below | 5 x 5 mm below 0.8 mm thick |
| Blind / buried vias | P1: HDI 1-3 step offered | P6, P20 (older text): blind/buried not processed | treat HDI as a special, dearer process; confirm before designing |
| 2 oz multilayer track | P1: 0.15 mm | P3: 0.16 mm "any layer" | 0.16 mm |
| Mask expansion | P1: 1:1 possible, >= 0.09 mm opening to trace | P7: 0.1 mm "generally recommended" | any expansion from 0 to 0.1 mm that keeps >= 0.09 mm to traces |
