"""Altium .RUL design rules writer, JLC preset rules, and PcbDoc diff tool."""
import argparse
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent

from altium import parse_rul_bytes, read_pcbdoc, read_rul  # noqa: E402


def format_rul_bytes(rules: list[dict[str, str]]) -> bytes:
    """Serialize a list of rule dicts to Altium .RUL byte format.

    Inverse of scripts/altium/rul.py: records separated by pipe-delimited
    key-value pairs, latin-1 encoding, with line ends \\xb6\\r\\n.
    """
    lines = []
    for r in rules:
        parts = [f"{k}={v}" for k, v in r.items()]
        line_str = "|" + "|".join(parts) + "|\xb6\r\n"
        lines.append(line_str.encode("latin-1"))
    return b"".join(lines)


def write_rul(rules: list[dict[str, str]], path) -> pathlib.Path:
    """Write rule dicts to an Altium .RUL export file."""
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(format_rul_bytes(rules))
    return p


def get_jlc_preset() -> dict:
    """Load the JLC preset rules from config/defaults.json."""
    cfg_path = REPO / "config" / "defaults.json"
    if not cfg_path.is_file():
        return {"rules": [], "capabilities_url": "https://jlcpcb.com/capabilities/pcb-capabilities"}
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        return data.get("jlc_rules", {})
    except Exception:
        return {"rules": [], "capabilities_url": "https://jlcpcb.com/capabilities/pcb-capabilities"}


def get_preset_rule_records() -> list[dict[str, str]]:
    """Return raw Altium record dicts for all rules in the JLC preset."""
    preset = get_jlc_preset()
    records = []
    for r in preset.get("rules", []):
        attrs = r.get("attributes")
        if attrs:
            records.append(attrs)
    return records


def rule_display_value(rule: dict[str, str]) -> str:
    """Extract a concise human-readable value representation for a rule."""
    kind = rule.get("RULEKIND", "")
    if kind == "Clearance":
        return rule.get("GAP") or rule.get("GENERICCLEARANCE", "")
    elif kind == "Width":
        min_w = rule.get("MINLIMIT", "")
        pref_w = rule.get("PREFEREDWIDTH", "")
        max_w = rule.get("MAXLIMIT", "")
        return f"Min: {min_w}, Pref: {pref_w}, Max: {max_w}"
    elif kind == "RoutingVias":
        hole = rule.get("HOLEWIDTH", rule.get("MINHOLEWIDTH", ""))
        dia = rule.get("WIDTH", rule.get("MINWIDTH", ""))
        return f"Hole: {hole}, Dia: {dia}"
    elif kind == "MinimumAnnularRing":
        return rule.get("MINIMUMRING", rule.get("MINIMUM", ""))
    elif kind == "HoleSize":
        min_h = rule.get("MINLIMIT", "")
        max_h = rule.get("MAXLIMIT", "")
        return f"Min: {min_h}, Max: {max_h}"
    elif kind == "SilkToSolderMaskClearance":
        return rule.get("MINSILKSCREENTOMASKGAP", "")
    elif kind == "SilkToSilkClearance":
        return rule.get("SILKTOSILKCLEARANCE", "")
    elif kind == "SolderMaskExpansion":
        return rule.get("EXPANSION", "")
    elif kind == "MinimumSolderMaskSliver":
        return rule.get("MINSOLDERMASKWIDTH", "")
    elif kind == "HoleToHoleClearance":
        return rule.get("GAP", "")
    elif kind == "ComponentClearance":
        return rule.get("GAP", "")
    elif kind == "PlaneClearance":
        return rule.get("CLEARANCE", "")
    else:
        # Generic fallback
        for key in ("GAP", "CLEARANCE", "WIDTH", "EXPANSION", "MINIMUMRING"):
            if key in rule:
                return rule[key]
        return "—"


def _normalize_val(val: str) -> str:
    """Normalize whitespace and case for value comparison."""
    if not val:
        return ""
    return "".join(val.lower().split())


def _prio(r: dict) -> int:
    try:
        return int(r.get("PRIORITY", "9999"))
    except ValueError:
        return 9999


def _scope_all(r: dict) -> bool:
    return (r.get("SCOPE1EXPRESSION", "All").strip().lower() in ("all", "")
            and r.get("SCOPE2EXPRESSION", "All").strip().lower() in ("all", ""))


