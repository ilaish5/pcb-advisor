"""Schematic preview: renders an Altium SchDoc to SVG.

Draws each component the way the sheet stores it: the body drawing, pins that run out of the body to their
connection point (the name inside the body, the number beside the line), the designator and the comment where
the designer put them, plus wires, net labels, power ports and ports. Supports clicking on parts or nets with
data-ref and data-net attributes.

Usage:
    python scripts/preview_sch.py <path_or_project> [--sheet <sheet>] [--output <out.svg>]
"""
import argparse
import html
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from altium.schdoc import pin_tip, read_schdoc
import project as project_mod
import workspace


def esc(s: str) -> str:
    return html.escape(str(s or ""), quote=True)


# Selector every rule below is scoped to: this renderer's own SVG (class "sch" + data-render="schdoc"), so the
# inlined <style> cannot touch the netlist renderer's SVG (skills/render_sheet.py, styled by ui/styles/previews.css)
# or anything else on the page. "&" stands for the scope.
SCOPE = 'svg.sch[data-render="schdoc"]'

# Colours are the page's tokens (ui/styles/base.css) with the light-theme value as fallback, so the picture
# follows the theme in the page and still draws when the SVG file is opened on its own. Text sizes are not here:
# every text carries its own size, worked out from the sheet's font (see font_px).
_CSS = """
& { font-family: var(--f-mono, "IBM Plex Mono", ui-monospace, monospace); }
& .sch-bg { fill: var(--sch-bg, #fbfcfe); }
& .sch-title { font-family: var(--f-ui, sans-serif); font-size: 14px; font-weight: 700; fill: var(--ink-3, #7d889b); }
& text { fill: var(--sch-text, #151515); }
& .refd { font-weight: 700; }
& .mpn { fill: var(--ink-3, #5b667b); }
& .pnum { fill: var(--ink-3, #888888); }
& .pname { font-weight: 600; }
& .w { stroke: var(--sch-wire, #233f99); stroke-width: 1.6; fill: none; stroke-linecap: round; stroke-linejoin: round; }
& .pin { stroke: var(--sch-text, #333333); stroke-width: 1.4; }
& .body { fill: var(--sch-body, #fdf2c8); stroke: var(--sch-body-line, #7d2f14); stroke-width: 1.5; }
& .sym { fill: none; stroke: var(--sch-body-line, #7d2f14); stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round; }
& .sym.solid { fill: var(--sch-body, #fdf2c8); }
& .jn { fill: var(--sch-wire, #233f99); }
& .pin-tip { fill: var(--sch-wire, #233f99); opacity: 0; }
& .part:hover .pin-tip { opacity: 0.8; }
& .part { cursor: pointer; }
& .hlbox { fill: transparent; stroke: none; }
& .part:hover .hlbox { fill: var(--hover, rgba(33, 72, 201, 0.08)); stroke: var(--sig-line, rgba(33, 72, 201, 0.3)); stroke-width: 1; }
& .part.sel .hlbox, & .part:focus-visible .hlbox { fill: var(--sig-soft, rgba(33, 72, 201, 0.15)); stroke: var(--sig, #2148c9); stroke-width: 1.8; }
& .part:focus-visible { outline: none; }
&.focus .part:not(.sel) { opacity: 0.3; }
& .net-label, & .power-port, & .port { cursor: pointer; }
& .net-label rect { fill: var(--net-soft, #f0e7fb); stroke: var(--net, #6b2fb3); stroke-width: 0.8; }
& .net-label text { font-weight: 600; fill: var(--net, #6b2fb3); }
& .power-port text { font-weight: 700; fill: var(--sch-pwr, #d27a12); }
& .power-port .hit { fill: transparent; stroke: none; }
& .pb { stroke: var(--sch-pwr, #d27a12); stroke-width: 2.2; fill: none; stroke-linecap: round; }
& .port-poly { fill: var(--ok-soft, #e1f2e8); stroke: var(--ok, #167a46); stroke-width: 1.2; }
& .port text { font-weight: 600; fill: var(--ok, #167a46); }
& .hl-net rect, & .hl-net polygon { stroke: var(--net, #6b2fb3); stroke-width: 2.4; }
& .hl-net text { font-weight: 800; }
&.netfocus [data-net]:not(.hl-net) { opacity: 0.35; }
& .net-label:focus-visible, & .power-port:focus-visible, & .port:focus-visible { outline: none; }
& .net-label:focus-visible rect, & .port:focus-visible polygon { stroke: var(--sig, #2148c9); stroke-width: 2; }
"""


