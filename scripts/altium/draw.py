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
import re

TAG = "[advisor]"                      # the same first word the skeleton frames carry
GRID = 100                             # mils: everything is placed on the 100 mil grid
DIRECTION = {0: (1, 0), 1: (0, 1), 2: (-1, 0), 3: (0, -1)}      # pin rotation: right, up, left, down
AREA = (800, 1000, 10800, 6800)        # usable drawing area of an A4 sheet in mils: x0, y0, x1, y1
HEADER = 300                           # height of a section heading
GAP = 200                              # between two parts, on top of their own margin
MARGIN = 200                           # room kept around a part for its power symbols and labels
CHAR = 70                              # width of one label character in mils (the default 10 pt font)
POWER_STUB = 200
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
    return str(net or "").strip().upper() in ("NC", "N/C", "NO_ERC")


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
    for p in part.get("pins", []):
        by_num[str(p.get("num", p.get("number", "")) or "")] = p
    lib_nums = {str(lp["number"]) for lp in symbol["pins"]}
    out, warn = [], []
    for num in by_num:
        if num not in lib_nums:
            errors.append(f"{ref}: netlist pin {num} ({by_num[num].get('name') or ''}) has no pin in library symbol {symbol['name']}")
    for lp in symbol["pins"]:
        num = str(lp["number"])
        np_ = by_num.get(num)
        if np_ is None:
            warn.append(f"{ref}: library pin {num} ({lp.get('name')}) is not in the netlist; left unconnected")
            continue
        nname = str(np_.get("name") or "").strip()
        if nname and str(lp.get("name") or "").strip() and not same_name(nname, lp.get("name")):
            other = [o for o in symbol["pins"] if str(o["number"]) != num and same_name(o.get("name"), nname)]
            if other:       # the netlist's name belongs to another pin of the symbol: a real swap
                errors.append(f"{ref}: pin {num} is {nname} in the netlist, but {nname} is pin {other[0]['number']} of library symbol "
                              f"{symbol['name']} (pin {num} is {lp.get('name')})")
                continue
            warn.append(f"{ref}: pin {num} is called {nname} in the netlist and {lp.get('name')} in the library (matched by number)")
        net = str(np_.get("net") or "").strip()
        if is_hidden(lp):
            if net and not is_nc(net) and not same_name(net, lp.get("name")):
                warn.append(f"{ref}: hidden pin {num} ({lp.get('name')}) connects to net {lp.get('name')} by itself, the netlist says {net}")
            continue
        out.append((lp, net))
    return out, warn, errors


def stub_length(net):
    kind = net_kind(net)
    if kind != "label":
        return POWER_STUB
    n = int(math.ceil((len(str(net)) * CHAR + 100) / GRID)) * GRID
    return max(300, min(n, 1500))


def _stub(lp, net, dense=False):
    """What goes at one pin, in symbol coordinates: {"tip", "end", "kind", "rot"...} (kind 'nc', 'power' or 'label')."""
    ori = int(lp.get("orientation", 0)) & 3
    dx, dy = DIRECTION[ori]
    tx, ty = tip(lp)
    if is_nc(net):
        return {"kind": "nc", "tip": (tx, ty), "end": (tx, ty), "net": "NC"}
    kind = net_kind(net)
    if kind == "gnd" and dy > 0 or kind == "rail" and dy < 0 or dense:
        kind = "label"                  # a ground symbol would hang upside down, and power symbols on pins 100 mil apart sit on
                                        # top of each other: a label reads better
    n = stub_length(net) if kind == "label" else POWER_STUB
    ex, ey = tx + dx * n, ty + dy * n
    out = {"kind": "power" if kind != "label" else "label", "tip": (tx, ty), "end": (ex, ey), "net": net, "ori": ori}
    if kind == "label":
        # the text runs along the stub, so it stays off the neighbours; rotated for a vertical stub
        if dx > 0:
            out["at"], out["rot"] = (tx + 100, ty), 0
        elif dx < 0:
            out["at"], out["rot"] = (ex, ey), 0
        elif dy > 0:
            out["at"], out["rot"] = (tx, ty + 100), 1
        else:
            out["at"], out["rot"] = (ex, ey), 1
    else:
        out["style"] = GROUND_STYLE if kind == "gnd" else RAIL_STYLE
        out["rot"] = (3 if kind == "gnd" else 1) if dy == 0 else ori
    return out


