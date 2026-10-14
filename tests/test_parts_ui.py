"""
Server and UI endpoints testing for parts and stock (Task A2):
- Availability states and risk for lines with fake supply
- cost_per_board and extended_fee totals
- /api/parts/alternatives endpoint with monkeypatched jlc
- /api/parts/datasheet success (monkeypatched fetch) and link-and-return failure
- role edit persistence via /api/bom/edit
"""
import json
import threading
import urllib.error
import urllib.request
import pytest

import jlc
import sources
import store


@pytest.fixture
def server(home, monkeypatch):
    from http.server import ThreadingHTTPServer
    import serve

    monkeypatch.setattr(serve, "QUIET", True)
    monkeypatch.setattr(serve, "recheck_async", lambda project, key: None)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def post(base, path, body, project):
    req = urllib.request.Request(
        f"{base}{path}{'&' if '?' in path else '?'}project={project}", method="POST",
        data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def get(base, path, project, raw=False):
    try:
        with urllib.request.urlopen(f"{base}{path}{'&' if '?' in path else '?'}project={project}", timeout=10) as r:
            body = r.read()
            return r.status, (body if raw else json.loads(body))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def line_by_key(state, key):
    return next(l for l in state["bom"] if l["key"] == key)


@pytest.fixture
def parts_project(home):
    import project
    name = project.create("parts_demo", title="Parts Demo")

    # Seed BOM lines
    store.append(name, "bom-log.jsonl", {
        "ts": store.now(), "by": "student", "line": "R1",
        "changes": {"refs": ["R1"], "mpn": "RES-10K", "package": "0603", "value": "10k"}
    })
    store.append(name, "bom-log.jsonl", {
        "ts": store.now(), "by": "student", "line": "U1",
        "changes": {"refs": ["U1"], "mpn": "MCU-LOW", "package": "QFN-32", "value": "MCU"}
    })
    store.append(name, "bom-log.jsonl", {
        "ts": store.now(), "by": "student", "line": "U2",
        "changes": {"refs": ["U2"], "mpn": "CHIP-EXT", "package": "SOIC-8", "value": "EXT"}
    })
    store.append(name, "bom-log.jsonl", {
        "ts": store.now(), "by": "student", "line": "D1",
        "changes": {"refs": ["D1"], "mpn": "DIODE-OOS", "package": "SOD-123", "value": "DIODE"}
    })
    store.append(name, "bom-log.jsonl", {
        "ts": store.now(), "by": "student", "line": "C1",
        "changes": {"refs": ["C1"], "mpn": "CAP-NOEXACT", "package": "0603", "value": "100nF"}
    })
    store.append(name, "bom-log.jsonl", {
        "ts": store.now(), "by": "student", "line": "L1",
        "changes": {"refs": ["L1"], "mpn": "IND-UNCHECK", "package": "0805", "value": "10uH"}
    })

    # Supply records
    # R1: Basic, high stock (500) -> ok, no risk
    store.add_supply(name, "R1", "LCSC", stock=500, unit_price=0.01, mpn="RES-10K",
                     library_type="Basic", package="0603", code="C101", exact=True,
                     datasheet_url="https://jlcpcb.com/res.pdf")

    # U1: Basic, low stock (15 < 1 * 5 * 10 = 50) -> low, low stock risk
    store.add_supply(name, "U1", "LCSC", stock=15, unit_price=2.00, mpn="MCU-LOW",
                     library_type="Basic", package="QFN-32", code="C102", exact=True,
                     datasheet_url="https://jlcpcb.com/mcu.pdf")

    # U2: Extended, high stock (1000) -> low, Extended fee risk
    store.add_supply(name, "U2", "LCSC", stock=1000, unit_price=1.50, mpn="CHIP-EXT",
                     library_type="Extended", package="SOIC-8", code="C103", exact=True,
                     datasheet_url="https://jlcpcb.com/ext.pdf")

    # D1: 0 stock -> none, out of stock risk
    store.add_supply(name, "D1", "LCSC", stock=0, unit_price=0.20, mpn="DIODE-OOS",
                     library_type="Basic", package="SOD-123", code="C104", exact=True,
                     datasheet_url="https://jlcpcb.com/diode.pdf")

    # C1: exact is False -> no exact MPN match risk
    store.add_supply(name, "C1", "LCSC", stock=400, unit_price=0.02, mpn="CAP-NOEXACT",
                     library_type="Basic", package="0603", code="C105", exact=False,
                     datasheet_url="https://jlcpcb.com/cap.pdf")

    # L1 has no supply -> unchecked, not checked risk

    return name


def test_availability_states_and_risk(server, parts_project):
    code, st = get(server, "/api/state", parts_project)
    assert code == 200

    r1 = line_by_key(st, "R1")
    assert r1["availability"] == "ok"
    assert r1["risk"] == []
    assert r1["library_type"] == "Basic"
    assert r1["cost_per_board"] == 0.01

    u1 = line_by_key(st, "U1")
    assert u1["availability"] == "low"
    assert "low stock" in u1["risk"]
    assert u1["library_type"] == "Basic"
    assert u1["cost_per_board"] == 2.00

    u2 = line_by_key(st, "U2")
    assert u2["availability"] == "low"
    assert "Extended fee" in u2["risk"]
    assert u2["library_type"] == "Extended"
    assert u2["cost_per_board"] == 1.50

    d1 = line_by_key(st, "D1")
    assert d1["availability"] == "none"
    assert "out of stock" in d1["risk"]

    c1 = line_by_key(st, "C1")
    assert "no exact MPN match" in c1["risk"]

    l1 = line_by_key(st, "L1")
    assert l1["availability"] == "unchecked"
    assert "not checked" in l1["risk"]


def test_cost_per_board_and_extended_fee_totals(server, parts_project):
    code, st = get(server, "/api/state", parts_project)
    assert code == 200
    totals = st["totals"]

    # cost_per_board = R1 (0.01) + U1 (2.00) + U2 (1.50) + C1 (0.02) = 3.53
    assert totals["cost_per_board"] == pytest.approx(3.53, 0.001)

    # Distinct Extended parts = 1 (U2) * $3.07 = 3.07 (JLC Economic assembly Feeder Loading fee, checked 2026-10-14)
    assert totals["extended_fee"] == 3.07


def test_alternatives_endpoint_with_monkeypatched_jlc(server, parts_project, monkeypatch):
    fake_alts = [
        {"code": "C999", "mpn": "ALT-1", "package": "0603", "stock": 500, "library_type": "Basic"}
    ]
    monkeypatch.setattr(jlc, "alternatives", lambda line, n=5: fake_alts)

    code, body = get(server, "/api/parts/alternatives?line=R1", parts_project)
    assert code == 200
    assert isinstance(body, list)
    assert body == fake_alts

    # Missing line
    code_bad, _ = get(server, "/api/parts/alternatives?line=DOES_NOT_EXIST", parts_project)
    assert code_bad == 404


def test_datasheet_endpoint_success_and_failure(server, parts_project, monkeypatch):
    # Success scenario. A part's datasheet is downloaded into the project (sources.get);
    # the fetch stub is for a server that still downloads through the shared library.
    monkeypatch.setattr(sources, "get", lambda project, url, name=None: {"name": "fetched_doc.pdf", "url": url})
    monkeypatch.setattr(sources, "fetch", lambda url, name=None, **kw: {"name": "fetched_doc.pdf", "url": url})

    code, body = post(server, "/api/parts/datasheet", {"line": "R1"}, parts_project)
    assert code == 200
    assert body.get("ok") is True
    assert body.get("datasheet") == "fetched_doc.pdf"

    # Verify line has datasheet set
    _, st = get(server, "/api/state", parts_project)
    assert line_by_key(st, "R1")["datasheet"] == "fetched_doc.pdf"

    # Link-and-return failure scenario
    def failing_fetch(url, name=None, **kw):
        raise urllib.error.URLError("Failed to download remote file")

    def failing_get(project, url, name=None):
        return failing_fetch(url, name)

    monkeypatch.setattr(sources, "fetch", failing_fetch)
    monkeypatch.setattr(sources, "get", failing_get)
    code_err, body_err = post(server, "/api/parts/datasheet", {"line": "U1"}, parts_project)
    assert code_err == 200
    assert "error" in body_err
    assert body_err["url"] == "https://jlcpcb.com/mcu.pdf"


def test_role_edit_persists(server, parts_project):
    code, st = post(server, "/api/bom/edit",
                    {"line": "R1", "field": "role", "value": "Pull-up resistor for I2C SDA"},
                    parts_project)
    assert code == 200
    assert line_by_key(st, "R1")["role"] == "Pull-up resistor for I2C SDA"

    # Reload from fresh GET /api/state
    code_get, st_fresh = get(server, "/api/state", parts_project)
    assert code_get == 200
    assert line_by_key(st_fresh, "R1")["role"] == "Pull-up resistor for I2C SDA"
