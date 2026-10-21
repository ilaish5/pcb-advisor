"""Design vs ordering, by footprint: the footprint identity of a line, the match of a candidate part, the pinned footprint
of an order-only swap, the order check and its action. The suppliers and EasyEDA are mocked: no network."""
import json
import os
import shutil
import sys
import time
import pathlib

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_partlib import FIX, fake_fetch, prep, proj  # noqa: E402,F401  (the fixture project and the fake EasyEDA)
from test_server import get as tget, post as tpost, server as server_url  # noqa: E402,F401  (the real handler)

import export_bom  # noqa: E402
import partlib_match  # noqa: E402
import jlc  # noqa: E402
import order_check  # noqa: E402
import partlib  # noqa: E402
import serve  # noqa: E402
import store  # noqa: E402
from altium import bridge  # noqa: E402


def fixture_fetch(mapping, calls=None):
    """An EasyEDA that answers C-numbers from fixture folders: {"C101": ("C100", edit)}; edit changes the .kicad_mod text."""
    def fetch(cid, dest):
        if calls is not None:
            calls.append(cid)
        if cid not in mapping:
            return False, "EasyEDA answered: part not found"
        src, edit = mapping[cid]
        shutil.copytree(FIX / src, dest, dirs_exist_ok=True)
        if edit:                                                    # (file pattern, old, new)
            for f in dest.rglob(edit[0]):
                f.write_text(f.read_text().replace(edit[1], edit[2]), encoding="utf-8")
        return True, "downloaded"
    return fetch


CANDIDATES = {"C101": ("C100", None),                              # the same land pattern as the line's C100
              "C102": ("C100", ("*.kicad_mod", "(size 0.8 0.9)", "(size 0.9 0.9)")),   # two pads, but wider
              "C200": ("C200", None),                              # three pins
              "C201": ("C200", None),                              # the line U1's own pads and pins
              "C202": ("C200", ("*.kicad_sym", '(name "VOUT"', '(name "EN"'))}   # the same pads, pin 3 does another job
RESISTOR = "10kΩ ±1% 100mW 0603 Chip Resistor - Surface Mount"
INFO = {"C101": {"package": "0603", "description": RESISTOR}, "C102": {"package": "0603", "description": RESISTOR},
        "C200": {"package": "SOT-23-3", "description": "LDO 3.3V 300mA"}, "C201": {"package": "SOT-23-3", "description": "LDO 3.3V"},
        "C202": {"package": "SOT-23-3", "description": "LDO 3.3V"}}


@pytest.fixture(autouse=True)
def jlc_info(monkeypatch):
    monkeypatch.setattr(jlc, "part_by_code", lambda code, transport=None: INFO.get(code))


def back(proj):
    """The inputs and the manifest were made some seconds ago: a log line written now is newer on any file system clock."""
    pd, now = store.pdir(proj), time.time()
    for f in [pd / "bom-log.jsonl", pd / "supply-log.jsonl", *(pd / "netlist").rglob("*.json")]:
        os.utime(f, (now - 20, now - 20))
    os.utime(pd / "library" / "manifest.json", (now - 10, now - 10))


@pytest.fixture
def built(proj, home):
    prep(proj, fetcher=fake_fetch([]))
    back(proj)
    assert not bridge.library_stale(proj)
    return proj


