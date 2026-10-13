"""Tests for scripts/checks/board.py (PcbDoc board layout checks)."""
import pathlib
import sys
import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from checks import board
from checks.board import check_board, check_decoupling_caps, check_edge_components, derive_opening_direction

FIXTURES = REPO / "tests" / "fixtures" / "altium"
OUTLINE = [0, 0, 100, 80]


def comp(ref, x, y, rotation=0.0, pattern="", lib_ref="", body=None, outline=None):
    c = {"ref": ref, "pattern": pattern, "lib_ref": lib_ref, "x_mm": x, "y_mm": y, "rotation": rotation}
    if body is not None:
        c["body_bbox_mm"] = body
    if outline is not None:
        c["outline_bbox_mm"] = outline
    return c


def pad(ref, name, x, y, net=None):
    return {"ref": ref, "name": name, "net": net, "x_mm": x, "y_mm": y}


def ids(res, id_):
    return [f for f in res["findings"] if f["id"] == id_]


def test_finished_board_checks():
    """Verify board checks run on finished-board.PcbDoc fixture."""
    res = check_board(FIXTURES / "finished-board.PcbDoc")
    assert res["component_count"] == 56
    assert res["pad_count"] == 272
    assert res["net_count"] == 71

    finding_ids = {f["id"] for f in res["findings"]}
    # Should flag CPL rotation sanity list
    assert "cpl_rotation_sanity" in finding_ids

    # C8 (5V) sits 11 mm from the regulator pad that supplies the rail; C7 (3V3bd) is next to its regulator Reg3
    decap_findings = ids(res, "decap_distance_excessive")
    flagged = {f["refs"][0] for f in decap_findings}
    assert "C8" in flagged and "C7" not in flagged
    assert next(f for f in decap_findings if f["refs"][0] == "C8")["refs"] == ["C8", "Reg5"]

    # The fixture's headers have no derivable opening direction: no error from a guess
    assert ids(res, "connector_faces_inward") == []

    # Every finding conforms to schema
    for f in res["findings"]:
        assert "id" in f
        assert f["severity"] in ("error", "warning", "info")
        assert isinstance(f["refs"], list)
        assert "message" in f
        assert "evidence" in f


# ---- connector opening direction: explicit spec -------------------------------------------------------

def test_connector_faces_inward_detected():
    """An explicit spec (opening at rotation 0 toward -Y) rotated by the component: pointing away from the edge is flagged."""
    mock_doc = {
        "file": "mock.PcbDoc",
        "components": [
            comp("J1", 5.0, 50.0, rotation=90.0, pattern="HDR1X2", lib_ref="Header 2"),   # (0,-1) -> (1,0): inward
            comp("J2", 5.0, 20.0, rotation=270.0, pattern="HDR1X2", lib_ref="Header 2"),  # (0,-1) -> (-1,0): outward
        ],
        "pads": [pad("J1", "1", 5.0, 50.0, "5V"), pad("J2", "1", 5.0, 20.0, "5V")],
        "nets": ["5V"],
    }
    specs = {"J1": {"wire_entry_dir_at_rot0": [0.0, -1.0]}, "J2": {"wire_entry_dir_at_rot0": [0.0, -1.0]}}

    res = check_board(mock_doc, outline_mm=OUTLINE, connector_specs=specs)
    inward = ids(res, "connector_faces_inward")
    assert len(inward) == 1
    assert inward[0]["refs"] == ["J1"]
    assert inward[0]["severity"] == "error"
    assert "inward" in inward[0]["message"]
    assert "facing vector (1.00," in inward[0]["evidence"]
    assert ids(res, "connector_direction_unknown") == []


def test_explicit_spec_beats_footprint_geometry():
    """The spec wins over what the body outline says, in both directions."""
    pads_ = [pad("J1", "1", 10.0, 40.0), pad("J1", "2", 10.0, 42.5)]
    outward_body = [0.0, 38.0, 10.0, 44.5]      # body overhangs toward the left edge: derived outward
    doc = {"components": [comp("J1", 10.0, 40.0, pattern="HDR", body=outward_body)], "pads": pads_}
    assert ids(check_board(doc, outline_mm=OUTLINE), "connector_faces_inward") == []
    inward_spec = {"J1": {"wire_entry_dir_at_rot0": [1.0, 0.0]}}
    bad = ids(check_board(doc, outline_mm=OUTLINE, connector_specs=inward_spec), "connector_faces_inward")
    assert len(bad) == 1 and "derived" not in bad[0]["message"]

    inward_body = [10.0, 38.0, 20.0, 44.5]      # derived inward, spec says outward: the spec wins
    doc["components"][0]["body_bbox_mm"] = inward_body
    assert ids(check_board(doc, outline_mm=OUTLINE), "connector_faces_inward")
    outward_spec = {"J1": {"wire_entry_dir_at_rot0": [-1.0, 0.0]}}
    assert ids(check_board(doc, outline_mm=OUTLINE, connector_specs=outward_spec), "connector_faces_inward") == []


