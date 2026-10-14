"""Placement + routing preview: renders an Altium PcbDoc to SVG with plan overlay.

Components (x, y, rotation, pads) + board outline -> SVG.
Overlays a placement plan JSON (groups, keep-outs, critical nets with notes).
Supports layer toggles (top, bottom, plan) and interactive click on part/net.

Usage:
    python scripts/preview_pcb.py <pcbdoc_or_project> [--plan <plan.json>] [--layer <top|bottom|all>] [--output <out.svg>]
"""
import argparse
import html
import json
import math
import pathlib
import re
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from altium.ole import open_doc, stream, text_records
from altium.pcbdoc import read_pcbdoc
import project as project_mod
import workspace


def esc(s: str) -> str:
    return html.escape(str(s or ""), quote=True)


# The picture is inlined into the page, so its <style> is global there: every rule starts with SCOPE and "&"
# below stands for it. The layer colours are data colours (the same on both themes, readable on both
# --pcb-bg values) and are defined once as variables on the SVG; everything else is the page's tokens with
# the dark value as fallback, so the file still draws when it is opened on its own.
SCOPE = "svg.pcb-preview"

_CSS = """
& { --c-top: #e74c3c; --c-bottom: #3498db; --c-multi: #f39c12; --c-crit: #2ecc71; --c-sel: #ffe066; --c-net: #c79bff;
    --c-board: #17281f; --c-board-line: #2d5a3c; --c-text: #f2f4f8; font-family: var(--f-mono, "IBM Plex Mono", ui-monospace, monospace); }
& .pcb-bg { fill: var(--pcb-bg, #121820); }
& .grid-line { stroke: var(--pcb-grid, rgba(255, 255, 255, 0.04)); stroke-width: 0.8; }
& .board-poly { fill: var(--c-board); stroke: var(--c-board-line); stroke-width: 2; }
& .plan-group { cursor: pointer; --zone: var(--c-bottom); }
& .plan-group rect { fill: var(--zone); stroke: var(--zone); fill-opacity: 0.15; stroke-dasharray: 4, 3; stroke-width: 1.5; }
& .plan-group text { fill: var(--zone); font-size: 11px; font-weight: 600; }
& .plan-group:hover rect, & .plan-group:focus-visible rect, & .plan-group.sel rect { fill-opacity: 0.3; }
& .plan-group.sel rect { stroke-width: 2.6; stroke-dasharray: none; }
& .plan-keepout { cursor: default; }
& .plan-keepout rect { fill: var(--c-top); fill-opacity: 0.18; stroke: var(--c-top); stroke-dasharray: 5, 3; stroke-width: 1.8; }
& .plan-keepout text { fill: var(--c-top); font-size: 10px; font-weight: 700; }
& .pcb-comp { cursor: pointer; }
& .pcb-comp rect { fill-opacity: 0.15; stroke-width: 1.2; rx: 1.5; }
& .comp-top rect { fill: var(--c-top); stroke: var(--c-top); }
& .comp-bottom rect { fill: var(--c-bottom); stroke: var(--c-bottom); }
& .comp-ref { font-size: 9px; font-weight: 700; fill: var(--c-text); text-anchor: middle; pointer-events: none; }
& .pad { cursor: pointer; }
& .pad-top { fill: var(--c-top); stroke: var(--c-top); stroke-width: 0.5; }
& .pad-bottom { fill: var(--c-bottom); stroke: var(--c-bottom); stroke-width: 0.5; }
& .pad-multi { fill: var(--c-multi); stroke: var(--c-multi); stroke-width: 0.7; }
& .crit { stroke: var(--c-crit); stroke-width: 1.8; }
& .pcb-comp:hover rect { stroke: var(--c-sel); stroke-width: 2.2; fill-opacity: 0.4; }
& .pad:hover { stroke: var(--c-text); stroke-width: 1.5; }
& .pcb-comp.sel rect, & .pcb-comp:focus-visible rect { stroke: var(--c-sel); stroke-width: 2.4; fill-opacity: 0.4; }
& .pcb-comp:focus-visible, & .plan-group:focus-visible, & .pad:focus-visible { outline: none; }
& .pad.sel, & .pad:focus-visible { stroke: var(--c-sel); stroke-width: 1.8; }
&.focus .pcb-comp:not(.sel), &.focus .pad:not(.sel) { opacity: 0.3; }
& .pad.hl-net { stroke: var(--c-net); stroke-width: 2.4; }
&.netfocus .pad:not(.hl-net) { opacity: 0.25; }
& .legend text { font-family: var(--f-ui, system-ui, sans-serif); font-size: 11px; fill: var(--ink-3, #94a0bd); }
"""