def _effective_index(rules, kind, skip=()):
    """Index of the highest-priority enabled scope-All rule of a kind, or None."""
    best = None
    for i, r in enumerate(rules):
        if i in skip or r.get("RULEKIND") != kind or not _scope_all(r):
            continue
        if r.get("ENABLED", "TRUE").upper() == "FALSE":
            continue
        if best is None or _prio(r) < _prio(rules[best]):
            best = i
    return best


_CONTROL_KEYS = {"NAME", "RULEKIND", "SCOPE1EXPRESSION", "SCOPE2EXPRESSION", "ENABLED", "PRIORITY"}


def _uid(name: str) -> str:
    import hashlib
    h = hashlib.sha1(name.encode("utf-8")).digest()
    return "".join(chr(65 + b % 26) for b in h[:8])


def board_rul_records(pcbdoc_path, preset=None) -> list[dict[str, str]]:
    """Full rule set for Altium "Replace existing rules": the board's rules
    unchanged, except that per preset kind the effective scope-All rule gets
    the JLC values (NAME, UNIQUEID, PRIORITY and other keys kept). Preset
    kinds with no scope-All rule are appended at the lowest priority of that
    kind (so scoped board rules keep winning inside their scope)."""
    if preset is None:
        preset = get_preset_rule_records()
    board = [dict(r) for r in read_pcbdoc(pcbdoc_path).get("rules", [])]
    names = {r.get("NAME") for r in board}
    for pr in preset:
        kind = pr.get("RULEKIND")
        values = {k: v for k, v in pr.items() if k not in _CONTROL_KEYS}
        idx = _effective_index(board, kind)
        if idx is not None:
            board[idx].update(values)
            continue
        same = [r for r in board if r.get("RULEKIND") == kind]
        name = pr.get("NAME", kind)
        while name in names:
            name += "_JLC"
        names.add(name)
        rec = {
            "LAYER": "TOP", "LOCKED": "FALSE", "POLYGONOUTLINE": "FALSE",
            "USERROUTED": "TRUE", "KEEPOUT": "FALSE", "UNIONINDEX": "0",
            "RULEKIND": kind,
            "NETSCOPE": "DifferentNets" if kind == "Clearance" else "AnyNet",
            "LAYERKIND": "SameLayer",
            "SCOPE1EXPRESSION": "All", "SCOPE2EXPRESSION": "All",
            "NAME": name, "ENABLED": "TRUE",
            "PRIORITY": str(max((_prio(r) for r in same), default=0) + 1),
            "COMMENT": "JLC preset", "UNIQUEID": _uid(name),
            "DEFINEDBYLOGICALDOCUMENT": "FALSE",
        }
        rec.update(values)
        board.append(rec)
    return board


# ---------------------------------------------------------------------------
# Numeric comparison of board rules against the JLC preset (verdicts)
# ---------------------------------------------------------------------------

SAME_REL = 0.02          # equal within 2 % ...
SAME_ABS_MM = 0.003      # ... or 0.003 mm: unit rounding (5.9055 mil = 0.15 mm vs 6 mil)
FAB_MIN_TOL_MM = 0.001   # float/rounding slack when testing against a fab minimum

VERDICTS = ("same", "safer", "tighter_ok", "below_fab_min", "unknown")
# "worse" first; used to pick the deciding bound
_VERDICT_RANK = {"below_fab_min": 0, "unknown": 1, "tighter_ok": 2, "same": 3, "safer": 4}

_UNIT_MM = {"mil": 0.0254, "mm": 1.0, "in": 25.4, "inch": 25.4, '"': 25.4, "um": 0.001}
_NUM_RE = re.compile(r'^\s*([-+]?\d+(?:\.\d+)?)\s*(mil|mm|inch|in|um|")?\s*$', re.IGNORECASE)

