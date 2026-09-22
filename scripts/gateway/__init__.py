"""
The LLM gateway: one door, any engine behind it.

Nothing above this package knows which engine answered.  Callers build a
Request, call route(), and get a Result.  Swapping Claude Code for another
engine is a config edit:

    "agent": { "provider": "codex" }

Registering a new engine is one class and one line in REGISTRY.  Everything
else - prompt building, action parsing, writing files - stays where it is.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import workspace                                        # noqa: E402
from .base import Provider, Request, Result             # noqa: E402,F401
from .claude_code import ClaudeCodeProvider             # noqa: E402
from .external import ExternalProvider                  # noqa: E402
from .planned import (                                  # noqa: E402
    AntigravityProvider,
    CodexProvider,
    OpenAICompatibleProvider,
)

REGISTRY = {
    ClaudeCodeProvider.id: ClaudeCodeProvider,
    ExternalProvider.id: ExternalProvider,
    CodexProvider.id: CodexProvider,
    AntigravityProvider.id: AntigravityProvider,
    OpenAICompatibleProvider.id: OpenAICompatibleProvider,
}

# names people actually type, mapped to what is registered
ALIASES = {"claude": "claude_code", "claude-code": "claude_code", "cli": "claude_code"}


def resolve(name=None):
    """The provider id in force: the argument, else config, else claude_code."""
    name = (name or workspace.get("agent.provider")
            or workspace.get("agent.backend")          # older config files
            or "claude_code")
    return ALIASES.get(name, name)


def provider(name=None):
    pid = resolve(name)
    cls = REGISTRY.get(pid)
    if cls is None:
        raise KeyError(f"unknown engine '{pid}'. Known: {', '.join(sorted(REGISTRY))}")
    return cls(workspace.get(f"agent.providers.{pid}", {}) or {})


def route(request: Request, name=None) -> Result:
    """Send one turn to whichever engine is configured."""
    try:
        prov = provider(name)
    except KeyError as exc:
        return Result(provider=str(name or ""), error=str(exc))

    ok, why = prov.available()
    if not ok:
        return Result(provider=prov.id, error=why)

    request.options.setdefault("cwd", str(workspace.home()))
    if not request.model:
        request.model = prov.config.get("model", "") or ""
    if not request.timeout:
        request.timeout = int(workspace.get("agent.timeout_seconds", 180))
    return prov.complete(request)


def describe_all():
    """Every registered engine and whether it could run right now."""
    active = resolve()
    out = []
    for pid, cls in REGISTRY.items():
        d = cls(workspace.get(f"agent.providers.{pid}", {}) or {}).describe()
        d["active"] = pid == active
        out.append(d)
    return sorted(out, key=lambda d: (d["status"] != "implemented", d["id"]))


if __name__ == "__main__":
    for d in describe_all():
        mark = "*" if d["active"] else " "
        state = "ready" if d["available"] else d["reason"]
        print(f"{mark} {d['id']:14} {d['status']:12} {state}")
