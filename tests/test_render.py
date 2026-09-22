"""
The picture.

These are the two faults the export shipped with: edges nobody drew, and an
aspect ratio that made them too small to notice.
"""
import pytest

render_schematic = pytest.importorskip(
    "render_schematic", reason="the drawing stack is optional")

import matplotlib.pyplot as plt  # noqa: E402
import model                     # noqa: E402


@pytest.fixture
def drawn(battery_mcu):
    """A board with a real sketch and several parts the decisions added."""
    import json
    import workspace
    path = workspace.projects_dir() / battery_mcu / "decisions.jsonl"
    with open(path, "a", encoding="utf-8") as fh:
        for node, value in (("power.topology", "linear"), ("power.testpoint", "yes_tp"),
                            ("power.protection", "pfet"), ("mcu.clock", "crystal")):
            fh.write(json.dumps({"ts": "2026-01-01T00:00:03", "by": "user",
                                 "node": node, "value": value}) + "\n")
    return battery_mcu


def test_no_edge_is_drawn_that_the_student_did_not_draw(drawn):
    """The cascade renderer used to take its arrows from adjacency in a list
    sorted by an authoring field, asserting that a test point sat in series
    between a crystal and a debug header."""
    m = model.build(project=drawn)
    drawn_links = {tuple(l) for l in m["links"]}
    sketched = {tuple(l) for l in m["sketch"]["links"]}
    assert drawn_links == sketched
    # and every one of them joins two blocks that are actually on the board
    on_board = {b["id"] for b in m["blocks"]}
    assert all(a in on_board and b in on_board for a, b in drawn_links)


def test_parts_the_decisions_added_are_on_the_board_but_unwired(drawn):
    m = model.build(project=drawn)
    joined = {i for l in m["links"] for i in l}
    added = [b["id"] for b in m["blocks"] if b.get("from") != "sketch"]
    assert added                                  # the decisions did add parts
    assert not (set(added) & joined)              # and none of them is wired up


def test_the_export_is_shaped_like_a_page_not_a_ribbon(drawn):
    """Eight blocks used to export at 1600x142 - 11:1, in which the text was
    illegible and the wrong arrows were invisible."""
    from PIL import Image
    _, png = render_schematic.render(drawn)
    im = Image.open(png)
    assert 0.25 < im.width / im.height < 4.0, f"{im.width}x{im.height}"


def test_rendering_leaks_no_figures(drawn):
    """schemdraw's backend opens a pyplot figure per drawing. redraw() runs
    after every applied action, so this leaked one per decision."""
    plt.close("all")
    for _ in range(5):
        render_schematic.render(drawn)
    assert plt.get_fignums() == []


def test_the_export_carries_a_legend_for_the_designators_it_prints(drawn):
    m = model.build(project=drawn)
    assert m["designators"], "this board does print designators"
    text = render_schematic.legend_text(m)
    for row in m["designators"]:
        assert f"{row['prefix']} = {row['means']}" in text


def test_a_board_with_no_designators_gets_no_legend_line(board):
    m = model.build(project=board(blocks=(("BAT", "power_in"),), confirmed=False))
    assert render_schematic.legend_text(m) == ""


def test_an_empty_sketch_still_renders(board):
    p = board(blocks=(), confirmed=False)
    svg, _ = render_schematic.render(p)
    assert svg.exists() and svg.stat().st_size > 0