# kind -> [(field, role, board attribute keys, preset *_mm key)]
#   floor   : a lower limit; a larger board value is more conservative ("safer"),
#             a smaller one is "tighter" and is checked against the fab minimum
#   ceiling : an upper limit; a smaller board value is more conservative, a larger
#             one only loosens the rule (no fab maximum is stored, so it is informational)
#   target  : a preferred/standard value; only "same" can be judged
_FIELDS = {
    "Clearance": [("gap", "floor", ("GAP", "GENERICCLEARANCE"), "value_mm")],
    "Width": [("min", "floor", ("MINLIMIT",), "min_mm"),
              ("pref", "target", ("PREFEREDWIDTH",), "pref_mm"),
              ("max", "ceiling", ("MAXLIMIT",), "max_mm")],
    "RoutingVias": [("hole", "floor", ("HOLEWIDTH", "MINHOLEWIDTH"), "hole_mm"),
                    ("dia", "floor", ("WIDTH", "MINWIDTH"), "dia_mm")],
    "MinimumAnnularRing": [("ring", "floor", ("MINIMUMRING", "MINIMUM"), "value_mm")],
    "HoleSize": [("min", "floor", ("MINLIMIT",), "min_mm"),
                 ("max", "ceiling", ("MAXLIMIT",), "max_mm")],
    "SilkToSolderMaskClearance": [("gap", "floor", ("MINSILKSCREENTOMASKGAP",), "value_mm")],
    "SolderMaskExpansion": [("expansion", "target", ("EXPANSION",), "value_mm")],
}


def to_mm(val) -> float | None:
    """Parse '6mil', '0.15 mm', '0.0059in', '15um' or a bare number (mil, as
    Altium and altium.pcbdoc.mil_to_mm treat it) into mm; None if unparsable."""
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val) * 0.0254
    m = _NUM_RE.match(str(val))
    if not m:
        return None
    return float(m.group(1)) * _UNIT_MM[(m.group(2) or "mil").lower()]


def _fmt(x: float) -> str:
    return f"{x:.4g}"


def _values_from_attrs(kind: str, attrs: dict) -> dict:
    """{field: mm} from a raw Altium rule record."""
    out = {}
    for field, _role, keys, _mmkey in _FIELDS.get(kind, []):
        for k in keys:
            v = to_mm(attrs.get(k))
            if v is not None:
                out[field] = v
                break
    return out


def _values_from_text(kind: str, text: str) -> dict:
    """{field: mm} from a preset display string ('6mil' or 'Min: 5mil, Pref: 8mil, Max: 40mil')."""
    fields = [f[0] for f in _FIELDS.get(kind, [])]
    if len(fields) == 1:
        v = to_mm(text)
        return {fields[0]: v} if v is not None else {}
    out = {}
    for name, num in re.findall(r"([A-Za-z]+)\s*:\s*([^,\s]+)", text or ""):
        v = to_mm(num)
        if v is not None and name.lower() in fields:
            out[name.lower()] = v
    return out


def preset_values_mm(pr: dict) -> dict:
    """{field: mm} of a preset rule: its .RUL attributes first, then the *_mm
    keys, then the display string."""
    kind = pr.get("kind") or (pr.get("attributes") or {}).get("RULEKIND", "")
    vals = _values_from_attrs(kind, pr.get("attributes") or {})
    for field, _role, _keys, mmkey in _FIELDS.get(kind, []):
        if field not in vals and isinstance(pr.get(mmkey), (int, float)):
            vals[field] = float(pr[mmkey])
    if len(vals) < len(_FIELDS.get(kind, [])):
        for field, v in _values_from_text(kind, pr.get("value") or "").items():
            vals.setdefault(field, v)
    return vals


def preset_fab_min(pr: dict, field: str) -> float | None:
    """JLC fab minimum (mm) for one field of a preset rule, or None when unknown.
    `fab_min_mm` is a number (applies to the kind's only/first floor field) or a
    {field: mm} dict."""
    fab = pr.get("fab_min_mm")
    if isinstance(fab, dict):
        v = fab.get(field)
        return float(v) if isinstance(v, (int, float)) else None
    if isinstance(fab, (int, float)) and not isinstance(fab, bool):
        floors = [f[0] for f in _FIELDS.get(pr.get("kind", ""), []) if f[1] == "floor"]
        return float(fab) if floors and floors[0] == field else None
    return None


def values_same(a: float, b: float) -> bool:
    """Equal within unit rounding: 2 % or 0.003 mm."""
    d = abs(a - b)
    return d <= SAME_ABS_MM or d <= SAME_REL * abs(b)


