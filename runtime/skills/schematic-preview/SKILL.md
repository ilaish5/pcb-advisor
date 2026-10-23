---
name: schematic-preview
description: Produces example schematic sheets (SVG) - parts split into readable blocks, every pin a short stub ending in a net label, power port or No-ERC cross - then asks the student whether they redraw it by hand in Altium or the agent draws it there (action altium.draw_schematic). Use when the student asks to see a schematic first, "draw me the sheet", "how should I lay out the schematic", "split the circuit into sheets", "which net labels and power ports", "make the schematic readable" (Hebrew - לשרטט סכמה, תצוגה מקדימה של סכמה, איך לחלק לדפים).
---

# Schematic preview (example sheets to redraw)

`<repo>` is the repo path from the WORKSPACE section of the prompt. The picture is a teaching aid: it shows WHAT to place and HOW to
lay it out. Who puts it into Altium is the student's choice (step 11): they redraw it themselves, so they learn, or you draw it.

## When to use
- The student has a part list or block idea and wants to see a sheet before drawing it in Altium.
- The student asks how to split a design into sheets or blocks, or how to name nets and power ports.
- An existing sheet is unreadable (crossing wires, tiny text) and they want a cleaner layout to copy.
- Not for: checking a sheet they already drew (use `schematic-review`); placing parts on the PCB (`placement-and-routing-plan`).

## Steps
1. Collect the data first: per IC the pin number, pin name and net; per small part the ref, value and the two nets.
   Take pins from the part's datasheet in the project's `sources/` or from the student's library when one is there. Simple parts
   (R, C, L, LED, diode, ferrite, crystal, generic connector) need none. For an IC or transistor with no datasheet, fetch it first
   (`jlc.py part` gives `datasheet_url`; `sources.py get <project> <url> <MPN>.pdf`). If no link works, use the well-known pinout
   and keep going: the part is saved as `pins_source: "agent"` (unverified); say which datasheet is missing. If you truly do not
   know the pinout of a part, leave that part out and say so; do not invent pins.
   Never wait for a complete sheet: write it early and partial. Draw what is known, leave undecided pins with net "" (shown as an
   open pin) and include parts whose BOM proposals are still pending (shown "pending approval"). The write returns warnings
   (open pins, parts not in the BOM yet); tell the student in one line, e.g. "sheet written, 3 open pins, U5 waits for approval".
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
11. End the preview with ONE question, in the student's language: "Do you want to draw this in Altium yourself, or should I draw it?"
    Then stop and wait. Never draw before the answer, and never answer for them.
    - "Myself" (or no clear answer): the manual path, steps 9-10 stay as they are; do not run the action.
    - "You draw it": run `{"type": "altium.draw_schematic", "student_said": "<their words, most of their last message>"}` (add
      `"sheet": "01"` for one sheet). The action is refused when the quote is only a fragment, or when their message says they draw it
      themselves ("I'll draw it myself", בעצמי, אני אשרטט). "תשרטט לבד" means YOU draw it. It needs the library built (`library.build`)
      and Altium open. It opens the project's SchDoc (adds one when the project has none), places every part from the project library
      (pin count checked against the library symbol), sets the designators, keeps the footprint and parameters, puts a wire stub +
      power port or net label on every connected pin and a No ERC cross on NC pins, lays the parts out on a grid, saves, and reads the
      saved file back to compare every net with the
      netlist. Report the result in the student's words: parts placed, nets, warnings (open pins, pins not in the library).
    - It refuses (and tells you why) when the sheet already has anything on it, or is open in Altium with unsaved changes: the student's
      drawing is never wiped. Only when the student says to replace the old drawing, ask them, then add `"replace": true` and
      `"replace_said"` = their words (replace, redraw, overwrite, start over, מחדש, תחליף, תמחק); the old file is copied to
      `.advisor-backup` first. Pins are matched by number: a different name is a warning (tell the student), a name that is
      another library pin's is a swap and refused. Hebrew headings are drawn as "Section N". Multi-part symbols are not
      drawn: say which, and fix the netlist or draw that part by hand. A refusal because the library lacks a symbol, a pin count
      differs, or the sheet does not fit one A4 page: say what is missing and fix that (library, netlist, a second sheet),
      never work around it with a script in Altium.
    - NEXT STEP after the schematic is drawn (never tell the student to do Design > Update PCB by hand, that is not the offer):
      ask ONE question in their language: "Should I place the parts on the board, or will you (Update PCB)?" Then stop and wait.
      "You place them" = follow the `placement-and-routing-plan` skill (`altium.place_pcb`, only on their answer); "myself" = then
      and only then explain Design > Update PCB.
    - Afterwards the student can check it with `schematic-review`. The layout is simple (a grid per section), readable, not optimized:
      say so, they may move parts by hand.

