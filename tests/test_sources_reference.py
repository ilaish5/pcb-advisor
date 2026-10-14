"""The general reference library (shared/reference/: course material and JLC pages) is a source like any other:
listed under scope shared, read-only, named by its path relative to that folder (how AGENTS.md tells the advisor to
cite it), and served by the endpoint the viewer uses. The agent and the user see the same documents."""
import http.client
import json
import pathlib
import re
import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
REFERENCE = REPO / "shared" / "reference"


@pytest.fixture
def server(home, monkeypatch):
    """The real handler on an ephemeral port, in this process."""
    from http.server import ThreadingHTTPServer
    import serve

    monkeypatch.setattr(serve, "QUIET", True)
    monkeypatch.setattr(serve, "recheck_async", lambda project, key: None)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address
    httpd.shutdown()
    httpd.server_close()


def fetch(addr, path):
    """(status, headers, body) of a GET with the path exactly as given: urllib would tidy a '..' away."""
    conn = http.client.HTTPConnection(addr[0], addr[1], timeout=10)
    try:
        conn.request("GET", path)
        r = conn.getresponse()
        return r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()
    finally:
        conn.close()


@pytest.fixture
def library(home, monkeypatch):
    """A small reference library of our own, so the listing tests do not depend on the real one."""
    import sources
    root = home / "ref"
    (root / "jlc").mkdir(parents=True)
    (root / "course" / "unit").mkdir(parents=True)
    (root / "AGENTS.md").write_text("# instructions\n", encoding="utf-8")
    (root / "README.md").write_text("# pointer\n", encoding="utf-8")
    (root / "course" / "unit" / "AGENTS.md").write_text("# nested instructions\n", encoding="utf-8")
    (root / "jlc" / "limits.en.md").write_text("# Limits\n\nTrace 0.1 mm.\n", encoding="utf-8")
    (root / "course" / "unit" / "m01-intro.en.md").write_text("# Intro\n", encoding="utf-8")
    (root / "course" / "unit" / "manual.pdf").write_bytes(b"%PDF-1.4 the original")
    (root / "course" / "unit" / "figure.png").write_bytes(b"\x89PNG")        # not text: not a source
    (root / "course" / "unit" / "notes.txt").write_text("scratch", encoding="utf-8")
    monkeypatch.setattr(sources, "reference_dir", lambda: root)
    return root


# ---------------------------------------------------------------- listing

def test_the_reference_library_is_listed_as_shared_read_only_sources(lte, library):
    import model
    rows = {r["name"]: r for r in model.list_sources(lte)}
    assert {n for n, r in rows.items() if "/" in n} == {"jlc/limits.en.md", "course/unit/m01-intro.en.md", "course/unit/manual.pdf"}
    for name in ("jlc/limits.en.md", "course/unit/m01-intro.en.md", "course/unit/manual.pdf"):
        r = rows[name]
        assert r["scope"] == "shared" and r["present"] is True and r["url"] is None
        assert r["kind"] == name.rsplit(".", 1)[1].upper()
        assert re.fullmatch(r"[0-9a-f]{8}", r["sha256"]) and r["size"] and r["used_for"] == "—"
    assert rows["jlc/limits.en.md"]["text"] is True
    assert rows["course/unit/manual.pdf"]["text"] is True              # its text is the .md beside it


def test_instructions_and_non_documents_are_not_sources(lte, library):
    import model
    names = {r["name"] for r in model.list_sources(lte)}
    for left_out in ("AGENTS.md", "README.md", "course/unit/AGENTS.md", "course/unit/figure.png", "course/unit/notes.txt"):
        assert left_out not in names, left_out


