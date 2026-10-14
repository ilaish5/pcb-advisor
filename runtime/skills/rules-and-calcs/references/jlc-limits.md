# JLC capability numbers and Altium rule catalogue

Source: JLC's capabilities page https://jlcpcb.com/capabilities/pcb-capabilities [P1] and its help pages, condensed with page ids and
dates in `<repo>/shared/reference/jlc/pcb-capabilities.en.md` (all read 2026-10-14; the P-ids below are that file's). JLC changes these
pages: re-read, and write the date next to any number you give. The tool's preset is `scripts/jlc_preset.py`. It picks its numbers
from the project's `board` block: layer count (1-2 layers use the 2-layer column, 3+ the multilayer one), copper weight
(1 or 2 oz; 2.5 / 3.5 / 4.5 oz exist on 2 layers only) and mask colour. Unknown values mean 2 layers, 1 oz, green.

Two numbers per rule, never mix them up:
- **Fab floor**: JLC's absolute minimum. A board value below it "may be rejected or altered" (verdict `below_fab_min`).
- **Preset value**: what to set in Altium. Above the floor, in whole mils, so that JLCDFM (JLC's design check) rates it Good.
  JLCDFM's limits are whole mils: Danger below r0, Warning below r1, Good below r2. 0.10 mm (3.94 mil) is Danger there although
  JLC's page accepts it, and 0.15 mm (5.9 mil) is a Warning. The tool adds the JLCDFM level to a diff row; the verdict stays the fab floor.

## Preset values and fab floors (read 2026-10-14)
| Altium rule (scope) | Preset 1-2 layer, 1 oz | Fab floor 1-2 layer, 1 oz | Multilayer 1 oz: preset / floor | 2 oz: preset / floor |
|---|---|---|---|---|
| Clearance | 6 mil | 0.10 mm (4 mil) [P1] | 6 mil / 0.09 mm (3.5 mil) | 8 mil / 0.16 mm [P3] |
| Width min / pref / max | 5 / 8 / 40 mil | 0.10 mm [P1] | same / 0.09 mm | 8 / 10 / 40 mil / 0.16 mm |
| RoutingVias hole / dia | 12 / 24 mil | 0.15 / 0.25 mm, dia >= hole + 0.1 [P1] | same | same |
| MinimumAnnularRing_PTH (IsPad) | 10 mil | 0.18 mm, 0.25 recommended [P1] | 8 mil / 0.15 mm, 0.20 recommended | 10 mil / 0.254 mm |
| MinimumAnnularRing_Via (IsVia) | 6 mil | 0.05 mm = (0.25 - 0.15) / 2 | same | same |
| HoleSize min / max | 12 mil / 6.3 mm | 0.15 mm / 6.3 mm [P1] | same | same |
| SilkToSolderMaskClearance | 6 mil | 0.15 mm pad to silk [P1] | same | same |
| SolderMaskExpansion | 2 mil | none; 1:1 accepted, 0.1 mm recommended [P1, P7] | same | same |
| MinimumSolderMaskSliver | 6 mil | 0.10 mm (green, red, yellow, blue, purple), 0.13 mm (black, white) [P1] | same | 8 mil / 0.20 mm |
| BoardOutlineClearance | 12 mil | 0.2 mm routed, 0.4 mm V-cut (use 16 mil) [P1] | same | same |
| HoleToHoleClearance_PTH (IsPad, IsPad) | 18 mil | 0.45 mm pad to pad [P1] | same | same |
| HoleToHoleClearance (All) | 8 mil | 0.2 mm via to via [P1] | same | same |
| ViasUnderSMD | not allowed | filled and plated-over vias only, extra cost under 6 layers [P1, P5] | same | same |
1-layer boards: smallest drill and via 0.3 mm. Heavy copper (2.5 / 3.5 / 4.5 oz, 2 layers): track/space floor 0.20 / 0.25 / 0.30 mm.
Via rings follow the via diameter rule, not the PTH ring: a via at JLC's minimum has a 0.05 mm ring, so one ring rule for both is wrong.
Other numbers (earlier table, not re-read): NPTH minimum hole 0.5 mm, silk line >= 0.15 mm, text height 1.0 mm, board thickness
0.4-2.0 mm (1.6 standard), impedance on published stacks (https://jlcpcb.com/impedance).

## JLCDFM check -> Altium rule (JLCDFM limits in mil: Danger / Warning / Good)
| JLCDFM check | Altium rule | Note |
|---|---|---|
| Trace width 4 / 5 / 8 | Width | preset min 5 mil |
| Trace spacing 4 / 6 / 8, Pad spacing 4 / 6 / 8 | Clearance | preset 6 mil |
| Annular ring 4 / 6 / 8 | MinimumAnnularRing (IsPad, IsVia) | pad 10 or 8 mil, via 6 mil |
| Trace to edge 6 / 8 / 10, Pad to edge 5 / 8 / 16 | BoardOutlineClearance | preset 12 mil; 0.2 mm is still a Warning |
| Soldermask bridge 4 / 6 / 8 | MinimumSolderMaskSliver | preset 6 mil; 0.10 mm is Danger |
| Plated through-hole spacing 7 / 8 / 10 | HoleToHoleClearance | JLCDFM does not catch a pad gap below 0.45 mm |
| Silkscreen to pad / hole 5 / 7 / 10 | SilkToSolderMaskClearance | JLCDFM adds mask expansion: 6 + 2 mil |
| Negative mask expansion, via within pad | SolderMaskExpansion, ViasUnderSMD | flags only |
| Mask opening exposing trace 3 / 6 / 8 | none; SolderMaskExpansion plus Clearance | keep >= 0.09 mm [P7] |
| Silkscreen line width 4 / 6 / 8 | none: Altium has no rule | manual: stroke width in the text properties, >= 6 mil |
| Component to component 8 / 12 / 16, to edge 20 / 32 / 40 | ComponentClearance exists | JLC spacing is per package pair; no single value, read JLCDFM |
| Slot width 24 / 32 / 40, via to PTH 40 / 44 / 48, PTH to trace 7 / 9 / 12 | none | manual, read JLCDFM |
| Sharp trace corner, short slot, missing PTH, BGA pad, fiducial | AcuteAngle exists, JLC gives no limit | manual |

## Rule catalogue (Altium kind -> purpose -> typical value to start from)
| Kind | Purpose | Typical start |
|---|---|---|
| Clearance | spacing per scope pair | the preset above; larger for high voltage, noisy-to-sensitive (about 1 mm) |
| Width | min / preferred / max track | the preset; power by current; RF/impedance from calculation |
| RoutingVias | via diameter / hole | inside fab capability; larger for power vias |
| HoleSize | drill range | fab range |
| HoleToHoleClearance | drill spacing | at or above the fab figure, one rule for pads and one for the rest |
| MinimumAnnularRing | ring | one rule for pads (IsPad) and one for vias (IsVia) |
| SolderMaskExpansion / MinimumSolderMaskSliver | mask opening / bridge | the preset (2 mil / 6 mil) |
| SilkToSolderMaskClearance / SilkToSilkClearance | silk hygiene | 0.15 mm |
| BoardOutlineClearance | copper to edge | the preset |
| ParallelSegment | crosstalk: max parallel run at a gap | sensitive nets 0.5 mm gap / 3 mm run; 3W for clocks |
| RoutingLayers | which layers a net may use | keep the reference plane free of tracks |
| ViasUnderSMD | via in pad | not allowed (filled via-in-pad costs extra) |
| AcuteAngle | acid traps | >= 90 degrees |
| PolygonConnect | pour connection | vias direct, pads thermal relief |
| ComponentClearance | part spacing | about 0.25 mm; assembly may need more |
Altium design rule types and "what values": `unit3-pcb-layout.en.md` [25]-[26]. Net classes and queries: `m19` 19.4-19.5.

## Typical 4-layer 1.6 mm stack (JLC published; verify on the impedance page)
Outer copper 35 um, inner 15.2 um. Prepreg L1-L2 about 0.21 mm (Er 4.4) or 0.10 mm (Er 4.1) depending on the stack code.
A thinner prepreg gives narrower 50 ohm lines (easier on fine-pitch pads). Use the code the student will order and its numbers.

## .RUL file facts (verified on AD26 and read on AD20 projects)
- Plain text, latin-1, one rule per line, each line a `|KEY=VALUE|...` record exactly as stored in the PcbDoc, line ends with
  the pilcrow character (0xB6) then CRLF. Altium's export skips the default SilkToBoardRegionClearance rule.
- Import (AD26): Design > Rules, right-click "Default Rule Set" > Import Rules... > "Select Design Rules" > Import > "Rule Set Already Exists": "Merge with existing rules" (duplicate names become `Name_1` at priority 2) or "Replace existing rules" (removes the board's rules). Values in mil are kept; the leading `|` and trailing `|¶` are accepted.
- Annular ring key is `MINIMUMRING` (not `MINIMUM`). Other keys: BoardOutlineClearance `GAP` and `GENERICCLEARANCE`
  (with `NETSCOPE=DifferentNets`), MinimumSolderMaskSliver `MINSOLDERMASKWIDTH`, HoleToHoleClearance `GAP`, ViasUnderSMD `ALLOWED=FALSE`.
- Scope strings as Altium writes them: `All`, `IsPad`, `IsVia`; a hole-to-hole rule has two (`IsPad` and `IsPad`). The ring and
  hole-to-hole rules with these scopes are generated from the device board's own export; the first Altium import of the generated file is
  still to be confirmed, so check the imported rules in the Rules editor.
- A scoped rule must have a lower PRIORITY number than the scope-All rule of its kind, or the All rule wins. The board-aware file
  inserts it just above the All rule and shifts the others; after a Merge import raise it by hand in Priorities.
- Keys that matter: `RULEKIND`, `NAME`, `SCOPE1EXPRESSION` (for example `InNet('NAME')`), `MINLIMIT`/`MAXLIMIT`/`PREFEREDWIDTH`,
  `PRIORITY`, `UNIQUEID` (8 chars, must be unique). Proof script: `<repo>/docs/feasibility/feas_rul.py`.

## Calculators
- Width for current: IPC-2221 (`trace_width.py`): A = (I / (k x dT^0.44))^(1/0.725) in mil^2, k = 0.048 outer, 0.024 inner.
  IPC-2152 is the newer standard and usually allows narrower traces with a plane nearby; say which one you used.
- Microstrip / CPWG / differential impedance: needs dielectric height, Er, trace thickness. Course: unit4 [17]-[19].
  Always confirm in the fab's calculator: https://jlcpcb.com/impedance.
- Divider: Vout = Vref x (1 + R1/R2); pick E24/E96 values, compute the real Vout and its error; keep the divider current well
  above the feedback-pin bias current from the datasheet.
