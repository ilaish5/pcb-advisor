# IPC-7351B courtyard excess by density level (summary)

> Source: public summaries listed below, read 2026-11-27. Summary in our own words. The standard itself is copyrighted and is not copied. Check the purchased IPC-7351B before a compliance decision.

Covers: how much extra space the placement courtyard adds around a part, for the three density levels. The tool uses Level B (owner decision 2026-11-27, `docs/e2e-2026-11-27/ACCEPTANCE.md` OD-3).

## Sources
| ID | Page | URL | Read |
|---|---|---|---|
| C1 | Atlas PCB, land pattern design per IPC-7351B | https://www.atlaspcb.com/blog/pcb-land-pattern-design-ipc-7351b-footprint-standards/ | 2026-11-27 |
| C2 | PCBSync, IPC-7351 land pattern | https://pcbsync.com/ipc-7351-land-pattern/ | 2026-11-27 |
| C3 | PCB Libraries forum, "Placement Courtyard Excess" | https://www.pcblibraries.com/forum/placement-courtyard-excess_topic3372.html | 2026-11-27 |
| C4 | PCB Libraries forum, "How is a courtyard excess defined?" | https://www.pcblibraries.com/forum/how-is-a-courtyard-excess-defined_topic3060.html | 2026-11-27 |
| C5 | RF Essentials glossary, "Courtyard" | https://rfessentials.com/resources/rf-glossary/courtyard/ | 2026-11-27 |

## Excess per side, mm
All five sources agree on these numbers (C3 and C4 name the levels Least / Nominal / Most, without the letters).

| Level | Name | Excess |
|---|---|---|
| A | Most (max protrusion) | 0.50 |
| B | Nominal | 0.25 |
| C | Least | 0.10 |

## How the courtyard is formed
- Start from the largest body extent plus how far the leads or lands stick out (C1, C5).
- Add the excess for the chosen level on each side, giving a closed outline (C1, C5).
- C1 rounds the outline outward to a 0.05 mm grid; C5 says it is conventionally drawn on a 0.05 mm grid. C2 only says pads snap to 0.05 mm.
- Tools may use separate settings for body and for pads; IPC-7352 has separate pad-edge and body clearances (C3, C4).

## Gaps and disagreements
- PCB Libraries' own tool defaults are 0.10 / 0.20 / 0.40 mm, not 0.10 / 0.25 / 0.50 (C3, C4). These are vendor defaults, not the standard.
- C2 says chips smaller than 1608 use 0.15 mm per side and a finer grid. C1 and C5 do not mention this; not cross-checked.
- C5's use cases (Level A for connectors and hand soldering, Level C for dense or RF boards) are one source's advice.
- The 0.05 mm grid rule rests on two sources only (C1, C5).
