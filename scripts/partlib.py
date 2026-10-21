"""Project part library, stage L1 (no Altium): fetch, convert, generate, share, check, manifest.

For every BOM line the tool gets a symbol, a footprint and (when EasyEDA has one) a STEP model:
  1. EasyEDA by the line's LCSC C-number, through easyeda2kicad run as a subprocess (no login). A failure is
     reported and the line falls through to 2; there is no retry around a block. Downloads are untrusted data.
  2. A vendor zip (SnapEDA, Ultra Librarian, Component Search Engine, Mouser/DigiKey) the student downloaded once:
     found by the MPN in its file name in the project's Sources or in Downloads, unpacked safely into library/vendor/,
     its KiCad symbol, footprint and STEP converted like EasyEDA's. These sites need a log-in, so the tool asks.
  3. Generated: an IPC-7351 nominal footprint for the standard packages and a standard-shape or box symbol
     (pins from the project's netlist sheets).
  4. Otherwise status "missing" with the reason. Nothing is invented.
Output, all under projects/<name>/library/: easyeda/<Cxxxx>/ (downloads), vendor/<MPN>/ (unpacked zips), build/ (the spec files stage L2 feeds
to Altium: symbols_spec.txt, footprints_spec.txt, links.txt, props.txt, parts.json) and manifest.json.
The LIBRARY|/FPLIB| lines carry the placeholders <SCHLIB>/<PCBLIB>; stage L2 fills in the real paths.

  python scripts/partlib.py prepare <project> [--no-fetch] [--refresh]
  python scripts/partlib.py status <project>
"""
import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sources  # noqa: E402
import store  # noqa: E402
from partlib_convert import clean, convert_footprint, convert_symbols, safe_name  # noqa: E402
from partlib_kicad import fetch_kicad, kicad_footprint  # noqa: E402
from partlib_generate import PASSIVE_PREFIX, POWER_NAME, footprint_for, package_key, symbol_for  # noqa: E402

LCSC_RE = re.compile(r"^C\d{2,9}$")
RATING_PREFIX = ("R", "C", "L")                 # these show their value as the comment, the rest their MPN
FETCH_TIMEOUT = 180
ZIP_MAX_BYTES = 50 * 1024 * 1024                # a vendor zip is untrusted: cap what it may unpack to
ZIP_MAX_MEMBERS = 1000
DOWNLOADS_DAYS = 30                             # a zip in Downloads counts for this long


# every module whose code shapes the built spec files; the ordering code (partlib_order, partlib_match) is not one
CONVERTER_MODULES = ("partlib.py", "partlib_convert.py", "partlib_generate.py", "partlib_kicad.py")


def converter_fingerprint():
    """Short hash of the converter code: a library built by older code is stale."""
    h = hashlib.sha256()
    for n in CONVERTER_MODULES:
        h.update((pathlib.Path(__file__).parent / n).read_bytes())
    return h.hexdigest()[:12]


def library_dir(project):
    return store.pdir(project) / "library"


# ---------------------------------------------------------------- fetch

def fetch_one(cid, dest, timeout=FETCH_TIMEOUT):
    """Download symbol, footprint and STEP for one LCSC part into dest/lib.*. Returns (ok, message)."""
    if not LCSC_RE.match(cid):
        return False, "not an LCSC C-number"
    dest.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-I", "-m", "easyeda2kicad", "--full", f"--lcsc_id={cid}",
           "--output", str(dest / "lib"), "--overwrite"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"could not run easyeda2kicad: {e}"
    out = (r.stdout + r.stderr).strip()
    if r.returncode != 0 or re.search(r"error|failed|not found", out, re.I) or not (dest / "lib.kicad_sym").exists():
        return False, (out[-300:] or f"exit code {r.returncode}")
    return True, "downloaded"


# ---------------------------------------------------------------- helpers

def _prefix(ref):
    m = re.match(r"[A-Za-z]+", ref or "")
    return m.group(0).upper() if m else "U"


def _sheet_pins(project):
    """ref -> [{"num","name","side"?}] from all netlist sheets."""
    out = {}
    for sid in store.sheet_ids(project):
        for part in store.load_sheet(project, sid).get("parts", []):
            pins = []
            for p in part.get("pins", []):
                num = str(p.get("num", p.get("number", "")))
                pins.append({"num": num, "name": str(p.get("name", num)), **({"side": p["side"]} if p.get("side") else {})})
            out.setdefault(part.get("ref"), pins)
    return out


