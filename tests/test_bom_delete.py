"""
E8 (docs/E2E-KILN-LTE-DEFECTS-2026-11-24.md): deleting a BOM line, or some refs of it, end to end.

The student's Delete applies at once and is undoable; the agent's delete proposal (changes.deleted / remove, kind delete_*)
is "critical": it waits for the student's click in every autonomy mode, then goes through the same path.
A line whose refs are on no sheet (while sheets exist) carries `off_sheet`, which the UI shows as "not on any sheet".
"""
import json
import pathlib
import re

import pytest

import store
from test_server import get, line, post, server  # noqa: F401  (the server fixture)

REPO = pathlib.Path(__file__).resolve().parent.parent
BOM_JS = (REPO / "ui" / "js" / "views" / "bom.js").read_text(encoding="utf-8")
INSP_JS = (REPO / "ui" / "js" / "views" / "inspector.js").read_text(encoding="utf-8")
CHAT_JS = (REPO / "ui" / "js" / "chat.js").read_text(encoding="utf-8")


def keys(project):
    return [l["key"] for l in store.bom_lines(project)]


def by_key(project):
    return {l["key"]: l for l in store.bom_lines(project)}


# ---------------------------------------------------------------- store

def test_the_student_deletes_a_whole_line_and_undo_puts_it_back_in_place(lte):
    order, before = keys(lte), by_key(lte)["C100"]
    log = store.pdir(lte) / "bom-log.jsonl"
    prop = store.delete_bom_line(lte, "C100")
    assert "C100" not in keys(lte)
    entry = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()][-1]
    assert entry["removed"] and entry["by"] == "student" and entry["proposal"] == prop["id"]
    assert entry["before"]["refs"] == ["C34", "C35", "C36", "C42"] and entry["deleted"] == before["refs"]
    hist = next(h for h in store.history(lte) if h["id"] == prop["id"])
    assert hist["label"] == "C100: deleted" and hist["status"] == "approved"
    store.undo(lte, prop["id"])
    assert keys(lte) == order                                   # back where it was, not at the end
    assert by_key(lte)["C100"] == before
    with pytest.raises(store.UndoRefused):
        store.undo(lte, prop["id"])


def test_removing_some_refs_keeps_the_line_and_all_refs_is_the_whole_line(lte):
    prop = store.delete_bom_line(lte, "C100", ["C35", "C42"])
    assert by_key(lte)["C100"]["refs"] == ["C34", "C36"]
    assert store.delete_spec(prop) == ("refs", ["C35", "C42"])
    assert next(h for h in store.history(lte) if h["id"] == prop["id"])["label"] == "C100: removed C35, C42"
    store.undo(lte, prop["id"])
    assert by_key(lte)["C100"]["refs"] == ["C34", "C35", "C36", "C42"]
    whole = store.delete_bom_line(lte, "C100", "C34, C35 C36,C42")      # every ref: the line goes
    assert store.delete_spec(whole) == ("whole", None) and "C100" not in keys(lte)


def test_a_bad_delete_changes_nothing(lte):
    log = (store.pdir(lte) / "bom-log.jsonl").read_text(encoding="utf-8")
    with pytest.raises(KeyError):
        store.delete_bom_line(lte, "NOPE")
    with pytest.raises(ValueError):
        store.delete_bom_line(lte, "C100", ["R1"])
    assert (store.pdir(lte) / "bom-log.jsonl").read_text(encoding="utf-8") == log


def test_undo_is_refused_when_it_would_duplicate_a_ref(lte):
    prop = store.delete_bom_line(lte, "C100", ["C42"])
    store.edit_bom(lte, "R30", "refs", by_key(lte)["R30"]["refs"] + ["C42"])
    with pytest.raises(store.UndoRefused, match="C42"):
        store.undo(lte, prop["id"])
    assert by_key(lte)["C100"]["refs"] == ["C34", "C35", "C36"]


def test_a_delete_changes_the_bom_outputs_are_made_from(lte):
    import lineage
    sha = lineage.state_sha(lte, "bom_csv", "jlc")
    store.delete_bom_line(lte, "C100")
    assert lineage.state_sha(lte, "bom_csv", "jlc") != sha            # Outputs read "the BOM changed since"


# ---------------------------------------------------------------- the agent's proposal

