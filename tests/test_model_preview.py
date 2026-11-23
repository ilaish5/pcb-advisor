"""
The Library quick preview: what the generic parser reads from a part's own files, and what the server refuses.

The fixtures under tests/fixtures/preview/library are real Blinker-555 files (a KiCad symbol and footprint from EasyEDA,
a KiCad-library footprint, build-spec lines) with small stand-ins for the 3D files. The manifest also carries two
hostile entries whose paths try to leave library/; they must never produce a file.
"""
import json
import pathlib
import shutil
import urllib.error
import urllib.request

import pytest

import model_preview as mp
import store
from test_server import server, get   # noqa: F401  (the real handler on an ephemeral port, and its GET helper)

FIX = pathlib.Path(__file__).resolve().parent / "fixtures" / "preview"
LIB = FIX / "library"
MAN = json.loads((LIB / "manifest.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- symbols

def test_a_kicad_symbol_is_read_with_its_pins():
    d = mp.preview(LIB, MAN, "U1", "symbol")
    assert d["source"] == "kicad_sym"
    assert len(d["pins"]) == 8
    assert {p["num"] for p in d["pins"]} == {str(n) for n in range(1, 9)}
    assert d["gfx"] and d["bounds"]


def test_a_symbol_without_a_kicad_file_is_drawn_from_the_build_spec():
    d = mp.preview(LIB, MAN, "R1", "symbol")
    assert d["source"] == "build spec"
    assert len(d["pins"]) == 2


# ---------------------------------------------------------------- footprints

def test_a_footprint_has_pads_pin_one_pitch_and_courtyard():
    d = mp.preview(LIB, MAN, "U1", "footprint")
    assert d["source"] == "kicad_mod"
    assert len(d["pads"]) == 8
    assert d["pin1"] == "1"
    assert d["pitch"] == 1.27
    assert d["courtyard"]
    assert not d["name"].startswith(("easyeda:", "lib:"))


def test_a_two_pad_footprint_from_the_kicad_library():
    d = mp.preview(LIB, MAN, "R1", "footprint")
    assert len(d["pads"]) == 2


def test_a_generated_footprint_comes_from_the_build_spec():
    d = mp.preview(LIB, MAN, "D1", "footprint")
    assert d["source"] == "build spec"
    assert d["pads"]


# ---------------------------------------------------------------- 3D

def test_model_info_says_which_files_exist():
    assert mp.preview(LIB, MAN, "U1", "model")["wrl"] is True
    assert mp.preview(LIB, MAN, "U1", "model")["step"] is True
    r = mp.preview(LIB, MAN, "R1", "model")
    assert r["step"] is True and r["wrl"] is False
    d = mp.preview(LIB, MAN, "D1", "model")
    assert d["step"] is False and d["wrl"] is False


def test_model_bytes_come_with_a_type_and_a_name():
    data, ctype, name = mp.model_file(LIB, MAN["U1"], "wrl")
    assert data and ctype == "model/vrml" and name.endswith(".wrl")
    data, ctype, name = mp.model_file(LIB, MAN["R1"], "step")
    assert data and ctype == "model/step"


def test_a_missing_model_or_an_unknown_format_is_an_error():
    with pytest.raises(mp.PreviewError) as e:
        mp.model_file(LIB, MAN["D1"], "step")
    assert e.value.code == 404
    with pytest.raises(mp.PreviewError) as e:
        mp.model_file(LIB, MAN["U1"], "exe")
    assert e.value.code == 400


def test_an_unknown_line_or_kind_is_refused():
    with pytest.raises(mp.PreviewError):
        mp.preview(LIB, MAN, "NOPE", "symbol")
    with pytest.raises(mp.PreviewError) as e:
        mp.preview(LIB, MAN, "U1", "gerber")
    assert e.value.code == 400
    with pytest.raises(mp.PreviewError):
        mp.preview(LIB, MAN, ["U1"], "symbol")          # a non-string key is not a line


# ---------------------------------------------------------------- paths never leave library/

@pytest.mark.parametrize("rel", ["../project.json", r"..\project.json","easyeda/../../secret.step", "/etc/passwd",
                                 "C:/Windows/win.ini", "", None, 7, "a\0b"])
def test_manifest_path_refuses_anything_outside_the_library(rel):
    assert mp.manifest_path(LIB, rel) is None


def test_a_manifest_step_that_climbs_out_gives_no_file():
    for key in ("EVIL", "EVIL2"):
        f = mp.part_files(LIB, MAN[key])
        assert f["step"] is None and f["wrl"] is None
        for fmt in ("step", "wrl"):
            with pytest.raises(mp.PreviewError):
                mp.model_file(LIB, MAN[key], fmt)


def test_a_symlink_out_of_the_library_is_not_followed(tmp_path):
    lib = tmp_path / "library"
    (lib / "easyeda" / "C1").mkdir(parents=True)
    outside = tmp_path / "secret.step"
    outside.write_text("secret")
    link = lib / "easyeda" / "C1" / "x.step"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not allowed here")
    assert mp.manifest_path(lib, "easyeda/C1/x.step") is None


# ---------------------------------------------------------------- over HTTP

@pytest.fixture
def lib_project(server, empty):   # noqa: F811
    dst = store.pdir(empty) / "library"
    shutil.copytree(LIB, dst, dirs_exist_ok=True)
    return empty


def raw(base, path, project, headers=None):
    req = urllib.request.Request(f"{base}{path}&project={project}", headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


def test_the_preview_endpoint_serves_a_line(server, lib_project):
    st, body = get(server, "/api/library/preview?line=U1&kind=footprint", lib_project)
    assert st == 200 and len(body["pads"]) == 8


def test_the_model_endpoint_serves_the_file(server, lib_project):
    st, data, h = raw(server, "/api/library/model?line=U1&format=wrl", lib_project)
    assert st == 200 and data and "vrml" in h["Content-Type"]


def test_the_endpoints_refuse_what_the_manifest_does_not_back(server, lib_project):
    assert get(server, "/api/library/preview?line=NOPE&kind=symbol", lib_project)[0] == 404
    assert get(server, "/api/library/preview?line=U1&kind=gerber", lib_project)[0] == 400
    for key in ("EVIL", "EVIL2"):
        for fmt in ("step", "wrl"):
            st, data, _ = raw(server, f"/api/library/model?line={key}&format={fmt}", lib_project)
            assert st == 404 and b"secret" not in data
    assert get(server, "/api/library/preview?line=U1&kind=symbol", "no-such-project")[0] == 404


def test_the_host_guard_covers_the_preview(server, lib_project):
    st, _, _ = raw(server, "/api/library/preview?line=U1&kind=symbol", lib_project, headers={"Host": "evil.com"})
    assert st == 403
