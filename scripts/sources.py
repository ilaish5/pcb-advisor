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
import urllib.parse
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


_LCSC_PDF = re.compile(rb"https://datasheet\.lcsc\.com/[A-Za-z0-9_\-./%]+?\.pdf")


def _viewer_pdf(url, blob):
    """The PDF a viewer page shows, or None. Only for LCSC's datasheet links (www.lcsc.com/datasheet/....pdf answers with an HTML
    page around the real file on datasheet.lcsc.com), and only when the page names exactly one such file."""
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if b"%PDF-" in blob[:1024] or not (host == "lcsc.com" or host.endswith(".lcsc.com")):
        return None
    found = {m.decode("ascii") for m in _LCSC_PDF.findall(blob)}
    return found.pop() if len(found) == 1 else None


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
    blob = _download(url, timeout)
    inner = _viewer_pdf(url, blob)
    if inner:                       # LCSC's "datasheet" link is a viewer page: the document is the PDF it shows
        blob = _download(inner, timeout)
    if "." not in name and b"%PDF-" in blob[:1024]:     # JLC's datasheet links end in a bare file id
        name += ".pdf"
    path = folder / name
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
    _record_quality(path)
    return _read_meta(path) or meta


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
            text = "\f".join((p.extract_text() or "") for p in reader.pages)    # \f = page break (head_of), a space to every other reader
        except Exception:
            import subprocess
            text = subprocess.run(["pdftotext", str(path), "-"],
                                  capture_output=True, encoding="utf-8",
                                  errors="replace").stdout
    else:
        text = path.read_text(encoding="utf-8", errors="replace")
    if text.strip():                # an empty extraction is not cached: it would stay "no text" after a better extractor is installed
        txt_path.write_text(text, encoding="utf-8")
    return text


_CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")
_PIN_HEADING = re.compile(r"pin\s*(?:configuration|description|assignment|definition|function)s?|pinout|terminal\s*(?:function|assignment)", re.I)


def quality(text):
    """How readable a document's extracted text is: {pages, chars_per_page, cjk_ratio, lang, has_pin_heading, state, why, score}.
    state "none" (nothing extracted), "poor" (mostly CJK, or a few characters a page: a scan or an image-only file) or "good".
    Cheap and pure, so it can run on the text at fetch, upload and adopt."""
    text = text or ""
    letters = re.sub(r"\s", "", text)
    pages = max(1, len([p for p in text.split("\f") if p.strip()])) if letters else 0
    cjk = len(_CJK.findall(letters)) / len(letters) if letters else 0.0
    cpp = round(len(letters) / pages) if pages else 0
    lang = "zh" if cjk > 0.2 else ("en" if letters else "")
    state, why = "good", ""
    if not letters:
        state, why = "none", "no text could be extracted (a scan or an image-only file)"
    elif cjk > 0.2:
        state, why = "poor", "the text is mostly Chinese/Japanese/Korean, so a pin table in it cannot be matched"
    elif cpp < 150 and pages >= 3:
        state, why = "poor", f"only about {cpp} characters a page could be read (a scan?)"
    return {"pages": pages, "chars_per_page": cpp, "cjk_ratio": round(cjk, 3), "lang": lang,
            "has_pin_heading": bool(_PIN_HEADING.search(text)), "state": state, "why": why,
            "score": 0 if state == "none" else (0.3 if state == "poor" else 1.0)}


def _quality_path(path):
    """Where a document's text quality is kept: <doc>.quality.txt beside the extracted text. Derived data, so it is never
    in the tracked .json sidecar (the sidecars of general sources must stay byte-identical on every machine); a .txt is
    untracked and skipped by every document list."""
    return path.with_suffix(path.suffix + ".quality.txt")


def _record_quality(path):
    """Write the text quality of a PDF beside it the first time it is read (fetch, upload, adopt). Never rewrites one."""
    qp = _quality_path(path)
    if path.suffix.lower() != ".pdf" or qp.exists():
        return
    try:
        qp.write_bytes((json.dumps(quality(text_of(path.name, path.parent)), indent=2) + "\n").encode("utf-8"))
    except Exception:
        pass            # a document nobody can read keeps no record; the list says "not read"


_quality_memo = {}


def text_state(path):
    """not_read | good | poor | none for a document of the list: from its quality record, else from the text cached beside it. A PDF is
    never extracted here (the list is polled): one with neither is "not_read"."""
    if path.suffix.lower() != ".pdf":
        return "good" if path.suffix.lower() in (".md", ".txt") else "not_read"
    qp = _quality_path(path)
    if qp.exists():
        try:
            q = json.loads(qp.read_text(encoding="utf-8"))
            if isinstance(q, dict) and q.get("state"):
                return q["state"]
        except (OSError, ValueError):
            pass
    txt = path.with_suffix(path.suffix + ".txt")
    if not txt.exists():
        return "not_read"
    st = txt.stat()
    key = (str(txt), st.st_size, st.st_mtime_ns)
    if key not in _quality_memo:
        _quality_memo[key] = quality(txt.read_text(encoding="utf-8", errors="replace"))["state"]
    return _quality_memo[key]


