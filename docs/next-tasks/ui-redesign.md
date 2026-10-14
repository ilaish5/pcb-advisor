# UI redesign: calm, modern, intuitive

Status: done (2026-10-14). The open items are in PLAN.md section 7, under "UI redesign done". The owner asked for a full redesign of the app. The aim is a clean, modern and pleasant tool that does not tire the eye, with no needless text or shapes. Decisions the owner made:

| Question | Decision |
|---|---|
| Theme | Light and dark. The default follows Windows; a switch lives in Settings. |
| Layout | Navigation on the left, the work in the centre, chat on the right (collapsible). |
| Tabs | Remove the stage stepper and the editor tabs. Keep "side by side": a second pane can show another stage or a document. |
| Colour | Colour only where it means something: status, nets, board layers, selection. Buttons are ink, not blue. |

Reference look: `docs/next-tasks/ui-redesign-mock.png` (light) and `-dark.png`. The design system lives in `ui/styles/base.css` and `ui/js/kit.js`. Read both before you write markup.

## 0. System files and project files (the owner's ground rule)

**System files** are the generic tool, the same for every project, and they go to GitHub:
- `ui/`
- `scripts/`
- `docs/`
- `tests/`
- `config/defaults.json`
- only the general information sources in `shared/` (guides, app notes, Altium reference). These appear in every project.

**Project files** live locally (git-ignored) under `projects/<name>/`: BOM, idea, diagram, chats, checks, exports, and sources, which include the datasheets of that project's parts. They fill the system with one project's data.

In the Sources view:
- the "Shared" filter shows the general sources;
- the "Project" filter shows the project's own sources.

Everything is reachable in two ways:
- **In the UI.**
- **Programmatically.** Through the HTTP API and the scripts, so the agent that drives the tool can read, edit, change and reorder exactly what the user can.

For this redesign that means:
- Every control that changes data calls an existing API endpoint, and the server writes the project files. These are the same endpoints and files the agent uses. A control that needs a new kind of change gets a new endpoint, with a test, not a client-only trick.
- No project data in the browser. `localStorage` holds only UI preferences: the theme, the chat width, the side sheet's content per project, a collapsed section. Losing it loses nothing of the project.
- Agent changes show up in the UI without a reload. The 4 s poll stays, and the views re-render from `S`.
- Nothing project-specific in system files: no part numbers, project names or paths in UI code or copy. Examples in docs are fine.

## 1. Principles

1. **Colour is information.**
   - Neutral surfaces and ink everywhere.
   - Green, amber and red mean ok, needs attention and wrong.
   - Violet means a net. The PCB layer colours are data.
   - The signal blue (`--sig`) is only for selection, focus and links.
   - Never colour something for decoration.
2. **One surface.**
   - The work sits on one sheet (`--sheet`) on a quiet frame (`--frame`). Navigation and chat sit directly on the frame.
   - No cards inside cards, no bordered boxes around tables, no shadows except on floating layers (menus, drawers, toasts, palette).
   - Build structure from spacing, type weight and a single hairline (`--line`).
3. **One primary action per view.**
   - It sits in the view header, styled `btn pri`.
   - Other actions are quiet buttons, a menu (`menu()`), or row actions that appear on hover.
4. **Words only where they help.**
   - No page subtitles that describe the page. No "What to do now" banners. No "How to" boxes that are always open.
   - The header's meta line carries the numbers that matter, and only shows a problem when there is one.
   - Help text goes behind a disclosure, a tooltip (`title`) or the empty state.
5. **The stage list is the spine.**
   - The seven stages are a real sequence, drawn as a PCB trace with one via per stage.
   - The via's colour is the stage's state. This is the one memorable element; everything else stays quiet.
6. **Motion answers the user.** Menus pop (120 ms), drawers slide (180 ms), nothing moves on its own, and `prefers-reduced-motion` is respected (base.css does it globally).
7. **Keyboard first-class.**
   - Ctrl+K opens the command palette.
   - Ctrl+J toggles the chat.
   - Esc closes the top-most overlay.
   - Menus work with the arrow keys, and focus is always visible.

