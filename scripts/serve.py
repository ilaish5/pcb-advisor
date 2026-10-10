"""
Renderer + the single writer.

All reasoning lives in model.py; all knowledge lives in cascade/ and sources/.
This file reads state, appends to it, and applies agent actions.  Keeping one
writer is what stops the two-sources-of-truth failure.

Nothing here is hardcoded: ports, paths, the default project and which LLM
engine to route to all come from config.json (see scripts/workspace.py).

    python3 pcb.py serve [--project NAME] [--port N] [--engine ID]
"""
import argparse
import base64
import datetime as dt
import json
import pathlib
import re
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import agent             # noqa: E402
import gateway           # noqa: E402
import model             # noqa: E402
import project as project_mod  # noqa: E402
import session as session_mod  # noqa: E402
import sources           # noqa: E402
import workspace         # noqa: E402

BACKEND = None            # set at startup; None means "whatever config says"
DEFAULT_PROJECT = None


def now():
    return dt.datetime.now().isoformat(timespec="seconds")


def append(project, filename, record):
    """decisions.jsonl and threads.jsonl - the design, shared by every session."""
    path = model.project_dir(project) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    project_mod.touch(project)          # so the project list sorts by real activity


def say(project, sess, record):
    """One conversation's log."""
    session_mod.append(project, sess, record)
    project_mod.touch(project)


def block_context(m, block_id):
    """Everything we know about one block, for a question asked about it.
    Built here rather than in the browser, so any agent driving the folder gets
    the same context."""
    b = next((x for x in m.get("blocks", []) if x["id"] == block_id), None)
    if not b:
        return None
    links = m.get("links") or []
    ctx = {
        "id": b["id"], "label": b.get("label"), "kind": b.get("kind"),
        "came_from": b.get("from"),
        "fed_by": [s for s, t in links if t == block_id],
        "feeds": [t for s, t in links if s == block_id],
    }
    if b.get("by"):
        ctx["added_by_decision"] = b["by"]
    # which domain this kind pulls in, and what is already locked because of it
    ctx["loads_domains"] = sorted(
        {d for d, c in model.load_cascades().items()
         if b.get("kind") in (c.get("blocks") or [])})
    ctx["constraints_from_those"] = [
        {"id": c["id"], "text": c["text"]} for c in m.get("constraints", [])
        if c.get("element") in ctx["loads_domains"]][:6]
    return ctx


def compact_if_due(project, sess):
    """Rewrite this session's memory when enough has happened. A separate call,
    so it never competes with answering the student."""
    due, _ = session_mod.due_for_compaction(project, sess)
    if not due:
        return None
    res = agent.compact(model.build(project=project, session=sess), project, sess,
                        backend=BACKEND)
    if not res.get("ok"):
        print(f"(memory not rewritten: {res.get('reason')})")
    return res


# What the browser may see and set. The rest of the config belongs to whoever
# runs the tool, not to the student sitting in front of it.
SETTABLE = (
    "user.language", "user.units", "user.show_unverified", "user.name",
    "user.theme", "agent.provider", "agent.model", "agent.memory_every",
    "agent.memory_max_chars", "agent.history_messages",
    "server.default_project",
)


def _public_config():
    cfg = workspace.load(reload=True)
    agent_cfg = cfg.get("agent", {})
    return {
        "user": cfg.get("user", {}),
        # whether the knowledge this tool is answering from has been authored or
        # is still the shipped demonstration. Not settable from the browser: a
        # student must not be able to dismiss it, and it is not theirs to change
        "corpus": cfg.get("corpus", {}),
        "engineering_defaults": cfg.get("engineering_defaults", {}),
        "agent": {**{k: v for k, v in agent_cfg.items() if k != "providers"},
                  "model": (agent_cfg.get("providers", {})
                            .get(gateway.resolve(BACKEND), {}).get("model", ""))},
        "server": {"default_project": DEFAULT_PROJECT or workspace.default_project()},
        "engine": gateway.resolve(BACKEND),
        "engines": gateway.describe_all(),
        "home": str(workspace.home()),
        "config_file": str(workspace.config_path()),
        "settable": list(SETTABLE),
    }


