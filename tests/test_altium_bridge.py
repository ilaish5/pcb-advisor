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
            elif c[0] == "ADDDOC":
                with open(self.prj, "a", encoding="ascii", newline="") as fh:
                    n = self.prj.read_text(encoding="ascii").count("[Document") + 1
                    fh.write(f"\r\n[Document{n}]\r\nDocumentPath={pathlib.Path(c[2]).name}\r\n")
            elif c[0] == "OUTJOB":                  # Altium's own folder next to the project: one Gerber per layer
                out = self.prj.parent / f"Project Outputs for {self.prj.stem}" / "Gerber"
                out.mkdir(parents=True, exist_ok=True)
                for ext in ("GTL", "GBL", "GTS", "GBS", "GTO", "GBO", "GTP", "GBP", "GM1"):
                    (out / f"{self.prj.stem}.{ext}").write_text("G04 x*\nM02*\n")
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
    # the stub Altium answers on launch (run_commands clears old answers first); while the script runs only the flag
    # files are looked at, response.txt and log.txt are read once end.flag is there

    def altium(*a, **k):
        (tmp_path / "response.txt").write_text("START\nOK 0\nDONE\n")
        (tmp_path / "start.flag").write_text("start.flag")
        (tmp_path / "end.flag").write_text("end.flag")
    monkeypatch.setattr(bridge.subprocess, "Popen", altium)
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


def test_a_skeleton_that_stalls_still_leaves_the_project_created_and_linked(lte, fake, monkeypatch):
    import serve

    def stall(project, sheet=None):
        raise bridge.BridgeError("Altium stopped in the middle of the script, after: title block on.")
    monkeypatch.setattr(bridge, "skeleton", stall)
    res = bridge.create(lte)
    assert project_mod.altium_link(lte)["project_file"] == res["project_file"]
    assert "title block on" in res["skeleton_error"]
    project_mod.set_altium_link(lte, project_file="", pcb_file="")
    for f in pathlib.Path(res["project_file"]).parent.glob("*.PrjPcb"):
        f.unlink()
    applied, _, refused = serve.apply_actions(lte, [{"type": "altium.create_project"}])
    assert applied == ["altium.create_project"] and refused[0].startswith("altium.skeleton:")


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


# ---------------------------------------------------------------- import-rules and run-outjob

FIX = pathlib.Path(__file__).parent / "fixtures" / "altium"


def _linked_with_rules_board(lte, fake):
    """A linked Altium project whose PcbDoc is the fixture board (it has rules of its own)."""
    res = bridge.new_project(lte)
    pcb = pathlib.Path(project_mod.altium_link(lte)["pcb_file"])
    pcb.write_bytes((FIX / "rules-board.PcbDoc").read_bytes())
    fake.runs.clear()
    return pathlib.Path(res["project_file"]), pcb


def test_import_rules_sends_the_preset_and_extras_minus_the_disabled_ones(lte, fake):
    prj, pcb = _linked_with_rules_board(lte, fake)
    todo, _ = bridge.rule_plan(lte, pcb)
    names = [rec["NAME"] for rec, _ in todo]
    assert names
    off = names[0]
    (store.pdir(lte) / "rules-off.json").write_text(json.dumps([off]), encoding="utf-8")
    (store.pdir(lte) / "rules.json").write_text(json.dumps([
        {"name": "Silk_Silk", "kind": "SilkToSilkClearance", "values": {"gap": "8mil"}},
        {"name": "Poly_Conn", "kind": "PolygonConnect", "values": {}}]), encoding="utf-8")
    res = bridge.import_rules(lte)
    cmds = fake.flat()
    assert cmds[0] == ("PROJECT", str(prj)) and cmds[-1] == ("SAVE", str(pcb))
    sent = {c[3]: c for c in cmds if c[0] == "RULE"}
    assert off not in sent and set(names) - {off} <= set(sent)               # the rule that is off is not written
    assert sent["Silk_Silk"][1:3] == (str(pcb), "SilkToSilkClearance") and "SilkToSilkClearance=80000" in sent["Silk_Silk"]
    assert "Poly_Conn" not in sent                                            # a kind we cannot write is reported, not sent
    assert [x["name"] for x in res["skipped"]] == ["Poly_Conn"]
    assert all(f.isascii() for c in sent.values() for f in c)
    assert (pathlib.Path(res["backup"]) / pcb.name).read_bytes() == (FIX / "rules-board.PcbDoc").read_bytes()
    assert any(e["op"] == "import-rules" for e in store.read_jsonl(store.pdir(lte) / "altium-log.jsonl"))


