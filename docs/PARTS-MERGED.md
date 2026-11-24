# One parts table: the BOM and the Library merged

Branch `parts-merged`, from `origin/main` at cae937c. The design is the one the student approved:
`docs/mockups/parts-merged.html`, plus two changes they asked for (a supply card, and two header buttons side by side).

The merged page is the **BOM stage** (`#bom`, nav label "BOM"). Its Next button still goes to Schematic. The mockup's heading
"Parts" was not used, so the heading and the nav label stay the same word.

## The table

One row per BOM line, these columns in this order:

| Column | What it shows | Where it comes from |
|---|---|---|
| Ref | the designators, shortened (`D1–D10`); the full list is the cell's title | `refsLabel` |
| Part | value, with the MPN on the sub-line (the maker when there is no MPN) | `bomRow` |
| Qty | quantity, or `DNP` | `qty(l)` |
| Models | the four icons (symbol, footprint, 3D, pins): green when present, grey when missing, red when they need fixing; a click opens the quick preview | `libIconsHTML(row, {built: false})` |
| Supply | one tag: In stock, Low stock, No stock, Extended fee, Not checked (worst first). A `+1` tag beside it counts supplier risks that are not about stock (the code is another part, no exact MPN match). **A click opens the supply card.** | `bomSupply` |
| Status | one tag from the library build (`libBuildTag`) or the pins (Pins conflict, Verify pins, Accepted risk). Its title is one short sentence. | `bomStatus` |
| (row actions) | Ask in chat, Alternatives (on hover or focus, as before) | unchanged |

A click anywhere else in a row opens the part panel (the inspector), as before.

### The supply card (change 1)

- **What it holds:**
  - the Supply tag and what it means;
  - the LCSC code with its JLC type (Basic / Preferred / Extended);
  - the quantity per board, the unit price (and at which supplier), and the per-board price;
  - when the stock was checked;
  - every supplier's stock and unit price, from `inspStockHTML` (the part panel's own list);
  - any supplier risk in words;
  - Check stock and Alternatives buttons.
- **Opening and closing:**
  - The Supply cell is a real `<button>` (`aria-haspopup="dialog"`, `aria-expanded`), so Tab reaches it and Enter or Space opens it.
  - The keyboard focus moves into the card.
  - **Esc** closes it, and the focus goes back to the cell. Esc is caught before the inspector or the drawer hears it, so one Esc closes only the card.
  - An **outside click** closes it. A click on the same cell closes it; a click on another Supply cell moves it there.
- **Redraws:** the card lives in `<body>`. The 4-second refresh redraws the table, and the card then paints itself again by the new cell, with the new numbers. It follows the table when it scrolls.

### The header (change 2)

