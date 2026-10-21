"""The order step: design vs ordering, by footprint.

During design a BOM line is fixed by value + package + pins and the project library is built from it. At ordering the
stock is checked again and a line that is out of stock or short may change its MPN / LCSC C-number FREELY when the new
part has the same footprint (the same land pattern) and the same function (the same pins): no schematic, library or board change. A swap to
another footprint is a design change: a library rebuild and a PCB update.

  python scripts/order_check.py <project> [--recheck]

order_check() classifies every bought line:
  ok               stock is fine (or not checked yet: class "unchecked")
  swap_free        short or out, and an in-stock alternative has the SAME footprint: order-only swap
  design_change    short or out, and every alternative has another (or an unproven) footprint
  no_alternative   short or out, nothing found
A swap is proposed through store.propose_bom with footprint_lock = the footprint name proven "same"; it still needs
approval like any part change. The lock is checked again when the proposal is made, never taken on trust.
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "skills"))
import jlc  # noqa: E402
import partlib  # noqa: E402
import partlib_order  # noqa: E402
import store  # noqa: E402

ALTERNATIVES = 3
LOW_FACTOR = 10         # stock under this many builds is a warning on an ok line (store.line_availability_and_risk's threshold)


def swap_changes(alt, footprint):
    """The changes of an order-only swap to alternative `alt` (a jlc.alternatives row) that keeps `footprint`."""
    return {"mpn": alt["mpn"], "lcsc": alt["code"], "manufacturer": alt.get("manufacturer") or "—", "footprint_lock": footprint}


def swap_reason(alt, footprint):
    return f"order-only swap: same footprint {footprint} ({alt['code']}, {alt['stock']} in stock)"


def _alternative(project, line, alt):
    m = partlib_order.footprint_match(project, line["key"], alt.get("code"), cand=alt)
    unit = (alt.get("price_breaks") or [{}])[0].get("price")
    return {"mpn": alt.get("mpn"), "code": alt.get("code"), "manufacturer": alt.get("manufacturer"),
            "package": alt.get("package"), "stock": alt.get("stock"), "unit_price": unit,
            "library_type": alt.get("library_type"), "match": m["match"], "why": m["why"], "footprint": m["footprint"]}


def lcsc_stock(line):
    """What JLC can place: the LCSC answer's stock, or None while LCSC has not answered for this line."""
    found = (line.get("supply") or {}).get("LCSC")
    return None if found is None else (found.get("stock") or 0)


def classify(line, alts, need):
    """'ok' | 'unchecked' | 'swap_free' | 'design_change' | 'no_alternative' for one bought line. Only LCSC stock below
    the need (or no LCSC answer) asks for an alternative; low stock above the need is a warning on an ok line."""
    if line.get("supply") is None:
        return "unchecked"
    stock = lcsc_stock(line)
    if stock is not None and stock >= need:
        return "ok"
    if any(a["match"] == "same" for a in alts):
        return "swap_free"
    return "design_change" if alts else "no_alternative"


def order_check(project, recheck=False):
    """{lines: [one per bought line], counts, params_stale, checked_at}. recheck asks the suppliers again first (it writes
    the supply log); a library that was current stays current when the answers change nothing it is made of."""
    if recheck:
        import check_availability
        check_availability.check(project)
        partlib_order.restamp_if_same(project)
    build_qty = int(store.workspace.get("jlc.build_qty", 5))
    out, counts = [], {}
    for l in store.bom(project, write=False):
        q = store.qty(l)
        if not q:
            continue
        need, alts = q * build_qty, []
        short = l.get("supply") is not None and (lcsc_stock(l) is None or lcsc_stock(l) < need)
        if short:
            try:
                found = jlc.alternatives(l, n=ALTERNATIVES * 2)
            except Exception:                        # a supplier being down costs the alternatives, not the check
                found = []
            found = [a for a in found if (a.get("stock") or 0) >= need]     # one that cannot cover the build is no way out
            alts = [_alternative(project, l, a) for a in found[:ALTERNATIVES]]
            alts.sort(key=lambda a: a["match"] != "same")
        cls = classify(l, alts, need)
        counts[cls] = counts.get(cls, 0) + 1
        stock = lcsc_stock(l)
        out.append({"line": l["key"], "refs": l.get("refs", []), "mpn": l.get("mpn"), "lcsc": l.get("lcsc") or l.get("code") or "",
                    "package": l.get("package"), "qty": q, "need": need, "availability": l.get("availability"),
                    "stock": stock, "risk": l.get("risk") or [], "class": cls, "alternatives": alts,
                    "warnings": ["low stock"] if cls == "ok" and stock < need * LOW_FACTOR else []})
    return {"lines": out, "counts": counts, "params_stale": partlib_order.params_notices(project), "checked_at": store.now()}


def summary(res):
    """A few words for the agent's action result."""
    c = res["counts"]
    todo = [f"{l['line']} {l['class']}" for l in res["lines"] if l["class"] in ("swap_free", "design_change", "no_alternative")]
    return (f"{len(res['lines'])} lines, " + ", ".join(f"{n} {k}" for k, n in sorted(c.items()))
            + (": " + "; ".join(todo[:6]) + (f" +{len(todo) - 6}" if len(todo) > 6 else "") if todo else "")
            + "".join(" " + n + "." for n in res.get("params_stale", [])))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Before you order: stock, and alternatives by footprint.")
    ap.add_argument("project")
    ap.add_argument("--recheck", action="store_true", help="ask the suppliers again first")
    a = ap.parse_args(argv)
    print(json.dumps(order_check(a.project, a.recheck), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
