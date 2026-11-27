---
name: altium-help
description: Step-by-step "how do I click it" answers for Altium Designer, cited from the AD20 Essentials manual. Use when the student asks how to do something by hand in Altium (menus, panels, shortcuts, compile, ECO / Update PCB, layers, polygons, DRC) or what a dialog or error means (Hebrew - "איך עושים ב-Altium", "איפה התפריט"). Rule values, library building and factory files: other skills.
---

# Altium help

Probe marker (used only by `python pcb.py probe`; ignore otherwise): PROBE-ALTIUM-7Q4X

`<repo>` is the repo path given in the WORKSPACE section of the prompt. Paths below are relative to it.

## When to use
- "How do I ... in Altium": a procedure, a menu path, a panel, a shortcut, a dialog setting.
- "What does this menu, dialog or error mean?" (compile, ERC, ECO, Footprint Not Found, DRC message).
- A concept question that needs an Altium picture (layers, rules, polygons, libraries).
- Not for: whether a design is good (board-review, schematic-review); rule values (rules-and-calcs); building the library
  (project-library); manufacturer files (manufacturer-and-dfm). Those topics are here only as "how to click it in Altium".

## Steps
1. Ask the Altium version only if the answer depends on it (Layer Stack Manager, Preferences, Components panel). Default:
   the student has a newer Altium (AD24-26) and the manual is AD20.
2. Open `<repo>/shared/reference/AGENTS.md` and find the topic in its "Topic index". Never read the whole tree.
3. For a procedure, open ONE section of one `mNN-<slug>.en.md` file in `<repo>/shared/reference/course/ad20-essentials/`
   (grep the heading or a keyword first). These are step-by-step "click here" instructions from Altium Designer 20.
4. For a concept (why, what is it), use the `course/altium-education/` unit named in the index
   (the course text is English; answer in the student's language).
5. Answer with a short numbered list of steps, in the student's language. Keep menu and dialog names in English
   exactly as in the manual. Mark the steps that come from AD20 and may differ in a newer version.
6. Cite file and heading: `{{src:m09-compiling.en.md|9.3 Project Options}}`.
7. If the manual has no section, say so, give what is known from the course units, and suggest the student press F1 on
   the dialog or search the Altium documentation. Do not guess a menu path.

## Scripts
None. This skill only reads files and explains how to do X by hand in Altium. The agent's own way (draw, place, route,
import rules, run OutJob) is the actions in AGENTS.md, REPLY FORMAT AND ACTIONS: use them when the student asks you to do it.

## References
- `<repo>/shared/reference/AGENTS.md` (topic index, how to look things up cheaply, how to cite)
- `<repo>/shared/reference/course/ad20-essentials/` (29 modules, m01 to m29, step lists)
- `<repo>/shared/reference/course/altium-education/` (4 units, concepts)
- Not in the course: decoupling, JLC limits, thermal. Say "no course source" and answer from the datasheet or general knowledge.

## Pitfalls
- The manual is AD20. The student may run a newer version (AD24-26): menu names can differ. Say "in AD20 the path
  is ..., newer versions may differ slightly" when you are not sure. Do not invent a path to fill a gap.
- Known drift: in newer versions the Layer Stack Manager is a document tab inside the PCB, the Components panel replaced the
  old Libraries panel, and Preferences gained pages. Treat these as "may differ", not as facts.
- When the student asks you to do it for them, send the AGENTS.md action; do not answer with a click list instead, and
  do not promise an action you do not send.
- Read the section you cite: a heading in the index is not an answer. Quote at most a sentence.
- "Altium will not close" or "the same script error box keeps coming back": a script is paused at a breakpoint after an error.
  Tell the student to open the script editor tab in Altium and press Run (F9) so the script runs to the end, then close Altium.
  The tool stops such a run itself before every step; you never run or resume a script yourself.
- Hebrew answers keep English menu names; do not translate them, because the student clicks the English UI.

## Output
Steps (3-8 lines), then the source as a chip `{{src:<file>|<heading>}}` (AGENTS.md, CITING). If the path is AD20 only, add one line:
"AD20 path; your version may name it differently." Answer in the student's language.
