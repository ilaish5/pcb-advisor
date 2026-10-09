"""The document library: adding a datasheet to a project, and taking it out."""
import json


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


def test_unuse_never_touches_the_shared_library(home, tmp_path):
    import sources
    pdf = tmp_path / "vendor" / "part.pdf"
    pdf.parent.mkdir()
    pdf.write_bytes(b"%PDF-1.4 fake")
    sources.get("board", pdf.as_uri())
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
