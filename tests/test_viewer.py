"""Tests for the in-app viewer endpoints: /api/altium/file and /api/source/ download header."""
import json
import pathlib
import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest

import workspace


@pytest.fixture
def server(home, monkeypatch):
    """The real handler on an ephemeral port, in this process."""
    from http.server import ThreadingHTTPServer
    from altium import registry
    import serve

    monkeypatch.setattr(serve, "QUIET", True)
    monkeypatch.setattr(serve, "recheck_async", lambda p, k: None)

    monkeypatch.setattr(registry, "find_installs", lambda reg=None: [
        {"build": "AD26", "version": "26.0.0", "path": "C:\\Program Files\\Altium\\AD26", "exe": "C:\\Program Files\\Altium\\AD26\\X2.EXE"}
    ])
    monkeypatch.setattr(registry, "recent_projects", lambda reg=None, limit=20: [
        {"path": "C:\\Projects\\Demo.PrjPcb", "name": "Demo", "exists": False, "build": "AD26"}
    ])

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def post(base, path, body, proj):
    req = urllib.request.Request(
        f"{base}{path}{'&' if '?' in path else '?'}project={proj}", method="POST",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def get(base, path, proj, raw=False):
    try:
        with urllib.request.urlopen(f"{base}{path}{'&' if '?' in path else '?'}project={proj}", timeout=10) as r:
            body = r.read()
            return r.status, (body if raw else json.loads(body))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def get_response(base, path, proj):
    try:
        with urllib.request.urlopen(f"{base}{path}{'&' if '?' in path else '?'}project={proj}", timeout=10) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def test_altium_file_linked_project_sheet(server, lte):
    fixture_path = str(pathlib.Path("tests/fixtures/altium/project/WCTopping.PrjPcb").resolve())
    status, body = post(server, "/api/altium/link", {"path": fixture_path}, lte)
    assert status == 200

    sheet_path = str(pathlib.Path("tests/fixtures/altium/project/Processor_Interface.SchDoc").resolve())
    status, file_body = get(server, f"/api/altium/file?path={urllib.parse.quote(sheet_path)}", lte)
    assert status == 200
    assert "components" in file_body
    assert isinstance(file_body["components"], int)
    assert file_body["components"] > 0


def test_altium_file_outside_path(server, lte, tmp_path):
    fixture_path = str(pathlib.Path("tests/fixtures/altium/project/WCTopping.PrjPcb").resolve())
    status, _ = post(server, "/api/altium/link", {"path": fixture_path}, lte)
    assert status == 200

    outside_file = tmp_path / "outside.SchDoc"
    outside_file.write_text("outside", encoding="utf-8")
    status, body = get(server, f"/api/altium/file?path={urllib.parse.quote(str(outside_file))}", lte)
    assert status == 403


def test_altium_file_nothing_linked(server, lte):
    sheet_path = str(pathlib.Path("tests/fixtures/altium/project/Processor_Interface.SchDoc").resolve())
    status, body = get(server, f"/api/altium/file?path={urllib.parse.quote(sheet_path)}", lte)
    assert status == 403


def test_source_download_header(server, lte):
    pdir = workspace.project_dir(lte)
    (pdir / "sources").mkdir(parents=True, exist_ok=True)
    sample_file = pdir / "sources" / "sample.txt"
    sample_file.write_text("hello world", encoding="utf-8")

    status, content, headers = get_response(server, "/api/source/sample.txt?download=1", lte)
    assert status == 200
    cd = headers.get("content-disposition", "") or headers.get("Content-Disposition", "")
    assert "attachment" in cd.lower()
    assert 'filename="sample.txt"' in cd


def test_source_html_served_as_text_plain(server, lte):
    pdir = workspace.project_dir(lte)
    (pdir / "sources").mkdir(parents=True, exist_ok=True)
    html_file = pdir / "sources" / "dangerous.html"
    html_file.write_text("<script>alert(1)</script>", encoding="utf-8")

    status, content, headers = get_response(server, "/api/source/dangerous.html", lte)
    assert status == 200
    ct = headers.get("content-type", "") or headers.get("Content-Type", "")
    assert ct.startswith("text/plain")


def test_altium_file_read_error(server, lte, tmp_path):
    import shutil
    proj_dir = tmp_path / "proj"
    shutil.copytree("tests/fixtures/altium/project", proj_dir)
    corrupt_sheet = proj_dir / "Processor_Interface.SchDoc"
    corrupt_sheet.write_bytes(b"not an ole file")
    prj_file = proj_dir / "WCTopping.PrjPcb"

    status, _ = post(server, "/api/altium/link", {"path": str(prj_file)}, lte)
    assert status == 200

    status, body = get(server, f"/api/altium/file?path={urllib.parse.quote(str(corrupt_sheet))}", lte)
    assert status == 422
    assert "error" in body

