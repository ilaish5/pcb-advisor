"""
Board-level DRC and physical layout checks on Altium PcbDoc files.

Checks performed:
1. Components near outline/edge:
   - Connectors: checks whether opening/wire entry faces the nearest board edge or inward toward center.
     The opening direction is the explicit spec (connector_specs: wire_entry_dir_at_rot0) when there is one,
     else it is derived from the footprint: a right-angle / edge connector's body overhangs toward its mating
     face, so the vector from the pads' centroid to the 3D body centre (or the silk/courtyard outline centre
     when the part has no body) is the opening. A part whose body is centred on its pads (pin header, U.FL,
     test point) has no direction and no finding. When nothing can be derived the result is an info finding,
     never an error from a guess. Only a derived or specified direction pointing inward is an error.
   - Outline clearance: components closer than 0.5 mm to any board edge.
2. Decoupling capacitors distance:
   - A decoupling cap is a small ceramic cap (0402-1206 pad span, not electrolytic/tantalum) with one pad on a
     ground net and the other on a power rail net. Its distance is measured to the nearest pad on that rail of a
     non-passive part (IC, connector). Debounce/filter caps (signal net to GND) and bulk caps are not decaps.
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

# Opening direction derived from the footprint: the body centre must sit at least this far from the pad centroid
# (absolute, and as a fraction of the body size along that axis) or the part has no direction. 1 mm / 20% keeps a
# U.FL receptacle (0.5 mm = 16%) and a centred terminal block (0.3-0.5 mm) direction-less while right-angle
# parts overhang their pads by 3-6 mm (35-50%).
OPENING_MIN_OFFSET_MM = 1.0
OPENING_MIN_OFFSET_FRAC = 0.2

# Decoupling caps
DECAP_MAX_DIST_MM = 3.0        # supply pin to its nearest same-net decoupling cap. General knowledge, no course source (owner 27/11); a
                              # datasheet or application-note value, cited by page, goes in `limits` and replaces it for that part
DECAP_MAX_PAD_SPAN_MM = 4.0    # pad centre to centre: 0402 ~1 mm, 0805 ~2 mm, 1206 ~3.2 mm; electrolytic/tantalum >= 6 mm
GROUND_NET = re.compile(r"GND|VSS|GROUND", re.I)
# +3V3 3V3 +3V3A +3V8 +12V +12V_RLY 5V 1V8 | VDD VCC VDDA AVDD VBAT VBUS VCAP1 VREF VIN VSYS, also as a suffix
# (SIM_VDD, USB_VBUS, MDM_USB_VBUS). Signal nets (BTN1, TC_P, NRST, OSC_IN, RF_ANT) do not match.
POWER_NET = re.compile(r"^[+-]?\d+V\d*[A-Z0-9_]*$|(?:^|_)[+-]?(?:[ADP]?V(?:DD|CC)|VBATT?|VBUS|VCAP|VREF|VIN|VSYS)", re.I)
POLARIZED_CAP = re.compile(r"ELEC|ELCO|TANT|POLAR|CPOL|ALUM|RADIAL|SUPERCAP|EEE", re.I)
# Parts that never supply a rail: the decap distance is measured to the nearest pad of anything else.
PASSIVE_REF = re.compile(r"^(?:R|C|L|D|FB|TP|LED|F|RN|RV)\d", re.I)
CAP_REF = re.compile(r"^C[A-Za-z]*\d")   # C1, CC2, Co2, COSC1


# JLC minimums (shared/reference/jlc/pcb-capabilities.en.md, "Drills, vias and annular ring", read 2026-10-14; P1 = capabilities page)
JLC_MIN_DRILL_MM = 0.15        # smallest drill, 2-layer and multilayer ordinary process
JLC_MIN_VIA_DIA_MM = 0.25      # via diameter at that drill; ring = (dia - hole) / 2 = 0.05
JLC_MIN_VIA_RING_MM = 0.05     # via ring follows the via diameter rule (diameter >= hole + 0.1), not the PTH ring
JLC_MIN_PTH_RING_MM = 0.15     # absolute min plated pad ring (multilayer 1 oz); 2-layer 1 oz is 0.18, 0.25 recommended
JLC_MIN_PTH_RING_2L_MM = 0.18
JLC_MIN_NPTH_MM = 0.50         # smallest non-plated hole
JLC_MIN_MASK_DAM_MM = 0.10     # smallest solder mask bridge, 1 oz green (pcb-capabilities)


def is_connector(comp: dict[str, Any]) -> bool:
    ref = comp.get("ref", "")
    pattern = comp.get("pattern", "")
    lib_ref = comp.get("lib_ref", "")
    if re.match(r"^D\d", ref, re.I):  # diode, even in an SMA package
        return False
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


def _box(value) -> list[float] | None:
    """A [x1, y1, x2, y2] bounding box from a PcbDoc component dict, or None when absent or malformed."""
    try:
        x1, y1, x2, y2 = (float(v) for v in value)
    except (TypeError, ValueError):
        return None
    return [x1, y1, x2, y2] if all(math.isfinite(v) for v in (x1, y1, x2, y2)) else None


def derive_opening_direction(comp: dict[str, Any], pads: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Direction a connector opens (mating face / wire entry), in board coordinates, from its footprint.

    A right-angle or edge connector's body overhangs the pads toward its mating face, so the opening is the
    direction from the pads' centroid to the centre of the component body (comp["body_bbox_mm"], the union of its
    3D bodies), or failing that of its silk/courtyard outline (comp["outline_bbox_mm"]). Board coordinates already
    include the placement rotation. Returns None when it cannot be derived (no pads, no body and no outline);
    otherwise {"dir": (dx, dy) unit vector or None, "offset_mm", "source", "pad_centroid", "body_centre"} where
    dir is None for a part without a direction (the body is centred on its pads: pin header, U.FL, test point)."""
    pts = [(float(p["x_mm"]), float(p["y_mm"])) for p in pads if "x_mm" in p and "y_mm" in p]
    if not pts:
        return None
    px = sum(x for x, _ in pts) / len(pts)
    py = sum(y for _, y in pts) / len(pts)
    for source, key in (("3D body", "body_bbox_mm"), ("outline", "outline_bbox_mm")):
        box = _box(comp.get(key))
        if box is None:
            continue
        bx, by = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
        dx, dy = bx - px, by - py
        offset = math.hypot(dx, dy)
        along, extent = (dx, box[2] - box[0]) if abs(dx) >= abs(dy) else (dy, box[3] - box[1])
        direction = None
        if abs(along) >= max(OPENING_MIN_OFFSET_MM, OPENING_MIN_OFFSET_FRAC * extent):
            direction = (dx / offset, dy / offset)
        return {"dir": direction, "offset_mm": offset, "source": source,
                "pad_centroid": (px, py), "body_centre": (bx, by)}
    return None


