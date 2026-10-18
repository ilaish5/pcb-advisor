"""Rule presets from standards designers add on top of the fab's limits: IPC-2221B voltage clearance and IPC-6012 class 2 / 3
annular ring. The numbers are in shared/reference/standards/ipc.json (our summary of public sources, cited by the two .md
files next to it). A preset never weakens the JLC preset: where the standard is smaller, the JLC value is kept and the row says so."""
import json
import re

import jlc_preset
import rule_kinds
import workspace
from jlc_preset import MIL, mil_text

DATA = workspace.REPO / "shared" / "reference" / "standards" / "ipc.json"

STANDARDS = {
    "ipc2221b": {"label": "IPC-2221B voltage clearance",
                 "hint": "Smallest spacing between conductors for the voltage between them (Table 6-1)."},
    "ipc_class": {"label": "IPC Class 2 / Class 3",
                  "hint": "Smallest annular ring a fab must leave, by performance class (IPC-6012, IPC-A-600)."},
}


def data() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def info() -> dict:
    """What the form needs: the presets, locations, classes and the source each cites."""
    d = data()
    return {
        "checked": d["checked"],
        "standards": [
            {"id": "ipc2221b", **STANDARDS["ipc2221b"], "source": d["clearance"]["source"],
             "max_volts": d["clearance"]["max_volts"],
             "locations": [{"id": k, "label": v["label"]} for k, v in d["clearance"]["locations"].items()]},
            {"id": "ipc_class", **STANDARDS["ipc_class"], "source": d["annular_ring"]["source"],
             "classes": [{"id": k, "label": v["label"]} for k, v in d["annular_ring"]["classes"].items()]},
        ],
    }


def clearance_mm(volts: float, location: str) -> float:
    """IPC-2221B spacing in mm for a peak voltage between conductors at B1 / B2 / B4."""
    d = data()["clearance"]
    col = d["locations"].get(location)
    if col is None:
        raise ValueError(f"location must be one of {', '.join(d['locations'])}")
    if not (volts > 0) or volts > d["max_volts"]:
        raise ValueError(f"voltage must be above 0 and up to {d['max_volts']} V")
    for upper, mm in col["bands"]:
        if volts <= upper:
            return mm
    last = col["bands"][-1][1]
    return round(last + col["per_volt_above_500"] * (volts - 500), 4)


def _jlc(board, kind, scope="all"):
    """The JLC preset rule (name, value_mm) of a kind and scope: the floor the standard may not go under."""
    for r in jlc_preset.build_preset(board).get("rules", []):
        if r["kind"] == kind and "".join(str(r.get("scope1") or "all").lower().split()) == scope:
            return r
    return None


def _slug(text):
    return re.sub(r"[^A-Za-z0-9]+", "", text)[:16]


def _row(name, kind, scope1, std_mm, jlc_rule, jlc_key, source, basis):
    jlc_mm = jlc_rule.get(jlc_key) if jlc_rule else None
    kept = "standard"
    final = std_mm
    note = ""
    if jlc_mm is not None and jlc_mm >= std_mm - 1e-9:
        final, kept = jlc_mm, "jlc" if jlc_mm > std_mm + 1e-9 else "equal"
        note = (f"The JLC preset ({mil_text(jlc_mm / MIL)}) is {'stricter than' if kept == 'jlc' else 'equal to'} the standard "
                f"({mil_text(std_mm / MIL)}); the stricter value is kept.")
    elif jlc_mm is not None:
        note = f"The standard ({mil_text(std_mm / MIL)}) is stricter than the JLC preset ({mil_text(jlc_mm / MIL)})."
    field = "gap" if kind == "Clearance" else "ring"
    rule = rule_kinds.validate_rule({
        "name": name, "kind": kind, "scope1": scope1, "values": {field: mil_text(round(final / MIL, 4))},
        "description": basis, "source": source})
    rule.update({"standard_mm": round(std_mm, 4), "jlc_mm": round(jlc_mm, 4) if jlc_mm is not None else None,
                 "kept": kept, "note": note, "value_mm": round(final, 4)})
    return rule


def preview(standard: str, params: dict, board=None) -> dict:
    """The rules a preset would add: {standard, label, source, rules: [...], notes}. Raises ValueError on bad input."""
    d = data()
    params = params or {}
    scope = (params.get("scope") or "All").strip() or "All"
    rule_kinds._check_scope(scope)
    if standard == "ipc2221b":
        try:
            volts = float(params.get("volts"))
        except (TypeError, ValueError):
            raise ValueError("Enter the peak voltage between the conductors, in volts")
        loc = params.get("location") or "B2"
        std = clearance_mm(volts, loc)
        src = d["clearance"]["source"]
        vtxt = f"{volts:g}"
        name = f"IPC2221B_{loc}_{vtxt}V" + ("" if scope.lower() == "all" else "_" + _slug(scope))
        basis = f"IPC-2221B Table 6-1, {d['clearance']['locations'][loc]['label']}, {vtxt} V peak: {std:g} mm [{src}]"
        rows = [_row(name, "Clearance", scope, std, _jlc(board, "Clearance"), "value_mm", src, basis)]
        notes = ["Electrical spacing only: creepage and safety standards (IEC 60664, 62368) can ask for more."]
        if loc == "B4":
            notes.append("B4 needs a permanent polymer coating over the conductors; solder mask does not count.")
        if scope.lower() == "all":
            notes.append("Scope All applies this spacing to the whole board; use InNetClass('HV') to limit it.")
    elif standard == "ipc_class":
        cls = str(params.get("class") or "2")
        c = d["annular_ring"]["classes"].get(cls)
        if c is None:
            raise ValueError(f"class must be one of {', '.join(d['annular_ring']['classes'])}")
        src = d["annular_ring"]["source"]
        std = max(c["external_mm"], c["internal_mm"])    # Altium's ring rule has one value for every layer
        rows = []
        for label, kind_scope in (("Pad", "IsPad"), ("Via", "IsVia")):
            jr = _jlc(board, "MinimumAnnularRing", kind_scope.lower())
            basis = (f"IPC-6012 class {cls} annular ring, external {c['external_mm']:g} mm, internal {c['internal_mm']:g} mm "
                     f"(the larger is used: one value for all layers) [{src}]")
            rows.append(_row(f"IPC_Class{cls}_AnnularRing_{label}", "MinimumAnnularRing", kind_scope, std, jr, "value_mm", src, basis))
        notes = ["Class 3 allows no breakout (hole touching the pad edge); class 2 allows 90 degrees with a teardrop."
                 if cls == "3" else
                 "Class 2 allows up to 90 degrees of breakout with a teardrop or fillet; the sources disagree here, so 0.05 mm is kept."]
        notes.append("JLC's own minimum ring is larger than the IPC figure, so the JLC value usually decides.")
    else:
        raise ValueError(f"unknown standard '{standard}'")
    return {"standard": standard, "label": STANDARDS[standard]["label"], "source": src, "rules": rows, "notes": notes}