def part_cell(part, symbol):
    """Everything about one part before it has a place: its pin stubs and the box (minx, miny, maxx, maxy, relative to the
    symbol origin) that holds the symbol, its stubs and their margin."""
    pins, warn, errors = pin_nets(part, symbol)
    ids = {int(p.get("part_id", 1)) for p in symbol["pins"]} - {0, -1}
    if ids - {1}:
        errors.append(f"{part['ref']}: library symbol {symbol['name']} has several parts (sub-parts {sorted(ids)}); "
                      "multi-part symbols cannot be drawn by the tool yet, draw this part by hand")
    xs, ys, stubs = [], [], []
    for lp in symbol["pins"]:
        xs += [lp["x"], tip(lp)[0]]
        ys += [lp["y"], tip(lp)[1]]
    wired = [(lp, net) for lp, net in pins if net and not is_nc(net)]
    for lp, net in pins:
        if net:
            side = int(lp.get("orientation", 0)) & 3
            across = lp["y"] if side in (0, 2) else lp["x"]
            dense = any(o is not lp and (int(o.get("orientation", 0)) & 3) == side
                        and abs((o["y"] if side in (0, 2) else o["x"]) - across) < 3 * GRID for o, _ in wired)
            s = _stub(lp, net, dense)
            s["pin"] = str(lp["number"])
            stubs.append(s)
            xs.append(s["end"][0])
            ys.append(s["end"][1])
    pad = MARGIN
    box = (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)
    open_pins = [f"{part['ref']}.{lp.get('name') or lp['number']}" for lp, net in pins if not net]
    for p in open_pins:
        warn.append(f"{p}: open pin (no net in the netlist), left undrawn")
    for s in stubs:
        for v in (s["tip"][0] % GRID, s["tip"][1] % GRID):
            if v:
                warn.append(f"{part['ref']}.{s['pin']}: the library pin is off the {GRID} mil grid")
                break
    return {"ref": part["ref"], "symbol": symbol["name"], "stubs": stubs, "box": box,
            "pins": len(symbol["pins"]), "warnings": warn, "errors": errors, "pin_nets": pins}


def _snap_up(v):
    return int(math.ceil(v / GRID)) * GRID


def layout(cells, sections, area=AREA):
    """Places the cells on a grid, section after section from the top of the sheet: each section is a heading and shelves of
    parts left to right. cells: [(section id, cell)]. Returns ({ref: (x, y)}, [(heading position, section id)], problems)."""
    x0, y0, x1, y1 = area
    pos, heads, problems = {}, [], []
    y = y1
    order = [s["id"] for s in sections] or [""]
    for sid in order:
        mine = [c for s, c in cells if s == sid]
        if not mine:
            continue
        heads.append(((x0, y - HEADER + 100), sid))
        y -= HEADER
        x, shelf_h, top = x0, 0, y
        for c in mine:
            bx0, by0, bx1, by1 = c["box"]
            w, h = bx1 - bx0, by1 - by0
            if x > x0 and x + w > x1:
                top -= shelf_h + GAP
                x, shelf_h = x0, 0
            ox, oy = _snap_up(x - bx0), _snap_up(top - by1)       # the symbol origin that puts the box's corner at (x, top)
            if ox + bx1 > x1 or oy + by0 < y0:
                problems.append(f"{c['ref']} does not fit on the sheet: split the design into more sheets")
            pos[c["ref"]] = (ox, oy)
            x = ox + bx1 + GAP
            shelf_h = max(shelf_h, h)
        y = top - shelf_h - GAP
    return pos, heads, problems


