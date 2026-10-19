"""Never block, verify later: a partial sheet is always written and visible; the gaps are warnings, marks and a Final checks list."""
import json
import urllib.request

import pytest

import render_sheet
import store
from test_server import server  # noqa: F401  (the real handler on a port)


def _sheet(parts):
    return {"sections": [{"id": "A", "title": "T"}], "parts": parts}


def _u(ref, net="+3V3"):
    return {"ref": ref, "section": "A", "pins": [{"num": "1", "name": "VCC", "net": net}, {"num": "2", "name": "RESET", "net": ""}]}


def _propose(empty, ref, mpn="ABCD1234"):
    store.propose_bom(empty, ref, {"mpn": mpn, "refs": [ref]}, new=True)
    return store.proposals(empty)[-1]["id"]


def _render(empty, sheet_id="01"):
    return render_sheet.render(empty, sheet_id, write=False)


def test_a_pending_proposal_part_is_written_marked_and_clears_on_approval(empty):
    pid = _propose(empty, "U1")
    res = store.write_sheet(empty, "01", _sheet([_u("U1")]))
    assert res["ok"] and "U1: waits for approval" in res["warnings"]
    assert store.load_sheet(empty, "01")["parts"][0]["bom_status"] == "pending"
    assert "pending approval" in _render(empty)
    store.decide(empty, pid, "approved")
    assert "pending approval" not in _render(empty) and "not in BOM" not in _render(empty)
    assert store.sheet_gaps(empty)["parts"] == []


def test_a_rejected_proposal_shows_the_part_as_missing(empty):
    pid = _propose(empty, "U1")
    store.write_sheet(empty, "01", _sheet([_u("U1")]))
    store.decide(empty, pid, "rejected")
    assert "not in BOM" in _render(empty)
    assert store.sheet_gaps(empty)["parts"] == [{"sheet": "01", "ref": "U1", "status": "missing"}]


def test_a_missing_ref_is_written_with_a_warning_and_later_gets_its_line(empty):
    res = store.write_sheet(empty, "01", _sheet([_u("U5")]))
    assert res["ok"] and "U5: not in the BOM yet" in res["warnings"]
    assert store.load_sheet(empty, "01")["parts"][0]["bom_status"] == "missing"
    assert "not in BOM" in _render(empty)
    store.propose_bom(empty, "U5", {"mpn": "X1", "refs": ["U5"]}, new=True)
    store.decide(empty, store.proposals(empty)[-1]["id"], "approved")
    assert "not in BOM" not in _render(empty)


def test_an_open_pin_is_written_with_a_warning_and_drawn_with_a_marker(empty):
    res = store.write_sheet(empty, "01", _sheet([_u("U1")]))
    assert "U1.RESET: open pin (no net yet)" in res["warnings"]
    assert store.load_sheet(empty, "01")["parts"][0]["pins"][1]["net"] == ""
    assert 'class="openpin"' in _render(empty)
    nc = _u("U1")
    nc["pins"][1]["net"] = "NC"
    store.write_sheet(empty, "01", _sheet([nc]))
    assert 'class="openpin"' not in _render(empty)


def test_an_undefined_section_warns_and_still_draws(empty):
    part = _u("U1")
    part["section"] = "Z"
    res = store.write_sheet(empty, "01", _sheet([part]))
    assert res["ok"] and any("section 'Z'" in w for w in res["warnings"])
    assert 'data-ref="U1"' in _render(empty)


@pytest.mark.parametrize("sheet", [
    "nope", {"title": "t"}, _sheet([{"pins": [{"net": "A"}]}]),
    _sheet([_u("U1"), _u("U1")]), _sheet([{"ref": "U1", "pins": []}]), _sheet(["U1"])])
def test_hard_errors_still_refuse(empty, sheet):
    res = store.write_sheet(empty, "01", sheet)
    assert not res["ok"] and res["errors"] and "01" not in store.sheet_ids(empty)


def test_final_checks_endpoint_lists_open_pins_and_missing_parts(server, empty):  # noqa: F811
    store.write_sheet(empty, "01", _sheet([_u("U1")]))
    with urllib.request.urlopen(f"{server}/api/final/incomplete?project={empty}", timeout=10) as r:
        gaps = json.loads(r.read())
    assert gaps["open_pins"] == [{"sheet": "01", "ref": "U1", "pin": "RESET"}]
    assert gaps["parts"] == [{"sheet": "01", "ref": "U1", "status": "missing"}]