def _fix_pins(pins, prefix):
    """The kiln fixes: passives' pins Passive, power pins Power."""
    for p in pins:
        if prefix in PASSIVE_PREFIX:
            p["type"] = "Passive"
        elif POWER_NAME.match(p["name"] or "") or p["type"] == "Power":
            p["type"] = "Power"


def _description(line):
    bits = []
    for b in (line.get("value"), line.get("description")):
        if b and str(b).strip().lower() not in [x.lower() for x in bits]:
            bits.append(str(b).strip())
    if line.get("lcsc"):
        bits.append(f"LCSC {line['lcsc']}")
    return clean(" ".join(bits) or line.get("mpn") or line["key"])


def _easyeda_part(dest):
    """Read the first symbol, its footprint and STEP from a downloaded lib. Returns (symbol, footprint, step_path)."""
    return _kicad_part(dest / "lib.kicad_sym", sorted((dest / "lib.pretty").glob("*.kicad_mod")),
                       list((dest / "lib.3dshapes").glob("*")))


def _kicad_part(sym_file, mods, steps, any_step=False):
    """Convert a KiCad symbol file, its footprint (the one the symbol names, else the first) and the STEP the footprint
    points at (any_step: else the first STEP there is). Returns (symbol, footprint, step_path)."""
    sym = convert_symbols(sym_file.read_text(encoding="utf-8"))[0]
    pick = next((m for m in mods if m.stem == sym["footprint"]), mods[0] if mods else None)
    if pick is None:
        raise ValueError("no footprint in the download")
    fp = convert_footprint(pick.read_text(encoding="utf-8"))
    fp["name"] = _plain_name(fp["name"])
    steps = [c for c in steps if c.suffix.lower() in (".step", ".stp")]
    step = None
    if fp["model"]:
        stem = pathlib.PurePosixPath(fp["model"]["file"].replace("\\", "/")).stem
        for cand in steps:
            if cand.stem == stem:
                step = cand
    if step is None and any_step and steps:
        step = steps[0]
    return sym, fp, step


def _plain_name(name):
    """A footprint name without KiCad's library nickname (easyeda2kicad:R0603 / easyeda2kicad_R0603 -> R0603)."""
    return safe_name(re.sub(r"^[A-Za-z0-9.+-]*easyeda2kicad[:_]", "", str(name), flags=re.I).split(":")[-1])


def lcsc_code(line, supply):
    """The line's LCSC C-number: its own `lcsc`, else `code`, else what the stock check found for the exact MPN."""
    found = (supply or {}).get("LCSC") or {}
    for cand in (line.get("lcsc"), line.get("code"), found.get("code") if found.get("exact") else None):
        cand = str(cand or "").strip().upper()
        if LCSC_RE.match(cand):
            return cand
    return ""


class Build:
    """The footprints and symbols collected for one library, names kept unique."""

    def __init__(self):
        self.footprints = {}        # name -> {"fp", "source", "steps"}
        self.symbols = {}           # name -> dict
        self.generated = {}         # package key -> footprint name (the sharing)

    def add_footprint(self, fp, source, step, tag):
        name = fp["name"]
        have = self.footprints.get(name)
        if have and have["fp"]["lines"] == fp["lines"]:
            return name                                     # same land pattern: shared
        if have:
            name = safe_name(f"{name}_{tag}")
            fp = {**fp, "name": name}
            if name in self.footprints:
                return name
        self.footprints[name] = {"fp": fp, "source": source, "steps": [step] if step else []}
        return name

    def symbol_name(self, wanted):
        name, n = safe_name(wanted) or "PART", 2
        while name in self.symbols:
            name = f"{safe_name(wanted)}_{n}"
            n += 1
        return name


# ---------------------------------------------------------------- vendor zips

def _mpn_keys(mpn):
    """What a zip name is looked for by: the normalized MPN, then the MPN without its packaging suffix (min 5 chars)."""
    norm = lambda t: re.sub(r"[^a-z0-9]", "", t.lower())
    keys = [norm(mpn)] if len(norm(mpn)) >= 4 else []
    base = re.split(r"[-/]", mpn.strip())[:-1]
    if base and len(norm("".join(base))) >= 5:
        keys.append(norm("".join(base)))
    return keys


