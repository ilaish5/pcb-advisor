"""
The reference library.

Three places. `shared/reference/` is the course and JLC material that ships with the
tool: read-only, listed in every project under its path relative to that folder
(`jlc/pcb-capabilities.en.md`), the name a citation uses. `shared/datasheets/` holds GENERAL documents only (application notes,
design guides, standards): everything there is visible in every project and its
.json sidecars go to git. A project's own documents - the datasheets of ITS parts,
what it uploads, what it cites - live in `projects/<name>/sources/` and never
leave that project. `get` (the "add this datasheet to my board" step) therefore
writes into the project only; `fetch` without a project writes to the shared
library, for a general document.  A document is stored with a sha256, so if a
vendor revises a datasheet the hash changes and every claim resting on it can be
flagged stale.

The important function here is verify(): a stored quote must be findable,
verbatim, in the fetched document.  That turns "trust me" into a test.
"""
import hashlib
import http.client
import json
import pathlib
import re
import shutil
import sys
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import workspace  # noqa: E402

UA = "Mozilla/5.0 (compatible; pcb-advisor/0.1; educational use)"


class SourceError(Exception):
    """A document that cannot be added: the download failed, the server sent
    something other than what the name says, or the name is taken. The message
    is written for the person at the terminal; the CLI prints it as one line."""


def cache():
    """The shared document library: general documents, visible in every project."""
    return workspace.datasheets_dir()


REFERENCE_TYPES = (".md", ".pdf")
# Instructions, not sources: AGENTS.md tells the advisor how to find things and README.md points a person at it.
# Neither holds a fact anyone cites (shared/reference/AGENTS.md "How to cite"), so neither is listed or served.
REFERENCE_SKIP = ("agents.md", "readme.md")


def reference_dir():
    """The general reference library (course material, JLC pages): shared/reference/ of the install, git-tracked,
    read-only. The advisor reads it from the same place (workspace.describe), so the UI shows what the agent reads."""
    return workspace.REPO / "shared" / "reference"


def reference_files():
    """{name: path} of every general reference document. The name is the path relative to the reference folder with
    forward slashes ('jlc/pcb-capabilities.en.md'): unique, and exactly how AGENTS.md tells the advisor to cite it.
    Markdown and the PDFs that sit next to their extracted text; instructions are left out (REFERENCE_SKIP)."""
    root = reference_dir()
    if not root.is_dir():
        return {}
    out = {}
    for f in sorted(root.rglob("*")):
        if f.is_file() and f.suffix.lower() in REFERENCE_TYPES and f.name.lower() not in REFERENCE_SKIP:
            out[f.relative_to(root).as_posix()] = f
    return out


def reference_path(name):
    """The file of a reference name, or None. Only a name in the listing resolves, so '..', absolute paths and
    names of other files find nothing: there is no path to sanitise."""
    return reference_files().get(name)


_sha_memo = {}


def file_sha256(path):
    """sha256 of a file, kept until the file changes (a size or a time that differs): the 4 s poll lists the reference
    documents every time, and one of them is a 21 MB PDF."""
    st = path.stat()
    key = (str(path), st.st_size, st.st_mtime_ns)
    if key not in _sha_memo:
        _sha_memo[key] = hashlib.sha256(path.read_bytes()).hexdigest()
    return _sha_memo[key]


def folder_of(project=None):
    """Where documents are stored: a project's sources/ folder, or, with no
    project, the shared library."""
    return workspace.project_dir(project) / "sources" if project else cache()


def _safe(name):
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)[:120]


def _meta_path(path):
    return path.with_suffix(path.suffix + ".json")