## 2. Design system (ui/styles/base.css, ui/js/kit.js)

**Tokens.** Use only these. No hex in area CSS or JS except data colours: the PCB layers, and user diagram colours that are stored in the project.

| Group | Tokens |
|---|---|
| Surfaces | `--frame`, `--sheet`, `--sunk` (inputs at rest, table heads, code), `--hover`, `--press` |
| Lines | `--line` (hairline), `--line-2` (control border) |
| Text | `--ink`, `--ink-2`, `--ink-3` (muted, still 5:1), `--ink-4` (placeholder, disabled, decoration) |
| Primary button | `--btn`, `--btn-ink`, `--btn-hover` |
| Selection, focus, links | `--sig`, `--sig-soft`, `--sig-line` |
| Meaning | `--ok`, `--warn`, `--bad`, `--net`, each with `-soft` |
| Overlays | `--float`, `--scrim` |
| Canvases | `--canvas`, `--canvas-dot`, `--pcb-bg`, `--pcb-grid`, `--sch-*` |
| Type | `--f-ui` (Atkinson Hyperlegible Next), `--f-mono` (Atkinson Hyperlegible Mono) |
| Sizes | `--t-xs` 11.5, `--t-sm` 12.5, `--t-md` 13.5, `--t-lg` 15, `--t-xl` 19; radii `--r-sm` 6, `--r-md` 8, `--r-lg` 12 |

- The dark values are defined twice: for `prefers-color-scheme: dark` and for `[data-theme="dark"]`.
- `ui/js/theme-boot.js` (in `<head>`) applies the saved choice before the first paint.

**Type.**
- Atkinson Hyperlegible was designed so that 0/O and 1/l/I never look alike, which matters for designators like C10, R1 and IO1.
- Mono is only for designators, MPNs, LCSC codes, nets, file names and code.
- Numbers use the UI font with tabular figures (`.num`).
- Sentence case everywhere. No all-caps labels and no letter-spaced eyebrows.

**Components** (class, then the kit.js helper):
- Buttons `.btn`, `.btn.pri`, `.btn.line`, `.btn.sm`, `.btn.icon`, `.btn.danger`, `.btn.link`: `btn(label, {kind, size, icon, iconAfter, act, title, ...data})`. An icon-only button must have a `title`, which also becomes its aria-label.
- Segmented control `.seg`: `seg(items, value, {act, label})`. Use it instead of several toggling buttons.
- Menu: `menu(trigger, items)`. Items are buttons with `data-act`, so the normal click delegate runs them. kit.js opens and closes menus, places them, handles the keyboard, and exposes `uiBusy()`.
- View header `.vh`: `viewHeader({title, meta, actions, primary, side})`.
  - `metaLine([...])` builds the meta line. It skips zero counts, and tone `warn` or `bad` colours a problem.
  - The header includes the "Side by side" icon (`data-act="side-open"`) unless `side:false`.
- Section: `section(title, body, {meta, actions})` gives a plain heading, not a card.
- Table `.tbl` (add `.rows` when rows are clickable, `.dense` for compact rows):
  - Hairline rows, sticky head on the sheet, `.num` for numbers, `.sub` for a muted second line in a cell.
  - `tr.sel` marks the selected row. `.row-acts` holds actions shown on row hover or focus.
  - No outer border. Wrap the table in `.tbl-wrap` for horizontal scroll.
- `tag(text, tone)` and `dot(tone, title)`. Show a tag only when it says something; a healthy row has no tag.
- Inputs `.in` (`.in.quiet` for inline edits that look like text until hovered) and `.field` (label above, hint below).
- `kv([[key, value], ...])` gives a key/value list, `<dl class="kv">`.
- `.note` (tones `warn`, `bad`, `ok`): one quiet inline message. Not a banner on every page.
- States:
  - `emptyState(title, text, actions)`: one sentence and the action that fills the view.
  - `loadingLine(text)`.
  - `errorLine(what, message, actions)`: "Couldn't load X: reason", plus Retry.
