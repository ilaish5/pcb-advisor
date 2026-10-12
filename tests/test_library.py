"""Tests for scripts/library.py: model search, package checks, and IntLib build script."""
import pathlib
import subprocess
import sys
import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from library import (  # noqa: E402
    check_package_variant,
    generate_library_build_script,
    model_search_links,
    write_library_build_package,
)


def test_model_search_links():
    """Verify model_search_links produces search URLs for all required services."""
    res = model_search_links("STM32G0B1KET6")
    assert res["mpn"] == "STM32G0B1KET6"
    links = res["links"]
    assert "LCSC" in links
    assert "EasyEDA" in links
    assert "Ultra Librarian" in links
    assert "SnapEDA" in links

    assert "STM32G0B1KET6" in links["LCSC"]
    assert "STM32G0B1KET6" in links["EasyEDA"]
    assert "STM32G0B1KET6" in links["Ultra Librarian"]
    assert "STM32G0B1KET6" in links["SnapEDA"]
    assert "link-and-return" in res["instructions"].lower()


def test_check_package_variant():
    """Verify check_package_variant detects matches, mismatches, and checks datasheet text."""
    # Compatible packages
    ok_res = check_package_variant("LQFP-48", "LQFP-48_7x7mm")
    assert ok_res["match"] is True
    assert ok_res["warning"] is None

    # Obvious mismatch
    mismatch_res = check_package_variant("TSSOP-20", "QFN-20")
    assert mismatch_res["match"] is False
    assert mismatch_res["warning"] is not None
    assert "mismatch" in mismatch_res["warning"].lower()

    # Passive size mismatch
    passive_res = check_package_variant("0603", "0805")
    assert passive_res["match"] is False

    # Datasheet text check
    ds_text = "Available packages: LQFP-48 (7x7mm), UFQFPN-48 (7x7mm)."
    ds_ok = check_package_variant("LQFP-48", "LQFP-48", datasheet_text=ds_text)
    assert ds_ok["match"] is True
    assert ds_ok["datasheet_found"] is True

    ds_miss = check_package_variant("BGA-100", "BGA-100", datasheet_text=ds_text)
    assert ds_miss["datasheet_found"] is False


def test_generate_library_build_script():
    """Verify DelphiScript and README generation for IntLib compilation."""
    script, readme = generate_library_build_script("SensorBoard")
    assert "Procedure BuildIntegratedLibrary" in script
    assert "SensorBoard.IntLib" in script
    assert "SensorBoard.LibPkg" in script

    # Readme contains the 4 steps from AD20 manual Module 29
    assert "AD20 Essentials Module 29" in readme
    assert "Compile Integrated Library" in readme
    assert "Install Library" in readme


def test_write_library_build_package(tmp_path):
    """Verify write_library_build_package creates files in output directory."""
    res = write_library_build_package(tmp_path, "DemoProject")
    script_file = pathlib.Path(res["script"])
    readme_file = pathlib.Path(res["readme"])

    assert script_file.is_file()
    assert readme_file.is_file()
    assert script_file.stat().st_size > 100
    assert readme_file.stat().st_size > 100


def test_library_cli():
    """Verify CLI subcommands for library tools."""
    # Search CLI
    cmd_s = [sys.executable, str(REPO / "scripts" / "library.py"), "search", "NE555P"]
    proc_s = subprocess.run(cmd_s, capture_output=True, text=True)
    assert proc_s.returncode == 0
    assert "SnapEDA" in proc_s.stdout

    # Package check CLI (matching)
    cmd_c1 = [sys.executable, str(REPO / "scripts" / "library.py"), "check-package", "SOIC-8", "SOIC-8"]
    proc_c1 = subprocess.run(cmd_c1, capture_output=True, text=True)
    assert proc_c1.returncode == 0

    # Package check CLI (mismatch exit code 1)
    cmd_c2 = [sys.executable, str(REPO / "scripts" / "library.py"), "check-package", "SOIC-8", "DIP-8"]
    proc_c2 = subprocess.run(cmd_c2, capture_output=True, text=True)
    assert proc_c2.returncode == 1
