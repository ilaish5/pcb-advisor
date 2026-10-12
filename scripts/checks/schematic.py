"""
Schematic netlist builder and review checks.

Extracts netlists:
1. From PcbDoc pads (pad_net_map)
2. From SchDoc wire/label/port geometry join

Checks performed:
1. Single-pin nets
2. Unconnected IC power pins
3. Nets only by label on one sheet
4. Pins whose name indicates VCC/VDD/GND but net differs

JSON findings schema:
    [{"id": str, "severity": "error"|"warning"|"info", "refs": list[str], "message": str, "evidence": str}]
"""
import argparse
import collections
import json
import pathlib
import re
import sys
from typing import Any

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import oscompat  # noqa: E402
from altium.pcbdoc import pad_net_map, read_pcbdoc  # noqa: E402
from altium.schdoc import read_schdoc  # noqa: E402

POWER_PIN_RE = re.compile(r"^(?:VCC|VDD|VIN|VBAT|VREF|VDDA|VSS|VSSA|GND|AGND|DGND|3V3|5V|12V)\b", re.I)
GND_RE = re.compile(r"GND|VSS|0V|AGND|DGND", re.I)
VCC_RE = re.compile(r"VCC|VDD|VIN|VBAT|VDDA|3V3|5V|12V|\+3V3|\+5V", re.I)


class UnionFind:
    def __init__(self):
        self.parent: dict[Any, Any] = {}

    def find(self, i):
        if i not in self.parent:
            self.parent[i] = i
            return i
        if self.parent[i] != i:
            self.parent[i] = self.find(self.parent[i])
        return self.parent[i]

    def union(self, i, j):
        root_i = self.find(i)
        root_j = self.find(j)
        if root_i != root_j:
            self.parent[root_i] = root_j


def pin_hot_spot(pin: dict[str, Any]) -> tuple[int, int]:
    """Calculate the electrical connection hot spot of a schematic pin."""
    x, y = int(pin.get("x", 0)), int(pin.get("y", 0))
    length = int(pin.get("length", 0))
    ori = int(pin.get("orientation", 0)) & 3
    if ori == 0:
        return (x + length, y)
    elif ori == 1:
        return (x, y + length)
    elif ori == 2:
        return (x - length, y)
    elif ori == 3:
        return (x, y - length)
    return (x, y)


def point_on_segment(pt: tuple[int, int], p1: tuple[int, int], p2: tuple[int, int]) -> bool:
    """Return True if point pt lies on the line segment between p1 and p2."""
    x, y = pt
    x1, y1 = p1
    x2, y2 = p2
    if min(x1, x2) <= x <= max(x1, x2) and min(y1, y2) <= y <= max(y1, y2):
        # Collinear check: (x - x1) * (y2 - y1) == (y - y1) * (x2 - x1)
        return (x - x1) * (y2 - y1) == (y - y1) * (x2 - x1)
    return False