def _plain(text):
    return all(32 <= ord(ch) < 127 for ch in str(text))


def text_problems(sheet, parts, symbols):
    """Names that cannot travel to Altium (the script file is plain ASCII, fields are TAB separated): refuse before drawing."""
    bad = []
    names = [("part", p["ref"]) for p in parts] + [("net", pin.get("net") or "") for p in parts for pin in p.get("pins", [])]
    names += [("symbol", sym["name"]) for sym in symbols.values()]
    for what, text in names:
        if not _plain(text):
            bad.append(f"{what} name {str(text)!r} has a non-ASCII character, a tab or a line break: rename it (letters, digits, + - _ . / only)")
    return sorted(set(bad))


def plan_sheet(sheet, symbols, schlib, doc, replace=False):
    """Plan one netlist sheet.
    sheet: the netlist sheet dict; symbols: {ref: symbol dict from read_schlib}; schlib / doc: file paths.
    Returns {"commands": [...], "parts": [{ref, symbol, pins, x, y}], "expected": {net: [tags]}, "no_erc": [tags],
             "warnings": [...], "errors": [...]}."""
    parts = [p for p in sheet.get("parts", []) if isinstance(p, dict) and p.get("ref")]
    sections = [s for s in sheet.get("sections", []) if isinstance(s, dict) and s.get("id")]
    ids = {s["id"] for s in sections}
    first = sections[0]["id"] if sections else ""
    errors, warnings, cells = [], [], []
    for p in parts:
        sym = symbols.get(p["ref"])
        if sym is None:
            errors.append(f"{p['ref']}: no symbol in the project library (run library.build first)")
            continue
        c = part_cell(p, sym)
        warnings += c["warnings"]
        errors += c["errors"]
        cells.append((p.get("section") if p.get("section") in ids else first, c))
    errors += text_problems(sheet, parts, symbols)
    out = {"commands": [], "parts": [], "expected": {}, "no_erc": [], "warnings": warnings, "errors": errors}
    if errors:
        return out
    pos, heads, problems = layout(cells, sections)
    errors += problems
    if errors:
        return out
    d = str(doc)
    cmds = [("DRAWBEGIN", d, "1" if replace else "0")]
    titles = {s["id"]: s.get("title") or "" for s in sections}
    head_names = {}
    for n, s_ in enumerate(sections, 1):        # section headings are cosmetic: a non-ASCII one is drawn as "Section N" / without its title
        if not _plain(s_["id"]) or not _plain(titles[s_["id"]]):
            warnings.append(f"section {n}: the heading has non-ASCII characters and is drawn as 'Section {n}'")
            titles[s_["id"]] = ""
            head_names[s_["id"]] = f"Section {n}"
    for (hx, hy), sid in heads:
        if sid:
            label = head_names.get(sid, sid)
            cmds.append(("FRAME", d, str(hx), str(hy - 100), "4500", str(HEADER - 100), f"{TAG} {label} - {titles.get(sid, '')}".strip(" -")))
    for _, c in cells:
        ox, oy = pos[c["ref"]]
        cmds.append(("PLACE", d, c["ref"], c["symbol"], str(schlib), str(ox), str(oy), str(c["pins"])))
        out["parts"].append({"ref": c["ref"], "symbol": c["symbol"], "pins": c["pins"], "x": ox, "y": oy})
        for s in c["stubs"]:
            tx, ty = ox + s["tip"][0], oy + s["tip"][1]
            tag = f"{c['ref']}-{s['pin']}"
            if s["kind"] == "nc":
                cmds.append(("NOERC", d, str(tx), str(ty)))
                out["no_erc"].append(tag)
                continue
            ex, ey = ox + s["end"][0], oy + s["end"][1]
            cmds.append(("WIRE", d, str(tx), str(ty), str(ex), str(ey)))
            if s["kind"] == "power":
                cmds.append(("POWER", d, str(ex), str(ey), str(s["rot"]), str(s["style"]), s["net"]))
            else:
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
