"""
No engine here on purpose.

`external` means an agent somewhere else is driving the project folder - your
own script, an IDE agent, a person with a text editor.  The server keeps
recording what arrives; it just never generates a reply itself.
"""
from .base import Provider, Request, Result


class ExternalProvider(Provider):
    id = "external"
    title = "External agent"
    status = "implemented"
    doc = "Nothing is generated here. Something outside the server writes to the project folder."

    def available(self):
        return True, ""

    def complete(self, request: Request) -> Result:
        return Result(text="", provider=self.id, meta={"noop": True})
