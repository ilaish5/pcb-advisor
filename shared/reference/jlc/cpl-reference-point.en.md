# JLCPCB CPL: which point is "Mid X / Mid Y"

> Source: JLCPCB help and blog pages plus Altium documentation, read 2026-11-27. Summary in our own words. Complements `jlc/files-and-formats.en.md` § CPL, with no contradiction.

## Sources
| ID | Page | URL | Read |
|---|---|---|---|
| J1 | JLC, Pick & Place File for PCB Assembly | https://jlcpcb.com/help/article/pick-place-file-for-pcb-assembly | 2026-11-27 |
| J2 | JLC blog, Files Needed for PCB Assembly | https://jlcpcb.com/blog/files-needed-for-pcb-assembly | 2026-11-27 |
| J3 | JLC, How to generate BOM and Centroid File from Altium | https://jlcpcb.com/help/article/how-to-generate-bill-of-materials-and-centroid-file-from-altium | 2026-11-27 |
| J4 | JLC, PCB Assembly FAQs (Part 2) | https://jlcpcb.com/help/article/pcb-assembly-faqs-part-2 | 2026-11-27 |
| J5 | JLC SMT Assembly Components orientation fix (GitHub) | https://www.github.com/JLCPCB/JLCPCB-SMT-Assembly-Components-orientation-fix | 2026-11-27 |
| AL1 | Altium KB, Calculate component Pick and Place Center of a footprint | https://www.altium.com/documentation/knowledge-base/altium-designer/calculate-component-pick-and-place-center-of-a-footprint | 2026-11-27 |
| AL2 | Altium docs, Preparing Assembly Data | https://www.altium.com/documentation/altium-designer/preparing-for-manufacture/output-jobs/assembly-data | 2026-11-27 |

## What JLC says Mid X / Mid Y is
- The X/Y of the component centroid, in mm (J1).
- The geometric centre of the component, not pin 1; pin 1 is a common mistake, especially with custom footprints (J2).
- CPL and Gerbers must share one origin (for example the board's bottom-left corner), or every part lands in the wrong place (J2).
- The Altium article (J3) gives no point choice (Center vs Ref), no offset and no tolerance.
- No JLC page defines "geometric centre" (body, pad bounding box or 3D model), and none gives a numeric tolerance.

## What Altium writes
- Center-X/Y: the midpoint between the two outermost pad locations, from pad data only (AL1, AL2).
- Ref-X/Y: the footprint's reference point, its origin (AL2).
- Altium warns that Center-X/Y can be off the true centroid for asymmetric footprints such as edge connectors, and that a footprint without pads has no centre; for those it suggests Ref-X/Y (AL1).

## Placement preview and corrections
- JLC's Gerber Viewer has a component placement tool to check and fix rotation (J2); position correction is not described there.
- JLC engineers review files and fix rotation and polarity from the silkscreen; if silkscreen and CPL disagree, JLC follows the silkscreen (J4).
- J5 shows a user editing Mid X by hand to fix a small offset seen in the viewer, and says JLC engineers fix data problems if the customer does not.
- JLC states no position tolerance on any page found.

## Gaps
- The exact JLC meaning of "geometric centre" (pad box or body) is not stated anywhere. The pad bounding-box centre is our reading, not a JLC statement.
- The flag tolerance the tool uses (0.25 mm, `docs/e2e-2026-11-27/ACCEPTANCE.md` OD-5) is an engineering choice with no JLC source.