def _judge_bound(role: str, board: float, preset: float | None, fab_min: float | None) -> tuple[str, str]:
    """(verdict, note) for one bound. See _FIELDS for the roles."""
    fab_txt = f"JLC fab min {_fmt(fab_min)} mm" if fab_min is not None else ""
    if preset is not None and values_same(board, preset):
        return "same", "same as the preset"
    if role == "ceiling":
        if preset is None:
            return "unknown", "no preset maximum to compare with"
        if board < preset:
            return "safer", "lower maximum than the preset (more restrictive)"
        return "unknown", "higher maximum than the preset; no fab maximum is stored, so not judged"
    if role == "floor" and preset is not None and board > preset:
        return "safer", "above the preset (more conservative)"
    # below the preset's safe value (floor), or a target that differs
    if fab_min is not None and board < fab_min - FAB_MIN_TOL_MM:
        return "below_fab_min", f"BELOW {fab_txt}: the fab may reject or alter it"
    if role == "target":
        return "unknown", "differs from the preset; direction cannot be judged" + (
            f" ({fab_txt}, not below it)" if fab_txt else "")
    if fab_min is None:
        return "unknown", "tighter than the preset; no fab minimum is stored to check against"
    return "tighter_ok", f"tighter than the preset but not below {fab_txt}"


def _combine(bounds: list[dict]) -> tuple[str, list[str]]:
    """Overall verdict and the bound names that decide it. Floor bounds decide
    when the rule has any (they are the fab-relevant ones: min width, via hole,
    ...); otherwise target bounds; ceilings only decide on their own."""
    for role in ("floor", "target", "ceiling"):
        cands = [b for b in bounds if b["role"] == role]
        if cands:
            break
    else:
        return "unknown", []
    worst = min(cands, key=lambda b: _VERDICT_RANK[b["verdict"]])["verdict"]
    if worst == "same" and any(b["verdict"] == "safer" for b in cands):
        worst = "safer"
    return worst, [b["name"] for b in cands if b["verdict"] == worst]


def judge_rule(kind: str, board_rule: dict, preset_rule: dict) -> dict:
    """Numeric comparison of one board rule against a preset rule of the same
    kind: {verdict, detail, decided_by, bounds}. All values in mm."""
    fields = _FIELDS.get(kind)
    if not fields:
        return {"verdict": "unknown", "detail": "not a JLC preset rule kind", "decided_by": [], "bounds": []}
    board = _values_from_attrs(kind, board_rule)
    preset = preset_values_mm(preset_rule)
    bounds = []
    for field, role, _keys, _mmkey in fields:
        if field not in board:
            continue
        fab_min = preset_fab_min(preset_rule, field)
        verdict, note = _judge_bound(role, board[field], preset.get(field), fab_min)
        bounds.append({"name": field, "role": role, "board_mm": round(board[field], 4),
                       "preset_mm": round(preset[field], 4) if field in preset else None,
                       "fab_min_mm": fab_min, "verdict": verdict, "note": note})
    if not bounds:
        return {"verdict": "unknown", "detail": "board value could not be read as a length",
                "decided_by": [], "bounds": []}
    verdict, decided_by = _combine(bounds)
    if any(b["role"] == "floor" for b in bounds):   # a preferred value next to a floor is only informational
        for b in bounds:
            if b["role"] == "target" and b["verdict"] == "unknown":
                b["note"] = "differs from the preset (informational)"
    parts = []
    for b in bounds:
        p = f" vs preset {_fmt(b['preset_mm'])} mm" if b["preset_mm"] is not None else ""
        deciding = " [decides]" if len(bounds) > 1 and verdict != "same" and b["name"] in decided_by else ""
        parts.append(f"{b['name']} {_fmt(b['board_mm'])} mm{p}: {b['note']}{deciding}")
    detail = "; ".join(parts)
    if str(board_rule.get("ENABLED", "TRUE")).upper() == "FALSE":
        verdict, detail = "unknown", "rule is disabled in Altium; " + detail
    return {"verdict": verdict, "detail": detail, "decided_by": decided_by, "bounds": bounds}


