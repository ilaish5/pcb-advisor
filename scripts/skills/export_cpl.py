"""
Export Pick and Place / CPL file for JLCPCB from linked Altium PcbDoc or BOM.

    python scripts/skills/export_cpl.py <project>

Writes projects/<project>/exports/<project>_cpl.csv with columns:
    Designator, Mid X, Mid Y, Layer, Rotation

Positions are relative to the board origin (Board6 ORIGINX/ORIGINY), as Altium writes them; Mid is the centre
of the part's pads, which matched Altium's "Center" column on 148 of 149 parts of a real board (a U.FL was
0.29 mm off). Rotation is the PcbDoc rotation: JLC rotation fixes are not applied here.
"""
import collections
import csv
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import oscompat  # noqa: E402
import project as project_mod  # noqa: E402
import workspace  # noqa: E402
from altium.ole import AltiumReadError, open_doc, stream, text_records  # noqa: E402
from altium.pcbdoc import mil_to_mm, read_pcbdoc  # noqa: E402


def board_origin_mm(pcb_path) -> tuple[float, float]:
    """The user origin set in Altium; component and pad coordinates in the file are absolute."""
    try:
        with open_doc(pathlib.Path(pcb_path)) as ole:
            rec = text_records(stream(ole, "Board6/Data"), prefix=0)
    except (AltiumReadError, KeyError, OSError):
        return 0.0, 0.0
    b = rec[0] if rec else {}
    return mil_to_mm(b.get("ORIGINX", "0")), mil_to_mm(b.get("ORIGINY", "0"))


def pad_centres(doc: dict) -> dict[str, tuple[float, float]]:
    """ref -> centre of the bounding box of its pads (absolute mm)."""
    boxes = collections.defaultdict(lambda: [float("inf"), float("inf"), float("-inf"), float("-inf")])
    for p in doc.get("pads", []):
        if not p.get("ref"):
            continue
        b = boxes[p["ref"]]
        hx, hy = p.get("sx_mm", 0.0) / 2, p.get("sy_mm", 0.0) / 2
        b[0] = min(b[0], p["x_mm"] - hx)
        b[1] = min(b[1], p["y_mm"] - hy)
        b[2] = max(b[2], p["x_mm"] + hx)
        b[3] = max(b[3], p["y_mm"] + hy)
    return {ref: ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2) for ref, b in boxes.items()}


def cpl_rows(project: str, pcb_path: str | pathlib.Path | None = None) -> list[dict]:
    """The rows the CPL file holds: from the PcbDoc when there is one, else a stub per BOM reference."""
    p_pcb = pcb_path or project_mod.altium_link(project).get("pcb_file")
    rows = []
    if p_pcb and pathlib.Path(p_pcb).is_file():
        doc = read_pcbdoc(p_pcb)
        ox, oy = board_origin_mm(p_pcb)
        centres = pad_centres(doc)
        for c in doc.get("components", []):
            ref = c.get("ref", "")
            if not ref:
                continue
            layer = "Top" if "top" in str(c.get("layer", "")).lower() else "Bottom"
            x, y = centres.get(ref, (c.get("x_mm", 0.0), c.get("y_mm", 0.0)))
            rows.append({
                "Designator": ref,
                "Mid X": f"{x - ox:.4f}mm",
                "Mid Y": f"{y - oy:.4f}mm",
                "Layer": layer,
                "Rotation": f"{float(c.get('rotation', 0.0)):.1f}",
            })
    else:
        # Fallback if no PcbDoc linked: generate stub from BOM lines
        import store
        lines = store.bom(project, write=False)
        for l in lines:
            if not store.qty(l):
                continue
            for r in l.get("refs", []):
                rows.append({
                    "Designator": r,
                    "Mid X": "0.0000mm",
                    "Mid Y": "0.0000mm",
                    "Layer": "Top",
                    "Rotation": "0.0",
                })
    return rows


def export_cpl(project: str, pcb_path: str | pathlib.Path | None = None) -> dict:
    p_pcb = pcb_path or project_mod.altium_link(project).get("pcb_file")
    from_pcb = str(p_pcb) if p_pcb and pathlib.Path(p_pcb).is_file() else ""
    rows = cpl_rows(project, from_pcb or None)

    out_dir = workspace.project_dir(project) / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{project}_cpl.csv"

    with open(out_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        writer.writeheader()
        writer.writerows(rows)
    import lineage
    lineage.note(project, out_file, lambda: [lineage.state_input(project, "cpl", from_pcb),
                                             lineage.file_input("pcb", from_pcb, compare=False) if from_pcb else None],
                 "export_cpl", note="" if from_pcb else "no PcbDoc linked: positions are a stub from the BOM")

    home = workspace.home()
    shown = out_file.relative_to(home).as_posix() if out_file.is_relative_to(home) else str(out_file)
    return {
        "file": shown,
        "name": out_file.name,
        "count": len(rows),
    }


def main(argv=None):
    oscompat.utf8_stdio()
    args = sys.argv[1:] if argv is None else list(argv)
    proj = args[0] if args else "demo"
    res = export_cpl(proj, args[1] if len(args) > 1 else None)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
