# AI engines: install and configure

The one-command installer in the README detects Claude Code and Antigravity, asks which one to install if neither is there (`PCB_ENGINE=claude|agy` answers for it), sets the provider and offers the sign-in for you. This page is for doing it by hand, or for Antigravity. `python pcb.py doctor` shows what is missing.

pcb-advisor does not ship a model. It runs an AI **command-line tool** that you install and sign in to
yourself. Two are supported:

| engine | provider id | account you need |
|---|---|---|
| Claude Code (`claude`) | `claude_code` | Claude Pro/Max subscription, or an Anthropic Console account |
| Antigravity CLI (`agy`) | `antigravity` | A Google account |

You need **one** of them. Install it, sign in once in a terminal, then tell pcb-advisor which one to use.

---

## 1. Claude Code (Windows)

1. Open **PowerShell** (not as administrator) and run:
   ```powershell
   irm https://claude.ai/install.ps1 | iex
   ```
   It installs `claude.exe` into `%USERPROFILE%\.local\bin` and adds that folder to your PATH.
2. **Close the terminal and open a new one** (the PATH change applies only to new terminals).
3. Check it: `claude --version`
4. Sign in: `claude auth login` (follow the browser login). Check with `claude auth status` (exit code 0 = signed in; it cannot tell that a saved login has expired, the chat then shows a "not signed in" card).

macOS / Linux: `curl -fsSL https://claude.ai/install.sh | bash`, then the same steps 2-4.

## 2. Antigravity CLI `agy` (Windows)

1. Open **PowerShell** (not as administrator) and run:
   ```powershell
   irm https://antigravity.google/cli/install.ps1 | iex
   ```
   The installer checks the download's SHA-512, puts `agy.exe` into `%LOCALAPPDATA%\agy\bin` and adds it to
   your PATH. It works on Intel/AMD and ARM64 Windows. Lines like `logging before google.Init` are harmless.
2. **Close the terminal and open a new one.**
3. Check it: `agy --version`
4. Sign in: run `agy` with no arguments and sign in with your Google account in the browser. Then exit.
5. Optional: `agy models` lists the models your account can use.

`agy` updates itself in the background; you never reinstall it.

## 3. Point pcb-advisor at the engine

From the pcb-advisor folder:

```powershell
python pcb.py engines                                  # what is installed and ready (* = active)
python pcb.py config agent.provider antigravity        # or: claude_code
```

Optional model choice:

```powershell
# Claude Code: a model name or alias, empty = the CLI default
python pcb.py config agent.providers.claude_code.model sonnet

# Antigravity: a name from `agy models`, empty = the CLI default
python pcb.py config agent.providers.antigravity.model gemini-3.1-pro-high
```

**Antigravity: set either `model` or `effort`, not both.** The model name already contains the level
(`...-high`, `...-low`); `agy` refuses `--model gemini-3.8-flash-high --effort low`. If both are set the
gateway sends only the model and ignores `effort`.

**Permissions and Altium files:** `agy` runs with `--dangerously-skip-permissions` by default (`config/defaults.json`), so it can run the advisor's inspection and calculation scripts non-interactively in headless mode without prompting for approvals. When an Altium project is linked in Settings, its folder is passed to the engine via `--add-dir` and explicitly marked read-only in the prompt's workspace instructions; the engine inspects SchDoc and PcbDoc files directly but never writes to them.

Restart `python pcb.py serve` after changing the engine.

## 4. If it does not work

| symptom | cause / fix |
|---|---|
| `python pcb.py engines` says "not on PATH" | You installed in another terminal. Open a new terminal and start pcb-advisor from it. Or set the full path: `python pcb.py config agent.providers.antigravity.command "$env:LOCALAPPDATA\agy\bin\agy.exe"` (PowerShell) |
| The chat answers "please sign in" / auth error | `claude auth login` (or run `agy` once) and finish the browser login. |
| `claude` is installed but "not found" | pcb-advisor also looks in `~/.local/bin` (Windows `%USERPROFILE%\.local\bin`), where the official installer puts it, so a terminal opened before the install still works. |
| Answers time out | A turn stops after `agent.idle_timeout_seconds` (default 180) with no output from the engine, or after `agent.timeout_seconds` (default 900) in total. Raise the one that fired; the chat says which. |
| Hebrew or other non-English text is garbled | Already handled: pcb-advisor talks to the CLI in UTF-8. Report it if you still see it. |

## 5. Notes for developers (verified 2026-10-11, agy 1.3.3, Claude Code 2.1.296, Windows 11 ARM64)

- `agy -p "text" --output-format json` returns one object: `{"status":"SUCCESS","response":"...","usage":{...}}`.
- `agy -p -` does **not** read the prompt from stdin; `-` is taken as the prompt itself. The gateway therefore
  never puts the prompt in argv (Windows limits a command line to about 32,000 characters). It always runs
  `agy -p= --input-format stream-json --output-format stream-json` and writes one NDJSON line to stdin:
  `{"event":"user","message":{"role":"user","content":"..."}}`. The answer is the stdout line with
  `"event":"result"` -> `result.response`. Non-JSON lines (`logging before google.Init`) are skipped. No result
  event, or a non-SUCCESS status / error field, becomes an error that carries a short tail of stdout and stderr.
  Everything is UTF-8 both ways (Hebrew round-trips).
- A config `args` list is treated as extra flags: `-p`, `-`, `-p=`, `--output-format X` and `--input-format X`
  are dropped from it (so an old config still works); the rest, e.g. `--dangerously-skip-permissions`, is kept.
- `--model` and `--effort` conflict: if a model is set, `--effort` is not sent and `Result.meta["dropped"]`
  is `["effort"]`; `--effort` is sent only when no model is set.
- `request.options["add_dirs"]` (absolute paths) becomes `--add-dir <path>` per entry, for both `agy` and `claude`.
  For `claude` the flags go before the variadic tool flags, so they cannot swallow or be swallowed.
- `--print-timeout` takes a duration (`60s`), not a number.
- `agy.exe` is a real executable, so the `.cmd` quoting problem of npm-installed CLIs does not apply to it.
- When agy auto-denies a tool in headless mode (no allow-rule), it still exits 0 with `status` SUCCESS and an empty
  `response`, plus `result.denied_actions: [{"action":"command","display_name":"RunCommand"}]`. The gateway turns an
  empty response with denials into an error (`agy denied RunCommand in headless mode; ...`), and an empty response
  without denials into `agy returned an empty answer`. A non-empty response with denials stays ok and the names are
  in `Result.meta["denied"]`.
