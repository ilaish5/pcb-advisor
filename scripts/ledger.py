"""The findings ledger (root cause R5: a finding has a lifecycle; chat text is not the control surface).

projects/<p>/ledger.json:  {"seq": n, "items": [item]}.  One item per finding the tool cannot fix itself (a design rule check class, a
step the student must do by hand in Altium, a tool limit):

    open -> student_fixed -> closed          the student says "done"; ONLY a check on the file as it is now closes it
    open -> accepted (a non-empty reason)     the student accepts the risk; a change of the file afterwards re-opens it
    student_fixed -> open                     the check ran and the finding is still there

An item carries the check that can close it (`check`) and the evidence of the last run ({sha256 of the file, items looked at, result}).
A check that cannot run (no Altium, no report on this file) answers not_checked: the item stays where it is and says why. Nothing here
calls Altium: a check that needs it is passed in as `runner` by the caller.

Everything the student can do is a function here and a route in the ext registry at the bottom (GET /api/ledger, POST /api/ledger/...).
"""
import hashlib
import json
import os
import pathlib
import re
import sys
import threading

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ext  # noqa: E402
import store  # noqa: E402

STATES = ("open", "student_fixed", "closed", "accepted")
OPEN_STATES = ("open", "student_fixed")
KINDS = ("drc", "hand_step", "limit")
_LOCK = threading.RLock()
FILE = "ledger.json"
MIN_REASON = 8                 # a reason is words, not a letter: "ok" is not a reason

# Rules the system keeps for itself. Advice that breaks one is refused as advice (the item says so), whatever wrote it.
SYSTEM_RULES = [
    {"id": "via_in_pad_never",
     "pattern": re.compile(r"\bvias?\b[^.\n]{0,60}\b(?:in|under|inside|into|within|beneath)\b[^.\n]{0,40}\b(?:pads?|exposed pad|EP|thermal pad|paddle)\b|"
                           r"\b(?:thermal|stitch\w*)\s+vias?\b[^.\n]{0,40}\b(?:in|under|inside|into|within|beneath|through)\s+(?:the\s+)?(?:exposed pad|EP|thermal pad|paddle|U\d+\b)|via[- ]in[- ]pad", re.I),
     "negation": re.compile(r"\b(?:never|not|no|don[’']?t|do not|avoid|without|instead of|forbidden|not allowed|next to|beside|around|near|outside|adjacent|alongside)\b", re.I),
     "rule": "No via in an SMD pad (ViasUnderSMD is Not allowed)",
     "why": "JLC makes via-in-pad only as filled and plated-over vias, which cost extra, and an open via in a pad wicks solder away. "
            "Put the thermal vias next to the pad instead, outside the paste window, or leave the pad to the top copper."},
]


def _path(project):
    return store.pdir(project) / FILE


def _now():
    return store.now()


def _empty():
    return {"seq": 0, "items": []}


class LedgerCorrupt(Exception):
    """ledger.json exists but cannot be read: the student is told, the file is left as it is, and nothing is written over it."""


def load(project):
    p = _path(project)
    try:
        raw = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _empty()
    except OSError as exc:
        raise LedgerCorrupt(f"The Findings list ({p.name}) cannot be read: {exc}. It was left as it is.") from exc
    try:
        d = json.loads(raw)
    except ValueError as exc:
        raise LedgerCorrupt(f"The Findings list ({p.name}) is damaged ({exc}). It was left as it is; copy the file somewhere safe and "
                            "ask for help before adding anything, so no item is lost.") from exc
    if isinstance(d, dict) and isinstance(d.get("items"), list):
        d.setdefault("seq", len(d["items"]))
        return d
    raise LedgerCorrupt(f"The Findings list ({p.name}) does not have the expected shape. It was left as it is.")


def _save(project, doc):
    p = _path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, ensure_ascii=False, indent=1)
    try:
        if p.read_text(encoding="utf-8") == text:       # the model is built on every poll: an unchanged ledger writes nothing
            return
    except OSError:
        pass
    tmp = p.with_name(p.name + ".tmp")          # written whole beside the file, then swapped in: a crash leaves the old file or the new one
    store._write_text(tmp, text)
    os.replace(tmp, p)


