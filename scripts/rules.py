"""Altium .RUL design rules writer, JLC preset rules, and PcbDoc diff tool."""
import argparse
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent

from altium import parse_rul_bytes, read_pcbdoc, read_rul  # noqa: E402
import jlc_preset  # noqa: E402


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


def get_jlc_preset(board: dict | None = None) -> dict:
    """The JLC preset for a board: its layer count, copper weight and mask colour (a project.json `board`
    block) pick the numbers; unknown means 2 layers, 1 oz, green. The name says which one."""
    return jlc_preset.build_preset(board)


def get_preset_rule_records(board: dict | None = None) -> list[dict[str, str]]:
    """Return raw Altium record dicts for all rules in the JLC preset."""
    return [r["attributes"] for r in get_jlc_preset(board).get("rules", []) if r.get("attributes")]


def board_settings(project: str | None = None, layers=None, oz=None, colour=None) -> dict:
    """A project's `board` block (config defaults underneath), with command-line overrides on top."""
    board: dict = {}
    if project:
        import project as project_mod
        board = dict(project_mod.board(project))
    for key, val in (("layers", layers), ("copper_oz", oz), ("mask_colour", colour)):
        if val is not None:
            board[key] = val
    return board


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
    elif kind == "ViasUnderSMD":
        return "Allowed" if str(rule.get("ALLOWED", "TRUE")).upper() == "TRUE" else "Not allowed"
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


def _norm_scope(expr) -> str:
    """A rule scope for comparison: blank means All; case and spaces do not matter."""
    return "".join(str(expr or "all").lower().split()) or "all"


_ALL = ("all", "all")


def _rule_scopes(r: dict) -> tuple[str, str]:
    return _norm_scope(r.get("SCOPE1EXPRESSION")), _norm_scope(r.get("SCOPE2EXPRESSION"))


def _preset_scopes(pr: dict) -> tuple[str, str]:
    a = pr.get("attributes") or {}
    return (_norm_scope(a.get("SCOPE1EXPRESSION", pr.get("scope1"))),
            _norm_scope(a.get("SCOPE2EXPRESSION", pr.get("scope2"))))


def _effective_index(rules, kind, skip=(), scopes=_ALL):
    """Index of the highest-priority enabled rule of a kind with exactly these scopes
    (default: scope All on both sides), or None."""
    best = None
    for i, r in enumerate(rules):
        if i in skip or r.get("RULEKIND") != kind or _rule_scopes(r) != scopes:
            continue
        if r.get("ENABLED", "TRUE").upper() == "FALSE":
            continue
        if best is None or _prio(r) < _prio(rules[best]):
            best = i
    return best


def _closest_preset(preset_rules, kind, br):
    """The preset rule a board rule of this kind is judged against: same scopes, else the one for the same
    object type (IsVia / IsPad), else the scope-All one, else the first."""
    cands = [p for p in preset_rules if p.get("kind") == kind]
    if not cands:
        return None
    scopes = _rule_scopes(br)
    for p in cands:
        if _preset_scopes(p) == scopes:
            return p
    for key in ("isvia", "ispad"):
        if key in scopes[0]:
            for p in cands:
                if key in _preset_scopes(p)[0]:
                    return p
    return next((p for p in cands if _preset_scopes(p) == _ALL), cands[0])


_CONTROL_KEYS = {"NAME", "RULEKIND", "SCOPE1EXPRESSION", "SCOPE2EXPRESSION", "ENABLED", "PRIORITY"}


def _uid(name: str) -> str:
    import hashlib
    h = hashlib.sha1(name.encode("utf-8")).digest()
    return "".join(chr(65 + b % 26) for b in h[:8])


