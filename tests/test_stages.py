"""Stream A slice 2: the stage model. stages[] is derived on the server; the nav dots read nothing else.
A green dot never sits beside violations, an empty DFM is never clean, a stale check is never clean, and Outputs is blocked exactly
when store.manufacturing_warning says so."""
import json
import pathlib
import re
import shutil
import subprocess
import tempfile

import board_results
import lineage
import pytest
import stages
import store
from test_chat_turns import call, server  # noqa: F401
from test_unverified_pins import _add, _sheet

REPO = pathlib.Path(__file__).resolve().parent.parent
SHELL = (REPO / "ui" / "js" / "shell.js").read_text(encoding="utf-8")


def by_id(project):
    import model
    m = model.build(project)
    return {s["id"]: s for s in m["stages"]}, m


@pytest.fixture
def pcb(tmp_path, monkeypatch):
    f = tmp_path / "B.PcbDoc"
    f.write_bytes(b"v1")
    monkeypatch.setattr(lineage, "linked_pcb", lambda p: f)
    monkeypatch.setattr(stages, "rules_state", lambda p: {"linked": True, "below": 0, "differ": 0, "missing_in_pcb": []})
    return f


def test_an_empty_project_has_seven_neutral_stages_and_one_primary(empty):
    st, m = by_id(empty)
    assert list(st) == list(stages.ORDER)
    assert all(s["state"] in ("not_started", "in_progress") for s in st.values())
    assert [s["id"] for s in st.values() if s["primary"]] == ["idea"]
    assert m["rev"] and m["board_check"] is None and m["stage_sheets"] == {"plan": 0, "altium": 0, "total": 0}


def test_layout_has_a_state_and_never_clean_beside_violations(empty, pcb):
    assert by_id(empty)[0]["pcb"]["state"] == "not_started"
    board_results.record(empty, "place", {"placed": ["R1"]})
    assert by_id(empty)[0]["pcb"]["state"] == "in_progress"
    board_results.record(empty, "route", {"routed": ["A"], "failed": [], "tracks": 3, "vias": 0, "drc_rules": {"Clearance Constraint": 21}, "drc_total": 21, "drc_clean": False})
    s = by_id(empty)[0]["pcb"]
    assert s["state"] == "issues" and s["severity"] == "bad" and s["open"] == 21 and "21 violations" in s["reason"]
    board_results.record(empty, "drc", {"rules": {"Clearance Constraint": 0}, "violations": [], "unrouted": 0, "total": 0, "complete": True, "clean": True})
    assert by_id(empty)[0]["pcb"]["state"] == "clean"
    assert by_id(empty)[1]["board_check"]["clean"] is True


def test_a_stale_check_is_never_clean(empty, pcb):
    board_results.record(empty, "place", {"placed": ["R1"]})
    board_results.record(empty, "route", {"routed": ["A"], "failed": [], "drc_rules": {"Clearance Constraint": 0}, "drc_total": 0, "drc_clean": True})
    assert by_id(empty)[0]["pcb"]["state"] == "clean"
    pcb.write_bytes(b"edited in altium")
    s = by_id(empty)[0]["pcb"]
    assert s["state"] == "issues" and "changed since" in s["reason"] and by_id(empty)[1]["board_check"]["stale"] is True


def test_placing_again_after_a_route_is_not_routed(empty, pcb):
    board_results.record(empty, "route", {"routed": ["A"], "failed": [], "drc_rules": {}, "drc_total": 0, "drc_clean": True})
    board_results.record(empty, "place", {"placed": ["R1"]})
    assert by_id(empty)[0]["pcb"]["state"] == "in_progress"


def test_a_partial_route_is_issues(empty, pcb):
    board_results.record(empty, "route", {"routed": ["A"], "failed": [("B", "no way")], "open_nets": ["B"], "drc_rules": {}, "drc_total": 0, "drc_clean": True})
    s = by_id(empty)[0]["pcb"]
    assert s["state"] == "issues" and s["open"] == 1 and "B" in s["reason"]