def scoped_css() -> str:
    """The stylesheet with every rule scoped to SCOPE (see above)."""
    out = []
    for line in _CSS.strip().splitlines():
        out.append(line.replace("&", SCOPE) if "&" in line else line)
    return chr(10).join(out)


_COLOR_RE = re.compile(r"^(#[0-9a-fA-F]{3,8}|[a-zA-Z]{3,20})$")


def _safe_color(value, default: str = "") -> str:
    """A plan colour goes into a style attribute, so only a hex value or a plain colour name passes."""
    v = str(value or "").strip()
    return v if _COLOR_RE.match(v) else default


def _mil(v) -> float:
    s = str(v or "0").strip().lower().removesuffix("mil")
    try:
        return float(s)
    except ValueError:
        return 0.0


def board6_outline(rec: dict) -> list[tuple[float, float]] | None:
    """Board shape from the Board6 record: VXn/VYn vertices, KINDn 1 = arc (CXn, CYn, Rn, SAn..EAn degrees).
    On a real board (2026-10-13) this was the shape in the Gerbers while BoardRegions still held the
    7000 x 5000 mil default, so it is read first."""
    pts = []
    i = 0
    while f"VX{i}" in rec and f"VY{i}" in rec:
        if str(rec.get(f"KIND{i}", "0")).strip() == "1" and _mil(rec.get(f"R{i}")) > 0:
            cx, cy, r = _mil(rec.get(f"CX{i}")), _mil(rec.get(f"CY{i}")), _mil(rec.get(f"R{i}"))
            sa, ea = float(rec.get(f"SA{i}", 0)), float(rec.get(f"EA{i}", 0))
            span = (ea - sa) % 360 or 360
            for k in range(9):
                a = math.radians(sa + span * k / 8)
                pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        else:
            pts.append((_mil(rec[f"VX{i}"]), _mil(rec[f"VY{i}"])))
        i += 1
    if len(pts) < 3 or len({p for p in pts}) < 3:
        return None
    return [(round(x * 0.0254, 4), round(y * 0.0254, 4)) for x, y in pts]


def get_board_outline(pcbdoc_path) -> list[tuple[float, float]] | None:
    """Board outline polygon vertices (in mm): the Board6 shape, else the first BoardRegions record."""
    try:
        p = pathlib.Path(pcbdoc_path)
        with open_doc(p) as ole:
            if ole.exists("Board6/Data"):
                recs = text_records(stream(ole, "Board6/Data"), prefix=0)
                pts = board6_outline(recs[0]) if recs else None
                if pts:
                    return pts
            if ole.exists("BoardRegions/Data"):
                recs = text_records(stream(ole, "BoardRegions/Data"), prefix=0)
                if recs:
                    raw = recs[0].get("LAYERSTACKID", "")
                    if isinstance(raw, str):
                        raw = raw.encode("latin-1")
                    if b"\x00" in raw:
                        _, rest = raw.split(b"\x00", 1)
                        if len(rest) >= 4:
                            n = struct.unpack("<I", rest[:4])[0]
                            if 3 <= n <= 2000 and len(rest) >= 4 + n * 16:
                                pts = []
                                for i in range(n):
                                    x, y = struct.unpack("<dd", rest[4 + i * 16 : 4 + (i + 1) * 16])
                                    pts.append((round(x / 10000 * 0.0254, 4), round(y / 10000 * 0.0254, 4)))
                                return pts
    except Exception:
        pass
    return None


