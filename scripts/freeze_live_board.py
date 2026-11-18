"""Freeze a placed PcbDoc as a routing test fixture: python scripts/freeze_live_board.py <board.PcbDoc> <out.json> [x0 y0 x1 y1].
Writes what route.plan_routes needs, as route_on gives it with replace=True: the pads, the nets, the drilled pads, the copper that belongs to
a footprint (tracks, arcs, fills, regions), no vias, the box and the rules read from the doc. Meant for synthetic test boards, never a student's."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from altium import route                                   # noqa: E402
from altium.pcbdoc import read_pcbdoc                      # noqa: E402


def freeze(pcb, box):
    doc = read_pcbdoc(pcb)
    keep = {k: [o for o in doc.get(k, []) if o.get("in_component")] for k in ("tracks", "arcs", "fills", "regions")}
    return {"box": list(box), "nets": doc["nets"], "pads": doc["pads"], "drilled_pads": doc.get("drilled_pads", []), "vias": [], **keep,
            "rules": dict(route.rules_from_doc(doc))}


if __name__ == "__main__":
    box = [float(v) for v in sys.argv[3:7]] if len(sys.argv) >= 7 else [0.0, 0.0, 45.009, 40.005]
    data = freeze(sys.argv[1], box)
    pathlib.Path(sys.argv[2]).write_text(json.dumps(data, separators=(",", ":"), sort_keys=True), encoding="utf-8")
