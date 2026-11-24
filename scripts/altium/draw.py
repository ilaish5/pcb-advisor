"""Draw a schematic sheet from the tool's netlist (pure Python: no Altium here, so it can be tested).

The agent's `altium.draw_schematic` action turns a netlist sheet (netlist/<id>.json) plus the project's SchLib into script
lines for the Altium bridge (AdvisorBridge.pas: DRAWBEGIN, PLACE, WIRE, NETLABEL, POWER, NOERC, FRAME). Every pin that is
connected gets a short wire stub that ends in a power port (ground and supply rails) or a net label (everything else); a pin
the netlist marks NC gets a No ERC cross; an open pin (net "") gets nothing and is reported. The same pattern is meant for
the later PCB placement and routing actions: plan here in Python, keep the Pascal side to dumb object creation, verify from
the saved file.

  plan_sheet(...)      layout + commands for one sheet
  verify_sheet(...)    compares the saved SchDoc (read_schdoc dict) with the plan: parts, pin counts, footprints, nets
"""
import math
import pathlib
import re
import sys
import unicodedata

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pinnames  # noqa: E402
from partlib_convert import NAME_CHAR, NAME_HEIGHT, NUMBER_RAISE  # noqa: E402

TAG = "[advisor]"                      # the same first word the skeleton frames carry
GRID = 100                             # mils: everything is placed on the 100 mil grid
DIRECTION = {0: (1, 0), 1: (0, 1), 2: (-1, 0), 3: (0, -1)}      # pin rotation: right, up, left, down
SHEETS = {"A4": {"style": 0, "size": (11500, 7600)},      # Altium SheetStyle and size in mils of the sheets drawn here
          "A3": {"style": 1, "size": (15500, 11100)}}      # (AdvisorBridge.pas DRAWBEGIN's style field sets the same value)
SHEET_ORDER = ("A4", "A3")             # a sheet is drawn on the first of these that holds its layout
SHEET_STYLE = SHEETS["A4"]["style"]    # the default sheet
SHEET_SIZE = SHEETS["A4"]["size"]      # its inner border is SHEET_BORDER inside the edge
SHEET_BORDER = 200


def sheet_area(name="A4"):
    """Usable drawing area in mils (x0, y0, x1, y1) of the sheet size `name`: frames reach FRAME_PAD past x1, still inside the inner
    border; the title block sits below y0."""
    w, h = SHEETS[name]["size"]
    return (800, 1000, w - 700, h - 800)


AREA = sheet_area("A4")
HEADER = 300                           # height of a section heading
GAP = 200                              # between two parts, on top of their own margin
MARGIN = 200                           # room kept around a part for its power symbols and labels
CHAR = 70                              # width of one label character in mils (the default 10 pt font)
POWER_STUB = 200
NUM_CHAR = NAME_CHAR                   # width of one pin number character (the same metric partlib_convert uses for symbol text)
TEXT_H = 100                           # height of one text line (the designator, the comment, a label)
TEXT_PITCH = 150                       # line to line of the designator and the comment
TEXT_GAP = 50                          # between the body (or other ink) and the part's texts
TEXT_CHAR = 65                         # width of one character of the designator and the comment (partlib uses 60; a little over)
TEXT_SPACE = 100                       # between the designator and the comment on one row
ONE_ROW = 800                          # designator and comment share a row up to this width (or the body's width)
GROUND_STYLE, RAIL_STYLE = 5, 2        # Altium: power port styles "Signal ground" and "Bar"

_GROUND = re.compile(r"^(?:[ADPSEC]?GND\w*|VSS\w*|GROUND)$", re.I)
_RAILS = {"VCC", "VDD", "VBUS", "VBAT", "VIN", "VSYS", "VEE", "VDDA", "VCCA", "AVDD", "DVDD", "VREF", "VCCIO"}
_RAIL_RE = re.compile(r"^[+-]\d|^\d+V\d*$", re.I)         # +5V, +3V3, -12V, 3V3


def net_kind(net):
    """'gnd' | 'rail' | 'label': how a net is drawn at the end of a stub."""
    n = str(net or "").strip()
    if _GROUND.match(n):
        return "gnd"
    if n.upper() in _RAILS or _RAIL_RE.match(n):
        return "rail"
    return "label"


def is_nc(net):
    return pinnames.is_nc_net(net)


def tip(pin):
    """The connection point (hot spot) of a library pin, relative to the symbol's origin."""
    dx, dy = DIRECTION[int(pin.get("orientation", 0)) & 3]
    n = pin.get("length", 0)
    return pin["x"] + dx * n, pin["y"] + dy * n


def is_hidden(pin):
    return bool(int(pin.get("conglomerate", 0)) & 4)


def same_name(a, b):
    return str(a or "").strip().upper() == str(b or "").strip().upper()


def pin_nets(part, symbol):
    """([(lib pin, net)], warnings, errors): which net each pin of the library symbol takes from the netlist part.
    Pins are matched by number. Both sides name the pin and the names differ: an error (a wrong pin map must not be drawn).
    A netlist pin the symbol does not have: an error. A library pin the netlist does not list: a warning, left unconnected.
    A hidden library pin (an implicit power connection by its name) is never drawn; a warning when the netlist's net differs
    from its name. net "" = open pin."""
    ref = part["ref"]
    by_num = {}
    errors = []
    unnumbered = []
    for p in part.get("pins", []):
        n = str(p.get("num", p.get("number", "")) or "").strip()
        if n:
            by_num[n] = p
        else:
            unnumbered.append(p)
    lib_nums = {str(lp["number"]) for lp in symbol["pins"]}
    out, warn = [], []
    # pins the symbol's drawing joins: one terminal (a tactile switch); only on a symbol of 4 or more pins (a diode drawn as a line
    # between its two pins is no joined pair). joined None = the drawing could not be read: only then the count fallback is allowed
    joined = {n: g for g in (symbol.get("joined") or []) if len(symbol["pins"]) >= 4 for n in g}
    twice = (symbol.get("joined") is None and 0 < len(by_num) and len(symbol["pins"]) == 2 * len(by_num) <= 8
             and all(str(q.get("electrical")) == "Passive" for q in symbol["pins"]))
    listed = [str(q.get("name") or "").strip().upper() for q in by_num.values()]
    named = any(nm and nm != n for nm, n in zip(listed, by_num))
    for p in unnumbered:        # a pin with no number cannot be wired: say that, not "pin  has no pin in the symbol"
        nm = str(p.get("name") or "").strip()
        errors.append(f"{ref}: netlist pin {nm or '(no name)'} has no pin number" + (
            f", and the name {nm} could not be matched by name to one pin of library symbol {symbol['name']}"
            if nm else "") + ". Give the pin number")
    for num in by_num:
        if num not in lib_nums:
            errors.append(f"{ref}: netlist pin {num} ({by_num[num].get('name') or ''}) has no pin in library symbol {symbol['name']}")
    for lp in symbol["pins"]:
        num = str(lp["number"])
        np_ = by_num.get(num)
        if np_ is None:
            mates = [m for m in joined.get(num, ()) if m != num and m in by_num]
            nets = {str(by_num[m].get("net") or "").strip() for m in mates}
            if len(nets) == 1 and next(iter(nets)) and not is_nc(next(iter(nets))):
                # the symbol itself joins this pad to a listed one (internally paired pads): same net, like the real part
                out.append((lp, next(iter(nets))))
                warn.append(f"{ref}: library pin {num} ({lp.get('name')}) is joined to pin {mates[0]} inside the symbol (one terminal); "
                            f"drawn on the same net {next(iter(nets))}")
            elif num in joined or (twice and _may_duplicate(lp, listed, named)):
                why = (f"the symbol joins it with pin {', '.join(m for m in joined[num] if m != num)}" if num in joined
                       else "the symbol has twice the pins of the netlist, so it is probably a duplicate pad of the same terminal")
                out.append((lp, "NC"))
                warn.append(f"{ref}: library pin {num} ({lp.get('name')}) is not in the netlist; {why}: marked No ERC, "
                            "check the datasheet pad table")
            else:
                warn.append(f"{ref}: library pin {num} ({lp.get('name')}) is not in the netlist; left unconnected")
            continue
        nname = str(np_.get("name") or "").strip()
        two = len(symbol["pins"]) == 2 and len(by_num) == 2
        lib_names = [o.get("name") for o in symbol["pins"]]
        net_names = [q.get("name") for q in by_num.values()]
        mine = pinnames.forms_among(nname, net_names, two)
        if nname and str(lp.get("name") or "").strip() and not same_name(nname, lp.get("name")) \
                and not mine & pinnames.forms_among(lp.get("name"), lib_names, two):
            # not the same name nor another spelling of it (RESET/RST, A/+ on a two-pin diode: no warning)
            other = [o for o in symbol["pins"] if str(o["number"]) != num and same_name(o.get("name"), nname)] or \
                    [o for o in symbol["pins"] if str(o["number"]) != num
                     and mine & pinnames.forms_among(o.get("name"), lib_names, two)]
            if other:       # the netlist's name belongs to another pin of the symbol: a real swap
                errors.append(f"{ref}: pin {num} is {nname} in the netlist, but {nname} is pin {other[0]['number']} of library symbol "
                              f"{symbol['name']} (pin {num} is {lp.get('name')})")
                continue
            if nname != num:        # the netlist only repeats the pad number (1, 2 against A, B): no name to disagree about
                warn.append(f"{ref}: pin {num} is called {nname} in the netlist and {lp.get('name')} in the library (matched by number)")
        net = str(np_.get("net") or "").strip()
        if is_hidden(lp):
            if net and not is_nc(net) and not same_name(net, lp.get("name")):
                warn.append(f"{ref}: hidden pin {num} ({lp.get('name')}) connects to net {lp.get('name')} by itself, the netlist says {net}")
            continue
        out.append((lp, net))
    for g in symbol.get("joined") or []:        # joined inside the symbol but on different nets in the netlist: say so
        nets = sorted({str(by_num[m].get("net") or "").strip() for m in g if m in by_num} - {""})
        if len(nets) > 1:
            warn.append(f"{ref}: pins {' and '.join(g)} are one terminal in library symbol {symbol['name']} (a line joins them) but the "
                        f"netlist puts them on different nets ({', '.join(nets)}): check the pin map against the datasheet")
    return out, warn, errors


