# Friction audit, 2026-11-23

Goal: cut what the system makes the student do, without lowering board quality. Trigger: the Library table asked to "verify the pins of every
diode separately" and to look for a datasheet for each, so the student worked for the table instead of the table helping them.

Branch `claude/friction-audit-e2717f`. Nothing merged, nothing pushed.

## 1. How it was measured

`tools/friction_count.py --home <folder with projects/>` builds the model of every project exactly as the page does (`model.build`) and counts
every place the system waits on the student. It must be pointed at a **copy** (the build stamps legacy accepts and rewrites `bom.json`).
"Before" ran on unmodified HEAD (`git archive 910740a`), "after" on this branch, each on its own fresh copy of the real projects made back to
back, so both saw the same project states (an earlier "before" run on an older snapshot differed, e.g. ceramic-controller, and was discarded).
Counts per project:

| column | what it counts |
| --- | --- |
| pin rows | parts listed as unverified or mismatch (the DFM list, the manufacturing gate): one per BOM line |
| questions | what the student is asked after grouping identical parts |
| own look | questions that need a person's own look (a mismatch) |
| auto | lines the library model verified by itself |
| lib buttons | per-row buttons on the Library table (Verify / Accept / Confirm pins) |
| asks | clicks that clear all of it: pin asks (HEAD: one per part; now: one bulk click plus the own-look rows) + BOM proposals + 1 if there are NC pins + lib buttons |

`asks` is a proxy for effort, not a measure of safety: the one bulk click still accepts ICs on the student's word (the dialog names them).
It is dominated by the Library buttons: at HEAD the table put a **Verify** button on every row whose verify state was not "pass", resistors and
capacitors included, and a second **Confirm pins** button on every open part. The HEAD button count in the script is an emulation of that
JS; checked against the real HEAD Library page of Blinker-555 served from the HEAD archive: 11 buttons (8 Verify, 3 Confirm pins), the script says 11.

## 2. Before / after, per project (copies of the real projects)

| project | pin rows before → after | auto-verified by the library model | lib buttons | asks |
| --- | --- | --- | --- | --- |
| Blinker-555 | 3 → 2 | D1 | 11 → 1 | 14 → 2 |
| Dark-sensor-LED | 4 → 2 | D1, J1 | 7 → 0 | 12 → 2 (1 bulk + NC gate) |
| Live-STM32 | 7 → 4 | J1, D1, D2 | 17 → 0 | 24 → 1 |
| Live-T29b / T29c | 3 → 2 each | D1 | 11 → 1 | 14 → 2 |
| Live-T29 | 0 | | 11 → 1 | 11 → 1 |
| Verify-Sheets | 5 → 3 | J1, D1 | 12 → 0 | 17 → 1 |
| UX-E2E-ESP32C3 | 0 | | 12 → 0 | 13 → 1 (26 NC pins) |
| Regulator-3V3 | 0 | | 7 → 0 | 7 → 0 |
| ceramic-controller | 0 | | 62 → 2 | 62 → 2 |
| led-chaser | 4 → 4 | | 0 | 4 → 1 |
| lte-tracker | 3 → 3 (1 mismatch, own look) | | 1 → 1 | 5 → 4 |
| test | 7 → 7 | | 0 | 7 → 1 |
| **total** | **39 → 29** | | | **204 → 20** |

The diode and LED rows the student complained about are gone from the pin list wherever a library model exists (Blinker D1, Dark-sensor D1,
Live-STM32 D1 and D2, T29b/c D1, Verify-Sheets D1). What is left is, in this order: ICs with no datasheet pin check, headers named by
numbers only, parts with no built EasyEDA library, and one real mismatch (lte-tracker D31).

Grouping of identical parts (section 5) changes no number on these projects: the BOM already merges same-MPN parts into one line
(led-chaser D1..D10 is one line, 13 designators). It fires only for lines that share MPN, footprint and pin pattern under different keys.

Browser check (port 8768, copy of Live-STM32): the Library page shows one line, "4 parts wait for your confirmation U1, U2, U3, J2 · 3 already
matched their library model · Confirm all (4) · Fetch datasheets", and no pin button on any row. Confirm all asks once, naming the three
ICs (nothing but the student's word settles them), then toasts "4 parts confirmed · Undo"; the DFM list and the Outputs banner show the same
line, the outputs gate opens, and Undo revokes all four decisions (4 revoke calls, waiting back to 4). No console errors.
Also checked in the browser: Blinker-555 Library shows the line plus exactly one **Verify** (U1, an IC with a datasheet linked); lte-tracker
Library and DFM show "2 parts wait ... Q3, D30 · 1 part needs your own look D31", D31 with its own **Confirm pins** and not in the bulk, and
the "Pick datasheet" select on the IC row; **Fetch datasheets** ran for real on lte-tracker and Live-STM32 copies (section 6).

## 3. What now clears by itself, and on what evidence

`scripts/pin_model.py`. The library of a project is built from an EasyEDA/LCSC part: `library/easyeda/<LCSC>/lib.kicad_sym` (pin number and
name) and `lib.pretty/*.kicad_mod` (pads), both carrying the LCSC code, plus what Altium gets (`library/build/symbols_spec.txt`,
`footprints_spec.txt`). A diode, LED or connector is verified only when **all** of these agree, each read from a file:

* the raw symbol and the built symbol have the same pins; the raw footprint and the built footprint have the same pads;
* the model is the one of this line's LCSC code and MPN, and the symbol is not generated from the sheet (generated and KiCad symbols agree
  with the sheet by construction, so they decide nothing);