def vendor_search_links(mpn):
    q = urllib.parse.quote(mpn.strip(), safe="")
    return {"Component Search Engine": f"https://componentsearchengine.com/search?term={q}",
            "SnapEDA": f"https://www.snapeda.com/search/?q={q}",
            "Ultra Librarian": f"https://www.ultralibrarian.com/search?q={q}"}


def vendor_hint(mpn):
    """What the student does for a part no EasyEDA download or generator covers."""
    if not (mpn or "").strip():
        return "the BOM line has no MPN, so no vendor model can be looked for; add the MPN"
    links = "; ".join(f"{n} {u}" for n, u in vendor_search_links(mpn).items())
    return (f"download the part's KiCad model once ({links}): choose the KiCad format, log in if the site asks, "
            "the zip lands in Downloads; then build the library again")


def _recent_downloads():
    """Zips in the user's Downloads folder changed within DOWNLOADS_DAYS, newest first."""
    cutoff, out = time.time() - DOWNLOADS_DAYS * 86400, []
    try:
        out = [f for f in (pathlib.Path.home() / "Downloads").glob("*.zip") if f.is_file() and f.stat().st_mtime >= cutoff]
    except OSError:
        pass
    return sorted(out, key=lambda f: f.stat().st_mtime, reverse=True)


def _project_zips(project):
    folder = sources.folder_of(project)
    zips = [f for f in folder.glob("*.zip") if f.is_file()] if folder.is_dir() else []
    return sorted(zips, key=lambda f: f.stat().st_mtime, reverse=True)


def _zip_for(mpn, zips):
    """The first zip whose normalized name carries the MPN (the full MPN before the trimmed one)."""
    for key in _mpn_keys(mpn):
        # separators may differ, but the MPN is a whole word: LM35 is not in LM358_KiCad.zip
        word = re.compile(r"(?<![a-z0-9])" + "[^a-z0-9]*".join(key) + r"(?![a-z0-9])")
        for f in zips:
            if word.search(f.stem.lower()):
                return f
    return None


def find_vendor_zip(project, mpn):
    """The vendor zip for an MPN: the project's Sources first, else a recent one in Downloads, which is copied into
    Sources (hashed like any source) so the project keeps it. None when there is none."""
    sources.adopt(project)
    hit = _zip_for(mpn, _project_zips(project))
    if hit:
        return hit
    hit = _zip_for(mpn, _recent_downloads())
    if not hit:
        return None
    folder = sources.folder_of(project)
    folder.mkdir(parents=True, exist_ok=True)
    dst, n = folder / hit.name, 1
    while dst.exists() and dst.read_bytes() != hit.read_bytes():
        dst = folder / f"{hit.stem}-{n}{hit.suffix}"
        n += 1
    if not dst.exists():
        shutil.copy2(hit, dst)
    sources.adopt(project)
    return dst


def vendor_zip_newer(project, since):
    """True when a zip in Sources or library/vendor, or a Downloads zip carrying a BOM line's MPN, is newer than `since`."""
    vendor = library_dir(project) / "vendor"
    zips = _project_zips(project) + (list(vendor.rglob("*.zip")) if vendor.is_dir() else [])
    if any(f.stat().st_mtime > since for f in zips):
        return True
    fresh = [f for f in _recent_downloads() if f.stat().st_mtime > since]
    return bool(fresh) and any(_zip_for(l.get("mpn") or "", fresh) for l in store.bom_lines(project))


