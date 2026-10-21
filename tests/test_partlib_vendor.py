"""Vendor zips (SnapEDA, Ultra Librarian, ...) in partlib.prepare: found by the MPN in the file name, unpacked safely,
their KiCad files converted; the staleness, the library.build action, the build/prepare endpoints and the manifest in the views."""
import json
import os
import pathlib
import threading
import time
import urllib.error
import urllib.request
import zipfile

import pytest

import partlib
import sources
import store
from altium import bridge
from test_partlib import FIX, prep, proj, fake_fetch  # noqa: F401  (proj is a fixture)


def make_zip(path, members=None, kicad=True):
    """A vendor zip: the KiCad files of the C100 fixture nested in KiCad/ the way vendors ship them, plus `members`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        if kicad:
            z.write(FIX / "C100" / "lib.kicad_sym", "Vendor/KiCad/part.kicad_sym")
            z.write(FIX / "C100" / "lib.pretty" / "R0603_FAKE.kicad_mod", "Vendor/KiCad/R0603_FAKE.kicad_mod")
        z.writestr("Vendor/readme.txt", "hello")
        for name, data in (members or {}).items():
            z.writestr(name, data)
    return path


def sources_dir(project):
    return sources.folder_of(project)


def downloads(home):
    return home / "userhome" / "Downloads"       # the `home` fixture points Path.home() here


def age(path, days):
    t = time.time() - days * 86400
    os.utime(path, (t, t))


def u3(m):
    return m["U3"]


def test_zip_in_sources_is_found_by_the_mpn_and_converted(proj, home):
    make_zip(sources_dir(proj) / "RF-QFN_KiCad.zip")
    m = prep(proj, fetcher=fake_fetch([]))
    e = u3(m)
    assert e["source"] == "vendor" and e["vendor_zip"] == "RF-QFN_KiCad.zip"
    assert e["symbol"] == "RF-QFN" and e["footprint"] == "R0603_FAKE" and e["status"] in ("ok", "warn")
    assert (home / "projects" / proj / "library" / "vendor" / "RF-QFN" / "Vendor" / "KiCad" / "part.kicad_sym").is_file()
    assert m["R1"]["source"] == "easyeda" and "vendor_zip" not in m["R1"]
    spec = (home / "projects" / proj / "library" / "build" / "footprints_spec.txt").read_text(encoding="cp1252")
    assert "FOOTPRINT|R0603_FAKE|" in spec


def test_zip_in_downloads_is_copied_into_sources_and_registered(proj, home):
    z = make_zip(downloads(home) / "ultralibrarian_rf_qfn.zip")      # normalized name carries rfqfn
    m = prep(proj, fetcher=fake_fetch([]))
    assert u3(m)["source"] == "vendor" and u3(m)["vendor_zip"] == "ultralibrarian_rf_qfn.zip"
    kept = sources_dir(proj) / "ultralibrarian_rf_qfn.zip"
    assert kept.read_bytes() == z.read_bytes() and (sources_dir(proj) / "ultralibrarian_rf_qfn.zip.json").is_file()
    z.unlink()
    assert u3(prep(proj, fetcher=fake_fetch([])))["source"] == "vendor"      # the project keeps its copy


def test_old_downloads_are_ignored(proj, home):
    age(make_zip(downloads(home) / "RF-QFN.zip"), 40)
    assert u3(prep(proj, fetcher=fake_fetch([])))["status"] == "missing"
    assert not (sources_dir(proj) / "RF-QFN.zip").exists()


def test_mpn_without_its_packaging_suffix_matches_too(proj, home):
    make_zip(sources_dir(proj) / "RC0603_footprint.zip")             # the line's MPN is RC0603-4K7
    m = prep(proj, fetcher=fake_fetch([]))
    assert m["R2"]["source"] == "vendor"
    assert partlib._mpn_keys("RC0603-4K7") == ["rc06034k7", "rc0603"]
    assert partlib._mpn_keys("AB-1") == []                                       # too short to look for


def test_zip_slip_member_is_refused_and_nothing_is_written_outside(proj, home):
    make_zip(sources_dir(proj) / "RF-QFN.zip", {"../../evil.txt": "x"})
    m = prep(proj, fetcher=fake_fetch([]))
    assert u3(m)["status"] == "missing" and any("points outside" in i for i in u3(m)["issues"])
    assert not (home / "projects" / proj / "evil.txt").exists() and not (home / "evil.txt").exists()


def test_absolute_member_is_refused(tmp_path):
    z = make_zip(tmp_path / "a.zip", {"/abs/evil.txt": "x"})
    with pytest.raises(ValueError, match="points outside"):
        partlib.safe_extract(z, tmp_path / "out")
    z = make_zip(tmp_path / "b.zip", {"C:/evil.txt": "x"})
    with pytest.raises(ValueError, match="points outside"):
        partlib.safe_extract(z, tmp_path / "out")


def test_symlink_members_are_skipped(tmp_path):
    z = tmp_path / "l.zip"
    with zipfile.ZipFile(z, "w") as zf:
        info = zipfile.ZipInfo("link.kicad_sym")
        info.external_attr = 0o120777 << 16
        zf.writestr(info, "/etc/passwd")
        zf.writestr("ok.txt", "fine")
    partlib.safe_extract(z, tmp_path / "out")
    assert (tmp_path / "out" / "ok.txt").is_file() and not (tmp_path / "out" / "link.kicad_sym").exists()


def test_oversize_and_too_many_members_are_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(partlib, "ZIP_MAX_BYTES", 2 * 2**20)
    z = make_zip(tmp_path / "big.zip", {"big.step": b"\0" * (3 * 2**20)})
    with pytest.raises(ValueError, match="more than 2 MB"):
        partlib.safe_extract(z, tmp_path / "out")
    monkeypatch.setattr(partlib, "ZIP_MAX_MEMBERS", 2)
    with pytest.raises(ValueError, match="more than 2"):
        partlib.safe_extract(make_zip(tmp_path / "many.zip"), tmp_path / "out")


def test_a_file_that_is_no_zip_is_a_clear_issue(proj, home):
    (sources_dir(proj)).mkdir(parents=True, exist_ok=True)
    (sources_dir(proj) / "RF-QFN.zip").write_bytes(b"not a zip")
    m = prep(proj, fetcher=fake_fetch([]))
    assert u3(m)["status"] == "missing" and any("not a readable zip" in i for i in u3(m)["issues"])


def test_zip_without_kicad_files_names_what_it_holds_and_falls_through(proj, home):
    make_zip(sources_dir(proj) / "RC0603-4K7_altium.zip", {"Altium/part.SchLib": b"x", "Altium/part.PcbLib": b"y"}, kicad=False)
    m = prep(proj, fetcher=fake_fetch([]))
    e = m["R2"]
    assert e["source"] == "generated" and e["footprint"] == "CHIP-0603" and e["vendor_zip"] == "RC0603-4K7_altium.zip"
    issue = next(i for i in e["issues"] if "no KiCad symbol" in i)
    assert ".schlib" in issue and ".pcblib" in issue and "KiCad format" in issue


def test_nothing_found_gives_the_search_links_and_the_steps(proj):
    m = prep(proj, fetcher=fake_fetch([]))
    text = " ".join(u3(m)["issues"])
    assert "componentsearchengine.com/search?term=RF-QFN" in text
    assert "snapeda.com/search/?q=RF-QFN" in text and "ultralibrarian.com/search?q=RF-QFN" in text
    assert "KiCad" in text and "log in" in text and "Downloads" in text and "build the library again" in text
    assert "term=A%2FB%20C" in partlib.vendor_hint("A/B C")


def test_a_new_zip_makes_the_library_stale(proj, home):
    prep(proj, fetcher=fake_fetch([]))
    assert bridge.library_stale(proj) is False
    man = home / "projects" / proj / "library" / "manifest.json"
    z = make_zip(sources_dir(proj) / "anything.zip")
    os.utime(z, (man.stat().st_mtime + 5, man.stat().st_mtime + 5))
    assert bridge.library_stale(proj) is True


def test_a_matching_zip_in_downloads_makes_it_stale_but_an_unrelated_one_does_not(proj, home):
    prep(proj, fetcher=fake_fetch([]))
    man = home / "projects" / proj / "library" / "manifest.json"
    later = man.stat().st_mtime + 5
    other = make_zip(downloads(home) / "holiday-photos.zip")
    os.utime(other, (later, later))
    assert bridge.library_stale(proj) is False
    hit = make_zip(downloads(home) / "RF-QFN.zip")
    os.utime(hit, (later, later))
    assert bridge.library_stale(proj) is True


def test_library_build_action_applies_and_refuses(proj, monkeypatch):
    import serve
    prep(proj, fetcher=fake_fetch([]))
    monkeypatch.setattr(bridge, "build_library", lambda project: {"built": 9, "lines": 11})
    applied, _, refused = serve.apply_actions(proj, [{"type": "library.build"}])
    assert not refused and applied[0].startswith("library.build: 9 of 11 lines built, IntLib installed (")
    assert "with issues)" in applied[0]

    def boom(project):
        raise bridge.BridgeError("Altium is not running")
    monkeypatch.setattr(bridge, "build_library", boom)
    applied, _, refused = serve.apply_actions(proj, [{"type": "library.build"}])
    assert not applied and refused == ["library.build: Altium is not running"]
    monkeypatch.setattr(bridge, "build_library", lambda project: (_ for _ in ()).throw(OSError("disk full")))
    assert serve.apply_actions(proj, [{"type": "library.build"}])[2] == ["library.build: disk full"]


def test_api_library_build_and_prepare(proj, monkeypatch):
    from http.server import ThreadingHTTPServer
    import serve
    monkeypatch.setattr(serve, "QUIET", True)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    def post(path):
        req = urllib.request.Request(f"{base}{path}?project={proj}", method="POST", data=b"{}",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    try:
        monkeypatch.setattr(partlib, "prepare", lambda project, **kw: {"R1": {"status": "ok"}})
        assert post("/api/library/prepare") == (200, {"R1": {"status": "ok"}})
        monkeypatch.setattr(bridge, "build_library", lambda project: {"built": 1, "lines": 1, "issues": []})
        code, body = post("/api/library/build")
        assert code == 200 and body["built"] == 1 and body["issues_lines"] == 0

        def boom(project):
            raise bridge.BridgeError("No Altium project is linked")
        monkeypatch.setattr(bridge, "build_library", boom)
        assert post("/api/library/build") == (400, {"error": "No Altium project is linked"})
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_library_view_and_bom_take_their_state_from_the_manifest(proj, home):
    prep(proj, fetcher=fake_fetch([]))
    rows = {r["line"]: r for r in store.library_view(proj)}
    assert set(rows) == {l["key"] for l in store.bom_lines(proj)}            # every line, not only the non-standard ones
    assert rows["U3"]["build_status"] == "missing" and rows["U3"]["source"] == "missing"
    assert any("snapeda.com" in i for i in rows["U3"]["issue_list"]) and "snapeda.com" in rows["U3"]["issues"]
    assert rows["R1"]["source"] == "easyeda" and rows["R1"]["symbol"] and rows["R1"]["footprint"] and rows["R1"]["step"]
    bom = {l["key"]: l["library"] for l in store.bom(proj, write=False)}
    assert bom["U3"] == "missing" and bom["R1"] == "review"                    # data exists, not built yet
    path = home / "projects" / proj / "library" / "manifest.json"
    man = json.loads(path.read_text())
    man["R1"]["built"] = True
    path.write_text(json.dumps(man))
    assert {l["key"]: l["library"] for l in store.bom(proj, write=False)}["R1"] == "ok"
    assert {r["line"]: r for r in store.library_view(proj)}["R1"]["built"] is True


def test_a_zip_of_a_longer_part_number_is_not_taken(tmp_path):
    # LM35 must not pick up LM358's model; separators in the name may differ from the BOM's
    zips = [tmp_path / "LIB_LM358DR.zip", tmp_path / "ul_ATtiny412_SSNR.zip"]
    assert partlib._zip_for("LM35", zips) is None
    assert partlib._zip_for("ATTINY412-SSNR", zips) == zips[1]
    assert partlib._zip_for("ATTINY412-SSNR", [tmp_path / "ATTINY4120.zip"]) is None
