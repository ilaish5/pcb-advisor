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
        if self.name == "bom.json":
            raise PermissionError("locked")
        return real(self, data)
    monkeypatch.setattr(pathlib.Path, "write_bytes", boom)
    restored, left = project_guard.end(tok)
    assert restored == [] and left == ["bom.json"]
    assert "could NOT be restored" in project_guard.refusal(restored, left)


def test_no_registry_left_and_note_free_outside_window(proj):
    tok = project_guard.begin(proj)
    project_guard.end(tok)
    assert not project_guard._registry(proj).exists()
    project_guard.note(_p(proj, "bom.json"))          # outside a window: no file appears
    assert not project_guard._registry(proj).exists()