def safe_extract(zip_path, dest):
    """Unpack an untrusted zip into a fresh dest: no absolute paths, no .., no links, capped size and member count.
    Nothing in it is executed. Raises ValueError saying why it was refused."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    root = dest.resolve()
    try:
        with zipfile.ZipFile(zip_path) as z:
            infos = z.infolist()
            if len(infos) > ZIP_MAX_MEMBERS:
                raise ValueError(f"it has {len(infos)} files (more than {ZIP_MAX_MEMBERS})")
            if sum(i.file_size for i in infos) > ZIP_MAX_BYTES:
                raise ValueError(f"it unpacks to more than {ZIP_MAX_BYTES // 2**20} MB")
            total = 0
            for i in infos:
                name = i.filename.replace("\\", "/")
                if name.startswith("/") or re.match(r"[A-Za-z]:", name) or ".." in name.split("/"):
                    raise ValueError(f"member '{i.filename}' points outside the folder")
                if i.is_dir() or (i.external_attr >> 16) & 0o170000 == 0o120000:     # folders; symlinks are skipped
                    continue
                target = (root / name).resolve()
                if root not in target.parents:
                    raise ValueError(f"member '{i.filename}' points outside the folder")
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(i) as src, open(target, "wb") as out:
                    while chunk := src.read(65536):                 # the header's size can lie: count what is written
                        total += len(chunk)
                        if total > ZIP_MAX_BYTES:
                            raise ValueError(f"it unpacks to more than {ZIP_MAX_BYTES // 2**20} MB")
                        out.write(chunk)
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        raise ValueError(f"it is not a readable zip ({exc})") from exc


def _vendor_part(build, e, mpn, zip_path, lib):
    """Symbol, footprint and STEP from a vendor zip's KiCad files: (pins, gfx, footprint name), or None with the reason
    in e["issues"] (the line then falls through to the generator)."""
    dest = lib / "vendor" / (safe_name(mpn) or "part")
    e["vendor_zip"] = zip_path.name
    try:
        safe_extract(zip_path, dest)
    except ValueError as exc:
        e["issues"].append(f"vendor zip {zip_path.name} was not used: {exc}")
        return None
    files = [f for f in sorted(dest.rglob("*")) if f.is_file()]
    kinds = lambda *suf: [f for f in files if f.suffix.lower() in suf]
    syms, mods, steps = kinds(".kicad_sym"), kinds(".kicad_mod"), kinds(".step", ".stp")
    if not syms or not mods:
        found = sorted({f.suffix.lower() for f in files if f.suffix}) or ["nothing"]
        e["issues"].append(f"vendor zip {zip_path.name} has no KiCad symbol and footprint (it holds {', '.join(found)}); "
                           "choose the KiCad format on the vendor's download page and build again")
        return None
    try:
        sym, fp, step = _kicad_part(syms[0], mods, steps, any_step=True)
    except (ValueError, KeyError, IndexError, TypeError, OSError, UnicodeError):
        e["issues"].append(f"vendor zip {zip_path.name}: its KiCad files could not be read; "
                           "download the KiCad format again and build again")
        return None
    fpname = build.add_footprint(fp, "vendor", step, safe_name(mpn))
    if step and not build.footprints[fpname]["steps"]:
        build.footprints[fpname]["steps"].append(step)
    if fp["model"] is not None:
        build.footprints[fpname].setdefault("model", fp["model"])
    e["source"] = "vendor"
    e["issues"] += fp.get("notes", [])
    return sym["pins"], sym["gfx"], fpname


# ---------------------------------------------------------------- prepare

def prepare(project, fetch=True, refresh=False, fetcher=None, kicad_fetcher=None):
    """Build the library data for every BOM line; returns the manifest dict (also written to disk)."""
    fetcher = fetcher or fetch_one
    kicad_fetcher = kicad_fetcher or fetch_kicad
    lib = library_dir(project)
    sheets = _sheet_pins(project)
    supply = store.supply_for(project)
    build, manifest, by_mpn = Build(), {}, {}
    last = _previous(lib)
    for line in store.bom_lines(project):
        key = line["key"]
        refs = line.get("refs") or [key]
        prefix = _prefix(refs[0])
        mpn = (line.get("mpn") or line.get("value") or key).strip()
        lcsc = lcsc_code(line, supply.get(key))
        line = {**line, "lcsc": lcsc}
        e = {"symbol": "", "footprint": "", "step": "", "source": "missing", "status": "missing", "issues": [],
             "package": line.get("package", ""), "lcsc": lcsc, "value": line.get("value", ""), "mpn": line.get("mpn", "")}
        if (last["manifest"].get(key) or {}).get("params_stale"):       # Altium's parameters stay old until a library build
            e["params_stale"] = last["manifest"][key]["params_stale"]
        manifest[key] = e
        prev = by_mpn.get(mpn.lower())
        if prev and manifest[prev]["symbol"]:               # the same MPN on another line: one library part
            src = manifest[prev]
            e.update({k: src[k] for k in ("symbol", "footprint", "step", "source", "status", "vendor_zip") if k in src})
            e["issues"] = list(src["issues"])
            build.symbols[src["symbol"]].setdefault("lines", [prev]).append(key)
            continue
        by_mpn[mpn.lower()] = key
        got = None                                          # (pins, gfx, desc_for_symbol, footprint name)
        keep = ""                                           # an order-only swap keeps the symbol's name too
        if line.get("footprint_lock"):                      # the footprint was proven the same: nothing is fetched or added
            got, why = _locked_part(build, last, key, line, lib)
            if got:
                keep = last["manifest"][key]["symbol"]
                e.update(source=last["manifest"][key].get("source", "easyeda"), locked=line["footprint_lock"])
            else:
                e["issues"].append(f"footprint lock {line['footprint_lock']} not kept: {why}; built as a design change")
        if got is None and lcsc:
            dest = lib / "easyeda" / lcsc
            if fetch and (refresh or not (dest / "lib.kicad_sym").exists()):
                ok, msg = fetcher(lcsc, dest)
                if not ok:
                    e["issues"].append(f"EasyEDA {lcsc}: {msg}")
            if (dest / "lib.kicad_sym").exists():
                try:
                    sym, fp, step = _easyeda_part(dest)
                    fpname = build.add_footprint(fp, "easyeda", step, lcsc)
                    if step and not build.footprints[fpname]["steps"]:
                        build.footprints[fpname]["steps"].append(step)
                    got = (sym["pins"], sym["gfx"], fpname)
                    e["source"] = "easyeda"
                    if fp["model"] is not None:
                        build.footprints[fpname].setdefault("model", fp["model"])
                    e["issues"] += fp.get("notes", [])
                except (ValueError, KeyError, IndexError, TypeError, OSError, UnicodeError):
                    e["issues"].append(f"EasyEDA {lcsc}: the model download for this part could not be read; "
                                       "the next step is a vendor zip (a log-in site) in Sources")
            elif not e["issues"]:
                e["issues"].append(f"EasyEDA {lcsc}: not downloaded")
        if got is None and line.get("mpn"):
            zip_path = find_vendor_zip(project, mpn)
            if zip_path:
                got = _vendor_part(build, e, mpn, zip_path, lib)
        if got is None:
            got = _generate(build, e, line, prefix, sheets.get(refs[0], []), (lib, kicad_fetcher, fetch, refresh))
        if got is None:
            continue
        pins, gfx, fpname = got
        _fix_pins(pins, prefix)
        name = build.symbol_name(keep or mpn)
        build.symbols[name] = {
            "name": name, "desc": _description(line), "pins": pins, "gfx": gfx, "footprint": fpname,
            "prefix": prefix, "line": key,
            "comment": clean(line.get("value") or mpn, 60) if prefix in RATING_PREFIX else clean(mpn, 60),
            "params": {"MPN": clean(line.get("mpn") or mpn, 80), "Manufacturer": clean(line.get("manufacturer"), 80),
                       "LCSC": lcsc, "Description": _description(line)},
            "hide_pin_names": len(pins) == 2}
        e["symbol"], e["footprint"] = name, fpname
        if build.footprints[fpname]["steps"]:
            e["step"] = build.footprints[fpname]["steps"][0].relative_to(lib).as_posix()
        e["status"] = "warn" if e["issues"] else "ok"        # a missing 3D model on a generated part is no warning
    _write(project, build)
    for p in check_build(lib / "build"):
        for e in manifest.values():
            if p["symbol"] and e["symbol"] == p["symbol"] or p["footprint"] and e["footprint"] == p["footprint"]:
                e["issues"].append(p["message"])
                if p["level"] == "problem":
                    e["status"] = "error"
                elif e["status"] == "ok" and not (p["kind"] == "3d" and e["source"] != "easyeda"):
                    e["status"] = "warn"
    (lib / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (lib / "converter.txt").write_text(converter_fingerprint() + "\n", encoding="utf-8")   # not in manifest.json: its values are all lines
    return manifest


def _kicad_footprint(build, key, prefix, ctx):
    """KiCad's official footprint (+ STEP) for a package key, from the cache or the net: (name, issues)."""
    lib, kfetch, fetch, refresh = ctx
    kf = kicad_footprint(key, prefix)
    if not kf:
        return None, []
    d = lib / "kicad" / kf[0]
    mod = d / f"{kf[1]}.kicad_mod"
    msg = ""
    if fetch and (refresh or not mod.exists()):
        _, msg = kfetch(kf[0], kf[1], d)
    fallback = " used the built-in nominal footprint (offline fallback)"
    if not mod.exists():
        return None, [f"KiCad library {kf[0]}/{kf[1]} not available ({msg or 'not downloaded'});" + fallback]
    try:
        fp = convert_footprint(mod.read_text(encoding="utf-8"))
    except (ValueError, KeyError, IndexError, TypeError, OSError, UnicodeError):
        return None, [f"KiCad footprint {kf[1]} could not be read;" + fallback]
    fp["name"], fp["desc"] = safe_name(kf[1]), f"KiCad {kf[0]} (CC-BY-SA 4.0, KiCad library exception)"
    step = d / f"{kf[1]}.step"
    name = build.add_footprint(fp, "kicad", step if step.exists() else None, key)
    if fp["model"] is not None:
        build.footprints[name].setdefault("model", fp["model"])
    return name, fp.get("notes", [])


