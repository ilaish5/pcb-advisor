"""Track width per net from the current it carries (pure: no Altium, no files).

One source of truth for a net's current: the per-net `current_a` the student (or the agent, with approval) set in the project
(store.net_currents). The only estimate made on its own is a regulator's output net, from a rated output current the BOM line
states (`iout_a` / `rated_current_a` on a line whose role says it is a regulator): a rating written down, never a guess.

  net_widths(nets, rules, currents, estimates, oz, rise)   {net: {"current_a", "width_mm", "source", "note"}}
  regulator_currents(bom_lines, sheets)                    {output net: rated current} from the BOM and the netlist sheets

Width: IPC-2221 external layer (scripts/trace_width.width_mm, the one calculator), 10 C rise and 1 oz unless the project says
otherwise, never below the board's width_min, never above the width rule's maximum. source is "set" (the current was set),
"regulator" (the rated current of the regulator that feeds the net), "rail default" (a supply rail with no current known: the
old 0.3 mm) or "rule" (a PcbDoc width rule on the net, or a net with no current and no rail name: the board's width).
A current outside the IPC-2221 range gets width_mm None and the note says so: no width is invented for it.
"""
import math
import re

import trace_width

RAIL_DEFAULT = 0.3                      # a rail with no current known is routed at least this wide (as before)
MAX_AMPS = 35.0                         # the chart range of the formula (trace_width.LIMITS)
MAX_MIL = 400.0
RISE_RANGE = (10.0, 100.0)
_REGULATOR = re.compile(r"regulat|ldo|buck|boost|dc.?dc|converter|power supply", re.I)
_OUT_PIN = re.compile(r"^(?:v?out\d*|vo|output|\+?vout\d*)$", re.I)
_RATING_KEYS = ("iout_a", "rated_current_a")


