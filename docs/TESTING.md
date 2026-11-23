# Testing

The suite (`tests/`, about 3400 pytest tests) is split by what a test needs.

| Marker    | Needs                                                   | Where it runs                          |
|-----------|---------------------------------------------------------|----------------------------------------|
| (none)    | Python, node (UI tests), git                            | CI on every push and pull request      |
| `windows` | Windows itself (Windows API, case-insensitive folders)  | the Windows PC                         |
| `altium`  | a live Altium Designer answering the bridge             | the Windows PC with Altium, `PCB_ADVISOR_ALTIUM=1` |

`tests/conftest.py` skips `windows` tests where `os.name != "nt"`, and `altium` tests unless `PCB_ADVISOR_ALTIUM=1`,
each with the reason. Nothing that passes on Linux is marked.

## CI (portable set)

```bash
python -m pytest -q -rfE -m "not windows and not altium" -o faulthandler_timeout=600 < /dev/null
```

Runs from `.github/workflows/tests.yml` on ubuntu-latest, Python 3.12, node LTS, on every push and pull request.
Results: the repository's **Actions** tab, workflow **tests**; the junit xml is the run's `pytest-junit` artifact.

## Windows PC (platform set)

```bat
python -m pytest -q -m "windows or altium" < NUL
```

With Altium open, `set PCB_ADVISOR_ALTIUM=1` first, or the `altium` tests are skipped.

## What is marked

| Test                                                                         | Marker              | Why                                       |
|------------------------------------------------------------------------------|---------------------|-------------------------------------------|
| `test_dfm_wave3.py::test_the_known_folder_api_answers_on_windows`            | `windows`           | shell32 `SHGetKnownFolderPath`            |
| `test_review_fixes_server_lib.py::test_delete_busy_check_ignores_case_on_windows` | `windows`      | folder names ignore case only on Windows  |
| `test_altium_live.py` (2 tests: status, PING round trip)                     | `windows`, `altium` | starts the real X2.EXE                    |

Every other bridge test fakes Altium (`subprocess.Popen`, `_running`, `_exe` patched) and runs in CI. The `test_live_*`
routing tests are pure Python (about 11 minutes of the run) and also run in CI.

## Numbers (Linux, Python 3.13, 4 cores, 2026-11-23)

|                                   | collected | ran  | failed | skipped | deselected (platform) | time    |
|-----------------------------------|-----------|------|--------|---------|-----------------------|---------|
| before (`910740a`, no filter)     | 3398      | 3398 | 3      | 8       | 0                     | 11m30s  |
| after (`-m "not windows and not altium"`) | 3401 | 3397 | 0  | 7       | 4                     | 11m15s  |

The 7 skips are not platform skips: private bench fixtures absent (4), `pwsh` absent (1), a known routing gap (1),
`PCB_ADVISOR_REAL_PROJECT` unset (1). GitHub's ubuntu runners have `pwsh`, so that test runs there.

pytest-xdist (`-n auto`) is not used: its workers collect the tests in different orders (some parametrize ids are not
deterministic), so the run stops at collection.
