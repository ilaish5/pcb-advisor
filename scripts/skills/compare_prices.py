"""
Compare what the BOM costs per board at each supplier, from the stored checks.

    python scripts/skills/compare_prices.py <project>

Reads supply-log.jsonl (through the derived BOM); it does not query anyone. If a
number is old, run check_availability first. A line nobody stocks is reported,
not priced at zero.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import oscompat  # noqa: E402
import store     # noqa: E402


def compare(project):
    lines = store.bom(project, write=False)
    out = []
    for supplier in store.SUPPLIERS:
        cost, missing, unchecked, checked_at = 0.0, [], [], ""
        for l in lines:
            q = store.qty(l)
            if not q:
                continue
            s = (l.get("supply") or {}).get(supplier)
            if s is None:
                unchecked.append(l["key"])
            elif s.get("unit_price") is not None and (s.get("stock") or 0) >= q:
                cost += s["unit_price"] * q
                checked_at = max(checked_at, s.get("checked_at") or "")
            else:
                missing.append(l["key"])
        out.append({"supplier": supplier, "cost_per_board": round(cost, 4), "missing": missing,
                    "not_checked": unchecked, "checked_at": checked_at or None})
    return {"qty_break": 10, "suppliers": out}


if __name__ == "__main__":
    oscompat.utf8_stdio()
    print(json.dumps(compare(sys.argv[1] if len(sys.argv) > 1 else "demo"), ensure_ascii=False, indent=2))
