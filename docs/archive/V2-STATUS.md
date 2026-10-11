# v2 status

Rebuilt from `docs/REBUILD-BRIEF.md` on branch `windows-verify-2026-10-11` (uncommitted when this was written).

## Built and tested

- **Data layer** (`scripts/store.py`): append-only logs (`bom-log`, `supply-log`, `proposals`, `library-log`), the
  derived BOM and library views, proposals with approve/reject, netlist validation against the BOM.
- **Server** (`scripts/serve.py`): the only writer. Actions `idea.propose`, `idea.confirm` (needs a quote from
  the student), `bom.propose` (pending until approved), `netlist.write` (validated), `library.add` (cannot set
  `verify`/`accepted`), `thread.open`. Endpoints for the UI: state, sheet svg, proposal decision, BOM edit,
  library accept/export, skills, sources, sessions, projects, settings.
- **UI** (`ui/index.html`), built from `docs/mock/pcb-advisor-mock.html`: chat with tool list, citation chips,
  diff cards and part context cards; Idea / BOM / Schematic; part drawer; library, sources, skills, settings.
- **Skills** (`scripts/skills/`): check_availability (LCSC live; Mouser with a key), compare_prices, verify_part,
  export_bom (JLC/PCBWay/generic), render_sheet.
- **Seed** `python pcb.py seed` -> `projects/lte-tracker` (the mock's modem sheet as real files; stock and price are
  sample data and say so).
- **Tests**: the whole suite passes on Windows (see the last run in the hand-over message).

## Stubbed or not built

- **Download models, Build part from datasheet**: not built. The Skills page shows them as "Not built yet".
- **Compile the IntLib**: needs Altium on Windows. "Export for Altium" writes a zip with `manifest.json`, a README
  and any files in `projects/<name>/library/`, and lists every part that is not verified and accepted.
- **DigiKey**: not wired up (needs OAuth). **Mouser**: works when `MOUSER_API_KEY` is set. Without a key the
  supplier has no row ("not checked"), never "0 stock".
- **verify_part** is a text heuristic: each pin number must appear near its name in the datasheet text. It needs the
  datasheet file and its text on this machine (`python scripts/sources.py restore`). Otherwise the result is
  "unchecked", and the part is not accepted.
- The course PDFs the brief wants in the shared library are not on this machine; `lte-tracker` lists
  `final-project-guidelines.pdf` as a sidecar only ("not here").
- Block diagram on the Idea tab is a simple left-to-right layout; long chains render small.

## Found while walking the definition of done

- The engine used to run in the workspace home; when `PCB_ADVISOR_HOME` is not the install, `scripts/` was not
  there and the agent could not run its skills. It now runs in the install, with absolute paths to the workspace.
- A part conversation starts with a card that has no `text`; it crashed the turn. Fixed, with a regression test.

## Where the other agent's skills are (please confirm)

The brief says a separate agent built "availability check, price comparison, model download, build part, convert
to Altium, verify". Those are not in this repo. The nearest things on this machine are in the real-project
project, `.claude/skills/`: `altium-part-sourcing` (EasyEDA/KiCad models by LCSC number),
`altium-library-builder` (SchLib/PcbLib/STEP -> IntLib with Altium scripts) and `altium-schematic-builder`.
They drive Altium and are Windows-only, so they could back "Download models" and "Convert & build Altium
library", but not run cross-platform. **Question for you: are those the skills meant? If another repo holds
them, give me the path.** Nothing was copied.

## Open questions

- Should "Check stock" also run on a schedule, or only on demand and when an MPN changes?
- Which manufacturer formats beyond JLC and PCBWay?
- Should an approved proposal that changes a package also invalidate the library entry (today the proposal carries its
  own library entry, which the student still has to accept)?
