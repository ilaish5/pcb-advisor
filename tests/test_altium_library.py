"""
build_library with Altium stubbed: the specs are filled in, the Altium steps are sent in order, the libraries are read
back and checked, the IntLib has to be fresh and installed, and the manifest says per line whether it was built.
(The real run was done live by hand; see scripts/altium/bridge.py.)
"""
import json
import os
import pathlib

import pytest

import store
import workspace
from altium import bridge
from altium.lib import read_pcblib, read_schlib

SYM_SPEC = ("LIBRARY|<SCHLIB>\nSYMBOL|R10K|r\nPIN|1|1|eElectricPassive|0|0|0\nPIN|2|2|eElectricPassive|100|0|0\n"
            "SYMBOL|U1X|u\nPIN|1|IN|eElectricInput|0|0|0\nPIN|2|OUT|eElectricOutput|100|0|0\nPIN|3|GND|eElectricPower|0|50|0\n")
FP_SPEC = ("FPLIB|<PCBLIB>\nFOOTPRINT|R0603|r\nPAD|1|0|0|1|1|0\nPAD|2|1|0|1|1|0\n"
           "FOOTPRINT|SOT23|s\nPAD|1|0|0|1|1|0\nPAD|2|1|0|1|1|0\nPAD|3|2|0|1|1|0\n")


@pytest.fixture
def lib(lte, home, monkeypatch):
    """A linked Altium project and a prepared library/build."""
    workspace.set_value("altium.projects_dir", str(home / "altium"))
    prj = home / "altium" / "lte" / "lte.PrjPcb"
    prj.parent.mkdir(parents=True)
    prj.write_text("[Design]\r\n", encoding="ascii")
    monkeypatch.setattr(bridge, "_linked", lambda project: prj)
    ldir = store.pdir(lte) / "library"
    build = ldir / "build"
    build.mkdir(parents=True)
    (build / "symbols_spec.txt").write_text(SYM_SPEC, encoding="cp1252")
    (build / "footprints_spec.txt").write_text(FP_SPEC, encoding="cp1252")
    (build / "links.txt").write_text("R10K=R0603\nU1X=SOT23\n", encoding="utf-8")
    (build / "props.txt").write_text("R10K=R|10k\nU1X=U|U1X\n", encoding="utf-8")
    (build / "parts.json").write_text(json.dumps({
        "symbols": {"R10K": {"params": {"MPN": "R10K", "Empty": " "}, "hide_pin_names": True}, "U1X": {"params": {"MPN": "U1X"}}},
        "footprints": {"R0603": {"steps": []}, "SOT23": {"steps": ["steps/sot.step"]}}}), encoding="utf-8")
    (ldir / "steps").mkdir()
    (ldir / "steps" / "sot.step").write_bytes(b"ISO-10303")
    (ldir / "manifest.json").write_text(json.dumps({
        "C1": {"symbol": "R10K", "footprint": "R0603"}, "U1": {"symbol": "U1X", "footprint": "SOT23"},
        "X9": {"symbol": None, "footprint": None}}), encoding="utf-8")
    (ldir / "converter.txt").write_text(bridge.partlib.converter_fingerprint() + "\n", encoding="utf-8")
    return lte


class Stub:
    """Altium's part: COMPILE writes the IntLib, CHECKINST says whether it is installed; the libraries read back
    as what the specs describe (or with a pad on no layer)."""

    def __init__(self, monkeypatch, bad_pads=False, stall_first=False, make_intlib=True, installed=True):
        self.runs, self.bad_pads, self.stalled = [], bad_pads, not stall_first
        self.make_intlib, self.installed, self.fail_commands = make_intlib, installed, False
        self.same_name = []
        self.adddoc, self.doc_path = True, "Library\\Project Outputs for lte-Lib\\lte-Lib.IntLib"
        monkeypatch.setattr(bridge, "run_commands", self)
        monkeypatch.setattr(bridge, "read_schlib", self.schlib)
        monkeypatch.setattr(bridge, "read_pcblib", self.pcblib)

    def names(self):
        return [c[0] for run in self.runs for c in run]

    def __call__(self, commands, **kw):
        self.runs.append(list(commands))
        if not self.stalled and any(c[0] == "SYMBATCH" for c in commands):
            self.stalled = True
            raise bridge.BridgeError("Altium stopped in the middle of the script")
        if self.fail_commands and any(c[0] == "FPBATCH" for c in commands):
            raise bridge.BridgeError("Altium did not start the script")
        out = []
        for c in commands:
            if c[0] == "COMPILE" and self.make_intlib:
                pathlib.Path(c[2]).parent.mkdir(parents=True, exist_ok=True)
                pathlib.Path(c[2]).write_bytes(b"intlib")
                out += [f"uninstalled same-name {p}" for p in self.same_name]
            if c[0] == "ADDDOC" and self.adddoc:
                with open(c[1], "a", encoding="ascii", newline="") as fh:
                    fh.write(f"\r\n[Document1]\r\nDocumentPath={self.doc_path}\r\n")
            if c[0] == "CHECKINST":
                out.append("INSTALLED yes x" if self.installed else "INSTALLED no x")
        return out

    def schlib(self, path):
        def pin(n, name, el, show):
            return {"number": n, "name": name, "electrical": el, "show_name": show}
        return {"symbols": [
            {"name": "R10K", "designator": "R?", "comment": "10k", "params": {"MPN": "R10K"}, "footprints": ["R0603"],
             "pinned_paths": [], "pins": [pin("1", "1", "Passive", False), pin("2", "2", "Passive", False)]},
            {"name": "U1X", "designator": "U?", "comment": "U1X", "params": {"MPN": "U1X"}, "footprints": ["SOT23"],
             "pinned_paths": [], "pins": [pin("1", "IN", "Input", True), pin("2", "OUT", "Output", True),
                                          pin("3", "GND", "Power", True)]}]}

    def pcblib(self, path):
        def pads(n):
            return [{"name": str(i + 1), "layer": 0 if self.bad_pads else 74} for i in range(n)]
        return {"footprints": [{"name": "R0603", "pads": pads(2), "bodies": []},
                               {"name": "SOT23", "pads": pads(3), "bodies": [{"model": "SOT23"}]}], "models": ["SOT23"]}


