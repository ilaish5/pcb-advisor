# Wave 2 design (from Fable 5.2 review, 23/11/2026) — W2-0 shim, W2-A, W2-B, W2-C, W3 consent preview

Basis: RCA-2026-11-23, LEDGER-2026-11-23, ARCHITECTURE.md, AGENTS.md. Line numbers are from 1e1d6c1; re-check after Wave 1 merges.
Unverified: `String2Layer('Keep-Out Layer')` inside FPBATCH; whether Altium repour avoids keep-out objects; exact Wave-1 line changes.

## Student decisions (23/11/2026) — override the text below where they differ
1. Legacy `pins_accepted:true` records are grandfathered: they count as accepted (basis "legacy") until the part's pin fingerprint changes. No forced re-confirm.
2. Open pins (no net, not marked NC) and unlisted pins (in the built symbol, absent from the netlist) BLOCK manufacturing outputs. This extends `store.manufacturing_warning`; the W2-A line "must not change store.py gate logic" is overridden for this one addition. Each blocking item offers "Mark NC" and "Ask the agent".
4. Low friction (student, 23/11): the flow must not make the student approve trivia or justify each click. Concretely, replacing W2-B text:
   - No mandatory reason field anywhere ("blind needs reason ≥10 chars" is dropped; reason is optional, basis is recorded automatically).
   - Pin confirm is one click: the modal shows the datasheet page next to the pin table with one "Pins match" button (and an optional "this pin is wrong" per row). No per-pin tick-all requirement.
   - R/C/L/crystal/simple 2-pin parts never ask. Parts whose pins the checker verified from the datasheet never ask.
   - Open/unlisted pins: one "Mark all N as NC" button plus per-pin override, and the agent may propose the NC list in one consent. The gate message lists everything at once, never one item per round.
   - Batch everywhere: "Accept all remaining" for pin decisions with one confirm; already-decided items never ask again; no repeated toasts for the same item.
   - Ask only when the answer changes the board; otherwise pick the safe default and show it as an editable note.
3. Mounting holes and keep-outs as mechanical footprints (H1..H4, KO*) placed via FPBATCH/PLACEFP are approved, with a UI warning that Altium "Update PCB" will offer to remove them.

## 0. Parallelisation
Order: Wave 1 merged → W2-0 shim (serial, small) → A, B, C in parallel → merge A, then B, then C → W3 later.

