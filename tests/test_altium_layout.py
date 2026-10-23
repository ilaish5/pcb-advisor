"""altium.place_pcb planning: pure Python (scripts/altium/layout.py)."""
from altium import layout

MIL = 0.0254


def fp(name, pads):
    """pads: [(name, x_mm, y_mm, w_mm, h_mm)]"""
    return {"name": name, "pads": [{"name": n, "x": x / MIL, "y": y / MIL, "xsize": w / MIL, "ysize": h / MIL, "layer": 1} for n, x, y, w, h in pads]}


FPS = {"R0603": fp("R0603", [("1", -0.8, 0, 0.8, 0.9), ("2", 0.8, 0, 0.8, 0.9)]),
       "C0402": fp("C0402", [("1", -0.5, 0, 0.6, 0.6), ("2", 0.5, 0, 0.6, 0.6)]),
       "QFN": fp("QFN", [(str(i + 1), -2 + i, -2, 0.3, 0.8) for i in range(5)] + [("6", 2, 2, 0.3, 0.8)]),
       "HDR": fp("HDR", [("1", 0, -1.27, 1.7, 1.7), ("2", 0, 1.27, 1.7, 1.7)])}


def part(ref, footprint, nets):
    return {"ref": ref, "footprint": footprint, "pins": [{"num": str(i + 1), "net": n} for i, n in enumerate(nets)]}


PARTS = [part("J1", "HDR", ["+5V", "GND"]),
         part("U1", "QFN", ["+3V3", "GND", "SDA", "SCL", "X", "NC"]),
         part("C1", "C0402", ["+3V3", "GND"]),
         part("C2", "C0402", ["+3V3", "GND"]),
         part("R1", "R0603", ["SDA", "+3V3"]),
         part("R2", "R0603", ["SCL", "+3V3"]),
         part("R3", "R0603", ["Q", "GND"])]
OUT = [0, 0, 40, 30]


def boxes(plan):
    return {p["ref"]: layout._moved(layout.rot_box(layout.footprint_box(FPS[p["footprint"]]), p["rot"]), p["x"], p["y"])
            for p in plan["places"]}


def dist(at, a, b):
    return ((at[a]["x"] - at[b]["x"]) ** 2 + (at[a]["y"] - at[b]["y"]) ** 2) ** 0.5


def test_board_size_from_requirement_text_and_explicit():
    idea = {"requirements": [{"id": "A", "topic": "x", "text": "Mains 230 V"},
                             {"id": "NFR-3", "topic": "Size", "text": "A single board, 100 x 80 mm with 4 M3 holes"}]}
    assert layout.board_size(idea) == (100.0, 80.0)
    assert layout.board_size({"board": {"width_mm": 50, "height_mm": 30}, **idea}) == (50.0, 30.0)
    assert layout.board_size({"requirements": [{"topic": "Power", "text": "5 x 7 mm part"}]}) is None
    assert layout.board_size({}) is None


def test_outline_limits():
    assert layout.plan_outline((100, 80)) == [0.0, 0.0, 100.0, 80.0]
    assert layout.plan_outline((5, 80)) is None
    assert layout.plan_outline(None) is None


def test_net_kinds():
    assert layout.is_gnd("AGND") and layout.is_gnd("GND") and not layout.is_gnd("SDA")
    assert layout.is_rail("+3V3") and layout.is_rail("VDD") and not layout.is_rail("GND")


def test_every_part_placed_inside_without_overlap():
    plan = layout.plan_placement(PARTS, FPS, OUT)
    assert not plan["errors"], plan
    assert {p["ref"] for p in plan["places"]} == {p["ref"] for p in PARTS}
    b = boxes(plan)
    for r, box in b.items():
        assert layout._inside(box, OUT, 0), r
    refs = sorted(b)
    for i, r in enumerate(refs):
        for o in refs[i + 1:]:
            assert not layout._hit(b[r], b[o], layout.GAP_MM - 1e-6), (r, o)


