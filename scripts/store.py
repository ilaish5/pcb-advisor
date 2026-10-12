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
import math
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import workspace  # noqa: E402

ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
COLOR_RE = re.compile(r"^(#[0-9A-Fa-f]{3,8}|rgba?\([0-9., %]+\)|[a-zA-Z]{1,20})$")

VALID_SHAPE_TYPES = {
    "block", "rectangle", "ellipse", "diamond", "triangle",
    "rounded_rectangle", "rounded-rectangle", "pill",
    "cloud", "star", "arrow_right", "arrow-right",
    "parallelogram", "hexagon", "octagon",
    "double_arrow", "double-arrow",
    "speech_callout", "speech-callout", "callout",
    "cylinder", "database", "process",
    "note_brace", "note-brace", "brace",
    "sticky", "text",
}
VALID_STROKE_STYLES = {"solid", "dashed", "dotted"}
VALID_CONNECT_ARROWS = {"none", "end", "both", "start"}
VALID_CONNECT_ROUTES = {"straight", "elbow", "curved"}
VALID_ENDPOINT_SIDES = {"top", "bottom", "left", "right"}
VALID_ALIGN = {"left", "center", "right"}
VALID_FONT_SIZES = {"S", "M", "L"}
VALID_DOMAINS = {
    "power", "sensing", "sensors", "mcu", "comms", "rf",
    "drive", "io", "ui", "sticky", "white", "none", "",
}

DOMAIN_COLORS = {
    "power": {"fill": "#fef3e2", "stroke": "#e67e22"},
    "sensing": {"fill": "#e8f8f0", "stroke": "#27ae60"},
    "sensors": {"fill": "#e8f8f0", "stroke": "#27ae60"},
    "mcu": {"fill": "#ebf5fb", "stroke": "#2980b9"},
    "comms": {"fill": "#f3ebf9", "stroke": "#8e44ad"},
    "rf": {"fill": "#f3ebf9", "stroke": "#8e44ad"},
    "drive": {"fill": "#fdedec", "stroke": "#c0392b"},
    "io": {"fill": "#fdedec", "stroke": "#c0392b"},
    "ui": {"fill": "#f2f4f4", "stroke": "#7f8c8d"},
}

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