def scoped_css() -> str:
    """The renderer's stylesheet with every rule scoped to SCOPE (see above)."""
    return "\n".join(
        line.replace("&", SCOPE) if line.startswith("&") or ", &" in line else line
        for line in _CSS.strip().splitlines()
    )


# Geometry. A SchDoc coordinate is 10 mil, so the 100 mil grid and the usual pin pitch are 10 units. SCALE turns a
# unit into SVG px: at 2 px a unit the pitch is 20 px, room for one line of text (cap height about 10 px) per pin.
# The sheet's font size (10 for the default font) times 0.7 is the em in px per unit of SCALE; the monospaced face
# is 0.6 em wide and its capitals 0.7 em high.
SCALE = 2.0
FONT_EM = 0.7
CHAR_W = 0.6
CAP_H = 0.7
NAME_GAP = 5 * SCALE       # pin name: from the body edge inward
NUM_GAP = 2 * SCALE        # pin number: from the body edge along the pin
LABEL_PAD = 3.0            # net label box: space above and beside the text (below it the box takes 4: the underscore hangs there)
STUB = 10 * SCALE          # power port: connection point to the bar
BAR = 5 * SCALE            # power port: half the bar
QUARTER = {0: (1, 0), 1: (0, -1), 2: (-1, 0), 3: (0, 1)}   # PIN_DIRECTION in SVG px (y points down)


def _px(x) -> float:
    return x * SCALE


def _py(y) -> float:
    return -y * SCALE


def font_px(fonts: dict, font_id, factor: float = 1.0) -> float:
    """Em size in px for a font id of the sheet's font table (size 10 when the id or the table is missing)."""
    size = (fonts.get(font_id) or {}).get("size", 10)
    return round(size * SCALE * FONT_EM * factor, 1)


def _rotate(dx, dy, quarters):
    """An offset turned anticlockwise on the screen by whole quarter turns."""
    for _ in range(quarters & 3):
        dx, dy = dy, -dx
    return dx, dy


def text_box(x, y, s: str, px: float, just: int = 0, orient: int = 0):
    """The box (x0, y0, x1, y1, SVG px) a text of em size px takes. (x, y) is the anchor, just the Altium
    justification (0 bottom-left, 1 bottom-centre, 2 bottom-right, 3-5 centred on the line, 6-8 hanging from it),
    orient the quarter turns anticlockwise. The same rule places the <text> in _text_svg."""
    w, h = len(s) * CHAR_W * px, CAP_H * px
    hj, vj = just % 3, (just % 9) // 3
    x0, y0 = -hj * w / 2, (vj - 2) * h / 2
    corners = [_rotate(cx, cy, orient) for cx in (x0, x0 + w) for cy in (y0, y0 + h)]
    return (x + min(c[0] for c in corners), y + min(c[1] for c in corners),
            x + max(c[0] for c in corners), y + max(c[1] for c in corners))


class _Bounds:
    """The extent of what is drawn, in SVG px."""

    def __init__(self):
        self.x0 = self.y0 = float("inf")
        self.x1 = self.y1 = float("-inf")

    def add(self, x, y):
        self.x0, self.x1 = min(self.x0, x), max(self.x1, x)
        self.y0, self.y1 = min(self.y0, y), max(self.y1, y)

    def add_box(self, box):
        self.add(box[0], box[1])
        self.add(box[2], box[3])

    def __bool__(self):
        return self.x0 <= self.x1


def _text_svg(x, y, s: str, px: float, cls: str, just: int = 0, orient: int = 0, bounds: "_Bounds" = None) -> str:
    """A <text> anchored at (x, y) by the rule of text_box."""
    if bounds is not None:
        bounds.add_box(text_box(x, y, s, px, just, orient))
    hj, vj = just % 3, (just % 9) // 3
    base = y + vj * CAP_H * px / 2
    turn = f' transform="rotate({-90 * (orient & 3)} {x:.1f} {y:.1f})"' if orient & 3 else ""
    klass = f' class="{cls}"' if cls else ""
    anchor = ("start", "middle", "end")[hj]
    return f'<text{klass} x="{x:.1f}" y="{base:.1f}" text-anchor="{anchor}" style="font-size:{px:g}px"{turn}>{esc(s)}</text>'


