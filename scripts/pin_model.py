"""The pin check against the part's library model: a diode, an LED or a connector whose sheet pins agree with the library model
the part is drawn from is verified by it, so the student is not asked.

The model is the EasyEDA / LCSC part the library was built from: `library/easyeda/<LCSC>/lib.kicad_sym` (symbol: pin numbers and
names) and `lib.pretty/*.kicad_mod` (footprint: pad names), paired by the LCSC code (the "LCSC Part" property of both files). Four
things must agree before anything is decided, and each is read from a file, never assumed:

    the sheet's pins   (store.load_sheet: number, name, net)
    the raw symbol     (kicad_sym of the LCSC folder)
    the built symbol   (library/build/symbols_spec.txt: what Altium gets) and the built footprint (footprints_spec.txt)
    the raw footprint  (kicad_mod of the LCSC folder)

check() -> {"result": "agree" | "disagree" | "undecided", "reason": str, "evidence": {...}}.
    agree      every wired pin of every part of the line has its number in the symbol and a pad in the footprint, and carries the
               name the symbol gives it; for a diode / LED the two pins also carry opposite A / K roles, the same as the symbol's.
    disagree   one of them does not: a pin number the model has no pad for, a name that differs, anode and cathode the other way round.
    undecided  the model cannot say: not an EasyEDA model (generated or KiCad symbols are built from the sheet itself, so they would
               agree with it by construction), the files or the build are missing or do not belong together, the names are only
               numbers (a 1x4 header), an array of diodes with no A / K names. The part then stays for the student, as before.

What this is NOT: a reading of a datasheet. The server fills the sheet's pin numbers from the built symbol by name (AGENTS.md,
netlist.write), so "agree" says the sheet uses the model's numbering and A / K naming, and that the model is the one of the
part's LCSC code. It does not say which net the agent meant as the anode. The evidence says so ("library numbering").

Never marks anything by itself: store._pins_status reads check() and only ever lifts a part that would be "unverified" (a
standing accept, a flagged or datasheet mismatch and a table pass are never overridden).
"""
import hashlib
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pinnames  # noqa: E402
import store  # noqa: E402

BASIS = "library_model"
ROLES = {"A": "A", "ANODE": "A", "+": "A", "K": "K", "C": "K", "CATHODE": "K", "-": "K"}
ROLE_WORD = {"A": "anode", "K": "cathode"}
CHECKED_PREFIXES = ("D", "LED", "J", "P")
_NO_MPN = ("", "—", "-", "none")


# ---------------------------------------------------------------- reading the model files

def parse_symbol(text):
    """{"symbols": [top-level names], "lcsc": the 'LCSC Part' property or '', "pins": [{num, name}]} of a kicad_sym text."""
    tops = [n for n in re.findall(r'\(symbol\s+"([^"]+)"', text) if not re.search(r"_\d+_\d+$", n)]
    pins = []
    for chunk in text.split("(pin ")[1:]:
        name, num = re.search(r'\(name\s+"([^"]*)"', chunk), re.search(r'\(number\s+"([^"]*)"', chunk)
        if num:
            pins.append({"num": num.group(1).strip(), "name": (name.group(1) if name else "").strip()})
    m = re.search(r'\(property\s+"LCSC Part"\s+"([^"]*)"', text)
    return {"symbols": tops, "lcsc": m.group(1).strip() if m else "", "pins": pins}


def parse_footprint(text):
    """{"name", "lcsc", "pads": [pad names, in file order, no duplicates, no unnamed]} of a kicad_mod text."""
    head = re.match(r"\s*\((?:module|footprint)\s+\"?([^\s\")]+)", text)
    pads = []
    for m in re.finditer(r'\(pad\s+(?:"([^"]*)"|([^\s")]+))', text):
        name = (m.group(1) if m.group(1) is not None else m.group(2) or "").strip()
        if name and name not in pads:
            pads.append(name)
    m = re.search(r'\(property\s+"LCSC Part"\s+"([^"]*)"', text)
    name = head.group(1).split(":", 1)[-1] if head else ""
    return {"name": name, "lcsc": m.group(1).strip() if m else "", "pads": pads}


