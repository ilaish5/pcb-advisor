# Windows handoff: verify PCB Advisor on Windows

For the agent working on Ilai's **Windows** machine. The app is developed on
macOS. Most students will run it on Windows, because Altium only runs there.
Your job is to **verify** that this version works on Windows. Fixing it is not
your job.

---

## 1. Rules

- **Verify, record, report.** For every check, record the exact command, the
  exact output (trimmed), and PASS / FAIL / BLOCKED.
- **Fix only trivial platform bugs, and only in `scripts/oscompat.py`** or at
  the single call site that should use it. Anything else goes in the report as
  FAIL, with the error and your best diagnosis.
- **No refactors, no feature work.** Do not change app behaviour or the UI.
- **Git:** work on a branch named `windows-verify-<date>`. Commit your report
  and any trivial fixes there. Never commit to the main branch.
- **Do not commit course PDFs or vendor datasheets.**
- If a check needs Ilai (logging in to the Claude CLI, opening Altium), stop at
  that check and say exactly what he must do.

---

## 2. What changed for Windows (what you are verifying)

All of it lives in `scripts/oscompat.py`. See the "Windows and macOS" section
of `README.md`.

1. **UTF-8 for child processes.** Every child process (the engine CLI, and
   `pdftotext`) is spoken to in UTF-8, and the engine's own Python children get
   `PYTHONUTF8=1`. Before this, Hebrew prompts broke under cp1255/cp1252.
2. **CLIs run by full path.** The engine CLI runs from the path `shutil.which`
   found. npm installs `claude.cmd`, and subprocess cannot start a `.cmd` by its
   bare name.
3. **Python command per machine.** The engine's allow-list is written as
   `Bash({python} scripts/...)` and expands to `python` / `py` here. It skips
   the Microsoft Store `python.exe` stub.
4. **Forward-slash paths for the engine.** Paths given to the engine use
   forward slashes.
5. **UTF-8 printing.** Every entry point prints UTF-8, so ✓, — and Hebrew don't
   raise UnicodeEncodeError.
6. **Safe names.**
   - Upload file names lose `: ? * " < > |`.
   - Project names that are Windows device names (`CON`, `NUL`, `COM1`, …) get
     a `_` prefix.
7. **CI.** The suite runs on `windows-latest` too. Check whether that run is
   green on the latest push. If it is, say so and link it.

**Known open risks.** Test these specifically:

- **`agy` (Antigravity) gets the prompt as a command-line argument, not on
  stdin.** If `agy` is a `.cmd`, a multi-line prompt, or one over about 8,000
  characters, may be cut off by `cmd.exe`.
- **Skills on Windows.** `scripts/skills/*.py` run as `python scripts/skills/<x>.py`; the engine runs in the
  install folder, so these relative paths must work even when `PCB_ADVISOR_HOME` is elsewhere.
- **Hebrew in the new files.** `idea.json`, the `.jsonl` logs, the netlist and the exported CSV are UTF-8 with
  LF line endings (`.gitattributes` says `* text=auto eol=lf`); a project name or a note in Hebrew must
  round-trip.
- **Paths:** the repo or home folder may sit under OneDrive, contain spaces or
  Hebrew, or exceed 260 characters.

---

## 3. Record the environment first

```powershell
systeminfo | findstr /B /C:"OS Name" /C:"OS Version"
python --version; py --version; where.exe python py python3
where.exe claude agy git
claude --version
chcp
reg query HKLM\SYSTEM\CurrentControlSet\Control\FileSystem /v LongPathsEnabled
git config --get core.autocrlf
(Get-Location).Path
```

Note whether the working folder is under OneDrive, and whether its path has
spaces or non-ASCII characters.

---

## 4. Setup

```powershell
git clone <repo-url> pcb-advisor    # or: git fetch; git checkout <branch Ilai names>
cd pcb-advisor
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python scripts\sources.py restore   # warms the vendor-PDF cache; needs network
```

If the repo arrived as a zip instead of a clone, say so in the report. Line
endings and `.gitattributes` may then differ.

---

## 5. Checks

Run them in order, and keep the numbers in your report.

### A. Base

| # | Check | Expected |
|---|---|---|
| A1 | `python -m pytest tests -q` | All pass. Paste the summary line, and the full failure for anything that fails. |
| A2 | `python scripts\verify_sources.py` | Same results as on macOS: `ok` lines for cached docs, no tracebacks. Its hint line says `python …`, not `python3 …`. |
| A3 | `python pcb.py init`, then `python pcb.py list` | Folders are created. ✓ / — print correctly in both PowerShell and `cmd.exe`. |
| A4 | `python pcb.py list > out.txt`, then open `out.txt` | No UnicodeEncodeError; the file is UTF-8. |
| A5 | `git status` after A1–A4 | No tracked file changed. In particular, `.json` sidecars and `.jsonl` were not rewritten with CRLF. |

### B. The platform seam

