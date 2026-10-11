# Windows verification - 2026-10-11
Commit: b02e9a4   Branch: windows-verify-2026-10-11 (from origin/wip/antigravity-ide-ui)
Environment: Windows 11 Pro 10.0.26300; PowerShell; Python 3.12 (venv; PATH also has 3.12 arm64 and 3.13);
`claude` 2.1.296 at <home>\.local\bin\claude.exe; `agy` not installed; git autocrlf=true;
LongPathsEnabled=0; folder C:\Users\Public\Documents\Altium\pcb-advisor (no OneDrive, no spaces, ASCII).
Repo arrived by `git clone`.

| #  | Result | Notes / output |
|----|--------|----------------|
| A1 | FAIL   | 1 failed, rest passed: `test_the_map_gives_an_absolute_path_once_the_home_has_moved` (see Failures) |
| A2 | PASS   | `0 quotes verified, 0 failed`, no traceback |
| A3 | PASS   | `init` already set up; `list` prints `·` correctly |
| A4 | PASS   | `list > out.txt` -> UTF-8, no UnicodeEncodeError (CRLF line ends, normal for Windows redirect) |
| A5 | PASS   | `git status`: no tracked file changed (only untracked `.venv/`) |
| B1 | PASS   | `python <home>\.local\bin\claude.EXE` |
| B2 | PASS   | allow-list shows `Bash(python scripts/...)`, no `{python}`, no `python3` |
| B3 | PASS   | `claude_code` ready; `antigravity`: "`agy` is not on PATH" |
| B4 | PASS   | `tests/test_oscompat.py`: 6 passed |
| B5 | PASS   | `_CON` and `בדיקה-עברית` created, then deleted |
| C1 | PASS (partial) | `GET /` -> 200. Browser console not inspected |
| C2 | PASS   | Hebrew question answered in readable Hebrew: 0.525 mm (20.7 mil), IPC-2221, no approval prompt |
| C3 | Not run | needs a real datasheet URL; ask the agent in the UI |
| C4 | PASS   | `test:file?.pdf` saved as `test_file_.pdf` (+ `.json` sidecar) |
| C5 | PASS   | 60 lines / Hebrew: the reply used the last line (`1 BANANA-77`) |
| C6 | Not run | `agy` is not installed (known risk stays open) |
| C7 | PASS   | no `png skipped` line in the server log; `blocks.png` exists |

## Failures
**A1** `pytest tests/test_workspace.py::test_the_map_gives_an_absolute_path_once_the_home_has_moved`
```
assert corpus["path"].startswith(str(workspace.REPO))
 'C:/Users/Public/Documents/Altium/pcb-advisor/cascade/*.yaml'.startswith('C:\Users\Public\Documents\Altium\pcb-advisor')
```
Diagnosis: the code is right (paths for the engine use forward slashes, REBUILD-BRIEF section 7); the test compares
with `str(REPO)`, which has backslashes on Windows. Suggested fix: `tests/test_workspace.py:128`, use
`workspace.REPO.as_posix()`. (Also: the cascade is meant to be removed in v2, so this test may go away anyway.)

## Fixes made
None.

## Not run
- C3: needs the user to ask the agent to fetch a datasheet from a URL (or do it in the UI).
- C6: install `agy` (Antigravity), then `python pcb.py config agent.provider antigravity` and repeat C2 and C5.
- Browser console in C1: open http://localhost:8931 and check DevTools.
- Section D (Altium): v2 does not produce an IntLib yet.
- CI on `windows-latest`: not checked (needs the GitHub Actions page).

## Notes
- Chat text posted with curl from Git Bash arrives as `?` (the shell mangles the Hebrew before curl); posting
  UTF-8 bytes from Python works. This is a test-tool issue, not an app one.
