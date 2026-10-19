"""A datasheet that is dropped in finds its part: matched by name, family or text, or linked on request."""
import base64
import json
import threading
import urllib.request

import pytest

import sources
import store
from test_server import get, post, server  # noqa: F401  (the server fixture)

PDF = b"%PDF-1.4 test"


def _bom(project, *rows):
    for key, mpn in rows:
        store.append(project, "bom-log.jsonl", {"ts": store.now(), "by": "student", "line": key,
                                                "changes": {"refs": [key], "mpn": mpn, "value": mpn}})


def _doc(project, name, text=None):
    d = store.pdir(project) / "sources"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_bytes(PDF)
    if text is not None:
        (d / (name + ".txt")).write_text(text, encoding="utf-8")   # text_of reads this cache before any PDF library


def _auto(project):
    r = store.auto_attach(project)
    return {m["line"]: m for m in r["matched"]}, r["unmatched"]


def test_a_file_named_after_the_family_is_linked(home, empty):
    _bom(empty, ("U1", "NE555DR"), ("U2", "CD4017BM96"), ("U3", "LM1117IMPX-3.3"))
    for n in ("NE555 datasheet.pdf", "cd4017b.pdf", "lm1117.pdf"):
        _doc(empty, n)
    got, left = _auto(empty)
    assert got["U1"]["name"] == "NE555 datasheet.pdf" and got["U1"]["how"] == "family"
    assert got["U2"]["name"] == "cd4017b.pdf" and got["U3"]["name"] == "lm1117.pdf"
    assert not left
    assert {l["key"]: l for l in store.bom_lines(empty)}["U1"]["datasheet"] == "NE555 datasheet.pdf"


def test_the_full_mpn_in_the_name_is_still_a_name_match(home, empty):
    _bom(empty, ("U1", "NE555DR"))
    _doc(empty, "ne555dr.pdf")
    assert _auto(empty)[0]["U1"]["how"] == "name"


def test_a_part_number_in_the_first_pages_links_a_file_with_a_useless_name(home, empty):
    _bom(empty, ("U1", "TPS62160DSGR"))
    _doc(empty, "scan0042.pdf", "TPS62160 3-17V input 1A step-down converter\npin 1 VIN")
    got, _ = _auto(empty)
    assert got["U1"]["name"] == "scan0042.pdf" and got["U1"]["how"] == "text"


def test_an_ambiguous_file_is_not_linked(home, empty):
    _bom(empty, ("U1", "LM358DR"), ("U2", "LM358"))
    _doc(empty, "lm358.pdf")
    got, left = _auto(empty)
    assert not got and left == ["lm358.pdf"]
    assert not any(l.get("datasheet") for l in store.bom_lines(empty))


def test_a_cap_never_gets_a_datasheet_and_a_digit_run_is_not_cut(home, empty):
    _bom(empty, ("C1", "GRM155R71C104KA88D"), ("U1", "NE5550A"))
    _doc(empty, "grm155r71c104ka88d.pdf")
    _doc(empty, "ne555.pdf")
    got, left = _auto(empty)
    assert not got and set(left) == {"grm155r71c104ka88d.pdf", "ne555.pdf"}


def test_attach_by_designator_verifies_the_pins(home, empty):
    _bom(empty, ("U1", "XYZ9000"))
    store.write_sheet(empty, "01", {"id": "01", "title": "T", "parts": [{"ref": "U1", "pins": [
        {"num": "1", "name": "GND", "net": "GND"}, {"num": "2", "name": "VCC", "net": "3V3"}]}]})
    _doc(empty, "whatever.pdf", "Pin 1 GND ground. Pin 2 VCC supply")
    r = store.attach_datasheet(empty, "U1", "whatever.pdf")
    assert r["status"] == "verified" and r["line"] == "U1"
    assert store.bom(empty, write=False)[0]["datasheet"] == "whatever.pdf"
    _doc(empty, "other.pdf", "Pin 1 GND only")
    assert store.attach_datasheet(empty, "U1", "other.pdf")["status"] == "mismatch"
    store.detach_datasheet(empty, "U1")
    assert not {l["key"]: l for l in store.bom_lines(empty)}["U1"]["datasheet"]
    with pytest.raises(ValueError):
        store.attach_datasheet(empty, "U1", "missing.pdf")
    with pytest.raises(KeyError):
        store.attach_datasheet(empty, "U9", "other.pdf")


def test_the_agent_attaches_a_dropped_file(home, empty):
    import serve
    _bom(empty, ("U3", "XYZ9000"))
    _doc(empty, "by_hand.pdf")
    applied, props, refused = serve.apply_actions(empty, [
        {"type": "part.attach_datasheet", "ref": "U3", "name": "by_hand.pdf"},
        {"type": "part.attach_datasheet", "ref": "U3", "name": "nope.pdf"}])
    assert applied and applied[0].startswith("part.attach_datasheet:U3 <- by_hand.pdf") and not props
    assert len(refused) == 1 and "nope.pdf" in refused[0]


def test_an_upload_reports_what_matched_and_what_did_not(server, empty):
    _bom(empty, ("U1", "NE555DR"))
    b64 = lambda: base64.b64encode(PDF).decode()
    code, r = post(server, "/api/upload", {"name": "NE555 datasheet.pdf", "data_b64": b64()}, empty)
    assert code == 200 and [(m["name"], m["ref"], m["how"]) for m in r["matched"]] == [("NE555 datasheet.pdf", "U1", "family")]
    code, r = post(server, "/api/upload", {"name": "mystery.pdf", "data_b64": b64()}, empty)
    assert r["matched"] == [] and r["unmatched"] == ["mystery.pdf"]
    code, r = post(server, "/api/parts/attach_datasheet", {"line": "U1", "name": "mystery.pdf"}, empty)
    assert code == 200 and r["attached"]["name"] == "mystery.pdf"
    code, r = post(server, "/api/parts/detach_datasheet", {"line": "U1"}, empty)
    assert code == 200 and r["detached"]["line"] == "U1"
    assert post(server, "/api/parts/attach_datasheet", {"line": "U7", "name": "x.pdf"}, empty)[0] == 400
