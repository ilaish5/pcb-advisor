---
name: rules-and-calcs
description: Produces the PCB design-rule table (JLC limits by layer count plus extra rules for current, impedance, noise), one .RUL file to import into Altium once, a read-back diff of the rules in the PcbDoc, and calculations (trace width, impedance, voltage divider) with formula and source for every number. Use when the student asks "which design rules do I set", "JLC minimum clearance / via / hole", "trace width for 2 A", "50 ohm trace width", "resistor divider for the feedback pin", "export the rules", "are my rules still the JLC ones" (Hebrew - חוקי תכנון, רוחב מסלול, מחלק מתח).
---

# Rules and calculations

`<repo>` is the repo path from the WORKSPACE section of the prompt. This tool is the single source of the rules: the student
never types them twice. The tool writes a `.RUL` file; the student imports it once in Altium. Later the tool reads the rules back
from the PcbDoc and shows differences. You never edit the PcbDoc.

## When to use
- The student starts the PCB and asks which rules, which layer count, which clearance/width/via values to use.
- A number is needed with a reason: trace width for a current, width for a target impedance, a divider resistor pair.
- The student changed rules in Altium and wants to know what differs from the plan.
- A DRC violation looks like a rule that is too tight or too loose (explain which JLC limit is behind it).
- Not for: placement or routing order (`placement-and-routing-plan`); reading DRC results of a finished board (`board-review`).

## Steps
1. Ask only what is theirs: layer count (2 or 4), copper weight (1 or 2 oz) and mask colour if they know, board thickness, which nets carry high current,
   whether any net is impedance-controlled (USB high speed, RF), and any special net (analog, crystal, switcher node).
2. Fix the capability limits from `references/jlc-limits.md`: the preset follows the project's layers, copper weight and mask colour
   (name on the Rules page, e.g. "JLC 4-layer 1 oz"). Those numbers carry a check date. If older than a month, tell the student to open
   the JLC capabilities page and read the value, then write the date.
3. Design to a margin above the fab minimum, not at it. Default set: clearance and track a bit above the minimum, via size
   and hole inside the capability, annular ring at least the fab minimum, copper-to-edge >= the fab figure.
4. Classify nets: power by current, sensitive (analog, crystal, feedback, reset), noisy (switch node, clocks, relay/coil), RF/high speed.
   Auto-named nets appear only after the first Update PCB (ECO); add them to the rules then, or label the nets in the schematic.
5. Calculate with the scripts below. Show the formula, the inputs (current, temperature rise, copper weight, layer) and the result
   rounded UP. State that IPC-2221 and IPC-2152 differ and which one was used.
6. Build the rule table: `Rule | Scope | Min/Pref/Max | Why | Source`. Specific rules get higher priority than the board default
   (Altium rule priorities: course m19 19.3.2).
7. Produce the `.RUL` when the tool supports it (see Scripts). Tell the student the import path in Altium (verified AD26): Design > Rules, right-click
   "Default Rule Set" > Import Rules... > pick the file > "Select Design Rules" (leave all ticked) > Import. In "Rule Set Already
   Exists": with a board-aware file (`export --board <PcbDoc>`, carries all the board's rules with JLC values) choose
   "Replace existing rules"; with the plain preset file choose "Merge with existing rules", then open "Priorities..." and raise the
   imported `*_1` rules to the top (or delete the old rules of the same kind). Then re-run the read-back diff.
8. Read-back: when the student says they edited rules, read the PcbDoc rules and list `only in plan / only in board / value differs`.
   Ask "update the plan from the board?" before changing anything.
9. Add layout practices that are not rules (stitching vias, decaps at the pins, hot-loop size) as a plain list for the layout stage.
   JLCDFM also checks what Altium has no rule for (silk line width, slot width, via to PTH, PTH to trace); list them as manual
   checks, mapping in `references/jlc-limits.md`.

## Scripts
- `python <repo>/scripts/rules.py diff <pcbdoc> [--project <name>]` - diff of a PcbDoc's rules vs the JLC preset
  (rule, kind, board value, preset value, status, verdict).
