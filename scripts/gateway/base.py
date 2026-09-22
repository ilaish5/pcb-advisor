"""
What every engine must look like from the outside.

A provider is a transport and nothing more: text in, text out.  It does not know
what a cascade is, it does not parse actions, and it never touches a file.  That
is what keeps "swap the engine" a one-line config change instead of a rewrite.
"""
import dataclasses
import typing


@dataclasses.dataclass
class Request:
    """One turn, fully self-contained. No provider may carry hidden state."""
    prompt: str                                     # the whole thing, ready to send
    system: str = ""                                # separate if the engine has a slot for it
    history: list = dataclasses.field(default_factory=list)   # [{role, text}], oldest first
    model: str = ""
    timeout: int = 180
    options: dict = dataclasses.field(default_factory=dict)   # provider-specific extras


@dataclasses.dataclass
class Result:
    """Raw text plus how it got here. Interpreting the text is the caller's job."""
    text: str = ""
    provider: str = ""
    model: str = ""
    error: str = ""
    meta: dict = dataclasses.field(default_factory=dict)

    @property
    def ok(self):
        return not self.error


class Provider:
    """Subclass, set `id`, implement `complete`. Register it in the registry."""

    id = "base"
    title = "base"
    status = "planned"          # implemented | planned
    doc = ""

    def __init__(self, config=None):
        self.config = config or {}

    def available(self) -> typing.Tuple[bool, str]:
        """(can it run right now, why not). Checked before routing, and shown
        in the UI so a misconfigured engine fails loudly instead of silently."""
        if self.status != "implemented":
            return False, f"{self.title} is registered but not implemented yet"
        if not self.config.get("enabled", True):
            return False, f"{self.id} is disabled in config"
        return True, ""

    def complete(self, request: Request) -> Result:
        raise NotImplementedError

    def describe(self):
        ok, why = self.available()
        return {"id": self.id, "title": self.title, "status": self.status,
                "available": ok, "reason": why,
                "model": self.config.get("model", ""), "doc": self.doc}
