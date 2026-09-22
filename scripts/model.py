"""
The engine.  cascade (authored knowledge) + state (what happened) -> design model.

Deterministic: same inputs, same output, every time.  An agent APPENDS to the
state files; it never writes the model.  Everything the UI shows is derived here.
"""
import json
import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import project as project_mod  # noqa: E402
import session as session_mod  # noqa: E402
import workspace  # noqa: E402

PROVENANCE = {
    "computed":   {"icon": "📐", "label": "computed",  "rank": 0},
    "standard":   {"icon": "📘", "label": "standard",  "rank": 1},
    "datasheet":  {"icon": "📄", "label": "datasheet", "rank": 2},
    "convention": {"icon": "⚠",  "label": "convention", "rank": 3},
}


# ---------------------------------------------------------------- loading

def load_cascades():
    """All domains, keyed by domain name."""
    out = {}
    for path in sorted(workspace.cascade_dir().glob("*.yaml")):
        cas = yaml.safe_load(path.read_text(encoding="utf-8"))
        out[cas["domain"]] = cas
    return out


def load_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def anchors(project=None):
    """Every id a thread may hang on: cascade nodes, and every constraint the
    corpus can ever produce - not just the active ones, so a thread survives
    the student changing a decision and the constraint going quiet."""
    out = {}
    for dom, cas in load_cascades().items():
        for node in cas.get("nodes", []):
            out[node["id"]] = {"kind": "node", "domain": dom,
                               "label": node.get("question", node["id"])}
            for opt in node.get("options", []) or []:
                for lock in opt.get("locks", []) or []:
                    out[lock["id"]] = {"kind": "constraint", "domain": dom,
                                       "label": lock.get("text", lock["id"])[:80]}
    return out


def project_dir(name=None):
    return workspace.project_dir(name)


# ---------------------------------------------------------------- building