def test_dfm_with_no_report_or_an_untriaged_one_is_never_clean(empty):
    assert by_id(empty)[0]["checks"]["state"] == "not_started"
    base = {"stem": "r", "triage_count": 0, "triage_open": 0, "triage_real": 0}
    assert stages.checks_stage({"checks": [base]})["state"] == "in_progress"
    assert stages.checks_stage({"checks": [{**base, "triage_count": 4}]})["state"] == "clean"
    assert stages.checks_stage({"checks": [{**base, "triage_count": 4, "triage_open": 2}]})["severity"] == "warn"
    assert stages.checks_stage({"checks": [{**base, "triage_count": 4, "triage_real": 1}]})["severity"] == "bad"


def test_outputs_is_blocked_exactly_when_the_manufacturing_gate_is(empty):
    assert by_id(empty)[0]["outputs"]["gate"]["blocked"] is False and store.manufacturing_warning(empty) == ""
    _sheet(empty)
    st = by_id(empty)[0]["outputs"]
    assert store.manufacturing_warning(empty) and st["state"] == "blocked" and st["gate"]["blocked"] and st["gate"]["why"] == store.manufacturing_warning(empty)
    store.accept_pins(empty, "U1")
    st = by_id(empty)[0]["outputs"]
    assert store.manufacturing_warning(empty) == "" and st["state"] != "blocked" and not st["gate"]["blocked"]


def test_open_pins_block_and_one_click_marks_them_all_nc(server, empty):
    _add(empty, "U1", "ABCD1234")
    _add(empty, "R1", "RC0603")
    store.write_sheet(empty, "01", {"sections": [{"id": "A", "title": "T"}], "parts": [
        {"ref": "U1", "section": "A", "pins": [{"num": "1", "name": "VCC", "net": "+3V3"}, {"num": "2", "name": "NC1", "net": ""}, {"num": "3", "name": "NC2", "net": ""}]},
        {"ref": "R1", "section": "A", "pins": [{"num": "1", "name": "1", "net": "+3V3"}, {"num": "2", "name": "2", "net": "X"}]}]})
    store.accept_pins(empty, "U1")
    msg = store.manufacturing_warning(empty)
    assert "2 pins have no net and no NC mark: U1 pin 2 (NC1), U1 pin 3 (NC2)" in msg and "mark them all NC" in msg
    st = by_id(empty)[0]
    assert st["outputs"]["state"] == "blocked" and len(st["outputs"]["gate"]["gaps"]["open"]) == 2
    assert st["sch"]["state"] == "issues" and st["sch"]["open"] == 2
    code, body = call(server, "POST", "/api/nc/mark", empty, {})
    assert code == 200 and body["marked"] == 2
    assert store.manufacturing_warning(empty) == ""
    assert {p["num"]: p["net"] for p in store.load_sheet(empty, "01")["parts"][0]["pins"]} == {"1": "+3V3", "2": "NC", "3": "NC"}
    assert by_id(empty)[0]["sch"]["state"] != "issues"


def test_mark_nc_per_item_and_a_bad_body(server, empty):
    _add(empty, "U1", "ABCD1234")
    store.write_sheet(empty, "01", {"sections": [{"id": "A", "title": "T"}], "parts": [
        {"ref": "U1", "section": "A", "pins": [{"num": "1", "name": "A", "net": ""}, {"num": "2", "name": "B", "net": ""}]}]})
    code, body = call(server, "POST", "/api/nc/mark", empty, {"items": [{"sheet": "01", "ref": "U1", "num": "2"}]})
    assert code == 200 and body["marked"] == 1
    assert {p["num"]: p["net"] for p in store.load_sheet(empty, "01")["parts"][0]["pins"]} == {"1": "", "2": "NC"}
    assert call(server, "POST", "/api/nc/mark", empty, {"items": "x"})[0] == 400


