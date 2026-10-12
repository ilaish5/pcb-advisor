---
name: idea-and-requirements
description: Turns a rough project idea into a short list of open requirements questions, the ones students regret not asking early. Use when the student describes a new idea or starts a project ("I want to build...", "what should I decide first", "which MCU", "how do I flash it", "battery or mains", "what connectors"; Hebrew - "יש לי רעיון לפרויקט", "מה צריך להחליט לפני שמתחילים", "איך צורבים").
---

# Idea and requirements

## When to use
- The student has an idea, or a project with no written requirements yet, and has not placed parts.
- The student is about to choose an MCU, a power source, a connector or a memory part.
- The student changes their mind later (new feature, new MCU): list what else the change touches.
- Not for: stock of chosen parts (`parts-and-stock`), or review of a drawn schematic (`schematic-review`).

## Steps
1. Read the idea and notes of the current project (`idea.json`, `notes.md`; paths are in the WORKSPACE section). Do not re-ask what is written.
2. Go through the question list below. Pick the 4-6 questions that are still open AND expensive to change later.
   Skip the ones the idea already answers. Never ask all of them.
3. For each open question give: the question, one line "why it matters" (what breaks if it is decided late), and a suggested default.
4. Ask the student to answer in one message. Do not choose for them: a default is only a proposal.
5. After the answers, list what each answer forces (a connector, a part, a footprint, a rule) and name the skill that handles it.
6. Record agreed items with `idea.propose`, one per topic. Use `idea.confirm` only after a clear yes, quoting their words.
7. Block diagram: edit directly with `idea.diagram.edit` (live, no approval) for adding/updating blocks, buses,
   connectors, frames, or auto-layout. Use `idea.diagram` (proposal with approve/reject) only for whole-diagram
   overhauls. Keep block text short: name + one-line role (e.g. "Charger\nBQ24075", "MCU\nSTM32G030"); label connectors
   with bus or rail ("5V", "I2C", "SPI"). Available ops: `add_shape`, `update_shape`, `delete_shape`, `add_connector`,
   `update_connector`, `delete_connector`, `add_frame`, `update_frame`, `delete_frame`, `auto_layout`. See
   `references/diagram-ops.md` for full op syntax and power-chain, MCU-bus, and dashed-domain-frame examples.

Question list (pick, do not ask all):
- Power: source (USB, battery, adapter, 12 V), highest and lowest voltage, peak current, battery life target, charging.
- Flashing and debug: how is the first firmware loaded and how is it debugged? ROM USB DFU (which pins), UART boot, or an SWD header.
- Cables: which cables leave the board, on which edge, which way the plug enters, any enclosure or panel hole.
- UI: buttons, LEDs, display, buzzer. What the user touches, and where.
- Memory: how much data and code, how often written. A smaller part is usually enough and much cheaper.
- Modules and radio: a module has a fixed footprint and an antenna rule. Decide it before the board outline.
- Size and layers: board size, mounting holes, height limit from an enclosure, 2 or 4 layers.
- Assembly at JLC: assembled or bare PCB, one side only, Basic parts preferred, Standard or Economic assembly, quantity.
- Environment: temperature, moisture, ESD at user-facing connectors.

## Scripts
- None needed for the questions. Do not run stock checks here; if the student already names parts, go to `parts-and-stock`.
- `python <repo>/scripts/model.py <project>` prints the project state (idea, BOM). Read it before asking.
- `python <repo>/scripts/keeping.py <project> log|decisions` - records agreed architectural decisions in the decision log.

## References
- `<repo>/docs/PRODUCT-PLAN.md` - section 1 (K4: late requirements cost a day of rework) and section 3.
- `<repo>/shared/reference/course/altium-education/unit2-schematics-libraries.en.md` - [15]-[19], [22] component choice, supply chain.
- `references/question-bank.md` - why-it-matters text and follow-ups per question (in this skill folder).
- `references/diagram-ops.md` - operations and examples for live diagram editing (in this skill folder).

## Pitfalls
- Flashing is the classic late question. Some MCU families have a ROM USB DFU boot mode, only on fixed USB pins; others only
  UART. Check the MCU reference manual or ST's boot-mode application note and cite the page, or say unknown. Switching MCU after
  placement means new symbol, footprint, ECO and re-placement: about a day lost.
- An SWD-only board needs a programmer the student may not own. Ask what they have. A BOOT button plus UART test pads is a cheap fallback.
- Connector side is decided by the enclosure and the cable, not by where the pins fall. A backwards connector is often seen only in 3D
  at the end. Ask which edge each cable leaves before placement.
- A large memory "just in case" can be the most expensive part. Estimate real data (bytes per record x records) before choosing.
- Assembly type moves the price. Modules and some fine-pitch parts may be Standard-only, and every Extended part type adds a fixed fee.
  Say it early; `parts-and-stock` then checks the real parts.
- Do not ask 30 questions. A long questionnaire gets ignored; the five that matter beat all of them.

## Output
- A list of at most 7 items in the student's language. Per item: `Question - why it matters - suggested default`.
- One last line: the next step and the skill that handles it. About 200 words at most.
- A claim about a chip's boot mode or pins needs a datasheet citation or the word "unknown".
