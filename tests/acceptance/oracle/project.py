"""Oracle readers for the project folder (idea, idea-versions, bom, bom-log, proposals, chats, sources, SchDoc).

Independent of product code (A2): plain json / re / olefile only. Everything here reads files that the product wrote and
returns plain Python data; no check logic and no status decisions live in this module.

Time handling: log rows carry millisecond ISO stamps, chat rows second stamps. `tkey` pads both to milliseconds so they
compare as strings.
"""
from __future__ import annotations

import json
import pathlib
import re
import struct
from typing import Any, Iterable

try:  # third-party, same package the PcbDoc oracle uses
    import olefile
except ImportError:  # pragma: no cover - a missing dependency is reported by the metric, not hidden
    olefile = None


# ----------------------------------------------------------------------------- generic readers
def read_json(path: pathlib.Path) -> Any:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def read_jsonl(path: pathlib.Path) -> list[dict]:
    p = pathlib.Path(path)
    if not p.is_file():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def tkey(ts: str, tail: str = ".000") -> str:
    """Sortable key for 'YYYY-MM-DDTHH:MM:SS[.mmm]'."""
    ts = str(ts or "")
    return ts if "." in ts else ts + tail


def minutes_between(a: str, b: str) -> float:
    import datetime as dt
    fa = dt.datetime.fromisoformat(tkey(a))
    fb = dt.datetime.fromisoformat(tkey(b))
    return (fb - fa).total_seconds() / 60.0


def norm_ws(s: str) -> str:
    """Whitespace-normalised, case-folded text (W16)."""
    return re.sub(r"\s+", " ", s or "").strip().casefold()


