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
commands. pcb-advisor neither takes that away nor hands it out: every key under
`agent.providers.claude_code.tools` defaults to `null`, and **a null key means
the flag is never passed**, so the CLI's own settings decide exactly as if this
tool did not exist. Set a key and you are deliberately overriding those settings
for the turns pcb-advisor drives.

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

## Errors

A provider returns `Result(error=...)`; it does not raise. The server turns that
into a chat line prefixed with the engine id, and the design state is untouched —
a failed engine must never cost a decision.

## `external`

`external` means an agent somewhere else is driving the project folder: your own
script, an IDE agent, a person with a text editor. The server keeps recording
what arrives; it just never generates a reply itself. This is also the honest
setting for offline work.