def log(proj, name, rec):
    with open(store.pdir(proj) / name, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


# ---------------------------------------------------------------- the two bugs of the old export / supply

def test_export_code_is_the_declared_one_else_the_check_of_the_current_mpn(proj):
    key = "R2"                                                        # mpn RC0603-4K7
    log(proj, "supply-log.jsonl", {"line": key, "mpn": "OLD-MPN", "supplier": "LCSC", "stock": 5, "source": "LCSC C555"})
    assert export_bom.lcsc_code(proj, key, {"mpn": "RC0603-4K7"}) == ""            # a code checked for another MPN
    log(proj, "supply-log.jsonl", {"line": key, "mpn": "rc0603-4k7", "supplier": "LCSC", "stock": 5, "source": "LCSC C777"})
    assert export_bom.lcsc_code(proj, key, {"mpn": "RC0603-4K7"}) == "C777"        # case does not matter
    log(proj, "supply-log.jsonl", {"line": key, "mpn": "OLD-MPN", "supplier": "LCSC", "stock": 5, "source": "LCSC C888"})
    assert export_bom.lcsc_code(proj, key, {"mpn": "RC0603-4K7"}) == "C777"        # the later hit is not this MPN's
    assert export_bom.lcsc_code(proj, key, {"mpn": "RC0603-4K7", "lcsc": "C300"}) == "C300"     # declared first


def test_a_changed_lcsc_makes_the_stock_answer_stale(proj):
    store.add_supply(proj, "R2", "LCSC", 900, 0.01, "RC0603-4K7", source="LCSC C1", declared="C1")
    store.edit_bom(proj, "R2", "lcsc", "C1")
    supply = lambda: next(l for l in store.bom(proj, write=False) if l["key"] == "R2")["supply"]
    assert supply()["LCSC"]["stock"] == 900
    store.edit_bom(proj, "R2", "lcsc", "C2")                                       # a C-number swap
    assert supply() is None                                                        # never the old part's stock
    store.add_supply(proj, "R2", "LCSC", 3, 0.02, "RC0603-4K7", source="LCSC C2", declared="C2")
    assert supply()["LCSC"]["stock"] == 3
    log(proj, "supply-log.jsonl", {"line": "R2", "mpn": "RC0603-4K7", "supplier": "Mouser", "stock": 7})   # an old answer without `lcsc`
    assert supply()["Mouser"]["stock"] == 7


# ---------------------------------------------------------------- footprint identity and match

def test_footprint_of_a_line_is_its_name_and_a_land_pattern_fingerprint(built):
    fp = partlib.footprint_of(built, "R1")
    assert fp["name"] == "R0603_FAKE" and fp["source"] == "easyeda" and fp["pads"] == 2 and fp["pins"] == ["1", "2"]
    assert fp["fingerprint"] and fp["fingerprint"] == partlib.footprint_of(built, "R3")["fingerprint"]
    assert partlib.footprint_of(built, "R2")["source"] == "generated"
    assert partlib.footprint_of(built, "NOPE") is None
    a = ["PAD|1|-31.5|20|0|Top Layer|1|0|0|0|0|31.5|35.4|2|", "PAD|2|31.5|20|0|Top Layer|1|0|0|0|0|31.5|35.4|2|", "TRACK|0|0|1|1|5|Top Overlay"]
    turned = ["PAD|2|31.5|20|90|Top Layer|1|0|0|0|0|35.4|31.5|2|", "PAD|1|-31.5|20|90|Top Layer|1|0|0|0|0|35.4|31.5|2|"]
    nudged = [a[0].replace("-31.5", "-32.5"), a[1]]
    assert partlib.land_fingerprint(a) == partlib.land_fingerprint(turned)         # silk, order and a quarter turn do not count
    assert partlib.land_fingerprint(a) != partlib.land_fingerprint(nudged)         # 0.01 mil is under the rounding, 1 mil is not
    assert partlib.land_fingerprint(a) == partlib.land_fingerprint([a[0].replace("31.5", "31.51"), a[1]])
    plated, unplated = "PAD|1|0|0|0|Multi-Layer|1|40|0|0|0|80|80|1|", "PAD|1|0|0|0|Multi-Layer|0|40|0|0|0|80|80|1|"
    slot, slot_turned = "PAD|1|0|0|0|Multi-Layer|1|40|2|120|0|80|80|1|", "PAD|1|0|0|0|Multi-Layer|1|40|2|120|90|80|80|1|"
    assert len({partlib.land_fingerprint([x]) for x in (plated, unplated, slot, slot_turned)}) == 4   # plating, slot and slot turn count
    flat, diagonal = "PAD|1|0|0|0|Top Layer|1|0|0|0|0|90|30|2|", "PAD|1|0|0|45|Top Layer|1|0|0|0|0|90|30|2|"
    assert partlib.land_fingerprint([flat]) != partlib.land_fingerprint([diagonal])                  # 45 degrees is not 0


def test_match_of_a_part_with_an_easyeda_footprint(built):
    calls = []
    f = fixture_fetch(CANDIDATES, calls)
    same = partlib.footprint_match(built, "R1", "C101", fetcher=f)
    assert same["match"] == "same" and same["footprint"] == "R0603_FAKE" and "same function" in same["why"]
    assert (store.pdir(built) / "library" / "easyeda" / "C101" / "lib.kicad_sym").exists()      # cached like prepare's
    assert partlib.footprint_match(built, "R1", "C102", fetcher=f)["match"] == "different"      # another land pattern
    pins = partlib.footprint_match(built, "R1", "C200", fetcher=f)
    assert pins["match"] == "different" and "pins" in pins["why"]
    n = len(calls)
    assert partlib.footprint_match(built, "R1", "C101", fetcher=f)["match"] == "same" and len(calls) == n    # from the cache


def test_a_match_that_cannot_be_decided_is_unknown_never_same(built, proj):
    f = fixture_fetch(CANDIDATES)
    assert partlib.footprint_match(built, "R1", "C555", fetcher=f)["match"] == "unknown"       # EasyEDA has nothing
    assert partlib.footprint_match(built, "R1", "", fetcher=f)["match"] == "unknown"
    assert partlib.footprint_match(built, "R1", "junk", fetcher=f)["match"] == "unknown"
    assert partlib.footprint_match(built, "NOPE", "C101", fetcher=f)["match"] == "unknown"    # no footprint in the library


def test_match_of_a_generated_footprint_goes_by_package_and_pins(built, monkeypatch):
    f = fixture_fetch(CANDIDATES)
    r2 = {"description": "4.7kΩ ±1% 0603 Resistor"}
    assert partlib.footprint_match(built, "R2", "C101", package="0603", fetcher=f, cand=r2)["match"] == "same"
    assert partlib.footprint_match(built, "R2", "C101", package="C0603", fetcher=f, cand=r2)["match"] == "same"   # the same package key
    calls = []
    assert partlib.footprint_match(built, "R2", "C101", package="0805", fetcher=fixture_fetch(CANDIDATES, calls))["match"] == "different"
    assert calls == []                                                                         # no download needed to say it
    assert partlib.footprint_match(built, "R2", "C200", package="0603", fetcher=f, cand=r2)["match"] == "different"    # three pins
    monkeypatch.setattr(jlc, "part_by_code", lambda code, transport=None: (_ for _ in ()).throw(OSError("offline")))
    assert partlib.footprint_match(built, "R2", "C101", fetcher=f)["match"] == "unknown"       # no package to compare
    assert partlib.footprint_match(built, "R2", "C101", package="Weird-9", fetcher=f, cand=r2)["match"] == "unknown"


# ---------------------------------------------------------------- the footprint pinned on an order-only swap

def swap(proj, **kw):
    return {"mpn": "NEW-RES", "lcsc": "C101", "manufacturer": "NewCo", "footprint_lock": "R0603_FAKE", **kw}


def test_prepare_keeps_a_locked_footprint_and_symbol(built, home):
    lib = home / "projects" / built / "library"
    before = (lib / "build" / "footprints_spec.txt").read_text(encoding="cp1252")
    sym_before = (lib / "build" / "symbols_spec.txt").read_text(encoding="cp1252")
    man_before = json.loads((lib / "manifest.json").read_text())
    log(built, "bom-log.jsonl", {"ts": "2026-10-21T11:00:00", "by": "t", "line": "R1", "changes": swap(built)})
    calls = []
    m = prep(built, fetcher=fake_fetch(calls))
    assert "C101" not in calls and not (lib / "easyeda" / "C101").exists()                  # nothing fetched, nothing added
    assert m["R1"]["footprint"] == "R0603_FAKE" and m["R1"]["symbol"] == man_before["R1"]["symbol"]
    assert m["R1"]["step"] == man_before["R1"]["step"] and m["R1"]["lcsc"] == "C101" and m["R1"]["locked"] == "R0603_FAKE"
    assert (lib / "build" / "footprints_spec.txt").read_text(encoding="cp1252") == before
    assert partlib.footprint_of(built, "R1")["fingerprint"] == partlib.land_fingerprint(
        partlib._spec_footprints(lib / "build" / "footprints_spec.txt")["R0603_FAKE"]["lines"])
    new_sym = (lib / "build" / "symbols_spec.txt").read_text(encoding="cp1252")
    body = lambda t: t.split("SYMBOL|")[1].split(chr(10), 1)[1]
    assert body(new_sym) == body(sym_before)                    # the first symbol keeps its drawing and pins
    assert json.loads((lib / "build" / "parts.json").read_text())["symbols"]["0603WAF1002T5E"]["params"]["MPN"] == "NEW-RES"
    assert [p for p in partlib.check_build(lib / "build") if p["level"] == "problem"] == []


def test_without_a_lock_a_swap_builds_the_part_again(built, home):
    log(built, "bom-log.jsonl", {"ts": "2026-10-21T11:00:00", "by": "t", "line": "R1", "changes": swap(built, footprint_lock="")})
    calls = []
    prep(built, fetcher=fake_fetch(calls))
    assert "C101" in calls                                                                  # today's behaviour: a design change


def test_a_lock_that_does_not_match_the_last_build_is_not_honoured(built):
    log(built, "bom-log.jsonl", {"ts": "2026-10-21T11:00:00", "by": "t", "line": "R1", "changes": swap(built, footprint_lock="OTHER_FP")})
    calls = []
    prep(built, fetcher=fake_fetch(calls))
    assert "C101" in calls


def test_an_approved_order_only_swap_does_not_stale_the_library(built, monkeypatch):
    monkeypatch.setattr(partlib, "fetch_one", fixture_fetch(CANDIDATES))
    rec = store.propose_bom(built, "R1", swap(built), reason="order-only swap: same footprint")
    assert rec["changes"]["footprint_lock"] == "R0603_FAKE" and store.classify_proposal(rec) == "important"
    assert not store.may_auto_apply(rec, "important") and store.may_auto_apply(rec, "auto")      # approvals are not loosened
    store.decide(built, rec["id"], "approved")
    line = next(l for l in store.bom_lines(built) if l["key"] == "R1")
    assert line["mpn"] == "NEW-RES" and line["lcsc"] == "C101" and line["footprint_lock"] == "R0603_FAKE"
    assert not bridge.library_stale(built)
    assert json.loads((store.pdir(built) / "library" / "manifest.json").read_text())["R1"]["lcsc"] == "C101"
    store.edit_bom(built, "R1", "mpn", "ANOTHER")                                           # a plain edit voids the lock
    assert "footprint_lock" not in next(l for l in store.bom_lines(built) if l["key"] == "R1")
    assert bridge.library_stale(built)


def test_a_swap_without_a_lock_stales_the_library(built):
    rec = store.propose_bom(built, "R1", swap(built, footprint_lock=""), reason="alternative")
    store.decide(built, rec["id"], "approved")
    assert bridge.library_stale(built)


def test_a_lock_that_is_not_proven_is_dropped_at_proposal(built, monkeypatch):
    monkeypatch.setattr(partlib, "fetch_one", fixture_fetch(CANDIDATES))
    for ch in (swap(built, lcsc="C102"), swap(built, lcsc="C200"), swap(built, lcsc="C555"), swap(built, footprint_lock="WRONG")):
        rec = store.propose_bom(built, "R1", ch)
        assert "footprint_lock" not in rec["changes"] and "footprint_lock" not in rec["before"]
    rec = store.propose_bom(built, "R1", {k: v for k, v in swap(built).items() if k != "lcsc"})      # no code, no proof
    assert "footprint_lock" not in rec["changes"]


# ---------------------------------------------------------------- the order check

def alt(code, mpn, stock, package="0603", **kw):
    return {"code": code, "mpn": mpn, "manufacturer": "AltCo", "package": package, "stock": stock, "library_type": "Basic",
            "description": RESISTOR, "price_breaks": [{"qty": 1, "price": 0.01}], **kw}


def stock(proj, key, mpn, n, **kw):
    store.add_supply(proj, key, "LCSC", n, 0.01, mpn, source="LCSC C100", **kw)


@pytest.fixture
def orderable(built, monkeypatch):
    monkeypatch.setattr(partlib, "fetch_one", fixture_fetch(CANDIDATES))
    stock(built, "R1", "0603WAF1002T5E", 0, code="C100", exact=True)             # out: a footprint-identical alternative exists
    stock(built, "R2", "RC0603-4K7", 0)                 # out: only another package
    stock(built, "U1", "LDO33", 0)                      # out: nothing at all
    stock(built, "D1", "BAT54", 100000)                 # fine
    stock(built, "C11", "CC0603-100N", 2)               # short: only an alternative with an unproven footprint
    alts = {"R1": [alt("C200", "THREE-PIN", 9000, "SOT-23"), alt("C101", "SAME-RES", 5000)],
            "R2": [alt("C200", "THREE-PIN", 9000, "SOT-23-3")],
            "U1": [],
            "C11": [alt("C555", "NO-MODEL", 9000)]}
    monkeypatch.setattr(jlc, "alternatives", lambda line, n=5, transport=None: alts.get(line["key"], []))
    return built


def test_order_check_classifies_each_line(orderable):
    stale = bridge.library_stale(orderable)
    res = order_check.order_check(orderable)
    assert bridge.library_stale(orderable) == stale                             # asking changes nothing
    by = {l["line"]: l for l in res["lines"]}
    assert by["R1"]["class"] == "swap_free" and by["R2"]["class"] == "design_change"
    assert by["U1"]["class"] == "no_alternative" and by["D1"]["class"] == "ok" and by["C11"]["class"] == "design_change"
    assert by["J1"]["class"] == "unchecked" and by["D1"]["alternatives"] == []
    first = by["R1"]["alternatives"][0]                                         # the identical footprint comes first
    assert (first["code"], first["match"], first["footprint"]) == ("C101", "same", "R0603_FAKE")
    assert by["R1"]["alternatives"][1]["match"] == "different"
    assert by["C11"]["alternatives"][0]["match"] == "unknown"                  # EasyEDA has nothing for C555: no claim
    assert len(by["R1"]["alternatives"]) <= 3
    assert res["counts"]["swap_free"] == 1 and "R1 swap_free" in order_check.summary(res)


def test_a_same_footprint_alternative_with_too_little_stock_is_no_swap(orderable, monkeypatch):
    monkeypatch.setattr(jlc, "alternatives", lambda line, n=5, transport=None: [alt("C101", "SAME-RES", 2)] if line["key"] == "R1" else [])
    by = {l["line"]: l for l in order_check.order_check(orderable)["lines"]}
    assert by["R1"]["class"] == "no_alternative" and by["R1"]["alternatives"] == []      # 2 in stock for a build of 5


def test_recheck_keeps_a_fresh_library_fresh_when_the_code_is_unchanged(orderable, monkeypatch):
    import check_availability

    def check(project, keys=None):
        store.add_supply(project, "R1", "LCSC", 800, 0.01, "0603WAF1002T5E", source="LCSC C100", code="C100", exact=True)
    monkeypatch.setattr(check_availability, "check", check)
    assert bridge.library_stale(orderable)                                      # the stock rows above are newer than the manifest
    partlib.restamp_if_same(orderable)
    assert not bridge.library_stale(orderable)
    order_check.order_check(orderable, recheck=True)
    assert not bridge.library_stale(orderable)                                  # supply-log is newer again, the manifest follows
    store.add_supply(orderable, "R1", "LCSC", 800, 0.01, "0603WAF1002T5E", source="LCSC C999", code="C999", exact=True)
    assert not partlib.restamp_if_same(orderable) and bridge.library_stale(orderable)     # another code: a design change


def test_the_order_check_action_returns_a_short_summary(orderable):
    applied, _, refused = serve.apply_actions(orderable, [{"type": "order.check"}])
    assert refused == [] and applied[0].startswith("order.check: ") and "swap_free" in applied[0]


# ---------------------------------------------------------------- review: function, a current library, who may set a lock

def test_same_pads_but_another_pin_function_is_different(built):
    f = fixture_fetch(CANDIDATES)
    own = partlib.footprint_match(built, "U1", "C201", fetcher=f)
    assert own["match"] == "same", own
    swapped = partlib.footprint_match(built, "U1", "C202", fetcher=f)                 # pin 3 is VOUT on the line, EN on the candidate
    assert swapped["match"] == "different" and "pin 3" in swapped["why"] and "VOUT" in swapped["why"] and "EN" in swapped["why"]


def test_a_generated_ic_footprint_needs_the_candidates_symbol_too(built):
    f = fixture_fetch(CANDIDATES)
    q1 = partlib.footprint_match(built, "Q1", "C201", package="SOT-23-3", fetcher=f)     # Q1 is a generated SOT-23-3 with G, S, D
    assert q1["match"] == "different" and "pin" in q1["why"]                           # VIN/GND/VOUT are not G/S/D
    gone = lambda cid, dest: (False, "EasyEDA answered: part not found")
    assert partlib.footprint_match(built, "Q1", "C555", package="SOT-23-3", fetcher=gone)["match"] == "unknown"


def test_a_two_pin_passive_is_compared_by_value_and_kind_not_pin_names(built):
    f = fixture_fetch(CANDIDATES)
    m = lambda **cand: partlib.footprint_match(built, "R1", "C101", fetcher=f, cand=cand)["match"]
    assert m(description="10 kΩ ±1% 100mW resistor") == "same" and m(description="10K 1% 0.1W Resistor") == "same" and m(description="10000R 1% 1/8W resistor") == "same"
    assert m(description="100kΩ 1% 100mW resistor") == "different"
    assert m(description="10kΩ 1% 100mW NTC thermistor") == "different"                     # a thermistor is not a resistor
    assert m(description="10kΩ +/-1% 100mW") == "unknown"                                # it does not say what it is
    assert m(description="0603 Chip Resistor") == "unknown"                             # no value to compare
    v = partlib_match.value
    assert v("C", "100nF") == pytest.approx(v("C", "0.1uF")) and v("C", "100n") == v("C", "100nF")
    assert v("R", "4K7") == pytest.approx(4700) and v("L", "10µH") == pytest.approx(1e-5)
    assert v("R", "10kΩ 100mW") == 10000 and v("R", "0603 Chip Resistor") is None


def test_a_polar_two_pin_part_is_compared_by_pin_names(built):
    f = fixture_fetch(CANDIDATES)
    d1 = partlib.footprint_match(built, "D1", "C101", package="SOD-123", fetcher=f)       # the BAT54 diode: its own pin names, the candidate has 1/2
    assert d1["match"] in ("different", "same") and ("pin" in d1["why"] or d1["match"] == "same")
    names = {p["name"] for p in partlib.footprint_of(built, "D1")["symbol_pins"]}
    assert (d1["match"] == "same") == (names == {"1", "2"})


def test_a_library_that_is_not_current_proves_nothing(built):
    f = fixture_fetch(CANDIDATES)
    assert partlib.footprint_match(built, "R1", "C101", fetcher=f)["match"] == "same"
    log(built, "bom-log.jsonl", {"ts": "2026-10-21T12:00:00", "by": "t", "line": "R1", "changes": {"package": "0805"}})
    m = partlib.footprint_match(built, "R1", "C101", fetcher=f)
    assert m["match"] == "unknown" and m["why"] == partlib.NOT_CURRENT


@pytest.mark.parametrize("what, change", [("package", {"package": "0805"}), ("value", {"value": "22k"})])
def test_a_lock_is_not_honoured_over_a_changed_package_or_value(built, what, change):
    log(built, "bom-log.jsonl", {"ts": "2026-10-21T12:00:00", "by": "t", "line": "R1", "changes": swap(built, **change)})
    calls = []
    m = prep(built, fetcher=fake_fetch(calls))
    assert "C101" in calls and any("not kept" in i and what in i for i in m["R1"]["issues"]) and "locked" not in m["R1"]


def test_a_lock_is_not_honoured_when_the_converter_changed(built):
    (store.pdir(built) / "library" / "converter.txt").write_text("0123456789ab" + chr(10), encoding="utf-8")      # built by other converter code
    log(built, "bom-log.jsonl", {"ts": "2026-10-21T12:00:00", "by": "t", "line": "R1", "changes": swap(built)})
    m = prep(built, fetcher=fake_fetch([]))
    assert any("not kept" in i and "converter" in i for i in m["R1"]["issues"]) and "locked" not in m["R1"]


def test_a_lock_is_proven_again_when_the_swap_is_approved(built, monkeypatch):
    monkeypatch.setattr(partlib, "fetch_one", fixture_fetch(CANDIDATES))
    rec = store.propose_bom(built, "R1", swap(built))
    assert rec["changes"]["footprint_lock"] == "R0603_FAKE"
    log(built, "bom-log.jsonl", {"ts": "2026-10-21T12:00:00", "by": "t", "line": "R2", "changes": {"value": "5.6k"}})   # the BOM moved on
    store.decide(built, rec["id"], "approved")
    line = next(l for l in store.bom_lines(built) if l["key"] == "R1")
    assert line["mpn"] == "NEW-RES" and "footprint_lock" not in line                   # approved as a design change
    assert bridge.library_stale(built)


def test_the_lock_cannot_be_edited_in_or_ride_on_other_changes(built, monkeypatch):
    monkeypatch.setattr(partlib, "fetch_one", fixture_fetch(CANDIDATES))
    with pytest.raises(ValueError):
        store.edit_bom(built, "R1", "footprint_lock", "R0603_FAKE")
    rec = store.propose_bom(built, "R1", swap(built, value="22k"))                     # a swap that also changes the value
    assert "footprint_lock" not in rec["changes"] and "value" in rec["lock_note"]
    rec = store.propose_bom(built, "R1", swap(built, package="0805"))
    assert "footprint_lock" not in rec["changes"]
    ok = store.propose_bom(built, "R1", swap(built))
    assert ok["changes"]["footprint_lock"] and "lock_note" not in ok
    bad = store.propose_bom(built, "R1", swap(built, lcsc="C200"))
    assert "footprint_lock" not in bad["changes"] and "different" in bad["lock_note"]


def test_a_swap_leaves_the_altium_parameters_old_and_says_so(built, monkeypatch):
    monkeypatch.setattr(partlib, "fetch_one", fixture_fetch(CANDIDATES))
    rec = store.propose_bom(built, "R1", swap(built))
    store.decide(built, rec["id"], "approved")
    assert not bridge.library_stale(built)
    stale = partlib.params_stale(built)["R1"]
    assert stale == {"mpn": "0603WAF1002T5E", "lcsc": "C100"}
    note = partlib.params_notices(built)[0]
    assert "R1" in note and "0603WAF1002T5E" in note and "C100" in note and "export_bom" in note
    assert note in order_check.order_check(built)["params_stale"]
    assert "still show" in partlib.format_status(partlib.status_rows(built))
    m = prep(built, fetcher=fake_fetch([]))                                              # a rebuild keeps the note until Altium is built
    assert m["R1"]["params_stale"] == stale
    partlib.clear_params_stale(built)
    assert partlib.params_stale(built) == {}


def test_the_jlc_export_never_takes_a_code_that_is_not_the_exact_part(proj):
    key, mpn = "R2", "RC0603-4K7"
    log(proj, "supply-log.jsonl", {"line": key, "mpn": mpn, "supplier": "LCSC", "source": "LCSC C777", "exact": False})
    log(proj, "supply-log.jsonl", {"line": key, "mpn": mpn, "supplier": "LCSC", "source": "LCSC C888", "code_mismatch": "another part"})
    assert export_bom.lcsc_code(proj, key, {"mpn": mpn}) == ""
    log(proj, "supply-log.jsonl", {"line": key, "mpn": mpn, "supplier": "LCSC", "source": "LCSC C999", "exact": True})
    assert export_bom.lcsc_code(proj, key, {"mpn": mpn}) == "C999"


def test_the_restamp_only_follows_supplier_answers(orderable):
    assert partlib.restamp_if_same(orderable)                                           # only the supply log is newer
    assert not bridge.library_stale(orderable)
    back(orderable)
    log(orderable, "bom-log.jsonl", {"ts": "2026-10-21T12:00:00", "by": "t", "line": "R2", "changes": {"value": "5.6k"}})
    stock(orderable, "R2", "RC0603-4K7", 1)
    assert not partlib.restamp_if_same(orderable) and bridge.library_stale(orderable)  # a BOM change is a design change


def test_the_order_check_goes_by_lcsc_stock(orderable, monkeypatch):
    store.add_supply(orderable, "R1", "Mouser", 50000, 0.02, "0603WAF1002T5E")           # Mouser has plenty, JLC has none
    stock(orderable, "R2", "RC0603-4K7", 30, code="C1")                                 # JLC: enough for the build (5), under 10 builds
    stock(orderable, "U1", "LDO33", 60, code="C200")                                    # JLC: plenty
    asked = []
    monkeypatch.setattr(jlc, "alternatives", lambda line, n=5, transport=None: asked.append(line["key"]) or [])
    by = {l["line"]: l for l in order_check.order_check(orderable)["lines"]}
    assert by["R1"]["class"] == "no_alternative" and by["R1"]["stock"] == 0
    assert by["R2"]["class"] == "ok" and by["R2"]["warnings"] == ["low stock"] and by["U1"]["warnings"] == []
    assert "R2" not in asked and "U1" not in asked and "R1" in asked


def test_a_supply_answer_matches_the_code_in_any_case(proj):
    store.add_supply(proj, "R2", "LCSC", 900, 0.01, "RC0603-4K7", source="LCSC C1", declared=" c1 ")
    store.edit_bom(proj, "R2", "lcsc", "C1")
    assert next(l for l in store.bom(proj, write=False) if l["key"] == "R2")["supply"]["LCSC"]["stock"] == 900


def test_recheck_flag_parsing_and_the_endpoints(orderable, monkeypatch, server_url):
    import check_availability
    checked = []
    monkeypatch.setattr(check_availability, "check", lambda project, keys=None: checked.append(project) or [])
    assert [serve._truthy(v) for v in (True, "true", "1", 1, "yes", False, "false", "0", "", None)] == [True] * 5 + [False] * 5
    serve.apply_actions(orderable, [{"type": "order.check", "recheck": "false"}])
    assert checked == []                                                                # "false" is not true
    serve.apply_actions(orderable, [{"type": "order.check", "recheck": True}])
    assert checked == [orderable]
    status, body = tget(server_url, "/api/order/check?recheck=1", orderable)
    assert status == 200 and "lines" in body and checked == [orderable]               # a GET never asks the suppliers
    status, body = tpost(server_url, "/api/order/check", {"recheck": True}, orderable)
    assert status == 200 and "lines" in body and checked == [orderable, orderable]
    status, body = tpost(server_url, "/api/order/check", {"recheck": "false"}, orderable)
    assert status == 200 and len(checked) == 2


def test_the_propose_endpoint_says_whether_the_footprint_was_kept(orderable, monkeypatch, server_url):
    monkeypatch.setattr(partlib, "fetch_one", fixture_fetch(CANDIDATES))
    status, body = tpost(server_url, "/api/bom/propose", {"line": "R1", "changes": swap(orderable), "reason": "order-only swap: same footprint"}, orderable)
    assert status == 200 and body["proposed"]["footprint_lock"] == "R0603_FAKE" and body["proposed"]["lock_note"] == ""
    status, body = tpost(server_url, "/api/bom/propose", {"line": "R1", "changes": swap(orderable, lcsc="C102")}, orderable)
    assert body["proposed"]["footprint_lock"] == "" and body["proposed"]["lock_note"]
    status, body = tpost(server_url, "/api/bom/edit", {"line": "R1", "field": "footprint_lock", "value": "R0603_FAKE"}, orderable)
    assert status == 400


# ---------------------------------------------------------------- ratings of plain passives

def test_ratings_are_read_from_text():
    r = partlib_match.rating
    assert r("volts", "100nF 50V X7R") == 50 and r("volts", "100nF 6.3V") == 6.3 and r("volts", "0603") is None
    assert r("watts", "10k 0.25W") == 0.25 and r("watts", "1/10W") == pytest.approx(0.1) and r("watts", "100mW") == pytest.approx(0.1)
    assert r("amps", "10uH 500mA") == pytest.approx(0.5) and r("amps", "2A") == 2
    assert r("tol", "±1% 0603") == 1 and r("tol", "no tolerance") is None
    assert r("diel", "X7R") == "X7R" and r("diel", "NP0") == r("diel", "C0G") == "C0G" and r("diel", "CL10B104") is None


@pytest.mark.parametrize("prefix, line, cand, verdict", [
    ("C", "100nF 50V", "100nF 6.3V", "different"), ("C", "100nF 50V", "100nF 50V", None), ("C", "100nF 50V", "100nF 100V", None),
    ("C", "100nF 50V", "100nF X7R", "unknown"), ("C", "100nF", "100nF 6.3V", None),                  # the line states no voltage
    ("R", "10k 0.25W", "10k 0.063W", "different"), ("R", "10k 0.1W", "10k 1/4W", None), ("R", "10k 0.1W", "10k", "unknown"),
    ("L", "10uH 1A", "10uH 500mA", "different"), ("L", "10uH 1A", "10uH 2A", None), ("L", "10uH 1A", "10uH", "unknown"),
    ("R", "10k 1%", "10k 5%", "different"), ("R", "10k 5%", "10k 1%", None), ("R", "10k 1%", "10k", "unknown"),
    ("C", "100nF X7R", "100nF X5R", "different"), ("C", "100nF NP0", "100nF C0G", None), ("C", "100nF X7R", "100nF", "unknown"),
    ("C", "100nF", "100nF X5R", None),
    ("L", "10uH 1A", "10uH Isat 2A Irms 800mA", "different"), ("L", "10uH 1A", "10uH Isat 1.5A Irms 1.2A", None)])  # the worst current
def test_a_candidate_must_be_as_good_on_every_rating_the_line_states(prefix, line, cand, verdict):
    assert partlib_match.ratings_check(prefix, line, cand, "C1")[0] == verdict


def test_footprint_match_applies_the_ratings(built, monkeypatch):
    f = fixture_fetch(CANDIDATES)
    real = store.bom_lines
    monkeypatch.setattr(partlib.store, "bom_lines", lambda p, *a, **k: [{**l, "description": "10kΩ ±1% 0.1W resistor"} if l["key"] == "R1" else l for l in real(p, *a, **k)])
    m = lambda desc: partlib.footprint_match(built, "R1", "C101", fetcher=f, cand={"description": desc})["match"]
    assert m("10kΩ ±1% 0.1W resistor") == "same" and m("10kΩ ±1% 0.25W resistor") == "same"
    assert m("10kΩ ±1% 0.063W resistor") == "different" and m("10kΩ ±5% 0.1W resistor") == "different"
    assert m("10kΩ resistor") == "unknown"                                          # says nothing of the rating
