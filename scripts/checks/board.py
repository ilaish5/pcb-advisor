"""
Board-level DRC and physical layout checks on Altium PcbDoc files.

Checks performed:
1. Components near outline/edge:
   - Connectors: checks whether opening/wire entry faces the nearest board edge or inward toward center.
   - Outline clearance: components closer than 0.5 mm to any board edge.
2. Decoupling capacitors distance:
   - For each decoupling cap on a power net, measures distance to the nearest IC power pin on the same net.
3. CPL rotation sanity list:
   - Identifies polarized/IC components and packages known to need 3D model orientation verification.

JSON findings schema:
    [{"id": str, "severity": "error"|"warning"|"info", "refs": list[str], "message": str, "evidence": str}]
"""
import argparse
import json
import math
import pathlib
import re
import sys
from typing import Any

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import oscompat  # noqa: E402
from altium.pcbdoc import read_pcbdoc  # noqa: E402

CONNECTOR_PATTERNS = re.compile(r"HDR|CONN|TERM|PHOENIX|MOLEX|USB|SMA|BARREL|JACK|HEADER|JST|WURTH", re.I)
POLAR_PATTERNS = re.compile(r"SOT|SOIC|SOP|TSSOP|QFP|LQFP|QFN|DFN|SMA|SMB|SMC|SOD|DIODE|ELECTRO|TANT", re.I)


def is_connector(comp: dict[str, Any]) -> bool:
    ref = comp.get("ref", "")
    pattern = comp.get("pattern", "")
    lib_ref = comp.get("lib_ref", "")
    if re.match(r"^(?:J|P|CON|TERM)\d*", ref, re.I):
        return True
    if CONNECTOR_PATTERNS.search(pattern) or CONNECTOR_PATTERNS.search(lib_ref):
        return True
    return False


def compute_board_bounds(doc: dict[str, Any], outline_mm: list[float] | None = None) -> tuple[float, float, float, float]:
    """Return (min_x, min_y, max_x, max_y) in mm."""
    if outline_mm and len(outline_mm) == 4:
        return float(outline_mm[0]), float(outline_mm[1]), float(outline_mm[2]), float(outline_mm[3])

    pads = doc.get("pads", [])
    comps = doc.get("components", [])

    xs = [p["x_mm"] for p in pads if "x_mm" in p] + [c["x_mm"] for c in comps if "x_mm" in c]
    ys = [p["y_mm"] for p in pads if "y_mm" in p] + [c["y_mm"] for c in comps if "y_mm" in c]

    if not xs or not ys:
        return 0.0, 0.0, 100.0, 100.0

    # Expand pads bbox slightly to estimate board edge if no outline provided
    pad_min_x, pad_max_x = min(xs), max(xs)
    pad_min_y, pad_max_y = min(ys), max(ys)
    margin = 2.0
    return pad_min_x - margin, pad_min_y - margin, pad_max_x + margin, pad_max_y + margin