def _pin_svg(p: dict, ref: str, name_px: float, num_px: float, bounds: _Bounds) -> str:
    """A pin: the line from the body edge (the stored location) to the connection point, the number beside the
    line if the pin shows it, the name inside the body if it shows that."""
    bx, by = _px(p.get("x", 0)), _py(p.get("y", 0))
    tx, ty = pin_tip(p)
    tx, ty = _px(tx), _py(ty)
    dx, dy = QUARTER[p.get("orientation", 0) & 3]
    bounds.add(bx, by)
    bounds.add(tx, ty)
    out = [f'<line class="pin" x1="{bx:.1f}" y1="{by:.1f}" x2="{tx:.1f}" y2="{ty:.1f}"/>',
           f'<circle class="pin-tip" cx="{tx:.1f}" cy="{ty:.1f}" r="3" data-ref="{esc(ref)}" data-pin="{esc(p.get("number", ""))}"/>']
    num = str(p.get("number", ""))
    if p.get("show_number", True) and num:
        if dx:      # beside a horizontal pin: above the line, starting at the body edge
            out.append(_text_svg(bx + dx * NUM_GAP, by - 4, num, num_px, "pnum", 0 if dx > 0 else 2, 0, bounds))
        else:       # beside a vertical pin: left of the line, turned to read along it
            out.append(_text_svg(bx - 4, by + dy * NUM_GAP, num, num_px, "pnum", 0 if dy < 0 else 2, 1, bounds))
    # Clean escaped slashes in inverted pin names like T\X\0\ -> TX0
    name = str(p.get("name", "")).replace("\\", "")
    if p.get("show_name", True) and name and name != "~":
        if dx:      # inside the body, centred on the pin's line
            out.append(_text_svg(bx - dx * NAME_GAP, by, name, name_px, "pname", 5 if dx > 0 else 3, 0, bounds))
        else:       # inside the body, turned to read along the pin
            out.append(_text_svg(bx, by - dy * NAME_GAP, name, name_px, "pname", 5 if dy < 0 else 3, 1, bounds))
    return "".join(out)


def _graphic_svg(g: dict, bounds: _Bounds, fonts: dict) -> str:
    """One primitive of a component body."""
    kind = g.get("kind")
    if kind == "rect":
        x1, y1, x2, y2 = _px(g["x1"]), _py(g["y1"]), _px(g["x2"]), _py(g["y2"])
        x, y, w, h = min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1)
        bounds.add(x, y)
        bounds.add(x + w, y + h)
        return f'<rect class="{"body" if g.get("solid") else "sym"}" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}"/>'
    if kind in ("polyline", "polygon"):
        pts = [(_px(x), _py(y)) for x, y in g.get("points", [])]
        for x, y in pts:
            bounds.add(x, y)
        if len(pts) < 2:
            return ""
        tag = "polygon" if kind == "polygon" else "polyline"
        cls = "sym solid" if kind == "polygon" and g.get("solid") else "sym"
        return f'<{tag} class="{cls}" points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}"/>'
    if kind == "arc":
        cx, cy, r = _px(g["x"]), _py(g["y"]), g["radius"] * SCALE
        bounds.add(cx - r, cy - r)
        bounds.add(cx + r, cy + r)
        start, end = g.get("start", 0.0), g.get("end", 360.0)
        sweep = (end - start) % 360
        if sweep == 0:
            return f'<circle class="sym" cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}"/>'
        x1, y1 = cx + r * math.cos(math.radians(start)), cy - r * math.sin(math.radians(start))
        x2, y2 = cx + r * math.cos(math.radians(end)), cy - r * math.sin(math.radians(end))
        return f'<path class="sym" d="M{x1:.1f} {y1:.1f}A{r:.1f} {r:.1f} 0 {int(sweep > 180)} 0 {x2:.1f} {y2:.1f}"/>'
    if kind == "text" and g.get("text"):
        return _text_svg(_px(g["x"]), _py(g["y"]), g["text"], font_px(fonts, g.get("font", 1)), "mpn",
                         g.get("justification", 0), g.get("orientation", 0), bounds)
    return ""


def _fallback_body(pins: list) -> tuple:
    """A body rectangle (x0, y0, x1, y1, units) for a component without a drawing: it spans the pins' body ends,
    half a pitch beyond the outer pins, and is never thinner than 8 units."""
    xs, ys = [p.get("x", 0) for p in pins], [p.get("y", 0) for p in pins]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if any((p.get("orientation", 0) & 3) in (0, 2) for p in pins):
        y0, y1 = y0 - 5, y1 + 5
    else:
        x0, x1 = x0 - 5, x1 + 5
    if x1 - x0 < 8:
        x0, x1 = (x0 + x1) / 2 - 4, (x0 + x1) / 2 + 4
    if y1 - y0 < 8:
        y0, y1 = (y0 + y1) / 2 - 4, (y0 + y1) / 2 + 4
    return x0, y0, x1, y1