- `.drawer` (`.drawer-h`, `.drawer-b`) is the right-hand inspector inside the sheet.
- `.toast` is for errors and Undo only, with `role="status"`. Success shows in place (a new row, a changed tag) rather than as a toast.
- `.palette` is the command palette.
- `details.disc` is a disclosure for help and for rarely used sections.
- `icon(name)` draws an inline SVG icon (1.6 stroke, 16 px); the names are in `KIT_ICONS`. Never use emoji as icons.

## 3. Copy rules

- Name things the way a student does: "Check stock", not "Check all"; "Export BOM (JLC)"; "Ask". An action keeps one name everywhere. The toast after "Generate OutJob" says "OutJob generated".
- Never explain what is already visible. Delete every `.vhead p` subtitle and the guidance bar.
- Numbers first: "60 to verify", "2 below JLC minimum".
- Errors say what happened and what to do, without apologising.
- Empty states invite the next step.
- No "PCB Advisor:" speaker labels, no "(Enter to send)" hints, and no file-system paths unless the path is the point (then use mono and `title` for the full path).
- The UI is English. Chat text can be any language, so set `dir="auto"` on message bodies and on the composer.

## 4. Shell

```
frame
├── nav (232 px, on the frame)
│   ├── project switcher: mark, name, chevron menu (switch, + New project)
│   ├── stage trace: Idea, BOM, Schematic, Layout, Rules, Outputs, DFM   (via = state, title = why)
│   ├── Library, Sources
│   └── foot: Search (Ctrl K), Settings
├── main: sheet (+ optional side sheet, 8 px gap, resizable)
│   ├── view header (title, meta, actions, primary)
│   ├── view body
│   └── #detail inspector drawer (absolute, right edge of the main sheet)
├── splitter (chat width, persisted)
└── chat (372 px default, on the frame, collapsible to nothing; Ctrl+J or the panel icon brings it back)
```

- **Stage names and ids.** The ids stay the same; only the labels change.
  - `idea` Idea, `bom` BOM, `sch` Schematic, `pcb` Layout, `rules` Rules, `outputs` Outputs, `checks` DFM.
  - Pages: `library` Library, `sources` Sources, `settings` Settings. Skills become a section of Settings and the nav item goes.
- **Stage state.** One function, `stageStatus(id)`, returns `{tone: 'ok'|'warn'|'bad'|'', title, hint}`. It feeds the via colour, the via `title` and an optional muted count.
  - Idea: ok when confirmed.
  - BOM: bad when anything is out of stock or a code is another part; warn when anything is not checked or not verified; ok otherwise.
  - Schematic: ok when sheets exist.
  - Layout: neutral.
  - Rules: bad when any rule is below the JLC minimum, warn when any differs, ok when they match.
  - Outputs: ok when the files exist.
  - DFM: bad for any real issue, warn for findings not yet reviewed, ok when all are reviewed.
- **Navigation.** One way to reach a stage: the trace. Remove the stepper strip (`#whead`), the editor tab bars, drag and drop, Ctrl+Alt moves, and the duplicate nav entries. `go(page, tab)` and `select(key)` stay global, because the test harness drives them.
  - `?page=` and `?tab=` must work on load. Today they are ignored.
  - The nav is not rebuilt while a menu is open (use `uiBusy()`).
  - Every nav click also does `setView('work')` on small screens.
- **Side by side.**
  - `side-open` opens a second sheet to the right. Its own small header has a menu to pick what it shows (any stage or page, or the last opened document), a "Swap" icon, and a close ×.
  - Opening a document (datasheet, export, DFM slice, Altium file) puts it in the side sheet, opening that sheet if needed. The side sheet's state persists in localStorage (try/catch).
  - Previews keyed by global ids (`#schwrap`, `#pcbwrap`) must not appear twice. Either scope lookups to the container, or refuse to show the same preview in both sheets.