## Scripts
- `python <repo>/scripts/preview_sch.py <schdoc> [--output <out.svg>]` - renders a linked Altium .SchDoc to interactive SVG.
- `python <repo>/scripts/skills/render_sheet.py <project> <sheet>` - renders `netlist/<sheet>.json` to `artifacts/sheet-<sheet>.svg`.
- `python <repo>/scripts/validate_netlist.py <sheet.json> <bom.json>` - lists sheet refs missing from the BOM.
- Action `altium.draw_schematic` draws the sheet in Altium; only after step 11.

## References
- `<repo>/shared/reference/AGENTS.md` - topic index (read "Schematic anatomy" and "Schematic best practice" rows).
- `<repo>/shared/reference/course/altium-education/unit2-schematics-libraries.en.md` - [01] anatomy, [02] nets, [03] ports,
  [13] before building, [20]-[21] layout.
- `<repo>/shared/reference/course/ad20-essentials/m06-making-the-connection.en.md` - wiring, net labels, power ports in Altium.
- `<repo>/shared/reference/course/ad20-essentials/m05-schematic-capture.en.md` - placing parts and designators.
- `<repo>/docs/PRODUCT-PLAN.md` - capability 5 (schematic preview) and pain point K8 (look before building in Altium).

## Pitfalls
- A wrong net drawn confidently is worse than no picture. The drawing only shows the data you gave it, so verify pin numbers
  against the datasheet when there is one; if not, draw from the known pinout, mark it unverified and list those parts.
- Long wires across the page make a sheet unreadable and hide errors. Short stub + label is the method; it maps one to one
  to Altium net labels and power ports. Use a wire only for a 2-pin link inside a block.
- Net names are global in a flat project but local to a sheet in a hierarchy. Say which one the student uses, or the same label on
  two sheets will silently join (or fail to join).
- Overlapping text is the usual defect (long pin names, neighbour labels). Shorten the label or widen the column; look at the image.
- Open pins: net "" while undecided (red ?); `NC` once decided to leave them open (No-ERC cross). Blank pins become "unconnected pin" ERC warnings later.
- Pin electrical types matter later: passives imported as Input cause "floating input pins" or "no driving source" ERC messages.
  Mention it when the student uses a downloaded library, and send them to `schematic-review`.
- Grid: a part placed off the 100 mil grid gives "Off grid" warnings; tell the student to keep the snap grid on.
- Do not run `altium.draw_schematic` because the preview looks good: the student chooses, in their own words. "ok" or "continue" is not a choice.
- Do not draw more than the student needs: a block diagram first, detail sheets only for blocks they ask for.

## Output
- The image path (SVG/PNG) of each sheet, one per block group.
- Then a table per block: `Ref | Value/part | Pin -> net | Why`. At most 25 rows; summarize repeated passives.
- 3 to 6 lines of "how to redraw in Altium", citing the AD20 manual as `{{src:m06-making-the-connection.en.md|6.3 Wiring the Schematic}}`.
- Every pin number or electrical fact cites the datasheet `{{src:<datasheet file>|p.N}}`, or says "unknown".
- Same language as the student; keep Altium menu names in English.
