"""R2 / W21: 'pins x and y are one terminal' is claimed only from evidence (pins stacked at one location), never from a drawn line."""
import test_altium_draw_text  # noqa: F401  (puts scripts/ on the path the same way the draw tests do)
from altium import draw
from altium.lib import stacked_pins


def _zener5():
    """A 5-pin passive part (a zener/TVS array) whose graphic is a line from pin 2's base to pin 5's base."""
    return [{"number": str(n), "name": str(n), "electrical": "Passive", "orientation": 0, "length": 100, "part_id": 1, "x": x, "y": y}
            for n, (x, y) in enumerate([(-100, 200), (-100, 100), (-100, 0), (100, 100), (100, 200)], 1)]


def _part():
    return {"ref": "D1", "pins": [{"num": str(n), "name": str(n), "net": f"N{n}"} for n in range(1, 6)]}


def test_a_polyline_between_pin_bases_is_no_evidence_of_one_terminal():
    pins = _zener5()
    sym = {"name": "ZENER5", "joined": [["2", "5"]], "stacked": stacked_pins(pins), "pins": pins}
    _, warn, _ = draw.pin_nets(_part(), sym)
    assert not [w for w in warn if "are one terminal" in w], warn            # the claim the compile would call false
    assert any("drawing only: not checked" in w and "2 and 5" in w for w in warn)


def test_pins_stacked_at_one_location_are_one_terminal_on_evidence():
    pins = _zener5()
    pins[4].update(x=-100, y=100)                    # pin 5 sits on pin 2: Altium joins them by itself
    assert stacked_pins(pins) == [["2", "5"]]
    sym = {"name": "ZENER5", "joined": [], "stacked": stacked_pins(pins), "pins": pins}
    _, warn, _ = draw.pin_nets(_part(), sym)
    assert any("D1: pins 2 and 5 are one terminal" in w and "sit at one location" in w for w in warn)
