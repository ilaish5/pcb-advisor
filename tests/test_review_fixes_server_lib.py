"""Second review round: update and delete hold the step lock, a footprint with converter errors fails closed (never written, drawn, placed
or made), the batch uses decide's own verdict, a non-loopback server.host is reachable, and the 403 / Content-Length edge cases."""
import json
import os
import socket
import threading
import time

import pytest

import background
import serve
import store
import workspace
from altium import bridge
from test_chat_turns import call, server  # noqa: F401
from test_partlib import fake_fetch, prep, proj  # noqa: F401
from test_security_locks import EVIL, _proposal, raw


@pytest.fixture(autouse=True)
def fresh_locks(monkeypatch):
    """Locks of our own: a lock another test leaked (a step thread still running at its end) must not decide these results."""
    monkeypatch.setattr(serve, "STEP_LOCK", threading.Lock())
    monkeypatch.setattr(serve, "UPDATE_LOCK", threading.Lock())
    monkeypatch.setitem(serve.UPDATE, "state", "idle")
    monkeypatch.setitem(serve.BUSY, "chat", 0)


# ---------------------------------------------------------------- 1. update holds the step lock

def test_update_holds_the_step_lock_through_apply(monkeypatch):
    import update
    monkeypatch.setitem(serve.UPDATE, "state", "idle")
    seen = {}

    def apply():
        seen["locked"] = serve.STEP_LOCK.locked()
        seen["button"] = serve.altium_start("nothing")      # a step button cannot start mid-update
        return {"ok": True, "to": "abc"}
    monkeypatch.setattr(update, "apply", apply)
    code, _ = serve.apply_update()
    assert code == 200 and seen["locked"] and seen["button"] == serve.ALTIUM_BUSY
    assert not serve.STEP_LOCK.locked()                     # no restart in a test (HTTPD is None): released


def test_update_keeps_the_lock_until_the_restart_and_releases_on_failure(monkeypatch):
    import update
    monkeypatch.setitem(serve.UPDATE, "state", "idle")
    monkeypatch.setitem(serve.BUSY, "chat", 0)
    monkeypatch.setattr(serve, "HTTPD", object())
    monkeypatch.setattr(threading, "Timer", lambda *a, **k: type("T", (), {"start": lambda self: None})())
    monkeypatch.setattr(update, "apply", lambda: {"ok": True, "to": "abc"})
    try:
        assert serve.apply_update()[0] == 200
        assert serve.STEP_LOCK.locked()                     # held: no step may start between apply and the restart
    finally:
        serve.STEP_LOCK.release()
    monkeypatch.setattr(update, "apply", lambda: {"ok": False, "reason": "no"})
    monkeypatch.setitem(serve.UPDATE, "state", "idle")
    assert serve.apply_update()[0] == 400 and not serve.STEP_LOCK.locked()


# ---------------------------------------------------------------- 1, 3, 4. delete

def _new(server, empty, name):
    assert call(server, "POST", "/api/projects/new", empty, {"name": name})[0] == 200
    return workspace.projects_dir() / workspace.safe_name(name)


def test_delete_holds_the_step_lock_while_it_moves(server, empty, monkeypatch):
    folder = _new(server, empty, "Held")
    seen = []
    real = os.rename
    monkeypatch.setattr(os, "rename", lambda a, b: seen.append(serve.STEP_LOCK.locked()) or real(a, b))
    assert call(server, "POST", "/api/projects/delete", empty, {"name": "Held"})[0] == 200
    assert seen == [True] and not folder.exists() and not serve.STEP_LOCK.locked()


def test_delete_busy_check_uses_the_folder_name(server, empty):
    folder = _new(server, empty, "My Board")
    assert folder.name == "My-Board"
    serve.TURNS[("My-Board", "s")] = serve._new_turn()      # TURNS is keyed by the folder, the text typed was "My Board"
    try:
        assert call(server, "POST", "/api/projects/delete", empty, {"name": "My Board"})[0] == 409
    finally:
        serve.TURNS.pop(("My-Board", "s"))
    assert folder.is_dir()


