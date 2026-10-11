---
name: altium-help
description: Answers "how do I do X in Altium Designer" with a short step list and a citation from the AD20 Essentials manual or the course units. Use when the student asks how to do something in Altium - panels, shortcuts, new project, schematic capture, annotate, compile, ERC, ECO or update PCB, layers and stackup, board shape, design rules, placement, routing, polygons, DRC, Gerber and OutJob, schematic or PCB libraries, footprints, 3D models, IntLib - or asks what a menu, dialog or error means.
---

# Altium help

Probe marker (used only by `python pcb.py probe`; ignore otherwise): PROBE-ALTIUM-7Q4X

`<repo>` is the repo path given in the WORKSPACE section of the prompt. Paths below are relative to it.

## Steps
1. Open `<repo>/shared/reference/AGENTS.md` and find the topic in its "Topic index". Never read the whole tree.
2. For a procedure, open ONE section of `<repo>/shared/reference/course/ad20-essentials/mNN-<slug>.en.md`
   (grep the heading or a keyword first). These are step-by-step "click here" instructions from Altium Designer 20.
3. For a concept (why, what is it), use the `course/altium-education/` unit named in the index
   (or `course/summaries-he/` when the student writes Hebrew).
4. Answer with a short numbered list of steps, in the student's language. Keep menu and dialog names in English
   exactly as in the manual.
5. Cite file and heading: `{{src:m09-compiling.en.md|9.3 Project Options}}`.

## Pitfalls
- The manual is AD20. The student may run a newer version (AD24-26): menu names can differ. Say "in AD20 the path
  is ..., newer versions may differ slightly" when you are not sure. Do not invent a path to fill a gap.
- If the manual has no section for the question, say so and give what is known; do not guess a menu path.
- Do not drive Altium or promise to; you only explain what the student does.

## Output
Steps (3-8 lines), then one line: `Source: <file> - <heading>`.
