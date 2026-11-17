"""Unverified pins block the manufacturing outputs (Altium OutJob, Gerber zip) until each part is resolved: a datasheet table pass or
the student's accept_pins. Previews stay allowed. The bridge and the zip are faked: nothing here touches Altium."""
import pathlib

import pytest

import jlc_upload
import serve
import store
from altium import bridge
from test_chat_turns import call, server  # noqa: F401
from test_unverified_pins import _datasheet, _jd_sheet, _sheet

REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def made(monkeypatch):
    """What the faked outputs were asked to make."""
    seen = []
    monkeypatch.setattr(bridge, "run_outjob", lambda p: seen.append("outjob") or {"files": ["a.GTL"], "added": False, "warnings": []})
    monkeypatch.setattr(jlc_upload, "gerber_zip", lambda p: seen.append("zip") or {"zip": "x.zip", "files": ["a.GTL"], "missing": [], "warnings": []})
    return seen


def _both(server, empty):
    return [call(server, "POST", "/api/altium/run-outjob", empty, {}), call(server, "POST", "/api/jlc/gerber-zip", empty, {})]


def test_outjob_and_zip_are_refused_while_a_part_is_unverified(server, empty, made):
    _sheet(empty)
    for code, body in _both(server, empty):
        assert code == 400
        assert body["error"].startswith("Not made yet: 1 part has pins nobody checked against a datasheet: U1.")
        assert "DFM > Unverified parts" in body["error"] and "accept it if you checked it yourself" in body["error"]
    applied, _, refused = serve.apply_actions(empty, [{"type": "altium.run_outjob"}, {"type": "jlc.gerber_zip"}])
    assert not applied and len(refused) == 2 and all("Not made yet" in r for r in refused)
    assert made == []


def test_the_message_lists_every_part(empty):
    _jd_sheet(empty)
    msg = store.manufacturing_warning(empty)
    assert msg.startswith("Not made yet: 2 parts have pins nobody checked against a datasheet: ") and "J1" in msg and "D1" in msg


def test_allowed_after_the_student_accepts_even_with_only_a_pin_diagram(server, empty, made):
    _sheet(empty)                    # a datasheet with no pin table (NE555: a diagram only) verifies nothing
    _datasheet(empty, ["see the pin diagram on page 1"])
    assert store.manufacturing_warning(empty)
    store.accept_pins(empty, "U1")
    assert store.manufacturing_warning(empty) == ""
    assert [c for c, _ in _both(server, empty)] == [200, 200] and made == ["outjob", "zip"]


def test_the_accept_endpoint_of_the_unverified_list_resolves_a_part(server, empty, made):
    _jd_sheet(empty)                 # D1 is polarised: only the student's accept clears it
    assert call(server, "POST", "/api/altium/run-outjob", empty, {})[0] == 400
    for key in ("J1", "D1"):
        assert call(server, "POST", "/api/pins/accept", empty, {"line": key})[0] == 200
    assert call(server, "POST", "/api/altium/run-outjob", empty, {})[0] == 200 and made == ["outjob"]


def test_allowed_after_a_table_pass(server, empty, made):
    _sheet(empty)
    _datasheet(empty, ["1 VCC Supply", "2 GND Ground"])
    assert [c for c, _ in _both(server, empty)] == [200, 200] and made == ["outjob", "zip"]
    applied, _, refused = serve.apply_actions(empty, [{"type": "altium.run_outjob"}, {"type": "jlc.gerber_zip"}])
    assert len(applied) == 2 and not refused


def test_dnp_lines_are_ignored(server, empty, made):
    _sheet(empty)
    store.edit_bom(empty, "U1", "dnp", True)
    assert store.manufacturing_warning(empty) == ""
    assert call(server, "POST", "/api/altium/run-outjob", empty, {})[0] == 200


def test_the_agent_cannot_accept_on_the_students_behalf(empty):
    _sheet(empty)
    assert serve._agent_may_set_library({"pins_accepted": True, "accepted": True, "verify": "pass", "footprint": "F"}) == {"footprint": "F"}
    serve.apply_actions(empty, [{"type": "library.add", "line": "U1", "changes": {"pins_accepted": True, "accepted": True, "verify": "pass"}}])
    assert not store.library_parts(empty).get("U1", {}).get("pins_accepted")
    assert store.manufacturing_warning(empty)


def test_the_unverified_list_has_an_accept_button_per_part():
    js = (REPO / "ui" / "js" / "views" / "checks.js").read_text(encoding="utf-8")
    assert "act: 'accept-pins', line: l.key" in js and "'/api/pins/accept', {line: d.line}" in js
    assert "rows.map(item)" in js     # every row, a mismatch included, comes from the one template that holds the button
