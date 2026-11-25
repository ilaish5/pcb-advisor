"""UI findings of the two E2E runs of 25/11/2026 (new board, Climate logger): U1-U12. Server logic runs for real; browser logic runs
under node (skipped without it); pure layout and wiring is checked as source (there is no browser in the suite)."""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

import altium
import background
import check_availability
import lineage
import stages
import store
import turn_truth
import workspace
from altium import bridge
from test_chat_turns import call, server  # noqa: F401
from ui_source import ui_css, ui_html, ui_js

REPO = pathlib.Path(__file__).resolve().parent.parent


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
def _cards(n):
    return [f"bom.propose:R{i}" for i in range(1, n + 1)], [f"p{i}" for i in range(1, n + 1)]


def test_all_n_lines_after_a_pick_verb_is_checked_against_the_real_cards():
    fix = turn_truth.card_correction("I picked all 11 lines from the idea.", *_cards(10))
    assert "10" in fix and "11" in fix
    assert turn_truth.card_correction("I picked all 10 lines from the idea.", *_cards(10)) == ""
    assert turn_truth.card_correction("I listed 40 lines of text.", *_cards(10)) == ""


@pytest.mark.parametrize("reply, cards", [
    ("Select the 3 cards above and approve them.", 0),
    ("Your BOM lists 14 lines now.", 2),
    ("Pick the 4 proposals you want to keep.", 1),
])
def test_an_instruction_or_a_present_tense_count_is_not_corrected(reply, cards):
    assert turn_truth.card_correction(reply, *_cards(cards)) == ""


# ---- U3 / U4: stages
def _held(monkeypatch, block="Not made yet: the board was never checked", warning=""):
    monkeypatch.setattr(store, "manufacturing_block", lambda p: block)
    monkeypatch.setattr(store, "manufacturing_warning", lambda p: warning)


def test_outputs_of_a_board_never_started_is_neutral_but_still_held(empty, monkeypatch):
    _held(monkeypatch)
    st = stages.outputs_stage(empty, {})
    assert st["state"] == "not_started" and not st.get("severity") and not st.get("open")
    assert st["gate"]["blocked"] and st["gate"]["quiet"] and "never checked" in st["gate"]["why"]      # the files stay refused


def test_a_design_blocker_stays_red_even_before_the_board(empty, monkeypatch):
    _held(monkeypatch, "Not made yet: 2 pins have no net. Also: the board was never checked", "Not made yet: 2 pins have no net")
    st = stages.outputs_stage(empty, {})
    assert st["state"] == "blocked" and st["gate"]["design"].startswith("Not made yet: 2 pins")
    assert st["gate"]["board_started"] is False and not st["gate"]["quiet"]


def test_a_board_placed_but_never_checked_still_blocks(empty, monkeypatch):
    _held(monkeypatch, "Not made yet: the board was routed but never checked")
    st = stages.outputs_stage(empty, {"altium_ok": {"place-pcb": True}})
    assert st["state"] == "blocked" and st["gate"]["board_started"] is True and not st["gate"]["quiet"]


def _linked_board(monkeypatch, tmp_path, doc):
    pcb = tmp_path / "B.PcbDoc"
    pcb.write_bytes(b"x")
    monkeypatch.setattr(lineage, "linked_pcb", lambda p: pcb)
    monkeypatch.setattr(altium, "read_pcbdoc", lambda p, **k: doc)
    stages._PCB_MEMO.clear()


@pytest.mark.parametrize("doc, label", [
    ({"components": [{"ref": "R1"}], "tracks": []}, "Route the board"),
    ({"components": [{"ref": "R1"}], "tracks": [{"net": "GND"}]}, "Check the board"),
])
def test_a_board_made_by_hand_in_altium_counts_as_started(empty, tmp_path, monkeypatch, doc, label):
    _linked_board(monkeypatch, tmp_path, doc)
    _held(monkeypatch)
    st = stages.outputs_stage(empty, {})
    assert st["state"] == "blocked" and st["gate"]["board_started"] and st["next"]["label"] == label


def test_an_empty_linked_board_is_still_not_started(empty, tmp_path, monkeypatch):
    _linked_board(monkeypatch, tmp_path, {"components": [], "tracks": [{"net": None}]})
    _held(monkeypatch)
    assert stages.outputs_stage(empty, {})["state"] == "not_started"


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


# ---- U8: the LCSC code of a new part is looked up for its card
def _new_card(project, mpn, ref="R90"):
    return store.propose_bom(project, ref, {"mpn": mpn, "value": "10k"}, new=True)["id"]