- **Inspector.** One right-hand drawer, `#detail`, for the selected part (from BOM, Library, Schematic or Layout) or net. It replaces both the old part drawer and the docked component panel. It has one primary action, "Ask".
- **Chat column.** Width is resizable with one splitter, persisted, and collapses to zero. Remove the nav splitter and the "hide centre" mode.
- **Command palette** (Ctrl+K and the nav Search item) searches:
  - stages and pages;
  - BOM refs and MPNs (opens the inspector);
  - nets (selects the net on the schematic);
  - source files (opens the document);
  - actions: Check stock, Generate OutJob, Export BOM (JLC), Toggle chat, Theme light / dark / system.
  It has arrow keys, Enter, Esc, and up to 8 results per group.
- **Theme.** A Settings switch (System / Light / Dark) uses `setThemePref()` from kit.js.
- **Responsive.**
  - At 1280 px or less, the nav collapses to a 56 px rail: vias and icons only, labels in `title`.
  - At 1100 px or less, the chat overlays the sheet as a drawer instead of taking a column.
  - At 860 px or less, one column with a Work / Chat switch.
- **Render loop.** `render()` must not rebuild what is under an open menu or palette, or an input in progress. Use `uiBusy()` and the existing focus guard.

## 5. Views

### BOM

- **Header**
  - Title "BOM".
  - Meta: lines, parts, $/board; plus "N not checked", "N out of stock", "N to verify" only when non-zero, with tones. "incl. $X extended fees" goes in muted text when above zero, with the $3/type assumption in its `title`.
  - Primary: **Check stock** (merge "Check all" and "Check stock" into one action and one code path).
  - Actions: an Export menu with "BOM (JLC)" and "BOM (generic)", and a ⋯ menu with "Compare prices" and "Import from Altium".
- **Table columns:** Ref, Part (value, with MPN and manufacturer as `.sub`), Package, Qty, Stock, Unit, Per board, and one tag column shown only for a problem.
  - Problem tags: Out of stock, Low stock, Code is another part, Not checked, To verify.
  - Extended, Preferred and Basic library type is a neutral tag.
  - Role, note, description, datasheet and manufacturer move to the inspector.
  - No inputs in the table. Editing happens in the inspector and keeps the same `/api/bom/edit` POST.
  - A row click opens the inspector. Row actions (Ask, Alternatives) appear on hover.
- **Import from Altium.** Show a primary "Import from Altium" in the empty state when a project is linked. Otherwise it is the ⋯ menu item, which opens a small drawer or dialog: CSV select, Preview, Import, and a report shown as a table plus an "Open report" link.
- **Compare prices** and **Alternatives** show in the inspector or a drawer, not as stacked cards above the table.
- **Export** shows a toast with "Download" and refreshes Outputs (fix: the export card only ever rendered on the BOM view, and Outputs never refreshed).
- **Footer:** "Prices at qty 10, excl. shipping. Checked 14 Oct 10:20." When the data is stale (over 24 h), that line turns amber.

### Inspector (part)

- **Header:** refs (mono), MPN, "manufacturer · package". One primary "Ask" (puts a context chip in the composer and focuses it). A ⋯ menu holds "Alternatives", "Show on schematic", "Show on layout" and "Open datasheet".
- **Sections without boxes:**
  - Role and note (editable inline, `.in.quiet`).
  - Where used (sheet and section list, clickable).
  - Nets (clickable: highlight on the schematic; this fixes the dead `data-net` buttons).
  - Stock and price (three lines, the best one in ink, the others muted).
  - Library ("Symbol ✓, Footprint ✓, 3D STEP · to review" on one line, with Verify / Accept as the contextual action).
  - Datasheet.
  - Pins (from `/api/component`, collapsed by default).

### Idea

- **Header:** title "Idea". Primary **Confirm idea**, disabled while proposals are pending or the list is empty. After confirming it becomes "Next: BOM".
- **Requirements:** a flat list on the sheet with no card and no nested scroll.
  - A proposed item shows a "Proposed" tag and inline Accept / Dismiss. Confirmed items show nothing.
  - Edit by clicking the text. Reorder by drag; up and down arrows only for keyboard users (Alt+↑/↓).
  - "+ Add requirement" is a quiet button at the end.