def _part_svg(comp: dict, fonts: dict, sys_font: int, bounds: _Bounds) -> str:
    """One component: highlight box, body drawing, pins, designator and comment."""
    ref = comp.get("ref", "")
    cur = comp.get("current_part_id", 1)
    pins = [p for p in comp.get("pins", []) if not p.get("hidden") and p.get("part_id", cur) in (cur, -1, 0)]
    gfx = [g for g in comp.get("graphics", []) if g.get("part_id", cur) in (cur, -1, 0)]
    own = _Bounds()     # body and pins: what the highlight box surrounds
    body = [_graphic_svg(g, own, fonts) for g in gfx if g.get("kind") != "text"]
    if not any(body):
        if pins:
            x0, y0, x1, y1 = _fallback_body(pins)
        else:
            x0, y0, x1, y1 = comp.get("x", 0) - 25, comp.get("y", 0) - 25, comp.get("x", 0) + 25, comp.get("y", 0) + 25
        body = [_graphic_svg({"kind": "rect", "x1": x0, "y1": y0, "x2": x1, "y2": y1, "solid": True}, own, fonts)]
    name_px, num_px = font_px(fonts, sys_font), font_px(fonts, sys_font, 0.85)
    inner = [_graphic_svg(g, bounds, fonts) for g in gfx if g.get("kind") == "text"]
    inner += [_pin_svg(p, ref, name_px, num_px, own) for p in pins]
    bounds.add_box((own.x0, own.y0, own.x1, own.y1))

    # Designator and comment: where the sheet stores them, else above and below the body
    des, com = comp.get("designator_text"), comp.get("comment_text")
    labels = []
    if ref and not (des or {}).get("hidden"):
        labels.append((ref, des, "refd", 0, (own.x0, own.y0 - 4)))
    sub = com.get("text", "") if com else (comp.get("comment") or comp.get("lib_ref") or "")
    if sub.startswith("=") and comp.get("params", {}).get(sub[1:]):     # "=Value": the part's parameter of that name
        sub = comp["params"][sub[1:]]
    if sub and not (com or {}).get("hidden"):
        labels.append((sub[:32], com, "mpn", 6, (own.x0, own.y1 + 4)))
    for text, st, cls, just, anchor in labels:
        if st:
            inner.append(_text_svg(_px(st["x"]), _py(st["y"]), text, font_px(fonts, st.get("font", 1)), cls,
                                   st.get("justification", 0), st.get("orientation", 0), bounds))
        else:
            inner.append(_text_svg(*anchor, text, font_px(fonts, 1), cls, just, 0, bounds))

    box = (f'<rect class="hlbox" x="{own.x0 - 6:.1f}" y="{own.y0 - 6:.1f}" width="{own.x1 - own.x0 + 12:.1f}" '
           f'height="{own.y1 - own.y0 + 12:.1f}" rx="5"/>')
    return (f'<g class="part" data-ref="{esc(ref)}" id="part-{esc(ref)}" cursor="pointer" tabindex="0">'
            + box + "".join(body) + "".join(inner) + "</g>")


def _net_label_svg(nl: dict, fonts: dict, bounds: _Bounds) -> str:
    """A net label: its box sits on the wire it names (the label's location is the wire end), a vertical one
    turned to read upward. The box is shorter than the 100 mil pin pitch, so labels on neighbouring pins never meet."""
    text = nl.get("text") or nl.get("name", "")
    px = font_px(fonts, nl.get("font", 1))
    x, y = _px(nl.get("x", 0)), _py(nl.get("y", 0))
    w = len(text) * CHAR_W * px + 2 * LABEL_PAD
    h = CAP_H * px + LABEL_PAD + 4
    quarters = nl.get("orientation", 0) & 1
    for cx, cy in ((0, -1.5), (w, -1.5 - h)):
        dx, dy = _rotate(cx, cy, quarters)
        bounds.add(x + dx, y + dy)
    turn = f' transform="rotate(-90 {x:.1f} {y:.1f})"' if quarters else ""
    return (f'<g class="net-label" data-net="{esc(text)}" tabindex="0"{turn}>'
            f'<rect x="{x:.1f}" y="{y - 1.5 - h:.1f}" width="{w:.1f}" height="{h:.1f}" rx="2"/>'
            f'<text x="{x + LABEL_PAD:.1f}" y="{y - 1.5 - 4:.1f}" style="font-size:{px:g}px">{esc(text)}</text></g>')