def test_connector_is_on_an_edge_turned_out():
    plan = layout.plan_placement(PARTS, FPS, OUT, connector_dirs={"J1": 0})
    box = boxes(plan)["J1"]
    assert box[0] <= OUT[0] + 0.06 or box[2] >= OUT[2] - 0.06 or box[1] <= OUT[1] + 0.06 or box[3] >= OUT[3] - 0.06
    assert not [w for w in plan["warnings"] if "J1" in w]          # direction was given: no 3D warning
    assert [w for w in layout.plan_placement(PARTS, FPS, OUT)["warnings"] if "J1" in w]


def test_decap_sits_close_to_the_supply_pin():
    plan = layout.plan_placement(PARTS, FPS, OUT)
    at = {p["ref"]: p for p in plan["places"]}
    assert dist(at, "C1", "U1") < 8 and dist(at, "C2", "U1") < 8


def test_signal_partners_end_up_near_each_other():
    plan = layout.plan_placement(PARTS, FPS, OUT)
    at = {p["ref"]: p for p in plan["places"]}
    assert dist(at, "R1", "U1") < 12 and dist(at, "R2", "U1") < 12


def test_refuses_when_parts_do_not_fit():
    plan = layout.plan_placement(PARTS, FPS, [0, 0, 9, 9])
    assert plan["errors"] and not plan["places"]


def test_refuses_a_missing_footprint():
    plan = layout.plan_placement(PARTS + [part("X1", "NOPE", ["A"])], FPS, OUT)
    assert any("X1" in e and "NOPE" in e for e in plan["errors"])


def test_clearance_rule_widens_the_gap():
    b = layout.plan_placement(PARTS, FPS, OUT, clearance_mm=1.5)
    assert not b["errors"]
    bx = boxes(b)
    refs = sorted(bx)
    for i, r in enumerate(refs):
        for o in refs[i + 1:]:
            assert not layout._hit(bx[r], bx[o], 1.5 - 1e-6), (r, o)


def test_kept_parts_do_not_move_and_are_obstacles():
    first = layout.plan_placement(PARTS, FPS, OUT)
    keep = {p["ref"]: (p["x"], p["y"], p["rot"]) for p in first["places"] if p["ref"] in ("U1", "J1")}
    again = layout.plan_placement(PARTS, FPS, OUT, keep=keep)
    assert not again["errors"]
    assert {p["ref"] for p in again["places"]} == {p["ref"] for p in PARTS} - {"U1", "J1"}


def test_commands_link_the_part_and_give_pad_nets():
    plan = layout.plan_placement(PARTS, FPS, OUT)
    cmds = layout.plan_commands("a.PcbDoc", OUT, True, plan["places"], FPS, PARTS, "lib.PcbLib")
    assert cmds[0] == ("PCBBEGIN", "a.PcbDoc", "0")
    assert cmds[1][:2] == ("OUTLINE", "a.PcbDoc") and cmds[-1] == ("PCBSAVE", "a.PcbDoc")
    assert sum(c[0] == "PLACEFP" for c in cmds) == len(PARTS)
    assert ("PADNET", "a.PcbDoc", "U1", "3", "SDA") in cmds
    assert not any(c[0] == "PADNET" and c[4] == "NC" for c in cmds)
    assert layout.plan_commands("a", OUT, False, [], FPS, PARTS, "l", replace=True)[0][2] == "1"


def test_non_ascii_names_refused():
    assert layout.text_problems([part("R1", "R0603", ["Nét", "GND"])])
    assert not layout.text_problems(PARTS)


def pcb(nets_by_pad, tracks=(), vias=()):
    return {"components": [{"ref": r, "pattern": "R0603"} for r in sorted({k[0] for k in nets_by_pad})],
            "pads": [{"ref": r, "name": n, "net": net, "layer": 1, "x_mm": x, "y_mm": y, "sx_mm": 1, "sy_mm": 1}
                     for (r, n), (net, x, y) in nets_by_pad.items()],
            "tracks": [dict(layer=1, net=n, x1_mm=a, y1_mm=b, x2_mm=c, y2_mm=d, width_mm=0.2) for n, a, b, c, d in tracks],
            "vias": list(vias), "arcs": []}