def number_lead(lp):
    """How far (mils) the pin's number text runs out past the stub's first end, along the stub: a long number (A1B12) is longer than
    a 100 mil pin, so its tail lies over the start of the stub where the net label would be. 0 when it fits on the pin."""
    if not lp.get("show_number", True):
        return 0
    over = len(str(lp.get("number") or "")) * NUM_CHAR - int(lp.get("length", 0))
    return over + 50 if over > 0 else 0


def _may_duplicate(lp, listed, named):
    """May an unlisted pin be a duplicate pad of a listed terminal (the count fallback)? Not when it is a supply or ground pin, nor
    when the netlist names its pins and this pin's name is none of them (a crystal's GND pins beside OSC1/OSC2)."""
    nm = str(lp.get("name") or "").strip()
    if str(lp.get("electrical")) == "Power" or net_kind(nm) != "label":
        return False
    return not named or nm.upper() in listed


def stub_length(net, lead=0, extra=0, label=False):
    """Length of a stub in mils. label: the net is drawn as a label even when it is a ground or supply net (a crowded or upside-down
    power symbol is replaced by a label), so the stub has to hold the whole name."""
    kind = "label" if label else net_kind(net)
    if kind != "label":
        return max(POWER_STUB, _snap_up(lead + 100)) if lead else POWER_STUB
    n = int(math.ceil((max(lead, 0) + len(str(net)) * CHAR + 100) / GRID)) * GRID
    return max(300, min(n, 1500)) + extra


def _stub(lp, net, dense=False, lead=0, extra=0):
    """What goes at one pin, in symbol coordinates: {"tip", "end", "kind", "rot"...} (kind 'nc', 'power' or 'label').
    lead: the part of the stub the pin number's text covers; extra: a longer stub (a staggered label), both in mils."""
    ori = int(lp.get("orientation", 0)) & 3
    dx, dy = DIRECTION[ori]
    tx, ty = tip(lp)
    if is_nc(net):
        return {"kind": "nc", "tip": (tx, ty), "end": (tx, ty), "net": "NC"}
    kind = net_kind(net)
    if kind == "gnd" and dy > 0 or kind == "rail" and dy < 0 or dense:
        kind = "label"                  # a ground symbol would hang upside down, and power symbols on pins 100 mil apart sit on
                                        # top of each other: a label reads better
    n = stub_length(net, lead, extra, True) if kind == "label" else stub_length(net, lead)
    ex, ey = tx + dx * n, ty + dy * n
    out = {"kind": "power" if kind != "label" else "label", "tip": (tx, ty), "end": (ex, ey), "net": net, "ori": ori}
    if kind == "label":
        # the text runs along the stub, so it stays off the neighbours; rotated for a vertical stub; it starts after the pin number
        start = max(100, lead) + extra
        if dx > 0:
            out["at"], out["rot"] = (tx + start, ty), 0
        elif dx < 0:
            out["at"], out["rot"] = (ex, ey), 0
        elif dy > 0:
            out["at"], out["rot"] = (tx, ty + start), 1
        else:
            out["at"], out["rot"] = (ex, ey), 1
    else:
        out["style"] = GROUND_STYLE if kind == "gnd" else RAIL_STYLE
        out["rot"] = (3 if kind == "gnd" else 1) if dy == 0 else ori
    return out


def label_width(net):
    return len(str(net)) * CHAR


def ink_rects(s, lp=None):
    """The rectangles (x0, y0, x1, y1, symbol coordinates) a stub's drawing covers: the wire, the net label text or the power port
    and its name, and (with the library pin) the pin's number text. Conservative on purpose: text boxes use CHAR per character."""
    out = []
    (tx, ty), (ex, ey) = s["tip"], s["end"]
    if s["kind"] != "nc":
        out.append((min(tx, ex) - 10, min(ty, ey) - 10, max(tx, ex) + 10, max(ty, ey) + 10))
    if s["kind"] == "label":
        ax, ay = s["at"]
        w = label_width(s["net"])
        out.append((ax, ay - 10, ax + w, ay + TEXT_H + 10) if s["rot"] == 0 else (ax - TEXT_H - 10, ay, ax + 10, ay + w))
    elif s["kind"] == "power":
        half = max(100, label_width(s["net"]) // 2)
        out.append((ex - half, ey - 150, ex + half, ey + 150))
    if lp is not None and lp.get("show_number", True) and str(lp.get("number") or ""):
        w = len(str(lp["number"])) * NUM_CHAR
        dx, dy = DIRECTION[int(lp.get("orientation", 0)) & 3]
        x, y = lp["x"], lp["y"]
        if dy == 0:
            lo, hi = sorted((x, x + dx * w))
            out.append((lo, y + NUMBER_RAISE, hi, y + NUMBER_RAISE + NAME_HEIGHT))
        else:
            lo, hi = sorted((y, y + dy * w))
            out.append((x - NUMBER_RAISE - NAME_HEIGHT, lo, x - NUMBER_RAISE, hi))
    return out


def _hit(a, b, slack=0):
    return a[0] < b[2] + slack and b[0] < a[2] + slack and a[1] < b[3] + slack and b[1] < a[3] + slack


def _body(symbol):
    """The symbol body's box (x0, y0, x1, y1): its drawing when the reader found one, else what the pins bound (a pin on the left
    or right is taken to have the body 100 mil beyond it, up and down)."""
    pins = symbol["pins"]
    xs = [p["x"] for p in pins] or [0]
    ys = [p["y"] for p in pins] or [0]
    horiz = [p for p in pins if (int(p.get("orientation", 0)) & 3) in (0, 2)]
    box = [min(xs), min(ys) - (100 if horiz else 0), max(xs), max(ys) + (100 if horiz else 0)]
    b = symbol.get("body")
    if b:
        box = [min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3])]
    return tuple(box)


