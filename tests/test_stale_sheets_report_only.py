"""Stale empty sheets: removal through Altium's script API duplicated [Document] sections in a live PrjPcb, so after a draw the tool
only REPORTS an empty, tool-made, unused sheet; it never changes the project or deletes a file."""
import pathlib

import store
from altium import bridge
from test_altium_draw import drawn  # noqa: F401  (the fixture)


def test_a_draw_reports_but_never_removes_empty_unused_tool_made_sheets(drawn, monkeypatch):
    project, fake, saved = drawn
    prj = bridge._linked(project)
    bridge.add_sheet(project, "Old placeholder")                      # made by the tool, empty
    bridge.add_sheet(project, "Has content")                          # made by the tool, but holds a drawing
    student = prj.parent / "Student notes.SchDoc"                     # not made by the tool, empty
    student.write_bytes(b"x")
    bridge.run_commands([("PROJECT", str(prj)), ("ADDDOC", str(prj), str(student)), ("SAVEPRJ", str(prj))])
    import altium.schdoc
    monkeypatch.setattr(altium.schdoc, "is_blank_sheet", lambda path: pathlib.Path(path).name in {"Old placeholder.SchDoc", "Student notes.SchDoc"})
    before_prj = prj.read_bytes()
    sent = []
    real = bridge.run_commands
    monkeypatch.setattr(bridge, "run_commands", lambda commands, **kw: (sent.extend(c[0] for c in commands), real(commands, **kw))[1])
    res = bridge.draw_schematic(project, replace=True)
    assert res["stale"]["removed"] == []
    assert [x["name"] for x in res["stale"]["left"]] == ["Old placeholder.SchDoc"]
    assert "Remove from Project" in res["stale"]["left"][0]["why"]
    assert any("Old placeholder" in w for w in res["warnings"]) and not any("Has content" in w or "Student" in w for w in res["warnings"])
    assert "REMDOC" not in sent
    assert (prj.parent / "Old placeholder.SchDoc").exists() and (prj.parent / "Has content.SchDoc").exists() and student.exists()
    assert not any(e["op"] == "remove-stale-sheets" for e in store.read_jsonl(store.pdir(project) / "altium-log.jsonl"))
    assert prj.read_bytes().count(b"[Document") == before_prj.count(b"[Document")      # no document sections added or lost