def _power_port_svg(pp: dict, fonts: dict, bounds: _Bounds) -> str:
    """A power port: a stub out of the connection point in the way the port points, then a bar (ground symbols: three
    bars), then the net name when the port shows it."""
    text = pp.get("text") or pp.get("name", "")
    px = font_px(fonts, pp.get("font", 1))
    x, y = _px(pp.get("x", 0)), _py(pp.get("y", 0))
    dx, dy = QUARTER[pp.get("orientation", 0) & 3]
    nx, ny = -dy, dx            # along the bar
    ground = pp.get("style", 0) in (4, 5, 6)
    bars = [(STUB, BAR), (STUB + 0.25 * STUB, BAR * 0.6), (STUB + 0.5 * STUB, BAR * 0.2)] if ground else [(STUB, BAR)]
    d = [f"M{x:.1f} {y:.1f}L{x + dx * STUB:.1f} {y + dy * STUB:.1f}"]
    for along, half in bars:
        cx, cy = x + dx * along, y + dy * along
        d.append(f"M{cx - nx * half:.1f} {cy - ny * half:.1f}L{cx + nx * half:.1f} {cy + ny * half:.1f}")
    reach = bars[-1][0]
    bounds.add(x, y)
    bounds.add(x + dx * reach + nx * BAR, y + dy * reach + ny * BAR)
    bounds.add(x + dx * reach - nx * BAR, y + dy * reach - ny * BAR)
    label = ""
    if pp.get("show_name", not ground) and text:
        just = {0: 3, 1: 1, 2: 5, 3: 7}[pp.get("orientation", 0) & 3]
        label = _text_svg(x + dx * (reach + 3), y + dy * (reach + 3), text, px, "pwr", just, 0, bounds)
    hit = (f'<rect class="hit" x="{min(x, x + dx * reach) - BAR:.1f}" y="{min(y, y + dy * reach) - BAR:.1f}" '
           f'width="{abs(dx * reach) + 2 * BAR:.1f}" height="{abs(dy * reach) + 2 * BAR:.1f}"/>')
    return (f'<g class="power-port" data-net="{esc(text)}" tabindex="0"><title>{esc(text)}</title>{hit}'
            f'<path class="pb" d="{"".join(d)}"/>{label}</g>')