def shown_comment(comment):
    """The comment as displayed: always the whole value (the instance comment feeds the BOM and the PCB, it is never changed)."""
    return str(comment or "").strip()


def part_texts(ref, comment, body, ink):
    """Where the designator and the comment go: {"des": (x, y, width), "com": ...}, symbol coordinates, the lower left corner of each
    text (Altium anchors a text there). The first of these spots that touches no stub, label, power port or pin number is taken, so
    the cell grows as little as it can: both on one row above the body (designator, then comment), the same right aligned to the
    body, two rows above (comment next to the body, designator over it), two rows beside the body (right, then left), and last two rows
    above everything the part draws. Deterministic: same part, same spots."""
    items = [("des", str(ref or ""))] + ([("com", str(comment))] if str(comment or "").strip() else [])
    wid = {k: len(t) * TEXT_CHAR for k, t in items}
    y0 = _snap50(body[3] + TEXT_GAP)

    def row(x, y):
        out, cx = {}, x
        for k, _ in items:
            out[k] = (int(cx), y, wid[k])
            cx += wid[k] + TEXT_SPACE
        return out

    def rows(x, y, right=False):
        """Two rows, the comment lowest. right=False: both start at x (left aligned); right=True: x is the right end, each text ends
        there, but never starts left of the body (a comment far wider than the body starts at its left edge and runs past the right,
        so the designator stays beside the body)."""
        return {k: (int(max(x - wid[k], body[0]) if right else x), y + i * TEXT_PITCH, wid[k]) for i, (k, _) in enumerate(reversed(items))}

    def rows_left(x, y):
        """Two rows left of the body: each text ends at x, the designator next to the body, a wide comment running further left."""
        return {k: (int(x - wid[k]), y + i * TEXT_PITCH, wid[k]) for i, (k, _) in enumerate(reversed(items))}

    def clash(spots):
        return any(_hit((x, y, x + w, y + TEXT_H), r, 20) for x, y, w in spots.values() for r in ink)
    one = sum(wid.values()) + TEXT_SPACE * (len(items) - 1)
    mid = _snap50((body[1] + body[3]) // 2 - TEXT_PITCH // 2)
    cands = []
    if len(items) == 1 or one <= max(body[2] - body[0], ONE_ROW):
        cands += [row(body[0], y0), row(body[2] - one, y0)]
    y_low = _snap50(min([body[1]] + [r[1] for r in ink]) - TEXT_GAP - 2 * TEXT_PITCH)
    cands += [rows(body[0], y0), rows(body[2], y0, True),
              rows(body[2] + TEXT_GAP + 100, mid), rows_left(body[0] - TEXT_GAP - 100, mid),
              rows(body[0], y_low), rows(body[2], y_low, True)]
    for c in cands:
        if not clash(c):
            return c
    y1 = _snap50(max([y0] + [r[3] + TEXT_GAP for r in ink]))
    return rows(body[0], y1)


def _snap50(v):
    return int(math.ceil(v / 50)) * 50


def _build_run(run, extra=0):
    """The stubs of a run of pins ([lp, net, dense, stub] entries, left to right on one top or bottom edge, one net, 100 mil
    apart): the first pin carries the port or label, the others are plain wires of the same length, joined at their ends by short
    wires, so one name serves the whole run (twelve IOVDD pins are one +3V3, not twelve stacked labels)."""
    lp0, net, dense = run[0][0], run[0][1], run[0][2]
    s0 = _stub(lp0, net, dense if len(run) == 1 else False, max(number_lead(t[0]) for t in run), extra)
    run[0][3] = s0
    if len(run) > 1:
        dx, dy = DIRECTION[s0["ori"]]
        n = abs(s0["end"][0] - s0["tip"][0]) + abs(s0["end"][1] - s0["tip"][1])
        ends = [s0["end"]]
        for t in run[1:]:
            tx, ty = tip(t[0])
            ends.append((tx + dx * n, ty + dy * n))
            t[3] = {"kind": "wire", "tip": (tx, ty), "end": ends[-1], "net": net, "ori": s0["ori"]}
        s0["links"] = list(zip(ends, ends[1:]))


def _crowded_edges(todo):
    """Pins 100 mil apart on a top or bottom edge are text columns that touch. Same-net neighbours become one run with one label or
    port (_build_run); neighbours of different nets are staggered: every second label starts past the end of its neighbours' labels."""
    side = sorted((t for t in todo if t[3]["kind"] in ("label", "power") and t[3]["ori"] in (1, 3)),
                  key=lambda t: (t[3]["ori"], tip(t[0])[1], t[0]["x"]))
    runs = []
    for t in side:
        last = runs[-1][-1] if runs else None
        if (last and last[3]["ori"] == t[3]["ori"] and last[1] == t[1] and t[0]["x"] - last[0]["x"] <= GRID
                and tip(last[0])[1] == tip(t[0])[1]):          # same net and the same height: a stepped edge never gets a diagonal
            runs[-1].append(t)
        else:
            runs.append([t])
    for r in runs:
        if len(r) > 1:
            _build_run(r)
    items = [(r[0][3]["ori"], r[0][0]["x"], r[-1][0]["x"], r) for r in runs if r[0][3]["kind"] == "label"]
    tier = []
    for i, (ori, xa, xb, r) in enumerate(items):
        prev = items[i - 1] if i else None
        tier.append(1 - tier[-1] if prev and prev[0] == ori and xa - prev[2] <= GRID
                    and tip(prev[3][0][0])[1] == tip(r[0][0])[1] else 0)
    for i, (ori, xa, xb, r) in enumerate(items):
        if tier[i]:
            near = [items[k] for k in (i - 1, i + 1) if 0 <= k < len(items) and tier[k] == 0 and items[k][0] == ori
                    and (xa - items[k][2] <= GRID if k < i else items[k][1] - xb <= GRID)
                    and tip(items[k][3][0][0])[1] == tip(r[0][0])[1]]
            _build_run(r, _snap_up(max([label_width(n[3][0][1]) for n in near] + [0]) + 100))


def part_cell(part, symbol):
    """Everything about one part before it has a place: its pin stubs, where its designator and comment go, and the box (minx, miny,
    maxx, maxy, relative to the symbol origin) that holds the symbol, its stubs, its texts and their margin."""
    pins, warn, errors = pin_nets(part, symbol)
    pin_errors = len(errors)                # the first ones come from the pin comparison: how plan_sheet tells "pins.unmapped" from the rest
    ids = {int(p.get("part_id", 1)) for p in symbol["pins"]} - {0, -1}
    if ids - {1}:
        errors.append(f"{part['ref']}: library symbol {symbol['name']} has several parts (sub-parts {sorted(ids)}); "
                      "multi-part symbols cannot be drawn by the tool yet, draw this part by hand")
    xs, ys, stubs = [], [], []
    for lp in symbol["pins"]:
        xs += [lp["x"], tip(lp)[0]]
        ys += [lp["y"], tip(lp)[1]]
    if not xs and symbol.get("body"):            # a placeholder of a part the netlist lists no pins for: just its rectangle
        b = symbol["body"]
        xs, ys = [b[0], b[2]], [b[1], b[3]]
    wired = [(lp, net) for lp, net in pins if net and not is_nc(net)]
    todo = []
    for lp, net in pins:
        if net:
            side = int(lp.get("orientation", 0)) & 3
            across = lp["y"] if side in (0, 2) else lp["x"]
            dense = any(o is not lp and (int(o.get("orientation", 0)) & 3) == side
                        and abs((o["y"] if side in (0, 2) else o["x"]) - across) < 3 * GRID for o, _ in wired)
            s = _stub(lp, net, dense, number_lead(lp))
            todo.append([lp, net, dense, s])
    _crowded_edges(todo)
    for lp, net, dense, s in todo:
        s["pin"] = str(lp["number"])
        stubs.append(s)
        xs.append(s["end"][0])
        ys.append(s["end"][1])
    ink = []
    for s in stubs:
        ink += ink_rects(s, next(t[0] for t in todo if t[3] is s))
        ink += [(min(a[0], b[0]) - 10, min(a[1], b[1]) - 10, max(a[0], b[0]) + 10, max(a[1], b[1]) + 10) for a, b in s.get("links", ())]
    for lp in symbol["pins"]:                      # the number of a pin that has no stub is drawn too
        if not any(t[0] is lp for t in todo):
            ink += ink_rects({"kind": "nc", "tip": tip(lp), "end": tip(lp), "net": ""}, lp)
    comment = shown_comment(str(symbol.get("comment") or "").strip() or str(symbol.get("name") or ""))
    texts = part_texts(part["ref"], comment, _body(symbol), ink)
    pad = MARGIN
    box = [min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad]
    for x, y, w in texts.values():          # the texts already keep TEXT_GAP from everything: no margin of their own
        box = [min(box[0], x), min(box[1], y), max(box[2], x + w), max(box[3], y + TEXT_H)]
    box = tuple(box)
    open_pins = [f"{part['ref']}.{lp.get('name') or lp['number']}" for lp, net in pins if not net]
    for p in open_pins:
        warn.append(f"{p}: open pin (no net in the netlist), left undrawn")
    for s in stubs:
        for v in (s["tip"][0] % GRID, s["tip"][1] % GRID):
            if v:
                warn.append(f"{part['ref']}.{s['pin']}: the library pin is off the {GRID} mil grid")
                break
    return {"ref": part["ref"], "symbol": symbol["name"], "stubs": stubs, "box": box, "texts": texts, "comment": comment, "ink": ink,
            "pins": len(symbol["pins"]), "warnings": warn, "errors": errors, "pin_errors": pin_errors, "pin_nets": pins}


def _snap_up(v):
    return int(math.ceil(v / GRID)) * GRID


FRAME_PAD = 100                        # between a section frame and the boxes of its parts
FRAME_GAP = 200                        # between two section frames
FRAME_MIN_W = 4500                     # a frame is never narrower than this (room for its title)
TITLE_CHAR = 80                        # width of one character of the frame text, with some slack
TITLE_LINE = 130                       # height of one line of the frame text


def frame_text(sid, title="", note=""):
    return f"{TAG} {sid} - {title}".strip(" -") + note


def _strip_height(text, width):
    """Height of the title strip at the top of a frame: one line is HEADER; a long title (the unverified-pins note) wraps."""
    per_line = max(10, (width - 2 * FRAME_PAD) // TITLE_CHAR)
    lines = max(1, int(math.ceil(len(str(text)) / per_line)))
    return HEADER if lines == 1 else _snap_up(120 + TITLE_LINE * lines)


def layout(cells, sections, area=AREA, texts=None):
    """Places the cells on a grid, section after section from the top of the sheet. Each section is one frame that encloses its
    title (a strip at the top) and all its parts with their stubs, labels and power ports (the cell boxes), the parts on shelves
    left to right. cells: [(section id, cell)]; texts: {section id: the frame's text} (sizes the title strip).
    Returns ({ref: (x, y)}, [((x, y, w, h), section id)], problems): the frame's lower left corner and size."""
    x0, y0, x1, y1 = area
    pos, heads, problems = {}, [], []
    y = y1
    texts = texts or {}
    titles = {s["id"]: s.get("title") or "" for s in sections}
    order = [s["id"] for s in sections] or [""]
    for sid in order:
        mine = [c for s, c in cells if s == sid]
        if not mine:
            continue
        rel, x, shelf_h, top = {}, x0, 0, 0                  # shelves relative to a top of 0, shifted below the title strip after
        right, bottom = x0, 0
        for c in mine:
            bx0, by0, bx1, by1 = c["box"]
            w, h = bx1 - bx0, by1 - by0
            if x > x0 and x + w > x1:
                top -= shelf_h + GAP
                x, shelf_h = x0, 0
            ox, oy = _snap_up(x - bx0), _snap_up(top - by1)       # the symbol origin that puts the box's corner at (x, top)
            rel[c["ref"]] = (ox, oy)
            right = max(right, ox + bx1)
            bottom = min(bottom, oy + by0)
            x = ox + bx1 + GAP
            shelf_h = max(shelf_h, h)
        fx = x0 - FRAME_PAD
        fw = max(_snap_up(right + FRAME_PAD - fx), FRAME_MIN_W)
        strip = _strip_height(texts.get(sid) or frame_text(sid, titles.get(sid, "")), fw)
        shift = y - strip - FRAME_PAD                         # a multiple of GRID, so the placed cells stay on the grid
        fy = int(math.floor((bottom + shift - FRAME_PAD) / GRID)) * GRID     # a box edge may be off the grid (a 50 mil pin offset)
        for c in mine:
            ox, oy = rel[c["ref"]]
            pos[c["ref"]] = (ox, oy + shift)
            bx0, by0, bx1, by1 = c["box"]
            if ox + bx1 > x1:
                problems.append(f"{c['ref']} does not fit on the sheet")
        if fy < y0 or fx + fw > x1 + FRAME_PAD:                # the frame itself stays above the title block and inside the border
            problems.append(f"section {sid or '(all parts)'} does not fit on the sheet")
        heads.append(((fx, fy, fw, y - fy), sid))
        y = fy - FRAME_GAP
    return pos, heads, problems


def _plain(text):
    return all(32 <= ord(ch) < 127 for ch in str(text))


# ---------------------------------------------------------------- non-ASCII net names: drawn under a deterministic ASCII name

_HEBREW = {"א": "A", "ב": "B", "ג": "G", "ד": "D", "ה": "H", "ו": "V", "ז": "Z", "ח": "CH", "ט": "T", "י": "Y", "ך": "K", "כ": "K",
           "ל": "L", "ם": "M", "מ": "M", "ן": "N", "נ": "N", "ס": "S", "ע": "A", "ף": "F", "פ": "P", "ץ": "TZ", "צ": "TZ", "ק": "Q",
           "ר": "R", "ש": "SH", "ת": "T"}
_DASHES = dict.fromkeys("\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe63\uff0d", "-")


def _ascii_char(ch):
    if 32 <= ord(ch) < 127:
        return ch
    if ch.isdigit():
        try:
            return str(unicodedata.decimal(ch))        # an Arabic-Indic or other digit keeps its value
        except (ValueError, TypeError):
            pass
    if ch in _HEBREW:
        return _HEBREW[ch]
    if ch in _DASHES:
        return "-"
    return None


def transliterate(text):
    """A name as plain ASCII, the same text always giving the same result: a Hebrew letter by the table above, an accented letter
    without its accent (NFKD), a dash look-alike as '-', every other character as '_'. A plain ASCII name is returned unchanged."""
    if _plain(text):
        return str(text)
    out = []
    for ch in str(text):
        got = _ascii_char(ch)
        if got is not None:
            out.append(got)
            continue
        for d in unicodedata.normalize("NFKD", ch):
            if unicodedata.combining(d):
                continue                      # the accent, a Hebrew point (niqqud)
            got = _ascii_char(d)
            out.append("_" if got is None else got)
    return "".join(out) or "_"


class AliasConflict(ValueError):
    """A plain net name that is already the drawn name of another (non-ASCII) net."""


def _power_kind(name):
    """'gnd' | 'rail' | 'label' by every classification the system uses (this module's and the router's)."""
    from altium import route
    n = str(name).strip()
    if net_kind(n) == "gnd" or route._is_gnd(n):
        return "gnd"
    if net_kind(n) == "rail" or route._RAIL.match(n):
        return "rail"
    return "label"


def assign_aliases(existing, names, guard_power=True):
    """(map, changed): `existing` {name: drawn name} extended with the non-ASCII `names` that have none yet. A drawn name that is
    taken (by a plain name in `names` or by any earlier assignment, compared without case) is never given again: _2, _3 ... is
    added. A name that was assigned keeps its drawn name for good. A transliteration that the system would classify as ground or
    a supply rail while the original name is not (ודד -> VDD) gets 'N_' in front, so it stays an ordinary net. Raises
    AliasConflict when a plain name is already the drawn name of another net that is still in the netlist. An entry whose net is
    gone does not block a plain name: it is dropped (any other stale entry stays, so it is stable if the net comes back)."""
    out = dict(existing)
    names = {str(n) for n in names if str(n or "").strip()}
    plain_up = {n.upper() for n in names if _plain(n)}
    stale = [k for k, v in out.items() if k not in names and v.upper() in plain_up]
    for k in stale:       # the net of that drawn name is gone and a plain net now has the name: the old entry gives way
        del out[k]
    taken = {}
    for k, v in out.items():
        taken.setdefault(v.upper(), k)
    for n in sorted(x for x in names if _plain(x)):
        if n.upper() in taken:
            raise AliasConflict(f"the name {n!r} is already the drawn name of {taken[n.upper()]!r}: rename one of the two nets "
                                "(the schematic draws one name for one net only)")
    used = set(taken) | {n.upper() for n in names if _plain(n)}
    changed = bool(stale)
    for n in sorted(x for x in names if not _plain(x) and x not in out):
        base = transliterate(n)
        if guard_power and _power_kind(base) != "label" and _power_kind(base) != _power_kind(n):
            base = "N_" + base
        cand, k = base, 1
        while cand.upper() in used:
            k += 1
            cand = f"{base}_{k}"
        used.add(cand.upper())
        out[n] = cand
        changed = True
    return out, changed


def net_aliases(names):
    """{net name: drawn name} for the non-ASCII names, from nothing assigned yet (see assign_aliases; alias_map is the
    project's persisted version, the one the draw, place and rules steps all use)."""
    names = list(names)
    got, _ = assign_aliases({}, names)
    return {n: a for n, a in got.items() if n in {str(x) for x in names}}


ALIAS_FILE = "net-names.json"


def _alias_path(project):
    import store
    return store.pdir(project) / ALIAS_FILE


def _project_nets(project):
    import store
    out = set()
    for sid in store.sheet_ids(project):
        for p in store.load_sheet(project, sid).get("parts", []):
            for pin in (p.get("pins", []) if isinstance(p, dict) else []):
                if isinstance(pin, dict) and str(pin.get("net") or "").strip():
                    out.add(str(pin["net"]))
    return out


def alias_map(project, extra=()):
    """THE source of the drawn net names: {net: drawn name} for every non-ASCII net of the project's netlist and `extra` names, read
    from and saved to the project's net-names.json. Stable: a name once assigned is never reassigned, and a new name never takes
    one already assigned or a plain net name. Raises AliasConflict when a plain net now has an assigned drawn name."""
    import json
    path = _alias_path(project)
    try:
        saved = json.loads(path.read_text(encoding="utf-8")).get("nets", {})
    except (OSError, ValueError, AttributeError):
        saved = {}
    saved = {str(k): str(v) for k, v in saved.items()} if isinstance(saved, dict) else {}
    nets = _project_nets(project) | {str(x) for x in extra}
    got, changed = assign_aliases(saved, nets)
    if changed:
        path.write_text(json.dumps({"nets": got}, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return {n: a for n, a in got.items() if n in nets}


def drawn_net_name(project, net):
    """The name a net is drawn, placed and ruled under (the net itself when it is plain ASCII)."""
    return net if _plain(net) else alias_map(project, [net])[str(net)]


def alias_parts(parts, aliases):
    """Copies of the netlist parts whose pins carry the drawn net names (the netlist itself is never rewritten)."""
    if not aliases:
        return parts
    return [{**p, "pins": [{**pin, "net": aliases.get(str(pin.get("net")), pin.get("net"))} if isinstance(pin, dict) else pin
                           for pin in p.get("pins", [])]} for p in parts]


_INNET = re.compile(r"(InNet\s*\(\s*')([^']+)(')", re.I)


def scope_nets(text):
    return [m.group(2) for m in _INNET.finditer(str(text or ""))]


def alias_scope(text, aliases):
    """A rule scope expression with its InNet('...') names replaced by the drawn names."""
    return _INNET.sub(lambda m: m.group(1) + aliases.get(m.group(2), m.group(2)) + m.group(3), str(text or ""))


def _tie(c, members):
    """How strongly a part is connected to the parts already on a sheet: shared signal nets count 10, shared supply or ground 1 (so
    decoupling capacitors and a crystal stay with the MCU they serve)."""
    mine = {x["net"] for x in c["stubs"] if x["kind"] != "nc" and x["net"]}
    got = 0
    for m in members:
        for n in mine & {x["net"] for x in m["stubs"] if x["kind"] != "nc" and x["net"]}:
            got += 10 if net_kind(n) == "label" else 1
    return got


def _nets(c):
    return {x["net"] for x in c["stubs"] if x["kind"] != "nc" and x["net"]}


def _count(c, net):
    return sum(1 for x in c["stubs"] if x["kind"] != "nc" and x["net"] == net)


def own_parts(seed, todo):
    """The small parts that belong to an IC, in the order they should join its sheet:
    1. decoupling capacitors (2 pins, every net a supply or ground) on a supply of the IC: a supply only this IC uses (the +1V1 core
       rail) gives all its capacitors to it; a supply several ICs share is split by their supply pin counts (9 of the 10 +3V3
       capacitors to an IC with 9 of the 10 +3V3 pins), so the first IC does not take every capacitor;
    2. 2-pin parts on the IC's signal nets only (pull-ups, a series resistor): every signal net of the part is one of the IC's and
       none reaches another large part;
    3. an oscillator (reference X or Y) on a signal net of the IC, and the 2-pin parts whose signal nets are the IC's or the
       oscillator's (its load capacitors and damping resistor).
    A signal net never pulls in a part of more than 2 pins (a switch, a connector, an LED chain), and a supply net never pulls in
    anything but a 2-pin supply/ground part."""
    if seed["pins"] <= 4:
        return []
    large = [c for c in todo if c["pins"] > 4 and c is not seed]
    sig = lambda c: {n for n in _nets(c) if net_kind(n) == "label"}      # noqa: E731
    mine, others = sig(seed), set()
    for c in large:
        others |= sig(c)
    got = []
    caps = [c for c in todo if c["pins"] == 2 and not sig(c)]
    for net in sorted({n for c in caps for n in _nets(c) if net_kind(n) == "rail"}):
        have = _count(seed, net)
        if not have:
            continue
        group = [c for c in caps if net in _nets(c) and c not in got]
        total = have + sum(_count(o, net) for o in large)
        take = group if total == have else group[:len(group) * have // total]
        got += take
    got.sort(key=lambda c: todo.index(c))
    for c in todo:                                                            # 2-pin parts on the IC's own signal nets
        if c["pins"] == 2 and c not in got and sig(c) and sig(c) <= mine and not (sig(c) & others):
            got.append(c)
    osc = [c for c in todo if c["pins"] <= 4 and c["ref"][:1] in "XY" and sig(c) & mine and not (sig(c) & others)]
    nets = mine.union(*[sig(c) for c in osc]) if osc else mine
    for c in osc:
        if c not in got:
            got.append(c)
    for c in todo:
        if c["pins"] == 2 and c not in got and sig(c) and sig(c) <= nets and not (sig(c) & others) and osc:
            got.append(c)
    return got


def _join(a, b):
    out = list(a)
    for sid, refs in b:
        k = next((n for n, (i, r) in enumerate(out) if i == sid and r is not None and refs is not None), None)
        if k is None:
            out.append((sid, refs))
        else:
            out[k] = (sid, out[k][1] + refs)
    return out


def fit_size(cells, sections, texts=None, sizes=SHEET_ORDER):
    """The first sheet size of `sizes` (A4, then A3) whose layout holds every cell: (name, pos, heads, []) or, when none does,
    (None, pos, heads, problems of the biggest size tried)."""
    for name in sizes:
        pos, heads, problems = layout(cells, sections, sheet_area(name), texts)
        if not problems:
            return name, pos, heads, []
    return None, pos, heads, problems


def suggest_sheets(cells, sections, area=AREA, texts=None):
    """How the design could be spread over several sheets so that EVERY sheet fits: ([sheet], [ref that does not fit alone]); a sheet
    is [(section id, [refs] or None for the whole section)]. Every candidate sheet goes through layout(), the very check plan_sheet
    makes (cell boxes with their stubs, labels and the part texts, the frames and their title strips, the sheet border), so a
    suggested sheet is never refused when it is drawn. Whole sections are kept together and in order; a section that is too big alone
    is cut by parts (in the netlist's order), each piece a sheet or the start of the next."""
    sec = {s["id"]: s for s in sections}
    have = {sid for sid, _ in cells}
    order = [i for i in ([s["id"] for s in sections] or [""]) if i in have]

    def fits(items):
        sel = [(sid, c) for sid, c in cells if any(sid == i and (r is None or c["ref"] in r) for i, r in items)]
        sids = []
        for sid, _ in sel:
            if sid not in sids:
                sids.append(sid)
        secs = [sec.get(i, {"id": i}) for i in sids]
        if not sel:
            return False
        return fit_size(sel, secs, texts)[0] is not None if area is None else not layout(sel, secs, area, texts)[2]
    sheets, hopeless, cur = [], [], []
    for sid in order:
        if cur and fits(cur + [(sid, None)]):
            cur = cur + [(sid, None)]
            continue
        if fits([(sid, None)]):
            if cur:
                sheets.append(cur)
            cur = [(sid, None)]
            continue
        if cur:
            sheets.append(cur)
        cur = []
        todo = [c for s_, c in cells if s_ == sid]
        while todo:
            seed = max(todo, key=lambda c: (c["pins"], -todo.index(c)))      # the biggest part first, its neighbours after it
            todo.remove(seed)
            if not fits([(sid, [seed["ref"]])]):
                hopeless.append(seed["ref"])
                continue
            piece, members = [seed["ref"]], [seed]
            for c in own_parts(seed, todo):
                if fits([(sid, piece + [c["ref"]])]):          # its own decoupling capacitors, crystal and pull-ups first
                    piece.append(c["ref"])
                    members.append(c)
            todo = [c for c in todo if c["ref"] not in piece]
            while True:
                best = sorted((c for c in todo if _tie(c, members) > 0), key=lambda c: (-_tie(c, members), todo.index(c)))
                add = next((c for c in best if fits([(sid, piece + [c["ref"]])])), None)
                if add is None:
                    break
                todo.remove(add)
                piece.append(add["ref"])
                members.append(add)
            sheets.append([(sid, piece)])
    if cur:
        sheets.append(cur)
    k = 0
    while k + 1 < len(sheets):          # small pieces that fit together (and are next to each other) share a sheet
        both = _join(sheets[k], sheets[k + 1])
        if fits(both):
            sheets[k:k + 2] = [both]
        else:
            k += 1
    return sheets, hopeless


def _too_big_message(cells, sections, texts=None):
    sheets, hopeless = suggest_sheets(cells, sections, area=None, texts=texts)
    titles = {s["id"]: str(s.get("title") or "").strip() for s in sections}
    refs = {}
    for sid, c in cells:
        refs.setdefault(sid, []).append(str(c.get("ref") or ""))

    def label(sid, only=None):
        """What the student sees for a section: its title and the parts in it (never the internal section letter alone)."""
        if not sid:
            return "the design"
        r = [x for x in (only or refs.get(sid, [])) if x]
        shown = ", ".join(r[:6]) + (" ..." if len(r) > 6 else "")
        return (titles.get(sid) or f"section {sid}") + (f" ({shown})" if shown else "")
    nets = {}
    for sid, c in cells:
        for sh_i, sh in enumerate(sheets):
            if any(sid == i and (r is None or c["ref"] in r) for i, r in sh):
                nets.setdefault(c["ref"], set()).add(sh_i)
    by_net = {}
    for sid, c in cells:
        for s_ in c["stubs"]:
            if s_["kind"] != "nc" and s_["net"] and net_kind(s_["net"]) == "label":
                by_net.setdefault(s_["net"], set()).update(nets.get(c["ref"], ()))
    shared = sorted(n for n, where in by_net.items() if len(where) > 1)
    cut = [sid for sid in dict.fromkeys(s_ for s_, _ in cells) if sum(1 for sh in sheets for i, r in sh if i == sid and r is not None)]
    if hopeless:
        return (f"the design does not fit on one A4 sheet, nor on A3, and {', '.join(hopeless[:6])} does not fit on an A3 sheet even by itself "
                "(too many pins or too long net names): split the part's connections differently or draw it by hand.")
    if len(sheets) <= 1:       # one sheet is all there is and it is still refused: there is nothing to move to a second sheet
        return (f"the design does not fit on one A4 sheet, nor on A3, and it is a single section ({', '.join(label(i) for i, _ in (sheets[0] if sheets else []))}) "
                "that is too big for a sheet by itself: it must be split into several sections (and sheets) in the netlist. "
                "The tool does not yet draw the nets that run between sheets (that needs ports), so each sheet is a netlist sheet of its own.")
    msg = (f"the design does not fit on one A4 sheet, nor on A3. It needs about {len(sheets)} sheets (each one checked to fit): "
           + "; ".join(f"sheet {k}: {', '.join(label(i, r) for i, r in sh)}" for k, sh in enumerate(sheets, 1)) + ". ")
    if cut:
        msg += f"Section {', '.join(label(x) for x in cut)} is too big for one sheet, so it is cut by parts above. "
    msg += ("The tool does not yet draw the nets that run between sheets (that needs ports), so write the netlist as separate "
            "sheets (one per group above) and draw them one by one"
            + (f". Nets that would cross: {', '.join(shared[:8])}" if shared else "") + ".")
    return msg


def text_problems(sheet, parts, symbols):
    """Names that cannot travel to Altium (the script file is plain ASCII, fields are TAB separated): refuse before drawing.
    Net names are not here: a non-ASCII net is drawn under its transliteration (net_aliases)."""
    bad = []
    names = [("part", p["ref"]) for p in parts]
    names += [("symbol", sym["name"]) for sym in symbols.values()]
    for what, text in names:
        if not _plain(text):
            bad.append(f"{what} name {str(text)!r} has a non-ASCII character, a tab or a line break: rename the part or symbol (letters, digits, + - _ . / only)")
    return sorted(set(bad))


# ---------------------------------------------------------------- draft: a placeholder for a part that has no usable symbol yet
# A draft draw never stops for a part the library cannot give a symbol (none built, none for the part, one that does not fit the
# netlist's pins): the part is drawn as a plain rectangle with the netlist's own pins, wire stubs and net labels as for any part, so
# every net stays connected on the sheet. The symbol is made from the netlist alone (partlib_generate.box_symbol, all pins Passive:
# nothing is known about them), lives in a draft SchLib of its own (never in the project library, whose build starts from the
# template), and is named in its comment. The sheet's heading and store.manufacturing_warning say "draft"; a later draw with the
# real symbol replaces it.

PLACEHOLDER_PREFIX = "PH_"
PLACEHOLDER_WORD = "PLACEHOLDER"
NO_SYMBOL = "no library symbol yet"
BAD_SYMBOL = "library symbol does not match the netlist pins"
MULTI_SYMBOL = "multi-part library symbol, draw it by hand"
_PIN_NUM = re.compile(r"[A-Za-z0-9]{1,6}")
_ORIENT = {"eRotate0": 0, "eRotate90": 1, "eRotate180": 2, "eRotate270": 3}


def symbol_problems(part, symbol):
    """Why the part cannot be drawn from this library symbol ([] = it can): the pin comparison's errors and a symbol of several parts."""
    errors = list(pin_nets(part, symbol)[2])
    ids = {int(p.get("part_id", 1)) for p in symbol["pins"]} - {0, -1}
    if ids - {1}:
        errors.append(f"{part['ref']}: library symbol {symbol['name']} has several parts")
    return errors


def placeholder_name(ref):
    return PLACEHOLDER_PREFIX + (re.sub(r"[^A-Za-z0-9]+", "_", str(ref)).strip("_")[:50] or "part")


def placeholder_comment(why):
    return f"{PLACEHOLDER_WORD}: {why}"


def _pin_text(text, fallback):
    from partlib_convert import clean
    plain = clean(transliterate(str(text or "").strip()), 40)
    return plain if plain and _plain(plain) else fallback


def placeholder(part, why, name):
    """The placeholder of one netlist part: {"part": the part with a drawable, unique number on every pin, "symbol": the symbol as
    lib.read_schlib reads it, "spec": the lines SYMBATCH makes it from, "props": the SYMPROPS line, "warnings": [...]}.
    A pin with no number, a number the library cannot hold or a number already taken gets the next free whole number (a warning
    says so); the netlist itself is never changed."""
    from partlib_generate import box_symbol
    ref = str(part["ref"])
    pins, taken, warn = [], set(), []
    for p in part.get("pins", []):
        if not isinstance(p, dict):
            continue
        num = str(p.get("num", p.get("number", "")) or "").strip()
        good = bool(_PIN_NUM.fullmatch(num)) and num not in taken
        if good:
            taken.add(num)
        pins.append([p, num if good else ""])
    nxt = 0
    for entry in pins:
        if entry[1]:
            continue
        nxt += 1
        while str(nxt) in taken:
            nxt += 1
        was = str(entry[0].get("num", entry[0].get("number", "")) or "").strip()
        entry[1] = str(nxt)
        taken.add(entry[1])
        warn.append(f"{ref}: pin {entry[0].get('name') or '(no name)'} has " + (f"no usable pin number ({was!r})" if was else "no pin number")
                    + f" in the netlist; the placeholder numbers it {nxt}")
    planned = []
    for p, num in pins:
        q = {k: v for k, v in p.items() if k != "number"}
        q["num"], q["name"] = num, _pin_text(p.get("name"), num)
        planned.append(q)
    sym_pins, gfx, _ = box_symbol("U", [{"num": q["num"], "name": q["name"], **({"side": q["side"]} if q.get("side") else {})} for q in planned], [])
    for sp in sym_pins:
        sp["type"] = "Passive"
    prefix = (re.match(r"[A-Za-z]+", ref) or [""])[0].upper()[:6] or "U"
    comment = placeholder_comment(why)
    xs0, ys0, xs1, ys1 = (gfx[0][4], gfx[0][5], gfx[0][6], gfx[0][7]) if gfx else (0, 0, 0, 0)
    symbol = {"name": name, "description": comment, "designator": f"{prefix}?", "comment": comment, "params": {}, "footprints": [],
              "pinned_paths": [], "graphics": len(gfx), "joined": [], "body": (xs0, ys0, xs1, ys1),
              "pins": [{"number": sp["num"], "name": sp["name"], "electrical": "Passive", "x": int(sp["x"]), "y": int(sp["y"]),
                        "length": int(sp["len"]), "orientation": _ORIENT.get(sp["orient"], 0),
                        "conglomerate": _ORIENT.get(sp["orient"], 0) | 8 | 16, "show_name": True, "show_number": True, "part_id": 1}
                       for sp in sym_pins]}
    from partlib_convert import clean
    spec = [f"SYMBOL|{name}|{clean(comment)}|1"]
    spec += ["GRAPHIC|" + "|".join(str(v) for v in g) for g in gfx]
    spec += [f"PIN|{clean(sp['num'], 20)}|{clean(sp['name'], 60)}|eElectricPassive|{sp['orient']}|{sp['x']}|{sp['y']}|1|{sp['len']}" for sp in sym_pins]
    return {"part": {**part, "pins": planned}, "symbol": symbol, "spec": spec, "props": f"{name}={prefix}|{clean(comment)}",
            "warnings": warn, "why": why}


def plan_sheet(sheet, symbols, schlib, doc, replace=False, aliases=None, placeholders=None, sheet_size=None):
    """Plan one netlist sheet.
    sheet: the netlist sheet dict; symbols: {ref: symbol dict from read_schlib}; schlib / doc: file paths.
    placeholders (a draft draw): {ref: {"why", "name", "schlib"}}: those parts are drawn from placeholder() (symbol `name` in the draft
    SchLib `schlib`) instead of `symbols`; a part with neither is an error, as ever.
    sheet_size: "A4" / "A3" to force a size, else the first of A4, A3 that holds the layout (out["sheet_size"]; None = too big even for A3).
    Returns {"commands": [...], "parts": [{ref, symbol, pins, x, y}], "expected": {net: [tags]}, "no_erc": [tags],
             "warnings": [...], "errors": [...], "placeholders": [{ref, why, section}]}."""
    placeholders = placeholders or {}
    symbols = dict(symbols)
    parts = [p for p in sheet.get("parts", []) if isinstance(p, dict) and p.get("ref")]
    if aliases is None:
        aliases = net_aliases(pin.get("net") for p in parts for pin in p.get("pins", []) if isinstance(pin, dict))
    used = {str(pin.get("net")) for p in parts for pin in p.get("pins", []) if isinstance(pin, dict)}
    renamed = {n: a for n, a in aliases.items() if n in used}
    parts = alias_parts(parts, renamed)     # the netlist itself is not touched: the planned copy carries the drawn names, so the read-back compares with them
    sections = [s for s in sheet.get("sections", []) if isinstance(s, dict) and s.get("id")]
    ids = {s["id"] for s in sections}
    first = sections[0]["id"] if sections else ""
    errors, warnings, cells = [], [], []
    why = set()          # which kinds of refusal there are: one mechanical kind (see altium.bridge.NEUTRAL_CODES) is "fix_code", else None
    warnings += [f"net {n!r} drawn as {a!r} (the schematic is plain ASCII; the netlist keeps its name)" for n, a in sorted(renamed.items())]
    drafted = {}
    for p in parts:
        sym = symbols.get(p["ref"])
        ph = placeholders.get(p["ref"])
        if ph is not None:
            e = placeholder(p, ph["why"], ph["name"])
            p, sym = e["part"], e["symbol"]
            symbols[p["ref"]] = sym
            warnings += [f"{p['ref']}: drawn as a placeholder ({ph['why']})"] + e["warnings"]
        elif sym is None:
            errors.append(f"{p['ref']}: no symbol in the project library (run library.build first)")
            why.add("prereq.library_not_built")
            continue
        c = part_cell(p, sym)
        if ph is not None:
            c["placeholder"] = ph
            drafted[p["ref"]] = ph["why"]
        c["unverified"] = p.get("pins_source") == "agent"
        c["accepted"] = p.get("pins_source") == "student"
        warnings += c["warnings"]
        errors += c["errors"]
        if c["pin_errors"]:
            why.add("pins.unmapped")
        if len(c["errors"]) > c["pin_errors"]:
            why.add("other")
        cells.append((p.get("section") if p.get("section") in ids else first, c))
    texts_bad = text_problems(sheet, parts, symbols)
    errors += texts_bad
    if texts_bad:
        why.add("other")
    out = {"commands": [], "parts": [], "expected": {}, "no_erc": [], "warnings": warnings, "errors": errors, "renamed": renamed, "sheet_size": None,
           "placeholders": [{"ref": r, "why": w} for r, w in drafted.items()]}
    if errors:
        out["fix_code"] = next(iter(why)) if len(why) == 1 and "other" not in why else None
        return out
    titles = {s["id"]: s.get("title") or "" for s in sections}
    head_names = {}
    for n, s_ in enumerate(sections, 1):        # section headings are cosmetic: a non-ASCII one is drawn as "Section N" / without its title
        if not _plain(s_["id"]) or not _plain(titles[s_["id"]]):
            warnings.append(f"section {n}: the heading has non-ASCII characters and is drawn as 'Section {n}'")
            titles[s_["id"]] = ""
            head_names[s_["id"]] = f"Section {n}"
    # parts whose pins came from the agent, not a datasheet (store._mark_pins_source): the drawn sheet says so in the heading of
    # their section, so the mark stays on the student's own drawing and not only in the advisor (principle 3 of the spec)
    unverified = {}
    for sid, c in cells:
        if c.get("unverified"):
            unverified.setdefault(sid, []).append(c["ref"])
    out["unverified"] = sorted(r for refs in unverified.values() for r in refs)
    accepted = {}
    for sid, c in cells:                        # pins the student accepted without a datasheet pin table: still marked on the sheet
        if c.get("accepted"):
            accepted.setdefault(sid, []).append(c["ref"])
    out["accepted_pins"] = sorted(r for refs in accepted.values() for r in refs)
    texts = {}
    draft = {}
    for sid, c in cells:                        # a draft sheet says so in the heading of the section that holds a placeholder
        if c.get("placeholder"):
            draft.setdefault(sid, []).append(c["ref"])
    for sid in ids | ({""} if draft.get("") else set()):
        refs = unverified.get(sid) or []         # the title strip wraps; a long list is cut, the advisor has all of it
        note = f" | pins not checked against a datasheet: {', '.join(refs[:6])}" + (f" +{len(refs) - 6}" if len(refs) > 6 else "") if refs else ""
        acc = accepted.get(sid) or []
        if acc:
            note += f" | pins accepted by student, not verified: {', '.join(acc[:6])}" + (f" +{len(acc) - 6}" if len(acc) > 6 else "")
        dr = draft.get(sid) or []
        if dr:
            note += f" | DRAFT, placeholder parts: {', '.join(dr[:6])}" + (f" +{len(dr) - 6}" if len(dr) > 6 else "")
        texts[sid] = frame_text(head_names.get(sid, sid), titles.get(sid, ""), note)
    size, pos, heads, problems = fit_size(cells, sections, texts, (sheet_size,) if sheet_size else SHEET_ORDER)
    out["sheet_size"] = size
    if problems:
        errors.append(problems[0] + (f" (+{len(problems) - 1} more)" if len(problems) > 1 else "") + ": " + _too_big_message(cells, sections, texts))
        out["fix_code"] = "sheet.too_big"
    if errors:
        return out
    d = str(doc)
    cmds = [("DRAWBEGIN", d, "1" if replace else "0", str(SHEETS[size]["style"]))]
    for (fx, fy, fw, fh), sid in heads:         # one frame around the whole section, its title at the top (a text frame starts its text there)
        if sid or texts.get(sid):
            cmds.append(("FRAME", d, str(fx), str(fy), str(fw), str(fh), texts[sid]))
    for _, c in cells:
        ox, oy = pos[c["ref"]]
        spots = []              # the designator and the comment text go to the free spots part_cell found (sheet coordinates)
        for k in ("des", "com"):
            t = c["texts"].get(k)
            spots += [str(ox + t[0]), str(oy + t[1])] if t else ["", ""]
        cmds.append(("PLACE", d, c["ref"], c["symbol"], str((c.get("placeholder") or {}).get("schlib") or schlib), str(ox), str(oy), str(c["pins"]), *spots))
        out["parts"].append({"ref": c["ref"], "symbol": c["symbol"], "pins": c["pins"], "x": ox, "y": oy,
                             **({"placeholder": True} if c.get("placeholder") else {})})
        for s in c["stubs"]:
            tx, ty = ox + s["tip"][0], oy + s["tip"][1]
            tag = f"{c['ref']}-{s['pin']}"
            if s["kind"] == "nc":
                cmds.append(("NOERC", d, str(tx), str(ty)))
                out["no_erc"].append(tag)
                continue
            ex, ey = ox + s["end"][0], oy + s["end"][1]
            cmds.append(("WIRE", d, str(tx), str(ty), str(ex), str(ey)))
            for (a1, b1), (a2, b2) in s.get("links", ()):       # the wires that join a run of same-net stubs at their ends
                cmds.append(("WIRE", d, str(ox + a1), str(oy + b1), str(ox + a2), str(oy + b2)))
            if s["kind"] == "power":
                cmds.append(("POWER", d, str(ex), str(ey), str(s["rot"]), str(s["style"]), s["net"]))
            elif s["kind"] == "label":
                ax, ay = ox + s["at"][0], oy + s["at"][1]
                cmds.append(("NETLABEL", d, str(ax), str(ay), str(s["rot"]), s["net"]))
            out["expected"].setdefault(s["net"], []).append(tag)
    cmds.append(("SAVE", d))
    out["commands"] = cmds
    return out


def verify_sheet(plan, doc, footprints=None):
    """Compares the saved sheet (read_schdoc dict) with the plan. Returns a list of problem strings (empty = it matches):
    every part there with the library symbol's pin count, its footprint link kept, every drawn net joining exactly the pins
    the netlist says, every NC pin marked No ERC."""
    from checks.schematic import build_schdoc_sheet_netlist
    footprints = footprints or {}
    problems = []
    comps = {c["ref"]: c for c in doc.get("components", [])}
    for p in plan["parts"]:
        c = comps.get(p["ref"])
        if c is None:
            problems.append(f"{p['ref']} is not on the saved sheet")
            continue
        if len(c["pins"]) != p["pins"]:
            problems.append(f"{p['ref']} has {len(c['pins'])} pins on the sheet, the library symbol {p['symbol']} has {p['pins']}")
        if c.get("lib_ref") != p["symbol"]:
            problems.append(f"{p['ref']} is symbol {c.get('lib_ref')!r}, expected {p['symbol']!r}")
        want = footprints.get(p["ref"])
        if want and c.get("footprint") != want:
            problems.append(f"{p['ref']} lost its footprint link (sheet: {c.get('footprint') or 'none'}, library: {want})")
    extra = sorted(set(comps) - {p["ref"] for p in plan["parts"]})
    if extra:
        problems.append(f"parts on the sheet that are not in the netlist: {', '.join(extra)}")
    got = build_schdoc_sheet_netlist(doc)
    pin_net = got["pin_net_map"]
    for net, tags in plan["expected"].items():
        for tag in tags:
            if pin_net.get(tag) != net:
                problems.append(f"{tag} should be on {net}, the sheet has it on {pin_net.get(tag)}")
        joined = set(got["nets"].get(net, []))
        stray = sorted(joined - set(tags))
        if stray:
            problems.append(f"net {net} also joins {', '.join(stray[:6])}, which the netlist does not put there")
    missing = sorted(set(plan["no_erc"]) - set(got["no_erc_pins"]))
    if missing:
        problems.append(f"No ERC marker missing on {', '.join(missing)}")
    return problems
