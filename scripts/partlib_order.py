"""Ordering: land patterns, whether an LCSC part can replace a BOM line at order time, order-only swaps. None of this
shapes the built library, so it is NOT in partlib.converter_fingerprint (editing it must not make libraries stale)."""
import hashlib
import json
import os
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import partlib  # noqa: E402
import partlib_match as pm  # noqa: E402
import store  # noqa: E402
from altium import bridge  # noqa: E402
from partlib_generate import package_key  # noqa: E402

GENERATED = ("generated", "kicad")      # footprints with no EasyEDA/vendor pads of their own: matched by package, not by pads
NOT_CURRENT = "the library is not built for the current BOM; build it first"
library_dir = partlib.library_dir


def land_pattern(lines):
    """The copper and holes of a footprint's spec lines: one tuple per pad, sorted, in mm rounded to 0.01: (number, shape, w, h,
    x, y, plated, hole, hole type, slot width, slot turn, pad turn). A pad turned a quarter turn swaps w and h (its slot
    turns with it); another turn stays in the tuple. Silk, courtyard and layer are not land."""
    mm = lambda v: round(float(v or 0) * 0.0254, 2) + 0.0
    out = []
    for ln in lines:
        f = ln.split("|")
        if f[0] != "PAD" or len(f) < 14:
            continue
        w, h, rot, hrot = mm(f[11]), mm(f[12]), round(float(f[4] or 0)) % 180, round(float(f[10] or 0)) % 180
        if rot == 90:
            w, h, rot, hrot = h, w, 0, (hrot + 90) % 180
        slot = f[8] not in ("", "0")
        out.append((f[1], f[13], w, h, mm(f[2]), mm(f[3]), f[6], mm(f[7]), f[8], mm(f[9]), hrot if slot else 0, rot))
    return sorted(out)


def land_fingerprint(lines):
    return hashlib.sha1(json.dumps(land_pattern(lines)).encode()).hexdigest()[:12]


def _pins(lines):
    return {p[0] for p in land_pattern(lines)}


def footprint_of(project, key):
    """What the board uses for line `key`, from the library build: {name, source, package, lcsc, pads, pins, fingerprint,
    lines, symbol, symbol_pins} (fingerprint: hash of the land pattern, None while the build files are missing), or None
    without a footprint."""
    lib = library_dir(project)
    try:
        e = json.loads((lib / "manifest.json").read_text(encoding="utf-8")).get(key) or {}
    except (OSError, json.JSONDecodeError):
        return None
    if not e.get("footprint"):
        return None
    fp = partlib._spec_footprints(lib / "build" / "footprints_spec.txt").get(e["footprint"])
    sym = partlib._spec_symbols(lib / "build" / "symbols_spec.txt").get(e.get("symbol"))
    return {"name": e["footprint"], "source": e.get("source", ""), "package": e.get("package", ""), "lcsc": e.get("lcsc", ""),
            "pads": len(land_pattern(fp["lines"])) if fp else 0, "pins": sorted(_pins(fp["lines"])) if fp else [],
            "fingerprint": land_fingerprint(fp["lines"]) if fp else None, "lines": fp["lines"] if fp else [],
            "symbol": e.get("symbol", ""), "symbol_pins": sym["pins"] if sym else []}


def _candidate(project, code, fetcher=None):
    """(symbol, footprint, "") of an LCSC part's EasyEDA download, cached in library/easyeda/<C>/ like prepare does;
    (None, None, why) when it cannot be had."""
    dest = library_dir(project) / "easyeda" / code
    if not (dest / "lib.kicad_sym").exists():
        ok, msg = (fetcher or partlib.fetch_one)(code, dest)
        if not ok:
            return None, None, f"EasyEDA has no footprint for {code} ({msg})"
    try:
        sym, fp, _ = partlib._easyeda_part(dest)
        return sym, fp, ""
    except (ValueError, KeyError, IndexError, TypeError, OSError, UnicodeError):
        return None, None, f"the EasyEDA download of {code} could not be read"


def _function(project, key, line, fp, sym, cand, code):
    """The electrical half of a match, after the land pattern agrees: (None, why) when the candidate is the same part
    electrically, ("different" | "unknown", why) otherwise. Pin names for ICs and polar parts, value and kind for plain
    2-pin resistors, capacitors and inductors."""
    prefix = partlib._prefix((line.get("refs") or [key])[0])
    mine, theirs = fp["symbol_pins"], [dict(p) for p in sym["pins"]]
    partlib._fix_pins(theirs, prefix)
    text = " ".join(str(line.get(k) or "") for k in ("description", "value", "mpn"))
    their_text = " ".join(str(cand.get(k) or "") for k in ("description", "mpn"))
    if prefix in pm.NONPOLAR and len(mine) == 2 and not pm.is_polar(prefix, text + " " + their_text, mine + theirs):
        a, b = pm.value(prefix, line.get("value")), pm.value(prefix, their_text)
        if a is None or b is None:
            return "unknown", f"the value of {'the line' if a is None else code} cannot be read, so it cannot be compared"
        if not pm.same_value(a, b):
            return "different", f"{code} is another value than the line's {line.get('value')}"
        mine_kind, their_kind = pm.kind(prefix, text), pm.kind(prefix, their_text, default=False)
        if their_kind is None:
            return "unknown", f"what kind of part {code} is cannot be read from its description"
        if mine_kind != their_kind:
            return "different", f"{code} is a {their_kind}, the line a {mine_kind}"
        return pm.ratings_check(prefix, text, their_text, code)
    if not mine or not theirs:
        return "unknown", "the pin functions of the line or of the candidate are not known"
    diff = pm.pin_diff(mine, theirs, typed=fp["source"] not in GENERATED)
    if diff:
        return "different", f"the pin functions differ: {'; '.join(diff[:3])}"
    return None, ""


