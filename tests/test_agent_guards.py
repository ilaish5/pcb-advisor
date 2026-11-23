"""Safety nets around the runtime agent: it never keeps edits of the tool, never changes Altium outside an action, a timeout is an error."""
import errno
import os
import subprocess
import sys

import pytest

import agent
import tool_guard
from altium import bridge


def _git(root, *a):
    subprocess.run(["git", *a], cwd=str(root), check=True, capture_output=True)


@pytest.fixture
def clone(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / ".gitignore").write_text("config.json\nprojects/*\n__pycache__/\n")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "a.py").write_text("print(1)\n")
    (tmp_path / "scripts" / "b.py").write_text("print(2)\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "x")
    return tmp_path


def test_guard_restores_modified_added_deleted_in_a_git_clone(clone):
    snap = tool_guard.snapshot(clone)
    (clone / "scripts" / "a.py").write_text("hacked\n")
    (clone / "scripts" / "b.py").unlink()
    (clone / "scripts" / "new.py").write_text("x\n")
    # legitimate data and caches are not the tool
    (clone / "config.json").write_text("{}")
    (clone / "projects").mkdir()
    (clone / "projects" / "p.json").write_text("{}")
    (clone / "__pycache__").mkdir()
    (clone / "__pycache__" / "a.pyc").write_text("x")
    changed, left = tool_guard.restore(snap)
    assert left == []
    assert changed == ["scripts/a.py", "scripts/b.py", "scripts/new.py"]
    assert (clone / "scripts" / "a.py").read_text() == "print(1)\n"
    assert (clone / "scripts" / "b.py").read_text() == "print(2)\n"
    assert not (clone / "scripts" / "new.py").exists()
    assert (clone / "config.json").exists() and (clone / "projects" / "p.json").exists()
    assert "restored" in tool_guard.refusal(changed) and "scripts/a.py" in tool_guard.refusal(changed)
    assert tool_guard.restore(tool_guard.snapshot(clone)) == ([], [])


def test_guard_keeps_the_owners_own_edit_made_before_the_turn(clone):
    (clone / "scripts" / "a.py").write_text("mine\n")
    snap = tool_guard.snapshot(clone)
    assert tool_guard.restore(snap) == ([], [])
    (clone / "scripts" / "a.py").write_text("agent\n")
    assert tool_guard.restore(snap) == (["scripts/a.py"], [])
    assert (clone / "scripts" / "a.py").read_text() == "mine\n"


def test_guard_in_a_zip_install_uses_a_snapshot(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "a.py").write_text("one\n")
    (tmp_path / "config.json").write_text("{}")
    snap = tool_guard.snapshot(tmp_path)
    assert not snap["git"]
    (tmp_path / "scripts" / "a.py").write_text("two\n")
    (tmp_path / "scripts" / "n.py").write_text("n\n")
    (tmp_path / "config.json").write_text('{"x": 1}')
    assert tool_guard.restore(snap) == (["scripts/a.py", "scripts/n.py"], [])
    assert (tmp_path / "scripts" / "a.py").read_text() == "one\n" and not (tmp_path / "scripts" / "n.py").exists()


def test_bridge_refuses_altium_changes_outside_the_server(monkeypatch):
    monkeypatch.setattr(bridge, "_server", False)
    monkeypatch.delenv("PCB_ADVISOR_DEV", raising=False)
    for cmd in ("OUTLINE", "PLACE", "PCBSAVE", "RULE", "outline"):
        with pytest.raises(bridge.BridgeError, match="go through actions"):
            bridge.run_commands([("PROJECT", "x.PrjPcb"), (cmd, "a")])
    for ok in ("PING", "PROJECT", "PCBCHECK", "DRC"):
        bridge._check_writes_allowed([(ok, "a")])
    monkeypatch.setenv("PCB_ADVISOR_DEV", "1")
    bridge._check_writes_allowed([("OUTLINE", "a")])
    monkeypatch.delenv("PCB_ADVISOR_DEV")
    monkeypatch.setattr(bridge, "_server", True)
    bridge._check_writes_allowed([("OUTLINE", "a")])


def test_every_changing_dispatch_command_is_blocked():
    import re
    pas = (bridge.REPO_BRIDGE_PAS if hasattr(bridge, "REPO_BRIDGE_PAS") else
           os.path.join(os.path.dirname(bridge.__file__), "bridge", "AdvisorBridge.pas"))
    cmds = set(re.findall(r"\(Cmd = '([A-Z0-9]+)'\)", open(pas, encoding="utf-8", errors="replace").read()))
    assert bridge.READ_ONLY <= cmds and "OUTLINE" in cmds and len(cmds) > 30


def test_the_engine_env_lacks_the_developer_switch(monkeypatch):
    import oscompat
    monkeypatch.setenv("PCB_ADVISOR_DEV", "1")
    assert "PCB_ADVISOR_DEV" not in oscompat.child_env()


def test_a_timed_out_turn_is_an_error_with_retry(monkeypatch):
    import gateway
    from gateway.base import Result

    def fake_route(req, name=None):
        return Result(text="", provider="antigravity", model="m", meta={"partial": True, "error_kind": "total_timeout"},
                      error="timed out after 900s")
    monkeypatch.setattr(gateway, "route", fake_route)
    monkeypatch.setattr(gateway, "resolve", lambda b=None: "antigravity")
    monkeypatch.setattr(agent.runtime_pack, "sync", lambda: ".")
    monkeypatch.setattr(agent, "_workspace_section", lambda *a: "")
    monkeypatch.setattr(agent, "_add_dirs", lambda *a: [])
    monkeypatch.setattr(agent, "_summary", lambda m: "")
    out = agent.respond({"project": "p"}, "hi", [])
    assert out["error"] and out["partial"] and "ran out of time (900 s)" in out["reply"] and "no actions were applied" in out["reply"] and out["actions"] == []
    # a stop by the student is not an error
    monkeypatch.setattr(gateway, "route", lambda req, name=None: Result(text="x", provider="antigravity", model="m",
                                                                         meta={"partial": True, "error_kind": "stopped"}, error="stopped"))
    assert not agent.respond({"project": "p"}, "hi", []).get("error")


def test_guard_is_off_for_developers(monkeypatch):
    monkeypatch.setenv("PCB_ADVISOR_DEV", "1")
    assert tool_guard.begin() is False and tool_guard.end(False) == ([], [])
    monkeypatch.delenv("PCB_ADVISOR_DEV")
    assert tool_guard.enabled()


def test_overlapping_turns_restore_only_when_the_last_one_ends(clone, monkeypatch):
    monkeypatch.delenv("PCB_ADVISOR_DEV", raising=False)
    monkeypatch.setattr(tool_guard, "REPO", clone)
    real = tool_guard.snapshot
    monkeypatch.setattr(tool_guard, "snapshot", lambda root=None: real(clone))
    a, b = tool_guard.begin(), tool_guard.begin()
    (clone / "scripts" / "a.py").write_text("hacked\n")
    assert tool_guard.end(a) == ([], [])                       # turn B is still running: nothing is restored under it
    assert (clone / "scripts" / "a.py").read_text() == "hacked\n"
    assert tool_guard.end(b) == (["scripts/a.py"], [])
    assert (clone / "scripts" / "a.py").read_text() == "print(1)\n"


def test_a_failing_git_turns_the_guard_off_for_the_turn(clone, monkeypatch):
    monkeypatch.setattr(tool_guard, "_git_state", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    snap = tool_guard.snapshot(clone)
    assert snap["state"] is None
    (clone / "scripts" / "a.py").write_text("edited\n")
    assert tool_guard.restore(snap) == ([], [])
    assert (clone / "scripts" / "a.py").read_text() == "edited\n"


def test_restore_never_raises(clone, monkeypatch):
    snap = tool_guard.snapshot(clone)
    monkeypatch.setattr(tool_guard, "_git_state", lambda *a: (_ for _ in ()).throw(OSError("disk")))
    assert tool_guard.restore(snap) == ([], [])


def test_a_projects_folder_with_another_name_is_not_the_tool(clone, monkeypatch):
    import workspace
    monkeypatch.setattr(workspace, "projects_dir", lambda: clone / "my_work")
    snap = tool_guard.snapshot(clone)
    (clone / "my_work").mkdir()
    (clone / "my_work" / "idea.json").write_text("{}")
    assert tool_guard.restore(snap) == ([], []) and (clone / "my_work" / "idea.json").exists()


def test_zip_install_reports_what_it_cannot_restore(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "big.bin").write_bytes(b"1234")
    (tmp_path / "scripts" / "a.py").write_text("one\n")
    snap = tool_guard.snapshot(tmp_path)
    (tmp_path / "scripts" / "big.bin").write_bytes(b"12345")
    (tmp_path / "scripts" / "a.py").write_text("two!\n")
    assert tool_guard.restore(snap) == (["scripts/a.py"], ["scripts/big.bin"])
    assert "could NOT" in tool_guard.refusal(["scripts/a.py"], ["scripts/big.bin"])


def test_serve_main_turns_server_mode_on_and_a_cli_process_stays_read_only(monkeypatch, tmp_path):
    import serve
    monkeypatch.setattr(bridge, "_server", False)
    monkeypatch.delenv("PCB_ADVISOR_DEV", raising=False)
    monkeypatch.setattr(serve.project_mod, "ensure", lambda p: None)
    monkeypatch.setattr(serve, "redraw", lambda p: None)
    monkeypatch.setattr(serve, "_Server", lambda *a, **k: (_ for _ in ()).throw(OSError(errno.EADDRINUSE, "busy")))   # "already running": main returns
    monkeypatch.setattr(serve, "port_holder", lambda *a, **k: "ours")
    assert serve.main(["--no-browser", "--quiet"]) == 0
    assert bridge._server is True                                  # set by the real entry, not by the test
    bridge._check_writes_allowed([("OUTLINE", "a"), ("REVERT", "b")])
    # a fresh process (the agent's shell, the CLI) has no flag
    env = {k: v for k, v in os.environ.items() if k != "PCB_ADVISOR_DEV"}
    code = ("import sys; sys.path.insert(0, 'scripts'); from altium import bridge\n"
            "try: bridge.run_commands([('OUTLINE', 'a')])\n"
            "except bridge.BridgeError as e: print('REFUSED', e)\n")
    out = subprocess.run([sys.executable, "-c", code], cwd=str(tool_guard.REPO), env=env, capture_output=True, text=True)
    assert "REFUSED Altium changes go through actions" in out.stdout, out.stderr


def test_a_broken_or_cut_off_actions_block_is_reported_not_swallowed():
    reply, actions, _t, problems = agent._parse('Done.\n```json\n{"actions": [\n  {"type": "x",}\n]}\n```')
    assert actions == [] and len(problems) == 1 and "line" in problems[0] and "nothing in it was applied" in problems[0]
    assert "```" not in reply and "actions" not in reply
    reply, actions, _t, problems = agent._parse('I added R1.\n```json\n{"actions": [{"type": "bom.propose"')
    assert actions == [] and len(problems) == 1 and "cut off" in problems[0]
    assert reply == "I added R1."


def test_a_good_actions_block_still_parses():
    reply, actions, _t, problems = agent._parse('Ok.\n```json\n{"actions": [{"type": "idea.ready"}]}\n```')
    assert reply == "Ok." and actions == [{"type": "idea.ready"}] and problems == []
    assert agent._parse("just words")[3] == []




def test_chips_of_a_streaming_engine_are_its_real_script_runs_with_the_claimed_detail():
    meta = {"stream": True, "runs": [{"label": "Running check_stock.py --all", "failed": False},
                                     {"label": "Running other.py", "failed": False},
                                     {"label": "Running crash.py", "failed": True}],
            "denied": [{"tool": "Bash", "input": {"command": "python scripts/other.py"}}]}
    claimed = [{"t": "Check availability (check_stock)", "d": "18 lines - LCSC", "st": "ok"},
               {"t": "Never ran this", "d": "x", "st": "ok"}]
    chips = agent.real_tools(meta, claimed)
    assert chips == [{"t": "Running a check", "raw": "Running check_stock.py --all", "st": "ok", "d": "18 lines - LCSC"},
                     {"t": "Running a check", "raw": "Running other.py", "st": "warn"},
                     {"t": "Running a check", "raw": "Running crash.py", "st": "bad"}]       # the student reads words; the command is `raw`
    assert agent.real_tools({"stream": True}, claimed) == []          # a stream with no script run: the claim is dropped


def test_an_engine_without_a_step_stream_keeps_the_claims_marked_unconfirmed():
    claimed = [{"t": "Check availability", "d": "18 lines", "st": "ok"}]
    assert agent.real_tools({}, claimed) == [{"t": "Check availability", "d": "18 lines", "st": "ok", "s": "claimed"}]
    assert agent.real_tools(None, []) == []


def test_respond_chips_unconfirmed_without_events_and_real_with_them(monkeypatch):
    import gateway
    from gateway.base import Result
    text = 'Ran it.\n```json\n{"tools": [{"t": "Check availability", "st": "ok"}], "actions": []}\n```'
    monkeypatch.setattr(gateway, "route", lambda req, name=None: Result(text=text, provider="antigravity", model="m"))
    monkeypatch.setattr(gateway, "resolve", lambda b=None: "antigravity")
    monkeypatch.setattr(agent.runtime_pack, "sync", lambda: ".")
    monkeypatch.setattr(agent, "_workspace_section", lambda *a: "")
    monkeypatch.setattr(agent, "_add_dirs", lambda *a: [])
    monkeypatch.setattr(agent, "_summary", lambda m: "")
    out = agent.respond({"project": "p"}, "hi", [])
    assert out["tools"] == [{"t": "Check availability", "st": "ok", "s": "claimed"}] and out["parse_refused"] == []
    monkeypatch.setattr(gateway, "route", lambda req, name=None: Result(text=text, provider="claude_code", model="m", meta={"stream": True}))
    assert agent.respond({"project": "p"}, "hi", [])["tools"] == []      # the engine streamed and ran nothing


def test_an_example_that_is_not_strict_json_is_not_a_refusal():
    ex = 'Set it like this:\n```json\n{"port": 8080, // comment\n "debug": true,}\n```\nDone.'
    reply, actions, _t, problems = agent._parse(ex)
    assert problems == [] and actions == [] and "8080" not in reply and "Done." in reply
    assert agent._parse('x\n```json\n{"port": 8080, "x": [1,}\n')[3] == []        # cut-off example: dropped quietly too
    assert len(agent._parse('x\n```json\n{"actions": [{"type": "a",}]}\n```')[3]) == 1
    assert agent._parse('x\n```json\n[{"type": "a",}]\n```')[3] == []              # "type" alone does not make it an actions block
    assert agent._parse('Each is an object with a type. The list of actions follows.\n```json\n{"type": "x",}\n```')[3] == []


def test_only_an_exact_json_fence_at_a_line_start_counts():
    assert agent._parse('a\n```jsonc\n{"actions": [{"type": "x",}]}\n```')[3] == []          # jsonc / json5 are not the actions block
    assert agent._parse('a\n```json5\n{"actions": [{"type": "x"}]}\n```')[1] == []
    reply, actions, _t, problems = agent._parse('Put it in a ```json fence.\n```json\n{"actions": [{"type": "idea.ready"}]}\n```')
    assert actions == [{"type": "idea.ready"}] and problems == [] and reply == "Put it in a ```json fence."
    assert agent._parse('a\n```json  \n{"actions": [{"type": "idea.ready"}]}\n```')[1] == [{"type": "idea.ready"}]


def test_real_actions_blocks_are_not_dropped_by_line_endings_indent_or_a_same_line_fence():
    good = '{"actions": [{"type": "idea.ready"}]}'
    want = [{"type": "idea.ready"}]
    assert agent._parse('Ok\r\n```json\r\n' + good + '\r\n```\r\n')[1] == want                  # CRLF
    assert agent._parse('1. Do this:\n   ```json\n   ' + good + '\n   ```\n')[1] == want        # under a list item
    reply, actions, _t, problems = agent._parse('Ok ```json ' + good + '```')                 # same line
    assert actions == want and problems == [] and reply == "Ok"
    assert len(agent._parse('Ok ```json {"actions": [{"type": "a",}]}```')[3]) == 1          # broken, same line: refused
    assert len(agent._parse('Ok ```json {"actions": [{"type": "a"')[3]) == 1                  # cut off, same line: refused
    assert agent._parse('Use a ```json fence for it.')[3] == []                              # prose only


def test_a_denied_call_is_warn_not_bad_and_the_detail_goes_to_the_right_run_once():
    meta = {"stream": True, "runs": [{"label": "Running check.py", "failed": False},
                                     {"label": "Running check_stock.py", "failed": False},
                                     {"label": "Running check_stock.py", "failed": False},
                                     {"label": "Running boom.py", "failed": True},
                                     {"label": "Running denied.py", "failed": True}],
            "denied": [{"tool": "Bash", "input": {"command": "python scripts/denied.py"}}]}
    claimed = [{"t": "Stock (check_stock.py)", "d": "18 lines"}, {"t": "Boom (boom)", "d": "never"},
               {"t": "Again", "d": "check_stock second"}]
    chips = agent.real_tools(meta, claimed)
    raw = lambda c: c["raw"].replace("Running ", "")
    assert [raw(c) for c in chips] == ["check.py", "check_stock.py", "check_stock.py", "boom.py", "denied.py"]
    assert chips[0].get("d") is None and chips[0]["st"] == "ok"               # check.py does not take check_stock's detail
    assert (chips[1]["st"], chips[1]["d"]) == ("ok", "18 lines")
    assert (chips[2]["st"], chips[2]["d"]) == ("ok", "check_stock second")      # a claim is used once, in order
    assert (chips[3]["st"], chips[3].get("d")) == ("bad", None)                 # a failed run never takes the model's detail
    assert (chips[4]["st"], chips[4].get("d")) == ("warn", None)                # denied wins over the error it comes with