def load_placement_plan(project_or_file) -> dict:
    """Load placement-plan.json for a project or from a file path."""
    p = pathlib.Path(project_or_file)
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}

    # Check project directory
    proj_dir = workspace.project_dir(str(project_or_file))
    plan_file = proj_dir / "placement-plan.json"
    if plan_file.is_file():
        try:
            return json.loads(plan_file.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_placement_plan(project: str, plan: dict) -> dict:
    """Save placement-plan.json in the project folder."""
    proj_dir = workspace.project_dir(project)
    proj_dir.mkdir(parents=True, exist_ok=True)
    plan_file = proj_dir / "placement-plan.json"
    plan_file.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return plan


def render_pcbdoc(doc_or_path, plan: dict = None, active_layer: str = "all",
                  write: bool = False, out_path: str = None) -> str:
    """Render a PcbDoc dict or file path to SVG with an optional placement plan overlay."""
    pcb_path = None
    if isinstance(doc_or_path, (str, pathlib.Path)):
        pcb_path = pathlib.Path(doc_or_path)
        doc = read_pcbdoc(pcb_path)
        doc_name = pcb_path.stem
    else:
        doc = doc_or_path
        doc_name = doc.get("file", "PCB")
        if doc.get("file"):
            pcb_path = pathlib.Path(doc["file"])

    components = doc.get("components", [])
    pads = doc.get("pads", [])
    nets = doc.get("nets", [])
    plan = plan or {}

    # Outline
    outline = None
    if pcb_path and pcb_path.is_file():
        outline = get_board_outline(pcb_path)

    # Collect coordinates
    xs = []
    ys = []

    if outline:
        for x, y in outline:
            xs.append(x)
            ys.append(y)

    for c in components:
        xs.append(c.get("x_mm", 0))
        ys.append(c.get("y_mm", 0))

    for p in pads:
        xs.append(p.get("x_mm", 0))
        ys.append(p.get("y_mm", 0))

    # Also include plan groups / keep-outs
    for g in plan.get("groups", []):
        gx = g.get("x", 0)
        gy = g.get("y", 0)
        gw = g.get("w", 0)
        gh = g.get("h", 0)
        xs.extend([gx, gx + gw])
        ys.extend([gy, gy + gh])

    for k in plan.get("keep_outs", []):
        kx = k.get("x", 0)
        ky = k.get("y", 0)
        kw = k.get("w", 0)
        kh = k.get("h", 0)
        xs.extend([kx, kx + kw])
        ys.extend([ky, ky + kh])

    if not xs:
        xs = [0.0, 100.0]
        ys = [0.0, 80.0]

    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)

    margin = 8.0  # 8 mm margin
    scale = 8.0   # 8 SVG px per mm

    w_mm = (max_x - min_x) + 2 * margin
    h_mm = (max_y - min_y) + 2 * margin
    w_px = max(500.0, w_mm * scale)
    h_px = max(400.0, h_mm * scale)

    # Transformations (mm -> SVG pixel units, Y inverted)
    def tx(x_mm):
        return (x_mm - min_x + margin) * scale

    def ty(y_mm):
        return (max_y - y_mm + margin) * scale

    def ts(dim_mm):
        return max(1.0, dim_mm * scale)

    crit_net_names = {cn.get("net") for cn in plan.get("critical_nets", []) if cn.get("net")}

    svg = [
        f'<svg id="pcb-preview" class="pcb-preview layer-{active_layer}" viewBox="0 0 {w_px:.1f} {h_px:.1f}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{esc(doc_name)}">'
    ]

    svg.append(f"<style>{scoped_css()}</style>")
    svg.append('<rect class="pcb-bg" x="0" y="0" width="100%" height="100%"/>')

    # Grid background pattern
    grid_step = 10.0 * scale  # 10mm grid
    svg.append('<g class="grid">')
    gx = 0.0
    while gx <= w_px:
        svg.append(f'<line x1="{gx:.1f}" y1="0" x2="{gx:.1f}" y2="{h_px:.1f}" class="grid-line"/>')
        gx += grid_step
    gy = 0.0
    while gy <= h_px:
        svg.append(f'<line x1="0" y1="{gy:.1f}" x2="{w_px:.1f}" y2="{gy:.1f}" class="grid-line"/>')
        gy += grid_step
    svg.append('</g>')

    # 1. Board Outline
    svg.append('<g id="pcb-layer-outline" class="layer-outline pcb-outline">')
    if outline:
        poly_pts = " ".join(f"{tx(x):.1f},{ty(y):.1f}" for x, y in outline)
        svg.append(f'<polygon points="{poly_pts}" class="board-poly pcb-outline"/>')
    else:
        # Fallback to bounding box rectangle
        ob_x = tx(min_x)
        ob_y = ty(max_y)
        ob_w = ts(max_x - min_x)
        ob_h = ts(max_y - min_y)
        svg.append(f'<rect x="{ob_x:.1f}" y="{ob_y:.1f}" width="{ob_w:.1f}" height="{ob_h:.1f}" class="board-poly pcb-outline" rx="4"/>')
    svg.append('</g>')

    # 2. Plan Overlay (Groups and Keep-Outs)
    svg.append('<g id="pcb-layer-plan" class="layer-plan">')
    for g in plan.get("groups", []):
        gx = tx(g.get("x", 0))
        # Note: inverting Y for rect: top-left Y is ty(y + h)
        gy = ty(g.get("y", 0) + g.get("h", 0))
        gw = ts(g.get("w", 0))
        gh = ts(g.get("h", 0))
        color = _safe_color(g.get("color"))
        zone = f' style="--zone:{color}"' if color else ""
        name = g.get("name", "Group")
        note = g.get("note", "")
        svg.append(
            f'<g class="plan-group" data-group="{esc(name)}"{zone}>'
            f'<rect x="{gx:.1f}" y="{gy:.1f}" width="{gw:.1f}" height="{gh:.1f}"/>'
            f'<text x="{gx + 6:.1f}" y="{gy + 14:.1f}">{esc(name)}'
            f'{f" · {esc(note)}" if note else ""}</text>'
            f'</g>'
        )

    for k in plan.get("keep_outs", []):
        kx = tx(k.get("x", 0))
        ky = ty(k.get("y", 0) + k.get("h", 0))
        kw = ts(k.get("w", 0))
        kh = ts(k.get("h", 0))
        kname = k.get("name", "Keep-out")
        knote = k.get("note", "")
        svg.append(
            f'<g class="plan-keepout">'
            f'<rect x="{kx:.1f}" y="{ky:.1f}" width="{kw:.1f}" height="{kh:.1f}"/>'
            f'<text x="{kx + 6:.1f}" y="{ky + 14:.1f}">Keep-out: {esc(kname)}'
            f'{f" ({esc(knote)})" if knote else ""}</text>'
            f'</g>'
        )
    svg.append('</g>')

    # 3. Bottom Layer
    svg.append('<g id="pcb-layer-bottom" class="layer-bottom">')
    # Bottom components
    for c in components:
        if c.get("layer") == "BOTTOM":
            ref = c.get("ref", "")
            cx = tx(c.get("x_mm", 0))
            cy = ty(c.get("y_mm", 0))
            rot = -c.get("rotation", 0.0)
            svg.append(
                f'<g class="pcb-comp comp-bottom" data-ref="{esc(ref)}" id="pcb-comp-{esc(ref)}" '
                f'transform="rotate({rot:.1f} {cx:.1f} {cy:.1f})">'
                f'<rect x="{cx - 16:.1f}" y="{cy - 12:.1f}" width="32" height="24"/>'
                f'<text class="comp-ref" x="{cx:.1f}" y="{cy + 3:.1f}">{esc(ref)}</text>'
                f'</g>'
            )
    # Bottom pads
    for p in pads:
        if p.get("layer") == 32:  # Bottom
            px = tx(p.get("x_mm", 0))
            py = ty(p.get("y_mm", 0))
            sx = ts(p.get("sx_mm", 1.5))
            sy = ts(p.get("sy_mm", 1.5))
            net = p.get("net") or ""
            ref = p.get("ref") or ""
            pname = p.get("name", "")
            is_crit = net in crit_net_names
            svg.append(
                f'<rect class="pad pad-bottom{" crit" if is_crit else ""}" '
                f'x="{px - sx / 2:.1f}" y="{py - sy / 2:.1f}" width="{sx:.1f}" height="{sy:.1f}" rx="1" '
                f'data-ref="{esc(ref)}" data-net="{esc(net)}">'
                f'<title>{esc(ref)}.{esc(pname)}: {esc(net)}</title>'
                f'</rect>'
            )
    svg.append('</g>')

    # 4. Top Layer (and Multi-Layer)
    svg.append('<g id="pcb-layer-top" class="layer-top">')
    # Multi-layer pads
    for p in pads:
        if p.get("layer") == 74:  # Multi-layer through-hole
            px = tx(p.get("x_mm", 0))
            py = ty(p.get("y_mm", 0))
            sx = ts(p.get("sx_mm", 1.8))
            sy = ts(p.get("sy_mm", 1.8))
            net = p.get("net") or ""
            ref = p.get("ref") or ""
            pname = p.get("name", "")
            is_crit = net in crit_net_names
            svg.append(
                f'<rect class="pad pad-multi{" crit" if is_crit else ""}" '
                f'x="{px - sx / 2:.1f}" y="{py - sy / 2:.1f}" width="{sx:.1f}" height="{sy:.1f}" rx="{sx / 2:.1f}" '
                f'data-ref="{esc(ref)}" data-net="{esc(net)}">'
                f'<title>{esc(ref)}.{esc(pname)} (TH): {esc(net)}</title>'
                f'</rect>'
            )

    # Top pads
    for p in pads:
        if p.get("layer") == 1:  # Top
            px = tx(p.get("x_mm", 0))
            py = ty(p.get("y_mm", 0))
            sx = ts(p.get("sx_mm", 1.5))
            sy = ts(p.get("sy_mm", 1.5))
            net = p.get("net") or ""
            ref = p.get("ref") or ""
            pname = p.get("name", "")
            is_crit = net in crit_net_names
            svg.append(
                f'<rect class="pad pad-top{" crit" if is_crit else ""}" '
                f'x="{px - sx / 2:.1f}" y="{py - sy / 2:.1f}" width="{sx:.1f}" height="{sy:.1f}" rx="1" '
                f'data-ref="{esc(ref)}" data-net="{esc(net)}">'
                f'<title>{esc(ref)}.{esc(pname)}: {esc(net)}</title>'
                f'</rect>'
            )

    # Top components
    for c in components:
        if c.get("layer") != "BOTTOM":
            ref = c.get("ref", "")
            cx = tx(c.get("x_mm", 0))
            cy = ty(c.get("y_mm", 0))
            rot = -c.get("rotation", 0.0)
            svg.append(
                f'<g class="pcb-comp comp-top" data-ref="{esc(ref)}" id="pcb-comp-{esc(ref)}" '
                f'transform="rotate({rot:.1f} {cx:.1f} {cy:.1f})">'
                f'<rect x="{cx - 16:.1f}" y="{cy - 12:.1f}" width="32" height="24"/>'
                f'<text class="comp-ref" x="{cx:.1f}" y="{cy + 3:.1f}">{esc(ref)}</text>'
                f'</g>'
            )
    svg.append('</g>')

    # Legend: the swatches use the classes of the drawing, so the colours live in the stylesheet only
    entries = [("pad-top", "Top"), ("pad-bottom", "Bottom"), ("pad-multi", "Through-hole")]
    if crit_net_names:
        entries.append(("pad-top crit", "Critical net"))
    lg = []
    lx = 0.0
    for cls, label in entries:
        lg.append(f'<rect class="{cls}" x="{lx:.1f}" y="0" width="9" height="9" rx="1.5"/>')
        lg.append(f'<text x="{lx + 14:.1f}" y="8.5">{esc(label)}</text>')
        lx += 14 + len(label) * 6.4 + 14
    svg.append(f'<g class="legend" transform="translate(16 16)">{"".join(lg)}</g>')

    svg.append('</svg>')
    res = "\n".join(svg)

    if write and out_path:
        out = pathlib.Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(res, encoding="utf-8")

    return res