@pytest.mark.parametrize("found, shown", [
    ({"exact": True, "code": "C25804", "model": "RC0603FR-0710KL"}, "C25804"),
    ({"exact": False, "code": "C1", "model": "RC0603FR-0710KL"}, None),
    ({"exact": True, "code": "C2", "model": "ANOTHER-PART"}, None),
    (None, None),
])
def test_a_new_card_gets_the_lcsc_code_of_exactly_its_mpn_and_the_change_is_untouched(empty, monkeypatch, found, shown):
    monkeypatch.setattr(check_availability, "lcsc_by_mpn", lambda m: found)
    monkeypatch.setattr(background, "STOCK_GAP", 0)
    pid = _new_card(empty, "RC0603FR-0710KL")
    background.proposal_lcsc_job(empty, pid)
    prop = next(x for x in store.proposals(empty) if x["id"] == pid)
    assert prop.get("lcsc_match") == shown and prop["status"] == "pending" and "lcsc" not in prop["changes"]


def test_the_match_reaches_the_browser_state_through_the_real_search_shape(server, empty, monkeypatch, real_lcsc_lookup):    # noqa: F811
    import jlc
    import serve
    monkeypatch.setattr(jlc, "search", lambda *a, **k: [{"mpn": "RC0603FR-0710KL", "code": "C25804", "stock": 5, "price_breaks": []}])
    monkeypatch.setattr(background, "STOCK_GAP", 0)
    monkeypatch.setattr(serve, "recheck_async", lambda project, key: None)
    pid = _new_card(empty, "RC0603FR-0710KL")
    serve.recheck_missing(empty)                    # the one sweep every proposal source ends in
    assert background.wait_idle(10)
    _, state = call(server, "GET", "/api/state", empty)
    assert next(p for p in state["proposals"] if p["id"] == pid)["lcsc_match"] == "C25804"


def test_a_late_answer_for_a_card_that_is_gone_makes_no_row(empty):
    store.append(empty, "proposals.jsonl", {"id": "p-gone", "ts": store.now_ms(), "lcsc_match": "C1"})
    assert not [p for p in store.proposals(empty) if p["id"] == "p-gone"]


# ---- U9: an approval links the datasheet that is already in Sources, once per click
def test_approving_a_card_links_a_datasheet_already_in_sources(server, empty, monkeypatch):    # noqa: F811
    seen = []
    monkeypatch.setattr(store, "auto_attach", lambda p: seen.append(p) or {})
    pid = _new_card(empty, "RC0603FR-0710KL")
    code, _ = call(server, "POST", "/api/proposal", empty, {"id": pid, "decision": "approved"})
    assert code == 200 and seen == [empty]


def test_approve_all_links_datasheets_once(server, empty, monkeypatch):    # noqa: F811
    seen = []
    monkeypatch.setattr(store, "auto_attach", lambda p: seen.append(p) or {})
    ids = [_new_card(empty, "", ref) for ref in ("R91", "R92", "R93")]
    code, body = call(server, "POST", "/api/proposals/batch", empty, {"ids": ids, "decision": "approved"})
    assert code == 200 and all(r["ok"] for r in body["results"]) and seen == [empty]


# ---- browser logic, run under node
def _js(rel):
    return (REPO / "ui" / "js" / rel).read_text(encoding="utf-8")


def _piece(text, start, end="\n}\n"):
    i = text.index(start)
    return text[i:text.index(end, i) + len(end)]