def redraw(project):
    """The drawing stack is optional. A decision must never be lost to a bad
    picture - or to schemdraw not being installed."""
    try:
        import render_schematic
    except ImportError as exc:
        print(f"(no diagram: {exc}. pip install -r requirements.txt)")
        return
    try:
        render_schematic.render(project)
    except Exception as exc:
        print(f"render failed: {exc}")


def _checked_value(project, node_id, raw, m=None):
    """(value, error). A question that asks for a number gets one checked here,
    because decisions.jsonl is append-only and nothing edits it afterwards."""
    m = m or model.build(project=project)
    node = next((n for n in m["open"] + m["answered"] + m["blocked"]
                 if n["id"] == node_id), None)
    spec = model.quantity_spec(node) if node else None
    return model.coerce_quantity(spec, raw) if spec else (raw, None)


def apply_actions(project, actions):
    """The server is the only writer. Agents propose; this applies."""
    applied = []
    for a in actions or []:
        kind = a.get("type")
        if kind == "idea.propose":
            idea = model.load_idea(model.project_dir(project))
            # simple mock apply for now
            applied.append("idea.propose")
        elif kind == "idea.confirm":
            idea = model.load_idea(model.project_dir(project))
            idea["confirmed"] = True
            model.save_idea(project, idea)
            applied.append("idea.confirm")
        elif kind == "bom.propose":
            append(project, "bom-log.jsonl", {
                "ts": now(), "by": "agent-approved", "line": a.get("line"), 
                "changes": a.get("changes", {}), "reason": a.get("reason"), "sources": a.get("sources", [])
            })
            applied.append(f"bom.propose:{a.get('line')}")
        elif kind == "netlist.write":
            # write netlist
            sheet = a.get("sheet")
            if sheet:
                pdir = model.project_dir(project)
                ndir = pdir / "netlist"
                ndir.mkdir(parents=True, exist_ok=True)
                (ndir / f"{sheet}.json").write_text(json.dumps(a.get("data", {}), ensure_ascii=False, indent=2), encoding="utf-8")
            applied.append(f"netlist.write:{sheet}")
        elif kind == "library.add":
            applied.append("library.add")
        elif kind == "thread.open" and a.get("anchor") and a.get("text"):
            append(project, "threads.jsonl", {"ts": now(), "anchor": a["anchor"], "role": "agent", "text": a["text"]})
            applied.append(f"thread.open:{a['anchor']}")
        elif kind in ("ask", "sheet") and a.get("anchor") and a.get("text"):
            append(project, "threads.jsonl", {"ts": now(), "anchor": a["anchor"], "role": "agent", "text": a["text"]})
            applied.append(f"ask:{a['anchor']}")
    if applied:
        redraw(project)
    return applied