def manifest(lib):
    return json.loads((store.pdir(lib) / "library" / "manifest.json").read_text(encoding="utf-8"))


def test_spec_readers(tmp_path):
    s = tmp_path / "s.txt"
    s.write_text(SYM_SPEC, encoding="cp1252")
    f = tmp_path / "f.txt"
    f.write_text(FP_SPEC, encoding="cp1252")
    assert bridge.spec_symbols(s)["U1X"] == [("1", "IN", "Input"), ("2", "OUT", "Output"), ("3", "GND", "Power")]
    assert bridge.spec_footprints(f) == {"R0603": 2, "SOT23": 3}
    assert bridge.spec_symbols(tmp_path / "none") == {}


def test_an_installed_library_of_the_same_file_name_is_reported_as_removed(lib, monkeypatch):
    stub = Stub(monkeypatch)
    stub.same_name = ["C:\\old\\lte-Lib.IntLib"]
    res = bridge.build_library(lib)
    assert len(res["notices"]) == 1 and "C:\\old\\lte-Lib.IntLib" in res["notices"][0] and "file name" in res["notices"][0]
    stub.same_name = []
    assert bridge.build_library(lib)["notices"] == []


def test_a_build_fills_the_specs_sends_the_steps_in_order_and_marks_every_line(lib, monkeypatch):
    stub = Stub(monkeypatch)
    res = bridge.build_library(lib)
    lp = bridge.library_paths(lib)
    assert res["installed"] and res["intlib_fresh"] and res["prepared"] is False
    assert res["counts"] == {"symbols": 2, "footprints": 2, "pads": 5, "bodies": 1, "models": 1}
    names = stub.names()
    assert names[0] == "LIBCLOSE"                           # nothing of the old library stays open or installed
    assert names[-5:] == ["COMPILE", "CHECKINST", "PROJECT", "ADDDOC", "SAVEPRJ"]
    for step in ("FPBATCH", "SYMBATCH", "SYMLINK", "SYMPROPS", "SYMPARAMS", "HIDEPINS", "ATTACH3D"):
        assert step in names and names.index(step) < names.index("COMPILE")
    assert names.index("FPBATCH") < names.index("FPREMOVE")          # the dummy goes only after the real parts are in
    assert names.index("SYMBATCH") < names.index("SYMREMOVE") < names.index("SYMLINK") < names.index("HIDEPINS")
    assert names.count("SAVELIB") == 2 and names.count("COMPILE") == 1
    removed = [c[2] for run in stub.runs for c in run if c[0] in ("FPREMOVE", "SYMREMOVE")]
    assert removed == [bridge.TEMPLATE_FOOTPRINT, bridge.TEMPLATE_SYMBOL]
    out = lp["prj"].parent / "Library"
    assert (out / "lte-Lib.SchLib").is_file() and (out / "lte-Lib.PcbLib").is_file()
    assert (out / "3D" / "SOT23.step").read_bytes() == b"ISO-10303"
    pkg = (out / "lte-Lib.LibPkg").read_bytes().decode("ascii")
    assert "lte-Lib.SchLib" in pkg and "lte-Lib.PcbLib" in pkg and "\r\n" in pkg
    alt = store.pdir(lib) / "library" / "build" / "altium"
    filled = (alt / "symbols_spec.txt").read_text(encoding="cp1252")
    assert "<SCHLIB>" not in filled and str(lp["schlib"]) in filled
    assert "Empty" not in (alt / "params.txt").read_text()
    assert (alt / "hide.txt").read_bytes() == b"R10K=1\r\n"                 # only the symbols flagged hide_pin_names
    hide = [c for run in stub.runs for c in run if c[0] == "HIDEPINS"]
    assert hide == [("HIDEPINS", str(lp["schlib"]), str(alt / "hide.txt"))]
    man = manifest(lib)
    assert man["C1"]["built"] and man["U1"]["built"]
    assert man["X9"]["built"] is False and "no symbol" in man["X9"]["built_issues"][0]
    assert (store.pdir(lib) / "altium-log.jsonl").is_file()


def test_a_rebuild_starts_from_the_templates_and_keeps_a_backup(lib, monkeypatch):
    Stub(monkeypatch)
    bridge.build_library(lib)
    lp = bridge.library_paths(lib)
    lp["schlib"].write_bytes(b"old schlib")
    (lp["d3"] / "stale.step").write_bytes(b"old")
    res = bridge.build_library(lib)
    assert lp["schlib"].read_bytes() == (bridge.TEMPLATES / "Template.SchLib").read_bytes()
    assert not (lp["d3"] / "stale.step").exists()
    assert res["backup"] and (lp["prj"].parent / ".advisor-backup").is_dir()


def test_a_stop_in_the_middle_is_retried_once_from_the_templates(lib, monkeypatch):
    stub = Stub(monkeypatch, stall_first=True)
    assert bridge.build_library(lib)["installed"]
    assert stub.names().count("LIBCLOSE") == 2