# ---- connector opening direction: derived from the footprint ------------------------------------------

def edge_connector(ref="J1", x=10.0, body=None, outline=None, rotation=0.0):
    """Two pads in a vertical line at x, near the left edge of OUTLINE."""
    return {
        "components": [comp(ref, x, 40.0, rotation=rotation, pattern="HDR1X2", body=body, outline=outline)],
        "pads": [pad(ref, "1", x, 40.0, "5V"), pad(ref, "2", x, 42.54, "GND")],
    }


def test_vertical_connector_has_no_direction():
    """A pin header / U.FL / test point: body centred on its pads, so no opening, no finding, no info."""
    doc = edge_connector(body=[8.73, 38.73, 11.27, 43.81])
    assert derive_opening_direction(doc["components"][0], doc["pads"])["dir"] is None
    res = check_board(doc, outline_mm=OUTLINE)
    assert ids(res, "connector_faces_inward") == [] and ids(res, "connector_direction_unknown") == []


@pytest.mark.parametrize("name,pad_centroid,body", [
    # numbers measured on a real finished board: pad centroid -> 3D body box
    ("terminal block, offset 0.47 mm (centred pads)", (32.59, 91.75), [27.98, 86.75, 37.81, 97.48]),
    ("U.FL receptacle, offset 0.51 mm (16% of 3.1 mm)", (99.4, 99.77), [97.9, 98.72, 100.9, 101.82]),
    ("terminal block, offset 0.50 mm", (36.67, 42.52), [33.42, 37.52, 40.92, 47.53]),
])
def test_small_offset_is_no_direction(name, pad_centroid, body):
    px, py = pad_centroid
    c = comp("J1", px, py, pattern="CONN", body=body)
    res = derive_opening_direction(c, [pad("J1", "1", px, py - 1), pad("J1", "2", px, py + 1)])
    assert res["dir"] is None, name


@pytest.mark.parametrize("name,pad_centroid,body,nearest_edge", [
    ("pluggable header, right edge", (116.2, 44.69), [115.0, 40.18, 124.2, 49.19], "right"),
    ("USB-C, bottom edge", (82.15, 32.62), [77.68, 25.98, 86.62, 33.76], "bottom"),
    ("SIM socket, right edge", (111.8, 77.84), [111.98, 72.66, 124.63, 83.01], "right"),
])
def test_right_angle_connectors_facing_their_edge(name, pad_centroid, body, nearest_edge):
    """Real right-angle geometry: the body overhangs the pads toward the nearest edge, so no error."""
    px, py = pad_centroid
    x, y = {"right": (px + 3, py), "bottom": (px, py - 3)}[nearest_edge]
    doc = {"components": [comp("J1", x, y, rotation=90.0, pattern="CONN", body=body)], "pads": [pad("J1", "1", px, py)]}
    outline = [26.0, 25.4, 126.2, 103.9]
    assert ids(check_board(doc, outline_mm=outline), "connector_faces_inward") == [], name
    d = derive_opening_direction(doc["components"][0], doc["pads"])
    assert d["dir"] is not None and d["source"] == "3D body"


def test_right_angle_connector_derived_inward_is_error():
    # pads at x=10, body from 10 to 20: the mating face is on the +X side, the nearest edge is the left one
    doc = edge_connector(body=[10.0, 38.0, 20.0, 44.5])
    res = check_board(doc, outline_mm=OUTLINE)
    bad = ids(res, "connector_faces_inward")
    assert len(bad) == 1 and bad[0]["severity"] == "error" and bad[0]["refs"] == ["J1"]
    assert "derived from the 3D body" in bad[0]["message"] and "3D view" in bad[0]["message"]
    assert "pad centroid" in bad[0]["evidence"]
    # the placement rotation is already in the board coordinates: rotating the field changes nothing
    doc["components"][0]["rotation"] = 90.0
    assert ids(check_board(doc, outline_mm=OUTLINE), "connector_faces_inward")


def test_right_angle_connector_derived_outward_is_clean():
    doc = edge_connector(body=[0.0, 38.0, 10.0, 44.5])
    res = check_board(doc, outline_mm=OUTLINE)
    assert ids(res, "connector_faces_inward") == [] and ids(res, "connector_direction_unknown") == []
    d = derive_opening_direction(doc["components"][0], doc["pads"])
    assert d["dir"] == pytest.approx((-1.0, 0.0), abs=0.01)


