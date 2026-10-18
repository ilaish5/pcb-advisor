"""
Render one schematic sheet from its netlist, in the "short stubs + net labels"
style: every pin gets a short wire ending in a power bar, a GND symbol, a net
label or a No-ERC cross. The student redraws the sheet in Altium from this.

    python scripts/skills/render_sheet.py <project> <sheet>      -> artifacts/sheet-<sheet>.svg

The picture is derived: it is drawn from netlist/<sheet>.json and the BOM, so
changing an MPN in the BOM changes the label here, with nothing to keep in step.
Classes (.sch .body .net .pwr ...) are styled by the page, not by this file.

netlist/<sheet>.json
    {"id": "03", "title": "Modem",
     "sections": [{"id": "A", "title": "U4 modem"}],
     "parts": [{"ref": "U4", "section": "A", "kind": "ic",
                "pins": [{"name": "VBAT", "num": "55", "net": "+3V8", "side": "left"}]}],
     "notes": [{"section": "A", "text": "Every GND pin gets its own symbol."}]}
kind: ic (default for 4+ pins) | res | cap | tvs | diode | tp | q (3 pins) | conn
Pins of an ic go to "side" left/right, else alternate left/right in order.
Two-pin parts: pins[0] is the top (or left) end, pins[1] the bottom (or right) end.
"""
import html
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import store      # noqa: E402
import workspace  # noqa: E402

CW = 5.9            # estimated width of one monospace label character
PITCH = 26


def esc(s):
    return html.escape(str(s), quote=True)


def T(x, y, s, c="", a="start"):
    return f'<text x="{x:g}" y="{y:g}" class="{c}" text-anchor="{a}">{esc(s)}</text>'


def L(x1, y1, x2, y2, c="w"):
    return f'<line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" class="{c}"/>'


def is_power(net):
    return net.startswith("+")


def gnd_down(x, y):
    return (L(x, y, x, y + 6) + L(x - 9, y + 6, x + 9, y + 6, "g") + L(x - 6, y + 10, x + 6, y + 10, "g")
            + L(x - 3, y + 14, x + 3, y + 14, "g") + T(x, y + 24, "GND", "gt", "middle"))


def gnd_side(x, y, d):
    return (L(x, y - 8, x, y + 8, "g") + L(x + d * 4, y - 5, x + d * 4, y + 5, "g")
            + L(x + d * 8, y - 2, x + d * 8, y + 2, "g") + T(x + d * 12, y + 3, "GND", "gt", "end" if d < 0 else "start"))


def net_end(x, y, net, d):
    """What a pin stub ends in, to the left (d=-1) or right (d=+1) of (x,y)."""
    if net == "NC":
        return (L(x - 4, y - 4, x + 4, y + 4, "nc") + L(x - 4, y + 4, x + 4, y - 4, "nc")
                + T(x + d * 8, y + 3, "No ERC", "nct", "end" if d < 0 else "start"))
    if net == "GND":
        return gnd_side(x, y, d)
    if is_power(net):
        g = net == "+3V3"
        return L(x, y - 7, x, y + 7, "pb3" if g else "pb") + T(x + d * 5, y + 4, net, "pwr3" if g else "pwr", "end" if d < 0 else "start")
    tw = len(net) * CW + 4
    return L(x, y, x + d * tw, y) + T(x + d * 2, y - 3, net, "net", "end" if d < 0 else "start")


def net_top(x, y, net):
    """A vertical pin end above a part: power bar, GND, or a boxed label."""
    if net == "GND":
        return gnd_down(x, y - 14) + ""
    if is_power(net):
        g = net == "+3V3"
        return L(x - 9, y, x + 9, y, "pb3" if g else "pb") + T(x, y - 6, net, "pwr3" if g else "pwr", "middle")
    w = len(net) * CW + 10
    return (f'<rect x="{x - w / 2:g}" y="{y - 16:g}" width="{w:g}" height="15" rx="3" class="nbox"/>'
            + T(x, y - 5, net, "net", "middle") + L(x, y - 1, x, y))


