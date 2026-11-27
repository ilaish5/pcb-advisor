"""Positive controls for the detectors added in acceptance-v1.1 (F-C, F-D, F-F, F-LIM, W11). Each detector is shown its PASS
condition on a hand-built input (the product has no pass state before the fix):

    python -I tests/acceptance/live/controls_v11.py        # every line must say PASS
"""
from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))


def main() -> int:
    from metrics import live_fc as FC, live_fd as FD, live_ff as FF, live_flim as FL, live_w11 as W
    out = []

    def check(name, ok):
        out.append(bool(ok))
        print(f"{'PASS' if ok else 'FAIL'}  {name}")

    names = ["VDD", "GND", "PA0", "PA1", "PB2", "BOOT0", "NRST", "PC13", "PA9", "PA10", "SWDIO", "SWCLK"]
    doc = "\f".join(["Cover page", "Table 8. Pin definitions\n" + " ".join(names), "Electrical characteristics VDD 3.3 V"])
    good, _ = FF.pin_table_pages(doc, names)
    check("F-F(a) the hand-built pin-table page is the only pin page", good == [2])
    check("F-F(a) a page with two pin names is not a pin page", 3 not in good)
    check("F-C(d) affirmative via-in-pad advice is caught", FC.VIA_ADVICE.search("Add thermal vias in the exposed pad of U1."))
    para = "No, I cannot add thermal vias in the exposed pad."
    m = FC.VIA_ADVICE.search(para)
    check("F-C(d) a refusal to add them is not advice", m and FC.NEGATED.search(para[:m.start()][-40:] + m.group(0)))
    check("F-D(a) a claim with a citation is backed", FD.FACT.search("U4 is 128 Mbit {{src:W25Q.pdf|p. 1}}") and FD.CITE.search("{{src:W25Q.pdf|p. 1}}"))
    check("F-D(a) an unverified-phrased claim is accepted", FD.UNVERIFIED.search("U4 is probably 128 Mbit (unverified)"))
    m = FD.PRICE.search("about $46 per board at 10 boards")
    check("F-D(c) a price at the break used is read with its quantity", m and int(m.group(2)) == 10)
    check("F-LIM a refusal line at the control is recognised",
          FL.REFUSE.search("JLC's DFM verdict needs your sign-in: the tool cannot fetch it; upload the report PDF here.")
          and re.search(next(x for x in FL.corpora.header("flim_limits")["limits"] if x["id"] == "jlc-dfm-signin")["words"], "needs your sign-in at JLC", re.I))
    check("W11 re-rendered previews are not side effects", W._changed({"a/x": 1, "artifacts/s.svg": 1}, {"a/x": 1, "artifacts/s.svg": 2}) == [])
    check("W11 a changed project file is a side effect", W._changed({"idea.json": 1}, {"idea.json": 2}) == ["idea.json"])
    return 0 if all(out) else 1


if __name__ == "__main__":
    sys.exit(main())
