# AGENTS.md - `shared/reference/` (course material the advisor answers from)

General reference for **PCB design course 27525 (Altium Designer)**. It is tracked in git (the repo is private). Vendor datasheets are NOT here:
they go to `shared/datasheets/` (untracked, re-fetched by URL). This file is the single source of truth for the folder (`README.md` only points here).
Read this file first; then open **one** file section from the index below. Never read the whole tree.

## What the advisor uses it for
1. "How do I do X in Altium?" (panels, ECO, rules, OutJob, polygons...) -> short answer + citation. Best source: `course/ad20-essentials/` (step lists).
2. Explain a PCB concept (stackup, rules, routing, vias, impedance, crosstalk, EMI, fab files) -> `course/altium-education/` (English) or `course/summaries-he/` (Hebrew).

## Full map
```
shared/reference/
  AGENTS.md  README.md                 this file / pointer for humans
  _set-aside/                          NOT for answering: duplicates and noise kept for traceability ([INDEX.md](_set-aside/INDEX.md) lists them)
  course/
    lectures/
      lecture3-schematic-simulation.en.md   SPICE simulation in Altium: workflow, 11 analysis types, 5 exercises (condensed from the slides)
      lecture3-schematic-simulation.en.pdf  original slides (25)
    ad20-essentials/                   Altium Designer 20 Essentials exercise manual, English, text extracted per module (29 files, ~290 PDF pages)
      m01..m29-<slug>.en.md            step-by-step "click here" procedures; ## N.M sections, <!-- p.N --> page markers
      ad20-essentials-exercises.pdf    original, 21 MB, copy-protected (see "PDF note"); use the md files instead
    altium-education/                  Altium Academy PCB course text, English, 4 units (118 lessons). Concepts + some Altium steps
      unit1-intro.en.md  unit2-schematics-libraries.en.md  unit3-pcb-layout.en.md  unit4-routing-signal-integrity.en.md   (## [NN] lesson headings)
    summaries-he/                      Hebrew study material (all derived from the Altium Education units)
      cheatsheet-units1-4.he.md        28 KB compact summary, best first stop for a fact or a number in Hebrew
      unit1-intro.he.md  unit2-schematics-libraries.he.md  unit3-pcb-layout.he.md   NotebookLM summaries with definitions, numbers table, confusions, bilingual glossary
      unit4a-routing-traces-vias-impedance.he.md  unit4b-high-speed-buses-emi.he.md  (same format; 4A + 4B replace the old combined unit 4)
      practice-exam-20q.he.md          20 multiple-choice questions with explanations
      quiz-40q.he.md                   the 40 original course-quiz questions (HE + EN) with verified answers
```
Altium parser fixtures (real SchDoc/PcbDoc/libraries) live in `tests/fixtures/altium/`: developer use, not reference material.

Language: `*.he.md` Hebrew (technical terms stay English); everything else English. Hebrew prose in `summaries-he/unit*` spells numbers in words ("שמונה מיל"), so grep the digits in the numbers tables or the cheatsheet.

