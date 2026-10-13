"""The deterministic-check registry.

A detector is `fn(fixture_dir: Path, incident: dict) -> list[dict]`, each finding
{"code", "refs", "message", "source"}. Detectors decide for themselves whether
the fixture's state files are relevant and return [] otherwise.

Adding checks in a later stage: write a module per stage, e.g.
scripts/bench/checks_parts.py, with

    from bench.detectors import register

    @register("PART-EOL")
    def eol(fixture_dir, incident): ...

then import it at the bottom of this file (see STAGE_MODULES). The baseline
ships with none, so every incident scores "not caught" deterministically.
"""
import importlib

REGISTRY = []          # [(code, fn)]

# Stage modules to import; each registers its detectors (empty in the I1 baseline).
STAGE_MODULES = ["bench.checks_parts", "bench.checks_schematic", "bench.checks_board", "bench.checks_idea"]


def register(code):
    def deco(fn):
        REGISTRY.append((code, fn))
        return fn
    return deco


def run_all(fixture_dir, incident):
    """{"findings": [...], "errors": [str]}. One detector raising never stops the rest."""
    findings, errors = [], []
    for code, fn in list(REGISTRY):
        try:
            for f in fn(fixture_dir, incident) or []:
                findings.append({"code": f.get("code", code), "refs": list(f.get("refs", [])),
                                 "message": f.get("message", ""),
                                 "source": f.get("source", getattr(fn, "__name__", code))})
        except Exception as exc:                       # noqa: BLE001 - recorded, not fatal
            errors.append(f"detector {code} ({getattr(fn, '__name__', '?')}): "
                          f"{type(exc).__name__}: {exc}")
    return {"findings": findings, "errors": errors}


def caught(findings, expect):
    refs = set(expect.get("refs") or [])
    return any(f["code"] == expect["code"] and (not refs or refs & set(f["refs"]))
               for f in findings)


for _m in STAGE_MODULES:
    importlib.import_module(_m)