W2-0 shim (no behaviour change):
- `scripts/ext.py`: registries GET, POST, ACTIONS, MODEL, SUMMARY (lists of callables returning None for "not mine").
- serve.py: one dispatch line in `_get`, in `_post` (after Wave 1's default-deny guard so new routes inherit it), and in the `_apply_actions` else branch.
- `model.py:build`: `for f in ext.MODEL: out.update(f(project, out))`; `agent.py:_summary` same with ext.SUMMARY.
- Empty stubs + tags in ui/index.html: ui/js/views/pins.js, ui/js/views/constraints.js, ui/styles/pins.css, ui/styles/constraints.css.
- Empty modules: scripts/stages.py, board_results.py, pin_decisions.py, constraints.py.

File ownership:
| Stream | Owns (new) | Owns (existing) | Single-site hooks |
|---|---|---|---|
| A | stages.py, board_results.py, tests/test_stages*.py | ui/js/shell.js, ready.js, boot.js, views/previews.js, views/rules.js, views/outputs.js, kit.js, styles/base.css, serve.readiness, serve._run_step/_log_step_end | — |
| B | pin_decisions.py, views/pins.js, pins.css | store.py pins block (2883-3200), skills/verify_part.py, pintable.py, sources.py, order_check.py, skills/render_sheet.py, views/checks.js, views/pages.js, views/inspector.js, viewer.js, views/bom.js, model.list_sources | core.js:327 (verify toast), draw.py:878-893 (mark text), AGENTS.md rules 1, 7, 11 |
| C | constraints.py, checks/requirements.py, checks/drc_origin.py, checks/drc_jlc_map.py, views/constraints.js | altium/layout.py, altium/route.py, altium/bridge.py, partlib.py, partlib_generate.py, altium/lib.py, checks/board.py, skills/export_cpl.py, store.py idea block (1626-2080), requirements.txt | views/idea.js (one call to constraintsHTML()), AGENTS.md one new line + board-review/placement skills |

Cross-stream contracts: A's previews.js calls `typeof boardReqHTML==='function' && boardReqHTML()` (C supplies); A's outputs.js calls `pinRisksHTML()` (B supplies); A's board-log record carries raw `drc.violations[]`, C classifies at read time; A's stages.py reads `out.get('pin_decisions')` / `out.get('requirements')` if present, never imports B/C.

## W2-A Readiness / stage model
Goal: one server-derived stages[]; Altium results persisted; no green dot beside violations.
- New append-only `projects/<p>/board-log.jsonl` (written by serve):
  `{"ts","op":"place|route|drc|outputs","ok","pcb","pcb_sha256","drc":{"rules":{..},"total","unrouted","clean","violations":[..]},"summary":{"placed","routed","failed","tracks","vias","open_nets"},"warnings"}`
- `board_results.record(project, step, res)` maps existing bridge result dicts; hash via `lineage.sha256_file(lineage.linked_pcb(p))`. Called from `serve._log_step_end` and the chat `altium.*` branch via one helper. `board_results.latest(project)` = last per op + `stale`.
- New step `POST /api/altium/drc` via `_run_step` (STEP_LOCK), calls existing `bridge.run_drc` (READ_ONLY) — no Pascal change. "Check board" button.
- `stages.derive(project, model)` in ext.MODEL → `rev` (digest of name/size/mtime_ns of *.jsonl, idea*.json, netlist/*, library manifest, linked PcbDoc — stat only, never hash on poll), `stages:[{id,state(not_started|in_progress|issues|clean|blocked),severity,reason,open,gate{blocked,why,page},next{label,act},primary}]`, `board_check`.
- Rules: idea confirmed→clean, draft→in_progress; bom: today's counts server-side; sch: none→not_started, sheet_gaps/unlisted pins→issues(open), drawn+no gaps→clean; pcb: no place→not_started, placed not routed→in_progress, DRC total>0 or stale→issues, clean+fresh→clean; rules: rule-set match only, counts missing_in_pcb; outputs: blocked iff `store.manufacturing_warning` non-empty; checks(DFM): no report→not_started, never clean.
- `stages.sheets:{plan,altium}` read by all three UI counters.
- Unlisted pins: compare built symbol pins (symbols_spec.txt) with netlist pins → sch.open += unlisted.
- UI: shell.js stageStatus = small mapper from S.stages incl. pcb case, no catch→neutral; rules.js header two rows (rule set / board DRC: N, time, not run, stale); previews.js pvNote seeded from S.board_check; ready.js readyLoad reruns on S.rev change, dismissal key `id:instance` (serve.readiness adds instance=digest(title+fix)); kit.js btn disabled+why → aria-disabled + title + data-why, base.css drops pointer-events:none for [aria-disabled], click handler toasts data-why; Next button per page from stage.next.
- Slices: (1) board-log/record/DRC step; (2) stages+rev, stageStatus reads it; (3) Rules split, Outputs gate; (4) readiness + aria-disabled.
- Tests: stageStatus derives only from S.stages (static + node fixture); outputs blocked ⇔ manufacturing_warning; stale never clean; DFM zero reports never clean; rev changes on append; record round-trip with fake bridge (test_step_buttons).
- Must not change: bridge result dicts, DRC_WATCHED pass criteria, store.py gate logic, altium-log.jsonl shape.

## W2-B Pin decisions
Policy kept: agent never sets verify/accept (`_agent_may_set_library` untouched).
- library-log.jsonl: `{"by":"student","line","changes":{"pin_decision":{"id","status":"accepted|revoked","basis":"datasheet_page|polarity|blind","reason","evidence":[{"doc","sha256","page","pins_checked"}],"fingerprint","ts"}}}`
- `pin_decisions.fingerprint(project,line)` = lineage._digest of sorted (ref,num,name,net) + mpn, package, lcsc (never whole part dict).
- Invalidation derived: `store.pins_status` returns accepted only if status accepted AND fingerprint current; else unverified with "accepted on <date>, pins changed since".
- Legacy `pins_accepted:true` → needs one-click re-confirm (decision pending: re-confirm vs grandfather).
- blind needs reason ≥10 chars.
- API (ext.POST): `/api/pins/accept {line,basis,reason,evidence}` (404 unknown line, idempotent), `/api/pins/revoke {line}`, `GET /api/pins/confirm-data?line=` → pins + docs with candidate_pages (from \f-split text matching pin configuration|pinout|pin description|top view|<package>).
- Confirm-against-page modal (views/pins.js): iframe `/api/source/<name>#page=N` + pin table, checkbox per pin + "this pin is wrong"; Save only when all ticked; flagged → verify:"mismatch" with note. No new PDF dependency. D/LED: basis polarity (A/K vs pad 1/2).
- Downstream: store.bom() adds pin_decision; "Accepted risk" tag in bom.js/inspector.js; `_mark_pins_source` gives "student" for accepted and stops popping J/P/D/LED while gated; render_sheet.py:249 / draw.py:878 mark "pins accepted by student, not verified"; order_check adds pin_decision + counts.accepted_risk; new `exports/<project>_order_manifest.json` beside (not inside) the Gerber zip `{accepted_risks, unverified, board_check, generated}` via lineage.note; JLC BOM CSV unchanged; `pinRisksHTML()` on Outputs/DFM with Revoke.
- Rule 11: gate wins. "R/C/L/crystal need no datasheet. Connectors, diodes, LEDs need none to draw, but the student confirms pin numbers/polarity before manufacturing files." Rule 1 exclusion adds "not pin assignments". Test `test_rules_match_gate` (AGENTS marker vs SIMPLE_PREFIXES).
- Ledger 20: netlist.write for gated part with numeric-only names or pins_source agent → warning "pins of X are a guess: confirm against the datasheet page"; Schematic page "Confirm pins" card. Draw not blocked.
- Verify toast: result + first issue; hide Verify when foregone; show "Attach datasheet / Confirm against page".
- Readability at fetch: `sources.quality` → sidecar `text_quality{pages,chars_per_page,cjk_ratio,lang,score,has_pin_heading}` in get/upload/adopt; poor/zh warning; `model.list_sources` text_state not_read|good|poor|none; viewer.js labels from it; fix text_of caching an empty .txt.
- pintable (time-box 1 day, each with real-text fixture + "swap still = mismatch"): digit-first names (3V3); mixed cells `1,2,11,14,36-53`; "die pad" prose in _EP; header-own-line + 3-line wrapped cell (drop first if late). Not: non-English headings, figure-only parts, BGA alnum.
- Tests: no decision survives pin/net/MPN change (property); revoke re-blocks; agent library.add with pin_decision dropped; existing test_pintable*, test_unverified_pins, test_manufacturing_block green; double accept idempotent.
- Must not change: pintable.check result shape, `_agent_may_set_library`, gate caller list.

## W2-C Physical constraints slice
No new Pascal commands in Wave 2. Holes/keep-outs/slots as generated footprints placed with existing FPBATCH + PLACEFP (spec grammar already carries NPTH pads, slots hole_type 2, TRACK/REGION with layer name; LibFootprintsBatch has per-primitive try/except). PcbTrack not reusable (non-bottom layer → top copper with net).
- Safety: `bridge.capabilities(force=False)` builds a scratch PcbLib in temp (keep-out track, NPTH pad, slot), reads back with lib.read_pcblib, caches `{pas_hash, altium_version, keepout_layer, slot}`; once per script hash before first real build. Fallback if keepout_layer false: Python-only keep-out (placer/router/pour) + finding.
- `idea["constraints"]` `{"version":1,"items":[{id,kind:mounting_hole|edge|keep_apart|keepout|attr,...,by,status:proposed|confirmed}]}`; `store.idea_changes` must compare constraints (save_idea_draft currently drops draft-only keys); `constraints.validate`; agent action `idea.constrain {op,item}` (ext.ACTIONS) writes proposed items, student confirms with Save; target = ref or block id; missing part → finding "constraint has no part"; Idea page `constraintsHTML()` editor.
- Library: `partlib.rf_module(line, fp)` regex (WROOM, MINI-1, WIFI, BLE, LoRa, antenna) + pad-free side → manifest `rf:{antenna_side,keepout_mm,source:"heuristic"}` + keep-out tracks in that footprint's spec; `partlib_generate.mounting_hole(dia)`, `keepout_box(w,h)` for confirmed constraints, manifest key `_mech:<name>` (no BOM line); 3D body check: bbox centre > 0.5 mm from pad/courtyard centre → issue.
- Placement: bridge.place_pcb passes connector_dirs (fixes "270 deg"), new `fixed={ref:(x,y,rot)}`, `constraints=`; `bridge._mechanical_parts` appends H*/KO*; layout.plan_placement: edge reuses connector-edge code with face0=antenna_side; keep_apart hard filter in find() + push in _target; keep-out rects via add_obstacle; export_cpl excludes _mech refs.
- Routing/pour: test route.fixed_shapes includes in_component keep-outs; route_commands pour box clipped to exclude edge keep-out strip (pure Python).
- `checks/requirements.check(project, doc)` → `[{id,status:met|violated|unverifiable,measured,need}]` after place and route; model key `requirements` → stages.
- `checks/drc_origin.classify(violations, doc)` (footprint/router/placement/unknown) + `drc_jlc_map` static map → table `{rule,n,by_origin,jlc_danger,jlc_warning,explained}`; route result adds `new_unwatched` warnings; DRC_WATCHED unchanged.
- Board facts: ext.SUMMARY adds `board_facts{measured_at,stale,size,on_board,edge_parts,holes,keepouts,copper_under_keepout,drc_total,requirements}` or "none measured"; AGENTS.md line: "Where a part sits, clearances, holes, antenna: only from board_facts or a script run this turn; otherwise say planned, never is."
- Tests: every confirmed constraint has a requirements row; layout edge/keep_apart/keepout/hole corner; pour ∩ keep-out = ∅; drc_origin fixtures; CPL has no H refs; draft constraint survives save_idea_draft; static .pas tests unchanged.
- Altium live verification mandatory before "fixed": capabilities smoke; build, place, route on a project with an RF module; no copper under antenna in read-back; DRC.
- Risks: H* parts not in schematic → Altium "Update PCB" ECO offers to remove them (warn in UI); RF heuristic may pick wrong side (show in Library with override).
- Must not change: AdvisorBridge.pas, meaning of keep, route pass criteria, BOM CSV.

## W3 preview — consent-neutral refusals
A refusal is neutral only if: consent check passed this turn (or kind needs none); reason carries a server-assigned code from a frozen set raised as `Fixable(code)` (never inferred from text); fix changes how, not what/whether; retry cannot wipe/replace.
- Neutral codes: `pins.unmapped`, `sheet.too_big`, `prereq.library_not_built`, `prereq.no_project`, `prereq.no_netlist`, `prereq.rules_not_imported` (route only).
- Never neutral: any consent refusal, NEEDS_REPLACE, schematic-not-drawn before place, partial route, manufacturing gate, busy/stopped, parse/cut-off, guard refusals, BridgeError without code.
- Retry rules: FOLLOWUP_MAX_RETRY=2, a round only if previous had ≥1 neutral refusal; whitelist netlist.write, library.build, altium.create_project, altium.import_rules, and draw/place/route only if the same kind passed consent in round 0; consent re-validated with identical inputs (original typed last_user, chat before the main record; follow-up prompt never a consent source); replace/partial refused unless granted in round 0; draw target = round-0 sheet or subset; retry record stores applied list; new student message/Stop/STEP_LOCK cancels; fix AGENTS.md:40/128 contradiction; FOLLOWUP_RETRY prompt text.
- Must stay green unchanged: test_consent_carryover, test_sheet_fixes_2026_11_21, test_agent_guards, test_netlist_symbol_pins, test_autonomy, consent cases in test_altium_draw, test_step_buttons, test_altium_place, test_server, test_no_placeholder_sheets; test_chat_followup non-neutral follow-ups drop every action.
- New tests: neutral set pinned by equality; every negative consent case parametrised through retry still refuses; retry adding replace / out-of-whitelist kind / draw without round-0 draw refused; ≤2 rounds; button message never yields a draw; after retry draw a bare "yes" next turn does not redraw.

## Verification per stream
| Stream | Unit | Browser | Altium |
|---|---|---|---|
| A | stage table, rev, record | dots, Rules, Outputs, aria-disabled | one live "Check board" |
| B | fingerprint, gate, pintable, quality | confirm flow, revoke, tags | optional |
| C | layout, route, requirements, drc_origin | Idea constraints, Layout panel | required |
| W3 | consent matrix | one chained-draw chat | one live draw |
