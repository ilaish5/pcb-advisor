"""
The project's data: append-only logs in, derived views out.

    bom-log.jsonl       every applied BOM change.   -> bom (the lines)
    supply-log.jsonl    every stock/price check.    -> line["supply"]
    proposals.jsonl     what the agent proposed, and what the student decided
    library-log.jsonl   library parts and their verification
    idea.json           goal, agreed items, blocks, links   (server-written)
    netlist/<id>.json   one schematic sheet            (validated before it is written)

The principle (docs/archive/REBUILD-BRIEF.md): the logs are the truth, everything else is derived.
Nothing here edits a log. bom.json and library.json are rewritten from the logs
on every read, so a hand-edit of either is lost - on purpose.

The only callers that write are the server and the skills in scripts/skills.
"""
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import workspace  # noqa: E402

BOM_FIELDS = ("refs", "value", "description", "mpn", "manufacturer", "package",
              "dnp", "nobuy", "note", "library", "datasheet", "sheet", "role")
# a change to one of these makes the old stock/price answer stale
SUPPLY_KEYS = ("mpn",)
SUPPLIERS = ("LCSC", "Mouser", "DigiKey")


def now():
    return dt.datetime.now().isoformat(timespec="seconds")


def pdir(project):
    return workspace.project_dir(project)


# ---------------------------------------------------------------- files

def read_jsonl(path):
    path = pathlib.Path(path)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue          # a torn last line must not take the project down
    return out


def append(project, filename, record):
    path = pdir(project) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


# ---------------------------------------------------------------- BOM

def bom_lines(project):
    """Fold bom-log.jsonl into lines, in the order they first appeared."""
    lines = {}
    for ev in read_jsonl(pdir(project) / "bom-log.jsonl"):
        key = ev.get("line")
        if not key:
            continue
        line = lines.setdefault(key, {"key": key, "refs": []})
        line.update(ev.get("changes") or {})
    return list(lines.values())


def supply_for(project):
    """Latest answer per (line, supplier), only while it still matches the MPN.
    A line whose MPN changed since the last check has no supply: the UI shows
    "checking" until a skill run answers for the new part."""
    by_key = {l["key"]: l for l in bom_lines(project)}
    out = {}
    for ev in read_jsonl(pdir(project) / "supply-log.jsonl"):
        line = by_key.get(ev.get("line"))
        if not line or ev.get("mpn") != line.get("mpn"):
            continue
        item = {
            "stock": ev.get("stock"), "unit_price": ev.get("unit_price"),
            "qty_break": ev.get("qty_break"), "checked_at": ev.get("ts"),
            "source": ev.get("source"),
        }
        for opt_key in ("library_type", "package", "code", "datasheet_url", "exact"):
            if opt_key in ev:
                item[opt_key] = ev[opt_key]
        out.setdefault(ev["line"], {})[ev["supplier"]] = item
    return out


def library_parts(project):
    """library-log.jsonl -> {line: entry}. An entry says what exists, where the
    model came from, whether a skill verified it, and whether the STUDENT
    accepted it. 'ok' needs both."""
    parts = {}
    for ev in read_jsonl(pdir(project) / "library-log.jsonl"):
        key = ev.get("line")
        if key:
            parts.setdefault(key, {"line": key}).update(ev.get("changes") or {})
    return parts


def library_status(line, entry):
    if line.get("library") == "std":
        return "std"
    if not entry:
        return "missing"
    have = entry.get("symbol") and entry.get("footprint")
    if not have:
        return "missing"
    if entry.get("verify") == "pass" and entry.get("accepted"):
        return "ok"
    return "review"


def line_availability_and_risk(line, best=None, build_qty=5):
    supply = line.get("supply")
    q = qty(line)

    lib_type = ""
    if supply:
        lcsc_sup = supply.get("LCSC") or {}
        lib_type = lcsc_sup.get("library_type") or (best or {}).get("library_type") or ""
    if not lib_type:
        lib_type = line.get("library_type") or ""

    unit_price = best.get("unit_price") if best else None
    cost_per_board = round(q * unit_price, 4) if (unit_price is not None and q > 0) else 0.0

    if supply is None:
        availability = "unchecked"
        risk = ["not checked"]
        return availability, lib_type, cost_per_board, risk

    stock = best.get("stock", 0) if best else 0
    if not best and supply:
        stock = max((s.get("stock") or 0) for s in supply.values())

    board_qty = q if q > 0 else 1
    threshold = board_qty * build_qty * 10

    risk = []
    if stock <= 0:
        availability = "none"
        risk.append("out of stock")
    elif stock < threshold or lib_type == "Extended":
        availability = "low"
        if stock < threshold:
            risk.append("low stock")
        if lib_type == "Extended":
            risk.append("Extended fee")
    else:
        availability = "ok"

    if stock <= 0 and lib_type == "Extended" and "Extended fee" not in risk:
        risk.append("Extended fee")

    exact_flags = [s.get("exact") for s in supply.values() if s.get("exact") is not None]
    if exact_flags and not all(exact_flags):
        risk.append("no exact MPN match")

    return availability, lib_type, cost_per_board, risk


