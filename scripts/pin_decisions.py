"""Stream B: the student's decision about a part's pins, as a record that can be read, undone and followed downstream.

"Accept as is" used to be one flag (library entry `pins_accepted`) with no date, no basis and no undo. A decision is now
`pin_decision` on the part's library entry (library-log.jsonl, by "student"):

    {"id", "status": "accepted" | "revoked", "basis": "datasheet_page" | "polarity" | "blind" | "legacy",
     "reason" (optional), "evidence": [{"doc", "sha256", "page"}], "fingerprint", "ts"}

The basis is worked out here, never asked for: a datasheet page the student looked at is "datasheet_page", a diode/LED
without one "polarity", anything else "blind". The decision stands only while the part's pin fingerprint is the one it was
made against (the wired pins by number and name, MPN, package, LCSC code; for a diode / LED also the net names of its two
pins, so swapping anode and cathode asks again): rename a pin, change the MPN or wire a pin that was open and the part asks
again, with the reason "accepted on <date>, pins changed since". Moving a pin to another net does not (except for D / LED). A legacy `pins_accepted: true` is grandfathered: it is stamped once with the
current fingerprint (basis "legacy") and then follows the same rule.

The agent can never write any of this (serve._agent_may_set_library drops every key but a few); the routes below are the
student's buttons. R/C/L/crystal and the other simple parts are never asked about (store.pins_status gives them "").
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ext  # noqa: E402
import lineage  # noqa: E402
import pinnames  # noqa: E402
import store  # noqa: E402

BASES = ("datasheet_page", "polarity", "blind", "legacy")
_HEADINGS = re.compile(r"pin\s*(?:configuration|description|assignment|definition|function|out)|pinout|terminal\s*(?:function|assignment)|top\s*view",
                       re.I)


# ---------------------------------------------------------------- the fingerprint

def _line(project, line):
    return line if isinstance(line, dict) else store._line_of(project, line)


FP_VERSION = 2       # 2 added the diode / LED polarity nets; a decision without "fpv" was made against version 1


def fingerprint(project, line, version=FP_VERSION):
    """What a pin decision was made about: sorted (ref, number, name) of the line's parts on the sheets, plus the MPN,
    the package and the declared LCSC code. Never the whole part dict (a drawn position or a note must not undo a decision).
    Only wired pins count, and only by number and name: the decision is about which number is which pin where it matters.
    Moving a pin to another net keeps it; marking open pins NC (any no-connect spelling, pinnames.is_nc_net) or adding a built
    symbol's unlisted pins as NC keeps it; wiring a pin that was open or NC, or unwiring one, is a change.
    One exception: a diode / LED is decided on polarity and its pins are often named just "1" / "2", so the net names of its
    pins are part of the fingerprint: swapping anode and cathode nets asks again. A decision is compared with the version it
    was made against, so a change of this rule never asks the student again about pins that did not change."""
    line = _line(project, line)
    return store.memoised(("fingerprint", version, project, line.get("key"), tuple(line.get("refs") or ()), line.get("mpn"),
                           line.get("package"), line.get("lcsc")), lambda: _fingerprint(project, line, version))


def _fingerprint(project, line, version=FP_VERSION):
    refs = set(line.get("refs") or [])
    rows, nets = [], []
    for sh in store.sheet_ids(project):
        for part in store.load_sheet(project, sh).get("parts", []):
            if part.get("ref") in refs:
                for p in part.get("pins", []):
                    net = str(p.get("net") or "").strip()
                    if net and not pinnames.is_nc_net(net):
                        rows.append([part["ref"], str(p.get("num", p.get("number", ""))), str(p.get("name") or "")])
                    nets.append([part["ref"], str(p.get("num", p.get("number", ""))), "" if pinnames.is_nc_net(net) else net.upper()])
    doc = {"pins": sorted(rows), "mpn": line.get("mpn") or "", "package": line.get("package") or "", "lcsc": line.get("lcsc") or ""}
    if version >= 2 and store._polarised_only(line):
        doc["polarity_nets"] = sorted(nets)
    return lineage._digest(doc)


def state(project, line, entry):
    """(accepted, note): accepted is the decision dict while it stands (a legacy flag counts, basis "legacy"), else None.
    note says why a decision no longer stands ("accepted on 2026-11-20, pins changed since"), else ''.
    Without a project the fingerprint cannot be read: the decision is taken as current."""
    entry = entry or {}
    dec = entry.get("pin_decision")
    if not dec:
        return ({"status": "accepted", "basis": "legacy", "ts": "", "id": "legacy"}, "") if entry.get("pins_accepted") else (None, "")
    if dec.get("status") != "accepted":
        return None, ""
    if project and dec.get("fingerprint") and dec["fingerprint"] != fingerprint(project, line, dec.get("fpv", 1)):
        return None, f"accepted on {str(dec.get('ts') or '')[:10] or 'an earlier day'}, pins changed since"
    return dec, ""


def current(project, key):
    """The standing decision of a BOM line key, or None."""
    return state(project, _line(project, key), store.library_parts(project).get(key))[0]


# ---------------------------------------------------------------- accept / revoke

def _basis(line, evidence):
    if any(e.get("page") for e in evidence):
        return "datasheet_page"
    return "polarity" if store._polarised_only(line) else "blind"


def _refresh_manifest(project):
    """Keep exports/<p>_order_manifest.json current after a decision changes: never a failed accept because the file could not be written."""
    try:
        write_manifest(project)
    except Exception:       # noqa: BLE001
        pass


def accept(project, key, evidence=None, reason="", wrong=None, basis=None, group=False):
    """The student says the pins match. {ok, line, decision, changed}. Idempotent: a second accept of the same fingerprint
    writes nothing. `wrong`, a list of pin numbers the student marked wrong, makes it a conflict instead (no decision).
    `group`: the identical parts of the same question (group_lines) are accepted with it, each with its own fingerprint and
    record; the result lists them in `also`."""
    sibs = group_lines(project, key) if group and not wrong else []        # before the accept: an accepted line leaves the list
    res = _accept(project, key, evidence, reason, wrong, basis)
    if sibs and res.get("ok"):
        res["also"] = []
        for other in sibs:
            if other != res["line"]:
                _accept(project, other, evidence, reason, None, basis)
                res["also"].append(other)
    return res


def valid_evidence(project, evidence):
    """The evidence that holds: a datasheet that is in the project, a page number, and a sha256 (when one is given) equal to that file's own.
    Anything else (a name nobody can open, a made-up hash, no page) is dropped, so it can never stand in for a reason."""
    import sources
    out = []
    for e in evidence or []:
        if not isinstance(e, dict) or not str(e.get("doc") or ""):
            continue
        page = int(e["page"]) if str(e.get("page") or "").isdigit() else 0
        path = sources.document_path(project, str(e["doc"]))
        if not page or path is None:
            continue
        sha = str(e.get("sha256") or "")
        if sha and sha != _sha256(path):
            continue
        out.append({"doc": str(e["doc"]), "sha256": sha, "page": page})
    return out


def _sha256(path):
    import lineage
    try:
        return lineage.sha256_file(path)
    except Exception:       # noqa: BLE001
        return ""


def _evidence_reason(evidence):
    return "Matches the datasheet pin table, " + "; ".join(f"page {e['page']} of {e['doc']}" for e in evidence[:3])


def _accept(project, key, evidence=None, reason="", wrong=None, basis=None):
    line = store._line_of(project, key)
    key = line["key"]
    if not store.has_wired_pins(project, line):
        # nothing is wired: an accept would record a decision about no pins, and later wiring would look confirmed
        return {"ok": False, "line": key, "decision": None, "changed": False, "why": "no pin of this part is wired yet: there is nothing to confirm"}
    if wrong:
        pins = ", ".join(str(w) for w in wrong)
        store.add_library(project, key, {"verify": "mismatch", "method": "", "evidence": "", "accepted": False,
                                         "issues": f"you marked pin {pins} as wrong against the datasheet",
                                         "pin_decision": None, "pins_accepted": False, "verified_at": store.now()}, by="student")
        store.refresh_pins_source(project)
        return {"ok": True, "line": key, "decision": None, "flagged": [str(w) for w in wrong]}
    entry = store.library_parts(project).get(key)
    standing, _ = state(project, line, entry)
    if standing and standing.get("basis") != "legacy":
        return {"ok": True, "line": key, "decision": standing, "changed": False}
    evidence = valid_evidence(project, evidence)
    if evidence and not str(reason or "").strip():          # the reason of a datasheet-backed accept is what the evidence says, never made up
        reason = _evidence_reason(evidence)
    dec = {"id": f"pd-{store.now_ms()}", "status": "accepted", "basis": basis if basis in BASES else _basis(line, evidence),
           "reason": str(reason or "").strip()[:300], "evidence": evidence, "fingerprint": fingerprint(project, line), "fpv": FP_VERSION, "ts": store.now()}
    store.add_library(project, key, {"pin_decision": dec, "pins_accepted": False}, by="student")
    store.refresh_pins_source(project)
    _refresh_manifest(project)
    return {"ok": True, "line": key, "decision": dec, "changed": True}


def revoke(project, key):
    """The student takes the decision back: the part is unverified again (the gate closes). Idempotent."""
    line = store._line_of(project, key)
    entry = store.library_parts(project).get(line["key"]) or {}
    old = entry.get("pin_decision") or {}
    if not (old.get("status") == "accepted" or (not old and entry.get("pins_accepted"))):
        return {"ok": True, "line": line["key"], "changed": False}
    dec = {**old, "status": "revoked", "revoked_at": store.now()}
    store.add_library(project, line["key"], {"pin_decision": dec, "pins_accepted": False}, by="student")
    store.refresh_pins_source(project)
    _refresh_manifest(project)
    return {"ok": True, "line": line["key"], "changed": True}


def remaining(project):
    """The parts a single "Accept all remaining" confirm covers: unverified (no conflict with a datasheet: a conflict is looked at
    one by one). [{line, refs, mpn, issues}]."""
    return [{"line": r["line"], "refs": r["refs"], "mpn": r["mpn"], "issues": r["issues"]}
            for r in store.pins_to_resolve(project) if r["status"] == "unverified"]


# ---------------------------------------------------------------- one question for identical parts

_NO_MPN = ("", "—", "-", "none")


def _kind_of(line):
    pre = {store._prefix_of(r) for r in line.get("refs") or []}
    if pre and pre <= set(store.POLARISED_PREFIXES):
        return "polarised"
    if pre and pre <= set(store.CONNECTOR_PREFIXES):
        return "connector"
    return "ic"


def group_key(project, line):
    """What makes two BOM lines ONE question: the same kind, MPN, footprint, LCSC code and the same pin pattern on every part
    (pin number, name and whether it is wired or open / NC). Net names are not part of it, so five LEDs on five nets are one question,
    but a copy with another pin wired, another name or another footprint is not. Each line keeps its own fingerprint and decision:
    grouping only decides what is asked once, never what is recorded. None (no group: it is asked alone) when the line has no
    MPN or no footprint to tell it by, or when its own parts differ from each other."""
    line = line if isinstance(line, dict) else store._line_of(project, line)
    mpn = str(line.get("mpn") or "").strip().casefold()
    fp = str((store.library_manifest(project).get(line.get("key")) or {}).get("footprint") or line.get("package") or "").strip().casefold()
    if mpn in _NO_MPN or not fp or not line.get("refs"):
        return None
    pats = {}
    for sh in store.sheet_ids(project):
        for part in store.load_sheet(project, sh).get("parts", []):
            if part.get("ref") in line["refs"]:
                pats.setdefault(part["ref"], []).extend(
                    (store._pin_num(p), str(p.get("name") or "").strip().casefold(),
                     bool(str(p.get("net") or "").strip()) and not pinnames.is_nc_net(str(p.get("net"))))
                    for p in part.get("pins", []))
    shapes = {tuple(sorted(v)) for v in pats.values()}
    if len(pats) != len(line["refs"]) or len(shapes) != 1:
        return None
    return (_kind_of(line), mpn, fp, str(line.get("lcsc") or "").strip().casefold(), shapes.pop())


def group_lines(project, key):
    """The BOM lines asked together with this one (itself first): the unverified lines that share its group_key; just itself when it has none."""
    line = store._line_of(project, key)
    gk = group_key(project, line)
    out = [line["key"]]
    if gk is None:
        return out
    for r in store.pins_to_resolve(project):
        if r["status"] == "unverified" and r["line"] != line["key"]:
            other = store._line_of(project, r["line"])
            if group_key(project, other) == gk:
                out.append(other["key"])
    return out


def questions(project, rows=None):
    """What the student is asked, one entry per question: [{id, lines, refs, mpn, status, issues, kind, blind, own_look, count}].
    A mismatch is always its own question (never grouped, never part of a bulk accept); identical unverified parts are one.
    `blind`: nothing but the student's word can settle it (an IC with no datasheet check): the bulk confirm names these first."""
    rows = store.pins_to_resolve(project) if rows is None else rows
    bom = {l["key"]: l for l in store.bom(project, write=False)}
    groups = {}
    for r in rows:
        line = bom.get(r["line"]) or store._line_of(project, r["line"])
        gk = None if r["status"] == "mismatch" else group_key(project, line)
        gid = ("one", r["line"]) if gk is None else gk
        g = groups.setdefault(gid, {"id": r["line"], "lines": [], "refs": [], "mpn": r.get("mpn") or "", "status": r["status"],
                                    "issues": r.get("issues") or "", "kind": _kind_of(line), "datasheet": bool(line.get("datasheet")),
                                    "fetchable": False})
        g["lines"].append(r["line"])
        g["refs"] += list(r.get("refs") or [r["line"]])
        g["fetchable"] = g["fetchable"] or (g["kind"] == "ic" and not line.get("datasheet") and bool(line.get("datasheet_url")))
    out = []
    for g in groups.values():
        g["count"] = len(g["refs"])
        g["own_look"] = g["status"] == "mismatch"
        g["blind"] = g["status"] != "mismatch" and g["kind"] == "ic"
        out.append(g)
    return out