HEAD_PAGES = 3
LAYOUT_PAGES = 150          # a datasheet's pin table is in its first 150 pages; a reference manual is not read to its end


def head_of(name, folder=None, pages=HEAD_PAGES):
    """The first pages of a document's text (what a datasheet says about itself on its front). A cache written before
    page breaks were kept (no form feed in it) gives its first 4000 characters per page instead."""
    text = text_of(name, folder)
    return "\f".join(text.split("\f")[:pages]) if "\f" in text else text[:4000 * pages]


def layout_text_of(name, folder=None):
    """The document's text with its columns kept (pypdf's layout mode, else `pdftotext -layout`), cached next to the PDF as
    <name>.layout.txt: a table row stays on one line with its cells apart. None when the document is not a PDF or no
    extractor can read it (the plain text is all there is)."""
    if reference_path(name) is not None:
        return None
    path = cache() / _safe(name)
    if folder is not None and (pathlib.Path(folder) / _safe(name)).exists():
        path = pathlib.Path(folder) / _safe(name)
    if not path.exists() or path.suffix.lower() != ".pdf":
        return None
    cached = path.with_suffix(path.suffix + ".layout.txt")
    if cached.exists():
        return cached.read_text(encoding="utf-8", errors="replace") or None
    text = ""
    try:
        import pypdf
        reader = pypdf.PdfReader(str(path))
        text = "\f".join((p.extract_text(extraction_mode="layout") or "") for p in reader.pages[:LAYOUT_PAGES])
    except Exception:
        try:
            import subprocess
            text = subprocess.run(["pdftotext", "-layout", "-l", str(LAYOUT_PAGES), str(path), "-"],
                                  capture_output=True, encoding="utf-8", errors="replace").stdout
        except OSError:
            text = ""
    if text.strip():
        cached.write_text(text, encoding="utf-8")
    return text or None


def _wild_hit(token, key):
    """STM32G031x6 for STM32G031F6P6: a token written with x for a letter or digit (six characters or more, a digit, an x
    after its third character) that the start of the key fits."""
    if len(token) < 6 or len(token) > len(key) or "x" not in token[3:] or not any(c.isdigit() for c in token):
        return False
    return re.fullmatch(token.replace("x", "[a-z0-9]"), key[:len(token)]) is not None


def mentions_part(head, mpn):
    """Does this text (a datasheet's first pages) name the part? The MPN itself, its family (NE555 for NE555DR: an ordering
    suffix cut off), its base before a "-" (AMS1117-3.3 in a datasheet of the AMS1117) or a family written with a
    wildcard letter (STM32G031x6)."""
    key = _key(mpn)
    if len(key) < 4:
        return False
    if key in _key(head):
        return True
    toks = _tokens(head)
    if any(_family_hit(t, key) or _wild_hit(t, key) for t in toks):
        return True
    base = _key(re.split(r"[-_/\s]", str(mpn).strip())[0])          # AMS1117-3.3 -> AMS1117: the voltage / option after a "-"
    return (base != key and len(base) >= 5 and sum(c.isdigit() for c in base) >= 3
            and any(_family_hit(t, base) for t in toks))


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


DOC_SUFFIXES = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".html", ".htm", ".zip")


def adopt(project):
    """Register the documents the student dropped into the project's sources/ by hand: a PDF with no
    sidecar gets one (name, sha256, no url), so it can be cited and verified like a downloaded one.
    Returns the names registered."""
    folder = folder_of(project)
    added = []
    for f in sorted(folder.glob("*")) if folder.is_dir() else []:
        if f.suffix.lower() not in DOC_SUFFIXES or f.name.startswith(".") or not f.is_file() or _meta_path(f).exists():
            continue
        meta = {"name": f.name, "url": None, "sha256": file_sha256(f), "bytes": f.stat().st_size,
                "origin": "added by the student"}
        _meta_path(f).write_bytes((json.dumps(meta, indent=2) + "\n").encode("utf-8"))
        _record_quality(f)
        added.append(f.name)
    return added


def find_for(project, mpn):
    """The project's document whose file name carries the part number (case and punctuation ignored)."""
    adopt(project)
    key = re.sub(r"[^a-z0-9]", "", (mpn or "").lower())
    if len(key) < 4:
        return None
    for f in sorted(folder_of(project).glob("*")):
        if f.suffix.lower() == ".pdf" and key in re.sub(r"[^a-z0-9]", "", f.name.lower()):
            return f.name
    return None


