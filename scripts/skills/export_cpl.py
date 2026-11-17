"""
Export Pick and Place / CPL file for JLCPCB from linked Altium PcbDoc or BOM.

    python scripts/skills/export_cpl.py <project>

Writes projects/<project>/exports/<project>_cpl.csv with columns:
    Designator, Mid X, Mid Y, Layer, Rotation

Positions are relative to the board origin (Board6 ORIGINX/ORIGINY), as Altium writes them; Mid is the centre
of the part's pads, which matched Altium's "Center" column on 148 of 149 parts of a real board (a U.FL was
0.29 mm off). Rotation is the PcbDoc rotation plus the BOM line's CPL rotation offset (`cpl_rotation`, set by the student's
approval after JLC's preview shows the part turned; never set from the package name). Bottom parts with an
offset are listed in the result's warnings: JLC does not document bottom-side rotation.
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


BOTTOM_WARNING = ("Bottom-side parts with a CPL rotation offset ({refs}): JLC does not document how bottom-side "
                  "rotation is counted; the offset was added as for Top parts. Check these parts in JLC's placement preview.")


def rotation_offsets(project: str) -> dict[str, int]:
    """ref -> CPL rotation offset (degrees) of the BOM line that holds it. Only what the student approved."""
    import store
    out = {}
    for l in store.bom_lines(project):
        if l.get("cpl_rotation") not in (None, ""):
            for r in l.get("refs", []):
                out[r] = store.cpl_rotation_value(l["cpl_rotation"])
    return out


def _apply_offsets(rows: list[dict], offsets: dict[str, int], applied: list | None) -> None:
    for row in rows:
        off = offsets.get(row["Designator"])
        if off:
            row["Rotation"] = f"{(float(row['Rotation']) + off) % 360:.1f}"
            if applied is not None:
                applied.append({"ref": row["Designator"], "offset": off, "layer": row["Layer"]})


def cpl_rows(project: str, pcb_path: str | pathlib.Path | None = None, applied: list | None = None) -> list[dict]:
    """The rows the CPL file holds: from the PcbDoc when there is one, else a stub per BOM reference.
    The BOM line's CPL rotation offset is added to the PcbDoc rotation; `applied` collects the refs that got one."""
    rows = _raw_rows(project, pcb_path)
    _apply_offsets(rows, rotation_offsets(project), applied)
    return rows


def _raw_rows(project: str, pcb_path: str | pathlib.Path | None = None) -> list[dict]:
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
    applied: list = []
    rows = cpl_rows(project, from_pcb or None, applied)

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
    res = {
        "file": shown,
        "name": out_file.name,
        "count": len(rows),
        "rotation_offsets": applied,
        "warnings": [],
    }
    bottom = [a["ref"] for a in applied if a["layer"] != "Top"]
    if bottom:
        res["warnings"].append(BOTTOM_WARNING.format(refs=", ".join(bottom)))
    return res


def main(argv=None):
    oscompat.utf8_stdio()
    args = sys.argv[1:] if argv is None else list(argv)
    proj = args[0] if args else "demo"
    res = export_cpl(proj, args[1] if len(args) > 1 else None)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
