---
name: schematic-preview
description: Produces example schematic sheets (SVG) the student redraws by hand in Altium - parts split into readable blocks, every pin a short stub ending in a net label, power port or No-ERC cross. Use when the student asks to see a schematic first, "draw me the sheet", "how should I lay out the schematic", "split the circuit into sheets", "which net labels and power ports", "make the schematic readable" (Hebrew - לשרטט סכמה, תצוגה מקדימה של סכמה, איך לחלק לדפים).
---

# Schematic preview (example sheets to redraw)

`<repo>` is the repo path from the WORKSPACE section of the prompt. The tool never draws in Altium; the student does.
The picture is a teaching aid: it shows WHAT to place and HOW to lay it out. The student redraws it, so they learn.

## When to use
- The student has a part list or block idea and wants to see a sheet before drawing it in Altium.
- The student asks how to split a design into sheets or blocks, or how to name nets and power ports.
- An existing sheet is unreadable (crossing wires, tiny text) and they want a cleaner layout to copy.
- Not for: checking a sheet they already drew (use `schematic-review`); placing parts on the PCB (`placement-and-routing-plan`).

## Steps
1. Collect the data first: per IC the pin number, pin name and net; per small part the ref, value and the two nets.
   Take pins from the part's datasheet in `<repo>/shared/datasheets/` or from the student's library. Never guess a pin number;
   write "unknown - need datasheet" and ask for the file (link-and-return) instead.
2. Split into blocks, one framed box each: power in, regulators, MCU core, clock and reset, programming/debug, USB,
   sensors, connectors/UI. Keep a block to about 45 parts or fewer; above that, make a second sheet.
3. Fix the net names before drawing: one short name per net, rails with a sign (`+3V3`, `+5V`), ground `GND`. Same name = same wire.
4. Lay out each IC in the middle of its block: inputs/power on the left, outputs on the right, a short stub on EVERY pin.
   Each stub ends in a power port, a GND symbol, a net label, or a No-ERC cross for a pin that is left open on purpose.
5. Put small parts (R, C, LED, diode) in columns next to the IC, each between two net names. A part on a rail or on GND
   uses that symbol; a part between two signals gets a label at both ends.
6. Place decoupling caps in the picture next to the IC pin they serve and say which pin (the student copies the order).
7. Write the sheet as the JSON model described in the script docstring, run the renderer, and OPEN the image to look
   at it. Fix overlapping text by moving a column or shortening a label. Do not hand over a picture you have not looked at.
8. Cross-check every net in the picture against the source data (datasheet pin table or the student's netlist).
9. Tell the student how to redraw it in Altium: place the parts, then wire only the short stub and name it (Place > Net Label,
   Place > Power Port); cite the AD20 manual step. Say the grey cross-sheet hints are not drawn objects.
10. Send the image path plus a short table (see Output). Say clearly: generated from data, verify with Alt+Click on a net.

## Scripts
- `python <repo>/scripts/skills/render_sheet.py <project> <sheet>` - renders `netlist/<sheet>.json` to `artifacts/sheet-<sheet>.svg`.
- `python <repo>/scripts/validate_netlist.py <sheet.json> <bom.json>` - lists sheet refs missing from the BOM.
- (planned, stage I9) `<repo>/scripts/preview/` - same renderer fed from the netlist read out of SchDoc/PcbDoc.
  Until then the model JSON is written by hand from the datasheet pin tables.

## References
- `<repo>/shared/reference/AGENTS.md` - topic index (read "Schematic anatomy" and "Schematic best practice" rows).
- `<repo>/shared/reference/course/altium-education/unit2-schematics-libraries.en.md` - [01] anatomy, [02] nets, [03] ports,
  [13] before building, [20]-[21] layout.
- `<repo>/shared/reference/course/ad20-essentials/m06-making-the-connection.en.md` - wiring, net labels, power ports in Altium.
- `<repo>/shared/reference/course/ad20-essentials/m05-schematic-capture.en.md` - placing parts and designators.
- `<repo>/docs/PRODUCT-PLAN.md` - capability 5 (schematic preview) and pain point K8 (look before building in Altium).

## Pitfalls
- A wrong net drawn confidently is worse than no picture. The drawing only shows the data you gave it, so verify pin numbers
  against the datasheet before drawing, and list what is unverified.
- Long wires across the page make a sheet unreadable and hide errors. Short stub + label is the method; it maps one to one
  to Altium net labels and power ports. Use a wire only for a 2-pin link inside a block.
- Net names are global in a flat project but local to a sheet in a hierarchy. Say which one the student uses, or the same label on
  two sheets will silently join (or fail to join).
- Overlapping text is the usual defect (long pin names, neighbour labels). Shorten the label or widen the column; look at the image.
- Open pins: show them with a No-ERC cross, not blank. Blank pins become "unconnected pin" ERC warnings later.
- Pin electrical types matter later: passives imported as Input cause "floating input pins" or "no driving source" ERC messages.
  Mention it when the student uses a downloaded library, and send them to `schematic-review`.
- Grid: a part placed off the 100 mil grid gives "Off grid" warnings; tell the student to keep the snap grid on.
- Do not draw more than the student needs: a block diagram first, detail sheets only for blocks they ask for.

## Output
- The image path (SVG/PNG) of each sheet, one per block group.
- Then a table per block: `Ref | Value/part | Pin -> net | Why`. At most 25 rows; summarize repeated passives.
- 3 to 6 lines of "how to redraw in Altium", citing the AD20 manual as `{{src:m06-making-the-connection.en.md|6.3 Wiring the Schematic}}`.
- Every pin number or electrical fact cites the datasheet `{{src:<datasheet file>|p.N}}`, or says "unknown".
- Same language as the student; keep Altium menu names in English.
