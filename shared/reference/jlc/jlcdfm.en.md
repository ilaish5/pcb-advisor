# JLCDFM: JLC's free online DFM checker, and how it relates to the order review

> Source: the JLCDFM home page and JLC's "DFM Tool Help" and "DFM FAQs" articles, the PCBA viewer page and related help pages in the table below, all read 2026-10-14; one JLC blog post marked as such. JLC publishes no list of the individual checks or their Danger and Warning thresholds (see Gaps). The report PDF layout and the triage of its findings are in the skill references, not repeated here.

Covers: what JLCDFM is and accepts, its screens, how to read a result (levels, values, object names, the 50-result cap), the parse and
false-report causes JLC documents, what it cannot know, and how it relates to the review JLC does after an order. For the report PDF
layout and per-finding triage use `runtime/skills/manufacturer-and-dfm/references/jlcdfm-report.md` and `jlcdfm-smt.md`.

## Sources
All read 2026-10-14. "Page date" is the "Last updated" stamp on the page.

| ID | Page | URL | Page date |
|---|---|---|---|
| D1 | Free Online PCB DFM Tool, JLCDFM (home) | https://jlcdfm.com/ | none shown |
| D2 | DFM Main Interface Help: PCB | https://jlcpcb.com/help/article/DFM-Main-Interface-Help:-PCB | 2025-04-24 |
| D3 | DFM Analysis Result View Help | https://jlcpcb.com/help/article/DFM-Analysis-Result-View-Help | 2024-08-09 |
| D4 | DFM Drill Layer Format Adjustment | https://jlcpcb.com/help/article/dfm-drill-layer-format-adjustment | 2025-04-24 |
| D5 | Why Are Drill Holes Not Aligned with the Copper Layer? | https://jlcpcb.com/help/article/why-are-drill-holes-not-aligned-with-the-copper-layer | 2024-06-24 |
| D6 | Misidentified Layers - Why Not Follow Gerber X2 Standards | https://jlcpcb.com/help/article/misidentified-layers-why-not-follow-gerber-x2-standards | 2024-08-09 |
| D7 | Why Are Components Inside the Board Reported as Intersecting with the Outline? | https://jlcpcb.com/help/article/Why-Are-Components-Inside-the-Board-Reported-as-Intersecting-with-the-Outline | 2024-06-24 |
| D8 | JLCPCB PCBA Viewer (order-time placement and DFM view) | https://jlcpcb.com/smt/dfm-result | none shown |
| D9 | SMT Service Lead Time Overview | https://jlcpcb.com/help/article/smt-service-lead-time-overview | 2026-09-09 |
| D10 | PCB Assembly FAQ (Part 2) | https://jlcpcb.com/help/article/pcb-assembly-faqs-part-2 | 2026-09-09 |
| D11 | SMT Reorder Process Overview | https://jlcpcb.com/help/article/smt-reorder-process-overview | 2026-09-09 |
| D12 | JLC blog: Design Rule Check Prevents Costly PCB Production Mistakes (blog, not product documentation) | https://jlcpcb.com/blog/design-rule-check | published 2026-03-26 |
| D13 | Help catalogues "DFM Tool Help" and "DFM FAQs" (the full list of JLC's DFM articles: D2-D7) | https://jlcpcb.com/help/catalog/2061-dfm-tool-help , https://jlcpcb.com/help/catalog/2071-dfm-faqs | listing |

Address: the tool is at https://jlcdfm.com (https://dfm.jlcpcb.com redirects there). The host name dfm.jlcdfm.com did not resolve on
2026-10-14 (DNS: non-existent domain).
Checked live, 2026-10-14: the report PDF the app exports still prints "https://dfm.jlcdfm.com/" in its header; use jlcdfm.com.

## What it is and what it accepts [D1]
- Free, web-based; upload a Gerber archive, "zip/rar format, max 50MB".
  Verified by upload, 2026-10-14: free but not anonymous. Without a login the upload (`pcbDfm/uploadGerber`) fails with HTTP 500 and
  the app sends the browser to the passport.jlcpcb.com login, so a JLCPCB account is needed. "View Example" (a demo board) and its
  PDF export work without an account (`docs/bench-runs/jlc-live-2026-10-14/`).
- "5 comprehensive analysis modules covering traces, solder masks, drilling, silkscreen, and component assembly" and "a 30+ point
  checklist", each finding located on the board; one-click PDF report.
- Rules: "Use ready-to-go DFM rules or incorporate DFM rules provided by your preferred supplier".
- Assembly side: BOM matching against JLC's parts library and JLC's own 3D component models; 2D and 3D views.
- The report sections seen in real reports (Routing, Soldermask, Silkscreen, Drill layer analysis; SMT Component assembly analysis) are
  described in the repo's `jlcdfm-report.md`.

## The screen [D2]
- Graphic area: wheel zooms, right-drag pans, left-drag rotates in 3D. View modes: Gerber, Wireframe, 2D Simulation, 3D Simulation.
- Unit toggle imperial/metric; live mouse coordinates; the original file name.
- "DFM Check" runs the one-click analysis. Tab "Overview": basic board data, "useful for evaluating prototyping costs". Tab "All": every
  analysis item with Statistics (counts by level) and a "Detail" button coloured by the worst level present (green = no Danger/Warning).
- Layer panel: eye icons per layer; hover shows the original Gerber file name; unrecognised layers go to a miscellaneous group.
- PCB mode is view-only; in SMT mode components can be edited.

## Reading a result [D3]
- Title "[module] > [item]" (e.g. "Routing Layer Analysis > Trace Spacing"), a short and a long description (the production risk), a
  diagram, and "alert level guidance rules" (Section H) that map values to levels.
- Levels: Danger (red), Warning (orange), Good (green). A layer label like "Top Layer (50, 0, 0)" means Danger 50, Warning 0, Good 0.
- Value column: usually a length between two objects; some items are unitless (percentages); some have no value (a dangling trace end is
  always Warning or Danger).
- Object 1 / Object 2 are the two measured objects, named by the DFM engine's primitives: `r3.93701` = round, 3.93701 mil diameter (for a
  trace, its width); `rect20x30`, `oval20x50`; component checks show designators; a one-object check shows `null` for the other.
