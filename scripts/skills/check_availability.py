"""
Check stock and price for the BOM lines of a project. Every answer is stored with
its supplier and the time (supply-log.jsonl) - stock and price are never stated
from memory.

    python scripts/skills/check_availability.py <project> [LINE ...]

LCSC/JLCPCB: the public parts search that jlcpcb.com itself uses (no login).
Mouser: set MOUSER_API_KEY. DigiKey is not wired up (it needs OAuth); a supplier
that was not checked simply has no row, so "not checked" never looks like "no stock".
The endpoint is not a documented API - if it changes, this skill says so and stores nothing.
"""
import json
import os
import pathlib
import sys
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import jlc      # noqa: E402
import oscompat  # noqa: E402
import store     # noqa: E402

JLC = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"
QTY_BREAK = 10


def _post(url, body, headers=None, timeout=30):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json", **(headers or {})})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def jlc_search(keyword, n=10):
    d = _post(JLC, {"keyword": keyword, "currentPage": 1, "pageSize": n, "searchSource": "search"})
    return ((d.get("data") or {}).get("componentPageInfo") or {}).get("list") or []

_orig_jlc_search = jlc_search


def jlc_price(c, n=QTY_BREAK):
    if not c:
        return None
    ps = c.get("price_breaks") or []
    if ps:
        for p in ps:
            if p["min"] <= n and (p["max"] == -1 or n <= p["max"]):
                return p["price"]
        return ps[0]["price"] if ps else None
    raw_ps = c.get("componentPrices") or []
    for p in raw_ps:
        if p["startNumber"] <= n and (p["endNumber"] == -1 or n <= p["endNumber"]):
            return p["productPrice"]
    return raw_ps[0]["productPrice"] if raw_ps else None


def lcsc(mpn):
    """The best match of an MPN: stock, price, LCSC code, model - or None."""
    if jlc_search is not _orig_jlc_search:
        hits = jlc_search(mpn)
        norm = lambda s: (s or "").lower().replace(" ", "")
        exact = [c for c in hits if norm(c.get("componentModelEn")) == norm(mpn)]
        pick = (exact or hits or [None])[0]
        if not pick:
            return None
        return {
            "stock": pick.get("stockCount", 0),
            "price": jlc_price(pick),
            "code": pick.get("componentCode"),
            "model": pick.get("componentModelEn"),
            "exact": bool(exact),
            "library_type": jlc._parse_library_type(pick),
            "package": pick.get("componentSpecificationEn"),
            "datasheet_url": jlc._parse_datasheet_url(pick),
        }

    p = jlc.part(mpn)
    if not p:
        return None
    return {
        "stock": p.get("stock", 0),
        "price": jlc_price(p),
        "code": p.get("code"),
        "model": p.get("mpn"),
        "exact": p.get("exact"),
        "library_type": p.get("library_type"),
        "package": p.get("package"),
        "datasheet_url": p.get("datasheet_url"),
    }


def mouser(mpn):
    key = os.environ.get("MOUSER_API_KEY")
    if not key:
        return None
    d = _post(f"https://api.mouser.com/api/v1/search/partnumber?apiKey={key}",
              {"SearchByPartRequest": {"mouserPartNumber": mpn}})
    parts = ((d.get("SearchResults") or {}).get("Parts")) or []
    if not parts:
        return {"stock": 0, "price": None, "code": None, "model": mpn, "exact": False}
    p = parts[0]
    stock = int("".join(ch for ch in str(p.get("Availability", "0")).split()[0] if ch.isdigit()) or 0)
    price = None
    for br in p.get("PriceBreaks", []):
        if int(br.get("Quantity", 0)) <= QTY_BREAK:
            price = float(str(br.get("Price", "0")).replace("$", "").replace(",", "") or 0)
    return {"stock": stock, "price": price, "code": p.get("MouserPartNumber"),
            "model": p.get("ManufacturerPartNumber"), "exact": True}


def check(project, keys=None):
    results = []
    for line in store.bom_lines(project):
        if keys and line["key"] not in keys:
            continue
        mpn = (line.get("mpn") or "").strip()
        if not store.qty(line) or mpn in ("", "—", "-"):
            continue
        for supplier, fn in (("LCSC", lcsc), ("Mouser", mouser)):
            try:
                r = fn(mpn)
            except Exception as exc:          # a supplier being down must not stop the others
                results.append({"line": line["key"], "supplier": supplier, "error": str(exc)})
                continue
            if r is None:
                continue
            store.add_supply(project, line["key"], supplier, r["stock"], r["price"], mpn,
                             QTY_BREAK, source=f"{supplier} {r.get('code') or ''}".strip(),
                             library_type=r.get("library_type"), package=r.get("package"),
                             code=r.get("code"), datasheet_url=r.get("datasheet_url"),
                             exact=r.get("exact"))
            results.append({"line": line["key"], "supplier": supplier, "mpn": mpn, "stock": r["stock"],
                            "price": r["price"], "code": r.get("code"), "exact": r.get("exact")})
    return results


if __name__ == "__main__":
    oscompat.utf8_stdio()
    if len(sys.argv) < 2:
        raise SystemExit("usage: check_availability.py <project> [LINE ...]")
    out = check(sys.argv[1], set(sys.argv[2:]) or None)
    print(json.dumps({"checked_at": store.now(), "results": out}, ensure_ascii=False, indent=2))