def row_buttons(row, line):
    """Buttons the library row of a part shows (the quick preview's Pins tab; the Library page's table is the BOM's now), as
    ui/js/views/pages.js libAction decides: Accept after a datasheet pass, Verify only
    where a datasheet check can decide (a part that is not a passive / diode / connector, with a datasheet linked and no pass yet), and
    Confirm pins only on a row that needs its own look (a mismatch). The other rows are settled by the one line on top."""
    line = line or {}
    if row.get("verify") == "pass" and not row.get("accepted"):
        return 1
    n = 0
    if row.get("verify") != "pass" and row.get("symbol"):
        refs = line.get("refs") or []
        if refs and not all(store.is_simple_ref(r) for r in refs) and line.get("datasheet") and line.get("pins_status") in ("unverified", "mismatch"):
            n += 1
        if line.get("pins_status") == "mismatch":
            n += 1
    return n


def waiting(project):
    """The one summary every page that shows the waiting parts reads (S.pin_decisions.waiting):
    {questions, lines, own_look, auto_verified, fetchable, groups, bulk, blind, lib_buttons}.
      parts, to_confirm, conflicts, lines   store.pin_counts: THE numbers every page shows (parts are designators)
      questions       how many rows the student is asked (groups: identical parts are one); a layout number, never shown as a count
      own_look        of those, how many need their own look (a mismatch): the only rows with their own button
      bulk            the lines one "Confirm all" settles (every unverified question, no mismatch)
      blind           the refs among them nothing but the student's word settles (an IC with no datasheet check)
      auto_verified   lines the library model verified by itself (pin_model)"""
    rows = store.pins_to_resolve(project)
    qs = questions(project, rows)
    bom = {l["key"]: l for l in store.bom(project, write=False)}
    bulk = [ln for q in qs if not q["own_look"] for ln in q["lines"]]
    # one count for every place that shows it (E11): parts (designators), from the same rows the gate refuses on
    return {**store.pin_counts(rows), "questions": len(qs), "own_look": sum(1 for q in qs if q["own_look"]),
            "auto_verified": sum(1 for l in bom.values() if l.get("pins_basis") == "library_model"),
            "fetchable": sum(1 for q in qs if q["fetchable"]), "groups": qs, "bulk": bulk,
            "blind": [r for q in qs if q["blind"] for r in q["refs"]],
            "lib_buttons": {r["line"]: row_buttons(r, bom.get(r["line"])) for r in store.library_view(project)}}


