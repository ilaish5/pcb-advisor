# Live (behaviour) harness

Behaviour metrics (`kind="behaviour"`, `metrics/live_*.py`) drive a running pcb-advisor server through a real browser and
its HTTP API. Nothing here imports product code (A2): the product runs as a child process from a git worktree.

## Run

```
python -I tests/acceptance/fetch_fixture.py                                    # the frozen 27/11 fixture, once
python -I tests/acceptance/live/server.py up --commit 2dcd691                  # prints {"url", "project", ...}; leave it running
python -I tests/acceptance/run.py --live <url> --live-project Final-E2E-4L --live-commit 2dcd691 --only P0-4 U1 ...
python -I tests/acceptance/live/controls.py                                    # the detectors' positive controls: all PASS
```

- `--live` / `--live-project`: the run's server. Read-only checks (what a page shows) use it. When it was started with
  `server.py up`, its home is found by port (`local/acceptance-live/<port>.json`) and its own project files are the artifact;
  otherwise the frozen fixture's `project/` is (the server must then be seeded with the fixture).
- `--live-commit`: the commit every metric that injects a fault starts its **own** private server from (default `2dcd691`,
  the pre-fix commit). A fix branch is measured with `--live-commit <fix sha>`.
- Locally on Windows: `ACCEPTANCE_BROWSER_CHANNEL=chrome` makes Playwright use the installed Chrome.
- Hidden corpora (A15): `hidden-corpora/` at the repo root (git-ignored) or `ACCEPTANCE_HIDDEN_CORPORA=<folder>`. Without
  them each corpus metric says `VISIBLE HALF ONLY` in its detail: valid for the red proof, never for a final pass.

## Parts

| File | What it does |
|---|---|
| `server.py` | `LiveServer(commit)`: `git worktree` of the commit under `local/acceptance-worktrees/`, a free port, its own `PCB_ADVISOR_HOME` and `PCB_ADVISOR_CONFIG` (temp), start / stop / restart. |
| `seed.py` | Copies the fixture's `project/` (and `altium/`, with the project's Altium paths pointed at the copy) or a synthetic project into the server's workspace. The frozen fixture is only read. |
| `driver.py` | Playwright page at 1366 x 768: DOM snapshots with timestamps, every `/api/*` response recorded. |
| `fake_engine.py` | The oracle's stand-in for the agent engine CLI (stream-json, like `claude -p`). The server's config points `agent.providers.claude_code.command` at it. Each turn plays a queued script: tool steps, silence (stall), death (exit 137), an error, a final reply with the product's actions block. Free and repeatable; it is oracle code, not product code. |
| `faults.py` | Blackhole proxy (network hangs), refusing port (JLC/LCSC unreachable), 404 server (URL source gone), engine kill, a foreign writer (a file written by another process). Network faults are set on the product process only (`HTTPS_PROXY`). |
| `failures.py` | The non-Altium P0-4 failure paths and the capture of what the page shows (title, weight, lines, Details control, forbidden-pattern list). |
| `pins.py` | The oracle's own W14 pin status of a BOM line (verified needs an evidence record matching the file on disk). |
| `corpora.py` | Loads a corpus's visible half (`tests/acceptance/corpora/`) and, when present, its hidden half. |
| `controls.py` | Hand-built pages and records that show each detector's PASS condition (most live metrics have no pass state before the fix). |

## What runs in the cloud box (established 27/11 on 2dcd691)

- The server starts on Linux (Python 3.13, `requirements.txt`): `python pcb.py serve --port N --no-browser`, with
  `PCB_ADVISOR_HOME` / `PCB_ADVISOR_CONFIG` honoured.
- Pages without Altium: every stage (Idea, BOM, Schematic, Layout, Rules, Outputs, DFM), Sources and Settings render from the
  project files; the fixture's Layout preview and DRC banner render. Every Altium action is refused with "The Altium bridge works
  on Windows with Altium Designer installed; this computer is not Windows."
- Agent engine: the Claude Code CLI is installed and authenticated in this box (`claude -p` answered). The metrics do not use it:
  they use the fake engine, so agent paths are free, deterministic and can be stalled or killed. Antigravity is not installed.
  Metrics that need a real engine's answers (T-F repeat consistency, the agent leg of T-B) are the local / E phase.
- Releases: this session may not create GitHub releases (403), so the hidden corpora were handed to the owner as a zip outside git.
