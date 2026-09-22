# The LLM gateway

One door, any engine behind it. Nothing above `scripts/gateway/` knows which
engine answered — swapping one for another is a config edit, not a rewrite.

```bash
python3 pcb.py engines
* claude_code    implemented  ready
  external       implemented  ready
  antigravity    planned      Antigravity is registered but not implemented yet
  codex          planned      Codex CLI is registered but not implemented yet
  openai_api     planned      OpenAI-compatible HTTP API is registered but not implemented yet

python3 pcb.py config agent.provider external
```

## The layers

```
serve.py            the only writer. Applies actions, never generates them.
  agent.py          the PROTOCOL: the rules, the state summary, parsing the
                    actions block back out of a reply. Knows nothing about engines.
    gateway/        the ROUTE: which engine, is it available, send and return.
      claude_code.py   spawn `claude -p`
      external.py      no-op; something outside is driving the folder
      planned.py       registered, not implemented — fails with a clear message
```

A provider is a transport and nothing more: **text in, text out**. It does not
know what a cascade is, it does not parse actions, and it never touches a file.
That boundary is what keeps a new engine cheap.

## Engines with hands, and engines without

A CLI agent sits in the workspace and can open a datasheet, grep the corpus and
run `trace_width.py`. An HTTP API cannot do any of that. Each provider declares
which it is:

```python
class ClaudeCodeProvider(Provider):
    workspace_access = True
```

`agent.py` reads it and builds a **different prompt** for each. An engine with
hands gets a `--- WORKSPACE ---` section: the real paths, what it may write, and
the scripts worth running. An engine without hands does not — because telling a
text-only engine to go and read a file does not fail loudly, **it invents**.

The flag is computed, not just declared: `claude_code` reports `False` when
`tools.available` is `""`, since a CLI with every tool disabled is text-only
again. `pcb.py engines` prints which each one is.

Set `workspace_access = True` on a new provider only if it can really reach the
filesystem the server is running on.

## Adding an engine

1. Copy `scripts/gateway/claude_code.py`.
2. Set `id`, `title`, `status = "implemented"`, and implement `complete()`:

```python
from .base import Provider, Request, Result

class MyEngineProvider(Provider):
    id = "my_engine"
    title = "My engine"
    status = "implemented"

    def available(self):
        if not self.config.get("enabled", True):
            return False, "my_engine is disabled in config"
        if not self.config.get("api_key_env") in os.environ:
            return False, "API key not in the environment"
        return True, ""

    def complete(self, request: Request) -> Result:
        text = ...                      # send request.prompt, get a string back
        return Result(text=text, provider=self.id, model=request.model)
```

3. Register it in `REGISTRY` in `scripts/gateway/__init__.py`.
4. Add its settings under `agent.providers.my_engine` in `config/defaults.json`.

`available()` is checked before every route and shown by `pcb.py engines`, so a
misconfigured engine says why instead of failing mid-conversation. Provider
blocks in the config are open — an id the defaults never declared is allowed, so
your own engine does not have to be upstreamed to be configured.

## Tool permissions

The Claude Code CLI is an agent in its own right — it can read files, grep, run
commands. `agent.providers.claude_code.tools` decides how much of that it may
use while answering. A `null` key passes no flag at all, leaving the CLI's own
settings to decide; a key with a value overrides them for the turns pcb-advisor
drives. The shipped default sets `allowed` and `disallowed` (see below) and
leaves the other two null.

| key | CLI flag | what it does |
|---|---|---|
| `available` | `--tools` | the built-in set it may draw from. `""` disables every tool, `"default"` is all of them |
| `allowed` | `--allowedTools` | pre-approved, no prompt. Patterns work: `["Read", "Bash(git status)"]` |
| `disallowed` | `--disallowedTools` | refused outright; wins over `allowed` |
| `permission_mode` | `--permission-mode` | `acceptEdits`, `auto`, `bypassPermissions`, `manual`, `dontAsk`, `plan` |