def check_edge_components(doc: dict[str, Any], bounds: tuple[float, float, float, float], connector_specs: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Check components near board outline, especially connector opening orientation.

    connector_specs {ref: {"wire_entry_dir_at_rot0": [x, y]}} gives an explicit opening direction (at rotation 0,
    rotated by the component's rotation). A connector without one has its direction derived from the footprint
    (see derive_opening_direction); when that is impossible it is listed in one info finding, never guessed."""
    min_x, min_y, max_x, max_y = bounds
    findings = []
    comps = doc.get("components", [])
    specs = connector_specs or {}
    pads_by_ref: dict[str, list[dict[str, Any]]] = {}
    for p in doc.get("pads", []):
        if p.get("ref"):
            pads_by_ref.setdefault(p["ref"], []).append(p)
    unknown: list[str] = []

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
            spec_entry = (specs.get(ref) or {}).get("wire_entry_dir_at_rot0")
            derived = None
            if spec_entry is not None:
                # Explicit spec: direction of wire entry at rotation 0, rotated by the component rotation
                theta = math.radians(rot_deg)
                entry_x = math.cos(theta) * spec_entry[0] - math.sin(theta) * spec_entry[1]
                entry_y = math.sin(theta) * spec_entry[0] + math.cos(theta) * spec_entry[1]
            else:
                derived = derive_opening_direction(c, pads_by_ref.get(ref, []))
                if derived is None:
                    unknown.append(ref)
                    continue
                if derived["dir"] is None:
                    continue  # body centred on its pads: no opening direction, nothing to check
                entry_x, entry_y = derived["dir"]

            # Dot product with outward normal of nearest edge
            dot = entry_x * outward_normal[0] + entry_y * outward_normal[1]

            # If dot < -0.1, the opening points away from the nearest edge (toward the inside of the board)
            if dot < -0.1:
                if derived is None:
                    how = ""
                    evidence = f"PcbDoc position ({x:.2f}, {y:.2f}), rotation {rot_deg:.0f} deg, facing vector ({entry_x:.2f}, {entry_y:.2f}) vs outward normal {outward_normal}"
                else:
                    how = f" (direction derived from the {derived['source']} geometry; verify it in the 3D view)"
                    bdx = derived["body_centre"][0] - derived["pad_centroid"][0]
                    bdy = derived["body_centre"][1] - derived["pad_centroid"][1]
                    evidence = (f"PcbDoc position ({x:.2f}, {y:.2f}); {derived['source']} centre is ({bdx:+.2f}, {bdy:+.2f}) mm "
                                f"from the pad centroid, so the opening faces ({entry_x:.2f}, {entry_y:.2f}) vs outward normal {outward_normal}")
                findings.append({
                    "id": "connector_faces_inward",
                    "severity": "error",
                    "refs": [ref],
                    "message": f"Connector {ref} opening faces inward toward the board center instead of the nearest ({nearest_edge}) edge.{how}",
                    "evidence": evidence,
                })

    if unknown:
        findings.append({
            "id": "connector_direction_unknown",
            "severity": "info",
            "refs": unknown,
            "message": f"The opening direction of {len(unknown)} connector(s) could not be derived (no 3D body or outline in the PcbDoc, no spec): verify the opening direction in the 3D view.",
            "evidence": "PcbDoc component has no body_bbox_mm / outline_bbox_mm and connector_specs gives no wire_entry_dir_at_rot0",
        })

    return findings


def _is_passive(comp: dict[str, Any], n_pads: int) -> bool:
    """R/C/L/FB/D/LED/TP/fuse by designator, or a non-connector with at most two pads whose custom designator
    starts with one of those letters (RL2, DI1, Co2, Crst1). Never a supplied load."""
    ref = comp.get("ref", "")
    return bool(PASSIVE_REF.match(ref)) or (ref[:1].upper() in "RCLDFT" and n_pads <= 2 and not is_connector(comp))


_SUPPLY_NAME = re.compile(r"^(?:[ADP]?V(?:DD|CC|IN|BUS|BAT|BATT|CCA|DDA|DDIO\d*|DDUSB|DDSD|REF\+?|CAP|\d)|VIN|VOUT|VO|\+?\d+V\d*|VS\+?|VP)[A-Z0-9_/+]*$", re.I)
_NOT_A_LOAD = re.compile(r"^(?:SW|S|K|RL|Q|TP|F|FB|LED|BZ)\d", re.I)       # a switch, relay, transistor or test point is no supplied chip
_CARD = re.compile(r"sd|sim|card|mmc|tf_|micro_?sd", re.I)


def pin_function(q, pin_names=None):
    """The function name of pad q: the symbol or netlist pin name (`pin_names[ref][pad number]`, or a `pin_name` on the pad) first, else the
    pad's own name when that is a name and not a number. '' when nothing says what the pin is (a PcbDoc pad is usually only a number)."""
    ref = q.get("ref")
    num = str(q.get("name") or q.get("num") or "").strip()
    given = str(q.get("pin_name") or ((pin_names or {}).get(ref) or {}).get(num) or "").strip()
    if given and given != num:
        return given
    if num and not num.isdigit() and len(num) > 1:
        return num
    return ""


def _supply_pin(q, comp, comp_pads, net, pin_names=None):
    """Is pad q a supply pin of an IC or a card connector? Not on a plain header, a relay coil or a one-pad net part. Decided only by the pin's
    function name (VDD, VCC, VBAT, VDDA, VREF+...) taken from the symbol or netlist; membership of a power net says nothing (a switch, a
    flash CS pin or a relay pin can sit on a rail). Returns True, False, or None when the pin's function is not known."""
    if len(comp_pads) < 3 or (is_connector(comp) and not _CARD.search(f"{comp.get('pattern', '')} {comp.get('lib_ref', '')}")):
        return False
    name = pin_function(q, pin_names)
    if not name:
        return None
    return bool(_SUPPLY_NAME.match(name))


def check_decoupling_caps(doc: dict[str, Any], max_dist_mm: float = DECAP_MAX_DIST_MM,
                          max_pad_span_mm: float = DECAP_MAX_PAD_SPAN_MM,
                          limits: dict[str, tuple[float, str]] | None = None,
                          pin_names: dict[str, dict[str, str]] | None = None) -> list[dict[str, Any]]:
    """Per supply pin: the distance from each supply pin of an IC or card connector to the nearest decoupling cap on its net (R2/W23).

    A supply pin is a pad of a part that is not a passive, on a power rail net. A decoupling cap is a two-pad capacitor with one pad on a
    ground net and the other on that rail (bulk or ceramic: the nearest one on the net is the one measured). A pin whose
    nearest such cap is farther than the limit, or that has none on its net, is flagged (one finding per pin, so a second pin of the same
    part is never hidden by the first). The limit is `limits[ref] = (mm, cite)` where the part's datasheet or application note gives one
    (cited by page), else max_dist_mm, labelled as general knowledge. Caps from a signal net to ground (button debounce, input filters,
    crystal loads) are not decaps."""
    findings = []
    comps = [c for c in doc.get("components", []) if c.get("ref")]
    comps_by_ref = {c["ref"]: c for c in comps}
    pads_by_ref: dict[str, list[dict[str, Any]]] = {}
    net_pads: dict[str, list[dict[str, Any]]] = {}
    for p in doc.get("pads", []):
        if p.get("ref"):
            pads_by_ref.setdefault(p["ref"], []).append(p)
        if p.get("net"):
            net_pads.setdefault(p["net"], []).append(p)

    caps: dict[str, list[tuple[str, dict[str, Any]]]] = {}       # rail net -> [(cap ref, its rail pad)]
    for c in comps:
        c_ref = c["ref"]
        if not CAP_REF.match(c_ref) or is_connector(c):
            continue
        cpads = pads_by_ref.get(c_ref, [])
        if len(cpads) != 2:
            continue                  # any two-pad capacitor between the rail and ground counts: the check measures the nearest cap, whatever its kind
        ground = [p for p in cpads if GROUND_NET.search(p.get("net") or "")]
        rail = [p for p in cpads if p.get("net") and not GROUND_NET.search(p["net"]) and POWER_NET.search(p["net"])]
        if len(ground) == 1 and len(rail) == 1:
            caps.setdefault(rail[0]["net"], []).append((c_ref, rail[0]))

    unknown: dict[str, list[str]] = {}
    for net, pads in sorted(net_pads.items()):
        if GROUND_NET.search(net) or not POWER_NET.search(net):
            continue
        for q in pads:
            ref = q.get("ref")
            if ref not in comps_by_ref or _is_passive(comps_by_ref[ref], len(pads_by_ref.get(ref, []))):
                continue
            is_supply = _supply_pin(q, comps_by_ref[ref], pads_by_ref.get(ref, []), net, pin_names)
            if is_supply is None:
                if not _NOT_A_LOAD.match(ref):
                    unknown.setdefault(ref, []).append(net)
                continue
            if not is_supply:
                continue
            limit, cite = (limits or {}).get(ref) or (max_dist_mm, "general knowledge, no course source")
            near = sorted(((math.hypot(cp["x_mm"] - q["x_mm"], cp["y_mm"] - q["y_mm"]), cref, cp) for cref, cp in caps.get(net, [])),
                          key=lambda t: t[0])
            where = f"{ref}-{q.get('name') or q.get('num') or ''}"
            if not near:
                findings.append({
                    "id": "decap_distance_excessive", "severity": "warning", "refs": [ref],
                    "message": f"Supply pin {where} on net '{net}' has no decoupling cap on that net. Recommended: <= {limit:g} mm ({cite}).",
                    "evidence": f"PcbDoc: no ceramic cap from {net} to ground; pin at ({q['x_mm']}, {q['y_mm']})"})
                continue
            dist, cref, cp = near[0]
            if dist > limit:
                findings.append({
                    "id": "decap_distance_excessive", "severity": "warning", "refs": [cref, ref],
                    "message": f"Supply pin {where} on net '{net}': the nearest decoupling cap {cref} is {dist:.1f} mm away. Recommended: <= {limit:g} mm ({cite}).",
                    "evidence": f"PcbDoc pad distance: {cref} ({cp['x_mm']}, {cp['y_mm']}) to {where} on net {net}"})

    for ref, nets in sorted(unknown.items()):
        findings.append({
            "id": "decap_not_checked", "severity": "info", "refs": [ref],
            "message": f"Decoupling not checked for {ref}: its pads on {', '.join(sorted(set(nets)))} carry numbers only and no symbol or netlist pin "
                       "name was given, so it is not known which of them are supply pins.",
            "evidence": "PcbDoc pad names are numbers; pass the pin names from the schematic netlist"})

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


def outline_bbox_containing_parts(path, doc: dict[str, Any], findings: list) -> list[float] | None:
    """The board shape's bbox from the PcbDoc, used only when it holds the parts: a file whose shape was never
    set keeps Altium's default rectangle, and the pad estimate is the better guess there."""
    import preview_pcb
    pts = preview_pcb.get_board_outline(path)
    comps = [c for c in doc.get("components", []) if "x_mm" in c]
    if not pts or not comps:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    box = [min(xs), min(ys), max(xs), max(ys)]
    inside = sum(box[0] <= c["x_mm"] <= box[2] and box[1] <= c["y_mm"] <= box[3] for c in comps)
    if inside >= 0.9 * len(comps):
        return box
    findings.append({
        "id": "board_shape_does_not_hold_parts", "severity": "info", "refs": [],
        "message": f"Only {inside} of {len(comps)} parts lie inside the board shape; edge checks use the pad "
                   "extent instead. Set the board shape (Design > Board Shape) before the edge checks mean much.",
        "evidence": f"board shape bbox {[round(v, 2) for v in box]} mm"})
    return None

def check_board(doc_or_path: dict[str, Any] | str | pathlib.Path, outline_mm: list[float] | None = None,
                connector_specs: dict[str, Any] | None = None,
                decap_max_dist_mm: float = DECAP_MAX_DIST_MM, library_stale: bool | None = None,
                decap_limits: dict[str, tuple[float, str]] | None = None,
                pin_names: dict[str, dict[str, str]] | None = None) -> dict[str, Any]:
    """Run all board checks on a PcbDoc (a path, or a read_pcbdoc dict; footprint geometry comes from
    read_pcbdoc(path, geometry=True), i.e. body_bbox_mm / outline_bbox_mm on each component)."""
    findings = []
    if isinstance(doc_or_path, (str, pathlib.Path)):
        doc = read_pcbdoc(doc_or_path, geometry=True)
        if outline_mm is None:
            outline_mm = outline_bbox_containing_parts(doc_or_path, doc, findings)
    else:
        doc = doc_or_path

    bounds = compute_board_bounds(doc, outline_mm=outline_mm)
    findings.extend(check_edge_components(doc, bounds, connector_specs=connector_specs))
    findings.extend(check_decoupling_caps(doc, max_dist_mm=decap_max_dist_mm, limits=decap_limits, pin_names=pin_names))
    findings.extend(check_cpl_rotation_sanity(doc))
    findings.extend(check_drills(doc))
    findings.extend(check_footprint_rules(doc, library_stale))

    return {
        "file": doc.get("file", ""),
        "findings": findings,
        "component_count": len(doc.get("components", [])),
        "pad_count": len(doc.get("pads", [])),
        "net_count": len(doc.get("nets", [])),
        "bounds_mm": bounds,
    }


def check_drills(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Per via and drilled pad against the JLC minimums above: hole too small, ring too thin, plated pad with no
    ring (copper not larger than the hole). The reader gives no slot shape, so slots are not checked."""
    out = []

    def add(id_, ref, msg, evidence):
        out.append({"id": id_, "severity": "error", "refs": [ref] if ref else [], "message": msg, "evidence": evidence})

    for p in doc.get("drilled_pads") or []:
        hole, size, plated = p.get("hole_mm") or 0, p.get("min_size_mm") or 0, bool(p.get("plated"))
        who = f"{p.get('ref') or '?'}-{p.get('name') or '?'}"
        where = f"at ({p.get('x_mm')}, {p.get('y_mm')}) mm"
        ev = f"hole {hole:g} mm, copper {size:g} mm, {'plated' if plated else 'unplated'}"
        if plated:
            if hole < JLC_MIN_DRILL_MM:
                add("drill_too_small", p.get("ref"), f"{who} {where}: hole {hole:g} mm is below the JLC minimum drill {JLC_MIN_DRILL_MM:g} mm.", ev)
            ring = round((size - hole) / 2, 4)
            if size <= hole:
                add("plated_pad_no_ring", p.get("ref"), f"{who} {where}: plated pad has no copper ring (copper {size:g} mm, hole {hole:g} mm); JLC cannot plate it.", ev)
            elif ring < JLC_MIN_PTH_RING_MM:
                add("annular_ring_too_thin", p.get("ref"), f"{who} {where}: annular ring {ring:g} mm is below the JLC minimum {JLC_MIN_PTH_RING_MM:g} mm.", ev)
            elif ring < JLC_MIN_PTH_RING_2L_MM:
                out.append({"id": "annular_ring_thin_2layer", "severity": "warning", "refs": [p["ref"]] if p.get("ref") else [],
                            "message": f"{who} {where}: annular ring {ring:g} mm is below the 2-layer minimum {JLC_MIN_PTH_RING_2L_MM:g} mm (multilayer minimum {JLC_MIN_PTH_RING_MM:g} mm).", "evidence": ev})
        elif hole < JLC_MIN_NPTH_MM:
            add("npth_too_small", p.get("ref"), f"{who} {where}: unplated hole {hole:g} mm is below the JLC minimum {JLC_MIN_NPTH_MM:g} mm.", ev)
    for v in doc.get("vias") or []:
        hole, dia = v.get("hole_mm") or 0, v.get("dia_mm") or 0
        where = f"via at ({v.get('x_mm')}, {v.get('y_mm')}) mm" + (f" net {v['net']}" if v.get("net") else "")
        ev = f"hole {hole:g} mm, diameter {dia:g} mm"
        if hole < JLC_MIN_DRILL_MM:
            add("drill_too_small", None, f"{where}: hole {hole:g} mm is below the JLC minimum drill {JLC_MIN_DRILL_MM:g} mm.", ev)
        if dia < JLC_MIN_VIA_DIA_MM:
            add("via_too_small", None, f"{where}: diameter {dia:g} mm is below the JLC minimum {JLC_MIN_VIA_DIA_MM:g} mm.", ev)
        elif round((dia - hole) / 2, 4) < JLC_MIN_VIA_RING_MM:
            add("annular_ring_too_thin", None, f"{where}: ring {round((dia - hole) / 2, 4):g} mm is below the JLC via minimum {JLC_MIN_VIA_RING_MM:g} mm.", ev)
    return out


def _rule_mm(doc, kind, attr, scope_has=None):
    """The value in mm of a board rule attribute ('10mil', '0.254mm'), the strictest (largest) one for annular ring / sliver, or None."""
    vals = []
    for r in doc.get("rules") or []:
        if r.get("RULEKIND") != kind or str(r.get("ENABLED", "TRUE")).upper() != "TRUE":
            continue
        if scope_has and scope_has.lower() not in str(r.get("SCOPE1EXPRESSION", "")).lower():
            continue
        m = re.fullmatch(r"\s*(-?[\d.]+)\s*(mil|mm|um)?\s*", str(r.get(attr, "")))
        if m:
            v = float(m.group(1))
            vals.append(v * {"mil": 0.0254, "um": 0.001}.get(m.group(2), 1.0))
    return max(vals) if vals else None


def _pad_box(p):
    sx, sy = p.get("sx_mm") or 0, p.get("sy_mm") or 0
    if round(float(p.get("rot") or 0)) % 180 == 90:
        sx, sy = sy, sx
    return p["x_mm"] - sx / 2, p["y_mm"] - sy / 2, p["x_mm"] + sx / 2, p["y_mm"] + sy / 2


def check_footprint_rules(doc: dict[str, Any], library_stale: bool | None = None) -> list[dict[str, Any]]:
    """What the footprints of the board cannot meet of the board's OWN rules (the rules the JLC preset imported), found in the saved
    file before Altium's design rule check says so: (1) a plated pad whose ring is thinner than the Minimum Annular Ring rule for pads;
    (2) top-layer pads so close that the mask dam left between their openings (gap minus twice the Solder Mask Expansion) is below the
    Minimum Solder Mask Sliver rule. Both come from the part's footprint, not from the routing, so each finding names the part and a
    way forward. Silently nothing when the file has no such rule."""
    out = []
    ring_rule = _rule_mm(doc, "MinimumAnnularRing", "MINIMUMRING", "IsPad")
    if ring_rule is not None:
        bad = {}
        for p in doc.get("drilled_pads") or []:
            hole, size = p.get("hole_mm") or 0, p.get("min_size_mm") or 0
            if not p.get("plated") or size <= hole:
                continue                       # (no ring at all is check_drills' error)
            ring = (size - hole) / 2
            if ring < ring_rule - 1e-4:
                bad.setdefault(p.get("ref") or "?", []).append((p, ring))
        for ref, rows in sorted(bad.items()):
            p0, ring = rows[0]
            hole = p0.get("hole_mm") or 0
            need = round(hole + 2 * ring_rule, 3)
            names = ", ".join(str(p.get("name") or "?") for p, _ in rows[:6])
            out.append({"id": "footprint_ring_below_rule", "severity": "warning", "refs": [ref],
                        "message": (f"{ref}: pad(s) {names} have an annular ring of {ring:.3f} mm, below the board's rule {ring_rule:.3f} mm "
                                    f"(JLC itself needs {JLC_MIN_PTH_RING_MM:g} mm); it is the footprint that comes with the part (LCSC / EasyEDA), "
                                    f"not the routing. Way forward: enlarge the copper of those pads to at least {need:g} mm in the PcbLib "
                                    f"footprint (hole {hole:g} mm), choose a part whose footprint has larger pads, or accept it knowing JLC can make "
                                    f"it and Altium's design rule check will keep reporting it"),
                        "evidence": f"ring {ring:.3f} mm < rule {ring_rule:.3f} mm"})
    sliver = _rule_mm(doc, "MinimumSolderMaskSliver", "MINSOLDERMASKWIDTH")
    exp = _rule_mm(doc, "SolderMaskExpansion", "EXPANSION") or 0.0
    if sliver is not None:
        pads = [p for p in doc.get("pads") or [] if p.get("layer") == 1 and p.get("x_mm") is not None and p.get("ref")]
        boxes = [(p, _pad_box(p)) for p in pads]
        bad = {}
        for i, (a, ba) in enumerate(boxes):
            for b, bb in boxes[i + 1:]:
                if a["ref"] != b["ref"]:
                    continue                   # between parts is placement, within one part is the footprint
                dx = max(bb[0] - ba[2], ba[0] - bb[2], 0.0)
                dy = max(bb[1] - ba[3], ba[1] - bb[3], 0.0)
                gap = math.hypot(dx, dy)
                dam = gap - 2 * exp
                if 0 < gap and 0 < dam < sliver - 1e-4:
                    bad.setdefault(a["ref"], []).append((dam, gap))
        for ref, rows in sorted(bad.items()):
            dam, gap = min(rows)
            ok_exp = max(round((gap - sliver) / 2, 3), 0.0)
            out.append({"id": "footprint_mask_sliver", "severity": "warning", "refs": [ref],
                        "message": (f"{ref}: {len(rows)} pad pair(s) leave a solder mask dam of only {dam:.3f} mm (pad gap {gap:.3f} mm minus "
                                    f"2 x the {exp:g} mm mask expansion), below the board's rule {sliver:.3f} mm"
                                    + (f" and JLC's {JLC_MIN_MASK_DAM_MM:g} mm" if dam < JLC_MIN_MASK_DAM_MM
                                       else f" (JLC's own minimum {JLC_MIN_MASK_DAM_MM:g} mm is met: the rule is the preset's stricter value)")
                                    + f". It is the fine pitch of the footprint (comes with the part), not the routing. Way forward: give those pads "
                                      f"a smaller Solder Mask Expansion in the footprint (at most {ok_exp:g} mm per side keeps the dam), or choose a "
                                      f"part with a wider pad pitch"),
                        "evidence": f"dam {dam:.3f} mm < rule {sliver:.3f} mm"})
    out.extend(check_silk_to_mask(doc, library_stale))
    return out


SILK_LAYER = 33                # Top Overlay in the PcbDoc layer numbering
_SILK_STEP_MM = 0.02           # silk is sampled this finely when its distance to a mask opening is measured


def _top_overlay_points(doc: dict[str, Any]):
    """[(kind, sample points, half width mm)] of every top-overlay line and arc of a read board (design text is left out: its glyph
    strokes are not in the file, a box around them would claim more than Altium measures)."""
    out = []
    for t in doc.get("tracks") or []:
        if t.get("layer") != SILK_LAYER:
            continue
        x1, y1, x2, y2 = t["x1_mm"], t["y1_mm"], t["x2_mm"], t["y2_mm"]
        n = max(1, math.ceil(math.hypot(x2 - x1, y2 - y1) / _SILK_STEP_MM))
        out.append(("line", [(x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n) for i in range(n + 1)], (t.get("width_mm") or 0) / 2))
    for a in doc.get("arcs") or []:
        if a.get("layer") != SILK_LAYER:
            continue
        a1, a2 = a["a1"], a["a2"]
        if a2 <= a1:
            a2 += 360.0
        r = a["r_mm"]
        n = max(2, math.ceil(math.radians(a2 - a1) * r / _SILK_STEP_MM))
        out.append(("arc", [(a["cx_mm"] + r * math.cos(math.radians(a1 + (a2 - a1) * i / n)),
                             a["cy_mm"] + r * math.sin(math.radians(a1 + (a2 - a1) * i / n))) for i in range(n + 1)],
                    (a.get("width_mm") or 0) / 2))
    return out


def _mask_gap(px: float, py: float, p: dict[str, Any], exp: float) -> float:
    """Distance in mm from a point to the mask opening of a top pad: its copper grown by the mask expansion (a round pad as a
    circle, an oval as a capsule, anything else as the rectangle of its size, turned as the pad is)."""
    hx, hy = (p.get("sx_mm") or 0) / 2 + exp, (p.get("sy_mm") or 0) / 2 + exp
    a = math.radians(-(p.get("rot") or 0.0))
    dx, dy = px - p["x_mm"], py - p["y_mm"]
    u, v = dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a)
    if p.get("shape") == 1:                                 # round / oval: a capsule along the longer side
        r = min(hx, hy)
        along = max(hx, hy) - r
        if hx >= hy:
            u = max(abs(u) - along, 0.0)
            v = abs(v)
        else:
            v = max(abs(v) - along, 0.0)
            u = abs(u)
        return max(math.hypot(u, v) - r, 0.0)
    return math.hypot(max(abs(u) - hx, 0.0), max(abs(v) - hy, 0.0))


def _seg_dist(p, a, b):
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    n = dx * dx + dy * dy
    t = 0.0 if n == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / n))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)


def check_silk_to_mask(doc: dict[str, Any], library_stale: bool | None = None) -> list[dict[str, Any]]:
    """Top silkscreen lines and arcs closer than the board's Silk To Solder Mask rule to (a) a pad's mask opening or (b) routed
    top-layer copper (a track or a via, grown by the Solder Mask Expansion: Altium's design rule check counts both, the 35 vias of
    the third live STM32 run match this to the piece), found in the saved file before Altium's check says so. (a) is the silkscreen
    drawn in the part's footprint, which the project library's converter cuts back from the pads (partlib_convert.SILK_TO_COPPER_MIL).
    Only a library built by older converter code (library_stale True: partlib.converter_stale(project), the converter fingerprint
    only, not file times) is told to rebuild; with a current one (False) the board may hold old footprint copies (update them
    from the library) and only a finding that stays means the library's own silk is too close; unknown (None) makes no claim. (b) is the routing running under a part's silkscreen. One finding per
    part and source. A piece's gap is its edge to the opening; the count is (piece, copper object) pairs (Altium lists fewer: do not
    compare the two numbers). The rule is the enabled Silk To Solder Mask rule of the highest priority (lowest PRIORITY number; the
    strictest value on a tie): a board carries the preset's 6 mil rule and Altium's own 10 mil one for pads at priority 2, and the
    third live run counted 0 under the 10 mil one. Silently nothing when the file has no such rule."""
    rules = []
    for rec in doc.get("rules") or []:
        if rec.get("RULEKIND") == "SilkToSolderMaskClearance" and str(rec.get("ENABLED", "TRUE")).upper() == "TRUE":
            m = re.fullmatch(r"\s*(-?[\d.]+)\s*(mil|mm|um)?\s*", str(rec.get("MINSILKSCREENTOMASKGAP", "")))
            if m:
                prio = str(rec.get("PRIORITY") or "99")
                rules.append((int(prio) if prio.isdigit() else 99, -float(m.group(1)) * {"mil": 0.0254, "um": 0.001}.get(m.group(2), 1.0)))
    if not rules:
        return []
    gap_rule = -min(rules)[1]
    exp = _rule_mm(doc, "SolderMaskExpansion", "EXPANSION") or 0.0
    pads = [p for p in doc.get("pads") or [] if p.get("layer") in (1, 74) and p.get("x_mm") is not None]
    tracks = [t for t in doc.get("tracks") or [] if t.get("layer") == 1]
    vias = [v for v in doc.get("vias") or [] if v.get("from_layer") == 1 and v.get("x_mm") is not None]
    comps = [c for c in doc.get("components") or [] if c.get("outline_bbox_mm")]
    reach = gap_rule + exp + 0.5                            # nothing farther than this from a piece can be within the rule of it
    bad: dict[tuple[str, str], list[tuple[float, str]]] = {}
    for _kind, pts, hw in _top_overlay_points(doc):
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        x0, x1, y0, y1 = min(xs) - reach, max(xs) + reach, min(ys) - reach, max(ys) + reach
        mx, my = pts[len(pts) // 2]
        owner, best = "?", None
        for c in comps:                                     # the part whose silk box holds the piece (smallest box wins)
            b = c["outline_bbox_mm"]
            if b[0] - 0.01 <= mx <= b[2] + 0.01 and b[1] - 0.01 <= my <= b[3] + 0.01:
                area = (b[2] - b[0]) * (b[3] - b[1])
                if best is None or area < best:
                    best, owner = area, c["ref"]
        hits = []
        for p in pads:
            r = max(p.get("sx_mm") or 0, p.get("sy_mm") or 0)
            if x0 - r <= p["x_mm"] <= x1 + r and y0 - r <= p["y_mm"] <= y1 + r:
                hits.append(("pad", min(_mask_gap(x, y, p, exp) for x, y in pts) - hw, f"pad {p.get('ref') or '?'}-{p.get('name')}"))
        for t in tracks:
            if (max(t["x1_mm"], t["x2_mm"]) < x0 or min(t["x1_mm"], t["x2_mm"]) > x1
                    or max(t["y1_mm"], t["y2_mm"]) < y0 or min(t["y1_mm"], t["y2_mm"]) > y1):
                continue
            g = min(_seg_dist(p, (t["x1_mm"], t["y1_mm"]), (t["x2_mm"], t["y2_mm"])) for p in pts) - hw - (t.get("width_mm") or 0) / 2 - exp
            hits.append(("routed", g, f"a track of net {t.get('net') or '-'}"))
        for v in vias:
            if x0 <= v["x_mm"] <= x1 and y0 <= v["y_mm"] <= y1:
                g = min(math.hypot(x - v["x_mm"], y - v["y_mm"]) for x, y in pts) - hw - (v.get("dia_mm") or 0) / 2 - exp
                hits.append(("routed", g, f"a via of net {v.get('net') or '-'}"))
        for src, g, what in hits:
            if g < gap_rule - 1e-4:
                bad.setdefault((owner, src), []).append((g, what))
    out = []
    for (ref, src), rows in sorted(bad.items()):
        worst, what = min(rows)
        refs = [ref] if ref != "?" else []
        if src == "pad":
            out.append({"id": "footprint_silk_to_mask", "severity": "warning", "refs": refs,
                        "message": (f"{ref}: {len(rows)} silkscreen piece/pad pair(s) of its footprint come closer than the board's Silk To "
                                    f"Solder Mask rule {gap_rule:.3f} mm to a mask opening (worst {max(worst, 0.0):.3f} mm, at {what}, "
                                    f"with the {exp:g} mm mask expansion counted); Altium's design rule check reports these. The silkscreen is"
                                    f" drawn in the part's footprint, not by the placement. Way forward: " + (
                                        "rebuild the project library (the library was built by older converter code, which did not cut "
                                        "the silk back far enough from the pads), or delete those silk lines in the PcbLib footprint"
                                        if library_stale else
                                        "the library was built by the current converter, but the board may still hold old copies of "
                                        "the footprints: update the board's footprints from the library (place the parts again, or "
                                        "Design > Update from PCB Libraries). If the finding stays, the footprint in the library itself "
                                        "is too close: edit or delete those silk lines in the PcbLib footprint"
                                        if library_stale is False else
                                        "update the board's footprints from the library if the board holds old copies (place the parts "
                                        "again, or Design > Update from PCB Libraries); if the finding stays, edit or delete those silk "
                                        "lines in the PcbLib footprint")),
                        "evidence": f"silk to mask {max(worst, 0.0):.3f} mm < rule {gap_rule:.3f} mm"})
        else:
            out.append({"id": "silk_over_routed_copper", "severity": "warning", "refs": refs,
                        "message": (f"{ref}: {len(rows)} silkscreen piece/copper pair(s) of its footprint come closer than the board's Silk "
                                    f"To Solder Mask rule {gap_rule:.3f} mm to routed top-layer copper (worst {max(worst, 0.0):.3f} mm, "
                                    f"{what}); Altium's design rule check counts silk over a track or via as well. It is the routing "
                                    f"running under the part's silkscreen. Way forward: move the track or via off the silk outline, "
                                    f"or remove that silk line from the footprint"),
                        "evidence": f"silk to routed copper {max(worst, 0.0):.3f} mm < rule {gap_rule:.3f} mm"})
    return out


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
    ap.add_argument("--decap-max-mm", type=float, default=DECAP_MAX_DIST_MM, help=f"Max decoupling cap distance to the supplied pad (default {DECAP_MAX_DIST_MM:g} mm)")
    ap.add_argument("--design", help="The design to compare the board with: a project name, its folder or netlist folder "
                                     "(adds design_* findings: a net or part the board lacks)")
    args = ap.parse_args(argv)

    stale = None
    if args.design:
        try:
            import partlib
            stale = partlib.converter_stale(pathlib.Path(args.design).name)      # a project name, or its folder
        except Exception:
            stale = None
    res = check_board(args.pcb, outline_mm=args.outline, decap_max_dist_mm=args.decap_max_mm, library_stale=stale)
    if args.design:
        from checks import schematic
        res["findings"].extend(schematic.design_vs_board(args.design, args.pcb))
    if args.json or True:
        print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