def board_rul_records(pcbdoc_path, preset=None, board=None) -> list[dict[str, str]]:
    """Full rule set for Altium "Replace existing rules": the board's rules
    unchanged, except that per preset rule the board rule with the same kind and
    scope (the effective one, by priority) gets the JLC values (NAME, UNIQUEID,
    PRIORITY and other keys kept). A preset rule the board has no rule for is
    appended: a scope-All rule at the lowest priority of its kind (so scoped board
    rules keep winning inside their scope), a scoped rule (IsPad, IsVia) just above
    the kind's scope-All rule, because below it the scope-All rule would shadow it.
    `board` is the project's board block (see get_jlc_preset); `preset` overrides it."""
    if preset is None:
        preset = get_preset_rule_records(board)
    rules = [dict(r) for r in read_pcbdoc(pcbdoc_path).get("rules", [])]
    names = {r.get("NAME") for r in rules}
    for pr in preset:
        kind = pr.get("RULEKIND")
        scopes = _preset_scopes({"attributes": pr})
        values = {k: v for k, v in pr.items() if k not in _CONTROL_KEYS}
        idx = _effective_index(rules, kind, scopes=scopes)
        if idx is not None:
            rules[idx].update(values)
            continue
        same = [r for r in rules if r.get("RULEKIND") == kind]
        prio = max((_prio(r) for r in same), default=0) + 1
        if scopes != _ALL:
            above = _effective_index(rules, kind)
            if above is not None:
                prio = _prio(rules[above])
                for r in same:
                    if "PRIORITY" in r and _prio(r) >= prio:
                        r["PRIORITY"] = str(_prio(r) + 1)
        name = pr.get("NAME", kind)
        while name in names:
            name += "_JLC"
        names.add(name)
        rec = {
            "LAYER": "TOP", "LOCKED": "FALSE", "POLYGONOUTLINE": "FALSE",
            "USERROUTED": "TRUE", "KEEPOUT": "FALSE", "UNIONINDEX": "0",
            "RULEKIND": kind,
            "NETSCOPE": "DifferentNets" if kind in ("Clearance", "BoardOutlineClearance") else "AnyNet",
            "LAYERKIND": "SameLayer",
            "SCOPE1EXPRESSION": pr.get("SCOPE1EXPRESSION", "All"), "SCOPE2EXPRESSION": pr.get("SCOPE2EXPRESSION", "All"),
            "NAME": name, "ENABLED": "TRUE",
            "PRIORITY": str(prio),
            "COMMENT": "JLC preset", "UNIQUEID": _uid(name),
            "DEFINEDBYLOGICALDOCUMENT": "FALSE",
        }
        rec.update(values)
        rules.append(rec)
    return rules


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
    "MinimumSolderMaskSliver": [("width", "floor", ("MINSOLDERMASKWIDTH",), "value_mm")],
    "BoardOutlineClearance": [("gap", "floor", ("GAP", "GENERICCLEARANCE"), "value_mm")],
    "HoleToHoleClearance": [("gap", "floor", ("GAP",), "value_mm")],
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


def _dfm_note(preset_rule: dict, board_mm: float) -> tuple[str | None, str]:
    """(level, text) when JLCDFM would rate this value Danger or Warning, else (None, ""). The verdict
    stays the JLC fab floor: JLCDFM's limits are whole mils and stricter than JLC's page (a drawn 0.10 mm
    is 3.94 mil, Danger against its 4 mil), so this only adds what the student will see in JLCDFM."""
    worst = None
    for chk in preset_rule.get("jlcdfm") or []:
        level = jlc_preset.dfm_level(board_mm, chk["range_mil"])
        if level in ("Danger", "Warning") and (worst is None or (level == "Danger" and worst[0] != "Danger")):
            worst = (level, chk)
    if worst is None:
        return None, ""
    level, chk = worst
    r0, r1, _ = chk["range_mil"]
    below = r0 if level == "Danger" else r1
    return level, f"JLCDFM {chk['check']}: {level} (below {below} mil)"


