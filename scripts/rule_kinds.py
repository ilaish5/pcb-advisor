"""The kinds of "Extra rules" a student can add: their value fields, validation, and the Altium .RUL record each one writes.

Every key below was read from a real Altium rule record (tests/fixtures/altium/rules-board.PcbDoc, an AD26 export of the
real student board, or the annular ring key confirmed by the AD26 import test in PLAN.md). Kinds without such a
record are not offered. Lengths are typed as '6mil', '0.15mm', '0.006in' or a bare number (mil, as Altium reads it) and
are stored as mil text, which is what Altium writes itself.
"""
import re

import rules as rules_mod
from jlc_preset import MIL, mil_text

NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_ .()\-]{0,59}$")
SCOPE_MAX = 200


def _f(key, label, attrs, lo_mm, hi_mm, placeholder, default=None, optional=False):
    return {"key": key, "label": label, "type": "length", "attrs": attrs, "lo_mm": lo_mm, "hi_mm": hi_mm,
            "placeholder": placeholder, "default": default, "optional": optional, "unit": "mil or mm"}


# kind -> label, hint, fields, static (fixed keys every record of the kind carries), netscope
KINDS = {
    "Width": {
        "label": "Width", "hint": "Track width of the nets in the scope: smallest, preferred and largest allowed.",
        "fields": [_f("min", "Min", ("MINLIMIT",), 0.02, 25, "10mil"),
                   _f("pref", "Preferred", ("PREFEREDWIDTH",), 0.02, 25, "20mil"),
                   _f("max", "Max", ("MAXLIMIT",), 0.02, 25, "50mil")],
        "order": [("min", "pref"), ("pref", "max")],
    },
    "Clearance": {
        "label": "Clearance", "hint": "Smallest copper-to-copper gap between different nets in the scope.",
        "fields": [_f("gap", "Gap", ("GAP", "GENERICCLEARANCE"), 0.02, 25, "10mil")],
        "netscope": "DifferentNets",
    },
    "RoutingVias": {
        "label": "Routing via size", "hint": "Hole and pad diameter the router uses for vias in the scope.",
        "fields": [_f("hole", "Hole", ("HOLEWIDTH", "MINHOLEWIDTH", "MAXHOLEWIDTH"), 0.1, 6.3, "12mil"),
                   _f("dia", "Diameter", ("WIDTH", "MINWIDTH", "MAXWIDTH"), 0.2, 12, "24mil")],
        "static": {"VIASTYLE": "Through Hole"},
        "order": [("hole", "dia")],
    },
    "ComponentClearance": {
        "label": "Component clearance", "hint": "Smallest gap between component bodies (assembly spacing).",
        "fields": [_f("gap", "Gap", ("GAP", "VERTICALGAP"), 0.0, 50, "10mil")],
        "static": {"COLLISIONCHECKMODE": "3", "SHOWDISTANCES": "FALSE"},
    },
    "HoleSize": {
        "label": "Hole size", "hint": "Smallest and largest drill diameter allowed for the holes in the scope.",
        "fields": [_f("min", "Min", ("MINLIMIT",), 0.1, 10, "12mil"),
                   _f("max", "Max", ("MAXLIMIT",), 0.1, 10, "250mil")],
        "static": {"ABSOLUTEVALUES": "TRUE", "MAXPERCENT": "80.000", "MINPERCENT": "20.000"},
        "order": [("min", "max")],
    },
    "MinimumAnnularRing": {
        "label": "Annular ring", "hint": "Smallest copper ring left around a drilled hole: (pad - hole) / 2.",
        "fields": [_f("ring", "Ring", ("MINIMUMRING",), 0.0, 5, "6mil")],
    },
    "HoleToHoleClearance": {
        "label": "Hole to hole", "hint": "Smallest wall-to-wall gap between two drilled holes.",
        "fields": [_f("gap", "Gap", ("GAP",), 0.0, 25, "10mil")],
        "static": {"ALLOWSTACKEDMICROVIAS": "TRUE"},
    },
    "SolderMaskExpansion": {
        "label": "Solder mask expansion", "hint": "How far the mask opening is larger than the pad (the mask clearance).",
        "fields": [_f("expansion", "Expansion", ("EXPANSION",), 0.0, 2, "4mil")],
        "static": {"ISTENTINGTOP": "FALSE"},
    },
    "PasteMaskExpansion": {
        "label": "Paste mask expansion", "hint": "Paste opening size against the pad; negative shrinks it (less paste).",
        "fields": [_f("expansion", "Expansion", ("EXPANSION",), -1, 1, "-2mil")],
    },
    "SilkToSolderMaskClearance": {
        "label": "Silk to mask opening", "hint": "Smallest gap between silkscreen and an exposed pad or mask opening.",
        "fields": [_f("gap", "Gap", ("MINSILKSCREENTOMASKGAP",), 0.0, 5, "6mil")],
        "static": {"CLEARANCETOEXPOSEDCOPPER": "TRUE"},
    },
    "SilkToSilkClearance": {
        "label": "Silk to silk", "hint": "Smallest gap between two silkscreen objects.",
        "fields": [_f("gap", "Gap", ("SILKTOSILKCLEARANCE",), 0.0, 5, "6mil")],
    },
    "PlaneClearance": {
        "label": "Plane clearance", "hint": "Gap from a plane layer's copper to holes that must not touch the plane.",
        "fields": [_f("gap", "Gap", ("CLEARANCE",), 0.0, 25, "20mil")],
    },
    "PolygonConnect": {
        "label": "Polygon connect", "hint": "How pours connect to pads: thermal relief spokes, or solid (direct).",
        "fields": [{"key": "style", "label": "Style", "type": "choice", "choices": ["Relief", "Direct"], "default": "Relief",
                    "attrs": ("CONNECTSTYLE",), "optional": False, "placeholder": "", "unit": ""},
                   _f("width", "Spoke width", ("RELIEFCONDUCTORWIDTH",), 0.05, 5, "10mil", default="10mil", optional=True),
                   _f("gap", "Air gap", ("AIRGAPWIDTH",), 0.05, 5, "10mil", default="10mil", optional=True)],
        "static": {"RELIEFENTRIES": "4", "POLYGONRELIEFANGLE": "90 Angle"},
    },
    "DiffPairsRouting": {
        "label": "Differential pair", "hint": "Track width and the gap between the two tracks of a pair.",
        "fields": [_f("width", "Width", (), 0.02, 25, "10mil"),
                   _f("gap", "Gap", ("MINLIMIT", "MAXLIMIT", "MOSTFREQGAP"), 0.02, 25, "8mil")],
        "static": {"MAXUNCOUPLEDLENGTH": "500mil"},
    },
}