def _generate(build, e, line, prefix, pins, ctx):
    """KiCad's official footprint, else the built-in one, with a symbol; None when it is missing (e says why)."""
    pkg = line.get("package", "")
    key = package_key(pkg)
    if not key:
        e["issues"].append((f"package '{pkg}' is not one the tool generates" if pkg else "the BOM line has no package")
                           + "; " + vendor_hint(line.get("mpn")))
        return None
    if (key, prefix) not in build.generated:               # one footprint per package (and KiCad chip family)
        name, notes = _kicad_footprint(build, key, prefix, ctx)
        if name:
            build.generated[key, prefix] = (name, "kicad", notes)
        else:
            build.generated[key, prefix] = (build.add_footprint(footprint_for(key), "generated", None, key),
                                            "generated", notes)
    fpname, source, notes = build.generated[key, prefix]
    npads = len({ln.split("|")[1] for ln in build.footprints[fpname]["fp"]["lines"] if ln.startswith("PAD|")})
    sym = symbol_for(prefix, f"{line.get('mpn', '')} {line.get('description', '')}", pins, npads)
    if sym is None:
        e["issues"].append(f"no netlist pins found for {line.get('refs', [line['key']])[0]} and the shape is not "
                           "a standard one; the pin list is needed, or " + vendor_hint(line.get("mpn")))
        return None
    e["source"] = source
    e["issues"] += notes + sym[2]
    return sym[0], sym[1], fpname