* every wired pin of every part on the line has its number in the symbol and a pad in the footprint, and carries the name the symbol gives it;
* for a diode/LED the two pins have opposite anode/cathode roles, the same as the symbol's.

Disagreement is a **mismatch with a reason** ("D1 pin 1 is the cathode on the sheet, but the library symbol KT-0805W (LCSC C34499) has it as
the anode"), shown on the part's own row and never part of a bulk click. Anything the model cannot decide (numeric-only pin names, ICs, no
library built, model files changed after the build) stays for the student exactly as before.

The verdict is live and memoised on file stat; the audit trail is a `pin_model_check` record by "system" in `library-log.jsonl` written once
and again only when the evidence changes, and the order manifest lists `verified_by_library_model`. The model never overrides a standing
accept, a flagged mismatch or a datasheet table pass (tests cover this).

**What this is not**: it is not a datasheet reading. The server fills the sheet's pin numbers from the built symbol by name, so "agree" says
the sheet uses the model's numbering and A/K naming and that the model belongs to the part's LCSC code. It does not say that the agent put the
anode on the intended net. The UI says "matches the library model of its LCSC part", never "verified against a datasheet".

## 4. What still needs the student, and why (per measured project)

| part | why it waits | can the system settle it |
| --- | --- | --- |
| ICs without a datasheet check (Live-STM32 U1-U3, Dark-sensor Q1/LDR1, Verify-Sheets U1/U2, lte-tracker Q3) | no datasheet linked; the pins are the agent's | yes, in part: all have a supplier datasheet link; "Fetch datasheets" downloads, links and table-checks them (section 6) |
| ICs with a datasheet linked but still unverified (Blinker U1, T29b/c U1, test: 5 parts) | the table check could not pass them | unknown, see proposal 1 |
| numeric headers (Blinker J1, T29b/c J1, Live-STM32 J2, Verify-Sheets J2, test J2) | the symbol names pins "1", "2", ... : nothing to compare | no evidence exists; see proposal 3 |
| projects with no built EasyEDA library (led-chaser, test, lte-tracker D30) | no model behind the part | after Build library |
| lte-tracker D31 | datasheet table conflicts with the sheet | no: own look, own button |
| USB-C unused pins (Dark-sensor 12, UX-E2E 2) and IO pins (UX-E2E 9) | "unlisted/open pin without NC blocks outputs" (binding decision) | 15 of the 38 are named NC by the library; the other 23 are design choices |

## 5. One decision per identical part

`pin_decisions.group_key` = kind, MPN, footprint, LCSC code and the pin pattern of every part (number, name, wired or not). Net names are not
part of it, so five LEDs on five nets are one question and read "D1-D5". Lines with no MPN or no footprint, with parts that differ from each
other, and any mismatch are asked alone. Accepting one line of a group writes a decision for **every** line of the group, each with its own
fingerprint and basis; when one copy's pins change later, only that copy's decision lapses (tested). The `/api/pins/confirm` route groups;
`accept()` called directly does not.

## 6. Bulk line and datasheets

* One line on every page that shows waiting parts (Library, DFM, Outputs banner), driven by `S.pin_decisions.waiting`: "N parts wait for your
  confirmation ... · Confirm all (N)". Per-row buttons remain only where a row needs its own look (a mismatch: **Confirm pins**) or a
  datasheet check can decide (**Verify**, only for a non-passive with a datasheet linked and no pass yet). It reuses `/api/pins/accept-all`.
* Behaviour change to be aware of: Confirm all used to always open a confirm dialog. It now opens one only when the click would skip a real
  check, i.e. for ICs with no datasheet check, and the dialog names those parts. Everything else is done at once with an Undo. The test
  `test_accept_all_is_one_confirm_that_lists_the_parts` in `tests/test_ui_pins.py` was rewritten to this contract.
* Datasheets: `store.fetch_datasheets` downloads every unverified IC's supplier datasheet into the project's `sources/` as `<MPN>.pdf`, links
  it and runs the table check; a failed download is reported and the part waits as before. It runs from "Fetch datasheets"/"Re-check
  datasheets" only, never from the model or a poll (network). Unit-tested with a mocked getter, **and run for real on copies**: lte-tracker
  Q3 (2N7002_215.pdf) and Live-STM32 U1-U3 (STM32F103C8T6, AMS1117-3.3, USBLC6-2SC6) were downloaded, linked and checked. **The
  downloads work, but the pin-table check then verified none of the four** ("... is linked, but its pins could not be checked against it"),
  so the student no longer has to find a datasheet, yet the parts still wait for the one click. The blocker is now the table check
  (proposal 1), not the download.
