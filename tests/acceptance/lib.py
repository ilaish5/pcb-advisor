"""Acceptance framework core: metric registry, run context, results.

Rules (docs/e2e-2026-11-27/ACCEPTANCE.md Part A):
- A2: nothing under tests/acceptance imports product code (scripts/, ui/, pcb.py). The runner runs with `python -I` and no
  product path on sys.path, and gate.py checks every import with the AST.
- A1: a metric reads artifacts (files, HTTP responses, DOM), never the product's own status or log as proof.
- A14: one metric, one measured value, one pass condition.
- Every artifact metric has a red fixture (the frozen 27/11 snapshot) and a positive control (a corrected or synthetic copy on which
  the same check must pass). A check that cannot go green proves nothing, a check that cannot go red proves nothing (A4).
"""
from __future__ import annotations

import dataclasses
import hashlib
import pathlib
import random
import shutil
from typing import Any, Callable

STATUSES = ("pass", "fail", "not_run", "error")


@dataclasses.dataclass
class Result:
    status: str                     # pass | fail | not_run | error
    measured: Any = None            # the one measured quantity (A14): a number, or a list of the offending items
    expected: str = ""              # the pass condition in words, e.g. "unflagged decap pins = 0"
    detail: str = ""                # short human text; for not_run, why
    evidence: list = dataclasses.field(default_factory=list)   # [{path, sha256, what}] of every file the check read

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"bad status {self.status!r}")


@dataclasses.dataclass
class Metric:
    id: str                         # catalogue id: P0-1, W27, U3, F-I(b), T-B ...
    title: str
    root: str                       # R1..R5, or P0
    p0: tuple                       # P0 classes this is an instance of, e.g. ("P0-3",)
    level: str                      # U | L | B | E (ACCEPTANCE.md Part B conventions)
    kind: str                       # "artifact" (reads the fixture) | "behaviour" (needs a live system, --live)
    check: Callable[["Ctx"], Result]
    control: Callable[["Ctx"], "Ctx"] | None = None   # builds a corrected/synthetic copy; check(control(ctx)) must pass
    module: str = ""


REGISTRY: list[Metric] = []


def metric(*, id: str, title: str, root: str, level: str, kind: str = "artifact", p0: tuple = (),
           control: Callable[["Ctx"], "Ctx"] | None = None):
    """Register a check function as a metric. One function per catalogue id (or per lettered sub-metric)."""
    def deco(fn: Callable[["Ctx"], Result]):
        REGISTRY.append(Metric(id=id, title=title, root=root, p0=tuple(p0), level=level, kind=kind,
                               check=fn, control=control, module=fn.__module__))
        return fn
    return deco


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Ctx:
    """What a check sees. `root` is a fixture-shaped folder: root/project (the pcb-advisor project folder) and root/altium
    (the Altium project folder). The frozen fixture is read-only: a control or canary works on `writable_copy()`."""

    def __init__(self, root: pathlib.Path, seed: int, work: pathlib.Path, live: dict | None = None,
                 frozen: bool = True, label: str = "fixture") -> None:
        self.root = pathlib.Path(root)
        self.project = self.root / "project"
        self.altium = self.root / "altium"
        self.seed = seed
        self.rng = random.Random(seed)
        self.work = pathlib.Path(work)
        self.live = live            # {"base_url": ..., "project": ...} when behaviour metrics may run, else None
        self.frozen = frozen
        self.label = label

    # -- reading
    def ev(self, path: pathlib.Path, what: str = "") -> dict:
        p = pathlib.Path(path)
        return {"path": str(p.relative_to(self.root)) if p.is_relative_to(self.root) else str(p),
                "sha256": sha256(p), "what": what}

    def pcbdoc(self) -> pathlib.Path:
        docs = sorted(self.altium.glob("*.PcbDoc"))
        if len(docs) != 1:
            raise FileNotFoundError(f"expected one PcbDoc in {self.altium}, found {len(docs)}")
        return docs[0]

    # -- writing (controls and canaries only)
    def writable_copy(self, name: str) -> "Ctx":
        dst = self.work / name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(self.root, dst, ignore=shutil.ignore_patterns(".advisor-backup", "MANIFEST.sha256"))
        return Ctx(dst, self.seed, self.work, self.live, frozen=False, label=name)


def not_run(why: str, expected: str = "") -> Result:
    return Result("not_run", expected=expected, detail=why)