def test_a_compile_that_stops_in_the_middle_is_run_once_more(lib, monkeypatch):
    """Blinker 555, 15/11: the first compile of a new library stopped on an Altium error box after closing the SchLib."""
    stub = Stub(monkeypatch)
    plain = stub.__call__
    state = {"stopped": False}

    def call(commands, **kw):
        if not state["stopped"] and any(c[0] == "COMPILE" for c in commands):
            state["stopped"] = True
            stub.runs.append(list(commands))
            raise bridge.BridgeError("Altium stopped in the middle of the script, after: closed x.SchLib.")
        return plain(commands, **kw)
    monkeypatch.setattr(bridge, "run_commands", call)
    assert bridge.build_library(lib)["installed"]
    assert stub.names().count("COMPILE") == 2 and stub.names().count("LIBCLOSE") == 1
    log = (store.pdir(lib) / "altium-log.jsonl").read_text(encoding="utf-8")
    assert '"retry": "compile: Altium stopped' in log


def test_a_compile_that_stops_twice_fails_and_restores(lib, monkeypatch):
    stub = Stub(monkeypatch)

    def call(commands, **kw):
        stub.runs.append(list(commands))
        if any(c[0] == "COMPILE" for c in commands):
            raise bridge.BridgeError("Altium stopped in the middle of the script, after: closed x.SchLib.")
        return []
    monkeypatch.setattr(bridge, "run_commands", call)
    monkeypatch.setattr(bridge, "read_schlib", stub.schlib)
    with pytest.raises(bridge.BridgeError, match="stopped in the middle"):
        bridge.build_library(lib)
    assert stub.names().count("COMPILE") == 2


def test_wrong_pads_stop_the_build_before_compiling(lib, monkeypatch):
    stub = Stub(monkeypatch, bad_pads=True)
    with pytest.raises(bridge.BridgeError, match="read back wrong"):
        bridge.build_library(lib)
    assert "COMPILE" not in stub.names()
    man = manifest(lib)
    assert man["U1"]["built"] is False and any("no layer" in m for m in man["U1"]["built_issues"])


def test_an_intlib_not_written_or_not_installed_is_an_error(lib, monkeypatch):
    Stub(monkeypatch, make_intlib=False, installed=False)
    with pytest.raises(bridge.BridgeError) as e:
        bridge.build_library(lib)
    assert "not written by this build" in str(e.value) and "not list" in str(e.value)
    assert manifest(lib)["C1"]["built"] is False


def test_a_stale_library_is_prepared_first(lib, monkeypatch):
    Stub(monkeypatch)
    assert bridge.library_stale(lib) is False
    calls = []
    monkeypatch.setattr(bridge.partlib, "prepare", lambda project, fetch=True: calls.append(project))
    (store.pdir(lib) / "bom-log.jsonl").write_text("{}\n")
    os.utime(store.pdir(lib) / "library" / "manifest.json", (1, 1))
    assert bridge.library_stale(lib) is True
    assert bridge.build_library(lib)["prepared"] is True and calls == [lib]


def test_text_altium_cannot_read_is_refused_before_anything_is_touched(lib, monkeypatch):
    stub = Stub(monkeypatch)
    build = store.pdir(lib) / "library" / "build"
    (build / "props.txt").write_text("R10K=R|עברית\n", encoding="utf-8")
    with pytest.raises(bridge.BridgeError, match="cp1252"):
        bridge.build_library(lib)
    assert stub.runs == []
    (build / "props.txt").write_text("R10K=R|10k\n", encoding="utf-8")
    prj = bridge.library_paths(lib)["prj"]
    monkeypatch.setattr(bridge, "_linked", lambda project: prj.parent / "פרויקט" / prj.name)
    with pytest.raises(bridge.BridgeError, match="ASCII"):
        bridge.build_library(lib)
    assert stub.runs == []


def test_a_locked_intlib_is_refused_at_once_with_what_to_do(lib, monkeypatch):
    stub = Stub(monkeypatch)
    lp = bridge.library_paths(lib)
    lp["intlib"].parent.mkdir(parents=True)
    lp["intlib"].write_bytes(b"old")
    real_open = open

    def locked(f, mode="r", *a, **k):
        if str(f) == str(lp["intlib"]) and "+" in mode:
            raise PermissionError(13, "Permission denied")
        return real_open(f, mode, *a, **k)
    monkeypatch.setattr(bridge, "open", locked, raising=False)
    with pytest.raises(bridge.BridgeError, match="locked.*(Close|restart)"):
        bridge.build_library(lib)
    assert "FPBATCH" not in stub.names()


def test_a_failed_build_puts_the_earlier_library_back_and_marks_every_line_unbuilt(lib, monkeypatch):
    stub = Stub(monkeypatch)
    bridge.build_library(lib)
    lp = bridge.library_paths(lib)
    lp["schlib"].write_bytes(b"the library that worked")
    lp["pcblib"].write_bytes(b"its footprints")
    (lp["d3"] / "old.step").write_bytes(b"old step")
    stub.fail_commands = True
    with pytest.raises(bridge.BridgeError, match="earlier library was put back and installed"):
        bridge.build_library(lib)
    assert lp["schlib"].read_bytes() == b"the library that worked" and lp["pcblib"].read_bytes() == b"its footprints"
    assert (lp["d3"] / "old.step").read_bytes() == b"old step"
    assert stub.names().count("INSTALL") == 1
    assert all(e["built"] is False and e["built_issues"] for e in manifest(lib).values())


def test_a_failed_first_build_leaves_no_half_made_library(lib, monkeypatch):
    stub = Stub(monkeypatch)
    stub.fail_commands = True
    with pytest.raises(bridge.BridgeError, match="no earlier library"):
        bridge.build_library(lib)
    lp = bridge.library_paths(lib)
    assert not lp["schlib"].exists() and not lp["pcblib"].exists() and not lp["libpkg"].exists()
    assert all(e["built"] is False for e in manifest(lib).values())