* The Library "To review / Confirm pins" noise of the complaint is gone: rows no longer carry Verify for resistors, capacitors, diodes or
  connectors.

## 7. Everything else the audit found, ranked

Impact is across the measured projects; risk is to board quality. "Student" means the item removes or changes a real engineering check and
must go through the main session.

1. **ICs with a datasheet linked that stay unverified** (Blinker, T29b/c, test: 8 parts, plus the 4 ICs the real fetch just linked). Impact:
   high, the largest remaining block (12 of the 29 open rows). Risk: none
   (it makes the check pass more, it removes nothing). Fix: find out why the table check does not pass (no pin table found, name aliases,
   page selection) per part; improve `pintable` against the 8 real datasheets. Not done: needs reading each datasheet.
2. **Fetch datasheets automatically, not by button** (8 ICs across 4 projects have a supplier link; the real run fetched 4 of 4). Impact:
   low until proposal 1 is done, since a fetched datasheet does not yet clear the part. Risk: low (a
   failed or wrong document never verifies by itself; the table check must still pass). Fix: call `fetch_datasheets` once after the BOM is
   approved, off the poll path, with the network failure surfaced once. Not done: needs a decision on where network may be called.
3. **Plain headers named by numbers** (5 parts). Impact: medium. Risk: it would remove a gate, so **student**: no tool can verify a 1x4 header
   pin order, the student's own wiring decides it. Fix options: do not gate manufacturing on a connector whose symbol has no pin names
   (keep it listed as information), or keep the gate and the one click. Today it is one click inside Confirm all, no dialog.
4. **Auto-mark NC for pins the library names NC** (15 of the 38 NC-gate pins, all in UX-E2E U1/U3). Impact: low to medium. Risk: low (evidence is the
   model's own pin name), but it touches the binding "open pins need NC" rule, so **student** should agree it. Fix: extend `nc_proposal` so
   the Mark-NC gate pre-selects them and keeps the real design choices (USB-C SBU/DP/DN, IO pins) for the student.
5. **LED orientation heuristic** (anode net vs cathode net, e.g. anode on GND). Impact: medium, quality gain. Risk: none (adds a warning,
   removes nothing). Fix: a net-name check next to the library-model check; closes the "not a datasheet reading" gap for LEDs.
6. **Stale gate wording**: "Open DFM > Unverified parts: verify or fix each, or accept it if you checked it yourself" now sits next to a
   Confirm all button. Impact: low. Risk: none; tests pin the text (`manufacturing_warning`), so it is a separate small change.
7. **Supply and library state**: out-of-stock / "not checked" lines (ceramic-controller 25, led-chaser 24, test 28) and library review rows
   already clear with one button each (Check stock, Build library); nothing to change except running Check stock automatically after the BOM
   is approved. Impact: medium, risk: network again.
8. **ESD arrays and other D-prefixed multi-pin parts** (lte-tracker D30/D31, led-chaser if built): the model returns undecided because they
   are not two-pin A/K diodes; datasheet check or one click. Fine as is.

## 8. Tests and files

* `tests/test_pin_model.py` (16): parsing the real kicad_sym/kicad_mod; agree (LED +/-, A/K in another case, USB-C with named pins);
  disagree (swapped A/K, a pad the model lacks, a renamed connector pin); undecided (numeric header, generated symbol, no library, another
  LCSC, model file changed after the build, a passive); never overrides an accept; audit record written once. Fixtures are the real library
  files of five parts under `tests/fixtures/pin_model/<LCSC>/` (Blinker-555 C84256, Dark-sensor-LED C34499 and C393939, Live-STM32 C99289
  and C32713270).
* `tests/test_pin_waiting.py` (15): grouping and what is never grouped; group accept writes per-line decisions with their own fingerprints
  and one copy lapses alone; waiting summary, bulk and blind list; order manifest lists library-verified parts; Library row buttons; the
  waiting line is wired into the Library, DFM and Outputs views; datasheet fetch (fetched, failed, nothing to fetch); the count script.
* Targeted runs, all green: the two new files, `test_pin_decisions`, `test_unverified_pins`, `test_ui_pins`, `test_pin_downstream`,
  `test_manufacturing_block`, `test_library`, `test_ui_dfm_outputs`, `test_ui_bom`, `test_dfm`, `test_netlist_symbol_pins`,
  `test_altium_library`, `test_outputs_remake`, `test_ui_rules_dfm`. `node --check` passes on the four changed views. The full suite was not
  run (the main session runs it once).
* Changed: `scripts/pin_model.py` (new), `scripts/store.py`, `scripts/pin_decisions.py`, `ui/js/views/{pins,checks,pages,outputs}.js`,
  `ui/styles/checks.css`, `tools/friction_count.py` (new). `libModels` / `libPins` in `pages.js` were not touched (the model-icons session).