@pytest.mark.windows        # folder names ignore case only on a Windows file system
def test_delete_busy_check_ignores_case_on_windows(server, empty):
    folder = _new(server, empty, "My Board")
    serve.TURNS[("My-Board", "s")] = serve._new_turn()
    try:
        assert call(server, "POST", "/api/projects/delete", empty, {"name": "my board"})[0] == 409
    finally:
        serve.TURNS.pop(("My-Board", "s"))
    assert folder.is_dir()


def test_delete_with_an_open_file_leaves_the_project_intact(server, empty, monkeypatch):
    folder = _new(server, empty, "Locked")
    (folder / "a.txt").write_text("x")

    def refuse(a, b):
        raise PermissionError("in use")
    monkeypatch.setattr(os, "rename", refuse)
    code, body = call(server, "POST", "/api/projects/delete", empty, {"name": "Locked"})
    assert code == 409 and "open" in body["error"] and "retry" in body["error"]
    assert (folder / "a.txt").read_text() == "x"
    assert not list((workspace.projects_dir() / ".trash").glob("Locked-*")) if (workspace.projects_dir() / ".trash").exists() else True


def test_delete_refused_while_a_redraw_or_a_background_job_runs(server, empty):
    folder = _new(server, empty, "Busy")
    with serve.project_busy("Busy"):
        assert call(server, "POST", "/api/projects/delete", empty, {"name": "Busy"})[0] == 409
    gate = threading.Event()
    assert background.submit("stock:Busy:R1", gate.wait)
    try:
        assert call(server, "POST", "/api/projects/delete", empty, {"name": "Busy"})[0] == 409
    finally:
        gate.set()
        background.wait_idle()
    assert folder.is_dir()
    assert call(server, "POST", "/api/projects/delete", empty, {"name": "Busy"})[0] == 200


# ---------------------------------------------------------------- 5. batch

def test_batch_reports_already_from_decides_own_verdict(server, empty, monkeypatch):
    pid = _proposal(empty)
    real = store.decide
    # another batch decided it between our look and our decide: decide (under its lock) says "already"
    monkeypatch.setattr(store, "decide", lambda *a, **k: {**real(*a, **k), "already": True})
    said = []
    monkeypatch.setattr(serve, "say", lambda *a, **k: said.append(a))
    code, body = call(server, "POST", "/api/proposals/batch", empty, {"ids": [pid], "decision": "rejected"})
    assert code == 200 and body["results"][0] == {"id": pid, "ok": True, "already": True}
    assert said == []                                       # not announced again


# ---------------------------------------------------------------- 6. non-loopback host

def test_allowed_hosts_for_a_lan_server(monkeypatch):
    assert serve.allowed_hosts("127.0.0.1") == set() and serve.allowed_hosts("localhost") == set()
    assert serve.allowed_hosts("192.168.1.20") == {"192.168.1.20"}
    assert serve.allowed_hosts("Lab-PC") == {"lab-pc"}
    monkeypatch.setattr(socket, "gethostname", lambda: "MyPC")
    monkeypatch.setattr(socket, "getfqdn", lambda: "mypc.lan")
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("10.0.0.5", 0)), (23, 1, 6, "", ("fe80::1%12", 0, 0, 12))])
    got = serve.allowed_hosts("0.0.0.0")
    assert {"mypc", "mypc.lan", "10.0.0.5", "[fe80::1]"} <= got and "evil" not in got


def test_a_configured_lan_host_is_accepted_and_others_still_refused(server, empty, monkeypatch):
    port = server.rsplit(":", 1)[1]
    assert raw(server, "GET", f"/api/state?project={empty}", None, {"Host": f"lab-pc:{port}"})[0] == 403
    monkeypatch.setattr(serve, "EXTRA_HOSTS", {"lab-pc"})
    assert raw(server, "GET", f"/api/state?project={empty}", None, {"Host": f"lab-pc:{port}"})[0] == 200
    assert raw(server, "GET", f"/api/state?project={empty}", None, {"Host": f"lab-pc:{port}", "Origin": f"http://lab-pc:{port}"})[0] == 200
    assert raw(server, "GET", f"/api/state?project={empty}", None, EVIL)[0] == 403
    assert raw(server, "GET", f"/api/state?project={empty}", None, {"Host": "rebound.example"})[0] == 403


# ---------------------------------------------------------------- 7. the 403 path

