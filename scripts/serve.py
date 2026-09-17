"""
Renderer + the single writer.

All reasoning lives in model.py; all knowledge lives in cascade/ and sources/.
This file reads state, appends to it, and applies agent actions.  Keeping one
writer is what stops the two-sources-of-truth failure.

    python3 scripts/serve.py [project] [port]
"""
import base64
import datetime as dt
import json
import pathlib
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import agent             # noqa: E402
import model             # noqa: E402
import render_schematic  # noqa: E402
import sources           # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
BACKEND = "claude"
DEFAULT_PROJECT = "demo"


def now():
    return dt.datetime.now().isoformat(timespec="seconds")


def append(project, filename, record):
    path = model.project_dir(project) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def redraw(project):
    try:
        render_schematic.render(project)
    except Exception as exc:            # a decision must never be lost to a bad picture
        print(f"render failed: {exc}")


def apply_actions(project, actions):
    """The server is the only writer. Agents propose; this applies."""
    applied = []
    for a in actions or []:
        kind = a.get("type")
        if kind == "sketch":
            model.save_sketch(project, {
                "brief": a.get("brief", model.load_sketch(model.project_dir(project)).get("brief", "")),
                "blocks": a.get("blocks", []),
                "links": a.get("links", []),
                "confirmed": bool(a.get("confirmed", False)),
            })
            applied.append("sketch")
        elif kind == "answer" and a.get("node") and a.get("value"):
            append(project, "decisions.jsonl", {"ts": now(), "node": a["node"],
                                                "value": a["value"], "by": "agent"})
            applied.append(f"answer:{a['node']}")
        elif kind == "ask" and a.get("anchor") and a.get("text"):
            append(project, "threads.jsonl", {"ts": now(), "anchor": a["anchor"],
                                              "role": "agent", "text": a["text"]})
            applied.append(f"ask:{a['anchor']}")
    if applied:
        redraw(project)
    return applied


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def project(self):
        q = parse_qs(urlparse(self.path).query)
        name = (q.get("project") or [DEFAULT_PROJECT])[0]
        return pathlib.Path(name).name or DEFAULT_PROJECT

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
            return self._send(200, (ROOT / "ui" / "index.html").read_text(encoding="utf-8"),
                              "text/html; charset=utf-8")
        if path == "/api/projects":
            return self._send(200, {"projects": model.list_projects(),
                                    "default": DEFAULT_PROJECT})
        if path == "/api/state":
            m = model.build(project=self.project())
            m["backend"] = BACKEND
            return self._send(200, m)
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
                         ROOT / "shared" / "datasheets"):
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

        n = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, {"error": "bad json"})

        if path == "/api/answer":
            if not data.get("node") or not data.get("value"):
                return self._send(400, {"error": "node and value required"})
            before = {c["id"] for c in model.build(project=proj)["constraints"]}
            append(proj, "decisions.jsonl", {"ts": now(), "node": data["node"],
                                             "value": data["value"], "by": data.get("by", "user")})
            after = model.build(project=proj)
            gained = [c for c in after["constraints"] if c["id"] not in before]
            node = next((n for n in after["answered"] if n["id"] == data["node"]), {})
            opt = next((o for o in node.get("options", []) if o["id"] == data["value"]), {})
            append(proj, "chat.jsonl", {
                "ts": now(), "role": "decision",
                "text": f"{node.get('question', data['node'])}  ->  {opt.get('label', data['value'])}",
                "node": data["node"],
                "locked": [{"id": c["id"], "text": c["text"], "icon": c["icon"],
                            "verified": c["verified"]} for c in gained],
            })
            redraw(proj)
            return self._send(200, model.build(project=proj))

        if path == "/api/message":
            if not data.get("anchor") or not data.get("text"):
                return self._send(400, {"error": "anchor and text required"})
            append(proj, "threads.jsonl", {"ts": now(), "anchor": data["anchor"],
                                           "role": data.get("role", "user"), "text": data["text"]})
            return self._send(200, model.build(project=proj))

        if path == "/api/chat":
            text = (data.get("text") or "").strip()
            if not text:
                return self._send(400, {"error": "text required"})
            append(proj, "chat.jsonl", {"ts": now(), "role": "user", "text": text})
            m = model.build(project=proj)
            res = agent.respond(m, text, m["chat"], backend=BACKEND)
            applied = apply_actions(proj, res.get("actions"))
            if res.get("reply"):
                append(proj, "chat.jsonl", {"ts": now(), "role": "agent", "text": res["reply"],
                                            "applied": applied})
            out = model.build(project=proj)
            out["last_actions"] = applied
            return self._send(200, out)

        if path == "/api/projects/new":
            name = (data.get("name") or "").strip() or "untitled"
            created = model.create_project(name)
            redraw(created)
            return self._send(200, {"created": created,
                                    "projects": model.list_projects()})

        if path == "/api/upload":
            # base64 in JSON rather than multipart: the stdlib cgi module was
            # removed in 3.13, and a datasheet is small enough not to care.
            name = pathlib.Path(data.get("name") or "upload.bin").name
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
            return self._send(200, model.build(project=proj))

        if path == "/api/sketch":
            # the student edited the diagram. Server is still the only writer.
            cur = model.load_sketch(model.project_dir(proj))
            model.save_sketch(proj, {
                "brief": data.get("brief", cur.get("brief", "")),
                "blocks": data.get("blocks", cur.get("blocks", [])),
                "links": data.get("links", cur.get("links", [])),
                "confirmed": bool(data.get("confirmed", cur.get("confirmed", False))),
            })
            if data.get("note"):
                append(proj, "chat.jsonl", {"ts": now(), "role": "user",
                                            "text": data["note"]})
            redraw(proj)
            if data.get("tell_agent"):
                m = model.build(project=proj)
                res = agent.respond(m, data.get("note") or "I edited the sketch.",
                                    m["chat"], backend=BACKEND)
                applied = apply_actions(proj, res.get("actions"))
                if res.get("reply"):
                    append(proj, "chat.jsonl", {"ts": now(), "role": "agent",
                                                "text": res["reply"], "applied": applied})
            return self._send(200, model.build(project=proj))

        if path == "/api/fetch_source":
            url = data.get("url")
            if not url:
                return self._send(400, {"error": "url required"})
            try:
                meta = sources.fetch(url, data.get("name"))
                sources.use(proj, meta["name"])
            except Exception as exc:
                return self._send(200, {"error": f"could not fetch: {exc}"})
            return self._send(200, model.build(project=proj))

        return self._send(404, {"error": "not found"})


if __name__ == "__main__":
    DEFAULT_PROJECT = sys.argv[1] if len(sys.argv) > 1 else "demo"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8931
    BACKEND = sys.argv[3] if len(sys.argv) > 3 else "claude"
    redraw(DEFAULT_PROJECT)
    print(f"pcb-advisor  workspace={ROOT.name}  backend={BACKEND}  "
          f"http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