# ---------------------------------------------------------------- previous build, locked parts

def _spec_footprints(path):
    """footprints_spec.txt -> {name: {"desc", "lines"}}"""
    out, cur = {}, None
    try:
        text = pathlib.Path(path).read_text(encoding="cp1252", errors="replace").splitlines()
    except OSError:
        return out
    for ln in text:
        if ln.startswith("FOOTPRINT|"):
            f = ln.split("|", 2)
            cur = out[f[1]] = {"desc": f[2] if len(f) > 2 else "", "lines": []}
        elif cur is not None and ln and not ln.startswith("FPLIB|"):
            cur["lines"].append(ln)
    return out


def _spec_symbols(path):
    """symbols_spec.txt -> {name: {"pins", "gfx"}}, as prepare builds them"""
    out, cur = {}, None
    try:
        text = pathlib.Path(path).read_text(encoding="cp1252", errors="replace").splitlines()
    except OSError:
        return out
    for ln in text:
        f = ln.split("|")
        if f[0] == "SYMBOL":
            cur = out[f[1]] = {"pins": [], "gfx": []}
        elif cur is not None and f[0] == "GRAPHIC":
            cur["gfx"].append(f[1:])
        elif cur is not None and f[0] == "PIN" and len(f) >= 9:
            cur["pins"].append({"num": f[1], "name": f[2], "type": f[3].replace("eElectric", ""), "orient": f[4],
                                "x": f[5], "y": f[6], "len": f[8]})
    return out


