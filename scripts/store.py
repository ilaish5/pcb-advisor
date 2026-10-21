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
import copy
import datetime as dt
import json
import math
import os
import pathlib
import re
import sys
import threading
import time
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import workspace  # noqa: E402

ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
COLOR_RE = re.compile(r"^(#[0-9A-Fa-f]{3,8}|rgba?\([0-9., %]+\)|[a-zA-Z]{1,20})$")

VALID_SHAPE_TYPES = {
    "box", "block", "rectangle", "ellipse", "diamond", "triangle",
    "rounded_rectangle", "rounded-rectangle", "pill",
    "cloud", "star", "arrow_right", "arrow-right",
    "parallelogram", "hexagon", "octagon",
    "double_arrow", "double-arrow",
    "speech_callout", "speech-callout", "callout",
    "cylinder", "database", "process",
    "note_brace", "note-brace", "brace",
    "sticky", "text",
}
VALID_STROKE_STYLES = {"solid", "dashed", "dotted", "thick"}
VALID_CONNECT_ARROWS = {"none", "end", "both", "start", "to"}
VALID_CONNECT_ROUTES = {"straight", "elbow", "curved"}
VALID_ENDPOINT_SIDES = {"top", "bottom", "left", "right"}
VALID_ENDPOINT_POINTS = VALID_ENDPOINT_SIDES | {"top-left", "top-right", "bottom-right", "bottom-left"}
VALID_ALIGN = {"left", "center", "right"}
VALID_FONT_SIZES = {"S", "M", "L"}
DOMAIN_ALIASES = {"sensor": "sensors", "microcontroller": "mcu", "controller": "mcu", "supply": "power",
                  "communication": "comms", "output": "drive", "input": "io", "debug": "io",
                  "programming": "io", "connector": "io", "battery": "power", "display": "ui", "audio": "drive",
                  "actuator": "drive", "wireless": "rf"}
VALID_DOMAINS = {
    "power", "sensing", "sensors", "mcu", "comms", "rf",
    "drive", "io", "ui", "sticky", "white", "none", "",
}


def _domain(raw):
    """A block's colour group; a name the tool does not know is drawn neutral, never a reason to drop the edit."""
    dom = str(raw or "").strip().lower()
    dom = DOMAIN_ALIASES.get(dom, dom)
    return dom if dom in VALID_DOMAINS else ""

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
              "dnp", "nobuy", "note", "library", "datasheet", "sheet", "role", "lcsc")
# `lcsc` is a code the student or an import declared for the line; what LCSC answered is in supply-log
# a change to one of these makes the old stock/price answer stale
SUPPLY_KEYS = ("mpn",)
CODE_RISK = "LCSC code is another part"       # the risk tag for a supply answer with `code_mismatch`
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
        if ev.get("removed"):                # an undo of a line the log had added
            lines.pop(key, None)
            continue
        line = lines.setdefault(key, {"key": key, "refs": []})
        line.update(ev.get("changes") or {})
    for line in lines.values():
        # a line approved without references is still known by its key when that is a designator
        if not line.get("refs") and re.fullmatch(r"[A-Za-z]+\d+", line["key"]):
            line["refs"] = [line["key"]]
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
        for opt_key in ("library_type", "package", "code", "datasheet_url", "exact", "code_mismatch"):
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
    if any(s.get("code_mismatch") for s in supply.values()):
        risk.append(CODE_RISK)

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
        l["pins_status"], l["pins_issues"] = pins_status(l, entry)
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
    # 3.07 USD: Economic assembly "Feeder Loading" per Extended part, https://jlcpcb.com/help/article/pcb-assembly-price
    # (page dated Sep 09 2026, read 2026-10-14). Standard assembly charges 1.53 for Basic and Extended alike.
    ext_fee_usd = float(workspace.get("jlc.extended_fee_usd", 3.07))
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
            if ev.get("after_hash"):
                rows[pid]["after_hash"] = ev["after_hash"]
        elif pid in rows and ev.get("status") == "undone":
            rows[pid].update(status="undone", undone_at=ev.get("ts"), undone_by=ev.get("by"))
        elif pid not in rows:
            rows[pid] = dict(ev)
    return list(rows.values())


def _new_proposal_id(project):
    """Time-ordered id; a suffix keeps two proposals in the same millisecond apart."""
    base = "p" + dt.datetime.now().strftime("%Y%m%d%H%M%S%f")[:17]
    taken = {p["id"] for p in proposals(project)}
    pid, n = base, 1
    while pid in taken:
        pid, n = f"{base}-{n}", n + 1
    return pid


def propose_bom(project, line, changes, reason="", sources=(), library=None, session=None, new=False, reserved=()):
    """Record a proposal. Nothing about the BOM changes until the student approves.
    `reserved`: refs other proposals of the same turn use (kept free when refs are added for a qty)."""
    existing = {l["key"]: l for l in bom_lines(project)}
    if line not in existing:
        # a line still waiting for approval: this card replaces it, carrying what it already said
        waiting = [p for p in proposals(project) if p.get("kind") == "bom" and p.get("status") == "pending"
                   and p.get("new") and p.get("line") == line]
        if waiting:
            changes, library, new = {**(waiting[-1].get("changes") or {}), **changes}, library or waiting[-1].get("library"), True
            for p in waiting:
                append(project, "proposals.jsonl", {"id": p["id"], "ts": now(), "status": "rejected", "by": "superseded"})
    if line not in existing and not new:
        raise ValueError(f"no BOM line {line!r} (use new: true to propose a new line)")
    before = {k: existing.get(line, {}).get(k) for k in changes}
    if new and line not in existing and "refs" not in changes and re.fullmatch(r"[A-Za-z]+\d+", line):
        changes = {**changes, "refs": [line]}
        before = {**before, "refs": None}
    # The quantity is the number of refs; "qty": 6 with one ref would order one. Add free refs of the same prefix.
    refs, want = changes.get("refs"), changes.get("qty")
    if new and isinstance(refs, list) and refs and isinstance(want, int) and want > len(refs):
        m = re.fullmatch(r"([A-Za-z]+)\d+", str(refs[0]))
        if m:
            taken = {r for l in existing.values() for r in (l.get("refs") or [])}
            taken |= {r for p in proposals(project) if p.get("kind") == "bom" and p.get("status") == "pending"
                      for r in ((p.get("changes") or {}).get("refs") or [])}
            taken |= set(refs) | set(reserved)
            refs, n = list(refs), 1
            while len(refs) < want:
                if f"{m.group(1)}{n}" not in taken:
                    refs.append(f"{m.group(1)}{n}")
                n += 1
            changes = {**changes, "refs": refs}
    pid = _new_proposal_id(project)
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

        # a whole diagram from the agent names the domain only: the block takes that domain's colours,
        # as add_shape gives them (blocks went white after an Approve)
        dom_colors = DOMAIN_COLORS.get(_domain(s.get("domain")), {"fill": "#ffffff", "stroke": "#1e293b"})
        fill = s.get("fill", dom_colors["fill"])
        stroke = s.get("stroke", dom_colors["stroke"])
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
            clean_s["domain"] = _domain(s["domain"])
        if "role" in s and isinstance(s["role"], str) and len(s["role"]) <= 200:
            clean_s["role"] = s["role"]
        valid_shapes.append(clean_s)

    shape_ids = {s["id"] for s in valid_shapes}
    valid_connectors = []
    for c in connectors:
        if not isinstance(c, dict):
            raise ValueError("connector must be an object")
        cid = c.get("id")
        if not cid or not isinstance(cid, str) or not ID_RE.match(cid):
            raise ValueError(f"invalid connector id: {cid!r}")

        def validate_endpoint(ep, name):
            # a bare shape id is the same shorthand add_connector accepts (the agent writes it in full diagrams too)
            if isinstance(ep, str) and ep in shape_ids:
                ep = {"shape": ep, "side": "right" if name == "from" else "left"}
            if not isinstance(ep, dict):
                raise ValueError(f"connector {cid} {name} must be object")
            if "shape" in ep:
                if not isinstance(ep["shape"], str) or not ID_RE.match(ep["shape"]):
                    raise ValueError(f"connector {cid} {name} shape invalid")
                if "point" in ep:
                    point = ep["point"]
                    if not isinstance(point, str) or point not in VALID_ENDPOINT_POINTS:
                        raise ValueError(f"connector {cid} {name} invalid point: {point!r}")
                    # new-style attached end: the shape must exist (legacy side-style ends stay lenient)
                    if ep["shape"] not in shape_ids:
                        raise ValueError(f"connector {cid} {name} references unknown shape: {ep['shape']!r}")
                    return {"shape": ep["shape"], "point": point}
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
                    if ep.get("point") in VALID_ENDPOINT_POINTS:
                        return {"shape": safe_sh, "point": ep["point"]}
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
    pid = _new_proposal_id(project)
    existing = load_idea_working(project)
    before = {
        "blocks": existing.get("blocks", []),
        "links": existing.get("links", []),
        "diagram": existing.get("diagram", {"shapes": [], "connectors": [], "frames": []}),
    }
    rec = {"id": pid, "ts": now(), "kind": "idea_diagram", "line": "diagram",
           "changes": changes, "before": before, "reason": reason, "sources": list(sources),
           "session": session, "status": "pending"}
    return append(project, "proposals.jsonl", rec)


