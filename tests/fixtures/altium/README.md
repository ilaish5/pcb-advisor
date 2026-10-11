# Altium parser fixtures

Real Altium Designer files for testing the read-only SchDoc / PcbDoc reader. They are AD20-era files from the *AD20 Essentials* exercises of course 27525 (demo design "WCTopping": CAN, relay I/O, digital I/O, processor interface and power supply). All of them already parse. They are fixtures: never open and save them in Altium. Developer use only; not reference material for the advisor.

| File | Source (AD20 exercise module) | What it exercises |
|---|---|---|
| `rules-board.PcbDoc` | Module 19, `Rules.PcbDoc` | board with parts, 2 layers, the default rule set (35 rules): rule reading |
| `finished-board.PcbDoc` | Module 25, `WCTopping.PcbDoc` | finished board: parts, pads with nets, tracks, vias, polygon pours, 45 rules |
| `project/WCTopping.PrjPcb` | Module 7 | project file listing the 5 sheets (text INI format) |
| `project/CAN_Interface.SchDoc` | Module 7 | schematic: 17 parts, wires, net labels, ports |
| `project/Digital_IO.SchDoc` | Module 7 | schematic: 12 parts, 34 wires, 30 net labels |
| `project/Power Supply.SchDoc` | Module 7 | schematic: 15 parts, few wires, no labels |
| `project/Processor_Interface.SchDoc` | Module 7 | schematic: 3 large parts, 40 wires, 27 net labels, 13 ports |
| `project/Relay_IO.SchDoc` | Module 7 | schematic: 13 parts (relays, connectors) |
| `outjob.OutJob` | Module 22, `WCtopping.OutJob` | OutJob file (text) |
| `parts.PcbLib` | Module 29, `WCTopping.PcbLib` | footprint library |
| `parts.SchLib` | Module 29, `WCTopping.SchLib` | schematic symbol library |
| `parts.IntLib` | Module 11, `WCT.IntLib` | compiled integrated library (SchLib + PcbLib + cross reference) |

The files under `project/` keep their original names because the PrjPcb refers to them by name. The other files were renamed. Part and wire counts above come from a rough scan and are indicative only.
The full exercise set (155 files, incl. a 4-layer board with planes, empty boards, a multi-sheet project with harnesses, a real Gerber/drill output set) is not in the repo; it can be recovered from the original course zip `חומרי_עזר_מעגלים_מודפסים.zip`.
