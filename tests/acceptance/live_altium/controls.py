"""Controls for the Altium-judged behaviour metrics (python -I tests/acceptance/live_altium/controls.py).

run.py does not run controls for behaviour metrics (they need a live system, and a pass state may not exist on the pre-fix product).
A pass state is shown here instead on synthetic observations: every metric module exports CONTROLS[id] = (judge, good, bad) where
`good` is what the page/Altium would show on a correct system and `bad` is the red observation. The judge must say pass on `good`
and fail on `bad` (A4: a check that cannot go green proves nothing, one that cannot go red proves nothing). Metrics whose judge cannot
be separated from the live observation say so in their own docstring and are listed as `no control`.
"""
from __future__ import annotations

import importlib
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

MODULES = ("metrics.altium_ui", "metrics.altium_ops", "metrics.altium_faults", "metrics.altium_agent", "metrics.altium_drc")


def main() -> int:
    bad = 0
    n = 0
    for name in MODULES:
        try:
            mod = importlib.import_module(name)
        except ModuleNotFoundError:
            continue
        for mid, (judge, good, badobs) in sorted(getattr(mod, "CONTROLS", {}).items()):
            n += 1
            g, b = judge(good).status, judge(badobs).status
            ok = (g == "pass" and b == "fail")
            bad += 0 if ok else 1
            print(f"{'ok ' if ok else 'BAD'} {mid:14s} good={g:5s} bad={b}")
    print(f"{n} controls, {bad} wrong")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