- `python <repo>/scripts/rules.py export <output.RUL> [--board <PcbDoc>] [--project <name>]` - export the preset to a .RUL file.
  With --board it is the full board rule set with JLC values (import with "Replace existing rules").
- `python <repo>/scripts/rules.py preset [--project <name>]` - print the preset. `--layers <n>` and `--oz <n>` override the project's board.
- `python <repo>/scripts/calc.py trace-width <amps> [--rise <C>] [--oz <n>]` - IPC-2152 trace width in mm and mil.
- `python <repo>/scripts/calc.py divider <vin> <vout>` - voltage divider resistor calculation with standard E24 values.
- `python <repo>/scripts/calc.py led <v_supply> <v_forward> <i_ma>` - LED series resistor and power rating.
- `python <repo>/scripts/calc.py via <drill_mm> [--rise <C>]` - via barrel current-carrying capacity.
- `python <repo>/scripts/calc.py microstrip <width_mm> <height_mm> [--er <val>]` - microstrip impedance (IPC-2141 approx).
- `python <repo>/scripts/trace_width.py <amps> --layer external|internal --rise <C> --oz <n>` - IPC-2221 width in mm and mil.

## References
- `references/jlc-limits.md` - capability numbers with source and date, JLC stack-ups, rule catalogue with typical values.
- `<repo>/shared/reference/jlc/pcb-capabilities.en.md` - full JLC tables (1-2 layer and multilayer, by copper weight, mask colour), cited with URL and date.
- `<repo>/shared/reference/course/ad20-essentials/m19-pcb-rules-and-panels.en.md` - 19.3 editor and priorities, 19.4 net classes.
- `<repo>/shared/reference/course/altium-education/unit3-pcb-layout.en.md` - [22]-[26] rule types and what values to use.
- `<repo>/shared/reference/course/altium-education/unit4-routing-signal-integrity.en.md` - [06]-[08] vias, [17] impedance.
- `<repo>/shared/reference/AGENTS.md` - topic index; JLC limits are not in the course, so cite the JLC page and its date.

## Pitfalls
- A fab minimum is not a design value. Boards designed at the limit fail on small fab variations and make every DFM check red.
  Keep a margin, and keep one set of values that works for any maker.
- Capability numbers change and depend on layer count (2-layer and multilayer differ for via and trace). Cite the page and the date;
  never quote from memory.
- A trace sized only by IPC-2221 may be too thin for a pulsed load; use the peak current of the datasheet and round up. Inner layers
  carry about half the current of outer layers at the same width.
- Impedance needs the REAL stack-up (dielectric height, Er) from the fab's published stack; with the wrong height the width is wrong.
  Confirm in the fab's own calculator before ordering. USB full speed needs no controlled impedance; high speed does.
- A rule that is too narrow for a part's pins (a 1 mm power width on 0.65 mm pitch pins) floods DRC. Set a min width the pins
  can take and neck down, and route the wide part by hand.
- Priorities: Altium applies the first matching rule by priority; a new rule lands at priority 1 and can silently override the
  board default. Check the order after import.
- Merge import renames same-named rules (`Clearance_1`) at priority 2, so the old rule still wins
  until the order is fixed. Replace removes the board's rules, so use it only with the board-aware file. Altium's export skips one default rule; a diff will
  show it as missing; that is expected.
- Auto-generated net names (from ECO) are not the schematic names; a rule scoped to a name that does not exist applies to nothing.
  Check each scope name against the board's net list.
- JLC checks the Gerbers without nets. It flags things Altium's DRC accepts (silk line width, via-to-pad spacing, NPTH "annular
  ring" in red). Mention these when explaining a red DFM mark, and send the student to `manufacturer-and-dfm`.

## Output
- Rule table, max 25 rows: `Rule | Scope | Min / Pref / Max | Why | Source`. Source = `{{src:<file>|<heading>}}` or JLC page + date.
- Calculation: 3 lines (formula, inputs, result rounded up) plus the source of the formula (IPC standard or course heading).
- Files: path of the `.RUL` when produced, and the one line on how to import it. Diff: three short lists.
- Say plainly which numbers are unverified. Student's language; rule kinds keep Altium's English names.