## Topic index (topic -> where to read)
`E`=`course/altium-education/`, `H`=`course/summaries-he/`, `A`=`course/ad20-essentials/`. "§" = heading number inside the file.
| Topic | Concept / explanation | Altium how-to |
|---|---|---|
| Design documents (schematic, BOM, layout, libraries), PCB vs PCBA, terms | `E/unit1-intro` [04]-[09]; `H/unit1-intro.he` §3-§4; `H/cheatsheet` "יחידה 1" | `A/m02-first-project` §2.2 |
| New project, save, share, Altium 365 | `E/unit1-intro` [11]-[13]; `H/unit1-intro.he` §5 | `A/m02` §2.2-2.3 |
| Altium UI: panels, shortcuts, layouts, undo | - | `A/m01-design-environment` §1.3-1.7; `A/m04-navigating-schematics` |
| Schematic anatomy, nets, power/ground ports, ports, multi-part symbols | `E/unit2` [01]-[08]; `H/unit2-schematics-libraries.he` §3-§4; `H/cheatsheet` "Nets ו-Ports" | `A/m05-schematic-capture`, `A/m06-making-the-connection` |
| Flat vs hierarchical sheets, sheet symbols | `E/unit2` [10]-[12]; `H/unit2` §5 | `A/m10-hierarchy` §10.4-10.6 |
| Schematic best practice (layout of a sheet, reading order, stubs) | `E/unit2` [13], [20], [21] | `A/m07-schematic-updating`, `A/m08-schematic-graphics` |
| Annotation, alignment, locking designators, net colors | - | `A/m07` §7.2-7.6 |
| Compile, ERC, error reporting, connection matrix | - | `A/m09-compiling` §9.3-9.5 |
| Component choice, stock, distributors, lifecycle, MOQ | `E/unit2` [15]-[19], [22]; `H/unit2` §6; `H/cheatsheet` "שרשרת האספקה" | `E/unit2` [17]-[18] (Components panel) |
| Libraries: schematic symbol, footprint, 3D, IntLib, LibPkg | `E/unit1-intro` [09] | `A/m26`..`A/m29` (SchLib, PcbLib, link, integrated lib); 3D body `A/m27` §27.3.6 |
| Transfer to PCB: ECO / Update PCB / Footprint Not Found | `E/unit2` [25]-[28]; `H/cheatsheet` "מעבר ל-Layout" | `A/m11-transfer-to-pcb` §11.3-11.4; `A/m12-updating-the-pcb` |
| Board outline / shape, DXF, board planning | `E/unit2` [28] | `A/m18-shaping-the-pcb` §18.3-18.5 |
| Layer stack, stackup, core/prepreg, plane vs signal, thickness 1.57 mm, copper weight | `E/unit3` [18]-[21], `E/unit2` [26]; `H/unit3-pcb-layout.he` §4; `H/cheatsheet` "Stackup תקני" | `A/m17-pcb-layers` §17.4-17.5 |
| Materials: Dk, Df, Tg, IPC-4101 | `E/unit3` [19], [21]; `H/unit3` §4 | - |
| Design rules (10 categories, safe values 4/8/5 mil, priorities) | `E/unit3` [22]-[26]; `H/unit3` §6, §9; `H/cheatsheet` "קטגוריות Design Rules" | `A/m19-pcb-rules-and-panels` §19.3-19.6 |
| Net classes, rule queries, Find Similar Objects | `E/unit4` [20] | `A/m19` §19.4-19.5; `A/m15-pcb-global-editing` §15.4-15.6 |
| Grids, snap grid | - | `A/m16-pcb-grids` |
| PCB navigation, layers on/off, single-layer mode, net highlight, cross probe | `E/unit3` [10]-[16]; `H/unit3` §7 | `A/m13`, `A/m14-pcb-navigation` §14.3-14.11 |
| Placement order, rooms, which parts first | `E/unit3` [27]-[30]; `H/unit3` §7 | `A/m20-pcb-placement` §20.4 |
| Routing basics: width, 3W rule, 45 degree, polygon vs trace | `E/unit4` [01]-[04]; `H/unit4a` §3 | `A/m21-pcb-routing` §21.4.2-21.4.3 |
| Vias: size, annular ring, types, IPC-6012 classes, teardrops | `E/unit4` [05]-[11] (teardrops in [09]); `H/unit4a` §4; `H/cheatsheet` "Vias" | `A/m21` §21.4.4 |
| Impedance, microstrip vs stripline, differential pairs, length matching | `E/unit4` [12]-[19]; `H/unit4a` §5; `H/cheatsheet` "עכבה" | `E/unit4` [18] (Layer Stack tool), [27] |
| Reference plane, split crossing, ground via, return path | `E/unit4` [19]; `H/unit4a` §6 | - |
| Interactive routing, multi-trace, glossing, ActiveRoute, autorouter | `E/unit4` [23]-[26] | `A/m21` §21.4.3-21.4.9 |
| Polygons, planes, thermal reliefs, pour manager, repour | `E/unit4` [03]; `E/unit3` [20], [25] (Plane rules); `H/unit3` §6 | `A/m22-polygons-and-power-planes` §22.3-22.9 |
| I2C / SPI / UART layout | `E/unit4` [28]-[32]; `H/unit4b` §3 | - |
| High speed = rise time, termination, crosstalk | `E/unit4` [33]-[37]; `H/unit4b` §4-§5 | - |
| EMI/EMC, ESD, filters, split ground | `E/unit4` [38]-[43]; `H/unit4b` §6 | - |
| DRC, violations panel, fixing violations | `E/unit3` [06] | `A/m23-drc` §23.3-23.5; `A/m13` §13.6 |
| Fabrication files: Gerber, drill, pick-and-place, assembly drawings, DFM | `E/unit3` [03], [06]; `H/unit3` §5; `H/cheatsheet` "קבצי ייצור" | `A/m25-fabrication-files` §25.4 (OutJob, containers, Generate content) |
| BOM export | `E/unit1-intro` [08] | `A/m25` §25.3; `A/m08` ; `A/m24` (BOM table) |
| Draftsman (fab/assembly drawings) | - | `A/m24-draftsman` |
| Schematic PDF / Smart PDF, sheet numbering | - | `A/m08` §8.4-8.5 |
| SPICE simulation, analyses, exercises | `course/lectures/lecture3-schematic-simulation.en.md` | same file §2 |
| Glossary EN<->HE | `H/unit1-intro.he` §10, `H/unit2` §11, `H/unit3` §12, `H/unit4a` §10, `H/unit4b` §10 | - |
| Self-test / exam practice | `H/practice-exam-20q.he.md`, `H/quiz-40q.he.md` | - |