def test_the_exchange_files_are_never_opened_while_the_script_runs(monkeypatch, tmp_path):
    """Altium writes log.txt and response.txt without sharing: a read at the wrong moment freezes its script."""
    monkeypatch.setattr(bridge, "EXCHANGE", tmp_path)
    monkeypatch.setattr(bridge, "_exe", lambda: "x2.exe")
    monkeypatch.setattr(bridge, "_running", lambda: True)
    monkeypatch.setattr(bridge.subprocess, "Popen", lambda *a, **k: bridge.flag_path("start").write_text("x"))
    reads, ticks = [], []

    def sleep(s):
        ticks.append(s)
        (tmp_path / "log.txt").write_text("> PING\n" * len(ticks))     # the script is writing its log
        if len(ticks) == 3:
            (tmp_path / "response.txt").write_text("START\nOK 0\nDONE\n")
            bridge.flag_path("end").write_text("x")
    real_read = bridge._read

    def read(path):
        reads.append((pathlib.Path(path).name, bridge.flag_path("end").exists()))
        return real_read(path)
    monkeypatch.setattr(bridge.time, "sleep", sleep)
    monkeypatch.setattr(bridge, "_read", read)
    assert bridge.run_commands([("PING",)]) == ["> PING"] * 3
    assert reads and all(done for _, done in reads)


def test_a_script_that_stops_logging_is_released_and_its_dialogs_are_reported(monkeypatch, tmp_path):
    monkeypatch.setattr(bridge, "EXCHANGE", tmp_path)
    monkeypatch.setattr(bridge, "_exe", lambda: "x2.exe")
    monkeypatch.setattr(bridge, "_running", lambda: True)
    monkeypatch.setattr(bridge.subprocess, "Popen", lambda *a, **k: bridge.flag_path("start").write_text("x"))
    monkeypatch.setattr(bridge.time, "sleep", lambda s: None)
    monkeypatch.setattr(bridge, "release_executor", lambda **kw: ["[TMessageForm] Error: Cannot create file"])
    with pytest.raises(bridge.BridgeError, match="stopped in the middle.*Cannot create file"):
        bridge.run_commands([("PING",)], stall_timeout=-1)


def test_a_blocking_altium_message_box_tells_the_student_what_to_do(monkeypatch, tmp_path):
    monkeypatch.setattr(bridge, "EXCHANGE", tmp_path)
    monkeypatch.setattr(bridge, "_exe", lambda: "x2.exe")
    monkeypatch.setattr(bridge, "_running", lambda: True)
    monkeypatch.setattr(bridge.subprocess, "Popen", lambda *a, **k: None)
    monkeypatch.setattr(bridge.time, "sleep", lambda s: None)
    monkeypatch.setattr(bridge.time, "time", iter(range(0, 10**6, 100)).__next__)
    monkeypatch.setattr(bridge, "release_executor", lambda **kw: ["[TMessageForm] Information: OK"])
    with pytest.raises(bridge.BridgeError, match=r"sign in.*close any message box.*try again.*\[TMessageForm\] Information: OK"):
        bridge.run_commands([("PING",)])


def test_the_shipped_templates_hold_no_leftovers_of_a_real_part_or_another_computer():
    for name in ("Template.SchLib", "Template.PcbLib"):
        data = (bridge.TEMPLATES / name).read_bytes()
        flat = data.replace(b"\0", b"")
        assert b"ceramic_controller" not in data and b"ceramic_controller" not in flat
        assert b"Keystone" not in flat and b"KEYSTONE" not in flat and b"5015" not in flat
    assert read_pcblib(bridge.TEMPLATES / "Template.PcbLib")["models"] == []


FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "altium" / "built"


def test_lib_reads_a_real_built_schlib():
    """Fixture-Lib.SchLib was built by the bridge in Altium: a 2-pin resistor and an 8-pin IC."""
    syms = {s["name"]: s for s in read_schlib(FIXTURES / "Fixture-Lib.SchLib")["symbols"]}
    assert set(syms) == {"0603WAF1002T5E", "LM393DR2G"}
    r, ic = syms["0603WAF1002T5E"], syms["LM393DR2G"]
    assert (r["designator"], r["comment"], r["footprints"]) == ("R?", "10k", ["R0603"])
    assert sorted(p["number"] for p in r["pins"]) == ["1", "2"]
    assert not any(p["show_name"] for p in r["pins"]) and all(p["show_number"] for p in r["pins"])    # names hidden on 2-pin parts
    assert (ic["designator"], ic["comment"], ic["footprints"]) == ("U?", "LM393DR2G", ["SOIC-8_L5.0-W4.0-P1.27-LS6.0-BL"])
    assert len(ic["pins"]) == 8 and all(p["show_name"] for p in ic["pins"])
    assert ic["params"]["MPN"] == "LM393DR2G" and ic["params"]["LCSC"] == "C7955" and ic["params"]["Manufacturer"] == "onsemi"
    assert ic["pinned_paths"] == [] and r["pinned_paths"] == []


def test_lib_reads_a_real_built_pcblib():
    fps = {f["name"]: f for f in read_pcblib(FIXTURES / "Fixture-Lib.PcbLib")["footprints"]}
    assert set(fps) == {"R0603", "SOIC-8_L5.0-W4.0-P1.27-LS6.0-BL"}
    assert len(fps["R0603"]["pads"]) == 2 and len(fps["SOIC-8_L5.0-W4.0-P1.27-LS6.0-BL"]["pads"]) == 8
    for fp in fps.values():
        assert {p["layer"] for p in fp["pads"]} == {1}              # Top Layer: never layer 0 (no layer)
        assert all(p["xsize"] > 0 and p["ysize"] > 0 for p in fp["pads"])
        assert fp["tracks"] + fp["arcs"] > 0 and fp["bodies"] == []


def test_lib_reads_text_as_windows_ansi():
    from altium import lib as altlib
    assert altlib._pascal(bytes([4]) + "a–b™".encode("cp1252")[:4], 0)[0] == "a–b™"
    assert altlib._pascal(bytes([2, 0x81, 0x41]), 0)[0].endswith("A")        # an undefined cp1252 byte does not raise


