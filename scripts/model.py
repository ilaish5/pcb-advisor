"""
The engine.  cascade (authored knowledge) + state (what happened) -> design model.

Deterministic: same inputs, same output, every time.  An agent APPENDS to the
state files; it never writes the model.  Everything the UI shows is derived here.
"""
import json
import pathlib
import re
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import project as project_mod  # noqa: E402
import session as session_mod  # noqa: E402
import workspace  # noqa: E402

# What the letter in front of a part number means. A board is covered in J1, U3,
# Q1, TP1 - the one convention every schematic assumes you already know, and the
# one a student meeting it for the first time has no way to look up from inside
# a diagram. Convention, deliberately: this is common practice, not a standard
# this tool holds a citable copy of.
DESIGNATORS = {
    "C": "capacitor",
    "D": "diode or LED",
    "F": "fuse",
    "J": "connector",
    "K": "relay",
    "L": "inductor",
    "Q": "transistor",
    "R": "resistor",
    "SW": "switch",
    "TP": "test point",
    "U": "integrated circuit",
    "Y": "crystal or oscillator",
}

_DESIGNATOR = re.compile(r"^([A-Z]{1,2})(\d+)$")

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


def designators(blocks):
    """The designator classes actually on this board, first appearance first.

    Only what is present: a legend listing twelve letters for a board that uses
    three teaches nothing and is ignored."""
    out, seen = [], set()
    for b in blocks or []:
        first = str(b.get("label") or b.get("id") or "").split("\n")[0].strip()
        hit = _DESIGNATOR.match(first)
        if not hit:
            continue
        prefix = hit.group(1)
        if prefix in DESIGNATORS and prefix not in seen:
            seen.add(prefix)
            out.append({"prefix": prefix, "means": DESIGNATORS[prefix], "example": first})
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

    # Both kinds of event fold in file order, last write wins. A withdrawal is
    # not a deletion: decisions.jsonl still shows the answer was once given and
    # why it stopped applying, and answering again simply overrides it back.
    answers, withdrawn = {}, {}
    for ev in events:
        if ev.get("node") not in index:
            continue
        if ev.get("retract"):
            answers.pop(ev["node"], None)
            withdrawn[ev["node"]] = ev
        elif ev.get("reopen"):
            # back to being an open question: neither answered nor ruled out
            answers.pop(ev["node"], None)
            withdrawn.pop(ev["node"], None)
        else:
            answers[ev["node"]] = ev
            withdrawn.pop(ev["node"], None)

    def available(node):
        """A node is reachable only if its guard matches AND its deps are answered.

        The guard goes first on purpose. It settles whether this question applies
        at all, and a node ruled out by its own guard is inapplicable whatever its
        dependencies are doing. Checking deps first reported "waiting on X" for an
        X that was itself guarded off and could never be answered - a question
        that could neither be completed nor dismissed.

        But an unmet guard is only a refusal once the guard has actually been
        SETTLED. Until then the honest answer is that we are waiting for it, and
        keeping that distinction is what still lets the student see one step
        ahead instead of watching half the path turn grey.
        """
        for guard_node, guard_val in (node.get("requires") or {}).items():
            if answers.get(guard_node, {}).get("value") == guard_val:
                continue
            settled = guard_node in answers or guard_node in withdrawn
            return False, (f"only if {guard_node} = {guard_val}" if settled
                           else f"waiting on {guard_node}")
        for dep in node.get("depends_on", []) or []:
            if dep not in answers:
                return False, f"waiting on {dep}"
        return True, None

    open_nodes, blocked, answered, irrelevant = [], [], [], []
    for node in nodes:
        ok, reason = available(node)
        entry = dict(node)
        if node["id"] in answers:
            entry["chosen"] = answers[node["id"]]["value"]
            entry["chosen_by"] = answers[node["id"]].get("by", "?")
            answered.append(entry)
        elif node["id"] in withdrawn:
            # the student said this does not apply to their board. Not blocked,
            # not open - and not silently gone either: the reason travels with it
            entry["reason"] = withdrawn[node["id"]].get("why") or "does not apply here"
            entry["withdrawn"] = True
            entry["withdrawn_by"] = withdrawn[node["id"]].get("by", "?")
            irrelevant.append(entry)
        elif ok:
            open_nodes.append(entry)
        elif reason and reason.startswith("only if"):
            entry["reason"] = reason
            irrelevant.append(entry)            # a guard excluded it - not blocked, just N/A
        else:
            entry["reason"] = reason
            blocked.append(entry)

    # Inapplicability is contagious. A question waiting on one that does not
    # apply will wait forever, so it does not apply either. Repeat until nothing
    # moves: the chain can be several deep.
    dead = {n["id"] for n in irrelevant}
    moved = True
    while moved:
        moved = False
        for entry in list(blocked):
            gone = [d for d in (entry.get("depends_on") or []) if d in dead]
            if gone:
                entry["reason"] = f"not needed once {gone[0]} does not apply"
                blocked.remove(entry)
                irrelevant.append(entry)
                dead.add(entry["id"])
                moved = True

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

    # What is actually on this board. A constraint may depend on a part being
    # present, so this has to be settled before the constraints are collected.
    # Both vocabularies count: the corpus names blocks by id (U_REG), the
    # student's sketch names them by kind (regulation).
    on_board = {b["id"] for b in uniq} | {b.get("kind") for b in uniq if b.get("kind")}
    # and what to call a part we have to name. Every cascade is read, not only
    # the active ones: a rule in one domain can need a part from another.
    block_names = {}
    for cas in cascades.values():
        block_names.update(cas.get("block_names") or {})

    constraints, conflicts, withheld = [], [], []
    for node in answered:
        opt = next((o for o in node.get("options", []) if o["id"] == node["chosen"]), None)
        if not opt:
            continue
        for lock in opt.get("locks", []) or []:
            # A rule can presuppose a part. "One connection between analog and
            # power ground, at the regulator's output capacitor" is advice about
            # a component, and on a board that has no regulator it is not merely
            # unhelpful - it instructs the student to go and find something that
            # is not there. Say what you need, and the model withholds you.
            need = lock.get("needs_block")
            if need and need not in on_board:
                withheld.append({"id": lock["id"], "text": lock["text"],
                                 "needs_block": need,
                                 # never show the id to the student
                                 "needs": block_names.get(need, need),
                                 "from_node": node["id"]})
                continue
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

    # A thread is the SPATIAL axis: everything ever said about one element,
    # whichever conversation it was said in. The chat is the timeline.
    known = anchors(project)
    threads = {}
    for m in sorted(messages, key=lambda m: m.get("ts", "")):
        threads.setdefault(m["anchor"], []).append(m)

    # what this thread was about, if it is still part of the design
    live_now = set(answers) | {c["id"] for c in constraints}

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
            # why it was closed. Closing used to record nothing at all, so a
            # thread documenting a contradiction could be dismissed in one click
            # and leave no trace of what was decided about it.
            "resolution": (closing[-1].get("text") or "").strip() if closing else "",
            # and closing it does not make the thing it was about go away: a
            # settled thread whose decision is still live is acknowledged, not
            # done. The distinction is the difference between "we fixed it" and
            # "we stopped talking about it".
            "still_live": resolved and anchor in live_now,
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
        # rules the corpus holds for parts this board does not have. Reported,
        # not hidden: an advisor that cannot see them re-derives them from
        # memory, which is exactly what it must not do.
        "withheld": withheld,
        "conflicts": conflicts,
        "blocks": uniq,
        # what J, U, Q mean on THIS board, so neither the picture nor the panel
        # has to assume the student already knows
        "designators": designators(uniq),
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
            "withdrawn": sum(1 for n in irrelevant if n.get("withdrawn")),
            "withheld": len(withheld),
            "acknowledged_threads": sum(1 for t in threads.values() if t.get("still_live")),
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
    for n in m["irrelevant"]:
        mark = "gone" if n.get("withdrawn") else "n/a "
        print(f"  {mark}   {n['id']}  ({n['reason']})")
