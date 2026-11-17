"""A16: flyback diode orientation, LED without resistor, polarized capacitor polarity, ground names."""
from checks import schematic


def pin(num, name, net):
    return {"num": num, "name": name, "net": net}


def ids(res, fid):
    return [f for f in res["findings"] if f["id"] == fid]


def run(parts):
    return schematic.check_schematic({"parts": parts})


def driver(diode_pins=None):
    parts = [
        {"ref": "Q1", "pins": [pin("1", "B", "CTRL"), pin("2", "E", "GND"), pin("3", "C", "BZ_LOW")]},
        {"ref": "BZ1", "pins": [pin("1", "+", "+5V"), pin("2", "-", "BZ_LOW")]},
    ]
    if diode_pins:
        parts.append({"ref": "D1", "pins": diode_pins})
    return parts


def test_flyback_diode_the_wrong_way_round_is_an_error():
    res = run(driver([pin("1", "A", "+5V"), pin("2", "K", "BZ_LOW")]))
    found = ids(res, "flyback_diode_reversed")
    assert len(found) == 1 and found[0]["severity"] == "error" and "D1" in found[0]["refs"]
    assert not ids(res, "inductive_load_no_flyback")


def test_flyback_diode_right_way_or_unreadable_polarity_is_not_flagged():
    assert not ids(run(driver([pin("1", "K", "+5V"), pin("2", "A", "BZ_LOW")])), "flyback_diode_reversed")
    assert not ids(run(driver([pin("1", "1", "+5V"), pin("2", "2", "BZ_LOW")])), "flyback_diode_reversed")


def test_high_side_switch_load_to_ground_diode_orientation():
    def ckt(a_net, k_net):
        return [{"ref": "Q1", "pins": [pin("1", "G", "CTRL"), pin("2", "S", "+12V"), pin("3", "D", "SW")]},
                {"ref": "K1", "pins": [pin("1", "1", "SW"), pin("2", "2", "GND")]},
                {"ref": "D1", "pins": [pin("1", "A", a_net), pin("2", "K", k_net)]}]
    assert not ids(run(ckt("GND", "SW")), "flyback_diode_reversed")
    assert ids(run(ckt("SW", "GND")), "flyback_diode_reversed")


def led(a, k, ref="LED1"):
    return [{"ref": ref, "pins": [pin("1", "A", a), pin("2", "K", k)]}]


def test_led_straight_across_rails_is_flagged_and_resistor_clears_it():
    found = ids(run(led("+3V3", "GND")), "led_no_series_resistor")
    assert len(found) == 1 and found[0]["refs"] == ["LED1"]
    with_r = led("LEDA", "GND") + [{"ref": "R1", "pins": [pin("1", "1", "+3V3"), pin("2", "2", "LEDA")]}]
    assert not ids(run(with_r), "led_no_series_resistor")
    assert not ids(run(led("IO1", "GND")), "led_no_series_resistor")
    assert not ids(run(led("GND", "+3V3")), "led_no_series_resistor")


def test_led_checks_use_bom_text_for_d_refs():
    assert not ids(run(led("+5V", "GND", "D1")), "led_no_series_resistor")
    nets = {"+5V": ["D1-1"], "GND": ["D1-2"]}
    det = {"D1-1": {"name": "A"}, "D1-2": {"name": "K"}}
    assert schematic.check_led_no_series_resistor(nets, det, [{"refs": ["D1"], "description": "Red LED 0603"}])
    assert not schematic.check_led_no_series_resistor(nets, det, [{"refs": ["D1"], "description": "LED with built-in resistor"}])


def cap(p, n):
    return [{"ref": "C1", "pins": [pin("1", "+", p), pin("2", "-", n)]}]


def test_polarized_cap_reversed_is_an_error_correct_ones_are_not():
    found = ids(run(cap("GND", "+5V")), "polarized_cap_reversed")
    assert len(found) == 1 and found[0]["severity"] == "error"
    assert not ids(run(cap("+5V", "GND")), "polarized_cap_reversed")
    assert not ids(run(cap("GND", "-5V")), "polarized_cap_reversed")
    assert not ids(run(cap("GND", "SIG")), "polarized_cap_reversed")
    plain = [{"ref": "C1", "pins": [pin("1", "1", "GND"), pin("2", "2", "+5V")]}]
    assert not ids(run(plain), "polarized_cap_reversed")


def test_ground_regex_matches_only_ground_names():
    for ok in ("GND", "AGND", "DGND", "PGND", "VSS", "0V", "GND_ISO", "+0V"):
        assert schematic.GND_RE.search(ok), ok
    for bad in ("+10V", "10V", "V10", "+30V", "+3V3"):
        assert not schematic.GND_RE.search(bad), bad
