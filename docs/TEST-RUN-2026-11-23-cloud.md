# Test run 2026-11-23 (cloud, Linux)

| | |
|---|---|
| Commit | `910740a` (`phase0-correctness`) |
| OS | Linux 6.18 (cloud container, no Altium, no pwsh) |
| Python | 3.12.3 (venv; `pip install -r requirements.txt -r requirements-dev.txt`) |
| node | v22.23.5 (on PATH) |
| Command | `python -m pytest -q -rfE -o faulthandler_timeout=600 --junitxml=/tmp/junit.xml < /dev/null` |

## Totals (single-process run, which is the result)

| collected | passed | failed | errors | skipped | xfailed |
|---:|---:|---:|---:|---:|---:|
| 3398 | **3387** | **3** | 0 | 7 | 1 |

Duration: **790 s (13 min 10 s)**. No hang, and the faulthandler never fired.

The `pytest.ini` `addopts = -q` plus the command's `-q` makes `-qq`, so the log has no final summary line. The totals above come from the JUnit XML.

### Skipped (7) and xfailed (1)

- `test_bench_checks_board::test_fixtures_caught_and_quiet_elsewhere`: private incident fixtures (local/bench-fixtures) not present
- `test_bench_checks_schematic::test_catches_6_7_9_and_quiet_elsewhere`: same reason
- `test_bench_checks_parts::test_caught[NOTSET]`, `test_no_false_positives[NOTSET]`: empty parameter set (the same fixtures are missing)
- `test_dfm_wave3::test_the_known_folder_api_answers_on_windows`: Windows Known Folder API
- `test_install_scripts::test_powershell_script_parses`: no pwsh
- `test_schematic_checks::test_real_finished_project_matches_its_board`: `PCB_ADVISOR_REAL_PROJECT` not set
- xfail: `test_live_rp2040_routing::test_the_rp2040_board_routes_every_net_with_no_violation` (known gap: +3V3, +1V1 and +5V are shut in at the QFN)

### Parallel run (`-n 4`, speed only)

- `pytest-xdist` installed cleanly.
- `-n 4` fails at collection, because the workers collect different test ids. `tests/test_drc_summary_time.py:20` parametrizes with `store.now_ms()`, so each worker gets a different id (`[2026-11-23T21:49:03.587]` vs `[...03.717]`).
- With `--deselect tests/test_drc_summary_time.py::test_drc_summary_reads_the_servers_time_stamp` (3 tests), `-n 4` took **543 s** and showed the same 3 failures. The wall time is dominated by `test_live_stm32_routing` (about 300 s, in one worker).
- To use xdist, give that parametrize a fixed id (for example `ids=["now", "ms-string", "none"]`) or compute the time stamp inside the test.

## 15 slowest test files (single-process run)

| # | file | time (s) | tests |
|---:|---|---:|---:|
| 1 | test_live_stm32_routing | 303.1 | 8 |
| 2 | test_live_rp2040_routing | 90.4 | 3 |
| 3 | test_live_stm32_placed_routing | 74.4 | 3 |
| 4 | test_live_stm32_rebuilt_routing | 35.7 | 2 |
| 5 | test_step_buttons | 28.7 | 79 |
| 6 | test_stm32_board_offline | 23.6 | 9 |
| 7 | test_altium_route | 21.7 | 28 |
| 8 | test_server | 18.2 | 41 |
| 9 | test_altium_netcurrent | 16.4 | 25 |
| 10 | test_sources_reference | 11.9 | 30 |
| 11 | test_ui_markdown | 9.6 | 13 |
| 12 | test_runlog | 8.8 | 20 |
| 13 | test_chat_followup | 7.5 | 15 |
| 14 | test_usability_fixes | 6.7 | 24 |
| 15 | test_agent_retry | 6.0 | 23 |

The four `test_live_*` files take 504 s together, 64% of the run.

## Failures, classified

Each test was rerun alone once and failed the same way, so none is flaky. All 3 fail the same way in the `-n 4` run too.

### 1. `tests/test_doctor.py::test_which_finds_the_installer_folder_when_path_is_stale`: **real (test bug, non-Windows branch)**

```
tests/test_doctor.py:258: agy.parent.mkdir(parents=True)
FileExistsError: [Errno 17] File exists: '.../test_which_finds_the_installer0/.local/bin'
```

The test has its own non-Windows branch. On that branch both `claude` and `agy` live in `~/.local/bin`. The test creates that folder for `claude` and then calls `mkdir(parents=True)` again for `agy`, without `exist_ok=True`. So the test's Linux/macOS path can never pass. The product code (`oscompat.which`) is not reached at this point.

Fix (test only): `agy.parent.mkdir(parents=True, exist_ok=True)`.

### 2. `tests/test_altium_library.py::test_the_build_leaves_a_project_that_already_lists_the_intlib_alone`: **platform**

```
tests/test_altium_library.py:409: assert "ADDDOC" not in stub.names() and "SAVEPRJ" not in stub.names()
AssertionError: assert ('ADDDOC' not in ['LIBCLOSE', 'FPBATCH', 'FPREMOVE', 'SAVELIB', ...])
```

The PrjPcb lists `LTE-LIB/LTE-LIB.intlib`, but the built file is `lte-Lib.IntLib`. `bridge._doc_key` (`scripts/altium/bridge.py:589`) compares them through `os.path.normcase`. That ignores case on Windows but does nothing on POSIX, so on Linux the IntLib is "not in the project" and gets added again. The match is right for Windows/Altium, where paths are case-insensitive, and Altium only runs there. The test assumes Windows case folding.

If it should hold on every OS: either use `.casefold()` in `_doc_key` (the docstring already says "case ignored"), or skip the test when `os.name != "nt"`.

### 3. `tests/test_oscompat.py::test_a_path_with_a_space_becomes_its_short_space_free_form`: **platform**

```
tests/test_oscompat.py:53: assert oscompat.command_path(r"C:\Users\John Smith\pcb-advisor") == "C:/Users/JOHNSM~1/pcb-advisor"
AssertionError: assert 'C:\\Users\\JOHNSM~1\\pcb-advisor' == 'C:/Users/JOHNSM~1/pcb-advisor'
```

`command_path` uses `pathlib.PurePath(...).as_posix()`, which is `PurePosixPath` on Linux and leaves backslashes alone. The test feeds in a Windows path and a mocked 8.3 short form. On Linux the real `_short_path` always returns `None`, so this code path cannot run outside Windows.

If it should hold on every OS: skip the test when `os.name != "nt"`, or build the expectation with `PureWindowsPath`.

## Summary

- Real: 1 (`test_doctor::test_which_finds_the_installer_folder_when_path_is_stale`, a test bug)
- Platform: 2 (`test_altium_library::...already_lists_the_intlib_alone`, `test_oscompat::...short_space_free_form`)
- Flaky: 0
- Side finding: a collection-time `now_ms()` parametrize in `test_drc_summary_time.py` blocks `pytest-xdist`.
