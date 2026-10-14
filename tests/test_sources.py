"""The document library: adding a datasheet to a project, and taking it out.

Two places: a project's sources/ (the datasheets of ITS parts, its uploads) and the
shared library (general documents only: app notes, guides, standards)."""
import json
import os
import runpy
import sys
import urllib.error
import urllib.request

import pytest


def serve_bytes(monkeypatch, sources, by_url):
    """Answer downloads from a dict instead of the network."""
    monkeypatch.setattr(sources, "_download", lambda url, timeout: by_url[url])


def test_get_puts_a_datasheet_in_the_project_with_its_provenance(home, tmp_path):
    import sources
    pdf = tmp_path / "vendor" / "LM1117.pdf"
    pdf.parent.mkdir()
    pdf.write_bytes(b"%PDF-1.4 fake")
    meta = sources.get("board", pdf.as_uri())
    copy = home / "projects" / "board" / "sources" / "LM1117.pdf"
    assert copy.exists()
    side = json.loads((copy.parent / "LM1117.pdf.json").read_text(encoding="utf-8"))
    assert side["url"] == pdf.as_uri() and side["sha256"] == meta["sha256"]
    # a part's datasheet is the project's: nothing is left in the shared library
    assert meta["path"] == str(copy)
    assert not list(sources.cache().glob("*"))


def test_unuse_never_touches_the_shared_library(home, tmp_path):
    import sources
    pdf = tmp_path / "vendor" / "part.pdf"
    pdf.parent.mkdir()
    pdf.write_bytes(b"%PDF-1.4 fake")
    sources.fetch(pdf.as_uri(), "part.pdf")        # a general document, in the shared library
    sources.use("board", "part.pdf")               # and a project that keeps its own copy
    assert sources.unuse("board", "part.pdf")["removed"] == ["part.pdf", "part.pdf.json"]
    assert (sources.cache() / "part.pdf").exists()
    assert (sources.cache() / "part.pdf.json").exists()
    # not in the project: nothing anywhere is removed, the shared copy included
    assert sources.unuse("board", "part.pdf")["removed"] == []
    assert (sources.cache() / "part.pdf").exists()


def test_unuse_cannot_climb_out_of_the_project(home):
    import sources
    victim = home / "config.json"
    victim.write_text("{}")
    sources.unuse("board", "../../config.json")
    assert victim.exists()


def test_get_refuses_a_different_file_under_a_name_the_project_holds(home, monkeypatch):
    import sources
    serve_bytes(monkeypatch, sources, {"https://a.example/x.pdf": b"%PDF-1.4 first",
                                       "https://b.example/x.pdf": b"%PDF-1.4 other"})
    first = sources.get("board", "https://a.example/x.pdf", "part-name.pdf")
    held = home / "projects" / "board" / "sources" / "part-name.pdf"
    side = held.parent / "part-name.pdf.json"
    before = (held.read_bytes(), side.read_bytes())
    with pytest.raises(sources.SourceError) as err:
        sources.get("board", "https://b.example/x.pdf", "part-name.pdf")
    msg = str(err.value)
    assert "https://a.example/x.pdf" in msg and first["sha256"][:12] in msg
    assert "project board's sources" in msg and "another name" in msg and "\n" not in msg
    # the file and its sidecar are as they were, and nothing reached the shared library
    assert (held.read_bytes(), side.read_bytes()) == before
    assert not list(sources.cache().glob("*"))
    # another project is its own folder: the same name may hold another document there
    sources.get("other-board", "https://b.example/x.pdf", "part-name.pdf")
    assert (home / "projects" / "other-board" / "sources" / "part-name.pdf").read_bytes() == b"%PDF-1.4 other"
    assert held.read_bytes() == b"%PDF-1.4 first"


def test_get_reuses_the_same_file_without_rewriting_the_sidecar(home, monkeypatch):
    import sources
    serve_bytes(monkeypatch, sources, {"https://a.example/x.pdf": b"%PDF-1.4 same",
                                       "https://mirror.example/x.pdf": b"%PDF-1.4 same"})
    first = sources.get("board", "https://a.example/x.pdf", "x.pdf")
    side = home / "projects" / "board" / "sources" / "x.pdf.json"
    os.utime(side, ns=(1_000_000_000_000_000_000, 1_000_000_000_000_000_000))
    stamp = side.stat().st_mtime_ns
    before = side.read_bytes()
    again = sources.get("board", "https://a.example/x.pdf", "x.pdf")
    mirror = sources.get("board", "https://mirror.example/x.pdf", "x.pdf")
    assert again["sha256"] == first["sha256"] == mirror["sha256"]
    assert side.stat().st_mtime_ns == stamp and side.read_bytes() == before
    # the first recorded origin stays; a mirror serving the same bytes does not replace it
    assert json.loads(before)["url"] == "https://a.example/x.pdf"