- **Diagram:** fills the rest of the view with no surrounding card.
  - A pending agent proposal becomes a slim bar on the canvas: "The agent suggests changes to the diagram" with Review and Dismiss.
  - diagram.js chrome (rail, popovers, context bar, canvas, grid, selection) uses the tokens through CSS variables.
  - User shape colours are data. In dark mode, map the preset palette (DOMAIN_PRESETS, COLOR_SWATCHES) to dark equivalents at render time; never rewrite stored colours.

### Schematic

- **Header:** title "Schematic". Meta "4 sheets · 558 pins match" (if available). Primary: none, or "Ask" when something is selected.
- **Sheets:** a quiet tab row (`seg`, or underline tabs) above the canvas.
- **Canvas:** fills the sheet. Zoom (−, +, Fit) is a small floating control inside it.
- **Selection:** opens the inspector. Toggle classes only; never re-render the SVG (fixes the zoom reset). Remove the sel-bar.
- **Colours:** follow the `--sch-*` tokens. The server fallback renderer (`preview_sch.py`) must scope its `<style>` to its own SVG (it currently leaks globally) and use the tokens as `var(--sch-*, fallback)`.

### Layout (PCB)

- **Header:** title "Layout". Layers as `seg` with Top, Bottom and Plan (multi-select).
- **Canvas:** `--pcb-bg` in both themes. Layer colours stay as data, but the legend must use the same classes as the drawing (preview_pcb.py duplicates the hex today).
- **Plan:** "N zones · N keep-outs · N critical nets" in the meta line only when a plan exists (fix: the numbers 3/1/2 are invented when there is no plan).
- **Empty:** "No PCB linked", with "Link a project" (goes to Settings).

### Rules

- **Header:** title "Rules". Meta e.g. "JLC preset 7 rules · your board: 2 differ, 1 below JLC minimum". Primary **Download .RUL**; the ⋯ menu holds "Preset only (.RUL)".
- **Diff table:** shows the rows that need attention by default, with a "Show all" toggle. One "Result" tag replaces Status + Verdict: Matches, Stricter, Below JLC minimum, Missing, Extra.
  - Keep the verdict mapping, its fallback and escaping. The existing tests pin `VERDICT[...] || VERDICT.unknown` and `esc(d.detail)`; rewrite those tests if the structure changes, but keep the contract.
- **Disclosures:** "How to import in Altium" (one short ordered list), "JLC preset" (the preset table) and "Extra rules".
- **Calculators:** a second segment (Rules | Calculators). Inputs update the result live, with no Calculate buttons.

### Outputs

- **Header:** title "Outputs". Primary **Generate OutJob**. An Export menu holds "BOM (JLC)", "BOM (generic)" and "Pick and place (CPL)", with the same names as in the BOM view.
- **Files:** Name (opens in the side sheet), Modified, Size (KB/MB), and a download icon on hover. A new file flashes once.
- **Hint:** one line under the table: "Saved in exports/. Copy the OutJob into your Altium project folder." The OutJob contents go in `title`.
- **Removed:** the workflow box and the OutJob banner.

### DFM (final manufacturer checks)

- **Header:** title "DFM". Meta "N findings · N to review · N real issues". Primary **Upload report** (a kind menu inside: Bare board, Assembly, Both).
- **Segment** Bare board | Assembly. Each shows its report select (quiet) and the findings list.
- **Findings list:** grouped by section. Each row shows the check, a level dot, the layer, a Verdict select (Not reviewed, Real issue, False alarm, By design) and an Ask icon.
  - Fix and evidence open in a row expansion.
  - The report's own numbers are read-only text, not inputs.
  - "Add finding" is a quiet button.
  - Saving is silent (no toast per cell).
- **Slices:** a thumbnail strip; a click opens the slice in the side sheet.
- **Status:** "Ready to order" only when no finding is still to review and no real issue is open. Fix: today it says ready as soon as reports exist.

