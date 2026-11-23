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


def fingerprint(project, line):
    """What a pin decision was made about: sorted (ref, number, name) of the line's parts on the sheets, plus the MPN,
    the package and the declared LCSC code. Never the whole part dict (a drawn position or a note must not undo a decision).
    Only wired pins count, and only by number and name: the decision is about which number is which pin where it matters.
    Moving a pin to another net keeps it; marking open pins NC (any no-connect spelling, pinnames.is_nc_net) or adding a built
    symbol's unlisted pins as NC keeps it; wiring a pin that was open or NC, or unwiring one, is a change.
    One exception: a diode / LED is decided on polarity and its pins are often named just "1" / "2", so the net names of its
    pins are part of the fingerprint: swapping anode and cathode nets asks again."""
    line = _line(project, line)
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
    if store._polarised_only(line):
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
    if project and dec.get("fingerprint") and dec["fingerprint"] != fingerprint(project, line):
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


def accept(project, key, evidence=None, reason="", wrong=None, basis=None):
    """The student says the pins match. {ok, line, decision, changed}. Idempotent: a second accept of the same fingerprint
    writes nothing. `wrong`, a list of pin numbers the student marked wrong, makes it a conflict instead (no decision)."""
    line = store._line_of(project, key)
    key = line["key"]
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
    evidence = [{"doc": str(e.get("doc") or ""), "sha256": str(e.get("sha256") or ""), "page": int(e["page"]) if str(e.get("page") or "").isdigit() else 0}
                for e in (evidence or []) if isinstance(e, dict)]
    dec = {"id": f"pd-{store.now_ms()}", "status": "accepted", "basis": basis if basis in BASES else _basis(line, evidence),
           "reason": str(reason or "").strip()[:300], "evidence": evidence, "fingerprint": fingerprint(project, line), "ts": store.now()}
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


def accept_all(project, lines=None):
    """Accept every part `remaining` lists (or the given subset of it) in one go, basis from the part (blind / polarity)."""
    todo = remaining(project)
    if lines is not None:
        todo = [r for r in todo if r["line"] in set(lines)]
    for r in todo:
        accept(project, r["line"])
    return {"ok": True, "accepted": [r["line"] for r in todo]}


def stamp_legacy(project, lines, lib):
    """Give every legacy `pins_accepted: true` the fingerprint of today, once, so it lasts until the pins change."""
    for l in lines:
        e = lib.get(l["key"]) or {}
        if e.get("pins_accepted") and not e.get("pin_decision") and l.get("refs"):
            dec = {"id": f"pd-legacy-{l['key']}", "status": "accepted", "basis": "legacy", "reason": "", "evidence": [],
                   "fingerprint": fingerprint(project, l), "ts": store.now()}
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


def candidate_pages(text, package=""):
    """1-based pages of the document that look like the pin table / pinout, best first (at most 5): a page with a pin heading
    scores above a page that only names the package."""
    scored = []
    for n, page in enumerate(text.split("\f"), 1):
        score = 2 * len(_HEADINGS.findall(page)) + (1 if package and re.search(re.escape(package), page, re.I) else 0)
        if score:
            scored.append((-score, n))
    return [n for _, n in sorted(scored)[:5]]


def confirm_data(project, key):
    """Everything the confirm modal needs: the pins, and the datasheet with the pages to look at."""
    import sources
    line = store._line_of(project, key)
    folder = sources.folder_of(project)
    ds = line.get("datasheet") or sources.find_for(project, line.get("mpn")) or ""
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
            "pins": _pins_of(project, line), "docs": docs, "status": st.get("pins_status", ""), "issues": st.get("pins_issues", ""),
            "polarised": store._polarised_only(line)}


# ---------------------------------------------------------------- what the rest of the app reads

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
                        "ts": dec.get("ts", ""), "reason": dec.get("reason", ""), "evidence": dec.get("evidence", [])})
    return out


def write_manifest(project):
    """exports/<project>_order_manifest.json: {accepted_risks, unverified, board_check, generated}, beside the Gerber zip, never inside it.
    Written when there is anything to say (or an older one to keep current); the JLC BOM CSV is not touched."""
    import json

    import workspace
    path = store.pdir(project) / "exports" / f"{workspace.safe_name(project)}_order_manifest.json"
    acc, unv = risks(project), store.pins_to_resolve(project)
    if not (acc or unv or path.exists()):
        return None
    try:
        import board_results             # stream A's record of the last Altium check; absent or empty, the manifest says null
        board = getattr(board_results, "latest", lambda p: None)(project)
    except Exception:
        board = None
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
        same = old.get("accepted_risks") == acc and old.get("unverified") == unv and old.get("board_check") == json.loads(json.dumps(board, default=str))
    except (OSError, ValueError):
        same = False
    if not same:
        path.parent.mkdir(parents=True, exist_ok=True)
        doc = {"accepted_risks": acc, "unverified": unv, "board_check": board, "generated": store.now()}
        store._write_text(path, json.dumps(doc, ensure_ascii=False, indent=2, default=str))
    return str(path)


@ext.register("model")
def _model(project, out):
    return {"pin_decisions": {"accepted": risks(project), "remaining": remaining(project)}}


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
    try:
        if path == "/api/pins/accept-all":
            if not body.get("confirm"):
                raise ext.HTTPError(400, "confirm required: this accepts every remaining part at once")
            return accept_all(proj, body.get("lines"))
        if not body.get("line"):
            raise ext.HTTPError(400, "line required")
        if path == "/api/pins/revoke":
            return revoke(proj, body["line"])
        return accept(proj, body["line"], evidence=body.get("evidence"), reason=body.get("reason"), wrong=body.get("wrong"))
    except KeyError:
        raise ext.HTTPError(404, f"no BOM line {body.get('line')!r}")