def _previous(lib):
    """What the last build made: manifest, parts.json, footprints and symbols by name, the converter it was made by."""
    def load(p):
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    b = lib / "build"
    try:
        conv = (lib / "converter.txt").read_text(encoding="utf-8").strip()
    except OSError:
        conv = ""
    return {"manifest": load(lib / "manifest.json"), "parts": load(b / "parts.json"), "converter": conv,
            "footprints": _spec_footprints(b / "footprints_spec.txt"), "symbols": _spec_symbols(b / "symbols_spec.txt")}


def _locked_part(build, last, key, line, lib):
    """((pins, gfx, footprint name), "") of the line as the last build made it, when that used footprint `line.footprint_lock`
    for the same package (and value of a passive) by the same converter; else (None, why): the line is then built as a
    design change."""
    lock = line["footprint_lock"]
    old = last["manifest"].get(key) or {}
    sym, fpb = last["symbols"].get(old.get("symbol")), last["footprints"].get(lock)
    if last["converter"] != converter_fingerprint():
        return None, "the converter changed since the last build"
    if old.get("footprint") != lock or not sym or not fpb:
        return None, "the last build did not use that footprint for this line"
    if (old.get("package") or "") != (line.get("package") or ""):
        return None, "the package of the line changed since the last build"
    refs = line.get("refs") or [key]
    if _prefix(refs[0]) in PASSIVE_PREFIX and (old.get("value") is None or str(old["value"]).strip().lower() != str(line.get("value") or "").strip().lower()):
        return None, "the value of the line changed since the last build"
    have = build.footprints.get(lock)
    if have and have["fp"]["lines"] != fpb["lines"]:
        return None, "the footprint name is taken by another land pattern"
    if not have:
        info = last["parts"].get("footprints", {}).get(lock, {})
        build.footprints[lock] = {"fp": {"name": lock, "lines": fpb["lines"], "tht": info.get("tht", False),
                                         "desc": fpb["desc"], "model": info.get("model")},
                                  "source": info.get("source", old.get("source", "easyeda")),
                                  "steps": [lib / s for s in info.get("steps", [])]}
        if info.get("model"):
            build.footprints[lock]["model"] = info["model"]
    return ([dict(p) for p in sym["pins"]], [list(g) for g in sym["gfx"]], lock), ""


# ---------------------------------------------------------------- spec files

def _write(project, build):
    out = library_dir(project) / "build"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    sy = ["LIBRARY|<SCHLIB>"]
    for s in build.symbols.values():
        sy.append(f"SYMBOL|{s['name']}|{clean(s['desc'])}|1")
        sy += ["GRAPHIC|" + "|".join(str(v) for v in g) for g in s["gfx"]]
        sy += [f"PIN|{clean(p['num'], 20)}|{clean(p['name'], 60)}|eElectric{p['type']}|{p['orient']}|{p['x']}|{p['y']}|1|{p['len']}"
               for p in s["pins"]]
    fp = ["FPLIB|<PCBLIB>"]
    for name, f in build.footprints.items():
        if any(s["footprint"] == name for s in build.symbols.values()):
            fp.append(f"FOOTPRINT|{name}|{clean(f['fp'].get('desc') or 'EasyEDA/LCSC')}")
            fp += f["fp"]["lines"]
    (out / "symbols_spec.txt").write_text("\n".join(sy) + "\n", encoding="cp1252", errors="replace")
    (out / "footprints_spec.txt").write_text("\n".join(fp) + "\n", encoding="cp1252", errors="replace")
    (out / "links.txt").write_text("".join(f"{s['name']}={s['footprint']}\n" for s in build.symbols.values()),
                                   encoding="utf-8")
    (out / "props.txt").write_text("".join(f"{s['name']}={s['prefix']}|{s['comment']}\n" for s in build.symbols.values()),
                                   encoding="utf-8")
    lib = library_dir(project)
    parts = {"symbols": {n: {k: s[k] for k in ("prefix", "comment", "params", "hide_pin_names", "line", "lines") if k in s}
                         for n, s in build.symbols.items()},
             "footprints": {n: {"source": f["source"], "tht": f["fp"]["tht"], "model": f.get("model"),
                                "steps": [p.relative_to(lib).as_posix() for p in f["steps"]]}
                            for n, f in build.footprints.items()
                            if any(s["footprint"] == n for s in build.symbols.values())}}
    (out / "parts.json").write_text(json.dumps(parts, indent=2) + "\n", encoding="utf-8")