def _read_meta(path):
    """The sidecar of a cached document as a dict; {} if there is none."""
    try:
        meta = json.loads(_meta_path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return meta if isinstance(meta, dict) else {}


def _download(url, timeout):
    """The bytes at a url. Every way a download fails comes out as SourceError
    with a one-line reason, so no caller has to know urllib's exception zoo."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        raise SourceError(f"{url}: HTTP {exc.code} {exc.reason}") from exc
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as exc:
        raise SourceError(f"{url}: {getattr(exc, 'reason', None) or exc}") from exc


def _check_kind(url, name, blob):
    """A name ending in .pdf must hold a PDF. A vendor site that suspects a bot
    answers 200 with an HTML challenge page, and saved under a .pdf name that
    is a citation nothing can verify. The header may follow a little junk (a
    BOM, blank lines), so look in the first KB, the way PDF readers do."""
    head = blob[:1024]
    if not name.lower().endswith(".pdf") or b"%PDF-" in head:
        return
    low = head.lower()
    what = "an HTML page" if b"<html" in low or b"<!doctype html" in low else "something that is not a PDF"
    raise SourceError(f"{url}: the server returned {what}, not a PDF. Download it by hand in a "
                      f"browser and add it from the Sources tab (Upload file).")


def fetch(url, name=None, timeout=45, project=None):
    """Download a document. With a project it goes into that project's sources/;
    without one it goes into the shared library, which is for GENERAL documents
    (a part's datasheet belongs to the project that uses the part: use get()).
    Returns the metadata dict. Raises SourceError when the download fails, is not
    what the name says, or would replace a different document already stored
    under that name."""
    folder = folder_of(project)
    where = f"project {project}'s sources" if project else "the shared library"
    name = _safe(name or url.rstrip("/").split("/")[-1] or "document.pdf")
    path = folder / name
    blob = _download(url, timeout)
    _check_kind(url, name, blob)
    # The sidecar describes the DOCUMENT - what it is, where it came from, what
    # it hashes to. All of that is the same on every machine, which is why the
    # file can be tracked in git at all.
    meta = {
        "name": name,
        "url": url,
        "sha256": hashlib.sha256(blob).hexdigest(),
        "bytes": len(blob),
    }
    # A name already holding a different document is not ours to reuse: chats and
    # BOM lines cite a document by its name. With no file on disk (a fresh clone
    # before `restore`) the sidecar is the record, unless it names this very url,
    # which is `restore` bringing it back.
    old = _read_meta(path)
    have = None
    if path.exists():
        have = hashlib.sha256(path.read_bytes()).hexdigest()
    elif old.get("url") != url:
        have = old.get("sha256")
    if have not in (None, meta["sha256"]):
        raise SourceError(
            f"{name} is already in {where} as a different file (url "
            f"{old.get('url') or 'unknown'}, sha256 {have[:12]}...). Not replacing it: "
            f"something may cite it. Save this one under another name, e.g. "
            f"get <project> {url} <other-name>")
    if not path.exists():
        folder.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
    # When the document is unchanged, leave the sidecar alone. `restore` warms
    # the cache on every fresh clone, and writing a new timestamp each time made
    # a tracked file dirty as a side effect of setting the project up - so
    # `git status` was never clean and nobody could see their own changes.
    # The first recorded origin wins, so the same file arriving from a mirror
    # does not rewrite it either.
    if old.get("sha256") == meta["sha256"]:
        return {**meta, **old}
    # bytes, not write_text: on Windows that turns every "\n" into "\r\n", and the
    # tracked sidecars are LF, so git would show a change that is only line endings
    _meta_path(path).write_bytes((json.dumps(meta, indent=2) + "\n").encode("utf-8"))
    return meta


def text_of(name, folder=None):
    """Plain text of a cached document, itself cached next to it. `folder` is a
    project's sources/ directory, tried before the shared library. A reference name
    ('jlc/pcb-capabilities.en.md') reads the reference document itself, with no cache."""
    ref = reference_path(name)
    if ref is not None:
        if ref.suffix.lower() == ".pdf":
            raise FileNotFoundError(f"{name} is a PDF: its text is in the .md files beside it")
        return ref.read_text(encoding="utf-8", errors="replace")
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


def verify(name, quote, project=None):
    """Is this quote actually in that document? The whole point of the module.
    With a project, that project's sources/ is searched before the shared library."""
    try:
        body = _norm(text_of(name, folder=folder_of(project) if project else None))
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
    """Copy a document of the shared library into the project, so the project folder
    stands alone. A general document is visible everywhere already; this is for a
    project that wants its own copy."""
    src = cache() / _safe(name)
    dst_dir = workspace.project_dir(project) / "sources"
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst_dir / src.name)
    if _meta_path(src).exists():
        shutil.copy2(_meta_path(src), _meta_path(dst_dir / src.name))
    return str(dst_dir / src.name)


def get(project, url, name=None):
    """Download straight into the project's sources/ - the whole of "add this
    datasheet to my board". Nothing goes to the shared library: that is for general
    documents, and a part's datasheet is this project's. Returns the metadata, plus
    where the file landed."""
    meta = fetch(url, name, project=project)
    return {**meta, "path": str(folder_of(project) / meta["name"])}


def unuse(project, name):
    """Take a document out of ONE project. The shared library is left alone: it is
    general material every project sees, and its .json is the tracked record of
    where it came from."""
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
    try:
        if cmd == "fetch":
            print(json.dumps(fetch(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None), indent=2))
        elif cmd == "verify":
            # verify <name> "<quote>" [project]: the project's sources/ is searched first
            print(json.dumps(verify(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None),
                             indent=2, ensure_ascii=False))
        elif cmd == "get":
            print(json.dumps(get(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None), indent=2))
        elif cmd == "use":
            print(use(sys.argv[2], sys.argv[3]))
        elif cmd == "unuse":
            print(json.dumps(unuse(sys.argv[2], sys.argv[3])))
        else:
            # list [project]: the shared library (downloaded documents, then the reference library by the name a
            # citation uses), then that project's own documents
            def own(folder):
                return [(f.name, f.stat().st_size) for f in sorted(folder.glob("*")) if f.suffix not in (".json", ".txt")]
            rows = [("shared", n, size) for n, size in own(cache())]
            rows += [("shared", name, f.stat().st_size) for name, f in reference_files().items()]
            if len(sys.argv) > 2:
                rows += [("project", n, size) for n, size in own(folder_of(sys.argv[2]))]
            for scope, name, size in rows:
                print(f"{scope:8s}{name} {size}" if len(sys.argv) > 2 else f"{name} {size}")
    except SourceError as exc:
        # one line a person (or the agent) can act on, not a traceback
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
