"""
Check stock and price for the BOM lines of a project. Every answer is stored with
its supplier and the time (supply-log.jsonl) - stock and price are never stated
from memory.

    python scripts/skills/check_availability.py <project> [LINE ...]

LCSC/JLCPCB: the public parts search that jlcpcb.com itself uses (no login). A line with
a declared LCSC code (`lcsc`, e.g. from an Altium import) is looked up by that code first;
the MPN is searched only when the code finds nothing. When the code names a part whose model
is not the line's MPN, stock and price are still the code's, but the result carries
`warning: code_mpn_mismatch` with a sentence (JLC places what the code names; another code is
suggested only when an MPN search finds that exact part), and the BOM line gets a risk tag.
Mouser: set MOUSER_API_KEY. DigiKey is not wired up (it needs OAuth); a supplier
that was not checked simply has no row, so "not checked" never looks like "no stock".
The endpoint is not a documented API - if it changes, this skill says so and stores nothing.
"""
import json
import os
import pathlib
import re
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


def _from_raw(pick, exact):
    return {
        "stock": pick.get("stockCount", 0),
        "price": jlc_price(pick),
        "code": pick.get("componentCode"),
        "model": pick.get("componentModelEn"),
        "exact": exact,
        "library_type": jlc._parse_library_type(pick),
        "package": pick.get("componentSpecificationEn"),
        "datasheet_url": jlc._parse_datasheet_url(pick),
        "brand": pick.get("componentBrandEn"),
    }


def _from_part(p):
    return {
        "stock": p.get("stock", 0),
        "price": jlc_price(p),
        "code": p.get("code"),
        "model": p.get("mpn"),
        "exact": p.get("exact"),
        "library_type": p.get("library_type"),
        "package": p.get("package"),
        "datasheet_url": p.get("datasheet_url"),
        "brand": p.get("manufacturer"),
    }


def lcsc_by_code(code):
    """The part with exactly this LCSC code - `exact` means the code matched - or None."""
    code = (code or "").strip().upper()
    if jlc_search is not _orig_jlc_search:
        pick = next((c for c in jlc_search(code) if (c.get("componentCode") or "").upper() == code), None)
        return _from_raw(pick, True) if pick else None
    p = jlc.part_by_code(code)
    return _from_part(p) if p else None


# what a reel adds to an MPN and a distributor's model often leaves out
_PACKING = ("TRPBF", "TR", "REEL", "TAPE")


def _norm_mpn(s):
    s = re.sub(r"\s*\([^)]*\)\s*$", "", str(s or "")).upper()        # a trailing note: "ABC123 (reel)"
    s = re.sub(r"\+T?$", "", s)                                      # Maxim/Analog: MAX31856MUD+ and +T
    return re.sub(r"[\s/\-_]", "", s)


def mpn_matches(a, b):
    """Is the model JLC lists the MPN of the line? Case, spaces, / - _ and a trailing
    (note) never matter, nor does a reel suffix on one side. Nothing to compare: a match."""
    a, b = _norm_mpn(a), _norm_mpn(b)
    if not a or not b or a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    return long_.startswith(short) and long_[len(short):] in _PACKING


def code_mismatch(mpn, found, declared):
    """The sentence for a declared LCSC code that is another part than the line's MPN. An
    alternative code is named only when searching the MPN finds that exact part."""
    brand = re.sub(r"\s*[(" + chr(0xFF08) + r"].*$", "", found.get("brand") or "").strip()      # "RUILON(...)" -> "RUILON"
    who = " ".join(x for x in (brand, found.get("model")) if x)
    try:
        alt = lcsc_by_mpn(mpn)
    except Exception:                      # a supplier being down only costs the suggestion
        alt = None
    alt_code = alt["code"] if alt and alt.get("exact") and alt.get("code") not in (None, declared) else None
    return (f"LCSC {declared} is {who}, not {mpn}: JLC will place {f'the {brand} part' if brand else 'that part'}. "
            f"Check it is equivalent{f', or use {alt_code}' if alt_code else ''}.")


def lcsc(mpn, code=None):
    """The best match of an MPN: stock, price, LCSC code, model - or None. A declared
    code is tried first: it names the part the student means, the MPN search only guesses.
    Stock and price come from that part even when its model is not the line's MPN, but
    then `code_mismatch` says so: JLC will place what the code names."""
    if code:
        found = lcsc_by_code(code)
        if found:
            if mpn and not mpn_matches(mpn, found["model"]):
                found["code_mismatch"] = code_mismatch(mpn, found, code.strip().upper())
            return found
    return lcsc_by_mpn(mpn)


def lcsc_by_mpn(mpn):
    if not mpn:
        return None
    if jlc_search is not _orig_jlc_search:
        hits = jlc_search(mpn)
        norm = lambda s: (s or "").lower().replace(" ", "")
        exact = [c for c in hits if norm(c.get("componentModelEn")) == norm(mpn)]
        pick = (exact or hits or [None])[0]
        return _from_raw(pick, bool(exact)) if pick else None

    p = jlc.part(mpn)
    return _from_part(p) if p else None


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
        declared = (line.get("lcsc") or "").strip()
        has_mpn = mpn not in ("", "—", "-")
        if not store.qty(line) or not (has_mpn or declared):     # a declared code alone is enough for LCSC
            continue
        for supplier, fn in (("LCSC", lambda m: lcsc(m, declared)), ("Mouser", mouser)):
            if supplier == "Mouser" and not has_mpn:
                continue
            try:
                r = fn(mpn if has_mpn else "")
            except Exception as exc:          # a supplier being down must not stop the others
                results.append({"line": line["key"], "supplier": supplier, "error": str(exc)})
                continue
            if r is None:
                continue
            store.add_supply(project, line["key"], supplier, r["stock"], r["price"], mpn,
                             QTY_BREAK, source=f"{supplier} {r.get('code') or ''}".strip(),
                             library_type=r.get("library_type"), package=r.get("package"),
                             code=r.get("code"), datasheet_url=r.get("datasheet_url"),
                             exact=r.get("exact"), code_mismatch=r.get("code_mismatch"), declared=declared)
            results.append({"line": line["key"], "supplier": supplier, "mpn": mpn, "stock": r["stock"],
                            "price": r["price"], "code": r.get("code"), "exact": r.get("exact"),
                            **({"warning": "code_mpn_mismatch", "message": r["code_mismatch"]}
                               if r.get("code_mismatch") else {})})
    return results


if __name__ == "__main__":
    oscompat.utf8_stdio()
    if len(sys.argv) < 2:
        raise SystemExit("usage: check_availability.py <project> [LINE ...]")
    out = check(sys.argv[1], set(sys.argv[2:]) or None)
    print(json.dumps({"checked_at": store.now(), "results": out}, ensure_ascii=False, indent=2))
