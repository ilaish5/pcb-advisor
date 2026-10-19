"""
The Altium bridge, with Altium itself stubbed: what we write, what we ask Altium to do, what we back up.
(The real thing needs Windows and Altium Designer; it was run live by hand, see scripts/altium/bridge.py.)
"""
import json
import pathlib
import threading
import urllib.request

import pytest

import project as project_mod
import store
import workspace
from altium import bridge
from altium.prjpcb import read_prjpcb


class FakeAltium:
    """Plays Altium's part: a new document is a file, a saved project lists the documents added to it."""

    def __init__(self):
        self.runs = []
        self.prj = None

    def __call__(self, commands, **kw):
        self.runs.append(list(commands))
        for c in commands:
            if c[0] == "PROJECT":
                self.prj = pathlib.Path(c[1])
            elif c[0] in ("SCH", "PCB"):
                pathlib.Path(c[1]).write_bytes(b"x")
                with open(self.prj, "a", encoding="ascii", newline="") as fh:
                    n = self.prj.read_text(encoding="ascii").count("[Document") + 1
                    fh.write(f"\r\n[Document{n}]\r\nDocumentPath={pathlib.Path(c[1]).name}\r\n")
        return []

    def flat(self):
        return [c for run in self.runs for c in run]


@pytest.fixture
def fake(monkeypatch, home):
    f = FakeAltium()
    monkeypatch.setattr(bridge, "run_commands", f)
    workspace.set_value("altium.projects_dir", str(home / "altium"))
    return f


def test_new_project_writes_the_project_and_one_sheet_per_advisor_sheet(lte, fake, home):
    sheets = store.sheet_ids(lte)
    assert sheets
    res = bridge.new_project(lte)
    prj = pathlib.Path(res["project_file"])
    assert prj.parent.parent == home / "altium" and prj.suffix == ".PrjPcb"
    assert prj.read_bytes().startswith(b"[Design]\r\nVersion=1.0\r\n")
    got = read_prjpcb(prj)
    assert len(got["sheets"]) == len(sheets) and len(got["pcbs"]) == 1 and not got["missing"]
    assert project_mod.altium_link(lte)["project_file"] == str(prj)
    assert project_mod.altium_link(lte)["pcb_file"].endswith(".PcbDoc")
    assert any(e["op"] == "new-project" for e in store.read_jsonl(store.pdir(lte) / "altium-log.jsonl"))


def test_no_sheets_gives_one_main_sheet(empty, fake):
    res = bridge.new_project(empty)
    assert read_prjpcb(res["project_file"])["sheets"] == ["Main.SchDoc"]


def test_an_existing_altium_project_is_never_overwritten(lte, fake):
    res = bridge.new_project(lte)
    before = pathlib.Path(res["project_file"]).read_bytes()
    with pytest.raises(bridge.BridgeError, match="never overwrite"):
        bridge.new_project(lte)
    assert pathlib.Path(res["project_file"]).read_bytes() == before


def test_skeleton_has_frames_and_no_components(lte, fake):
    bridge.new_project(lte)
    fake.runs.clear()
    bridge.skeleton(lte)
    cmds = fake.flat()
    names = [c[0] for c in cmds]
    assert "TITLEBLOCK" in names and "FRAME" in names and "CLEAR" in names
    assert not {"COMPONENT", "PLACE", "WIRE"} & set(names)
    sheet = store.load_sheet(lte, store.sheet_ids(lte)[0])
    frames = [c for c in cmds if c[0] == "FRAME"]
    assert len(frames) == len(sheet["sections"])
    assert all(c[6].startswith(bridge.TAG) for c in frames)          # tagged: a re-run finds and replaces its own
    first = sheet["sections"][0]["id"]
    refs = [p["ref"] for p in sheet["parts"] if p.get("section") == first]
    assert all(r in frames[0][6] for r in refs)
    clear_at = names.index("CLEAR")
    assert clear_at < names.index("FRAME")                            # old frames go first