def decide(project, pid, decision, by="student"):
    """Approve or reject. Approving appends to bom-log.jsonl (and library-log.jsonl) - that is
    the only way an agent-proposed change reaches the BOM. `by` is "student" for a click and
    "auto" when the autonomy setting let a routine change through (the logs are otherwise identical)."""
    if decision not in ("approved", "rejected"):
        raise ValueError("decision must be approved or rejected")
    prop = next((p for p in proposals(project) if p["id"] == pid), None)
    if not prop:
        raise KeyError(f"no such proposal: {pid}")
    if prop["status"] != "pending":
        raise ValueError(f"proposal already {prop['status']}")

    if decision == "approved":
        if prop.get("kind") == "idea_diagram":
            idea = load_idea_working(project)
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

            save_idea_draft(project, idea)
            append(project, "proposals.jsonl", {"id": pid, "ts": now(), "status": decision, "by": by,
                                                "after_hash": _idea_hash(load_idea_working(project))})
        else:
            append(project, "proposals.jsonl", {"id": pid, "ts": now(), "status": decision, "by": by})
            append(project, "bom-log.jsonl", {
                "ts": now(), "by": "agent-approved", "line": prop["line"],
                "changes": _drop_stale_lcsc(project, prop["line"], dict(prop["changes"])),
                "before": prop.get("before"), "reason": prop.get("reason"),
                "sources": prop.get("sources"), "proposal": pid})
            if prop.get("library"):
                append(project, "library-log.jsonl", {
                    "ts": now(), "by": "agent-approved", "line": prop["line"],
                    "changes": prop["library"], "proposal": pid})
    else:
        append(project, "proposals.jsonl", {"id": pid, "ts": now(), "status": decision, "by": by})
    return prop


# ---------------------------------------------------------------- autonomy
#
# "act, show, allow undo; ask only for what matters". The agent.autonomy setting decides which
# proposals are applied without a click:
#   ask        none (every proposal waits for Approve)
#   important  ROUTINE ones are applied at once; IMPORTANT and CRITICAL wait            (default)
#   auto       ROUTINE and IMPORTANT are applied; only CRITICAL waits
# Levels: routine = passive values, BOM edits that do not choose a costed part, diagram, notes ...
#         important = choosing or changing a part with an MPN/LCSC code (costs money), confirming the
#         idea, anything that writes Altium files; critical = ordering/upload to the manufacturer,
#         deleting data. An unknown kind is treated as important.
AUTONOMY_MODES = ("ask", "important", "auto")
DEFAULT_AUTONOMY = "important"


def autonomy():
    mode = workspace.get("agent.autonomy", DEFAULT_AUTONOMY)
    return mode if mode in AUTONOMY_MODES else DEFAULT_AUTONOMY


def _real(v):
    return isinstance(v, str) and v.strip() not in ("", "—", "-")


def classify_proposal(prop):
    """'routine' | 'important' | 'critical' for one proposal record. The one place that decides."""
    kind = prop.get("kind") or "bom"
    if kind.startswith("delete") or kind in ("order", "upload", "jlc_upload", "jlc"):
        return "critical"
    if kind == "bom":
        ch, before = prop.get("changes") or {}, prop.get("before") or {}
        if ch.get("deleted") or ch.get("remove"):
            return "critical"
        for key in ("mpn", "lcsc"):          # a costed part is chosen (new line) or swapped
            if _real(ch.get(key)) and str(ch[key]).strip() != str(before.get(key) or "").strip():
                return "important"
        return "routine"
    if kind in ("idea_diagram", "description", "note", "rules", "rules_extra", "sheet", "diagram"):
        return "routine"
    return "important"          # idea_confirm, altium*, anything unknown


def may_auto_apply(prop, mode=None):
    mode = mode or autonomy()
    level = classify_proposal(prop)
    if mode == "auto":
        return level != "critical"
    if mode == "important":
        return level == "routine"
    return False


