"""Routing of the live 26-part STM32F103 board (tests/live_stm32_fixture.py, 45 x 40 mm, USB-C connector, LQFP-48 at 0.5 mm pitch), placed by
layout.py and routed by route.py with the ground poured on the bottom layer (pour_net="GND"), as a live run does.

It routed 16/18 nets: USB_DM at the USB-C pad J1-A7 and GND at U1-35 (before the last placement fix: +3V3 and NRST, "pad U1-7 is too close to
other copper"). Causes found: (1) the grid search kept 0.08 + 0.07 mm further off every obstacle than the rules ask, which closed the fan-out of
a 0.5 mm pitch IC at 0.2 mm clearance (fine pitch pads whose only way out was a 0.4 mm channel); (2) a ground pad whose stub and via fitted by
exact geometry was given up because the grid said no; (3) the search is greedy, and one net's track closed a pad's way out for ever, because
the nets that failed were never laid first. The numbers below are measured, not hoped for: the checks use the exact geometry of the tool's own
violations() and the router's own result. The CPU of a plan is printed (pytest -s)."""
import random
import time

import pytest

import live_stm32_fixture as fx
import test_live_stm32_placement as placed
from altium import layout, route

POUR_NET = "GND"
CLEARANCES = (0.127, 0.2)            # mm: the JLC minimum, and 8 mil (what the live run's messages match)
JITTER_MM = 0.25
JITTER_REFS = 4                      # passives moved per run
JITTER_SEEDS = (11, 23, 37)


def _rules(doc, clearance, amps=None):
    r = dict(route.rules_from_doc(doc), clearance=clearance)
    if amps:
        r["net_current"] = {"+3V3": amps}
    return r


def _board(jitter=None):
    """The placed live board (doc dict); jitter = (seed): a few passives moved by up to JITTER_MM in x and y, as a different placement
    would, kept only where the parts still do not overlap (layout.verify_layout)."""
    plan = layout.plan_placement(fx.PARTS, fx.FPS, fx.OUTLINE, clearance_mm=0.0, edge_copper_mm=fx.EDGE_COPPER_MM)
    if jitter is not None:
        rnd = random.Random(jitter)
        refs = sorted(p["ref"] for p in plan["places"] if p["ref"][0] in "CR")
        moved = rnd.sample(refs, JITTER_REFS)
        for pl in plan["places"]:
            if pl["ref"] in moved:
                old = (pl["x"], pl["y"])
                for f in (1.0, 0.5, 0.25, 0.0):
                    pl["x"], pl["y"] = round(old[0] + f * rnd.uniform(-JITTER_MM, JITTER_MM), 3), round(old[1] + f * rnd.uniform(-JITTER_MM, JITTER_MM), 3)
                    if f == 0.0 or not layout.verify_layout(placed._doc(plan), fx.PARTS, fx.OUTLINE, footprints=fx.FPS):
                        break
    return placed._doc(plan)


def _route(doc, clearance, amps=None, pour=POUR_NET):
    rules = _rules(doc, clearance, amps)
    t0 = time.process_time()
    res = route.plan_routes(doc, fx.OUTLINE, rules, seconds=route.SEGMENT_S, max_seconds=route.SECONDS_MAX, pour_net=pour)
    return res, rules, time.process_time() - t0


def _report(tag, res, cpu):
    print(f"\n{tag}: {len(res['routed'])}/{len(res['routed']) + len(res['failed'])} nets, plans {res['stats']['attempts']}, cpu {cpu:.1f}s, "
          f"pour {res['pour']}, failed {[(n, w[:90]) for n, w in res['failed']]}")


@pytest.mark.parametrize("clearance", CLEARANCES)
def test_live_board_routes_all_18_nets_with_the_ground_pour(clearance):
    doc = _board()
    res, rules, cpu = _route(doc, clearance)
    _report(f"clearance {clearance}", res, cpu)
    assert res["failed"] == [], res["failed"]
    assert len(res["routed"]) == 18
    assert route.violations(doc, res["items"], rules, fx.OUTLINE) == []        # the exact geometry, not the grid the router searched on
    assert res["pour"]["net"] == POUR_NET and res["pour"]["mode"] in ("drops", "tracks")


def test_live_board_with_a_rail_current_routes_all_18_nets():
    """The +3V3 rail with a current set (1.5 A: 0.5 mm wide) as the student can: more copper round the MCU."""
    doc = _board()
    res, rules, cpu = _route(doc, 0.2, amps=1.5)
    _report("clearance 0.2, +3V3 1.5 A", res, cpu)
    assert res["failed"] == [], res["failed"]
    assert route.violations(doc, res["items"], rules, fx.OUTLINE) == []


def test_live_board_without_the_pour_model_routes_all_18_nets():
    """bridge.route_on calls plan_routes(doc, box, rules, pitch=, seconds=) with no pour_net (the pour is drawn after the tracks): the
    ground is then routed by tracks, and that is what a live run gets."""
    doc = _board()
    res, rules, cpu = _route(doc, 0.2, pour=None)
    _report("clearance 0.2, no pour model", res, cpu)
    assert res["failed"] == [], res["failed"]
    assert route.violations(doc, res["items"], rules, fx.OUTLINE) == []


def test_routing_is_the_same_every_time():
    doc = _board()
    a, _, _ = _route(doc, 0.2)
    b, _, _ = _route(doc, 0.2)
    assert a["items"] == b["items"] and a["failed"] == b["failed"]


@pytest.mark.parametrize("seed", JITTER_SEEDS)
def test_small_placement_changes_keep_at_least_17_of_18(seed):
    """A 0.25 mm shift of a few passives used to change which nets fail: the router may not depend on the luck of a placement. At least 17
    of 18 every time, 0 violations, and the net that is left open (if any) is named with a reason."""
    doc = _board(jitter=seed)
    res, rules, cpu = _route(doc, 0.2)
    _report(f"jitter seed {seed}", res, cpu)
    assert len(res["routed"]) >= 17, res["failed"]
    assert route.violations(doc, res["items"], rules, fx.OUTLINE) == []
    for net, why in res["failed"]:
        assert why and len(why) > 10
