"""Stage B/C detectors: parts, stock and library (incidents 1-5).

Each detector reads only the fixture's state files (jlc_snapshot.json,
library_parts.csv, footprint_facts.json) and applies a general rule shared with
the product (scripts/jlc.py, scripts/store.py, scripts/library.py). Nothing here
looks at incident.json.
"""
import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import jlc      # noqa: E402
import library  # noqa: E402
import store    # noqa: E402

from bench.detectors import register  # noqa: E402

DETECTORS = []
DEFAULT_BOARDS = 5   # used when the snapshot does not record the board count


def _mine(code):
    reg = register(code)

    def deco(fn):
        DETECTORS.append((code, fn))
        return reg(fn)
    return deco


def _snapshot(fixture_dir):
    p = pathlib.Path(fixture_dir) / "jlc_snapshot.json"
    if not p.is_file():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    return data if isinstance(data.get("rows"), list) else None


def _rows(snap):
    return [r for r in snap["rows"] if r.get("refs")]


def _line(row):
    """A store-style BOM line + best offer built from one snapshot row (no network)."""
    stock, lt, price = row.get("stock"), row.get("lib_type") or "", row.get("unit_price_usd_qty1")
    line = {"refs": list(row["refs"]), "library_type": lt}
    if stock is None:
        return line, None
    line["supply"] = {"LCSC": {"stock": stock, "library_type": lt, "exact": True}}
    best = None
    if stock >= len(row["refs"]):
        best = {"stock": stock, "library_type": lt, "unit_price": price}
    return line, best


@_mine("footprint_variant_mismatch")
def footprint_variant(fixture_dir, incident):
    d = pathlib.Path(fixture_dir)
    p = d / "library_parts.csv"
    if not p.is_file():
        return []
    facts = {}
    if (d / "footprint_facts.json").is_file():
        facts = json.loads((d / "footprint_facts.json").read_text(encoding="utf-8"))
    out = []
    with p.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            hit = library.footprint_variant_conflict(row.get("ordered_mpn"), row.get("footprint"))
            if not hit:
                continue
            msg = (f"{row['ref']}: ordered {row['ordered_mpn']} (variant {hit['ordered_variant']}) but library "
                   f"footprint {row['footprint']} is the {hit['family']}{hit['footprint_variant']} variant "
                   f"(library_parts.csv)")
            counts = {k: v for k, v in facts.items() if k.endswith("_pad_count")}
            if facts.get("part") == row["ref"] and len(counts) >= 2:
                msg += "; pad counts " + ", ".join(f"{k}={v}" for k, v in counts.items()) + " (footprint_facts.json)"
            out.append({"code": "footprint_variant_mismatch", "refs": [row["ref"]], "message": msg,
                        "source": "library_parts.csv"})
    return out


@_mine("jlc_no_match")
def no_match(fixture_dir, incident):
    snap = _snapshot(fixture_dir)
    if not snap:
        return []
    bad = [r for r in _rows(snap) if r.get("match") == "no_match"]
    if not bad:
        return []
    refs = [x for r in bad for x in r["refs"]]
    return [{"code": "jlc_no_match", "refs": refs, "source": "jlc_snapshot.json",
             "message": f"{len(bad)} BOM lines have no JLC match (match=no_match in jlc_snapshot.json): {', '.join(refs)}"}]


@_mine("expensive_extended_part")
def expensive_extended(fixture_dir, incident):
    snap = _snapshot(fixture_dir)
    if not snap:
        return []
    lines = []
    for r in _rows(snap):
        line, best = _line(r)
        _, lib_type, _, _ = store.line_availability_and_risk(line, best, build_qty=snap.get("boards") or DEFAULT_BOARDS)
        lines.append({"refs": r["refs"], "qty": len(r["refs"]), "unit_price": r.get("unit_price_usd_qty1"),
                      "library_type": lib_type})
    return [{"code": "expensive_extended_part", "refs": l["refs"], "source": "jlc_snapshot.json",
             "message": (f"{', '.join(l['refs'])}: Extended part at {l['cost_per_board']} USD per board, "
                         f"{l['share']:.0%} of the priced parts cost (unit_price_usd_qty1 in jlc_snapshot.json)")}
            for l in jlc.expensive_extended_lines(lines)]


@_mine("part_out_of_stock")
def out_of_stock(fixture_dir, incident):
    snap = _snapshot(fixture_dir)
    if not snap:
        return []
    boards = snap.get("boards") or DEFAULT_BOARDS
    out = []
    for r in _rows(snap):
        if r.get("stock") is None:
            continue
        line, best = _line(r)
        _, _, _, risk = store.line_availability_and_risk(line, best, build_qty=boards)
        short = jlc.stock_shortfall(r["stock"], len(r["refs"]), boards)
        if "out of stock" in risk:
            why = f"stock {r['stock']}"
        elif short:
            why = f"stock {r['stock']} is {short} short of {len(r['refs']) * boards} needed for {boards} boards"
        else:
            continue
        out.append({"code": "part_out_of_stock", "refs": list(r["refs"]), "source": "jlc_snapshot.json",
                    "message": f"{', '.join(r['refs'])}: {r.get('jlc_part')} {why} at JLC (jlc_snapshot.json)"})
    return out


@_mine("assembly_standard_only")
def standard_only(fixture_dir, incident):
    snap = _snapshot(fixture_dir)
    if not snap:
        return []
    return [{"code": "assembly_standard_only", "refs": list(r["refs"]), "source": "jlc_snapshot.json",
             "message": (f"{', '.join(r['refs'])}: {r.get('jlc_part')} assembly is '{r['assembly']}' "
                         f"(jlc_snapshot.json), economic assembly not possible")}
            for r in _rows(snap) if jlc.is_standard_only(r.get("assembly"))]