def test_import_rules_lengths_are_altium_units_and_every_property_is_one_the_kind_has(lte, fake):
    _, pcb = _linked_with_rules_board(lte, fake)
    todo, _ = bridge.rule_plan(lte, pcb)
    assert todo
    for rec, vals in todo:
        assert rec["RULEKIND"] in bridge.RULE_PROPS and set(vals) <= set(bridge.RULE_PROPS[rec["RULEKIND"]].values())
    assert bridge._coord("6mil") == 60000 and bridge._coord("0.1524mm") == 60000 and bridge._coord("-2mil") == -20000
    assert bridge._same_values({"Gap": 60000}, {"Gap": 60010}) and not bridge._same_values({"Gap": 60000}, {"Gap": 61000})


def test_import_rules_needs_a_linked_project_and_leaves_a_matching_board_alone(lte, fake, monkeypatch):
    with pytest.raises(bridge.BridgeError, match="No Altium project is linked"):
        bridge.import_rules(lte)
    _linked_with_rules_board(lte, fake)
    monkeypatch.setattr(bridge, "rule_plan", lambda project, pcb: ([], []))
    res = bridge.import_rules(lte)
    assert res["created"] == res["updated"] == [] and not res["backup"] and not fake.runs


def test_run_outjob_adds_ours_when_the_project_has_none(lte, fake):
    prj, _ = _linked_with_rules_board(lte, fake)
    res = bridge.run_outjob(lte)
    out = prj.parent / f"{prj.stem}.OutJob"
    assert res["added"] and out.is_file() and res["containers"] == ["Folder Structure"]
    cmds = fake.flat()
    assert [c[0] for c in cmds] == ["PROJECT", "ADDDOC", "SAVEPRJ", "OUTJOB"]
    assert cmds[1][1:] == (str(prj), str(out)) and cmds[3][1:3] == (str(out), "Folder Structure")
    assert (pathlib.Path(res["backup"]) / prj.name).is_file()                  # the project file is copied first
    assert any(f.endswith(".GTL") for f in res["files"])


def test_run_outjob_uses_the_projects_own_outjob_and_the_gerber_set_is_found(lte, fake):
    import jlc_upload
    _linked_with_rules_board(lte, fake)
    bridge.run_outjob(lte)                       # the fake adds the OutJob to the project file, as Altium does
    fake.runs.clear()
    res = bridge.run_outjob(lte)
    assert not res["added"] and [c[0] for c in fake.flat()] == ["PROJECT", "OUTJOB"]
    got = jlc_upload.find_set(lte)
    assert {p.suffix.upper() for p, _ in got["gerbers"]} >= {".GTL", ".GBL", ".GTS", ".GBS"}


def test_run_outjob_says_so_when_altium_wrote_nothing(lte, fake, monkeypatch):
    _linked_with_rules_board(lte, fake)
    monkeypatch.setattr(bridge, "run_commands", lambda commands, **kw: [])
    with pytest.raises(bridge.BridgeError, match="wrote no files"):
        bridge.run_outjob(lte)


def test_the_outjob_template_plots_the_copper_mask_silk_and_paste_layers():
    import outjob
    cfg = outjob.OUTJOB_TEMPLATE.split("OutputType3=Gerber")[1].split("Configuration3_Item1=")[1].split("\n")[0]
    plot = cfg.split("|Plot.Set=")[1].split("|")[0]
    for layer in ("16777217", "16842751", "16973830", "16973834", "16973832"):   # top, bottom, silk, mask, paste
        assert f"{layer}~1" in plot
    assert "16908289" not in cfg.split("AddToAllPlots.Set=")[1].split("|")[0]    # the outline is not in every plot


def test_the_new_actions_route_to_the_bridge_and_report(lte, fake):
    import serve
    _linked_with_rules_board(lte, fake)
    applied, _, refused = serve.apply_actions(lte, [{"type": "altium.import_rules"}, {"type": "altium.run_outjob"}])
    assert not refused
    assert applied[0].startswith("altium.import_rules:") and "added" in applied[0]
    assert applied[1].startswith("altium.run_outjob:") and "OutJob added" in applied[1]


def test_the_new_actions_are_refused_not_raised_without_a_project(lte, fake):
    import serve
    applied, _, refused = serve.apply_actions(lte, [{"type": "altium.import_rules"}, {"type": "altium.run_outjob"}])
    assert not applied and len(refused) == 2 and all("No Altium project is linked" in r for r in refused)


def test_api_import_rules_and_run_outjob(lte, fake, monkeypatch):
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
        for path in ("/api/altium/import-rules", "/api/altium/run-outjob"):
            code, body = post(path)                                  # nothing linked yet
            assert code == 400 and "No Altium project is linked" in body["error"]
        _linked_with_rules_board(lte, fake)
        code, body = post("/api/altium/import-rules")
        assert code == 200 and body["created"] + body["updated"] and set(body) >= {"skipped", "unconfirmed", "backup"}
        code, body = post("/api/altium/run-outjob")
        assert code == 200 and body["added"] and any(f.endswith(".GTL") for f in body["files"])
    finally:
        httpd.shutdown()
        httpd.server_close()