### Library

- **Header:** title "Library". Meta "N parts · N to review". Primary **Export IntLib**.
- **Table:** Part (refs and MPN), Models (symbol, footprint and 3D as three ticks in one cell), Status tag, and one contextual action (Verify, then Accept) as a quiet button. A row click opens the inspector.
- **Install steps:** in a disclosure shown after export.

### Sources

- **Header:** title "Sources". Meta "N files · N missing". Primary is an **Add** menu with "Upload file" and "From URL". "From URL" uses an inline field or a small dialog, not `prompt()`.
- **Filter:** a `seg` with All, Shared and Project.
- **Table:** Name (opens in the side sheet), Type, Size, Used for. Origin, sha256 and the text-extracted flag go into the row `title` and the document header.
- **Missing files:** "N files missing. Run `python scripts/sources.py restore`." with a copy button, shown only when some are missing.

### Settings

- **Sections** (plain headings, no boxes): Appearance (Theme: System / Light / Dark), Agent (engine, model, language with an "עברית" option label, your name), Altium (linked project line "MyBoard.PrjPcb · Change · Unlink", PcbDoc, output folder, sheets, missing documents; the detected install as a select; manual path under Advanced), Memory (disclosure), Skills (a plain read-only list; hide unbuilt ones or tag them "Planned").
- **Saving:** autosave on change, with "Saved" shown next to the field for 2 s. No Save buttons.
- "Reset layout" is a link at the bottom.
- `loadAltium()` failure shows `errorLine` with Retry (today "Loading…" stays forever).

### Documents (side sheet)

- **Header:** the file name, an "Ask" icon, and a ⋯ menu with Download and Open in new tab.
- **PDF:** fills the pane.
- **CSV:** a `.tbl.dense` capped at 500 rows, with "Showing 500 of N".
- **Altium file:** one meta line of counts, then lists (sheets, PCBs, OutJobs). Restore the useful lists from the dead legacy viewer code, then delete that code.
- **Errors:** one error style.

### Chat

- **Header:** the conversation title as a menu (the list shows the last message, not a count; anchors are readable, e.g. "F1" or "DFM: Pad spacing"), a "New chat" icon and a "Hide chat" icon.
- **Messages:**
  - The user's message is a sheet-coloured bubble.
  - Agent text is plain on the frame, with no speaker label and `dir="auto"`.
  - Tool runs are one muted line ("Checked stock · 3 steps", expandable).
  - Source chips are subtle inline links.
  - Remove the stage card. The context card becomes a one-line thread header.
- **Proposal card:**
  - Heading "F1: change the LCSC code", the change in mono (old struck through → new), a muted reason, and Approve (pri) / Reject.
  - It collapses to one line after a decision.
  - A diagram proposal gets its own card. Fix: it renders as "Proposed BOM change" with `[object Object]`.
- **Composer:**
  - One rounded box: an autosizing textarea (`dir="auto"`), a context chip inside the box, and a round send button that becomes Stop while the agent works.
  - Errors show inline with Retry.
  - Suggestions: at most 3, stage-aware, only on an empty thread.
- **`askAbout(ctx)`** is the single entry point for every "Ask" button in the app. `ctx` is `{kind: 'part'|'net'|'file'|'dfm'|'rule'|'zone', id, label, text?}`. It sets the chip, opens the chat if it is hidden, and focuses the composer.

## 6. Bugs fixed by the redesign (from the review)

1. A diagram proposal renders as a BOM diff ("Proposed BOM change", `[object Object]`).
2. Export from Outputs gives no feedback and does not refresh the file list.
3. The project menu closes under the user on every 4 s poll.
4. Split view breaks the Schematic and Layout views in the second group (global ids).
5. `?tab=` and `?page=` are ignored on load; editor state is not per project.
6. The PCB plan shows invented numbers when there is no plan.
7. One click on a schematic part opens three panels; selection re-renders the SVG and resets zoom.
8. The part drawer's net buttons do nothing.
9. "Ask about this" and "Discuss this part" do the same thing.
10. "Check all" and "Check stock" duplicate one action.
11. Settings "Save" and "Save path" both save everything; some fields autosave and some don't; a failed Altium load hangs on "Loading…".
12. The DFM banner says ready as soon as reports exist.
13. There is no textarea autosize and no stop or retry in the composer.
14. Dead code: about 330 lines of legacy viewer after `return`, the `g.diag-block` handlers, and CSS with no elements (`.diag-wrap`, `.blocks`, `.diag-btn`).
15. `preview_sch.py`'s `<style>` leaks into the whole page.