def check_build(build_dir):
    """Spec-level audit (check_lib.py without the Altium files): a list of {level, symbol, footprint, message}."""
    build_dir = pathlib.Path(build_dir)
    res = []

    def add(level, message, symbol="", footprint="", kind=""):
        res.append({"level": level, "kind": kind, "symbol": symbol, "footprint": footprint, "message": message})
    read = lambda n: (build_dir / n).read_text(encoding="cp1252", errors="replace").splitlines() \
        if (build_dir / n).exists() else []
    fps = [ln.split("|")[1] for ln in read("footprints_spec.txt") if ln.startswith("FOOTPRINT|")]
    syms = [ln.split("|")[1] for ln in read("symbols_spec.txt") if ln.startswith("SYMBOL|")]
    links = dict(ln.split("=", 1) for ln in read("links.txt") if "=" in ln)
    parts = {}
    if (build_dir / "parts.json").exists():
        parts = json.loads((build_dir / "parts.json").read_text(encoding="utf-8"))
    for name in sorted({n for n in fps if fps.count(n) > 1}):
        add("problem", f"footprint name {name} defined more than once", footprint=name)
    for s in syms:
        fp = links.get(s, "")
        if not fp:
            add("problem", f"symbol {s} has no footprint", symbol=s)
        elif re.search(r"[\\/:]|\.pcblib$", fp, re.I):
            add("problem", f"symbol {s} links to a file path, not a footprint name", symbol=s, footprint=fp)
        elif fp not in fps:
            add("problem", f"symbol {s} links to missing footprint {fp}", symbol=s, footprint=fp)
    for name in dict.fromkeys(fps):
        info = parts.get("footprints", {}).get(name, {})
        n = len(info.get("steps", []))
        if n == 0:
            # the board still builds without a body; the student sees the gap and can add a STEP later
            add("warning", f"no 3D model for footprint {name}", footprint=name, kind="3d")
        elif n > 1:
            add("problem", f"footprint {name} has {n} 3D models, expected 1", footprint=name, kind="3d")
    return res


# ---------------------------------------------------------------- status / CLI

def status_rows(project):
    path = library_dir(project) / "manifest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def format_status(manifest):
    cols = ("line", "symbol", "footprint", "3D", "source", "status", "issues")
    rows = [[k, e["symbol"] or "-", e["footprint"] or "-", "yes" if e["step"] else "no", e["source"], e["status"],
             "; ".join(e["issues"])] for k, e in manifest.items()]
    widths = [max(len(c), *(len(r[i]) for r in rows)) if rows else len(c) for i, c in enumerate(cols)]
    widths[-1] = 0
    fmt = lambda r: "  ".join(str(v).ljust(w) for v, w in zip(r, widths)).rstrip()
    counts = {}
    for e in manifest.values():
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    return "\n".join([fmt(cols)] + [fmt(r) for r in rows] + ["", ", ".join(f"{n} {s}" for s, n in sorted(counts.items()))]
                     + [f"note: Altium's parameters for {k} still show {p.get('mpn') or '?'}{' / ' + p['lcsc'] if p.get('lcsc') else ''} "
                        "(order-only swap): the JLC BOM comes from the advisor's export, not from Altium; the next library build updates them"
                        for k, e in manifest.items() for p in [e.get("params_stale")] if p])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Project part library: prepare the symbols, footprints and 3D models.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare", help="download, convert and generate; write library/build and manifest.json")
    p.add_argument("project")
    p.add_argument("--no-fetch", action="store_true", help="use only what is already downloaded")
    p.add_argument("--refresh", action="store_true", help="download again even if a part is already there")
    s = sub.add_parser("status", help="print the per-line table from manifest.json")
    s.add_argument("project")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 1 if e.code else 0
    if not store.pdir(a.project).is_dir():
        print(f"no such project: {a.project}", file=sys.stderr)
        return 1
    if a.cmd == "prepare":
        manifest = prepare(a.project, fetch=not a.no_fetch, refresh=a.refresh)
    else:
        manifest = status_rows(a.project)
        if manifest is None:
            print(f"no library manifest yet: run  python scripts/partlib.py prepare {a.project}")
            return 0
    print(format_status(manifest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