def _number(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def regulator_currents(bom_lines, sheets):
    """{output net: rated output current (A)} for BOM lines that are regulators and state a rating. `sheets` are netlist sheet dicts
    (parts with ref and pins [{name, num, net}]). A regulator with no rating or no output pin named OUT / VOUT gives nothing."""
    out = {}
    for line in bom_lines or []:
        amps = next((_number(line.get(k)) for k in _RATING_KEYS if _number(line.get(k))), None)
        if not amps or amps <= 0 or not _REGULATOR.search(str(line.get("role") or "")):
            continue
        refs = set(line.get("refs") or [line.get("key")])
        for sh in sheets or []:
            for part in sh.get("parts", []):
                if part.get("ref") not in refs:
                    continue
                for pin in part.get("pins", []):
                    net = (pin.get("net") or "").strip()
                    if net and _OUT_PIN.match(str(pin.get("name") or "").strip()):
                        out[net] = max(out.get(net, 0), amps)
    return out


def _fmt(w):
    return f"{w:.3f}".rstrip("0").rstrip(".") + " mm"


def net_widths(nets, rules, currents=None, estimates=None, oz=1.0, rise=10.0, is_rail=lambda n: False):
    """The width for each net of `nets`. rules: the router's rules (width, width_min, width_max, net_width). currents: {net: A} set by
    the student; estimates: {net: A} from regulator ratings (a set current wins). Returns {net: {"current_a", "width_mm", "source",
    "note"}}; width_mm is None only for a current outside the IPC-2221 range (the router then uses the rail default or the board
    width and the note says so)."""
    currents, estimates = currents or {}, estimates or {}
    wmin = rules.get("width_min") or rules["width"]
    wmax = rules.get("width_max") or 10.0
    res = {}
    for n in nets:
        rule_w = (rules.get("net_width") or {}).get(n)
        amps, source = None, None
        if _number(currents.get(n)) is not None:
            amps, source = _number(currents[n]), "set"
        elif _number(estimates.get(n)) is not None:
            amps, source = _number(estimates[n]), "regulator"
        entry = {"current_a": amps, "width_mm": None, "source": "rule", "note": ""}
        res[n] = entry
        if amps is None:
            if rule_w is not None:
                entry.update(width_mm=rule_w, note=f"PcbDoc width rule {_fmt(rule_w)}")
            elif is_rail(n):
                w = min(max(rules["width"], RAIL_DEFAULT), wmax)
                entry.update(width_mm=w, source="rail default",
                             note=f"current unknown: default {_fmt(w)}; set the net's current for a width from IPC-2221")
            else:
                entry.update(width_mm=rules["width"], note="no current set: the board's track width")
            continue
        entry["source"] = source
        if not (0 < amps <= MAX_AMPS) or not (RISE_RANGE[0] <= rise <= RISE_RANGE[1]) or oz <= 0:
            entry["note"] = (f"{amps:g} A (rise {rise:g} C, {oz:g} oz) is outside IPC-2221 range (up to {MAX_AMPS:g} A, "
                             f"{RISE_RANGE[0]:g}-{RISE_RANGE[1]:g} C rise): no width calculated, size it by hand")
            continue
        need = trace_width.width_mm(amps, "external", rise, oz)
        if need / 0.0254 > MAX_MIL:
            entry["note"] = f"{amps:g} A needs {_fmt(need)}: outside IPC-2221 range (over {MAX_MIL:g} mil), no width calculated"
            continue
        w = max(need, wmin)
        txt = f"{amps:g} A ({source}): IPC-2221 external, {rise:g} C rise, {oz:g} oz needs {_fmt(need)}"
        if need < wmin:
            txt += f", board minimum {_fmt(wmin)} used"
        if w > wmax + 1e-9:
            txt += f"; the width rule allows at most {_fmt(wmax)}, used that: too narrow for {amps:g} A, widen the rule or use a pour"
            w = wmax
        if rule_w is not None and rule_w >= w - 1e-9:
            entry.update(width_mm=rule_w, source="rule", note=txt + f"; PcbDoc width rule {_fmt(rule_w)} is wider and wins")
        elif rule_w is not None:
            entry.update(width_mm=rule_w, source="rule",
                         note=txt + f"; PcbDoc width rule {_fmt(rule_w)} is narrower than needed, the rule is kept: check it")
        else:
            entry["width_mm"], entry["note"] = w, txt
    return res


_PROBLEM = ("outside IPC-2221", "no room", "allows at most", "narrower", "wins")


def width_line(widths):
    """One short line (step note and agent) with the width of each power net: a net with a current, a rail, or a PcbDoc rule on it.
    Plain signal nets are left out. '' when there is nothing to say. A problem (out of range, no room, a rule that wins or is
    narrower) is added in brackets."""
    bits = []
    for n, w in sorted((widths or {}).items()):
        if w["source"] == "rule" and w["current_a"] is None and not str(w["note"]).startswith("PcbDoc"):
            continue
        got = f"{w['width_mm']:g} mm" if w["width_mm"] is not None else "not routed"
        why = f"{w['current_a']:g} A, {w['source']}" if w["current_a"] is not None else w["source"]
        flag = ""
        if any(k in w["note"] for k in _PROBLEM):
            flag = " [" + w["note"].split("; ")[-1].strip() + "]"
        bits.append(f"{n} {got} ({why}){flag}")
    return "track widths: " + ", ".join(bits) if bits else ""


def width_problems(widths, names=None):
    """Problems (strings) in a route's per-net widths: a net with a current that was drawn narrower than its current needs (the board
    had no room for the wanted width, e.g. at a fine pitch pad). Names the net, the wanted and drawn widths and the current."""
    names = names or {}
    out = []
    for n, w in sorted((widths or {}).items()):
        if w.get("current_a") is None or w.get("width_mm") is None or w.get("wanted_mm") is None:
            continue
        if w["width_mm"] < w["wanted_mm"] - 1e-9:
            out.append(f"{names.get(n, n)} carries {w['current_a']:g} A and needs {_fmt(w['wanted_mm'])}, but only {_fmt(w['width_mm'])} fitted "
                       f"(a fine pitch pad or a tight spot): lower its current, give it room, or widen it by hand in Altium")
    return out


def width_warnings(widths, names=None):
    """Notes that are not problems but must be read: a current outside the IPC-2221 range (no width calculated) or one clamped to the
    width rule's maximum."""
    names = names or {}
    return [f"{names.get(n, n)}: {w['note']}" for n, w in sorted((widths or {}).items())
            if w.get("current_a") is not None and ("outside IPC-2221" in w["note"] or "allows at most" in w["note"])]
