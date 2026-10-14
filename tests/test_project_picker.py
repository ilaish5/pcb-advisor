"""Static checks: the project selector is a dropdown menu (kit.js menu()), not an always-open list, and it is safe and accessible."""
import re

from ui_source import UI, ui_all

HTML = ui_all()
SHELL_JS = (UI / "js" / "shell.js").read_text(encoding="utf-8")
KIT_JS = (UI / "js" / "kit.js").read_text(encoding="utf-8")
CORE_JS = (UI / "js" / "core.js").read_text(encoding="utf-8")


def test_dropdown_markup_present():
    # the switcher is the kit menu: the trigger announces a popup, the list is role="menu" and starts hidden
    assert "aria-haspopup" in KIT_JS and "'menu'" in KIT_JS
    assert "aria-expanded" in KIT_JS
    assert 'role="menu"' in KIT_JS and "'menuitemradio' : 'menuitem'" in KIT_JS
    nav = re.search(r"function navHTML\(\)\s*\{(.*?)\n\}", SHELL_JS, re.S).group(1)
    assert "const switcher = menu(" in nav, "the nav's project switcher is a kit menu()"
    assert "cls: 'proj'" in nav
    assert "checked: p.name === PROJECT" in nav, "the current project is marked (aria-checked)"
    assert "label: 'New project'" in nav and "act: 'newproj'" in nav


def test_dropdown_handlers_present():
    # one handler for every menu in the app (kit.js): open, place, arrow keys, Escape, outside click
    assert "function kitMenuOpen" in KIT_JS and "function kitMenuClose" in KIT_JS
    assert "e.key === 'Escape'" in KIT_JS
    assert "'ArrowDown'" in KIT_JS and "'ArrowUp'" in KIT_JS
    # choosing a project and creating one are registered actions / delegate cases
    assert "d.proj" in CORE_JS, "the click delegate switches project on data-proj"
    assert "onAct('newproj'" in SHELL_JS


def test_names_escaped():
    # project names reach the markup through kit.js, which escapes labels and data-* values
    assert "attrs: {proj: p.name}" in SHELL_JS
    assert "kesc(it.label)" in KIT_JS
    assert re.search(r"\$\{kesc\(v\)\}", KIT_JS), "attribute values are escaped in kattrs()"
    assert "esc(ptitle)" in SHELL_JS and "esc(initials(ptitle))" in SHELL_JS, "the name on the trigger is escaped"


def test_old_always_open_list_gone():
    assert 'class="nitem" data-proj=' not in HTML
    assert 'class="nitem" data-act="newproj"' not in HTML
    assert "toggleProjMenu" not in HTML and "closeProjMenu" not in HTML
    assert "data-act=\"projmenu\"" not in HTML and "onAct('projmenu'" not in HTML


def test_new_project_asks_in_a_dialog_not_prompt():
    """prompt() is blocking, unstyled and unavailable in some embedded browsers; askText() is a native <dialog>."""
    no_prompt = r"(?<![\w.])prompt\("
    for name in ("shell.js", "palette.js", "boot.js"):   # the views' own prompt() calls belong to their owners
        text = (UI / "js" / name).read_text(encoding="utf-8")
        assert not re.search(no_prompt, text), f"window.prompt must not be used in {name}"
    assert not re.search(no_prompt, re.sub(r"/\*.*?\*/", "", CORE_JS, flags=re.S)), "window.prompt must not be used in core.js"
    assert "function askText(" in CORE_JS
    ask = re.search(r"function askText\(.*?\n\}", CORE_JS, re.S).group(0)
    assert "createElement('dialog')" in ask and "showModal()" in ask
    assert 'method="dialog"' in ask and "required" in ask, "the name is required, so an empty form cannot be submitted"
    # Enter in the field submits through the form's FIRST submit button: Cancel must not be a submit button, OK must be
    assert '<button type="button" class="btn" data-cancel>' in ask and ".close('cancel')" in ask
    assert ask.count('type="submit"') == 1 and 'value="ok"' in ask
    assert "askText({" in SHELL_JS


def test_a_menu_is_not_rebuilt_under_the_user():
    """The 4 s refresh must not close the open project menu (the nav is skipped while a menu is open and unchanged HTML is not redrawn)."""
    render_nav = re.search(r"function renderNav\(\)\s*\{(.*?)\n\}", SHELL_JS, re.S).group(1)
    assert "uiBusy()" in render_nav
    assert "lastNavHTML" in render_nav and "return;" in render_nav
