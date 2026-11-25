"""
The proposed parts as ONE shared table (kit.js proposalTable): one row per proposal, used by the chat group card and the BOM
page, with ticks shared by proposal id, one set of button labels, a busy guard on every button and no red toast for "already
approved". Static checks in the style of test_chat_ui.py, plus a node run of the HTML builder when node is installed.
"""
import json
import re
import shutil
import subprocess

import pytest

from ui_source import UI

KIT = (UI / "js" / "kit.js").read_text(encoding="utf-8")
CHAT = (UI / "js" / "chat.js").read_text(encoding="utf-8")
BOM = (UI / "js" / "views" / "bom.js").read_text(encoding="utf-8")
CORE = (UI / "js" / "core.js").read_text(encoding="utf-8")
CHECKS = (UI / "js" / "views" / "checks.js").read_text(encoding="utf-8")
BASE_CSS = (UI / "styles" / "base.css").read_text(encoding="utf-8")


def fn(src, name):
    i = src.index(f"function {name}(")
    m = re.search(r"\n(?:function |async function |const |let |onAct\(|onChange\(|/\*)", src[i + 10:])
    return src[i:i + 10 + (m.start() if m else 20000)]


def test_both_places_use_the_one_component():
    assert "proposalTable(" in KIT
    assert "propListHTML(" in fn(CHAT, "propGroupHTML") and "proposalTable(" in fn(CHAT, "propGroupHTML")
    assert "propListHTML(" in fn(BOM, "bomPendingBox")
    # the empty state and the note above the BOM table both go through the same box
    assert BOM.count("bomPendingBox(pend") >= 2
    assert "prop-grow" not in CHAT + BOM and "<details class=\"prop-glist\"" not in CHAT


def test_the_table_has_one_row_per_proposal_and_a_tick_each():
    t = fn(KIT, "proposalRow")
    assert "<tr" in t and "data-ptick" in t and 'type="checkbox"' in t
    for col in ("MPN", "Manufacturer", "Package", "LCSC", "Value", "Role", "Why"):
        assert col in KIT
    assert "Unverified" in t and "ptr-why" in t


def test_unverified_rows_start_unticked():
    assert "unverified" in fn(CHAT, "propIsUnverified") and "!(p && propIsUnverified(p))" in fn(CHAT, "propTicked")


def test_style_is_in_the_shared_sheet_not_one_view():
    assert ".ptbl" in BASE_CSS and ".ptr.unv" in BASE_CSS
    assert ".ptbl" not in (UI / "styles" / "bom.css").read_text(encoding="utf-8")


def test_ticks_are_one_state_by_proposal_id():
    assert "let propTicks" in CHAT and "data-pids" in fn(BOM, "bomPendingBox")
    assert "propSyncUI" in CHAT and "onChange(t => t.dataset && t.dataset.ptick" in CHAT


def _code(src):
    """The source without its comments: a comment may name a button ("a delete is never part of Approve all") without drawing it."""
    return re.sub(r"(^|[^:\\'\"])//[^\n]*", r"\1", re.sub(r"/\*.*?\*/", "", src, flags=re.S))


def test_same_three_buttons_everywhere():
    a = fn(CHAT, "propActsHTML")
    assert "Approve selected (${n})" in a and "Reject selected" in a and "Approve all" in a
    assert "Approve all" not in _code(BOM) and "bom-approve-pending" not in BOM and "batch-decide" not in CHAT


def test_click_delegate_has_a_busy_guard():
    d = CORE[CORE.index("document.addEventListener('click'"):CORE.index("document.addEventListener('change'")]
    assert "BUSY.has(busyId)) return;" in d and "BUSY.add(busyId)" in d and "finally" in d and "BUSY.delete(busyId)" in d


def test_already_decided_is_not_a_red_toast():
    assert "PROP_ALREADY_DECIDED" in CORE and "{bad: false}" in CORE[CORE.index("PROP_ALREADY_DECIDED.test"):][:400]
    assert "PROP_ALREADY" in fn(CHAT, "propGroupHTML") or "PROP_ALREADY.test" in CHAT


def test_confirming_pins_is_one_part_at_a_time():
    """A modal dialog per part (views/pins.js), guarded against a second open while the first awaits: no row slides under the pointer."""
    pins = (UI / "js" / "views" / "pins.js").read_text(encoding="utf-8")
    h = pins[pins.index("let pinsOpen"):pins.index("onAct('confirm-pins'")]
    assert "if (pinsOpen) return;" in h and "finally { pinsOpen = false; }" in h and "showModal()" in h
    assert "accept-pins" not in CHECKS