def bom(project, write=True):
    """The derived BOM: lines + supply + library state. Also written to
    bom.json for any agent that would rather read a file."""
    lines = bom_lines(project)
    supply = supply_for(project)
    lib = library_parts(project)
    sheets = {}
    for sh in sheet_ids(project):
        for part in load_sheet(project, sh).get("parts", []):
            sheets.setdefault(part["ref"], (sh, part.get("section")))
    build_qty = int(workspace.get("jlc.build_qty", 5))
    for l in lines:
        l["supply"] = supply.get(l["key"])
        entry = lib.get(l["key"])
        l["library"] = library_status(l, entry)
        l["library_entry"] = entry
        l["on_sheet"] = sorted({sheets[r][0] + ":" + (sheets[r][1] or "") for r in l.get("refs", []) if r in sheets})
        l["role"] = l.get("role") or ""

        b = best_offer(l)
        avail, lib_type, cost_pb, risk = line_availability_and_risk(l, b, build_qty=build_qty)
        l["availability"] = avail
        l["library_type"] = lib_type
        l["cost_per_board"] = cost_pb
        l["risk"] = risk

        sup_dict = l.get("supply") or {}
        lcsc_sup = sup_dict.get("LCSC") or {}
        if lcsc_sup.get("code") and not l.get("code"):
            l["code"] = lcsc_sup["code"]
        if lcsc_sup.get("datasheet_url") and not l.get("datasheet_url"):
            l["datasheet_url"] = lcsc_sup["datasheet_url"]
    if write:
        p = pdir(project) / "bom.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(lines, ensure_ascii=False, indent=2), encoding="utf-8")
    return lines


def qty(line):
    return 0 if (line.get("dnp") or line.get("nobuy")) else len(line.get("refs", []))


def best_offer(line, supply=None):
    supply = supply if supply is not None else line.get("supply") or {}
    best = None
    for name in SUPPLIERS:
        s = supply.get(name)
        if not s or s.get("unit_price") is None:
            continue
        if (s.get("stock") or 0) >= max(qty(line), 1) and (best is None or s["unit_price"] < best["unit_price"]):
            best = {"supplier": name, **s}
    return best


def totals(lines):
    ext_fee_usd = float(workspace.get("jlc.extended_fee_usd", 3.0))
    t = {"lines": len(lines), "parts": 0, "cost": 0.0, "buy": 0, "in_stock": 0,
         "out_of_stock": 0, "checking": 0, "to_verify": 0,
         "cost_per_board": 0.0, "extended_fee": 0.0}
    extended_parts = set()
    total_cost_per_board = 0.0
    for l in lines:
        q = qty(l)
        t["parts"] += q
        if l.get("library") in ("review", "missing"):
            t["to_verify"] += 1
        if not q:
            continue
        t["buy"] += 1
        if l.get("supply") is None:
            t["checking"] += 1
            continue
        b = best_offer(l)
        if b:
            t["in_stock"] += 1
            line_cost = b["unit_price"] * q
            t["cost"] += line_cost
            total_cost_per_board += line_cost
        else:
            t["out_of_stock"] += 1

        lib_type = l.get("library_type")
        if not lib_type and l.get("supply"):
            lcsc_sup = (l["supply"].get("LCSC") or {})
            lib_type = lcsc_sup.get("library_type")
        if lib_type == "Extended":
            part_id = l.get("mpn") or l.get("code") or l.get("key")
            extended_parts.add(part_id)

    t["cost"] = round(t["cost"], 4)
    t["cost_per_board"] = round(total_cost_per_board, 4)
    t["extended_fee"] = round(len(extended_parts) * ext_fee_usd, 2)
    return t


# ---------------------------------------------------------------- proposals

def proposals(project):
    """proposals.jsonl -> one row per proposal with its current status."""
    rows = {}
    for ev in read_jsonl(pdir(project) / "proposals.jsonl"):
        pid = ev.get("id")
        if not pid:
            continue
        if pid in rows and ev.get("status") in ("approved", "rejected"):
            rows[pid].update(status=ev["status"], decided_at=ev.get("ts"), decided_by=ev.get("by"))
        elif pid not in rows:
            rows[pid] = dict(ev)
    return list(rows.values())