def test_the_readers_read_the_shipped_templates():
    sch = read_schlib(bridge.TEMPLATES / "Template.SchLib")
    assert [s["name"] for s in sch["symbols"]] == [bridge.TEMPLATE_SYMBOL]
    pcb = read_pcblib(bridge.TEMPLATES / "Template.PcbLib")
    assert [f["name"] for f in pcb["footprints"]] == [bridge.TEMPLATE_FOOTPRINT]


def test_the_build_adds_the_intlib_to_the_project_and_says_so(lib, monkeypatch):
    stub = Stub(monkeypatch)
    res = bridge.build_library(lib)
    assert res["in_project"] is True
    adds = [c for run in stub.runs for c in run if c[0] in ("ADDDOC", "SAVEPRJ")]
    assert [c[0] for c in adds] == ["ADDDOC", "SAVEPRJ"] and adds[0][2].endswith("lte-Lib.IntLib")
    assert [e for e in store.read_jsonl(store.pdir(lib) / "altium-log.jsonl") if e["op"] == "build-library"][-1]["in_project"] is True


def test_the_build_leaves_a_project_that_already_lists_the_intlib_alone(lib, monkeypatch):
    stub = Stub(monkeypatch)
    prj = bridge._linked(lib)
    prj.write_bytes(b"\xef\xbb\xbf[Design]\r\n[Document1]\r\nDocumentPath=LIBRARY/project outputs for LTE-LIB/LTE-LIB.intlib\r\n")
    assert bridge.build_library(lib)["in_project"] is True
    assert "ADDDOC" not in stub.names() and "SAVEPRJ" not in stub.names()


def test_the_build_says_when_the_project_still_lacks_the_intlib(lib, monkeypatch):
    stub = Stub(monkeypatch)
    stub.adddoc = False
    with pytest.raises(bridge.BridgeError, match="not part of lte.PrjPcb.*Footprint Not Found"):
        bridge.build_library(lib)
    last = [e for e in store.read_jsonl(store.pdir(lib) / "altium-log.jsonl") if e["op"] == "build-library"][-1]
    assert last["in_project"] is False and any("Footprint Not Found" in i for i in last["issues"])


def _lists_the_intlib(lib, monkeypatch):
    """The state after a first build: an IntLib on disk that the (open) Altium project lists as a project library."""
    lp = bridge.library_paths(lib)
    lp["intlib"].parent.mkdir(parents=True, exist_ok=True)
    lp["intlib"].write_bytes(b"old intlib")
    bridge._linked(lib).write_bytes(b"[Design]\r\n[Document1]\r\nDocumentPath=Library/Project Outputs for lte-Lib/lte-Lib.IntLib\r\n")
    return lp


def test_a_rebuild_takes_the_intlib_out_of_the_open_project_first_and_puts_it_back_after(lib, monkeypatch):
    """Altium cannot write an IntLib that is a library of the open project ("Could not create integrated library")."""
    stub = Stub(monkeypatch)
    lp = _lists_the_intlib(lib, monkeypatch)
    res = bridge.build_library(lib)
    names = stub.names()
    assert names[:2] == ["LIBRELEASE", "LIBCLOSE"] and names.index("LIBRELEASE") < names.index("COMPILE")
    assert stub.runs[0][0] == ("LIBRELEASE", str(bridge._linked(lib)), str(lp["intlib"]))
    assert names[-3:] == ["PROJECT", "ADDDOC", "SAVEPRJ"]          # sent although the saved file still lists it
    assert res["in_project"] is True and res["intlib_fresh"] is True


def test_a_first_build_has_nothing_to_release(lib, monkeypatch):
    stub = Stub(monkeypatch)
    bridge.build_library(lib)
    assert "LIBRELEASE" not in stub.names()


def test_a_failed_rebuild_puts_the_project_library_back_into_the_project(lib, monkeypatch):
    stub = Stub(monkeypatch)
    _lists_the_intlib(lib, monkeypatch)
    stub.fail_commands = True
    with pytest.raises(bridge.BridgeError, match=r"lte-Lib\.IntLib is a library of lte\.PrjPcb again"):
        bridge.build_library(lib)
    names = stub.names()
    assert names[0] == "LIBRELEASE" and names[-3:] == ["PROJECT", "ADDDOC", "SAVEPRJ"]


def test_a_compile_error_box_is_explained_not_left_as_a_silent_wait(lib, monkeypatch):
    stub = Stub(monkeypatch)
    real = stub.__call__

    def call(commands, **kw):
        if any(c[0] == "COMPILE" for c in commands):
            raise bridge.BridgeError("Altium stopped in the middle of the script, after: x. Dialogs: [TMessageForm] Error: OK")
        return real(commands, **kw)
    monkeypatch.setattr(bridge, "run_commands", call)
    with pytest.raises(bridge.BridgeError, match=r"error box while compiling the library.*lte-Lib\.IntLib.*holds that file"):
        bridge.build_library(lib)


def test_an_altium_error_box_ends_the_wait_without_the_stall_timeout(monkeypatch, tmp_path):
    monkeypatch.setattr(bridge, "EXCHANGE", tmp_path)
    monkeypatch.setattr(bridge, "_exe", lambda: "x2.exe")
    monkeypatch.setattr(bridge, "_running", lambda: True)
    monkeypatch.setattr(bridge.subprocess, "Popen", lambda *a, **k: bridge.flag_path("start").write_text("x"))
    clock = [0.0]
    monkeypatch.setattr(bridge.time, "time", lambda: clock[0])
    monkeypatch.setattr(bridge.time, "sleep", lambda s: clock.__setitem__(0, clock[0] + 5))
    looks = []
    monkeypatch.setattr(bridge, "_close_dialogs", lambda only_look=False: looks.append(only_look) or ["[TMessageForm] Error: OK"])
    monkeypatch.setattr(bridge, "preflight", lambda strict=False, **kw: None)          # this test counts the wait loop's own looks
    monkeypatch.setattr(bridge, "release_executor", lambda **kw: ["[TMessageForm] Error: OK"])
    with pytest.raises(bridge.BridgeError, match="stopped in the middle"):
        bridge.run_commands([("PING",)], stall_timeout=180, total_timeout=900)
    assert looks == [True] and clock[0] < 60          # found by looking, long before the 180 s stall timeout