def _socket_post(server, headers, body=b"", chunks=None):
    host, port = server[len("http://"):].split(":")
    s = socket.create_connection((host, int(port)), timeout=15)
    s.sendall(("POST /api/chat/stop HTTP/1.1\r\n" + "".join(f"{k}: {v}\r\n" for k, v in headers.items()) + "\r\n").encode())
    for c in (chunks or [body]):
        try:
            s.sendall(c)
        except OSError:
            break
    out = b""
    end = time.time() + 15
    while b"\r\n\r\n" not in out and time.time() < end:
        got = s.recv(65536)
        if not got:
            break
        out += got
    s.close()
    return out


def test_403_with_a_huge_body_is_delivered_and_closes(server):
    size = 6 << 20
    chunk = b"x" * (1 << 20)
    out = _socket_post(server, {"Host": "evil", "Content-Type": "application/json", "Content-Length": str(size)}, chunks=[chunk] * 6)
    head = out.split(b"\r\n\r\n")[0].decode().lower()
    assert head.startswith("http/1.") and " 403 " in head.split("\r\n")[0] and "connection: close" in head


def test_a_non_numeric_content_length_is_a_400(server):
    for host in ("evil", server[len("http://"):]):
        out = _socket_post(server, {"Host": host, "Content-Length": "abc"})
        assert b" 400 " in out.split(b"\r\n")[0], host


# ---------------------------------------------------------------- 2. a footprint in error fails closed

def _broken(proj):
    def fetch(cid, dest):
        ok, msg = fake_fetch([])(cid, dest)
        if cid == "C100":                                    # the resistor's footprint has an unknown pad shape
            mod = dest / "lib.pretty" / "R0603_FAKE.kicad_mod"
            mod.write_text(mod.read_text().replace(" rect ", " trapezoid "))
        return ok, msg
    return prep(proj, fetcher=fetch)


def test_a_footprint_with_errors_is_not_written_to_the_spec(proj, home):
    m = _broken(proj)
    assert m["R1"]["status"] == "error"
    build = home / "projects" / proj / "library" / "build"
    spec = (build / "footprints_spec.txt").read_text(encoding="cp1252")
    assert "FOOTPRINT|R0603_FAKE" not in spec and "FOOTPRINT|" in spec          # the sound ones are still there
    assert store.footprint_errors(proj)["R0603_FAKE"]
    assert any("trapezoid" in p["message"] for p in partlib_check(build))
    assert not any("links to missing footprint" in p["message"] for p in partlib_check(build))


def partlib_check(build):
    import partlib
    return partlib.check_build(build)


def test_a_footprint_error_is_its_own_state_in_the_bom(proj, home):
    _broken(proj)
    lines = {l["key"]: l for l in store.bom(proj)}
    assert lines["R1"]["library"] == "error" and lines["U1"]["library"] != "error"
    t = store.totals(list(lines.values()))
    assert t["library_error"] >= 1
    assert not [r for r in store.library_view(proj) if r["line"] == "R1" and r["status"] != "error"]


def test_bridge_refuses_to_draw_or_place_a_part_with_a_bad_footprint_naming_all_of_them(proj, home):
    _broken(proj)
    bad = sorted(r for p in store.footprint_error_parts(proj) for r in p["refs"])
    assert "R1" in bad and "R3" in bad and "U1" not in bad
    for what in ("draw", "place"):
        with pytest.raises(bridge.BridgeError) as exc:
            bridge.refuse_footprint_errors(proj, {"R1", "R3", "U1"}, what)
        msg = str(exc.value)
        assert f"Cannot {what}" in msg and "R1" in msg and "R3" in msg and "U1" not in msg and "trapezoid" in msg
        assert "another LCSC code" in msg and "generates the footprint" in msg
    bridge.refuse_footprint_errors(proj, {"U1"}, "place")        # parts that are fine pass


def test_manufacturing_is_blocked_while_a_bom_part_has_a_footprint_error(proj, home):
    _broken(proj)
    msg = store.manufacturing_warning(proj)
    assert msg.startswith("Not made yet:") and "R1" in msg and "footprint with errors" in msg and "trapezoid" in msg
    assert json.dumps(msg).count("Not made yet") == 1 or "Also:" in msg
