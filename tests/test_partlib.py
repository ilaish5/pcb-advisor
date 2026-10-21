"""Tests for scripts/partlib.py (stage L1 of the project library): convert, generate, share, manifest, check."""
import json
import pathlib
import shutil
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import partlib  # noqa: E402
import partlib_convert as conv  # noqa: E402
import partlib_generate as gen  # noqa: E402

FIX = pathlib.Path(__file__).parent / "fixtures" / "partlib"
MM = 1 / 0.0254


def pads(lines):
    return {f[1]: f for f in (ln.split("|") for ln in lines if ln.startswith("PAD|"))}


# ---------------------------------------------------------------- convert

def test_symbol_pins_land_on_the_100_mil_grid_with_body_end_locations():
    syms = {s["name"]: s for s in conv.convert_symbols((FIX / "C200" / "lib.kicad_sym").read_text())}
    s = syms["VendorLdo_C200"]
    assert len(s["pins"]) == 3
    for p in s["pins"]:
        cx, cy = conv.conn(p)
        assert cx % 100 == 0 and cy % 100 == 0, p
    vin = next(p for p in s["pins"] if p["name"] == "VIN")
    assert vin["orient"] == "eRotate180"            # KiCad angle 0 points at the body; Altium points outward
    assert conv.conn(vin)[0] < vin["x"]               # the connection end is outside the body end
    assert vin["type"] == "Power"


def test_footprint_flips_y_keeps_relative_coords_and_widens_silk():
    fp = conv.convert_footprint((FIX / "C100" / "lib.pretty" / "R0603_FAKE.kicad_mod").read_text())
    p = pads(fp["lines"])
    assert float(p["1"][2]) == pytest.approx(-0.8 * MM, abs=0.01)
    assert float(p["1"][3]) == pytest.approx(-0.5 * MM, abs=0.01)          # KiCad y 0.5 (down) -> Altium y -0.5
    assert abs(float(p["1"][2])) < 1000                                     # relative, never +50000 mil
    silk = [ln.split("|") for ln in fp["lines"] if ln.endswith("Top Overlay")]
    assert silk and float(silk[0][5]) >= 5.9                                # 0.1 mm silk widened to >= 0.15 mm
    assert fp["model"]["seat"] == 1 and fp["model"]["rz"] == 90             # KiCad -90 -> Altium 90


def _pads_of(*pads):
    body = "".join(pads)
    return conv.convert_footprint(f'(module X (layer F.Cu){body})')["lines"]


def test_oval_drill_becomes_a_real_slot_and_ringless_thru_hole_is_unplated():
    v = _pads_of('(pad 13 thru_hole oval (at -4.32 -1.80 0.00) (size 1.000 2.100) (layers *.Cu *.Mask)(drill oval 0.6 1.7))')[0].split("|")
    assert v[6] == "1" and v[8] == "2" and float(v[7]) == pytest.approx(0.6 * MM, abs=0.01)
    assert float(v[9]) == pytest.approx(1.7 * MM, abs=0.01) and v[10] == "90"
    h = _pads_of('(pad 1 thru_hole oval (at 0 0) (size 2.1 1.0) (layers *.Cu *.Mask)(drill oval 1.7 0.6))')[0].split("|")
    assert h[8] == "2" and float(h[7]) == pytest.approx(0.6 * MM, abs=0.01) and h[10] == "0"
    r = _pads_of('(pad 2 thru_hole circle (at 0 0) (size 1.6 1.6) (layers *.Cu *.Mask)(drill 0.8))')[0].split("|")
    assert r[6] == "1" and r[8] == "0" and r[9] == "0" and float(r[7]) == pytest.approx(0.8 * MM, abs=0.01)
    m = _pads_of('(pad "" thru_hole circle (at -2.89 -1.30) (size 0.65 0.65) (drill 0.65) (layers *.Cu *.Mask))')[0].split("|")
    assert m[6] == "0" and m[8] == "0"