def validate_diagram(data):
    """Validate diagram object containing shapes, connectors, and frames.
    Rejects unknown types, caps counts and lengths, ensures numbers are finite."""
    if not isinstance(data, dict):
        raise ValueError("diagram must be an object")

    shapes = data.get("shapes", [])
    connectors = data.get("connectors", [])
    frames = data.get("frames", [])

    if not isinstance(shapes, list) or not isinstance(connectors, list) or not isinstance(frames, list):
        raise ValueError("shapes, connectors, and frames must be arrays")

    if len(shapes) > 500:
        raise ValueError("too many shapes (max 500)")
    if len(connectors) > 500:
        raise ValueError("too many connectors (max 500)")
    if len(frames) > 100:
        raise ValueError("too many frames (max 100)")

    valid_shapes = []
    for s in shapes:
        if not isinstance(s, dict):
            raise ValueError("shape must be an object")
        sid = s.get("id")
        if not sid or not isinstance(sid, str) or not ID_RE.match(sid):
            raise ValueError(f"invalid shape id: {sid!r}")
        stype = s.get("type", "block")
        if stype not in VALID_SHAPE_TYPES:
            raise ValueError(f"unknown shape type: {stype!r}")

        for num_field in ("x", "y", "w", "h"):
            val = s.get(num_field)
            if not isinstance(val, (int, float)) or not math.isfinite(val):
                raise ValueError(f"shape {sid} field {num_field} must be finite number")
        w, h = float(s["w"]), float(s["h"])
        if w < 0 or h < 0 or w > 20000 or h > 20000:
            raise ValueError(f"shape {sid} dimensions out of range")

        text = s.get("text", "")
        if not isinstance(text, str) or len(text) > 2000:
            raise ValueError(f"shape {sid} text must be string <= 2000 chars")

        fill = s.get("fill", "#ffffff")
        stroke = s.get("stroke", "#1e293b")
        if not isinstance(fill, str) or not COLOR_RE.match(fill):
            raise ValueError(f"shape {sid} invalid fill")
        if not isinstance(stroke, str) or not COLOR_RE.match(stroke):
            raise ValueError(f"shape {sid} invalid stroke")

        stroke_style = s.get("strokeStyle", "solid")
        if stroke_style not in VALID_STROKE_STYLES:
            raise ValueError(f"shape {sid} invalid strokeStyle: {stroke_style}")

        stroke_width = s.get("strokeWidth", 2)
        if not isinstance(stroke_width, (int, float)) or not math.isfinite(stroke_width) or stroke_width < 0 or stroke_width > 50:
            raise ValueError(f"shape {sid} invalid strokeWidth")

        font_size = s.get("fontSize", "M")
        if isinstance(font_size, (int, float)):
            if not math.isfinite(font_size) or font_size < 4 or font_size > 120:
                raise ValueError(f"shape {sid} invalid fontSize")
        elif font_size not in VALID_FONT_SIZES:
            raise ValueError(f"shape {sid} invalid fontSize: {font_size}")

        bold = bool(s.get("bold", False))
        align = s.get("align", "center")
        if align not in VALID_ALIGN:
            raise ValueError(f"shape {sid} invalid align: {align}")

        z = s.get("z", 1)
        if not isinstance(z, (int, float)) or not math.isfinite(z):
            raise ValueError(f"shape {sid} field z must be finite number")

        locked = bool(s.get("locked", False))

        clean_s = {
            "id": sid,
            "type": stype,
            "x": float(s["x"]),
            "y": float(s["y"]),
            "w": float(s["w"]),
            "h": float(s["h"]),
            "text": text,
            "fill": fill,
            "stroke": stroke,
            "strokeStyle": stroke_style,
            "strokeWidth": float(stroke_width),
            "fontSize": font_size,
            "bold": bold,
            "align": align,
            "z": float(z),
            "locked": locked,
        }
        if "domain" in s:
            dom = s["domain"]
            if not isinstance(dom, str) or dom not in VALID_DOMAINS:
                raise ValueError(f"shape {sid} invalid domain: {dom!r}")
            clean_s["domain"] = dom
        if "role" in s and isinstance(s["role"], str) and len(s["role"]) <= 200:
            clean_s["role"] = s["role"]
        valid_shapes.append(clean_s)

    valid_connectors = []
    for c in connectors:
        if not isinstance(c, dict):
            raise ValueError("connector must be an object")
        cid = c.get("id")
        if not cid or not isinstance(cid, str) or not ID_RE.match(cid):
            raise ValueError(f"invalid connector id: {cid!r}")

        def validate_endpoint(ep, name):
            if not isinstance(ep, dict):
                raise ValueError(f"connector {cid} {name} must be object")
            if "shape" in ep:
                if not isinstance(ep["shape"], str) or not ID_RE.match(ep["shape"]):
                    raise ValueError(f"connector {cid} {name} shape invalid")
                side = ep.get("side", "right")
                if side not in VALID_ENDPOINT_SIDES:
                    raise ValueError(f"connector {cid} {name} invalid side: {side}")
                return {"shape": ep["shape"], "side": side}
            elif "x" in ep and "y" in ep:
                x, y = ep["x"], ep["y"]
                if not isinstance(x, (int, float)) or not math.isfinite(x) or not isinstance(y, (int, float)) or not math.isfinite(y):
                    raise ValueError(f"connector {cid} {name} coordinates must be finite")
                return {"x": float(x), "y": float(y)}
            else:
                raise ValueError(f"connector {cid} {name} must have shape or x,y")

        ep_from = validate_endpoint(c.get("from"), "from")
        ep_to = validate_endpoint(c.get("to"), "to")

        label = c.get("label", "")
        if not isinstance(label, str) or len(label) > 500:
            raise ValueError(f"connector {cid} label must be string <= 500 chars")

        stroke = c.get("stroke", "#64748b")
        if not isinstance(stroke, str) or not COLOR_RE.match(stroke):
            raise ValueError(f"connector {cid} invalid stroke")

        style = c.get("style", "solid")
        if style not in VALID_STROKE_STYLES:
            raise ValueError(f"connector {cid} invalid style: {style}")

        arrows = c.get("arrows", "end")
        if arrows not in VALID_CONNECT_ARROWS:
            raise ValueError(f"connector {cid} invalid arrows: {arrows}")

        route = c.get("route", "elbow")
        if route not in VALID_CONNECT_ROUTES:
            raise ValueError(f"connector {cid} invalid route: {route}")

        valid_connectors.append({
            "id": cid,
            "from": ep_from,
            "to": ep_to,
            "label": label,
            "stroke": stroke,
            "style": style,
            "arrows": arrows,
            "route": route,
        })

    valid_frames = []
    for f in frames:
        if not isinstance(f, dict):
            raise ValueError("frame must be an object")
        fid = f.get("id")
        if not fid or not isinstance(fid, str) or not ID_RE.match(fid):
            raise ValueError(f"invalid frame id: {fid!r}")

        for num_field in ("x", "y", "w", "h"):
            val = f.get(num_field)
            if not isinstance(val, (int, float)) or not math.isfinite(val):
                raise ValueError(f"frame {fid} field {num_field} must be finite number")
        w, h = float(f["w"]), float(f["h"])
        if w < 0 or h < 0 or w > 20000 or h > 20000:
            raise ValueError(f"frame {fid} dimensions out of range")

        title = f.get("title", "")
        if not isinstance(title, str) or len(title) > 500:
            raise ValueError(f"frame {fid} title must be string <= 500 chars")

        stroke = f.get("stroke", "#94a3b8")
        if not isinstance(stroke, str) or not COLOR_RE.match(stroke):
            raise ValueError(f"frame {fid} invalid stroke")

        valid_frames.append({
            "id": fid,
            "x": float(f["x"]),
            "y": float(f["y"]),
            "w": float(f["w"]),
            "h": float(f["h"]),
            "title": title,
            "stroke": stroke,
        })

    return {
        "shapes": valid_shapes,
        "connectors": valid_connectors,
        "frames": valid_frames,
    }


