---
name: board-review
description: Reviews a placed or routed PCB for expensive late layout mistakes and explains DRC messages. Use when the student asks "is my board OK", "check the layout", "connector direction", "decoupling caps close enough", "antenna keep-out", "GND pour", "what does this DRC violation mean" (Hebrew - "לבדוק את הלוח", "כיוון מחבר", "הפרות DRC").
---

# Board review

`<repo>` is the repo path given in the WORKSPACE section of the prompt.

## When to use
- The student has a PcbDoc (placed or routed) and wants it checked before outputs.
- A question about connector direction, decap distance, antenna or RF area, GND pour or stitching, silkscreen.
- The student pastes or describes a DRC violation and asks what it means or how to fix it.
- Not for: choosing rules or widths (rules-and-calcs), export files and the JLC DFM site (manufacturer-and-dfm).

## Steps
1. Read `board_facts` and `constraints` in CURRENT STATE first; ask only for the
   board facts neither has: board outline and mounting holes, which side each connector's cable
   enters, any antenna or module with a datasheet keep-out. If the student gives only a screenshot, review the screenshot
   and say what you cannot see (bottom side, inner layers).
2. Connectors. Run `python <repo>/scripts/checks/board.py <pcbdoc> --design <project>`
   (the PcbDoc path: the linked Altium project line in WORKSPACE) to verify opening orientation against the nearest board edge normal. For each connector,
   the opening must face outward toward the board edge and be free of obstructing parts. Ask for a tilted 3D screenshot
   (View > 3D layout mode, tilt, look from the edge) to verify symmetric footprints that may hide a 180° rotation.
3. Decoupling. The same `checks/board.py` run measures distance from each decoupling cap to its IC power pin on the same net.
   Aim for 2-3 mm from the pin; `checks/board.py` flags above 5 mm. The small cap sits closer than the bulk cap. One cap per
   supply pin, not one cap for all.
   Flag a cap whose current path goes through a via first. Datasheet layout advice wins over the rule of thumb; cite its page.
4. RF and antenna. Use the module datasheet keep-out: no copper, no pour, no parts under or beside the antenna element
   as drawn there. Feed line: short, one layer, over an unbroken reference plane, with GND stitching vias beside it.
   Ask for the stackup before judging width; do not guess an impedance (rules-and-calcs).
5. GND and pours. Check that a GND reference exists under fast and sensitive nets and is not split. After any copper
   change, repour (Tools > Polygon Pours > Repour All) before judging. Look for islands (dead copper), thin necks, and
   stitching vias along the board edge and around RF lines. Cite {{src:m22-polygons-and-power-planes.en.md|22.3}}.
6. Silkscreen. Designators readable and not over pads; polarity and pin 1 marks visible; board name, version and date
   present; text not under parts. Text height and stroke must meet the fab minimum (ask the manufacturer-and-dfm skill).
7. DRC. Have the student run the batch Design Rule Check (Tools > Design Rule Check, all rules enabled) and paste the
   violations list. Group by rule, explain each class in one line, say fix the copper or change the rule, never both
   blindly. Online DRC at zero is not enough (see Pitfalls). Cite {{src:m23-drc.en.md|23.5 Resolving Violations}}.
8. Write the findings table. Offer to re-check after the fix; do not edit the board yourself.

## Scripts
- `python <repo>/scripts/altium/dump.py <file> [--full]` reads a SchDoc/PcbDoc/PrjPcb/.RUL of the linked Altium project
  (read-only): parts, pins, pads with nets, rules. Use it instead of screenshots.
- `python <repo>/scripts/trace_width.py ...` IPC-2221 trace width for a current; use it instead of estimating.
- `python <repo>/scripts/model.py <project>` prints project state (BOM, parts, notes) to read the part list.
- `python <repo>/scripts/checks/board.py <pcb_file> [--design <project>]` connector opening vs nearest edge, decap distance, CPL rotation;
  with `--design` also nets, pins and parts the board lacks. Run it with every DRC review.
- Never run Altium, Altium scripts or the GUI. The student runs DRC and sends the result.

## References
- `<repo>/shared/reference/course/ad20-essentials/m23-drc.en.md` (DRC, Violations panel, resolving)
- `<repo>/shared/reference/course/ad20-essentials/m22-polygons-and-power-planes.en.md` (pours, repour)
- `<repo>/shared/reference/course/altium-education/unit3-pcb-layout.en.md` ([06] Preparing for Manufacturing)
- `<repo>/shared/reference/course/altium-education/unit4-routing-signal-integrity.en.md` (return path, EMI)
- `<repo>/shared/reference/AGENTS.md` (topic index). Decoupling and antenna layout are NOT in the course: use the part
  datasheet, or say it is general knowledge.

## Pitfalls
- Connector faces inward: a body with symmetric pads can be placed 180 degrees wrong and pass every number check. It
  shows only in 3D, and the model itself can be rotated or offset from its pads. Check every connector in 3D, each time
  the board changes.
- Online DRC 0 is not clean. Batch DRC also checks mask slivers, silk to solder mask and acute angles. Run it after the
  last repour. Unrouted nets are not reported by online DRC.
- A rule value changed to silence a violation hides a real fault. Change the rule only when the fab capability allows
  it, and write why next to the rule.
- Unused pads of a footprint that is not exactly the module in use (variant mismatch) need no paste and no copper.
  Better: fix the footprint against the datasheet.
- Longer pads or moved parts can touch same-net vias; Altium ignores same-net contact, the JLC DFM tool flags it.
- Autorouted tracks can run under a module or antenna. Look at the area under every module on both layers.
- A pour split on a plane layer breaks the return path of any signal that crosses it, also from the neighbour layer.

## Measured, not remembered
Positions, distances, copper under the antenna: quote `board_facts` only if not marked stale; "none measured" = say "planned"
(AGENTS.md, WHERE THINGS ARE). The `requirements` rows (met, violated, unverifiable; `python <repo>/scripts/model.py <project>`)
are the checklist of what the student confirmed.

## Output
The chat is a narrow side panel: lead with the verdict in one line ("One thing to fix: J1 faces inward"), then only the
findings that need the student, worst first, one line each: what is wrong, where, the fix, with the evidence as a chip
(`{{src:<file>|<heading or page>}}`, or the student's image). A table (`Finding | Where | Fix`, max 8 rows) only for
four or more findings. What passed is not listed: "the rest of what I checked is fine" inside the verdict line is enough. A check that
belongs to a later stage (rotation in the JLC preview) is not a finding now: leave it out. What you could not check
(no DRC result, bottom side not seen) goes into the next action ("then run the DRC and send me the list"), not into a
line of its own. End with that one next action. Under 70 words for one or two findings. Answer in the student's language.
