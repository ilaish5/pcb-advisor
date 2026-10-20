"""
Lineage: what every output was made from, and whether it still matches.

Each file the tool writes for the manufacturer or for Altium (BOM CSV, CPL, OutJob, Gerber zip, library package)
gets one line in projects/<p>/lineage-log.jsonl when it is written: the file's sha256, the tool version, and
every input it was made from with its own fingerprint at that moment. `status()` takes the fingerprints again:

    fresh     the output and every input are as they were
    stale     an input changed since (the PcbDoc was saved after the Gerbers were zipped)
    edited    the output itself was changed or replaced by hand
    missing   the output is gone
    unknown   no record: written before lineage existed, or put there by hand

An input is a file (the PcbDoc, a Gerber) or a piece of project state. State is fingerprinted by what the
exporter would write from it now, not by the log it is folded from, so a stock check that leaves the BOM CSV
the same does not make it stale.

    python scripts/lineage.py <project> [status | show <file>]
"""
import hashlib
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import store       # noqa: E402
import workspace   # noqa: E402

LOG = "lineage-log.jsonl"
# The Gerbers must be generated after the board was last saved; Altium writes them within seconds of a save.
SAVED_AFTER_S = 60

_hash_memo: dict = {}      # (path, size, mtime_ns) -> sha256: the UI asks every few seconds
_state_memo: dict = {}     # (name, args, deps) -> sha256


def sha256_file(path) -> str:
    p = pathlib.Path(path)
    st = p.stat()
    key = (str(p), st.st_size, st.st_mtime_ns)
    if key not in _hash_memo:
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        _hash_memo[key] = h.hexdigest()
    return _hash_memo[key]


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- project state an output is made from
#
# name -> (what the exporter would write now, the files whose change can change it). The second part only keys the
# memo, so the same state is not rebuilt on every poll.

def _bom_csv(project, fmt):
    from skills import export_bom
    return export_bom.rows(project, fmt)[0]


def _cpl(project, pcb):
    from skills import export_cpl
    return export_cpl.cpl_rows(project, pcb or None)


def _outjob(project):
    import outjob
    return outjob.OUTJOB_TEMPLATE.format(project=project)


def _library(project):
    lib = store.pdir(project) / "library"
    files = {f.relative_to(lib).as_posix(): sha256_file(f) for f in sorted(lib.rglob("*")) if f.is_file()} \
        if lib.is_dir() else {}
    return {"parts": store.library_view(project), "files": files}


def _project_files(project):
    """Every file at the top of the project folder: the logs and settings the BOM is folded from. Stat only, so
    a change anywhere rebuilds the state once, and nothing that matters can be missed."""
    d = store.pdir(project)
    skip = {LOG, "design-model.json", "bom.json"}     # derived from the others, and rewritten on every read
    return sorted(f for f in d.iterdir() if f.is_file() and f.name not in skip) if d.is_dir() else []


STATES = {
    "bom_csv": (_bom_csv, lambda p, *a: _project_files(p)),
    "cpl": (_cpl, lambda p, pcb="": _project_files(p) + ([pathlib.Path(pcb)] if pcb else [])),
    "outjob": (_outjob, lambda p: []),
    "library": (_library, lambda p: _project_files(p) + sorted((store.pdir(p) / "library").rglob("*"))),
}


def _stamp(paths):
    out = []
    for p in paths:
        try:
            st = os.stat(p)
            out.append((str(p), st.st_size, st.st_mtime_ns))
        except OSError:
            out.append((str(p), None, None))
    return tuple(out)


def state_sha(project, name, *args) -> str:
    fn, deps = STATES[name]
    paths = deps(project, *args)
    key = (project, name, args, _stamp(paths)) if paths else None
    if key and key in _state_memo:
        return _state_memo[key]
    sha = _digest(fn(project, *args))
    if key:
        _state_memo[key] = sha
    return sha


# ---------------------------------------------------------------- inputs

def file_input(role, path, compare=True) -> dict:
    """compare=False records the file for the history only: the state input next to it already says what in it
    matters (a CPL depends on the part positions in the PcbDoc, not on its rules)."""
    p = pathlib.Path(path)
    rec = {"kind": "file", "role": role, "path": str(p), "sha256": sha256_file(p), "mtime": p.stat().st_mtime}
    if not compare:
        rec["compare"] = False
    return rec


def state_input(project, name, *args) -> dict:
    return {"kind": "state", "role": name, "name": name, "args": list(args), "sha256": state_sha(project, name, *args)}


def linked_pcb(project):
    """The linked PcbDoc, or None. A bare name is relative to the Altium project's folder."""
    import project as project_mod
    link = project_mod.altium_link(project)
    name = link.get("pcb_file")
    if not name:
        return None
    pcb = pathlib.Path(name)
    if not pcb.is_file() and link.get("project_file"):
        pcb = pathlib.Path(link["project_file"]).parent / name
    return pcb if pcb.is_file() else None


# ---------------------------------------------------------------- record

def _key(project, output) -> str:
    """How an output is named in the log: relative to the project folder when it is inside it."""
    p = pathlib.Path(output).resolve()
    base = store.pdir(project).resolve()
    return p.relative_to(base).as_posix() if p.is_relative_to(base) else str(p)


def record(project, output, inputs, tool, **extra) -> dict:
    """Append one record for an output just written. `inputs` may be a function that builds them, so that one that
    cannot be read (a PcbDoc that Altium or OneDrive holds open on Windows) is caught by note() below."""
    if callable(inputs):
        inputs = inputs()
    out = pathlib.Path(output)
    rec = {"ts": store.now(), "output": _key(project, out), "sha256": sha256_file(out), "tool": tool,
           "version": _version(), "inputs": [i for i in inputs if i]}
    rec.update({k: v for k, v in extra.items() if v not in (None, "", [], {})})
    store.append(project, LOG, rec)
    return rec