def render_schdoc(doc_or_path, title: str = None, write: bool = False, out_path: str = None) -> str:
    """Render a parsed SchDoc dict or a .SchDoc file path to SVG string."""
    if isinstance(doc_or_path, (str, pathlib.Path)):
        p = pathlib.Path(doc_or_path)
        doc = read_schdoc(p)
        doc_name = p.stem
    else:
        doc = doc_or_path
        doc_name = doc.get("file", "Schematic")

    sheet_title = title or doc.get("file") or doc_name
    fonts = doc.get("fonts", {})
    sys_font = doc.get("system_font", 1)
    bounds = _Bounds()

    # Coordinate mapping: Altium Y increases upwards; SVG Y increases downwards. Everything is drawn at SCALE px a
    # unit in that frame, and the viewBox starts where the drawing does.
    parts = []

    # 1. Wires
    parts.append('<g class="wires">')
    for w in doc.get("wires", []):
        pts = w.get("points", [])
        if len(pts) >= 2:
            for x, y in pts:
                bounds.add(_px(x), _py(y))
            pts_str = " ".join(f"{_px(x):.1f},{_py(y):.1f}" for x, y in pts)
            parts.append(f'<polyline class="w" points="{pts_str}"/>')
    parts.append('</g>')

    # 2. Components
    parts.append('<g class="components">')
    for comp in doc.get("components", []):
        parts.append(_part_svg(comp, fonts, sys_font, bounds))
    parts.append('</g>')

    # 3. Junctions (over the pins, whose connection points they mark)
    parts.append('<g class="junctions">')
    for j in doc.get("junctions", []):
        jx, jy = _px(j.get("x", 0)), _py(j.get("y", 0))
        bounds.add(jx, jy)
        parts.append(f'<circle cx="{jx:.1f}" cy="{jy:.1f}" r="3.5" class="jn"/>')
    parts.append('</g>')

    # 4. Net labels
    parts.append('<g class="net-labels">')
    parts.extend(_net_label_svg(nl, fonts, bounds) for nl in doc.get("net_labels", []))
    parts.append('</g>')

    # 5. Power ports
    parts.append('<g class="power-ports">')
    parts.extend(_power_port_svg(pp, fonts, bounds) for pp in doc.get("power_ports", []))
    parts.append('</g>')

    # 6. Ports
    parts.append('<g class="ports">')
    port_px = font_px(fonts, 1)
    half = 4 * SCALE
    for port in doc.get("ports", []):
        port_name = (port.get("name") or port.get("text", "")).replace("\\", "")
        x, y = _px(port.get("x", 0)), _py(port.get("y", 0))
        pw = max(port.get("width", 0) * SCALE, len(port_name) * CHAR_W * port_px + 2 * half + 4)
        bounds.add(x, y - half)
        bounds.add(x + pw, y + half)
        # Port chevron polygon
        poly_pts = (f"{x:.1f},{y - half:.1f} {x + pw - half:.1f},{y - half:.1f} {x + pw:.1f},{y:.1f} "
                    f"{x + pw - half:.1f},{y + half:.1f} {x:.1f},{y + half:.1f}")
        parts.append(
            f'<g class="port" data-net="{esc(port_name)}" tabindex="0">'
            f'<polygon class="port-poly" points="{poly_pts}"/>'
            f'{_text_svg(x + 4, y, port_name, port_px, "", 3)}'
            f'</g>'
        )
    parts.append('</g>')

    if not bounds:
        bounds.add(0, -300)
        bounds.add(800, 300)
    pad = 50
    vx, vy = bounds.x0 - pad, bounds.y0 - pad
    w_px = max(400.0, bounds.x1 - bounds.x0 + 2 * pad)
    h_px = max(300.0, bounds.y1 - bounds.y0 + 2 * pad)

    svg_parts = [
        f'<svg id="sch" class="sch" data-render="schdoc" viewBox="{vx:g} {vy:g} {w_px:g} {h_px:g}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{esc(sheet_title)}">'
    ]

    # The <style> is inlined into the page, so it is global there. Every rule is scoped to this SVG (the
    # SCOPE selector) and colours come from the page's tokens: var(--sch-*, fallback). Opened on its own
    # (python scripts/preview_sch.py ... -o out.svg) there are no tokens and the fallbacks draw it.
    svg_parts.append(f"<style>{scoped_css()}</style>")

    # Background and title watermark
    svg_parts.append(f'<rect class="sch-bg" x="{vx:g}" y="{vy:g}" width="{w_px:g}" height="{h_px:g}"/>')
    svg_parts.append(f'<text class="sch-title" x="{vx + 20:g}" y="{vy + 25:g}">{esc(sheet_title)}</text>')
    svg_parts.extend(parts)
    svg_parts.append('</svg>')
    res = "\n".join(svg_parts)

    if write and out_path:
        out = pathlib.Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(res, encoding="utf-8")

    return res


