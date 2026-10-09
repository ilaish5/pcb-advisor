import json
import sys
import pathlib

def validate(sheet_json_path, bom_json_path):
    with open(sheet_json_path, 'r', encoding='utf-8') as f:
        sheet = json.load(f)
    with open(bom_json_path, 'r', encoding='utf-8') as f:
        bom = json.load(f)

    bom_refs = set()
    for item in bom:
        bom_refs.update(item.get("refs", []))

    errors = []
    for part in sheet.get("parts", []):
        ref = part.get("ref")
        if ref not in bom_refs:
            errors.append(f"Part {ref} in netlist not found in BOM.")
        
        for pin in part.get("pins", []):
            net = pin.get("net")
            if not net:
                errors.append(f"Pin {pin.get('name')} of {ref} is missing a net.")
    return errors

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python validate_netlist.py <sheet_json> <bom_json>")
        sys.exit(1)
    
    errors = validate(sys.argv[1], sys.argv[2])
    if errors:
        for err in errors:
            print(err)
        sys.exit(1)
    print("Netlist valid.")
