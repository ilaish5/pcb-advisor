"""Template (files starting with _ are not loaded). Copy to metrics/<area>.py.

from lib import metric, Result
import thresholds as TH

def _control(ctx):
    c = ctx.writable_copy("W99-control")
    # ...correct the artifact in c (or build a synthetic one)...
    return c

@metric(id="W99", title="what is measured", root="R1", p0=("P0-3",), level="U", control=_control)
def w99(ctx):
    f = ctx.project / "bom.json"
    bad = [...]                                    # offending items found by rule, not by name
    return Result("pass" if not bad else "fail", measured=bad, expected="offending items = 0",
                  evidence=[ctx.ev(f, "BOM")])
"""
