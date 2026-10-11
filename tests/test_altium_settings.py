"""Tests for Altium settings, endpoints, config, and engine access."""
import json
import pathlib
import shutil
import threading
import urllib.error
import urllib.request

import pytest

import agent
import project
import workspace


@pytest.fixture
def server(home, monkeypatch):
    """The real handler on an ephemeral port, in this process."""
    from http.server import ThreadingHTTPServer
    from altium import registry
    import serve

    monkeypatch.setattr(serve, "QUIET", True)
    monkeypatch.setattr(serve, "recheck_async", lambda p, k: None)

    monkeypatch.setattr(registry, "find_installs", lambda reg=None: [
        {"build": "AD26", "version": "26.0.0", "path": "C:\\Program Files\\Altium\\AD26", "exe": "C:\\Program Files\\Altium\\AD26\\X2.EXE"}
    ])
    monkeypatch.setattr(registry, "recent_projects", lambda reg=None, limit=20: [
        {"path": "C:\\Projects\\Demo.PrjPcb", "name": "Demo", "exists": False, "build": "AD26"}
    ])

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def post(base, path, body, proj):
    req = urllib.request.Request(
        f"{base}{path}{chr(38) if chr(63) in path else chr(63)}project={proj}", method="POST",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def get(base, path, proj, raw=False):
    try:
        with urllib.request.urlopen(f"{base}{path}{'&' if '?' in path else '?'}project={proj}", timeout=10) as r:
            body = r.read()
            return r.status, (body if raw else json.loads(body))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_get_altium_no_link(server, lte):
    status, body = get(server, "/api/altium", lte)
    assert status == 200
    assert body["linked"] is None
    assert len(body["installs"]) == 1
    assert body["installs"][0]["version"] == "26.0.0"
    assert len(body["recent"]) == 1
    assert body["active_install"]["version"] == "26.0.0"
    assert body["install_path"] == ""


def test_link_by_file_and_unlink(server, lte):
    fixture_path = str(pathlib.Path("tests/fixtures/altium/project/WCTopping.PrjPcb").resolve())
    status, body = post(server, "/api/altium/link", {"path": fixture_path}, lte)
    assert status == 200

    linked = body["linked"]
    assert linked is not None
    assert linked["project_file"] == fixture_path
    assert linked["exists"] is True
    assert linked["summary"]["name"] == "WCTopping"
    assert len(linked["sheets"]) == 5
    assert len(linked["summary"]["sheets"]) == 5
    assert linked["outputs_dir"].endswith("Outputs")

    # Stored in project.json
    meta = project.load_meta(lte)
    assert meta["altium"]["project_file"] == fixture_path
    assert meta["altium"]["outputs_dir"] == linked["outputs_dir"]

    link_data = project.altium_link(lte)
    assert link_data["project_file"] == fixture_path

    # Unlink
    status, unlinked_body = post(server, "/api/altium/unlink", {}, lte)
    assert status == 200
    assert unlinked_body["linked"] is None
    assert project.altium_link(lte)["project_file"] == ""


def test_link_by_folder(server, lte):
    folder_path = str(pathlib.Path("tests/fixtures/altium/project").resolve())
    expected_file = str(pathlib.Path("tests/fixtures/altium/project/WCTopping.PrjPcb").resolve())

    status, body = post(server, "/api/altium/link", {"path": folder_path}, lte)
    assert status == 200
    assert body["linked"]["project_file"] == expected_file
    assert len(body["linked"]["sheets"]) == 5


def test_link_refusals(server, lte, tmp_path):
    # Folder with no PrjPcb -> 400
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()
    status, body = post(server, "/api/altium/link", {"path": str(empty_dir)}, lte)
    assert status == 400
    assert "error" in body

    # Folder with multiple PrjPcb -> 400 (copy fixtures to tmp_path, never touch fixtures)
    multi_dir = tmp_path / "multi"
    shutil.copytree("tests/fixtures/altium/project", multi_dir)
    (multi_dir / "Extra.PrjPcb").write_text("[Design]\n", encoding="latin-1")
    status, body = post(server, "/api/altium/link", {"path": str(multi_dir)}, lte)
    assert status == 400
    assert "several projects" in body["error"].lower()

    # A .SchDoc file -> 400
    sch_path = str(pathlib.Path("tests/fixtures/altium/project/Power Supply.SchDoc").resolve())
    status, body = post(server, "/api/altium/link", {"path": sch_path}, lte)
    assert status == 400
    assert "not a .prjpcb" in body["error"].lower()

    # Missing path -> 400
    status, body = post(server, "/api/altium/link", {"path": str(tmp_path / "nonexistent.PrjPcb")}, lte)
    assert status == 400
    assert "not found" in body["error"].lower()


def test_altium_install_path_settable_via_config(server, lte):
    custom_path = "C:\\Custom\\Altium_AD26"
    status, body = post(server, "/api/config", {"set": {"altium.install_path": custom_path}}, lte)
    assert status == 200

    cfg = body["config"]
    assert cfg["altium"]["install_path"] == custom_path
    assert workspace.get("altium.install_path") == custom_path

    status, alt_body = get(server, "/api/altium", lte)
    assert status == 200
    assert alt_body["install_path"] == custom_path
    assert alt_body["active_install"]["path"] == custom_path


def test_engine_access_add_dirs_and_workspace_describe(lte):
    # Nothing linked
    dirs_before = agent._add_dirs(lte)
    desc_before = workspace.describe(lte)
    places_before = desc_before["places"]
    assert not any("student's Altium project" in p["what"] for p in places_before)

    # Link project
    fixture_path = str(pathlib.Path("tests/fixtures/altium/project/WCTopping.PrjPcb").resolve())
    folder_path = pathlib.Path(fixture_path).parent
    project.set_altium_link(lte, project_file=fixture_path)

    dirs_after = agent._add_dirs(lte)
    desc_after = workspace.describe(lte)
    places_after = desc_after["places"]

    assert str(folder_path) in dirs_after
    assert len(dirs_after) == len(dirs_before) + 1

    assert len(places_after) == len(places_before) + 1
    alt_place = next(p for p in places_after if "student's Altium project" in p["what"])
    assert alt_place["write"] is False
    assert alt_place["path"] == folder_path.as_posix()
    assert "scripts/altium/dump.py" in alt_place["what"] and "READ ONLY" in alt_place["what"]

    # Unlink
    project.set_altium_link(lte, project_file="")
    dirs_unlinked = agent._add_dirs(lte)
    desc_unlinked = workspace.describe(lte)

    assert dirs_unlinked == dirs_before
    assert len(desc_unlinked["places"]) == len(places_before)
    assert not any("student's Altium project" in p["what"] for p in desc_unlinked["places"])