def test_skeleton_backs_up_a_sheet_before_changing_it(lte, fake):
    res = bridge.new_project(lte)
    sch = next(pathlib.Path(res["project_file"]).parent.glob("*.SchDoc"))
    sch.write_bytes(b"the student's work")
    out = bridge.skeleton(lte)
    saved = list(pathlib.Path(out["backup"]).glob("*.SchDoc"))
    assert [s.read_bytes() for s in saved] == [b"the student's work"]
    assert pathlib.Path(out["backup"]).parent.name == bridge.BACKUP_DIR


def test_add_sheet_and_add_pcb_back_up_the_project_file(lte, fake):
    res = bridge.new_project(lte)
    prj = pathlib.Path(res["project_file"])
    out = bridge.add_sheet(lte, "Power: 5V/3V3?")
    assert pathlib.Path(out["file"]).name == "Power 5V 3V3.SchDoc"
    assert (pathlib.Path(out["backup"]) / prj.name).is_file()
    with pytest.raises(bridge.BridgeError, match="already exists"):
        bridge.add_sheet(lte, "Power 5V 3V3")
    bridge.add_pcb(lte)
    assert len(read_prjpcb(prj)["pcbs"]) == 2


def test_operations_need_a_linked_project(lte, fake):
    with pytest.raises(bridge.BridgeError, match="No Altium project is linked"):
        bridge.skeleton(lte)


def test_frames_layout_fits_the_sheet():
    many = [(f"S{i}", ["Parts: R1", "Nets: GND"]) for i in range(9)]
    for c in bridge.skeleton_commands("a.SchDoc", "T", "P", "", many):
        if c[0] == "FRAME":
            x, y, w, h = map(int, c[2:6])
            assert x >= 0 and y >= 0 and x + w <= 11000 and y + h <= 7600


def test_request_is_ascii_and_tabbed(monkeypatch, tmp_path):
    monkeypatch.setattr(bridge, "EXCHANGE", tmp_path)
    monkeypatch.setattr(bridge, "_exe", lambda: "x2.exe")
    monkeypatch.setattr(bridge.subprocess, "Popen", lambda *a, **k: None)
    monkeypatch.setattr(bridge, "_running", lambda: True)
    monkeypatch.setattr(bridge.time, "sleep", lambda s: None)
    (tmp_path / "response.txt").write_text("START\nDONE\n")
    # the stub Altium answered before we asked; run_commands clears the old answer, so provide it on launch
    monkeypatch.setattr(bridge.subprocess, "Popen",
                        lambda *a, **k: (tmp_path / "response.txt").write_text("START\nOK 0\nDONE\n"))
    bridge.run_commands([("FRAME", "p", "1", "2", "3", "4", "café\\nline")])
    assert (tmp_path / "request.txt").read_bytes() == b"FRAME\tp\t1\t2\t3\t4\tcaf?\\nline\r\n"


def test_non_windows_says_so(monkeypatch):
    monkeypatch.setattr(bridge.sys, "platform", "linux")
    with pytest.raises(bridge.BridgeError, match="Windows"):
        bridge.run_commands([("PING",)])


def test_actions_route_to_the_bridge(lte, fake):
    import serve
    applied, proposals, refused = serve.apply_actions(lte, [
        {"type": "altium.create_project"}, {"type": "altium.add_sheet", "name": "Extra"},
        {"type": "altium.skeleton"}, {"type": "altium.add_pcb"}])
    assert not refused and not proposals
    assert applied[:2] == ["altium.create_project", "altium.add_sheet:Extra"]
    assert "altium.skeleton" in applied and "altium.add_pcb" in applied


def test_an_action_without_a_project_is_refused_not_raised(lte, fake):
    import serve
    applied, _, refused = serve.apply_actions(lte, [{"type": "altium.skeleton"}])
    assert not applied and "No Altium project is linked" in refused[0]


def test_api_create_links_and_reports_errors(lte, fake, monkeypatch):
    from http.server import ThreadingHTTPServer
    import serve
    monkeypatch.setattr(serve, "QUIET", True)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    def post(path):
        req = urllib.request.Request(f"{base}{path}?project={lte}", method="POST", data=b"{}",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    try:
        code, body = post("/api/altium/create")
        assert code == 200 and body["linked"]["project_file"].endswith(".PrjPcb")
        code, body = post("/api/altium/create")                     # the folder now holds a project
        assert code == 400 and "never overwrite" in body["error"]
    finally:
        httpd.shutdown()
        httpd.server_close()
