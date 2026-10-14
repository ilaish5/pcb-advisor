---
name: schematic-review
description: Reviews the student's schematic and returns a findings table where every finding cites a datasheet page - pull-ups/pull-downs, open-drain versus push-pull outputs, decoupling per datasheet (including a cap above the MAX value on a regulator pin), abs-max ratings, unconnected pins, MCU-swap fallout, and ERC messages explained. Use when the student asks "check my schematic", "do I need a pull-up here", "is this cap OK", "what does this ERC error mean", "I changed the MCU, what else changes" (Hebrew - לבדוק סכמה, צריך pull-up, שגיאת ERC, החלפתי מעבד).
---

# Schematic review (findings with datasheet citations)

`<repo>` is the repo path from the WORKSPACE section of the prompt. Read-only: you never edit the student's files.
A finding without a datasheet page is not a finding; it is a question to the student.

## When to use
- The student finished (or half finished) a sheet and wants it checked before Update PCB.
- A specific question: pull-up or not, cap value, voltage limit, what to do with an unused pin.
- The student pasted ERC/compile messages and does not understand them.
- The student replaced a part (most often the MCU) and asks what else must change.
- Not for: drawing an example sheet (`schematic-preview`); layout after the board exists (`board-review`).

## Steps
1. Get the real data, not a screenshot: the SchDoc/PrjPcb in the student's local project, or the PcbDoc netlist after ECO
   (pads carry nets). If you only have an image, say so and mark every finding "from image, unverified".
2. List the active parts (ICs, regulators, connectors with signals). For each, find its datasheet in the project's `sources/`
   (general documents are in `<repo>/shared/datasheets/`). No datasheet: ask the student for it (link-and-return) and skip that part; never review from memory.
3. For each IC read the pin table, the "recommended operating conditions", the "absolute maximum ratings", the typical
   application circuit and the electrical-characteristics rows for the pins you check. Note the page of each.
4. Run the checks of `references/checklist.md` in order: run `scripts/checks/schematic.py` to flag single-pin nets,
   unconnected IC power pins, sheet-local net labels, and power/ground pin name mismatches; then check decoupling,
   resets and boot pins, pull-ups/pull-downs, output types, abs-max margins, regulator caps, crystal load caps.
5. Output type: read the VOH/VOL or "output structure" rows. A pin with VOH near VCC is push-pull: no pull-up, and a pull-up
   may even hold a downstream switch on when the driver is dead. Only an open-drain/open-collector pin (or an input with no
   internal bias) needs one.
6. MCU or part swap: diff the old and new pin tables pin by pin (`references/checklist.md`, section "Swap").
   Tell the student what the new part needs (for example a core-regulator pin that needs a capacitor) and what it no longer needs.
7. ERC messages: look the text up in `references/erc-messages.md`; explain cause and fix in two lines; fix the root cause
   (usually a pin type in the library, or a missing port), not by suppressing the message.
8. Keep unknowns separate: "not found in datasheet", "value only in a figure". Do not guess a value.
9. Answer with the table below, worst first. Offer to re-check after the student fixes the top items.

## Scripts
- `python <repo>/scripts/altium/dump.py <file> [--full]` reads a SchDoc/PcbDoc/PrjPcb/.RUL of the linked Altium project
  (read-only): parts, pins, pads with nets, rules. Use it instead of screenshots.
- `python <repo>/scripts/skills/verify_part.py <project> <bom-key>` - checks the part's pin numbers against the datasheet text.
- `python <repo>/scripts/validate_netlist.py <sheet.json> <bom.json>` - sheet refs missing from the BOM, pins without a net.
- `python <repo>/scripts/checks/schematic.py <file>` builds netlist from wire geometry and checks single-pin nets, unconnected IC power, and rail mismatches.

## References
- `references/checklist.md` - the checks, how to read each datasheet section, the swap procedure.
- `references/erc-messages.md` - common Altium ERC/compile messages with cause and fix.
- `<repo>/shared/reference/course/ad20-essentials/m09-compiling.en.md` - 9.3 Project Options, 9.4 compiler, ERC and connection matrix.
- `<repo>/shared/reference/course/altium-education/unit2-schematics-libraries.en.md` - [07] pin directions, [02] nets, [03] ports.
- `<repo>/shared/reference/course/altium-education/unit4-routing-signal-integrity.en.md` - [29] I2C, [30] SPI, [31] UART.
- `<repo>/shared/reference/AGENTS.md` - decoupling is not in the course; use the datasheet and say there is no course source.

## Pitfalls
- Arguing from search snippets or memory wasted hours once, on whether a fault pin needed a pull-up. The datasheet's VOH row
  settled it in one minute (push-pull). Open the electrical-characteristics table first, then answer.
- A reviewer working from screenshots reported a part "missing from the schematic" when it was there. Read the files; a
  claim about connectivity needs a net list or a pin-to-net line, not a picture.
- Capacitor values have a MAX as well as a MIN. A supply or BIAS/VCC pin of a switching regulator may allow only a few hundred nF;
  a "more decoupling is better" 1 uF exceeded the limit. Compare every cap value with the datasheet table, both ends.
- Core-regulator pins (VCAP-style) on some MCUs need a specific capacitor to ground; the same package on a sibling MCU may use
  that pin as a GPIO. Without the cap the chip does not start. Check this on every MCU swap.
- Swapping a part changes more than its symbol: pins that moved, internal pull-ups that now make an external one wrong
  (a USB D+ pull-up inside the chip plus an external one breaks USB), boot-mode pins and the programming path.
- ERC "no driving source" or "floating input" usually means pin types in the imported library (passives typed Input),
  not a wiring mistake. Fix the library symbol; do not paper over it with a No-ERC cross.
- An unconnected pin is fine only if the datasheet says "NC / leave open". Otherwise tie it as the datasheet says (for example
  an enable or a mode pin). Unused inputs must not float.
- Absolute maximum is not an operating point. Check recommended operating conditions, and the margin on 5 V signals into 3.3 V pins.
- Datasheet revisions and package variants differ (letters at the end of the part number). Confirm the exact variant and package.

## Output
Table, worst first, max 12 rows: `# | Sev (error/warn/info) | Where (ref.pin or net) | Finding | Fix | Source`.
Source = `{{src:<datasheet file>|p.N <heading>}}` or `{{src:<course file>|<heading>}}`; if none, write "unknown - no source" and mark it a question.
Then one line: what was NOT checked (no datasheet, image only). Student's language; keep pin and net names as written.
