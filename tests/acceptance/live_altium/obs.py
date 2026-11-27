"""Observation helpers shared by the Altium-judged behaviour metrics (metrics/altium_*.py).

One observation per Altium operation is cached in this process (the runner runs all metrics in one process): the metric that needs
"the page after Check board" and the metric that needs "Altium's own DRC report of the same board" read the same observation, so one
Altium operation is run once. Nothing here imports product code (A2).
"""
from __future__ import annotations

import contextlib
import json
import pathlib
import re
import time
from typing import Any, Callable

from . import env
from .browser import Browser

_CACHE: dict[str, Any] = {}
_BROWSERS: list = []


class NotObservable(RuntimeError):
    """The injected condition (or the live system) could not be established independently: the metric reports `error`, never `fail`."""


def cached(key: str, fn: Callable[[], Any]) -> Any:
    if key not in _CACHE:
        _CACHE[key] = fn()
    return _CACHE[key]


def forget(*keys: str) -> None:
    for k in keys:
        _CACHE.pop(k, None)


def live(ctx) -> dict:
    if not ctx.live:
        raise NotObservable("no --live server")
    return ctx.live


def server(ctx) -> env.Server:
    return env.attach(live(ctx))


def base(ctx) -> str:
    return live(ctx)["base_url"].rstrip("/")


def proj(ctx) -> str:
    return live(ctx)["project"]


def api(ctx, path: str, data=None, timeout: float = 60):
    sep = "&" if "?" in path else "?"
    return env.http(f"{base(ctx)}{path}{sep}project={proj(ctx)}", data, timeout=timeout)


def scratch_altium(ctx) -> pathlib.Path:
    return env.altium_dir(server(ctx))


def scratch_pcb(ctx) -> pathlib.Path:
    return scratch_altium(ctx) / f"{proj(ctx)}.PcbDoc"


def scratch_prj(ctx) -> pathlib.Path:
    return scratch_altium(ctx) / f"{proj(ctx)}.PrjPcb"


def owner_busy() -> bool:
    """True while the owner's own server (port 8931) runs an Altium step: the shared Altium is theirs then and the run waits."""
    code, body = env.http(f"http://127.0.0.1:{env.OWNER_PORT}/api/altium/step-status", timeout=3)
    return code == 200 and isinstance(body, dict) and bool(body.get("running"))


def wait_owner_idle(timeout: float = 600) -> None:
    t0 = time.time()
    while owner_busy():
        if time.time() - t0 > timeout:
            raise NotObservable("the owner's server is still running an Altium step; not touching the shared Altium")
        time.sleep(5)


@contextlib.contextmanager
def browser(ctx, **kw):
    """A Chrome with a throw-away profile, closed on exit (RAM: one at a time)."""
    b = Browser(base(ctx), proj(ctx), **kw)
    b.__enter__()
    try:
        yield b
    finally:
        b.__exit__(None, None, None)


def step_status(b: Browser) -> dict:
    r = b.api(f"/api/altium/step-status?project={b.project}")
    return r["body"] if isinstance(r["body"], dict) else {}


def step_running(b: Browser) -> bool:
    return bool(step_status(b).get("running"))


def click_step(b: Browser, label: str) -> None:
    b.page.click(f'#view [data-act="altium-step"]:has-text("{label}")')


def click_replace(b: Browser, step: str) -> bool:
    """The second click the product asks for when the board already holds the result (its own 'Replace ...' button)."""
    sel = f'#view [data-act="altium-step"][data-step="{step}"][data-replace="1"]'
    if b.page.query_selector(sel):
        b.page.click(sel)
        return True
    return False


def watch(b: Browser, max_s: float, every: float = 1.0, until_idle: bool = True, label: str = "w", started_grace: float = 8.0,
          settle_s: float = 20.0) -> list[dict]:
    """Snapshots (with the step-status running flag, which only decides WHEN to stop watching) until the step ends or max_s."""
    out: list[dict] = []
    t0 = time.time()
    seen_running = False
    idle_since = None
    while time.time() - t0 < max_s:
        s = b.snap(label)
        s["status"] = step_status(b)
        s["running"] = bool(s["status"].get("running"))
        out.append(s)
        seen_running = seen_running or s["running"]
        if until_idle and not s["running"] and (seen_running or time.time() - t0 > started_grace):
            # the page lags the server: wait (at most settle_s) until the page itself no longer shows the run
            if not any("pv-run" in n["cls"] or "loading" in n["cls"] for n in s["notes"]):
                break
            idle_since = idle_since or time.time()
            if time.time() - idle_since > settle_s:
                break
        time.sleep(every)
    s = b.snap(label + "-end")
    s["running"] = step_running(b)
    out.append(s)
    return out


def tone(cls: str) -> str:
    """The tone of a note from its DOM classes: ok (green), warn (amber), bad (red), or '' (neutral)."""
    c = " " + cls + " "
    if re.search(r"\b(bad|err|error|fail|danger)\b", c):
        return "bad"
    if re.search(r"\b(warn|warning|amber)\b", c):
        return "warn"
    if re.search(r"\b(ok|good|success|green)\b", c):
        return "ok"
    return ""


def notes_with(snap: dict, pattern: str) -> list[dict]:
    rx = re.compile(pattern, re.I)
    return [n for n in snap.get("notes", []) if rx.search(n.get("text", ""))]


def dump(path: pathlib.Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, default=str, ensure_ascii=False), encoding="utf-8")
