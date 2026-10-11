"""
The reference library.

Shared cache, per-project copies of what was actually cited.  A document is
stored with a sha256, so if a vendor revises a datasheet the hash changes and
every claim resting on it can be flagged stale.

The important function here is verify(): a stored quote must be findable,
verbatim, in the fetched document.  That turns "trust me" into a test.
"""
import hashlib
import json
import pathlib
import re
import shutil
import sys
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import workspace  # noqa: E402

UA = "Mozilla/5.0 (compatible; pcb-advisor/0.1; educational use)"


def cache():
    """The shared document library. One copy, reused by every project."""
    return workspace.datasheets_dir()


def _safe(name):
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)[:120]


def _meta_path(path):
    return path.with_suffix(path.suffix + ".json")


def fetch(url, name=None, timeout=45):
    """Download into the shared cache. Returns the metadata dict."""
    cache().mkdir(parents=True, exist_ok=True)
    name = _safe(name or url.rstrip("/").split("/")[-1] or "document.pdf")
    path = cache() / name
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        blob = resp.read()
    path.write_bytes(blob)
    # The sidecar describes the DOCUMENT - what it is, where it came from, what
    # it hashes to. All of that is the same on every machine, which is why the
    # file can be tracked in git at all.
    meta = {
        "name": name,
        "url": url,
        "sha256": hashlib.sha256(blob).hexdigest(),
        "bytes": len(blob),
    }
    # When the document is unchanged, leave the sidecar alone. `restore` warms
    # the cache on every fresh clone, and writing a new timestamp each time made
    # a tracked file dirty as a side effect of setting the project up - so
    # `git status` was never clean and nobody could see their own changes.
    old_path = _meta_path(path)
    if old_path.exists():
        try:
            if json.loads(old_path.read_text(encoding="utf-8")) == meta:
                return meta
        except json.JSONDecodeError:
            pass
    old_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


def text_of(name, folder=None):
    """Plain text of a cached document, itself cached next to it. `folder` is a
    project's sources/ directory, tried before the shared library."""
    path = cache() / _safe(name)
    if folder is not None and (pathlib.Path(folder) / _safe(name)).exists():
        path = pathlib.Path(folder) / _safe(name)
    if not path.exists():
        raise FileNotFoundError(f"{name} is not in the cache")
    txt_path = path.with_suffix(path.suffix + ".txt")
    if txt_path.exists():
        return txt_path.read_text(encoding="utf-8", errors="replace")
    text = ""
    if path.suffix.lower() == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            text = "\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception:
            import subprocess
            text = subprocess.run(["pdftotext", str(path), "-"],
                                  capture_output=True, encoding="utf-8",
                                  errors="replace").stdout
    else:
        text = path.read_text(encoding="utf-8", errors="replace")
    txt_path.write_text(text, encoding="utf-8")
    return text


def _norm(s):
    """
    Both sides of a comparison go through this, so any deterministic transform
    is safe.  The one that matters: PDF extraction breaks words across lines as
    "compo - nent".  Joining a hyphen that is FOLLOWED by whitespace repairs
    that without touching real hyphenates like "step-down".
    """
    s = (s or "").lower()
    s = re.sub(r"(?<=[a-z])\s*-\s+(?=[a-z])", "", s)
    return re.sub(r"\s+", " ", s).strip()


def verify(name, quote):
    """Is this quote actually in that document? The whole point of the module."""
    try:
        body = _norm(text_of(name))
    except FileNotFoundError as exc:
        return {"ok": False, "reason": str(exc)}
    q = _norm(quote)
    if not q:
        return {"ok": False, "reason": "empty quote"}
    if q in body:
        i = body.find(q)
        return {"ok": True, "context": body[max(0, i - 90): i + len(q) + 90]}
    # a near miss is worth reporting differently from a fabrication
    words = q.split()
    if len(words) > 6:
        head = " ".join(words[:6])
        if head in body:
            return {"ok": False, "reason": "opening words found but full quote does not match - "
                                           "likely paraphrased or line-broken"}
    return {"ok": False, "reason": "quote not present in the document"}


def use(project, name):
    """Copy a cached document into the project, so the project folder stands alone."""
    src = cache() / _safe(name)
    dst_dir = workspace.project_dir(project) / "sources"
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst_dir / src.name)
    if _meta_path(src).exists():
        shutil.copy2(_meta_path(src), _meta_path(dst_dir / src.name))
    return str(dst_dir / src.name)


def get(project, url, name=None):
    """Fetch into the shared cache and copy into the project, in one step - the
    whole of "add this datasheet to my board". Returns the metadata, plus where
    the project copy landed."""
    meta = fetch(url, name)
    return {**meta, "path": use(project, meta["name"])}


def unuse(project, name):
    """Take a document out of ONE project. The shared cache is left alone: other
    projects may cite it, and its .json is the tracked record of where it came
    from."""
    target = workspace.project_dir(project) / "sources" / _safe(name)
    removed = []
    for p in (target, _meta_path(target), target.with_suffix(target.suffix + ".txt")):
        if p.exists():
            p.unlink()
            removed.append(p.name)
    return {"removed": removed}


def search_hint(part):
    """We do not guess datasheet URLs. Point the human at somewhere real."""
    return [
        f"https://www.google.com/search?q={part}+datasheet+filetype:pdf",
        f"https://www.digikey.com/en/products/result?keywords={part}",
        f"https://www.lcsc.com/search?q={part}",
    ]


def restore():
    """
    Re-fetch every document that has a sidecar with a url but no file on this machine:
    the shared library and every project's sources/. Vendor PDFs are not redistributed
    with this repo, so a fresh clone runs this once.
    """
    folders = [cache()]
    root = workspace.projects_dir()
    if root.exists():
        folders += [d / "sources" for d in sorted(root.iterdir()) if (d / "sources").is_dir()]
    failed = 0
    for folder in folders:
        for side in sorted(folder.glob("*.json")):
            base = side.name[:-5]
            if not pathlib.Path(base).suffix:
                continue                      # not a sidecar of a document
            try:
                meta = json.loads(side.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            url = meta.get("url")
            if (folder / base).exists():
                print(f"  have  {base}")
                continue
            if not url:
                print(f"  skip  {base}: no url recorded (it was uploaded by hand)")
                continue
            try:
                if folder == cache():
                    fetch(url, base)
                else:
                    blob = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=45).read()
                    (folder / base).write_bytes(blob)
                print(f"  got   {base}")
            except Exception as exc:
                print(f"  FAIL  {base}: {exc}")
                failed += 1
    if failed:
        print(f"\n{failed} document(s) could not be fetched. Citations of them stay unchecked.")
    return failed


if __name__ == "__main__":
    import oscompat
    oscompat.utf8_stdio()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "restore":
        # a setup step that prints FAIL and exits 0 is one no script can check
        raise SystemExit(1 if restore() else 0)
    if cmd == "fetch":
        print(json.dumps(fetch(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None), indent=2))
    elif cmd == "verify":
        print(json.dumps(verify(sys.argv[2], sys.argv[3]), indent=2, ensure_ascii=False))
    elif cmd == "get":
        print(json.dumps(get(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None), indent=2))
    elif cmd == "use":
        print(use(sys.argv[2], sys.argv[3]))
    elif cmd == "unuse":
        print(json.dumps(unuse(sys.argv[2], sys.argv[3])))
    else:
        for f in sorted(cache().glob("*")):
            if f.suffix not in (".json", ".txt"):
                print(f.name, f.stat().st_size)