def render_project_sch(project: str, sheet: str = None) -> str:
    """Render a schematic sheet for a project, prioritizing linked Altium SchDoc files."""
    link = project_mod.altium_link(project)
    project_file = link.get("project_file")

    if project_file and pathlib.Path(project_file).is_file():
        try:
            from altium.prjpcb import read_prjpcb
            prj = read_prjpcb(project_file)
            prj_dir = pathlib.Path(project_file).parent
            sheets = prj.get("sheets", [])

            target_path = None
            if sheet:
                # Find matching sheet
                for s in sheets:
                    p = prj_dir / pathlib.Path(s.replace("\\", "/"))
                    if p.name.lower() == sheet.lower() or p.stem.lower() == sheet.lower():
                        target_path = p
                        break
            elif sheets:
                target_path = prj_dir / pathlib.Path(sheets[0].replace("\\", "/"))

            if target_path and target_path.is_file():
                return render_schdoc(target_path)
        except Exception:
            pass

    try:
        from skills import render_sheet
        import store
        return render_sheet.render(project, sheet or (store.sheet_ids(project) or [""])[0], write=False)
    except (Exception, SystemExit) as exc:
        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 100"><text x="20" y="50" style="fill:var(--ink-3,#999)">No schematic preview available ({esc(str(exc))})</text></svg>'


def resolve_schdoc_component_pins(doc: dict, target_comp: dict) -> list[dict]:
    """Resolve nets for pins of a SchDoc component by tracing wires to net labels and power ports."""
    segments = []
    for w in doc.get("wires", []):
        pts = w.get("points", [])
        for i in range(len(pts) - 1):
            segments.append((pts[i], pts[i + 1]))

    def point_on_seg(p, seg):
        (x1, y1), (x2, y2) = seg
        px, py = p
        if x1 == x2 == px:
            return min(y1, y2) <= py <= max(y1, y2)
        if y1 == y2 == py:
            return min(x1, x2) <= px <= max(x1, x2)
        dx, dy = x2 - x1, y2 - y1
        if dx * (py - y1) == dy * (px - x1):
            return min(x1, x2) <= px <= max(x1, x2) and min(y1, y2) <= py <= max(y1, y2)
        return False

    parent = list(range(len(segments)))

    def find(i):
        if parent[i] == i:
            return i
        parent[i] = find(parent[i])
        return parent[i]

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    for i in range(len(segments)):
        for j in range(i + 1, len(segments)):
            s1, s2 = segments[i], segments[j]
            if (point_on_seg(s1[0], s2) or point_on_seg(s1[1], s2) or
                    point_on_seg(s2[0], s1) or point_on_seg(s2[1], s1)):
                union(i, j)

    labels = []
    for item in doc.get("net_labels", []) + doc.get("power_ports", []) + doc.get("ports", []):
        labels.append(((item.get("x", 0), item.get("y", 0)), (item.get("name") or item.get("text", "")).replace("\\", "")))

    resolved_pins = []
    for pin in target_comp.get("pins", []):
        pt = (pin.get("x", 0), pin.get("y", 0))
        tip = pin_tip(pin)
        pin_seg = (pt, tip)
        matched_net = None

        # 1. Direct label at pin tip or base
        for lpt, lname in labels:
            if lpt == tip or lpt == pt:
                matched_net = lname
                break

        # 2. Wire touching pin tip, base, or pin segment
        if not matched_net:
            for s_idx, seg in enumerate(segments):
                if (point_on_seg(tip, seg) or point_on_seg(pt, seg) or
                        point_on_seg(seg[0], pin_seg) or point_on_seg(seg[1], pin_seg)):
                    root = find(s_idx)
                    for lpt, lname in labels:
                        for s2_idx, seg2 in enumerate(segments):
                            if find(s2_idx) == root and point_on_seg(lpt, seg2):
                                matched_net = lname
                                break
                        if matched_net:
                            break
                if matched_net:
                    break

        resolved_pins.append({
            "number": pin.get("number", ""),
            "name": pin.get("name", "").replace("\\", ""),
            "net": matched_net or ""
        })

    return resolved_pins


def get_component_details(project: str, ref: str, sheet: str = None) -> dict | None:
    """Retrieve full details for a component by designator in a project.

    Gathers MPN, value/comment, package/footprint, sheet, parameters, pins with nets,
    BOM line info with JLC code + stock, and datasheet link.
    """
    if not ref:
        return None

    import store
    lines = store.bom(project, write=False)
    bom_line = next((l for l in lines if ref in l.get("refs", []) or l.get("key") == ref), None)

    comp_found = None
    sheet_name = sheet or None
    link = project_mod.altium_link(project)
    project_file = link.get("project_file")

    # 1. Search Altium SchDocs if linked
    if project_file and pathlib.Path(project_file).is_file():
        try:
            from altium.prjpcb import read_prjpcb
            from altium.schdoc import read_schdoc
            prj = read_prjpcb(project_file)
            prj_dir = pathlib.Path(project_file).parent
            sheets_list = prj.get("sheets", [])

            ordered_sheets = []
            if sheet:
                for s in sheets_list:
                    p = prj_dir / pathlib.Path(s.replace("\\", "/"))
                    if p.name.lower() == sheet.lower() or p.stem.lower() == sheet.lower():
                        ordered_sheets.append(p)
                        break
            for s in sheets_list:
                p = prj_dir / pathlib.Path(s.replace("\\", "/"))
                if p not in ordered_sheets and p.is_file():
                    ordered_sheets.append(p)

            for doc_path in ordered_sheets:
                if not doc_path.is_file():
                    continue
                doc = read_schdoc(doc_path)
                for c in doc.get("components", []):
                    if c.get("ref", "").lower() == ref.lower():
                        comp_found = c
                        sheet_name = doc_path.stem
                        comp_found["resolved_pins"] = resolve_schdoc_component_pins(doc, c)
                        break
                if comp_found:
                    break
        except Exception:
            pass

    # 2. Search local netlists
    if not comp_found:
        for sid in store.sheet_ids(project):
            sh_data = store.load_sheet(project, sid)
            for part in sh_data.get("parts", []):
                if part.get("ref", "").lower() == ref.lower():
                    comp_found = part
                    sheet_name = sh_data.get("title") or sid
                    break
            if comp_found:
                break

    # 3. Check PcbDoc pads / components
    pcb_pads = []
    if link.get("pcb_file") and pathlib.Path(link["pcb_file"]).is_file():
        try:
            from altium.pcbdoc import read_pcbdoc
            pdoc = read_pcbdoc(link["pcb_file"])
            for pad in pdoc.get("pads", []):
                if (pad.get("ref") or "").lower() == ref.lower():
                    pcb_pads.append({
                        "number": pad.get("name", ""),
                        "name": pad.get("name", ""),
                        "net": pad.get("net") or ""
                    })
            if not comp_found:
                for c in pdoc.get("components", []):
                    if (c.get("ref") or "").lower() == ref.lower():
                        comp_found = c
                        sheet_name = sheet_name or "PCB"
                        break
        except Exception:
            pass

    if not comp_found and not bom_line and not pcb_pads:
        return None

    # Resolve BOM info
    bom_info = None
    mpn = ""
    value = ""
    package = ""
    description = ""
    datasheet = ""
    jlc_code = ""
    stock = None

    if bom_line:
        mpn = bom_line.get("mpn") or ""
        value = bom_line.get("value") or ""
        package = bom_line.get("package") or ""
        description = bom_line.get("description") or ""
        datasheet = bom_line.get("datasheet") or bom_line.get("datasheet_url") or ""
        supply = bom_line.get("supply") or {}
        lcsc = supply.get("LCSC") or {}
        jlc_code = lcsc.get("code") or bom_line.get("code") or ""
        stock = lcsc.get("stock")
        if stock is None:
            for sup_key in ("Mouser", "DigiKey"):
                if supply.get(sup_key, {}).get("stock") is not None:
                    stock = supply[sup_key]["stock"]
                    break
        bom_info = {
            "line": bom_line.get("key"),
            "mpn": mpn,
            "jlc_code": jlc_code,
            "stock": stock,
            "datasheet": datasheet
        }

    # Pins
    pins = []
    if comp_found and "resolved_pins" in comp_found:
        pins = comp_found["resolved_pins"]
    elif comp_found and "pins" in comp_found:
        for p in comp_found["pins"]:
            pins.append({
                "number": str(p.get("number") or p.get("num") or ""),
                "name": str(p.get("name") or "").replace("\\", ""),
                "net": p.get("net") or ""
            })
    elif pcb_pads:
        pins = pcb_pads
    else:
        nets = store.nets_of(project, ref)
        if nets:
            pins = [{"number": str(i + 1), "name": f"Pin {i + 1}", "net": n} for i, n in enumerate(nets)]

    # Parameters
    params = {}
    if comp_found and isinstance(comp_found.get("params"), dict):
        params = comp_found["params"]
    elif bom_line:
        for k in ("manufacturer", "package", "value", "role", "note"):
            if bom_line.get(k):
                params[k.capitalize()] = str(bom_line[k])

    actual_ref = (comp_found.get("ref") if comp_found else None) or (bom_line.get("refs", [ref])[0] if bom_line else ref)
    actual_value = (comp_found.get("comment") if comp_found else None) or value or ""
    actual_mpn = mpn or (comp_found.get("comment") if comp_found else "") or actual_value
    actual_footprint = (comp_found.get("footprint") or comp_found.get("pattern") if comp_found else None) or package or ""
    actual_desc = (comp_found.get("description") if comp_found else None) or description or ""

    return {
        "ref": actual_ref,
        "value": actual_value,
        "comment": actual_value,
        "mpn": actual_mpn,
        "footprint": actual_footprint,
        "package": actual_footprint,
        "sheet": sheet_name or (sheet or "Schematic"),
        "description": actual_desc,
        "params": params,
        "pins": pins,
        "bom": bom_info,
        "datasheet": datasheet
    }


def main(argv=None):
    ap = argparse.ArgumentParser(prog="preview_sch", description="Altium SchDoc schematic preview renderer")
    ap.add_argument("target", help="Path to .SchDoc file or project name")
    ap.add_argument("--sheet", help="Sheet name when target is a project")
    ap.add_argument("--output", "-o", help="Output SVG file path")
    args = ap.parse_args(argv)

    p = pathlib.Path(args.target)
    if p.is_file() and p.suffix.lower() == ".schdoc":
        svg = render_schdoc(p, write=bool(args.output), out_path=args.output)
    else:
        svg = render_project_sch(args.target, sheet=args.sheet)
        if args.output:
            pathlib.Path(args.output).write_text(svg, encoding="utf-8")

    if not args.output:
        print(f"Rendered SVG ({len(svg)} bytes)")


if __name__ == "__main__":
    main()