def _read(path):
    try:
        return pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _sha(text):
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _norm(name):
    return re.sub(r"[^a-z0-9+]", "", str(name or "").casefold())


def _same_name(sheet, lib):
    """A pin name as the sheet writes it and as the library has it: case and punctuation do not matter, and a library name that only
    adds a numbering suffix to the sheet's (GND_1, VBUS2) is the same pin."""
    a, b = _norm(sheet), _norm(lib)
    if not a or not b:
        return False
    return a == b or re.sub(r"\d+$", "", b) == a or re.sub(r"\d+$", "", a) == b


def _numeric(name):
    return bool(re.fullmatch(r"\d+", str(name or "").strip()))


def _role(name):
    return ROLES.get(str(name or "").strip().upper())


def _dec(result, reason, **evidence):
    return {"result": result, "reason": reason, "evidence": evidence}


# ---------------------------------------------------------------- the model of a line

_MODELS = {}      # (project, line key, mpn, lcsc) -> (stat signature of the files it was read from, result): the gate is asked on every poll


def _signature(project, line):
    import partlib
    lib = partlib.library_dir(project)
    entry = store.library_manifest(project).get(line.get("key")) or {}
    base = lib / "easyeda" / str(entry.get("lcsc") or "-")
    paths = [lib / "manifest.json", lib / "build" / "symbols_spec.txt", lib / "build" / "footprints_spec.txt", base / "lib.kicad_sym", base / "lib.pretty"]
    paths += sorted((base / "lib.pretty").glob("*.kicad_mod")) if (base / "lib.pretty").is_dir() else []
    sig = []
    for p in paths:
        try:
            st = p.stat()
            sig.append((str(p), st.st_size, st.st_mtime_ns))
        except OSError:
            sig.append((str(p), None, None))
    return tuple(sig)


def model_of(project, line):
    """(model dict, "") or (None, why not): the library model behind a BOM line, every file read and cross-checked.
    Kept until one of the files it was read from changes (size / mtime), so a poll that finds none changed reads nothing."""
    key = (project, line.get("key"), line.get("mpn"), line.get("lcsc"))
    sig = _signature(project, line)
    hit = _MODELS.get(key)
    if hit and hit[0] == sig:
        return hit[1]
    res = _model_of(project, line)
    _MODELS[key] = (sig, res)
    return res


def _model_of(project, line):
    import partlib
    key = line.get("key")
    entry = store.library_manifest(project).get(key) or {}
    if not entry:
        return None, "no library model built for this part yet"
    if entry.get("source") != "easyeda":
        return None, f"the library symbol is not a sourced model ({entry.get('source') or 'unknown'}): it is built from the sheet itself"
    if partlib.symbol_from_netlist(entry):
        return None, "the library symbol was generated from the sheet"
    for f in ("mpn", "lcsc"):
        if entry.get(f) and line.get(f) and str(entry[f]).strip().lower() != str(line[f]).strip().lower():
            return None, f"the library was built for another {f.upper()} than this line's"
    lcsc = str(entry.get("lcsc") or "").strip()
    if not re.fullmatch(r"C\d+", lcsc):
        return None, "the library part has no LCSC code"
    base = partlib.library_dir(project) / "easyeda" / lcsc
    sym_text = _read(base / "lib.kicad_sym")
    if sym_text is None:
        return None, f"the EasyEDA symbol file of {lcsc} is not in the project library"
    sym = parse_symbol(sym_text)
    if len(sym["symbols"]) != 1 or (sym["lcsc"] and sym["lcsc"] != lcsc):
        return None, f"the symbol file of {lcsc} does not hold exactly that one part"
    mods = sorted((base / "lib.pretty").glob("*.kicad_mod")) if (base / "lib.pretty").is_dir() else []
    mods = [(p, _read(p)) for p in mods]
    mods = [(p, t, parse_footprint(t)) for p, t in mods if t]
    want = str(entry.get("footprint") or "").strip()
    mods = [m for m in mods if m[2]["name"] == want and (not m[2]["lcsc"] or m[2]["lcsc"] == lcsc)]
    if len(mods) != 1:
        return None, f"the EasyEDA footprint of {lcsc} is not in the project library"
    fp_text, fp = mods[0][1], mods[0][2]
    built = store._built_symbols(project).get(entry.get("symbol") or "")
    if not built:
        return None, "the library is not built yet (no symbol in symbols_spec.txt)"
    raw = {p["num"]: p["name"] for p in sym["pins"]}
    spec = {str(p["num"]).strip(): str(p["name"]).strip() for p in built["pins"]}
    if len(raw) != len(sym["pins"]) or raw != spec:
        return None, "the built symbol and the EasyEDA symbol of this part do not have the same pins"
    built_pads = partlib.footprint_pads(project, key)
    if built_pads is None or {p for p in built_pads if p} != set(fp["pads"]):
        return None, "the built footprint and the EasyEDA footprint of this part do not have the same pads"
    return {"lcsc": lcsc, "symbol": entry.get("symbol") or "", "footprint": want, "pins": raw, "pads": fp["pads"],
            "sym_sha256": _sha(sym_text), "mod_sha256": _sha(fp_text)}, ""