def _bridge_files(monkeypatch, tmp_path):
    monkeypatch.setattr(bridge, "EXCHANGE", tmp_path)
    monkeypatch.setattr(bridge, "_exe", lambda: "x2.exe")
    monkeypatch.setattr(bridge, "_running", lambda: True)
    monkeypatch.setattr(bridge.time, "sleep", lambda s: None)
    monkeypatch.setattr(bridge, "PREFLIGHT_NOTES", [])


def _finishing_script(tmp_path, order):
    def popen(*a, **k):
        order.append("RunScript")
        bridge.flag_path("start").write_text("x")
        (tmp_path / "response.txt").write_text("START\nDONE\n")
        (tmp_path / "log.txt").write_text("> PING\n")
        bridge.flag_path("end").write_text("x")
    return popen


def test_a_paused_script_is_stopped_before_the_next_command_is_sent(monkeypatch, tmp_path):
    _bridge_files(monkeypatch, tmp_path)
    order = []
    states = iter([{"boxes": ["[TMessageForm] Error: OK"], "foreign": [], "windows": ["AdvisorBridge.pas [Paused] - Altium"]},
                   {"boxes": [], "foreign": [], "windows": []}])
    monkeypatch.setattr(bridge, "_script_state", lambda: next(states))
    monkeypatch.setattr(bridge, "release_executor", lambda **kw: order.append("Stop") or ["[TMessageForm] Error: OK"])
    monkeypatch.setattr(bridge.subprocess, "Popen", _finishing_script(tmp_path, order))
    events = []
    monkeypatch.setattr(bridge.runlog, "event", lambda kind, **f: events.append((kind, f)))
    assert bridge.run_commands([("PING",)]) == ["> PING"]
    assert order == ["Stop", "RunScript"]                                 # released first, then the command
    pre = [f for k, f in events if k == "altium-preflight"]
    assert len(pre) == 1 and pre[0]["box_still_open"] is False and pre[0]["found"] == ["[TMessageForm] Error: OK"] and pre[0]["windows"] == ["AdvisorBridge.pas [Paused] - Altium"]
    notes = bridge.take_preflight_notes()
    assert len(notes) == 1 and notes[0].startswith("**A script was paused in Altium**") and "next step started" in notes[0] and "clean" not in notes[0]
    assert bridge.take_preflight_notes() == []


def test_a_clean_altium_is_not_touched_by_the_preflight(monkeypatch, tmp_path):
    _bridge_files(monkeypatch, tmp_path)
    order = []
    monkeypatch.setattr(bridge, "_script_state", lambda: {"boxes": [], "foreign": [], "windows": []})
    monkeypatch.setattr(bridge, "release_executor", lambda **kw: order.append("Stop") or [])
    monkeypatch.setattr(bridge.subprocess, "Popen", _finishing_script(tmp_path, order))
    bridge.run_commands([("PING",)])
    assert order == ["RunScript"] and bridge.take_preflight_notes() == []


def test_a_gone_box_is_not_a_clean_altium_when_the_script_still_does_not_start(monkeypatch, tmp_path):
    """Seen live: OK and Stop removed the box, the next RunScript still failed. "Clean" is claimed only after start.flag."""
    _bridge_files(monkeypatch, tmp_path)
    states = iter([{"boxes": ["[TMessageForm] Error: OK"], "foreign": [], "windows": []}] + [{"boxes": [], "foreign": [], "windows": []}] * 9)
    monkeypatch.setattr(bridge, "_script_state", lambda: next(states))
    monkeypatch.setattr(bridge, "release_executor", lambda **kw: bridge._RUN.update(evidence=True) or ["[TMessageForm] Error: OK"])   # evidence of a pause
    monkeypatch.setattr(bridge.subprocess, "Popen", lambda *a, **k: None)          # RunScript never creates start.flag
    monkeypatch.setattr(bridge.time, "time", iter(range(0, 10**6, 50)).__next__)
    with pytest.raises(bridge.BridgeError) as err:
        bridge.run_commands([("PING",)])
    msg = str(err.value)
    assert msg.startswith("**Altium cannot run scripts right now** - a script is paused or blocked in Altium.")
    assert "script tab with the highlighted line and press Run (F9) until the highlight is gone" in msg and "restart Altium" in msg and "[TMessageForm] Error: OK" in msg    # the box texts stay in the details
    assert "clean" not in msg.lower() and bridge.take_preflight_notes() == []


def test_the_student_line_says_the_next_step_started_only_after_start_flag(monkeypatch, tmp_path):
    _bridge_files(monkeypatch, tmp_path)
    monkeypatch.setattr(bridge, "_script_state", lambda: {"boxes": ["[TMessageForm] Error: OK"], "foreign": [], "windows": []})
    monkeypatch.setattr(bridge, "release_executor", lambda **kw: [])
    seen = []
    monkeypatch.setattr(bridge.subprocess, "Popen", lambda *a, **k: (seen.append(bridge.take_preflight_notes()),
                                                                       _finishing_script(tmp_path, [])())[0])
    bridge.run_commands([("PING",)])
    assert seen == [[]]                                      # nothing is said before the script has started
    assert "next step started" in bridge.take_preflight_notes()[0]