def build_schdoc_sheet_netlist(sheet_doc: dict[str, Any]) -> dict[str, Any]:
    """
    Build connected nets for a single SchDoc sheet using 2D geometry join.
    Returns:
        {
            "nets": {net_name: [f"{ref}-{pin_num}", ...]},
            "pin_net_map": {f"{ref}-{pin_num}": net_name},
            "net_labels": {net_name: list_of_labels},
            "power_ports": {net_name: list_of_power_ports},
            "ports": {net_name: list_of_ports},
            "components": sheet_doc.get("components", []),
            "sheet_name": sheet_doc.get("file", "Sheet"),
        }
    """
    sheet_name = sheet_doc.get("file", "Sheet")
    uf = UnionFind()
    wire_segments = []

    # 1. Register wire vertices and segments
    for w in sheet_doc.get("wires", []):
        pts = [tuple(p) for p in w.get("points", [])]
        for i in range(len(pts) - 1):
            p1, p2 = pts[i], pts[i + 1]
            wire_segments.append((p1, p2))
            uf.union(p1, p2)

    # 2. Pins to wires / hot spots
    pins_by_hotspot: dict[tuple[int, int], list[dict[str, Any]]] = collections.defaultdict(list)
    all_pins = []
    for c in sheet_doc.get("components", []):
        ref = c.get("ref", "")
        for p in c.get("pins", []):
            hs = pin_hot_spot(p)
            pin_info = {
                "ref": ref,
                "number": p.get("number", ""),
                "name": p.get("name", ""),
                "tag": f"{ref}-{p.get('number', '')}",
                "hotspot": hs,
                "electrical": p.get("electrical", 0),
            }
            all_pins.append(pin_info)
            pins_by_hotspot[hs].append(pin_info)

    for hs in pins_by_hotspot:
        # Check if hs touches any wire segment
        for p1, p2 in wire_segments:
            if point_on_segment(hs, p1, p2):
                uf.union(hs, p1)
                break

    # 3. Power ports
    power_ports_by_root: dict[Any, list[str]] = collections.defaultdict(list)
    for pp in sheet_doc.get("power_ports", []):
        pt = (int(pp.get("x", 0)), int(pp.get("y", 0)))
        text = pp.get("text") or pp.get("name", "")
        for p1, p2 in wire_segments:
            if point_on_segment(pt, p1, p2):
                uf.union(pt, p1)
                break
        if pt in pins_by_hotspot:
            uf.union(pt, pt)
        root = uf.find(pt)
        power_ports_by_root[root].append(text)

    # 4. Net labels
    labels_by_root: dict[Any, list[str]] = collections.defaultdict(list)
    for nl in sheet_doc.get("net_labels", []):
        pt = (int(nl.get("x", 0)), int(nl.get("y", 0)))
        text = nl.get("text") or nl.get("name", "")
        for p1, p2 in wire_segments:
            if point_on_segment(pt, p1, p2):
                uf.union(pt, p1)
                break
        if pt in pins_by_hotspot:
            uf.union(pt, pt)
        root = uf.find(pt)
        labels_by_root[root].append(text)

    # 5. Ports (RECORD=18)
    ports_by_root: dict[Any, list[str]] = collections.defaultdict(list)
    for port in sheet_doc.get("ports", []):
        x = int(port.get("x", 0))
        y = int(port.get("y", 0))
        w = int(port.get("width", 0))
        name = port.get("name") or port.get("text", "")
        candidate_pts = [(x + w, y), (x, y), (x - w, y)]
        matched_pt = None
        for pt in candidate_pts:
            for p1, p2 in wire_segments:
                if point_on_segment(pt, p1, p2):
                    matched_pt = pt
                    uf.union(pt, p1)
                    break
            if matched_pt:
                break
        if matched_pt:
            root = uf.find(matched_pt)
            ports_by_root[root].append(name)

    # Group pins by UF root
    pins_by_root: dict[Any, list[dict[str, Any]]] = collections.defaultdict(list)
    for p in all_pins:
        hs = p["hotspot"]
        root = uf.find(hs)
        pins_by_root[root].append(p)

    # Derive net names
    nets: dict[str, list[str]] = collections.defaultdict(list)
    pin_net_map_res: dict[str, str] = {}
    net_labels_res: dict[str, list[str]] = collections.defaultdict(list)
    power_ports_res: dict[str, list[str]] = collections.defaultdict(list)
    ports_res: dict[str, list[str]] = collections.defaultdict(list)

    auto_idx = 1
    for root, plist in pins_by_root.items():
        pps = power_ports_by_root.get(root, [])
        nls = labels_by_root.get(root, [])
        pts = ports_by_root.get(root, [])

        if pps:
            net_name = pps[0]
        elif nls:
            net_name = nls[0]
        elif pts:
            net_name = pts[0]
        else:
            first_pin = plist[0]
            net_name = f"Net{first_pin['ref']}_{first_pin['number']}" if first_pin['ref'] else f"Net_auto_{auto_idx}"
            auto_idx += 1

        for p in plist:
            nets[net_name].append(p["tag"])
            pin_net_map_res[p["tag"]] = net_name

        if nls:
            net_labels_res[net_name].extend(nls)
        if pps:
            power_ports_res[net_name].extend(pps)
        if pts:
            ports_res[net_name].extend(pts)

    return {
        "sheet_name": sheet_name,
        "nets": {k: sorted(v) for k, v in nets.items()},
        "pin_net_map": pin_net_map_res,
        "net_labels": dict(net_labels_res),
        "power_ports": dict(power_ports_res),
        "ports": dict(ports_res),
        "all_pins": all_pins,
        "components": sheet_doc.get("components", []),
    }