def render_project_pcb(project: str, plan_file: str = None, layer: str = "all") -> str:
    """Render PCB preview for a linked Altium project."""
    link = project_mod.altium_link(project)
    pcb_file = link.get("pcb_file")

    if not pcb_file or not pathlib.Path(pcb_file).is_file():
        # Check if project_file has a PCB document
        prj_file = link.get("project_file")
        if prj_file and pathlib.Path(prj_file).is_file():
            try:
                from altium.prjpcb import read_prjpcb
                prj = read_prjpcb(prj_file)
                pcbs = prj.get("pcbs", [])
                if pcbs:
                    cand = pathlib.Path(prj_file).parent / pathlib.Path(pcbs[0].replace("\\", "/"))
                    if cand.is_file():
                        pcb_file = str(cand)
            except Exception:
                pass

    if not pcb_file or not pathlib.Path(pcb_file).is_file():
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 200">'
            '<rect width="100%" height="100%" style="fill:var(--pcb-bg,#121820)"/>'
            '<text x="250" y="100" text-anchor="middle" font-family="sans-serif" font-size="14" '
            'style="fill:var(--ink-3,#94a0bd)">'
            'No Altium .PcbDoc linked. Link one in Settings to view PCB placement &amp; routing preview.'
            '</text></svg>'
        )

    plan = load_placement_plan(plan_file or project)
    return render_pcbdoc(pcb_file, plan=plan, active_layer=layer)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="preview_pcb", description="Altium PcbDoc placement & routing preview renderer")
    ap.add_argument("target", help="Path to .PcbDoc file or project name")
    ap.add_argument("--plan", help="Path to placement-plan.json")
    ap.add_argument("--layer", choices=["top", "bottom", "all"], default="all", help="Layer visibility filter")
    ap.add_argument("--output", "-o", help="Output SVG file path")
    args = ap.parse_args(argv)

    p = pathlib.Path(args.target)
    if p.is_file() and p.suffix.lower() == ".pcbdoc":
        plan = load_placement_plan(args.plan) if args.plan else {}
        svg = render_pcbdoc(p, plan=plan, active_layer=args.layer, write=bool(args.output), out_path=args.output)
    else:
        svg = render_project_pcb(args.target, plan_file=args.plan, layer=args.layer)
        if args.output:
            pathlib.Path(args.output).write_text(svg, encoding="utf-8")

    if not args.output:
        print(f"Rendered PCB SVG ({len(svg)} bytes)")


if __name__ == "__main__":
    main()
