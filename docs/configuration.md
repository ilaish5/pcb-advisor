# Configuration

Everything is a local file. Nothing is stored anywhere you cannot open in an editor.

```
config/defaults.json   shipped with the repo, always complete, tracked in git
config.json            yours, local, gitignored — only what you changed
environment            PCB_ADVISOR_HOME, PCB_ADVISOR_CONFIG, PCB_ADVISOR_PORT,
                       PCB_ADVISOR_PROVIDER
```

They layer in that order. `python3 pcb.py init` writes `config.json`; every other
key falls through to the defaults, so you inherit future defaults instead of
freezing today's. Saving writes back **only the difference** — that is why your
`config.json` stays three lines long.

```bash
python3 pcb.py config                        # the effective config, merged
python3 pcb.py config server.port            # one value
python3 pcb.py config server.port 9000       # set it
python3 pcb.py config user.language he
python3 pcb.py config agent.provider external
```

A key that no default declares is reported as a warning at startup — a typo in a
config file should not fail silently.

## The sections

### `workspace` — where things live

| key | default | note |
|---|---|---|
| `projects_dir` | `projects` | your designs |
| `shared_dir` | `shared` | the document cache, shared by every project |
| `templates_dir` | `templates` | what `pcb.py new` copies |
| `ui_dir` | `ui` | the browser UI |
| `downloads_dir` | empty = `~/Downloads` | where "Find my report" looks for a JLCDFM report PDF the user exported (only report-named PDFs are opened) |

A relative path resolves against the **workspace home**; an absolute one is used
as-is, so `projects_dir` can point at Dropbox or a git repo of your own.

`PCB_ADVISOR_HOME` moves the workspace. Your work (`projects`, `shared`) follows
it; `templates` and `ui` stay with the install, because they are the program, not your data.
The engine runs in the install (so `scripts/` is where it expects), and is given absolute paths to
your projects when the home is somewhere else:

```bash
PCB_ADVISOR_HOME=~/Documents/boards python3 pcb.py init
PCB_ADVISOR_HOME=~/Documents/boards python3 pcb.py serve
```

### `server`

| key | default |
|---|---|
| `host` | `127.0.0.1` — localhost only, on purpose |
| `port` | `8931` |
| `default_project` | `demo` |
| `open_browser` | `true` |

### `user`

`name` (stamped as a project's owner), `language` (`auto` follows what you type),
`units` (`mm` / `mil`), `theme`.

`theme` is `auto` (default), `light` or `dark`. `auto` follows the operating
system's light/dark setting and changes with it while the page is open. The
Settings panel in the UI writes this key, and applies the choice as you pick it.

### `agent`

Which LLM engine answers, and how. See [gateway.md](gateway.md).

| key | default |
|---|---|
| `provider` | `claude_code` |
| `timeout_seconds` | `180` |
| `history_messages` | `8` — how many recent messages go with each turn |
| `memory_every` | `10` — rewrite a conversation's memory every N messages |
| `memory_max_chars` | `2000` — hard ceiling; the engine is asked to compress to fit |
| `providers.<id>` | per-engine settings (command, model, enabled, tool permissions) |

`providers.claude_code.tools` decides what the CLI may touch on your machine
while it answers. It ships allowing reads and the calculation scripts, and
refusing Write and Edit — `pcb.py tools` shows it, `--clear` hands control back
to the CLI's own settings. See [gateway.md](gateway.md).

### `engineering_defaults`

The starting point for a new board: `layers`, `copper_oz`, `trace_layer`,
`ambient_c`, `max_temp_rise_c`, `min_track_mm`, `min_clearance_mm`,
`min_via_drill_mm`, `board_finish`, `mask_colour`, `assembly`.

`layers`, `copper_oz` and `mask_colour` also pick the JLC design-rule preset
(`scripts/jlc_preset.py`): 1-2 layers use JLC's 2-layer limits, 3 or more its
multilayer ones; 1 and 2 oz (and 2.5, 3.5, 4.5 oz on 2 layers) each have their
own; `black` and `white` mask need a wider mask bridge than the other colours.
An unknown value falls back to 2 layers, 1 oz, green.

These are **copied** into `project.json` when a project is created, and the copy
is what the project uses from then on. Changing a default later does not rewrite
boards you already started — a design that was calculated for 1 oz copper must
not silently become a 2 oz design.
