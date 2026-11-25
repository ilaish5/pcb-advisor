# Test run 2026-11-25 (cloud, Linux)

| | |
|---|---|
| Commit | `45aa22c` (`claude/dreamy-shannon-43jusy`, which is `integrate/e2e-fixes-2026-11-24` at `2c06d9f` plus 3 fix commits) |
| OS | Linux 6.18 (cloud container, no Altium, no pwsh) |
| Python | 3.13.18 (venv; `pip install -r requirements.txt -r requirements-dev.txt`) |
| node | v22.23.5 (on PATH) |
| Command | `python -m pytest -q -rfE -o faulthandler_timeout=600 --junitxml=/tmp/junit.xml < /dev/null` |

## Totals (single-process run, which is the result)

| collected | passed | failed | errors | skipped | xfailed |
|---:|---:|---:|---:|---:|---:|
| 3752 | **3741** | **0** | 0 | 10 | 1 |

Duration: **746 s (12 min 26 s)** from the JUnit XML, 747 s wall time. The exit code is 0. There was no hang, and the faulthandler never fired.

The totals come from the JUnit XML (`tests=3752 failures=0 errors=0 skipped=11`, where the 11 skips include 1 xfail). With `-q -q`, the log has no final summary line.

Compared with 2026-11-24 (`2c06d9f`, 3727 passed and 14 failed, see `docs/TEST-RUN-2026-11-24-cloud.md`): all 14 failures are gone. The number of tests is the same (3752). The fix commits added no test and removed none.

### What changed since 2026-11-24

| commit | what |
|---|---|
| `7d540ae` | Product: `layout.plan_placement` keeps the plan with the shortest wiring among plans that are equally good otherwise (new `layout.wirelength`). `route.astar` gets `stay_off`: a pad of a net poured on the bottom reaches the pour by a via only and never runs along the pour layer, both for the drop and for the tie. Tests: `test_stm32_board_offline` routing budget raised to 75 s CPU, deadline 80 s (was 45/50), with the reason (the USB-C is now turned the right way, E4, and fans out along the edge). 9 tests updated to the merged E2E fixes. |
| `e8d43fa` | `test_altium_layout::test_connector_opens_out_...`: it checks the opening at whichever edge the placer picks. The shortest-wiring plan puts J1 at the top: 12.4 mm of wiring against 19.2 mm at the bottom. |
| `45aa22c` | Product: the "sheet too big" message names the sizes that were really tried. A forced A4 no longer claims "nor on A3", it says when A3 holds the design, and the split it suggests is for A4 sheets. |

The 14 failures of 2026-11-24 and what closed each:

- `test_stm32_board_offline` (2, real): 45/45 nets with 0 violations, GND dropped to the pour with no track of its own on the bottom. Routing took 55–57 s CPU against the new budget of 75.
- `test_chat_turns` (4, 3 of them a cascade of the first), `test_gateway_stream` (4): the tests expect the plain step words ("Calculating", "Reading the datasheet", "Running a command").
- `test_proposal_table`: checks the BOM code without its comments.
- `test_sheet_fixes_2026_11_21`, `test_altium_draw_text`: per-drawing sheet style (`SheetSetupStyle`), A3 for a section that does not fit A4. The forced-A4 message is checked too.
- `test_u9_u11`: the outputs limits text of the server's gate.

### Skipped (10) and xfailed (1)

These are the same as 2026-11-24.

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
| 1 | test_live_stm32_routing | 235.7 | 8 |
| 2 | test_live_rp2040_routing | 104.2 | 3 |
| 3 | test_live_stm32_placed_routing | 62.2 | 3 |
| 4 | test_stm32_board_offline | 60.6 | 9 |
| 5 | test_live_stm32_rebuilt_routing | 29.2 | 2 |
| 6 | test_step_buttons | 29.0 | 81 |
| 7 | test_server | 17.4 | 41 |
| 8 | test_altium_route | 17.3 | 28 |
| 9 | test_altium_netcurrent | 13.2 | 25 |
| 10 | test_sources_reference | 11.3 | 30 |
| 11 | test_four_layer | 11.3 | 42 |
| 12 | test_altium_draw | 11.0 | 74 |
| 13 | test_runlog | 8.4 | 20 |
| 14 | test_chat_followup | 7.2 | 15 |
| 15 | test_usability_fixes | 6.6 | 24 |

Together the four `test_live_*` files take 432 s, 58% of the run. `test_stm32_board_offline` went from 29 s to 61 s, because it now routes all 45 nets on the correct USB-C orientation instead of stopping at its old 50 s deadline. No parallel (`-n 4`) run was made.

## Failures

None.

## Summary

- 3741 passed, 0 failed, 0 errors, 10 skipped (Windows, pwsh, private fixtures, real project), 1 xfail (known RP2040 gap).
- Platform-bound: 0. Timing or flaky: 0.
- One open item: the offline STM32 routing budget was raised from 45 to 75 s CPU, by the owner's choice. The run used 55–61 s. Speeding up the router (A* and the rip-up rounds take about 80% of the time) would bring it back under the old budget.