def test_unrouted_counts_open_nets_and_sees_routes():
    pads = {("R1", "1"): ("A", 0, 0), ("R2", "1"): ("A", 10, 0), ("R3", "1"): ("A", 10, 10),
            ("R1", "2"): ("B", 0, 5), ("R2", "2"): ("B", 10, 5)}
    assert [n for n, _ in layout.unrouted(pcb(pads))] == ["A", "B"]
    assert layout.unrouted(pcb(pads, tracks=[("A", 0, 0, 10, 0), ("A", 10, 0, 10, 10), ("B", 0, 5, 10, 5)])) == []
    assert [n for n, _ in layout.unrouted(pcb(pads, tracks=[("A", 0, 0, 10, 0), ("B", 0, 5, 10, 5)]))] == ["A"]


def test_unrouted_layer_change_needs_a_via():
    pads = {("R1", "1"): ("A", 0, 0), ("R2", "1"): ("A", 10, 0)}
    d = pcb(pads, tracks=[("A", 0, 0, 5, 0)])
    d["tracks"].append(dict(layer=32, net="A", x1_mm=5, y1_mm=0, x2_mm=10, y2_mm=0, width_mm=0.2))
    d["pads"][1]["layer"] = 32
    assert layout.unrouted(d)
    d["vias"] = [{"net": "A", "x_mm": 5, "y_mm": 0, "dia_mm": 0.6}]
    assert layout.unrouted(d) == []


def test_verify_layout_finds_wrong_footprint_net_and_overlap():
    plan_parts = [part("R1", "R0603", ["A", "GND"]), part("R2", "R0603", ["A", "NC"])]
    ok = pcb({("R1", "1"): ("A", 0, 0), ("R1", "2"): ("GND", 2, 0), ("R2", "1"): ("A", 10, 0), ("R2", "2"): (None, 12, 0)})
    assert layout.verify_layout(ok, plan_parts, [-5, -5, 20, 5]) == []
    bad = pcb({("R1", "1"): ("B", 0, 0), ("R1", "2"): ("GND", 2, 0), ("R2", "1"): ("A", 1, 0), ("R2", "2"): (None, 3, 0)})
    bad["components"][0]["pattern"] = "R0402"
    out = " | ".join(layout.verify_layout(bad, plan_parts, [-5, -5, 20, 5]))
    assert "R1-1 is on net B" in out and "overlap" in out and "footprint" in out
    missing = pcb({("R1", "1"): ("A", 0, 0), ("R1", "2"): ("GND", 2, 0)})
    assert any("R2 is not on the saved board" in p for p in layout.verify_layout(missing, plan_parts))


def test_occupied_reports_parts_and_copper():
    refs, n = layout.occupied(pcb({("R1", "1"): ("A", 0, 0)}, tracks=[("A", 0, 0, 1, 1)]))
    assert refs == ["R1"] and n == 1


# ---- the real extent of a part: pads + silkscreen + courtyard + 3D body (a connector body is far bigger than its pads)

def big_fp():
    """A USB-C like connector: pads in one row, a shell (silk/mech/body outline) reaching 5 mm beyond them on -y, body over the pads."""
    f = fp("USBC", [("1", -2, 2.4, 0.3, 1.3), ("2", 2, 2.4, 0.3, 1.3), ("S1", -4.3, -1, 1.2, 2.0), ("S2", 4.3, -1, 1.2, 2.0)])
    f["extent"] = {"silk": [-4.5 / MIL, -5.1 / MIL, 4.5 / MIL, 2.8 / MIL], "mech": [-4.5 / MIL, -5.1 / MIL, 4.5 / MIL, 2.3 / MIL],
                   "body": [-4.5 / MIL, -2.6 / MIL, 4.5 / MIL, 5.3 / MIL]}
    return f


BIG = dict(FPS, USBC=big_fp())
BIG_PARTS = [part("J1", "USBC", ["+5V", "GND", "CC", "GND"]), part("R1", "R0603", ["CC", "GND"]), part("R2", "R0603", ["CC", "+5V"]),
             part("R3", "R0603", ["+5V", "X"])]


def real(plan, ref):
    p = next(p for p in plan["places"] if p["ref"] == ref)
    return layout._moved(layout.rot_box(layout.footprint_extent(BIG[p["footprint"]]), p["rot"]), p["x"], p["y"])


def test_footprint_extent_is_bigger_than_the_pads():
    e = layout.footprint_extent(big_fp())
    assert e[1] <= -5.0 and e[3] >= 5.2 and e[0] <= -4.4 and e[2] >= 4.4
    assert layout.pads_box(big_fp())[3] < 3.1


