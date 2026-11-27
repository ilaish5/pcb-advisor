"""Spec phase 3/4 target, offline and generic: an STM32 board of 60 parts on 2 layers, 50 x 40 mm, placed by layout.py and routed by
route.py with no Altium. The board comes from tests/stm32_board_fixture.py. The checks are honest: what the tool cannot do yet is
asserted as what it reports (a warning, a failed net with a reason), never loosened to pass; the numbers are printed (pytest -s)."""
import math
import time

import pytest

import stm32_board_fixture as fx
from altium import layout, route

# What the tests check is the RESULT (every net routed or named, no violation, nothing lost), never the speed of the machine: a slow CI
# runner must not fail a correct board (it did at 80 s, with all 45 nets routed and 0 violations). Routing has a 120 s segment that is
# renewed while nets are still closing (route.Clock), so the time cap is not what decides the result. The speed guard is the number of
# cells the searches expanded (deterministic, the same on every machine): a regression of the search shows there, a slow runner does not.
# Placement: its time is printed; PLACE_HANG_S (several times the measured 5-20 s) only catches a hang.
PLACE_HANG_S = 120.0
ROUTE_SECONDS = route.SEGMENT_S            # one segment (120 s) ...
ROUTE_MAX_SECONDS = route.SECONDS_MAX      # ... renewed while nets are still closing, as route_on does
MAX_EXPANSIONS = 6_000_000                 # measured 1.3 to 1.8 million on 2026-11-27; a search more than three times as costly is a regression
RULES = dict(clearance=0.127, width=0.127, width_min=0.127, width_max=10, via_dia=0.6, via_hole=0.3, edge=0.3)
POUR_NET = "GND"                         # the ground net is poured on the bottom layer: its pads are dropped to the pour by vias
RAIL_AMPS = 1.5                           # a current set by the student on +3V3: IPC-2221 wants about 0.5 mm, more than the 0.127 default


@pytest.fixture(scope="module")
def board():
    parts = fx.build_parts()
    t0 = time.process_time()
    plan = layout.plan_placement(parts, fx.FPS, fx.OUTLINE)
    place_s = time.process_time() - t0
    doc = fx.doc_from_plan(parts, plan)
    rules = dict(route.rules_from_doc({}), **RULES, net_current={"+3V3": RAIL_AMPS})
    t0 = time.process_time()
    res = route.plan_routes(doc, fx.OUTLINE, rules, seconds=ROUTE_SECONDS, max_seconds=ROUTE_MAX_SECONDS, pour_net=POUR_NET)
    route_s = time.process_time() - t0
    return dict(parts=parts, plan=plan, doc=doc, rules=rules, res=res, place_s=place_s, route_s=route_s)


def _xy(doc, ref, pad):
    p = next(p for p in doc["pads"] if p["ref"] == ref and p["name"] == pad)
    return p["x_mm"], p["y_mm"]


def test_board_has_about_sixty_parts(board):
    assert 55 <= len(board["parts"]) <= 65 and len(board["plan"]["places"]) == len(board["parts"])


def test_placement_no_overlap_and_honest_findings(board):
    plan, doc, parts = board["plan"], board["doc"], board["parts"]
    errors = [f for f in plan["findings"] if f["level"] == "error"]
    problems = layout.verify_layout(doc, parts, fx.OUTLINE, places=plan["places"], footprints=fx.FPS)
    print(f"\nPLACEMENT cpu {board['place_s']:.1f}s (hang guard {PLACE_HANG_S:g}s), {len(plan['places'])} parts, "
          f"verify problems {len(problems)}, plan errors {len(plan['errors'])}, error findings {len(errors)}")
    for f in plan["findings"]:
        print("  ", f["level"], f["text"][:140])
    assert board["place_s"] < PLACE_HANG_S
    assert plan["errors"] == [] and problems == []                  # every part placed, 0 overlaps, inside the outline, nets as the netlist
    assert not [p for p in problems if "overlap" in p]
    # every decoupling cap is within 3 mm of its supply pin: no finding on a cap (the crystal has its own test)
    assert errors == [] and [f for f in plan["findings"] if f["ref"] != "Y1"] == [], plan["findings"]


