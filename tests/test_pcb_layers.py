"""Tests for PCB layer extraction and rendering."""
import pathlib
import pytest

from scripts.altium.pcbdoc import (
    parse_arcs,
    parse_texts,
    parse_tracks,
    read_pcbdoc,
)
from scripts.preview_pcb import get_board_outline, render_pcbdoc

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "altium"


def test_pcbdoc_tracks_sane_values():
    """Reader returns tracks with sane values on finished-board.PcbDoc."""
    doc = read_pcbdoc(FIXTURES / "finished-board.PcbDoc")
    tracks = doc.get("tracks", [])
    assert len(tracks) > 0

    # Layer IDs must be ints
    assert all(isinstance(t["layer"], int) for t in tracks)

    # Widths must be > 0
    assert all(t["width_mm"] > 0 for t in tracks)

    # Coordinates inside board outline bounding box plus a margin
    outline = get_board_outline(FIXTURES / "finished-board.PcbDoc")
    assert outline is not None
    oxs = [p[0] for p in outline]
    oys = [p[1] for p in outline]
    margin = 5.0  # 5 mm tolerance margin
    min_x, max_x = min(oxs) - margin, max(oxs) + margin
    min_y, max_y = min(oys) - margin, max(oys) + margin

    for t in tracks:
        assert min_x <= t["x1_mm"] <= max_x, f"track x1 {t['x1_mm']} outside bbox"
        assert min_x <= t["x2_mm"] <= max_x, f"track x2 {t['x2_mm']} outside bbox"
        assert min_y <= t["y1_mm"] <= max_y, f"track y1 {t['y1_mm']} outside bbox"
        assert min_y <= t["y2_mm"] <= max_y, f"track y2 {t['y2_mm']} outside bbox"


def test_pcbdoc_arcs_and_texts():
    """Reader returns arcs and silkscreen texts with sane values."""
    doc = read_pcbdoc(FIXTURES / "finished-board.PcbDoc")
    arcs = doc.get("arcs", [])
    assert len(arcs) > 0
    assert all(isinstance(a["layer"], int) for a in arcs)
    assert all(a["width_mm"] > 0 for a in arcs)
    assert all(a["r_mm"] >= 0 for a in arcs)

    texts = doc.get("texts", [])
    assert len(texts) > 0
    # Texts only on silkscreen layers (33: Top Overlay, 34: Bottom Overlay)
    assert all(t["layer"] in (33, 34) for t in texts)
    assert all(isinstance(t["text"], str) and t["text"] for t in texts)
    assert all(t["height_mm"] > 0 for t in texts)
    assert all("x" in t and "y" in t and "height" in t for t in texts)


def test_pcbdoc_malformed_or_missing_streams():
    """Tolerant parsing: missing or malformed streams give empty lists, never exceptions."""
    nets = ["GND", "VCC", "5V"]

    # Empty bytes
    assert parse_tracks(b"", nets) == []
    assert parse_arcs(b"", nets) == []
    assert parse_texts(b"") == []

    # Truncated or garbage bytes
    garbage = b"\x01\x02\x03\x04\x05garbage\xff\xfe\xfd"
    assert parse_tracks(garbage, nets) == []
    assert parse_arcs(garbage, nets) == []
    assert parse_texts(garbage) == []

    # Partially valid header but truncated payload
    truncated = b"\x00\x10\x00\x00\x00short"
    assert parse_tracks(truncated, nets) == []
    assert parse_arcs(truncated, nets) == []
    assert parse_texts(truncated) == []


def test_svg_contains_new_group_ids():
    """SVG layout contains the new layer group ids and existing groups."""
    svg = render_pcbdoc(FIXTURES / "finished-board.PcbDoc")

    expected_groups = [
        'id="pcb-layer-top-copper"',
        'id="pcb-layer-bottom-copper"',
        'id="pcb-layer-inner"',
        'id="pcb-layer-vias"',
        'id="pcb-layer-silk-top"',
        'id="pcb-layer-silk-bottom"',
        'id="pcb-layer-outline"',
        'id="pcb-layer-top"',
        'id="pcb-layer-bottom"',
        'id="pcb-layer-plan"',
    ]
    for gid in expected_groups:
        assert gid in svg, f"Expected {gid} in SVG"

    # Component click targets still present
    assert 'class="pcb-comp comp-top"' in svg
    assert 'id="pcb-comp-' in svg

    # Tracks and vias rendered with classes
    assert 'class="track track-top"' in svg
    assert 'class="via"' in svg