def _idea_hash(idea):
    import hashlib
    blob = json.dumps({k: idea.get(k) for k in ("blocks", "links", "diagram")}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- undo
#
# Undo is a compensating entry appended to the logs; nothing is rewritten. It restores the `before`
# the proposal recorded. Simple safe rule: it is refused unless the thing still looks exactly as the
# change left it. If something later touched the same line/diagram/sheet, the message says so and
# the student undoes that later change first (i.e. undo works in reverse order, one step at a time).

class UndoRefused(ValueError):
    pass


def _restore_value(key, v):
    if v is not None:
        return v
    return [] if key == "refs" else False if key in ("dnp", "nobuy") else ""


def undo_proposal(project, pid, by="student"):
    prop = next((p for p in proposals(project) if p["id"] == pid), None)
    if not prop:
        raise KeyError(f"no such proposal: {pid}")
    if prop["status"] == "undone":
        raise UndoRefused("this change is already undone")
    if prop["status"] != "approved":
        raise UndoRefused("only an applied change can be undone")
    if prop.get("kind") == "idea_diagram":
        idea = load_idea_working(project)
        if prop.get("after_hash") and _idea_hash(idea) != prop["after_hash"]:
            raise UndoRefused("the diagram was edited after this change; undo is refused so those edits are not lost")
        before = prop.get("before") or {}
        for k in ("blocks", "links", "diagram"):
            if k in before:
                idea[k] = before[k]
        save_idea_draft(project, idea)
    else:
        entry = next((e for e in read_jsonl(pdir(project) / "bom-log.jsonl") if e.get("proposal") == pid), None)
        if not entry:
            raise UndoRefused("this change left no BOM entry to undo")
        cur = next((l for l in bom_lines(project) if l["key"] == entry["line"]), None)
        if cur is None:
            raise UndoRefused(f"line {entry['line']} no longer exists")
        for k, v in (entry.get("changes") or {}).items():
            if cur.get(k) != v:
                raise UndoRefused(f"{entry['line']} was changed after this ({k} is now {cur.get(k)!r}); "
                                  "undo that later change first")
        if prop.get("new"):
            append(project, "bom-log.jsonl", {"ts": now(), "by": "undo", "line": entry["line"], "removed": True,
                                              "changes": {}, "before": entry.get("changes"), "undoes": pid})
        else:
            before = entry.get("before") or prop.get("before") or {}
            append(project, "bom-log.jsonl", {
                "ts": now(), "by": "undo", "line": entry["line"], "undoes": pid,
                "changes": {k: _restore_value(k, before.get(k)) for k in entry["changes"]},
                "before": entry.get("changes"), "reason": "undo of " + pid})
        if prop.get("library"):
            append(project, "library-log.jsonl", {"ts": now(), "by": "undo", "line": entry["line"], "undoes": pid,
                                                  "changes": {k: None for k in prop["library"]}})
    append(project, "proposals.jsonl", {"id": pid, "ts": now(), "status": "undone", "by": by})
    return prop


def _sheet_hash(sheet):
    import hashlib
    return hashlib.sha1(json.dumps(sheet, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def write_sheet_logged(project, sheet_id, sheet, by="agent"):
    """write_sheet, plus a sheet-log.jsonl entry holding the sheet as it was, so the write can be undone."""
    sid = workspace.safe_name(sheet_id)
    before = load_sheet(project, sid) or None
    res = write_sheet(project, sheet_id, sheet)
    if res.get("ok"):
        after = load_sheet(project, res["sheet"])
        if after != before:
            taken = {e.get("id") for e in read_jsonl(pdir(project) / "sheet-log.jsonl")}
            cid, n = "s" + dt.datetime.now().strftime("%Y%m%d%H%M%S%f")[:17], 1
            base = cid
            while cid in taken:
                cid, n = f"{base}-{n}", n + 1
            append(project, "sheet-log.jsonl", {"id": cid, "ts": now(), "kind": "sheet", "sheet": res["sheet"],
                                                "before": before, "after_hash": _sheet_hash(after), "by": by})
            res["change"] = cid
    return res


def _sheet_changes(project):
    rows = {}
    for ev in read_jsonl(pdir(project) / "sheet-log.jsonl"):
        cid = ev.get("id")
        if not cid:
            continue
        if cid in rows and ev.get("status") == "undone":
            rows[cid].update(status="undone", undone_at=ev.get("ts"))
        elif cid not in rows:
            rows[cid] = {**ev, "status": "applied"}
    return list(rows.values())


def undo_sheet_write(project, cid, by="student"):
    ch = next((c for c in _sheet_changes(project) if c["id"] == cid), None)
    if not ch:
        raise KeyError(f"no such change: {cid}")
    if ch["status"] == "undone":
        raise UndoRefused("this change is already undone")
    path = netlist_dir(project) / f"{ch['sheet']}.json"
    if _sheet_hash(load_sheet(project, ch["sheet"])) != ch["after_hash"]:
        raise UndoRefused(f"sheet {ch['sheet']} was written again after this; undo that later change first")
    if ch.get("before") is None:
        path.unlink(missing_ok=True)
    else:
        path.write_text(json.dumps(ch["before"], ensure_ascii=False, indent=2), encoding="utf-8")
    append(project, "sheet-log.jsonl", {"id": cid, "ts": now(), "status": "undone", "by": by})
    return ch


def undo(project, cid, by="student"):
    """Undo one applied change by its id: 'p...' a proposal, 's...' a sheet write."""
    if str(cid).startswith("s"):
        return undo_sheet_write(project, cid, by)
    return undo_proposal(project, cid, by)


def history(project, limit=40):
    """Applied changes, newest first, each with what the UI needs to show a line and an Undo."""
    out = []
    for p in proposals(project):
        if p.get("status") not in ("approved", "undone"):
            continue
        if p.get("kind") == "idea_diagram":
            label = "Diagram changed"
        else:
            label = f"{p.get('line')}: " + (", ".join(p.get("changes") or {}) or "change")
        out.append({"id": p["id"], "kind": p.get("kind") or "bom", "label": label, "ts": p.get("decided_at") or p["ts"],
                    "by": p.get("decided_by"), "status": p["status"]})
    for c in _sheet_changes(project):
        out.append({"id": c["id"], "kind": "sheet", "label": f"Sheet {c['sheet']} written", "ts": c["ts"],
                    "by": c.get("by"), "status": "undone" if c["status"] == "undone" else "approved"})
    out.sort(key=lambda r: (r["ts"], r["id"]), reverse=True)
    return out[:limit]


def _drop_stale_lcsc(project, line, changes):
    """A declared LCSC code belongs to the part it was declared for: a new MPN voids it."""
    if "mpn" in changes and "lcsc" not in changes:
        cur = next((l for l in bom_lines(project) if l["key"] == line), None)
        if cur and cur.get("lcsc") and cur.get("mpn") != changes["mpn"]:
            changes["lcsc"] = ""
    return changes


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
        _drop_stale_lcsc(project, line, changes)
    return append(project, "bom-log.jsonl", {
        "ts": now(), "by": "student", "line": line, "changes": changes,
        "before": {field: existing[line].get(field)}})


def add_supply(project, line, supplier, stock, unit_price, mpn, qty_break=10, source="skill",
               library_type=None, package=None, code=None, datasheet_url=None, exact=None, code_mismatch=None):
    rec = {
        "ts": now(), "line": line, "mpn": mpn, "supplier": supplier, "stock": stock,
        "unit_price": unit_price, "qty_break": qty_break, "source": source,
    }
    if library_type is not None: rec["library_type"] = library_type
    if package is not None: rec["package"] = package
    if code is not None: rec["code"] = code
    if datasheet_url is not None: rec["datasheet_url"] = datasheet_url
    if exact is not None: rec["exact"] = exact
    if code_mismatch: rec["code_mismatch"] = code_mismatch      # the declared code is another part than the MPN
    return append(project, "supply-log.jsonl", rec)


def add_library(project, line, changes, by="agent"):
    return append(project, "library-log.jsonl", {"ts": now(), "by": by, "line": line, "changes": changes})


# ---------------------------------------------------------------- idea

def _atomic_write_json(path, obj):
    """Write JSON so a crash or a second reader never sees a half file. The temp name is per thread (the server
    is threaded); on Windows os.replace briefly fails while a reader holds the file open, so retry."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        for attempt in range(10):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.05)
    finally:
        tmp.unlink(missing_ok=True)


def _idea_defaults(idea):
    idea.setdefault("goal", "")
    idea.setdefault("agreed", [])
    idea.setdefault("blocks", [])
    idea.setdefault("links", [])
    idea.setdefault("confirmed", False)
    migrate_idea_diagram(idea)
    return idea


def load_idea(project):
    """The SAVED idea (idea.json). Everything downstream of the idea stage reads this, never the draft."""
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
    return _idea_defaults(idea)


def _normalise_idea(idea):
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
    return idea


def save_idea(project, idea):
    """Write the SAVED idea. The idea stage's own edits go through save_idea_draft instead."""
    _normalise_idea(idea)
    _atomic_write_json(pdir(project) / "idea.json", idea)
    return idea


# ---- draft: the working copy the agent and the student edit, saved by an explicit Save

IDEA_VERSIONS_KEEP = 20


def idea_draft_path(project):
    return pdir(project) / "idea-draft.json"


def idea_versions_path(project):
    return pdir(project) / "idea-versions.json"


def has_idea_draft(project):
    return idea_draft_path(project).is_file()


def load_idea_working(project):
    """What the student and the agent are looking at: the draft when there is one, else the saved idea."""
    path = idea_draft_path(project)
    if path.is_file():
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(d, dict) and isinstance(d.get("idea"), dict):
                return _idea_defaults(d["idea"])
        except (json.JSONDecodeError, OSError):
            pass
    return load_idea(project)


def idea_changes(saved, draft):
    """How many things differ between the saved idea and the draft: requirements added / removed / changed,
    the description, and diagram shapes / connectors / frames added / removed / changed. Derived, never counted."""
    n = 0
    sa = {i.get("topic"): i for i in saved.get("agreed", [])}
    da = {i.get("topic"): i for i in draft.get("agreed", [])}
    for t in set(sa) | set(da):
        a, b = sa.get(t), da.get(t)
        if a is None or b is None or (a.get("text"), a.get("status")) != (b.get("text"), b.get("status")):
            n += 1
    if (saved.get("goal") or "") != (draft.get("goal") or ""):
        n += 1
    sd, dd = saved.get("diagram") or {}, draft.get("diagram") or {}
    for key in ("shapes", "connectors", "frames"):
        a = {json.dumps(x, sort_keys=True) for x in sd.get(key, [])}
        b = {json.dumps(x, sort_keys=True) for x in dd.get(key, [])}
        n += max(len(a - b), len(b - a))
    return n


def idea_draft_marks(saved, draft):
    """Which requirements are new or changed in the draft, and whether the description changed: the UI tags them."""
    sa = {i.get("topic"): i.get("text") for i in saved.get("agreed", [])}
    marks = {i.get("topic"): ("new" if i.get("topic") not in sa else "changed")
             for i in draft.get("agreed", []) if sa.get(i.get("topic")) != i.get("text")}
    sg, dg = (saved.get("goal") or "").strip(), (draft.get("goal") or "").strip()
    return {"items": marks, "goal": False if sg == dg else ("changed" if sg else "new")}


def idea_draft_info(project):
    """For the UI bar: {"active", "changes": n, "since": ts, "marks": {"items": {topic: new|changed}, "goal": bool},
    "versions": [{n, ts, by, summary}]}."""
    versions = [{k: v.get(k) for k in ("n", "ts", "by", "summary")} for v in idea_versions(project)]
    info = {"active": False, "changes": 0, "since": None, "marks": {"items": {}, "goal": False},
            "versions": versions[::-1]}
    path = idea_draft_path(project)
    if path.is_file():
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            info["since"] = d.get("started")
            saved, draft = load_idea(project), _idea_defaults(d["idea"])
            info["changes"] = idea_changes(saved, draft)
            info["marks"] = idea_draft_marks(saved, draft)
            info["active"] = True
        except (json.JSONDecodeError, OSError, KeyError, TypeError):
            pass
    return info


def save_idea_draft(project, idea):
    """Write the draft. A draft equal to the saved idea is dropped (nothing to save or revert)."""
    _normalise_idea(idea)
    saved = load_idea(project)
    path = idea_draft_path(project)
    if idea_changes(saved, idea) == 0 and all(idea.get(k) == saved.get(k) for k in ("goal_status", "goal_by")):
        revert_idea_draft(project)
        return idea
    started = now()
    if path.is_file():
        try:
            started = json.loads(path.read_text(encoding="utf-8")).get("started") or started
        except (json.JSONDecodeError, OSError):
            pass
    _atomic_write_json(path, {"started": started, "updated": now(), "idea": idea})
    return idea


def revert_idea_draft(project):
    """Throw the draft away; the saved idea is what is left. Returns True when there was a draft."""
    path = idea_draft_path(project)
    if path.is_file():
        path.unlink()
        return True
    return False


def idea_versions(project):
    path = idea_versions_path(project)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _push_idea_version(project, idea, by, summary):
    versions = idea_versions(project)
    n = (versions[-1]["n"] + 1) if versions else 1
    versions.append({"n": n, "ts": now(), "by": by, "summary": summary, "idea": copy.deepcopy(idea)})
    _atomic_write_json(idea_versions_path(project), versions[-IDEA_VERSIONS_KEEP:])
    return n


def save_idea_from_draft(project, by="student"):
    """Save: the draft becomes the idea (one version-history entry, which is also the log entry).
    Returns the saved idea. Without a draft there is nothing to do and the saved idea is returned."""
    path = idea_draft_path(project)
    if not path.is_file():
        return load_idea(project)
    saved = load_idea(project)
    draft = load_idea_working(project)
    changes = idea_changes(saved, draft)
    if not idea_versions(project) and idea_exists(project):
        _push_idea_version(project, saved, "before first save", "the idea as it was before drafts")
    keep = {k: saved[k] for k in ("confirmed", "confirmed_at") if k in saved}
    draft.update(keep)
    save_idea(project, draft)
    _push_idea_version(project, draft, by, f"{changes} change{'s' if changes != 1 else ''} saved")
    revert_idea_draft(project)
    return draft


def idea_exists(project):
    return (pdir(project) / "idea.json").is_file()


def restore_idea_version(project, n):
    """Put saved version n into the draft (non-destructive: the student can Save it or Revert)."""
    v = next((x for x in idea_versions(project) if x.get("n") == n), None)
    if v is None:
        raise KeyError(f"no saved version {n}")
    saved = load_idea(project)
    idea = copy.deepcopy(v["idea"])
    for k in ("confirmed", "confirmed_at"):
        idea.pop(k, None)
        if k in saved:
            idea[k] = saved[k]
    idea = _idea_defaults(idea)
    save_idea_draft(project, idea)
    return load_idea_working(project)


def accept_all_proposed(project, accept=True):
    """Accept (or dismiss) every proposed requirement and description in the working idea."""
    idea = load_idea_working(project)
    kept = []
    for it in idea.get("agreed", []):
        if it.get("status") == "proposed":
            if not accept:
                if it.get("prev_text"):
                    it["text"] = it.pop("prev_text")
                    it["status"] = "confirmed"
                else:
                    continue
            else:
                it["status"] = "confirmed"
                it["ts"] = now()
        kept.append(it)
    idea["agreed"] = kept
    if idea.get("goal_status") == "proposed":
        prev = idea.pop("goal_prev", None) or {}
        if not accept:
            idea["goal"] = prev.get("text", "")
            idea["goal_by"] = prev.get("by", "student")
        idea["goal_status"] = "confirmed"
        idea["goal_ts"] = now()
    save_idea_draft(project, idea)
    return idea


GOAL_MAX = 3000


def check_idea_goal(text):
    """Raise ValueError unless text is an acceptable description (checked before anything is saved)."""
    if not isinstance(text, str) or len(text.strip()) > GOAL_MAX:
        raise ValueError(f"description must be text of at most {GOAL_MAX} chars")


def set_idea_goal(project, text, by="student"):
    """The description: the board in plain words (what it is, what it is for, the diagram told as text).
    Both go into the live draft at once; the student's Save (or Revert) is the only gate."""
    check_idea_goal(text)
    text = text.strip()
    idea = load_idea_working(project)
    if by == "agent" and not text:
        raise ValueError("description is empty")
    idea.pop("goal_prev", None)
    idea.update(goal=text, goal_by="agent" if by == "agent" else "student", goal_status="confirmed")
    idea["goal_ts"] = now()
    return save_idea_draft(project, idea)


def decide_idea_goal(project, accept):
    """Accept the agent's description, or dismiss it and put back the text it replaced."""
    idea = load_idea_working(project)
    if idea.get("goal_status") != "proposed":
        raise KeyError("no proposed description")
    prev = idea.pop("goal_prev", None) or {}
    if not accept:
        idea["goal"] = prev.get("text", "")
        idea["goal_by"] = prev.get("by", "student")
    idea["goal_status"] = "confirmed"
    idea["goal_ts"] = now()
    return save_idea_draft(project, idea)


def validate_idea_item(topic, text):
    if not topic or not isinstance(topic, str) or not topic.strip() or len(topic.strip()) > 60:
        raise ValueError("topic must be 1-60 chars")
    if not text or not isinstance(text, str) or not text.strip() or len(text.strip()) > 1000:
        raise ValueError("text must be 1-1000 chars")
    return topic.strip(), text.strip()


def propose_idea(project, topic, text, by="agent"):
    """A requirement, written into the live draft at once (the student's Save is the gate). 'proposed' only
    survives in projects made before the draft existed; Accept all / Dismiss all clear those."""
    topic, text = validate_idea_item(topic, text)
    idea = load_idea_working(project)
    item = next((i for i in idea["agreed"] if i["topic"] == topic), None)
    status = "confirmed"
    if item:
        if by == "agent" and item.get("text") and item["text"] != text:
            item["prev_text"] = item["text"]
        item.update(text=text, by=by, status=status, ts=now())
    else:
        idea["agreed"].append({"topic": topic, "text": text, "by": by, "status": status, "ts": now()})
    return save_idea_draft(project, idea)


def update_idea_item(project, index=None, old_topic=None, topic=None, text=None):
    """Student updates/renames a requirement row. Sets by='student' and status='confirmed'."""
    topic, text = validate_idea_item(topic, text)
    idea = load_idea_working(project)
    agreed = idea.get("agreed", [])
    item_idx = None
    if index is not None and isinstance(index, int) and 0 <= index < len(agreed):
        item_idx = index
    elif old_topic:
        item_idx = next((i for i, it in enumerate(agreed) if it["topic"] == old_topic), None)
    if item_idx is None:
        raise KeyError("requirement not found")

    for i, it in enumerate(agreed):
        if i != item_idx and it.get("topic") == topic:
            raise ValueError("topic exists")

    item = agreed[item_idx]
    item["topic"] = topic
    item["text"] = text
    item["by"] = "student"
    item["status"] = "confirmed"
    item["ts"] = now()
    save_idea_draft(project, idea)
    return idea


def delete_idea_item(project, index=None, topic=None):
    """Delete a requirement row."""
    idea = load_idea_working(project)
    agreed = idea.get("agreed", [])
    item_idx = None
    if index is not None and isinstance(index, int) and 0 <= index < len(agreed):
        item_idx = index
    elif topic:
        item_idx = next((i for i, it in enumerate(agreed) if it.get("topic") == topic), None)
    if item_idx is None:
        raise KeyError("requirement not found")
    deleted = agreed.pop(item_idx)
    save_idea_draft(project, idea)
    return deleted


def confirm_idea_item(project, index=None, topic=None):
    """Confirm a specific requirement item (or all if none specified)."""
    idea = load_idea_working(project)
    agreed = idea.get("agreed", [])
    if index is not None and isinstance(index, int) and 0 <= index < len(agreed):
        agreed[index]["status"] = "confirmed"
        agreed[index]["ts"] = now()
    elif topic:
        item = next((it for it in agreed if it.get("topic") == topic), None)
        if not item:
            raise KeyError(f"no requirement with topic {topic!r}")
        item["status"] = "confirmed"
        item["ts"] = now()
    else:
        for it in agreed:
            if it.get("status") == "proposed":
                it["status"] = "confirmed"
                it["ts"] = now()
    save_idea_draft(project, idea)
    return idea


def move_idea_item(project, from_index, to_index):
    """Reorder requirements list by moving an item from from_index to to_index."""
    idea = load_idea_working(project)
    agreed = idea.get("agreed", [])
    if not isinstance(from_index, int) or not isinstance(to_index, int):
        raise ValueError("from and to must be integers")
    if not (0 <= from_index < len(agreed)) or not (0 <= to_index < len(agreed)):
        raise ValueError("indices out of range")
    item = agreed.pop(from_index)
    agreed.insert(to_index, item)
    save_idea_draft(project, idea)
    return idea


def confirm_idea(project):
    """Confirm the idea: the draft (if any) is saved first, then the saved idea is marked confirmed."""
    idea = load_idea_working(project)
    for i in idea["agreed"]:
        if i["status"] == "proposed":
            i["status"] = "confirmed"
    if idea.get("goal_status") == "proposed":
        idea["goal_status"] = "confirmed"
        idea.pop("goal_prev", None)
    if has_idea_draft(project):
        save_idea_draft(project, idea)
        save_idea_from_draft(project, by="confirm")
        idea = load_idea(project)
    idea["confirmed"] = True
    idea["confirmed_at"] = now()
    return save_idea(project, idea)


# ---------------------------------------------------------------- diagram history & edit

def diagram_history_path(project):
    return pdir(project) / "idea-diagram-history.json"


def diagram_history(project):
    """Return the list of diagram history snapshots."""
    path = diagram_history_path(project)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_diagram_snapshot(project, diagram):
    """Keep last 20 diagram snapshots in idea-diagram-history.json."""
    path = diagram_history_path(project)
    history = []
    if path.is_file():
        try:
            history = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(history, list):
                history = []
        except Exception:
            history = []
    history.append({"ts": now(), "diagram": copy.deepcopy(diagram)})
    history = history[-20:]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    return history


def undo_diagram(project):
    """Restore the previous snapshot from idea-diagram-history.json."""
    path = diagram_history_path(project)
    if not path.is_file():
        raise ValueError("no undo history")
    try:
        history = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(history, list) or not history:
            raise ValueError("no undo history")
    except Exception as exc:
        if isinstance(exc, ValueError):
            raise
        raise ValueError("no undo history")

    last = history.pop()
    path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    idea = load_idea_working(project)
    valid_diag = validate_diagram(last.get("diagram", {}))
    idea["diagram"] = valid_diag
    save_idea_draft(project, idea)
    return valid_diag


def _auto_layout(shapes, connectors, frames):
    """Columns by link depth: sources on the left, the hub in the middle, what it drives on the right.
    Moves the shapes and frames in place; returns the ids it moved."""
    touched = set()
    frame_members = {}
    for f in frames:
        f_mems = []
        fx, fy, fw, fh = f["x"], f["y"], f["w"], f["h"]
        for s in shapes:
            cx = s["x"] + s["w"] / 2
            cy = s["y"] + s["h"] / 2
            if fx <= cx <= fx + fw and fy <= cy <= fy + fh:
                f_mems.append(s["id"])
        frame_members[f["id"]] = f_mems

    adj = defaultdict(list)
    in_deg = {s["id"]: 0 for s in shapes}
    for c in connectors:
        f_id = c["from"]["shape"] if isinstance(c["from"], dict) else c["from"]
        t_id = c["to"]["shape"] if isinstance(c["to"], dict) else c["to"]
        if f_id in in_deg and t_id in in_deg and f_id != t_id:
            adj[f_id].append(t_id)
            in_deg[t_id] += 1

    ranks = {}
    queue = [sid for sid, d in in_deg.items() if d == 0]
    if not queue and shapes:
        queue = [shapes[0]["id"]]
    for q in queue:
        ranks[q] = 0

    visited = set()
    curr = list(queue)
    while curr:
        nxt = []
        for u in curr:
            visited.add(u)
            r_u = ranks.get(u, 0)
            for v in adj[u]:
                ranks[v] = max(ranks.get(v, 0), r_u + 1)
                if v not in visited and v not in nxt:
                    nxt.append(v)
        curr = nxt

    for s in shapes:
        if s["id"] not in ranks:
            ranks[s["id"]] = 0

    by_rank = defaultdict(list)
    for s in shapes:
        by_rank[ranks[s["id"]]].append(s)

    start_x = 80.0
    start_y = 80.0
    gap_x = 80.0
    gap_y = 40.0
    for r in sorted(by_rank.keys()):
        group = by_rank[r]
        max_w = max(s["w"] for s in group)
        for i, s in enumerate(group):
            s["x"] = start_x
            s["y"] = start_y + i * (s["h"] + gap_y)
            touched.add(s["id"])
        start_x += max_w + gap_x

    for f in frames:
        mems = [s for s in shapes if s["id"] in frame_members.get(f["id"], [])]
        if mems:
            pad = 24.0
            f["x"] = min(s["x"] for s in mems) - pad
            f["y"] = min(s["y"] for s in mems) - pad
            f["w"] = (max(s["x"] + s["w"] for s in mems) - min(s["x"] for s in mems)) + 2 * pad
            f["h"] = (max(s["y"] + s["h"] for s in mems) - min(s["y"] for s in mems)) + 2 * pad
            touched.add(f["id"])
    return touched


def _hidden_links(shapes, connectors):
    """Links drawn straight through another block: every block in one row with a hub in it shows a hub as
    a chain (MCU - sensor - buzzer), though each one is wired to the MCU. Both Sonnet and Flash drew that."""
    box = {sh["id"]: sh for sh in shapes}
    for c in connectors:
        ends = [c[k]["shape"] if isinstance(c[k], dict) else c[k] for k in ("from", "to")]
        if not all(e in box for e in ends):
            continue
        a, b = (box[e] for e in ends)
        ya, yb = a["y"] + a["h"] / 2, b["y"] + b["h"] / 2
        if abs(ya - yb) > min(a["h"], b["h"]) / 2:
            continue
        lo, hi = sorted((a["x"] + a["w"] / 2, b["x"] + b["w"] / 2))
        for o in shapes:
            if o is a or o is b:
                continue
            if lo < o["x"] + o["w"] / 2 < hi and o["y"] <= (ya + yb) / 2 <= o["y"] + o["h"]:
                return True
    return False


def apply_diagram_edit(project, ops):
    """Apply a batch of diagram edit operations directly.
    Cap 100 ops. Validated with validate_diagram; any invalid op raises and leaves diagram unchanged.
    Before applying, keeps a snapshot in idea-diagram-history.json.
    """
    if not isinstance(ops, list):
        raise ValueError("ops must be a list")
    if len(ops) > 100:
        raise ValueError("too many ops (max 100)")

    idea = load_idea_working(project)
    cur_diag = idea.get("diagram", {"shapes": [], "connectors": [], "frames": []})
    shapes = [copy.deepcopy(s) for s in cur_diag.get("shapes", [])]
    connectors = [copy.deepcopy(c) for c in cur_diag.get("connectors", [])]
    frames = [copy.deepcopy(f) for f in cur_diag.get("frames", [])]

    touched_ids = set()

    for op in ops:
        if not isinstance(op, dict):
            raise ValueError("op must be an object")
        op_name = op.get("op") or op.get("type")
        if not op_name:
            raise ValueError("op requires op or type field")
        # Sonnet wrote remove_connector; the verb is not worth refusing the whole edit over
        verb, _, noun = str(op_name).partition("_")
        verb = {"remove": "delete", "del": "delete", "edit": "update", "modify": "update", "move": "update",
                "create": "add", "new": "add"}.get(verb, verb)
        op_name = f"{verb}_{noun}" if noun else op_name
        # a model often escapes the line break twice: "Coin cell\\nCR2032" would show the backslash
        for part in (op, *(v for v in op.values() if isinstance(v, dict))):
            for k in ("text", "label"):
                if isinstance(part.get(k), str):
                    part[k] = part[k].replace("\\n", "\n")

        if op_name == "add_shape":
            sid = op.get("id")
            if sid:
                if not isinstance(sid, str) or not ID_RE.match(sid):
                    raise ValueError(f"invalid shape id: {sid!r}")
                if any(s["id"] == sid for s in shapes):
                    raise ValueError(f"shape {sid} already exists")
            else:
                idx = 1
                existing_sids = {s["id"] for s in shapes}
                while f"shape_{idx}" in existing_sids:
                    idx += 1
                sid = f"shape_{idx}"

            stype = op.get("type", "block")
            if stype not in VALID_SHAPE_TYPES:
                raise ValueError(f"unknown shape type: {stype!r}")

            w = float(op.get("w", 160.0))
            h = float(op.get("h", 68.0))
            if not math.isfinite(w) or not math.isfinite(h) or w <= 0 or h <= 0 or w > 20000 or h > 20000:
                raise ValueError("shape dimensions out of range")

            if "x" in op and "y" in op and op["x"] is not None and op["y"] is not None:
                x = float(op["x"])
                y = float(op["y"])
                if not math.isfinite(x) or not math.isfinite(y):
                    raise ValueError("shape coordinates must be finite")
            else:
                near_id = op.get("near")
                if not near_id:
                    for c in connectors:
                        f_sh = c.get("from", {}).get("shape") if isinstance(c.get("from"), dict) else c.get("from")
                        t_sh = c.get("to", {}).get("shape") if isinstance(c.get("to"), dict) else c.get("to")
                        if f_sh == sid and t_sh and any(s["id"] == t_sh for s in shapes):
                            near_id = t_sh
                            break
                        elif t_sh == sid and f_sh and any(s["id"] == f_sh for s in shapes):
                            near_id = f_sh
                            break
                rel_shape = next((s for s in shapes if s["id"] == near_id), None) if near_id else None
                if rel_shape:
                    cand_x = rel_shape["x"] + rel_shape["w"] + 40.0
                    cand_y = rel_shape["y"]
                elif shapes:
                    cand_x = max(s["x"] + s["w"] for s in shapes) + 40.0
                    cand_y = shapes[0]["y"]
                else:
                    cand_x = 100.0
                    cand_y = 100.0

                def overlaps(cx, cy, cw, ch):
                    for s in shapes:
                        if not (cx + cw <= s["x"] or cx >= s["x"] + s["w"] or cy + ch <= s["y"] or cy >= s["y"] + s["h"]):
                            return True
                    return False

                while overlaps(cand_x, cand_y, w, h):
                    cand_y += 80.0
                    if cand_y > 1000.0:
                        cand_x += 200.0
                        cand_y = 100.0
                x, y = cand_x, cand_y

            text = str(op.get("text", ""))
            if len(text) > 2000:
                raise ValueError("text must be <= 2000 chars")

            dom = _domain(op.get("domain"))
            dom_colors = DOMAIN_COLORS.get(dom, {"fill": "#ffffff", "stroke": "#1e293b"})

            fill = op.get("fill") or dom_colors["fill"]
            stroke = op.get("stroke") or dom_colors["stroke"]
            if not COLOR_RE.match(fill):
                raise ValueError(f"invalid fill: {fill!r}")
            if not COLOR_RE.match(stroke):
                raise ValueError(f"invalid stroke: {stroke!r}")

            stroke_style = op.get("strokeStyle", "solid")
            if stroke_style not in VALID_STROKE_STYLES:
                raise ValueError(f"invalid strokeStyle: {stroke_style!r}")

            stroke_width = float(op.get("strokeWidth", 2.0))
            if not math.isfinite(stroke_width) or stroke_width < 0 or stroke_width > 50:
                raise ValueError("invalid strokeWidth")

            font_size = op.get("fontSize", "M")
            if isinstance(font_size, (int, float)):
                if not math.isfinite(font_size) or font_size < 4 or font_size > 120:
                    raise ValueError("invalid fontSize")
            elif font_size not in VALID_FONT_SIZES:
                raise ValueError(f"invalid fontSize: {font_size}")

            bold = bool(op.get("bold", True))
            align = op.get("align", "center")
            if align not in VALID_ALIGN:
                raise ValueError(f"invalid align: {align}")

            z = float(op.get("z", len(shapes) + 1))
            locked = bool(op.get("locked", False))

            new_s = {
                "id": sid, "type": stype, "x": x, "y": y, "w": w, "h": h,
                "text": text, "fill": fill, "stroke": stroke, "strokeStyle": stroke_style,
                "strokeWidth": stroke_width, "fontSize": font_size, "bold": bold,
                "align": align, "z": z, "locked": locked,
            }
            if dom:
                new_s["domain"] = dom
            if "role" in op and isinstance(op["role"], str):
                new_s["role"] = op["role"][:200]
            shapes.append(new_s)
            touched_ids.add(sid)

        elif op_name == "update_shape":
            sid = op.get("id")
            if not sid:
                raise ValueError("update_shape requires id")
            shape = next((s for s in shapes if s["id"] == sid), None)
            if not shape:
                raise ValueError(f"shape {sid} not found")

            if "type" in op:
                if op["type"] not in VALID_SHAPE_TYPES:
                    raise ValueError(f"unknown shape type: {op['type']!r}")
                shape["type"] = op["type"]
            for num_f in ("x", "y", "w", "h"):
                if num_f in op:
                    v = float(op[num_f])
                    if not math.isfinite(v):
                        raise ValueError(f"field {num_f} must be finite")
                    if num_f in ("w", "h") and (v <= 0 or v > 20000):
                        raise ValueError(f"field {num_f} out of range")
                    shape[num_f] = v
            if "text" in op:
                t = str(op["text"])
                if len(t) > 2000:
                    raise ValueError("text <= 2000 chars")
                shape["text"] = t
            if "domain" in op:
                dom = _domain(op["domain"])
                shape["domain"] = dom
                if "fill" not in op and dom in DOMAIN_COLORS:
                    shape["fill"] = DOMAIN_COLORS[dom]["fill"]
                if "stroke" not in op and dom in DOMAIN_COLORS:
                    shape["stroke"] = DOMAIN_COLORS[dom]["stroke"]
            if "fill" in op:
                if not COLOR_RE.match(op["fill"]):
                    raise ValueError("invalid fill")
                shape["fill"] = op["fill"]
            if "stroke" in op:
                if not COLOR_RE.match(op["stroke"]):
                    raise ValueError("invalid stroke")
                shape["stroke"] = op["stroke"]
            if "strokeStyle" in op:
                if op["strokeStyle"] not in VALID_STROKE_STYLES:
                    raise ValueError("invalid strokeStyle")
                shape["strokeStyle"] = op["strokeStyle"]
            if "strokeWidth" in op:
                sw = float(op["strokeWidth"])
                if not math.isfinite(sw) or sw < 0 or sw > 50:
                    raise ValueError("invalid strokeWidth")
                shape["strokeWidth"] = sw
            if "fontSize" in op:
                fs = op["fontSize"]
                if isinstance(fs, (int, float)):
                    if not math.isfinite(fs) or fs < 4 or fs > 120:
                        raise ValueError("invalid fontSize")
                elif fs not in VALID_FONT_SIZES:
                    raise ValueError("invalid fontSize")
                shape["fontSize"] = fs
            if "bold" in op:
                shape["bold"] = bool(op["bold"])
            if "align" in op:
                if op["align"] not in VALID_ALIGN:
                    raise ValueError("invalid align")
                shape["align"] = op["align"]
            if "z" in op:
                z = float(op["z"])
                if not math.isfinite(z):
                    raise ValueError("z must be finite")
                shape["z"] = z
            if "locked" in op:
                shape["locked"] = bool(op["locked"])
            if "role" in op:
                shape["role"] = str(op["role"])[:200]
            touched_ids.add(sid)

        elif op_name == "delete_shape":
            sid = op.get("id")
            if not sid:
                raise ValueError("delete_shape requires id")
            if not any(s["id"] == sid for s in shapes):
                raise ValueError(f"shape {sid} not found")
            shapes = [s for s in shapes if s["id"] != sid]
            connectors = [c for c in connectors if not (
                (isinstance(c.get("from"), dict) and c["from"].get("shape") == sid) or
                (isinstance(c.get("to"), dict) and c["to"].get("shape") == sid) or
                c.get("from") == sid or c.get("to") == sid
            )]
            touched_ids.add(sid)

        elif op_name == "add_connector":
            cid = op.get("id")
            if cid:
                if not isinstance(cid, str) or not ID_RE.match(cid):
                    raise ValueError(f"invalid connector id: {cid!r}")
                if any(c["id"] == cid for c in connectors):
                    raise ValueError(f"connector {cid} already exists")
            else:
                idx = 1
                existing_cids = {c["id"] for c in connectors}
                while f"conn_{idx}" in existing_cids:
                    idx += 1
                cid = f"conn_{idx}"

            def parse_ep(raw, def_side, name):
                if isinstance(raw, dict):
                    if "shape" in raw:
                        sh = raw["shape"]
                        if not any(s["id"] == sh for s in shapes):
                            raise ValueError(f"connector {cid} {name} shape {sh!r} not found")
                        if "point" in raw:
                            if raw["point"] not in VALID_ENDPOINT_POINTS:
                                raise ValueError(f"invalid point: {raw['point']!r}")
                            return {"shape": sh, "point": raw["point"]}
                        side = raw.get("side", def_side)
                        if side not in VALID_ENDPOINT_SIDES:
                            raise ValueError(f"invalid side: {side}")
                        return {"shape": sh, "side": side}
                    elif "x" in raw and "y" in raw:
                        x, y = float(raw["x"]), float(raw["y"])
                        if not math.isfinite(x) or not math.isfinite(y):
                            raise ValueError(f"connector {cid} {name} coordinates must be finite")
                        return {"x": x, "y": y}
                    raise ValueError(f"connector {cid} {name} must have shape or coordinates")
                elif isinstance(raw, str):
                    if not any(s["id"] == raw for s in shapes):
                        raise ValueError(f"connector {cid} {name} shape {raw!r} not found")
                    side = op.get(f"{name}_side", def_side)
                    if side not in VALID_ENDPOINT_SIDES:
                        side = def_side
                    return {"shape": raw, "side": side}
                raise ValueError(f"connector {cid} {name} required")

            ep_f_raw = op.get("from") or op.get("from_id") or op.get("source")
            ep_t_raw = op.get("to") or op.get("to_id") or op.get("target")
            ep_f = parse_ep(ep_f_raw, "right", "from")
            ep_t = parse_ep(ep_t_raw, "left", "to")

            label = str(op.get("label", ""))[:500]
            style = op.get("style", "solid")
            if style not in VALID_STROKE_STYLES:
                raise ValueError(f"invalid style: {style}")
            arrows = op.get("arrows", "end")
            if arrows not in VALID_CONNECT_ARROWS:
                raise ValueError(f"invalid arrows: {arrows}")
            route = op.get("route", "elbow")
            if route not in VALID_CONNECT_ROUTES:
                raise ValueError(f"invalid route: {route}")
            stroke = op.get("stroke", "#dc2626" if "safety" in label.lower() else "#64748b")
            if not COLOR_RE.match(stroke):
                raise ValueError(f"invalid stroke: {stroke}")

            connectors.append({
                "id": cid, "from": ep_f, "to": ep_t, "label": label,
                "stroke": stroke, "style": style, "arrows": arrows, "route": route,
            })
            touched_ids.add(cid)
            if "shape" in ep_f:
                touched_ids.add(ep_f["shape"])
            if "shape" in ep_t:
                touched_ids.add(ep_t["shape"])

        elif op_name == "update_connector":
            cid = op.get("id")
            if not cid:
                raise ValueError("update_connector requires id")
            conn = next((c for c in connectors if c["id"] == cid), None)
            if not conn:
                raise ValueError(f"connector {cid} not found")
            if "from" in op:
                conn["from"] = parse_ep(op["from"], "right", "from")
            if "to" in op:
                conn["to"] = parse_ep(op["to"], "left", "to")
            if "label" in op:
                conn["label"] = str(op["label"])[:500]
            if "style" in op:
                if op["style"] not in VALID_STROKE_STYLES:
                    raise ValueError("invalid style")
                conn["style"] = op["style"]
            if "arrows" in op:
                if op["arrows"] not in VALID_CONNECT_ARROWS:
                    raise ValueError("invalid arrows")
                conn["arrows"] = op["arrows"]
            if "route" in op:
                if op["route"] not in VALID_CONNECT_ROUTES:
                    raise ValueError("invalid route")
                conn["route"] = op["route"]
            if "stroke" in op:
                if not COLOR_RE.match(op["stroke"]):
                    raise ValueError("invalid stroke")
                conn["stroke"] = op["stroke"]
            touched_ids.add(cid)

        elif op_name == "delete_connector":
            cid = op.get("id")
            if not cid:
                raise ValueError("delete_connector requires id")
            if not any(c["id"] == cid for c in connectors):
                raise ValueError(f"connector {cid} not found")
            connectors = [c for c in connectors if c["id"] != cid]
            touched_ids.add(cid)

        elif op_name == "add_frame":
            fid = op.get("id")
            if fid:
                if not isinstance(fid, str) or not ID_RE.match(fid):
                    raise ValueError(f"invalid frame id: {fid!r}")
                if any(f["id"] == fid for f in frames):
                    raise ValueError(f"frame {fid} already exists")
            else:
                idx = 1
                existing_fids = {f["id"] for f in frames}
                while f"frame_{idx}" in existing_fids:
                    idx += 1
                fid = f"frame_{idx}"

            title = str(op.get("title", ""))[:500]
            stroke = op.get("stroke", "#94a3b8")
            if not COLOR_RE.match(stroke):
                raise ValueError("invalid stroke")

            if "around" in op:
                around = op["around"]
                if not isinstance(around, list) or not around:
                    raise ValueError("around must be a non-empty list of shape ids")
                for sh_id in around:
                    if not any(s["id"] == sh_id for s in shapes):
                        raise ValueError(f"frame {fid} around shape {sh_id!r} not found")
                member_shapes = [s for s in shapes if s["id"] in around]
                pad = float(op.get("padding", 24.0))
                min_x = min(s["x"] for s in member_shapes)
                min_y = min(s["y"] for s in member_shapes)
                max_x = max(s["x"] + s["w"] for s in member_shapes)
                max_y = max(s["y"] + s["h"] for s in member_shapes)
                x = min_x - pad
                y = min_y - pad
                w = (max_x - min_x) + 2 * pad
                h = (max_y - min_y) + 2 * pad
            else:
                x = float(op.get("x", 50.0))
                y = float(op.get("y", 50.0))
                w = float(op.get("w", 400.0))
                h = float(op.get("h", 300.0))
                if not math.isfinite(x) or not math.isfinite(y) or not math.isfinite(w) or not math.isfinite(h) or w < 0 or h < 0:
                    raise ValueError("frame coordinates/dimensions out of range")

            frames.append({
                "id": fid, "x": x, "y": y, "w": w, "h": h,
                "title": title, "stroke": stroke,
            })
            touched_ids.add(fid)

        elif op_name == "update_frame":
            fid = op.get("id")
            if not fid:
                raise ValueError("update_frame requires id")
            frame = next((f for f in frames if f["id"] == fid), None)
            if not frame:
                raise ValueError(f"frame {fid} not found")
            if "around" in op:
                around = op["around"]
                if not isinstance(around, list) or not around:
                    raise ValueError("around must be a non-empty list of shape ids")
                for sh_id in around:
                    if not any(s["id"] == sh_id for s in shapes):
                        raise ValueError(f"frame {fid} around shape {sh_id!r} not found")
                member_shapes = [s for s in shapes if s["id"] in around]
                pad = float(op.get("padding", 24.0))
                min_x = min(s["x"] for s in member_shapes)
                min_y = min(s["y"] for s in member_shapes)
                max_x = max(s["x"] + s["w"] for s in member_shapes)
                max_y = max(s["y"] + s["h"] for s in member_shapes)
                frame["x"] = min_x - pad
                frame["y"] = min_y - pad
                frame["w"] = (max_x - min_x) + 2 * pad
                frame["h"] = (max_y - min_y) + 2 * pad
            else:
                for num_f in ("x", "y", "w", "h"):
                    if num_f in op:
                        v = float(op[num_f])
                        if not math.isfinite(v) or (num_f in ("w", "h") and v < 0):
                            raise ValueError(f"frame {num_f} invalid")
                        frame[num_f] = v
            if "title" in op:
                frame["title"] = str(op["title"])[:500]
            if "stroke" in op:
                if not COLOR_RE.match(op["stroke"]):
                    raise ValueError("invalid stroke")
                frame["stroke"] = op["stroke"]
            touched_ids.add(fid)

        elif op_name == "delete_frame":
            fid = op.get("id")
            if not fid:
                raise ValueError("delete_frame requires id")
            if not any(f["id"] == fid for f in frames):
                raise ValueError(f"frame {fid} not found")
            frames = [f for f in frames if f["id"] != fid]
            touched_ids.add(fid)

        elif op_name == "auto_layout":
            touched_ids |= _auto_layout(shapes, connectors, frames)
        else:
            raise ValueError(f"unknown op: {op_name} (ops: add_, update_, delete_ + shape, connector or frame; auto_layout)")

    # the agent's own new blocks are laid out again when a link would pass through another block; a block the
    # student placed is never moved by this
    added = {op.get("id") for op in ops if isinstance(op, dict) and (op.get("op") or op.get("type")) == "add_shape"}
    if added and not any(o.get("op") == "auto_layout" for o in ops if isinstance(o, dict))             and all(sh["id"] in added for sh in shapes) and _hidden_links(shapes, connectors):
        touched_ids |= _auto_layout(shapes, connectors, frames)

    valid_diag = validate_diagram({"shapes": shapes, "connectors": connectors, "frames": frames})
    save_diagram_snapshot(project, cur_diag)
    idea["diagram"] = valid_diag
    save_idea_draft(project, idea)
    return {"ok": True, "diagram": valid_diag, "touched": list(touched_ids)}


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


def check_sheet(sheet, bom_refs, pending_refs=()):
    """(errors, warnings) for one sheet. Never block, verify later: only a sheet that cannot be drawn at all is an
    error (not a dict, no parts list, a part without ref or pins, a duplicate ref). A ref not in the BOM yet, a pin
    without a net and an undefined section are warnings: the sheet is still written and shows the gap."""
    errors, warnings = [], []
    if not isinstance(sheet, dict) or not isinstance(sheet.get("parts"), list):
        return ["a sheet needs a 'parts' list"], warnings
    sections = {s.get("id") for s in sheet.get("sections", []) if isinstance(s, dict)}
    seen = set()
    for part in sheet["parts"]:
        if not isinstance(part, dict):
            errors.append("a part is not an object")
            continue
        ref = part.get("ref")
        if not ref:
            errors.append("a part has no ref")
            continue
        if ref in seen:
            errors.append(f"{ref}: appears twice")
        seen.add(ref)
        pins = part.get("pins")
        if not isinstance(pins, list) or not pins:
            errors.append(f"{ref}: no pins")
            pins = []
        elif not all(isinstance(pin, dict) for pin in pins):
            errors.append(f"{ref}: a pin is not an object")
            pins = []
        if ref not in bom_refs:
            warnings.append(f"{ref}: waits for approval" if ref in pending_refs else f"{ref}: not in the BOM yet")
        if sections and part.get("section") not in sections:
            warnings.append(f"{ref}: section {part.get('section')!r} is not defined (drawn in the first section)")
        for pin in pins:
            if not (pin.get("net") or "").strip():
                warnings.append(f"{ref}.{pin.get('name') or pin.get('num')}: open pin (no net yet)")
    return errors, warnings


def validate_sheet(sheet, bom_refs):
    """Every problem with one sheet, errors first then warnings (list of strings; empty = fine)."""
    errors, warnings = check_sheet(sheet, bom_refs)
    return errors + warnings


def pending_bom_refs(project):
    """Refs a pending BOM proposal would add: those parts may be drawn before the student approves."""
    refs = set()
    for p in proposals(project):
        if p.get("kind") == "bom" and p.get("status") == "pending":
            ch = p.get("changes") or {}
            refs.update(ch.get("refs") or ([p["line"]] if re.fullmatch(r"[A-Za-z]+\d+", p.get("line") or "") else []))
    return refs


def bom_status_of(ref, bom_refs, pending_refs):
    """'' (in the BOM), 'pending' (a proposal waits for the student) or 'missing'. Always computed from the current
    BOM and proposals, so approving or rejecting a proposal changes it with nothing to refresh."""
    return "" if ref in bom_refs else "pending" if ref in pending_refs else "missing"


def mark_bom_status(project, parts):
    bom_refs = {r for l in bom_lines(project) for r in l.get("refs") or []}
    pending = pending_bom_refs(project)
    out = []
    for part in parts:
        part = dict(part)
        st = bom_status_of(part.get("ref"), bom_refs, pending)
        if st:
            part["bom_status"] = st
        else:
            part.pop("bom_status", None)
        out.append(part)
    return out


def sheet_gaps(project):
    """What a partial sheet still lacks: open pins and parts not in the BOM (or waiting for approval)."""
    open_pins, parts = [], []
    for sh in sheet_ids(project):
        marked = mark_bom_status(project, load_sheet(project, sh).get("parts", []))
        for part in marked:
            if part.get("bom_status"):
                parts.append({"sheet": sh, "ref": part["ref"], "status": part["bom_status"]})
            for pin in part.get("pins", []):
                if not (pin.get("net") or "").strip():
                    open_pins.append({"sheet": sh, "ref": part["ref"], "pin": pin.get("name") or pin.get("num") or ""})
    return {"open_pins": open_pins, "parts": parts}


def write_sheet(project, sheet_id, sheet):
    """Write a sheet, partial or not. Refuses only a sheet that cannot be drawn; the rest comes back as warnings."""
    refs = set()
    for l in bom_lines(project):
        refs.update(l.get("refs") or [])
    errors, warnings = check_sheet(sheet, refs, pending_bom_refs(project))
    if errors:
        return {"ok": False, "errors": errors}
    sheet = {**sheet, "id": workspace.safe_name(sheet_id)}
    parts = []
    for part in sheet["parts"]:
        part = dict(part)
        part["pins"] = [{**pin, "net": (pin.get("net") or "").strip()} for pin in part["pins"]]
        parts.append(part)
    sheet["parts"] = mark_bom_status(project, _mark_pins_source(project, parts))
    d = netlist_dir(project)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{sheet['id']}.json").write_text(json.dumps(sheet, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "sheet": sheet["id"], "warnings": warnings}


# ---------------------------------------------------------------- unverified pins
# Verify later, don't block now: the agent places an IC from the well-known pinout of its MPN/package and the
# part is marked pins_source "agent" until a datasheet is dropped in and verify_part passes (or the student accepts
# it as is). Generic parts never need a datasheet. The only gate is the Final checks list.

SIMPLE_PREFIXES = ("R", "C", "L", "D", "LED", "FB", "Y", "X", "XTAL", "J", "P", "H", "TP", "SW", "F", "FID", "MH")


def is_simple_ref(ref):
    """Passives and simple parts (R, C, L, LED, diode, ferrite, crystal, connector, test point): no datasheet needed."""
    prefix = re.match(r"[A-Za-z]+", ref or "")
    return bool(prefix) and prefix.group(0).upper() in SIMPLE_PREFIXES


def pins_status(line, entry):
    """('', '') for a simple part or one not on a sheet yet; else ('verified'|'accepted'|'unverified'|'mismatch', issues)."""
    refs = line.get("refs") or []
    if not refs or all(is_simple_ref(r) for r in refs):
        return "", ""
    entry = entry or {}
    if entry.get("verify") == "pass":
        return "verified", ""
    if entry.get("verify") == "mismatch":
        return ("accepted" if entry.get("pins_accepted") else "mismatch"), entry.get("issues", "")
    if entry.get("pins_accepted"):
        return "accepted", ""
    return "unverified", ""


def _mark_pins_source(project, parts):
    lib = library_parts(project)
    by_ref = {}
    for l in bom_lines(project):
        for r in l.get("refs") or []:
            by_ref[r] = l
    out = []
    for part in parts:
        part = dict(part)
        ref = part.get("ref")
        if is_simple_ref(ref):
            part.pop("pins_source", None)
        else:
            ln = by_ref.get(ref)
            st = pins_status(ln, lib.get(ln["key"]))[0] if ln else "unverified"
            if st in ("verified", "accepted"):
                part["pins_source"] = "datasheet" if st == "verified" else "student"
            else:
                part["pins_source"] = "agent"
        out.append(part)
    return out


def refresh_pins_source(project):
    """Re-mark the parts of every sheet after a verify or an accept."""
    for sh in sheet_ids(project):
        sheet = load_sheet(project, sh)
        marked = _mark_pins_source(project, sheet.get("parts", []))
        if marked != sheet.get("parts"):
            (netlist_dir(project) / f"{sh}.json").write_text(
                json.dumps({**sheet, "parts": marked}, ensure_ascii=False, indent=2), encoding="utf-8")


def unverified_parts(project, verify_new=True):
    """Every BOM line on a sheet whose pins are not verified or accepted. With verify_new, a datasheet that has
    appeared since is used first (verify_part), which clears the mark or raises the conflicting pins."""
    if verify_new:
        auto_attach(project)           # a document that arrived by hand is matched to its part first
    lines = [l for l in bom(project, write=False) if l.get("on_sheet") and l.get("pins_status") in ("unverified", "mismatch")]
    if verify_new:
        import sources
        import verify_part
        ran = False
        for l in lines:
            if l["pins_status"] == "unverified" and (l.get("datasheet") or sources.find_for(project, l.get("mpn"))):
                verify_part.verify(project, l["key"])
                ran = True
        if ran:
            refresh_pins_source(project)
            lines = [l for l in bom(project, write=False) if l.get("on_sheet") and l.get("pins_status") in ("unverified", "mismatch")]
    return [{"line": l["key"], "refs": l.get("refs", []), "mpn": l.get("mpn"), "status": l["pins_status"],
             "issues": l.get("pins_issues", "")} for l in lines]


def accept_pins(project, key):
    """The student accepts the agent's pins as is."""
    add_library(project, key, {"pins_accepted": True}, by="student")
    refresh_pins_source(project)


# ---------------------------------------------------------------- datasheet link
# A BOM line's `datasheet` names a document of the project's sources/ (or the shared library). Set by the student
# in the UI, by the agent (part.attach_datasheet) or by the matcher when a file arrives; each link is verified at once.

def _line_of(project, line_or_ref):
    for l in bom_lines(project):
        if l["key"] == line_or_ref or line_or_ref in (l.get("refs") or []):
            return l
    raise KeyError(f"no BOM line or part {line_or_ref!r}")


def _verify_line(project, key):
    import verify_part
    r = verify_part.verify(project, key)
    return {"status": {"pass": "verified"}.get(r["verify"], r["verify"]), "issues": r.get("issues", "")}


def attach_datasheet(project, line_or_ref, doc_name, by="student"):
    """Link a document to a BOM line (a line key or a designator) and verify the part's pins against it.
    Returns {ok, line, refs, name, status: verified|mismatch|unchecked, issues}."""
    import sources
    line = _line_of(project, line_or_ref)
    sources.adopt(project)
    name = pathlib.Path(doc_name or "").name
    if not name or not ((sources.folder_of(project) / name).is_file() or (sources.cache() / name).is_file()):
        raise ValueError(f"no document {doc_name!r} in this project's sources or the shared library")
    if line.get("datasheet") != name:
        append(project, "bom-log.jsonl", {"ts": now(), "by": by, "line": line["key"], "changes": {"datasheet": name},
                                          "before": {"datasheet": line.get("datasheet")}})
    return {"ok": True, "line": line["key"], "refs": line.get("refs", []), "name": name, **_verify_line(project, line["key"])}


def detach_datasheet(project, line_or_ref, by="student"):
    """Take the link away: the part goes back to unverified until a datasheet is linked again."""
    line = _line_of(project, line_or_ref)
    if line.get("datasheet"):
        append(project, "bom-log.jsonl", {"ts": now(), "by": by, "line": line["key"], "changes": {"datasheet": ""},
                                          "before": {"datasheet": line.get("datasheet")}})
    add_library(project, line["key"], {"verify": "unchecked", "issues": "datasheet detached", "verified_at": now()}, by=by)
    refresh_pins_source(project)
    return {"ok": True, "line": line["key"], "refs": line.get("refs", [])}


def auto_attach(project):
    """Match the project's documents to the ICs that have no datasheet yet, link the unambiguous ones and verify
    them. Returns {matched: [{name, line, ref, how, status, issues}], unmatched: [names nobody claims]}."""
    import sources
    sources.adopt(project)
    todo = [(l["key"], l.get("mpn")) for l in bom_lines(project)
            if not l.get("datasheet") and l.get("mpn") not in (None, "", "—", "-")
            and l.get("refs") and not all(is_simple_ref(r) for r in l["refs"])]
    found, free = sources.match_documents(project, todo)
    matched = []
    for key, m in found.items():
        r = attach_datasheet(project, key, m["name"], by="auto")
        matched.append({"name": m["name"], "line": key, "ref": (r["refs"] or [key])[0], "how": m["how"],
                        "status": r["status"], "issues": r["issues"]})
    linked = {l.get("datasheet") for l in bom_lines(project)}
    return {"matched": matched, "unmatched": [n for n in free if n not in linked]}


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