- Only the 50 lowest-level (worst) results per item are kept, to avoid "audit fatigue". So a list of 50 can hide more cases.
  Checked live, 2026-10-14 (demo result file): at most 50 results per check and layer are stored, with the original count beside them
  (e.g. 1555 annular-ring results cut to 50).
- "Smart Display" hides unrelated layers when jumping to a result; "Auto Fit View" zooms to it.

## Parse problems and false reports JLC documents
| Symptom | Cause | Fix | Src |
|---|---|---|---|
| Drill holes shrunk into a corner or spread beyond the board | drill format guessed wrong (Excellon files often omit units, zero mode, digits; the guess is right "in 99% of cases") | in PCB DFM mode, Drill Format: set absolute/relative, leading/trailing zero, digits (e.g. 3:5), metric/imperial, "Apply to All Layers", Confirm | D4 |
| Drills not aligned to pads | NPTH-only board, or pads drawn from line segments so no pad centre can be found | flash pads as single round/rectangular objects (about 80 % of pads is enough) | D5 |
| Several files all shown as copper although names are right | Gerber X2 attributes override file names (also X2 attributes inside G04 comments) | output correct X2 attributes, or plain RS-274X | D6 |
| Components inside the board "intersect the outline" | the wrong layer was taken as outline (e.g. GM13 holding drawings instead of GKO) | one clean outline layer; nothing else on it | D7 |

## What it cannot know
- JLC's pages do not list the 30+ checks, their thresholds, or whether the thresholds follow the capability page (gap).
- General knowledge, not a JLC statement: RS-274X Gerbers carry no netlist, so a Gerber-only check cannot tell same-net from different-net
  copper; the repo's triage treats same-net spacing findings accordingly (`jlcdfm-report.md`, `runtime/skills/manufacturer-and-dfm`).
- A JLC blog post (not product documentation) says JLCDFM finds acid traps, copper slivers, mask dam widths and drill-to-edge distances
  that a CAD DRC does not [D12].
- Polarity is judged from the silkscreen; "+" marks a diode's or polarised capacitor's anode, "-" the cathode; the red dot marks an IC's
  orientation [D10 #8, #10].

## Relation to the review after ordering
- JLC recommends JLCDFM as a self-check before uploading [D9]. It is not the order review: after ordering, JLC's engineers review the PCB
  design and advanced options, build the engineering data and send questions; "the final responsibility for design details and functional
  implementation remains with the customer" [D9]. For bare boards "Confirm Production File" lets you check JLC's processed Gerbers
  (`ordering-workflow.en.md`).
- For assembly the order flow has its own viewer [D8]: placements as adjusted by JLC's engineers ("Show Revised Items") and "DFM
  Results" (All / Correct / Warning / Polarized part / No data) with the note "This result is automatically detected by the system and may
  not be accurate. If you confirm it is correct, the DFM warning can be ignored."
- DFM data is regenerated for every reorder and has to be confirmed again; orientation can differ from the first order [D11].

## Gaps
- The individual checks of each module and their Danger/Warning thresholds (not published in the pages read).
  Checked live, 2026-10-14 (no upload: the web app serves its built-in rules at `pcbDfm/getDfmConfigFile`): each check has a range
  [r0, r1, r2] in mil; below r0 Danger, below r1 Warning, below r2 Good, above r2 not listed (the demo's statistics reproduce this).
  Trace width 4/5/8, trace spacing 4/6/8, trace to board edge 6/8/10, pad spacing 4/6/8, pad to board edge 5/8/16, PTH to trace
  7/9/12, annular ring 4/6/8, soldermask bridge 4/6/8, mask opening to trace 3/6/8, silkscreen to pad and to hole 5/7/10, silkscreen
  line width 4/6/8, PTH spacing 7/8/10, slot width 24/32/40, via to PTH 40/44/48; assembly: component spacing 8/12/16, component to
  board edge 20/32/40 (the demo result adds via to pad 4/6/8). The bounds are whole mils, so a
  value at JLC's own mm minimum lands below them: 0.10 mm track, space or mask dam (3.94 mil) is Danger; 0.15 mm silk width, silk to
  pad or ring (5.9 mil) is Warning; 0.20 mm copper to edge (7.9 mil) is Warning. Full list: `docs/bench-runs/jlc-live-2026-10-14/jlcdfm_rules.json`.
- An "SMT" counterpart of the "DFM Main Interface Help: PCB" page (none in the DFM Tool Help catalogue on 2026-10-14) [D13].