def annular_ring_summary(doc: dict | None) -> dict | None:
    """Smallest annular ring actually on the board, (diameter - hole) / 2, over
    vias and plated drilled pads (copper size = smallest top/middle/bottom
    dimension). Unplated mounting holes are ignored. None when the board has no
    drills or the reader did not expose them."""
    if not isinstance(doc, dict):
        return None
    rings = []
    for v in doc.get("vias") or []:
        hole, dia = v.get("hole_mm") or 0, v.get("dia_mm") or 0
        if hole > 0 and dia > 0:
            rings.append({"source": "via", "ring_mm": round((dia - hole) / 2, 4), "hole_mm": hole,
                          "copper_mm": dia, "net": v.get("net"), "x_mm": v.get("x_mm"), "y_mm": v.get("y_mm")})
    for p in doc.get("drilled_pads") or []:
        hole, size = p.get("hole_mm") or 0, p.get("min_size_mm") or 0
        if p.get("plated") and hole > 0 and size > 0:
            rings.append({"source": "pad", "ring_mm": round((size - hole) / 2, 4), "hole_mm": hole,
                          "copper_mm": size, "ref": p.get("ref"), "pad": p.get("name"),
                          "x_mm": p.get("x_mm"), "y_mm": p.get("y_mm")})
    if not rings:
        return None
    worst = min(rings, key=lambda r: r["ring_mm"])
    by_src = {s: [r["ring_mm"] for r in rings if r["source"] == s] for s in ("via", "pad")}
    return {
        "min_ring_mm": worst["ring_mm"],
        "worst": worst,
        "via_count": len(by_src["via"]),
        "pad_count": len(by_src["pad"]),
        "min_via_ring_mm": min(by_src["via"]) if by_src["via"] else None,
        "min_pad_ring_mm": min(by_src["pad"]) if by_src["pad"] else None,
    }


def _ring_where(worst: dict) -> str:
    if worst["source"] == "via":
        return f"via hole {_fmt(worst['hole_mm'])} mm / diameter {_fmt(worst['copper_mm'])} mm"
    return (f"pad {worst.get('ref') or ''}-{worst.get('pad') or ''} hole {_fmt(worst['hole_mm'])} mm / "
            f"copper {_fmt(worst['copper_mm'])} mm")


def judge_missing_ring(preset_rule: dict, doc: dict | None) -> dict:
    """Verdict for a preset MinimumAnnularRing rule the board has no rule for,
    from the board's actual vias and plated pads."""
    summ = annular_ring_summary(doc)
    if summ is None:
        return {"verdict": "unknown", "decided_by": [], "bounds": [],
                "detail": "no rule on the board; actual annular ring not computed (no via/pad drill data)"}
    preset = preset_values_mm(preset_rule).get("ring")
    fab_min = preset_fab_min(preset_rule, "ring")
    verdict, note = _judge_bound("floor", summ["min_ring_mm"], preset, fab_min)
    pv = f"; preset {_fmt(preset)} mm" if preset is not None else ""
    fv = f", JLC fab min {_fmt(fab_min)} mm" if fab_min is not None else ""
    if verdict == "below_fab_min":
        note = "BELOW the fab minimum: the fab may reject or alter it"
    elif fab_min is not None and verdict in ("same", "safer"):
        note = "at or above the fab minimum"
    detail = (f"no rule on the board; actual minimum ring {_fmt(summ['min_ring_mm'])} mm "
              f"({_ring_where(summ['worst'])}; {summ['via_count']} vias, {summ['pad_count']} plated pads)"
              f"{pv}{fv}: {note}")
    return {"verdict": verdict, "detail": detail, "decided_by": ["ring"], "actual": summ,
            "bounds": [{"name": "ring", "role": "floor", "board_mm": summ["min_ring_mm"],
                        "preset_mm": round(preset, 4) if preset is not None else None,
                        "fab_min_mm": fab_min, "verdict": verdict, "note": note}]}


