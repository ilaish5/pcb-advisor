# A draft schematic can always be drawn

Branch `claude/draft-schematic-786506`. Two tasks: (1) the Draw button and the agent's `altium.draw_schematic` always draw, with a
clearly named placeholder for any part that has no usable library symbol; (2) the chat no longer contradicts the Outputs banner about
what blocks the manufacturing outputs.

## 1. What the draw does now

| Situation | Before | Now |
|---|---|---|
| Unverified pins, open pins, unfinished BOM | drew | draws (unchanged) |
| No project library file at all | refused: "run library.build first" | draws, every part a placeholder |
| `library.build` fails (button flow) | the chain stopped | the failure is noted, the draw goes on |
| Part has no symbol in the library | refused | placeholder (`no library symbol yet`) |
| Symbol does not fit the netlist pins | refused | placeholder (`library symbol does not match the netlist pins`) |
| Multi-part symbol | refused | placeholder (`multi-part library symbol, draw it by hand`) |
| Library SchLib unreadable | refused | every part a placeholder |
| Footprint in error (`refuse_footprint_errors`) | refused | drawn with its real symbol, listed as a footprint error (see below) |

Good parts are drawn exactly as before: the commands of an all-good sheet are identical to commit 20d85b4 (test
`test_a_sheet_with_no_placeholder_is_planned_exactly_as_before`).

### Placeholder design
- A rectangle from the same generator as library symbols (`partlib_generate.box_symbol`) with **the netlist's pins**: number and name kept
  (names transliterated to ASCII, empty name falls back to the number, invalid or duplicate numbers get the next free integer with a
  warning), every pin `Passive`. The sheet therefore has stubs and net labels on every pin and every net is connected, as for a real part.
- Symbol name `PH_<ref>`, Comment `PLACEHOLDER: <reason>`, designator `<prefix>?` placed as the ref.
- The symbols live in **`<Library>/<Project>-Lib-Draft.SchLib`**, never in the project SchLib (the library build starts from the template and
  `verify_library_files` rejects a symbol that is not ours). It is built before the draw (copy of the template, one symbol per placeholder),
  read back and compared with what was asked, and closed after the run. A failed build is a refusal that changes nothing.
- The sheet's frame note ends with `| DRAFT, placeholder parts: U1, J2 +n`.
- Redraw: the existing replace / `.advisor-backup` flow and every "never wipe a drawing" rule are untouched. Once the project library has
  the real symbol, the next draw picks it and the part is no longer a placeholder.

### Where the draft shows
- **Schematic page**: amber banner "Draft: 3 parts drawn as placeholders, no real library symbol yet (U1, R1, R2). Build the library, then
  draw again to replace them." (`stages.draft_summary`, `S.draft`, `pvDraftNote`). Screenshot: `docs/img/draft-schematic/schematic-page-draft.png`.
- **Stage status**: the Schematic stage is `in_progress` with "Draft: N placeholder parts (...), no real library symbol yet" and next step
  "Build the library, draw again". It is never `clean` while a placeholder exists. (When pin gaps also exist: `issues`, with the count added.)
- **Button / chat result**: "N parts and M nets drawn ... as a DRAFT: 3 parts are placeholders (U1, R1, R2) ..."; a failed library build is
  one of the result's warnings, so the chat chip is amber and carries the cause.
- **State** is replayed from the `draw-schematic` altium-log record (`draft` per sheet, `footprint_errors`); each draw of a sheet replaces the
  earlier state of that sheet, so a redraw with real symbols clears it (`store.draft_parts`). A record of a failed or restored draw
  (`error` / `restored` / `failed`) says nothing, so it can never open the gate. A part that the student drew by hand (the way out of
  "multi-part library symbol, draw it by hand"), or a restored `.advisor-backup`, clears too: when the SchDoc is newer than the draw record
  it is read, and a part that is no longer a `PH_` symbol is dropped; an unreadable SchDoc leaves the part a placeholder (fail closed).

### Manufacturing outputs stay blocked
`store.manufacturing_warning` (the single outputs gate; Outputs banner, stage `gate`, agent context) now also blocks while
`draft_parts` is non-empty: "the schematic is a draft: 3 parts are placeholders (...). Build the library so each placeholder part gets its
real symbol, then draw the schematic again (Schematic page)." A placeholder counts as a blocker exactly as an unverified pin does.

### What is safe for board layout from a draft
Placement reads the netlist and the library manifest, not the SchDoc symbols; placeholders are real SchDoc components. Still, **`place_pcb`
refuses while the schematic is a draft** ("The schematic is still a draft ... Nothing was changed"). Reason (from the code, not tested in
Altium): `place_pcb` stores each part's schematic unique id (`_sch_links`) so that Update PCB finds it instead of adding it twice; a redraw
with `replace` places new components, which carry new ids, and a draft is by definition waiting for that redraw. The same risk exists for any
redraw after placement (not specific to drafts, and not changed here); the refusal only keeps the expected draft redraw from creating it.
The Layout stage says so ("the schematic is still a draft", next step "Build the library, draw again") instead of offering "Place parts".
A footprint in error and a missing library footprint still refuse placement as before. Order: build the library, redraw, place.