- **Check stock** and **Build library** are both always there, side by side. Both are disabled only while they run or when the BOM is empty.
- `viewHeader` takes one `primary`. Build library is the primary and Check stock is the last action just before it, so nothing sits between them.
- When the stage's Next button is the filled one, `viewHeader` turns Build library to the outlined style. That is the existing "one filled button" rule.
- Next stays in its fixed `.vh-next` slot.
- **Menus:**
  - Export menu: BOM (JLC), BOM (generic), and **Library package** (was the Library page's Export).
  - More menu: Compare prices, Import from Altium, and **Prepare library only** (was "Prepare only").
- **Meta line** (unchanged): lines, parts, per-board total, extended fees, not checked, out of stock, footprint error, to verify.

## What moved where

| Was on the Library page | Is now |
|---|---|
| Build library (primary) | BOM header, primary, beside Check stock |
| Prepare only | BOM header, More menu: "Prepare library only" |
| Export (library package) | BOM header, Export menu: "Library package" |
| Build note / error banner (with Create / Link an Altium project) | BOM page, above the table (`bomLibNote`) |
| `pinsWaitingBar()` | BOM page, above the table |
| `libExportHTML()` (install steps after an export) | BOM page, above the table |
| Icon legend (`libLegendHTML`) | BOM page, above the table |
| Models column (`libIconsHTML`) | BOM Models column; the table leaves out the "Built / Not built" word because Status says it |
| Status tag (`libBuildTag` / `PG_LIB`) | BOM Status column (`bomStatus`), also the tag of the part panel's Library section |
| Source column (EasyEDA, vendor zip, ...) | Part panel, Library section: "Source: ..." |
| Long issue text (`libIssues`, raw converter output) | Part panel, Library section only. The table says it in one short sentence (the Status tag's title, and the first line of the panel's Library section). |
| Per-row Verify / Accept / Confirm pins (`libAction`) | Part panel, Library section (Accept, Verify, Confirm pins), and the quick preview's Pins tab (`libAction`, unchanged) |
| Keyboard on library rows | BOM rows already had it (Enter opens the panel, arrows move) |

| Was on the BOM page | Is now |
|---|---|
| Package, LCSC, Stock, Unit, Per board columns | Supply card (and the part panel, as before) |
| Problem tags (`bomProblems`, `bomTags`) | Split: stock problems in Supply, model and pin problems in Status |

## No Library page any more

- The Library nav item is gone (`PAGE_TITLES` has no `library`). The command palette no longer offers it, and the side-sheet picker no longer lists it.
- **Every old way in lands on the BOM.** `PAGE_MOVED = {library: 'bom'}` in `shell.js` covers:
  - `go('library')` and any `data-page="library"` button;
  - a saved sheet `page:library`, for the main sheet or the side sheet (`itemFromRef`);
  - `?page=library` (`boot.js initialMain`).
- I found no hash route (`#library`) in `ui/js`. The UI routes with `?page=`, `?tab=` and the saved sheet.
- **`scripts/serve.py`:** the two step-button texts that said "Library page" now say "BOM page" (`BUTTON_WORDS`, `button_words`). `tests/test_step_buttons.py` was updated to match.
- **Other files:**
  - `core.js` (`select`), `inspector.js` (`INSP_VIEWS`) and `ready.js` (`READY_ALTIUM_VIEWS`) drop `library`.
  - In `kit.js`, the Library title no longer gets a page Next button.
  - `chat.js`: the BOM's starter chips include "Which parts still need models?" from the old Library list.
- **Code removed from `pages.js`:** `libHTML`, `libRow` and the `.lib-tbl` keyboard handler.

## Fits 1280 px with the chat open

I measured this in headless Chromium against the running server. The demo project is a copy of `examples/led-chaser` seeded
with MPNs, stock answers and a library manifest, so every tag shows. It is not committed.

| Window | Nav | Chat | Sheet (scroller) | Table scrollWidth | Part column | Clipped tag cells |
|---|---|---|---|---|---|---|
| 1280 | folded (default at this width) | open, 372 px | 844 | 844 | 307 px | 0 |
| 1280 | expanded | open, 372 px | 668 | 668 | 131 px | 0 |
| 1440 | expanded | open | 828 | 828 | 291 px | 0 |
| 1100 | expanded | open | 830 | 830 | 293 px | 0 |
| 1024 | folded | drawer | 930 | 930 | 393 px | 0 |
| 900 | folded | drawer | 806 | 806 | 269 px | 0 |

No horizontal scroll anywhere. Below 560 px of sheet, the row-action icons hide (the panel has Ask and Alternatives).

## Screenshots (`docs/img/parts-merged/`, 1280×800, device scale 2)

- `bom-1280-chat-open.png`: the page as it opens at 1280 with the chat open (opened by `?page=library`, which landed here).
- `bom-1280-nav-open.png`: the same with the nav expanded, the narrowest case. No Library item in the nav.
- `supply-card.png`: the supply card of U2, opened from the keyboard (Low stock, Extended, LCSC and Mouser).
- `part-panel.png`: a row click opens the part panel. C5's Library section shows the status sentence, the source and the converter's full note.
- `bom-1280-chat-closed.png`: chat closed.

The update toast is hidden in these shots; it comes from the test machine's git state.

## Behaviour checked in the browser

These were checked with Playwright scripts against the running server; the scripts are not committed.

- `?page=library`, `go('library')` and a saved `page:library` all open the BOM stage.
- The supply card:
  - Enter on a Supply cell opens it with the focus inside.
  - Esc closes it and the focus returns to the cell.
  - An outside click closes it.
  - It follows a forced redraw on a scrolled table and stays by its cell.
  - With the part panel open, the first Esc closes only the card and the panel stays.
- A click on the Part cell opens the part panel and no card.
- A click on a Models icon opens the quick preview.
- No page errors in the console.

## Tests

`pytest -q -m "not windows and not altium" < /dev/null`, full run on this branch: **3499 passed, 6 skipped, 1 xfailed, 3 failed**.
None of the 3 failures is in UI code:

- `tests/test_pin_downstream.py::test_order_check_carries_the_accepted_risk_and_writes_a_manifest_beside_the_zip`
  **already fails on `origin/main`** (cae937c, checked with the same command): `{'U1': 'blind'} != {'U1': 'datasheet_page'}`.
  This branch touches no server code it uses.
- `tests/test_agent_retry.py::test_a_neutral_refusal_is_retried_with_round_0_consent_and_stores_its_applied_list` and
  `::test_at_most_two_retry_rounds` failed in the full run and **pass when the file is run alone, three times in a row**
  (`23 passed`). They wait for background chat follow-ups with a fixed timeout (`wait_for(..., 8)`), so they are timing-sensitive under load.
  An earlier full run showed the same kind of flake once in `tests/test_chat_followup.py`, which also passes alone.

All the UI test files pass: `tests/test_ui_*.py`, `tests/test_ui_parts_merged.py` (10 new tests),
`tests/test_pin_waiting.py`, `tests/test_step_buttons.py`, `tests/test_wave4_verify_fixes.py` and the others listed below.

`node --check` passes on every changed JS file: `ui/js/boot.js`, `chat.js`, `core.js`, `kit.js`, `palette.js`, `ready.js`, `shell.js`,
`views/bom.js`, `views/inspector.js`, `views/pages.js`, `views/pins.js`.

**Updated** (they asserted on the two old tables):
- `tests/test_ui_bom.py`: columns, the Supply and Status cells, the Models cell, the narrow-sheet rule, both header actions.
- `tests/test_ui_pages.py`: the BOM header is the library's primary, there is no `libHTML` / `libRow`, and the row actions moved to the panel.
- `tests/test_ui_model_icons.py`: the legend is above the BOM table, the table leaves out the Built word, and the panel keeps the icons.
- `tests/test_ui_component_panel.py`: the panel's Library section has the status sentence, the source and the full notes.
- `tests/test_ui_compact_preview.py`: the page-Next case uses Sources (Library has no page).
- Other tests that asserted on the two old tables:
  - `tests/test_ui_chat.py`, `tests/test_ui_clarity.py` (LCSC code and type are on the supply card now);
  - `tests/test_pin_waiting.py` (the waiting line is on the BOM);
  - `tests/test_usability_fixes.py`;
  - `tests/test_e2e_2026_11_20_ui_drc.py` (the "no Altium project" note is `bomLibNote`);
  - `tests/test_step_buttons.py` ("BOM page" wording);
  - `tests/test_wave4_verify_fixes.py` (the page-Next harness uses Sources instead of Library).
- `tests/test_ui_pins.py` needed no change.

**New:** `tests/test_ui_parts_merged.py`. Several of these run the real functions in node with the real `kit.js`:
- the Supply tag, worst first, for 7 kinds of line (node);
- the Supply cell is a keyboard button and the row still opens the panel (node);
- the supply card's content: every supplier, the code, the type, the prices and the time (node);
- the card closes on Esc and on an outside click, and gives the focus back;
- both header buttons, side by side, when idle, busy and with an empty BOM, with Next in its slot (node);
- the Library page's pieces are above the table, and the converter text appears only in the panel;
- there is no Library nav item, no Library page and no palette entry;
- the redirect: a source check, plus a run of the real `go()` and `itemFromRef()` (node);
- no user-facing "Library page" text is left in `ui/js` or `serve.py`.

## Agent text that still says "Library page"

I did not edit `AGENTS.md` or `runtime/skills/*`, because another branch is changing them. After that merge, these lines should
say "BOM page" (or "the BOM's Models and Status columns"):

- `runtime/skills/project-library/SKILL.md:65`: "The Library page shows the full table: in the chat list only the parts with a gap ..."
- `runtime/skills/part-models/SKILL.md:69-70`: "The Library page shows the full table: in the chat list only the parts with a gap or a mismatch ..."
- `runtime/AGENTS.md:26`: "The tool's pages (BOM, Library, Rules, Schematic, DFM) already show the full tables". Library is no longer a page; it should read "(BOM, Rules, Schematic, DFM)".

Also mentioned, but historical and not instructions: `docs/FRICTION-AUDIT-2026-11-23.md`. The test docstrings that name the
Library page describe what it was.

## Left open

- **The part panel covers the Supply column.** It is an overlay on the right of the sheet, as it always was for the BOM's right-hand columns. While it is open, the Supply tags under it cannot be clicked; the panel itself has the full stock list. Reserving room for the panel would squeeze the table below 1280 px.
- **Tooltip only.** The Status tag's short sentence is its title (hover) in the table; the panel shows it as text. There was no room for a visible third line in a 668 px sheet.
- **The Accepted risk tag.** A line whose pins the student accepted shows "Accepted risk" in Status (warn) instead of "Built". That keeps the old BOM tag's warning. If the student finds it noisy, it can fall back to the build tag.
- **Unused server field.** `S.pin_decisions.waiting.lib_buttons` (`scripts/pin_decisions.py row_buttons`) still counts the per-row buttons of the old Library table. Nothing in the UI reads it now. The quick preview's Pins tab still uses `libAction`. Remove it in a server clean-up if nothing else needs it.
- **No Windows check.** Altium was not needed and I did not run a Windows browser check. Build library, Prepare and Export call the same endpoints as before.