def _sheet_pins(project, line):
    """[(ref, [{num, name, net}])] of the line's parts on the sheets, one entry per ref (the same ref on two sheets: merged)."""
    refs = list(line.get("refs") or [])
    out = {}
    for sh in store.sheet_ids(project):
        for part in store.load_sheet(project, sh).get("parts", []):
            if part.get("ref") in refs:
                rows = out.setdefault(part["ref"], [])
                for p in part.get("pins", []):
                    rows.append({"num": store._pin_num(p), "name": str(p.get("name") or "").strip(), "net": str(p.get("net") or "").strip()})
    return [(r, out[r]) for r in refs if r in out]


def _wired(pin):
    return bool(pin["net"]) and not pinnames.is_nc_net(pin["net"])


def _check_part(ref, pins, mdl, polar):
    """(result, reason, [[num, sheet name, model name]]) for one part against the model."""
    rows, bad = [], []
    for p in pins:
        if not _wired(p):
            continue
        if p["num"] not in mdl["pins"]:
            bad.append(f"{ref} pin {p['num']} is not a pin of the library symbol {mdl['symbol']}")
        elif p["num"] not in mdl["pads"]:
            bad.append(f"{ref} pin {p['num']} has no pad in the library footprint {mdl['footprint']}")
        else:
            rows.append((p, mdl["pins"][p["num"]]))
    if bad:
        return "disagree", "; ".join(bad), []
    if not rows:
        return "undecided", f"{ref} has no wired pin to compare", []
    shown = [[p["num"], p["name"], lib] for p, lib in rows]
    if polar:
        if len(mdl["pins"]) != 2 or len(rows) != 2:
            return "undecided", f"{ref} is not a plain two-pin diode in its library model", shown
        lib_roles = {n: _role(nm) for n, nm in mdl["pins"].items()}
        if set(lib_roles.values()) != {"A", "K"}:
            return "undecided", f"the library symbol names its pins {', '.join(mdl['pins'].values())}, not anode and cathode", shown
        sheet_roles = {p["num"]: _role(p["name"]) for p, _ in rows}
        if set(sheet_roles.values()) != {"A", "K"}:
            return "undecided", f"{ref} is drawn with pins named {', '.join(p['name'] or p['num'] for p, _ in rows)}, not anode and cathode", shown
        wrong = [n for n in sheet_roles if sheet_roles[n] != lib_roles[n]]
        if wrong:
            n = wrong[0]
            return "disagree", (f"{ref} pin {n} is the {ROLE_WORD[sheet_roles[n]]} on the sheet, but the library symbol {mdl['symbol']} "
                                f"(LCSC {mdl['lcsc']}) has it as the {ROLE_WORD[lib_roles[n]]}"), shown
        return "agree", "", shown
    named = [(p, lib) for p, lib in rows if p["name"]]
    differ = [(p, lib) for p, lib in named if not _same_name(p["name"], lib) and not (_numeric(p["name"]) and _numeric(lib))]
    if differ:
        p, lib = differ[0]
        return "disagree", f"{ref} pin {p['num']} is named {p['name']} on the sheet, but {lib} in the library symbol {mdl['symbol']} (LCSC {mdl['lcsc']})", shown
    if not any(lib and not _numeric(lib) for _, lib in rows):
        return "undecided", f"the library symbol names {ref}'s pins only by number: nothing in it to compare the names with", shown
    if any(not p["name"] for p, _ in rows):
        return "undecided", f"{ref} has a wired pin with no name on the sheet", shown
    return "agree", "", shown


