# JLCPCB assembly (PCBA): services, limits, parts library, fees, lead times

> Source: the JLCPCB PCBA capabilities page, price guide and help-center articles in the table below, all read 2026-10-14. Condensed to rules and numbers; marketing text trimmed. Fees are in USD as shown on the day read; JLC notes they "may vary slightly due to exchange rate fluctuations" [A2]. Stock and part prices are never taken from here: run `check_availability.py` and quote its time.

Covers: Economic vs Standard PCBA, sides, minimum package and pitch, part spacing, edge rails, fiducials, tooling holes, the parts library
classes (Basic, Preferred/Promotional Extended, Extended) and how the fees work, consigned / global-sourcing / pre-order parts,
through-hole, what JLC will not place, quantities, lead times, inspection. File formats: `files-and-formats.en.md`. Ordering steps:
`ordering-workflow.en.md`.

## Sources
All read 2026-10-14. "Page date" is the "Last updated" stamp on the page.

| ID | Page | URL | Page date |
|---|---|---|---|
| A1 | PCB Assembly Capabilities | https://jlcpcb.com/capabilities/pcb-assembly-capabilities | none shown |
| A2 | PCB Assembly Cost: What Does the Price Include? | https://jlcpcb.com/help/article/pcb-assembly-price | 2026-09-09 |
| A3 | PCB Assembly FAQs | https://jlcpcb.com/help/article/pcb-assembly-faqs | 2026-09-09 |
| A4 | PCB Assembly FAQ (Part 2) | https://jlcpcb.com/help/article/pcb-assembly-faqs-part-2 | 2026-09-09 |
| A5 | Basic & Promotional Extended Components (parts library) | https://jlcpcb.com/parts/basic_parts | live list |
| A6 | PCBA Parts Sourcing Instruction | https://jlcpcb.com/help/article/pcba-parts-sourcing-instruction | 2026-09-09 |
| A7 | How to use my own parts for PCB assembly order | https://jlcpcb.com/help/article/how-to-use-my-own-parts-for-pcb-assembly-order | 2026-09-09 |
| A8 | How to use JLCPCB Global Sourcing Parts Service? | https://jlcpcb.com/help/article/how-to-use-jlcpcb-global-sourcing-parts-service | 2026-09-09 |
| A9 | Important note before you consign the part to JLCPCB | https://jlcpcb.com/help/article/important-note-before-you-consign-the-part-to-jlcpcb | 2026-09-09 |
| A10 | Component Matching Guidelines for PCBA Orders | https://jlcpcb.com/help/article/component-matching-guidelines-for-pcba-orders | 2026-09-09 |
| A11 | Common BOM / CPL Matching Issues and Explanations | https://jlcpcb.com/help/article/common-bom-and-cpl-matching-issues-and-explanations | 2026-09-09 |
| A12 | SMT Service Lead Time Overview | https://jlcpcb.com/help/article/smt-service-lead-time-overview | 2026-09-09 |
| A13 | JLCPCB Supported Personalized Services | https://jlcpcb.com/help/article/jlcpcb-supported-personalized-services | 2026-09-09 |
| A14 | Minimum Spacing Requirements for SMD Components | https://jlcpcb.com/help/article/minimum-spacing-for-smd-components | 2026-09-09 |
| A15 | How to add tooling holes for PCB assembly order | https://jlcpcb.com/help/article/how-to-add-tooling-holes-for-pcb-assembly-order | 2026-09-09 |
| A16 | How to Add Edge Rails and Fiducials for PCB Assembly Orders | https://jlcpcb.com/help/article/how-to-add-edge-rails-fiducials-for-pcb-assembly-order | 2026-09-09 |
| A17 | Panelizing your PCB for Assembly | https://jlcpcb.com/help/article/panelizing-your-pcb-for-assembly | 2026-09-09 |
| A18 | PCB Assembly Fixtures | https://jlcpcb.com/help/article/pcb-assembly-fixtures | 2026-09-09 |
| A19 | How Is SMT Stencil Data Prepared for JLCPCB SMT Orders? | https://jlcpcb.com/help/article/smt-stencil-data-prepared-for-smt-orders | 2026-09-09 |
| A20 | Introduction for using SMT Mechanical assembly components | https://jlcpcb.com/help/article/introduction-smt-mechanical-assembly-components | 2026-09-09 |
| A21 | What Inspection Capabilities Does JLCPCB's SMT Assembly Service Provide? | https://jlcpcb.com/help/article/smt-inspection-and-testing-capabilities | 2026-09-09 |
| A22 | SMT PCB Assembly Service (landing page) | https://jlcpcb.com/pcb-assembly | none shown |
| A23 | Terms and Conditions of JLCPCB Parts Selection Service | https://jlcpcb.com/help/article/terms-and-conditions-of-jlcpcb-parts-selection-service | 2026-09-24 |
| A24 | Components Pickup Pricing | https://jlcpcb.com/help/article/components-pickup-pricing | 2026-09-09 |
| A25 | PCB Panelization | https://jlcpcb.com/help/article/pcb-panelization | 2026-09-09 |
| A26 | Specifications for Adding Process Edges and Positioning Holes | https://jlcpcb.com/help/article/specifications-for-adding-process-edges-and-positioning-holes | 2026-09-09 |
| A27 | X-Ray Inspection Report Interpretation Guide | https://jlcpcb.com/help/article/x-ray-inspection-report-interpretation-guide | 2026-09-09 |

