---
name: project-keeping
description: Keeps the project folder in order, records who decided what and why, lists what else changes when a part or MCU changes, and prepares the final file organization. Use when the student asks "where should I save this", "log this decision", "what changes if I swap this part", "I changed the MCU, what else", "organize my project folder", "what do I submit", "handoff notes" (Hebrew - "סדר בתיקייה", "יומן החלטות", "מה משתנה אם מחליפים", "ארגון קבצים להגשה").
---

# Project keeping

`<repo>` is the repo path given in the WORKSPACE section of the prompt.

## When to use
- The student asks where a file belongs, or the folder is a mess and old versions contradict the new ones.
- A decision was made in chat ("keep this part", "use USB-C") and must be written down.
- A part, MCU, voltage or connector changes: list the knock-on changes before anything is edited.
- The student is near the end and wants the files organized.
- Not for: choosing parts (parts-and-stock), or report text.

## Steps
1. Read the state first: `python <repo>/scripts/model.py <project>` and the project's `notes.md`. Do not rely on the chat.
2. Folder order. One current file per thing. Suggested tree (keep the student's own names if they have them):
   `Docs/` (notes, requirements, datasheets used), `Libraries/`, the schematic and PCB at the project root,
   `Outputs/Fabrication`, `Outputs/Assembly`, `Outputs/Reports`, `_Old/` for superseded files.
   Move a superseded file to `_Old/` with a date; never delete it. Altium files move only from inside Altium
   (Projects panel), because the project file stores their paths.
3. Notes files, short and current, in `Docs/`: STATUS (done / open / next, with a date), PLAN (stages and what finished),
   HANDOFF (read order for the next person or agent). When a note is replaced, say so at the top of the old one.
4. Decision log. Append one entry per decision, never edit an old one: `date | decision | who decided | why | source`.
   "Who" is the student; an advisor proposal is not a decision until the student approves it.
   Source is a datasheet page, a JLC query with time, a course file, or "student preference".
5. Change impact. For a part change: read the new datasheet first. Then walk this list and mark each item affected,
   not affected, or unknown: symbol and pin map, footprint and 3D model, supply voltage and decoupling, pull-ups and
   level shifting, clock or crystal, programming and debug connector, boot pins, net names used in rules, PCB
   placement, BOM line and LCSC number, CPL rotation, silk text, notes and the log. Name the file to edit.
6. Do not apply the change. List it, ask the student, wait for approval, then log it.
7. Final file organization: every output in one place, each file name with the project name and a date or version;
   the project folder as one zip; Gerber zip; BOM, CPL; schematic PDF; DFM report and screenshots; the log.

## Scripts
- `python <repo>/scripts/altium/dump.py <file> [--full]` reads a SchDoc/PcbDoc/PrjPcb/.RUL of the linked Altium project
  (read-only): parts, pins, pads with nets, rules. Use it instead of screenshots.
- `python <repo>/scripts/model.py <project>` prints the project state.
- `python <repo>/scripts/project.py ...` project folder helpers (see its usage text).
- (planned, stage I10) `scripts/keeping.py` folder order, decision log, change impact, final file organization. Until
  it exists, say "not automated yet", write the entries by hand in `notes.md`, and list files by reading the folders.
- Submission itself is out of scope: only the file organization.

## References
- `<repo>/docs/PRODUCT-PLAN.md` (section 7, decisions on order and out-of-scope submission)
- `<repo>/docs/ARCHITECTURE.md` (data layout of a project folder)
- `<repo>/shared/reference/course/ad20-essentials/m02-first-project.en.md` (project and file structure in Altium)

## Pitfalls
- Several sessions or agents write contradicting notes (an old BOM with two parts swapped). Keep one source of truth
  per fact, mark old ones superseded at the top, and check the date before quoting a note.
- A decision that exists only in chat is lost. Write it the same turn, with the reason; the reason is what is needed
  when the next change comes.
- A swap that "only changes the BOM" can still change pads, pin functions, boot behaviour, or the debug path. Walk
  every item of step 5; "unknown" is an answer.
- Moving Altium files in Explorer breaks the project's links; use the Projects panel. Cloud-synced projects: work on
  the local copy and never push to the server for the student.
- Mixed versions in the submission zip (schematic of v2, PCB of v3). Before zipping, confirm date and version of each.
- The name must be in every uploaded file name; pairs name both partners.
- Do not call a part verified or accepted: the script verifies, the student accepts.

## Output
Folder order: a tree, max 20 lines, with the move list `from -> to`. Decision entry: one line in the log format of step 4.
Change impact: table `Item | Affected? | Why | File to edit | Source`, max 15 rows. Final organization: list of
outputs with present / missing. Cite `{{src:<file>|<heading>}}`. Answer in the student's language.