def _geometry_note(kind: str, doc: dict | None) -> str:
    """What the board's actual vias/holes look like, for rules that govern them."""
    if not isinstance(doc, dict):
        return ""
    vias, pads = doc.get("vias") or [], doc.get("drilled_pads") or []
    if kind == "RoutingVias" and vias:
        sizes: dict = {}
        for v in vias:
            k = (v.get("hole_mm"), v.get("dia_mm"))
            sizes[k] = sizes.get(k, 0) + 1
        top = sorted(sizes.items(), key=lambda kv: -kv[1])[:3]
        return "actual vias (hole/diameter): " + ", ".join(
            f"{_fmt(h)}/{_fmt(d)} mm x{n}" for (h, d), n in top)
    if kind == "HoleSize" and (vias or pads):
        holes = [v["hole_mm"] for v in vias if v.get("hole_mm")] + [p["hole_mm"] for p in pads if p.get("hole_mm")]
        if holes:
            return f"actual drills on the board: {_fmt(min(holes))} to {_fmt(max(holes))} mm"
    if kind == "MinimumAnnularRing":
        summ = annular_ring_summary(doc)
        if summ:
            return f"actual minimum ring {_fmt(summ['min_ring_mm'])} mm ({_ring_where(summ['worst'])})"
    return ""


def _with_geometry(judged: dict, kind: str, doc: dict | None) -> dict:
    note = _geometry_note(kind, doc)
    if note:
        judged["detail"] = (judged["detail"] + "; " if judged["detail"] else "") + note
    return judged


def diff_pcbdoc(pcbdoc, preset_rules: list[dict] = None) -> list[dict]:
    """diff_rules() for a PcbDoc path or an already read PcbDoc dict, including
    the geometry-based checks (actual annular ring, via and drill sizes)."""
    doc = pcbdoc if isinstance(pcbdoc, dict) else read_pcbdoc(pcbdoc)
    return diff_rules(doc.get("rules", []), preset_rules, board_geom=doc)


def diff_rules(board_rules: list[dict[str, str]], preset_rules: list[dict] = None,
               board_geom: dict | None = None) -> list[dict]:
    """Compare a PcbDoc's rules against the preset rules.

    Returns a table of:
        {rule, kind, board value, preset value, status, verdict, detail, ...}
    where status is one of:
        'match'            board value matches preset value (as text)
        'differs'          board value differs from preset value (as text)
        'missing_on_board' preset rule not present in the board
        'extra_on_board'   custom board rule not in preset
    and verdict is the numeric judgement in mm (unit rounding ignored):
        'same'          equal within 2 % or 0.003 mm
        'safer'         more conservative than the preset (larger clearance / min width /
                        via hole ..., lower maximum)
        'tighter_ok'    tighter than the preset's safe value, not below the JLC fab minimum
        'below_fab_min' below the JLC fab minimum (the fab may reject or alter it)
        'unknown'       no numeric comparison possible (no fab minimum stored, direction
                        undefined, disabled rule, no preset of that kind)
    `detail` explains it per bound and names the bound that decides; `bounds` has the
    numbers. `board_geom` (the dict from read_pcbdoc) adds the actual annular ring for a
    missing MinimumAnnularRing rule and via/drill sizes to the via and hole rules.
    """
    if preset_rules is None:
        preset_info = get_jlc_preset()
        preset_rules = preset_info.get("rules", [])

    matched_board_indices = set()
    table = []

    # 1. Compare each preset rule against board rules
    for pr in preset_rules:
        p_name = pr.get("name", "")
        p_kind = pr.get("kind", "")
        p_val = pr.get("value")
        if not p_val and pr.get("attributes"):
            p_val = rule_display_value(pr["attributes"])
        p_val = p_val or "—"

        # Effective rule per kind: highest priority (lowest PRIORITY number)
        # among enabled scope-All rules; fall back to a same-name rule.
        matched_idx = _effective_index(board_rules, p_kind, matched_board_indices)
        if matched_idx is None:
            for i, br in enumerate(board_rules):
                if i not in matched_board_indices and br.get("NAME") == p_name and br.get("RULEKIND") == p_kind:
                    matched_idx = i
                    break

        if matched_idx is not None:
            matched_board_indices.add(matched_idx)
            br = board_rules[matched_idx]
            b_val = rule_display_value(br)
            b_name = br.get("NAME", p_name)

            if _normalize_val(b_val) == _normalize_val(p_val):
                status = "match"
            else:
                status = "differs"

            row = {
                "rule": b_name,
                "kind": p_kind,
                "board value": b_val,
                "preset value": p_val,
                "status": status,
                "board_value": b_val,
                "preset_value": p_val,
            }
            row.update(_with_geometry(judge_rule(p_kind, br, pr), p_kind, board_geom))
        else:
            row = {
                "rule": p_name,
                "kind": p_kind,
                "board value": "—",
                "preset value": p_val,
                "status": "missing_on_board",
                "board_value": "—",
                "preset_value": p_val,
            }
            if p_kind == "MinimumAnnularRing":
                row.update(judge_missing_ring(pr, board_geom))
            else:
                row.update({"verdict": "unknown", "detail": "no rule of this kind on the board",
                            "decided_by": [], "bounds": []})
        table.append(row)

    # 2. Add extra board rules that were not matched to any preset rule
    for i, br in enumerate(board_rules):
        if i in matched_board_indices:
            continue
        b_name = br.get("NAME", f"Rule_{i+1}")
        b_kind = br.get("RULEKIND", "")
        b_val = rule_display_value(br)
        row = {
            "rule": b_name,
            "kind": b_kind,
            "board value": b_val,
            "preset value": "—",
            "status": "extra_on_board",
            "board_value": b_val,
            "preset_value": "—",
        }
        # A scoped / lower-priority rule of a preset kind is still judged against
        # that preset rule (e.g. a Width_RF rule against the preset Width).
        same_kind = next((p for p in preset_rules if p.get("kind") == b_kind), None)
        if same_kind is None:
            row.update({"verdict": "unknown", "detail": "not a JLC preset rule kind",
                        "decided_by": [], "bounds": []})
        else:
            judged = judge_rule(b_kind, br, same_kind)
            judged["detail"] = "scoped/extra rule, compared with the preset " + same_kind.get("name", b_kind) + ": " + judged["detail"]
            row.update(judged)
        table.append(row)

    return table


