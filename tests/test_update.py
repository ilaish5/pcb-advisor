"""
Self-update: a fast-forward of the install's branch, refused when it would overwrite anything, rolled back when the
new version does not start. Offline: the "GitHub" here is a bare repository in a temp folder.
"""
import json
import os
import shutil
import subprocess

import pytest

import update

pytestmark = pytest.mark.skipif(not shutil.which("git"), reason="git is not installed")


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})


def _commit(cwd, name, text, msg):
    (cwd / name).write_text(text, encoding="utf-8")
    _git(cwd, "add", name)
    _git(cwd, "commit", "-q", "-m", msg)


@pytest.fixture
def repos(tmp_path):
    """origin (bare), the install (a clone of it), and a second clone that pushes new versions."""
    origin, install, dev = tmp_path / "origin.git", tmp_path / "install", tmp_path / "dev"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    _git(tmp_path, "clone", "-q", str(origin), str(dev))
    _git(dev, "checkout", "-q", "-b", "main")
    _commit(dev, "app.py", "v = 1\n", "first")
    _git(dev, "push", "-q", "-u", "origin", "main")
    _git(tmp_path, "clone", "-q", str(origin), str(install))
    update._version_cache.clear()
    yield origin, install, dev
    update._version_cache.clear()


def _push(dev, n=1):
    for i in range(n):
        _commit(dev, "app.py", f"v = {i + 2}\n", f"change {i + 2}")
    _git(dev, "push", "-q")


def test_up_to_date(repos):
    _, install, _ = repos
    st = update.check(repo=install)
    assert st["kind"] == "git" and st["behind"] == 0 and not st["can_update"] and st["reason"] == "Up to date."
    assert st["upstream"] == "origin/main" and not st["error"]


def test_behind_lists_the_new_commits_and_may_update(repos):
    _, install, dev = repos
    _push(dev, 2)
    st = update.check(repo=install)
    assert st["behind"] == 2 and st["ahead"] == 0 and st["can_update"]
    assert [c["subject"] for c in st["commits"]] == ["change 3", "change 2"]


def test_apply_fast_forwards_and_logs(repos, home):
    _, install, dev = repos
    _push(dev)
    res = update.apply(repo=install, smoke_check=lambda repo: "")
    assert res["ok"] and res["from"] != res["to"] and not res["rolled_back"]
    assert (install / "app.py").read_text(encoding="utf-8") == "v = 2\n"
    assert update.check(repo=install)["behind"] == 0
    log = [json.loads(l) for l in (home / update.LOG).read_text(encoding="utf-8").splitlines()]
    assert log[-1]["ok"] and log[-1]["to"] == res["to"]


def test_a_new_version_that_does_not_start_is_rolled_back(repos, home):
    _, install, dev = repos
    _push(dev)
    before = (install / "app.py").read_text(encoding="utf-8")
    res = update.apply(repo=install, smoke_check=lambda repo: "SyntaxError: invalid syntax")
    assert not res["ok"] and res["rolled_back"] and "did not start" in res["reason"]
    assert (install / "app.py").read_text(encoding="utf-8") == before
    assert update.check(repo=install)["behind"] == 1           # still offered, nothing lost


def test_local_edits_stop_the_update_and_are_kept(repos):
    _, install, dev = repos
    _push(dev)
    (install / "app.py").write_text("mine\n", encoding="utf-8")
    st = update.check(repo=install)
    assert not st["can_update"] and st["dirty"] == ["app.py"] and "edited here" in st["reason"]
    res = update.apply(repo=install, smoke_check=lambda repo: "")
    assert not res["ok"] and (install / "app.py").read_text(encoding="utf-8") == "mine\n"


def test_local_commits_stop_the_update(repos):
    _, install, dev = repos
    _push(dev)
    _commit(install, "other.py", "x\n", "mine")
    st = update.check(repo=install)
    assert st["ahead"] == 1 and st["behind"] == 1 and not st["can_update"] and "of its own" in st["reason"]


def test_no_upstream_and_detached(repos):
    _, install, _ = repos
    _git(install, "checkout", "-q", "-b", "local")
    assert "does not track" in update.check(repo=install)["reason"]
    _git(install, "checkout", "-q", "--detach")
    assert "detached" in update.check(repo=install)["reason"]


def test_a_zip_install_points_to_the_download(tmp_path):
    st = update.check(repo=tmp_path)
    assert st["kind"] == "zip" and not st["can_update"] and update.GITHUB in st["reason"]


def test_an_unreachable_remote_is_an_error_not_a_hang(repos, tmp_path):
    _, install, _ = repos
    _git(install, "remote", "set-url", "origin", str(tmp_path / "gone.git"))      # git's object files are read-only on Windows: no rmtree
    st = update.check(repo=install)
    assert st["error"].startswith("Could not reach GitHub") and not st["can_update"]


def test_the_real_smoke_check_imports_this_repo():
    assert update.smoke() == ""