def test_text_is_cp1252_safe_and_has_no_pipe():
    assert conv.clean("10k\u03a9 1%") == "10kohm 1%"
    s = conv.clean("a|b\u2192c")
    assert "|" not in s and s.encode("cp1252")


# ---------------------------------------------------------------- generate

def test_generated_0603_pitch_and_pad_size():
    fp = gen.footprint_for(gen.package_key("0603 (1608 Metric)"))
    p = pads(fp["lines"])
    assert fp["name"] == "CHIP-0603"
    assert float(p["2"][2]) - float(p["1"][2]) == pytest.approx(1.65 * MM, abs=0.01)
    assert (float(p["1"][11]), float(p["1"][12])) == pytest.approx((0.8 * MM, 0.95 * MM), abs=0.01)
    assert all(float(ln.split("|")[5]) >= 5.9 for ln in fp["lines"] if ln.startswith("TRACK") and ln.endswith("Top Overlay"))


def test_generated_soic8_pitch_rows_and_pin_order():
    fp = gen.footprint_for(gen.package_key("SOIC-8_3.9x4.9mm"))
    p = pads(fp["lines"])
    assert len(p) == 8
    assert float(p["1"][3]) - float(p["2"][3]) == pytest.approx(1.27 * MM, abs=0.01)
    assert float(p["1"][2]) == pytest.approx(-2.7 * MM, abs=0.01) and float(p["5"][2]) == pytest.approx(2.7 * MM, abs=0.01)
    assert float(p["1"][3]) > 0 > float(p["4"][3])                          # pin 1 top left, pin 4 bottom left
    assert float(p["5"][3]) < 0 < float(p["8"][3])                          # pin 5 bottom right, pin 8 top right


def test_unknown_package_is_never_guessed():
    assert gen.package_key("QFN-48") is None
    assert gen.package_key("") is None
    assert gen.package_key("PinHeader 1x4 1.27mm") is None
    assert gen.package_key("Pin header 1x04 2.54mm") == "PinHeader-1x04_P2.54mm"


def test_header_footprint_is_through_hole_with_square_pin_one():
    fp = gen.footprint_for("PinHeader-2x03_P2.54mm")
    p = pads(fp["lines"])
    assert len(p) == 6 and fp["tht"]
    assert p["1"][5] == "Multi-Layer" and p["1"][13] == "2" and p["2"][13] == "1"


def test_two_pin_symbol_shapes_and_grid():
    for prefix in ("R", "C", "L", "D"):
        pins, gfx, _ = gen.two_pin_symbol(prefix, "", [])
        assert len(pins) == 2 and gfx
        for p in pins:
            cx, cy = conv.conn(p)
            assert cx % 100 == 0 and cy % 100 == 0


def test_box_symbol_groups_pins_and_sets_types():
    pins = [{"num": "1", "name": "VCC"}, {"num": "2", "name": "GND"}, {"num": "3", "name": "SDA"},
            {"num": "4", "name": "TX"}]
    out, gfx, _ = gen.box_symbol("U", pins, [])
    by = {p["name"]: p for p in out}
    assert by["VCC"]["orient"] == "eRotate90" and by["GND"]["orient"] == "eRotate270"
    assert by["TX"]["orient"] == "eRotate0" and by["SDA"]["orient"] == "eRotate180"
    assert by["VCC"]["type"] == "Power" and by["TX"]["type"] == "Output" and by["SDA"]["type"] == "IO"
    for p in out:
        cx, cy = conv.conn(p)
        assert cx % 100 == 0 and cy % 100 == 0


# ---------------------------------------------------------------- project

def fake_kicad(calls):
    def fetch(lib, name, dest):
        calls.append(f"{lib}/{name}")
        src = FIX / "kicad" / lib
        if not (src / f"{name}.kicad_mod").exists():
            return False, "HTTPError: 404"
        dest.mkdir(parents=True, exist_ok=True)
        for f in src.glob(name + ".*"):
            shutil.copy(f, dest / f.name)
        return True, "downloaded"
    return fetch


