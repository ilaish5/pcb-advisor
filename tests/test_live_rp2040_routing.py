"""The Live-RP2040 test board (37 parts, 40 x 30 mm, two layers, an RP2040 in a 0.4 mm pitch QFN-56 and a USB-C connector) as
layout.py placed it in Altium, frozen by scripts/freeze_live_board.py (tests/fixtures/live_rp2040_placed.json; synthetic, no student
data; placement only: the tracks and vias of the partial route are not in it).

Known gap: the router routes 24 of 27 nets and leaves +3V3, +1V1 and +5V open (as in the live run). The track width is NOT the cause:
each rail routes alone at its 0.3 mm in under a second, and the three together too. The cause is pin access at the QFN: its rows
interleave power and signal pins (43..50: ADC_AVDD, VREG_IN, VREG_VOUT, USB_DM, USB_DP, USB_VDD, IOVDD, DVDD), so whichever nets are
laid first run along the rows and shut the pins behind them in; the rip-up rounds trade one open net for another. Tried and dropped
(no gain, slower): a cost on the cells in front of other nets' fine pitch pads (1.0 to 2.5 mm deep, also prohibitive), and other
orders of rails / ground / signals. The full route is kept here as a strict xfail so that a router change that closes it shows."""
import time

import pytest

import live_stm32_placed as placed
from altium import route

RAILS = ("+3V3", "+1V1", "+5V")


def test_the_fixture_is_the_placed_board():
    doc, box, rules = placed.load("live_rp2040_placed")
    assert box == [0.0, 0.0, 40.0, 30.0] and abs(rules["clearance"] - 0.1524) < 1e-6
    assert len(doc["nets"]) == 27 and doc["vias"] == [] and len({p["ref"] for p in doc["pads"]}) == 37
    assert all(t["in_component"] for k in ("tracks", "arcs") for t in doc[k])


def test_the_rails_route_at_their_width_when_alone():
    """Not a width problem: on the placed board, without the signals, every rail is drawn at the 0.3 mm rail default."""
    doc, box, rules = placed.load("live_rp2040_placed")
    for net in RAILS:
        res = route.plan_routes(doc, box, rules, pitch=0.1, seconds=120, only={net})
        assert res["failed"] == [] and res["widths"][net]["width_mm"] == pytest.approx(0.3), (net, res["failed"])
        assert route.violations(doc, res["items"], rules, box) == []


@pytest.mark.slow
@pytest.mark.xfail(strict=True, reason="known gap: +3V3, +1V1, +5V are shut in at the QFN by the greedy order (see the module doc)")
def test_the_rp2040_board_routes_every_net_with_no_violation():
    doc, box, rules = placed.load("live_rp2040_placed")
    t0 = time.process_time()
    res = route.plan_routes(doc, box, rules, pitch=0.1, seconds=120, pour_net=route.pour_net_for(doc))
    print(f"\nRP2040: {len(res['routed'])}/27, plans {res['stats']['attempts']}, cpu {time.process_time() - t0:.1f}s, failed {res['failed']}")
    assert route.violations(doc, res["items"], rules, box) == []       # what is drawn is always clean
    assert res["failed"] == [], res["failed"]