def propose_bom(project, line, changes, reason="", sources=(), library=None, session=None, new=False):
    """Record a proposal. Nothing about the BOM changes until the student approves."""
    existing = {l["key"]: l for l in bom_lines(project)}
    if line not in existing and not new:
        raise ValueError(f"no BOM line {line!r} (use new: true to propose a new line)")
    before = {k: existing.get(line, {}).get(k) for k in changes}
    pid = "p" + dt.datetime.now().strftime("%Y%m%d%H%M%S%f")[:17]
    rec = {"id": pid, "ts": now(), "kind": "bom", "line": line, "new": bool(new and line not in existing),
           "changes": changes, "before": before, "reason": reason, "sources": list(sources),
           "library": library or None, "session": session, "status": "pending"}
    return append(project, "proposals.jsonl", rec)


def propose_idea_diagram(project, changes, reason="", sources=(), session=None):
    """Record a proposal to update the idea block diagram."""
    pid = "p" + dt.datetime.now().strftime("%Y%m%d%H%M%S%f")[:17]
    existing = load_idea(project)
    before = {"blocks": existing.get("blocks", []), "links": existing.get("links", [])}
    rec = {"id": pid, "ts": now(), "kind": "idea_diagram", "line": "diagram",
           "changes": changes, "before": before, "reason": reason, "sources": list(sources),
           "session": session, "status": "pending"}
    return append(project, "proposals.jsonl", rec)


def decide(project, pid, decision):
    """Approve or reject. Approving appends to bom-log.jsonl (and library-log.jsonl) - that is
    the only way an agent-proposed change reaches the BOM."""
    if decision not in ("approved", "rejected"):
        raise ValueError("decision must be approved or rejected")
    prop = next((p for p in proposals(project) if p["id"] == pid), None)
    if not prop:
        raise KeyError(f"no such proposal: {pid}")
    if prop["status"] != "pending":
        raise ValueError(f"proposal already {prop['status']}")
    append(project, "proposals.jsonl", {"id": pid, "ts": now(), "status": decision, "by": "student"})
    if decision == "approved":
        if prop.get("kind") == "idea_diagram":
            idea = load_idea(project)
            changes = prop.get("changes") or {}
            for k in ("blocks", "links"):
                if k in changes:
                    idea[k] = changes[k]
            save_idea(project, idea)
        else:
            append(project, "bom-log.jsonl", {
                "ts": now(), "by": "agent-approved", "line": prop["line"], "changes": prop["changes"],
                "before": prop.get("before"), "reason": prop.get("reason"),
                "sources": prop.get("sources"), "proposal": pid})
            if prop.get("library"):
                append(project, "library-log.jsonl", {
                    "ts": now(), "by": "agent-approved", "line": prop["line"],
                    "changes": prop["library"], "proposal": pid})
    return prop


def edit_bom(project, line, field, value):
    """The student edits a cell. Allowed fields only; recorded as by=student."""
    if field not in BOM_FIELDS:
        raise ValueError(f"not an editable BOM field: {field}")
    existing = {l["key"]: l for l in bom_lines(project)}
    if line not in existing:
        raise KeyError(f"no BOM line {line!r}")
    if existing[line].get(field) == value:
        return None
    changes = {field: value}
    if field == "mpn":
        changes["manufacturer"] = "—"      # unknown until a check answers for the new MPN
    return append(project, "bom-log.jsonl", {
        "ts": now(), "by": "student", "line": line, "changes": changes,
        "before": {field: existing[line].get(field)}})


def add_supply(project, line, supplier, stock, unit_price, mpn, qty_break=10, source="skill",
               library_type=None, package=None, code=None, datasheet_url=None, exact=None):
    rec = {
        "ts": now(), "line": line, "mpn": mpn, "supplier": supplier, "stock": stock,
        "unit_price": unit_price, "qty_break": qty_break, "source": source,
    }
    if library_type is not None: rec["library_type"] = library_type
    if package is not None: rec["package"] = package
    if code is not None: rec["code"] = code
    if datasheet_url is not None: rec["datasheet_url"] = datasheet_url
    if exact is not None: rec["exact"] = exact
    return append(project, "supply-log.jsonl", rec)


def add_library(project, line, changes, by="agent"):
    return append(project, "library-log.jsonl", {"ts": now(), "by": by, "line": line, "changes": changes})


# ---------------------------------------------------------------- idea