def prep(proj, **kw):
    """prepare() with the network off: KiCad's library unreachable unless the test passes a kicad_fetcher."""
    kw.setdefault("kicad_fetcher", lambda lib, name, dest: (False, "offline"))
    kw.setdefault("fetcher", fake_fetch([]))
    return partlib.prepare(proj, **kw)


def line(key, **kw):
    return {"ts": "2026-10-21T10:00:00", "by": "test", "line": key,
            "changes": {"refs": [key], "package": "", "mpn": "", "manufacturer": "ACME", **kw}}


@pytest.fixture
def proj(home):
    import project
    name = project.create("plib", title="Part library")
    d = home / "projects" / name
    rows = [line("R1", value="10k", mpn="0603WAF1002T5E", package="0603", description="10k 1% 0603"),
            line("R3", value="10k", mpn="0603WAF1002T5E", package="0603", description="10k 1% 0603"),
            line("R2", value="4.7k", mpn="RC0603-4K7", package="0603"),
            line("C11", value="100n", mpn="CC0603-100N", package="C0603"),
            line("U1", value="LDO33", mpn="LDO33", code="C200", package="SOT-23-3"),
            line("J1", value="USB-C", mpn="USBC-6P", lcsc="C300", package="SMD"),
            line("X1", value="Odd", mpn="ODD-1", lcsc="C400", package="XYZ"),
            line("U2", value="Flash", mpn="W25Q-SOIC", package="SOIC-8"),
            line("U3", value="Radio", mpn="RF-QFN", lcsc="C999", package="QFN-48"),
            line("Q1", value="NMOS", mpn="2N7002", package="SOT-23-3"),
            line("D1", value="BAT54", mpn="BAT54", package="SOD-123")]
    (d / "bom-log.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    P = lambda n, num, net: {"name": n, "num": num, "net": net}
    sheet = {"id": "01", "title": "Main", "parts": [
        {"ref": "U2", "kind": "ic", "pins": [P("CS", "1", "CS"), P("DO", "2", "DO"), P("GND", "4", "GND"), P("DI", "5", "DI"),
                                             P("CLK", "6", "CLK"), P("VCC", "8", "+3V3")]},
        {"ref": "Q1", "kind": "q", "pins": [P("G", "1", "G"), P("S", "2", "GND"), P("D", "3", "D")]}]}
    sup = {"line": "R1", "mpn": "0603WAF1002T5E", "supplier": "LCSC", "stock": 10, "unit_price": 0.01, "code": "C100",
           "exact": True}
    (d / "supply-log.jsonl").write_text(json.dumps(sup) + "\n", encoding="utf-8")
    (d / "netlist").mkdir(exist_ok=True)
    (d / "netlist" / "01.json").write_text(json.dumps(sheet), encoding="utf-8")
    return name


def fake_fetch(calls):
    def fetch(cid, dest):
        calls.append(cid)
        src = FIX / cid
        if not src.exists():
            return False, "EasyEDA answered: part not found"
        shutil.copytree(src, dest, dirs_exist_ok=True)
        return True, "downloaded"
    return fetch


def test_prepare_manifest_sharing_and_missing(proj, home):
    calls = []
    m = prep(proj, fetcher=fake_fetch(calls))
    assert calls == ["C100", "C200", "C300", "C400", "C999"]
    assert m["R1"]["source"] == "easyeda" and m["R1"]["status"] == "ok"
    assert m["R1"]["symbol"] == "0603WAF1002T5E"                         # renamed from the EasyEDA name to the MPN
    assert m["R1"]["lcsc"] == "C100" and m["U1"]["lcsc"] == "C200"      # from the stock check / the line's `code`
    assert m["R1"]["footprint"] == "R0603_FAKE"                           # no easyeda2kicad nickname
    assert {k: m["R3"][k] for k in ("symbol", "footprint", "step")} == {k: m["R1"][k] for k in ("symbol", "footprint", "step")}
    assert m["R1"]["step"].endswith("R0603_FAKE.step") and (home / "projects" / proj / "library" / m["R1"]["step"]).exists()
    assert m["R2"]["source"] == "generated" and m["R2"]["footprint"] == "CHIP-0603"
    assert m["C11"]["footprint"] == m["R2"]["footprint"]                    # same package, one footprint
    assert m["U3"]["status"] == "missing" and m["U3"]["symbol"] == "" and m["U3"]["source"] == "missing"
    assert any("C999" in i for i in m["U3"]["issues"]) and any("QFN-48" in i for i in m["U3"]["issues"])
    assert m["U2"]["source"] == "generated" and m["U2"]["footprint"] == "SOIC-8"
    assert m["Q1"]["footprint"] == "SOT-23-3" and m["U1"]["footprint"] == "LDO_FAKE"
    assert m["J1"]["source"] == "easyeda" and not any("slot hole" in i for i in m["J1"]["issues"])   # oval drill is a real slot
    assert m["X1"]["status"] == "missing"
    assert "float" not in m["X1"]["issues"][0] and "Error" not in m["X1"]["issues"][0]
    assert m["X1"]["issues"][0].endswith("vendor zip (a log-in site) in Sources")
    assert m["D1"]["status"] == "warn" and any("cathode" in i for i in m["D1"]["issues"])
    assert json.loads((home / "projects" / proj / "library" / "manifest.json").read_text()) == m


def test_build_specs_and_part_fixes(proj, home):
    prep(proj, fetcher=fake_fetch([]))
    b = home / "projects" / proj / "library" / "build"
    sy = (b / "symbols_spec.txt").read_text(encoding="cp1252")
    fp = (b / "footprints_spec.txt").read_text(encoding="cp1252")
    assert sy.startswith("LIBRARY|<SCHLIB>") and fp.startswith("FPLIB|<PCBLIB>")
    assert fp.count("FOOTPRINT|CHIP-0603|") == 1                           # shared, written once
    assert sy.count("SYMBOL|0603WAF1002T5E|") == 1 and "0603WAF1002T5E_2" not in sy     # same MPN, one part
    assert "LDO33" in sy and "VendorLdo_C200" not in sy
    parts = json.loads((b / "parts.json").read_text())
    r1 = parts["symbols"]["0603WAF1002T5E"]
    assert r1["hide_pin_names"] is True and r1["prefix"] == "R" and r1["comment"] == "10k"
    assert r1["params"]["LCSC"] == "C100" and "LCSC C100" in r1["params"]["Description"]
    assert r1["params"]["Manufacturer"] == "ACME"
    assert parts["symbols"]["LDO33"]["comment"] == "LDO33" and parts["symbols"]["LDO33"]["hide_pin_names"] is False
    # passives' pins are Passive (the EasyEDA resistor came with Input pins), power pins Power
    r1_pins = [ln for ln in sy.splitlines() if ln.startswith("PIN|") and ln.split("|")[2] in ("1", "2")][:2]
    assert all("eElectricPassive" in ln for ln in r1_pins)
    assert "|GND|eElectricPower|" in sy and "|VIN|eElectricPower|" in sy
    assert (b / "links.txt").read_text().splitlines()[0] == "0603WAF1002T5E=R0603_FAKE"
    assert (b / "props.txt").read_text().splitlines()[0] == "0603WAF1002T5E=R|10k"


def test_spec_pins_snap_and_check_is_clean(proj, home):
    prep(proj, fetcher=fake_fetch([]))
    b = home / "projects" / proj / "library" / "build"
    problems = [p for p in partlib.check_build(b) if p["level"] == "problem"]
    assert problems == []
    warnings = {p["footprint"] for p in partlib.check_build(b) if p["level"] == "warning"}
    assert "CHIP-0603" in warnings                                         # generated: no 3D is only a warning
    for ln in (b / "symbols_spec.txt").read_text().splitlines():
        if ln.startswith("PIN|"):
            f = ln.split("|")
            x, y, ln_ = float(f[5]), float(f[6]), float(f[8])
            dx, dy = {"eRotate0": (1, 0), "eRotate180": (-1, 0), "eRotate90": (0, 1), "eRotate270": (0, -1)}[f[4]]
            assert (x + dx * ln_) % 100 == 0 and (y + dy * ln_) % 100 == 0, ln


def test_official_kicad_footprints_are_the_source_for_standard_packages(proj, home):
    calls = []
    m = prep(proj, kicad_fetcher=fake_kicad(calls))
    assert "Resistor_SMD/R_0603_1608Metric" in calls and "Capacitor_SMD/C_0603_1608Metric" in calls
    assert m["R2"]["source"] == "kicad" and m["R2"]["footprint"] == "R_0603_1608Metric"
    assert m["C11"]["footprint"] == "C_0603_1608Metric"
    assert m["R2"]["step"] == "kicad/Resistor_SMD/R_0603_1608Metric.step"
    assert m["R2"]["status"] == "ok" and m["R2"]["issues"] == []
    assert m["U2"]["source"] == "kicad" and m["U2"]["footprint"] == "SOIC-8_3.9x4.9mm_P1.27mm"
    # SOT-23 and SOD-123 are not in the fake KiCad library: the built-in footprint, said plainly
    assert m["Q1"]["source"] == "generated" and any("offline fallback" in i for i in m["Q1"]["issues"])
    b = home / "projects" / proj / "library" / "build"
    fp = (b / "footprints_spec.txt").read_text(encoding="cp1252")
    p = pads(fp.split("FOOTPRINT|R_0603_1608Metric|")[1].split("FOOTPRINT|")[0].splitlines())
    assert set(p) == {"1", "2"}                                            # the paste-only pad is dropped
    assert float(p["1"][2]) == pytest.approx(-0.825 * MM, abs=0.01) and p["1"][13] == "9"
    assert "R_0603_1608Metric|KiCad Resistor_SMD" in fp
    parts = json.loads((b / "parts.json").read_text())
    assert parts["footprints"]["R_0603_1608Metric"]["model"]["seat"] == 1
    assert [p for p in partlib.check_build(b) if p["level"] == "problem"] == []


def test_kicad_library_is_cached_and_not_asked_again(proj):
    calls = []
    prep(proj, kicad_fetcher=fake_kicad(calls))
    n = len(calls)
    prep(proj, kicad_fetcher=fake_kicad(calls))
    assert len(calls) == n + 2                                              # only the ones that were not there (404s)


def test_kicad_fetch_downloads_footprint_and_step(tmp_path, monkeypatch):
    import partlib_kicad as pk
    urls = []

    def get(url, timeout=60):
        urls.append(url)
        if url.endswith(".step") and "Bad" in url:
            raise OSError("404")
        return b"data"
    monkeypatch.setattr(pk, "_get", get)
    ok, _ = pk.fetch_kicad("Resistor_SMD", "R_0603_1608Metric", tmp_path)
    assert ok and (tmp_path / "R_0603_1608Metric.kicad_mod").exists() and (tmp_path / "R_0603_1608Metric.step").exists()
    assert "kicad-footprints" in urls[0] and "kicad-packages3D" in urls[1]
    ok, _ = pk.fetch_kicad("Resistor_SMD", "Bad_Name", tmp_path)            # a missing STEP is no failure
    assert ok and not (tmp_path / "Bad_Name.step").exists()
    assert not pk.fetch_kicad("../x", "y", tmp_path)[0]
    assert pk.kicad_footprint("0603", "LED") == ("LED_SMD", "LED_0603_1608Metric")
    assert pk.kicad_footprint("SOT-23-3", "Q") == ("Package_TO_SOT_SMD", "SOT-23")


def test_lcsc_code_order():
    f = partlib.lcsc_code
    assert f({"lcsc": "C11", "code": "C22"}, {"LCSC": {"code": "C33", "exact": True}}) == "C11"
    assert f({"code": "C22"}, {"LCSC": {"code": "C33", "exact": True}}) == "C22"
    assert f({}, {"LCSC": {"code": "C33", "exact": True}}) == "C33"
    assert f({}, {"LCSC": {"code": "C33"}}) == "" and f({"lcsc": "junk"}, None) == ""


def test_check_finds_the_spec_level_problems(tmp_path):
    (tmp_path / "symbols_spec.txt").write_text("LIBRARY|x\nSYMBOL|A||1\nSYMBOL|B||1\nSYMBOL|C||1\nSYMBOL|D||1\n")
    (tmp_path / "footprints_spec.txt").write_text("FPLIB|x\nFOOTPRINT|F1|d\nFOOTPRINT|F1|d\nFOOTPRINT|F2|d\n")
    (tmp_path / "links.txt").write_text("B=Nope\nC=C:\\libs\\x.PcbLib\nD=F2\n")
    (tmp_path / "parts.json").write_text(json.dumps({"footprints": {
        "F1": {"source": "easyeda", "steps": ["a.step", "b.step"]}, "F2": {"source": "generated", "steps": []}}}))
    msgs = [p["message"] for p in partlib.check_build(tmp_path)]
    joined = "\n".join(msgs)
    assert "symbol A has no footprint" in joined
    assert "links to missing footprint Nope" in joined
    assert "file path" in joined
    assert "F1 defined more than once" in joined
    assert "2 3D models" in joined
    levels = {p["footprint"]: p["level"] for p in partlib.check_build(tmp_path) if p["kind"] == "3d"}
    assert levels["F2"] == "warning" and levels["F1"] == "problem"


def test_failed_fetch_falls_back_to_generated_and_is_reported(proj):
    m = prep(proj, fetcher=lambda cid, dest: (False, "blocked"))
    assert m["R1"]["source"] == "generated" and m["R1"]["status"] == "warn"      # 0603 is known
    assert any("C100" in i and "blocked" in i for i in m["R1"]["issues"])
    assert m["U1"]["status"] == "missing"                                       # an IC with no known pins: not invented
    assert any("pin list" in i for i in m["U1"]["issues"])


def test_no_fetch_does_not_call_the_fetcher(proj):
    def boom(cid, dest):
        raise AssertionError("fetched")
    m = prep(proj, fetch=False, fetcher=boom)
    assert m["R1"]["source"] == "generated"


def test_downloaded_part_is_not_fetched_twice(proj):
    calls = []
    prep(proj, fetcher=fake_fetch(calls))
    prep(proj, fetcher=fake_fetch(calls))
    assert calls.count("C100") == 1 and calls.count("C999") == 2             # a failure is asked again, never worked around


def test_fetch_one_runs_easyeda2kicad_isolated(tmp_path, monkeypatch):
    seen = {}

    def run(cmd, **kw):
        seen["cmd"] = cmd
        (tmp_path / "lib.kicad_sym").write_text("x")
        return subprocess.CompletedProcess(cmd, 0, "Created Kicad symbol", "")
    monkeypatch.setattr(partlib.subprocess, "run", run)
    ok, _ = partlib.fetch_one("C7955", tmp_path)
    assert ok
    assert seen["cmd"][1:4] == ["-I", "-m", "easyeda2kicad"] and "--lcsc_id=C7955" in seen["cmd"] and "--overwrite" in seen["cmd"]
    ok, msg = partlib.fetch_one("--evil", tmp_path)
    assert not ok and "C-number" in msg
    monkeypatch.setattr(partlib.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "HTTP 403"))
    (tmp_path / "lib.kicad_sym").unlink()
    ok, msg = partlib.fetch_one("C7955", tmp_path)
    assert not ok and "403" in msg


def test_cli_status_and_usage(proj, capsys):
    assert partlib.main(["status", proj]) == 0
    assert "prepare" in capsys.readouterr().out                              # no manifest yet
    prep(proj, fetcher=fake_fetch([]))
    assert partlib.main(["status", proj]) == 0
    out = capsys.readouterr().out
    assert "R1" in out and "easyeda" in out and "missing" in out
    assert partlib.main(["status", "no-such-project"]) == 1
    assert partlib.main([]) == 1