def test_outline_is_used_when_there_is_no_body():
    doc = edge_connector(outline=[10.0, 38.0, 20.0, 44.5])
    bad = ids(check_board(doc, outline_mm=OUTLINE), "connector_faces_inward")
    assert len(bad) == 1 and "outline" in bad[0]["message"]
    # the 3D body wins over the outline when both exist
    doc["components"][0]["body_bbox_mm"] = [0.0, 38.0, 10.0, 44.5]
    assert ids(check_board(doc, outline_mm=OUTLINE), "connector_faces_inward") == []


def test_no_geometry_is_info_never_error():
    """Nothing to derive a direction from (and no spec): one info finding listing the connectors, no error."""
    doc = edge_connector()
    doc["components"].append(comp("J2", 10.0, 20.0, pattern="HDR1X2"))
    doc["pads"].append(pad("J2", "1", 10.0, 20.0))
    res = check_board(doc, outline_mm=OUTLINE)
    assert ids(res, "connector_faces_inward") == []
    unknown = ids(res, "connector_direction_unknown")
    assert len(unknown) == 1 and unknown[0]["severity"] == "info"
    assert unknown[0]["refs"] == ["J1", "J2"] and "3D view" in unknown[0]["message"]
    assert not [f for f in res["findings"] if f["severity"] == "error"]


def test_diode_in_sma_package_is_not_a_connector():
    assert not board.is_connector(comp("D3", 1, 1, pattern="SMA_L4.2-W2.6-LS5.0-RD_1"))
    assert board.is_connector(comp("J3", 1, 1, pattern="SMA_EDGE"))


# ---- decoupling caps ----------------------------------------------------------------------------------

def cap(ref, x, y, net_a, net_b, pattern="C0603", gap=1.4):
    return ([comp(ref, x, y, pattern=pattern)],
            [pad(ref, "1", x, y, net_a), pad(ref, "2", x + gap, y, net_b)])


def decap_doc(*parts):
    comps_, pads_ = [], []
    for c, p in parts:
        comps_ += c
        pads_ += p
    return {"components": comps_, "pads": pads_}


def ic(ref, x, y, net, pin="7"):
    return ([comp(ref, x, y, pattern="QFN32")],
            [pad(ref, pin, x, y, net), pad(ref, "8", x, y + 1, None), pad(ref, "9", x + 5, y, "GND"), pad(ref, "10", x + 5, y + 1, None)])


def test_decap_far_from_its_ic_is_a_warning():
    doc = decap_doc(cap("C1", 0, 0, "+3V3", "GND"), ic("U1", 12.0, 0.0, "+3V3"))
    found = check_decoupling_caps(doc)
    assert len(found) == 1
    f = found[0]
    assert f["id"] == "decap_distance_excessive" and f["severity"] == "warning" and f["refs"] == ["C1", "U1"]
    assert "12.0 mm" in f["message"] and "<= 5 mm" in f["message"]
    assert "U1-7" in f["evidence"]


def test_decap_close_to_its_ic_is_fine():
    doc = decap_doc(cap("C1", 0, 0, "+3V3", "GND"), ic("U1", 3.0, 0.0, "+3V3"))
    assert check_decoupling_caps(doc) == []


def test_decap_limit_is_configurable_and_matches_the_text():
    assert board.DECAP_MAX_DIST_MM == 5.0
    doc = decap_doc(cap("C1", 0, 0, "+3V3", "GND"), ic("U1", 12.0, 0.0, "+3V3"))
    assert check_decoupling_caps(doc, max_dist_mm=15.0) == []
    f = check_decoupling_caps(doc, max_dist_mm=8.0)
    assert len(f) == 1 and "<= 8 mm" in f[0]["message"]
    assert len(ids(check_board(doc, outline_mm=OUTLINE), "decap_distance_excessive")) == 1
    assert ids(check_board(doc, outline_mm=OUTLINE, decap_max_dist_mm=15.0), "decap_distance_excessive") == []


@pytest.mark.parametrize("net", ["BTN1", "TC_P", "NRST", "OSC_IN", "RF_ANT", "NetC5_1"])
def test_signal_net_cap_is_not_a_decap(net):
    """A debounce / input-filter / crystal-load cap shares its signal net with a far IC pin: not a decoupling cap."""
    doc = decap_doc(cap("C61", 0, 0, net, "GND"), ic("U6", 30.0, 0.0, net, pin="34"))
    assert check_decoupling_caps(doc) == []


