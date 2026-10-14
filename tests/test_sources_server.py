"""The two places the server downloads a document: both keep it in the project, not the shared library."""
import json
import threading
import urllib.error
import urllib.request

import pytest


@pytest.fixture
def server(home, monkeypatch):
    """The real handler on an ephemeral port, in this process."""
    from http.server import ThreadingHTTPServer
    import serve

    monkeypatch.setattr(serve, "QUIET", True)
    monkeypatch.setattr(serve, "recheck_async", lambda project, key: None)   # no network
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def post(base, path, body, project):
    req = urllib.request.Request(f"{base}{path}?project={project}", method="POST",
                                 data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_a_source_added_by_url_stays_in_the_project(server, lte, home, monkeypatch):
    import sources
    monkeypatch.setattr(sources, "_download", lambda url, timeout: b"%PDF-1.4 some note")
    code, st = post(server, "/api/fetch_source", {"url": "https://v.example/note.pdf", "name": "note.pdf"}, lte)
    assert code == 200 and "error" not in st
    assert (home / "projects" / lte / "sources" / "note.pdf").read_bytes() == b"%PDF-1.4 some note"
    assert not list(sources.cache().glob("*"))
    assert next(s for s in st["sources"] if s["name"] == "note.pdf")["scope"] == "project"


def test_a_datasheet_fetched_for_a_part_stays_in_the_project(server, lte, home, monkeypatch):
    import jlc
    import sources
    monkeypatch.setattr(jlc, "part", lambda mpn: {"datasheet_url": "https://v.example/u4.pdf"})
    monkeypatch.setattr(sources, "_download", lambda url, timeout: b"%PDF-1.4 u4")
    code, body = post(server, "/api/parts/datasheet", {"line": "U4"}, lte)
    assert code == 200 and body.get("ok"), body
    assert (home / "projects" / lte / "sources" / body["datasheet"]).read_bytes() == b"%PDF-1.4 u4"
    assert not list(sources.cache().glob("*"))
    assert next(s for s in body["state"]["sources"] if s["name"] == body["datasheet"])["scope"] == "project"