def _node(script, tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    (tmp_path / "t.js").write_text(script, encoding="utf-8")
    r = subprocess.run([node, str(tmp_path / "t.js")], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_u2_a_changed_link_reads_the_state_pictures_and_banner_again(tmp_path):
    pages = _js("views/pages.js")
    out = _node("""
const log = [];
var impFor = 'x', svgCache = {key: 'a', text: 'a'}, pcbSvgCache = {key: 'b', text: 'b'}, pvSchErr = 'e', pvPcbErr = 'e';
var libNote = {text: 'No Altium project is linked yet'};
const refresh = async f => log.push('refresh:' + f), renderCenter = f => log.push('center:' + f), readyLoad = () => log.push('ready');
var ALTIUM_DATA, ALTIUM_ERR; const api = async p => { log.push(p); return {}; };
""" + _piece(pages, "async function pgLinkChanged") + _piece(pages, "async function pgLink(path)") + """
pgLink('p').then(() => console.log(JSON.stringify({log, impFor, svg: svgCache.key + pcbSvgCache.key, err: pvSchErr + pvPcbErr, libNote})));
""", tmp_path)
    assert out == {"log": ["/api/altium/link", "refresh:true", "center:true", "ready"], "impFor": None, "svg": "", "err": "", "libNote": None}


def test_u8_the_code_beside_a_card_is_never_another_parts(tmp_path):
    out = _node(_piece(_js("chat.js"), "function propKnownLcsc") + """
const known = {mpn: 'A', lcsc: 'C1', supply: {LCSC: {code: 'C1'}}};
const bad = {mpn: 'A', lcsc: 'C9', supply: {LCSC: {code: 'C9', code_mismatch: 'C9 is another part'}}};
console.log(JSON.stringify([propKnownLcsc({}, known), propKnownLcsc({mpn: 'A'}, known), propKnownLcsc({mpn: 'B'}, known),
  propKnownLcsc({}, bad), propKnownLcsc({}, {supply: {LCSC: {code: 'C5'}}}), propKnownLcsc({mpn: 'B'}, {}),
  propKnownLcsc({}, {supply: {Mouser: {code: '603-RC0603'}}})]));
""", tmp_path)
    assert out == ["C1", "C1", "", "", "C5", "", ""]


@pytest.mark.parametrize("card_shown", [True, False])
def test_u11_the_chip_stays_on_the_card_it_finds(tmp_path, card_shown):
    out = _node("""
const log = [], ACT = {}; const onAct = (n, f) => { ACT[n] = f; };
let shown = %s;
const row = {scrollIntoView: () => log.push('scroll'), classList: {add: c => log.push(c), remove() {}}, getClientRects: () => [1], closest: () => null};
const hidden = {getClientRects: () => [], scrollIntoView: () => log.push('hidden')};     // the same card on a view that is not shown
globalThis.document = {querySelectorAll: () => shown ? [hidden, row] : [hidden]}; globalThis.CSS = {escape: x => x};
globalThis.setTimeout = f => f();
const S = {proposals: [{id: 'p1', status: 'pending', line: 'R1', changes: {}}]};
const lineOfRef = () => null, select = () => log.push('select'), toast = () => log.push('toast');
const go = (a, b) => { log.push('go:' + b); shown = true; };
""" % json.dumps(card_shown) + _piece(_js("chat.js"), "onAct('chat-act-open'", "\n});\n") + """
ACT['chat-act-open']({}, {ref: 'R1'}).then(() => console.log(JSON.stringify(log)));
""", tmp_path)
    assert out == (["scroll", "flash"] if card_shown else ["go:bom", "scroll", "flash"])


def test_u12_a_background_redraw_waits_for_the_mouse_to_come_up(tmp_path):
    core = _js("core.js")
    out = _node("""
const on = {}, later = []; let drawn = 0;
globalThis.document = {addEventListener: (t, f) => { on[t] = f; }};
globalThis.setTimeout = f => later.push(f);
var S = {title: 'x'}, pendingRender = false;
const uiBusy = () => false, renderNav = () => { drawn++; }, renderChat = () => {};
""" + _piece(core, "let uiPressed = false;", "document.addEventListener('pointercancel', uiRelease, true);\n")
        + _piece(core, "function render(force)").split("  const key = ")[0] + "}\n" + """
const out = [];
on.pointerdown({target: {closest: () => ({})}});
render(); out.push(drawn);          // pressed: the poll's redraw waits
render(true); out.push(drawn);      // the redraw after an action never waits
on.pointerup(); later.forEach(f => f()); out.push(drawn);
console.log(JSON.stringify(out));
""", tmp_path)
    assert out == [0, 1, 2]


# ---- layout and wiring, as source
def test_u1_the_readiness_note_is_in_the_flow_and_the_link_problem_is_shown_once():
    html, css, js = ui_html(), ui_css(), ui_js()
    assert html.index('id="ready"') > html.index('id="work"') and html.index('id="ready"') < html.index('id="view"')
    assert not re.search(r"\.ready\{[^}]*position:fixed", css)
    assert ".work:has(>#detail:not([hidden])) .ready{padding-right:" in css       # the open inspector never covers its buttons
    assert "READY_ONCE_IDS" in js and "readyOnceHidden" in js


def test_u3_the_schematic_page_leaves_out_a_board_that_is_not_there_yet():
    js = ui_js()
    assert "outBlockNote('sch')" in js and "g.quiet" in js and "board_started === false" in js


def test_u7_the_bom_part_column_keeps_a_width_on_a_phone():
    assert re.search(r"\.bom-tbl \.c-part\{[^}]*min-width:96px", ui_css())


def test_u2_u8_u11_wiring():
    js = ui_js()
    assert js.count("await pgLinkChanged()") >= 3 and "S.rev" in js[js.index("const pvSheetKey"):][:200]
    assert "propKnownLcsc(c, known) || p.lcsc_match" in js
    assert js.count("chatActChip(a, 'ok', a)") == 2 and "tr.ptr.flash" in ui_css()
