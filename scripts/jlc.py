"""
JLC client with disk cache, part lookup, and alternatives search.

Provides search and part lookup against JLCPCB component database with
disk-caching of queries under the workspace shared cache directory.
"""
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import workspace  # noqa: E402

JLC_URL = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"
DEFAULT_TRANSPORT = None


class JLCError(Exception):
    """Raised when JLC request fails or returns an error."""
    pass


def cache_dir():
    """Disk cache folder under the workspace shared directory."""
    d = workspace.shared_dir() / "cache" / "jlc"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_path(keyword, n):
    slug = re.sub(r"[^A-Za-z0-9._-]", "_", keyword.strip())[:40]
    h = hashlib.sha256(f"{keyword.strip().lower()}_{n}".encode("utf-8")).hexdigest()[:12]
    return cache_dir() / f"{slug}_{h}.json"


def _get_cached(keyword, n):
    path = _cache_path(keyword, n)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    cached_time = data.get("ts", 0)
    ttl_hours = float(workspace.get("jlc.cache_hours", 6))
    if time.time() - cached_time >= ttl_hours * 3600:
        return None
    return data.get("results")


def _set_cached(keyword, n, results):
    try:
        path = _cache_path(keyword, n)
        record = {
            "keyword": keyword,
            "n": n,
            "ts": time.time(),
            "results": results,
        }
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _default_transport(url, body, headers=None, timeout=30):
    req_headers = {
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/json",
        **(headers or {}),
    }
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        raise JLCError(f"HTTP {e.code}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise JLCError(f"Network error: {e.reason}") from e
    except Exception as e:
        raise JLCError(f"Request failed: {e}") from e


def _call_transport(transport, url, body, headers=None, timeout=30):
    fn = transport or DEFAULT_TRANSPORT or _default_transport
    try:
        try:
            res = fn(url, body, headers=headers, timeout=timeout)
        except TypeError:
            try:
                res = fn(url, body, headers=headers)
            except TypeError:
                res = fn(url, body)
    except JLCError:
        raise
    except Exception as exc:
        raise JLCError(f"Transport failed: {exc}") from exc

    if isinstance(res, (bytes, str)):
        try:
            res = json.loads(res)
        except Exception as exc:
            raise JLCError(f"Invalid JSON from transport: {exc}") from exc
    if not isinstance(res, dict):
        raise JLCError("Transport did not return a dict response")
    return res


def _parse_library_type(c):
    lt = c.get("library_type")
    if lt in ("Basic", "Extended", "Preferred", ""):
        return lt
    if c.get("preferredComponentFlag"):
        return "Preferred"
    raw = str(c.get("componentLibraryType") or "").lower()
    if raw in ("base", "basic"):
        return "Basic"
    if raw in ("expand", "extended"):
        return "Extended"
    return ""


def _parse_datasheet_url(c):
    if c.get("datasheet_url"):
        return c["datasheet_url"]
    access_id = c.get("dataManualFileAccessId")
    if access_id:
        return f"https://jlcpcb.com/api/file/downloadByFileSystemAccessId/{access_id}"
    return c.get("dataManualUrl") or ""


def _parse_price_breaks(c):
    if "price_breaks" in c:
        return [
            {"min": int(b.get("min", 0)), "max": int(b.get("max", -1)), "price": float(b.get("price", 0.0))}
            for b in c["price_breaks"]
        ]
    return [
        {"min": int(p.get("startNumber", 0)), "max": int(p.get("endNumber", -1)), "price": float(p.get("productPrice", 0.0))}
        for p in (c.get("componentPrices") or [])
    ]


def _parse_part(c, requested_mpn=None):
    code = c.get("componentCode") or c.get("code") or ""
    mpn = c.get("componentModelEn") or c.get("mpn") or ""
    manufacturer = c.get("componentBrandEn") or c.get("manufacturer") or ""
    package = c.get("componentSpecificationEn") or c.get("package") or ""
    description = c.get("describe") or c.get("description") or ""
    stock = int(c.get("stockCount", c.get("stock", 0)) or 0)
    price_breaks = _parse_price_breaks(c)
    library_type = _parse_library_type(c)
    datasheet_url = _parse_datasheet_url(c)

    norm = lambda s: (s or "").lower().replace(" ", "").replace("-", "")
    if "exact" in c:
        exact = bool(c["exact"])
    elif requested_mpn:
        exact = norm(mpn) == norm(requested_mpn)
    else:
        exact = False

    checked_at = c.get("checked_at") or dt.datetime.now().isoformat(timespec="seconds")

    return {
        "code": code,
        "mpn": mpn,
        "manufacturer": manufacturer,
        "package": package,
        "description": description,
        "stock": stock,
        "price_breaks": price_breaks,
        "library_type": library_type,
        "datasheet_url": datasheet_url,
        "exact": exact,
        "checked_at": checked_at,
    }


def search(keyword, n=10, transport=None):
    """Search JLC components by keyword or MPN, returning list of parsed match dicts."""
    keyword_str = (keyword or "").strip()
    if not keyword_str:
        return []

    cached = _get_cached(keyword_str, n)
    if cached is not None:
        return cached

    body = {"keyword": keyword_str, "currentPage": 1, "pageSize": n, "searchSource": "search"}
    raw = _call_transport(transport, JLC_URL, body)

    # Validate raw response structure
    data = raw.get("data")
    if data is None and raw.get("code") not in (None, 200, 0):
        raise JLCError(f"JLC error response: {raw.get('message') or raw.get('msg') or raw.get('code')}")

    page_info = (data or {}).get("componentPageInfo") or {}
    raw_list = page_info.get("list")
    if raw_list is None and isinstance(data, list):
        raw_list = data
    if raw_list is None:
        raw_list = []

    results = [_parse_part(c, requested_mpn=keyword_str) for c in raw_list]
    _set_cached(keyword_str, n, results)
    return results


def part(mpn, transport=None):
    """The best match for an MPN, or None."""
    mpn_str = (mpn or "").strip()
    if not mpn_str or mpn_str in ("—", "-"):
        return None

    hits = search(mpn_str, n=10, transport=transport)
    if not hits:
        return None

    norm = lambda s: (s or "").lower().replace(" ", "").replace("-", "")
    target = norm(mpn_str)
    exact_hits = [c for c in hits if norm(c.get("mpn")) == target]
    pick = exact_hits[0] if exact_hits else hits[0]
    out = dict(pick)
    out["exact"] = bool(exact_hits and pick == exact_hits[0])
    return out


def part_by_code(code, transport=None):
    """The part with this LCSC code, or None. The search is by keyword, so a code also
    returns look-alikes (C94355 finds MIC94355-...): only the exact code counts."""
    code_str = (code or "").strip().upper()
    if not re.fullmatch(r"C\d{2,}", code_str):
        return None
    pick = next((c for c in search(code_str, n=10, transport=transport)
                 if (c.get("code") or "").upper() == code_str), None)
    if not pick:
        return None
    return {**pick, "exact": True}


def _norm_pkg(p):
    return (p or "").lower().replace(" ", "").replace("-", "").replace("_", "")


def alternatives(line, n=5, transport=None):
    """
    Find in-stock alternatives with the same package and a matching value/keyword,
    Basic/Preferred first, excluding the current code.
    """
    line_dict = line if isinstance(line, dict) else {}
    cur_code = line_dict.get("code") or ""
    if not cur_code and isinstance(line_dict.get("supply"), dict):
        cur_code = (line_dict["supply"].get("LCSC") or {}).get("code") or ""
    cur_mpn = (line_dict.get("mpn") or "").strip()
    pkg = (line_dict.get("package") or "").strip()
    val = (line_dict.get("value") or "").strip()
    desc = (line_dict.get("description") or "").strip()

    kw = (line_dict.get("keyword") or val or desc or cur_mpn).strip()
    if not kw:
        return []

    hits = search(kw, n=max(n * 4, 20), transport=transport)
    norm_line_pkg = _norm_pkg(pkg)

    candidates = []
    for h in hits:
        if h.get("stock", 0) <= 0:
            continue
        if cur_code and h.get("code") == cur_code:
            continue
        if cur_mpn and h.get("mpn") == cur_mpn:
            continue

        norm_h_pkg = _norm_pkg(h.get("package"))
        if norm_line_pkg and norm_h_pkg:
            if norm_line_pkg != norm_h_pkg and norm_line_pkg not in norm_h_pkg and norm_h_pkg not in norm_line_pkg:
                continue

        candidates.append(h)

    def _priority(c):
        lt = c.get("library_type")
        if lt == "Basic":
            return 0
        if lt == "Preferred":
            return 1
        if lt == "Extended":
            return 2
        return 3

    candidates.sort(key=_priority)
    return candidates[:n]


# ---- pure snapshot rules (no network); shared by the product and bench/checks_parts.py

EXPENSIVE_SHARE = 0.25     # an Extended line costing >= this share of the board's parts cost
EXPENSIVE_MIN_COST = 5.0   # ... and at least this many USD per board


def stock_shortfall(stock, qty_per_board, boards):
    """Units missing to build `boards` boards, or 0. `stock` None means unknown -> 0."""
    if stock is None:
        return 0
    return max(0, int(qty_per_board) * int(boards) - int(stock))


def is_standard_only(assembly):
    """True when a JLC assembly note says the part can only go on Standard (not Economic) assembly."""
    return "standard only" in str(assembly or "").lower()


def expensive_extended_lines(lines, share=EXPENSIVE_SHARE, min_cost=EXPENSIVE_MIN_COST):
    """lines: [{refs, qty, unit_price, library_type}]. Returns the Extended lines whose cost per
    board is >= `share` of the total priced cost and >= `min_cost` USD. Each result gets
    cost_per_board and share."""
    priced = [(l, (l.get("unit_price") or 0.0) * (l.get("qty") or 0)) for l in lines]
    total = sum(c for _, c in priced)
    out = []
    for l, c in priced:
        if total > 0 and l.get("library_type") == "Extended" and c >= min_cost and c / total >= share:
            out.append({**l, "cost_per_board": round(c, 4), "share": round(c / total, 3)})
    return out


if __name__ == "__main__":
    import oscompat
    oscompat.utf8_stdio()
    args = sys.argv[1:]
    if not args:
        print("Usage: python jlc.py [search <kw> | part <mpn> | alternatives <kw> [pkg]]")
        sys.exit(1)
    cmd = args[0]
    if cmd == "search" and len(args) > 1:
        print(json.dumps(search(args[1]), indent=2, ensure_ascii=False))
    elif cmd == "part" and len(args) > 1:
        print(json.dumps(part(args[1]), indent=2, ensure_ascii=False))
    elif cmd == "alternatives" and len(args) > 1:
        dummy_line = {"value": args[1], "package": args[2] if len(args) > 2 else ""}
        print(json.dumps(alternatives(dummy_line), indent=2, ensure_ascii=False))
    else:
        print(json.dumps(part(args[0]), indent=2, ensure_ascii=False))
