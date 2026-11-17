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


def test_ground_names_with_0v_inside_still_match():
    for ok in ("0V_ISO", "ISO_0V", "0V_DIG", "0VA", "-0V"):
        assert schematic.GND_RE.search(ok), ok
    for bad in ("+10V", "1.0V", "0V5", "+20V", "V10", "10V_ISO"):
        assert not schematic.GND_RE.search(bad), bad


def test_negative_rails_are_not_positive():
    for neg in ("VCC-", "VDD_N", "M5V", "-12V", "VCCN", "VDDN", "+5V-"):
        assert not schematic._is_pos_rail(neg), neg
    for pos in ("+5V", "VCC", "VDD", "VIN", "+3V3"):
        assert schematic._is_pos_rail(pos), pos
    assert not ids(run(cap("GND", "VDD_N")), "polarized_cap_reversed")
    assert not ids(run(cap("GND", "M5V")), "polarized_cap_reversed")


def flyback(parts, bom):
    sh = schematic.build_netlist_sheets_netlist([{"parts": parts}])
    det = {p["tag"]: p for p in sh["all_pins"]}
    return schematic.check_inductive_load_no_flyback(sh["nets"], det, bom)


def test_bidirectional_tvs_across_a_coil_is_skipped():
    parts = driver([pin("1", "A", "+5V"), pin("2", "K", "BZ_LOW")])  # would be reversed
    assert [f["id"] for f in flyback(parts, [])] == ["flyback_diode_reversed"]
    for text in ("Bidirectional TVS", "bi-directional", "TVS diode 15V"):
        assert flyback(parts, [{"refs": ["D1"], "description": text}]) == []
    assert flyback(parts, [{"refs": ["D1"], "mpn": "SMBJ15CA"}]) == []


def test_bridge_rectifier_pins_are_not_read_as_polarity():
    parts = driver([pin("1", "+", "+5V"), pin("2", "-", "BZ_LOW"), pin("3", "~", "AC1"), pin("4", "~", "AC2")])
    assert flyback(parts, []) == []
    parts = driver([pin("1", "+", "+5V"), pin("2", "-", "BZ_LOW")])
    assert flyback(parts, [{"refs": ["D1"], "description": "Bridge rectifier"}]) == []


def test_series_diode_and_zener_clamp_across_the_coil_is_accepted():
    parts = driver() + [{"ref": "D1", "pins": [pin("1", "K", "+5V"), pin("2", "A", "MID")]},
                        {"ref": "D2", "pins": [pin("1", "K", "MID"), pin("2", "A", "BZ_LOW")]}]
    assert not ids(run(parts), "inductive_load_no_flyback")
    # a resistor in the middle instead is not a diode clamp
    parts = driver() + [{"ref": "D1", "pins": [pin("1", "K", "+5V"), pin("2", "A", "MID")]},
                        {"ref": "R1", "pins": [pin("1", "1", "MID"), pin("2", "2", "BZ_LOW")]}]
    assert ids(run(parts), "inductive_load_no_flyback")
