"""
The skills the agent runs. They work on files in the project, so each is tested
against the seeded example; the network is replaced.
"""
import csv
import json

import check_availability
import compare_prices
import export_bom
import registry
import render_sheet
import store
import pintable
import verify_part


def test_compare_prices_reports_missing_lines_instead_of_pricing_them_at_zero(lte):
    out = {s["supplier"]: s for s in compare_prices.compare(lte)["suppliers"]}
    assert "D30" in out["LCSC"]["missing"]
    assert out["LCSC"]["cost_per_board"] > 0
    assert "U4" in out["Mouser"]["missing"]              # Mouser has none in stock


def test_export_leaves_out_unfitted_lines_and_says_so(lte):
    res = export_bom.export(lte, "pcbway")
    assert set(res["left_out"]) == {"C40", "TP"}
    path = store.pdir(lte) / "exports" / f"{lte}_BOM_pcbway.csv"
    rows = list(csv.reader(path.open(encoding="utf-8")))
    assert rows[0][:3] == ["Designator", "Qty", "MPN"]
    assert all("TP12" not in r[0] and "C40" not in r[0] for r in rows[1:])


def test_jlc_export_needs_an_lcsc_number_and_lists_the_lines_without(lte):
    assert "U5" in export_bom.export(lte, "jlc")["needs_lcsc"]
    store.add_supply(lte, "U5", "LCSC", 10, 0.4, "TXS0104EPWR", source="LCSC C44955")
    assert "U5" not in export_bom.export(lte, "jlc")["needs_lcsc"]


def test_every_ref_is_in_the_rendered_sheet(lte):
    svg = render_sheet.render(lte, "03", write=False)
    refs = [p["ref"] for p in store.load_sheet(lte, "03")["parts"]]
    for ref in refs:
        assert f'data-ref="{ref}"' in svg, ref
    assert svg.startswith("<svg") and "No ERC" in svg


def test_the_sheet_label_follows_the_bom(lte):
    store.edit_bom(lte, "U5", "mpn", "TXS0104EPW")
    assert "TXS0104EPW<" in render_sheet.render(lte, "03", write=False)


def test_hebrew_and_markup_in_a_netlist_are_escaped(lte):
    sheet = {"title": "<b>x</b>", "parts": [{"ref": "U5", "kind": "ic", "pins": [
        {"name": "<script>", "num": "1", "net": "NET&1"}]}]}
    svg = render_sheet.render_sheet(sheet, store.bom(lte, write=False))
    assert "<script>" not in svg and "NET&amp;1" in svg


def test_availability_stores_stock_with_a_time_and_the_part_number(lte, monkeypatch):
    monkeypatch.setattr(check_availability, "jlc_search", lambda kw, n=10: [
        {"componentModelEn": "TXS0104EPWR", "stockCount": 777, "componentCode": "C44955",
         "componentPrices": [{"startNumber": 1, "endNumber": -1, "productPrice": 0.37}]}])
    monkeypatch.delenv("MOUSER_API_KEY", raising=False)
    out = check_availability.check(lte, {"U5"})
    assert out == [{"line": "U5", "supplier": "LCSC", "mpn": "TXS0104EPWR", "stock": 777,
                    "price": 0.37, "code": "C44955", "exact": True}]
    s = {l["key"]: l for l in store.bom(lte)}["U5"]["supply"]["LCSC"]
    assert s["stock"] == 777 and s["checked_at"] and "C44955" in s["source"]


def test_availability_survives_a_supplier_being_down(lte, monkeypatch):
    def boom(kw, n=10):
        raise OSError("offline")
    monkeypatch.setattr(check_availability, "jlc_search", boom)
    out = check_availability.check(lte, {"U5"})
    assert out[0]["error"] == "offline"
    assert {l["key"]: l for l in store.bom(lte)}["U5"]["supply"]["LCSC"]["stock"] == 12400   # unchanged


def test_availability_skips_lines_that_are_not_bought(lte, monkeypatch):
    monkeypatch.setattr(check_availability, "jlc_search", lambda kw, n=10: [])
    assert check_availability.check(lte, {"TP", "C40"}) == []


def test_verify_without_the_datasheet_says_unchecked_and_unaccepts(lte):
    res = verify_part.verify(lte, "U5")
    assert res["verify"] == "unchecked"
    row = {r["line"]: r for r in store.library_view(lte)}["U5"]
    assert row["status"] == "review" and not row["accepted"]


def test_verify_finds_pins_in_the_datasheet_text(lte):
    d = store.pdir(lte) / "sources"
    (d / "txs0104e.pdf").write_bytes(b"x")
    pins = next(x for x in store.load_sheet(lte, "03")["parts"] if x["ref"] == "U5")["pins"]
    (d / "txs0104e.pdf.txt").write_text(
        "TXS0104E 4-bit level shifter\nTable 5-3. Pin Functions\nPIN\nNAME NO. TYPE DESCRIPTION\n"
        + "".join(f"{p['name']} {p['num']} I/O Description of {p['name']}\n" for p in pins), encoding="utf-8")
    res = verify_part.verify(lte, "U5")
    assert res["verify"] == "pass", res


