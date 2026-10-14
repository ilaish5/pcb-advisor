---
name: altium-help
description: Answers "how do I do X in Altium Designer" with a short step list and a citation from the AD20 Essentials manual or the course units. Use when the student asks how to do something in Altium - panels, shortcuts, new project, schematic capture, annotate, compile, ERC, ECO or update PCB, layers and stackup, board shape, design rules, placement, routing, polygons, DRC, Gerber and OutJob, schematic or PCB libraries, footprints, 3D models, IntLib - or asks what a menu, dialog or error means (Hebrew - "איך עושים ב-Altium", "איפה התפריט").
---

# Altium help

Probe marker (used only by `python pcb.py probe`; ignore otherwise): PROBE-ALTIUM-7Q4X

`<repo>` is the repo path given in the WORKSPACE section of the prompt. Paths below are relative to it.

## When to use
- "How do I ... in Altium": a procedure, a menu path, a panel, a shortcut, a dialog setting.
- "What does this menu, dialog or error mean?" (compile, ERC, ECO, Footprint Not Found, DRC message).
- A concept question that needs an Altium picture (layers, rules, polygons, libraries).
- Not for: whether a design is good (board-review, schematic-review), manufacturer files (manufacturer-and-dfm).

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
None. This skill only reads files. Do not run Altium, its scripts or its GUI; the student does the clicks.

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
- If the manual has no section for the question, say so and give what is known; do not guess a menu path.
- Do not drive Altium or promise to; you only explain what the student does.
- Read the section you cite: a heading in the index is not an answer. Quote at most a sentence.
- Hebrew answers keep English menu names; do not translate them, because the student clicks the English UI.

## Output
Steps (3-8 lines), then one line: `Source: <file> - <heading>`. If the path is AD20 only, add one line:
"AD20 path; your version may name it differently." Answer in the student's language.