### Footprint errors: decision
`refuse_footprint_errors(..., "draw")` blocked the draw because the part could not be made safely. The reason is the **PCB footprint**: the
library build never writes it to the PcbLib (fail closed). A schematic carries no copper, so the draw is not unsafe. The draw therefore
draws such a part with its real symbol (when there is one) and lists it (`footprint_errors` in the result, one warning, stage draft line).
The block stays where the copper is: `place_pcb` and the outputs gate (`footprint_error_text`), unchanged.

### Still blocks the draw (real reasons, unchanged)
Whatever `plan_sheet` reports as an error (structural netlist problems, a ref Altium cannot take, a sheet that does not fit, an alias
conflict), an existing drawing without `replace`, Altium refusing a step (the sheet is closed unsaved, as before), and a draft library that
cannot be built and read back (nothing is drawn). Nothing about a missing or unbuildable *project* library blocks it any more.

### Wiring
Button: `serve._run_step("draw")`. `library.build` is still planned first when no SchLib exists, but its failure is tolerated; a
pre-check (`bridge.draw_needs_library`) inserts a tolerated build when a stale library is the only reason a part would be a placeholder.
Chat: `apply_actions` -> `bridge.draw_schematic` (same function). `runtime/AGENTS.md` (2 lines) and
`runtime/skills/schematic-preview/SKILL.md` (draw step) say: it always draws, placeholders are named, never call the schematic done.

## 2. The chat contradicted the UI about what blocks the outputs

**Cause, two layers.** (a) In the chat session in question the agent's CURRENT STATE carried no stage / gate data (commit 8b6c1a0 was not
in that checkout), so it answered from `lineage.py` / `partlib.py status`, which do not know the gate. (b) Even with `stages`, the gate
reason was cut to 240 characters and nothing told the agent that the Outputs banner's own text is the answer.

**Fix** (commit 34475a5). `agent._summary` carries `outputs_blocked`: the exact text of the Outputs gate, up to 900 characters (head 40 %,
tail 60 %, so both the first blocker and the "how to fix" survive); one `AGENTS.md` line says to answer "what blocks the outputs" from it.
Tests in `tests/test_agent_context.py` (three): the same text as the banner, long text cut at both ends, nothing when not blocked.

## Tests run (local, targeted only)
- `tests/test_draft_schematic.py` (new, 32): placeholder geometry / names / duplicates, plan commands unchanged for good sheets, no library,
  missing symbol, bad symbol, unreadable library, footprint error, redraw replaces the draft, per-sheet replay, outputs gate, stage, model
  key, draft-library read-back failure, `draw_needs_library`, place refuses a draft, failed record never clears, hand-drawn part clears, Layout stage, chat draw after a refused build. Altium is faked there.
- `test_step_buttons` (81), `test_altium_draw*`, `test_altium_bridge`, `test_altium_place`, `test_stages*`, `test_unverified_pins`,
  `test_manufacturing_block`, `test_agent_*`, `test_runtime_pack`, `test_docs`, `test_ui_*` pages / chat / pins / findings / dfm,
  `test_server`, `test_store`: all pass.
- `pytest -m "windows or altium"` (stdin NUL): passes (live tests skip without `PCB_ADVISOR_ALTIUM=1`).
- **Live Altium 26.8**, scratch project in a temp workspace (nothing of a real project touched), through the system's own server and
  buttons (`/api/altium/create`, `/api/altium/draw-schematic`):
  1. no library, 3 parts: all three drawn as `PH_*` with comment `PLACEHOLDER: no library symbol yet`, saved and verified against the
     netlist (every net), the draft SchLib built and read back, `DRAFT, placeholder parts: U1, R1, R2` in the SchDoc; a redraw with
     `replace` replaced it and left an `.advisor-backup`. The Schematic stage, Outputs gate and banner showed the draft.
  2. mixed sheet, project SchLib copied from another built library: R1 and U2 loaded from the project SchLib, U9 (no symbol) from the draft
     SchLib, in one run, verified; stages showed "draft"; then U9 got a real symbol and a redraw replaced the placeholder: no placeholder,
     draft text empty, banner gone.
  Not exercised live: `place_pcb` with a draft (guarded by test), a multi-part symbol, and the build-then-draw order with a real library
  build (a failed build was seen to run and be tolerated).
- A test-isolation bug found on the way: a fake `read_schdoc` patched before `checks.schematic` was first imported stayed bound there
  for later test files; the test file now imports it first and patches both names.

## Files
`scripts/altium/draw.py`, `scripts/altium/bridge.py`, `scripts/store.py`, `scripts/stages.py`, `scripts/serve.py`, `scripts/agent.py`,
`ui/js/core.js`, `ui/js/views/previews.js`, `runtime/AGENTS.md`, `runtime/skills/schematic-preview/SKILL.md`, tests.