def _key(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _family_hit(token, key):
    """One of two alphanumeric strings is the other with an ordering suffix cut off (NE555 / NE555DR,
    CD4017B / CD4017BM96). At least 4 characters, one digit, and the cut must not fall inside a run of
    digits (NE55 is not NE555)."""
    if token == key:
        return len(token) >= 4
    short, long_ = sorted((token, key), key=len)
    if len(short) < 4 or not any(c.isdigit() for c in short) or not long_.startswith(short):
        return False
    return not (short[-1].isdigit() and long_[len(short)].isdigit())


def _tokens(text):
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def match_documents(project, lines):
    """Which project document belongs to which BOM line. `lines` are (line key, MPN) pairs still without a
    datasheet. Returns ({line key: {"name", "how"}}, [names no line claims]). `how` is 'name' (the full MPN is in the
    file name), 'family' (the MPN without its ordering suffix is) or 'text' (it is in the first pages).
    A file that fits two lines, or a line that fits two files at the same level, is left alone."""
    adopt(project)
    folder = folder_of(project)
    docs = [f.name for f in sorted(folder.glob("*")) if f.suffix.lower() == ".pdf" and f.is_file()]
    lines = [(k, _key(m)) for k, m in lines if len(_key(m)) >= 4]
    found = {}          # file -> {level: set of line keys}
    for name in docs:
        stem_key, toks = _key(name), _tokens(pathlib.Path(name).stem)
        by_name = {k for k, m in lines if m in stem_key}
        by_family = {k for k, m in lines if any(_family_hit(t, m) for t in toks)}
        if by_name or by_family:
            found[name] = {"name" if by_name else "family": by_name | by_family}
    for name in docs:
        if name in found or not lines:
            continue
        try:
            head = text_of(name, folder)[:6000]
        except Exception:
            continue
        head_key, toks = _key(head), _tokens(head)
        hit = {k for k, m in lines if m in head_key or any(_family_hit(t, m) for t in toks)}
        if hit:
            found[name] = {"text": hit}
    claimed = {}        # line key -> [(level rank, file)]
    for name, by_level in found.items():
        level, keys = next(iter(by_level.items()))
        if len(keys) == 1:
            claimed.setdefault(next(iter(keys)), []).append((("name", "family", "text").index(level), name, level))
    out = {}
    for key, cands in claimed.items():
        cands.sort()
        best = [c for c in cands if c[0] == cands[0][0]]
        if len(best) == 1 or cands[0][2] == "name":
            out[key] = {"name": best[0][1], "how": best[0][2]}
    used = {v["name"] for v in out.values()}
    return out, [n for n in docs if n not in used]


def unuse(project, name):
    """Take a document out of ONE project. The shared library is left alone: it is
    general material every project sees, and its .json is the tracked record of
    where it came from."""
    target = workspace.project_dir(project) / "sources" / _safe(name)
    removed = []
    for p in (target, _meta_path(target), target.with_suffix(target.suffix + ".txt"), _quality_path(target)):
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
        elif cmd == "text":
            # text <project> <doc> [find]: a document's plain text (a PDF's is extracted once and cached beside it as
            # <doc>.txt); with `find`, only the lines that contain it (case-insensitive), each with its line number
            try:
                body = text_of(sys.argv[3], folder_of(sys.argv[2]))
            except FileNotFoundError as exc:
                # only "not in the cache" means the document is missing; a missing pdftotext or a reference PDF
                # ("its text is in the .md files beside it") keeps its own message
                if "not in the cache" not in str(exc):
                    raise SourceError(str(exc)) from exc
                raise SourceError(f"{sys.argv[3]} is not in project {sys.argv[2]}'s sources nor the shared library "
                                  f"(sources.py list {sys.argv[2]})") from exc
            if not body.strip():
                print(f"{sys.argv[3]}: no text could be extracted (a scanned or image-only PDF)")
            elif len(sys.argv) > 4:
                hits = [f"{i}: {ln}" for i, ln in enumerate(body.splitlines(), 1) if sys.argv[4].lower() in ln.lower()]
                print("\n".join(hits) if hits else f"no line of {sys.argv[3]} contains {sys.argv[4]!r} (the document has text)")
            else:
                print(body)
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
                adopt(sys.argv[2])
                rows += [("project", n, size) for n, size in own(folder_of(sys.argv[2]))]
            for scope, name, size in rows:
                print(f"{scope:8s}{name} {size}" if len(sys.argv) > 2 else f"{name} {size}")
    except SourceError as exc:
        # one line a person (or the agent) can act on, not a traceback
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
