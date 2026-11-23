"""Review round after Wave 2 (23/11): constraint validation never raises TypeError / accepts NaN, one action's exception does not lose the turn,
keep-out footprint names are unique, pin gaps compare per ref across sheets, diode fingerprints include the nets."""
import json

import constraints
import partlib
import partlib_generate as gen
import pin_decisions
import pytest
import serve
import store
from test_unverified_pins import _add, _jd_sheet


@pytest.mark.parametrize("item", [
    {"kind": "mounting_hole", "points_mm": [[None, 2]]},
    {"kind": "mounting_hole", "points_mm": [[float("nan"), 2]]},
    {"kind": "mounting_hole", "points_mm": [["1", {}]]},
    {"kind": "keepout", "rect_mm": [None, 0, 5, 5]},
    {"kind": "keepout", "rect_mm": [float("nan"), 0, 5, 5]},
    {"kind": "keepout", "rect_mm": [0, 0, float("inf"), 5]},
    {"kind": "keepout", "edge": ["left"], "depth_mm": 3},
    {"kind": "keepout", "rect_mm": None, "edge": None},
    {"kind": "edge", "target": ["U1"], "side": ["left"]},
    {"kind": "attr", "target": "U1", "attr": ["heat_source"]},
    {"kind": "keep_apart", "a": None, "b": "U2"},
    {"kind": ["edge"]},
    {"kind": "mounting_hole", "diameter_mm": None},
])
def test_validate_item_raises_only_valueerror(item):
    with pytest.raises(ValueError):
        constraints.validate_item(item)
    with pytest.raises(ValueError):
        constraints.validate({"items": [item]})


def test_one_bad_action_does_not_lose_the_rest_of_the_turn(empty, monkeypatch):
    def boom(*a, **k):
        raise TypeError("'NoneType' object is not subscriptable")
    monkeypatch.setattr(store, "propose_idea", boom)
    applied, _, refused = serve._apply_actions(empty, [{"type": "idea.propose", "topic": "t", "text": "x"},
                                                       {"type": "idea.describe", "text": "a goal"}], last_user="hi")
    assert applied == ["idea.describe"]
    assert len(refused) == 1 and refused[0].startswith("idea.propose: could not be applied (TypeError") and "other actions" in refused[0]


def test_keepout_footprint_names_do_not_collide_on_long_ids():
    a, b = "keepout-antenna-left-side-1", "keepout-antenna-left-side-2"
    assert a[:20] == b[:20] and gen.keepout_name(a) != gen.keepout_name(b)
    assert gen.keepout_name("a.b") != gen.keepout_name("a_b")
    assert gen.keepout_name(a) == gen.keepout_name(a) and gen.is_mech_footprint(gen.keepout_name(a))


def test_unlisted_pins_are_compared_per_ref_across_sheets(empty):
    _add(empty, "U1", "ABCD1234")
    lib = partlib.library_dir(empty)
    (lib / "build").mkdir(parents=True, exist_ok=True)
    (lib / "manifest.json").write_text(json.dumps({"U1": {"symbol": "SYM_U1", "mpn": "ABCD1234"}}), encoding="utf-8")
    pin = "PIN|{n}|{name}|eElectricPassive|0|0|0|0|10"
    (lib / "build" / "symbols_spec.txt").write_text("SYMBOL|SYM_U1\n" + "\n".join(pin.format(n=n, name=f"P{n}") for n in "123") + "\n", encoding="cp1252")

    def part(*pins):
        return {"ref": "U1", "section": "A", "pins": [{"num": n, "name": f"P{n}", "net": "N" + n} for n in pins]}
    for sh, pins in (("01", "12"), ("02", "3")):         # one part drawn on two sheets: pins 1+2 on the first, pin 3 on the second
        assert store.write_sheet(empty, sh, {"sections": [{"id": "A", "title": "T"}], "parts": [part(*pins)]})["ok"]
    assert store.pin_gaps(empty)["unlisted"] == []
    assert store.write_sheet(empty, "02", {"sections": [{"id": "A", "title": "T"}], "parts": [part("2")]})["ok"]
    assert [(g["ref"], g["num"]) for g in store.pin_gaps(empty)["unlisted"]] == [("U1", "3")]      # once, not once per sheet


def test_diode_fingerprint_follows_the_nets_and_nc_spellings_do_not_matter(empty):
    _jd_sheet(empty, ("1", "2"))                                   # a diode whose pins are only numbered
    pin_decisions.accept_all(empty)
    assert store.unverified_parts(empty) == []
    sheet = store.load_sheet(empty, "01")
    d1 = next(p for p in sheet["parts"] if p["ref"] == "D1")
    d1["pins"][0]["net"], d1["pins"][1]["net"] = d1["pins"][1]["net"], d1["pins"][0]["net"]      # anode and cathode nets swapped
    assert store.write_sheet(empty, "01", sheet)["ok"]
    assert [u["line"] for u in store.unverified_parts(empty)] == ["D1"]
    j1_before = pin_decisions.fingerprint(empty, "J1")
    sheet = store.load_sheet(empty, "01")
    next(p for p in sheet["parts"] if p["ref"] == "J1")["pins"].append({"num": "3", "name": "SH", "net": "N/C"})
    assert store.write_sheet(empty, "01", sheet)["ok"]
    assert pin_decisions.fingerprint(empty, "J1") == j1_before      # N/C is NC like "NC"


def test_one_model_build_computes_pin_gaps_and_the_derived_bom_once(empty, monkeypatch):
    import model
    _jd_sheet(empty)
    calls = {"gaps": 0, "bom": 0}
    real_gaps, real_bom = store._pin_gaps, store._bom
    monkeypatch.setattr(store, "_pin_gaps", lambda p: calls.__setitem__("gaps", calls["gaps"] + 1) or real_gaps(p))
    monkeypatch.setattr(store, "_bom", lambda p, w: calls.__setitem__("bom", calls["bom"] + (0 if w else 1)) or real_bom(p, w))
    m = model.build(empty)
    assert m["stages"] and calls["gaps"] == 1 and calls["bom"] == 1
    model.build(empty)
    assert calls["gaps"] == 2 and calls["bom"] == 2                       # a new build computes again: nothing outlives it


def test_a_write_inside_a_build_scope_drops_the_memo(empty):
    _jd_sheet(empty)
    with store.build_scope():
        before = store.pin_gaps(empty)
        sheet = store.load_sheet(empty, "01")
        next(p for p in sheet["parts"] if p["ref"] == "J1")["pins"].append({"num": "3", "name": "SH", "net": ""})
        assert store.write_sheet(empty, "01", sheet)["ok"]
        after = store.pin_gaps(empty)
    assert len(after["open"]) == len(before["open"]) + 1


def test_the_readiness_rev_ignores_conversation_and_usage_logs(empty):
    import stages
    r0 = stages.rev(empty)
    store.append(empty, "usage-log.jsonl", {"ts": 1})
    store.append(empty, "threads.jsonl", {"ts": 1})
    assert stages.rev(empty) == r0
    store.append(empty, "bom-log.jsonl", {"ts": 1})
    assert stages.rev(empty) != r0