def _judge_flag(board_rule: dict, preset_rule: dict) -> dict:
    """Via in SMD pad: a yes/no rule, so there is no number to compare, only 'same as the preset' or not."""
    want = str((preset_rule.get("attributes") or {}).get("ALLOWED", "FALSE")).upper()
    have = str(board_rule.get("ALLOWED", "TRUE")).upper()
    if str(board_rule.get("ENABLED", "TRUE")).upper() == "FALSE":
        verdict, detail = "unknown", "rule is disabled in Altium"
    elif have == want:
        verdict, detail = "same", "same as the preset"
    else:
        verdict = "unknown"
        detail = ("vias are allowed in SMD pads on the board; JLC makes via-in-pad only as filled and plated-over "
                  "vias (extra cost on boards under 6 layers) and JLCDFM warns about them" if have == "TRUE"
                  else "via in pad is not allowed on the board, the preset allows it")
    return {"verdict": verdict, "detail": detail, "decided_by": [], "bounds": []}


def judge_rule(kind: str, board_rule: dict, preset_rule: dict) -> dict:
    """Numeric comparison of one board rule against a preset rule of the same
    kind: {verdict, detail, decided_by, bounds}. All values in mm."""
    if kind == "ViasUnderSMD":
        return _judge_flag(board_rule, preset_rule)
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
        bound = {"name": field, "role": role, "board_mm": round(board[field], 4),
                 "preset_mm": round(preset[field], 4) if field in preset else None,
                 "fab_min_mm": fab_min, "verdict": verdict, "note": note}
        if role == "floor" and not any(b["role"] == "floor" and "jlcdfm" in b for b in bounds):
            level, dfm_text = _dfm_note(preset_rule, board[field])
            if level:
                bound["jlcdfm"] = level
                bound["note"] = f"{note}; {dfm_text}"
        bounds.append(bound)
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


def annular_ring_summary(doc: dict | None, source: str | None = None) -> dict | None:
    """Smallest annular ring actually on the board, (diameter - hole) / 2, over
    vias and plated drilled pads (copper size = smallest top/middle/bottom
    dimension). Unplated mounting holes are ignored. `source` ('via' or 'pad')
    restricts it to one kind, for the scoped IsVia / IsPad preset rules. None
    when the board has no drills (of that kind) or the reader did not expose them."""
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
    if source:
        rings = [r for r in rings if r["source"] == source]
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
    summ = annular_ring_summary(doc, _preset_source(preset_rule))
    if summ is None:
        return {"verdict": "unknown", "decided_by": [], "bounds": [],
                "detail": "no rule on the board; actual annular ring not computed (no via/pad drill data)"}
    preset = preset_values_mm(preset_rule).get("ring")
    fab_min = preset_fab_min(preset_rule, "ring")
    verdict, note = _judge_bound("floor", summ["min_ring_mm"], preset, fab_min)
    level, dfm_text = _dfm_note(preset_rule, summ["min_ring_mm"])
    pv = f"; preset {_fmt(preset)} mm" if preset is not None else ""
    fv = f", JLC fab min {_fmt(fab_min)} mm" if fab_min is not None else ""
    if verdict == "below_fab_min":
        note = "BELOW the fab minimum: the fab may reject or alter it"
    elif fab_min is not None and verdict in ("same", "safer"):
        note = "at or above the fab minimum"
    if level:
        note = f"{note}; {dfm_text}"
    src = _preset_source(preset_rule)
    counts = (f"{summ['via_count']} vias" if src == "via" else f"{summ['pad_count']} plated pads" if src == "pad"
              else f"{summ['via_count']} vias, {summ['pad_count']} plated pads")
    detail = (f"no rule on the board; actual minimum ring {_fmt(summ['min_ring_mm'])} mm "
              f"({_ring_where(summ['worst'])}; {counts})"
              f"{pv}{fv}: {note}")
    return {"verdict": verdict, "detail": detail, "decided_by": ["ring"], "actual": summ,
            "bounds": [{"name": "ring", "role": "floor", "board_mm": summ["min_ring_mm"],
                        "preset_mm": round(preset, 4) if preset is not None else None,
                        "fab_min_mm": fab_min, "verdict": verdict, "note": note}]}


