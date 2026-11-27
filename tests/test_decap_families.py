"""R2 / W22: every entry of the cited decoupling-family table names a file of the general sources, a page that exists, and every value of the entry is
confirmed by the text of that page. An entry that cannot be confirmed does not belong in the table (its pins are "not checked")."""
import json
import re

import pytest

import decap_requirements as dr

ENTRIES = [(f["id"], g["pin"], s) for f in json.loads(dr.TABLE.read_text(encoding="utf-8"))["families"] for g in f["groups"] for s in g["schemes"]]


def test_the_table_is_valid_json_with_a_families_list():
    assert isinstance(json.loads(dr.TABLE.read_text(encoding="utf-8"))["families"], list)


@pytest.mark.parametrize("fam, pin, scheme", ENTRIES or [pytest.param(None, None, None, marks=pytest.mark.skip(reason="no entry confirmed from a file yet"))])
def test_each_entry_is_confirmed_by_its_cited_page(fam, pin, scheme):
    cite = scheme["cite"]
    assert cite.get("file") and cite.get("page"), "an entry cites a file and a page"
    assert (dr.TABLE.parent / cite["file"]).is_file(), f"{fam}: the cited file is not in the general sources"
    text = dr.page_text(cite)
    assert text is not None, f"{fam}: page {cite['page']} of {cite['file']} does not exist"
    if cite.get("figure"):
        assert cite["figure"].lower() in text.lower()
    slots = scheme.get("per_pin", []) + scheme.get("per_device", [])
    assert len(cite.get("confirm", [])) >= len(slots), "one confirm pattern per value of the entry"
    for rx in cite["confirm"]:
        assert re.search(rx, text, re.I), f"{fam}: the page does not confirm {rx}"


def test_the_page_checker_opens_a_text_file_by_form_feed_pages_and_refuses_a_missing_page(tmp_path):
    f = tmp_path / "doc.txt"
    f.write_text("page one\fFigure 3. Power supply scheme: VDD 100 nF\f", encoding="utf-8")
    assert "Figure 3" in dr.page_text({"file": "doc.txt", "page": 2}, root=tmp_path)
    assert dr.page_text({"file": "doc.txt", "page": 9}, root=tmp_path) is None
    assert dr.page_text({"file": "gone.txt", "page": 1}, root=tmp_path) is None


def test_an_entry_cannot_be_looked_up_without_a_matching_part_number(monkeypatch):
    fam = {"id": "f", "match": "^ABC", "groups": [{"pin": "^VDD$", "schemes": [{"per_pin": [{"role": "hf", "farads": 1e-7}],
                                                                              "cite": {"file": "a.md", "page": 3, "figure": "Figure 1"}}]}]}
    monkeypatch.setitem(dr._cache, "t", [fam])
    assert dr.requirement("VDD", "ABC123")["schemes"][0]["why"] == "a.md, page 3, Figure 1"
    assert dr.requirement("VDD", "XYZ1") is None and dr.requirement("VDD", "") is None and dr.requirement("VDDA", "ABC123") is None