def check_edge_components(doc: dict[str, Any], bounds: tuple[float, float, float, float], connector_specs: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Check components near board outline, especially connector opening orientation."""
    min_x, min_y, max_x, max_y = bounds
    findings = []
    comps = doc.get("components", [])
    specs = connector_specs or {}

    for c in comps:
        ref = c.get("ref")
        if not ref:
            continue
        x = c.get("x_mm", 0.0)
        y = c.get("y_mm", 0.0)
        rot_deg = float(c.get("rotation", 0.0))

        # Distances to the 4 edges
        d_left = x - min_x
        d_right = max_x - x
        d_bottom = y - min_y
        d_top = max_y - y

        edge_dists = [("left", d_left, (-1.0, 0.0)),
                      ("right", d_right, (1.0, 0.0)),
                      ("bottom", d_bottom, (0.0, -1.0)),
                      ("top", d_top, (0.0, 1.0))]
        edge_dists.sort(key=lambda item: item[1])
        nearest_edge, nearest_dist, outward_normal = edge_dists[0]

        # Outline clearance check (general component too close to edge)
        if nearest_dist < 0.5:
            findings.append({
                "id": "component_near_edge",
                "severity": "warning",
                "refs": [ref],
                "message": f"Component {ref} is within {nearest_dist:.2f} mm of the {nearest_edge} board edge.",
                "evidence": f"PcbDoc coordinates ({x}, {y}) vs {nearest_edge} edge ({min_x if nearest_edge=='left' else max_x if nearest_edge=='right' else min_y if nearest_edge=='bottom' else max_y})",
            })

        # Connector check
        if is_connector(c):
            spec = specs.get(ref, {})
            # Direction of wire entry at rotation 0: default is (0, -1) (down) or from spec
            entry_at_0 = spec.get("wire_entry_dir_at_rot0", [0.0, -1.0])
            theta = math.radians(rot_deg)
            # Standard 2D rotation of entry vector
            entry_x = math.cos(theta) * entry_at_0[0] - math.sin(theta) * entry_at_0[1]
            entry_y = math.sin(theta) * entry_at_0[0] + math.cos(theta) * entry_at_0[1]

            # Dot product with outward normal of nearest edge
            dot = entry_x * outward_normal[0] + entry_y * outward_normal[1]

            # If dot < -0.1, the opening points away from the nearest edge (toward the inside of the board)
            if dot < -0.1:
                findings.append({
                    "id": "connector_faces_inward",
                    "severity": "error",
                    "refs": [ref],
                    "message": f"Connector {ref} opening faces inward toward the board center instead of the nearest ({nearest_edge}) edge.",
                    "evidence": f"PcbDoc position ({x:.2f}, {y:.2f}), rotation {rot_deg:.0f} deg, facing vector ({entry_x:.2f}, {entry_y:.2f}) vs outward normal {outward_normal}",
                })

    return findings


def check_decoupling_caps(doc: dict[str, Any], max_dist_mm: float = 12.0) -> list[dict[str, Any]]:
    """Check distance between decoupling caps and nearest IC power pin on the same net."""
    findings = []
    pads = doc.get("pads", [])
    comps_by_ref = {c["ref"]: c for c in doc.get("components", []) if c.get("ref")}

    # Group pads by net
    net_pads: dict[str, list[dict[str, Any]]] = {}
    for p in pads:
        net = p.get("net")
        if net:
            net_pads.setdefault(net, []).append(p)

    for net, plist in net_pads.items():
        net_upper = net.upper()
        # Skip ground net (GND return path is usually plane/pour, decap check focuses on power rails)
        if "GND" in net_upper or "VSS" in net_upper:
            continue

        c_pads = [p for p in plist if p.get("ref", "").startswith("C")]
        ic_pads = [p for p in plist if p.get("ref", "").startswith("U") or p.get("ref", "").startswith("IC")]

        if not c_pads or not ic_pads:
            continue

        for cp in c_pads:
            c_ref = cp.get("ref", "")
            dists = []
            for ip in ic_pads:
                d = math.hypot(cp["x_mm"] - ip["x_mm"], cp["y_mm"] - ip["y_mm"])
                dists.append((d, ip.get("ref", ""), ip.get("name", "")))
            dists.sort()
            min_dist, nearest_ic, pin_name = dists[0]

            if min_dist > max_dist_mm:
                findings.append({
                    "id": "decap_distance_excessive",
                    "severity": "warning",
                    "refs": [c_ref, nearest_ic],
                    "message": f"Decoupling cap {c_ref} on net '{net}' is {min_dist:.1f} mm away from nearest IC power pin ({nearest_ic}-{pin_name}). Recommended: <= 5 mm.",
                    "evidence": f"PcbDoc pad distance: {c_ref} ({cp['x_mm']}, {cp['y_mm']}) to {nearest_ic}-{pin_name} on net {net}",
                })

    return findings


def check_cpl_rotation_sanity(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Check CPL rotation sanity for polarized/asymmetric parts."""
    findings = []
    comps = doc.get("components", [])
    polarized = []
    non_orthogonal = []

    for c in comps:
        ref = c.get("ref", "")
        rot = float(c.get("rotation", 0.0))
        pattern = c.get("pattern", "")

        # Check orthogonal
        if abs(rot % 90.0) > 0.01 and abs(rot % 90.0 - 90.0) > 0.01:
            non_orthogonal.append((ref, rot))

        if ref.startswith(("U", "Q", "D")) or POLAR_PATTERNS.search(pattern):
            polarized.append(ref)

    if non_orthogonal:
        findings.append({
            "id": "cpl_rotation_non_orthogonal",
            "severity": "warning",
            "refs": [r for r, _ in non_orthogonal],
            "message": f"{len(non_orthogonal)} component(s) have non-orthogonal rotations ({', '.join(f'{r}:{rot:.1f}°' for r, rot in non_orthogonal[:5])}).",
            "evidence": "PcbDoc component ROTATION field",
        })

    if polarized:
        findings.append({
            "id": "cpl_rotation_sanity",
            "severity": "info",
            "refs": polarized,
            "message": f"{len(polarized)} polarized / IC component(s) require CPL rotation alignment verification against JLC 3D preview.",
            "evidence": "PcbDoc component package patterns and designators",
        })

    return findings


def check_board(doc_or_path: dict[str, Any] | str | pathlib.Path, outline_mm: list[float] | None = None, connector_specs: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run all board checks on a PcbDoc."""
    if isinstance(doc_or_path, (str, pathlib.Path)):
        doc = read_pcbdoc(doc_or_path)
    else:
        doc = doc_or_path

    bounds = compute_board_bounds(doc, outline_mm=outline_mm)
    findings = []
    findings.extend(check_edge_components(doc, bounds, connector_specs=connector_specs))
    findings.extend(check_decoupling_caps(doc))
    findings.extend(check_cpl_rotation_sanity(doc))

    return {
        "file": doc.get("file", ""),
        "findings": findings,
        "component_count": len(doc.get("components", [])),
        "pad_count": len(doc.get("pads", [])),
        "net_count": len(doc.get("nets", [])),
        "bounds_mm": bounds,
    }


def parse_placement_csv(text: str) -> list[dict[str, Any]]:
    """Parse an Altium Pick Place / CPL csv (Designator,Mid X,Mid Y,Layer,Rotation; values may carry 'mm')
    into component dicts {ref, x_mm, y_mm, layer, rotation} (the shape check_edge_components reads)."""
    import csv
    import io

    def num(v: str) -> float:
        return float(str(v).strip().lower().replace("mm", "") or 0.0)

    rows = []
    for r in csv.DictReader(io.StringIO(text.lstrip("﻿"))):
        key = {k.strip().lower(): v for k, v in r.items() if k}
        ref = (key.get("designator") or key.get("ref") or "").strip()
        if not ref:
            continue
        rows.append({"ref": ref, "x_mm": num(key.get("mid x", key.get("x", "0"))),
                     "y_mm": num(key.get("mid y", key.get("y", "0"))),
                     "layer": (key.get("layer") or "").strip(),
                     "rotation": num(key.get("rotation", "0"))})
    return rows


def check_connectors_from_placement(placement: list[dict[str, Any]], outline_mm: list[float],
                                    connector_specs: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Pure entry point of the connector-opening check for data that does not come from a PcbDoc:
    placement rows (see parse_placement_csv), board outline [x1, y1, x2, y2] in mm and per-connector
    specs {ref: {"wire_entry_dir_at_rot0": [x, y]}}. Returns only connector_faces_inward findings."""
    bounds = compute_board_bounds({}, outline_mm=outline_mm)
    res = check_edge_components({"components": placement}, bounds, connector_specs=connector_specs)
    return [f for f in res if f["id"] == "connector_faces_inward"]


def check_cpl_vs_model_rotation(cpl: list[dict[str, Any]], model_offsets: dict[str, float]) -> list[dict[str, Any]]:
    """Compare CPL rotations with the JLC 3D-model orientation. `model_offsets` maps designator to the
    angle (deg) by which JLC's model differs from our footprint. Any offset that is not a multiple of 360
    means the raw CPL rotation puts that part wrong in JLC's assembly preview, so it needs a correction.
    Returns one cpl_rotation_mismatch finding listing every such part present in the CPL."""
    by_ref = {c["ref"]: c for c in cpl}
    bad = []
    for ref, off in model_offsets.items():
        if ref in by_ref and abs(((float(off) + 180.0) % 360.0) - 180.0) > 0.01:
            bad.append((ref, float(by_ref[ref].get("rotation", 0.0)), float(off) % 360.0))
    if not bad:
        return []
    shown = ", ".join(f"{r} (CPL {c:.0f}, model offset {o:.0f})" for r, c, o in bad[:6])
    return [{"id": "cpl_rotation_mismatch", "severity": "error", "refs": [r for r, _, _ in bad],
             "message": f"{len(bad)} CPL rotation(s) disagree with the JLC 3D model orientation: {shown}"
                        + (" ..." if len(bad) > 6 else "") + ".",
             "evidence": "CPL rotation vs JLC model offset per part"}]


def main(argv=None):
    oscompat.utf8_stdio()
    ap = argparse.ArgumentParser(description="PcbDoc physical board review checks")
    ap.add_argument("pcb", help="Path to .PcbDoc file")
    ap.add_argument("--outline", nargs=4, type=float, metavar=("X1", "Y1", "X2", "Y2"), help="Board outline min_x min_y max_x max_y (mm)")
    ap.add_argument("--json", action="store_true", help="Print JSON findings")
    args = ap.parse_args(argv)

    res = check_board(args.pcb, outline_mm=args.outline)
    if args.json or True:
        print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