def accept_all(project, lines=None, reason=""):
    """Accept every part `remaining` lists (or the given subset of it) in one go, basis from the part (blind / polarity), with the
    student's reason, which every one of them carries."""
    todo = remaining(project)
    if lines is not None:
        todo = [r for r in todo if r["line"] in set(lines)]
    for r in todo:
        accept(project, r["line"], reason=reason)
    return {"ok": True, "accepted": [r["line"] for r in todo]}


def stamp_legacy(project, lines, lib):
    """Give every legacy `pins_accepted: true` the fingerprint of today, once, so it lasts until the pins change."""
    for l in lines:
        e = lib.get(l["key"]) or {}
        if e.get("pins_accepted") and not e.get("pin_decision") and l.get("refs"):
            dec = {"id": f"pd-legacy-{l['key']}", "status": "accepted", "basis": "legacy", "reason": "", "evidence": [],
                   "fingerprint": fingerprint(project, l), "fpv": FP_VERSION, "ts": store.now()}
            store.add_library(project, l["key"], {"pin_decision": dec}, by="system")
            e["pin_decision"] = dec


# ---------------------------------------------------------------- what the modal shows

def _pins_of(project, line):
    out = []
    for sh in store.sheet_ids(project):
        for part in store.load_sheet(project, sh).get("parts", []):
            if part.get("ref") in (line.get("refs") or []):
                out += [{"ref": part["ref"], "num": str(p.get("num", p.get("number", ""))), "name": p.get("name") or "", "net": p.get("net") or ""}
                        for p in part.get("pins", [])]
    return out