def _diffpair_width_attrs(width):
    """DiffPairsRouting carries a min/max/preferred width for every layer (top, 30 mid layers, bottom)."""
    out = {}
    layers = ["TOPLAYER"] + [f"MIDLAYER{i}" for i in range(1, 31)] + ["BOTTOMLAYER"]
    for lay in layers:
        for suffix in ("MINWIDTH", "MAXWIDTH", "PREFWIDTH"):
            out[f"{lay}_{suffix}"] = width
    return out


def kinds_info():
    """What the form needs for each kind: label, hint, and the fields."""
    return [{"kind": k, "label": s["label"], "hint": s["hint"],
             "fields": [{x: f[x] for x in ("key", "label", "type", "placeholder", "unit", "optional", "default", "choices") if x in f}
                        for f in s["fields"]]} for k, s in KINDS.items()]


def parse_length(text, field):
    """Text -> mil text, or ValueError naming the field."""
    mm = rules_mod.to_mm(text)
    if mm is None:
        raise ValueError(f"{field['label']}: '{text}' is not a length (use 6mil, 0.15mm or a number in mil)")
    if mm < field["lo_mm"] - 1e-9 or mm > field["hi_mm"] + 1e-9:
        raise ValueError(f"{field['label']}: {mil_text(mm / MIL)} is outside {mil_text(field['lo_mm'] / MIL)} to "
                         f"{mil_text(field['hi_mm'] / MIL)}")
    return mil_text(round(mm / MIL, 4)), mm


def _check_text(what, text, maxlen):
    if not isinstance(text, str):
        raise ValueError(f"{what} must be text")
    if len(text) > maxlen or any(ord(c) < 32 or c in "|" for c in text):
        raise ValueError(f"{what} has a character Altium rule files cannot hold (|, control characters) or is too long")
    try:
        text.encode("latin-1")
    except UnicodeEncodeError:
        raise ValueError(f"{what} may only use Latin-1 characters (the .RUL format)")


def _check_scope(text):
    _check_text("Scope", text, SCOPE_MAX)
    if text.count("(") != text.count(")") or text.count("'") % 2:
        raise ValueError("Scope: unbalanced brackets or quotes, e.g. InNetClass('HV')")


