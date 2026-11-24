# Test run 2026-11-24 (cloud, Linux)

| | |
|---|---|
| Commit | `2c06d9f` (`integrate/e2e-fixes-2026-11-24`) |
| OS | Linux 6.18 (cloud container, no Altium, no pwsh) |
| Python | 3.13.18 (venv; `pip install -r requirements.txt -r requirements-dev.txt`) |
| node | v22.23.5 (on PATH) |
| Command | `python -m pytest -q -rfE -o faulthandler_timeout=600 --junitxml=/tmp/junit.xml < /dev/null` |

## Totals (single-process run, which is the result)

| collected | passed | failed | errors | skipped | xfailed |
|---:|---:|---:|---:|---:|---:|
| 3752 | **3727** | **14** | 0 | 10 | 1 |

Duration: **733 s (12 min 13 s)** from the JUnit XML, 735 s wall time. There was no hang, and the faulthandler never fired.

The totals come from the JUnit XML (`tests=3752 failures=14 errors=0 skipped=11`, where the 11 skips include 1 xfail). With `-q -q`, the log has no final summary line.

Compared with 2026-11-23 (`910740a`): 354 more tests, and 14 failures instead of 3. None of the 3 old failures shows up this time.

### Skipped (10) and xfailed (1)

- `test_altium_live::test_altium_is_found_and_the_bridge_script_stages`: needs Windows (marked `windows`)
- `test_altium_live::test_a_ping_comes_back_from_the_running_script`: needs Windows (marked `windows`)
- `test_dfm_wave3::test_the_known_folder_api_answers_on_windows`: needs Windows (marked `windows`)
- `test_review_fixes_server_lib::test_delete_busy_check_ignores_case_on_windows`: needs Windows (marked `windows`)
- `test_bench_checks_board::test_fixtures_caught_and_quiet_elsewhere`: private incident fixtures (local/bench-fixtures) not present
- `test_bench_checks_schematic::test_catches_6_7_9_and_quiet_elsewhere`: same reason
- `test_bench_checks_parts::test_caught[NOTSET]`, `test_no_false_positives[NOTSET]`: empty parameter set (the same fixtures are missing)
- `test_install_scripts::test_powershell_script_parses`: no pwsh
- `test_schematic_checks::test_real_finished_project_matches_its_board`: real project not available (`PCB_ADVISOR_REAL_PROJECT` not set)
- xfail: `test_live_rp2040_routing::test_the_rp2040_board_routes_every_net_with_no_violation` (known gap: +3V3, +1V1 and +5V are shut in at the QFN by the greedy order)

## 15 slowest test files (single-process run)

| # | file | time (s) | tests |
|---:|---|---:|---:|
| 1 | test_live_stm32_routing | 240.8 | 8 |
| 2 | test_live_rp2040_routing | 101.2 | 3 |
| 3 | test_live_stm32_placed_routing | 62.3 | 3 |
| 4 | test_live_stm32_rebuilt_routing | 29.8 | 2 |
| 5 | test_stm32_board_offline | 29.4 | 9 |
| 6 | test_step_buttons | 29.0 | 81 |
| 7 | test_altium_route | 17.9 | 28 |
| 8 | test_server | 17.7 | 41 |
| 9 | test_altium_netcurrent | 13.1 | 25 |
| 10 | test_four_layer | 11.5 | 42 |
| 11 | test_sources_reference | 11.3 | 30 |
| 12 | test_altium_draw | 10.7 | 74 |
| 13 | test_chat_turns | 8.6 | 12 |
| 14 | test_runlog | 8.4 | 20 |
| 15 | test_chat_followup | 7.2 | 15 |

Together the four `test_live_*` files take 434 s, 59% of the run. No parallel (`-n 4`) run was made this time.

## Failures, classified

Each failure was re-run alone once. 11 fail the same way when run alone. 3 pass alone (group B), and their cause was confirmed. None is timing-dependent, and none is bound to Windows or Altium: every failure reproduces on Linux with no Altium. Nothing was fixed.

### A. Real: product regression (2 tests, one cause)

#### 1–2. `tests/test_stm32_board_offline.py`: **real (routing regression)**

```
tests/test_stm32_board_offline.py:115: test_routing_within_budget_with_zero_violations_and_every_net_accounted
AssertionError: (0.8666666666666667, {'SCL': 'no way from J3-3 to U1-42 (no track of another net to move)', 'SDA': 'no way from J3-2 t...',
                 'IO_PB1': 'no way from U1-19 to R19-1 (after moving IO_PA3, IO_PB11, USB_DM, USB_DP)', ...})
assert 39 >= (45 - 1)

tests/test_stm32_board_offline.py:140: test_ground_is_dropped_to_the_pour_or_routed_by_tracks_with_a_stated_reason
AssertionError: {'net': 'GND', 'mode': None, 'note': 'the bottom layer tracks of other nets cut the pour off from C1-2, C2-2, C20-2, C21-2 ...: the net is routed by tracks'}
assert ('GND' in ['+3V3', 'BOOT0', 'CC1', ...])
```

This is the offline STM32 board: the placer, router and pour, with no Altium. It passed in the 2026-11-23 run. Now only 39 of 45 nets route (budget 44), and GND neither drops to the pour nor routes.

The failure is deterministic (alone, in the file, and in the full run), so it is not timing. A `git bisect` on this file between `910740a` and `2c06d9f` finds the first bad commit: **`71666ef`** "Kiln LTE E4/E5/E6: connector opening from more evidence, antenna rule derived for radio parts, ...". That commit came in by the merge of `claude/awesome-cerf-65tadz` (`528a121`). It changes `layout.opening_guess` (body, pad-row offset, part kind) and `layout.rf_rules`. A different connector opening gives a different placement on the STM32 board, and that placement can no longer be routed. The review fix in `2c06d9f` (opening direction across the pad rows) does not repair it: the test already fails on `77b4768`, and still fails on `2c06d9f`.

