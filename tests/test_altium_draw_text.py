"""Schematic drawing: the part's designator and comment text, long pin numbers, crowded top pins, a split that really fits, and
tactile-switch pads. The inputs are the netlists and symbols of the 2026-11-20 live verify run (tests/fixtures/draw_verify): real
symbols (a 4-pin crystal, a 16-pin USB-C, the 57-pin RP2040, a 4-pad switch), not hand-made ones. The text boxes are estimated
with the same metrics partlib_convert uses for symbol text."""
import json
import pathlib

import pytest

import partlib_convert as pc
from altium import draw
from altium.lib import symbol_graphics

FIX = pathlib.Path(__file__).parent / "fixtures" / "draw_verify"
ELEC = {"eElectricPassive": "Passive", "eElectricPower": "Power", "eElectricIO": "IO", "eElectricInput": "Input",
        "eElectricOutput": "Output"}
ORI = {"eRotate0": 0, "eRotate90": 1, "eRotate180": 2, "eRotate270": 3}
SYMBOL_OF = {"Y1": "X322512MSB4SI", "J1": "TYPE-C-31-M-12", "U1": "RP2040", "U2": "W25Q16JVSNIQ", "SW": "TS-1187A-B-A-B",
             "D1": "KT-0603R", "J2": "2.54-1_3PPin", "R": "0603WAF1001T5E", "C": "CC0603KRX7R9BB104"}


