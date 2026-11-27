"""Seed projects into a live server's workspace: a copy of the frozen fixture's project/ (+ its altium/ folder, with the
project's Altium paths pointed at the copy), and synthetic projects built from a few JSON files.

The frozen fixture is only read (copytree); every write goes to the server's own temp home.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil

REPO = pathlib.Path(__file__).resolve().parent.parent.parent.parent
FIXTURE = pathlib.Path(os.environ.get("ACCEPTANCE_FIXTURE") or REPO / "local" / "acceptance-fixtures" / "final-e2e-4l-1127")


def fixture_root() -> pathlib.Path:
    if not (FIXTURE / "MANIFEST.sha256").is_file():
        raise FileNotFoundError(f"no fixture at {FIXTURE}: run python -I tests/acceptance/fetch_fixture.py")
    return FIXTURE


def seed_fixture(projects: pathlib.Path, name: str | None = None, root: pathlib.Path | None = None) -> str:
    """Copy root/project into projects/<name> (name from its project.json unless given) and root/altium next to the
    workspace; returns the project name the server knows it by."""
    root = pathlib.Path(root or fixture_root())
    meta = json.loads((root / "project" / "project.json").read_text(encoding="utf-8"))
    name = name or meta["name"]
    dst = projects / name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(root / "project", dst)
    alt_src = root / "altium"
    if alt_src.is_dir():
        alt_dst = projects.parent / "altium" / name
        if alt_dst.exists():
            shutil.rmtree(alt_dst)
        shutil.copytree(alt_src, alt_dst)
        old = meta.get("altium") or {}
        def moved(p):
            if not p:
                return p
            base = str(p).replace("\\", "/").rsplit("/", 1)[-1]
            return str(alt_dst / base)
        meta["altium"] = {k: moved(v) for k, v in old.items()}
    meta["name"] = name
    (dst / "project.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return name


def seed_synthetic(projects: pathlib.Path, name: str, files: dict[str, object]) -> str:
    """A synthetic project: files maps a relative path to a dict/list (written as JSON) or a str (written as text).
    project.json gets the minimum the server needs when it is not given."""
    dst = projects / name
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    files = dict(files)
    files.setdefault("project.json", {"schema_version": 1, "name": name, "title": name, "brief": "", "status": "draft",
                                      "tags": [], "board": {}, "altium": {}, "notes": ""})
    for rel, body in files.items():
        p = dst / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(body, (dict, list)):
            p.write_text(json.dumps(body, indent=1), encoding="utf-8")
        elif isinstance(body, bytes):
            p.write_bytes(body)
        else:
            p.write_text(str(body), encoding="utf-8")
    return name


def read_jsonl(path: pathlib.Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out
