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
2. Draft first, then ask. On the first message about a new board write a full first draft AT ONCE, in one turn: the
   description (`idea.describe`), the block diagram (`idea.diagram.edit`), and one `idea.propose` per requirement. Mark
   every guess "(assumed)" in the requirement text. The edits land in a live draft the student sees and can Save or Revert,
   so a wrong guess costs one click. Never open with a questionnaire.
3. Then ask at most 1-3 questions: the ones from the list below whose answer would change the draft most and are
   expensive to change later. Per question: one line "why it matters" and your default (the one already in the draft).
4. When the answers come, change the draft (replace "(assumed)" with the agreed value), list what each answer forces
   (a connector, a part, a footprint, a rule) and name the skill that handles it.
5. When you think the idea is agreed, emit `{"type": "idea.ready"}`: the reply shows a Confirm idea button and the student
   decides. Do not ask them to type a yes. `idea.confirm` still exists, only with a quote of a clear yes in their last message.
- `{"type": "idea.describe", "text": "..."}` the board in plain words (what it is, what it is for, the diagram told as text);
  applies to the draft at once.
6. Student edits go into the same draft. Read the draft (the idea in the project state) before changing anything.
7. Block diagram: edit directly with `idea.diagram.edit` (live in the draft, no approval) for adding/updating blocks, buses,
   connectors, frames, or auto-layout. Use `idea.diagram` (proposal with approve/reject) only for whole-diagram
   overhauls. Keep block text short: name + one-line role (e.g. "Charger\nBQ24075", "MCU\nSTM32G030"); label connectors
   with bus or rail ("5V", "I2C", "SPI"). Available ops: `add_shape`, `update_shape`, `delete_shape`, `add_connector`,
   `update_connector`, `delete_connector`, `add_frame`, `update_frame`, `delete_frame`, `auto_layout`. See
   `references/diagram-ops.md` for full op syntax and power-chain, MCU-bus, and dashed-domain-frame examples.
   Default layout for a new diagram: the "system block diagram" style in that file (a board frame with off-board parts
   outside, one colour per domain, a labelled link each, dashed safety paths). Use it unless the student asks otherwise.

Question list (pick, do not ask all):
- Power: source (USB, battery, adapter, 12 V), highest and lowest voltage, peak current, battery life target, charging.
- Flashing and debug: how is the first firmware loaded and how is it debugged? ROM USB DFU (which pins), UART boot, or an SWD header.
  When an MCU is named, look its family up in `references/mcu-bootloaders.json` and cite its `source` field (not
  memory); a family not listed there is "unknown".
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
- `references/mcu-bootloaders.json` - which MCU families have a ROM USB DFU bootloader, with sources (in this skill folder).

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
- Do not ask 30 questions, and do not ask before drafting. A draft the student can correct beats a questionnaire they must answer.

## Output
- The draft actions, then at most 3 questions in the student's language. Per question: `Question - why it matters - default used in the draft`.
- One last line: the next step and the skill that handles it. About 200 words at most.
- A claim about a chip's boot mode or pins needs a datasheet citation or the word "unknown".