def symbols_from(path):
    """{name: symbol dict as read_schlib returns it} from the spec file the library builder wrote."""
    out, cur = {}, None
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        f = line.split("|")
        if f[0] == "SYMBOL":
            cur = out[f[1]] = {"name": f[1], "pins": [], "comment": f[1], "_text": []}
        elif f[0] == "PIN":
            cur["pins"].append({"number": f[1], "name": f[2], "electrical": ELEC.get(f[3], f[3]), "orientation": ORI[f[4]],
                                "x": int(float(f[5])), "y": int(float(f[6])), "length": int(float(f[8])), "part_id": 1,
                                "show_name": True, "show_number": True, "conglomerate": 0})
        elif f[0] == "GRAPHIC":
            v = [float(x) / 10 for x in (f[5:9] if f[1] == "rectangle" else f[4:] if f[1] == "polyline" else f[5:]) if x]
            if f[1] == "rectangle":
                cur["_text"].append({"RECORD": "14", "LOCATION.X": str(round(v[0])), "LOCATION.Y": str(round(v[1])),
                                     "CORNER.X": str(round(v[2])), "CORNER.Y": str(round(v[3]))})
            elif f[1] in ("polyline", "polygon"):
                r = {"RECORD": "6" if f[1] == "polyline" else "7", "LOCATIONCOUNT": str(len(v) // 2)}
                for i in range(len(v) // 2):
                    r[f"X{i + 1}"], r[f"Y{i + 1}"] = str(round(v[2 * i])), str(round(v[2 * i + 1]))
                cur["_text"].append(r)
    for s in out.values():
        s["body"], s["joined"] = symbol_graphics(s.pop("_text"), s["pins"])
    return out


SYMS = symbols_from(FIX / "symbols_spec.txt")


def _sym_for(ref):
    key = ref if ref in SYMBOL_OF else ref.rstrip("0123456789")
    return SYMS[SYMBOL_OF[key]]


def _lib_for(sheet):
    out = {}
    for p in sheet["parts"]:
        if p["ref"] == "U3":        # AP2112K: 5 pins; the symbol of that part is not in the fixture, so a plausible one
            out["U3"] = {"name": "AP2112K-3.3TRG1", "comment": "AP2112K-3.3TRG1", "body": (-300, -100, 300, 200), "joined": [],
                         "pins": [{"number": str(i + 1), "name": nm, "electrical": "Passive", "orientation": o, "x": x, "y": y,
                                   "length": 100, "part_id": 1, "show_number": True}
                                  for i, (nm, o, x, y) in enumerate([("VIN", 2, -300, 100), ("GND", 2, -300, 0), ("EN", 2, -300, -100),
                                                                     ("NC", 0, 300, -100), ("VOUT", 0, 300, 100)])]}
        else:
            out[p["ref"]] = _sym_for(p["ref"])
    return out


def sheet(name):
    return json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))


def planned(name):
    sh = sheet(name)
    return draw.plan_sheet(sh, _lib_for(sh), "lib.SchLib", "sheet.SchDoc"), sh


# ---------------------------------------------------------------- what the commands draw, as boxes (read from the commands)

H = pc.NAME_HEIGHT + 20            # a text line is this high, with a little slack
CH = pc.NAME_CHAR                  # mil per character (the estimate partlib_convert uses for symbol text)


def _inter(a, b, slack=0):
    return a[0] < b[2] - slack and b[0] < a[2] - slack and a[1] < b[3] - slack and b[1] < a[3] - slack


def drawn(p, lib):
    """{'text': [(what, box)], 'obstacles': [(what, box)], 'wires': [(x1, y1, x2, y2)]} from the plan's commands alone."""
    text, obst, wires = [], [], []
    for c in p["commands"]:
        if c[0] == "PLACE":
            ref, ox, oy = c[2], int(c[5]), int(c[6])
            for k, (xi, yi) in (("designator", (8, 9)), ("comment", (10, 11))):
                if c[xi]:
                    s = ref if k == "designator" else draw.shown_comment(lib[ref].get("comment") or lib[ref]["name"])
                    x, y = int(c[xi]), int(c[yi])
                    text.append((f"{ref} {k}", (x, y, x + len(s) * CH, y + H)))
            for pin in lib[ref]["pins"]:        # the pin number text
                if pin.get("show_number", True):
                    q = {"x": pin["x"], "y": pin["y"], "orient": {0: "eRotate0", 1: "eRotate90", 2: "eRotate180", 3: "eRotate270"}[pin["orientation"]],
                         "num": pin["number"]}
                    b = pc._text_box(q, pin["number"], False)
                    obst.append((f"{ref} pin {pin['number']} number", (b[0] + ox, b[1] + oy, b[2] + ox, b[3] + oy)))
        elif c[0] == "WIRE":
            wires.append(tuple(int(v) for v in c[2:6]))
        elif c[0] == "NETLABEL":
            x, y, rot, t = int(c[2]), int(c[3]), int(c[4]), c[5]
            w = len(t) * CH
            obst.append((f"label {t}", (x, y, x + w, y + pc.NAME_HEIGHT) if rot == 0 else (x - pc.NAME_HEIGHT, y, x, y + w)))
        elif c[0] == "POWER":
            x, y = int(c[2]), int(c[3])
            obst.append((f"power {c[6]}", (x - 100, y - 100, x + 100, y + 100)))
    return {"text": text, "obstacles": obst, "wires": wires}


def collisions(d):
    """Every text box that touches a wire, a label, a power port, a pin number or another text."""
    bad = []
    for i, (k, b) in enumerate(d["text"]):
        for what, o in d["obstacles"]:
            if _inter(b, o):
                bad.append((k, what))
        for w in d["wires"]:
            if pc._segment_hits(b, *w):
                bad.append((k, f"wire {w}"))
        for k2, b2 in d["text"][i + 1:]:
            if _inter(b, b2):
                bad.append((k, k2))
    return bad


@pytest.mark.parametrize("name", ["Clock", "Core", "Main", "Periph"])
def test_the_designator_and_comment_text_never_covers_a_pin_stub_label_or_power_port(name):
    p, sh = planned(name)
    assert not p["errors"], p["errors"]
    lib = _lib_for(sh)
    d = drawn(p, lib)
    assert len(d["text"]) >= len(sh["parts"])           # every part has its designator and comment placed
    assert collisions(d) == []


def obstacle_overlaps(d):
    o = d["obstacles"]
    return [(a, b) for i, (a, x) in enumerate(o) for b, y in o[i + 1:] if _inter(x, y)]


@pytest.mark.parametrize("name", ["Clock", "Core", "Main", "Periph"])
def test_no_label_power_port_or_pin_number_text_overlaps_another(name):
    p, sh = planned(name)
    assert obstacle_overlaps(drawn(p, _lib_for(sh))) == []


def test_a_long_pin_number_leaves_the_net_label_clear_of_it():
    # J1 (USB-C): A1B12 / B4A9 / B1A12 are 5 characters on a 100 mil pin: the label starts past the end of the number
    p, sh = planned("Main")
    lib = _lib_for(sh)
    d = drawn(p, lib)
    nums = [(w, b) for w, b in d["obstacles"] if w.startswith("J1 pin") and any(n in w for n in ("A1B12", "A4B9", "B4A9", "B1A12"))]
    labels = [(w, b) for w, b in d["obstacles"] if w.startswith("label")]
    assert len(nums) == 4 and not [1 for _, n in nums for _, lab in labels if _inter(n, lab)]
    # and the stub is longer for it than for a short number on the same side
    j1 = next(c for c in p["commands"] if c[0] == "PLACE" and c[2] == "J1")
    stubs = {}
    for c in p["commands"]:
        if c[0] == "WIRE":
            stubs[(int(c[2]), int(c[3]))] = abs(int(c[4]) - int(c[2]))
    ox, oy = int(j1[5]), int(j1[6])
    by_num = {q["number"]: q for q in lib["J1"]["pins"]}
    long_ = stubs[(ox + draw.tip(by_num["A1B12"])[0], oy + draw.tip(by_num["A1B12"])[1])]
    short = stubs[(ox + draw.tip(by_num["A5"])[0], oy + draw.tip(by_num["A5"])[1])]
    overhang = len("A1B12") * CH - by_num["A1B12"]["length"]            # how far the number runs past the pin's tip
    assert overhang > 0 and long_ >= overhang + 50 + len("GND") * draw.CHAR + 100 and long_ > short


def test_labels_on_adjacent_top_pins_are_staggered_not_crammed():
    # a part with five pins 100 mil apart on its top edge, all labels: no two label texts touch and the stub lengths alternate
    top = {"name": "TOPIC", "comment": "TOPIC", "joined": [], "body": (-300, -200, 300, 100),
           "pins": [{"number": str(i + 1), "name": f"P{i + 1}", "electrical": "Passive", "orientation": 1, "x": -200 + 100 * i, "y": 100,
                     "length": 200, "part_id": 1, "show_number": True} for i in range(5)]}
    part = {"ref": "U9", "pins": [{"num": str(i + 1), "name": f"P{i + 1}", "net": f"+3V3_RAIL_{i}"} for i in range(5)]}
    cell = draw.part_cell(part, top)
    lens = [abs(s["end"][1] - s["tip"][1]) for s in sorted(cell["stubs"], key=lambda s: s["tip"][0])]
    assert len(set(lens)) == 2 and all(lens[i] != lens[i + 1] for i in range(4))
    labels = [(s["at"][0] - pc.NAME_HEIGHT, s["at"][1], s["at"][0], s["at"][1] + len(s["net"]) * CH) for s in cell["stubs"] if s["kind"] == "label"]
    assert not [1 for i, a in enumerate(labels) for b in labels[i + 1:] if _inter(a, b)]
    # the stagger sits inside the cell box, so the frame keeps it
    assert all(s["end"][1] + draw.MARGIN <= cell["box"][3] for s in cell["stubs"])


def test_every_part_gets_both_text_spots_from_the_plan_not_the_library_symbol():
    p, sh = planned("Clock")
    places = [c for c in p["commands"] if c[0] == "PLACE"]
    assert places and all(len(c) == 13 and all(v != "" for v in c[8:12]) for c in places)


def test_the_cell_box_and_so_the_frame_enclose_the_part_texts():
    p, sh = planned("Clock")
    frames = {c[6].split()[1]: tuple(int(v) for v in c[2:6]) for c in p["commands"] if c[0] == "FRAME"}
    sec = {x["ref"]: x["section"] for x in sh["parts"]}
    lib = _lib_for(sh)
    for what, (x0, y0, x1, y1) in drawn(p, lib)["text"]:
        fx, fy, fw, fh = frames[sec[what.split()[0]]]
        assert fx <= x0 and x1 <= fx + fw and fy <= y0 and y1 <= fy + fh - draw.HEADER, (what, frames)


def test_the_text_spots_are_deterministic():
    a, _ = planned("Main")
    b, _ = planned("Main")
    assert a["commands"] == b["commands"]


def test_the_pascal_side_moves_the_designator_and_the_comment_and_the_old_eight_fields_still_work():
    pas = (pathlib.Path(draw.__file__).parent / "bridge" / "AdvisorBridge.pas").read_text(encoding="utf-8")
    assert "C.Designator.Location :=" in pas and "C.Comment.Location :=" in pas and "Field(Line, 11)" in pas
    assert "(DesX <> '') and (DesY <> '')" in pas and "(ComX <> '') and (ComY <> '')" in pas     # an empty field leaves the symbol's spot
    assert all(ord(ch) < 128 for ch in pas)


def test_the_text_anchor_is_made_bottom_left_before_the_spot_is_set():
    # the planner's boxes assume the text starts at the spot and runs right and up: the Pascal side forces that (a library text may
    # be centred or turned), and does it before it moves the text
    pas = (pathlib.Path(draw.__file__).parent / "bridge" / "AdvisorBridge.pas").read_text(encoding="utf-8")
    for what in ("Designator", "Comment"):
        j = pas.index(f"C.{what}.Justification := eJustify_BottomLeft;")
        assert j < pas.index(f"C.{what}.Location :=") and pas.index(f"C.{what}.Orientation := eRotate0;") < pas.index(f"C.{what}.Location :=")


# ---------------------------------------------------------------- crowded top pins of the same net share one label or port

def _top_part(nets):
    pins = [{"number": str(i + 1), "name": f"P{i + 1}", "electrical": "Passive", "orientation": 1, "x": -200 + 100 * i, "y": 100,
             "length": 200, "part_id": 1, "show_number": True} for i in range(len(nets))]
    sym = {"name": "TOPIC", "comment": "TOPIC", "joined": [], "body": (-300, -200, 300, 100), "pins": pins}
    return {"ref": "U9", "pins": [{"num": str(i + 1), "name": f"P{i + 1}", "net": n} for i, n in enumerate(nets)]}, sym


def test_five_same_net_pins_side_by_side_share_one_name_and_stay_connected():
    part, sym = _top_part(["+3V3"] * 5)
    p = draw.plan_sheet({"parts": [{**part, "section": ""}], "sections": []}, {"U9": sym}, "l", "d")
    assert not p["errors"]
    names = [c for c in p["commands"] if c[0] in ("NETLABEL", "POWER")]
    assert len(names) == 1                                       # one name for the five pins, not five stacked ones
    wires = [tuple(int(v) for v in c[2:6]) for c in p["commands"] if c[0] == "WIRE"]
    stubs = sorted(w for w in wires if w[0] == w[2])                    # vertical: the stubs of the pins
    links = sorted(w for w in wires if w[1] == w[3] and w[0] != w[2])  # horizontal: the wires that join them
    assert len(stubs) == 5 and len(links) == 4
    assert sorted(p["expected"]["+3V3"]) == [f"U9-{i}" for i in range(1, 6)]
    # chained at the ends: link k runs from the end of stub k to the end of stub k+1, so nothing hangs in the air
    for k, (a, b) in enumerate(zip(links, [(stubs[i][2], stubs[i][3], stubs[i + 1][2], stubs[i + 1][3]) for i in range(4)])):
        assert a == b, (k, a, b)


def test_a_stepped_top_edge_never_gets_a_diagonal_link():
    # pins 3 and 4 of a same-net group sit 100 mil higher than the others: runs break at the step, every wire is horizontal or vertical
    part, sym = _top_part(["+3V3"] * 5)
    sym["pins"][3]["y"] = sym["pins"][4]["y"] = 200
    p = draw.plan_sheet({"parts": [{**part, "section": ""}], "sections": []}, {"U9": sym}, "l", "d")
    assert not p["errors"]
    wires = [tuple(int(v) for v in c[2:6]) for c in p["commands"] if c[0] == "WIRE"]
    assert all(w[0] == w[2] or w[1] == w[3] for w in wires)
    assert len([c for c in p["commands"] if c[0] in ("NETLABEL", "POWER")]) == 2        # one name per height, not one for the step


def test_a_run_of_same_net_pins_is_read_back_as_one_net():
    # the wires chain at their ends, so the read-back sees all five pins on +3V3 (simulated the way test_altium_draw does)
    from altium.draw import verify_sheet
    from test_altium_draw import simulate, SYMS as S0
    part, sym = _top_part(["+3V3"] * 3 + ["GND"] + ["+3V3"] * 2)
    p = draw.plan_sheet({"parts": [{**part, "section": ""}], "sections": []}, {"U9": sym}, "l", "d")
    assert not p["errors"]
    S0["__U9"] = sym
    try:
        doc = simulate(p["commands"])
    finally:
        del S0["__U9"]
    assert verify_sheet(p, doc, {}) == []


# ---------------------------------------------------------------- the split suggestion: every suggested sheet really fits

def _one_section(names):
    secs = [{"id": "ALL", "title": "Everything"}]
    parts = []
    for n in names:
        for p in sheet(n)["parts"]:
            parts.append({**p, "section": "ALL"})
    return {"id": "Big", "sections": secs, "parts": parts}


def test_a_section_too_big_for_a_sheet_is_cut_by_parts_into_sheets_that_each_draw():
    # the evidence case: RP2040, the crystal, 15 capacitors and more in one section: no sheet of that can fit
    big = _one_section(["Core", "Clock", "Periph"])
    lib = _lib_for(big)
    p = draw.plan_sheet(big, lib, "l", "d")
    assert p["commands"] == [] and p["errors"]
    msg = p["errors"][0]
    assert "needs about" in msg and "1 sheets" not in msg and "cut by parts" in msg
    cells = [(x["section"], draw.part_cell(x, lib[x["ref"]])) for x in big["parts"]]
    sheets, hopeless = draw.suggest_sheets(cells, big["sections"])
    assert len(sheets) >= 2 and hopeless == []
    seen = []
    for sh in sheets:                                    # every suggested sheet is accepted by the very check the drawing makes
        refs = [r for _, rs in sh for r in (rs or [])]
        seen += refs
        sub = {"id": "x", "sections": big["sections"], "parts": [x for x in big["parts"] if x["ref"] in refs]}
        assert draw.plan_sheet(sub, lib, "l", "d")["errors"] == [], refs
    assert sorted(seen) == sorted(x["ref"] for x in big["parts"])        # nothing lost, nothing twice
    # the live run put RP2040, the crystal and 15 capacitors on one sheet: not any more (that sheet is refused by plan_sheet)
    u1 = next(rs for sh in sheets for _, rs in sh if "U1" in rs)
    assert len([r for r in u1 if r.startswith("C")]) < 15


def test_whole_sections_that_fit_together_stay_together_and_every_group_fits():
    secs, parts = [], []
    for n in ("Main", "Clock", "Core", "Periph"):
        for s in sheet(n)["sections"]:
            secs.append({"id": f"{n}_{s['id']}", "title": s["title"]})
        parts += [{**x, "section": f"{n}_{x['section']}"} for x in sheet(n)["parts"]]
    big = {"id": "All", "sections": secs, "parts": parts}
    lib = _lib_for(big)
    cells = [(x["section"], draw.part_cell(x, lib[x["ref"]])) for x in parts]
    sheets, hopeless = draw.suggest_sheets(cells, secs)
    assert hopeless == [] and len(sheets) >= 2 and all(r is None for sh in sheets for _, r in sh)
    for sh in sheets:
        ids = [i for i, _ in sh]
        sub = {"id": "x", "sections": [s for s in secs if s["id"] in ids], "parts": [x for x in parts if x["section"] in ids]}
        assert draw.plan_sheet(sub, lib, "l", "d")["errors"] == []


def test_the_message_never_says_one_sheets(monkeypatch):
    big = _one_section(["Core"])
    lib = _lib_for(big)
    cells = [(x["section"], draw.part_cell(x, lib[x["ref"]])) for x in big["parts"]]
    monkeypatch.setattr(draw, "suggest_sheets", lambda *a, **k: ([[("ALL", None)]], []))
    msg = draw._too_big_message(cells, big["sections"])
    assert "1 sheets" not in msg and "single section" in msg and "must be split into several sections" in msg
    monkeypatch.setattr(draw, "suggest_sheets", lambda *a, **k: ([[("ALL", ["U1"])], [("ALL", ["U2"])]], []))
    assert "about 2 sheets" in draw._too_big_message(cells, big["sections"])
    monkeypatch.setattr(draw, "suggest_sheets", lambda *a, **k: ([[("ALL", ["U1"])]], ["U1"]))
    assert "even by itself" in draw._too_big_message(cells, big["sections"])


# ---------------------------------------------------------------- tactile switch pads that the symbol joins

def _sw(nets):
    sym = SYMS["TS-1187A-B-A-B"]
    return {"ref": "SW1", "pins": [{"name": n, "num": n, "net": net} for n, net in nets]}, sym


def test_a_switch_symbol_with_joined_pads_is_read_from_its_drawing():
    assert SYMS["TS-1187A-B-A-B"]["joined"] == [["3", "4"], ["1", "2"]] or SYMS["TS-1187A-B-A-B"]["joined"] == [["1", "2"], ["3", "4"]]
    assert SYMS["0603WAF1001T5E"]["joined"] == [] and SYMS["RP2040"]["joined"] == []


def test_the_second_pad_of_a_joined_pair_gets_the_net_of_its_listed_pad():
    part, sym = _sw([("1", "BOOT"), ("3", "GND")])
    pins, warn, errors = draw.pin_nets(part, sym)
    got = {lp["number"]: net for lp, net in pins}
    assert got == {"1": "BOOT", "2": "BOOT", "3": "GND", "4": "GND"} and not errors
    assert any("joined to pin 1" in w and "same net BOOT" in w for w in warn)
    assert not any("left unconnected" in w for w in warn)


def test_unlisted_pads_of_a_pair_nobody_lists_are_no_erc_with_a_note_not_open_stubs():
    part, sym = _sw([("1", "BOOT"), ("2", "BOOT")])          # one terminal listed twice; pads 3 and 4 are the other terminal
    pins, warn, _ = draw.pin_nets(part, sym)
    got = {lp["number"]: net for lp, net in pins}
    assert got["3"] == "NC" and got["4"] == "NC"
    p = draw.plan_sheet({"parts": [{**part, "section": ""}], "sections": []}, {"SW1": sym}, "l", "d")
    assert [c[0] for c in p["commands"]].count("NOERC") == 2 and sorted(p["no_erc"]) == ["SW1-3", "SW1-4"]
    assert any("marked No ERC" in w for w in p["warnings"])


def test_the_evidence_switches_give_two_notes_not_eight_warnings():
    p, sh = planned("Periph")
    sw = [w for w in p["warnings"] if w.startswith(("SW1", "SW2"))]
    assert not [w for w in sw if "is called" in w]                # no "1 in the netlist and A in the library" noise
    assert not [w for w in sw if "left unconnected" in w]
    assert len([w for w in sw if "marked No ERC" in w]) == 4 and len([w for w in sw if "one terminal" in w]) == 2
    assert sorted(x for x in p["no_erc"] if x.startswith("SW")) == ["SW1-3", "SW1-4", "SW2-3", "SW2-4"]


def test_a_symbol_with_twice_the_netlist_pins_and_no_drawing_info_marks_the_extra_pads_no_erc():
    sym = {"name": "SWX", "joined": None, "pins": [{"number": str(i), "name": "ABCD"[i - 1], "electrical": "Passive", "orientation": 0 if i % 2 else 2,
                                                  "x": 100 * (i % 2), "y": -100 * (i // 3), "length": 100, "part_id": 1} for i in range(1, 5)]}
    pins, warn, _ = draw.pin_nets({"ref": "SW9", "pins": [{"num": "1", "name": "1", "net": "A"}, {"num": "2", "name": "2", "net": "B"}]}, sym)
    assert {lp["number"]: n for lp, n in pins}["3"] == "NC" and any("duplicate pad" in w for w in warn)
    # an IC with an unlisted pin is not touched: the warning stays and nothing is drawn for it
    ic = {"name": "IC", "joined": [], "pins": [{**q, "electrical": "Input"} for q in sym["pins"]]}
    pins, warn, _ = draw.pin_nets({"ref": "U9", "pins": [{"num": "1", "name": "1", "net": "A"}, {"num": "2", "name": "2", "net": "B"}]}, ic)
    assert [lp["number"] for lp, _ in pins] == ["1", "2"] and any("left unconnected" in w for w in warn)


def _four_pads():
    return [{"number": str(i + 1), "x": x, "y": y, "electrical": "Passive"} for i, (x, y) in enumerate([(-100, 100), (100, 100), (-100, -200), (100, -200)])]


def _line(x1, y1, x2, y2):
    return {"RECORD": "6", "LOCATIONCOUNT": "2", "X1": str(x1 // 10), "Y1": str(y1 // 10), "X2": str(x2 // 10), "Y2": str(y2 // 10)}


def test_symbol_graphics_finds_the_body_and_only_pin_to_pin_lines_on_passive_symbols_of_four_or_more_pins():
    pins = _four_pads()
    box = {"RECORD": "14", "LOCATION.X": "-5", "LOCATION.Y": "-5", "CORNER.X": "5", "CORNER.Y": "5"}
    body, joined = symbol_graphics([_line(-100, 100, 100, 100), _line(-100, -200, 100, -200), box], pins)
    assert joined == [["1", "2"], ["3", "4"]] and body == (-100, -200, 100, 100)
    assert symbol_graphics([_line(-100, 100, 100, 100)], [{**p, "electrical": "Input"} for p in pins])[1] == []   # an IC's drawing
    assert symbol_graphics([box], pins) == ((-50, -50, 50, 50), [])
    assert symbol_graphics([], pins) == (None, None)                    # no drawing read: unknown, not "nothing joined"
    # lines that make pin 1 a member of two groups give no pairs at all for it
    assert symbol_graphics([_line(-100, 100, 100, 100), _line(-100, 100, -100, -200)], pins)[1] == []


def test_a_diode_or_fuse_drawn_as_a_line_between_its_two_pins_is_never_joined():
    two = [{"number": "1", "x": -100, "y": 0, "electrical": "Passive"}, {"number": "2", "x": 100, "y": 0, "electrical": "Passive"}]
    assert symbol_graphics([_line(-100, 0, 100, 0)], two)[1] == []
    sym = {"name": "FUSE", "joined": [["1", "2"]], "pins": [{**q, "name": q["number"], "orientation": 0, "length": 100, "part_id": 1} for q in two]}
    pins, warn, _ = draw.pin_nets({"ref": "F1", "pins": [{"num": "1", "name": "1", "net": "VIN"}]}, sym)
    assert [(lp["number"], n) for lp, n in pins] == [("1", "VIN")] and any("left unconnected" in w for w in warn)


def test_a_crystals_ground_pins_are_never_marked_no_erc_for_not_being_listed():
    xt = SYMS["X322512MSB4SI"]                      # the C9002 crystal: OSC1, GND, OSC2, GND
    part = {"ref": "Y1", "pins": [{"num": "1", "name": "OSC1", "net": "XIN"}, {"num": "3", "name": "OSC2", "net": "XOUT"}]}
    for sym in (xt, {**xt, "joined": None}):          # with a read drawing and with none (the count fallback must not take it)
        pins, warn, _ = draw.pin_nets(part, sym)
        assert sorted(lp["number"] for lp, _ in pins) == ["1", "3"] and not any(n == "NC" for _, n in pins)
        assert [w for w in warn if "left unconnected" in w and w.startswith("Y1")] and not any("No ERC" in w for w in warn)
    p = draw.plan_sheet({"parts": [{**part, "section": ""}], "sections": []}, {"Y1": {**xt, "joined": None}}, "l", "d")
    assert p["no_erc"] == []