def test_every_decap_near_its_vdd_pin_or_a_truthful_warning(board):
    parts, doc = board["parts"], board["doc"]
    warns = layout.decap_distance_warnings(doc, parts)
    pins = {}                                                           # rail -> positions of the MCU supply pins on it
    for ic in ("U1", "U2"):                                             # the MCU's supply pins and the regulator's output pins
        for q in next(p for p in parts if p["ref"] == ic)["pins"]:
            if q.get("name") in ("VDD", "VBAT", "VDDA", "VOUT"):
                pins.setdefault(q["net"], []).append(_xy(doc, ic, q["num"]))
    caps = [p for p in parts if p["ref"].startswith("C") and p["value"] == "100nF" and any(q["net"] in ("+3V3", "VDDA") for q in p["pins"])
            and p["ref"] not in ("C41",)]
    far = []
    for c in caps:
        rail = next(q for q in c["pins"] if q["net"] in ("+3V3", "VDDA"))
        d = min(math.hypot(_xy(doc, c["ref"], rail["num"])[0] - x, _xy(doc, c["ref"], rail["num"])[1] - y) for x, y in pins[rail["net"]])
        if d > layout.DECAP_NEAR_MM + layout.DECAP_TOL_MM:
            far.append((c["ref"], round(d, 1)))
            assert any(w.startswith(c["ref"] + " is ") for w in warns), f"{c['ref']} is {d:.1f} mm away and nothing says so"
    near = len(caps) - len(far)
    print(f"\nDECAPS {near} of {len(caps)} 100 nF caps within 3 mm of a VDD/VBAT/VDDA/VOUT pin; far (and warned): {far}")
    assert far == [] and near == len(caps)


def test_crystal_near_the_oscillator_pins_or_a_truthful_finding(board):
    plan, doc = board["plan"], board["doc"]
    (xt,) = plan["crystals"]
    assert xt["ref"] == "Y1" and {p["name"] for p in xt["pins"]} == {"PD0-OSC_IN", "PD1-OSC_OUT"}
    ours = {p["pin"]: _xy(doc, "U1", p["pin"]) for p in xt["pins"]}
    real = max(math.hypot(_xy(doc, "Y1", p["pad"])[0] - ours[p["pin"]][0], _xy(doc, "Y1", p["pad"])[1] - ours[p["pin"]][1]) for p in xt["pins"])
    assert abs(real - xt["max_mm"]) < 0.1                              # the plan's number is the real distance
    print(f"\nCRYSTAL Y1 {real:.1f} mm from the OSC pins (threshold {layout.XTAL_NEAR_MM:g} mm)")
    if real > layout.XTAL_NEAR_MM:                                      # farther than the threshold: a finding names the crystal, never silent
        assert any(f["ref"] == "Y1" and "close as possible" in f["text"] for f in plan["findings"])
    else:
        assert not any(f["ref"] == "Y1" for f in plan["findings"])


def test_routing_with_zero_violations_and_every_net_accounted(board):
    res, doc, rules = board["res"], board["doc"], board["rules"]
    nets = {}
    for p in doc["pads"]:
        if p["net"]:
            nets.setdefault(p["net"], set()).add((p["ref"], p["name"]))
    multi = {n for n, ps in nets.items() if len({r for r, _ in ps}) >= 2 or len(ps) >= 2}
    routed, failed = set(res["routed"]), dict(res["failed"])
    frac = len(routed) / len(multi)
    viol = route.violations(doc, res["items"], rules, fx.OUTLINE)
    print(f"\nROUTING cpu {board['route_s']:.1f}s stats {res['stats']}")
    print(f"ROUTED {len(routed)} of {len(multi)} nets = {frac:.0%}; router's own exact check: {len(viol)} violations")
    for n, why in sorted(failed.items()):
        print(f"  FAILED {n}: {why[:160]}")
    assert res["stats"]["expansions"] < MAX_EXPANSIONS, res["stats"]      # the search is not more costly than it was (cells, not seconds)
    assert res["stats"]["stopped"] == "", res["stats"]                      # never ended by a stall or the ceiling with this board
    assert viol == []                                                   # whatever was drawn is rule-clean
    assert routed | set(failed) == multi and not routed & set(failed)  # every net routed or failed, none lost
    assert all(why.strip() for why in failed.values())                 # each failure has a reason
    # measured today: 45/45 with the ground dropped to the pour (same every run: the budget is a count of cells). 45 sits on the
    # edge of MAX_RIPS (4 rounds give 44), so the floor is 44; below it is a regression of the placement or of the router
    assert len(routed) >= len(multi) - 1, (frac, failed)
    # what is drawn leaves no open gap on the nets reported as routed (the ground pour is modelled: see _with_pour)
    open_nets = {n for n, *_ in layout.unrouted(_with_pour(doc, res))}
    assert not (open_nets & routed), open_nets & routed
    # a failure says what stops it, never a bare "no path"
    for n, why in failed.items():
        assert "no way" in why or "needs" in why or "budget" in why or "time" in why, (n, why)