| # | Check | Expected |
|---|---|---|
| B1 | `python -c "import sys; sys.path.insert(0,'scripts'); import oscompat; print(oscompat.python_cmd(), oscompat.resolve('claude'))"` | `python` or `py` (never a WindowsApps path), and a full path to `claude.exe` or `claude.cmd`. |
| B2 | `python pcb.py tools` | The allow-list shows `Bash(python scripts/...)` (or `py`): no `{python}` and no `python3`. |
| B3 | `python pcb.py engines` | `claude_code` is available. If it says "not on PATH", record `where.exe claude`. |
| B4 | `python -m pytest tests/test_oscompat.py -v` | All pass. The Hebrew round-trip test is the important one. |
| B5 | `python pcb.py new "CON"` and `python pcb.py new "בדיקה עברית"` | Folders `_CON` and `בדיקה-עברית` are created. Delete both afterwards. |

### C. The app, end to end (needs the Claude CLI logged in)

| # | Check | Expected |
|---|---|---|
| C1 | `python pcb.py serve` | The browser opens on `http://localhost:8931`, and the UI loads with no console errors. |
| C2 | In the chat, send in Hebrew: `מה רוחב המסלול ל-1.5 אמפר בשכבה חיצונית?` | The reply is readable Hebrew, not `???` or mojibake. The agent ran `trace_width.py` **without asking for approval**, and the reply contains its number. |
| C3 | Ask the agent to add a datasheet from a URL. | It runs `sources.py get …`. The file and its `.json` sidecar appear in the project's `sources\`. |
| C4 | Upload a file named `test:file?.pdf` through the UI. | It is saved as `test_file_.pdf`, with no error. |
| C5 | Send a long, multi-line message (paste about 60 lines). | The full message reaches the engine. Check the reply refers to the last line. |
| C6 | If `agy` is installed: set `python pcb.py config agent.provider antigravity` and repeat C2 and C5. | Record whether it is `agy.exe` or `agy.cmd`, and whether the multi-line prompt arrives whole. **Known risk.** |
| C7 | Look at the server log for any `(png skipped: …)` line. | If it appears, the reason is a missing Cairo DLL and nothing else broke. |

### C2. The v2 surface (needs the Claude CLI logged in for C2.5)

| # | Check | Expected |
|---|---|---|
| C2.1 | `python pcb.py seed`, then `python pcb.py show lte-tracker` and `python pcb.py check` | 19 BOM lines, 1 sheet, 1 pending proposal; `check` reports one sheet ok, the course PDF "not here", no FAIL |
| C2.2 | `python scripts/skills/check_availability.py lte-tracker U5` | a real LCSC answer (stock, price, `C44955`), appended to `supply-log.jsonl` |
| C2.3 | `python scripts/skills/export_bom.py lte-tracker jlc` then `pcbway` | CSV in `exports/`, opens in Excel; C40/C41 and the test pads are listed as left out |
| C2.4 | In the browser: BOM, Schematic, Idea, Altium library, Sources, Skills, Settings | every page renders; no console errors; the schematic is sharp at 100% and 200% zoom |
| C2.5 | Press "Discuss this part" on U5 and ask a question in Hebrew | a part conversation opens with the context card; the reply is readable Hebrew |
| C2.6 | Approve the D30 proposal; edit an MPN in the table | D30 changes in the BOM and schematic; the edited line shows "checking", then a stock number |
| C2.7 | Altium library page, "Export for Altium" | `exports/lte-tracker_library.zip` downloads and lists D30 and D31 as unverified |
| C2.8 | Upload a file named `test:file?.pdf` on the Sources page | saved as `test_file_.pdf`, with a sha256 |

### D. Altium (Windows only, the reason this machine matters)

Run these once v2 produces a library.

| # | Check | Expected |
|---|---|---|
| D1 | Install the generated `<Project>.IntLib` (*Components panel ▸ ☰ ▸ File-based Libraries Preferences ▸ Installed ▸ Install…*). | Installs with no errors. Every part from the app's Altium library page is listed. |
| D2 | Place each non-standard part on a blank schematic. | Symbol pins match the datasheet. Parts marked "to review" in the app must be reported, whatever their state. |
| D3 | Update to a blank PCB. | Every footprint resolves, with no "footprint not found". 3D bodies appear where the app says STEP. |
| D4 | Any skill that drives Altium directly (for example a DelphiScript). | Runs from the app on this machine. Record the Altium version. |

---

## 6. Report

Write `docs/windows-verify-report.md` on your branch:

```markdown
# Windows verification - <date>
Commit: <sha>   Branch: <branch>
Environment: <section 3 output, trimmed>

| #  | Result | Notes / output |
|----|--------|----------------|
| A1 | PASS   | 131 passed in 12.3s |
| …  |        |                |

## Failures
<one block per FAIL: command, full error, diagnosis, suggested fix (file:line)>

## Fixes made
<each trivial fix: file:line, before/after, which check it unblocked>

## Not run
<check, why, what Ilai must do>
```

Then reply to Ilai with: overall PASS or FAIL, the count per section, and the
three most important failures.

---

## 7. Keeping this file current

The macOS-side agent updates this file with every version it hands over: new
checks go in §5, new risks in §2. The current baseline is the v2 rebuild
described in `docs/REBUILD-BRIEF.md`. Sections A–C apply now. Section D applies
once v2 produces an IntLib.