QUIET = False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        """One line per request, unless --quiet.

        This used to be a bare `pass`. A rejected write then produced no trace
        anywhere: not in the browser, which swallowed it, and not in the
        terminal, which said nothing. There was no way to tell whether a request
        had been sent, refused, or dropped - which is a long way to go to keep a
        terminal tidy.
        """
        if QUIET:
            return
        line = (fmt % args) if args else str(fmt)
        # the UI polls /api/state every three seconds; logging that would bury
        # everything else within a minute
        if "/api/state" in line and " 200 " in line:
            return
        sys.stderr.write(f"  {dt.datetime.now().strftime('%H:%M:%S')}  {line}\n")

    def project(self):
        q = parse_qs(urlparse(self.path).query)
        name = (q.get("project") or [DEFAULT_PROJECT or workspace.default_project()])[0]
        return workspace.safe_name(name)

    def session(self, project):
        q = parse_qs(urlparse(self.path).query)
        return session_mod.current(project, (q.get("session") or [None])[0])

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False)
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # ---------------------------------------------------------------- read
    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self._send(200, (workspace.ui_dir() / "index.html").read_text(encoding="utf-8"),
                              "text/html; charset=utf-8")
        if path == "/api/projects":
            return self._send(200, {"projects": model.list_projects(),
                                    "default": DEFAULT_PROJECT or workspace.default_project()})
        if path == "/api/state":
            proj = self.project()
            m = model.build(project=proj, session=self.session(proj))
            m["backend"] = gateway.resolve(BACKEND)
            m["engine"] = gateway.resolve(BACKEND)
            return self._send(200, m)
        if path == "/api/sessions":
            proj = self.project()
            return self._send(200, {"sessions": session_mod.list_all(proj),
                                    "current": self.session(proj)})
        if path == "/api/config":
            return self._send(200, _public_config())
        if path == "/api/schematic.svg":
            proj = self.project()
            svg = model.project_dir(proj) / "artifacts" / "blocks.svg"
            if not svg.exists():
                redraw(proj)
            return self._send(200, svg.read_text(encoding="utf-8"),
                              "image/svg+xml; charset=utf-8")
        if path.startswith("/api/source/"):
            name = unquote(path.split("/api/source/", 1)[1])
            for base in (model.project_dir(self.project()) / "sources",
                         workspace.datasheets_dir()):
                f = base / pathlib.Path(name).name
                if f.exists():
                    ctype = "application/pdf" if f.suffix == ".pdf" else "text/plain; charset=utf-8"
                    return self._send(200, f.read_bytes(), ctype)
            return self._send(404, {"error": "not in the library"})
        return self._send(404, {"error": "not found"})

    # ---------------------------------------------------------------- write
    def do_POST(self):
        path = self.path.split("?")[0]
        proj = self.project()
        sess = self.session(proj)

        n = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, {"error": "bad json"})

        
        if path == "/api/idea":
            idea = model.load_idea(model.project_dir(proj))
            idea["blocks"] = data.get("blocks", idea.get("blocks", []))
            idea["links"] = data.get("links", idea.get("links", []))
            model.save_idea(proj, idea)
            redraw(proj)
            return self._send(200, model.build(project=proj, session=sess))

        if path == "/api/message":
            if not data.get("anchor") or not data.get("text"):
                return self._send(400, {"error": "anchor and text required"})
            # an unchecked anchor is an invisible orphan forever: one typo and
            # the thread never appears beside anything again
            if data["anchor"] not in model.anchors(proj):
                return self._send(400, {"error": f"no such anchor: {data['anchor']}"})
            append(proj, "threads.jsonl", {"ts": now(), "anchor": data["anchor"],
                                           "role": data.get("role", "user"), "text": data["text"]})
            out = model.build(project=proj, session=sess)
            # a question from the student is answered by the agent, in the same turn
            if data.get("role", "user") == "user" and data.get("ask_agent", True):
                res = agent.respond(out, f"[question about {data['anchor']}] {data['text']}",
                                    out["chat"], backend=BACKEND)
                # An `ask` anchored to the thread being answered lands on the
                # same anchor as the reply, so one question produced two agent
                # lines with the same timestamp, answering it in contradictory
                # terms. The reply IS the answer here; the anchor is redundant.
                actions = [a for a in (res.get("actions") or [])
                           if not (a.get("type") == "ask"
                                   and a.get("anchor") == data["anchor"])]
                applied = apply_actions(proj, actions)
                if res.get("reply"):
                    append(proj, "threads.jsonl", {"ts": now(), "anchor": data["anchor"],
                                                   "role": "agent", "text": res["reply"]})
                out = model.build(project=proj, session=sess)
                out["last_actions"] = applied
            return self._send(200, out)

        if path == "/api/thread/resolve":
            if not data.get("anchor"):
                return self._send(400, {"error": "anchor required"})
            # A reason is required. Closing used to write an empty line, so a
            # thread recording a real contradiction could be dismissed in one
            # click, permanently, with no record of what was concluded - the
            # exact loss anchoring exists to prevent.
            why = (data.get("text") or "").strip()
            if not why:
                return self._send(400, {"error": "say what settled it"})
            append(proj, "threads.jsonl", {"ts": now(), "anchor": data["anchor"],
                                           "role": "resolved", "text": why})
            return self._send(200, model.build(project=proj, session=sess))

        if path == "/api/chat":
            text = (data.get("text") or "").strip()
            if not text:
                return self._send(400, {"error": "text required"})
            block = data.get("block")
            say(proj, sess, {"ts": now(), "role": "user", "text": text,
                             **({"block": block} if block else {})})
            m = model.build(project=proj, session=sess)
            ask = text
            if block:
                ctx = block_context(m, block)
                if ctx:
                    ask = (f"[the student is asking about one block of their diagram]\n"
                           f"{json.dumps(ctx, ensure_ascii=False, indent=2)}\n\n{text}")
            res = agent.respond(m, ask, m["chat"], backend=BACKEND)
            applied = apply_actions(proj, res.get("actions"))
            if res.get("reply"):
                say(proj, sess, {"ts": now(), "role": "agent", "text": res["reply"],
                                 "applied": applied})
            compact_if_due(proj, sess)
            out = model.build(project=proj, session=sess)
            out["last_actions"] = applied
            return self._send(200, out)

        if path == "/api/config":
            changes = data.get("set") or {}
            bad = [k for k in changes if k not in SETTABLE]
            if bad:
                return self._send(400, {"error": f"not settable from here: {', '.join(bad)}"})
            # a model name belongs to one engine - a Gemini id sent to Claude
            # fails the turn - so it is stored under whichever engine is current,
            # and the engine is switched first when both arrive together
            for key in sorted(changes, key=lambda k: k != "agent.provider"):
                value = changes[key]
                if key == "agent.model":
                    key = f"agent.providers.{gateway.resolve(BACKEND)}.model"
                workspace.set_value(key, value)
            return self._send(200, {"config": _public_config()})

        if path == "/api/sessions/new":
            created = session_mod.create(proj, title=data.get("title"))
            return self._send(200, {"created": created,
                                    "sessions": session_mod.list_all(proj)})

        if path == "/api/sessions/rename":
            if not data.get("title"):
                return self._send(400, {"error": "title required"})
            session_mod.rename(proj, sess, data["title"])
            return self._send(200, {"sessions": session_mod.list_all(proj)})

        if path == "/api/sessions/delete":
            # the design survives; only this conversation goes
            session_mod.delete(proj, data.get("session") or sess)
            return self._send(200, {"sessions": session_mod.list_all(proj),
                                    "current": session_mod.current(proj)})

        if path == "/api/memory":
            # the student may correct their own memory file by hand
            if data.get("text") is None:
                res = agent.compact(model.build(project=proj, session=sess), proj, sess,
                                    backend=BACKEND)
                return self._send(200, {"rewritten": res,
                                        "memory": session_mod.read_memory(proj, sess)})
            text, trimmed = session_mod.fit(data["text"])
            session_mod.write_memory(proj, sess, text)
            return self._send(200, {"memory": text, "trimmed": trimmed})

        if path == "/api/bom":
            text = data.get("text") or ""
            (model.project_dir(proj) / "BOM.md").write_text(text, encoding="utf-8")
            return self._send(200, {"bom": text})

        if path == "/api/projects/new":
            name = (data.get("name") or "").strip() or "untitled"
            created = project_mod.create(name, title=data.get("title") or name,
                                     brief=data.get("brief", ""))
            redraw(created)
            return self._send(200, {"created": created,
                                    "projects": model.list_projects()})

        if path == "/api/projects/delete":
            name = (data.get("name") or "").strip()
            if not name:
                return self._send(400, {"error": "name required"})
            
            import shutil
            proj_dir = model.project_dir(name)
            if proj_dir.exists():
                shutil.rmtree(proj_dir)
            
            projects = model.list_projects()
            default = projects[0]["name"] if projects else "demo"
            return self._send(200, {"deleted": name, "projects": projects, "default": default})

        if path == "/api/project/meta":
            # title, status, tags, and this board's engineering settings
            meta = project_mod.load_meta(proj)
            for key in ("title", "brief", "status", "tags", "notes"):
                if key in data:
                    meta[key] = data[key]
            if isinstance(data.get("board"), dict):
                meta["board"] = {**(meta.get("board") or {}), **data["board"]}
            project_mod.save_meta(proj, meta)
            project_mod.touch(proj)
            return self._send(200, model.build(project=proj))

        if path == "/api/upload":
            # base64 in JSON rather than multipart: the stdlib cgi module was
            # removed in 3.13, and a datasheet is small enough not to care.
            # also strip what Windows refuses in a file name (: ? * " < > |)
            name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", pathlib.Path(data.get("name") or "upload.bin").name)
            blob = data.get("data_b64")
            if not blob:
                return self._send(400, {"error": "data_b64 required"})
            dest = model.project_dir(proj) / "sources"
            dest.mkdir(parents=True, exist_ok=True)
            target = dest / name
            target.write_bytes(base64.b64decode(blob))
            target.with_suffix(target.suffix + ".json").write_text(json.dumps(
                {"name": name, "url": None, "uploaded_at": now(),
                 "origin": "uploaded by the student"}, indent=2), encoding="utf-8")
            return self._send(200, model.build(project=proj, session=sess))

        if path == "/api/fetch_source":
            url = data.get("url")
            if not url:
                return self._send(400, {"error": "url required"})
            try:
                meta = sources.fetch(url, data.get("name"))
                sources.use(proj, meta["name"])
            except Exception as exc:
                return self._send(200, {"error": f"could not fetch: {exc}"})
            return self._send(200, model.build(project=proj, session=sess))

        if path == "/api/delete_source":
            name = data.get("name")
            if not name:
                return self._send(400, {"error": "name required"})
            sources.unuse(proj, name)
            return self._send(200, model.build(project=proj, session=sess))

        return self._send(404, {"error": "not found"})


