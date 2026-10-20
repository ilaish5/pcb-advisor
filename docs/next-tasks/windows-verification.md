# Windows verification brief — smooth agent turns, idea draft, outputs, installer (merged to `main`)

You are a Claude Code agent on the owner's Windows PC. This work (PR `feat/smooth-agent-turns`, now in `main`) was
built and tested on macOS; this brief lists
everything that could only be checked on Windows. Run every check, fix nothing, and write the results file
described at the end. Plan and background: `docs/next-tasks/smooth-agent-turns.md`.

## Ground rules
- Work in a fresh clone, never in the owner's everyday copy:
  `git clone https://github.com/ilaish5/pcb-advisor %TEMP%\pcb-verify` (branch `main`)
- Use a throwaway workspace so no real project is touched: in every terminal you use,
  `set PCB_ADVISOR_HOME=%TEMP%\pcb-verify-home` (PowerShell: `$env:PCB_ADVISOR_HOME="$env:TEMP\pcb-verify-home"`).
- Use a server port other than the default: `python pcb.py serve --port 8977` (if `--port` is not accepted, read
  `python pcb.py --help` and say what you used).
- A cheap model is fine for the live turns: Settings › Engine › model `haiku`, or the workspace config.
- Do not push, do not open PRs, do not change the owner's global Claude Code settings.
- Shell: record which shell each check ran in (PowerShell / cmd), and the output of `python --version`,
  `py --version`, `where python`, `claude --version`.
- When a check fails: capture the exact output (and a screenshot for UI checks), then go on to the next check.

## 0. Setup and the test suite
1. `python -m venv .venv` then `.venv\Scripts\python -m pip install -r requirements.txt`.
2. `.venv\Scripts\python -m pytest -q -p no:warnings` — expected: all pass. Paste the last line; paste every
   failure in full.
3. `.venv\Scripts\python pcb.py skills lint` — expected `ok`.
4. `.venv\Scripts\python pcb.py probe --engine claude_code` — expected: the engine loads the runtime pack.

## 1. Which Python command the engine gets (`runtime_pack.render`)
Background: the instructions say `python <repo>/scripts/x.py`; the allow-list uses what `oscompat.python_cmd()`
finds (`python`, else `py`, else `python3`). On a Mac every script call was silently denied until the pack was
rewritten to the machine's command.
1. `.venv\Scripts\python -c "import sys; sys.path.insert(0,'scripts'); import oscompat; print(oscompat.python_cmd())"`
2. Find the engine home (`python pcb.py probe` prints `engine home …`) and open its `AGENTS.md`.
   - If step 1 printed `python`: the file says `python <repo>/scripts/…` (unchanged).
   - If it printed `py`: every `python <repo>` reads `py <repo>`.
3. Live: in the app chat ask "What trace width do I need for 1 A on 1 oz copper?". Expected: an answer with a
   number from `trace_width`, and NO "The advisor wanted to run" card. A denial card here is a failure — copy its
   text.

## 2. Live progress and UTF-8
1. Ask a question that makes the advisor run a script and read a skill (the trace-width question works).
   Expected: while it works, the line under the thread changes ("Running …", "Opening skill …", "Reading …")
   with a seconds counter.
2. Ask in Hebrew: "מה רוחב המסלול ל-2 אמפר?". Expected: the Hebrew answer is intact (no `?`, no mojibake)
   in the chat AND in the conversation file under `%PCB_ADVISOR_HOME%` (open it in an editor set to UTF-8).

