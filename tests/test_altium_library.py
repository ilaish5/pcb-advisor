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


def test_a_build_fills_the_specs_sends_the_steps_in_order_and_marks_every_line(lib, monkeypatch):
    stub = Stub(monkeypatch)
    res = bridge.build_library(lib)
    lp = bridge.library_paths(lib)
    assert res["installed"] and res["intlib_fresh"] and res["prepared"] is False
    assert res["counts"] == {"symbols": 2, "footprints": 2, "pads": 5, "bodies": 1, "models": 1}
    names = stub.names()
    assert names[0] == "LIBCLOSE"                           # nothing of the old library stays open or installed
    assert names[-2:] == ["COMPILE", "CHECKINST"]
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
    monkeypatch.setattr(bridge.subprocess, "Popen", lambda *a, **k: (tmp_path / "start.flag").write_text("x"))
    reads, ticks = [], []

    def sleep(s):
        ticks.append(s)
        (tmp_path / "log.txt").write_text("> PING\n" * len(ticks))     # the script is writing its log
        if len(ticks) == 3:
            (tmp_path / "response.txt").write_text("START\nOK 0\nDONE\n")
            (tmp_path / "end.flag").write_text("x")
    real_read = bridge._read

    def read(path):
        reads.append((pathlib.Path(path).name, (tmp_path / "end.flag").exists()))
        return real_read(path)
    monkeypatch.setattr(bridge.time, "sleep", sleep)
    monkeypatch.setattr(bridge, "_read", read)
    assert bridge.run_commands([("PING",)]) == ["> PING"] * 3
    assert reads and all(done for _, done in reads)


def test_a_script_that_stops_logging_is_released_and_its_dialogs_are_reported(monkeypatch, tmp_path):
    monkeypatch.setattr(bridge, "EXCHANGE", tmp_path)
    monkeypatch.setattr(bridge, "_exe", lambda: "x2.exe")
    monkeypatch.setattr(bridge, "_running", lambda: True)
    monkeypatch.setattr(bridge.subprocess, "Popen", lambda *a, **k: (tmp_path / "start.flag").write_text("x"))
    monkeypatch.setattr(bridge.time, "sleep", lambda s: None)
    monkeypatch.setattr(bridge, "release_executor", lambda: ["[TMessageForm] Error: Cannot create file"])
    with pytest.raises(bridge.BridgeError, match="stopped in the middle.*Cannot create file"):
        bridge.run_commands([("PING",)], stall_timeout=-1)


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
