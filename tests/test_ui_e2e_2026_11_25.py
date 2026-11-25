"""UI findings of the two E2E runs of 25/11/2026 (new board, Climate logger): U1-U12. Server logic runs for real; the browser code is
checked as source (there is no browser in the suite)."""
import re

import pytest

import stages
import store
import turn_truth
import workspace
from altium import bridge
from test_chat_turns import call, server  # noqa: F401
from ui_source import ui_css, ui_html, ui_js


# ---- U10: refuse first, write nothing
def test_create_project_on_a_host_that_is_not_windows_writes_nothing(empty, tmp_path, monkeypatch, real_host_check):
    base = tmp_path / "altium-base"
    workspace.set_value("altium.projects_dir", str(base))
    monkeypatch.setattr(bridge.sys, "platform", "linux")
    ran = []
    monkeypatch.setattr(bridge, "run_commands", lambda *a, **k: ran.append(a))
    with pytest.raises(bridge.BridgeError, match="not Windows"):
        bridge.new_project(empty)
    assert not base.exists() and not ran


# ---- U5: the count the reply states is the count of cards
def test_all_n_lines_after_a_pick_verb_is_checked_against_the_real_cards():
    applied = [{"tool": "bom.propose", "id": f"R{i}"} for i in range(1, 11)]
    props = [{"id": f"p{i}", "kind": "bom_line"} for i in range(1, 11)]
    fix = turn_truth.card_correction("I picked all 11 lines from the idea.", applied, props)
    assert "10" in fix and "11" in fix
    assert turn_truth.card_correction("I picked all 10 lines from the idea.", applied, props) == ""
    assert turn_truth.card_correction("I listed 40 lines of text.", applied, props) == ""


# ---- U3 / U4: stages
def test_outputs_of_a_board_never_started_is_neutral_but_still_held(empty, monkeypatch):
    monkeypatch.setattr(store, "manufacturing_block", lambda p: "Not made yet: the board was never checked")
    monkeypatch.setattr(store, "manufacturing_warning", lambda p: "")
    st = stages.outputs_stage(empty, {})
    assert st["state"] == "not_started" and not st.get("severity") and not st.get("open")
    assert st["gate"]["blocked"] and st["gate"]["quiet"] and "never checked" in st["gate"]["why"]      # the files stay refused


def test_a_design_blocker_stays_red_even_before_the_board(empty, monkeypatch):
    monkeypatch.setattr(store, "manufacturing_block", lambda p: "Not made yet: 2 pins have no net. Also: the board was never checked")
    monkeypatch.setattr(store, "manufacturing_warning", lambda p: "Not made yet: 2 pins have no net")
    st = stages.outputs_stage(empty, {})
    assert st["state"] == "blocked" and st["gate"]["design"].startswith("Not made yet: 2 pins")
    assert st["gate"]["board_started"] is False and not st["gate"]["quiet"]


def test_a_board_placed_but_never_checked_still_blocks(empty, monkeypatch):
    monkeypatch.setattr(store, "manufacturing_block", lambda p: "Not made yet: the board was routed but never checked")
    monkeypatch.setattr(store, "manufacturing_warning", lambda p: "")
    st = stages.outputs_stage(empty, {"altium_ok": {"place-pcb": True}})
    assert st["state"] == "blocked" and st["gate"]["board_started"] is True and not st["gate"]["quiet"]


def test_bom_stage_without_parts_points_at_the_parts_once_the_idea_is_confirmed():
    confirmed = stages.bom_stage({"bom": [], "idea": {"confirmed": True}})
    assert confirmed["next"]["label"] == "Propose the parts"
    assert stages.bom_stage({"bom": [], "idea": {}})["next"]["label"] == "Confirm the idea"


# ---- U6: a note is cut at the frame, never run past it
def test_a_long_sheet_note_is_wrapped_inside_its_frame():
    from scripts.skills import render_sheet
    note = "Expose the pad and keep the loop short " * 8
    secs = [{"id": "A", "title": "T"}]
    parts = [{"ref": "R1", "section": "A", "pins": [{"name": "1", "num": "1", "net": "X"}, {"name": "2", "num": "2", "net": "GND"}]}]
    svg = render_sheet.render_sheet({"sections": secs, "parts": parts, "notes": [{"section": "A", "text": note}]}, [], [])
    lines = re.findall(r'<text[^>]*class="note"[^>]*>([^<]*)</text>', svg)
    lines = [x for x in lines if not x.startswith("rendered")]
    assert len(lines) > 1 and " ".join(lines).split() == note.split()
    assert all(len(x) * render_sheet.CW < 900 for x in lines)


# ---- U9: an approval links the datasheet that is already in Sources
def test_approving_a_card_links_a_datasheet_already_in_sources(server, lte, monkeypatch):    # noqa: F811
    seen = []
    monkeypatch.setattr(store, "auto_attach", lambda p: seen.append(p) or {})
    pend = [p for p in store.proposals(lte) if p.get("status") == "pending"]
    if not pend:
        store.add_proposal(lte, "bom_line", {"line": "R99", "changes": {"value": "10k"}}) if hasattr(store, "add_proposal") else None
        pend = [p for p in store.proposals(lte) if p.get("status") == "pending"]
    if not pend:
        pytest.skip("fixture has no pending proposal")
    code, _ = call(server, "POST", "/api/proposal", lte, {"id": pend[0]["id"], "decision": "approved"})
    assert code == 200 and seen


# ---- browser code, as source
def test_u1_the_readiness_note_is_in_the_flow_and_the_link_problem_is_shown_once():
    html, css, js = ui_html(), ui_css(), ui_js()
    assert html.index('id="ready"') > html.index('id="work"') and html.index('id="ready"') < html.index('id="view"')
    assert not re.search(r"\.ready\{[^}]*position:fixed", css)
    assert "READY_ONCE_IDS" in js and "readyOnceHidden" in js


def test_u2_the_sheet_picture_and_the_link_views_are_read_again():
    js = ui_js()
    assert "S.rev" in js[js.index("const pvSheetKey"):][:200]
    body = js[js.index("async function pgLinkChanged"):][:600]
    assert js.count("await pgLinkChanged()") >= 3
    assert "refresh(true)" in body and "readyLoad()" in body and "pcbSvgCache" in body


def test_u3_the_schematic_page_leaves_out_a_board_that_is_not_there_yet():
    js = ui_js()
    assert "outBlockNote('sch')" in js and "g.quiet" in js and "board_started === false" in js


def test_u7_the_bom_part_column_keeps_a_width_on_a_phone():
    assert re.search(r"\.bom-tbl \.c-part\{[^}]*min-width:96px", ui_css())


def test_u8_the_proposal_row_falls_back_to_the_lcsc_the_line_or_the_stock_check_knows():
    assert "known.lcsc" in ui_js() and "Object.values(sup).find(v => v && v.code)" in ui_js()


def test_u11_the_proposal_chip_opens_its_card():
    js = ui_js()
    assert "chat-act-open" in js and js.count("chatActChip(a, 'ok', a)") == 2 and "tr.ptr.flash" in ui_css()


def test_u12_a_background_redraw_never_replaces_a_button_under_the_mouse():
    js = ui_js()
    assert "if (uiPressed && !force) return;" in js and "uiRelease" in js
