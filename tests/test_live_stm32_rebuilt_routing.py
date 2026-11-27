"""The Live-STM32 test board as layout.py placed it after the part library was rebuilt (tests/fixtures/live_stm32_rebuilt.json, frozen by
scripts/freeze_live_board.py; synthetic, no student data): the same 26 parts, placed differently. The router left USB_DM open here: the
rip-up rounds took up every net a way crossed at once (up to 8) and laid them again, and the greedy search closed other nets' ways in turn
(a different net open in every plan). Now the least disturbance is tried first (one, then two blocking nets taken up), so the board
routes 18/18 (in the second plan: the first plan is unchanged, the graded pass runs in the plans after it)."""
import time

import live_stm32_placed as placed
from altium import route

CPU_BUDGET_S = 600.0      # a hang guard, not a speed test (measured about 30-40 s): the routing is segmented like the server's, and the result is asserted


def _plan(pour):
    doc, box, rules = placed.load("live_stm32_rebuilt")
    t0 = time.process_time()
    res = route.plan_routes(doc, box, rules, pitch=0.1, seconds=route.SEGMENT_S, max_seconds=route.SECONDS_MAX, pour_net=pour)
    return doc, box, rules, res, time.process_time() - t0


def test_the_fixture_is_the_board_route_on_plans():
    doc, box, rules = placed.load("live_stm32_rebuilt")
    assert box == [0.0, 0.0, 45.009, 40.005] and abs(rules["clearance"] - 0.1524) < 1e-6
    assert len(doc["nets"]) == 18 and doc["vias"] == []
    assert all(t["in_component"] for k in ("tracks", "arcs") for t in doc[k])


def test_the_rebuilt_live_board_routes_all_18_nets_with_no_violation():
    pour = "GND"          # as bridge.route_on plans it; the ground by tracks on two layers (no pour) is not asked of this tight placement
    doc, box, rules, res, cpu = _plan(pour)
    print(f"\npour {pour}: {len(res['routed'])}/18, plans {res['stats']['attempts']}, cpu {cpu:.1f}s, pour {res['pour']}")
    assert res["failed"] == [], res["failed"]
    assert len(res["routed"]) == 18
    assert route.violations(doc, res["items"], rules, box) == []
    assert cpu < CPU_BUDGET_S
    assert res["pour"]["net"] == "GND" and res["pour"]["mode"] in ("drops", "tracks")