**Not covered anywhere in this folder** (answer from general knowledge or the datasheet and say there is no course source): decoupling/bypass capacitors and placement,
power integrity beyond planes, thermal design, JLCPCB-specific limits and DFM tools, IPC-356, 4+ layer fab trade-offs, firmware/programming connectors. Do not invent a citation.

## How to look things up cheaply
1. Match the question to the index row. Open that file with `grep -n "^#" <file>` first (headings only), then read just the matching section (`sed -n 'START,ENDp'` or a Read with offset/limit).
2. Quick facts and numbers: `grep -n -i "<term>" course/summaries-he/cheatsheet-units1-4.he.md` (28 KB) before anything bigger.
3. Altium steps (AD20 manual): `grep -n -i "<menu or panel name>" course/ad20-essentials/*.md` (e.g. `"Output Job"`, `"Repour"`, `"Rule Priorities"`), then read that `##` section only. Menu paths are written `File » New » Project`.
4. Hebrew term -> search the Hebrew file; English term -> `*.en.md`. Technical terms are English in both.
5. Sizes for planning: altium-education units 25-112 KB each, ad20-essentials modules 2-15 KB each, cheatsheet 28 KB, Hebrew unit files 21-29 KB. Prefer ad20-essentials modules (small) for how-to.
6. Never open `.pdf` for answers. The md files hold the text.

## How to cite
`path-from-reference-root` + heading, e.g. `course/ad20-essentials/m19-pcb-rules-and-panels.en.md § 19.3.2 Rule Priorities` or
`course/altium-education/unit4-routing-signal-integrity.en.md § [17] Calculating Characteristic Impedance and Trace Width`. AD20 files also carry a page: `(PDF p.187)` from the `<!-- p.N -->` marker.
Cite the file you actually read. Say when a menu name comes from AD20 (the course version) and may differ in the student's newer Altium.

## Caveats
- Altium steps are **AD20**. Newer versions rename panels and move the Layer Stack Manager; say so when unsure.
- `E/unit3` [14] says assembly layers define paste/solder mask apertures. That is loose: in Altium those are the Top/Bottom Solder and Paste layers; assembly layers are mechanical layers for drawings.
- The lecture-3 slide header says course no. 50177 (different from 27525).
- Hebrew unit files are AI-generated summaries (NotebookLM). Where they disagree with `altium-education/`, the English course text wins; the cheatsheet matches it.
- `E/unit1..4` have no images; phrases like "in the image below" point to nothing.
- PDF note: the AD20 PDF opens with an empty password but is AES-encrypted. pypdf needs an AES backend: `cryptography` does not build on Windows ARM64, `pycryptodome` works instead. Not needed for answers, since the text is extracted.

## Rules for editing, adding and organizing
- New general material (course notes, Altium docs, standards you may redistribute): put it under `course/<kind>/` or a new top-level folder here, **in the same change update the Full map and the Topic index above**.
- Names: English, kebab-case, short; language in the name (`*.he.md`, `*.en.md`); numbered series as `mNN-`, `unitN-`.
- Text only in `.md`. One topic per file; headings must be stable (they are the citation anchors). Add a one-line `> Source:` note saying where it came from and what was trimmed.
- Trim noise before adding: podcast or video scripts, "listen now" sections, voice drills, repeated summaries, ads, link lists without content. Keep facts, numbers, procedures, common mistakes, bilingual glossary.
- Do not delete. Unwanted or duplicate files go to `_set-aside/<original relative path>` and get one line in [`_set-aside/INDEX.md`](_set-aside/INDEX.md).
- No vendor datasheets here (`shared/datasheets/`). No student project files (they live in `projects/`, untracked).
- Only text lives here, plus the original PDFs next to their extracted text. CAD files (SchDoc, PcbDoc, libraries) are test fixtures and go to `tests/fixtures/altium/`, not here.
- Only this one `AGENTS.md` exists in the tree; put extra detail in a plain file (e.g. `INDEX.md`) and link it from here.
- Student-facing answers must come from this folder or be marked as general knowledge; do not paste long passages, quote a sentence and cite it.