def build_multisheet_schdoc_netlist(sheet_docs: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge single-sheet netlists into a complete multi-sheet project netlist."""
    sheet_results = [build_schdoc_sheet_netlist(s) for s in sheet_docs]

    # Global merge by net name for power ports and ports
    merged_nets: dict[str, set[str]] = collections.defaultdict(set)
    labels_by_sheet: dict[str, set[str]] = collections.defaultdict(set)
    ports_by_net: dict[str, set[str]] = collections.defaultdict(set)
    all_pins = []

    for sr in sheet_results:
        s_name = sr["sheet_name"]
        for net, pins in sr["nets"].items():
            merged_nets[net].update(pins)

        for net in sr["net_labels"]:
            labels_by_sheet[net].add(s_name)

        for net in sr["ports"]:
            ports_by_net[net].add(s_name)

        all_pins.extend(sr["all_pins"])

    return {
        "nets": {k: sorted(v) for k, v in merged_nets.items()},
        "labels_by_sheet": {k: sorted(v) for k, v in labels_by_sheet.items()},
        "ports_by_net": {k: sorted(v) for k, v in ports_by_net.items()},
        "all_pins": all_pins,
        "sheet_results": sheet_results,
    }


def check_schematic(source: Any) -> dict[str, Any]:
    """
    Run schematic review checks on SchDoc(s) or PcbDoc.
    Source can be a path to .SchDoc/.PcbDoc, list of paths, or parsed dict.
    """
    findings = []
    netlist: dict[str, list[str]] = {}
    pin_details: dict[str, dict[str, Any]] = {}
    labels_by_sheet: dict[str, list[str]] = {}
    ports_by_net: dict[str, list[str]] = {}

    is_pcb = False

    # 1. Determine source type and extract netlist
    if isinstance(source, (str, pathlib.Path)):
        p = pathlib.Path(source)
        if p.is_dir():
            sch_files = list(p.glob("*.SchDoc"))
            if sch_files:
                docs = [read_schdoc(f) for f in sch_files]
                res = build_multisheet_schdoc_netlist(docs)
                netlist = res["nets"]
                labels_by_sheet = res["labels_by_sheet"]
                ports_by_net = res["ports_by_net"]
                for p_info in res["all_pins"]:
                    pin_details[p_info["tag"]] = p_info
            else:
                pcb_files = list(p.glob("*.PcbDoc"))
                if pcb_files:
                    doc = read_pcbdoc(pcb_files[0])
                    is_pcb = True
                    netlist = pad_net_map(doc)
                    for pad in doc.get("pads", []):
                        ref = pad.get("ref", "")
                        tag = f"{ref}-{pad.get('name', '')}"
                        pin_details[tag] = {"ref": ref, "number": pad.get("name", ""), "name": pad.get("name", ""), "tag": tag, "net": pad.get("net")}
        elif p.suffix.lower() == ".pcbdoc":
            doc = read_pcbdoc(p)
            is_pcb = True
            netlist = pad_net_map(doc)
            for pad in doc.get("pads", []):
                ref = pad.get("ref", "")
                tag = f"{ref}-{pad.get('name', '')}"
                pin_details[tag] = {"ref": ref, "number": pad.get("name", ""), "name": pad.get("name", ""), "tag": tag, "net": pad.get("net")}
        elif p.suffix.lower() == ".schdoc":
            doc = read_schdoc(p)
            res = build_schdoc_sheet_netlist(doc)
            netlist = res["nets"]
            for nl, sheets in res["net_labels"].items():
                labels_by_sheet[nl] = [doc.get("file", "Sheet")]
            ports_by_net = {k: [doc.get("file", "Sheet")] for k in res["ports"]}
            for p_info in res["all_pins"]:
                pin_details[p_info["tag"]] = p_info
    elif isinstance(source, list):
        docs = [read_schdoc(f) if isinstance(f, (str, pathlib.Path)) else f for f in source]
        res = build_multisheet_schdoc_netlist(docs)
        netlist = res["nets"]
        labels_by_sheet = res["labels_by_sheet"]
        ports_by_net = res["ports_by_net"]
        for p_info in res["all_pins"]:
            pin_details[p_info["tag"]] = p_info
    elif isinstance(source, dict):
        if "pads" in source and "components" in source:  # PcbDoc dict
            is_pcb = True
            netlist = pad_net_map(source)
            for pad in source.get("pads", []):
                ref = pad.get("ref", "")
                tag = f"{ref}-{pad.get('name', '')}"
                pin_details[tag] = {"ref": ref, "number": pad.get("name", ""), "name": pad.get("name", ""), "tag": tag, "net": pad.get("net")}
        elif "wires" in source and "components" in source:  # Single SchDoc dict
            res = build_schdoc_sheet_netlist(source)
            netlist = res["nets"]
            for nl in res["net_labels"]:
                labels_by_sheet[nl] = [source.get("file", "Sheet")]
            ports_by_net = {k: [source.get("file", "Sheet")] for k in res["ports"]}
            for p_info in res["all_pins"]:
                pin_details[p_info["tag"]] = p_info

    # Invert netlist: pin_tag -> net
    pin_to_net = {}
    for net, pins in netlist.items():
        for pin in pins:
            pin_to_net[pin] = net

    # Check 1: Single-pin nets
    single_pin_nets = []
    for net, pins in netlist.items():
        if len(pins) == 1:
            single_pin_nets.append(net)
            tag = pins[0]
            ref = tag.split("-")[0]
            findings.append({
                "id": "single_pin_net",
                "severity": "warning",
                "refs": [ref],
                "message": f"Net '{net}' has only one connected pin ({tag}).",
                "evidence": f"Netlist pin count for '{net}': 1 ({tag})",
            })

    # Check 2: Unconnected IC power pins
    for tag, p_info in pin_details.items():
        ref = p_info.get("ref", "")
        if ref.startswith(("U", "IC")):
            p_name = p_info.get("name", "")
            if POWER_PIN_RE.search(p_name):
                assigned_net = pin_to_net.get(tag)
                # Unconnected if no net, or net connects only this single pin and has no power port
                is_unconnected = (
                    not assigned_net
                    or (assigned_net in single_pin_nets and not POWER_PIN_RE.search(assigned_net))
                )
                if is_unconnected:
                    findings.append({
                        "id": "unconnected_ic_power",
                        "severity": "error",
                        "refs": [ref],
                        "message": f"IC {ref} power pin {p_info.get('number', '')} ('{p_name}') is unconnected.",
                        "evidence": f"Pin {tag} ({p_name}) has no circuit net connection (net '{assigned_net or 'None'}')",
                    })

    # Check 3: Nets only by label on one sheet
    for net, sheets in labels_by_sheet.items():
        if len(sheets) == 1 and net not in ports_by_net and not GND_RE.search(net) and not VCC_RE.search(net):
            pins = netlist.get(net, [])
            refs = list({p.split("-")[0] for p in pins if "-" in p})
            findings.append({
                "id": "net_only_by_label_on_one_sheet",
                "severity": "info",
                "refs": refs,
                "message": f"Net '{net}' is connected only by net label on a single sheet ('{sheets[0]}') with no inter-sheet port.",
                "evidence": f"Net label '{net}' on sheet '{sheets[0]}'",
            })

    # Check 4: Pins whose name says VCC/VDD/GND but net differs
    for tag, p_info in pin_details.items():
        p_name = p_info.get("name", "")
        assigned_net = pin_to_net.get(tag)
        if not assigned_net:
            continue
        ref = p_info.get("ref", "")
        num = p_info.get("number", "")

        # Ground pin connected to non-ground
        if GND_RE.search(p_name) and not GND_RE.search(assigned_net):
            findings.append({
                "id": "pin_net_mismatch",
                "severity": "error",
                "refs": [ref],
                "message": f"Ground pin {ref}-{num} ('{p_name}') is connected to non-ground net '{assigned_net}'.",
                "evidence": f"Pin name '{p_name}' vs net name '{assigned_net}'",
            })
        # Power pin connected to ground
        elif VCC_RE.search(p_name) and GND_RE.search(assigned_net):
            findings.append({
                "id": "pin_net_mismatch",
                "severity": "error",
                "refs": [ref],
                "message": f"Power pin {ref}-{num} ('{p_name}') is connected to ground net '{assigned_net}'.",
                "evidence": f"Pin name '{p_name}' vs ground net '{assigned_net}'",
            })

    return {
        "findings": findings,
        "net_count": len(netlist),
        "pin_count": len(pin_details),
        "single_pin_nets": single_pin_nets,
        "netlist": netlist,
    }


def main(argv=None):
    oscompat.utf8_stdio()
    ap = argparse.ArgumentParser(description="Schematic netlist and review checks")
    ap.add_argument("source", help="Path to .SchDoc/.PcbDoc or folder of SchDocs")
    ap.add_argument("--json", action="store_true", help="Print JSON findings")
    args = ap.parse_args(argv)

    res = check_schematic(args.source)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