def test_opening_is_read_from_the_outline_not_assumed():
    assert layout.opening_dir(big_fp()) == 270            # the silkscreen reaches far on -y: the plug end
    assert layout.opening_dir(FPS["HDR"]) is None         # no outline: cannot tell


def test_small_parts_keep_clear_of_a_big_connector_body():
    """The board of the screenshot: J1 body covered R1, R2, R3 because only its pads were counted."""
    plan = layout.plan_placement(BIG_PARTS, BIG, [0, 0, 40, 30])
    assert not plan["errors"], plan
    j = real(plan, "J1")
    for r in ("R1", "R2", "R3"):
        assert not layout._hit(j, real(plan, r), layout.GAP_MM - 1e-6), r
    for r in ("J1", "R1", "R2", "R3"):
        assert layout._inside(real(plan, r), [0, 0, 40, 30], -1e-6), r


def test_connector_opens_out_with_pads_off_the_edge_and_body_inside():
    plan = layout.plan_placement(BIG_PARTS, BIG, [0, 0, 40, 30])
    j = next(p for p in plan["places"] if p["ref"] == "J1")
    box = real(plan, "J1")
    assert j["rot"] == 0 and 0 <= box[1] <= 0.5          # opening (-y) at the bottom edge, nothing outside
    pads = layout._moved(layout.rot_box(layout.pads_box(BIG["USBC"]), j["rot"]), j["x"], j["y"])
    assert pads[1] >= layout.EDGE_COPPER_MM - 1e-6       # pad copper keeps the edge clearance
    assert abs((box[0] + box[2]) / 2 - 20) < 1.0         # centred along its edge, not in the corner


def test_parts_use_the_board_not_one_corner():
    plan = layout.plan_placement(BIG_PARTS, BIG, [0, 0, 60, 40])
    xs = [p["x"] for p in plan["places"] if p["ref"] != "J1"]
    assert min(xs) > 10 and max(xs) < 50                 # drawn towards the middle of a roomy board


def test_designators_are_small_and_outside_every_pad():
    plan = layout.plan_placement(BIG_PARTS, BIG, [0, 0, 40, 30])
    pads = []
    for p in plan["places"]:
        pb = layout._moved(layout.rot_box(layout.pads_box(BIG[p["footprint"]]), p["rot"]), p["x"], p["y"])
        pads.append((p["ref"], pb))
    labels = {}
    for p in plan["places"]:
        w, h = layout.label_size(p["ref"])
        assert p["label_h"] <= 1.0
        labels[p["ref"]] = [p["label"][0] - w / 2, p["label"][1] - h / 2, p["label"][0] + w / 2, p["label"][1] + h / 2]
        assert layout._inside(labels[p["ref"]], [0, 0, 40, 30], -1e-6)
    for ref, lb in labels.items():
        assert not any(layout._hit(lb, pb, 0) for _, pb in pads), ref
    refs = sorted(labels)
    for i, a in enumerate(refs):
        for b in refs[i + 1:]:
            assert not layout._hit(labels[a], labels[b], 0)


def saved(parts, texts=None):
    """A saved-board dict: parts = [(ref, x, y, rot, body_bbox)] each with two pads 1 mm apart."""
    doc = {"components": [], "pads": [], "texts": texts if texts is not None else []}
    for ref, x, y, rot, body in parts:
        doc["components"].append({"ref": ref, "pattern": "R0603", "x_mm": x, "y_mm": y, "rotation": rot, "body_bbox_mm": body, "outline_bbox_mm": None})
        for k, dx in (("1", -0.5), ("2", 0.5)):
            doc["pads"].append({"ref": ref, "name": k, "net": "N" + k, "x_mm": x + dx, "y_mm": y, "sx_mm": 0.6, "sy_mm": 0.6, "rot": 0})
    return doc


PP = [{"ref": "J1", "footprint": "R0603", "pins": [{"num": "1", "net": "N1"}, {"num": "2", "net": "N2"}]},
      {"ref": "R1", "footprint": "R0603", "pins": [{"num": "1", "net": "N1"}, {"num": "2", "net": "N2"}]}]