def test_reference_sits_between_the_shared_datasheets_and_the_project_in_the_list(lte, library, home):
    import model
    import sources
    sources.cache().mkdir(parents=True, exist_ok=True)
    (sources.cache() / "app-note.pdf").write_bytes(b"%PDF-1.4 a general note")
    (home / "projects" / lte / "sources").mkdir(parents=True, exist_ok=True)
    (home / "projects" / lte / "sources" / "u1.pdf").write_bytes(b"%PDF-1.4 a datasheet")
    rows = model.list_sources(lte)
    order = [(r["scope"], r["name"]) for r in rows]
    assert order.index(("shared", "app-note.pdf")) < order.index(("shared", "course/unit/m01-intro.en.md")) < order.index(("project", "u1.pdf"))
    assert [r["scope"] for r in rows] == sorted((r["scope"] for r in rows), key=["shared", "project"].index)
    assert len({r["name"] for r in rows}) == len(rows), "a name identifies one source"


def test_a_missing_reference_folder_lists_nothing_and_breaks_nothing(lte, home, monkeypatch):
    import model
    import sources
    monkeypatch.setattr(sources, "reference_dir", lambda: home / "no-such-folder")
    assert sources.reference_files() == {}
    assert not [r for r in model.list_sources(lte) if "/" in r["name"]]


def test_the_real_library_is_listed_with_the_names_agents_md_tells_the_advisor_to_cite():
    import sources
    names = set(sources.reference_files())
    on_disk = {p.relative_to(REFERENCE).as_posix() for p in REFERENCE.rglob("*")
               if p.is_file() and p.suffix in (".md", ".pdf") and p.name not in ("AGENTS.md", "README.md")}
    assert names == on_disk and len(names) >= 39
    assert not {"AGENTS.md", "README.md"} & names
    agents = (REFERENCE / "AGENTS.md").read_text(encoding="utf-8")
    cite = agents[agents.index("## How to cite"):agents.index("## Caveats")]
    cited = re.findall(r"`((?:course|jlc)/[\w./-]+\.(?:md|pdf))", cite)
    assert len(cited) >= 3
    for name in cited:
        assert name in names, f"AGENTS.md cites {name}, the Sources list must have it under that name"
    assert "jlc/pcb-capabilities.en.md" in names
    assert "course/ad20-essentials/ad20-essentials-exercises.pdf" in names


def test_state_carries_the_reference_documents(lte, library, server):
    status, _, body = fetch(server, f"/api/state?project={lte}")
    rows = {r["name"]: r for r in json.loads(body)["sources"]}
    assert status == 200 and rows["jlc/limits.en.md"]["scope"] == "shared"


# ---------------------------------------------------------------- serving

def test_a_reference_document_is_served_by_the_endpoint_the_viewer_uses(lte, library, server):
    for url in (f"/api/source/jlc/limits.en.md?project={lte}",
                f"/api/source/{urllib.parse.quote('jlc/limits.en.md', safe='')}?project={lte}"):   # the viewer sends %2F
        status, headers, body = fetch(server, url)
        assert status == 200, url
        assert body == (library / "jlc" / "limits.en.md").read_bytes()
        assert headers["content-type"].startswith("text/plain")
    status, headers, body = fetch(server, f"/api/source/course/unit/manual.pdf?project={lte}")
    assert status == 200 and headers["content-type"] == "application/pdf" and body == b"%PDF-1.4 the original"


def test_a_reference_document_can_be_downloaded(lte, library, server):
    status, headers, _ = fetch(server, f"/api/source/jlc/limits.en.md?project={lte}&download=1")
    assert status == 200 and headers["content-disposition"] == 'attachment; filename="limits.en.md"'


def test_the_real_pcb_capabilities_document_is_served(lte, server):
    status, _, body = fetch(server, f"/api/source/jlc/pcb-capabilities.en.md?project={lte}")
    assert status == 200 and body == (REFERENCE / "jlc" / "pcb-capabilities.en.md").read_bytes()
    assert b"Traces and spacing" in body


