import csv
import json
import pathlib
import sys

def main(project):
    pdir = pathlib.Path("projects") / project
    bom_path = pdir / "bom.json"
    if not bom_path.exists():
        print("No BOM found.")
        sys.exit(1)
        
    bom = json.loads(bom_path.read_text(encoding="utf-8"))
    out_path = pdir / "BOM_export.csv"
    
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Designator", "Value", "Footprint", "MPN", "Manufacturer", "Quantity"])
        for item in bom:
            refs = item.get("refs", [])
            writer.writerow([
                ", ".join(refs),
                item.get("value", ""),
                item.get("package", ""),
                item.get("mpn", ""),
                item.get("manufacturer", ""),
                len(refs)
            ])
    print(f"BOM exported to {out_path}")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "demo")
