"""
Engines with a slot but no implementation yet.

They are registered so the routing table is honest: the UI lists them, the CLI
lists them, and selecting one fails with a message that says exactly which file
to write.  That is deliberately better than a provider that half-works.

To implement one: copy claude_code.py, set `status = "implemented"`, implement
`complete()`, and swap the class into REGISTRY in __init__.py.
"""
from .base import Provider


class CodexProvider(Provider):
    id = "codex"
    title = "Codex CLI"
    doc = "Planned. Implement in scripts/gateway/codex.py - same shape as claude_code.py."


class AntigravityProvider(Provider):
    id = "antigravity"
    title = "Antigravity"
    doc = "Planned. Implement in scripts/gateway/antigravity.py."


class OpenAICompatibleProvider(Provider):
    id = "openai_api"
    title = "OpenAI-compatible HTTP API"
    doc = ("Planned. Any /v1/chat/completions endpoint: set base_url, model and "
           "api_key_env in config, then implement scripts/gateway/openai_api.py.")
