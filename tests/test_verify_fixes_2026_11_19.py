"""Fixes from the runtime verify of de6b8d2: text fields in bodies, partial route naming every open net, activity report gaps."""
import json

import pytest  # noqa: F401

import runlog
import workspace
from altium import bridge
from test_chat_turns import call, server  # noqa: F401
from test_runlog import logs  # noqa: F401


def test_name_fields_must_be_text_and_deleting_nothing_is_404(server, empty):
    for bad in (["a"], 123, {"x": 1}):
        code, body = call(server, "POST", "/api/projects/new", empty, {"name": bad})
        assert code == 400 and "text" in body["error"], bad
        code, body = call(server, "POST", "/api/projects/delete", empty, {"name": bad})
        assert code == 400 and "text" in body["error"], bad
    assert call(server, "POST", "/api/delete_source", empty, {"name": ["x"]})[0] == 400
    assert call(server, "POST", "/api/projects/delete", empty, {"name": "never-made"})[0] == 404
    assert call(server, "POST", "/api/projects/new", empty, {"name": "Doomed"})[0] == 200
    # a cross-site page cannot delete; a real delete moves the folder to projects/.trash (not rmtree) and hides it from the list
    import http.client
    host, port = server[len("http://"):].split(":")
    c = http.client.HTTPConnection(host, int(port), timeout=15)
    c.request("POST", f"/api/projects/delete?project={empty}", json.dumps({"name": "Doomed"}), {"Origin": "https://evil.example", "Content-Type": "application/json"})
    assert c.getresponse().status == 403
    assert (workspace.projects_dir() / "Doomed").is_dir()
    code, body = call(server, "POST", "/api/projects/delete", empty, {"name": "Doomed"})
    assert code == 200 and "Doomed" not in [p["name"] for p in body["projects"]]
    assert not (workspace.projects_dir() / "Doomed").exists() and list((workspace.projects_dir() / ".trash").glob("Doomed-*"))
    assert call(server, "POST", "/api/projects/delete", empty, {"name": "Doomed"})[0] == 404


def test_new_project_is_logged_in_the_new_project(server, empty):
    assert call(server, "POST", "/api/projects/new", empty, {"name": "Fresh"})[0] == 200
    new = workspace.projects_dir() / "Fresh" / "usage-log.jsonl"
    assert new.is_file() and '"kind":"project"' in new.read_text(encoding="utf-8").replace(" ", "")
    old = workspace.projects_dir() / empty / "usage-log.jsonl"
    assert not old.exists() or "Fresh" not in old.read_text(encoding="utf-8")


def test_partial_route_names_every_open_net(tmp_path, monkeypatch):
    res = {"routed": ["A"], "failed": [("+3V3", "no way from R8-1 to U1-22")], "saved_open": ["+1V1", "+3V3", "+5V"], "written": True,
           "restored": False, "problems": ["the saved board still has open nets: +1V1 (C16-1); +3V3 (C10-1); +5V (C13-1)",
                                           "not routed: +3V3 (no way from R8-1 to U1-22)"],
           "summary": "24 nets routed; own check: 3 open nets", "tracks": 1, "vias": 0, "backup": "", "drc_before": {}, "drc_after": {},
           "widths": {}, "drills": [], "capability_warnings": [], "pour_warnings": []}
    monkeypatch.setattr(bridge, "_linked", lambda p: tmp_path / "a.PrjPcb")
    monkeypatch.setattr(bridge, "_project_pcb", lambda p: tmp_path / "a.PcbDoc")
    monkeypatch.setattr(bridge, "rules_missing", lambda p: [])
    monkeypatch.setattr(bridge.partlib, "converter_stale", lambda p: None)
    monkeypatch.setattr(bridge, "net_current_inputs", lambda p: {})
    monkeypatch.setattr(bridge, "route_on", lambda *a, **k: dict(res))
    monkeypatch.setattr(bridge, "_log", lambda *a, **k: None)
    monkeypatch.setattr(bridge, "design_problems", lambda p: [])
    out = bridge.route_pcb("x", keep_partial=True)
    assert out["open_nets"] == ["+3V3", "+1V1", "+5V"]
    assert "PARTIAL ROUTE, left open: +3V3 (no way from R8-1 to U1-22), +1V1, +5V" in out["summary"]
    assert out["warnings"][0] == "open nets, not routed: +3V3, +1V1, +5V"


def _rows(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_timeline_marks_partial_drops_chat_noise_and_orders_second_precision_after(empty, logs):  # noqa: F811
    p = workspace.projects_dir() / empty
    _rows(p / "usage-log.jsonl", [
        {"ts": "2026-11-18T10:00:00.250", "kind": "click", "text": "J2", "id": "J2", "act": "", "checked": False},
        {"ts": "2026-11-18T10:00:01.100", "kind": "step", "op": "chat.altium-actions", "phase": "end", "ok": True, "seconds": 1},
        {"ts": "2026-11-18T10:00:02.000", "kind": "step", "op": "route", "phase": "end", "ok": True, "seconds": 111,
         "shown": "24 nets routed; PARTIAL ROUTE, left open: +3V3 (no way), +1V1, +5V; Altium DRC: total 3"},
    ])
    _rows(p / "proposals.jsonl", [{"ts": "2026-11-18T10:00:00", "id": "p1", "status": "approved"}])
    text = runlog.project_timeline_text(empty, run_events=[])
    assert "altium-actions" not in text and "null" not in text
    assert "STEP route PARTIAL in 111s: PARTIAL ROUTE, left open: +3V3 (no way), +1V1, +5V" in text
    assert "1 partial" in text
    assert "now unticked" in text and "id=J2" in text
    assert text.index("CLICK") < text.index("PROPOSALS")            # same second: the millisecond click came first


def test_paths_of_the_user_profile_are_hidden():
    t = runlog.home_paths(r"read C:\Users\someone\AppData\x and C:\\Users\\other\\y and C:/Users/third/z; C:\Users\Public\Documents\ok")
    assert "someone" not in t and "other" not in t and "third" not in t and t.count("%USERPROFILE%") == 3
    assert r"C:\Users\Public\Documents\ok" in t


def test_server_output_is_cut_to_the_project(empty, logs):  # noqa: F811
    other = workspace.projects_dir() / "Other"
    other.mkdir(exist_ok=True)
    lines = [
        "2026-11-18T09:00:00.000 err too early",
        "2026-11-18T10:00:00.000 err Ignoring wrong pointing object 590 0 (offset 0)",
        "2026-11-18T10:00:01.000 out [guard] project edits in projects/Other/idea.json restored",
        f"2026-11-18T10:00:02.000 out [guard] project edits in projects/{empty}/idea.json restored",
        "2026-11-18T10:00:03.000 err Traceback (most recent call last):",
        "2026-11-18T10:00:04.000 err ConnectionAbortedError: [WinError 10053]",
        "2026-11-18T10:00:05.000 out stock sweep done",
    ]
    out = runlog.filter_output(lines, empty, "2026-11-18 10:00:00.000", "2026-11-18 11:00:00.000")
    assert "too early" not in out and "wrong pointing" not in out and "Other" not in out
    assert f"projects/{empty}/idea.json" in out and "stock sweep done" in out
    assert "!! 2026-11-18T10:00:03.000 err Traceback" in out and "!! 2026-11-18T10:00:04.000 err ConnectionAborted" in out