def _with_pour(doc, res):
    """The board as drawn, with the ground pour modelled as what it is: bottom layer copper that joins every ground via (a chain of
    bottom layer tracks from via to via; layout.unrouted does not read pours). Whether a track of another net cuts the pour is
    checked by the router itself (route._pour_cut_off) and, in real use, by pourcheck on the board read back."""
    tracks = _tracks(res)
    vias = [i for i in res["items"] if i["kind"] == "via" and i["net"] == POUR_NET]
    for a, b in zip(vias, vias[1:]):
        tracks.append({"layer": 32, "net": POUR_NET, "x1_mm": a["x"], "y1_mm": a["y"], "x2_mm": b["x"], "y2_mm": b["y"], "width_mm": 0.127})
    return dict(doc, tracks=tracks, vias=_vias(res))


def test_ground_is_dropped_to_the_pour_or_routed_by_tracks_with_a_stated_reason(board):
    res, doc = board["res"], board["doc"]
    pour = res["pour"]
    print(f"\nPOUR {pour}")
    assert pour["net"] == POUR_NET
    assert POUR_NET in res["routed"] and pour["mode"] == "drops", pour      # dropped to the pour, nothing cut off
    if POUR_NET in res["routed"]:
        assert pour["mode"] in ("drops", "tracks")
        gnd = [p for p in doc["pads"] if p["net"] == POUR_NET]
        vias = [i for i in res["items"] if i["kind"] == "via" and i["net"] == POUR_NET]
        if pour["mode"] == "drops":
            assert vias and len(vias) <= len(gnd)                      # a short via stub per pad, not a web of ground tracks
            assert not [i for i in res["items"] if i["kind"] == "track" and i["net"] == POUR_NET and i["layer"] == 32]   # nothing of its own on the bottom: that is the pour
    else:
        assert dict(res["failed"])[POUR_NET]


def test_a_net_is_never_left_unrouted_between_its_own_two_connector_pads(board):
    failed = dict(board["res"]["failed"])
    for n in ("USB_DP", "USB_DM"):
        assert n not in failed or ("J1-B7 to J1-A7" not in failed[n] and "J1-A6 to J1-B6" not in failed[n]), failed[n]


def _tracks(res):
    return [{"layer": i["layer"], "net": i["net"], "x1_mm": i["x1"], "y1_mm": i["y1"], "x2_mm": i["x2"], "y2_mm": i["y2"], "width_mm": i["width"]}
            for i in res["items"] if i["kind"] == "track"]


def _vias(res):
    return [{"net": i["net"], "x_mm": i["x"], "y_mm": i["y"], "dia_mm": i["dia"], "hole_mm": i["hole"]} for i in res["items"] if i["kind"] == "via"]


def test_usb_pair_is_coupled_or_has_a_stated_fallback(board):
    res = board["res"]
    (pr,) = res["pairs"]
    assert pr["nets"] == ["USB_DP", "USB_DM"]
    print(f"\nUSB pair coupled={pr['coupled']} note: {pr['note']}")
    if pr["coupled"]:
        assert pr["mismatch_ok"] or "guideline" in pr["note"]
    else:
        assert pr["note"].startswith("not routed as a coupled pair: ")


def test_rail_with_a_set_current_gets_its_width_or_a_neck_or_a_reason(board):
    res = board["res"]
    w = res["widths"]["+3V3"]
    assert w["current_a"] == RAIL_AMPS and w["wanted_mm"] and w["wanted_mm"] > 0.3
    print(f"\n+3V3 {RAIL_AMPS:g} A wants {w['wanted_mm']:g} mm: drawn {w['width_mm']}, necks {len(w['necks'])}, note: {w['note']}")
    if "+3V3" in res["routed"]:
        assert w["width_mm"] is not None
        assert w["width_mm"] >= w["wanted_mm"] - 1e-9 or w["necks"] or "no room" in w["note"]
        assert res["width_problems"] == [] or any("+3V3" in str(p) for p in res["width_problems"])
    else:
        assert "needs" in dict(res["failed"])["+3V3"]