def main(argv=None):
    global BACKEND, DEFAULT_PROJECT, QUIET

    cfg = workspace.load()
    ap = argparse.ArgumentParser(prog="serve", description="pcb-advisor server")
    ap.add_argument("project", nargs="?", help="project to open (default: from config)")
    ap.add_argument("port", nargs="?", type=int, help="port (default: from config)")
    ap.add_argument("engine", nargs="?", help="LLM engine id (default: from config)")
    ap.add_argument("--project", dest="project_opt")
    ap.add_argument("--port", dest="port_opt", type=int)
    ap.add_argument("--engine", "--backend", dest="engine_opt")
    ap.add_argument("--host", dest="host_opt")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--quiet", action="store_true",
                    help="do not log requests (the old behaviour)")
    a = ap.parse_args(argv)
    QUIET = a.quiet

    DEFAULT_PROJECT = workspace.safe_name(
        a.project_opt or a.project or cfg["server"]["default_project"])
    port = a.port_opt or a.port or int(cfg["server"]["port"])
    host = a.host_opt or cfg["server"]["host"]
    # If the user explicitly asks for an engine, use it. Otherwise, None means
    # "read from config dynamically", so settings changes apply without restart.
    BACKEND = a.engine_opt or a.engine

    for key in workspace.unknown_keys():
        print(f"  warning: unknown config key {key}")

    project_mod.ensure(DEFAULT_PROJECT)
    redraw(DEFAULT_PROJECT)

    url = f"http://{host}:{port}"
    _engine = gateway.resolve(BACKEND)
    ok, why = gateway.provider(_engine).available()
    print(f"pcb-advisor  home={workspace.home()}  project={DEFAULT_PROJECT}")
    print(f"             engine={_engine}" + ("" if ok else f"  (unavailable: {why})"))
    print(f"             {url}")
    if not QUIET:
        print("             logging requests; --quiet turns this off")

    if cfg["server"].get("open_browser") and not a.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        ThreadingHTTPServer((host, port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