def note(project, output, inputs, tool, **extra):
    """record(), for the exporters: the export already happened, so a lineage failure only says so on stderr."""
    try:
        return record(project, output, inputs, tool, **extra)
    except Exception as exc:
        print(f"lineage: could not record {pathlib.Path(output).name}: {exc}", file=sys.stderr)
        return None


def _version() -> str:
    try:
        import update
        return update.version().get("commit", "")
    except Exception:
        return ""


def records(project) -> list:
    return store.read_jsonl(store.pdir(project) / LOG)


def latest(project) -> dict:
    """output key -> its newest record."""
    out = {}
    for rec in records(project):
        if rec.get("output"):
            out[rec["output"]] = rec
    return out


# ---------------------------------------------------------------- status

def _check_input(project, inp) -> str:
    """'' when the input is as recorded, else why not."""
    if inp.get("compare") is False:
        return ""
    if inp.get("kind") == "state":
        try:
            now = state_sha(project, inp["name"], *inp.get("args", []))
        except Exception as exc:                 # an exporter that cannot run now cannot say "fresh" either
            return f"{inp['name']} could not be read again ({exc})"
        return "" if now == inp.get("sha256") else STATE_CHANGED.get(inp["name"], f"{inp['name']} changed")
    p = pathlib.Path(inp.get("path", ""))
    if not p.is_file():
        return f"{p.name} is gone"
    if sha256_file(p) != inp.get("sha256"):
        return f"{p.name} changed since"
    return ""


STATE_CHANGED = {
    "bom_csv": "the BOM changed since",
    "cpl": "the placement changed since (PcbDoc or BOM)",
    "outjob": "the OutJob template changed since (a tool update)",
    "library": "the library parts changed since",
}


def _saved_after(rec) -> str:
    """The board was saved after the files made from it: Gerbers generated before the last save."""
    pcb = next((i for i in rec.get("inputs", []) if i.get("role") == "pcb"), None)
    made = [i.get("mtime") or 0 for i in rec.get("inputs", []) if i.get("role") in ("gerber", "drill")]
    if pcb and made and (pcb.get("mtime") or 0) - max(made) > SAVED_AFTER_S:
        return f"{pathlib.Path(pcb['path']).name} was saved after these Gerbers were generated"
    return ""


def check(project, rec) -> dict:
    out = store.pdir(project) / rec["output"] if not os.path.isabs(rec["output"]) else pathlib.Path(rec["output"])
    row = {"output": rec["output"], "name": out.name, "written": rec.get("ts"), "tool": rec.get("tool"),
           "version": rec.get("version", ""), "inputs": [{k: i.get(k) for k in ("kind", "role", "path", "name")}
                                                        for i in rec.get("inputs", [])], "reasons": []}
    if not out.is_file():
        row.update(status="missing", reasons=[f"{out.name} is gone"])
        return row
    if sha256_file(out) != rec.get("sha256"):
        row.update(status="edited", reasons=[f"{out.name} was changed after the tool wrote it"])
        return row
    reasons = [r for r in (_check_input(project, i) for i in rec.get("inputs", [])) if r]
    early = _saved_after(rec)
    if early:
        reasons.insert(0, early)
    row.update(status="stale" if reasons else "fresh", reasons=reasons)
    return row


def status(project) -> list:
    """One row per file in exports/ (and per recorded output elsewhere), newest record each."""
    rows = {}
    for key, rec in latest(project).items():
        rows[key] = check(project, rec)
    exp = store.pdir(project) / "exports"
    if exp.is_dir():
        for f in sorted(exp.iterdir()):
            key = _key(project, f)
            if f.is_file() and key not in rows and not f.name.endswith(".part"):
                rows[key] = {"output": key, "name": f.name, "status": "unknown", "inputs": [], "written": None,
                             "reasons": ["no record of how it was made: export it again from here"]}
    return sorted(rows.values(), key=lambda r: r["output"])


def by_name(project) -> dict:
    """exports/ file name -> its status row, for the Outputs view."""
    return {r["name"]: r for r in status(project) if r["output"].startswith("exports/")}


def stale(project) -> list:
    """The outputs that must not go to the manufacturer as they are."""
    return [r for r in status(project) if r["output"].startswith("exports/") and r["status"] in ("stale", "edited")]


# ---------------------------------------------------------------- CLI

MARK = {"fresh": "ok", "stale": "STALE", "edited": "EDITED", "missing": "gone", "unknown": "?"}


def main(argv=None):
    import oscompat
    oscompat.utf8_stdio()
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        raise SystemExit("usage: lineage.py <project> [status | show <file>]")
    project = workspace.safe_name(args[0])
    cmd = args[1] if len(args) > 1 else "status"
    if cmd == "show":
        want = args[2] if len(args) > 2 else ""
        hits = [r for r in records(project) if pathlib.PurePath(r.get("output", "")).name == pathlib.PurePath(want).name]
        if not hits:
            print(f"no record for {want}")
            return 1
        print(json.dumps(hits[-1], ensure_ascii=False, indent=2))
        return 0
    rows = status(project)
    if not rows:
        print("no outputs yet")
        return 0
    for r in rows:
        print(f"{MARK.get(r['status'], r['status']):7} {r['output']}" + (f"   ({r['written']}, {r['tool']})" if r.get("written") else ""))
        for why in r["reasons"]:
            print(f"        - {why}")
    return 1 if any(r["status"] in ("stale", "edited") for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
