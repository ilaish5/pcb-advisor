# Red proof of the live metrics on 2dcd691 (27/11)

Run: `run.py --live <server.py up, 2dcd691> --live-project Final-E2E-4L --live-commit 2dcd691 --seed 20261127`, fixture manifest
`423530bb…` verified before and after, both corpus halves present (the hidden half is owner-held). Result: 29 fail, 1 not_run (T-F), 0 error.
`python -I tests/acceptance/live/controls.py`: 11/11 detector controls PASS (each detector goes green on a hand-built pass state).
`gate.py imports`: PASS.

| id | status | measured on 2dcd691 | red on 27/11 (ACCEPTANCE) |
|---|---|---|---|
| W3 | fail | `{"flagged": "0/20", "false_on_twins": 0}` | 0/1 flagged |
| W22 | fail | `{"detected": "0/5", "false_on_twins": 0, "model_only_0_errors": 5}` | 2 missed; 3/3 results without scope |
| W6 | fail | `{"missed": 4, "false_on_twins": 0}` | 1 (PB2) |
| W13 | fail | `{"missed": "8/8", "false_on_twins": 0}` | crystals 2 misses, VDDA 1 miss |
| W37 | fail | `{"reported_with_location": "0/3", "false_on_clean_twin": 0}` | 0/4 |
| W20 | fail | `{"false_conflicts": "1/8", "renames_found": "6/8", "twins_not_verified (info)": 2}` | 1 false conflict (U4) |
| F-E | fail | `{"affirmatives_refused": "18/20", "negations_granted": 0, "announced_before_consent": 28}` | 1 refused yes; 1 pre-announced replacement |
| P0-4 | fail | `5` | S4-40 5-line banner with Windows paths, no title/details; S6-48 float noise; S1-12 fetch error vanished |
| P0-2 | fail | `6` | 20-min silent library build; 5-7 min routes; agent turns with no end message (theme A, 15) |
| P0-1 | fail | `2` | C18 + S1-08 deleted by tool_guard; PlaneClearance skipped silently; a requirement deleted; notes dropped; project created after Stop |
| P0-3 | fail | `211` | green 'Checked' on unverified pins; '51 parts'; green tick over 421 DRC; many unbacked claims |
| T-A | fail | `1` | 15 confusions |
| T-B | fail | `2` | 19 |
| F-B | fail | `3` | >= 6 field disagreements |
| T-C | fail | `12` | 6 |
| T-D | fail | `36` | 14 |
| T-E | fail | `{"leaks": 14, "wide_tables": 6, "messages_over_10_lines": 56}` | 10 |
| T-F | not_run | `null` | 13 |
| T-G | fail | `{"low_contrast_texts": 1268, "net_select_by_name": false}` | 13 |
| T-H | fail | `6` | 7 |
| F-G | fail | `6` | C1, C4, C6, C29, C68 |
| T-I | fail | `1` | 7 |
| T-J | fail | `0` | 2 |
| U1 | fail | `9` | 4 (F1, Y1, Y2, SW1) |
| U5 | fail | `8` | 0 accept controls on DRC; 6 empty reasons |
| U7 | fail | `3` | green with 424 DRC lines and U1 open |
| U8 | fail | `1` | 1 + 1 |
| F-I(e) | fail | `1` | (not stated; F-LIM: JLC sign-in silent) |
| F-I(f) | fail | `1` | deliverables below the fold |
| U6 | fail | `2` | 2 unmarked skips |

## Notes per metric (what the number is, and whether a pass state can exist before the fix)
- **Pass state before the fix: none** for every metric here. The product at 2dcd691 has no evidence records (A10), no conflict, strap,
  rule-class, gm_crit/Tj or Gerber-geometry checks, no ledger, no readiness card. Controls are therefore hand-built pages
  (`controls.py`); synthetic twins (W3, W6, W13, W20, W22, W37) are the negative controls and are quiet on 2dcd691 (0 false flags),
  except W20, where the product itself raises 1 false conflict (the ordering-code-note case, the 27/11 U4 mechanism).