# a contents or index line: a title, a run of dot leaders, a page number ("Pin Configuration ........ 5")
_LEADER = re.compile(r"(?:\.\s?){4,}\s*\d{1,3}\s*$|(?:\s\.){3,}\s*\d{1,3}\s*$|…{2,}\s*\d{1,3}\s*$", re.M)
_CONTENTS = re.compile(r"^\s*(?:table\s+of\s+contents|contents|index)\s*$", re.I | re.M)
_PIN_TABLE = re.compile(r"pin\s*(?:no\.?|number|#|name)\b|\bI\s*/\s*O\b|\bpin\s+description", re.I)


def is_contents_page(page):
    """A table of contents or an index: several lines that end in dot leaders and a page number. It names every pin heading of the
    datasheet and every package, so without this check it outscores the pin page it only points to (E13: W25Q128JV page 2)."""
    leaders = len(_LEADER.findall(page))
    return leaders >= 4 or (leaders >= 2 and bool(_CONTENTS.search(page)))


def _package_words(package):
    """The package family and pin count to look for ("SOIC-8" -> SOIC, 8; "WSON-8 6x5" -> WSON, 8): a datasheet writes
    "8-pin SOIC 208-mil", never the library's "SOIC-8"."""
    fam = [w for w in re.findall(r"[A-Za-z]{2,}", package or "") if w.lower() not in ("mm", "mil", "pin", "pins", "x")]
    return fam[:1]