def footprint_match(project, key, code, package="", fetcher=None, cand=None):
    """Would LCSC part `code` replace line `key` with no schematic, library or board change?
    {"match": "same" | "different" | "unknown", "why", "footprint"}. "same" needs evidence on both counts: the footprint
    (an identical land pattern for a line from EasyEDA or a vendor zip; the same standard package and pin count for a
    generated one) AND the function (the same pin names, or for a plain 2-pin passive the same value and kind). `cand` is
    what JLC says of the part (package, description); it is looked up when missing. A library that is not built for the
    current BOM proves nothing."""
    fp = footprint_of(project, key)
    res = lambda m, why: {"match": m, "why": why, "footprint": fp["name"] if fp else ""}
    code = (code or "").strip().upper()
    if not fp:
        return res("unknown", "the library has no footprint for this line yet")
    if bridge.library_stale(project):
        return res("unknown", NOT_CURRENT)
    if not partlib.LCSC_RE.match(code):
        return res("unknown", "the part has no LCSC C-number to fetch a footprint for")
    line = next((l for l in store.bom_lines(project) if l["key"] == key), {"key": key})
    cand = dict(cand or {})
    if package:
        cand["package"] = package
    if not (cand.get("package") and cand.get("description")):
        try:
            import jlc
            cand = {**(jlc.part_by_code(code) or {}), **{k: v for k, v in cand.items() if v}}
        except Exception:                               # a supplier being down only costs the answer
            pass
    generated = fp["source"] in GENERATED
    if generated:
        mine = package_key(fp["package"])
        if not mine:
            return res("unknown", f"package '{fp['package']}' of the line is not a standard one: no evidence")
        theirs = package_key(cand.get("package"))
        if not theirs:
            return res("unknown", f"package '{cand.get('package') or ''}' of {code} is not a standard one: no evidence")
        if theirs != mine:
            return res("different", f"package {theirs} is not {mine}")
    sym, cfp, why = _candidate(project, code, fetcher)
    if sym is None:
        return res("unknown", why)
    their, mine_pins = _pins(cfp["lines"]), set(fp["pins"])
    if their != mine_pins:
        return res("different", f"{code} has {len(their)} pins, the line {len(mine_pins)}")
    if not generated and land_fingerprint(cfp["lines"]) != fp["fingerprint"]:
        return res("different", f"the land pattern of {code} differs from {fp['name']}")
    verdict, why = _function(project, key, line, fp, sym, cand, code)
    if verdict:
        return res(verdict, why)
    return res("same", (f"package {package_key(fp['package'])}" if generated else f"same land pattern as {fp['name']}")
               + f", {len(mine_pins)} pins, same function")


def _manifest(project):
    try:
        return json.loads((library_dir(project) / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def supply_codes_changed(project):
    """True when a line of the built library would now be built from another LCSC code than the manifest records."""
    built, supply = _manifest(project), store.supply_for(project)
    return any(partlib.lcsc_code(l, supply.get(l["key"])) != built[l["key"]].get("lcsc", "")
               for l in store.bom_lines(project) if l["key"] in built)


def swap_keeps_library(project, key, lock):
    """True when approving an order-only swap (footprint `lock`) on line `key` leaves a current library current."""
    return (_manifest(project).get(key) or {}).get("footprint") == lock and not bridge.library_stale(project)


def stamp_swap(project, key, changes):
    """An order-only swap changed the BOM line, not what the board uses: the manifest takes the new code and its time
    moves past the BOM log, so the library is not stale. Altium's own symbol parameters are NOT changed: the manifest
    records the old MPN/code in `params_stale` until the next library build."""
    path = library_dir(project) / "manifest.json"
    man = json.loads(path.read_text(encoding="utf-8"))
    if key in man:
        e = man[key]
        e.setdefault("params_stale", {"mpn": e.get("mpn", ""), "lcsc": e.get("lcsc", "")})
        e["locked"] = changes.get("footprint_lock")
        if changes.get("lcsc"):
            e["lcsc"] = changes["lcsc"]
    path.write_text(json.dumps(man, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def params_stale(project):
    return {k: e["params_stale"] for k, e in _manifest(project).items() if e.get("params_stale")}


def params_notices(project):
    """One sentence per line whose Altium library parameters still show the part before an order-only swap."""
    lines = {l["key"]: l for l in store.bom_lines(project)}
    return [f"Altium's parameters for {', '.join(lines.get(k, {}).get('refs') or [k])} still show "
            f"{p.get('mpn') or '?'}{' / ' + p['lcsc'] if p.get('lcsc') else ''}: the JLC BOM comes from the advisor's export "
            "(export_bom), not from Altium; the next library build updates them" for k, p in params_stale(project).items()]


def clear_params_stale(project):
    path = library_dir(project) / "manifest.json"
    man = _manifest(project)
    if any(e.pop("params_stale", None) for e in man.values()):
        path.write_text(json.dumps(man, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def restamp_if_same(project):
    """After a stock check of a current library: only the supplier answers are newer, and no line would now be built
    from another LCSC code, so the manifest's time moves past the log. False (nothing touched) otherwise."""
    if bridge.library_stale(project):
        return False
    os.utime(library_dir(project) / "manifest.json")
    return True
