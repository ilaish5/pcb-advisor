"""Acceptance runner. Run from the repo root, isolated (no product code on the path):

    .venv/Scripts/python.exe -I tests/acceptance/run.py                       # red proof on the frozen 27/11 fixture
    .venv/Scripts/python.exe -I tests/acceptance/run.py --controls            # also: every control must pass
    .venv/Scripts/python.exe -I tests/acceptance/run.py --only W27 W35 --seed 1234
    .venv/Scripts/python.exe -I tests/acceptance/run.py --root <folder with project/ and altium/>   # a fix branch's artifacts
    .venv/Scripts/python.exe -I tests/acceptance/run.py --live http://localhost:8931 --live-project <name>

The fixture manifest is verified before and after the run; a changed fixture makes the run VOID (A4). The seed is printed and
stored (A5). Results go to local/acceptance-runs/<utc>-<seed>.json (local only: they name project files).
Exit code: 0 only when the run is valid and every selected metric has the status the mode requires.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import pathlib
import re
import secrets
import sys
import tempfile
import traceback

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))          # only tests/acceptance itself; never scripts/

import lib  # noqa: E402

DEFAULT_FIXTURE = REPO / "local" / "acceptance-fixtures" / "final-e2e-4l-1127"
MANIFEST_SHA = "423530bb3cdefa11906cc7741d9748191ea4e22299dea10c8766801707519e27"


def verify_manifest(fixture: pathlib.Path) -> list[str]:
    """Return a list of problems; empty = the frozen fixture is intact."""
    man = fixture / "MANIFEST.sha256"
    if not man.is_file():
        return [f"no manifest at {man}"]
    if lib.sha256(man) != MANIFEST_SHA:
        return ["MANIFEST.sha256 itself changed"]
    bad = []
    for line in man.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, rel = line.split(" ", 1)
        rel = rel.lstrip("*").removeprefix("./")
        p = fixture / rel
        if not p.is_file():
            bad.append(f"missing {rel}")
        elif lib.sha256(p) != digest:
            bad.append(f"changed {rel}")
    return bad


def load_metrics() -> None:
    for path in sorted((HERE / "metrics").glob("*.py")):
        if path.name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(f"metrics.{path.stem}", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)


def run_one(m: lib.Metric, ctx: lib.Ctx) -> lib.Result:
    if m.kind == "behaviour" and not ctx.live:
        return lib.not_run("behaviour metric: needs --live (a running server; see README, live replay)")
    try:
        r = m.check(ctx)
        if not isinstance(r, lib.Result):
            return lib.Result("error", detail=f"check returned {type(r).__name__}")
        return r
    except Exception as e:  # a crashing checker is an error, never a pass
        return lib.Result("error", detail=f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=pathlib.Path, help="folder with project/ and altium/ (default: the frozen fixture)")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--only", nargs="*", default=None, help="metric ids (prefix match: W27 matches W27 and W27(a))")
    ap.add_argument("--controls", action="store_true", help="also run every metric on its control; control must pass")
    ap.add_argument("--live", default=None, help="base URL of a running pcb-advisor server, enables behaviour metrics")
    ap.add_argument("--live-project", default=None)
    ap.add_argument("--out", type=pathlib.Path, default=None)
    a = ap.parse_args(argv)

    seed = a.seed if a.seed is not None else secrets.randbelow(2**31)
    root = a.root or DEFAULT_FIXTURE
    is_fixture = a.root is None
    print(f"acceptance run  seed={seed}  root={root}")

    if is_fixture:
        problems = verify_manifest(root)
        if problems:
            print("VOID: the frozen fixture does not match its manifest:", *problems[:10], sep="\n  ")
            return 3
        print(f"fixture manifest ok ({MANIFEST_SHA[:12]}...)")

    load_metrics()
    metrics = lib.REGISTRY
    if a.only:
        metrics = [m for m in metrics if any(m.id == o or m.id.startswith(o + "(") for o in a.only)]
    ids = [m.id for m in metrics]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        print("ERROR: duplicate metric ids:", sorted(dupes))
        return 4

    live = {"base_url": a.live, "project": a.live_project} if a.live else None
    rows = []
    with tempfile.TemporaryDirectory(prefix="acceptance-") as tmp:
        ctx = lib.Ctx(root, seed, pathlib.Path(tmp), live=live, frozen=is_fixture,
                      label="fixture-27-11" if is_fixture else "root")
        for m in metrics:
            r = run_one(m, ctx)
            row = {"id": m.id, "title": m.title, "root_cause": m.root, "p0": list(m.p0), "level": m.level,
                   "kind": m.kind, "module": m.module, **{k: v for k, v in vars(r).items()}}
            if a.controls and m.kind == "artifact":
                if m.control is None:
                    row["control"] = {"status": "error", "detail": "no control: a check that cannot be shown green proves nothing"}
                else:
                    try:
                        cctx = m.control(ctx)
                        cr = run_one(m, cctx)
                        row["control"] = {"status": cr.status, "measured": cr.measured, "detail": cr.detail}
                    except Exception as e:
                        row["control"] = {"status": "error", "detail": f"{type(e).__name__}: {e}"}
            rows.append(row)
            c = f"  control={row['control']['status']}" if "control" in row else ""
            print(f"{m.id:10} {r.status:8} measured={json.dumps(r.measured, default=str)[:80]}{c}")

    if is_fixture:
        problems = verify_manifest(root)
        if problems:
            print("VOID: a check wrote into the frozen fixture:", *problems[:10], sep="\n  ")
            return 3

    # Red proof on the fixture: every artifact metric must FAIL there; with --controls every control must PASS.
    ok = True
    for row in rows:
        if is_fixture and row["kind"] == "artifact" and row["status"] != "fail":
            ok = False
        if "control" in row and row["control"]["status"] != "pass":
            ok = False
        if row["status"] == "error":
            ok = False
    # Coverage: every catalogue id in ACCEPTANCE.md needs at least one metric (only checked on a full run).
    missing = []
    if not a.only:
        doc = (REPO / "docs" / "e2e-2026-11-27" / "ACCEPTANCE.md").read_text(encoding="utf-8")
        want = re.findall(r"^### ([A-Z][A-Z0-9-]*) ·", doc, re.M) + re.findall(r"^\*\*(P0-\d)\.", doc, re.M)             + re.findall(r"^### (T-[A-J]) ·", doc, re.M)
        have = {r["id"].split("(")[0] for r in rows}
        missing = [w for w in dict.fromkeys(want) if w not in have]
        if missing:
            ok = False
            print(f"catalogue ids with no metric yet ({len(missing)}): {' '.join(missing)}")
    if not rows:
        ok = False
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in lib.STATUSES}
    print(f"\n{len(rows)} metrics: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    if is_fixture:
        print("RED PROOF " + ("OK: every artifact metric fails on 27/11" if ok else "INCOMPLETE: see rows not 'fail' above"))

    out = a.out or (REPO / "local" / "acceptance-runs" /
                    f"{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}-{seed}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"seed": seed, "root": str(root), "manifest": MANIFEST_SHA if is_fixture else None,
                               "controls": a.controls, "live": live, "rows": rows}, indent=1, default=str),
                   encoding="utf-8")
    print(f"results: {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