- **U1 = 9** vs 27/11's 4: the 4 empty-status lines (F1, Y1, Y2, SW1) plus 5 lines the product labels "verified" with no W14 evidence
  record (U3, J1, J2, D3, D4). W14 defines verified as needing that record.
- **P0-3 = 211**: 161 green statuses with no A10 record (presence chips included), 49 agent success claims without evidence, 1 staleness
  canary (BOM changed after the outputs, "Current" stayed green).
- **P0-4 = 5/5** non-Altium paths fail (no bold title, no Details, raw "[Errno 111]", auto-hidden toasts, original text not kept).
- **P0-2 = 6**: agent turn and stock check show phase + elapsed but never step k/n or a range; 75 s and 104 s backend silences never
  reported; the stock check under a hanging network never ended within 110 s and left no end message after reload.
- **P0-1 = 2**: a rule left out of the .RUL with no row or log naming it; an agent "drop requirement X" action refused without naming X.
  The guard canary (foreign file removed) was named in chat and log, so it matched (W1's blame is the E-phase metric).
- **U7 = 3**: the dot was amber (2 outputs out of date in the seeded copy), not green as on 27/11; the 3 are the missing readiness-card counts.
- **U8 = 1**: the Layout chip on Outputs. The 51 answers matched to their chat records carry the right engine label; the engine-switch
  canary (Antigravity format) is not built.
- **T-H / F-G = 6**: refusals caused by this machine (no Windows/Altium, no Downloads folder) are recorded and not counted. One of the 6 is
  the "not linked" banner absent on the empty unlinked project's Schematic page.
- **T-B / F-B**: 12 fields drawn from the 12 computable here (40-field list in `corpora/tb_fields.json`); the agent leg and 28 board/Gerber fields are local/E.

## Not built here (to the local Altium phase or the E rerun), and why
| id | why |
|---|---|
| P0-2, P0-4 Altium paths | library build (IntLib locked), Altium closed mid-step, Altium modal, bridge timeout, width rule that cannot fit a pin, route with shorts, outputs with a missing layer: need Altium. |
| P0-1 Altium canaries | rule import skips into Rules6, Altium objects placed then removed: need Altium + PcbDoc reader. |
| U8 engine switch | needs an Antigravity-format fake engine (or the real CLI). |
| W6 pin plan in chat | the 27/11 PB2 plan is agent prose; the live metric checks the netlist leg only. |
| W13 decoupling figure | needs an MCU decoupling-figure corpus mapped to netlist supply pins. |
| W37 (d) | "DRC summary value != Rules6 value" needs a PcbDoc writer / Altium DRC report. |
| T-B agent leg, T-F | need a real agent engine answering scripted / probe questions twice (`ACCEPTANCE_REAL_ENGINE=1`), and a ledger. |
| T-G geometry, 400% zoom | footprint geometry vs PcbLib needs the board session's PcbLib reader; zoom scale needs Altium-rendered sheets. |
| U2, U3, U4, B1, W1, W9, W11, W21, W24-W31, W33, F-A, F-C, F-D, F-H, F-J, F-LIM | Altium as judge or E-level (A12) by ACCEPTANCE. |

## T-F with the real engine (27/11, 14:00 UTC)
`ACCEPTANCE_REAL_ENGINE=1 run.py --only T-F --live-commit 2dcd691 --seed 20261127`: the product's own engine (Claude Code CLI)
answered 10 probe questions twice in fresh chats; the oracle's judge (`claude -p`, outside the product) compared the facts.
**fail**: inconsistent 3/10 (e.g. "the tool cannot change the layer stack" vs "it adds Mid-Layer 1 and 2 via ensure_stack", the
W26 contradiction; "inner layers under the crystals unknown" vs "GND and +3V3 pours on MID1/MID2"), the BOM-quantity canary did not
change the answer, no ledger. 27/11: 13 T-F confusions.

## Full run on the merged main (82eeeec)
`run.py --controls --no-altium --live ... --live-commit 2dcd691 --seed 20261127`: 70 metrics (40 artifact, 30 behaviour):
69 fail, T-F not_run (no real engine in that run), 0 error; all 40 artifact controls PASS. The run says INCOMPLETE only for the
catalogue coverage: 15 ids whose metrics drive Altium and were left out by `--no-altium` (B1 W1 W11 W15 W21 W26 W30 U2 U3 U4
F-A F-C F-D F-F F-LIM).

## Acceptance v1.1: browser / engine legs of F-D, F-F, F-C, F-LIM, W11 (27/11)
Additions only (`metrics/live_fc.py`, `live_fd.py`, `live_ff.py`, `live_flim.py`, `live_w11.py`, `controls_v11.py` 10/10 PASS,
corpus `flim_limits`). `ACCEPTANCE_REAL_ENGINE=1 run.py --live ... --live-commit 2dcd691 --seed 20261127 --only F-D F-F F-C F-LIM W11`
with the visible and hidden corpus halves: 15 legs, 11 fail, 2 pass, 2 not_run (local Altium).

| leg | 2dcd691 | measured | 27/11 red |
|---|---|---|---|
| F-D(a) unverified facts stated as fact | fail | 138 of 164 claim sentences | >= 6 instances |
| F-D(b) same question, two answers (real engine) | fail | 3/10 inconsistent | (same family as T-F) |
| F-D(c) price at a quantity uses another break | fail | 1 ("$46 per board at 5 boards" from the 10 break) | "at 5 boards" used the 10-piece break |
| F-F(a) Confirm pins opens a pin-table page | **pass** | 0 (draw: U5, page 6 is a pin-table page) | C80 opened the wrong page |
| F-F(b) pad count vs pin count explained | fail | 2 (J1 16 vs 18, J2 13 vs 15, unnamed THT pads) | J1 16/18, J2 13/15 unexplained |
| F-C(a) decisions without a ledger | fail | 36 | all |
| F-C(b) Check datasheets after the PDF changed | fail | 1 (U3 BME280.pdf, record keeps the old sha256) | (dead control) |
| F-C(c) "Unknown" where the log has the detail | fail | 2 (board clearance, silk to silk) | 2 groups |
| F-C(d) advice against a served rule | fail | 1 (via-in-pad advice vs "No via in an SMD pad") | 1 |
| F-C(e) dead controls | **pass** | 0 of 72 tried | 3 controls |
| F-LIM(a) non-Altium limits stated where they bite | fail | 5/5 (stm32-pin-table has the control, no ledger item) | 3 silent, 1 false, 11 chat-only |
| F-LIM(b) the 10 Altium limits | not_run | local Altium leg | |
| W11(a) review chip writes files | fail | 3 (idea-draft.json, netlist/Z69.json, project.json) | 2 side effects after Stop |
| W11(b) side effects after Stop | not_run | local Altium leg (Altium project + skeleton) | |
| W11(c) end message names every change | fail | 1 (sheet missing) | |

The two passes are reported as they are, not tuned to fail:
- F-F(a) draws one random line. This draw picked U5, whose page is right. C80's wrong page is not reproduced by this seed.
- F-C(e) uses the "own semantics" rule: a control is dead only if the DOM, URL, dialogs and project files all stay unchanged. Under that rule the 27/11 dead
  controls (D1/D2 rows, Check datasheets) are not dead on 2dcd691: they re-render or call the API. "Check datasheets" does nothing
  useful, and F-C(b) catches that.

Legs left to the local Altium phase:
- W11(b).
- F-LIM(b), which covers 10 limits: planeclearance-import, change-layers, footprint-fix, single-part-place, tent-vias, diffpair-route, draw-ports, compile-erc, keepouts-in-pcblib, incremental-schematic.
- F-D(b) runs only with `ACCEPTANCE_REAL_ENGINE=1`.