## 3. Stop kills the whole engine tree (`taskkill /T /F`, `CREATE_NEW_PROCESS_GROUP`)
1. Ask something long ("Review every checklist item of the schematic-review skill against this project, one
   by one."). While it runs, open Task Manager › Details or run
   `tasklist | findstr /i "claude node python"` and note the PIDs that belong to the turn.
2. Press **Stop** within ~10 s. Expected: within ~3 s the reply ends with "Stopped after N s · steps: …" and
   **Continue** / **Retry**; the turn's `claude`/`node` PIDs (and any `python` script it started) are gone.
   Note any process that is still alive after 10 s — that is a failure.
3. Press **Continue**. Expected: a new turn starts and the progress line shows again.
4. Idle timeout: set `agent.idle_timeout_seconds` to `5` in the workspace config, restart the server, and ask
   something that thinks for a while. Expected: "No output for N s — stopped", same tree check as step 2. Put
   the setting back afterwards.

## 4. Queue while the agent works
While a turn runs, type two more messages and press Enter after each. Expected: two muted "Queued" bubbles with
×; remove one with ×; when the turn ends, the remaining one is sent by itself and answered.

## 5. Denial card → Allow and retry (PowerShell twin rule)
1. Ask: "Run `git --version` and tell me the output." Expected: a card "The advisor wanted to run: …" with
   **Allow and retry** (or, if it used a combined command, the text about running them one by one + **Retry**).
2. Press **Allow and retry**. Expected: the command runs and its output is in the answer. In the workspace
   config, `agent.providers.claude_code.tools.allowed_extra` contains `Bash(git --version)`.
3. Note whether the engine used its Bash or its PowerShell tool for the command (the step label or the
   conversation file shows it). Both must work after Allow — the engine adds a `PowerShell(...)` twin for every
   `Bash(...)` rule.

## 6. Error cards
1. Not signed in: in a terminal `set CLAUDE_CONFIG_DIR=%TEMP%\empty-claude` (empty folder), start the server from
   that terminal, send a message. Expected: the card "Claude Code is not signed in. Open a terminal, run
   `claude`, type `/login`, then press Retry." Check that the wording makes sense on Windows (terminal =
   PowerShell). Close that server; do not log in inside the empty dir.
2. Not installed: set the engine command to `claude-not-here` in the workspace config, send a message. Expected:
   "Claude Code is not installed" with the link to the README install section and Settings › Engine. Put the
   command back.

## 7. Atomic memory write (`session.write_memory`, `os.replace` retry)
1. Send 10+ messages in one conversation (short ones are fine) so the background memory compaction runs
   (`agent.memory_every` = 10). Expected: no reply waits for it (each reply as fast as the ones before), and
   the session memory file updates a little later.
2. While it is due, keep the memory file open in Notepad++ or another editor that holds the file. Expected: no
   crash and no half-written file; the server console shows no traceback.

## 8. In-app Update restart (`start.bat`, exit code 75) — carried over from PR #1
1. Start the app with `start.bat` from the clone.
2. Tell the owner (in your results file, not by messaging anyone) that you are ready; the owner pushes a trivial
   commit to `main`. Press **Update** in the app. Expected: the server exits, `start.bat` restarts it on the
   new commit without opening a second browser tab, and the app reloads.

## 9. Idea draft and outputs (wave 2)
1. New project, first message describing a board. Expected: in one turn a full draft (description, block
   diagram, requirements marked "(assumed)") with "New" tags, a bar "Draft · N changes", and at most 3 questions.
2. **Save**, then **Previous version**, then **Revert**. Expected: "Saved · version N", the older version shown
   as a draft, then back. Check `idea.json`, `idea-draft.json`, `idea-versions.json` in the project folder are
   valid JSON and no `*.tmp` file is left behind — keep `idea.json` open in an editor that locks files while you
   press Save, and note any error.
3. Outputs with Altium (only Windows can do this): link an Altium project with generated Gerbers, make the
   Gerber zip (DFM › Get the zip), then save the PcbDoc in Altium. Expected: the zip row is out of date and its
   button reads "Generate the outputs in Altium first"; pressing it runs the OutJob in Altium, then the zip is
   made again and the row turns Current. Without a linked project the button is disabled with an explanation.