def main(argv=None):
    import oscompat
    oscompat.utf8_stdio()
    ap = argparse.ArgumentParser(description="PCB design rules reader, writer, and diff tool")
    sub = ap.add_subparsers(dest="cmd")

    diff_p = sub.add_parser("diff", help="Diff PcbDoc rules against JLC preset")
    diff_p.add_argument("pcbdoc", help="Path to .PcbDoc file")
    diff_p.add_argument("--json", action="store_true",
                        help="Print the rows as JSON (with verdict, detail, bounds) instead of a table")

    exp_p = sub.add_parser("export", help="Export JLC preset rules to .RUL file")
    exp_p.add_argument("output", help="Output .RUL file path")
    exp_p.add_argument("--board", help="PcbDoc: write the board's full rule set with JLC values (use Replace existing rules)")

    sub.add_parser("preset", help="Print JLC preset design rules")

    args = ap.parse_args(argv)

    if args.cmd == "diff":
        doc = read_pcbdoc(args.pcbdoc)
        diff = diff_pcbdoc(doc)
        if args.json:
            print(json.dumps({"pcbdoc": str(args.pcbdoc), "rules": diff,
                              "annular_ring": annular_ring_summary(doc)}, ensure_ascii=False, indent=2))
            return 0
        print(f"Rules diff for {args.pcbdoc} vs JLC preset ({len(diff)} rules):")
        print(f"{'Rule':<25} {'Kind':<25} {'Board Value':<30} {'Preset Value':<30} {'Status':<16} {'Verdict':<14} Detail")
        print("-" * 160)
        for r in diff:
            print(f"{r['rule']:<25} {r['kind']:<25} {r['board value']:<30} {r['preset value']:<30} "
                  f"{r['status']:<16} {r['verdict']:<14} {r['detail']}")
        return 0

    elif args.cmd == "export":
        if args.board:
            records = board_rul_records(args.board)
            out = write_rul(records, args.output)
            print(f"Exported {len(records)} board-aware rules to {out} (import with 'Replace existing rules')")
        else:
            records = get_preset_rule_records()
            out = write_rul(records, args.output)
            print(f"Exported {len(records)} preset rules to {out} (import with 'Merge', then raise *_1 rules in Priorities)")
        return 0

    elif args.cmd == "preset":
        preset = get_jlc_preset()
        print(f"JLC Preset Rules (source: {preset.get('capabilities_url', 'JLC Capabilities')})")
        for r in preset.get("rules", []):
            print(f"  {r.get('name', ''):<25} {r.get('kind', ''):<25} {r.get('value', ''):<30} {r.get('description', '')}")
        return 0

    else:
        ap.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
