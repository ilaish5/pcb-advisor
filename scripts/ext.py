"""Extension registries: new routes, agent actions and model keys live in their own modules, not in serve.py.

Each registry is a plain list of callables. An extension module appends to it (directly or with register(kind)) when imported;
load() imports the modules listed in MODULES, and import errors are not swallowed.

    GET / POST   (handler, path, query_or_body) -> dict | None
        Reached only for a path no built-in route matched, after the cross-site guard. GET gets the query as a {key: first value}
        dict (only /api/* paths); POST gets the parsed JSON body (a dict). Return None for "not mine"; otherwise the JSON result
        (sent as 200). To refuse, raise HTTPError(status, message) (sent as {"error": message}, like the built-in routes:
        400 bad input, 404 unknown thing, 409 not now); a serve.BadField also becomes a 400. handler is the request Handler
        (handler.project(), handler.session(project), handler.query(key)).
    ACTIONS      (project, action_dict, ctx) -> result | None
        For an agent action kind the built-in branches of serve._apply_actions do not handle. None means "not mine"; otherwise
        a string (reported as applied), or a (list_applied, list_refused) tuple. ctx is a dict: sess, last_user, meta, allow_auto.
        Raising ValueError / KeyError is reported as a refusal, like the built-ins.
    MODEL        (project, model_dict) -> dict
        Merged into the output of model.build (model_dict is what build made so far, extensions before this one included).
    SUMMARY      (project, summary_dict) -> dict
        Merged into what agent._summary shows the agent each turn.
"""
import importlib

GET, POST, ACTIONS, MODEL, SUMMARY = [], [], [], [], []

_KINDS = {"get": GET, "post": POST, "action": ACTIONS, "model": MODEL, "summary": SUMMARY}
MODULES = ("stages", "board_results", "pin_decisions", "constraints", "ledger", "limits")


class HTTPError(Exception):
    """Raise from a GET / POST extension to answer with this status and {"error": message}."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


def register(kind):
    """Decorator: @ext.register("post") adds the function to that registry ("get", "post", "action", "model", "summary")."""
    registry = _KINDS[kind]

    def deco(fn):
        registry.append(fn)
        return fn
    return deco


def load():
    """Import the extension modules (cached after the first time). A broken module raises here, not silently."""
    for name in MODULES:
        importlib.import_module(name)


def dispatch_http(registry, handler, path, arg):
    """(status, body) of the first handler that claims the path, or None. An HTTPError becomes its status."""
    for fn in list(registry):
        try:
            res = fn(handler, path, arg)
        except HTTPError as exc:
            return exc.status, {"error": exc.message}
        if res is not None:
            return 200, res
    return None


def dispatch_action(project, action, ctx):
    """The result of the first ACTIONS extension that claims the action, or None."""
    for fn in list(ACTIONS):
        res = fn(project, action, ctx)
        if res is not None:
            return res
    return None


def merge(registry, project, data):
    """Fold the MODEL / SUMMARY extensions into data (in place) and return it."""
    for fn in list(registry):
        data.update(fn(project, data) or {})
    return data