def net_width(net):
    return 0 if net in ("GND",) else len(net) * CW + 12


def label_w(net):
    if net == "NC":
        return 58
    if net == "GND":
        return 40
    return len(net) * CW + 8


# ---------------------------------------------------------------- parts
# every part returns (svg, width, height) with its own origin at (0, 0)

def zig(x, y, horiz):
    pts = [(0, 0)] + [(3 + i * 6, 5 if i % 2 else -5) for i in range(6)] + [(36, 0)]
    return '<polyline class="w" points="' + " ".join(
        f"{x + a:g},{y + b:g}" if horiz else f"{x + b:g},{y + a:g}" for a, b in pts) + '"/>'


def part_ic(p, sub):
    pins = p["pins"]
    left = [q for q in pins if q.get("side") == "left"]
    right = [q for q in pins if q.get("side") == "right"]
    rest = [q for q in pins if q.get("side") not in ("left", "right")]
    for i, q in enumerate(rest):          # alternate; the first half left, the rest right
        (left if i < (len(rest) + 1) // 2 else right).append(q)
    n = max(len(left), len(right), 1)
    h = n * PITCH + 12
    name_w = lambda ps: max([len(q.get("name", "")) for q in ps] + [3]) * CW
    bw = max(110, name_w(left) + name_w(right) + 36)
    lw = max([label_w(q["net"]) for q in left] + [0]) + 30
    rw = max([label_w(q["net"]) for q in right] + [0]) + 30
    x0, y0 = lw, 18
    s = f'<rect x="{x0:g}" y="{y0}" width="{bw:g}" height="{h}" class="body"/>'
    s += T(x0, y0 - 6, p["ref"], "refd") + T(x0, y0 + h + 14, sub, "mpn")
    for i, q in enumerate(left):
        py = y0 + PITCH * i + PITCH / 2 + 6
        s += L(x0 - 30, py, x0, py, "pin") + T(x0 - 4, py - 3, q.get("num", ""), "pnum", "end")
        s += T(x0 + 5, py + 3.5, q.get("name", ""), "pname") + net_end(x0 - 30, py, q["net"], -1)
    for i, q in enumerate(right):
        py = y0 + PITCH * i + PITCH / 2 + 6
        s += L(x0 + bw, py, x0 + bw + 30, py, "pin") + T(x0 + bw + 4, py - 3, q.get("num", ""), "pnum")
        s += T(x0 + bw - 5, py + 3.5, q.get("name", ""), "pname", "end") + net_end(x0 + bw + 30, py, q["net"], 1)
    return s, lw + bw + rw, y0 + h + 24


def part_vertical(p, value, kind):
    a, b = p["pins"][0], p["pins"][1]
    cx, top = 60, 22
    s = ""
    if kind == "cap":
        s += net_top(cx, top, a["net"]) if a["net"] != "GND" else ""
        s += L(cx, top, cx, top + 30) + L(cx - 11, top + 30, cx + 11, top + 30) + L(cx - 11, top + 36, cx + 11, top + 36)
        s += L(cx, top + 36, cx, top + 60)
    elif kind in ("tvs", "diode"):
        s += net_top(cx, top, a["net"])
        s += L(cx, top, cx, top + 14) + f'<polygon points="{cx - 8},{top + 14} {cx + 8},{top + 14} {cx},{top + 28}" class="w"/>'
        s += L(cx - 8, top + 28, cx + 8, top + 28)
        if kind == "tvs":
            s += L(cx - 8, top + 28, cx - 11, top + 24) + L(cx + 8, top + 28, cx + 11, top + 32)
        s += L(cx, top + 28, cx, top + 60)
    else:                                           # generic two-pin: a resistor, vertical
        s += net_top(cx, top, a["net"])
        s += L(cx, top, cx, top + 12) + zig(cx, top + 12, False) + L(cx, top + 48, cx, top + 60)
    end = b["net"]
    if end == "GND":
        s += gnd_down(cx, top + 60)
    elif is_power(end):
        s += net_top(cx, top + 60, end).replace(f'y="{top + 60 - 16}"', f'y="{top + 60 + 1}"')
    elif end == "NC":
        s += net_end(cx, top + 60, "NC", 1)
    else:
        s += T(cx, top + 76, end, "net", "middle")
    s += T(cx - 16, top + 31, p["ref"], "refs", "end") + T(cx - 16, top + 43, value or "", "refs", "end")
    return s, 120, top + 96


def part_res_h(p, value):
    a, b = p["pins"][0], p["pins"][1]
    lw, rw = label_w(a["net"]) , label_w(b["net"])
    x = lw + 6
    s = zig(x, 30, True) + T(x + 18, 20, f'{p["ref"]} {value or ""}', "refs", "middle")
    s += L(x - 6, 30, x, 30) + net_end(x - 6, 30, a["net"], -1)
    s += L(x + 36, 30, x + 42, 30) + net_end(x + 42, 30, b["net"], 1)
    return s, x + 42 + rw + 6, 52


def part_tp(p):
    net = p["pins"][0]["net"]
    s = f'<circle cx="12" cy="24" r="5.5" class="tpc"/>' + T(22, 22, p["ref"], "refd")
    if net == "GND":
        s += L(12, 29.5, 12, 38) + gnd_down(12, 38)
        return s, 80, 74
    s += T(22, 35, net, "net")
    return s, max(80, 26 + len(net) * CW), 44


def part_conn(p, sub):
    # a connector is a one-sided IC
    pins = [dict(q, side="left") for q in p["pins"]]
    return part_ic(dict(p, pins=pins), sub)


def render_part(p, line, bom_line):
    ref = p["ref"]
    kind = p.get("kind") or ("ic" if len(p["pins"]) > 3 else "res" if len(p["pins"]) == 2 else "q")
    value = (bom_line or {}).get("value") or p.get("value") or ""
    sub = (bom_line or {}).get("mpn") or p.get("label") or value
    if kind == "tp":
        body = part_tp(p)
    elif kind in ("cap", "tvs", "diode") and len(p["pins"]) == 2:
        body = part_vertical(p, value if kind != "tvs" else (sub or value), kind)
    elif kind == "res" and len(p["pins"]) == 2:
        body = part_res_h(p, value)
    elif kind == "conn":
        body = part_conn(p, sub)
    else:
        body = part_ic(p, sub)
    svg, w, h = body
    if p.get("pins_source") == "agent":
        svg += (f'<g class="unv"><title>Pins from the agent; add the datasheet to verify</title>'
                f'<text x="{max(w - 4, 0):g}" y="-2" text-anchor="end" font-size="9" fill="#b7791f" '
                f'font-style="italic">unverified</text></g>')
    if (bom_line or {}).get("dnp") or p.get("dnp"):
        svg = f'<g class="dnp">{svg}</g>'
    return svg, w, h


# ---------------------------------------------------------------- layout

def layout_section(sec, parts, notes, bom_by_ref):
    """Flow a section's parts: ICs first (one per row), then the small parts in rows."""
    rendered = [(p, *render_part(p, None, bom_by_ref.get(p["ref"]))) for p in parts]
    ics = [r for r in rendered if r[0].get("kind") in ("ic", "conn", "q") or (not r[0].get("kind") and len(r[0]["pins"]) > 2)]
    small = [r for r in rendered if r not in ics]
    inner = max([r[2] for r in ics] + [440])
    pad, y = 14, 34
    out = []
    for p, svg, w, h in ics:
        out.append((p, svg, pad, y))
        y += h + 8
    x, row_h = pad, 0
    for p, svg, w, h in small:
        if x + w > inner + pad and x > pad:
            y += row_h + 6
            x, row_h = pad, 0
        out.append((p, svg, x, y))
        x += w + 8
        row_h = max(row_h, h)
    y += row_h + 8
    note_svg = ""
    for n in notes:
        note_svg += T(pad, y + 6, n["text"], "note")
        y += 14
    w_total, h_total = inner + 2 * pad, y + 10
    body = ""
    for p, svg, px, py in out:
        body += f'<g class="part" data-ref="{esc(p["ref"])}" transform="translate({px:g},{py:g})">{svg}</g>'
    box = (f'<rect x="0" y="0" width="{w_total:g}" height="{h_total:g}" rx="8" class="secr"/>'
           + T(12, 20, f'{sec["id"]}. {sec.get("title", "")}', "sect"))
    return box + body + note_svg, w_total, h_total


def render_sheet(sheet, bom_lines):
    bom_by_ref = {r: l for l in bom_lines for r in l.get("refs", [])}
    secs = sheet.get("sections") or [{"id": "", "title": ""}]
    blocks = []
    for sec in secs:
        parts = [p for p in sheet.get("parts", []) if (p.get("section") or secs[0]["id"]) == sec["id"]]
        # a note may be a plain string: it belongs to the first section
        notes = [n if isinstance(n, dict) else {"section": secs[0]["id"], "text": str(n)} for n in sheet.get("notes", [])]
        notes = [n for n in notes if n.get("section", secs[0]["id"]) == sec["id"]]
        if parts or notes:
            blocks.append(layout_section(sec, parts, notes, bom_by_ref))
    ncols = 1 if len(blocks) <= 1 else 2 if len(blocks) <= 4 else 3
    cols = [[] for _ in range(ncols)]
    heights = [0] * ncols
    for b in blocks:
        i = heights.index(min(heights))
        cols[i].append(b)
        heights[i] += b[2] + 14
    x, pieces, total_h = 10, [], 0
    for col in cols:
        y, cw = 40, max([b[1] for b in col] + [0])
        for svg, w, h in col:
            pieces.append(f'<g transform="translate({x:g},{y:g})">{svg}</g>')
            y += h + 14
        total_h = max(total_h, y)
        x += cw + 14
    width = max(x, 400)
    head = T(14, 24, f'Sheet {sheet.get("id", "")} {sheet.get("title", "")}'.strip(), "title") + \
        T(14 + 10 * len(f'Sheet {sheet.get("id", "")} {sheet.get("title", "")}') + 12, 24,
          "rendered from the netlist · short stubs + labels", "note")
    return (f'<svg class="sch" id="sch" viewBox="0 0 {width:g} {total_h:g}" xmlns="http://www.w3.org/2000/svg" '
            f'role="img" aria-label="Sheet {esc(sheet.get("id", ""))}">{head}{"".join(pieces)}</svg>')


def render(project, sheet_id, write=True):
    sheet = store.load_sheet(project, sheet_id)
    if not sheet:
        try:
            import preview_sch
            import project as project_mod
            link = project_mod.altium_link(project)
            if link.get("project_file"):
                svg = preview_sch.render_project_sch(project, sheet=sheet_id)
                if svg and not svg.startswith('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 100">'):
                    if write:
                        out = store.pdir(project) / "artifacts" / f"sheet-{sheet_id}.svg"
                        out.parent.mkdir(parents=True, exist_ok=True)
                        out.write_text(svg, encoding="utf-8")
                    return svg
        except Exception:
            pass
        raise SystemExit(f"no sheet {sheet_id!r} in {project}")
    svg = render_sheet(sheet, store.bom(project, write=False))
    if write:
        out = store.pdir(project) / "artifacts" / f"sheet-{sheet['id']}.svg"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(svg, encoding="utf-8")
    return svg


if __name__ == "__main__":
    import oscompat
    oscompat.utf8_stdio()
    if len(sys.argv) < 3:
        raise SystemExit("usage: render_sheet.py <project> <sheet>")
    render(sys.argv[1], sys.argv[2])
    print(f"wrote projects/{sys.argv[1]}/artifacts/sheet-{sys.argv[2]}.svg")
