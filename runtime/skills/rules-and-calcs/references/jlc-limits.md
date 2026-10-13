# JLC capability numbers and Altium rule catalogue

Capability source: https://jlcpcb.com/capabilities/pcb-capabilities (standard multilayer, checked 2026-10-09 by a previous
project). Re-check the page and write today's date next to any number you give; limits change.
2-layer figures are NOT in this file: for a 2-layer board open the page, read the 1-2 layer column, quote it with the date.
The fab limits are minimums; design above them.

| Item | JLC (multilayer, 4+ layers) |
|---|---|
| Min trace / space | 0.09 / 0.09 mm |
| Min via drill / pad | 0.15 / 0.25 mm |
| Annular ring (PTH) | 0.20 mm (0.15 absolute) |
| Hole to hole | via 0.2 mm, pad 0.45 mm |
| Pad to track | 0.1 mm |
| Copper to board edge | 0.3 mm recommended (routed outline) |
| NPTH min hole | 0.5 mm |
| Mask bridge (green) | 0.10 mm |
| Silk line / text height | 0.15 / 1.0 mm |
| Board thickness | 0.4-2.0 mm (1.6 standard) |
| Impedance control | yes, on published stacks (https://jlcpcb.com/impedance) |

A common margin set that has gone through JLC unchanged: trace/space 0.15 mm, via 0.6 pad / 0.3 drill (minimum 0.5 / 0.2),
hole-to-hole 0.254 mm for vias, edge 0.3 mm, mask expansion 0.05 mm, mask sliver 0.1 mm, silk 0.15 mm / 1.0 mm text.
It is a starting point for the student's board, not a rule.

## Typical 4-layer 1.6 mm stack (JLC published; verify on the impedance page)
Outer copper 35 um, inner 15.2 um. Prepreg L1-L2 about 0.21 mm (Er 4.4) or 0.10 mm (Er 4.1) depending on the stack code.
A thinner prepreg gives narrower 50 ohm lines (easier on fine-pitch pads). Use the code the student will order and its numbers.

## Rule catalogue (Altium kind -> purpose -> typical value to start from)
| Kind | Purpose | Typical start |
|---|---|---|
| Clearance | spacing per scope pair | board default above fab min; larger for high voltage, noisy-to-sensitive (about 1 mm) |
| Width | min / preferred / max track | default 0.15-0.2 / 0.2-0.25; power by current; RF/impedance from calculation |
| RoutingVias | via diameter / hole | inside fab capability; larger for power vias |
| HoleSize | drill range | fab range |
| HoleToHoleClearance | drill spacing | at or above the fab figure |
| MinimumAnnularRing | ring | at or above the fab figure |
| SolderMaskExpansion / MinimumSolderMaskSliver | mask opening / bridge | 0.05 mm / 0.1 mm |
| SilkToSolderMaskClearance / SilkToSilkClearance | silk hygiene | 0.15 mm |
| BoardOutlineClearance | copper to edge | fab figure |
| ParallelSegment | crosstalk: max parallel run at a gap | sensitive nets 0.5 mm gap / 3 mm run; 3W for clocks |
| RoutingLayers | which layers a net may use | keep the reference plane free of tracks |
| ViasUnderSMD | via in pad | not allowed (filled via-in-pad costs extra) |
| AcuteAngle | acid traps | >= 90 degrees |
| PolygonConnect | pour connection | vias direct, pads thermal relief |
| ComponentClearance | part spacing | about 0.25 mm; assembly may need more |
Altium design rule types and "what values": `unit3-pcb-layout.en.md` [25]-[26]. Net classes and queries: `m19` 19.4-19.5.

## .RUL file facts (verified on AD26 and read on AD20 projects)
- Plain text, latin-1, one rule per line, each line a `|KEY=VALUE|...` record exactly as stored in the PcbDoc, line ends with
  the pilcrow character (0xB6) then CRLF. Altium's export skips the default SilkToBoardRegionClearance rule.
- Import (AD26): Design > Rules, right-click "Default Rule Set" > Import Rules... > "Select Design Rules" > Import > "Rule Set Already Exists": "Merge with existing rules" (duplicate names become `Name_1` at priority 2) or "Replace existing rules" (removes the board's rules). Values in mil are kept; the leading `|` and trailing `|¶` are accepted.
- Annular ring key is `MINIMUMRING` (not `MINIMUM`).
- Keys that matter: `RULEKIND`, `NAME`, `SCOPE1EXPRESSION` (for example `InNet('NAME')`), `MINLIMIT`/`MAXLIMIT`/`PREFEREDWIDTH`,
  `PRIORITY`, `UNIQUEID` (8 chars, must be unique). Proof script: `<repo>/docs/feasibility/feas_rul.py`.

## Calculators
- Width for current: IPC-2221 (`trace_width.py`): A = (I / (k x dT^0.44))^(1/0.725) in mil^2, k = 0.048 outer, 0.024 inner.
  IPC-2152 is the newer standard and usually allows narrower traces with a plane nearby; say which one you used.
- Microstrip / CPWG / differential impedance: needs dielectric height, Er, trace thickness. Course: unit4 [17]-[19].
  Always confirm in the fab's calculator: https://jlcpcb.com/impedance.
- Divider: Vout = Vref x (1 + R1/R2); pick E24/E96 values, compute the real Vout and its error; keep the divider current well
  above the feedback-pin bias current from the datasheet.