def _package_on_page(page, package):
    """The package is on the page: its full name, or its family word together with its pin count ("SOIC-8", "SOIC8", "8-pin SOIC").
    The family word alone is on every page of a package chapter, so it counts for nothing."""
    m = re.search(r"[A-Za-z][-_ ]?(\d{1,3})\b", package or "")
    n = m.group(1) if m else None
    if not n or int(n) < 3:
        return False                       # no pin count in the name: nothing but the family word to go by
    if re.search(re.escape(package), page, re.I):
        return True
    for w in _package_words(package):
        if re.search(rf"\b{re.escape(w)}[-\s]?{n}\b|\b{n}[-\s]?(?:pin|lead|ball)s?[-\s]+(?:\w+[-\s]+)?{re.escape(w)}", page, re.I):
            return True
    return False


def candidate_pages(text, package=""):
    """1-based pages of the document that look like the pin table / pinout, best first (at most 5): a page with a pin heading
    scores above a page that only names the package, a page with the pin table itself (Pin No. / Pin Name / I/O) above one with only
    a heading, and the part's package on the same page adds to it. A contents or index page (dot leaders and page numbers) is
    never offered: it lists the headings, not the pins."""
    scored = []
    for n, page in enumerate(text.split("\f"), 1):
        if is_contents_page(page):
            continue
        heads = len(_HEADINGS.findall(page))
        table = len(_PIN_TABLE.findall(page))
        pkg = _package_on_page(page, package)
        score = 2 * heads + (3 if heads and table else 0) + (1 if pkg else 0) + (1 if heads and pkg else 0)
        if score:
            scored.append((-score, n))
    return [n for _, n in sorted(scored)[:5]]


