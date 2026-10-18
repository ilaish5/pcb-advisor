# IPC-2221B electrical conductor spacing by voltage (Table 6-1, summary)

> Source: public summaries of the table (listed below), read 2026-10-18. The table is a summary in our own words; the standard itself is copyrighted and is not copied. Check the purchased IPC-2221B before a safety or compliance decision.

Covers: the minimum spacing between two conductors for a given voltage between them (DC or AC peak), for three board locations. Used by the Rules tab, Standard section (data: `shared/reference/standards/ipc.json`).

## Sources
| ID | Page | URL | Read |
|---|---|---|---|
| S1 | IPC-2221 Clearance and Spacing by Voltage (indipcb) | https://indipcb.com/blog/ipc-2221-clearance-spacing | 2026-10-18 |
| S2 | PCB Creepage and Clearance, IPC-2221 (PCBSync) | https://pcbsync.com/pcb-creepage-clearance/ | 2026-10-18 |
| S3 | PCB Line Spacing for High Voltage (SF Circuits) | https://www.sfcircuits.com/pcb-school/pcb-line-spacing-clearance-creepage | 2026-10-18 |
| S4 | PCB Conductor Spacing Calculator (trafolo) | https://trafolo.eu/calculators/pcb-conductor-spacing/ | 2026-10-18 |

## Spacing in mm (S1, S2, S3 agree on every value below)
| Peak voltage between conductors | B1 internal | B2 external, uncoated | B4 external, permanent coating |
|---|---|---|---|
| 0 - 15 V | 0.05 | 0.10 | 0.05 |
| 16 - 30 V | 0.05 | 0.10 | 0.05 |
| 31 - 50 V | 0.10 | 0.60 | 0.13 |
| 51 - 100 V | 0.10 | 0.60 | 0.13 |
| 101 - 150 V | 0.20 | 0.60 | 0.40 |
| 151 - 170 V | 0.20 | 1.25 | 0.40 |
| 171 - 250 V | 0.20 | 1.25 | 0.40 |
| 251 - 300 V | 0.20 | 1.25 | 0.40 |
| 301 - 500 V | 0.25 | 2.50 | 0.80 |

Above 500 V: take the 301-500 V value and add a rate per volt over 500: B1 0.0025 mm/V, B2 0.005 mm/V, B4 0.00305 mm/V (S1, S4; S2 prints B1 as 0.005 but its own worked example uses 0.0025, so 0.0025 is used). Example, B2 at 1000 V: 2.5 + 0.005 x 500 = 5.0 mm. The tool stops at 1500 V.

## Column meaning
- B1: internal layers, any altitude. B2: external, uncoated, sea level to 3050 m. B4: external with a permanent polymer coating, any altitude (S3, S4: solder mask does not qualify as that coating).
- Altitude above 3050 m needs larger values (column B3); not offered by the tool.

## Gaps and disagreements
- The columns A5, A6, A7 (component leads, conformal coating over the assembly) are left out: S2 and S3 print different A6 values, so no value could be cross-checked.
- One search snippet claimed B2 is already 1.25 mm from 101 V; S1, S2, S3 all show 0.60 mm for 101-150 V and 1.25 mm from 151 V, so that is used. Use the next higher band if unsure.
- The figures are electrical minimums only. Creepage along surfaces, safety standards (IEC 60950/62368, 60664) and the fab's limits can need more; the fab's minimum always wins when it is larger.