def test_bulk_caps_are_not_decaps():
    # 100 uF electrolytic (pad span 6.2 mm) and a 7.3x4.3 tantalum (7.0 mm), far from the IC on the same rail
    elec = cap("C1", 0, 0, "+12V", "GND", pattern="CAP_EEEFK1E101P", gap=6.2)
    tant = cap("C30", 0, 10, "+12V", "GND", pattern="CAP-SMD_L7.3-W4.3-R-RD", gap=7.0)
    doc = decap_doc(elec, tant, ic("U1", 25.0, 0.0, "+12V", pin="2"))
    assert check_decoupling_caps(doc) == []
    # the same pad span with a plain ceramic pattern is still too large for a decap; a 0805 is a candidate
    big = cap("C2", 0, 20, "+12V", "GND", pattern="C0805", gap=6.2)
    assert check_decoupling_caps(decap_doc(big, ic("U1", 25.0, 20.0, "+12V", pin="2"))) == []
    small = cap("C3", 0, 20, "+12V", "GND", pattern="C0805", gap=2.0)
    assert len(check_decoupling_caps(decap_doc(small, ic("U1", 25.0, 20.0, "+12V", pin="2")))) == 1


def test_decap_is_measured_to_the_connector_that_it_supplies():
    """SIM_VDD cap next to the SIM socket J7; the modem pin on the same net is 27 mm away: no finding."""
    j7 = ([comp("J7", 7.0, 0.0, pattern="MOLEX_104224-0820")], [pad("J7", "S1", 3.5, 0.0, "SIM_VDD"), pad("J7", "G1", 3.5, 3, "GND")])
    doc = decap_doc(cap("C42", 0, 0, "SIM_VDD", "GND"), j7, ic("U4", 27.7, 0.0, "SIM_VDD", pin="30"))
    assert check_decoupling_caps(doc) == []
    # without the socket the far modem pin is all there is
    doc = decap_doc(cap("C42", 0, 0, "SIM_VDD", "GND"), ic("U4", 27.7, 0.0, "SIM_VDD", pin="30"))
    assert [f["refs"] for f in check_decoupling_caps(doc)] == [["C42", "U4"]]


def test_passives_are_not_loads():
    """Resistors and other 2-terminal parts (even with a custom designator) on the rail do not count as the supplied part."""
    r1 = ([comp("R1", 2.0, 0.0, pattern="R0603")], [pad("R1", "1", 2.0, 0.0, "+3V3")])
    rl2 = ([comp("RL2", 3.0, 0.0, pattern="0805_L")], [pad("RL2", "1", 3.0, 0.0, "+3V3"), pad("RL2", "2", 3.0, 2.0, "X")])
    other_cap = cap("CC2", 1.0, 3.0, "+3V3", "GND")
    doc = decap_doc(cap("C1", 0, 0, "+3V3", "GND"), r1, rl2, other_cap, ic("U1", 12.0, 0.0, "+3V3"))
    found = check_decoupling_caps(doc)
    assert [f["refs"] for f in found] == [["C1", "U1"], ["CC2", "U1"]]


@pytest.mark.parametrize("net,rail", [
    ("+3V3", True), ("3V3", True), ("+3V3A", True), ("+3V8", True), ("+12V", True), ("+12V_RLY", True),
    ("5V", True), ("1V8", True), ("3V3bd", True), ("VDD", True), ("VDD_EXT", True), ("VCC", True), ("VDDA", True),
    ("SIM_VDD", True), ("VBAT", True), ("VBUS", True), ("USB_VBUS", True), ("MDM_USB_VBUS", True),
    ("VCAP1", True), ("VREF+", True), ("AVDD", True),
    ("BTN1", False), ("TC_P", False), ("NRST", False), ("OSC_IN", False), ("RF_ANT", False), ("SW", False),
    ("MDM_RXD_1V8", False), ("I2C_SDA", False), ("GND", False), ("NetC5_1", False), ("COIL1_N", False),
])
def test_power_rail_name_pattern(net, rail):
    assert bool(board.POWER_NET.search(net)) is rail


def test_edge_checks_use_the_board_shape_only_when_it_holds_the_parts():
    fixtures = pathlib.Path(__file__).parent / "fixtures" / "altium"
    fin = board.check_board(fixtures / "finished-board.PcbDoc")
    assert fin["bounds_mm"] == (25.4, 25.4, 127.127, 127.0)
    assert not [f for f in fin["findings"] if f["id"] == "board_shape_does_not_hold_parts"]
    # rules-board still has Altium's default shape and parts far outside it: fall back, and say so
    rb = board.check_board(fixtures / "rules-board.PcbDoc")
    assert [f for f in rb["findings"] if f["id"] == "board_shape_does_not_hold_parts"]
    assert rb["bounds_mm"][2] > 200
