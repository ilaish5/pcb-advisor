"""
Schematic netlist builder and review checks.

Extracts netlists:
1. From PcbDoc pads (pad_net_map)
2. From SchDoc wire/label/port geometry join (one sheet, a list of sheets, a folder
   or a .PrjPcb)

Checks performed:
1. Single-pin nets (a pin with a No ERC marker is intentionally unconnected and is
   reported once, as an info count)
2. Unconnected IC power pins
3. Net labels that connect nothing, ports without a partner on another sheet
4. Pins whose name indicates VCC/VDD/GND but net differs
5. Optional: compare the schematic connectivity with the pad nets of a PcbDoc
   made from it (compare_with_board / --board)

JSON findings schema:
    [{"id": str, "severity": "error"|"warning"|"info", "refs": list[str], "message": str, "evidence": str}]

How the schematic netlist is joined (what Altium does, minus its sheet symbols):
- a pin connects at its hot spot (pin location + length along the pin direction);
  the pin records of a SchDoc are already in sheet coordinates, so component
  rotation/mirroring is not applied again
- everything that touches the same point is one node: wire vertices, junctions,
  pin hot spots, net labels, power ports, port ends. A point lying on the inside of
  a wire segment joins that wire (pin end, label, power port, a wire end that makes
  a T). Two wires that merely cross are not joined unless a junction sits there.
- names join nodes: all objects named N (power ports and ports project wide, net
  labels project wide or per sheet depending on the net identifier scope) are one net
- of the pins of a multi-part component only those of the placed part exist
- a hidden power pin joins the net named like the pin
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
from altium.prjpcb import read_prjpcb  # noqa: E402
from altium.schdoc import read_schdoc  # noqa: E402

POWER_PIN_RE = re.compile(r"^(?:VCC|VDD|VIN|VBAT|VREF|VDDA|VSS|VSSA|GND|AGND|DGND|3V3|5V|12V)\b", re.I)
GND_RE = re.compile(r"GND|VSS|0V|AGND|DGND", re.I)
VCC_RE = re.compile(r"VCC|VDD|VIN|VBAT|VDDA|3V3|5V|12V|\+3V3|\+5V", re.I)

ELECTRICAL_POWER = 7  # Altium pin electrical type "Power"
_CELL = 50  # spatial hash cell (sheet units) for the point-on-wire lookups


class UnionFind:
    def __init__(self):
        self.parent: dict[Any, Any] = {}

    def find(self, i):
        if i not in self.parent:
            self.parent[i] = i
            return i
        root = i
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[i] != root:  # path compression, iterative
            self.parent[i], i = root, self.parent[i]
        return root

    def union(self, i, j):
        root_i = self.find(i)
        root_j = self.find(j)
        if root_i != root_j:
            self.parent[root_i] = root_j


def _norm(v) -> "int | float":
    """Snap a coordinate within 0.02 unit of a whole number to that int, else round to 3 decimals."""
    r = round(v)
    return int(r) if abs(v - r) < 0.02 else round(float(v), 3)


def _pt(x, y) -> tuple:
    return (_norm(x), _norm(y))


def pin_hot_spot(pin: dict[str, Any]) -> tuple:
    """Calculate the electrical connection hot spot of a schematic pin."""
    x, y = pin.get("x", 0), pin.get("y", 0)
    length = pin.get("length", 0)
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


def point_on_segment(pt: tuple, p1: tuple, p2: tuple) -> bool:
    """Return True if point pt lies on the line segment between p1 and p2."""
    x, y = pt
    x1, y1 = p1
    x2, y2 = p2
    if min(x1, x2) <= x <= max(x1, x2) and min(y1, y2) <= y <= max(y1, y2):
        # Collinear check: (x - x1) * (y2 - y1) == (y - y1) * (x2 - x1)
        return (x - x1) * (y2 - y1) == (y - y1) * (x2 - x1)
    return False


def _placed_pins(comp: dict[str, Any]):
    """Pins that exist on the sheet: for a multi-part component only those of the placed part
    (the SchDoc component record lists the pins of every part; part -1/0 = common to all)."""
    cur = int(comp.get("current_part_id") or 1)
    for p in comp.get("pins", []):
        if int(p.get("part_id", cur)) in (cur, 0, -1):
            yield p


def _sheet_geometry(sheet_doc: dict[str, Any], unannotated: "collections.Counter | None" = None) -> dict[str, Any]:
    """Join one sheet by geometry. Returns the pins and the groups of touching objects:
    {"all_pins": [...], "groups": {root: {"pins": [...], "labels": [...], "power_ports": [...],
    "ports": [...], "hidden_power": [...]}}, "labels"/"power_ports"/"ports": [text, ...]}."""
    uf = UnionFind()
    grid: dict[tuple, list[tuple]] = collections.defaultdict(list)  # cell -> segments whose bbox covers it

    for w in sheet_doc.get("wires", []):
        pts = [_pt(*p) for p in w.get("points", [])]
        for p in pts:
            uf.find(p)
        for a, b in zip(pts, pts[1:]):
            uf.union(a, b)
            for cx in range(int(min(a[0], b[0]) // _CELL), int(max(a[0], b[0]) // _CELL) + 1):
                for cy in range(int(min(a[1], b[1]) // _CELL), int(max(a[1], b[1]) // _CELL) + 1):
                    grid[(cx, cy)].append((a, b))

    def touch(pt: tuple) -> tuple:
        """Make pt a node and join it to every wire segment it lies on."""
        uf.find(pt)
        for a, b in grid.get((int(pt[0] // _CELL), int(pt[1] // _CELL)), ()):
            if point_on_segment(pt, a, b):
                uf.union(pt, a)
        return pt

    # A wire end (or any vertex) that lands inside another wire makes a T connection.
    for v in list(uf.parent):
        touch(v)
    # Junctions join every wire that passes through them (also plain crossings).
    for j in sheet_doc.get("junctions", []):
        touch(_pt(j.get("x", 0), j.get("y", 0)))

    no_erc = {_pt(m.get("x", 0), m.get("y", 0)) for m in sheet_doc.get("no_erc", []) if m.get("active", True)}

    all_pins = []
    attach: list[tuple[tuple, str, str]] = []  # (node, kind, text)
    for c in sheet_doc.get("components", []):
        ref = c.get("ref", "")
        if unannotated is not None and "?" in ref:
            # every "R?" is a different part: keep their pin tags apart
            unannotated[ref] += 1
            ref = f"{ref}#{unannotated[ref]}"
        for p in _placed_pins(c):
            hs = touch(_pt(*pin_hot_spot(p)))
            number = p.get("number", "")
            info = {
                "ref": ref,
                "number": number,
                "name": p.get("name", ""),
                "tag": f"{ref}-{number}",
                "hotspot": hs,
                "electrical": p.get("electrical", 0),
                "hidden": bool(p.get("hidden", False)),
                "no_erc": hs in no_erc,
            }
            all_pins.append(info)
            if info["hidden"] and info["electrical"] == ELECTRICAL_POWER and info["name"]:
                attach.append((hs, "hidden_power", info["name"]))

    for pp in sheet_doc.get("power_ports", []):
        attach.append((touch(_pt(pp.get("x", 0), pp.get("y", 0))), "power_ports", pp.get("text") or pp.get("name", "")))
    for nl in sheet_doc.get("net_labels", []):
        attach.append((touch(_pt(nl.get("x", 0), nl.get("y", 0))), "labels", nl.get("text") or nl.get("name", "")))
    for port in sheet_doc.get("ports", []):
        x, y = port.get("x", 0), port.get("y", 0)
        w = port.get("width", 0) or 0
        ends = [(x, y), (x, y + w), (x, y - w)] if port.get("vertical") else [(x, y), (x + w, y)]
        text = port.get("name") or port.get("text", "")
        for k, (ex, ey) in enumerate(ends):
            # the port is counted once (first end); every end joins the wire it touches
            attach.append((touch(_pt(ex, ey)), "ports" if k == 0 else "ports_end", text))

    groups: dict[Any, dict[str, list]] = collections.defaultdict(
        lambda: {"pins": [], "labels": [], "power_ports": [], "ports": [], "ports_end": [], "hidden_power": []})
    for info in all_pins:
        groups[uf.find(info["hotspot"])]["pins"].append(info)
    for node, kind, text in attach:
        groups[uf.find(node)][kind].append(text)

    return {
        "all_pins": all_pins,
        "groups": groups,
        "labels": [t for _, k, t in attach if k == "labels"],
        "power_ports": [t for _, k, t in attach if k == "power_ports"],
        "ports": [t for _, k, t in attach if k == "ports"],
    }


def _auto_net_name(pin: dict[str, Any], idx: int) -> str:
    return f"Net{pin['ref']}_{pin['number']}" if pin["ref"] else f"Net_auto_{idx}"


def _join_sheets(sheet_docs: list[dict[str, Any]], labels_global: bool = True) -> dict[str, Any]:
    """Geometry-join every sheet, then join the groups across sheets by name."""
    unannotated: collections.Counter = collections.Counter()
    geo = [_sheet_geometry(s, unannotated) for s in sheet_docs]
    names = [s.get("file", f"Sheet{i + 1}") for i, s in enumerate(sheet_docs)]
    uf = UnionFind()

    for si, sg in enumerate(geo):
        sheet_power = {t for g in sg["groups"].values() for t in g["power_ports"] + g["hidden_power"]}
        for root, g in sg["groups"].items():
            gk = ("g", si, root)
            uf.find(gk)
            for t in g["power_ports"] + g["hidden_power"] + g["ports"] + g["ports_end"]:
                uf.union(gk, ("n", t))
            for t in g["labels"]:
                if labels_global or t in sheet_power:
                    uf.union(gk, ("n", t))
                else:
                    uf.union(gk, ("n", si, t))

    comp: dict[Any, dict[str, list]] = collections.defaultdict(
        lambda: {"pins": [], "labels": [], "power_ports": [], "ports": [], "sheets": [], "hidden_power": []})
    for si, sg in enumerate(geo):
        for root, g in sg["groups"].items():
            c = comp[uf.find(("g", si, root))]
            for k in ("pins", "labels", "power_ports", "ports", "hidden_power"):
                c[k].extend(g[k])
            c["sheets"].append(si)

    nets: dict[str, list[str]] = {}
    pin_net: dict[str, str] = {}
    auto_nets: list[str] = []
    labels_by_sheet: dict[str, set[str]] = collections.defaultdict(set)
    ports_by_net: dict[str, set[str]] = collections.defaultdict(set)
    power_ports_by_net: dict[str, set[str]] = collections.defaultdict(set)
    net_of_group: dict[Any, str] = {}
    auto_idx = 1
    for root, c in comp.items():
        if not c["pins"]:
            continue
        explicit = c["power_ports"] + c["hidden_power"] + c["labels"] + c["ports"]
        if explicit:
            name = explicit[0]
        else:
            name = _auto_net_name(c["pins"][0], auto_idx)
            auto_idx += 1
            auto_nets.append(name)
        if name in nets:  # same name kept apart on purpose (sheet-local label): disambiguate
            name = f"{name}@{names[c['sheets'][0]]}"
        nets[name] = [p["tag"] for p in c["pins"]]
        net_of_group[root] = name
        for p in c["pins"]:
            pin_net[p["tag"]] = name
        for si in c["sheets"]:
            if c["labels"]:
                labels_by_sheet[name].add(names[si])
            if c["ports"]:
                ports_by_net[name].add(names[si])
            if c["power_ports"]:
                power_ports_by_net[name].add(names[si])

    all_pins = [p for sg in geo for p in sg["all_pins"]]
    # Per object records (label/port/power port) for the label checks: where it is and what net it names
    objects = []
    for si, sg in enumerate(geo):
        for root, g in sg["groups"].items():
            net = net_of_group.get(uf.find(("g", si, root)))
            n_pins = len(nets[net]) if net else 0
            for kind in ("labels", "ports", "power_ports"):
                for t in g[kind]:
                    objects.append({"kind": kind, "text": t, "sheet": names[si], "net": net, "pins_on_net": n_pins})

    return {
        "nets": {k: sorted(v) for k, v in nets.items()},
        "pin_net_map": pin_net,
        "auto_nets": auto_nets,
        "labels_by_sheet": {k: sorted(v) for k, v in labels_by_sheet.items()},
        "ports_by_net": {k: sorted(v) for k, v in ports_by_net.items()},
        "power_ports_by_net": {k: sorted(v) for k, v in power_ports_by_net.items()},
        "objects": objects,
        "no_erc_pins": sorted(p["tag"] for p in all_pins if p["no_erc"]),
        "unannotated": sorted({r for p in all_pins for r in [p["ref"]] if "?" in r}),
        "all_pins": all_pins,
        "sheet_names": names,
    }


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
            ... (also "all_pins", "auto_nets", "no_erc_pins")
        }
    """
    res = _join_sheets([sheet_doc])
    net_labels: dict[str, list[str]] = collections.defaultdict(list)
    power_ports: dict[str, list[str]] = collections.defaultdict(list)
    ports: dict[str, list[str]] = collections.defaultdict(list)
    target = {"labels": net_labels, "power_ports": power_ports, "ports": ports}
    for o in res["objects"]:
        if o["net"] and o["kind"] in target:
            target[o["kind"]][o["net"]].append(o["text"])
    return {
        "sheet_name": sheet_doc.get("file", "Sheet"),
        "nets": res["nets"],
        "pin_net_map": res["pin_net_map"],
        "net_labels": dict(net_labels),
        "power_ports": dict(power_ports),
        "ports": dict(ports),
        "all_pins": res["all_pins"],
        "auto_nets": res["auto_nets"],
        "no_erc_pins": res["no_erc_pins"],
        "components": sheet_doc.get("components", []),
    }