def test_builder_output_has_one_row_per_proposal(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    rows = [{"id": f"p{i}", "ref": f"R{i}", "mpn": f"M{i}", "checked": i != 1, "unverified": i == 1, "reason": "why <b>"} for i in range(3)]
    script = ("global.window=global;global.addEventListener=()=>{};global.document={addEventListener(){},querySelector(){return null},documentElement:{}};"
              + KIT + ";process.stdout.write(JSON.stringify(proposalTable(" + json.dumps(rows) + ",{})));")
    js = tmp_path / "builder.js"  # a file, not -e: Windows caps command lines at 8191/32767 chars
    js.write_text(script, encoding="utf-8")
    r = subprocess.run([node, str(js)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    html = json.loads(r.stdout)
    body = html[html.index("<tbody>"):]
    assert body.count("<tr ") == 3 and body.count('type="checkbox"') == 3
    assert body.count(" checked") == 2 and body.count("Unverified") == 1 and "why &lt;b&gt;" in body


def _node():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    return node


def run_node(script):
    r = subprocess.run([_node(), "-"], input=script, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_busy_guard_is_keyed_by_the_action_so_a_replaced_button_is_still_busy():
    # a background render replaces the button element; the second click lands on a new element of the same action
    script = (CORE[CORE.index("function busyKey("):CORE.index("document.addEventListener('click'")] + "const BUSY=new Set();"
              "const mk=(ds,pids)=>({dataset:ds,textContent:'x',closest:()=>pids?{dataset:{pids}}:null});"
              "const a=mk({act:'prop-decide',scope:'all',decision:'approved'},'p1,p2');"
              "const a2=mk({decision:'approved',scope:'all',act:'prop-decide'},'p1,p2');"
              "const other=mk({act:'prop-decide',scope:'all',decision:'approved'},'p3');"
              "const rej=mk({act:'prop-decide',scope:'all',decision:'rejected'},'p1,p2');"
              "BUSY.add(busyKey(a));"
              "process.stdout.write(JSON.stringify([BUSY.has(busyKey(a2)),BUSY.has(busyKey(other)),BUSY.has(busyKey(rej))]));")
    assert run_node(script) == [True, False, False]


def _acts_harness(proposals, tail):
    return ("const S={proposals:" + json.dumps(proposals) + "};let propTicks={};"
            "const esc=s=>String(s);const btn=(label,o)=>'<button>'+label+'</button>';"
            + fn(CHAT, "propIsUnverified") + fn(CHAT, "propTicked") + fn(CHAT, "propUnverifiedIds") + fn(CHAT, "propActsHTML") + tail)


def test_approve_all_says_how_many_are_unverified_and_acts_at_once_when_none():
    props = [{"id": "p1", "changes": {"mpn": "OK1"}}, {"id": "p2", "changes": {"mpn": "XX (unverified)"}},
             {"id": "p3", "changes": {"mpn": "OK3", "notes": "unverified"}}]
    out = run_node(_acts_harness(props, "process.stdout.write(JSON.stringify([propActsHTML(['p1','p2','p3'],true),propActsHTML(['p1'],true)]));"))
    assert "Approve all (2 unverified)" in out[0] and "Approve all (" not in out[1] and "Approve all<" in out[1]
    h = fn(CHAT, "propActsHTML")
    assert h.count("Approve all") >= 2


def test_approve_all_confirms_the_unverified_rows_once_in_the_apps_dialog():
    h = CHAT[CHAT.index("onAct('prop-decide'"):]
    h = h[:h.index("setState(r)")]
    assert "propUnverifiedIds(ids)" in h and "askChoice(" in h and "window.confirm" not in h and "confirm(" not in h.replace("askChoice", "")
    assert "r.ref" in h and "r.mpn" in h and "if (ok !== true) return;" in h
    assert h.count("askChoice(") == 1
    # only the approve-all scope asks; approving the ticked rows or rejecting never does
    assert "d.scope === 'all' && d.decision === 'approved'" in h
    dlg = fn(CORE, "askChoice")
    assert "o.list" in dlg and "o.no === false" in dlg