## Economic vs Standard PCBA [A1]
| Feature | Economic PCBA | Standard PCBA |
|---|---|---|
| Sides placed | one side only (SMT / through-hole) | one or both sides |
| PCB layers | 2, 4, 6 | 1-32 |
| Board thickness | 0.8-1.6 mm | no limit |
| Single PCB size | 10 x 10 to 470 x 500 mm | 70 x 70 to 460 x 500 mm |
| Panel size | 10 x 10 to 250 x 250 mm | 70 x 70 to 250 x 250 mm |
| Order quantity | 2-50 pcs | 2-80,000 pcs |
| Finish, colour | only the combinations in the next table | no limit |
| Delivery format | single PCB, panel with mouse bites | single, mouse-bite panel, V-cut panel |
| Stack-up | standard only | all |
| Gold fingers, castellated holes, edge plating | not supported | supported |
| Edge rails / fiducials | not necessary / not necessary | necessary / necessary |
| Smallest package | 0402 | 0201 (see Conflicts: 01005) |
| Min IC pin pitch | 0.4 mm | 0.35 mm |
| Min BGA pitch (centre to centre) | 0.5 mm | 0.3 mm |
| Reflow peak | 255 +/-5 C, not adjustable | 240 +/-5 C |
| SPI / AOI / visual / X-ray | no / yes / yes / yes for some parts (BGA) | yes / yes / yes / yes for some parts |
| Build time | 1-3 days | >= 4 days |