def test_verify_fails_when_a_small_part_sits_inside_the_connector_body():
    """The old verify said [] here: the pad boxes are 1.6 mm apart, but the saved 3D body of J1 covers R1."""
    doc = saved([("J1", 10, 10, 0, [5, 5, 15, 15]), ("R1", 12, 12, 0, None)])
    out = " | ".join(layout.verify_layout(doc, PP, [0, 0, 40, 30]))
    assert "J1 and R1 overlap" in out
    ok = saved([("J1", 10, 10, 0, [5, 5, 15, 15]), ("R1", 25, 12, 0, None)])
    assert not [p for p in layout.verify_layout(ok, PP, [0, 0, 40, 30]) if "overlap" in p]


def test_verify_outline_overhang_only_for_a_connector_on_one_side():
    doc = saved([("J1", 20, 10, 0, [15, -0.8, 25, 6]), ("R1", 25, 12, 0, [24, 11, 26, 13])])
    assert not [p for p in layout.verify_layout(doc, PP, [0, 0, 40, 30]) if "sticks out" in p]          # 0.8 mm mating-face overhang
    doc = saved([("J1", 20, 10, 0, [15, -3, 25, 6]), ("R1", 25, 12, 0, [24, 11, 26, 13])])
    assert any("J1 sticks out" in p for p in layout.verify_layout(doc, PP, [0, 0, 40, 30]))              # the whole body outside
    doc = saved([("J1", 20, 10, 0, None), ("R1", 25, 12, 0, [24, 11, 26, 40])])
    assert any("R1 sticks out" in p for p in layout.verify_layout(doc, PP, [0, 0, 40, 30]))              # only connectors may


def test_verify_pad_too_close_to_the_edge():
    doc = saved([("J1", 20, 10, 0, None), ("R1", 0.4, 12, 0, None)])
    assert any("R1-1" in p and "board edge" in p for p in layout.verify_layout(doc, PP, [0, 0, 40, 30]))


def test_verify_designators():
    h = {"kind": "designator", "height_mm": 1.0, "rotation": 0}
    doc = saved([("J1", 10, 10, 0, None), ("R1", 25, 12, 0, None)],
                texts=[dict(h, text="J1", x_mm=9.7, y_mm=9.8), dict(h, text="R1", x_mm=24.0, y_mm=13.5)])
    out = " | ".join(layout.verify_layout(doc, PP, [0, 0, 40, 30]))
    assert "designator J1 is over pad J1-1" in out and "designator R1" not in out
    doc["texts"] = [dict(h, text="J1", x_mm=9.7, y_mm=12.0), dict(h, text="R1", x_mm=9.9, y_mm=12.2)]
    assert any("designators J1 and R1 overlap" in p for p in layout.verify_layout(doc, PP, [0, 0, 40, 30]))
    doc["texts"] = [dict(h, text="J1", x_mm=9.7, y_mm=12.0, height_mm=3.0), dict(h, text="R1", x_mm=24.0, y_mm=14.0)]
    assert any("3 mm high" in p for p in layout.verify_layout(doc, PP, [0, 0, 40, 30]))


def test_verify_every_pad_of_a_shared_number_and_the_plan():
    doc = saved([("J1", 10, 10, 0, None), ("R1", 25, 12, 0, None)])
    doc["pads"].append({"ref": "R1", "name": "2", "net": "OTHER", "x_mm": 25.5, "y_mm": 13, "sx_mm": 0.6, "sy_mm": 0.6, "rot": 0})
    out = " | ".join(layout.verify_layout(doc, PP, [0, 0, 40, 30]))
    assert "R1-2 is on net OTHER" in out                 # a second pad with the same number is not hidden by the first
    plan = [{"ref": "J1", "x": 10, "y": 10, "rot": 0}, {"ref": "R1", "x": 26, "y": 12, "rot": 90}]
    out = " | ".join(layout.verify_layout(saved([("J1", 10, 10, 0, None), ("R1", 25, 12, 0, None)]), PP, [0, 0, 40, 30], places=plan))
    assert "R1 sits at (25, 12) turned 0, the plan says (26, 12) turned 90" in out