def validate_rule(rule: dict) -> dict:
    """The rule as the form or the API gives it -> the clean stored rule. Raises ValueError with a sentence for the student.
    Input: name, kind, scope1 (default All), scope2 (default All), values {field: text} or, for the old one-field form,
    `value` (Width: min = preferred = max)."""
    if not isinstance(rule, dict):
        raise ValueError("rule must be an object")
    name, kind = rule.get("name"), rule.get("kind")
    if not isinstance(name, str) or not NAME_RE.match(name.strip()):
        raise ValueError("Name: 1 to 60 letters, digits, space, _ . - ( ), starting with a letter or digit")
    name = name.strip()
    spec = KINDS.get(kind)
    if not spec:
        raise ValueError(f"Kind '{kind}' is not supported; choose one of: {', '.join(KINDS)}")
    scope1 = (rule.get("scope1") or "All")
    scope2 = (rule.get("scope2") or "All")
    scope1 = scope1.strip() if isinstance(scope1, str) else scope1
    scope2 = scope2.strip() if isinstance(scope2, str) else scope2
    scope1, scope2 = scope1 or "All", scope2 or "All"
    _check_scope(scope1)
    _check_scope(scope2)
    values = rule.get("values")
    if not isinstance(values, dict):
        values = {}
        legacy = rule.get("value")
        if legacy not in (None, ""):
            numeric = [f for f in spec["fields"] if f["type"] == "length" and not f["optional"]]
            if kind == "Width":
                values = {"min": legacy, "pref": legacy, "max": legacy}
            elif len(numeric) == 1:
                values = {numeric[0]["key"]: legacy}
            else:
                raise ValueError(f"{spec['label']} needs {len(numeric)} values: {', '.join(f['label'] for f in numeric)}")
    clean, mm = {}, {}
    for f in spec["fields"]:
        raw = values.get(f["key"])
        raw = raw.strip() if isinstance(raw, str) else raw
        if raw in (None, ""):
            if f["default"] is not None:
                raw = f["default"]
            elif f["optional"]:
                continue
            else:
                raise ValueError(f"{f['label']}: a value is required")
        if f["type"] == "choice":
            if raw not in f["choices"]:
                raise ValueError(f"{f['label']}: choose {' or '.join(f['choices'])}")
            clean[f["key"]] = raw
        else:
            clean[f["key"]], mm[f["key"]] = parse_length(str(raw), f)
    for lo, hi in spec.get("order", []):
        if mm[lo] > mm[hi] + 1e-9:
            names = {f["key"]: f["label"] for f in spec["fields"]}
            raise ValueError(f"{names[lo]} must not be larger than {names[hi]}")
    if kind == "RoutingVias" and mm["dia"] <= mm["hole"]:
        raise ValueError("Diameter must be larger than the hole")
    out = {"name": name, "kind": kind, "scope1": scope1, "scope2": scope2, "values": clean}
    attrs = build_attributes(out)
    out["value"] = rules_mod.rule_display_value(attrs)
    out["description"] = (rule.get("description") or "Custom rule")
    _check_text("Description", out["description"], 300)
    if rule.get("source"):
        _check_text("Source", rule["source"], 200)
        out["source"] = rule["source"]
    out["attributes"] = attrs
    return out


def build_attributes(rule: dict) -> dict:
    """The complete .RUL record of a validated rule {name, kind, scope1, scope2, values}."""
    spec = KINDS[rule["kind"]]
    name, kind = rule["name"], rule["kind"]
    rec = {
        "SELECTION": "FALSE", "LAYER": "TOP", "LOCKED": "FALSE", "POLYGONOUTLINE": "FALSE", "USERROUTED": "TRUE",
        "KEEPOUT": "FALSE", "UNIONINDEX": "0", "RULEKIND": kind, "NETSCOPE": spec.get("netscope", "AnyNet"),
        "LAYERKIND": "SameLayer", "SCOPE1EXPRESSION": rule.get("scope1") or "All",
        "SCOPE2EXPRESSION": rule.get("scope2") or "All", "NAME": name, "ENABLED": "TRUE", "PRIORITY": "1",
        "COMMENT": "extra rule", "UNIQUEID": rules_mod._uid(name), "DEFINEDBYLOGICALDOCUMENT": "FALSE",
    }
    vals = rule["values"]
    for f in spec["fields"]:
        if f["key"] in vals:
            for a in f["attrs"]:
                rec[a] = vals[f["key"]]
    if kind == "DiffPairsRouting":
        rec.update(_diffpair_width_attrs(vals["width"]))
    if kind == "PolygonConnect" and vals.get("style") == "Direct":
        rec.setdefault("RELIEFCONDUCTORWIDTH", "10mil")
        rec.setdefault("AIRGAPWIDTH", "10mil")
    rec.update(spec.get("static", {}))
    return rec


def record_for(rule: dict) -> dict | None:
    """The .RUL record of a stored extra rule. Rules saved before the kinds were checked had only a GAP key; they are
    rebuilt from their kind and value when that is possible, else their stored attributes are used as they are."""
    try:
        return validate_rule(rule)["attributes"]
    except (ValueError, KeyError, TypeError):
        return rule.get("attributes") if isinstance(rule.get("attributes"), dict) else None


def append_extra_records(records: list, extras: list) -> list:
    """Add the extra rules to a .RUL record list with workable priorities: a rule with its own scope goes above the
    existing rules of its kind (priority 1, the others move down), a scope-All rule goes after them."""
    for ex in extras or []:
        if ex.get("enabled") is False:
            continue
        rec = record_for(ex)
        if not rec:
            continue
        rec = dict(rec)
        same = [r for r in records if r.get("RULEKIND") == rec.get("RULEKIND")]
        if rules_mod._norm_scope(rec.get("SCOPE1EXPRESSION")) != "all" or rules_mod._norm_scope(rec.get("SCOPE2EXPRESSION")) != "all":
            for r in same:
                r["PRIORITY"] = str(rules_mod._prio(r) + 1)
            rec["PRIORITY"] = "1"
        else:
            rec["PRIORITY"] = str(max((rules_mod._prio(r) for r in same if "PRIORITY" in r), default=0) + 1)
        records.append(rec)
    return records
