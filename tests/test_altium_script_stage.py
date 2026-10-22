"""The bridge runs a content-addressed copy of the Altium script, so a changed script is a new project path."""
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
from altium import bridge  # noqa: E402


def _src(tmp_path, pas="x"):
    src = tmp_path / "src dir"          # a space in the path on purpose
    src.mkdir(exist_ok=True)
    (src / "AdvisorBridge.PrjScr").write_text("[Design]\n", encoding="ascii")
    (src / "AdvisorBridge.pas").write_text(pas, encoding="ascii")
    return src


def test_same_content_same_path(tmp_path):
    src, root = _src(tmp_path), tmp_path / "stage root"
    a = bridge.stage_script(src, root)
    b = bridge.stage_script(src, root)
    assert a == b and a.is_file() and (a.parent / "AdvisorBridge.pas").read_text() == "x"
    assert a.parent.parent == root and " " in str(a)


def test_changed_pas_new_path(tmp_path):
    src, root = _src(tmp_path), tmp_path / "stage"
    a = bridge.stage_script(src, root)
    _src(tmp_path, "y")
    b = bridge.stage_script(src, root)
    assert a != b and (b.parent / "AdvisorBridge.pas").read_text() == "y"
    assert (a.parent / "AdvisorBridge.pas").read_text() == "x"      # the one Altium has open is not touched


def test_cleanup_keeps_last_two(tmp_path):
    src, root = _src(tmp_path, "0"), tmp_path / "stage"
    made = []
    for i in range(4):
        _src(tmp_path, str(i))
        made.append(bridge.stage_script(src, root).parent)
        os.utime(made[-1], (time.time() + i, time.time() + i))
    left = sorted(d.name for d in root.iterdir())
    assert left == sorted(d.name for d in made[-2:])


def test_missing_script_is_a_bridge_error(tmp_path):
    try:
        bridge.stage_script(tmp_path, tmp_path / "stage")
    except bridge.BridgeError:
        return
    raise AssertionError("expected BridgeError")
