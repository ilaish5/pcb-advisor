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


def jlc_price(c, n=QTY_BREAK):
    ps = c.get("componentPrices") or []
    for p in ps:
        if p["startNumber"] <= n and (p["endNumber"] == -1 or n <= p["endNumber"]):
            return p["productPrice"]
    return ps[0]["productPrice"] if ps else None


def lcsc(mpn):
    """The best match of an MPN: stock, price, LCSC code, model - or None."""
    hits = jlc_search(mpn)
    norm = lambda s: (s or "").lower().replace(" ", "")
    exact = [c for c in hits if norm(c.get("componentModelEn")) == norm(mpn)]
    pick = (exact or hits or [None])[0]
    if not pick:
        return None
    return {"stock": pick.get("stockCount", 0), "price": jlc_price(pick), "code": pick.get("componentCode"),
            "model": pick.get("componentModelEn"), "exact": bool(exact)}


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
                             QTY_BREAK, source=f"{supplier} {r.get('code') or ''}".strip())
            results.append({"line": line["key"], "supplier": supplier, "mpn": mpn, "stock": r["stock"],
                            "price": r["price"], "code": r.get("code"), "exact": r.get("exact")})
    return results


if __name__ == "__main__":
    oscompat.utf8_stdio()
    if len(sys.argv) < 2:
        raise SystemExit("usage: check_availability.py <project> [LINE ...]")
    out = check(sys.argv[1], set(sys.argv[2:]) or None)
    print(json.dumps({"checked_at": store.now(), "results": out}, ensure_ascii=False, indent=2))
