"""The project-data guard: the agent never keeps a direct edit of server-written project files; server writes stay."""
import json
import subprocess
import sys

import pytest

import project_guard
import store
import workspace


@pytest.fixture
def proj(home, monkeypatch):
    monkeypatch.delenv("PCB_ADVISOR_DEV", raising=False)
    import project
    name = workspace.safe_name("pg")
    project.ensure(name)
    store.append(name, "bom-log.jsonl", {"line": "R1", "changes": {"value": "10k"}})
    store.bom(name)
    return name


def _p(name, rel):
    return workspace.project_dir(name) / rel


def test_direct_edit_restored_and_reported(proj):
    f = _p(proj, "bom.json")
    before = f.read_bytes()
    tok = project_guard.begin(proj)
    f.write_text("[]", encoding="utf-8")
    restored, left = project_guard.end(tok)
    assert restored == ["bom.json"] and left == []
    assert f.read_bytes() == before
    assert "edited project files directly: bom.json" in project_guard.refusal(restored, left)


def test_new_netlist_file_removed(proj):
    tok = project_guard.begin(proj)
    new = _p(proj, "netlist/evil.json")
    new.parent.mkdir(exist_ok=True)
    new.write_text("{}", encoding="utf-8")
    restored, left = project_guard.end(tok)
    assert restored == ["netlist/evil.json"] and not new.exists()


def test_deleted_log_restored(proj):
    f = _p(proj, "bom-log.jsonl")
    before = f.read_bytes()
    tok = project_guard.begin(proj)
    f.unlink()
    assert project_guard.end(tok)[0] == ["bom-log.jsonl"]
    assert f.read_bytes() == before


def test_server_write_during_window_kept(proj):
    tok = project_guard.begin(proj)
    store.append(proj, "bom-log.jsonl", {"line": "R2", "changes": {"value": "1k"}})
    store.bom(proj)
    idea = store.load_idea(proj)
    store.save_idea(proj, idea)
    assert project_guard.end(tok) == ([], [])
    assert "R2" in _p(proj, "bom-log.jsonl").read_text(encoding="utf-8")


def test_server_sheet_write_kept(proj):
    tok = project_guard.begin(proj)
    store.write_sheet(proj, "main", {"id": "main", "parts": []})
    assert project_guard.end(tok) == ([], [])
    assert _p(proj, "netlist/main.json").exists()


def test_subprocess_write_kept(proj):
    code = ("import sys; sys.path.insert(0, %r); import store; "
            "store.append(%r, 'bom-log.jsonl', {'line': 'R9', 'changes': {'value': '2k'}}); store.bom(%r)"
            % (str(workspace.REPO / "scripts"), proj, proj))
    tok = project_guard.begin(proj)
    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True)
    assert project_guard.end(tok) == ([], [])
    assert "R9" in _p(proj, "bom-log.jsonl").read_text(encoding="utf-8")


def test_edit_after_registered_write_restored(proj):
    tok = project_guard.begin(proj)
    store.append(proj, "bom-log.jsonl", {"line": "R2", "changes": {"value": "1k"}})
    f = _p(proj, "bom-log.jsonl")
    kept = f.read_bytes()
    f.write_bytes(kept + b'{"line": "EVIL"}\n')
    restored, _ = project_guard.end(tok)
    assert restored == ["bom-log.jsonl"]
    assert "EVIL" not in f.read_text(encoding="utf-8")


def test_guard_off_does_nothing(proj, monkeypatch):
    monkeypatch.setenv("PCB_ADVISOR_DEV", "1")
    f = _p(proj, "idea.json")
    tok = project_guard.begin(proj)
    assert tok is None
    f.write_text(json.dumps({"hacked": 1}), encoding="utf-8")
    assert project_guard.end(tok) == ([], [])
    assert "hacked" in f.read_text(encoding="utf-8")


def test_restore_failure_reported_not_raised(proj, monkeypatch):
    f = _p(proj, "bom.json")
    tok = project_guard.begin(proj)
    f.write_text("[]", encoding="utf-8")
    import pathlib
    real = pathlib.Path.write_bytes

    def boom(self, data):
        if self.name.startswith("bom.json"):
            raise PermissionError("locked")
        return real(self, data)
    monkeypatch.setattr(pathlib.Path, "write_bytes", boom)
    restored, left = project_guard.end(tok)
    assert restored == [] and left == ["bom.json"]
    assert "could NOT be restored" in project_guard.refusal(restored, left)


def test_no_registry_left_and_note_free_outside_window(proj):
    tok = project_guard.begin(proj)
    project_guard.end(tok)
    assert not project_guard._regdir(proj).exists()
    project_guard.note(_p(proj, "bom.json"))          # outside a window: nothing appears
    assert not project_guard._regdir(proj).exists()