@pytest.mark.parametrize("changes", [{"deleted": True}, {"remove": ["C34", "C35", "C36", "C42"]}])
def test_an_agent_delete_is_critical_and_waits_in_every_mode(lte, changes):
    rec = store.propose_bom(lte, "C100", changes, reason="not on any sheet")
    assert store.classify_proposal(rec) == "critical"
    assert not any(store.may_auto_apply(rec, m) for m in store.AUTONOMY_MODES)
    assert "C100" in keys(lte)                                  # nothing changes until the click
    store.decide(lte, rec["id"], "approved")
    assert "C100" not in keys(lte)
    entry = [e for e in store.read_jsonl(store.pdir(lte) / "bom-log.jsonl") if e.get("proposal") == rec["id"]][0]
    assert entry["by"] == "agent-approved"
    store.undo(lte, rec["id"])
    assert by_key(lte)["C100"]["refs"] == ["C34", "C35", "C36", "C42"]


def test_a_delete_kind_proposal_is_applied_too(lte):
    pid = store._new_proposal_id(lte)
    rec = store.append(lte, "proposals.jsonl", {"id": pid, "ts": store.now_ms(), "kind": "delete_bom_line", "line": "C100",
                                                "changes": {"refs": ["C42"]}, "status": "pending"})
    assert store.classify_proposal(rec) == "critical"
    store.decide(lte, pid, "approved")
    assert by_key(lte)["C100"]["refs"] == ["C34", "C35", "C36"]


def test_deleting_a_line_supersedes_the_changes_still_waiting_for_it(lte):
    waiting = store.propose_bom(lte, "C100", {"note": "x"})
    store.delete_bom_line(lte, "C100")
    assert next(p for p in store.proposals(lte) if p["id"] == waiting["id"])["status"] == "rejected"


def test_a_delete_proposal_refuses_when_the_line_is_gone(lte):
    rec = store.propose_bom(lte, "C100", {"deleted": True})
    store.delete_bom_line(lte, "C100")
    p = next(p for p in store.proposals(lte) if p["id"] == rec["id"])
    assert p["status"] == "rejected"                            # superseded: no card left to fail on a click


# ---------------------------------------------------------------- orphan lines

def test_a_line_on_no_sheet_is_marked_only_while_sheets_exist(lte):
    lines = {l["key"]: l for l in store.bom(lte)}
    on = [l for l in lines.values() if l["on_sheet"]]
    off = [l for l in lines.values() if l["refs"] and not l["on_sheet"]]
    assert on and off
    assert all(set(l["off_sheet"]) < set(l["refs"]) for l in on)
    assert all(l["off_sheet"] == l["refs"] for l in off)
    for sh in store.sheet_ids(lte):
        (store.netlist_dir(lte) / f"{sh}.json").unlink()
    assert all(l["off_sheet"] == [] for l in store.bom(lte))     # no sheets yet: nothing is "not on a sheet"


# ---------------------------------------------------------------- server

def test_the_delete_endpoint_applies_marks_stale_and_undoes(server, lte):  # noqa: F811
    import project as project_mod
    project_mod.save_meta(lte, {**project_mod.load_meta(lte), "updated": "2000-01-01T00:00:00"})
    stamp = "2000-01-01T00:00:00"
    code, st = post(server, "/api/bom/delete", {"line": "C100", "refs": ["C42"]}, lte)
    assert code == 200 and line(st, "C100")["refs"] == ["C34", "C35", "C36"]
    assert st["deleted"]["refs"] == ["C42"] and st["deleted"]["line"] == "C100"
    assert project_mod.load_meta(lte).get("updated") and project_mod.load_meta(lte).get("updated") != stamp
    code, st = post(server, "/api/undo", {"id": st["deleted"]["id"]}, lte)
    assert code == 200 and line(st, "C100")["refs"] == ["C34", "C35", "C36", "C42"]
    code, st = post(server, "/api/bom/delete", {"line": "C100"}, lte)
    assert code == 200 and all(l["key"] != "C100" for l in st["bom"]) and st["deleted"]["refs"] == ["C34", "C35", "C36", "C42"]
    assert post(server, "/api/bom/delete", {"line": "C100"}, lte)[0] == 404
    assert post(server, "/api/bom/delete", {"line": "R30", "refs": ["Z9"]}, lte)[0] == 400


@pytest.mark.parametrize("action", [{"type": "bom.delete", "line": "C100", "reason": "not on any sheet"},
                                    {"type": "bom.propose", "line": "C100", "changes": {"deleted": True}}])