def net_scope_of(prj: "dict | None", sheet_docs: list[dict[str, Any]]) -> str:
    """'global' (net labels and ports join across sheets) or 'sheet' (net labels stay on their
    sheet). The project's NetIdentifierScope wins when it says so; Automatic (the default and what
    a project file without the key means) is global when the project has no sheet symbols
    (record 15) and hierarchical, labels local, when it has."""
    setting = str(((prj or {}).get("settings") or {}).get("NETIDENTIFIERSCOPE", "")).strip().lower()
    if setting.startswith("global"):
        return "global"
    if setting.startswith(("hier", "strict", "flat")):
        return "sheet"
    has_symbols = any(int((s.get("record_counts") or {}).get("15", 0) or 0) for s in sheet_docs)
    return "sheet" if has_symbols else "global"


def build_multisheet_schdoc_netlist(sheet_docs: list[dict[str, Any]], net_scope: str = "global") -> dict[str, Any]:
    """Merge single-sheet netlists into a complete multi-sheet project netlist."""
    res = _join_sheets(sheet_docs, labels_global=(net_scope != "sheet"))
    res["sheet_results"] = [build_schdoc_sheet_netlist(s) for s in sheet_docs]
    res["net_scope"] = net_scope
    res["hierarchical"] = any(int((s.get("record_counts") or {}).get("15", 0) or 0) for s in sheet_docs)
    return res


