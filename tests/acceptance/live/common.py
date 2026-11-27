"""Helpers every live metric uses: which server to talk to, private servers for fault injection, evidence files.

Two kinds of server:
- the run's server (`--live URL --live-project NAME`): read-only checks of what the page shows. When it was started with
  `live/server.py up`, its home is known (local/acceptance-live/<port>.json) and its project files are read there; otherwise
  the frozen fixture's project/ is the artifact (the run's server must then be seeded with the fixture).
- private servers (`private()`): started by the metric itself from `--live-commit` (default the pre-fix commit), seeded,
  faulted, restarted and stopped by the metric. Nothing the metric does can touch the run's server.
"""
from __future__ import annotations

import atexit
import datetime as dt
import json
import pathlib
import re
import time
from urllib.parse import urlencode, urlparse

from live import seed
from live.server import REPO, LiveServer, commit_of, http_json

RUN_STAMP = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
EVID = REPO / "local" / "acceptance-runs" / f"live-{RUN_STAMP}"
_PRIVATE: dict = {}


class Run:
    """The run's server as a metric sees it."""

    def __init__(self, ctx) -> None:
        if not ctx.live or not ctx.live.get("base_url"):
            raise RuntimeError("behaviour metric without --live")
        self.ctx = ctx
        self.url = ctx.live["base_url"].rstrip("/")
        self.project = ctx.live.get("project") or ""
        reg = REPO / "local" / "acceptance-live" / f"{urlparse(self.url).port}.json"
        info = json.loads(reg.read_text(encoding="utf-8")) if reg.is_file() else {}
        self.home = pathlib.Path(info["home"]) if info.get("home") else None
        if not self.project:
            self.project = info.get("project", "")

    @property
    def project_dir(self) -> pathlib.Path:
        """The project files behind the page: the server's own folder when known, else the frozen fixture's project/."""
        if self.home and (self.home / "projects" / self.project).is_dir():
            return self.home / "projects" / self.project
        return self.ctx.project

    def get(self, path: str, **q):
        q.setdefault("project", self.project)
        return http_json(f"{self.url}{path}?{urlencode(q)}")

    def post(self, path: str, body: dict, **q):
        q.setdefault("project", self.project)
        return http_json(f"{self.url}{path}?{urlencode(q)}", body, timeout=120)


def private(ctx, key: str = "fixture", engine: str = "fake", env: dict | None = None, fresh: bool = False) -> LiveServer:
    """A server only this metric (or this run's metrics, for key reuse) uses. key 'fixture' = seeded with the frozen
    fixture's project; any other key = an empty workspace the metric seeds itself. fresh=True: always a new one, and the
    caller stops it."""
    commit = commit_of(ctx.live)
    k = (key, commit, engine, json.dumps(env or {}, sort_keys=True))
    if not fresh and k in _PRIVATE and _PRIVATE[k].proc and _PRIVATE[k].proc.poll() is None:
        return _PRIVATE[k]
    srv = LiveServer(commit, engine=engine, env=env)
    if key == "fixture":
        srv.project = seed.seed_fixture(srv.projects, root=ctx.root if (ctx.root / "project").is_dir() else None)
    srv.start()
    if not fresh:
        _PRIVATE[k] = srv
    return srv


@atexit.register
def _stop_all() -> None:
    for s in _PRIVATE.values():
        try:
            s.stop()
        except Exception:
            pass


def save(ctx, name: str, obj) -> dict:
    """Write a measured record (DOM snapshots, API bodies) to the run's evidence folder and return its evidence entry."""
    EVID.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w.-]+", "_", name)
    p = EVID / f"{safe}.json"
    p.write_text(json.dumps(obj, indent=1, default=str, ensure_ascii=False), encoding="utf-8")
    return ctx.ev(p, name)


def queue_turn(srv: LiveServer, script: dict, name: str = "") -> None:
    """Queue one scripted turn for the fake engine of a private server."""
    q = srv.home / "fake-engine" / "queue"
    q.mkdir(parents=True, exist_ok=True)
    (q / f"{time.time_ns()}.json").write_text(json.dumps({**script, "name": name}), encoding="utf-8")


def actions_block(actions: list) -> str:
    """The product's actions block, as its engine contract asks for (scripts/agent.py reads a fenced json block)."""
    return "\n\n```json\n" + json.dumps({"actions": actions}, indent=1) + "\n```"


def chat_rows(project_dir: pathlib.Path) -> list[dict]:
    rows = []
    for f in sorted((project_dir / "chats").glob("*.jsonl")):
        rows += seed.read_jsonl(f)
    return rows


def result(status_ok: bool, measured, expected: str, detail: str = "", evidence=None):
    from lib import Result
    return Result("pass" if status_ok else "fail", measured=measured, expected=expected, detail=detail,
                  evidence=evidence or [])