## 7. Contracts to keep

- API URLs and payloads.
- Escaping (`esc(...)` on every value from the server).
- The SVG class and id contracts from the server: `g.part[data-ref]`, `g.net-label`, `g.power-port`, `g.port`, `g.pcb-comp[data-ref]`, `rect.pad[data-net]`, `g.plan-group`, `#pcb-layer-top|bottom|plan`.
- `attachPanHelper` and `initZoomPan`.
- `DiagramEditor.mount` and `updateData`.
- `go(page, tab)` and `select(key)`.
- Every `localStorage` use sits inside try/catch (tests check that each line has `try` within 10 lines above and `catch` within 10 below).
- No Hebrew in UI source files (test_docs). The "עברית" language option label is the one exception if needed: write it as `&#1506;&#1489;&#1512;&#1497;&#1514;`.
- Register click handlers with `onAct(name, fn)` in the area file. A `data-act` name may be renamed only together with its handler and tests.

## 8. Tests

- Static UI tests read the UI through `tests/ui_source.py` (`ui_html()`, `ui_css()`, `ui_js()`, `ui_all()`).
- Tests that pin a real behaviour stay: try/catch, escaping, aria labels, keyboard, API contracts, server SVG contracts.
- Tests that pin the old look (two separators, `.nav.compact`, editor tabs and split classes, tab arrows, 70% scroll, `comp-panel` 320 px, 900 px breakpoint, `.idea-layout`, `<th>Status</th><th>Verdict</th>`) are rewritten by the owner of that area so that they pin the new structure meaningfully. Never just delete a test.
- The full suite `python -m pytest -o addopts= -q` stays green.

## 9. Verification per area

- Screenshot harness: `python <scratchpad>/shoot.py <out-dir> --theme both --views <your views>`. It reports JS errors per view; there must be 0.
- Look at every screenshot in both themes against the principles above:
  - Is any text not needed?
  - Is any box or border not needed?
  - Is there exactly one primary?
  - Is colour only meaningful?
  - Does it hold at 1280 px (`--size 1280x800`)?
- Remove one accessory before calling it done.

## 10. Ownership

| Area | Files |
|---|---|
| Design system | `ui/styles/base.css`, `ui/js/kit.js`, `ui/js/theme-boot.js`, this document |
| Shell + core + palette | `ui/index.html`, `ui/js/core.js`, `ui/js/shell.js`, `ui/js/palette.js`, `ui/styles/shell.css`, `ui/styles/core.css` |
| Chat | `ui/js/chat.js`, `ui/styles/chat.css` |
| BOM | `ui/js/views/bom.js`, `ui/styles/bom.css` |
| Inspector + previews | `ui/js/views/inspector.js`, `ui/js/views/previews.js`, `ui/styles/inspector.css`, `ui/styles/previews.css`, `scripts/preview_pcb.py`, `scripts/preview_sch.py` |
| Idea + diagram | `ui/js/views/idea.js`, `ui/styles/idea.css`, `ui/diagram.js` |
| Rules | `ui/js/views/rules.js`, `ui/styles/rules.css` |
| DFM + Outputs | `ui/js/views/checks.js`, `ui/js/views/outputs.js`, `ui/styles/checks.css`, `ui/styles/outputs.css` |
| Pages + documents | `ui/js/views/pages.js`, `ui/js/viewer.js`, `ui/styles/pages.css`, `ui/styles/viewer.css` |

Each owner also owns the tests for its area.