def norm_alnum(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


# ----------------------------------------------------------------------------- part numbers
_FAMILY = re.compile(r"[A-Z]+\d+[A-Z]?\d*")


def family(mpn: str) -> str:
    """Ordering-code family of an MPN: letters+digits(+one variant letter+digits), separators removed.
    ABC1234XU6 -> ABC1234, XY6211A33PG-N -> XY6211A33."""
    s = norm_alnum(mpn)
    m = _FAMILY.match(s)
    return m.group(0) if m else s


def mentions_part(text: str, mpn: str) -> bool:
    """True when `text` names the part: its normalised ordering-code family occurs in the normalised text."""
    fam = family(mpn)
    if len(fam) < 4:
        return False
    return fam in norm_alnum(text)


def tokens(text: str) -> list[str]:
    """Part-number-like tokens of a text: start with a letter, contain a digit."""
    return re.findall(r"[A-Za-z][A-Za-z0-9]*(?:[-.][A-Za-z0-9]+)*\d[A-Za-z0-9]*(?:[-.][A-Za-z0-9]+)*", text or "")


# ----------------------------------------------------------------------------- project loader
class Project:
    """Lazy, read-only view of one project folder."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = pathlib.Path(root)
        self._cache: dict[str, Any] = {}

    def path(self, *parts: str) -> pathlib.Path:
        return self.root.joinpath(*parts)

    def _get(self, key: str, fn):
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    @property
    def idea(self) -> dict:
        return self._get("idea", lambda: read_json(self.path("idea.json")))

    @property
    def versions(self) -> list[dict]:
        return self._get("versions", lambda: read_json(self.path("idea-versions.json"))
                         if self.path("idea-versions.json").is_file() else [])

    @property
    def bom(self) -> list[dict]:
        def f():
            d = read_json(self.path("bom.json"))
            return d["lines"] if isinstance(d, dict) and "lines" in d else d
        return self._get("bom", f)

    @property
    def bomlog(self) -> list[dict]:
        return self._get("bomlog", lambda: sorted(read_jsonl(self.path("bom-log.jsonl")), key=lambda r: tkey(r["ts"])))

    @property
    def proposals(self) -> list[dict]:
        return self._get("proposals", lambda: read_jsonl(self.path("proposals.jsonl")))

    @property
    def chat(self) -> list[dict]:
        """Every chat message of every session, oldest first. Each row carries `_file`."""
        def f():
            rows = []
            for p in sorted(self.path("chats").glob("*.jsonl")):
                for r in read_jsonl(p):
                    r["_file"] = p.name
                    rows.append(r)
            return sorted(rows, key=lambda r: tkey(r["ts"]))
        return self._get("chat", f)

    @property
    def librarylog(self) -> list[dict]:
        return self._get("liblog", lambda: read_jsonl(self.path("library-log.jsonl")))

    @property
    def sheetlog(self) -> list[dict]:
        return self._get("sheetlog", lambda: read_jsonl(self.path("sheet-log.jsonl")))

    @property
    def project_json(self) -> dict:
        return self._get("pj", lambda: read_json(self.path("project.json")) if self.path("project.json").is_file() else {})

    def netlist_parts(self) -> list[dict]:
        out = []
        for p in sorted(self.path("netlist").glob("*.json")):
            d = read_json(p)
            for part in d.get("parts", []):
                part = dict(part)
                part["_sheet"] = d.get("id", p.stem)
                out.append(part)
        return out

    def source_pages(self, name: str) -> list[str] | None:
        """Text of sources/<name>.txt split on form feed (one chunk per page), or None when there is no text."""
        p = self.path("sources", name + ".txt")
        if not p.is_file():
            return None
        return p.read_text(encoding="utf-8", errors="replace").split("\f")

    def source_text(self, name: str) -> str | None:
        pages = self.source_pages(name)
        return None if pages is None else "\n".join(pages)

    def source_names(self) -> list[str]:
        """Names of the sources that have a text file (sources/<name>.txt, quality and layout files excluded)."""
        return sorted(f.name[:-4] for f in self.path("sources").glob("*.txt")
                      if not f.name.endswith((".quality.txt", ".layout.txt")))

    def cite_records(self) -> list[dict]:
        """Every record of every chats/*.cites.json: [{file, loc, status, at}] (keys are 'file|location')."""
        out = []
        for p in sorted(self.path("chats").glob("*.cites.json")):
            for at, rec in read_json(p).items():
                for key, v in (rec.get("items") or {}).items():
                    f, _, loc = key.partition("|")
                    out.append({"file": f, "loc": loc, "status": v.get("status"), "at": at})
        return out

    def order_manifests(self) -> list[pathlib.Path]:
        return sorted(self.path("exports").glob("*order_manifest.json"))

    def export_texts(self) -> dict[str, str]:
        """Human-readable export documents of the project: README, notes, text/markdown files in exports/."""
        out = {}
        for rel in ("README.md", "notes.md"):
            p = self.path(rel)
            if p.is_file():
                out[rel] = p.read_text(encoding="utf-8", errors="replace")
        for p in sorted(self.path("exports").glob("*")):
            if p.suffix.lower() in (".md", ".txt"):
                out["exports/" + p.name] = p.read_text(encoding="utf-8", errors="replace")
        return out


# ----------------------------------------------------------------------------- BOM replay
def replay_bom(rows: Iterable[dict], upto: str | None = None) -> dict[str, dict]:
    """Fold bom-log rows (oldest first) into {line: fields}. `upto` is an inclusive time stamp (second resolution ok)."""
    lim = tkey(upto, ".999") if upto else None
    state: dict[str, dict] = {}
    for r in rows:
        if lim and tkey(r["ts"]) > lim:
            break
        st = state.setdefault(r["line"], {})
        for k, v in (r.get("changes") or {}).items():
            st[k] = v
    return state


def bom_totals(state: dict[str, dict]) -> tuple[int, int]:
    """(lines, refs) of a replayed BOM; a line with no refs counts one ref (its key)."""
    lines = [s for s in state.values() if s.get("refs") or s.get("mpn") or s.get("value")]
    refs = sum(len(s["refs"]) if s.get("refs") else 1 for s in lines)
    return len(lines), refs


def duplicate_episodes(rows: Iterable[dict]) -> list[dict]:
    """Replay bom-log; return maximal episodes in which one ref sits on two or more lines.
    [{ref, lines, start, end|None}] (end None = still duplicated after the last row)."""
    state: dict[str, set] = {}
    open_ep: dict[tuple, dict] = {}
    done: list[dict] = []
    for r in rows:
        ch = r.get("changes") or {}
        if "refs" in ch:
            state[r["line"]] = set(ch["refs"] or [])
        owners: dict[str, list] = {}
        for line, refs in state.items():
            for ref in refs:
                owners.setdefault(ref, []).append(line)
        now = {(ref, tuple(sorted(ls))) for ref, ls in owners.items() if len(ls) > 1}
        for key in list(open_ep):
            if key not in now:
                ep = open_ep.pop(key)
                ep["end"] = r["ts"]
                done.append(ep)
        for key in now:
            if key not in open_ep:
                open_ep[key] = {"ref": key[0], "lines": list(key[1]), "start": r["ts"], "end": None}
    return done + list(open_ep.values())


# ----------------------------------------------------------------------------- chat
SRC_CITE = re.compile(r"\{\{src:([^|}]*)\|([^}]*)\}\}")
PAGE_LOC = re.compile(r"^\s*(?:pp?\.|page)\s*(\d+)\s*(?:,\s*(.*))?$", re.S | re.I)


def page_cites(text: str) -> list[dict]:
    """Every `{{src:file|p. N, quote}}` page cite of an agent message: [{file, page, quote, raw}]."""
    out = []
    for m in SRC_CITE.finditer(text or ""):
        pm = PAGE_LOC.match(m.group(2))
        if pm:
            out.append({"file": m.group(1).strip(), "page": int(pm.group(1)),
                        "quote": (pm.group(2) or "").strip(), "raw": m.group(0)})
    return out


def approval_messages(chat: list[dict]) -> list[dict]:
    return [r for r in chat if r.get("role") == "agent" and r.get("decision") == "approved"]


# ----------------------------------------------------------------------------- SchDoc (raw olefile)
def schdoc_records(path: pathlib.Path) -> list[dict]:
    """Parse the FileHeader stream of an Altium SchDoc: a list of {KEY: value} dicts (keys upper-cased)."""
    if olefile is None:
        raise RuntimeError("olefile is not installed")
    o = olefile.OleFileIO(str(path))
    try:
        data = o.openstream("FileHeader").read()
    finally:
        o.close()
    out, i = [], 0
    while i + 4 <= len(data):
        ln = struct.unpack("<I", data[i:i + 4])[0] & 0xFFFFFF
        i += 4
        blk = data[i:i + ln]
        i += ln
        if b"RECORD=" not in blk[:40]:
            continue
        kv = {}
        for part in blk.rstrip(b"\x00").decode("latin-1").split("|"):
            if "=" in part:
                k, v = part.split("=", 1)
                kv[k.upper()] = v
        out.append(kv)
    return out


def schdoc_designators(path: pathlib.Path) -> set[str]:
    return {r.get("TEXT", "") for r in schdoc_records(path)
            if r.get("RECORD") == "34" and r.get("NAME") == "Designator"}


def schdoc_component_names(path: pathlib.Path) -> set[str]:
    return {r.get("LIBREFERENCE", "") for r in schdoc_records(path) if r.get("RECORD") == "1"}


def ole_storage_names(path: pathlib.Path) -> set[str]:
    """Top-level storage names of an Altium library (one per component / footprint)."""
    if olefile is None:
        raise RuntimeError("olefile is not installed")
    o = olefile.OleFileIO(str(path))
    try:
        return {e[0] for e in o.listdir()}
    finally:
        o.close()


def schdoc_state_at(altium: pathlib.Path, sheet_file: str, ts: str) -> tuple[pathlib.Path | None, str]:
    """The SchDoc as it was on disk at `ts`: the first `.advisor-backup/<yyyymmdd-hhmmss>/<sheet_file>` taken at or after
    `ts` holds the file as it was just before the next rewrite, i.e. the state at `ts`. Falls back to the current file.
    Returns (path, how)."""
    b = pathlib.Path(altium) / ".advisor-backup"
    want = tkey(ts)[:19].replace("-", "").replace(":", "").replace("T", "-")
    best = None
    if b.is_dir():
        for d in sorted(b.iterdir()):
            f = d / sheet_file
            if f.is_file() and d.name >= want:
                best = f
                break
    if best:
        return best, "backup " + best.parent.name
    cur = pathlib.Path(altium) / sheet_file
    return (cur if cur.is_file() else None), "current file"