def _pcb_sha(project):
    try:
        import lineage
        pcb = lineage.linked_pcb(project)
        return lineage.sha256_file(pcb) if pcb else ""
    except Exception:       # noqa: BLE001 - no file is "no sha", never a crash
        return ""


def _hist(item, state, note):
    item.setdefault("history", []).append({"ts": _now(), "state": state, "note": str(note)[:400]})
    item["state"] = state


def _find(doc, item_id):
    for it in doc["items"]:
        if it["id"] == item_id:
            return it
    raise KeyError(f"no finding {item_id!r}")


def _norm(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def key_of(text):
    return "adv:" + hashlib.sha256(_norm(text).encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------- adding

def add(project, key, kind, title, detail="", page="", check=None, source="", severity="warn", extra=None, reopen_closed=True):
    """The item for `key`; created open, or returned as it is when it is already open / waiting. A closed item whose finding is back is
    re-opened (its history says so). An accepted item stays accepted until the file changes (see view)."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}")
    with _LOCK:
        doc = load(project)
        for it in doc["items"]:
            if it["key"] == key:
                if it["state"] == "closed" and reopen_closed:
                    _hist(it, "open", "the finding is back")
                if title and it["state"] in OPEN_STATES:
                    it["title"] = str(title)[:200]
                    if detail:
                        it["detail"] = str(detail)[:2000]
                    if extra:
                        it.update(extra)
                _save(project, doc)
                return it
        doc["seq"] += 1
        sha = _pcb_sha(project)
        conflict = advice_conflict(f"{title}. {detail}") if kind == "hand_step" else None
        it = {"id": f"F-{doc['seq']:03d}", "key": key, "kind": kind, "title": str(title)[:200], "detail": str(detail)[:2000], "page": page,
              "state": "open", "severity": severity, "source": source, "check": check or {"type": "manual"},
              "opened_sha256": sha, "last_check": None, "reason": "", "history": [], "created": _now()}
        if conflict:
            it["conflict"] = conflict
        if extra:
            it.update(extra)
        _hist(it, "open", f"opened by {source or kind}")
        doc["items"].append(it)
        _save(project, doc)
        return it


def advice_conflict(text):
    """The system rule that advice text breaks, or None: {"id", "rule", "why"}. A sentence that says "never ..." is not advice to do it."""
    for sent in re.split(r"(?<=[.!?])\s+|\n+", str(text)):
        for r in SYSTEM_RULES:
            if r["pattern"].search(sent) and not r["negation"].search(sent):
                return {"id": r["id"], "rule": r["rule"], "why": r["why"]}
    return None


_HAND = re.compile(
    r"\b(?:by hand|manually|yourself)\b[^.\n]{0,40}\bAltium\b|\bAltium\b[^.\n]{0,40}\b(?:by hand|manually|yourself)\b|"
    r"\b(?:in|inside|with) Altium\b[^.\n]{0,60}\b(?:Tools|Place|Design|Edit|View|File|Reports|Project)\s*>|"
    r"\b(?:Tools|Place|Design|Edit|Reports)\s*>\s*[A-Z][^.\n]{0,40}\bin Altium\b|"
    r"\b(?:you (?:need|have|must|should|can) (?:to )?|please |then |next,? |now )?(?:open|move|edit|fix|add|widen|repour|re-?pour|delete|change|set|draw|route|run|place|rotate|select|replace|swap)\b"
    r"[^.\n]{0,80}\b(?:in|inside|with) Altium\b", re.I)
_TOOL_SIDE = re.compile(r"\b(?:the tool|this tool|the app|the system|pcb advisor|the server|the agent|I(?:'ve| have| did)?)\b[^.\n]{0,30}\b(?:ran|runs|drew|draws|placed|places|routed|routes|did|does|will do|has done)\b", re.I)


# Not a step for the student: the agent doing it, an offer or a question, or a sentence that says nothing needs doing by hand.
_NOT_STEP = re.compile(
    r"\b(?:I(?:'ll|’ll| will| can| could| would| am going to|'m going to|’m going to)|let me|shall I|should I|do you want me|want me to|tell me to|ask me to"
    r"|or tell me|no need|(?:do not|don't|don’t|doesn't|doesn’t|does not|did not|didn't) (?:need|have) to|not need to|nothing to do|never need|"
    r"without having to|(?:you )?(?:need|have) not)\b", re.I)
_WIDE = re.compile(r"\bin Altium\b[^.\n]{0,80}\b(?:move|set|change|edit|tent|fix|delete|add|run|open|drag|disable)\b|\b(?:by hand|manually|yourself)\b", re.I)
_REFS = re.compile(r"\b[A-Z]{1,3}\d{1,3}\b")
_ANNOTATION = re.compile(r"\n\n(?:Do not follow the step in F-\d+|Tracked on your Findings list:|Nothing in this reply was added to your Findings list|A limit of this tool:|Correction:).*\Z", re.S)


def original(text):
    """The agent's own text: what annotate_reply appended (the Tracked line, a refusal, a correction) is taken off, so a reply has ONE identity
    whether it is looked at when it is written or read back from the stored chat."""
    return _ANNOTATION.sub("", str(text or "")).strip()


def _sentences(text):
    for sent in re.split(r"(?<=[.!?])\s+|\n+", str(text or "")):
        s_ = sent.strip(" \t-*•>#")
        if len(s_) >= 12:
            yield s_


def _is_step(sent):
    return not (_TOOL_SIDE.match(sent) or _NOT_STEP.search(sent) or sent.rstrip().endswith("?"))


def hand_steps(text):
    """The sentences of a text that tell the student to do something by hand in Altium (what the ledger must hold)."""
    return [s_[:400] for s_ in _sentences(text) if (_HAND.search(s_) or _WIDE.search(s_)) and _is_step(s_)]


def track_message(project, text, ts="", source="agent", page=""):
    """ONE item per reply: the hand steps it holds (title: the first, detail: all of them) naming every part and net the reply mentions.
    The key is the hash of the agent's own text, so the same reply never makes a second item, however it comes back (live, annotated,
    read from the stored chat). A closed or accepted item is left as it is. Returns the item or None. Never raises."""
    try:
        text = original(text)
        steps = hand_steps(text)
        if not steps:
            return None
        refs = sorted(set(_REFS.findall(text)))
        key = "msg:" + hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:14]
        label = steps[0][:120] + (f" ({', '.join(refs[:8])})" if refs else "")
        mech = any(re.search(r"\b(?:DRC|design rule|clearance|short|un-?routed)\b", x, re.I) for x in steps)
        return add(project, key, "hand_step", label[:200], "\n".join(steps)[:2000] + ("\n\n" + text[:1500] if len(text) > 200 else ""), page=page, source=source,
                   check={"type": "drc_clean"} if mech else {"type": "manual"}, extra={"refs": refs}, reopen_closed=False)
    except LedgerCorrupt:
        raise
    except Exception as exc:       # noqa: BLE001
        print(f"(ledger: message not tracked: {type(exc).__name__}: {exc})", file=sys.stderr)
        return None


_BACKFILL_SEEN = {}


def backfill(project):
    """Hand-step advice the agent gave before this ledger existed (the stored chats) becomes items too: nothing said stays only in chat.
    The same key as the live path, so a reply already tracked is found, never added again. Reads a chat file again only when it changed."""
    d = store.pdir(project) / "chats"
    try:
        files = sorted(d.glob("*.jsonl"))
    except OSError:
        return
    for f in files:
        try:
            st = f.stat()
            sig = (st.st_mtime_ns, st.st_size)
            if _BACKFILL_SEEN.get((str(project), str(f))) == sig:
                continue
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if isinstance(r, dict) and r.get("role") == "agent" and r.get("text") and not r.get("error"):
                    track_message(project, r.get("text"), r.get("ts", ""), source="agent (earlier chat)")
            _BACKFILL_SEEN[(str(project), str(f))] = sig
        except OSError:
            continue


def track_advice(project, text, source="agent", page=""):
    """The reply's hand steps as ONE ledger item. Returns [{"id", "title", "state", "conflict"?}] (empty when it holds none)."""
    it = track_message(project, text, source=source, page=page)
    if not it:
        return []
    return [{"id": it["id"], "title": it["title"], "state": it["state"], **({"conflict": it["conflict"]} if it.get("conflict") else {})}]


# ---------------------------------------------------------------- checks

def _short(rule):
    try:
        from checks import drc_jlc_map
        return drc_jlc_map.short(rule)
    except Exception:       # noqa: BLE001
        return re.split(r" \(|:", str(rule), maxsplit=1)[0].replace(" Constraint", "").strip()


def _drc_record(project):
    try:
        import board_results
        return (board_results.latest(project) or {}).get("board_check")
    except Exception:       # noqa: BLE001
        return None


def rule_counts(drc):
    out = {}
    for k, v in ((drc or {}).get("rules") or {}).items():
        out[_short(k)] = out.get(_short(k), 0) + int(v or 0)
    return out


def _evidence(project, sha, scope, examined, failed, check, detail=""):
    return {"ts": _now(), "check": check, "sha256": sha, "in_scope": scope, "examined": examined, "failed": failed, "detail": detail}


def check_item(project, item, runner=None):
    """Run the item's check on the file as it is now. Returns {"status": pass|fail|not_checked, "detail", "evidence"}."""
    cur = _pcb_sha(project)
    typ = (item.get("check") or {}).get("type", "manual")
    if typ in ("drc_rule", "drc_clean"):
        rec = _drc_record(project)
        if (not rec or rec.get("pcb_sha256") != cur) and runner and cur:
            try:
                runner()
            except Exception as exc:       # noqa: BLE001 - a check that could not run is not_checked, with the reason
                return {"status": "not_checked", "detail": f"the design rule check could not run: {exc}", "evidence": None}
            rec = _drc_record(project)
        if not cur:
            return {"status": "not_checked", "detail": "there is no board file linked to check", "evidence": None}
        if not rec or rec.get("pcb_sha256") != cur:
            return {"status": "not_checked", "detail": "no design rule check on the board file as it is now: press Check board", "evidence": None}
        drc = rec.get("drc") or {}
        if not drc.get("complete"):
            return {"status": "not_checked", "detail": "the design rule check report was not read in full", "evidence": None}
        counts = rule_counts(drc)
        if typ == "drc_rule":
            n = counts.get(item["check"]["rule"], 0)
            ev = _evidence(project, cur, drc.get("total"), drc.get("total"), n, "drc_rule", f"{item['check']['rule']}: {n}")
            return {"status": "pass" if n == 0 else "fail", "detail": f"{item['check']['rule']}: {n} left", "evidence": ev, "count": n}
        n = int(drc.get("total") or 0)
        ev = _evidence(project, cur, n, n, n, "drc_clean", f"total {n}")
        return {"status": "pass" if n == 0 else "fail", "detail": f"the board check shows {n} violations", "evidence": ev, "count": n}
    return {"status": "not_checked", "detail": "the tool has no automatic check for this step. Accept it with a note of what you did, or leave it open.",
            "evidence": None}


# ---------------------------------------------------------------- the student's moves

def mark_done(project, item_id, runner=None):
    """"Done, check again": the check runs on the file as it is now. Only a passing check closes the item. Returns the item with
    "check": {"status", "detail"}. An item whose file has not changed since it was last looked at is not closed by saying so."""
    with _LOCK:
        doc = load(project)
        it = _find(doc, item_id)
        if it["state"] not in OPEN_STATES:
            raise ValueError(f"{item_id} is {it['state']}: nothing to check")
        cur = _pcb_sha(project)
        last = (it.get("last_check") or {}).get("sha256") or it.get("opened_sha256")
        needs_file = (it.get("check") or {}).get("type") in ("drc_rule", "drc_clean")
        if needs_file and cur and last and cur == last and (it.get("last_check") or {}).get("status") != "not_checked":
            _hist(it, "open", "marked done, but the board file has not changed since it was last checked")
            it["check_result"] = {"status": "fail", "detail": "the board file has not changed since the last check: nothing to check again"}
            _save(project, doc)
            return it
        _hist(it, "student_fixed", "the student says it is done")
        _save(project, doc)
    res = check_item(project, it, runner)          # outside the lock: it may run a long step
    with _LOCK:
        doc = load(project)
        it = _find(doc, item_id)
        it["check_result"] = {"status": res["status"], "detail": res["detail"]}
        if res.get("evidence"):
            it["last_check"] = {**res["evidence"], "status": res["status"]}
        if res["status"] == "pass":
            _hist(it, "closed", f"re-checked on the file ({it['last_check']['sha256'][:12]}): {res['detail']}")
        elif res["status"] == "fail":
            _hist(it, "open", f"re-checked: still there ({res['detail']})")
            if "count" in res:
                it["count"] = res["count"]
        else:
            it["state"] = "student_fixed"          # waiting for a check; says why
            it["history"].append({"ts": _now(), "state": "student_fixed", "note": f"not re-checked: {res['detail']}"})
        _save(project, doc)
        return it


def accept(project, item_id, reason, make_anyway=False):
    """Accept the finding with a reason (at least MIN_REASON characters of words). A finding the fab may reject also needs make_anyway."""
    reason = str(reason or "").strip()
    if len(reason) < MIN_REASON or not re.search(r"[A-Za-z֐-׿]{3}", reason):
        raise ValueError("a reason is needed to accept a finding: say in a sentence why it is fine")
    with _LOCK:
        doc = load(project)
        it = _find(doc, item_id)
        if it["state"] == "accepted":
            return it
        if it.get("jlc_reject") and not make_anyway:
            raise ValueError("the fab may reject this: to accept it anyway, give the reason and confirm 'make anyway'")
        it["reason"] = reason[:400]
        it["accepted_sha256"] = _pcb_sha(project)
        it["accepted_anyway"] = bool(make_anyway)
        _hist(it, "accepted", f"accepted: {reason[:200]}")
        _save(project, doc)
        return it


def reopen(project, item_id, note="reopened by the student"):
    with _LOCK:
        doc = load(project)
        it = _find(doc, item_id)
        _hist(it, "open", note)
        it.pop("accepted_sha256", None)
        _save(project, doc)
        return it


# ---------------------------------------------------------------- syncing with what Altium said

def _class_rows(rec):
    drc = (rec or {}).get("drc") or {}
    counts = rule_counts(drc)
    lines = drc.get("violations") or []
    try:
        import violation_pairs as vp
    except Exception:       # noqa: BLE001
        vp = None
    by_rule = {}
    for ln in lines:
        by_rule.setdefault(_short(str(ln).partition(":")[0]), []).append(ln)
    rows = []
    for rule, n in counts.items():
        ls = by_rule.get(rule, [])
        pairs = vp.group(ls)[:20] if vp else []
        rows.append({"rule": rule, "count": n, "listed": len(ls), "pairs": pairs,
                     "details": [vp.pair_words(p) for p in pairs[:8]] if vp else [str(x)[:160] for x in ls[:8]]})
    return rows


def sync_drc(project):
    """Bring the ledger to the newest design rule check: one item per rule class with violations (count and the objects the report
    names), a class that no longer has any on a complete check of THIS file is closed with that evidence. A check made on another
    version of the file changes nothing here: it says nothing about this one."""
    rec = _drc_record(project)
    if not rec or not (rec.get("drc") or {}).get("complete"):
        return load(project)
    cur = _pcb_sha(project)
    if not cur or rec.get("pcb_sha256") != cur:
        return load(project)
    try:
        from checks import drc_jlc_map
    except Exception:       # noqa: BLE001
        drc_jlc_map = None
    rows = _class_rows(rec)
    seen = set()
    with _LOCK:
        for r in rows:
            if r["count"] <= 0:
                continue
            seen.add(r["rule"])
            jlc = drc_jlc_map.jlc_item(r["rule"]) if drc_jlc_map else None
            strict = r["rule"] in ("Short-Circuit", "Un-Routed Net") or bool(jlc)
            detail = "; ".join(r["details"]) if r["details"] else f"{r['count']} violations; the report lists none of them by object"
            it = add(project, f"drc:{r['rule']}", "drc", f"DRC {r['rule']}: {r['count']} {'violation' if r['count'] == 1 else 'violations'}",
                     detail, page="pcb", check={"type": "drc_rule", "rule": r["rule"]}, source="design rule check",
                     severity="block" if strict else "warn",
                     extra={"count": r["count"], "jlc_item": jlc, "jlc_reject": strict, "objects": r["pairs"][:20]})
            doc = load(project)
            cur_it = _find(doc, it["id"])
            cur_it["last_check"] = {**_evidence(project, cur, (rec["drc"] or {}).get("total"), (rec["drc"] or {}).get("total"), r["count"], "drc_rule"),
                                    "status": "fail"}
            if cur_it["state"] == "student_fixed":
                _hist(cur_it, "open", f"re-checked: {r['count']} still there")
            _save(project, doc)
        doc = load(project)
        for it in doc["items"]:
            if it["kind"] == "drc" and it["state"] in OPEN_STATES and (it.get("check") or {}).get("rule") not in seen:
                it["last_check"] = {**_evidence(project, cur, (rec["drc"] or {}).get("total"), (rec["drc"] or {}).get("total"), 0, "drc_rule"), "status": "pass"}
                it["count"] = 0
                _hist(it, "closed", f"a design rule check of the board file ({cur[:12]}) shows none left")
        _save(project, doc)
        return doc


def view(project):
    """The ledger as the pages and the manifest read it. An accepted item whose board file has changed since is open again."""
    with _LOCK:
        try:
            sync_drc(project)
        except Exception as exc:       # noqa: BLE001
            print(f"(ledger: sync failed: {type(exc).__name__}: {exc})", file=sys.stderr)
        try:
            backfill(project)
        except Exception as exc:       # noqa: BLE001
            print(f"(ledger: backfill failed: {type(exc).__name__}: {exc})", file=sys.stderr)
        doc = load(project)
        cur = _pcb_sha(project)
        changed = False
        for it in doc["items"]:
            if it["state"] == "accepted" and it.get("accepted_sha256") and cur and cur != it["accepted_sha256"]:
                _hist(it, "open", "the board file changed after it was accepted: accepted for the old file only")
                it.pop("accepted_sha256", None)
                changed = True
        if changed:
            _save(project, doc)
        return doc


def counts(doc):
    c = {s: 0 for s in STATES}
    for it in doc["items"]:
        c[it["state"]] = c.get(it["state"], 0) + 1
    c["blocking"] = sum(1 for it in doc["items"] if it["state"] in OPEN_STATES and it.get("severity") == "block")
    c["open_total"] = c["open"] + c["student_fixed"]
    return c


def accepted_for_manifest(project):
    return [{"id": it["id"], "title": it["title"], "kind": it["kind"], "reason": it["reason"], "accepted_anyway": bool(it.get("accepted_anyway")),
             "sha256": it.get("accepted_sha256", "")} for it in view(project)["items"] if it["state"] == "accepted"]


def public(it):
    keep = ("id", "kind", "title", "detail", "page", "state", "severity", "source", "check", "reason", "history", "count", "jlc_item", "jlc_reject",
            "objects", "conflict", "check_result", "last_check", "accepted_anyway", "limit", "created")
    return {k: it[k] for k in keep if k in it}


# ---------------------------------------------------------------- routes

@ext.register("model")
def _model(project, out):
    try:
        doc = view(project)
        return {"ledger": {"counts": counts(doc), "items": [public(i) for i in doc["items"] if i["state"] != "closed"][:60]}}
    except LedgerCorrupt as exc:
        return {"ledger": {"error": str(exc), "counts": {k: 0 for k in STATES}, "items": []}}
    except Exception:       # noqa: BLE001 - the page loads without a ledger rather than not at all
        return {}


@ext.register("get")
def _get(handler, path, q):
    if path == "/api/ledger":
        try:
            doc = view(handler.project())
        except LedgerCorrupt as exc:
            raise ext.HTTPError(500, str(exc))
        return {"counts": counts(doc), "items": [public(i) for i in doc["items"]]}
    return None


def _drc_runner(handler, proj):
    """The Check board step, run by the page's own machinery (Altium, the step lock and the step note), for a re-check."""
    import sys as _s
    serve = _s.modules[type(handler).__module__]

    def run():
        code, body, _ = serve.run_step_button(proj, handler.session(proj), "drc", {})
        if code != 200 or (isinstance(body, dict) and body.get("error")):
            raise RuntimeError((body or {}).get("error") or "the check did not run")
    return run


@ext.register("post")
def _post(handler, path, body):
    if not path.startswith("/api/ledger/"):
        return None
    proj = handler.project()
    item = body.get("id")
    try:
        if path == "/api/ledger/done":
            return public(mark_done(proj, item, _drc_runner(handler, proj) if body.get("recheck", True) else None))
        if path == "/api/ledger/accept":
            return public(accept(proj, item, body.get("reason"), bool(body.get("make_anyway"))))
        if path == "/api/ledger/reopen":
            return public(reopen(proj, item))
        if path == "/api/ledger/track":
            title = str(body.get("title") or "").strip()
            if not title:
                raise ext.HTTPError(400, "title required")
            it = add(proj, body.get("key") or key_of(title), "limit" if body.get("limit") else "hand_step", title, str(body.get("detail") or ""),
                     page=str(body.get("page") or ""), source="student", extra={"limit": body["limit"]} if body.get("limit") else None)
            return public(it)
    except KeyError as exc:
        raise ext.HTTPError(404, str(exc.args[0]))
    except ValueError as exc:
        raise ext.HTTPError(400, str(exc))
    return None


@ext.register("action")
def _action(project, a, ctx):
    """The agent's way into the ledger: it adds an item (a step for the student); it can never accept, close or remove one."""
    if a.get("type") != "ledger.track":
        return None
    title = str(a.get("title") or "").strip()
    if not title:
        raise ValueError("ledger.track needs a title")
    it = add(project, key_of(title), "hand_step", title, str(a.get("detail") or ""), page=str(a.get("page") or ""), source="agent")
    return f"ledger.track:{it['id']}"


# ---------------------------------------------------------------- the chat

def annotate_reply(project, reply):
    """The reply with the ledger's part added: (text, [ids]). Every hand step in it becomes an item ("Tracked: F-007"), every limit it states
    becomes an item, advice that breaks a system rule is named and withdrawn, and a false "cannot" about something the tool does is
    corrected. The agent's text is never rewritten, only followed by short lines."""
    import limits
    text = str(reply or "")
    ids, notes = [], []
    try:
        tracked = track_advice(project, text, source="agent")
        for t in tracked:
            ids.append(t["id"])
            if t.get("conflict"):
                c = t["conflict"]
                notes.append(f"Do not follow the step in {t['id']}: it breaks a rule of this tool ({c['rule']}). {c['why']}")
        for it in limits.track_text(project, text):
            if it["id"] not in ids:
                ids.append(it["id"])
    except LedgerCorrupt as exc:
        notes.append(f"Nothing in this reply was added to your Findings list. {exc}")
    wrong = limits.false_claims(text)
    if wrong:
        notes.append(limits.correction(wrong))
    if ids:
        notes.append("Tracked on your Findings list: " + ", ".join(ids) + ". Press Done there when you have done it and the tool checks the file again.")
    return (text + "".join("\n\n" + n for n in notes)).strip(), ids