A list is joined with commas, a string is passed through. `""` is a real value —
it is how `--tools` disables everything — which is why "do not pass this" is
`null` and not the empty string.

```bash
# let it read the workspace but never write
python3 pcb.py config agent.providers.claude_code.tools.allowed '["Read","Grep","Glob"]'
python3 pcb.py config agent.providers.claude_code.tools.disallowed '["Write","Edit","Bash"]'

# no tools at all - the engine only answers
python3 pcb.py config agent.providers.claude_code.tools.available '""'

# back to the CLI's own settings
python3 pcb.py config agent.providers.claude_code.tools.allowed null
```

`pcb.py engines` prints the policy in force, and a bad value (an unknown
permission mode, a mistyped key) makes the engine report unavailable with the
reason instead of failing mid-conversation.

Note what this does and does not bound. The **protocol** is bounded whatever you
set here: only the three actions below ever change the design, and they go
through the server. Tool permissions bound something else — what the engine may
touch on your machine while it composes a reply.

## The three actions

Whatever tools the engine has, only three things it emits ever change the
design, and the server is what applies them:

| action | effect |
|---|---|
| `{"type":"sketch", "blocks":[...], "links":[...], "confirmed":false}` | writes `sketch.json` |
| `{"type":"answer", "node":"...", "value":"..."}` | appends to `decisions.jsonl` |
| `{"type":"ask", "anchor":"...", "text":"..."}` | appends to `threads.jsonl` |

Any other action type is dropped. The engine cannot create a constraint: those
come from the cascade automatically once a decision is recorded.

## A recommended tool policy

This policy **ships as the default**, and it has to: with no allow-list the CLI
asks to approve each command, print mode has nobody to approve, and the engine
ends up reporting that it could not compute instead of computing. Verified
against the real CLI.

```bash
python3 pcb.py tools            # what is in force
python3 pcb.py tools --clear    # hand control back to the CLI's own settings
python3 pcb.py tools --apply    # restore the default
```

What ships:

```json
"allowed":    ["Read", "Grep", "Glob",
               "Bash(python3 scripts/trace_width.py *)",
               "Bash(python3 scripts/sources.py *)",
               "Bash(python3 scripts/model.py *)"],
"disallowed": ["Write", "Edit", "NotebookEdit"]
```

Reading, grepping and the scripts are reachable; direct edits are not. The three
things worth protecting, in order:

1. **`decisions.jsonl` / `threads.jsonl` / `chat.jsonl`** — append-only, and each
   decision records `by` (user or agent). An edit destroys the record of a
   student changing their mind; a forged `by` destroys the only enforcement of
   "the student decides, the agent recommends". These are also outside git, so
   there is nothing to revert to.
2. **`cascade/*.yaml`** — a constraint invented here is served to every future
   project, and `convention` provenance requires no source at all, so
   `validate_cascade.py` will not catch it. Git does track the corpus, so this
   one is at least visible in a diff.
3. Derived files are rewritten on the next run; writing them achieves nothing.

Adding a document is the one write worth allowing, and it goes through
`scripts/sources.py fetch` rather than curl, so the sha256 and the url are
recorded with it.

### Why the prompt goes on stdin

`--allowedTools`, `--disallowedTools` and `--tools` are **variadic**: the CLI
reads every following argument as another tool name. A prompt passed as a
trailing argument is therefore swallowed the moment any tool flag is set, and
the CLI exits with "Input must be provided". The provider pipes the prompt
through stdin instead, which also sidesteps ARG_MAX and lets a pattern contain
spaces — `Bash(python3 scripts/trace_width.py *)` only works this way.

## Errors

A provider returns `Result(error=...)`; it does not raise. The server turns that
into a chat line prefixed with the engine id, and the design state is untouched —
a failed engine must never cost a decision.

## `external`

`external` means an agent somewhere else is driving the project folder: your own
script, an IDE agent, a person with a text editor. The server keeps recording
what arrives; it just never generates a reply itself. This is also the honest
setting for offline work.