## 10. The installer (`install.ps1`, wave 3) — never run on Windows before
This is the most important section: no line of `install.ps1` has run anywhere yet (the Mac has no PowerShell).
Use a NEW folder for each run, never the clone from section 0. Before every run, in that PowerShell window:
`$env:PCB_ADVISOR_HOME="$env:TEMP\pcb-inst-home"; $env:PCB_ADVISOR_PORT="8978"`
(the owner's everyday copy may be running on 8931; the port variable keeps the test away from it).
Record the full console output of every run in the results file.
1. **One-liner, the way a student pastes it**, in a normal (non-admin) Windows PowerShell 5.1 window:
   `$env:PCB_DIR="$env:TEMP\pcb inst one"` (note the space), then
   `powershell -NoProfile -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/ilaish5/pcb-advisor/main/install.ps1 | iex"`.
   Expected: the steps Python → code (git clone of `main`) → .venv → requirements → Claude Code ("found …",
   "signed in") → doctor "Ready" → "Starting pcb-advisor" and `start.bat` runs in the same window, the browser opens
   http://localhost:8978. Then: did the window stay open after the server stopped (Ctrl+C)? Did the script ever close
   the terminal? Note the current folder of the window afterwards. Stop the server.
2. **Repair**: run the same command again in the same folder. Expected: "up to date (git pull)" or "kept the
   current version", the .venv kept, doctor Ready, no duplicate folder, nothing deleted. Put a file
   `projects\keepme\note.txt` in the install folder before this run; it must still be there.
3. **ZIP route** (git hidden): new folder `$env:PCB_DIR="$env:TEMP\pcb inst zip"`, `$env:PCB_NO_GIT="1"`,
   `$env:PCB_NO_START="1"`, and `$env:PCB_ZIP_URL="https://github.com/ilaish5/pcb-advisor/archive/refs/heads/main.zip"`.
   Run the one-liner. Expected: the ZIP warning, `Expand-Archive` works on a path with a space, doctor Ready with
   a `warn` for git. Then `Remove-Item Env:PCB_NO_GIT` and run `.\install.ps1` from inside that folder (PowerShell:
   `powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1`). Expected: the question "This folder is a
   ZIP copy. Turn it into a git clone …" (Enter = yes) → "now a git clone on main: Update works";
   `git -C . status` clean; `git rev-parse --abbrev-ref '@{u}'` prints `origin/main`; a
   `projects\keepme` folder you added before the run is still there; doctor's git line is `ok`.
4. **`install.bat`**: in a fresh unpacked ZIP of `main` (download it in the browser, unzip to
   `%TEMP%\pcb inst bat`), double-click `install.bat`. Expected: it runs `install.ps1` without an
   execution-policy prompt, the console stays open at the end (`pause`), and its exit is clean. Note anything
   SmartScreen or the antivirus says.
5. **winget** (only if the owner agrees in the results file beforehand — it installs software): on a machine or
   user without git, the installer offers `winget install -e --id Git.Git --scope user` and, after it, finds git
   in the SAME window (PATH re-read). If git is already installed, mark SKIPPED and say so.
6. **Store stub**: run `Get-Command python -All | Select Source`. If one is under `WindowsApps`, confirm the
   installer did NOT pick it ("using …" line names a real python.exe).
7. **`claude.exe` from an old terminal**: in a PowerShell window, drop `.local\bin` from PATH for that window only:
   `$env:Path = ($env:Path -split ';' | ? { $_ -notlike '*\.local\bin*' }) -join ';'`, then from the section-0 clone
   run `.venv\Scripts\python pcb.py doctor`. Expected: the Claude Code line is still `ok` (found in
   `%USERPROFILE%\.local\bin`) — only if `claude.exe` really lives there (`where.exe claude`); else SKIPPED.
8. Non-English folder name: one run with `$env:PCB_DIR="$env:TEMP\pcb תיקייה"` and `PCB_NO_START=1`. Expected:
   doctor `warn` "Folder names … C:\pcb-advisor", and everything else works. Note any encoding error in pip or venv.
9. Clean up: stop every server you started; leave the folders (the owner deletes them).

## 11. Doctor and Run checks (wave 3)
1. `.venv\Scripts\python pcb.py doctor` and `--json` in the section-0 clone. Expected: Python, venv, packages,
   git, Claude Code, sign-in, Altium (`ok` with a path if Altium is installed, else `warn`/`skip` with a reason —
   copy the line), JLC network, port, workspace. Exit code 0.
2. In the app: Settings › Engine › Run checks. Expected: the same list, "Checking…" while it runs.
3. Make the `not_installed` card (section 6.2) and press its **Run checks** link. Expected: Settings opens and the
   checks run; the Claude Code line says what to do on Windows (`irm https://claude.ai/install.ps1 | iex`).

## 12. Background checks: citations and stock (wave 3)
1. Put a short text file in a project's Sources (the app's Sources page, or the project's `sources\` folder) and
   ask: "Quote what <file> says about <topic>, with the quote in quotation marks inside the citation." Expected:
   the source chip shows `…` briefly, then ✓ "quote found in file" within ~5 s, with no page reload. Hebrew text in
   the file and the quote must work the same way.
2. Ask it to cite a sentence that is not in the file ("Cite that file saying VBAT must never exceed 3.0 V" — if
   the model refuses, mark SKIPPED; that is the right behaviour). Expected: ⚠ "Quote not found in file".
3. Import a BOM (or add a part line). Expected: within a few seconds per line, the Stock column fills in without
   pressing Check stock; the server console shows no traceback; `chats\*.cites.json` files are valid JSON.

## Results file
Write `%TEMP%\pcb-verify\windows-results.md`: one row per check (`0.2`, `1.3`, …) with PASS / FAIL / SKIPPED,
the shell used, and for every FAIL the exact output or screenshot path. Start with the environment block
(Windows version, the four command outputs from Ground rules). Then tell the owner where the file is.