def confirm_data(project, key):
    """Everything the confirm modal needs: the pins, and the datasheet with the pages to look at."""
    import sources
    line = store._line_of(project, key)
    folder = sources.folder_of(project)
    ds = line.get("datasheet") or sources.find_for(project, line.get("mpn")) or ""
    missing = ""
    if ds and sources.document_path(project, ds) is None:
        # linked, but the file is not on this machine (a sidecar-only record, or a deleted file): another document of the
        # same part may be, else the dialog says so instead of showing an empty page
        alt = sources.find_for(project, line.get("mpn"))
        if alt and sources.document_path(project, alt) is not None:
            ds = alt
        else:
            missing, ds = ds, ""
    docs = []
    if ds:
        try:
            text = sources.text_of(ds, folder)
        except (FileNotFoundError, OSError):
            text = ""
        meta = sources._read_meta(folder / ds)
        docs.append({"name": ds, "sha256": meta.get("sha256", ""), "url": "/api/source/" + ds,
                     "candidate_pages": candidate_pages(text, line.get("package") or ""), "quality": sources.quality(text)})
    st = next((l for l in store.bom(project, write=False) if l["key"] == line["key"]), {})
    return {"line": line["key"], "refs": line.get("refs", []), "mpn": line.get("mpn") or "", "package": line.get("package") or "",
            "pins": _pins_of(project, line), "wired": store.has_wired_pins(project, line), "docs": docs, "missing_doc": missing,
            "status": st.get("pins_status", ""), "issues": st.get("pins_issues", ""),
            "polarised": store._polarised_only(line), "group_refs": [r for g in [group_lines(project, line["key"])] for k in g
                                                                      for r in (store._line_of(project, k).get("refs") or [k])]}


# ---------------------------------------------------------------- what the rest of the app reads

def _evidence_words(dec):
    """What the decision itself records, in words: the datasheet page it was checked against. A decision with no reason and no evidence has
    NO reason: it is never given one here (the order manifest shows it empty, and the acceptance check flags it)."""
    ev = [e for e in (dec.get("evidence") or []) if isinstance(e, dict) and e.get("doc")]
    return "; ".join(f"pins checked against {e['doc']}" + (f", page {e['page']}" if e.get("page") else "") for e in ev)


def risks(project):
    """The accepted risks: every part whose pins stand on the student's decision rather than a datasheet pin table.
    [{line, refs, mpn, basis, ts, reason, evidence}]; a revoked or stale decision is no risk, it is a gate item."""
    lib = store.library_parts(project)
    out = []
    for l in store.bom(project, write=False):
        if not l.get("refs") or l.get("pins_status") != "accepted" or l.get("dnp") or l.get("nobuy"):
            continue
        dec = state(project, l, lib.get(l["key"]))[0]
        if dec:
            out.append({"line": l["key"], "refs": l["refs"], "mpn": l.get("mpn") or "", "basis": dec.get("basis", ""),
                        "ts": dec.get("ts", ""), "reason": dec.get("reason") or _evidence_words(dec), "evidence": dec.get("evidence", [])})
    return out