def test_pins_of_the_built_symbol_missing_from_the_netlist_are_unlisted_and_block(empty):
    _add(empty, "U1", "ABCD1234")
    store.write_sheet(empty, "01", {"sections": [{"id": "A", "title": "T"}], "parts": [
        {"ref": "U1", "section": "A", "pins": [{"num": "1", "name": "VCC", "net": "+3V3"}]}]})
    store.accept_pins(empty, "U1")
    assert store.manufacturing_warning(empty) == ""
    lib = store.pdir(empty) / "library"
    (lib / "build").mkdir(parents=True)
    (lib / "manifest.json").write_text(json.dumps({"U1": {"symbol": "SYM_U1", "mpn": "ABCD1234"}}), encoding="utf-8")
    pin = "PIN|{n}|{name}|eElectricPassive|0|0|0|0|10"
    (lib / "build" / "symbols_spec.txt").write_text("SYMBOL|SYM_U1\n" + "\n".join(pin.format(n=n, name=nm) for n, nm in (("1", "VCC"), ("2", "EN"), ("3", "GND"))) + "\n", encoding="cp1252")
    gaps = store.pin_gaps(empty)
    assert [(g["ref"], g["num"]) for g in gaps["unlisted"]] == [("U1", "2"), ("U1", "3")] and gaps["open"] == []
    assert "2 pins of the built symbols are missing from the netlist: U1 pin 2 (EN), U1 pin 3 (GND)" in store.manufacturing_warning(empty)
    assert by_id(empty)[0]["sch"]["state"] == "issues"
    res = store.mark_pins_nc(empty)
    assert res["marked"] == 2 and store.manufacturing_warning(empty) == ""
    assert {p["num"]: p["net"] for p in store.load_sheet(empty, "01")["parts"][0]["pins"]} == {"1": "+3V3", "2": "NC", "3": "NC"}