def load_idea(project):
    path = pdir(project) / "idea.json"
    if path.exists():
        try:
            idea = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            idea = {}
    else:
        old = pdir(project) / "sketch.json"          # v1 projects
        idea = {}
        if old.exists():
            try:
                o = json.loads(old.read_text(encoding="utf-8"))
                idea = {"goal": o.get("brief", ""), "blocks": o.get("blocks", []),
                        "links": o.get("links", []), "confirmed": bool(o.get("confirmed"))}
            except json.JSONDecodeError:
                idea = {}
    idea.setdefault("goal", "")
    idea.setdefault("agreed", [])
    idea.setdefault("blocks", [])
    idea.setdefault("links", [])
    idea.setdefault("confirmed", False)
    return idea


def save_idea(project, idea):
    path = pdir(project) / "idea.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(idea, ensure_ascii=False, indent=2), encoding="utf-8")
    return idea


def propose_idea(project, topic, text, by="agent"):
    """An agreed item. The agent proposes; it becomes 'confirmed' only when the student says so."""
    idea = load_idea(project)
    item = next((i for i in idea["agreed"] if i["topic"] == topic), None)
    status = "confirmed" if by == "student" else "proposed"
    if item:
        item.update(text=text, by=by, status=status, ts=now())
    else:
        idea["agreed"].append({"topic": topic, "text": text, "by": by, "status": status, "ts": now()})
    return save_idea(project, idea)


def confirm_idea(project):
    idea = load_idea(project)
    idea["confirmed"] = True
    idea["confirmed_at"] = now()
    for i in idea["agreed"]:
        if i["status"] == "proposed":
            i["status"] = "confirmed"
    return save_idea(project, idea)


# ---------------------------------------------------------------- netlist

def netlist_dir(project):
    return pdir(project) / "netlist"


def sheet_ids(project):
    d = netlist_dir(project)
    return sorted(f.stem for f in d.glob("*.json")) if d.exists() else []


def load_sheet(project, sheet):
    path = netlist_dir(project) / f"{workspace.safe_name(sheet)}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def validate_sheet(sheet, bom_refs):
    """Problems with one sheet (list of strings; empty = fine). Every ref must be
    in the BOM, and every pin needs a net or an explicit NC."""
    errors = []
    if not isinstance(sheet, dict) or not isinstance(sheet.get("parts"), list):
        return ["a sheet needs a 'parts' list"]
    sections = {s.get("id") for s in sheet.get("sections", [])}
    seen = set()
    for part in sheet["parts"]:
        ref = part.get("ref")
        if not ref:
            errors.append("a part has no ref")
            continue
        if ref in seen:
            errors.append(f"{ref}: appears twice")
        seen.add(ref)
        if ref not in bom_refs:
            errors.append(f"{ref}: not in the BOM")
        if sections and part.get("section") not in sections:
            errors.append(f"{ref}: section {part.get('section')!r} is not defined")
        pins = part.get("pins")
        if not pins:
            errors.append(f"{ref}: no pins")
        for pin in pins or []:
            if not (pin.get("net") or "").strip():
                errors.append(f"{ref}.{pin.get('name') or pin.get('num')}: no net (write NC if unconnected)")
    return errors


def write_sheet(project, sheet_id, sheet):
    """Validate against the BOM, then write. Refuses a sheet with problems."""
    refs = {r for l in bom_lines(project) for r in l.get("refs", [])}
    errors = validate_sheet(sheet, refs)
    if errors:
        return {"ok": False, "errors": errors}
    sheet = {**sheet, "id": workspace.safe_name(sheet_id)}
    d = netlist_dir(project)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{sheet['id']}.json").write_text(json.dumps(sheet, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "sheet": sheet["id"]}


def nets_of(project, ref):
    nets = []
    for sh in sheet_ids(project):
        for part in load_sheet(project, sh).get("parts", []):
            if part.get("ref") == ref:
                for p in part.get("pins", []):
                    n = p.get("net")
                    if n and n != "NC" and n not in nets:
                        nets.append(n)
    return nets


# ---------------------------------------------------------------- library view

def library_view(project):
    """Non-standard parts only, for the Altium library page."""
    rows = []
    for l in bom(project, write=False):
        if l["library"] == "std":
            continue
        e = l.get("library_entry") or {}
        rows.append({"line": l["key"], "refs": l.get("refs", []), "mpn": l.get("mpn"),
                     "symbol": bool(e.get("symbol")), "footprint": bool(e.get("footprint")),
                     "step": bool(e.get("step")), "model_source": e.get("model_source", ""),
                     "verify": e.get("verify", "unchecked"), "accepted": bool(e.get("accepted")),
                     "issues": e.get("issues", ""), "status": l["library"]})
    return rows


if __name__ == "__main__":
    import oscompat
    oscompat.utf8_stdio()
    proj = sys.argv[1] if len(sys.argv) > 1 else workspace.default_project()
    lines = bom(proj)
    print(json.dumps({"totals": totals(lines), "lines": len(lines)}, indent=2))
