"""Positive controls for the live detectors (A4: a check that cannot go green proves nothing).

Most live metrics have no pass state before the fix (the product has no such check yet), so the control is a hand-built
page or record that shows the PASS condition, run through the same detector code the metric uses:

    python -I tests/acceptance/live/controls.py        # every line must say PASS
"""
from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

GOOD_FAILURE = """<main><div role="alert" class="notice bad" style="font: 14px/20px sans-serif; width: 600px">
<strong>Rule 'Rqwerty' not added: kind 'Kindqwerty' is not supported</strong>
<p>Nothing was changed; choose a supported kind and add it again.</p>
<details><summary>Details</summary><pre>Kind 'Kindqwerty' is not supported; choose one of: Width, Clearance</pre></details></div></main>"""
BAD_FAILURE = """<main><div class="toast bad" style="font: 14px/20px sans-serif; width: 300px">could not fetch: C:\\\\Users\\\\x\\\\a.pdf
[Errno 111] Connection refused while reading scripts/sources.py at 0.299999 mm</div></main>"""
CONFLICT = """<main><p>Conflict: requirement Power ("no battery") and requirement Clock ("RTC keeps time unplugged") cannot both hold.</p></main>"""
NETLIST_DRAWING = ("<main><div>" + "".join(f"<div>{t}</div>" for t in ["U12", "STM32F411CEU6", "20", "PB2", "BOOT1_STRAP"])
                   + "</div></main>")          # the preview draws one label per element
FINDING = """<main><p>U12 pin 20 PB2 (BOOT1) has no level: the boot table needs it tied low for boot from flash.</p></main>"""


def main() -> int:
    from live import failures
    from live.driver import launch
    from metrics import live_design as D, live_p0 as P0, live_ui as UI, live_themes as TH
    from playwright.sync_api import sync_playwright
    out = []

    def check(name, ok):
        out.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  {name}")

    with sync_playwright() as pw:
        b = launch(pw)
        pg = b.new_page(viewport={"width": 1366, "height": 768})

        class _P:                      # the small part of driver.Page the detectors use
            page = pg

            def eval(self, js, arg=None):
                return pg.evaluate(js, arg) if arg is not None else pg.evaluate(js)

        P = _P()
        pg.set_content(GOOD_FAILURE)
        c = [x for x in failures.visible_failures(P) if x["cls"].startswith("notice")][0]
        c["still_after_15s"] = True
        c["expanded"] = "Kind 'Kindqwerty' is not supported; choose one of: Width, Clearance"
        v = failures.readability(c, "qwerty", re.compile(r"rule", re.I), c["expanded"])
        check(f"P0-4 readability passes a hand-built good failure card {v}", v == [])
        pg.set_content(BAD_FAILURE)
        c = failures.visible_failures(P)[0]
        c["still_after_15s"] = False
        check("P0-4 readability fails the 27/11-style toast", len(failures.readability(c, "qwerty", re.compile("fetch"), None)) >= 4)
        check("P0-2 compliant status 'Reading the BOM · 12 s · step 2/5'", P0._compliant(["Reading the BOM · 12 s · step 2/5"]))
        check("P0-2 timer-only status is not compliant", not P0._compliant(["Working… 12 s"]))
        pg.set_content(CONFLICT)
        check("W3 conflict naming both items is detected", D._conflict_shown(D._messages(P), "Power", "Clock"))
        pg.set_content(NETLIST_DRAWING)
        check("W6/W22 a drawn netlist is not a message", D._named(D._messages(P), "U12", r"boot|strap") == [])
        pg.set_content(FINDING)
        check("W6/W22 a prose finding naming the part is a message", len(D._named(D._messages(P), "U12", r"boot|strap|level")) == 1)
        pg.set_content('<main><button class="mic ok" aria-label="Pins: verified">x</button></main>')
        check("U1 tone reader sees an ok chip", pg.locator("button").evaluate(UI.TONE_JS) == "ok")
        check("W13 number match within 5 %", D._numbers_near("gm_crit 1.67 mA/V exceeds 1 mA/V", 1.70) and not D._numbers_near("gm 2.4", 1.70))
        check("T-E clean message has no leak", not any(re.search(rx, "The BOM has 31 lines and 55 parts.") for rx in TH.LEAKS))
        check("P0-3 evidence record that matches the file holds", _evidence_control(P0))
        b.close()
    return 0 if all(out) else 1


def _evidence_control(P0) -> bool:
    import hashlib
    import json
    import tempfile
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "bom.json").write_text("[]")
    rec = {"path": "bom.json", "sha256": hashlib.sha256(b"[]").hexdigest(), "in_scope": 3, "examined": 3, "failed": 0}
    ok = P0._evidence_holds(json.dumps(rec), d)
    (d / "bom.json").write_text("[1]")          # stale: the file changed after the check
    return ok and not P0._evidence_holds(json.dumps(rec), d)


if __name__ == "__main__":
    sys.exit(main())