def write_manifest(project):
    """exports/<project>_order_manifest.json: {warning, accepted_risks, unverified, verified_by_library_model, board_check, generated}, beside the Gerber zip, never inside it.
    Written when there is anything to say (or an older one to keep current); the JLC BOM CSV is not touched."""
    import json

    import workspace
    path = store.pdir(project) / "exports" / f"{workspace.safe_name(project)}_order_manifest.json"
    acc, unv = risks(project), store.pins_to_resolve(project)
    warn = store.pins_warning(project, rows=unv)            # named, never a block: the order goes out with it in plain words
    try:
        import pin_model
        lib = pin_model.verified_lines(project)
    except Exception:       # noqa: BLE001
        lib = []
    try:
        import ledger
        findings = ledger.accepted_for_manifest(project)       # findings accepted with a reason (Findings list)
    except Exception:       # noqa: BLE001
        findings = []
    if not (acc or unv or lib or findings or path.exists()):
        return None
    try:
        import board_results             # stream A's record of the last Altium check; absent or empty, the manifest says null
        board = getattr(board_results, "latest", lambda p: None)(project)
    except Exception:
        board = None
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
        same = old.get("accepted_risks") == acc and old.get("accepted_findings", []) == findings and old.get("unverified") == unv and old.get("verified_by_library_model", []) == lib and old.get("board_check") == json.loads(json.dumps(board, default=str)) and old.get("warning", "") == warn
    except (OSError, ValueError):
        same = False
    if not same:
        path.parent.mkdir(parents=True, exist_ok=True)
        doc = {"warning": warn, "accepted_risks": acc, "accepted_findings": findings, "unverified": unv, "verified_by_library_model": lib, "board_check": board, "generated": store.now()}
        store._write_text(path, json.dumps(doc, ensure_ascii=False, indent=2, default=str))
    return str(path)


@ext.register("model")
def _model(project, out):
    return {"pin_decisions": {"accepted": risks(project), "remaining": remaining(project), "waiting": waiting(project)}}


@ext.register("get")
def _get(handler, path, q):
    if path == "/api/pins/confirm-data":
        key = (q or {}).get("line")
        if not key:
            raise ext.HTTPError(400, "line required")
        try:
            return confirm_data(handler.project(), key)
        except KeyError:
            raise ext.HTTPError(404, f"no BOM line {key!r}")
    return None


@ext.register("post")
def _post(handler, path, body):
    if path not in ("/api/pins/confirm", "/api/pins/revoke", "/api/pins/accept-all"):
        return None
    proj = handler.project()
    if body.get("line") and path != "/api/pins/accept-all":
        try:
            store._line_of(proj, body["line"])
        except KeyError:
            raise ext.HTTPError(404, f"no BOM line {body.get('line')!r}")      # an unknown part is not found, before it is asked for a reason
    backed = path == "/api/pins/confirm" and bool(valid_evidence(proj, body.get("evidence")))       # a real datasheet page says it itself
    if path != "/api/pins/revoke" and not backed and not body.get("wrong") \
            and not re.search(r"[A-Za-z֐-׿]{3}", str(body.get("reason") or "")):
        raise ext.HTTPError(400, "a reason is needed to accept a risk: say in a sentence why it is fine")      # a blank reason is no reason (U5)
    try:
        if path == "/api/pins/accept-all":
            if not body.get("confirm"):
                raise ext.HTTPError(400, "confirm required: this accepts every remaining part at once")
            return accept_all(proj, body.get("lines"), reason=str(body.get("reason") or "")[:300])
        if not body.get("line"):
            raise ext.HTTPError(400, "line required")
        if path == "/api/pins/revoke":
            return revoke(proj, body["line"])
        return accept(proj, body["line"], evidence=body.get("evidence"), reason=body.get("reason"), wrong=body.get("wrong"), group=True)
    except KeyError:
        raise ext.HTTPError(404, f"no BOM line {body.get('line')!r}")