@pytest.mark.parametrize("path", [
    "/api/source/../../config/defaults.json",
    "/api/source/jlc/../../config/defaults.json",
    "/api/source/jlc/../AGENTS.md",
    "/api/source/%2e%2e/%2e%2e/config/defaults.json",
    "/api/source/jlc%2f..%2f..%2fconfig%2fdefaults.json",
    "/api/source/jlc\\..\\..\\config\\defaults.json",
    "/api/source//etc/passwd",
    "/api/source/C:/Windows/win.ini",
    "/api/source/C:win.ini",
    "/api/source/jlc/",
    "/api/source/jlc",
    "/api/source/course/unit/figure.png",        # in the folder, but not a document of the library
    "/api/source/course/unit/AGENTS.md",         # instructions are not sources
    "/api/source/AGENTS.md",
    "/api/source/README.md",
    "/api/source/jlc/missing.en.md",
])
def test_a_path_outside_the_listed_documents_is_refused(lte, library, server, path):
    status, _, body = fetch(server, f"{path}?project={lte}")
    assert status == 404 and json.loads(body)["error"] == "not in the library"
    assert b"instructions" not in body and b"schema_version" not in body


def test_a_project_file_cannot_stand_in_for_a_reference_name(lte, library, home, server):
    sources_dir = home / "projects" / lte / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    (sources_dir / "limits.en.md").write_text("the project's own file", encoding="utf-8")
    _, _, mine = fetch(server, f"/api/source/limits.en.md?project={lte}")
    _, _, general = fetch(server, f"/api/source/jlc/limits.en.md?project={lte}")
    assert mine == b"the project's own file" and general.startswith(b"# Limits")


# ---------------------------------------------------------------- citations

def test_a_citation_of_a_reference_document_resolves_and_counts(lte, library):
    import model
    import session
    sid = session.current(lte)
    session.append(lte, sid, {"role": "agent", "text": "JLC's floor is 0.1 mm {{src:jlc/limits.en.md|§ Limits}}."})
    assert model.citations(lte)["jlc/limits.en.md"] == ["§ Limits"]
    rows = {r["name"]: r for r in model.list_sources(lte)}
    assert set(model.citations(lte)) <= set(rows)                      # every cited name is a listed source
    assert rows["jlc/limits.en.md"]["used_for"] == "1 citation · § Limits"


def test_the_chat_chip_pattern_reads_a_name_with_folders():
    """core.js inline() turns {{src:NAME|where}} into a chip and looks NAME up in S.sources (srcByName): the pattern
    must keep the slashes of a reference name, and so must the server's."""
    import model
    core = (REPO / "ui" / "js" / "core.js").read_text(encoding="utf-8")
    js = re.search(r"\.replace\(/(\\\{\\\{src:.*?)/g, \(m, n, w\)", core).group(1)
    for pattern in (js, model.CITE.pattern):
        m = re.search(pattern, "see {{src:jlc/pcb-capabilities.en.md|§ Traces and spacing}} for it")
        assert m and m.group(1) == "jlc/pcb-capabilities.en.md" and m.group(2) == "§ Traces and spacing"
    assert re.search(r"const srcByName = n => \(S\.sources \|\| \[\]\)\.find\(s => s\.name === n\)", core)


# ---------------------------------------------------------------- the agent's side: scripts/sources.py

def test_verify_reads_a_reference_document_by_its_name(home, library):
    import sources
    assert sources.verify("jlc/limits.en.md", "Trace 0.1 mm.")["ok"] is True
    assert sources.verify("jlc/limits.en.md", "Trace 0.9 mm.")["ok"] is False
    pdf = sources.verify("course/unit/manual.pdf", "the original")
    assert pdf["ok"] is False and ".md files" in pdf["reason"]
    assert not list((library / "jlc").glob("*.txt")), "reading a reference document leaves no cache in the library"


def test_the_listing_command_names_the_reference_documents_too(home):
    import os
    import subprocess
    import sys
    env = {**os.environ, "PCB_ADVISOR_HOME": str(home), "PCB_ADVISOR_CONFIG": str(home / "config.json"), "PYTHONIOENCODING": "utf-8"}
    out = subprocess.run([sys.executable, str(REPO / "scripts" / "sources.py"), "list"], env=env, cwd=home,
                         capture_output=True, encoding="utf-8", timeout=60).stdout
    assert "jlc/pcb-capabilities.en.md" in out and "AGENTS.md" not in out