def test_an_agent_delete_waits_for_the_click_even_in_auto_mode(server, lte, monkeypatch, action):  # noqa: F811
    import workspace
    from test_autonomy import _agent_says
    workspace.set_value("agent.autonomy", "auto")
    _agent_says(monkeypatch, [action])
    _, st = post(server, "/api/chat", {"text": "C100 is not on any sheet, delete it"}, lte)
    prop = st["proposals"][-1]
    assert prop["status"] == "pending" and prop["changes"] == {"deleted": True} and "C100" in keys(lte)
    code, st = post(server, "/api/proposal", {"id": prop["id"], "decision": "approved"}, lte)
    assert code == 200 and all(l["key"] != "C100" for l in st["bom"])
    assert any("Line C100 deleted from the BOM" in (m.get("text") or "") for m in st["chat"])


# ---------------------------------------------------------------- UI (source checks, as the other UI tests do)

def _handler(src, act):
    start = src.index(f"onAct('{act}'")
    nxt = re.search(r"\n(?:onAct\(|onChange\(|const |function |async function |/\*)", src[start + 10:])
    return src[start:start + 10 + (nxt.start() if nxt else 20000)]


def test_the_ui_offers_delete_with_one_confirmation_and_an_undo_toast():
    h = _handler(BOM_JS, "bom-delete")
    assert h.count("askChoice(") == 1 and "refs.join(', ')" in h and "l.key" in h      # names the line and the refs
    assert "'/api/bom/delete'" in h and "label: 'Undo'" in h and "'/api/undo'" in h and "r.deleted.id" in h
    assert "askText(" not in h                                                       # no typed reason
    assert "act: 'bom-delete'" in INSP_JS and "Delete from BOM" in INSP_JS and "danger: true" in INSP_JS


def test_an_orphan_row_shows_the_mark_and_a_delete_button():
    row = BOM_JS[BOM_JS.index("function bomRow("):BOM_JS.index("function bomHeader(")]
    assert "bomOrphan(l)" in row and "'not on any sheet'" in row and "act: 'bom-delete'" in row and "icon: 'trash'" in row
    orphan = BOM_JS[BOM_JS.index("function bomOrphan("):BOM_JS.index("function bomRow(")]
    assert "off_sheet" in orphan and "refs.length > 0" in orphan


def test_the_chat_card_of_a_delete_names_what_goes():
    assert "function propDelete(" in CHAT_JS and "if (del) return propDeleteHTML(p, del);" in CHAT_JS
    card = CHAT_JS[CHAT_JS.index("function propDeleteHTML("):CHAT_JS.index("function propSummary(")]
    assert "decide: 'approved'" in card and "decide: 'rejected'" in card and "undo-change" in card


# ---------------------------------------------------------------- review fixes: a delete is its own card, an undo names what it cannot bring back

def test_undo_of_a_delete_names_the_pending_changes_it_threw_out(lte):
    waiting = store.propose_bom(lte, "C100", {"note": "x"})
    prop = store.delete_bom_line(lte, "C100")
    assert store.superseded_by_delete(lte, next(p for p in store.proposals(lte) if p["id"] == prop["id"])) == [waiting["id"]]
    undone = store.undo(lte, prop["id"])
    assert undone["superseded"] == [waiting["id"]]
    assert next(p for p in store.proposals(lte) if p["id"] == waiting["id"])["status"] == "rejected"     # not back: the student is told
    plain = store.delete_bom_line(lte, "C100")
    assert store.undo(lte, plain["id"])["superseded"] == []


def test_approve_all_never_takes_a_delete(server, lte):  # noqa: F811
    rec = store.propose_bom(lte, "C100", {"deleted": True})
    other = store.propose_bom(lte, "R1", {"note": "n"}) if "R1" in keys(lte) else None
    code, body = post(server, "/api/proposals/batch", {"ids": [rec["id"]], "decision": "approved"}, lte)
    assert code == 200 and body["results"][0]["ok"] is False and "own card" in body["results"][0]["error"]
    assert "C100" in keys(lte) and next(p for p in store.proposals(lte) if p["id"] == rec["id"])["status"] == "pending"
    assert other is None or other["status"] == "pending"
    assert post(server, "/api/proposals/batch", {"ids": [rec["id"]], "decision": "rejected"}, lte)[1]["results"][0]["ok"]      # Keep, in a batch, is fine


def test_the_ui_keeps_deletes_out_of_the_group_card_and_toasts_what_an_undo_could_not_restore():
    assert "pendDel = pending.filter(p => propDelete(p))" in CHAT_JS and "pendDel.map(diffHTML)" in CHAT_JS
    assert "r.superseded" in CHAT_JS and "dels.map(diffHTML)" in BOM_JS