# ---------------------------------------------------------------------------
# Compare the schematic netlist with the pad nets of the PcbDoc made from it
# ---------------------------------------------------------------------------
def _board_groups(pcb_doc: dict[str, Any]) -> dict[str, "str | None"]:
    """{"REF-PAD": board net or None} from a read_pcbdoc() dict (pads without a ref are skipped)."""
    out: dict[str, "str | None"] = {}
    for pad in pcb_doc.get("pads", []):
        ref = pad.get("ref")
        if not ref:
            continue
        tag = f"{ref}-{pad.get('name', '')}"
        net = pad.get("net") or None
        if tag not in out or (out[tag] is None and net):
            out[tag] = net
    return out


def compare_with_board(sch_netlist: dict[str, Any], pcb_doc: dict[str, Any]) -> dict[str, Any]:
    """Compare the schematic connectivity with the pad nets of the PcbDoc made from it.

    sch_netlist: a build_*_netlist() result (or {net: [pins]}); every pin that is in a net counts,
    a pin alone in its net is unconnected. pcb_doc: read_pcbdoc() dict (pads: ref, name, net).
    Nets are compared as groups of pins, not by name: auto-named nets (NetU2_4) may be named
    differently by Altium. Only pins that exist in both are compared.

    Returns {"mismatches": [...], "compared_pins", "only_in_schematic", "only_in_board",
    "matching_pins"}. One mismatch per pin: {"pin", "kind", "schematic_net", "board_net",
    "together_in_schematic_only": [pins], "together_in_board_only": [pins]} with kind one of
    "unconnected_in_schematic" (schematic has the pin alone, the board connects it),
    "unconnected_in_board" and "different_nets" (both connect it, to different pin sets).
    """
    nets = sch_netlist.get("nets", sch_netlist) if isinstance(sch_netlist, dict) else {}
    sch_net_of: dict[str, str] = {}
    for net, pins in nets.items():
        for pin in pins:
            sch_net_of[pin] = net
    board_net_of = _board_groups(pcb_doc)

    shared = sorted(set(sch_net_of) & set(board_net_of))
    shared_set = set(shared)
    sch_members: dict[str, set[str]] = collections.defaultdict(set)
    board_members: dict[str, set[str]] = collections.defaultdict(set)
    for tag in shared:
        sch_members[sch_net_of[tag]].add(tag)
        if board_net_of[tag]:
            board_members[board_net_of[tag]].add(tag)

    mismatches = []
    for tag in shared:
        s_net, b_net = sch_net_of[tag], board_net_of[tag]
        s_peers = sch_members[s_net] - {tag}
        b_peers = (board_members[b_net] - {tag}) if b_net else set()
        if s_peers == b_peers:
            continue
        if not s_peers:
            kind = "unconnected_in_schematic"
        elif not b_peers:
            kind = "unconnected_in_board"
        else:
            kind = "different_nets"
        mismatches.append({
            "pin": tag,
            "kind": kind,
            "schematic_net": s_net,
            "board_net": b_net,
            "together_in_schematic_only": sorted(s_peers - b_peers)[:8],
            "together_in_board_only": sorted(b_peers - s_peers)[:8],
        })

    return {
        "mismatches": mismatches,
        "compared_pins": len(shared_set),
        "matching_pins": len(shared_set) - len(mismatches),
        "only_in_schematic": sorted(set(sch_net_of) - set(board_net_of)),
        "only_in_board": sorted(set(board_net_of) - set(sch_net_of)),
    }


def _board_findings(cmp: dict[str, Any]) -> list[dict[str, Any]]:
    """One board_netlist_mismatch error per (kind, schematic net, board net) cluster of pins."""
    clusters: dict[tuple, list[dict[str, Any]]] = collections.OrderedDict()
    for m in cmp["mismatches"]:
        clusters.setdefault((m["kind"], m["schematic_net"], m["board_net"]), []).append(m)
    out = []
    for (kind, s_net, b_net), ms in clusters.items():
        pins = [m["pin"] for m in ms]
        refs = sorted({p.rsplit("-", 1)[0] for p in pins})
        shown = ", ".join(pins[:8]) + (f" (+{len(pins) - 8} more)" if len(pins) > 8 else "")
        only_s = sorted({p for m in ms for p in m["together_in_schematic_only"]})
        only_b = sorted({p for m in ms for p in m["together_in_board_only"]})
        what = {
            "unconnected_in_schematic": f"the schematic leaves {shown} unconnected (net '{s_net}') but the board has them on '{b_net}'",
            "unconnected_in_board": f"the board has {shown} unconnected but the schematic puts them on '{s_net}'",
            "different_nets": f"{shown} (schematic net '{s_net}', board net '{b_net}') differ in what they connect to"
                              + (f": only the schematic joins {_max_list(only_s, 6)}" if only_s else "")
                              + (f"{';' if only_s else ':'} only the board joins {_max_list(only_b, 6)}" if only_b else ""),
        }[kind]
        out.append({
            "id": "board_netlist_mismatch",
            "severity": "error",
            "refs": refs,
            "message": f"Schematic and board disagree: {what}.",
            "evidence": f"{len(pins)} pin(s), kind {kind}; schematic net '{s_net}' vs board net '{b_net}'",
        })
    return out


