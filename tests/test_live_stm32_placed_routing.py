"""The Live-STM32 test board as layout.py placed it in Altium (tests/fixtures/live_stm32_placed.json, frozen by scripts/freeze_live_board.py;
synthetic, no student data): 26 parts, 45 x 40 mm, the rules the doc holds (clearance 0.1524 mm). The router left one net open here
(with the pour model: +5V; without: GND) while the 0.2 mm fixture of the same design routed 18/18. Cause: a fine pitch pin's way out was closed by
the fan-out of its neighbours, because the ground (a pin in the middle of each side of the IC) was laid last. The ground (the poured net, or a
ground routed by tracks) is now laid after the rails and before the signals, with the tight keep-off, in the first plan."""
import time

import pytest

import live_stm32_placed as placed
from altium import route

CPU_BUDGET_S = 75.0       # was 64 s without the pour model before the ground went early; 120 s wall is the server deadline


def _plan(pour):
    doc, box, rules = placed.load()
    t0 = time.process_time()
    res = route.plan_routes(doc, box, rules, pitch=0.1, seconds=120, pour_net=pour)
    return doc, box, rules, res, time.process_time() - t0


def test_the_fixture_is_the_board_route_on_plans():
    doc, box, rules = placed.load()
    assert box == [0.0, 0.0, 45.009, 40.005] and abs(rules["clearance"] - 0.1524) < 1e-6
    assert len(doc["pads"]) == 124 and len(doc["nets"]) == 18 and doc["vias"] == []
    assert all(t["in_component"] for k in ("tracks", "arcs") for t in doc[k])


@pytest.mark.parametrize("pour", [None, "GND"])
def test_the_placed_live_board_routes_all_18_nets_with_no_violation(pour):
    doc, box, rules, res, cpu = _plan(pour)
    print(f"\npour {pour}: {len(res['routed'])}/18, plans {res['stats']['attempts']}, cpu {cpu:.1f}s, pour {res['pour']}")
    assert res["failed"] == [], res["failed"]
    assert len(res["routed"]) == 18
    assert route.violations(doc, res["items"], rules, box) == []
    assert cpu < CPU_BUDGET_S
    if pour:
        assert res["pour"]["net"] == "GND" and res["pour"]["mode"] in ("drops", "tracks")
