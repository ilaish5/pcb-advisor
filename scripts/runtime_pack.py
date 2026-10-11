#!/usr/bin/env python3
"""
The runtime pack: the instructions and skills the student's AI engine works from.

Source of truth is `runtime/` in the repo (AGENTS.md + skills/<name>/). Nothing in
there is auto-loaded by any CLI, on purpose: both Claude Code and agy also read the
enclosing git root, so a pack that lived in the repo would mix with developer files,
and developer files would leak into the student's engine.

So the pack is materialised in the ENGINE HOME, a folder outside any git tree, and
the engine runs with that as its cwd:

    <engine home>/AGENTS.md                the constitution (agy, and any AGENTS.md CLI)
    <engine home>/CLAUDE.md                "@AGENTS.md" (Claude Code imports it)
    <engine home>/.agents/skills/<n>/...   skills for agy
    <engine home>/.claude/skills/<n>/...   the same skills for Claude Code
    <engine home>/.pack.json               sha256 of every source file

    python scripts/runtime_pack.py sync     write it (idempotent)
    python scripts/runtime_pack.py where    print the engine home
    python scripts/runtime_pack.py check    is the engine home in step with runtime/ ?
"""
import hashlib
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import oscompat    # noqa: E402
import workspace   # noqa: E402

SOURCE = workspace.REPO / "runtime"
MANIFEST = ".pack.json"
SKILL_TREES = (".agents/skills", ".claude/skills")
CLAUDE_MD = "@AGENTS.md\n"


class RuntimePackError(RuntimeError):
    pass


def engine_home():
    """Where the engine runs. PCB_ADVISOR_ENGINE_HOME, else `agent.engine_home` in the config, or a per-OS app-data folder."""
    raw = os.environ.get("PCB_ADVISOR_ENGINE_HOME") or workspace.get("agent.engine_home")
    if raw:
        return pathlib.Path(raw).expanduser().resolve()
    return (oscompat.app_data_dir() / "pcb-advisor" / "engine").resolve()


def _git_root(path):
    """The nearest folder at or above `path` that holds a .git (dir or file), else None."""
    path = pathlib.Path(path).resolve()
    for d in (path, *path.parents):
        if (d / ".git").exists():
            return d
    return None


def _check_dest(dest):
    repo = workspace.REPO.resolve()
    if dest == repo or repo in dest.parents:
        raise RuntimePackError(f"engine home {dest} is inside the repo {repo}; the engine would load "
                               "developer files. Set agent.engine_home to a folder outside it.")
    root = _git_root(dest)
    if root:
        raise RuntimePackError(f"engine home {dest} is inside the git work tree {root}; the engine would "
                               "load that repo's instructions and skills. Set agent.engine_home to a "
                               "folder outside any git tree.")


def _sources():
    """{path relative to runtime/ (posix): bytes}"""
    if not (SOURCE / "AGENTS.md").is_file():
        raise RuntimePackError(f"{SOURCE / 'AGENTS.md'} is missing")
    out = {"AGENTS.md": (SOURCE / "AGENTS.md").read_bytes()}
    skills = SOURCE / "skills"
    for f in sorted(skills.rglob("*")) if skills.is_dir() else []:
        rel = f.relative_to(SOURCE)
        if f.is_file() and "__pycache__" not in rel.parts and f.suffix != ".pyc":
            out[rel.as_posix()] = f.read_bytes()
    return out


def _desired(sources):
    """{path relative to the engine home: bytes}"""
    want = {"AGENTS.md": sources["AGENTS.md"], "CLAUDE.md": CLAUDE_MD.encode("utf-8")}
    for rel, data in sources.items():
        if rel.startswith("skills/"):
            for tree in SKILL_TREES:
                want[f"{tree}/{rel[len('skills/'):]}"] = data
    manifest = {"version": 1,
                "files": {rel: hashlib.sha256(data).hexdigest() for rel, data in sources.items()}}
    want[MANIFEST] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return want


def _stale(dest, want):
    """Files in the skill trees that the source no longer has."""
    stale = []
    for tree in SKILL_TREES:
        root = dest / tree
        for f in sorted(root.rglob("*")) if root.is_dir() else []:
            if f.is_file() and f.relative_to(dest).as_posix() not in want:
                stale.append(f)
    return stale


