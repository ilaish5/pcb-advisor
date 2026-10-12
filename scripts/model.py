"""
The model: the project's logs -> one dict the UI and the agent both read.

Nothing here decides anything. store.py folds the logs; this file puts the
pieces side by side (idea, BOM, sheets, library, sources, conversations).
"""
import hashlib
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import project as project_mod  # noqa: E402
import session as session_mod  # noqa: E402
import store                   # noqa: E402
import workspace               # noqa: E402

CITE = re.compile(r"\{\{src:([^|}]+)(?:\|([^}]*))?\}\}")
REF = re.compile(r"\{\{ref:([^}]+)\}\}")


def project_dir(name=None):
    return workspace.project_dir(name)


load_jsonl = store.read_jsonl
load_idea = store.load_idea


def save_idea(project, idea):
    return store.save_idea(project, idea)


def list_projects():
    return project_mod.list_all()


def create_project(name):
    return project_mod.create(name)


# ---------------------------------------------------------------- sources

def _size(n):
    return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"


def _kind(name):
    return (pathlib.Path(name).suffix.lstrip(".") or "file").upper()


def citations(project):
    """{source name: [where it was cited]} from chats and proposals."""
    out = {}
    for row in session_mod.list_all(project):
        for m in session_mod.load_chat(project, row["id"]):
            for name, loc in CITE.findall(m.get("text", "")):
                out.setdefault(name.strip(), []).append((loc or "").strip())
    for p in store.proposals(project):
        for name in p.get("sources", []):
            out.setdefault(name, []).append("proposal " + p["line"])
    return out


def _host(url):
    parts = (url or "").split("/")
    return parts[2] if len(parts) > 2 else ""


def list_sources(project):
    """Shared library + project sources. A document is a file with a .json sidecar
    (url, sha256, bytes); a sidecar alone still lists, flagged as not present."""
    cites = citations(project)
    rows = []
    for scope, d in (("shared", workspace.datasheets_dir()), ("project", project_dir(project) / "sources")):
        if not d.exists():
            continue
        names = {}
        for f in d.iterdir():
            if f.name.startswith(".") or f.suffix == ".txt":
                continue
            base = f.name
            if f.suffix == ".json" and pathlib.Path(f.name[:-5]).suffix:
                base = f.name[:-5]          # a sidecar: name.pdf.json -> name.pdf
            names[base] = True
        for name in sorted(names):
            path = d / name
            meta_path = d / (name + ".json")
            meta = {}
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    meta = {}
            present = path.exists() and path.is_file()
            sha = meta.get("sha256") or (hashlib.sha256(path.read_bytes()).hexdigest() if present and path.stat().st_size < 50_000_000 else "")
            used = cites.get(name, [])
            rows.append({
                "name": name, "scope": scope, "kind": _kind(name), "present": present,
                "size": _size(path.stat().st_size) if present else (_size(meta["bytes"]) if meta.get("bytes") else "—"),
                "origin": meta.get("origin") or _host(meta.get("url")) or "uploaded",
                "url": meta.get("url"), "sha256": sha[:8] if sha else "—",
                "text": (d / (name + ".txt")).exists() or (path.suffix in (".md", ".txt") and present),
                "used_for": f"{len(used)} citation{'s' if len(used) != 1 else ''}" + (f" · {used[0]}" if used and used[0] else "") if used else "—",
            })
    return rows


# ---------------------------------------------------------------- anchors, sheets

def anchors(project=None):
    """Everything a conversation can be anchored to: a refdes or a sheet id."""
    out = {}
    for line in store.bom_lines(project):
        for ref in line.get("refs", []):
            out[ref] = {"kind": "part", "label": ref, "line": line["key"]}
    for sid in store.sheet_ids(project):
        out[sid] = {"kind": "sheet", "label": f"Sheet {sid}"}
    return out


def sheets(project):
    out = []
    for sid in store.sheet_ids(project):
        s = store.load_sheet(project, sid)
        out.append({"id": sid, "title": s.get("title", ""),
                    "sections": s.get("sections", []),
                    "parts": {p["ref"]: {"section": p.get("section"),
                                         "nets": store.nets_of(project, p["ref"])}
                              for p in s.get("parts", [])}})
    link = project_mod.altium_link(project)
    if link.get("project_file"):
        pf = pathlib.Path(link["project_file"])
        if pf.is_file():
            try:
                from altium.prjpcb import read_prjpcb
                prj_info = read_prjpcb(pf)
                for s in prj_info.get("sheets", []):
                    s_name = pathlib.Path(s.replace("\\", "/")).name
                    s_stem = pathlib.Path(s.replace("\\", "/")).stem
                    if not any(x["id"] in (s_name, s_stem) for x in out):
                        out.append({"id": s_stem, "title": s_stem, "sections": [], "parts": {}, "altium": True, "file": s_name})
            except Exception:
                pass
    return out


def part_context(project, ref):
    """What the agent knows about one part. Built here, so any agent gets the same card."""
    line = next((l for l in store.bom(project, write=False) if ref in l.get("refs", [])), None)
    if not line:
        return None
    where = []
    for sid in store.sheet_ids(project):
        sheet = store.load_sheet(project, sid)
        titles = {s["id"]: s.get("title", "") for s in sheet.get("sections", [])}
        for p in sheet.get("parts", []):
            if p["ref"] == ref:
                where.append({"sheet": sid, "block": p.get("section"), "title": titles.get(p.get("section"), "")})
    return {"ref": ref, "line": line["key"], "mpn": line.get("mpn"), "value": line.get("value"),
            "manufacturer": line.get("manufacturer"), "package": line.get("package"),
            "description": line.get("description"), "datasheet": line.get("datasheet"),
            "refs": line.get("refs", []), "where": where,
            "nets": sorted({n for r in line.get("refs", []) for n in store.nets_of(project, r)}), "library": line.get("library"),
            "note": line.get("note"), "role": line.get("role", ""), "availability": line.get("availability"),
            "library_type": line.get("library_type"), "risk": line.get("risk", [])}


# ---------------------------------------------------------------- build

def build(project=None, session=None):
    project = workspace.safe_name(project or workspace.default_project())
    pdir = project_dir(project)
    meta = project_mod.load_meta(project)
    sess = session_mod.current(project, session)
    idea = store.load_idea(project)
    lines = store.bom(project)
    tot = store.totals(lines)
    props = store.proposals(project)
    sessions = session_mod.list_all(project)
    import preview_pcb
    placement_plan = preview_pcb.load_placement_plan(project)
    return {
        "project": project,
        "title": meta.get("title") or project,
        "meta": meta,
        "board": {**workspace.get("engineering_defaults", {}), **(meta.get("board") or {})},
        "idea": idea,
        "placement_plan": placement_plan,
        "bom": lines,
        "totals": tot,
        "proposals": props,
        "sheets": sheets(project),
        "library": store.library_view(project),
        "sources": list_sources(project),
        "chat": session_mod.load_chat(project, sess),
        "session": sess,
        "sessions": sessions,
        "memory": session_mod.read_memory(project, sess),
        "progress": {
            "pending_proposals": sum(1 for p in props if p["status"] == "pending"),
            "to_verify": tot["to_verify"], "out_of_stock": tot["out_of_stock"],
        },
    }


def write(project=None, session=None):
    m = build(project, session)
    pdir = project_dir(m["project"])
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "design-model.json").write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    return m


if __name__ == "__main__":
    import oscompat
    oscompat.utf8_stdio()
    print(json.dumps(build(sys.argv[1] if len(sys.argv) > 1 else None), ensure_ascii=False, indent=2))