def build(project=None, session=None):
    project = workspace.safe_name(project or workspace.default_project())
    cascades = load_cascades()
    pdir = project_dir(project)
    meta = project_mod.load_meta(project)
    # decisions and threads are the DESIGN: shared by every conversation.
    # only the chat and its memory belong to one session.
    events = load_jsonl(pdir / "decisions.jsonl")
    messages = load_jsonl(pdir / "threads.jsonl")
    sess = session_mod.current(project, session)
    chat = session_mod.load_chat(project, sess)
    sketch = load_sketch(pdir)

    # which domains are in play, decided by the AGREED block sketch.
    # Nothing loads until the student confirms it - otherwise they get asked
    # cascade questions about a diagram they have not accepted yet.
    active, unmapped = [], []
    for blk in (sketch.get("blocks", []) if sketch.get("confirmed") else []):
        hit = [d for d, c in cascades.items() if blk.get("kind") in (c.get("blocks") or [])]
        if hit:
            active.extend(hit)
        else:
            unmapped.append(blk)
    active = sorted(set(active))

    nodes = []
    for dom in active:
        for n in cascades[dom]["nodes"]:
            nodes.append({**n, "domain": dom})
    index = {n["id"]: n for n in nodes}

    answers = {}
    for ev in events:
        if ev.get("node") in index:
            answers[ev["node"]] = ev            # last write wins

    def available(node):
        """A node is reachable only if its deps are answered AND its guard matches."""
        for dep in node.get("depends_on", []) or []:
            if dep not in answers:
                return False, f"waiting on {dep}"
        for guard_node, guard_val in (node.get("requires") or {}).items():
            got = answers.get(guard_node, {}).get("value")
            if got != guard_val:
                return False, f"only if {guard_node} = {guard_val}"
        return True, None

    open_nodes, blocked, answered, irrelevant = [], [], [], []
    for node in nodes:
        ok, reason = available(node)
        entry = dict(node)
        if node["id"] in answers:
            entry["chosen"] = answers[node["id"]]["value"]
            entry["chosen_by"] = answers[node["id"]].get("by", "?")
            answered.append(entry)
        elif ok:
            open_nodes.append(entry)
        elif reason and reason.startswith("only if"):
            entry["reason"] = reason
            irrelevant.append(entry)            # a guard excluded it - not blocked, just N/A
        else:
            entry["reason"] = reason
            blocked.append(entry)

    constraints, conflicts = [], []
    for node in answered:
        opt = next((o for o in node.get("options", []) if o["id"] == node["chosen"]), None)
        if not opt:
            continue
        for lock in opt.get("locks", []) or []:
            prov = lock.get("provenance", "convention")
            src = lock.get("source") or {}
            constraints.append({
                "id": lock["id"],
                "text": lock["text"],
                "provenance": prov,
                "icon": PROVENANCE.get(prov, PROVENANCE["convention"])["icon"],
                "verified": bool(lock.get("verified", prov == "computed")),
                "source": src,
                "element": node["domain"],
                "from_node": node["id"],
                "from_option": node["chosen"],
                "from_label": opt.get("label", node["chosen"]),
            })
        for cf in opt.get("conflicts", []) or []:
            conflicts.append({
                "a": node["id"], "a_label": opt.get("label", ""),
                "b": cf["with"], "note": cf["note"],
            })

    # only report a conflict once BOTH sides are actually live
    live = {c["id"] for c in constraints} | set(answers)
    conflicts = [c for c in conflicts if c["b"] in live]

    # The student's agreed sketch is the SPINE of the diagram. The cascade adds
    # parts to it; it does not replace it. Seeding base_blocks first would show
    # someone their LiPo and STM32 turning into "J1 DC in -> LOAD" the moment
    # they confirmed - the design they agreed to, thrown away.
    blocks = []
    for b in (sketch.get("blocks", []) if sketch.get("confirmed") else []):
        blocks.append({"id": b["id"], "label": b.get("label") or b["id"],
                       "kind": b.get("kind"), "from": "sketch", "order": 10})
    for dom in active:
        blocks.extend({**b, "from": "cascade"}
                      for b in (cascades[dom].get("base_blocks", []) or []))
    for node in answered:
        opt = next((o for o in node.get("options", []) if o["id"] == node["chosen"]), None)
        if opt:
            blocks.extend({**b, "from": "decision", "by": node["id"]}
                          for b in (opt.get("blocks", []) or []))
    # first writer of an id wins, so a sketched block keeps the student's label
    seen, uniq = {}, []
    for b in blocks:
        if b["id"] in seen:
            seen[b["id"]].update({k: v for k, v in b.items() if k not in seen[b["id"]]})
            continue
        seen[b["id"]] = dict(b)
        uniq.append(seen[b["id"]])
    uniq.sort(key=lambda b: b.get("order", 50))

    # A thread is the SPATIAL axis: everything ever said about one element,
    # whichever conversation it was said in. The chat is the timeline.
    known = anchors(project)
    threads = {}
    for m in sorted(messages, key=lambda m: m.get("ts", "")):
        threads.setdefault(m["anchor"], []).append(m)

    for anchor, msgs in threads.items():
        meta_a = known.get(anchor, {"kind": "unknown", "label": anchor})
        resolved = any(m.get("role") == "resolved" for m in msgs)
        said = [m for m in msgs if m.get("role") in ("user", "agent")]
        last = said[-1].get("role") if said else None
        threads[anchor] = {
            "anchor": anchor,
            "kind": meta_a["kind"],
            "label": meta_a["label"],
            "messages": msgs,
            "resolved": resolved,
            # both directions matter. A question the STUDENT asked and nobody
            # answered is the one that actually gets lost.
            "waiting_on": None if resolved else
                          {"user": "agent", "agent": "student"}.get(last),
        }

    return {
        "project": project,
        "title": meta.get("title") or project,
        "meta": meta,
        "board": {**workspace.get("engineering_defaults", {}), **(meta.get("board") or {})},
        "stage": "sketch" if not sketch.get("confirmed") else "cascade",
        "sketch": sketch,
        "unmapped_blocks": unmapped,
        "domains": active,
        "open": open_nodes,
        "blocked": blocked,
        "irrelevant": irrelevant,
        "answered": answered,
        "constraints": constraints,
        "conflicts": conflicts,
        "blocks": uniq,
        # the sketch's topology survives too; the UI merges it with what the
        # cascade added rather than synthesising a straight chain
        "links": (sketch.get("links", []) if sketch.get("confirmed") else []),
        "threads": threads,
        "chat": chat,
        "session": sess,
        "sessions": session_mod.list_all(project),
        "memory": session_mod.read_memory(project, sess),
        "sources": list_sources(project),
        "graph": graph(answered, open_nodes, blocked, constraints, conflicts),
        "progress": {
            "answered": len(answered),
            "total": len(answered) + len(open_nodes) + len(blocked),
            "constraints": len(constraints),
            "unverified": sum(1 for c in constraints if not c["verified"]),
            "conflicts": len(conflicts),
            "waiting_on_agent": sum(1 for t in threads.values()
                                    if t["waiting_on"] == "agent"),
            "waiting_on_student": sum(1 for t in threads.values()
                                      if t["waiting_on"] == "student"),
            "threads": len(threads),
            "orphan_threads": sum(1 for t in threads.values() if t["kind"] == "unknown"),
        },
    }