def test_ui_write_then_agent_edit_keeps_ui_write(proj):
    log, bomf = _p(proj, "bom-log.jsonl"), _p(proj, "bom.json")
    tok = project_guard.begin(proj)
    store.append(proj, "bom-log.jsonl", {"line": "R2", "changes": {"value": "1k"}})     # the student, in the UI
    store.bom(proj)
    legit_bom = bomf.read_bytes()
    log.write_bytes(log.read_bytes() + b'{"line": "EVIL"}\n')                           # the agent, directly
    bomf.write_text("[]", encoding="utf-8")
    restored, left = project_guard.end(tok)
    assert sorted(restored) == ["bom-log.jsonl", "bom.json"] and left == []
    text = log.read_text(encoding="utf-8")
    assert "R2" in text and "EVIL" not in text
    assert bomf.read_bytes() == legit_bom


def test_agent_truncating_log_gets_ui_appends_back(proj):
    log = _p(proj, "bom-log.jsonl")
    tok = project_guard.begin(proj)
    store.append(proj, "bom-log.jsonl", {"line": "R2", "changes": {"value": "1k"}})
    want = log.read_bytes()
    log.write_bytes(b"")
    assert project_guard.end(tok)[0] == ["bom-log.jsonl"]
    assert log.read_bytes() == want


def test_project_deleted_mid_turn_no_ghost(proj):
    import shutil
    tok = project_guard.begin(proj)
    shutil.rmtree(workspace.project_dir(proj))
    assert project_guard.end(tok) == ([], [])
    assert not workspace.project_dir(proj).exists()


def test_reset_mid_turn_is_legitimate(proj):
    import project
    tok = project_guard.begin(proj)
    project.reset(proj)
    assert project_guard.end(tok) == ([], [])
    assert _p(proj, "bom-log.jsonl").read_bytes() == b""


def test_restore_goes_through_replace(proj, monkeypatch):
    import os
    calls, real = [], os.replace
    monkeypatch.setattr(os, "replace", lambda a, b: (calls.append(str(b)), real(a, b))[1])
    f = _p(proj, "bom.json")
    tok = project_guard.begin(proj)
    f.write_text("[]", encoding="utf-8")
    assert project_guard.end(tok)[0] == ["bom.json"]
    assert any(c.endswith("bom.json") for c in calls)


def test_middle_line_rewrite_keeps_ui_append(proj):
    log = _p(proj, "bom-log.jsonl")
    tok = project_guard.begin(proj)
    store.append(proj, "bom-log.jsonl", {"line": "R2", "changes": {"value": "1k"}})
    want = log.read_bytes()
    log.write_bytes(want.replace(b'"10k"', b'"99k"'))                   # the agent changes an older line
    assert project_guard.end(tok)[0] == ["bom-log.jsonl"]
    assert log.read_bytes() == want


def test_deleted_project_json_is_restored(proj):
    f = _p(proj, "project.json")
    before = f.read_bytes()
    tok = project_guard.begin(proj)
    f.unlink()
    assert project_guard.end(tok) == (["project.json"], [])
    assert f.read_bytes() == before


def test_restore_retries_permission_error(proj, monkeypatch):
    import os
    real, n = os.replace, {"n": 0}

    def flaky(a, b):
        n["n"] += 1
        if n["n"] < 3:
            raise PermissionError("held by a reader")
        return real(a, b)
    monkeypatch.setattr(os, "replace", flaky)
    f = _p(proj, "bom.json")
    before = f.read_bytes()
    tok = project_guard.begin(proj)
    f.write_text("[]", encoding="utf-8")
    assert project_guard.end(tok) == (["bom.json"], [])
    assert f.read_bytes() == before and n["n"] == 3


def test_stale_registry_entry_ignored(proj, monkeypatch):
    import hashlib
    evil = b"[]"
    h = hashlib.sha256(evil).hexdigest()
    reg = project_guard._regdir(proj)
    reg.mkdir(parents=True, exist_ok=True)
    (reg / f"{h}.bin").write_bytes(evil)
    (reg / "4242.jsonl").write_text(json.dumps({"seq": 1, "p": "bom.json", "h": h}) + "\n", encoding="utf-8")
    monkeypatch.setattr(project_guard.shutil, "rmtree", lambda *a, **k: None)     # the old window's folder cannot be removed
    f = _p(proj, "bom.json")
    before = f.read_bytes()
    tok = project_guard.begin(proj)
    f.write_bytes(evil)
    assert project_guard.end(tok)[0] == ["bom.json"]
    assert f.read_bytes() == before


def test_registry_files_of_two_processes_merged(proj):
    import os
    tok = project_guard.begin(proj)
    store.append(proj, "bom-log.jsonl", {"line": "R2", "changes": {"value": "1k"}})
    reg = project_guard._regdir(proj)
    mine = reg / f"{os.getpid()}.jsonl"
    (reg / "99999.jsonl").write_text(mine.read_text(encoding="utf-8"), encoding="utf-8")   # another process' file
    mine.unlink()
    assert project_guard.end(tok) == ([], [])
    assert "R2" in _p(proj, "bom-log.jsonl").read_text(encoding="utf-8")
