"""
Project lifecycle: create from the template, list, read and write project.json.

A project is a folder and nothing else - no database, no index, no registry.
Drop a folder into projects/ and it is a project; zip one up and mail it and it
still works.  `ensure()` repairs a folder that is missing pieces, which is what
makes a hand-made folder as valid as a generated one.
"""
import datetime as dt
import json
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import session  # noqa: E402
import workspace  # noqa: E402

SCHEMA_VERSION = 1
# the design log. The conversation lives in chats/<id>.jsonl, one per session.
STATE_FILES = ("decisions.jsonl", "threads.jsonl")
DERIVED = ("design-model.json", "constraints.md", "artifacts")


def now():
    return dt.datetime.now().isoformat(timespec="seconds")


def template_dir():
    return workspace.templates_dir() / "project"


def dir_of(name):
    return workspace.project_dir(name)


def meta_path(name):
    return dir_of(name) / "project.json"


def exists(name):
    return dir_of(name).is_dir()


# ---------------------------------------------------------------- create

def create(name, title=None, brief=""):
    """Instantiate the template under a free name. Returns the name used."""
    safe = _free_name(workspace.safe_name(name))
    dest = dir_of(safe)
    src = template_dir()
    if not src.is_dir():
        raise SystemExit(f"project template missing: {src}")

    shutil.copytree(src, dest)
    (dest / "sources").mkdir(exist_ok=True)
    (dest / "chats").mkdir(exist_ok=True)

    fills = {
        "__NAME__": safe,
        "__TITLE__": title or name or safe,
        "__BRIEF__": brief,
        "__NOW__": now(),
        "__OWNER__": workspace.get("user.name", "") or "",
    }
    for path in (dest / "project.json", dest / "README.md"):
        if path.exists():
            text = path.read_text(encoding="utf-8")
            for token, value in fills.items():
                text = text.replace(token, _escape(value, path.suffix))
            path.write_text(text, encoding="utf-8")

    session.create(safe, title="First conversation")

    meta = load_meta(safe)
    meta["schema_version"] = SCHEMA_VERSION
    # the board starts as a copy of your engineering defaults, then diverges
    meta["board"] = {**workspace.get("engineering_defaults", {}), **(meta.get("board") or {})}
    save_meta(safe, meta)
    return safe


def _escape(value, suffix):
    return json.dumps(value, ensure_ascii=False)[1:-1] if suffix == ".json" else value


def _free_name(safe):
    if not dir_of(safe).exists():
        return safe
    n = 2
    while dir_of(f"{safe}-{n}").exists():
        n += 1
    return f"{safe}-{n}"


def ensure(name):
    """Make an existing folder a complete project. Never destroys anything."""
    d = dir_of(name)
    d.mkdir(parents=True, exist_ok=True)
    (d / "sources").mkdir(exist_ok=True)
    (d / "chats").mkdir(exist_ok=True)
    for f in STATE_FILES:
        (d / f).touch()
    if not session.list_all(name):
        session.create(name, title="First conversation")
    if not (d / "sketch.json").exists():
        (d / "sketch.json").write_text(json.dumps(
            {"brief": "", "blocks": [], "links": [], "confirmed": False},
            ensure_ascii=False, indent=2), encoding="utf-8")
    if not meta_path(name).exists():
        save_meta(name, {
            "schema_version": SCHEMA_VERSION,
            "name": workspace.safe_name(name),
            "title": name,
            "brief": "",
            "created": now(),
            "updated": now(),
            "owner": workspace.get("user.name", "") or "",
            "status": "draft",
            "tags": [],
            "board": dict(workspace.get("engineering_defaults", {})),
            "notes": "",
        })
    return workspace.safe_name(name)


# ---------------------------------------------------------------- metadata

def load_meta(name):
    path = meta_path(name)
    if not path.exists():
        return {"name": workspace.safe_name(name), "title": name, "board": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"name": workspace.safe_name(name), "title": name, "board": {},
                "error": "project.json is not valid JSON"}


def save_meta(name, meta):
    path = meta_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def touch(name, **fields):
    """Stamp `updated`, and set any fields passed along with it."""
    meta = load_meta(name)
    meta.update(fields)
    meta["updated"] = now()
    save_meta(name, meta)
    return meta


def board(name):
    """This board's engineering settings, with the global defaults underneath."""
    return {**workspace.get("engineering_defaults", {}), **(load_meta(name).get("board") or {})}


# ---------------------------------------------------------------- listing

def _lines(path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def list_all():
    """Every project in the workspace, newest activity first."""
    root = workspace.projects_dir()
    root.mkdir(parents=True, exist_ok=True)
    out = []
    for d in root.iterdir():
        if not d.is_dir() or d.name.startswith("."):
            continue
        meta = load_meta(d.name)
        sketch = {}
        if (d / "sketch.json").exists():
            try:
                sketch = json.loads((d / "sketch.json").read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                sketch = {}
        decisions = _lines(d / "decisions.jsonl")
        sessions = session.list_all(d.name)
        chat = _lines(session.chat_path(d.name, sessions[0]["id"])) if sessions else []
        stamps = [e.get("ts", "") for e in decisions + chat if e.get("ts")]
        out.append({
            "name": d.name,
            "title": meta.get("title") or d.name,
            "brief": sketch.get("brief") or meta.get("brief")
                     or (chat[0]["text"][:80] if chat else ""),
            "status": meta.get("status", "draft"),
            "blocks": len(sketch.get("blocks", [])),
            "decisions": len({e["node"] for e in decisions if e.get("node")}),
            "sessions": len(sessions),
            "messages": sum(x.get("messages", 0) for x in sessions),
            "confirmed": bool(sketch.get("confirmed")),
            "updated": max(stamps) if stamps else meta.get("updated", ""),
        })
    out.sort(key=lambda p: p["updated"], reverse=True)
    return out


# ---------------------------------------------------------------- reset

def reset(name):
    """Back to empty. The corpus and your notes are untouched."""
    d = dir_of(name)
    if not d.exists():
        raise SystemExit(f"no such project: {name}")
    for f in ("decisions.jsonl", "threads.jsonl", "design-model.json", "constraints.md"):
        (d / f).unlink(missing_ok=True)
    shutil.rmtree(d / "artifacts", ignore_errors=True)
    shutil.rmtree(d / "chats", ignore_errors=True)
    (d / "sketch.json").write_text(json.dumps(
        {"brief": "", "blocks": [], "links": [], "confirmed": False},
        ensure_ascii=False, indent=2), encoding="utf-8")
    ensure(name)
    touch(name)
    return workspace.safe_name(name)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "new":
        print(create(sys.argv[2] if len(sys.argv) > 2 else "untitled"))
    elif cmd == "reset":
        print(f"reset {reset(sys.argv[2] if len(sys.argv) > 2 else workspace.default_project())}")
    elif cmd == "show":
        print(json.dumps(load_meta(sys.argv[2]), ensure_ascii=False, indent=2))
    else:
        for p in list_all():
            print(f"{p['name']:24} {p['decisions']:>3} decisions  {p['updated']}  {p['brief'][:40]}")
