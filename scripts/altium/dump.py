#!/usr/bin/env python3
"""CLI utility to dump a JSON summary or full dump of an Altium file."""
import json
import pathlib
import sys

# Ensure 'scripts' is on sys.path when invoked directly
SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from altium import AltiumReadError, pad_net_map, read_any  # noqa: E402


def summarize(path_obj: pathlib.Path, doc) -> dict:
    """Build a concise summary dictionary for supported Altium document types."""
    ext = path_obj.suffix.lower()
    if ext == ".pcbdoc":
        return {
            "file": doc["file"],
            "components": len(doc["components"]),
            "components_sample": [c["ref"] for c in doc["components"][:5]],
            "nets": len(doc["nets"]),
            "nets_sample": doc["nets"][:5],
            "pads": len(doc["pads"]),
            "pads_sample": [f"{p['ref']}-{p['name']}" for p in doc["pads"][:5] if p.get("ref")],
            "rules": len(doc["rules"]),
            "classes": len(doc["classes"]),
        }
    if ext == ".schdoc":
        return {
            "file": doc["file"],
            "components": len(doc["components"]),
            "components_sample": [
                {
                    "ref": c["ref"],
                    "lib_ref": c["lib_ref"],
                    "footprint": c["footprint"],
                    "pins": len(c["pins"]),
                }
                for c in doc["components"][:5]
            ],
            "wires": len(doc["wires"]),
            "net_labels": len(doc["net_labels"]),
            "power_ports": len(doc["power_ports"]),
            "ports": len(doc["ports"]),
            "junctions": len(doc["junctions"]),
            "record_counts": doc["record_counts"],
        }
    if ext == ".prjpcb":
        return {
            "file": doc["file"],
            "name": doc["name"],
            "documents": len(doc["documents"]),
            "sheets": doc["sheets"],
            "pcbs": doc["pcbs"],
            "outjobs": doc["outjobs"],
            "other": doc["other"],
            "missing": doc["missing"],
        }
    if ext == ".rul":
        return {
            "rules": len(doc),
            "rules_sample": [r.get("NAME") for r in doc[:5]],
        }
    return doc


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or "-h" in args or "--help" in args:
        print("Usage: python scripts/altium/dump.py <file> [--full] [--net NAME]", file=sys.stderr)
        return 2

    full = False
    if "--full" in args:
        full = True
        args.remove("--full")

    net = None
    if "--net" in args:
        i = args.index("--net")
        if i + 1 >= len(args):
            print("Error: --net needs a net name", file=sys.stderr)
            return 2
        net = args[i + 1]
        del args[i:i + 2]

    if not args:
        print("Error: missing target file", file=sys.stderr)
        return 2

    target = pathlib.Path(args[0])
    try:
        doc = read_any(target)
    except AltiumReadError as exc:
        print(f"AltiumReadError: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if net is not None:
        if target.suffix.lower() != ".pcbdoc":
            print("Error: --net works on a .PcbDoc only", file=sys.stderr)
            return 2
        pads = pad_net_map(doc).get(net)
        if pads is None:
            print(f"Error: net {net} not found", file=sys.stderr)
            return 2
        print(json.dumps({"net": net, "pads": pads}, ensure_ascii=False))
    elif full:
        print(json.dumps(doc, indent=2, ensure_ascii=False))
    else:
        summary = summarize(target, doc)
        print(json.dumps(summary, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