def test_the_preflight_also_runs_after_an_error(monkeypatch, tmp_path):
    _bridge_files(monkeypatch, tmp_path)
    monkeypatch.setattr(bridge.subprocess, "Popen", lambda *a, **k: None)
    monkeypatch.setattr(bridge, "release_executor", lambda **kw: bridge._RUN.update(evidence=True) or [])
    calls = []
    monkeypatch.setattr(bridge, "preflight", lambda strict=False, **kw: calls.append("pre"))
    monkeypatch.setattr(bridge.time, "time", iter(range(0, 10**6, 100)).__next__)
    with pytest.raises(bridge.BridgeError, match="F9"):
        bridge.run_commands([("PING",)])
    assert calls == ["pre", "pre"]            # before sending, and once more after the failure


def test_the_altium_help_skill_tells_what_to_do_about_a_paused_script():
    skill = (pathlib.Path(__file__).parent.parent / "runtime" / "skills" / "altium-help" / "SKILL.md").read_text(encoding="utf-8")
    assert "F9" in skill and "paused" in skill and "never run or resume a script yourself" in skill


def test_a_window_title_alone_never_triggers_the_preflight(monkeypatch, tmp_path):
    """Seen live: the script editor is a tab of the main window, so a title is only extra logging, never the trigger."""
    monkeypatch.setattr(bridge, "PREFLIGHT_NOTES", [])
    monkeypatch.setattr(bridge, "_script_state", lambda: {"boxes": [], "foreign": [], "windows": ["AdvisorBridge.pas [Paused]"]})
    monkeypatch.setattr(bridge, "release_executor", lambda **kw: pytest.fail("nothing is open that blocks a script"))
    assert bridge.preflight() is None and bridge.take_preflight_notes() == []


def _boxes(*specs):
    return [{"hwnd": i, "cls": cls, "line": f"[{cls}] {title}: {' / '.join(parts)}", "ok_only": bridge._ok_only(parts)}
            for i, (cls, title, parts) in enumerate(specs, 1)]


def test_a_box_that_asks_a_question_is_never_pressed_and_stops_the_step(monkeypatch, tmp_path):
    _bridge_files(monkeypatch, tmp_path)
    pressed = []
    monkeypatch.setattr(bridge, "_dialog_boxes", lambda: _boxes(("TMessageForm", "Confirm", ["&Yes", "&No", "Cancel"]),
                                                                 ("TMessageForm", "Error", ["OK"])))
    monkeypatch.setattr(bridge, "_post_enter", lambda h: pressed.append(("enter", h)))
    monkeypatch.setattr(bridge, "_post_close", lambda h: pressed.append(("close", h)))
    monkeypatch.setattr(bridge.subprocess, "Popen", lambda *a, **k: pressed.append("RunScript"))
    monkeypatch.setattr(bridge.subprocess, "run", lambda *a, **k: type("R", (), {"stdout": ""})())      # tasklist
    with pytest.raises(bridge.BridgeError, match=r"\*\*A message box is open in Altium\*\*.*answer it.*Confirm: &Yes / &No / Cancel"):
        bridge.run_commands([("PING",)])
    assert pressed == []                       # nothing pressed, nothing closed, nothing sent


def test_an_ok_only_script_error_box_is_released_and_a_question_box_left_alone(monkeypatch):
    pressed = []
    monkeypatch.setattr(bridge, "_dialog_boxes", lambda: _boxes(("TMessageForm", "Error", ["OK"]),
                                                                 ("TMessageForm", "Confirm", ["Save", "Discard", "Cancel"]),
                                                                 ("#32770", "Open", ["Cancel"])))
    monkeypatch.setattr(bridge, "_post_enter", lambda h: pressed.append(("enter", h)))
    monkeypatch.setattr(bridge, "_post_close", lambda h: pressed.append(("close", h)))
    seen = bridge._close_dialogs()
    assert pressed == [("enter", 1), ("close", 3)]
    assert seen == ["[TMessageForm] Error: OK", "(left open, not pressed) [TMessageForm] Confirm: Save / Discard / Cancel", "[#32770] Open: Cancel"]
    assert bridge._close_dialogs(only_look=True)[1] == "[TMessageForm] Confirm: Save / Discard / Cancel" and len(pressed) == 2


def test_the_preflight_releases_an_ok_only_box_and_ignores_the_ok_rule_for_nothing_else(monkeypatch):
    monkeypatch.setattr(bridge, "PREFLIGHT_NOTES", [])
    monkeypatch.setattr(bridge, "_dialog_boxes", lambda: _boxes(("TMessageForm", "Error", ["OK"])))
    monkeypatch.setattr(bridge, "release_executor", lambda **kw: ["[TMessageForm] Error: OK"])
    assert bridge.preflight(strict=True)["found"] == ["[TMessageForm] Error: OK"]


def test_preflight_notes_are_kept_per_project(monkeypatch):
    monkeypatch.setattr(bridge, "PREFLIGHT_NOTES", [("a", "note a"), ("b", "note b"), ("a", "second a")])
    assert bridge.take_preflight_notes("a") == ["note a", "second a"]
    assert bridge.take_preflight_notes("a") == [] and bridge.take_preflight_notes("b") == ["note b"]


