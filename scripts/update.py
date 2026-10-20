"""
Self-update from the git repository the tool was cloned from.

    python pcb.py update            fetch, list what is new, update, check it starts, roll back if it does not
    python pcb.py update --check    only say whether an update is waiting
    python pcb.py version           which commit this install is on

The server checks once at every start, in the background (no network or a slow one never delays it), and the UI
shows an Update button when this install is behind. An update is a fast-forward of the current branch and nothing
else: edits to tracked files, local commits, or a branch with no upstream stop it with the reason, and nothing is
overwritten. After the pull the requirements are installed again when requirements.txt changed, and a smoke check
runs (every module the server needs imports). When that fails the install goes back to the commit it was on.
Projects and config.json live outside git and are never touched.
"""
import datetime as dt
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
GITHUB = "https://github.com/ilaish5/pcb-advisor"
LOG = "update-log.jsonl"
MAX_COMMITS = 20
# What has to import for the server to come up. A broken update fails here, before the restart.
SMOKE = "import serve, agent, gateway, model, store, lineage, introspect, update, runtime_pack"

_version_cache: dict = {}


def _now():
    return dt.datetime.now().isoformat(timespec="seconds")


def git(*args, repo=None, timeout=30):
    """Run git in the install. Never prompts: a remote that wants a password fails instead of hanging the server."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "", "SSH_ASKPASS": "", "GCM_INTERACTIVE": "never",
           "LC_ALL": "C"}
    return subprocess.run(["git", *args], cwd=str(repo or REPO), capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, env=env)


def _out(*args, repo=None, timeout=30):
    p = git(*args, repo=repo, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or f"git {args[0]} failed").strip().splitlines()[-1][:300])
    return p.stdout.strip()


def kind(repo=None) -> str:
    """'git' | 'zip' (no .git: unpacked from a download) | 'no-git' (a clone, but git is not installed)."""
    root = pathlib.Path(repo or REPO)
    if not (root / ".git").exists():
        return "zip"
    return "git" if shutil.which("git") else "no-git"


def version(repo=None) -> dict:
    """{kind, commit, date, branch}. Read once per process: the commit only changes through apply(), which restarts."""
    key = str(repo or REPO)
    if key in _version_cache:
        return _version_cache[key]
    k = kind(repo)
    v = {"kind": k, "commit": "", "date": "", "branch": ""}
    if k == "git":
        try:
            v["commit"], v["date"] = _out("log", "-1", "--format=%h%x09%cI", repo=repo).split("\t")
            v["branch"] = _out("rev-parse", "--abbrev-ref", "HEAD", repo=repo)
        except (RuntimeError, ValueError, OSError, subprocess.SubprocessError):
            pass
    _version_cache[key] = v
    return v


def _log(record):
    try:
        import workspace
        path = workspace.home() / LOG
        with open(path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass                    # the log is a convenience; an update must not fail on it


def check(fetch=True, repo=None) -> dict:
    """Is there an update, and may it be applied here? Never raises."""
    k = kind(repo)
    res = {"kind": k, "checked": _now(), "current": version(repo).get("commit", ""), "latest": "", "branch": "",
           "upstream": "", "behind": 0, "ahead": 0, "commits": [], "dirty": [], "can_update": False,
           "reason": "", "error": "", "url": GITHUB}
    if k == "zip":
        res["reason"] = ("Installed from a ZIP, so it cannot update itself. Install git, then run the installer again "
                         "in this folder: it turns the folder into a clone and keeps your projects. Or download the new ZIP from "
                         f"{GITHUB}")
        return res
    if k == "no-git":
        res["reason"] = "git is not installed, so the tool cannot update itself. Install git, or download the new ZIP."
        return res
    try:
        res["branch"] = _out("rev-parse", "--abbrev-ref", "HEAD", repo=repo)
        if res["branch"] == "HEAD":
            res["reason"] = "Not on a branch (a detached checkout): update by hand."
            return res
        up = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", repo=repo)
        if up.returncode != 0:
            res["reason"] = f"Branch {res['branch']} does not track a remote branch: update by hand."
            return res
        res["upstream"] = up.stdout.strip()
        if fetch:
            remote = res["upstream"].split("/", 1)[0]
            f = git("fetch", "--quiet", remote, repo=repo, timeout=25)
            if f.returncode != 0:
                res["error"] = "Could not reach GitHub: " + ((f.stderr or "").strip().splitlines() or ["no answer"])[-1][:200]
        ahead, behind = _out("rev-list", "--left-right", "--count", "HEAD...@{u}", repo=repo).split()
        res["ahead"], res["behind"] = int(ahead), int(behind)
        res["latest"] = _out("rev-parse", "--short", "@{u}", repo=repo)
        if res["behind"]:
            for line in _out("log", f"--max-count={MAX_COMMITS}", "--format=%h%x09%cI%x09%s", "HEAD..@{u}",
                             repo=repo).splitlines():
                sha, date, subject = (line.split("\t", 2) + ["", ""])[:3]
                res["commits"].append({"sha": sha, "date": date, "subject": subject})
        porcelain = git("status", "--porcelain", "--untracked-files=no", repo=repo).stdout   # not stripped: "XY path"
        res["dirty"] = [ln[3:] for ln in porcelain.splitlines() if ln.strip()]
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as exc:
        res["error"] = str(exc)
        return res

    if not res["behind"]:
        res["reason"] = "Up to date."
    elif res["ahead"]:
        res["reason"] = (f"This install has {res['ahead']} commit(s) of its own that are not on GitHub: "
                         "update by hand (git pull).")
    elif res["dirty"]:
        res["reason"] = (f"{len(res['dirty'])} file(s) of the tool were edited here ({', '.join(res['dirty'][:3])}"
                         f"{'...' if len(res['dirty']) > 3 else ''}). Undo the edits or update by hand.")
    else:
        res["can_update"] = True
    return res


def _requirements_sha(repo=None):
    p = pathlib.Path(repo or REPO) / "requirements.txt"
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else ""


def _pip(repo=None):
    p = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"],
                       cwd=str(repo or REPO), capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        raise RuntimeError("pip install failed: " + ((p.stderr or p.stdout).strip().splitlines() or ["?"])[-1][:300])


def smoke(repo=None) -> str:
    """'' when the updated tool imports; else the error. Runs in a fresh interpreter, so this process's modules
    (the old code) do not hide a broken import."""
    root = pathlib.Path(repo or REPO)
    code = f"import sys; sys.path.insert(0, {str(root / 'scripts')!r}); sys.path.insert(0, {str(root / 'scripts' / 'skills')!r}); {SMOKE}"
    try:
        p = subprocess.run([sys.executable, "-c", code], cwd=str(root), capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return "the updated tool did not finish loading in 120 s"
    if p.returncode != 0:
        return ((p.stderr or p.stdout).strip().splitlines() or ["it did not start"])[-1][:300]
    return ""


def apply(repo=None, smoke_check=None) -> dict:
    """Fast-forward to the remote branch, install requirements if they changed, smoke-check, roll back on failure.
    {ok, from, to, commits, reason, rolled_back}."""
    smoke_check = smoke_check or smoke
    st = check(fetch=True, repo=repo)
    res = {"ok": False, "from": st["current"], "to": st["current"], "commits": st["commits"], "rolled_back": False,
           "reason": ""}
    if not st["can_update"]:
        res["reason"] = st["error"] or st["reason"]
        return res
    try:
        old = _out("rev-parse", "HEAD", repo=repo)
        req = _requirements_sha(repo)
        _out("merge", "--ff-only", "@{u}", repo=repo, timeout=120)
        res["to"] = _out("rev-parse", "--short", "HEAD", repo=repo)
        req_changed = _requirements_sha(repo) != req
        problem = ""
        if req_changed:
            try:
                _pip(repo)
            except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
                problem = str(exc)
        problem = problem or smoke_check(repo)
        if problem:
            _out("reset", "--hard", old, repo=repo)
            if req_changed:
                try:
                    _pip(repo)
                except (RuntimeError, OSError, subprocess.SubprocessError):
                    pass
            res.update(rolled_back=True, to=res["from"],
                       reason=f"The new version did not start ({problem}). Went back to {res['from']}; nothing else changed.")
        else:
            res["ok"] = True
            res["requirements"] = req_changed
            _version_cache.pop(str(repo or REPO), None)
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        res["reason"] = str(exc)
    _log({"ts": _now(), **{k: res[k] for k in ("ok", "from", "to", "rolled_back", "reason")},
          "commits": len(res["commits"])})
    return res


def main(argv=None):
    import oscompat
    oscompat.utf8_stdio()
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "version":
        v = version()
        print(f"pcb-advisor {v['commit'] or '(no git)'} {v['date'][:10]} {v['branch']}".rstrip())
        return 0
    st = check(fetch=True)
    if st["error"]:
        print(st["error"])
    if not st["behind"]:
        print(st["reason"] or "Up to date.")
        return 0
    print(f"{st['behind']} new change(s) on {st['upstream']} (this install: {st['current']}, latest: {st['latest']}):")
    for c in st["commits"]:
        print(f"  {c['sha']}  {c['date'][:10]}  {c['subject']}")
    if "--check" in args:
        return 0
    if not st["can_update"]:
        print(st["reason"])
        return 1
    res = apply()
    if res["ok"]:
        print(f"Updated {res['from']} -> {res['to']}" + (" (requirements installed again)" if res.get("requirements") else "")
              + ". Restart the server to use it.")
        return 0
    print(res["reason"])
    return 1


if __name__ == "__main__":
    sys.path.insert(0, str(REPO / "scripts"))
    raise SystemExit(main())