Economic board options [A1] (the page's "Layer" column is not readable in the page source; the rows below are in page order):

| Thickness | Colour | Finish | Qty |
|---|---|---|---|
| 0.8 | Green | HASL lead-free or leaded | 2-30 |
| 1.0 / 1.2 | Green or Black | HASL lead-free or leaded | 2-30 |
| 1.6 | Green | HASL or ENIG (lead-free or leaded) | 2-50 |
| 1.6 | Black | HASL | 2-50 |
| 1.6 | Blue, Purple | HASL | 5-30 |
| 1.6 | Red, White | leaded HASL only | 5-30 |
| 1.0 / 1.2 / 1.6 / 1.6 (second group) | Green | HASL; HASL; HASL or ENIG; ENIG | 2-30; 2-50; 2-50; 2-30 |

Panels above 250 x 250 mm are accepted by the system at the customer's risk (bending, placement and soldering defects) [A1 FAQ].

- A part marked "Standard Only" cannot be placed in an Economic order: switch to Standard or mark it "Do not place" [A11].
- More than 30 boards on Economic: panelize (panel <= 250 x 250 mm) or choose Standard [A3 #10]. Economic panels use mouse bites only;
  V-cut needs Standard [A3 #11, A25 #7].
- Economic boards are routed apart after assembly with about 0.2 mm tolerance: keep traces and components > 0.3 mm from the edge [A4 #14].

## Placement limits and part spacing
- Minimum package and pitch: table above [A1]. Fine-pitch BGA, LGA, QFN, QFP supported (Standard 0.35 mm, Economic 0.40 mm lead pitch) [A1].
- Recommended minimum spacing between SMD parts [A14], mm (the measurement method is only shown as a picture on the page):

| | 0201 | 0402 | 0603 | 0805 | 1206 | QFN | QFP | SOP/SOIC | SOT | BGA |
|---|---|---|---|---|---|---|---|---|---|---|
| chip 0201 / 0402 | 0.15 | 0.15 | 0.18 | 0.18 | 0.25 | 1.0 | 0.5 | 0.4 | 0.2 | 1.0 |
| chip 0603 / 0805 | | | 0.18 | 0.18 | 0.25 | 1.0 | 0.5 | 0.4 | 0.2 | 1.0 |
| chip 1206 | | | | | 0.35 | 1.0 | 0.5 | 0.4 | 0.2 | 1.0 |
| QFN | | | | | | 1.0 | 1.0 | 1.0 | 1.0 | 1.5 |
| QFP | | | | | | | 1.25 | 1.25 | 1.0 | 1.5 |
| SOP/SOIC | | | | | | | | 0.5 | 0.4 | 1.0 |
| SOT | | | | | | | | | 0.4 | 1.0 |
| BGA | | | | | | | | | | 2.0 |

- In the CPL two different designators must be more than 0.2 mm apart, else "Repeated Designator" [A11].
- Parts the machine cannot pick (rough surface, too tall, nozzle cannot hold them) are placed by hand [A4 #12].

## Edge rails, fiducials, tooling holes
- Standard: edge rails >= 5 mm wide; boards ship with rails attached unless removal is ordered (extra fee) [A16]. Fiducial = undrilled round
  copper pad, 1 mm recommended, mask opening twice the pad diameter, 3-4 along the board edges, >= 3.35 mm from the board edge including
  the keep-out [A16]. For JLC SMT JLC recommends 5 mm process edges, 2 mm tooling holes, 1 mm fiducials 3.85 mm from the panel edge [A26].
- "Panel by JLCPCB" with edge rails: fiducials and tooling holes are added on the rails, not on each board [A25 #8].
- Economic: tooling holes "are a must": 2-3 non-plated holes of 1.152 mm with 0.148 mm mask expansion in opposite corners, away from traces.
  If yours do not meet this, JLC adds them by default [A15].
- JLC's own FAQ says you do not have to add fiducials, JLC adds them [A3 #12] (see Conflicts).

## Parts library classes and how the fees work
| Class | What it is | Economic PCBA | Standard PCBA | Src |
|---|---|---|---|---|
| Basic | common parts kept loaded on the machines | no feeder fee | feeder loading $1.53 per part | A2, A3 #6, A5 |
| Preferred (shown as "Promotional") Extended | former Basic parts now loaded by hand | no feeder fee | feeder loading $1.53 per part | A3 #7, A5, A2 |
| Extended | all other library parts, loaded by hand | $3.07 per Extended part ("Extended Components Fee") | feeder loading $1.53 per part | A2 |

- Neither A2 nor A3 says in words whether the fee counts distinct parts or placements; A3 #6 explains it as the operator mounting a
  feeder for the part, which implies one fee per distinct part (inference). A3 #6 (older) gives "$3 per extended component".
- JLC's live list of Basic plus Promotional Extended parts held 1586 parts on 2026-10-14 [A5].
- Cost per board = setup + stencil + joints + feeder/extended fees + components + extras. The quote shows the exact amounts after the parts
  are selected [A3 #1].

## Fees [A2]
| Fee | Economic | Standard |
|---|---|---|
| Setup | $8.18 | $25.56 one side / $51.12 two sides |
| Panel (more than 1 design panelized) | $8.21 | $8.21 |
| Stencil (not shipped) | $1.53 | $8.21 one side / $16.42 two sides |
| Pre-reflow soldering | $0.016 per joint | $0.016 per joint |
| SMT assembly | $0.0016 per joint (1-100,000) | $0.0016 (1-50,000), $0.0013 (to 100,000), $0.0012 (to 1,000,000) per joint |
| Manual assembly | $0.0164 / $0.015 / $0.012 per joint (1-10k / 10-30k / 30-100k) | same |
| Hand-soldering labour | $3.58 per order | $3.58 per order |
| Feeder loading | $3.07 per Extended part | $1.53 per Basic or Extended part |
| Large board (> 650 cm2) | $57.46 | $57.46 |
| Packing | free | $0.50 + $0.00003 x PCB area (cm2) |
| X-ray (per component) | $1.64 (1-10), $0.82 (11-50), $0.49 (51-200), $0.33 (201-500), $0.25 (501-1000), $0.16 (1001-3000), $0.082 (more) | same |
| Handling fee | - | when both services are possible, Standard must cost >= $14.93 more; any shortfall is charged |
| Single-board assembly minimum | - | $0.48 per board (panelize to avoid) |
| Confirm Parts Placement | $0.45 | $0.45 |
| Stencil / fixture storage | - | $4.93 / $4.93 |
| Fixtures, rigid | - | $8.21 each: 2 (1-29 pcs), 3 (30-99), 5 (100-199), 10 (200-349), 15 (350-499), 20 (500+) |
| Fixtures, flex | - | $24.63 each, same quantity steps |

- Components are priced "per system" at order time; the price can differ from the last order and from LCSC; spare parts for attrition are
  included in the component cost [A2, A4 #11].
- Parts selection service (JLC engineers choose parts for you): $10, partly refundable if they cannot find parts [A23].
- Personalised services [A13]: programming after soldering (Standard only) $7.86 + $7.86/h; power-on test $15.7 + $7.86/h; adding a
  placed SMT part after ordering $47.14 for 2 positions + $1.57 each more; pin headers or RF connectors clamped on the edge $0.05 per joint;
  manual insertion (jumpers, plug-in terminals) from $0.03 per device.

## Part quantities, attrition, stock
- Most SMD parts need a minimum quantity or extra parts for attrition. Below the minimum you pay for the minimum; unused parts are discarded,
  not shipped [A4 #4]. Minimum placement quantity and loss allowance can cause a "Shortfall" although stock looks sufficient [A11].
  The actual attrition and minimum numbers per package are not published in the pages read (gap).
- Stock shown on LCSC can be 0 at JLC: two warehouses, no transfer [A4 #6]. Restock dates are not known in advance [A4 #5].
- Only parts ticked on the matching page are assembled; unmatched, shortfall and unselected lines are treated as "not required" [A10, A4 #7].

## Sourcing channels [A6, A7, A8, A9]
| Channel | What | Notes |
|---|---|---|
| JLCPCB parts | public in-stock library | default |
| Pre-order | you buy stock into your private library | usable only after it arrives |
| Global sourcing | JLC buys from global distributors | lead time 9-15 days [A6, A22]; no cancel after payment; some categories carry 3-30 % duty or a $20 inspection fee; parts not on tape: $0.017 per pin (<= 5 pins), max $0.078 per part (> 5 pins) [A8] |
| Consigned | you ship your own parts | part must have a JLC number (or be approved); customs agent about $45 (parcel < 5000 CNY) or $85 (> 5000 CNY); more than 50 part numbers in one shipment: $70 per 50 (e.g. $70 for 51, $140 for 101) [A9] |
| New part request | part not yet listed | submit a request [A6] |

- For one part, public stock can combine with pre-order stock, and global-sourcing with consigned stock; no other mix [A7]. "My Parts" is
  used first when it covers the whole need [A7].
- Parts bought at JLC are for assembly only; pickup costs 30 % of value (min $30) and ships within mainland China only [A24].

## Through-hole and mixed assembly
- Through-hole and mixed SMD + THT are offered in both Economic and Standard. SMD is reflowed, through-hole is wave-soldered; unused
  through-holes stay free of solder [A1 FAQ].
- Library parts whose assembly type is "wave soldering" are assembled manually; build time + 1 day; cost = hand-soldering labour per
  order + manual assembly per joint [A3 #2, A2].

## What JLC will not do, or does only by hand or on request
- Assemble boards made by another fab: no [A3 #14]. Ship unassembled parts with the boards: no (customs) [A4 #15, A1 FAQ].
- Components needing secondary work (hardware, cables, heat sinks) are flagged "Mechanical assembly components": set "PCBA remark" to Yes
  and describe the work [A20]. A part stacked on another (IC in a socket): both in BOM and CPL, the second coordinate > 0.2 mm away, plus
  a remark; manual cost [A1 FAQ].
- Programming: Standard orders only, case by case (MPN, programming interface, board image, HEX/BIN file) [A1 FAQ, A13].
- Polarity is taken from the silkscreen; with no silkscreen mark JLC asks by email, which delays the order [A4 #10].

## Inspection and test [A1, A2, A21, A27]
SPI (3D) after paste printing (Standard only [A1]); 2D/3D AOI after placement; visual inspection [A21]. X-ray is added and charged
automatically for hidden-joint parts (BGA, QFN, LGA) [A1 FAQ, A2]; the system may miss some parts, so name them in the remark; the report is
under Order History > Production Progress > X-Ray Report [A27]. Flying-probe test (parts down to 0201, +/-0.02 mm) and functional test
are customised services [A21].

## Stencil on assembly orders [A19]
JLC makes the stencil from its own SMT data, not straight from the paste Gerber; apertures only for SMT parts selected in the order; apertures
are optimised, not equal to pads; the stencil is not shipped (it can be stored for reorders). Battery holders: say in the remark whether the
centre pad gets paste. Precision parts may trigger a step-stencil question (fee refunded if not needed).

## Lead times [A1, A3, A12, A22]
- Assembly starts right after PCB fabrication; over 90 % of orders finish SMT within 24-48 h after the PCB is done [A12, A3 #13].
- Build time: Economic 1-3 days, Standard >= 4 days [A1]. PCBA orders get 24-hour PCB fabrication by default [A12].
- Library creation for parts without a placement footprint: usually within 48 h [A12]. SMT expedite: $47.83 per day [A12].
- A "Pending" status means JLC waits for you; the clock stops until you answer [A12].

## Conflicts between JLC sources
| Topic | One source | The other |
|---|---|---|
| Extended part fee | A2: $3.07 per Extended part (Economic) | A3 #6 (older FAQ): $3 per extended component |
| Base fees | A2: setup $8.18, stencil $1.53, $0.0016/joint, hand-solder $3.58, manual $0.0164/joint | A3 #1: $8.00, $1.50, $0.0017, $3.5, $0.0173; A22: "$8 setup + $0.0016 per solder joint" |
| Single-board minimum | A2: $0.48 per board | A17: $0.46 per board, surcharge only near 100+ pcs |
| Fiducials | A1 / A16: necessary for Standard | A3 #12: not needed, JLC adds them |
| Flex fixture | A2: $24.63 per fixture | A1 FAQ: $23.57 per fixture |
| Economic quantity | A1: 2-50 pcs (2-30 or 5-30 for some options) | A3 #10: more than 30 pcs needs a panel or Standard |
| Library size | A22: "740,000+" and "680,000+" on the same page | A3 #5: "40k+ kinds ... 698 basic ... 300k+ extended" (stale) |
| Review before payment | A4 #9: not supported for PCBA | `ordering-workflow.en.md` [O5], 2026-09-23: now available |
| Smallest package | A1 table: Standard 0201, Economic 0402 | A1 FAQ, A4 #16, A22: 01005 supported (step stencil advised when package sizes differ a lot) |