def test_the_altium_script_checks_before_it_reads_and_states_the_try_except_rule():
    pas = (pathlib.Path(bridge.__file__).parent / "bridge" / "AdvisorBridge.pas").read_text(encoding="utf-8", errors="replace")
    assert "never rely on try/except for a call that may fail" in pas.lower()
    # every procedure that walks the open schematic library says so first, instead of raising on nil
    flat = pas.replace(chr(13) + chr(10), chr(10))
    assert flat.count(chr(10) + "    Lib := SchServer.GetCurrentSchDocument;") == 5
    assert pas.count("if (Lib.ObjectID <> eSchLib) then") == 5 and pas.count("ERR no schematic library is open in Altium") == 5
    for guard in ("ERR the board has no layer stack", "ERR the board has no top or bottom layer in its stack",
                  "ERR the stack has no free signal layer for the first inner layer",
                  "ERR the stack has no room for two more signal layers"):
        assert guard in pas
    docs = (pathlib.Path(bridge.__file__).parent.parent.parent / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    assert "Never rely on try/except for a call that may fail" in docs


class Release:
    """Altium for the release tests: the boxes, a clock that sleep advances, every command line sent to X2.EXE and every key pressed."""

    def __init__(self, monkeypatch, tmp_path, boxes=(("TMessageForm", "Error", ["OK"]),)):
        self.cmds, self.pressed, self.events, self.clock = [], [], [], [0.0]
        self.boxes = list(boxes)
        self.on_macro = None
        monkeypatch.setattr(bridge, "EXCHANGE", tmp_path)
        self.dir = tmp_path
        monkeypatch.setattr(bridge, "_exe", lambda: "x2.exe")
        monkeypatch.setattr(bridge, "_running", lambda: True)
        monkeypatch.setattr(bridge, "preflight", lambda strict=False, **kw: None)
        monkeypatch.setattr(bridge, "_dialog_boxes", lambda: _boxes(*self.boxes))
        monkeypatch.setattr(bridge, "_post_enter", lambda h: self.pressed.append(("enter", self.boxes[h - 1][1])))
        monkeypatch.setattr(bridge, "_post_close", lambda h: self.pressed.append(("close", self.boxes[h - 1][1])))
        monkeypatch.setattr(bridge.subprocess, "Popen", self.popen)
        monkeypatch.setattr(bridge.time, "time", lambda: self.clock[0])
        monkeypatch.setattr(bridge.time, "sleep", lambda s: self.clock.__setitem__(0, self.clock[0] + s))
        monkeypatch.setattr(bridge.runlog, "event", lambda kind, **f: self.events.append((kind, f)))
        self.start_script = None

    def popen(self, line, *a, **k):
        line = str(line)
        name = "RunMacro" if "RunMacro" in line else "Stop" if "Stop" in line else "RunScript"
        self.cmds.append(name)
        if name == "RunScript" and self.start_script:
            self.start_script()
        if name == "RunMacro" and self.on_macro:
            self.on_macro()

    def flags(self, start=True, end=False):
        if start:
            bridge.flag_path("start").write_text("x")
            (self.dir / "log.txt").write_text("> PING\n")
        if end:
            bridge.flag_path("end").write_text("x")
            (self.dir / "response.txt").write_text("START\nOK 0\nDONE\n")

    def steps(self):
        return [f["step"] for k, f in self.events if k == "altium-release"]


def test_a_script_that_never_starts_gets_one_runmacro_per_release_and_stop_only_at_the_end(monkeypatch, tmp_path):
    env = Release(monkeypatch, tmp_path)
    with pytest.raises(bridge.BridgeError, match=r"^\*\*Altium cannot run scripts right now\*\*"):
        bridge.run_commands([("PING",)], start_timeout=2)
    assert env.cmds == ["RunScript", "RunMacro", "RunScript", "RunMacro", "Stop"]       # two RunMacro in all, Stop last
    assert ("enter", "Error") in env.pressed and all(k != "enter" or t == "Error" for k, t in env.pressed)
    assert env.steps().count("runmacro") == 2 and env.steps()[-1] == "stop"             # every step is in the run log


def test_a_paused_run_of_ours_is_resumed_with_runmacro_and_its_answer_is_used(monkeypatch, tmp_path):
    env = Release(monkeypatch, tmp_path)
    env.start_script = env.flags                              # the script starts, then stops logging (paused at its error)
    env.on_macro = lambda: env.flags(start=False, end=True)   # F9: it runs to its end
    assert bridge.run_commands([("PING",)], stall_timeout=1) == ["> PING"]
    assert env.cmds == ["RunScript", "RunMacro"]              # no Stop: it was resumed, not killed
    runs = [f for k, f in env.events if k == "altium-release" and f["step"] == "runmacro"]
    assert len(runs) == 1 and runs[0]["run_ended"] is True


def test_a_run_that_stays_paused_gets_at_most_two_runmacro_and_then_stop(monkeypatch, tmp_path):
    env = Release(monkeypatch, tmp_path)
    env.start_script = env.flags
    with pytest.raises(bridge.BridgeError, match="stopped in the middle"):
        bridge.run_commands([("PING",)], stall_timeout=1)
    assert env.cmds == ["RunScript", "RunMacro", "RunMacro", "Stop"]


def test_runmacro_is_never_sent_without_evidence_of_a_pause(monkeypatch, tmp_path):
    env = Release(monkeypatch, tmp_path, boxes=())                                     # nothing open: a slow script, not a paused one
    bridge.release_executor(pause_context=True)
    assert env.cmds == ["Stop"]
    env = Release(monkeypatch, tmp_path)                                               # the pre-flight (no pause context): OK pressed only
    bridge.release_executor()
    assert {t for _, t in env.pressed} == {"Error"} and "RunMacro" not in env.cmds          # only the OK-only box is ever pressed


def test_a_box_that_asks_a_question_is_never_pressed_and_blocks_runmacro(monkeypatch, tmp_path):
    env = Release(monkeypatch, tmp_path, boxes=(("TMessageForm", "Error", ["OK"]), ("TMessageForm", "Confirm", ["&Yes", "&No", "Cancel"])))
    bridge.release_executor(pause_context=True)
    assert {t for _, t in env.pressed} == {"Error"} and "RunMacro" not in env.cmds          # only the OK-only box is ever pressed