def check(project, line):
    """The verdict for a BOM line of diodes / LEDs or connectors (see the module doc); memoised for the build in progress."""
    line = store._line_of(project, line) if not isinstance(line, dict) else line
    return store.memoised(("pin_model", project, line.get("key"), tuple(line.get("refs") or ()), line.get("mpn"), line.get("lcsc")),
                          lambda: _check(project, line))


def _check(project, line):
    refs = line.get("refs") or []
    pre = {store._prefix_of(r) for r in refs}
    if not refs or not pre <= set(CHECKED_PREFIXES):
        return _dec("undecided", "not a diode, LED or connector")
    polar = pre <= set(store.POLARISED_PREFIXES)
    if not polar and not pre <= set(store.CONNECTOR_PREFIXES):
        return _dec("undecided", "diodes / LEDs and connectors are checked on their own, not mixed on one line")
    mdl, why = model_of(project, line)
    if not mdl:
        return _dec("undecided", why)
    parts = _sheet_pins(project, line)
    if len(parts) != len(refs):
        return _dec("undecided", "a part of this line is not on a sheet")
    seen, pins, verdict = [], {}, "agree"
    for ref, p in parts:
        res, why, shown = _check_part(ref, p, mdl, polar)
        pins[ref] = shown
        if res == "disagree":
            return _dec("disagree", why, lcsc=mdl["lcsc"], symbol=mdl["symbol"], pins=pins)
        if res == "undecided":
            verdict = "undecided"
            seen.append(why)
    ev = {"basis": BASIS, "lcsc": mdl["lcsc"], "symbol": mdl["symbol"], "footprint": mdl["footprint"], "pins": pins,
          "sym_sha256": mdl["sym_sha256"], "mod_sha256": mdl["mod_sha256"],
          "note": "the sheet's pin numbers and names match the library model of this LCSC part; it is not a datasheet reading"}
    if verdict == "undecided":
        return _dec("undecided", seen[0], **ev)
    return _dec("agree", f"pins match the library model of LCSC {mdl['lcsc']}", **ev)


# ---------------------------------------------------------------- what the rest of the system reads

def digest(chk):
    """A short fingerprint of a verdict's evidence: the audit record is rewritten only when this changes."""
    return hashlib.sha256(json.dumps(chk["evidence"], sort_keys=True, default=str).encode()).hexdigest()[:16]


def stamp(project, lines, lib):
    """The audit trail: library-log.jsonl gets `pin_model_check` (by "system") for every line the model verifies, once and again only
    when its evidence changes. Audit only: the live check above is what verifies, so a record that is stale or missing changes nothing."""
    for l in lines:
        if not l.get("refs") or l.get("dnp") or l.get("nobuy"):
            continue
        chk = check(project, l)
        e = lib.get(l["key"]) or {}
        old = e.get("pin_model_check") or {}
        if chk["result"] == "agree" and old.get("digest") != digest(chk):
            rec = {"result": "agree", "basis": BASIS, "digest": digest(chk), "evidence": chk["evidence"], "ts": store.now()}
            store.add_library(project, l["key"], {"pin_model_check": rec}, by="system")
            e["pin_model_check"] = rec
        elif chk["result"] != "agree" and old.get("result") == "agree":
            rec = {"result": chk["result"], "basis": BASIS, "digest": "", "reason": chk["reason"], "ts": store.now()}
            store.add_library(project, l["key"], {"pin_model_check": rec}, by="system")
            e["pin_model_check"] = rec


def verified_lines(project):
    """[{line, refs, mpn, lcsc, evidence}] of every line the library model verifies: what the order manifest lists."""
    out = []
    for l in store.bom(project, write=False):
        if l.get("pins_basis") == BASIS:
            chk = check(project, l)
            out.append({"line": l["key"], "refs": l["refs"], "mpn": l.get("mpn") or "", "basis": BASIS, "reason": chk["reason"],
                        "evidence": chk["evidence"]})
    return out
