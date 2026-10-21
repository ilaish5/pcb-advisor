"""Project part library, stage L1 (no Altium): fetch, convert, generate, share, check, manifest.

For every BOM line the tool gets a symbol, a footprint and (when EasyEDA has one) a STEP model:
  1. EasyEDA by the line's LCSC C-number, through easyeda2kicad run as a subprocess (no login). A failure is
     reported and the line falls through to 2; there is no retry around a block. Downloads are untrusted data.
  2. Generated: an IPC-7351 nominal footprint for the standard packages and a standard-shape or box symbol
     (pins from the project's netlist sheets).
  3. Otherwise status "missing" with the reason. Nothing is invented.
Output, all under projects/<name>/library/: easyeda/<Cxxxx>/ (downloads), build/ (the spec files stage L2 feeds
to Altium: symbols_spec.txt, footprints_spec.txt, links.txt, props.txt, parts.json) and manifest.json.
The LIBRARY|/FPLIB| lines carry the placeholders <SCHLIB>/<PCBLIB>; stage L2 fills in the real paths.

  python scripts/partlib.py prepare <project> [--no-fetch] [--refresh]
  python scripts/partlib.py status <project>
"""
import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import store  # noqa: E402
from partlib_convert import clean, convert_footprint, convert_symbols, safe_name  # noqa: E402
from partlib_kicad import fetch_kicad, kicad_footprint  # noqa: E402
from partlib_generate import PASSIVE_PREFIX, POWER_NAME, footprint_for, package_key, symbol_for  # noqa: E402

LCSC_RE = re.compile(r"^C\d{2,9}$")
RATING_PREFIX = ("R", "C", "L")                 # these show their value as the comment, the rest their MPN
FETCH_TIMEOUT = 180


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
    sym = convert_symbols((dest / "lib.kicad_sym").read_text(encoding="utf-8"))[0]
    mods = sorted((dest / "lib.pretty").glob("*.kicad_mod"))
    pick = next((m for m in mods if m.stem == sym["footprint"]), mods[0] if mods else None)
    if pick is None:
        raise ValueError("no footprint in the download")
    fp = convert_footprint(pick.read_text(encoding="utf-8"))
    fp["name"] = _plain_name(fp["name"])
    step = None
    if fp["model"]:
        stem = pathlib.PurePosixPath(fp["model"]["file"].replace("\\", "/")).stem
        for cand in (dest / "lib.3dshapes").glob("*"):
            if cand.stem == stem and cand.suffix.lower() in (".step", ".stp"):
                step = cand
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


# ---------------------------------------------------------------- prepare

def prepare(project, fetch=True, refresh=False, fetcher=None, kicad_fetcher=None):
    """Build the library data for every BOM line; returns the manifest dict (also written to disk)."""
    fetcher = fetcher or fetch_one
    kicad_fetcher = kicad_fetcher or fetch_kicad
    lib = library_dir(project)
    sheets = _sheet_pins(project)
    supply = store.supply_for(project)
    build, manifest, by_mpn = Build(), {}, {}
    for line in store.bom_lines(project):
        key = line["key"]
        refs = line.get("refs") or [key]
        prefix = _prefix(refs[0])
        mpn = (line.get("mpn") or line.get("value") or key).strip()
        lcsc = lcsc_code(line, supply.get(key))
        line = {**line, "lcsc": lcsc}
        e = {"symbol": "", "footprint": "", "step": "", "source": "missing", "status": "missing", "issues": [],
             "package": line.get("package", ""), "lcsc": lcsc}
        manifest[key] = e
        prev = by_mpn.get(mpn.lower())
        if prev and manifest[prev]["symbol"]:               # the same MPN on another line: one library part
            src = manifest[prev]
            e.update({k: src[k] for k in ("symbol", "footprint", "step", "source", "status")})
            e["issues"] = list(src["issues"])
            build.symbols[src["symbol"]].setdefault("lines", [prev]).append(key)
            continue
        by_mpn[mpn.lower()] = key
        got = None                                          # (pins, gfx, desc_for_symbol, footprint name)
        if lcsc:
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
        if got is None:
            got = _generate(build, e, line, prefix, sheets.get(refs[0], []), (lib, kicad_fetcher, fetch, refresh))
        if got is None:
            continue
        pins, gfx, fpname = got
        _fix_pins(pins, prefix)
        name = build.symbol_name(mpn)
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
                           + "; put a vendor zip with the part's files in Sources")
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
                           "a standard one; the pin list is needed")
        return None
    e["source"] = source
    e["issues"] += notes + sym[2]
    return sym[0], sym[1], fpname


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
    return "\n".join([fmt(cols)] + [fmt(r) for r in rows] + ["", ", ".join(f"{n} {s}" for s, n in sorted(counts.items()))])


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