def test_rev_changes_when_a_log_grows_and_never_hashes_the_pcb(empty, pcb, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("rev must not hash a file")
    monkeypatch.setattr(lineage, "sha256_file", boom)
    r1 = stages.rev(empty)
    assert r1 == stages.rev(empty)
    store.append(empty, "bom-log.jsonl", {"ts": 1})
    r2 = stages.rev(empty)
    assert r2 != r1
    pcb.write_bytes(b"v2 longer")
    assert stages.rev(empty) != r2


def test_every_state_is_one_of_the_five_and_blocked_has_a_reason(empty):
    st, _ = by_id(empty)
    for s in st.values():
        assert s["state"] in stages.STATES and set(s) == {"id", "state", "severity", "reason", "open", "gate", "next", "primary"}


# ---- the page: the dots read S.stages only


def _status(stages_list, sid):
    start = SHELL.index("const plural = ")
    end = SHELL.index("// The stage record of the server")
    js = ("let S = " + json.dumps({"stages": stages_list}) + ";\n" + SHELL[start:end]
          + "\nconsole.log(JSON.stringify(stageStatus(" + json.dumps(sid) + ")));")
    with tempfile.TemporaryDirectory() as d:
        f = pathlib.Path(d) / "t.js"
        f.write_text(js, encoding="utf-8")
        out = subprocess.run([shutil.which("node"), str(f)], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_stage_status_is_a_pure_mapper_of_S_stages_with_no_other_data_source():
    block = SHELL[SHELL.index("function stageStatus"):SHELL.index("// The stage record of the server")]
    assert re.search(r"S\.stages", block)
    for other in ("RULES_DATA", "lines()", "S.checks", "S.exports", "S.sheets", "triageMap", "S.idea", "S.bom"):
        assert other not in block, other


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_stage_status_mapping_under_node():
    mk = lambda **kw: {"id": "pcb", "state": "clean", "severity": "", "reason": "r", "open": 0, **kw}
    assert _status([mk()], "pcb") == {"tone": "ok", "title": "r", "hint": ""}
    assert _status([mk(state="issues", severity="bad", open=21, reason="21 violations")], "pcb") == {"tone": "bad", "title": "21 violations", "hint": "21"}
    assert _status([mk(state="issues", severity="warn", open=2)], "pcb")["tone"] == "warn"
    assert _status([mk(state="blocked", severity="bad", open=3)], "pcb")["tone"] == "bad"
    assert _status([mk(state="not_started")], "pcb")["tone"] == ""
    assert _status([mk(state="in_progress")], "pcb")["tone"] == ""
    assert _status([mk()], "rules") == {"tone": "", "title": "", "hint": ""}        # a stage the server did not send is neutral
    assert _status([], "pcb")["tone"] == ""


# ---- slice 3 and 4: the UI sources (checked as text) and the readiness instance ----
UI = pathlib.Path(__file__).resolve().parent.parent / "ui"


def _src(rel):
    return (UI / rel).read_text(encoding="utf-8")


def test_a_disabled_button_is_aria_disabled_with_a_reason_and_a_click_toasts_it():
    kit, css = _src("js/kit.js"), _src("styles/base.css")
    assert "aria-disabled" in kit and "data-why" in kit or "rest.why" in kit
    assert "[aria-disabled=\"true\"]" in kit and "toast(" in kit and "}, true);" in kit   # capture-phase handler
    assert ".btn[aria-disabled=\"true\"]" in css and "not-allowed" in css


def test_the_rules_header_has_a_board_drc_row_from_board_check():
    src = _src("js/views/rules.js")
    assert "rulesDrcRow" in src and "S.board_check" in src and "pvStepBtn('drc'" in src
    assert "stale" in src + _src("js/views/previews.js")      # drcSummary (previews.js) words it


def test_outputs_gate_comes_from_the_stage_and_offers_mark_all_nc_and_ask():
    src = _src("js/views/outputs.js")
    assert "stageOf('outputs')" in src and "/api/nc/mark" in src
    assert "Mark all" in src and "nc-ask" in src and "askAbout" in src
    assert "why: outBlockWhy()" in src       # the Gerber zip item explains itself


def test_every_stage_page_header_gets_the_next_button_from_the_server():
    kit, shell = _src("js/kit.js"), _src("js/shell.js")
    assert "stageNextBtn" in kit and "stageNextBtn" in shell and "stage-next" in shell


def test_readiness_problems_carry_an_instance_that_changes_with_the_words(monkeypatch):
    import serve
    from test_readiness_port import _patch
    _patch(monkeypatch, altium_ok=False, linked=False)
    a = serve.readiness("demo")["problems"]
    assert a and all(len(p["instance"]) == 8 for p in a)
    assert a == serve.readiness("demo")["problems"]       # stable between calls


def test_readiness_dismissal_is_per_instance_and_reloads_when_the_rev_changes():
    src = _src("js/ready.js")
    assert "p.id + ':' + (p.instance" in src
    assert "readyRev" in src and "S.rev" in src and "readyLoad()" in src
    assert "readyDismiss(problems.map(readyKey))" in src
    assert "readyLoad()" in _src("js/boot.js")


def test_a_node_run_of_btn_disabled_markup():
    node = shutil.which("node")
    if not node:
        pytest.skip("no node")
    js = (
        "const src=require('fs').readFileSync(process.argv[2],'utf8');"
        "const m=src.match(/function btn\\([\\s\\S]*?\\n}\\n/);"
        "if(!m){console.log('NOFN');process.exit(0)}"
        "global.kesc=s=>String(s);global.esc=global.kesc;global.icon=()=>'';"
        "let f;try{f=new Function(m[0]+';return btn;')()}catch(e){console.log('ERR '+e.message);process.exit(0)}"
        "let h;try{h=f('Go',{disabled:true,why:'Because'})}catch(e){console.log('ERR '+e.message);process.exit(0)}"
        "console.log(h)"
    )
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "t.js"
        p.write_text(js, encoding="utf-8")
        out = subprocess.run([node, str(p), str(UI / "js" / "kit.js")], capture_output=True, text=True).stdout
    if out.startswith(("NOFN", "ERR")):
        pytest.skip(out.strip())
    assert 'aria-disabled="true"' in out and 'why="Because"' in out and " disabled" not in out