_NC_NETS = ("NC", "N/C", "NO_ERC")
_PIN_TOKEN_RE = re.compile(r"[A-Za-z]+\d+")


def _board_pad_index(pcb_doc: dict[str, Any]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    out: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for pad in pcb_doc.get("pads", []):
        ref = pad.get("ref")
        if ref:
            out.setdefault(str(ref), {}).setdefault(str(pad.get("name", "")), []).append(pad)
    return out


def _pads_of_pin(by_name: dict[str, list[dict[str, Any]]], num: str) -> list[dict[str, Any]]:
    """The pads a netlist pin number stands for: the pad of that designator, else (a merged pin such as
    'A4B9' on a board that has 'A4' and 'B9' pads) the pads named by its parts. [] when none fits."""
    if num in by_name:
        return by_name[num]
    joined = re.sub(r"[^A-Za-z0-9]", "", num)                  # 'A4/B9' is the pad 'A4B9'
    if joined != num and joined in by_name:
        return by_name[joined]
    parts = _PIN_TOKEN_RE.findall(num)
    if len(parts) > 1 and "".join(parts) == joined:
        found = [pad for t in parts for pad in by_name.get(t, [])]
        if found:
            return found
    return []


def check_intent_vs_board(sheets: list[dict], pcb_doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Design intent (the netlist sheets the agent wrote) against the PcbDoc's pads. Findings:
    design_part_missing (error: a part with connections is not on the board), design_net_mismatch (error: a pin's pad
    has no net or another net than its intended net, or the board joins fewer pins than the design), design_nets_shorted
    (error: two intended nets on one board net), design_pin_unknown (warning: a pin number no pad has).
    A pin with net NC or no net is intentionally open and never reported."""
    by_ref = _board_pad_index(pcb_doc)
    intent: dict[str, list[tuple[str, str]]] = collections.OrderedDict()      # net -> [(ref, num)]
    unknown: dict[str, list[str]] = collections.OrderedDict()
    missing_parts: list[str] = []
    pads_of: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for sheet in sheets:
        for part in sheet.get("parts", []):
            ref = str(part.get("ref", ""))
            wired = [(str(p.get("num") or p.get("number") or p.get("name") or ""), str(p.get("net") or "").strip())
                     for p in part.get("pins", [])]
            wired = [(num, net) for num, net in wired if net and net.upper() not in _NC_NETS]
            if not wired:
                continue
            if ref not in by_ref:
                if ref not in missing_parts:
                    missing_parts.append(ref)
                continue
            for num, net in wired:
                pads = _pads_of_pin(by_ref[ref], num)
                if not pads:
                    unknown.setdefault(ref, []).append(num)
                    continue
                pads_of[(ref, num)] = pads
                if (ref, num) not in intent.setdefault(net, []):
                    intent[net].append((ref, num))

    out: list[dict[str, Any]] = []
    for ref in missing_parts:
        out.append({"id": "design_part_missing", "severity": "error", "refs": [ref],
                    "message": f"{ref} is in the design but not on the board: its connections cannot be made. "
                               "Update the PcbDoc from the schematic.",
                    "evidence": f"{ref} has no pad in the PcbDoc"})
    for ref, nums in unknown.items():
        out.append({"id": "design_pin_unknown", "severity": "warning", "refs": [ref],
                    "message": f"{ref} pin(s) {', '.join(nums)} of the design match no pad on the board (different pin "
                               "numbering?): not compared.",
                    "evidence": f"pads of {ref}: {_max_list(sorted(by_ref[ref]), 12)}"})

    board_nets_of: dict[str, set[str]] = collections.defaultdict(set)         # board net -> intended nets on it
    for net, pins in intent.items():
        pads = [(f"{r}-{n}", pad) for r, n in pins for pad in pads_of[(r, n)]]
        on = collections.Counter(pad.get("net") for _, pad in pads if pad.get("net"))
        for b in on:
            board_nets_of[b].add(net)
        if not on:
            main = None
        elif on.get(net):
            main = net
        else:
            main = on.most_common(1)[0][0]
        none_pins = [tag for tag, pad in pads if not pad.get("net")]
        wrong = [(tag, pad["net"]) for tag, pad in pads if pad.get("net") and pad["net"] != main]
        joined = sorted({tag for tag, pad in pads if main and pad.get("net") == main})
        too_few = len(pins) >= 2 and len(joined) < 2
        if not (none_pins or wrong or too_few):
            continue
        bits = []
        if not on:
            bits.append(f"net '{net}' is not on the board at all")
        elif too_few:
            bits.append(f"net '{net}' joins only {_max_list(joined, 8)} on the board")
        if none_pins:
            bits.append(f"{_max_list(none_pins, 8)} should be on '{net}' but the pad has no net")
        if wrong:
            bits.append("; ".join(f"{t} should be on '{net}' but is on '{b}'" for t, b in wrong[:6]))
        refs = sorted({r for r, _ in pins})
        out.append({"id": "design_net_mismatch", "severity": "error", "refs": refs,
                    "message": f"Design and board disagree on net '{net}': " + "; ".join(bits) + ". The connection is missing on the board.",
                    "evidence": f"design pins on '{net}': {_max_list([f'{r}-{n}' for r, n in pins], 10)}; board nets: "
                                + (_max_list([f"{k} x{v}" for k, v in on.items()], 6) or "none")})
    for b, nets in board_nets_of.items():
        if len(nets) > 1:
            pins = [f"{r}-{n}" for net in sorted(nets) for r, n in intent[net]]
            out.append({"id": "design_nets_shorted", "severity": "error",
                        "refs": sorted({r for net in nets for r, _ in intent[net]}),
                        "message": f"Board net '{b}' joins nets the design keeps apart: {', '.join(sorted(nets))}.",
                        "evidence": _max_list(pins, 10)})
    return out


def design_vs_board(project_or_sheets: Any, board: Any) -> list[dict[str, Any]]:
    """check_intent_vs_board from a project name / folder / netlist folder / sheet(s) and a PcbDoc (path or read_pcbdoc
    dict). [] when there is no design intent to compare."""
    got = _netlist_sources(project_or_sheets)
    if not got:
        return []
    pcb_doc = board if isinstance(board, dict) else read_pcbdoc(board)
    return check_intent_vs_board(got[0], pcb_doc)


# ---------------------------------------------------------------------------
# Source loading
# ---------------------------------------------------------------------------
def _sheet_paths(folder: pathlib.Path) -> "tuple[list[pathlib.Path], dict | None]":
    """The SchDocs of a folder: the sheets of its .PrjPcb when there is exactly one, else every .SchDoc."""
    prjs = sorted(f for f in folder.iterdir() if f.is_file() and f.suffix.lower() == ".prjpcb")
    if len(prjs) == 1:
        paths, prj = _prjpcb_sheets(prjs[0])
        if paths:
            return paths, prj
    return sorted(f for f in folder.iterdir() if f.is_file() and f.suffix.lower() == ".schdoc"), None


def _prjpcb_sheets(prj_path: pathlib.Path) -> "tuple[list[pathlib.Path], dict]":
    prj = read_prjpcb(prj_path)
    paths = []
    for rel in prj["sheets"]:
        f = prj_path.parent / pathlib.Path(rel.replace("\\", "/"))
        if f.is_file() and f.suffix.lower() == ".schdoc":
            paths.append(f)
    return paths, prj


def _pcb_details(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out = {}
    for pad in doc.get("pads", []):
        ref = pad.get("ref", "")
        tag = f"{ref}-{pad.get('name', '')}"
        out[tag] = {"ref": ref, "number": pad.get("name", ""), "name": pad.get("name", ""), "tag": tag, "net": pad.get("net")}
    return out


def _max_list(items: list, n: int = 12) -> str:
    return ", ".join(items[:n]) + (f" (+{len(items) - n} more)" if len(items) > n else "")


def _is_netlist_sheet(doc: Any) -> bool:
    return isinstance(doc, dict) and isinstance(doc.get("parts"), list) and "wires" not in doc and "pads" not in doc


def _netlist_sources(source: Any) -> "tuple[list[dict], str | None] | None":
    """The tool's own netlist sheets (store.write_sheet) behind a source, or None when it is something else.
    A sheet dict, a list of them, a sheet .json, a netlist folder of .json, or a project name.
    Returns (sheets, project name or None)."""
    if _is_netlist_sheet(source):
        return [source], None
    if isinstance(source, list) and source and all(_is_netlist_sheet(d) for d in source):
        return list(source), None
    if not isinstance(source, (str, pathlib.Path)):
        return None
    p = pathlib.Path(source)
    files: list[pathlib.Path] = []
    project = None
    if p.is_file() and p.suffix.lower() == ".json":
        files = [p]
        if p.parent.name == "netlist":
            project = p.parent.parent.name
    elif p.is_dir():
        if p.name != "netlist" and (p / "netlist").is_dir():       # a project folder: its netlist/ is the design
            project, p = p.name, p / "netlist"
        files = sorted(p.glob("*.json"))
        if p.name == "netlist":
            project = p.parent.name
    elif isinstance(source, str) and not p.suffix and not p.exists():
        import store  # a project name
        sheets = [store.load_sheet(source, sid) for sid in store.sheet_ids(source)]
        sheets = [d for d in sheets if _is_netlist_sheet(d)]
        return (sheets, source) if sheets else None
    docs = []
    for f in files:
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if _is_netlist_sheet(doc):
            docs.append(doc)
    return (docs, project) if docs else None


def build_netlist_sheets_netlist(sheets: list[dict]) -> dict[str, Any]:
    """Nets from netlist sheets, in the shape of build_multisheet_schdoc_netlist (what check_schematic reads).
    A pin with no net is open: it gets a net of its own (auto). Net 'NC' is an intentional no-connect (No ERC)."""
    nets: dict[str, list[str]] = {}
    all_pins: list[dict[str, Any]] = []
    auto_nets: list[str] = []
    no_erc: list[str] = []
    for sheet in sheets:
        for part in sheet.get("parts", []):
            ref = str(part.get("ref", ""))
            for pin in part.get("pins", []):
                num = str(pin.get("num") or pin.get("number") or pin.get("name") or "")
                tag = f"{ref}-{num}"
                net = str(pin.get("net") or "").strip()
                nc = net.upper() in ("NC", "N/C", "NO_ERC")
                if not net or nc:
                    net = f"Net{ref}_{num}"
                    auto_nets.append(net)
                    if nc:
                        no_erc.append(tag)
                if tag in nets.get(net, []):
                    continue
                nets.setdefault(net, []).append(tag)
                all_pins.append({"ref": ref, "number": num, "name": str(pin.get("name") or ""), "tag": tag,
                                 "net": net, "no_erc": nc, "section": part.get("section", "")})
    return {"nets": nets, "all_pins": all_pins, "auto_nets": auto_nets, "no_erc_pins": sorted(no_erc),
            "power_ports_by_net": {}, "objects": [], "unannotated": [], "hierarchical": False}


def check_schematic(source: Any, board: Any = None) -> dict[str, Any]:
    """
    Run schematic review checks on SchDoc(s) or PcbDoc.
    Source can be a path to .SchDoc/.PcbDoc/.PrjPcb or a folder, a list of paths/dicts,
    or a parsed dict. The tool's own netlist sheets work too: a project name, its netlist folder,
    a sheet .json or a sheet dict with "parts" (a pin with net "" is open, net "NC" is a No ERC pin). board (a PcbDoc path or read_pcbdoc dict) also compares the schematic
    connectivity with the pad nets of that board: board_mismatches and board_netlist_mismatch errors.
    """
    findings: list[dict[str, Any]] = []
    netlist: dict[str, list[str]] = {}
    pin_details: dict[str, dict[str, Any]] = {}
    sch: dict[str, Any] = {}
    n_sheets = 0
    is_pcb = False

    # 1. Determine source type and extract netlist
    sheet_docs: list[dict[str, Any]] = []
    prj = None
    project = None
    from_netlist = _netlist_sources(source)
    if from_netlist:
        net_sheets, project = from_netlist
        n_sheets = len(net_sheets)
        sch = build_netlist_sheets_netlist(net_sheets)
        netlist = sch["nets"]
        for p_info in sch["all_pins"]:
            pin_details[p_info["tag"]] = p_info
    elif isinstance(source, (str, pathlib.Path)):
        p = pathlib.Path(source)
        if p.is_dir():
            paths, prj = _sheet_paths(p)
            if paths:
                sheet_docs = [read_schdoc(f) for f in paths]
            else:
                pcb_files = sorted(p.glob("*.PcbDoc"))
                if pcb_files:
                    doc = read_pcbdoc(pcb_files[0])
                    is_pcb = True
                    netlist = pad_net_map(doc)
                    pin_details = _pcb_details(doc)
        elif p.suffix.lower() == ".prjpcb":
            paths, prj = _prjpcb_sheets(p)
            sheet_docs = [read_schdoc(f) for f in paths]
        elif p.suffix.lower() == ".pcbdoc":
            doc = read_pcbdoc(p)
            is_pcb = True
            netlist = pad_net_map(doc)
            pin_details = _pcb_details(doc)
        elif p.suffix.lower() == ".schdoc":
            sheet_docs = [read_schdoc(p)]
    elif isinstance(source, list):
        sheet_docs = [read_schdoc(f) if isinstance(f, (str, pathlib.Path)) else f for f in source]
    elif isinstance(source, dict):
        if "pads" in source and "components" in source:  # PcbDoc dict
            is_pcb = True
            netlist = pad_net_map(source)
            pin_details = _pcb_details(source)
        elif "wires" in source and "components" in source:  # Single SchDoc dict
            sheet_docs = [source]

    scope = "global"
    if sheet_docs:
        n_sheets = len(sheet_docs)
        scope = net_scope_of(prj, sheet_docs)
        sch = build_multisheet_schdoc_netlist(sheet_docs, scope)
        netlist = sch["nets"]
        for p_info in sch["all_pins"]:
            pin_details[p_info["tag"]] = p_info

    auto_nets = set(sch.get("auto_nets", []))
    no_erc = set(sch.get("no_erc_pins", []))

    # Invert netlist: pin_tag -> net
    pin_to_net = {}
    for net, pins in netlist.items():
        for pin in pins:
            pin_to_net[pin] = net

    # Check 1: Single-pin nets (a No ERC pin is left open on purpose: counted once, below)
    single_pin_nets = []
    for net, pins in netlist.items():
        if len(pins) == 1:
            tag = pins[0]
            if tag in no_erc:
                continue
            single_pin_nets.append(net)
            ref = tag.split("-")[0]
            alone = net in auto_nets
            findings.append({
                "id": "single_pin_net",
                "severity": "warning",
                "refs": [ref],
                "message": (f"Pin {tag} is not connected to anything (no wire, label or port on it)." if alone
                            else f"Net '{net}' has only one connected pin ({tag})."),
                "evidence": f"Netlist pin count for '{net}': 1 ({tag})",
            })
    unannotated = sch.get("unannotated", [])
    if unannotated:
        findings.append({
            "id": "unannotated_components",
            "severity": "warning",
            "refs": list(dict.fromkeys(r.split("#")[0] for r in unannotated))[:12],
            "message": f"{len(unannotated)} component(s) still have a '?' designator (not annotated); "
                       f"their pins are listed as REF#n-PIN.",
            "evidence": _max_list(unannotated),
        })
    open_marked = [t for t in sorted(no_erc) if len(netlist.get(pin_to_net.get(t, ""), [])) == 1]
    if open_marked:
        refs = sorted({t.rsplit("-", 1)[0] for t in open_marked})
        findings.append({
            "id": "no_erc_unused_pins",
            "severity": "info",
            "refs": refs,
            "message": f"{len(open_marked)} unused pin(s) on {len(refs)} component(s) carry a No ERC marker "
                       f"(intentionally unconnected).",
            "evidence": _max_list(open_marked),
        })

    # Check 2: Unconnected IC power pins
    for tag, p_info in pin_details.items():
        ref = p_info.get("ref", "")
        if ref.startswith(("U", "IC")) and tag not in no_erc:
            p_name = p_info.get("name", "")
            if POWER_PIN_RE.search(p_name):
                assigned_net = pin_to_net.get(tag)
                # Unconnected: no net, or alone on a net that no power port names. A pin on a named
                # power rail is connected even when it is the only pin the project puts there.
                alone = assigned_net is not None and len(netlist.get(assigned_net, [])) == 1
                has_power_port = bool(assigned_net and assigned_net in sch.get("power_ports_by_net", {}))
                is_unconnected = not assigned_net or (alone and not has_power_port and not POWER_PIN_RE.search(assigned_net))
                if is_unconnected:
                    findings.append({
                        "id": "unconnected_ic_power",
                        "severity": "error",
                        "refs": [ref],
                        "message": f"IC {ref} power pin {p_info.get('number', '')} ('{p_name}') is unconnected.",
                        "evidence": f"Pin {tag} ({p_name}) has no circuit net connection (net '{assigned_net or 'None'}')",
                    })

    # Check 2b: a transistor switching a coil without a flyback diode
    bom: list = []
    if project:
        try:
            import store
            bom = store.bom_lines(project)
        except Exception:
            bom = []
    findings.extend(check_inductive_load_no_flyback(netlist, pin_details, bom))

    # Check 3: net labels that connect nothing and ports without a partner on another sheet.
    # Using a label inside a sheet to name a net is normal and is not reported.
    if sch:
        name_count = collections.Counter(o["text"] for o in sch["objects"])
        for o in sch["objects"]:
            text, net = o["text"], o["net"]
            if o["kind"] == "power_ports" or name_count[text] != 1 or GND_RE.search(text) or VCC_RE.search(text):
                continue
            pins = netlist.get(net, []) if net else []
            refs = sorted({p.rsplit("-", 1)[0] for p in pins})
            if o["kind"] == "labels" and len(pins) <= 1:
                findings.append({
                    "id": "net_only_by_label_on_one_sheet",
                    "severity": "info",
                    "refs": refs,
                    "message": f"Net label '{text}' on sheet '{o['sheet']}' appears once in the project and "
                               f"joins {'one pin' if pins else 'no pin'}: it connects nothing by name.",
                    "evidence": f"Net label '{text}' on sheet '{o['sheet']}', pins on its net: {len(pins)}",
                })
            elif o["kind"] == "ports" and n_sheets > 1 and not sch.get("hierarchical"):
                findings.append({
                    "id": "net_only_by_label_on_one_sheet",
                    "severity": "info",
                    "refs": refs,
                    "message": f"Port '{text}' on sheet '{o['sheet']}' has no port or net label of the same name "
                               f"on another sheet.",
                    "evidence": f"Port '{text}' on sheet '{o['sheet']}', {len(pins)} pin(s) on its net",
                })

    # Check 4: Pins whose name says VCC/VDD/GND but net differs
    for tag, p_info in pin_details.items():
        p_name = p_info.get("name", "")
        assigned_net = pin_to_net.get(tag)
        if not assigned_net or tag in no_erc or assigned_net in auto_nets:
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

    # Check 5: the board made from these sheets must have the same connectivity
    board_cmp = None
    if board is not None and sch:
        pcb_doc = board if isinstance(board, dict) else read_pcbdoc(board)
        board_cmp = compare_with_board(sch, pcb_doc)
        if from_netlist:                                  # the design intent: named nets, pins, parts
            findings.extend(check_intent_vs_board(net_sheets, pcb_doc))
        else:
            findings.extend(_board_findings(board_cmp))
        missing = [] if from_netlist else board_cmp["only_in_schematic"]
        if missing:
            findings.append({
                "id": "board_pins_missing",
                "severity": "warning",
                "refs": sorted({t.rsplit("-", 1)[0] for t in missing})[:12],
                "message": f"{len(missing)} schematic pin(s) have no pad on the board (board not updated from the "
                           f"schematic, or different designators); they were not compared.",
                "evidence": _max_list(missing),
            })

    return {
        "findings": findings,
        "net_count": len(netlist),
        "pin_count": len(pin_details),
        "single_pin_nets": single_pin_nets,
        "netlist": netlist,
        "no_erc_pins": sorted(no_erc),
        "net_scope": scope,
        "board_mismatches": board_cmp["mismatches"] if board_cmp else [],
        "board_compare": ({k: v for k, v in board_cmp.items() if k != "mismatches"} if board_cmp else None),
    }


# ---------------------------------------------------------------------------
# Datasheet-fact rules (pure functions: netlist + parts + facts dict).
# netlist: {net: ["U1-7", "C4-1", ...]}; parts: {ref: {"value":..., ...}};
# facts: datasheet_facts.json ({"part": "U1 MPN", "facts": [{"page","pin","text","source"}], ...}).
# Shared by the product and by scripts/bench/checks_schematic.py.
# ---------------------------------------------------------------------------
_CAP_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*([pnuµμm])\s*F\b", re.I)
_CAP_UNIT = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "μ": 1e-6, "m": 1e-3}


def parse_capacitance(text: Any) -> "float | None":
    """'1uF' / '100nF' / '0.22 uF' / '100uF 25V' -> farads, else None."""
    m = _CAP_RE.search(str(text or ""))
    if not m:
        return None
    return float(m.group(1).replace(",", ".")) * _CAP_UNIT[m.group(2).lower()]


def _fmt_cap(f: float) -> str:
    for unit, k in (("uF", 1e-6), ("nF", 1e-9), ("pF", 1e-12)):
        if f >= k * 0.9999:
            return f"{f / k:g} {unit}"
    return f"{f:g} F"


def net_of_pin(netlist: dict, pin: str) -> "str | None":
    for net, pins in netlist.items():
        if pin in pins:
            return net
    return None


def _tag_ref(tag: str) -> str:
    return tag.rsplit("-", 1)[0]


def _fact_src(fact: dict, facts: dict) -> str:
    bits = [str(facts.get("datasheet") or "")]
    if fact.get("page") is not None:
        bits.append(f"p.{fact['page']}")
    if fact.get("source"):
        bits.append(f"({fact['source']})")
    return " ".join(b for b in bits if b).strip() or "datasheet_facts"


def _facts_part_ref(facts: dict) -> "str | None":
    m = re.match(r"\s*([A-Za-z]+\d+)\b", str(facts.get("part") or ""))
    return m.group(1) if m else None


_MAXWORD_RE = re.compile(r"no more than|not more than|maximum|max\.?|at most|not exceed", re.I)


def check_pin_capacitance_max(netlist: dict, parts: dict, facts: dict) -> list:
    """Fact with a "pin" ('7 VCC') and a capacitance maximum: the total capacitance on that
    pin's net must not exceed it. One finding per over-limit pin."""
    out = []
    ref = _facts_part_ref(facts)
    for fact in facts.get("facts", []):
        pin_txt, text = str(fact.get("pin") or ""), str(fact.get("text") or "")
        pm = re.match(r"\s*(\w+)", pin_txt)
        mw = _MAXWORD_RE.search(text)
        if not (ref and pm and mw):
            continue
        limit = parse_capacitance(text[mw.end():])
        net = net_of_pin(netlist, f"{ref}-{pm.group(1)}") if limit is not None else None
        if net is None:
            continue
        caps = []
        for tag in netlist[net]:
            cref = _tag_ref(tag)
            val = parse_capacitance((parts.get(cref) or {}).get("value")) if re.match(r"C\d", cref) else None
            if val is not None and cref not in [c[0] for c in caps]:
                caps.append((cref, val))
        total = sum(v for _, v in caps)
        if total > limit * 1.0001:
            names = ", ".join(f"{c} {_fmt_cap(v)}" for c, v in caps)
            src = _fact_src(fact, facts)
            out.append({"id": "pin_capacitance_over_max", "refs": [c for c, _ in caps] + [ref, net],
                        "message": f"{ref} pin {pin_txt}: {names} on net {net} = {_fmt_cap(total)}, "
                                   f"above the datasheet maximum {_fmt_cap(limit)} ({src}).",
                        "source": src})
    return out


def check_output_type_unverified(netlist: dict, parts: dict, facts: dict) -> list:
    """facts["output_type"] says the datasheet does not state push-pull/open-drain, and a pin
    described as an output ('Pin 13 FAULT: ... output') drives a net shared with other pins and
    with no resistor on it: the pull direction/need cannot be decided, so ask."""
    ot = str(facts.get("output_type") or "")
    if not re.search(r"not stated|unknown|unclear|unspecified", ot, re.I):
        return []
    ref = _facts_part_ref(facts)
    out = []
    for fact in facts.get("facts", []):
        m = re.match(r"\s*Pin\s+(\d+)\s+(\w+)\s*:.*\boutput\b", str(fact.get("text") or ""), re.I)
        if not (ref and m):
            continue
        net = net_of_pin(netlist, f"{ref}-{m.group(1)}")
        if net is None or len(netlist[net]) < 2:
            continue
        if any(re.match(r"R\d", _tag_ref(t)) for t in netlist[net]):
            continue
        src = _fact_src(fact, facts)
        out.append({"id": "output_type_unverified", "refs": [ref, net],
                    "message": f"{ref} pin {m.group(1)} ({m.group(2)}) is an output on net {net} "
                               f"({len(netlist[net]) - 1} other pins, no pull resistor), but the datasheet "
                               f"does not state its type ({ot}); verify push-pull vs open-drain "
                               f"before choosing a pull-up/pull-down ({src}).",
                    "source": src})
    return out


def swap_target_ref(swap_text: str) -> "str | None":
    m = re.search(r"Replace\s+([A-Za-z]+\d+)\b", swap_text or "")
    return m.group(1) if m else None


def check_swap_requirements(netlist: dict, parts: dict, facts: dict, swap_text: str) -> list:
    """Part swap: (a) a pin the facts say needs an external capacitor ('X needs a ... capacitor',
    pin from 'pin N is X') must sit on a dedicated net of capacitor(s) only; a signal net there
    means the cap is missing. (b) a resistor the facts name as redundant ('internal ... pull-up ...
    external ... (R82) ... not needed') that is still in the netlist is flagged."""
    ref = swap_target_ref(swap_text)
    if not ref:
        return []
    out = []
    pinmap = {}
    for fact in facts.get("facts", []):
        for m in re.finditer(r"pin\s+(\d+)\s+is\s+(\w+)", str(fact.get("text") or ""), re.I):
            pinmap[m.group(2)] = m.group(1)
    for fact in facts.get("facts", []):
        text = str(fact.get("text") or "")
        src = _fact_src(fact, facts)
        m = re.match(r"\s*(\w+)\s+needs\s+an?\s+(?:\w+\s+)?capacitor", text, re.I)
        if m and m.group(1) in pinmap:
            name, pin = m.group(1), f"{ref}-{pinmap[m.group(1)]}"
            net = net_of_pin(netlist, pin)
            others = [t for t in (netlist.get(net) or []) if t != pin]
            dedicated = bool(others) and all(
                re.match(r"C\d", _tag_ref(t)) and
                parse_capacitance((parts.get(_tag_ref(t)) or {}).get("value")) is not None
                for t in others)
            if not dedicated:
                where = f"its net {net} carries {', '.join(others)}" if net else "it is unconnected"
                out.append({"id": "swap_pin_cap_missing", "refs": [ref, pin] + ([net] if net else []),
                            "message": f"After the swap {name} is {pin} and needs an external capacitor "
                                       f"to GND, but {where} and has no dedicated capacitor ({src}).",
                            "source": src})
        m = re.search(r"internal\s+[\w+ ]*?pull-up.*?external[^()]*\((R\d+)\)[^.;]*not needed", text, re.I)
        if m:
            rref = m.group(1)
            net = next((n for n, ps in netlist.items() if any(_tag_ref(t) == rref for t in ps)), None)
            if net:
                out.append({"id": "swap_pullup_redundant", "refs": [rref, ref, net],
                            "message": f"{rref} ({(parts.get(rref) or {}).get('value', '?')}) on net {net} is a "
                                       f"pull-up that the new part makes redundant ({src}).",
                            "source": src})
    return out


_COLLECTOR_RE = re.compile(r"^(?:C|D|COLLECTOR|DRAIN)$", re.I)
_MAGNETIC_RE = re.compile(r"magnetic|electromagnetic|coil|transducer|inductive", re.I)
_PIEZO_RE = re.compile(r"piezo", re.I)
_LOAD_KIND = {"K": "relay coil", "M": "motor", "BZ": "buzzer"}


def _ref_prefix(ref: str) -> str:
    return re.match(r"[A-Za-z]*", ref).group(0).upper()


def check_inductive_load_no_flyback(netlist: dict, pin_details: dict, bom: "list | None" = None) -> list:
    """A Q* collector/drain on the same net as a relay (K), motor (M) or buzzer (BZ) pin, and no diode (D*) across
    the load. A buzzer is judged by its BOM description/mpn: magnetic warns, piezo is skipped, unknown is info."""
    out = []
    ref_nets: dict[str, set] = {}
    for net, pins in netlist.items():
        for t in pins:
            ref_nets.setdefault(_tag_ref(t), set()).add(net)
    for net, pins in netlist.items():
        drivers = [t for t in pins if _ref_prefix(_tag_ref(t)) == "Q"
                   and _COLLECTOR_RE.match(str(pin_details.get(t, {}).get("name", "")))]
        if not drivers:
            continue
        q = _tag_ref(drivers[0])
        for load in sorted({_tag_ref(t) for t in pins if _ref_prefix(_tag_ref(t)) in _LOAD_KIND}):
            other = ref_nets.get(load, set()) - {net}
            diode_refs = {_tag_ref(t) for t in pins if _ref_prefix(_tag_ref(t)) == "D"}
            if any(_tag_ref(t) in diode_refs for o in other for t in netlist.get(o, [])):
                continue
            sev = "warning"
            if _ref_prefix(load) == "BZ":
                line = next((l for l in (bom or []) if load in (l.get("refs") or [])), {})
                text = f"{line.get('description', '')} {line.get('mpn', '')}"
                if _PIEZO_RE.search(text) and not _MAGNETIC_RE.search(text):
                    continue
                if not _MAGNETIC_RE.search(text):
                    sev = "info"
            fix = (f"Add a diode across {load} (e.g. 1N4148 or a Schottky), cathode to the supply side, "
                   f"anode to net '{net}'.")
            if sev == "info":
                msg = (f"{q} switches buzzer {load} on net '{net}' with no diode across it. A magnetic buzzer needs a "
                       f"flyback diode, a piezo does not (the BOM does not say which this is). {fix}")
            else:
                msg = (f"{q} switches {_LOAD_KIND[_ref_prefix(load)]} {load} on net '{net}' with no flyback diode "
                       f"across it: the switch-off voltage spike can destroy {q}. {fix}")
            out.append({"id": "inductive_load_no_flyback", "severity": sev, "refs": [load, q], "message": msg,
                        "evidence": f"{drivers[0]} and {load} share net '{net}'; no D* joins it to {load}'s other net"})
    return out


def main(argv=None):
    oscompat.utf8_stdio()
    ap = argparse.ArgumentParser(description="Schematic netlist and review checks")
    ap.add_argument("source", help="Path to .SchDoc/.PcbDoc/.PrjPcb or a folder of SchDocs; or the tool's own netlist: "
                                   "a project name, its netlist folder or a sheet .json")
    ap.add_argument("--board", help="PcbDoc made from these sheets: compare its pad nets with the schematic")
    ap.add_argument("--json", action="store_true", help="Print JSON findings")
    args = ap.parse_args(argv)

    res = check_schematic(args.source, board=args.board)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