def migrate_idea_diagram(idea):
    """Ensure idea has diagram with shapes, connectors, frames.
    Migrate old blocks/links if diagram is missing or empty."""
    diagram = idea.get("diagram")
    if not isinstance(diagram, dict):
        diagram = {}
    shapes = list(diagram.get("shapes") or [])
    connectors = list(diagram.get("connectors") or [])
    frames = list(diagram.get("frames") or [])

    blocks = idea.get("blocks") or []
    links = idea.get("links") or []

    id_map = {}

    # If diagram has no shapes but idea has blocks, migrate blocks and links
    if not shapes and blocks:
        for idx, b in enumerate(blocks):
            raw_bid = str(b.get("id") or "")
            if raw_bid and ID_RE.match(raw_bid):
                bid = raw_bid
            else:
                bid = f"block_{idx}"
            if raw_bid:
                id_map[raw_bid] = bid

            x = b.get("x")
            y = b.get("y")
            if x is None or y is None or not isinstance(x, (int, float)) or not math.isfinite(x) or not isinstance(y, (int, float)) or not math.isfinite(y):
                x = 100 + (idx % 3) * 220
                y = 80 + (idx // 3) * 140
            w = b.get("w", 160)
            if not isinstance(w, (int, float)) or not math.isfinite(w):
                w = 160
            h = b.get("h", 64)
            if not isinstance(h, (int, float)) or not math.isfinite(h):
                h = 64

            raw_domain = str(b.get("domain") or "").lower()
            domain = raw_domain if raw_domain in VALID_DOMAINS else ""
            dom_colors = DOMAIN_COLORS.get(domain, {"fill": "#f1f5f9", "stroke": "#64748b"})

            label = str(b.get("label") or bid)
            role = str(b.get("role") or "")
            text = f"{label}\n{role}" if role else label

            raw_fill = b.get("fill")
            fill = raw_fill if (isinstance(raw_fill, str) and COLOR_RE.match(raw_fill)) else dom_colors["fill"]

            raw_stroke = b.get("stroke")
            stroke = raw_stroke if (isinstance(raw_stroke, str) and COLOR_RE.match(raw_stroke)) else dom_colors["stroke"]

            shapes.append({
                "id": bid,
                "type": "block",
                "x": float(x),
                "y": float(y),
                "w": float(w),
                "h": float(h),
                "text": text,
                "fill": fill,
                "stroke": stroke,
                "strokeStyle": "solid",
                "strokeWidth": 2.0,
                "fontSize": "M",
                "bold": True,
                "align": "center",
                "z": float(idx + 1),
                "locked": False,
                "domain": domain,
                "role": role,
            })

        for i, raw in enumerate(links):
            if isinstance(raw, (list, tuple)):
                from_id = raw[0] if len(raw) > 0 else ""
                to_id = raw[1] if len(raw) > 1 else ""
                label = raw[2] if len(raw) > 2 else ""
                safety = bool(raw[3]) if len(raw) > 3 else ("safety" in str(label).lower())
            elif isinstance(raw, dict):
                from_id = raw.get("from") or raw.get("a") or ""
                to_id = raw.get("to") or raw.get("b") or ""
                label = raw.get("label") or ""
                safety = bool(raw.get("safety")) or ("safety" in str(label).lower())
            else:
                continue

            from_str = str(from_id)
            to_str = str(to_id)
            safe_from = id_map.get(from_str, from_str)
            if not ID_RE.match(safe_from):
                safe_from = shapes[0]["id"] if shapes else "block_0"
            safe_to = id_map.get(to_str, to_str)
            if not ID_RE.match(safe_to):
                safe_to = shapes[0]["id"] if shapes else "block_0"

            connectors.append({
                "id": f"conn_{i}",
                "from": {"shape": safe_from, "side": "right"},
                "to": {"shape": safe_to, "side": "left"},
                "label": str(label or ("SAFETY" if safety else "")),
                "stroke": "#dc2626" if safety else "#64748b",
                "style": "dashed" if safety else "solid",
                "arrows": "end",
                "route": "elbow",
            })
    else:
        clean_shapes = []
        for idx, s in enumerate(shapes):
            if not isinstance(s, dict):
                continue
            raw_sid = str(s.get("id") or "")
            sid = raw_sid if (raw_sid and ID_RE.match(raw_sid)) else f"shape_{idx}"
            if raw_sid:
                id_map[raw_sid] = sid

            raw_dom = str(s.get("domain") or "").lower() if "domain" in s else ""
            dom = raw_dom if raw_dom in VALID_DOMAINS else ""
            dom_colors = DOMAIN_COLORS.get(dom, {"fill": "#ffffff", "stroke": "#1e293b"})

            raw_fill = s.get("fill")
            fill = raw_fill if (isinstance(raw_fill, str) and COLOR_RE.match(raw_fill)) else dom_colors["fill"]
            raw_stroke = s.get("stroke")
            stroke = raw_stroke if (isinstance(raw_stroke, str) and COLOR_RE.match(raw_stroke)) else dom_colors["stroke"]

            stype = s.get("type", "block")
            if stype not in VALID_SHAPE_TYPES:
                stype = "block"

            x = s.get("x", 0)
            y = s.get("y", 0)
            w = s.get("w", 160)
            h = s.get("h", 68)
            x = float(x) if isinstance(x, (int, float)) and math.isfinite(x) else 0.0
            y = float(y) if isinstance(y, (int, float)) and math.isfinite(y) else 0.0
            w = float(w) if isinstance(w, (int, float)) and math.isfinite(w) and w > 0 else 160.0
            h = float(h) if isinstance(h, (int, float)) and math.isfinite(h) and h > 0 else 68.0

            s_style = s.get("strokeStyle", "solid")
            if s_style not in VALID_STROKE_STYLES:
                s_style = "solid"

            s_width = s.get("strokeWidth", 2)
            if not isinstance(s_width, (int, float)) or not math.isfinite(s_width):
                s_width = 2.0

            font_sz = s.get("fontSize", "M")
            if isinstance(font_sz, (int, float)):
                if not math.isfinite(font_sz) or font_sz < 4 or font_sz > 120:
                    font_sz = "M"
            elif font_sz not in VALID_FONT_SIZES:
                font_sz = "M"

            align = s.get("align", "center")
            if align not in VALID_ALIGN:
                align = "center"

            z = s.get("z", idx + 1)
            z = float(z) if isinstance(z, (int, float)) and math.isfinite(z) else float(idx + 1)

            clean_s = {
                "id": sid,
                "type": stype,
                "x": x,
                "y": y,
                "w": w,
                "h": h,
                "text": str(s.get("text") or "")[:2000],
                "fill": fill,
                "stroke": stroke,
                "strokeStyle": s_style,
                "strokeWidth": float(s_width),
                "fontSize": font_sz,
                "bold": bool(s.get("bold", False)),
                "align": align,
                "z": z,
                "locked": bool(s.get("locked", False)),
            }
            if dom:
                clean_s["domain"] = dom
            if "role" in s and isinstance(s["role"], str):
                clean_s["role"] = s["role"][:200]
            clean_shapes.append(clean_s)
        shapes = clean_shapes

        clean_conns = []
        for idx, c in enumerate(connectors):
            if not isinstance(c, dict):
                continue
            raw_cid = str(c.get("id") or "")
            cid = raw_cid if (raw_cid and ID_RE.match(raw_cid)) else f"conn_{idx}"

            raw_stroke = c.get("stroke")
            stroke = raw_stroke if (isinstance(raw_stroke, str) and COLOR_RE.match(raw_stroke)) else "#64748b"
            style = c.get("style", "solid")
            if style not in VALID_STROKE_STYLES:
                style = "solid"
            arrows = c.get("arrows", "end")
            if arrows not in VALID_CONNECT_ARROWS:
                arrows = "end"
            route = c.get("route", "elbow")
            if route not in VALID_CONNECT_ROUTES:
                route = "elbow"

            def sanitize_ep(ep, name):
                if not isinstance(ep, dict):
                    return {"x": 0.0, "y": 0.0}
                if "shape" in ep:
                    raw_sh = str(ep["shape"])
                    safe_sh = id_map.get(raw_sh, raw_sh)
                    if not ID_RE.match(safe_sh):
                        safe_sh = shapes[0]["id"] if shapes else "shape_0"
                    side = ep.get("side", "right")
                    if side not in VALID_ENDPOINT_SIDES:
                        side = "right"
                    return {"shape": safe_sh, "side": side}
                elif "x" in ep and "y" in ep:
                    x, y = ep["x"], ep["y"]
                    x = float(x) if isinstance(x, (int, float)) and math.isfinite(x) else 0.0
                    y = float(y) if isinstance(y, (int, float)) and math.isfinite(y) else 0.0
                    return {"x": x, "y": y}
                return {"x": 0.0, "y": 0.0}

            clean_conns.append({
                "id": cid,
                "from": sanitize_ep(c.get("from"), "from"),
                "to": sanitize_ep(c.get("to"), "to"),
                "label": str(c.get("label") or "")[:500],
                "stroke": stroke,
                "style": style,
                "arrows": arrows,
                "route": route,
            })
        connectors = clean_conns

        clean_frames = []
        for idx, f in enumerate(frames):
            if not isinstance(f, dict):
                continue
            raw_fid = str(f.get("id") or "")
            fid = raw_fid if (raw_fid and ID_RE.match(raw_fid)) else f"frame_{idx}"
            raw_stroke = f.get("stroke")
            stroke = raw_stroke if (isinstance(raw_stroke, str) and COLOR_RE.match(raw_stroke)) else "#94a3b8"
            x = f.get("x", 0)
            y = f.get("y", 0)
            w = f.get("w", 320)
            h = f.get("h", 200)
            x = float(x) if isinstance(x, (int, float)) and math.isfinite(x) else 0.0
            y = float(y) if isinstance(y, (int, float)) and math.isfinite(y) else 0.0
            w = float(w) if isinstance(w, (int, float)) and math.isfinite(w) and w > 0 else 320.0
            h = float(h) if isinstance(h, (int, float)) and math.isfinite(h) and h > 0 else 200.0
            clean_frames.append({
                "id": fid,
                "x": x,
                "y": y,
                "w": w,
                "h": h,
                "title": str(f.get("title") or "")[:500],
                "stroke": stroke,
            })
        frames = clean_frames

    diagram = validate_diagram({
        "shapes": shapes,
        "connectors": connectors,
        "frames": frames,
    })
    idea["diagram"] = diagram

    # Keep backward compatibility: sync blocks & links from shapes & connectors
    if shapes and not idea.get("blocks"):
        idea["blocks"] = [
            {
                "id": s["id"],
                "label": s.get("text", "").split("\n")[0] or s["id"],
                "role": s.get("role", "") or (s.get("text", "").split("\n", 1)[1] if "\n" in s.get("text", "") else ""),
                "domain": s.get("domain", ""),
                "x": s.get("x", 0),
                "y": s.get("y", 0),
            }
            for s in shapes if s.get("type") in ("block", "rectangle")
        ]
    return idea


def propose_idea_diagram(project, changes, reason="", sources=(), session=None):
    """Record a proposal to update the idea block diagram."""
    pid = "p" + dt.datetime.now().strftime("%Y%m%d%H%M%S%f")[:17]
    existing = load_idea(project)
    before = {
        "blocks": existing.get("blocks", []),
        "links": existing.get("links", []),
        "diagram": existing.get("diagram", {"shapes": [], "connectors": [], "frames": []}),
    }
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

    if decision == "approved":
        if prop.get("kind") == "idea_diagram":
            idea = load_idea(project)
            changes = prop.get("changes") or {}
            if "diagram" in changes:
                if not isinstance(changes["diagram"], dict):
                    raise ValueError("diagram must be an object")
                idea["diagram"] = validate_diagram(changes["diagram"])
            for k in ("shapes", "connectors", "frames"):
                if k in changes:
                    if not isinstance(changes[k], list):
                        raise ValueError(f"{k} must be an array")
                    idea.setdefault("diagram", {})[k] = changes[k]
            for k in ("blocks", "links"):
                if k in changes:
                    idea[k] = changes[k]
            if ("blocks" in changes or "links" in changes) and ("diagram" not in changes and "shapes" not in changes):
                migrate_idea_diagram(idea)
            if "diagram" in idea:
                idea["diagram"] = validate_diagram(idea["diagram"])

            append(project, "proposals.jsonl", {"id": pid, "ts": now(), "status": decision, "by": "student"})
            save_idea(project, idea)
        else:
            append(project, "proposals.jsonl", {"id": pid, "ts": now(), "status": decision, "by": "student"})
            append(project, "bom-log.jsonl", {
                "ts": now(), "by": "agent-approved", "line": prop["line"], "changes": prop["changes"],
                "before": prop.get("before"), "reason": prop.get("reason"),
                "sources": prop.get("sources"), "proposal": pid})
            if prop.get("library"):
                append(project, "library-log.jsonl", {
                    "ts": now(), "by": "agent-approved", "line": prop["line"],
                    "changes": prop["library"], "proposal": pid})
    else:
        append(project, "proposals.jsonl", {"id": pid, "ts": now(), "status": decision, "by": "student"})
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
    migrate_idea_diagram(idea)
    return idea


def save_idea(project, idea):
    path = pdir(project) / "idea.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if "diagram" in idea:
        if not isinstance(idea["diagram"], dict):
            raise ValueError("diagram must be an object")
        idea["diagram"] = validate_diagram(idea["diagram"])
        # keep blocks/links synced
        shapes = idea["diagram"].get("shapes", [])
        if shapes:
            idea["blocks"] = [
                {
                    "id": s["id"],
                    "label": s.get("text", "").split("\n")[0] or s["id"],
                    "role": s.get("role", "") or (s.get("text", "").split("\n", 1)[1] if "\n" in s.get("text", "") else ""),
                    "domain": s.get("domain", ""),
                    "x": s.get("x", 0),
                    "y": s.get("y", 0),
                }
                for s in shapes if s.get("type") in ("block", "rectangle")
            ]
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