def test_verify_lists_the_pins_it_cannot_find(lte):
    d = store.pdir(lte) / "sources"
    (d / "txs0104e.pdf").write_bytes(b"x")
    pins = next(x for x in store.load_sheet(lte, "03")["parts"] if x["ref"] == "U5")["pins"]
    (d / "txs0104e.pdf.txt").write_text(
        "TXS0104E 4-bit level shifter\nPin Functions\nPIN NAME TYPE\n"
        + "".join(f"{p['num']} {'GND' if p['num'] == '8' else p['name']} I/O Description\n" for p in pins), encoding="utf-8")
    res = verify_part.verify(lte, "U5")
    assert res["verify"] == "mismatch" and "pin 8 OE" in res["issues"] and "GND" in res["issues"]


def test_a_short_pin_name_matches_the_datasheet_long_one():
    # the sheet's 555 calls pin 4 RST, TI's pin table RESET: the same pin, not a mismatch
    assert pintable.name_matches("RST", "RESET")
    assert pintable.name_matches("~RST", "RESET") and pintable.name_matches("nRESET", "RESET")
    assert pintable.name_matches("RESET_n", "RESET") and pintable.name_matches("RESET", "RST")
    assert not pintable.name_matches("RST", "OUT")   # an alias never stands in for a different function


def test_an_alias_matches_only_a_whole_word():
    # before the aliases each of these failed, and a wrong pin number must still fail
    for cell, name in [("drain", "ENABLE"), ("dissipation", "DISCH"), ("through-hole", "THRESHOLD"), ("without", "OUTPUT"),
                       ("contents", "CONTROL"), ("does", "nOE"), ("lower", "~WE")]:
        assert not pintable.name_matches(name, cell), name


def test_a_mark_alone_is_not_a_name():
    assert pintable.pinnames.spellings("~") == set() and not pintable.name_matches("~", "VCC")


def test_the_skills_page_lists_only_scripts_that_exist(lte):
    rows = {r["name"]: r for r in registry.listing()}
    assert rows["Check availability"]["available"]
    assert not rows["Download models"]["available"]


def test_the_skills_page_lists_export_cpl():
    rows = {r["name"]: r for r in registry.listing()}
    row = rows["Export CPL (pick and place) for JLC"]
    assert row["script"] == "export_cpl.py" and row["available"]


def test_the_manufacturing_skill_makes_the_cpl_before_naming_it():
    """The live mistake: the student was told to upload a CPL that was never written."""
    import pathlib
    text = (pathlib.Path(__file__).resolve().parent.parent / "runtime" / "skills" / "manufacturer-and-dfm" / "SKILL.md").read_text(encoding="utf-8")
    assert "export_cpl.py" in text and "Produce the files before naming them" in text and "No CPL file: say so, never name one" in text


def test_a_netlist_without_kinds_draws_parts_by_their_designator():
    """Blinker 555, 16/11: the agent wrote no "kind", and capacitors, the LED and the header were drawn as resistors."""
    from skills import render_sheet as rs
    two = [{"name": "1", "num": "1", "net": "A"}, {"name": "2", "num": "2", "net": "GND"}]
    kinds = {ref: rs.part_kind({"ref": ref, "pins": two}) for ref in ("C1", "D1", "LED2", "J1", "P3", "TP1", "R1", "L1")}
    assert kinds == {"C1": "cap", "D1": "diode", "LED2": "diode", "J1": "conn", "P3": "conn", "TP1": "tp", "R1": "res", "L1": "res"}
    assert rs.part_kind({"ref": "X1", "pins": two * 2}) == "ic" and rs.part_kind({"ref": "D1", "kind": "led", "pins": two}) == "diode"
    assert rs.part_kind({"ref": "C1", "kind": "res", "pins": two}) == "res"           # a kind written wins


def test_a_diode_listed_cathode_first_is_drawn_anode_on_top():
    from skills import render_sheet as rs
    ka = {"ref": "D1", "pins": [{"name": "K", "num": "1", "net": "GND"}, {"name": "A", "num": "2", "net": "LED_A"}]}
    ak = {"ref": "D1", "pins": [{"name": "A", "num": "2", "net": "LED_A"}, {"name": "K", "num": "1", "net": "GND"}]}
    assert rs.render_part(ka, None, None)[0] == rs.render_part(ak, None, None)[0]


def test_a_clamp_diode_keeps_its_rail_on_top_and_points_up():
    from skills import render_sheet as rs
    clamp = {"ref": "D3", "pins": [{"name": "K", "num": "1", "net": "VBUS"}, {"name": "A", "num": "2", "net": "GND"}]}
    svg = rs.render_part(clamp, None, None)[0]
    assert "VBUS" in svg
    assert '<polygon points="52,50 68,50 60,36"' in svg                   # apex up, at the cathode on top
    assert rs.part_kind({"ref": "TP1", "pins": []}) == "q"                  # no pins: not a test point drawing
    wide = {"ref": "D1", "pins": [{"name": str(i), "num": str(i), "net": f"N{i}"} for i in range(6)]}
    sec = rs.layout_section({"id": "A"}, [wide], [], {})
    assert sec is not None