def test_get_refuses_an_html_page_saved_as_a_pdf(home, monkeypatch):
    import sources
    page = b"<!DOCTYPE html><html><body>Checking your browser before accessing...</body></html>"
    serve_bytes(monkeypatch, sources, {"https://vendor.example/ds.pdf": page})
    with pytest.raises(sources.SourceError) as err:
        sources.get("board", "https://vendor.example/ds.pdf")
    assert "HTML page, not a PDF" in str(err.value) and "by hand" in str(err.value)
    # nothing in the shared library and nothing in the project
    assert not list(sources.cache().glob("*"))
    assert not (home / "projects" / "board" / "sources").exists()
    # a name that does not claim to be a PDF is left alone
    sources.get("board", "https://vendor.example/ds.pdf", "ds.html")
    assert (home / "projects" / "board" / "sources" / "ds.html").read_bytes() == page
    assert not list(sources.cache().glob("*"))


def test_a_pdf_header_may_follow_a_bom_and_blank_lines(home, monkeypatch):
    import sources
    serve_bytes(monkeypatch, sources, {"https://v.example/a.pdf": b"\xef\xbb\xbf\r\n\r\n%PDF-1.7 body"})
    assert sources.get("board", "https://v.example/a.pdf")["bytes"] == 20


@pytest.mark.parametrize("failure, reason", [
    (urllib.error.HTTPError("https://v.example/a.pdf", 403, "Forbidden", {}, None), "HTTP 403 Forbidden"),
    (urllib.error.HTTPError("https://v.example/a.pdf", 404, "Not Found", {}, None), "HTTP 404 Not Found"),
    (urllib.error.URLError("[Errno 11001] getaddrinfo failed"), "[Errno 11001] getaddrinfo failed"),
    (TimeoutError("timed out"), "timed out"),
    (ConnectionResetError("connection reset by peer"), "connection reset by peer"),
])
def test_cli_prints_one_line_when_the_download_fails(home, monkeypatch, capsys, failure, reason):
    import sources
    url = "https://v.example/a.pdf"

    def boom(req, timeout=None):
        raise failure

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    for argv in (["get", "board", url], ["fetch", url]):
        monkeypatch.setattr(sys, "argv", ["sources.py", *argv])
        with pytest.raises(SystemExit) as exit_:
            runpy.run_path(sources.__file__, run_name="__main__")
        assert exit_.value.code not in (0, None)
        out, err = capsys.readouterr()
        assert err.splitlines() == [f"error: {url}: {reason}"]
        assert "Traceback" not in out + err
    assert not list(sources.cache().glob("*"))
    assert not (home / "projects" / "board" / "sources").exists()


def test_sidecar_is_written_with_lf_only_in_the_tracked_format(home, monkeypatch):
    import sources
    blob = b"%PDF-1.4 sidecar"
    serve_bytes(monkeypatch, sources, {"https://v.example/a.pdf": blob})
    meta = sources.fetch("https://v.example/a.pdf", "a.pdf")
    raw = (sources.cache() / "a.pdf.json").read_bytes()
    assert b"\r" not in raw and raw.endswith(b"}\n")
    # the same key order and indent as the sidecars tracked in shared/datasheets
    assert raw.decode("utf-8") == (
        '{\n  "name": "a.pdf",\n  "url": "https://v.example/a.pdf",\n'
        f'  "sha256": "{meta["sha256"]}",\n  "bytes": {len(blob)}\n}}\n')
    # and the copy a project gets is byte for byte the same
    sources.use("board", "a.pdf")
    assert (home / "projects" / "board" / "sources" / "a.pdf.json").read_bytes() == raw


def test_a_fresh_clone_restores_a_tracked_sidecar_but_does_not_let_another_url_take_its_name(home, monkeypatch):
    import sources
    serve_bytes(monkeypatch, sources, {"https://a.example/x.pdf": b"%PDF-1.4 first",
                                       "https://b.example/x.pdf": b"%PDF-1.4 other"})
    sources.fetch("https://a.example/x.pdf", "x.pdf")
    side = sources.cache() / "x.pdf.json"
    before = side.read_bytes()
    (sources.cache() / "x.pdf").unlink()          # what a clone has: the sidecar, not the file
    with pytest.raises(sources.SourceError):
        sources.fetch("https://b.example/x.pdf", "x.pdf")
    assert not (sources.cache() / "x.pdf").exists() and side.read_bytes() == before
    sources.fetch("https://a.example/x.pdf", "x.pdf")   # what `restore` does
    assert (sources.cache() / "x.pdf").read_bytes() == b"%PDF-1.4 first" and side.read_bytes() == before