def sync(dest=None):
    """Make `dest` (default: the engine home) match runtime/. Only rewrites what changed.
    Returns the engine home as a Path; `sync.last` has the written/removed lists."""
    dest = pathlib.Path(dest).expanduser().resolve() if dest else engine_home()
    _check_dest(dest)
    want = _desired(_sources())
    written, removed = [], []
    for rel, data in want.items():
        target = dest / rel
        if target.is_file() and target.read_bytes() == data:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        written.append(rel)
    for f in _stale(dest, want):
        removed.append(f.relative_to(dest).as_posix())
        f.unlink()
    for tree in SKILL_TREES:                          # drop folders the pruning emptied
        root = dest / tree
        for d in sorted((p for p in root.rglob("*") if p.is_dir()), reverse=True) if root.is_dir() else []:
            if not any(d.iterdir()):
                d.rmdir()
    sync.last = {"dest": str(dest), "written": written, "removed": removed}
    return dest


sync.last = {}


def check(dest=None):
    """Problems between runtime/ and the engine home (empty list = in step). Writes nothing."""
    dest = pathlib.Path(dest).expanduser().resolve() if dest else engine_home()
    want = _desired(_sources())
    problems = []
    for rel, data in want.items():
        target = dest / rel
        if not target.is_file():
            problems.append(f"missing  {rel}")
        elif target.read_bytes() != data:
            problems.append(f"differs  {rel}")
    problems += [f"stale    {f.relative_to(dest).as_posix()}" for f in _stale(dest, want)]
    return problems


# ---------------------------------------------------------------- probe
#
# Proves, with the real engine, that the pack is what it loads: a code that exists
# only in a skill file and a codeword that exists only in AGENTS.md. If the engine
# answers both, it read both from its engine home.

SKILL_CODE = "PROBE-ALTIUM-7Q4X"
AGENTS_CODE = "KESTREL-31"
PROBE_PROMPT = (
    "Pack probe. Answer from your loaded instructions and skills; do not search the web. "
    "(1) What is the 'Probe marker' code in your altium-help skill? "
    "(2) What is the 'constitution codeword' in your AGENTS.md instructions? "
    "Reply with just the two values, nothing else.")


def probe(engine, timeout=240):
    """Ask one engine through the gateway, cwd = engine home. -> (ok, seconds, detail)"""
    import time
    import gateway
    ok, why = gateway.provider(engine).available()
    if not ok:
        return None, 0.0, why
    home = sync()
    req = gateway.Request(prompt=PROBE_PROMPT, timeout=timeout,
                          options={"cwd": str(home), "add_dirs": [str(workspace.REPO)]})
    t0 = time.time()
    res = gateway.route(req, name=engine)
    secs = time.time() - t0
    if not res.ok:
        return False, secs, res.error
    text = res.text or ""
    missing = [n for n, c in (("skill code", SKILL_CODE), ("AGENTS.md codeword", AGENTS_CODE)) if c not in text]
    return (not missing), secs, ("answer: " + " ".join(text.split())[:200]
                                 if not missing else "missing " + ", ".join(missing) +
                                 " | answer: " + " ".join(text.split())[:300])


def main(argv=None):
    oscompat.utf8_stdio()
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else "where"
    try:
        if cmd == "where":
            print(engine_home())
        elif cmd == "sync":
            dest = sync(args[1] if len(args) > 1 else None)
            print(f"engine home  {dest}")
            for rel in sync.last["written"]:
                print(f"  wrote    {rel}")
            for rel in sync.last["removed"]:
                print(f"  removed  {rel}")
            if not (sync.last["written"] or sync.last["removed"]):
                print("  already in step - nothing to do")
        elif cmd == "check":
            problems = check(args[1] if len(args) > 1 else None)
            for p in problems:
                print("  " + p)
            print("engine home is in step with runtime/" if not problems else
                  f"{len(problems)} difference(s) - run: python scripts/runtime_pack.py sync")
            return 1 if problems else 0
        else:
            print(__doc__.strip())
            return 2
    except RuntimePackError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