# The relevant fields of the real Blink-555 idea.json (the size was only in goal and agreed, in Hebrew, "30x25 מ\"מ").
BLINK_555 = {
    "goal": "כרטיס הבהוב מבוסס טיימר NE555 בתצורת astable, מוזן מ-USB-C (5V), מהבהב LED אדום בתדר של כ-1Hz. גודל מוערך 30x25 מ\"מ, 2 שכבות, הרכבת SMT ב-JLCPCB.",
    "agreed": [
        {"topic": "Power", "text": "הזנת 5V מחיבור USB-C (Power only עם נגדי 5.1kΩ CC ל-GND) (assumed)"},
        {"topic": "Frequency & Duty Cycle", "text": "תדר הבהוב של כ-1Hz, אסימטרי קל (~60% ON) ללא דיודה נוספת (assumed)"},
        {"topic": "PCB & Assembly", "text": "כרטיס 2 שכבות, כ-30x25 מ\"מ, רכיבי SMT צד עליון בלבד להרכבה ב-JLCPCB (assumed)"},
    ],
}


def test_board_size_real_blink_555_idea():
    assert layout.board_size(BLINK_555) == (30.0, 25.0)
    assert layout.board_size({"goal": BLINK_555["goal"]}) == (30.0, 25.0)
    assert layout.board_size({"agreed": BLINK_555["agreed"]}) == (30.0, 25.0)


def test_board_size_units_separators_and_languages():
    def req(text, topic="Board"):
        return {"requirements": [{"topic": topic, "text": text}]}
    assert layout.board_size(req("כרטיס קטן, בערך 30 על 25 מ\"מ, שני שכבות", "")) == (30.0, 25.0)
    assert layout.board_size(req("גודל 30×25 מ״מ")) == (30.0, 25.0)
    assert layout.board_size(req("מידות: 40 X 20 ממ", "")) == (40.0, 20.0)
    assert layout.board_size(req("size 3,5 x 2 cm")) == (35.0, 20.0)
    assert layout.board_size(req("לוח 5 על 4 ס\"מ", "")) == (50.0, 40.0)
    assert layout.board_size(req("board 45.5 by 30.25 mm", "")) == (45.5, 30.25)
    assert layout.board_size({"describe": "small board, 30*25 mm, 2 layers"}) == (30.0, 25.0)
    assert layout.board_size(req("30mm x 25mm", "PCB")) == (30.0, 25.0)
    assert layout.board_size({"board": {"width_mm": 50, "height_mm": 30}, **BLINK_555}) == (50.0, 30.0)


def test_board_size_ignores_numbers_that_are_not_a_size():
    for text in ("USB-C 5V, blink at 1Hz, 47k resistor", "גודל קטן, 2x LED, 5V", "R1 10k x 2 pieces, size small",
                 "5 x 7 mm part", "כרטיס 2 שכבות, 1.6 מ\"מ עובי", "נגד 47k על 5V"):
        assert layout.board_size({"requirements": [{"topic": "Board", "text": text}], "goal": text}) is None, text
    assert layout.board_size({"goal": "LED 20x15"}) is None
    assert layout.board_size({}) is None


def test_board_size_word_rules_and_mixed_units():
    def req(text, topic=""):
        return {"requirements": [{"topic": topic, "text": text}]}
    # "size" alone is not the board: an OLED has a size too
    assert layout.board_size(req("OLED size 128x64 pixels", "Display")) is None
    assert layout.board_size(req("OLED 128x64 size")) is None
    # Hebrew words count only as whole words: "במידה ו" is "if", "לוח זמנים" is a schedule
    assert layout.board_size(req("במידה ו-40x30 מתאים נשתמש בו")) is None
    assert layout.board_size(req("לוח זמנים 40x30 מ\"מ")) is None
    assert layout.board_size(req("הכרטיס 40x30 מ\"מ")) == (40.0, 30.0)
    assert layout.board_size(req("בלוח 40 על 30 מ\"מ")) == (40.0, 30.0)
    # each number has its own unit
    assert layout.board_size(req("board 30mm x 2.5cm")) == (30.0, 25.0)
    assert layout.board_size(req("board 3cm x 25mm")) == (30.0, 25.0)
    assert layout.board_size(req("board 3 x 2.5 cm")) == (30.0, 25.0)