def test_a_project_fetch_has_the_same_tracked_format_and_the_same_clone_rule(home, monkeypatch):
    """What `get` writes into a project is read the same way as the shared library:
    an LF sidecar, and a different document never takes a recorded name."""
    import sources
    serve_bytes(monkeypatch, sources, {"https://a.example/x.pdf": b"%PDF-1.4 first",
                                       "https://b.example/x.pdf": b"%PDF-1.4 other"})
    meta = sources.fetch("https://a.example/x.pdf", "x.pdf", project="board")
    folder = home / "projects" / "board" / "sources"
    raw = (folder / "x.pdf.json").read_bytes()
    assert b"\r" not in raw and raw.decode("utf-8") == (
        '{\n  "name": "x.pdf",\n  "url": "https://a.example/x.pdf",\n'
        f'  "sha256": "{meta["sha256"]}",\n  "bytes": {len(b"%PDF-1.4 first")}\n}}\n')
    (folder / "x.pdf").unlink()                   # a copy of the folder without the vendor files
    with pytest.raises(sources.SourceError):
        sources.fetch("https://b.example/x.pdf", "x.pdf", project="board")
    assert not (folder / "x.pdf").exists() and (folder / "x.pdf.json").read_bytes() == raw
    sources.fetch("https://a.example/x.pdf", "x.pdf", project="board")
    assert (folder / "x.pdf").read_bytes() == b"%PDF-1.4 first" and (folder / "x.pdf.json").read_bytes() == raw
    assert not list(sources.cache().glob("*"))


def test_a_part_datasheet_is_listed_under_its_project_only_and_a_general_one_under_every_project(home, monkeypatch):
    import model
    import project
    import sources
    serve_bytes(monkeypatch, sources, {"https://ti.example/app-note.pdf": b"%PDF-1.4 an application note",
                                       "https://vendor.example/mp2315.pdf": b"%PDF-1.4 a part datasheet"})
    for name in ("board", "other"):
        project.create(name)
    sources.fetch("https://ti.example/app-note.pdf", "app-note.pdf")                     # general: shared library
    sources.get("board", "https://vendor.example/mp2315.pdf", "MP2315_datasheet.pdf")    # a part of board
    mine = {(r["name"], r["scope"]) for r in model.list_sources("board")}
    theirs = {(r["name"], r["scope"]) for r in model.list_sources("other")}
    assert mine == {("app-note.pdf", "shared"), ("MP2315_datasheet.pdf", "project")}
    assert theirs == {("app-note.pdf", "shared")}


def test_verify_searches_the_project_before_the_shared_library(home, monkeypatch):
    import sources
    serve_bytes(monkeypatch, sources, {"https://v.example/note.md": b"Use a 10 uF ceramic capacitor on VIN.",
                                       "https://g.example/note.md": b"A general note about layout."})
    sources.get("board", "https://v.example/note.md")
    quote = "10 uF ceramic capacitor on VIN"
    assert not sources.verify("note.md", quote)["ok"]            # not in the shared library
    assert sources.verify("note.md", quote, project="board")["ok"]
    assert not sources.verify("note.md", quote, project="other")["ok"]
    # a project document shadows a shared one of the same name, as text_of() always did
    sources.fetch("https://g.example/note.md")
    assert sources.verify("note.md", "general note about layout")["ok"]
    assert not sources.verify("note.md", "general note about layout", project="board")["ok"]


def test_cli_verify_and_list_take_a_project(home, monkeypatch, capsys):
    import sources
    serve_bytes(monkeypatch, sources, {"https://v.example/note.md": b"Keep the loop small.",
                                       "https://g.example/guide.md": b"A guide."})
    sources.get("board", "https://v.example/note.md")
    sources.fetch("https://g.example/guide.md")

    def run(*argv):
        monkeypatch.setattr(sys, "argv", ["sources.py", *argv])
        runpy.run_path(sources.__file__, run_name="__main__")
        return capsys.readouterr().out

    assert json.loads(run("verify", "note.md", "keep the loop small", "board"))["ok"] is True
    assert json.loads(run("verify", "note.md", "keep the loop small"))["ok"] is False
    assert run("list").split() == ["guide.md", str(len(b"A guide."))]
    both = run("list", "board").splitlines()
    assert [row.split()[:2] for row in both] == [["shared", "guide.md"], ["project", "note.md"]]


def test_the_agent_is_told_where_part_datasheets_live(home):
    import workspace
    d = workspace.describe("board")
    runs = " ".join(sc["run"] for sc in d["scripts"])
    assert "sources.py get board <url>" in runs and 'verify <name> "<quote>" board' in runs
    shared = next(p for p in d["places"] if p["path"].endswith("shared/datasheets"))
    assert "GENERAL" in shared["what"] and "project's sources/" in shared["what"]
