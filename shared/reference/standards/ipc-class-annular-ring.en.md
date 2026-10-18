# IPC-6012 / IPC-A-600 annular ring, Class 2 and Class 3 (summary)

> Source: public summaries (listed below), read 2026-10-18; our own words, the standard is copyrighted and not copied. The sources disagree on Class 2, so the conservative reading is used. Confirm against the current IPC-6012 revision (F or later) before a contract requirement.

Covers: the smallest annular ring (copper left around a plated hole) after fabrication, by performance class. Used by the Rules tab, Standard section (data: `shared/reference/standards/ipc.json`).

## Sources
| ID | Page | URL | Read |
|---|---|---|---|
| R1 | PCB Annular Ring, IPC standards (AtlasPCB) | https://www.atlaspcb.com/blog/pcb-annular-ring-ipc-standards/ | 2026-10-18 |
| R2 | Plated Thru Hole Annular Ring Class 2, 3 and "Class 3 Light" (Summit Interconnect) | https://summitinterconnect.com/blog/article/differences-between-annular-ring-classes/ | 2026-10-18 |
| R3 | IPC Class 2 vs Class 3 design rule impacts (Weller PCB) | https://wellerpcb.com/high-quality-printed-circuit-boards-manufacturing-ipc-class-2-and-3 | 2026-10-18 |
| R4 | Annular Rings in PCB Design (JLCPCB blog) | https://jlcpcb.com/blog/annular-rings-pcb-design | 2026-10-18 |
| R5 | PCBSync, PCB drill tolerance / annular ring pages | https://pcbsync.com/pcb-hole-tolerance/ | 2026-10-18 |

## Values used (mm)
| Class | External layers | Internal layers | Breakout (hole touching the edge of the pad) |
|---|---|---|---|
| Class 2 | 0.05 (R1, R4) | 0.05 (R1; conservative) | up to 90 degrees allowed with a teardrop or fillet (R2, R3, R5) |
| Class 3 | 0.05 (R1, R2, R5) | 0.025 (R2, R5) | none allowed (R1, R2) |

## Notes
- Class 2 is the disputed row: R2, R3 and R5 describe it by a breakout allowance rather than a fixed ring, R1 and R4 give 0.05 mm. The tool uses 0.05 mm, the stricter reading.
- Altium's annular ring rule has one value for all layers, so the tool writes the larger of the external and internal values (0.05 mm for both classes). The practical difference of Class 3 is that breakout is not allowed: do not rely on teardrops to rescue a small ring.
- These are fabricated minimums after drill and plating tolerance; designers add margin (R2 suggests about 0.15 mm / 6 mil as a Class 3 design target, single source, not used by the tool).
- A fab's own minimum (JLC: see `jlc/pcb-capabilities.en.md`) is almost always larger than these values and then decides.