def _preset_source(pr: dict) -> str | None:
    """'via' or 'pad' for a preset ring rule scoped IsVia / IsPad, else None (both)."""
    scope1 = _preset_scopes(pr)[0]
    return "via" if "isvia" in scope1 else "pad" if "ispad" in scope1 else None


def _geometry_note(kind: str, doc: dict | None, source: str | None = None) -> str:
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
        summ = annular_ring_summary(doc, source)
        if summ:
            return f"actual minimum ring {_fmt(summ['min_ring_mm'])} mm ({_ring_where(summ['worst'])})"
    return ""


def _with_geometry(judged: dict, kind: str, doc: dict | None, source: str | None = None) -> dict:
    note = _geometry_note(kind, doc, source)
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
        preset_rules = get_jlc_preset().get("rules", [])

    matched_board_indices = set()   # board rules a preset rule took (each is shown once)
    shared_board_indices = set()    # scope-All board rules that also stand in for a scoped preset rule
    table = []

    # 1. Compare each preset rule against board rules
    for pr in preset_rules:
        p_name = pr.get("name", "")
        p_kind = pr.get("kind", "")
        p_scopes = _preset_scopes(pr)
        p_val = pr.get("value")
        if not p_val and pr.get("attributes"):
            p_val = rule_display_value(pr["attributes"])
        p_val = p_val or "—"

        # The rule that decides on the board: highest priority (lowest PRIORITY number) among the
        # enabled rules with the same scopes; fall back to a same-name rule.
        matched_idx = _effective_index(board_rules, p_kind, matched_board_indices, p_scopes)
        if matched_idx is None:
            for i, br in enumerate(board_rules):
                if i not in matched_board_indices and br.get("NAME") == p_name and br.get("RULEKIND") == p_kind:
                    matched_idx = i
                    break
        shared = False
        if matched_idx is None and p_scopes != _ALL:
            # A scoped preset rule (annular ring of pads / of vias ...) with no same-scope rule on the board:
            # the board's scope-All rule of that kind governs those objects too, and is judged here
            # without being used up, so the scope-All preset rule can still match it.
            matched_idx = _effective_index(board_rules, p_kind)
            shared = matched_idx is not None

        if matched_idx is not None:
            if shared:
                shared_board_indices.add(matched_idx)
            else:
                matched_board_indices.add(matched_idx)
            br = board_rules[matched_idx]
            b_val = rule_display_value(br)
            b_name = p_name if shared else br.get("NAME", p_name)

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
            judged = judge_rule(p_kind, br, pr)
            if shared:
                judged["detail"] = (f"the board's rule {br.get('NAME', p_kind)} (all objects) also applies to these: "
                                    + judged["detail"])
            row.update(_with_geometry(judged, p_kind, board_geom, _preset_source(pr)))
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
        if i in matched_board_indices or i in shared_board_indices:
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
        same_kind = _closest_preset(preset_rules, b_kind, br)
        if same_kind is None:
            row.update({"verdict": "unknown", "detail": "not a JLC preset rule kind",
                        "decided_by": [], "bounds": []})
        else:
            judged = judge_rule(b_kind, br, same_kind)
            judged["detail"] = "scoped/extra rule, compared with the preset " + same_kind.get("name", b_kind) + ": " + judged["detail"]
            row.update(judged)
        table.append(row)

    return table


def _add_board_args(p):
    p.add_argument("--project", help="project name: its board block (layers, copper_oz, mask_colour) picks the JLC preset")
    p.add_argument("--layers", type=int, help="layer count, overrides the project (1-2 use the 2-layer limits)")
    p.add_argument("--oz", type=float, help="outer copper weight in oz, overrides the project (1, 2; 2.5, 3.5, 4.5 on 2 layers)")


