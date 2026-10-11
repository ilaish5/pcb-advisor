"""Tests for scripts/altium/registry.py with fake and error registries."""
import builtins
import pathlib
import sys

import pytest

from altium import registry


class FakeKey:
    def __init__(self, path, subkeys=None, values=None):
        self.path = path
        self.subkeys = list(subkeys or [])
        self.values = list(values or [])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class FakeRegistry:
    HKEY_LOCAL_MACHINE = 1
    HKEY_CURRENT_USER = 2
    KEY_READ = 131097

    def __init__(self, tree=None):
        self.tree = tree or {}

    def _norm(self, root, path):
        return (root, path.lower().replace("/", "\\").rstrip("\\"))

    def OpenKey(self, root, path, reserved=0, access=0):
        key = self._norm(root, path)
        if key in self.tree:
            return self.tree[key]
        raise OSError(f"Registry key not found: {root}, {path}")

    def EnumKey(self, key, index):
        if 0 <= index < len(key.subkeys):
            return key.subkeys[index]
        raise OSError("No more subkeys")

    def EnumValue(self, key, index):
        if 0 <= index < len(key.values):
            return key.values[index]
        raise OSError("No more values")

    def QueryValueEx(self, key, name):
        for vname, val, vtype in key.values:
            if vname.lower() == name.lower():
                return val, vtype
        raise OSError(f"Value not found: {name}")

    def CloseKey(self, key):
        pass


class ErrorRegistry:
    HKEY_LOCAL_MACHINE = 1
    HKEY_CURRENT_USER = 2
    KEY_READ = 1

    def OpenKey(self, *args, **kwargs):
        raise OSError("Simulated permission denied")


def test_find_installs_orders_by_version_and_detects_exe(tmp_path):
    dir_old = tmp_path / "AD21"
    dir_old.mkdir()

    dir_new = tmp_path / "AD25"
    dir_new.mkdir()
    exe_file = dir_new / "X2.EXE"
    exe_file.touch()

    tree = {
        (FakeRegistry.HKEY_LOCAL_MACHINE, "software\\altium\\builds"): FakeKey(
            "software\\altium\\builds",
            subkeys=["Build_21", "Build_25"],
        ),
        (FakeRegistry.HKEY_LOCAL_MACHINE, "software\\altium\\builds\\build_21"): FakeKey(
            "software\\altium\\builds\\build_21",
            values=[
                ("Version", "21.9.2", 1),
                ("ProgramsInstallPath", str(dir_old), 1),
            ],
        ),
        (FakeRegistry.HKEY_LOCAL_MACHINE, "software\\altium\\builds\\build_25"): FakeKey(
            "software\\altium\\builds\\build_25",
            values=[
                ("Version", "25.1.0", 1),
                ("ProgramsInstallPath", str(dir_new), 1),
            ],
        ),
    }
    fake_reg = FakeRegistry(tree)
    installs = registry.find_installs(reg=fake_reg)

    assert len(installs) == 2
    # Newest version first (25.1.0 before 21.9.2)
    first, second = installs[0], installs[1]
    assert first["version"] == "25.1.0"
    assert first["build"] == "Build_25"
    assert first["path"] == str(dir_new)
    assert first["exe"] == str(exe_file)

    assert second["version"] == "21.9.2"
    assert second["build"] == "Build_21"
    assert second["path"] == str(dir_old)
    assert second["exe"] == ""


def test_recent_projects_filters_dedupes_and_checks_exists(tmp_path):
    existing_prj = tmp_path / "board.PrjPcb"
    existing_prj.touch()
    sch_file = tmp_path / "sheet.SchDoc"
    sch_file.touch()
    missing_prj = tmp_path / "missing.PrjPcb"

    tree = {
        (FakeRegistry.HKEY_CURRENT_USER, "software\\altium"): FakeKey(
            "software\\altium",
            subkeys=["Build_25"],
        ),
        (FakeRegistry.HKEY_CURRENT_USER, "software\\altium\\build_25\\designexplorer\\recent documents"): FakeKey(
            "recent documents",
            values=[
                ("RecentDocument1", str(existing_prj), 1),
                ("RecentDocument2", str(sch_file), 1),       # should be filtered out
                ("RecentDocument3", str(existing_prj), 1),   # duplicate, should be deduped
                ("RecentDocument4", str(missing_prj), 1),    # missing file, exists=False
                ("RecentDocumentCount", 4, 4),               # non-document value
            ],
        ),
    }
    fake_reg = FakeRegistry(tree)
    recent = registry.recent_projects(reg=fake_reg)

    assert len(recent) == 2
    first, second = recent[0], recent[1]
    assert first["path"] == str(existing_prj)
    assert first["name"] == "board"
    assert first["exists"] is True
    assert first["build"] == "Build_25"

    assert second["path"] == str(missing_prj)
    assert second["name"] == "missing"
    assert second["exists"] is False
    assert second["build"] == "Build_25"


def test_error_registry_returns_empty_lists():
    err_reg = ErrorRegistry()
    assert registry.find_installs(reg=err_reg) == []
    assert registry.recent_projects(reg=err_reg) == []


def test_reg_none_without_winreg(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "winreg":
            raise ImportError("No module named 'winreg'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setitem(sys.modules, "winreg", None)

    assert registry.find_installs(reg=None) == []
    assert registry.recent_projects(reg=None) == []
