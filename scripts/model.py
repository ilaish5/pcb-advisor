"""
The engine. state (what happened) -> design model.
"""
import json
import pathlib
import sys
import datetime as dt

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import project as project_mod
import session as session_mod
import workspace
import sources as sources_mod

def project_dir(name=None):
    return workspace.project_dir(name)

def load_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]

def load_idea(pdir):
    path = pdir / "idea.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    # migrate from sketch.json if it exists
    old_path = pdir / "sketch.json"
    if old_path.exists():
        old = json.loads(old_path.read_text(encoding="utf-8"))
        idea = {
            "goal": old.get("brief", ""),
            "agreed": [],
            "blocks": old.get("blocks", []),
            "links": old.get("links", []),
            "confirmed": old.get("confirmed", False)
        }
        save_idea(pdir.name, idea)
        old_path.unlink()
        return idea
    return {"goal": "", "agreed": [], "blocks": [], "links": [], "confirmed": False}

def save_idea(project, idea):
    pdir = project_dir(project)
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "idea.json").write_text(json.dumps(idea, ensure_ascii=False, indent=2), encoding="utf-8")

def anchors(project=None):
    pdir = project_dir(project)
    out = {}
    
    # BOM lines
    bom = load_bom(project)
    for line in bom:
        for ref in line.get("refs", []):
            out[ref] = {"kind": "part", "label": ref}
            
    # sheets
    for f in (pdir / "netlist").glob("*.json"):
        sheet_id = f.stem
        out[sheet_id] = {"kind": "sheet", "label": f"Sheet {sheet_id}"}
        
    return out

def load_bom(project):
    pdir = project_dir(project)
    log_path = pdir / "bom-log.jsonl"
    bom = {}
    if log_path.exists():
        for change in load_jsonl(log_path):
            line_key = change.get("line")
            if line_key:
                if "changes" in change:
                    if line_key not in bom:
                        bom[line_key] = {}
                    bom[line_key].update(change["changes"])
    
    # Save derived bom.json
    bom_list = list(bom.values())
    (pdir / "bom.json").write_text(json.dumps(bom_list, ensure_ascii=False, indent=2), encoding="utf-8")
    return bom_list

def list_sources(project):
    out = []
    for scope, d in (("project", project_dir(project) / "sources"),
                     ("shared", workspace.datasheets_dir())):
        if not d.exists():
            continue
        for f in sorted(d.iterdir()):
            if f.name.startswith(".") or f.suffix in (".json", ".txt"):
                continue
            meta_path = f.with_suffix(f.suffix + ".json")
            meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
            out.append({"name": f.name, "scope": scope, "size": f.stat().st_size, **meta})
    return out

def list_projects():
    return project_mod.list_all()

def create_project(name):
    return project_mod.create(name)

def build(project=None, session=None):
    project = workspace.safe_name(project or workspace.default_project())
    pdir = project_dir(project)
    meta = project_mod.load_meta(project)
    
    messages = load_jsonl(pdir / "threads.jsonl")
    sess = session_mod.current(project, session)
    chat = session_mod.load_chat(project, sess)
    idea = load_idea(pdir)
    
    known = anchors(project)
    threads = {}
    for m in sorted(messages, key=lambda m: m.get("ts", "")):
        threads.setdefault(m["anchor"], []).append(m)

    for anchor, msgs in threads.items():
        meta_a = known.get(anchor, {"kind": "unknown", "label": anchor})
        closing = [m for m in msgs if m.get("role") == "resolved"]
        resolved = bool(closing)
        said = [m for m in msgs if m.get("role") in ("user", "agent")]
        last = said[-1].get("role") if said else None
        threads[anchor] = {
            "anchor": anchor,
            "kind": meta_a["kind"],
            "label": meta_a["label"],
            "messages": msgs,
            "resolved": resolved,
            "resolution": (closing[-1].get("text") or "").strip() if closing else "",
            "waiting_on": None if resolved else {"user": "agent", "agent": "student"}.get(last),
        }

    return {
        "project": project,
        "title": meta.get("title") or project,
        "meta": meta,
        "board": {**workspace.get("engineering_defaults", {}), **(meta.get("board") or {})},
        "idea": idea,
        "threads": threads,
        "chat": chat,
        "session": sess,
        "sessions": session_mod.list_all(project),
        "memory": session_mod.read_memory(project, sess),
        "bom": load_bom(project),
        "sources": list_sources(project),
        "progress": {
            "waiting_on_agent": sum(1 for t in threads.values() if t["waiting_on"] == "agent"),
            "waiting_on_student": sum(1 for t in threads.values() if t["waiting_on"] == "student"),
            "threads": len(threads),
        },
    }

def write(project=None, session=None):
    m = build(project, session)
    pdir = project_dir(m["project"])
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "design-model.json").write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    return m

