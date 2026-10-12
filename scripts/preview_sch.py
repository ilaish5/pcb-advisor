"""Schematic preview: renders an Altium SchDoc to SVG.

Renders components as boxes with ref + pins, wires, net labels, power ports, and ports.
Supports clicking on parts or nets with data-ref and data-net attributes.

Usage:
    python scripts/preview_sch.py <path_or_project> [--sheet <sheet>] [--output <out.svg>]
"""
import argparse
import html
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from altium.schdoc import read_schdoc
import project as project_mod
import workspace


def esc(s: str) -> str:
    return html.escape(str(s or ""), quote=True)


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
    components = doc.get("components", [])
    wires = doc.get("wires", [])
    net_labels = doc.get("net_labels", [])
    power_ports = doc.get("power_ports", [])
    ports = doc.get("ports", [])
    junctions = doc.get("junctions", [])

    # Collect coordinates for bounding box
    xs = []
    ys = []

    for c in components:
        xs.append(c.get("x", 0))
        ys.append(c.get("y", 0))
        for pin in c.get("pins", []):
            xs.append(pin.get("x", 0))
            ys.append(pin.get("y", 0))

    for w in wires:
        for x, y in w.get("points", []):
            xs.append(x)
            ys.append(y)

    for item in net_labels + power_ports + ports + junctions:
        xs.append(item.get("x", 0))
        ys.append(item.get("y", 0))

    if not xs:
        xs = [0, 800]
        ys = [0, 600]

    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)

    pad = 50
    w_px = max(400, (max_x - min_x) + 2 * pad)
    h_px = max(300, (max_y - min_y) + 2 * pad)

    # Coordinate mapping: Altium Y increases upwards; SVG Y increases downwards
    def tx(x):
        return (x - min_x) + pad

    def ty(y):
        return (max_y - y) + pad

    svg_parts = [
        f'<svg id="sch" class="sch" viewBox="0 0 {w_px} {h_px}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{esc(sheet_title)}">'
    ]

    # Embedded CSS styles compatible with ui/index.html
    svg_parts.append("""
    <style>
      .sch { background: #fbfcfe; font-family: "IBM Plex Mono", ui-monospace, monospace; }
      .sch text { font-size: 10px; fill: #151515; }
      .sch .refd { font-weight: 700; font-size: 11px; fill: #2148c9; }
      .sch .mpn { font-size: 9px; fill: #5b667b; }
      .sch .pnum { font-size: 8px; fill: #888888; }
      .sch .pname { font-size: 8.5px; font-weight: 600; fill: #222222; }
      .sch .w { stroke: #233f99; stroke-width: 1.6; fill: none; stroke-linecap: round; stroke-linejoin: round; }
      .sch .pin { stroke: #333333; stroke-width: 1.2; }
      .sch .body { fill: #fdf2c8; stroke: #7d2f14; stroke-width: 1.5; rx: 3; }
      .sch .hlbox { fill: transparent; stroke: none; }
      .sch .part:hover .hlbox { fill: rgba(33, 72, 201, 0.08); stroke: rgba(33, 72, 201, 0.3); stroke-width: 1; }
      .sch .part.sel .hlbox { fill: rgba(33, 72, 201, 0.15); stroke: #2148c9; stroke-width: 1.8; }
      .sch .net-label { cursor: pointer; }
      .sch .net-label:hover rect { fill: #e3e9fb; stroke: #2148c9; }
      .sch .net-label text { font-size: 9.5px; font-weight: 600; fill: #6b2fb3; }
      .sch .power-port { cursor: pointer; }
      .sch .power-port text { font-size: 9px; font-weight: 700; fill: #d27a12; }
      .sch .pb { stroke: #d27a12; stroke-width: 2.2; }
      .sch .port { cursor: pointer; }
      .sch .port-poly { fill: #e1f2e8; stroke: #167a46; stroke-width: 1.2; }
      .sch .port text { font-size: 9px; font-weight: 600; fill: #167a46; }
      .sch .jn { fill: #233f99; }
      .sch .pin-tip { fill: #233f99; opacity: 0; }
      .sch .part:hover .pin-tip { opacity: 0.8; }
    </style>
    """)

    # Background
    svg_parts.append(f'<rect width="{w_px}" height="{h_px}" fill="#fbfcfe"/>')

    # Title watermark
    svg_parts.append(f'<text x="20" y="25" font-family="sans-serif" font-size="14" font-weight="700" fill="#7d889b">{esc(sheet_title)}</text>')

    # 1. Wires
    svg_parts.append('<g class="wires">')
    for w in wires:
        pts = w.get("points", [])
        if len(pts) >= 2:
            pts_str = " ".join(f"{tx(x):.1f},{ty(y):.1f}" for x, y in pts)
            svg_parts.append(f'<polyline class="w" points="{pts_str}"/>')
    svg_parts.append('</g>')

    # 2. Junctions
    svg_parts.append('<g class="junctions">')
    for j in junctions:
        jx, jy = tx(j.get("x", 0)), ty(j.get("y", 0))
        svg_parts.append(f'<circle cx="{jx:.1f}" cy="{jy:.1f}" r="2.5" class="jn"/>')
    svg_parts.append('</g>')

    # 3. Components
    svg_parts.append('<g class="components">')
    for comp in components:
        ref = comp.get("ref", "")
        pins = comp.get("pins", [])
        cx, cy = tx(comp.get("x", 0)), ty(comp.get("y", 0))

        # Calculate bounding box of the component body
        pin_coords_x = []
        pin_coords_y = []
        for p in pins:
            px = tx(p.get("x", 0))
            py = ty(p.get("y", 0))
            pin_coords_x.append(px)
            pin_coords_y.append(py)

        if pin_coords_x and pin_coords_y:
            body_min_x = min(pin_coords_x) + 12
            body_max_x = max(pin_coords_x) - 12
            if body_max_x <= body_min_x:
                body_min_x = min(pin_coords_x) - 15
                body_max_x = max(pin_coords_x) + 15
            body_min_y = min(pin_coords_y) - 10
            body_max_y = max(pin_coords_y) + 10
        else:
            body_min_x = cx - 25
            body_max_x = cx + 25
            body_min_y = cy - 25
            body_max_y = cy + 25

        bw = max(36.0, body_max_x - body_min_x)
        bh = max(26.0, body_max_y - body_min_y)
        bx = body_min_x
        by = body_min_y

        sub_label = comp.get("comment") or comp.get("lib_ref") or ""

        svg_parts.append(
            f'<g class="part" data-ref="{esc(ref)}" id="part-{esc(ref)}" cursor="pointer" tabindex="0">'
        )
        # Highlight rect
        svg_parts.append(f'<rect class="hlbox" x="{bx - 6:.1f}" y="{by - 6:.1f}" width="{bw + 12:.1f}" height="{bh + 12:.1f}" rx="5"/>')
        # Body rect
        svg_parts.append(f'<rect class="body" x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{bh:.1f}"/>')
        # Designator label
        svg_parts.append(f'<text class="refd" x="{bx + 5:.1f}" y="{by + 13:.1f}">{esc(ref)}</text>')
        # Sub label (comment or lib_ref)
        if sub_label:
            svg_parts.append(f'<text class="mpn" x="{bx + 5:.1f}" y="{by + bh - 5:.1f}">{esc(sub_label[:18])}</text>')

        # Pins
        for p in pins:
            px = tx(p.get("x", 0))
            py = ty(p.get("y", 0))
            length = p.get("length", 20)
            orient = p.get("orientation", 0)  # 0=Right, 1=Up, 2=Left, 3=Down

            # Calculate inward pin line end (at the body boundary)
            if orient == 0:  # pin goes right from body to connection point
                end_x, end_y = px - length, py
                name_anchor, name_x = "start", px - length + 4
                num_anchor, num_x = "end", px - 3
            elif orient == 1:  # pin goes up from body to connection point
                end_x, end_y = px, py + length
                name_anchor, name_x = "middle", px
                num_anchor, num_x = "middle", px
            elif orient == 2:  # pin goes left from body to connection point
                end_x, end_y = px + length, py
                name_anchor, name_x = "end", px + length - 4
                num_anchor, num_x = "start", px + 3
            else:  # 3: pin goes down from body to connection point
                end_x, end_y = px, py - length
                name_anchor, name_x = "middle", px
                num_anchor, num_x = "middle", px

            svg_parts.append(f'<line class="pin" x1="{px:.1f}" y1="{py:.1f}" x2="{end_x:.1f}" y2="{end_y:.1f}"/>')
            # Pin hotspot
            svg_parts.append(f'<circle class="pin-tip" cx="{px:.1f}" cy="{py:.1f}" r="3" data-ref="{esc(ref)}" data-pin="{esc(p.get("number", ""))}"/>')

            pnum = p.get("number", "")
            if pnum:
                svg_parts.append(f'<text class="pnum" x="{num_x:.1f}" y="{py - 2:.1f}" text-anchor="{num_anchor}">{esc(pnum)}</text>')

            pname = p.get("name", "")
            if pname:
                # Clean escaped slashes in inverted pin names like T\X\0\ -> TX0
                clean_name = pname.replace("\\", "")
                svg_parts.append(f'<text class="pname" x="{name_x:.1f}" y="{py + 3:.1f}" text-anchor="{name_anchor}">{esc(clean_name)}</text>')

        svg_parts.append('</g>')
    svg_parts.append('</g>')

    # 4. Net labels
    svg_parts.append('<g class="net-labels">')
    for nl in net_labels:
        net_text = nl.get("text") or nl.get("name", "")
        lx, ly = tx(nl.get("x", 0)), ty(nl.get("y", 0))
        label_w = max(24, len(net_text) * 6 + 8)
        svg_parts.append(
            f'<g class="net-label" data-net="{esc(net_text)}" tabindex="0">'
            f'<rect x="{lx:.1f}" y="{ly - 10:.1f}" width="{label_w}" height="13" fill="#f0e7fb" stroke="#6b2fb3" stroke-width="0.8" rx="2"/>'
            f'<text x="{lx + 4:.1f}" y="{ly - 1:.1f}">{esc(net_text)}</text>'
            f'</g>'
        )
    svg_parts.append('</g>')

    # 5. Power ports
    svg_parts.append('<g class="power-ports">')
    for pp in power_ports:
        p_text = pp.get("text") or pp.get("name", "")
        px, py = tx(pp.get("x", 0)), ty(pp.get("y", 0))
        svg_parts.append(
            f'<g class="power-port" data-net="{esc(p_text)}" tabindex="0">'
            f'<line x1="{px - 8:.1f}" y1="{py:.1f}" x2="{px + 8:.1f}" y2="{py:.1f}" class="pb"/>'
            f'<text x="{px:.1f}" y="{py - 4:.1f}" text-anchor="middle">{esc(p_text)}</text>'
            f'</g>'
        )
    svg_parts.append('</g>')

    # 6. Ports
    svg_parts.append('<g class="ports">')
    for port in ports:
        port_name = (port.get("name") or port.get("text", "")).replace("\\", "")
        px, py = tx(port.get("x", 0)), ty(port.get("y", 0))
        pw = max(30, len(port_name) * 6 + 12)
        # Port chevron polygon
        poly_pts = f"{px},{py - 6:.1f} {px + pw - 6:.1f},{py - 6:.1f} {px + pw},{py} {px + pw - 6:.1f},{py + 6:.1f} {px},{py + 6:.1f}"
        svg_parts.append(
            f'<g class="port" data-net="{esc(port_name)}" tabindex="0">'
            f'<polygon class="port-poly" points="{poly_pts}"/>'
            f'<text x="{px + 4:.1f}" y="{py + 3:.1f}">{esc(port_name)}</text>'
            f'</g>'
        )
    svg_parts.append('</g>')

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
        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 100"><text x="20" y="50" fill="#999">No schematic preview available ({esc(str(exc))})</text></svg>'


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

    def get_pin_tip(p):
        x, y, length, orient = p.get("x", 0), p.get("y", 0), p.get("length", 20), p.get("orientation", 0)
        dx = length if orient == 0 else (-length if orient == 2 else 0)
        dy = length if orient == 1 else (-length if orient == 3 else 0)
        return (x + dx, y + dy)

    resolved_pins = []
    for pin in target_comp.get("pins", []):
        pt = (pin.get("x", 0), pin.get("y", 0))
        tip = get_pin_tip(pin)
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
