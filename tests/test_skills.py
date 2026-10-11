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
    (d / "txs0104e.pdf.txt").write_text(
        " ".join(f"{p['num']} {p['name']}" for p in next(x for x in store.load_sheet(lte, "03")["parts"] if x["ref"] == "U5")["pins"]),
        encoding="utf-8")
    assert verify_part.verify(lte, "U5")["verify"] == "pass"


def test_verify_lists_the_pins_it_cannot_find(lte):
    d = store.pdir(lte) / "sources"
    (d / "txs0104e.pdf").write_bytes(b"x")
    (d / "txs0104e.pdf.txt").write_text("1 VCCA 2 A1", encoding="utf-8")
    res = verify_part.verify(lte, "U5")
    assert res["verify"] == "mismatch" and "pin 8 OE" in res["issues"]


def test_the_skills_page_lists_only_scripts_that_exist(lte):
    rows = {r["name"]: r for r in registry.listing()}
    assert rows["Check availability"]["available"]
    assert not rows["Download models"]["available"]
