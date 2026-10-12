"""
Export Pick and Place / CPL file for JLCPCB from linked Altium PcbDoc or BOM.

    python scripts/skills/export_cpl.py <project>

Writes projects/<project>/exports/<project>_cpl.csv with columns:
    Designator, Mid X, Mid Y, Layer, Rotation
"""
import csv
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import oscompat  # noqa: E402
import project as project_mod  # noqa: E402
import workspace  # noqa: E402
from altium.pcbdoc import read_pcbdoc  # noqa: E402


def export_cpl(project: str, pcb_path: str | pathlib.Path | None = None) -> dict:
    link = project_mod.altium_link(project)
    p_pcb = pcb_path or link.get("pcb_file")

    rows = []
    if p_pcb and pathlib.Path(p_pcb).is_file():
        doc = read_pcbdoc(p_pcb)
        for c in doc.get("components", []):
            ref = c.get("ref", "")
            if not ref:
                continue
            layer = "Top" if "top" in str(c.get("layer", "")).lower() else "Bottom"
            rows.append({
                "Designator": ref,
                "Mid X": f"{c.get('x_mm', 0.0):.4f}mm",
                "Mid Y": f"{c.get('y_mm', 0.0):.4f}mm",
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

    out_dir = workspace.project_dir(project) / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{project}_cpl.csv"

    with open(out_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        writer.writeheader()
        writer.writerows(rows)

    home = workspace.home()
    shown = out_file.relative_to(home).as_posix() if out_file.is_relative_to(home) else str(out_file)
    return {
        "file": shown,
        "name": out_file.name,
        "count": len(rows),
    }


def main(argv=None):
    oscompat.utf8_stdio()
    proj = sys.argv[1] if len(sys.argv) > 1 else "demo"
    res = export_cpl(proj)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