def main(argv=None):
    import oscompat
    oscompat.utf8_stdio()
    ap = argparse.ArgumentParser(description="PCB design rules reader, writer, and diff tool")
    sub = ap.add_subparsers(dest="cmd")

    diff_p = sub.add_parser("diff", help="Diff PcbDoc rules against JLC preset")
    diff_p.add_argument("pcbdoc", help="Path to .PcbDoc file")
    diff_p.add_argument("--json", action="store_true",
                        help="Print the rows as JSON (with verdict, detail, bounds) instead of a table")
    _add_board_args(diff_p)

    exp_p = sub.add_parser("export", help="Export JLC preset rules to .RUL file")
    exp_p.add_argument("output", help="Output .RUL file path")
    exp_p.add_argument("--board", help="PcbDoc: write the board's full rule set with JLC values (use Replace existing rules)")
    _add_board_args(exp_p)

    preset_p = sub.add_parser("preset", help="Print JLC preset design rules")
    _add_board_args(preset_p)

    args = ap.parse_args(argv)
    board = board_settings(getattr(args, "project", None), getattr(args, "layers", None), getattr(args, "oz", None))

    if args.cmd == "diff":
        doc = read_pcbdoc(args.pcbdoc)
        preset = get_jlc_preset(board)
        diff = diff_rules(doc.get("rules", []), preset.get("rules"), board_geom=doc)
        if args.json:
            print(json.dumps({"pcbdoc": str(args.pcbdoc), "preset": preset.get("name"), "rules": diff,
                              "annular_ring": annular_ring_summary(doc)}, ensure_ascii=False, indent=2))
            return 0
        print(f"Rules diff for {args.pcbdoc} vs {preset.get('name', 'JLC preset')} ({len(diff)} rules):")
        print(f"{'Rule':<25} {'Kind':<25} {'Board Value':<30} {'Preset Value':<30} {'Status':<16} {'Verdict':<14} Detail")
        print("-" * 160)
        for r in diff:
            print(f"{r['rule']:<25} {r['kind']:<25} {r['board value']:<30} {r['preset value']:<30} "
                  f"{r['status']:<16} {r['verdict']:<14} {r['detail']}")
        return 0

    elif args.cmd == "export":
        records = get_preset_rule_records(board)
        name = get_jlc_preset(board).get("name", "JLC preset")
        if args.board:
            records = board_rul_records(args.board, records)
            out = write_rul(records, args.output)
            print(f"Exported {len(records)} board-aware rules ({name} values) to {out} (import with 'Replace existing rules')")
        else:
            out = write_rul(records, args.output)
            print(f"Exported {len(records)} {name} rules to {out} (import with 'Merge', then raise the *_1 / scoped rules in Priorities)")
        return 0

    elif args.cmd == "preset":
        preset = get_jlc_preset(board)
        print(f"{preset.get('name', 'JLC Preset Rules')} (source: {preset.get('capabilities_url', 'JLC Capabilities')})")
        for r in preset.get("rules", []):
            fab = r.get("fab_min_mm")
            fab_txt = ""
            if isinstance(fab, dict):
                fab_txt = "fab min " + ", ".join(f"{k} {_fmt(v)}" for k, v in fab.items()) + " mm"
            elif isinstance(fab, (int, float)):
                fab_txt = f"fab min {_fmt(fab)} mm"
            scope = ""
            if _preset_scopes(r) != _ALL:
                scope = f" [{r.get('scope1')}" + (f" / {r.get('scope2')}" if _norm_scope(r.get("scope2")) != "all" else "") + "]"
            print(f"  {r.get('name', ''):<28} {r.get('kind', ''):<25} {r.get('value', ''):<30} {fab_txt}{scope}")
        return 0

    else:
        ap.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
