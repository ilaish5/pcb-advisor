"""Static checks: the project selector is a dropdown, not an always-open list."""
from pathlib import Path

HTML = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text(encoding="utf-8")


def test_dropdown_markup_present():
    assert 'aria-haspopup="menu"' in HTML
    assert 'aria-expanded' in HTML
    assert 'role="menu"' in HTML
    assert 'role="menuitem"' in HTML
    assert 'data-act="projmenu"' in HTML
    assert '+ New project' in HTML


def test_dropdown_handlers_present():
    assert 'function toggleProjMenu' in HTML
    assert 'function closeProjMenu' in HTML
    assert "e.key === 'Escape'" in HTML
    assert "d.act === 'projmenu'" in HTML


def test_names_escaped():
    assert 'data-proj="${esc(p.name)}"' in HTML
    assert '${esc(p.title)}' in HTML


def test_old_always_open_list_gone():
    assert 'class="nitem" data-proj=' not in HTML
    assert 'class="nitem" data-act="newproj"' not in HTML