### B. Cascade of a test in group C (3 tests)

#### 3–5. `tests/test_chat_turns.py`: `test_stop_returns_the_partial_record_and_applies_no_actions`, `test_idle_timeout_record_carries_the_limit_that_fired`, `test_stop_when_nothing_runs_is_409`: **knock-on, not on their own**

```
test_stop_returns_the_partial_record_...: assert False  (where False = <threading.Event ...: unset>.wait(5))
test_idle_timeout_record_...:            assert 409 == 200
test_stop_when_nothing_runs_is_409:      assert (200 == 409)
```

Each passes alone. The file without `test_progress_while_a_turn_runs_then_idle` passes 11/11. The whole file fails these same 4 tests three times out of three. So these are not flaky. `test_progress_while_a_turn_runs_then_idle` fails on its label assert (item 6) before it reaches `POST /api/chat/stop`. That leaves its fake turn running on the shared server, and the next three tests then see a busy chat. They go green once item 6 is fixed.

### C. Real: tests not updated for changes on this branch (9 tests)

The code changed on purpose in the merged E2E fixes, but these tests still pin the old text or the old behaviour. The product does what the commits say. The tests are stale.

#### 6. `tests/test_chat_turns.py::test_progress_while_a_turn_runs_then_idle`

```
tests/test_chat_turns.py:89: assert [s["label"] for s in p["steps"]] == ["Running calc.py a", "Reading datasheet.pdf"]
AssertionError: assert ['Calculating', ...'Reading the datasheet'] == ['Running calc.py a', 'Reading datasheet.pdf']
```

`8c38add` (E11, E13–E19: "plain progress words") changed `scripts/gateway/events.py`: `calc.py` → "Calculating", and the bare tool names → "Reading a file", "Running a command", and so on. The test still expects the raw command text.

#### 7–10. `tests/test_gateway_stream.py`: `test_parse_stream_json_lines_with_denials_merged_by_id` and `test_stop_and_timeouts_keep_the_partial_text[stopped|idle_timeout|total_timeout-7]`

```
tests/test_gateway_stream.py:165: assert meta["steps"] == ["Running ls /tmp && pwd"]
AssertionError: assert ['Running a command'] == ['Running ls /tmp && pwd']
```

This has the same cause as item 6 (`8c38add`): a Bash step is now labelled "Running a command" (`events.py:160`), not with the command line.

#### 11. `tests/test_proposal_table.py::test_same_three_buttons_everywhere`

```
tests/test_proposal_table.py:63: assert "Approve all" not in BOM and "bom-approve-pending" not in BOM and "batch-decide" not in CHAT
'Approve all' is contained here:  ...part of Approve all: it gets its own card (Delete / Keep) under the list
```

`2c06d9f` ("delete cards apart from Approve all") added a code comment to `ui/js/views/bom.js` (and to `ui/js/chat.js`) that contains the words "Approve all". There is no button: the match is the comment. The test searches the raw source for the string.

#### 12. `tests/test_sheet_fixes_2026_11_21.py::test_the_bridge_sets_the_sheet_the_drawing_assumes_when_it_draws_or_makes_a_skeleton`

```
tests/test_sheet_fixes_2026_11_21.py:182: assert f"Sch.SheetStyle := {draw.SHEET_STYLE};" in PAS
assert 'Sch.SheetStyle := 0;' in "{ PCB advisor <-> Altium bridge ..."
```

`93e89d7` (E7: sheets drawn on A3 when a part does not fit A4) made `SheetSetupStyle(Sch, Style)` in `AdvisorBridge.pas` take the style as an argument (`Sch.SheetStyle := Style;`). The literal `:= 0;` is gone. Also, the grid lines are now `MilsToCoord(100)`, not `MilsToCoord({draw.GRID})`, so the next assert would need the same update.

#### 13. `tests/test_altium_draw_text.py::test_a_section_too_big_for_a_sheet_is_cut_by_parts_into_sheets_that_each_draw`

```
tests/test_altium_draw_text.py:297: assert p["commands"] == [] and p["errors"]
AssertionError: Left contains 226 more items, first extra item: ('DRAWBEGIN', 'd', '0', '1')
```

The test expects `plan_sheet` to refuse a section too big for A4. Since `93e89d7` (E7: "one too-big sheet no longer blocks Draw"), the planner draws the sheet instead, on a larger size.

#### 14. `tests/test_u9_u11.py::test_empty_states_state_the_limits`

```
tests/test_u9_u11.py:96: assert "Altium outputs and the Gerber zip are refused while a part" in out and "production files" not in out
```

`4c51534` (E1/E3/E12: "an unrouted board blocks the outputs") rewrote the limits text in `ui/js/views/outputs.js`. The refusal now covers unrouted nets ("…are refused by the server while the board has unrouted nets…"), so the pinned sentence is gone.

## Summary

- Real, product: 2 tests, one cause. `test_stm32_board_offline` routing and GND pour regressed. First bad commit is `71666ef` (E4/E5/E6, from `claude/awesome-cerf-65tadz`).
- Real, stale tests: 9 (items 6–14). Each one pins text or behaviour that a merged E2E fix changed on purpose (`8c38add`, `93e89d7`, `4c51534`, `2c06d9f`).
- Cascade: 3 (`test_chat_turns`, items 3–5). They pass alone and will go green once item 6 is fixed.
- Platform (Windows/Altium-only): 0. Timing or flaky: 0.
- The 3 failures from 2026-11-23 (`test_doctor`, `test_altium_library`, `test_oscompat`) no longer fail.