def graph(answered, open_nodes, blocked, constraints, conflicts):
    """Only what the student has actually reached: the graph GROWS, it does not unfurl."""
    gn, ge = [], []
    shown = set()
    for n in answered:
        gn.append({"id": n["id"], "label": n["id"].split(".")[-1], "kind": n["type"],
                   "state": "answered", "detail": n["question"]})
        shown.add(n["id"])
    for n in open_nodes:
        gn.append({"id": n["id"], "label": n["id"].split(".")[-1], "kind": n["type"],
                   "state": "open", "detail": n["question"]})
        shown.add(n["id"])
    # one ring of lookahead so the student sees where the path continues
    for n in blocked:
        if any(d in shown for d in (n.get("depends_on") or [])):
            gn.append({"id": n["id"], "label": n["id"].split(".")[-1], "kind": n["type"],
                       "state": "next", "detail": n["question"]})
            shown.add(n["id"])
    for n in answered + open_nodes + blocked:
        if n["id"] not in shown:
            continue
        for dep in n.get("depends_on", []) or []:
            if dep in shown:
                ge.append({"source": dep, "target": n["id"], "kind": "unlocks"})
    for c in constraints:
        gn.append({"id": c["id"], "label": c["id"].split(".")[-1], "kind": "constraint",
                   "state": "locked", "detail": c["text"], "icon": c["icon"],
                   "verified": c["verified"]})
        shown.add(c["id"])
        ge.append({"source": c["from_node"], "target": c["id"], "kind": "locks"})
    for cf in conflicts:
        if cf["a"] in shown and cf["b"] in shown:
            ge.append({"source": cf["a"], "target": cf["b"], "kind": "conflict"})
    return {"nodes": gn, "edges": ge}


# ---------------------------------------------------------------- sketch

def load_sketch(pdir):
    path = pdir / "sketch.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"brief": "", "blocks": [], "links": [], "confirmed": False}


def save_sketch(project, sketch):
    pdir = project_dir(project)
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "sketch.json").write_text(
        json.dumps(sketch, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------- sources

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
    """Every project in the workspace, newest activity first."""
    return project_mod.list_all()


def create_project(name):
    """Instantiate the project template. Returns the folder name used."""
    return project_mod.create(name)


def write(project=None, session=None):
    m = build(project, session)
    pdir = project_dir(m["project"])
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "design-model.json").write_text(
        json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    return m


if __name__ == "__main__":
    proj = sys.argv[1] if len(sys.argv) > 1 else workspace.default_project()
    m = write(proj)
    p = m["progress"]
    print(f"{proj}: stage={m['stage']} domains={m['domains'] or '-'}")
    print(f"  {p['answered']}/{p['total']} answered · {p['constraints']} constraints "
          f"({p['unverified']} unverified) · {p['conflicts']} conflicts")
    for n in m["open"]:
        print(f"  OPEN   {n['id']}  {n['question']}")
    for n in m["blocked"]:
        print(f"  next   {n['id']}  ({n['reason']})")
