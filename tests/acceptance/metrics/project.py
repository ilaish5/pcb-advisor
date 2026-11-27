"""Project-data metrics (artifact part of W2, W5, W7, W8, W9, W10, W12, W14, W16, W25(b), W36, F-J(b), U5).

Each check reads the project folder (ctx.project) with the independent readers in oracle/project.py and returns the offending
items as `measured`. Each control builds a corrected copy and then proves the check is not blind: a canary is injected at a
random place of the corrected copy (ctx.rng, canaries/project.py) and the check must fail on exactly that item, while the
untouched twin stays clean. A control whose canary is missed raises, which the runner reports as an error, never a pass.

Scope rule: a check whose scope is empty (nothing to examine) FAILS with the scope count in `detail`; it never passes on an
empty project, so deleting the evidence (chat, goal, log) cannot turn a metric green.
"""
from __future__ import annotations

import copy
import json
import pathlib
import re

from lib import Ctx, Result, metric
from oracle import project as PO
from canaries import project as CAN


# ----------------------------------------------------------------------------- helpers
def _P(ctx: Ctx) -> PO.Project:
    return PO.Project(ctx.project)


def _result(items: list, expected: str, detail: str, ev: list, scope: int, empty_status: str = "fail") -> Result:
    if scope == 0:
        return Result(empty_status, measured=None, expected=expected, evidence=ev,
                      detail="scope empty: nothing was examined, so this cannot pass. " + detail)
    return Result("pass" if not items else "fail", measured=items, expected=expected,
                  detail=f"n={len(items)}; scope={scope}. {detail}".strip(), evidence=ev)


def _ev(ctx: Ctx, *rels: str) -> list:
    out = []
    for rel in rels:
        p = ctx.project / rel
        if p.is_file():
            out.append(ctx.ev(p, rel))
    return out


def _selftest(control_ctx: Ctx, check, inject, name: str, must_name) -> None:
    """Canary proof: inject into a copy of the corrected control, the check must FAIL and name the injected item."""
    c = control_ctx.writable_copy(name)
    info = inject(c)
    r = check(c)
    named = r.status == "fail" and must_name(info, [str(x) for x in (r.measured or [])])
    if not named:
        raise AssertionError(f"canary {name} not caught: status={r.status} injected={info} measured={r.measured}")


def _assert_clean(c: Ctx, check, what: str) -> None:
    r = check(c)
    if r.status != "pass":
        raise AssertionError(f"{what}: corrected control still {r.status}: {str(r.measured)[:200]}")


# ============================================================================= W2
_SIZE = re.compile(r"(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*mm", re.I)
_LAYERS = re.compile(r"(\d+)\s*[- ]\s*layers?", re.I)
_REPLACES = re.compile(r"(replaces?|replaced|instead of|formerly|previously|was|not|no longer)\W+(?:\w+\W+){0,3}$", re.I)


def _idea_texts(idea: dict):
    """(location, text) of every live text of an idea: goal, agreed items, diagram. `prev_text` is history, never live."""
    if idea.get("goal") and idea.get("goal_status") != "stale" and not idea.get("goal_stale"):
        yield "goal", idea["goal"]
    for a in idea.get("agreed", []):
        if a.get("status") != "stale" and not a.get("stale"):
            yield f"agreed:{a.get('topic')}", a.get("text", "")
    d = idea.get("diagram") or {}
    for s in d.get("shapes", []):
        if s.get("text"):
            yield f"diagram:{s.get('id')}", s["text"]
    for f in d.get("frames", []):
        if f.get("title"):
            yield f"diagram:frame:{f.get('id', f.get('title'))}", f["title"]


def _stale_entities(idea: dict, bom: dict, replaced: set, layers: int | None) -> set:
    cur = {PO.norm_alnum(s.get("mpn")) for s in bom.values() if s.get("mpn")}
    cur |= {PO.norm_alnum(s.get("value")) for s in bom.values() if s.get("value")}
    cur.discard("")
    out = set()
    board = idea.get("board") or {}
    for loc, text in _idea_texts(idea):
        for m in PO.tokens(text):
            nt = PO.norm_alnum(m)
            if len(nt) < 5 or any(c.startswith(nt) or nt.startswith(c) for c in cur if len(c) >= 5):
                continue
            if any(r.startswith(nt) for r in replaced):
                before = text[:text.find(m)]
                if not _REPLACES.search(before[-48:]):
                    out.add((loc, "mpn", m))
        if board.get("width_mm") and board.get("height_mm"):
            for sm in _SIZE.finditer(text):
                near = text[max(0, sm.start() - 40): sm.end() + 40].lower()
                if loc == "goal" or "board" in near:
                    w, h = float(sm.group(1)), float(sm.group(2))
                    bw, bh = float(board["width_mm"]), float(board["height_mm"])
                    if not ((abs(w - bw) < 0.01 and abs(h - bh) < 0.01) or (abs(w - bh) < 0.01 and abs(h - bw) < 0.01)):
                        out.add((loc, "size", sm.group(0)))
        if layers:
            for lm in _LAYERS.finditer(text):
                if int(lm.group(1)) != layers and (loc == "goal" or "board" in text.lower() or loc == "agreed:Board"):
                    out.add((loc, "layers", lm.group(0)))
    return out


def w2_items(P: PO.Project) -> tuple[list, int]:
    versions = list(P.versions)
    final = {"n": "final", "ts": "9999", "idea": P.idea}
    layers = (P.project_json.get("board") or {}).get("layers")
    events = sorted({PO.tkey(v["ts"]) for v in versions} | {PO.tkey(r["ts"]) for r in P.bomlog})
    found, scope = {}, 0
    for t in events + ["9999"]:
        tk = "9999.999" if t == "9999" else PO.tkey(t, ".999")
        cands = [v for v in versions + [final] if PO.tkey(v["ts"]) <= tk]
        if not cands:
            continue
        v = cands[-1]
        bom = PO.replay_bom(P.bomlog, upto=t if t != "9999" else None)
        replaced = set()
        for r in P.bomlog:
            if PO.tkey(r["ts"]) > (PO.tkey(t, ".999") if t != "9999" else "z"):
                break
            old = (r.get("before") or {}).get("mpn")
            if old and old != (r.get("changes") or {}).get("mpn"):
                replaced.add(PO.norm_alnum(old))
        scope += 1
        for ent in _stale_entities(v["idea"], bom, replaced, layers):
            found.setdefault(ent, (v["n"], t))
    items = [f"{loc}:{kind}:{tok} (first seen in idea v{n} at {t[:19]})" for (loc, kind, tok), (n, t) in sorted(found.items(), key=str)]
    return items, scope


def _w2_control(ctx: Ctx) -> Ctx:
    c = ctx.writable_copy("W2-control")
    P = _P(c)
    items, _ = w2_items(P)
    # corrected copy: every stale token is replaced by the value the BOM holds now for the line that replaced it
    bom_now = PO.replay_bom(P.bomlog)
    repl = {}
    for r in P.bomlog:
        old = (r.get("before") or {}).get("mpn")
        if old and old != (r.get("changes") or {}).get("mpn"):
            repl[PO.norm_alnum(old)] = bom_now[r["line"]].get("mpn") or r["changes"].get("mpn")

    def fix_text(t: str) -> str:
        for m in PO.tokens(t):
            nt = PO.norm_alnum(m)
            for old, new in repl.items():
                if len(nt) >= 5 and old.startswith(nt) and new and not PO.norm_alnum(new).startswith(nt):
                    t = t.replace(m, new)
        return t

    # only fix what the check flags: entities named in `items` are in goal/agreed/diagram of some version
    vs = json.loads((c.project / "idea-versions.json").read_text(encoding="utf-8"))
    for v in vs:
        # keep legitimate "replaces" notes untouched: fix_text is applied only where the check found a stale token
        idea = v["idea"]
        for loc, text in list(_idea_texts(idea)):
            if any(it.startswith(loc + ":") for it in items):
                if loc == "goal":
                    idea["goal"] = fix_text(idea["goal"])
                elif loc.startswith("agreed:"):
                    for a in idea["agreed"]:
                        if f"agreed:{a.get('topic')}" == loc:
                            a["text"] = fix_text(a["text"])
                elif loc.startswith("diagram:"):
                    for s in idea["diagram"]["shapes"]:
                        if f"diagram:{s.get('id')}" == loc and s.get("text"):
                            s["text"] = fix_text(s["text"])
    (c.project / "idea-versions.json").write_text(json.dumps(vs, ensure_ascii=False, indent=1), encoding="utf-8")
    idea = json.loads((c.project / "idea.json").read_text(encoding="utf-8"))
    for loc, text in list(_idea_texts(idea)):
        if any(it.startswith(loc + ":") for it in items):
            if loc == "goal":
                idea["goal"] = fix_text(idea["goal"])
    (c.project / "idea.json").write_text(json.dumps(idea, ensure_ascii=False, indent=1), encoding="utf-8")
    _assert_clean(c, w2, "W2")
    _selftest(c, w2, CAN.inject_w2, "W2-canary",
              lambda info, m: any(PO.norm_alnum(info["token"]) in PO.norm_alnum(x) for x in m))
    return c


@metric(id="W2", title="Stale entities (board size, layers, MPN) in goal/agreed/diagram vs saved values, replayed over idea versions and BOM writes",
        root="R1", p0=("P0-3",), level="U", control=_w2_control)
def w2(ctx: Ctx) -> Result:
    P = _P(ctx)
    items, scope = w2_items(P)
    return _result(items, "unmarked stale entities = 0",
                   "frozen regexes: size, N-layer, part-number tokens vs replayed bom-log and the version's own board field; "
                   "prev_text is history and is not scanned; a text marked stale is exempt",
                   _ev(ctx, "idea-versions.json", "idea.json", "bom-log.jsonl", "project.json"), scope)


# ============================================================================= W4
def _item_parts(P: PO.Project, text: str, names: list[str]) -> set[str]:
    """Part families (>= 6 characters) named in an item text that also name a source of this project."""
    fams = {PO.family(n) for n in names}
    return {PO.family(tk) for tk in PO.tokens(text) if len(PO.family(tk)) >= 6} & fams


def _cite_field_ok(P: PO.Project, item: dict, parts: set[str]) -> bool:
    cites = item.get("cites") or []
    for c in cites if isinstance(cites, list) else []:
        if not isinstance(c, dict):
            continue
        pages = P.source_pages(str(c.get("file", "")))
        page, quote = c.get("page"), c.get("quote")
        if not pages or not isinstance(page, int) or not 1 <= page <= len(pages) or not quote:
            continue
        if PO.norm_ws(quote) not in PO.norm_ws(pages[page - 1]):
            continue
        if parts and PO.family(str(c["file"])) not in parts:
            continue                                   # the item names a part; the cite must be about that part
        return True
    return False


def w4_items(P: PO.Project) -> tuple[list, int]:
    names = P.source_names()
    recs = [r for r in P.cite_records() if r["status"] == "ok"]
    out, scope, backed = [], 0, 0
    for a in P.idea.get("agreed", []):
        if a.get("status") != "confirmed" or a.get("by") == "student":
            continue
        scope += 1
        parts = _item_parts(P, a.get("text", ""), names)
        ok = _cite_field_ok(P, a, parts) or any(PO.family(r["file"]) in parts for r in recs)
        backed += ok
        if not ok:
            out.append(f"{a.get('topic')}: confirmed by {a.get('by')}, no structured cite (file + page) that can be re-checked"
                       + (f"; names {sorted(parts)}" if parts else ""))
    if scope and not backed:
        out.append("no confirmed item carries a cite: nothing can be re-checked")
    return out, scope


def _w4_control(ctx: Ctx) -> Ctx:
    c = ctx.writable_copy("W4-control")
    P = _P(c)
    names = P.source_names()
    idea = json.loads((c.project / "idea.json").read_text(encoding="utf-8"))
    for a in idea["agreed"]:
        if a.get("status") != "confirmed" or a.get("by") == "student":
            continue
        parts = _item_parts(P, a.get("text", ""), names)
        if _cite_field_ok(P, a, parts):
            continue
        for n in [n for n in names if not parts or PO.family(n) in parts]:
            for i, pg in enumerate(P.source_pages(n) or [], 1):
                words = pg.split()
                if len(words) >= 8:                     # a real quote from a real page of a file that names the part
                    a["cites"] = [{"file": n, "page": i, "quote": " ".join(words[:8])}]
                    break
            if a.get("cites"):
                break
    (c.project / "idea.json").write_text(json.dumps(idea, ensure_ascii=False, indent=1), encoding="utf-8")
    _assert_clean(c, w4, "W4")
    # twin: cited items stay confirmed in the control, and a copy with everything unverified must fail
    if not any(a.get("cites") and a.get("status") == "confirmed" for a in idea["agreed"]):
        raise AssertionError("W4 control has no cited item left confirmed")
    t = c.writable_copy("W4-unverified")
    ti = json.loads((t.project / "idea.json").read_text(encoding="utf-8"))
    for a in ti["agreed"]:
        a["status"] = "proposed"
    (t.project / "idea.json").write_text(json.dumps(ti, ensure_ascii=False, indent=1), encoding="utf-8")
    if w4(t).status != "fail":
        raise AssertionError("W4: 'unverify everything' passed")
    _selftest(c, w4, CAN.inject_w4, "W4-canary", lambda info, m: any(x.startswith(info["topic"] + ":") for x in m))
    return c


@metric(id="W4", title="Confirmed agreed items with no structured cite (file + page) that can be re-checked when a part changes", root="R3",
        p0=("P0-3",), level="B", control=_w4_control)
def w4(ctx: Ctx) -> Result:
    P = _P(ctx)
    items, scope = w4_items(P)
    return _result(items, "confirmed non-student items without a re-checkable cite = 0",
                   "cite-backed = a `cites` field (file, page, quote found on that page) or a cites.json record with status ok naming a "
                   "source for a part the item names (part-number tokens of the item text that match a source name). file_only records do "
                   "not count (no quote was compared). Student items are exempt. If no confirmed item is backed at all the check fails, so "
                   "unverifying everything cannot pass. cites.json records are per chat message, not per item: a per-item cites field "
                   "in the product would be the strong form of this check",
                   _ev(ctx, "idea.json") + [ctx.ev(p, "cites") for p in sorted((ctx.project / "chats").glob("*.cites.json"))], scope)


# ============================================================================= W5
_ASSUMED = re.compile(r"\(\s*assumed\s*\)", re.I)


def _is_assumed(a: dict) -> bool:
    return bool(a.get("assumed")) or a.get("status") == "assumed" or bool(_ASSUMED.search(a.get("text", "")))


def w5a_items(P: PO.Project) -> tuple[list, int]:
    seen, scope = {}, 0
    for v in P.versions + [{"n": "final", "ts": "", "idea": P.idea}]:
        for a in v["idea"].get("agreed", []):
            scope += 1
            if _is_assumed(a) and a.get("status") == "confirmed" and a.get("by") != "student":
                seen.setdefault((a.get("topic"), a.get("text", "")), v["n"])
    return [f"{t}: by agent, confirmed, assumed (first in idea v{n})" for (t, _), n in seen.items()], scope


def _w5a_control(ctx: Ctx) -> Ctx:
    c = ctx.writable_copy("W5a-control")
    vs = json.loads((c.project / "idea-versions.json").read_text(encoding="utf-8"))

    def fix(idea):
        for a in idea.get("agreed", []):
            if _is_assumed(a) and a.get("status") == "confirmed" and a.get("by") != "student":
                a["status"] = "proposed"          # an assumed item stays a proposal until the student acts on it
    for v in vs:
        fix(v["idea"])
    (c.project / "idea-versions.json").write_text(json.dumps(vs, ensure_ascii=False, indent=1), encoding="utf-8")
    idea = json.loads((c.project / "idea.json").read_text(encoding="utf-8"))
    fix(idea)
    (c.project / "idea.json").write_text(json.dumps(idea, ensure_ascii=False, indent=1), encoding="utf-8")
    _assert_clean(c, w5a, "W5(a)")
    _selftest(c, w5a, CAN.inject_w5a, "W5a-canary", lambda info, m: any(info["topic"] in x for x in m))
    return c


@metric(id="W5(a)", title="Assumed items confirmed by the agent (state vs the assumed marker)", root="R2", p0=("P0-3",), level="U",
        control=_w5a_control)
def w5a(ctx: Ctx) -> Result:
    items, scope = w5a_items(_P(ctx))
    return _result(items, "assumed items confirmed by someone other than the student = 0",
                   "assumed = `assumed` field, status 'assumed', or the frozen text marker '(assumed)' (an item that only "
                   "says 'assumed' inside other words is not matched)",
                   _ev(ctx, "idea-versions.json", "idea.json"), scope)


def _agreed_sig(idea: dict) -> dict:
    return {(a.get("topic"), a.get("text")): a for a in idea.get("agreed", [])}


def w5b_items(P: PO.Project) -> tuple[list, int]:
    out, scope = [], 0
    vs = P.versions
    for prev, cur in zip([None] + vs[:-1], vs):
        idea = cur["idea"]
        if not idea.get("confirmed") or not idea.get("confirmed_at"):
            continue
        scope += 1
        marker = idea.get("changed_since_confirm") or idea.get("needs_reconfirm") or idea.get("confirm_stale")
        old = _agreed_sig(prev["idea"]) if prev else {}
        changed = [a for k, a in _agreed_sig(idea).items() if k not in old]
        late = [a for a in changed if PO.tkey(a.get("ts", "")) > PO.tkey(idea["confirmed_at"])]
        if late and not marker:
            out.append(f"idea v{cur['n']}: {len(late)} agreed item(s) changed after confirmed_at {idea['confirmed_at']}, still 'confirmed' "
                       f"({late[0].get('topic')}...)")
    return out, scope


def _w5b_control(ctx: Ctx) -> Ctx:
    c = ctx.writable_copy("W5b-control")
    vs = json.loads((c.project / "idea-versions.json").read_text(encoding="utf-8"))
    bad = {int(re.match(r"idea v(\d+)", s).group(1)) for s in w5b_items(_P(c))[0]}
    for v in vs:
        if v["n"] in bad:                          # a save that changed an agreed item reopens the confirmation
            v["idea"]["confirmed"] = False
            v["idea"].pop("confirmed_at", None)
            v["idea"]["changed_since_confirm"] = True
    (c.project / "idea-versions.json").write_text(json.dumps(vs, ensure_ascii=False, indent=1), encoding="utf-8")
    _assert_clean(c, w5b, "W5(b)")
    _selftest(c, w5b, CAN.inject_w5b, "W5b-canary",
              lambda info, m: any(f"idea v{info['n_bad']}:" in x for x in m) and not any(f"idea v{info['n_twin']}:" in x for x in m))
    return c


@metric(id="W5(b)", title="A save that changes an agreed item after confirmed_at keeps the idea 'confirmed'", root="R2", p0=("P0-3",),
        level="U", control=_w5b_control)
def w5b(ctx: Ctx) -> Result:
    items, scope = w5b_items(_P(ctx))
    return _result(items, "confirmed versions holding agreed items changed after confirmed_at, without a changed-since-confirm marker = 0",
                   "only saves that change an agreed item count (diff vs the previous version); constraint-only saves and no-op saves "
                   "do not. Markers recognised: changed_since_confirm, needs_reconfirm, confirm_stale, or confirmed=false",
                   _ev(ctx, "idea-versions.json"), scope)


# ============================================================================= W7
_RANGE = re.compile(r"\b([A-Z]{1,3})(\d+)\s*[-–]\s*(?:\1)?(\d+)\b")
_MULT = [re.compile(r"\b(\d+)\s*[x×]\s*\("), re.compile(r"\(\s*[x×]\s*(\d+)\s*\)")]
_SLASH = re.compile(r"((?:[A-Za-z][A-Za-z0-9_+]*(?:-[A-Za-z0-9]+)?)(?:\s*/\s*[A-Za-z][A-Za-z0-9_+]*(?:-[A-Za-z0-9]+)?)+)\s+"
                    r"(?:pull-?ups?|pull-?downs?|resistors?|caps?|capacitors?|buttons?|LEDs?|diodes?)\b", re.I)


def implied_count(role: str, reason: str) -> int | None:
    """N parts implied by a role/reason text, by frozen forms; None when no form applies or the forms disagree."""
    found = set()
    for text in (role or "", reason or ""):
        for rx in _MULT:
            for m in rx.finditer(text):
                found.add(int(m.group(1)))
        for m in _SLASH.finditer(text):
            n = 0
            for item in re.split(r"\s*/\s*", m.group(1)):
                rm = re.fullmatch(r"([A-Za-z]+)(\d+)-\1?(\d+)", item.strip())
                n += (int(rm.group(3)) - int(rm.group(2)) + 1) if rm else 1
            found.add(n)
        for m in _RANGE.finditer(text):
            found.add(int(m.group(3)) - int(m.group(2)) + 1)
    return found.pop() if len(found) == 1 else None


def w7_items(P: PO.Project) -> tuple[list, int]:
    out, scope, seen = [], 0, set()
    for r in P.bomlog:                                    # first applied write of each line = the first BOM
        if r["line"] in seen or "refs" not in (r.get("changes") or {}):
            continue
        seen.add(r["line"])
        scope += 1
        ch = r["changes"]
        n = implied_count(ch.get("role"), r.get("reason"))
        if n and n > 1 and len(ch["refs"]) != n:
            out.append(f"{r['line']}: first applied with {len(ch['refs'])} ref(s), role/reason imply {n} "
                       f"({(ch.get('role') or '')[:40]!r}) at {r['ts'][11:19]}")
    parts = P.netlist_parts()
    if parts:
        net_refs = {p["ref"] for p in parts}
        for line in P.bom:
            miss = [x for x in line.get("refs", []) if x not in net_refs]
            if miss:
                out.append(f"{line['key']}: BOM refs {miss} missing from the netlist")
        bom_refs = {x for line in P.bom for x in line.get("refs", [])}
        extra = sorted(net_refs - bom_refs)
        if extra:
            out.append(f"netlist refs without a BOM line: {extra}")
    return out, scope


def _w7_control(ctx: Ctx) -> Ctx:
    c = ctx.writable_copy("W7-control")
    P = _P(c)
    rows = list(P.bomlog)
    final = {l["key"]: l for l in P.bom}
    seen, fix = set(), {}
    for r in rows:
        if r["line"] in seen or "refs" not in r["changes"]:
            continue
        seen.add(r["line"])
        n = implied_count(r["changes"].get("role"), r.get("reason"))
        if n and n > 1 and len(r["changes"]["refs"]) != n:
            fix[(r["ts"], r["line"])] = n
    out = []
    for r in rows:
        k = (r["ts"], r["line"])
        if k in fix:
            base = final.get(r["line"], {}).get("refs", r["changes"]["refs"])
            refs = list(base[:fix[k]]) if len(base) >= fix[k] else list(base) + [f"{r['line']}x{i}" for i in range(fix[k] - len(base))]
            r["changes"]["refs"] = refs
        out.append(r)
    (c.project / "bom-log.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in out) + "\n", encoding="utf-8")
    _assert_clean(c, w7, "W7")
    _selftest(c, w7, CAN.inject_w7, "W7-canary", lambda info, m: any(x.startswith(info["line"] + ":") for x in m))
    return c


@metric(id="W7", title="First-applied BOM lines whose refs differ from the count their role implies; BOM vs netlist refs", root="R3",
        level="U", control=_w7_control)
def w7(ctx: Ctx) -> Result:
    P = _P(ctx)
    items, scope = w7_items(P)
    first = {}
    for r in P.bomlog:
        if "refs" in r["changes"] and r["line"] not in first:
            first[r["line"]] = r
    t0 = min((r["ts"] for r in first.values()), default="")
    batch = [r for r in first.values() if r["ts"][:19] == t0[:19]]
    corroboration = (f"first approved batch {sum(len(r['changes']['refs']) for r in batch)} refs / {len(batch)} lines "
                     f"vs final BOM {sum(len(l.get('refs', [])) for l in P.bom)} refs")
    return _result(items, "lines whose refs count differs from the implied count = 0; BOM refs = netlist refs",
                   "implied count by frozen forms ('2 x (', 'A/B pull-ups', designator ranges); ambiguous texts are skipped; " + corroboration,
                   _ev(ctx, "bom-log.jsonl", "bom.json"), scope)


# ============================================================================= W8
def _approved_ids(P: PO.Project) -> dict:
    return {p["id"]: p for p in P.proposals if p.get("status") == "approved"}


def w8a_items(P: PO.Project) -> tuple[list, int]:
    appr = _approved_ids(P)
    out, scope = [], 0
    for p in P.proposals:
        if p.get("kind") != "bom" or p["id"] not in appr:
            continue
        scope += 1
        ch, bf = p.get("changes") or {}, p.get("before") or {}
        if not any(ch.get(k) != bf.get(k) for k in ch):
            out.append(f"{p['id']} line {p.get('line')} ({p['ts'][11:19]}): changes == before, approved by {appr[p['id']].get('by')}")
    return out, scope


def _w8a_control(ctx: Ctx) -> Ctx:
    c = ctx.writable_copy("W8a-control")
    P = _P(c)
    noop = {s.split()[0] for s in w8a_items(P)[0]}
    rows = []
    for r in P.proposals:
        if r["id"] in noop and r.get("status") == "approved":
            rows.append({"id": r["id"], "ts": r["ts"], "status": "refused", "by": "server",
                         "reason": f"{r['id']}: no field changes; nothing to apply"})
        else:
            rows.append(r)
    (c.project / "proposals.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n", encoding="utf-8")
    _assert_clean(c, w8a, "W8(a)")
    _selftest(c, w8a, CAN.inject_w8a, "W8a-canary", lambda info, m: any(info["id"] in x for x in m))
    return c


@metric(id="W8(a)", title="Approved proposal cards with no effective change", root="R1", p0=("P0-3", "P0-1"), level="B", control=_w8a_control)
def w8a(ctx: Ctx) -> Result:
    items, scope = w8a_items(_P(ctx))
    return _result(items, "approved cards with changes == before = 0", "approved = a later status record 'approved' for the card id",
                   _ev(ctx, "proposals.jsonl"), scope)


_COUNT_CLAIMS = [
    re.compile(r"\bBOM\b[^.\n]{0,24}?\b(?:has|holds|contains|lists|shows|carries)\s+\**(\d+)\**\s+(parts?|components?|lines?|refs?|designators?)\b", re.I),
]


def w8b_items(P: PO.Project) -> tuple[list, int]:
    out, scope = [], 0
    for m in P.chat:
        if m.get("role") != "agent":
            continue
        state = None
        for rx in _COUNT_CLAIMS:
            for hit in rx.finditer(m.get("text", "")):
                scope += 1
                if state is None:
                    state = PO.bom_totals(PO.replay_bom(P.bomlog, upto=m["ts"]))
                n, unit = int(hit.group(1)), hit.group(2).lower()
                actual = state[0] if unit.startswith("line") else state[1]
                if n != actual:
                    out.append(f"{m['ts'][11:19]}: says {n} {unit}, bom-log replay at that time has {actual}")
    return out, scope


def _w8b_control(ctx: Ctx) -> Ctx:
    c = ctx.writable_copy("W8b-control")
    P = _P(c)
    rows = list(P.chat)
    for m in rows:
        if m.get("role") != "agent":
            continue
        state = PO.bom_totals(PO.replay_bom(P.bomlog, upto=m["ts"]))
        for rx in _COUNT_CLAIMS:
            def fix(h):
                unit = h.group(2).lower()
                real = state[0] if unit.startswith("line") else state[1]
                return h.group(0).replace(h.group(1), str(real), 1)
            m["text"] = rx.sub(fix, m["text"])
    by_file: dict = {}
    for m in rows:
        by_file.setdefault(m.pop("_file"), []).append(m)
    for fn, ms in by_file.items():
        (c.project / "chats" / fn).write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in ms) + "\n", encoding="utf-8")
    _assert_clean(c, w8b, "W8(b)")
    _selftest(c, w8b, CAN.inject_w8b, "W8b-canary", lambda info, m: any(info["ts"][11:19] in x for x in m))
    return c


@metric(id="W8(b)", title="Counts the agent states about the BOM vs the bom-log replay at message time", root="R1", p0=("P0-3",), level="B",
        control=_w8b_control)
def w8b(ctx: Ctx) -> Result:
    items, scope = w8b_items(_P(ctx))
    return _result(items, "stated BOM counts that differ from the replay at message time = 0",
                   "frozen regex: 'BOM ... has|holds|contains N parts|lines'; card counts ('N BOM lines as cards'), forward-looking sentences and counts of "
                   "sheet/netlist parts are not matched. The LLM-judge half of W8(b) is behaviour and is not registered here",
                   _ev(ctx, "bom-log.jsonl") + [ctx.ev(p, "chat") for p in sorted((ctx.project / "chats").glob("*.jsonl"))], scope)


# ============================================================================= W9
_DEST = [("bom", re.compile(r"\bBOM\b", re.I)),
         ("schematic", re.compile(r"\bschematic\b|\bsheet\b|\blabel\b", re.I)),
         ("library", re.compile(r"\blibrary\b|\bsymbol\b|\bfootprint\b", re.I))]
_REF = re.compile(r"\{\{ref:([A-Za-z]+\d+)\}\}")


def _next_msg_ts(chat: list, ts: str) -> str:
    for m in chat:
        if PO.tkey(m["ts"]) > PO.tkey(ts, ".999"):
            return m["ts"]
    return "9999"


def w9_items(ctx: Ctx, P: PO.Project) -> tuple[list, int]:
    cards = {p["id"]: p for p in P.proposals if p.get("kind") == "bom"}
    out, scope = [], 0
    sch_files = sorted(ctx.altium.glob("*.SchDoc"))
    for a in PO.approval_messages(P.chat):
        named = [d for d, rx in _DEST if rx.search(a.get("text", ""))]
        card = cards.get(a.get("proposal"))
        if not named or not card:
            continue
        scope += 1
        end = _next_msg_ts(P.chat, a["ts"])
        line = card.get("line")
        state_end = PO.replay_bom(P.bomlog, upto=end if end != "9999" else None).get(line, {})
        refs = state_end.get("refs") or [line]
        bad = []
        if "bom" in named:
            row = [r for r in P.bomlog if r.get("proposal") == card["id"]]
            vals_ok = all(state_end.get(k) == v for k, v in (card.get("changes") or {}).items())
            if not row or not vals_ok:
                bad.append("bom")
        if "schematic" in named:
            seen_refs, seen_text = set(), ""
            for f in sch_files:
                st, _how = PO.schdoc_state_at(ctx.altium, f.name, a["ts"])
                if st is None:
                    continue
                seen_refs |= PO.schdoc_designators(st)
                seen_text += " " + " ".join(v for r in PO.schdoc_records(st) for v in r.values())
            new_mpn = (card.get("changes") or {}).get("mpn")
            if not set(refs) <= seen_refs or (new_mpn and PO.norm_alnum(new_mpn) not in PO.norm_alnum(seen_text)):
                bad.append("schematic")
        if "library" in named:
            wrote = [r for r in P.librarylog if r.get("line") == line and a["ts"] <= r["ts"] and PO.tkey(r["ts"]) <= PO.tkey(end, ".999")
                     and any((r.get("changes") or {}).get(k) for k in ("symbol", "footprint", "step"))]
            if not wrote:
                bad.append("library")
        if bad:
            out.append(f"{a['ts'][11:19]} {line}: text names {named}; not changed at that time: {bad}")
    return out, scope


def _w9_control(ctx: Ctx) -> Ctx:
    c = ctx.writable_copy("W9-control")
    # the backup folders are what makes the schematic state at approval time readable: carry the SchDoc ones into the copy
    src = ctx.altium / ".advisor-backup"
    if src.is_dir():
        import shutil
        for d in src.iterdir():
            for f in d.glob("*.SchDoc"):
                (c.altium / ".advisor-backup" / d.name).mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, c.altium / ".advisor-backup" / d.name / f.name)
    P = _P(c)
    bad = {s.split()[0] for s in w9_items(c, P)[0]}          # HH:MM:SS of the approval texts that claim an unchanged destination

    def fix(m):
        if m.get("decision") == "approved" and m["ts"][11:19] in bad:
            m["text"] = "Approved. The BOM line is updated."          # corrected: the text claims only the destination that did change
    CAN.rewrite_chat(c, fix)
    _assert_clean(c, w9, "W9")
    _selftest(c, w9, CAN.inject_w9(ctx.altium), "W9-canary", lambda info, m: any(info["line"] in x for x in m))
    return c


@metric(id="W9", title="Approval texts naming a destination (BOM, schematic, library) that did not change at that time", root="R1",
        p0=("P0-3",), level="L", control=_w9_control)
def w9(ctx: Ctx) -> Result:
    items, scope = w9_items(ctx, _P(ctx))
    return _result(items, "approval texts naming a destination that is unchanged = 0",
                   "destination phrases: BOM; schematic/sheet/label; library/symbol/footprint. BOM = bom-log row for the card + replayed "
                   "values; schematic = the SchDoc as it was at approval time (first .advisor-backup copy after the approval, else the "
                   "current file) must hold the card's refs (and new MPN) by olefile; library = a library-log write for the line before "
                   "the next chat message. Texts that name nothing (e.g. 'Approved 5 proposals') are out of scope",
                   _ev(ctx, "proposals.jsonl", "bom-log.jsonl", "library-log.jsonl") + [ctx.ev(f, "SchDoc") for f in sorted(ctx.altium.glob("*.SchDoc"))], scope)


# ============================================================================= W10
def w10_items(P: PO.Project) -> tuple[list, int]:
    eps = PO.duplicate_episodes(P.bomlog)
    items = []
    for e in eps:
        dur = f"{PO.minutes_between(e['start'], e['end']):.1f} min" if e["end"] else "still open after the last write"
        items.append(f"{e['ref']} on lines {e['lines']} from {e['start'][11:19]}: {dur}")
    return items, len(P.bomlog)


def _w10_control(ctx: Ctx) -> Ctx:
    c = ctx.writable_copy("W10-control")
    P = _P(c)
    eps = PO.duplicate_episodes(P.bomlog)
    rows = list(P.bomlog)
    for e in eps:                                   # corrected: the card that created the duplicate was refused up front
        for r in rows:
            ch = r.get("changes") or {}
            if "refs" in ch and e["ref"] in ch["refs"] and r["line"] != e["ref"] and r["line"] in e["lines"] and PO.tkey(r["ts"]) <= PO.tkey(e["start"]):
                ch["refs"] = [x for x in ch["refs"] if x != e["ref"]]
    (c.project / "bom-log.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n", encoding="utf-8")
    _assert_clean(c, w10, "W10")
    _selftest(c, w10, CAN.inject_w10, "W10-canary", lambda info, m: any(info["ref"] in x for x in m))
    return c


@metric(id="W10", title="Duplicate designators across BOM lines (bom-log replay)", root="R2", level="U", control=_w10_control)
def w10(ctx: Ctx) -> Result:
    items, scope = w10_items(_P(ctx))
    return _result(items, "persisted duplicate-ref states = 0", "episode = one ref on two or more lines between two writes",
                   _ev(ctx, "bom-log.jsonl"), scope)


# ============================================================================= W12
def w12_items(P: PO.Project) -> tuple[list, int]:
    out, scope = [], 0
    state: dict[str, dict] = {}
    open_w: dict[str, dict] = {}
    undecidable = set()

    def verdict(line: str, st: dict):
        ds, mpn = st.get("datasheet"), st.get("mpn")
        if not ds or not mpn:
            return "ok"
        text = P.source_text(ds)
        if text is None:
            undecidable.add(f"{line}:{ds}")
            return "unknown"
        return "ok" if PO.mentions_part(text, mpn) else "stale"
    for r in P.bomlog:
        line, ch = r["line"], r.get("changes") or {}
        st = state.setdefault(line, {})
        trigger = any(k in ch and ch[k] != st.get(k) for k in ("mpn", "lcsc")) and st.get("mpn") is not None
        st.update(ch)
        if "datasheet" in ch or trigger:
            v = verdict(line, st)
            if line in open_w and v != "stale":
                w = open_w.pop(line)
                out.append(f"{line}: datasheet {w['ds']} did not name {w['mpn']} from {w['start'][11:19]} to {r['ts'][11:19]} "
                           f"({PO.minutes_between(w['start'], r['ts']):.1f} min)")
            elif line in open_w and v == "stale" and trigger:
                w = open_w.pop(line)
                out.append(f"{line}: datasheet {w['ds']} did not name {w['mpn']} from {w['start'][11:19]} to {r['ts'][11:19]} "
                           f"({PO.minutes_between(w['start'], r['ts']):.1f} min)")
                open_w[line] = {"start": r["ts"], "ds": st["datasheet"], "mpn": st["mpn"]}
            elif trigger and v == "stale":
                open_w[line] = {"start": r["ts"], "ds": st["datasheet"], "mpn": st["mpn"]}
        if trigger:
            scope += 1
    for line, w in open_w.items():
        out.append(f"{line}: datasheet {w['ds']} still does not name {w['mpn']} after the last write")
    return out, scope


def _w12_control(ctx: Ctx) -> Ctx:
    c = ctx.writable_copy("W12-control")
    P = _P(c)
    items, _ = w12_items(P)
    stale_lines = {s.split(":")[0] for s in items}
    rows = list(P.bomlog)
    state: dict = {}
    for r in rows:
        ch = r["changes"]
        st = state.setdefault(r["line"], {})
        trig = any(k in ch and ch[k] != st.get(k) for k in ("mpn", "lcsc")) and st.get("mpn") is not None
        st.update(ch)
        if trig and r["line"] in stale_lines and st.get("datasheet") and not PO.mentions_part(P.source_text(st["datasheet"]) or "", st["mpn"]):
            ch["datasheet"] = None                   # corrected: unbound in the same write (pins/verify = not_checked)
            st["datasheet"] = None
    (c.project / "bom-log.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n", encoding="utf-8")
    _assert_clean(c, w12, "W12")
    _selftest(c, w12, CAN.inject_w12, "W12-canary", lambda info, m: any(x.startswith(info["line"] + ":") for x in m))
    return c


@metric(id="W12", title="MPN/LCSC change without a datasheet rebind (windows over bom-log)", root="R2", p0=("P0-3",), level="U",
        control=_w12_control)
def w12(ctx: Ctx) -> Result:
    items, scope = w12_items(_P(ctx))
    return _result(items, "stale datasheet bindings after an mpn/lcsc write = 0",
                   "window opens at an mpn/lcsc write whose bound datasheet text does not name the part (ordering-code family, normalised) "
                   "and closes at the write that rebinds or unbinds; a datasheet without extractable text cannot be judged and is not counted",
                   _ev(ctx, "bom-log.jsonl") + [], scope)


# ============================================================================= W14
_POLAR_REF = re.compile(r"^(D|LED|Q|CR)\d", re.I)
_POLAR_PIN = re.compile(r"^(A|K|ANODE|CATHODE|\+|-|POS|NEG|VF)$", re.I)


def w14_needs_check(line: dict, parts: dict) -> str | None:
    refs = line.get("refs") or [line.get("key")]
    maxpins = 0
    polar = False
    for ref in refs:
        p = parts.get(ref)
        if p:
            maxpins = max(maxpins, len(p.get("pins", [])))
            if any(_POLAR_PIN.match(str(q.get("name", ""))) for q in p.get("pins", [])):
                polar = True
        if _POLAR_REF.match(ref or ""):
            polar = True
    if re.search(r"polari|electrolytic|tantalum", f"{line.get('role', '')} {line.get('value', '')}", re.I):
        polar = True
    if maxpins > 2:
        return f"{maxpins} pins"
    if polar:
        return "polarised"
    return None


def w14_items(P: PO.Project) -> tuple[list, int]:
    parts = {p["ref"]: p for p in P.netlist_parts()}
    out, scope = [], 0
    for line in P.bom:
        why = w14_needs_check(line, parts)
        if not why:
            continue
        scope += 1
        if line.get("pins_status") not in ("verified", "accepted"):
            out.append(f"{line['key']} ({why}): pins_status={line.get('pins_status')!r}")
    return out, scope


def _w14_control(ctx: Ctx) -> Ctx:
    c = ctx.writable_copy("W14-control")
    P = _P(c)
    bad = {s.split()[0] for s in w14_items(P)[0]}
    d = json.loads((c.project / "bom.json").read_text(encoding="utf-8"))
    lines = d["lines"] if isinstance(d, dict) else d
    for l in lines:
        if l["key"] in bad:
            l["pins_status"] = "accepted"
    (c.project / "bom.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    _assert_clean(c, w14, "W14")
    _selftest(c, w14, CAN.inject_w14, "W14-canary", lambda info, m: any(x.startswith(info["key"] + " ") for x in m))
    return c


@metric(id="W14", title="Lines with polarity or more than 2 pins whose pins status is not verified/accepted", root="R2", p0=("P0-3",),
        level="B", control=_w14_control)
def w14(ctx: Ctx) -> Result:
    items, scope = w14_items(_P(ctx))
    return _result(items, "polarised or >2-pin lines whose status is not verified or accepted = 0",
                   "pin count from netlist/*.json parts; polarity from a D/LED/Q designator, anode/cathode-like pin names, or a polarised role. "
                   "The 'names k of n' half (oracle pin-table parser corpus) is not part of this registration",
                   _ev(ctx, "bom.json") + [ctx.ev(p, "netlist") for p in sorted((ctx.project / "netlist").glob("*.json"))], scope)


# ============================================================================= W16
def _pages_valid(P: PO.Project, name: str) -> tuple[bool, str]:
    pages = P.source_pages(name)
    if pages is None:
        return False, "no text"
    q = P.path("sources", name + ".quality.txt")
    if q.is_file():
        try:
            n = json.loads(q.read_text(encoding="utf-8")).get("pages")
        except ValueError:
            n = None
        if n and n != len(pages):
            return False, f"text has {len(pages)} chunks, quality file says {n} pages"
    return True, ""


def w16_items(P: PO.Project) -> tuple[list, int, list]:
    out, scope, skipped = [], 0, []
    for m in P.chat:
        if m.get("role") != "agent":
            continue
        for c in PO.page_cites(m.get("text", "")):
            scope += 1
            tag = f"{m['ts'][11:19]} {c['file']} p. {c['page']}"
            ok, why = _pages_valid(P, c["file"])
            if why == "no text":
                out.append(f"{tag}: source has no text file, a page cite cannot be backed")
                continue
            if not ok:
                skipped.append(f"{tag}: {why}")
                continue
            pages = P.source_pages(c["file"])
            if not c["quote"]:
                out.append(f"{tag}: page cite with no quote to compare")
            elif c["page"] > len(pages) or PO.norm_ws(c["quote"]) not in PO.norm_ws(pages[c["page"] - 1]):
                out.append(f"{tag}: quote not on that page")
    return out, scope, skipped


def _w16_control(ctx: Ctx) -> Ctx:
    c = ctx.writable_copy("W16-control")
    P = _P(c)

    def fix(m):
        if m.get("role") != "agent":
            return
        def sub(h):
            pm = PO.PAGE_LOC.match(h.group(2))
            if not pm:
                return h.group(0)
            f, page, quote = h.group(1).strip(), int(pm.group(1)), (pm.group(2) or "").strip()
            pages = P.source_pages(f)
            ok, why = _pages_valid(P, f)
            if pages is None or (ok and (not quote or page > len(pages) or PO.norm_ws(quote) not in PO.norm_ws(pages[page - 1]))):
                return "{{src:%s|%s}}" % (f, quote or "file only")   # renders as 'file only, not read'
            return h.group(0)
        m["text"] = PO.SRC_CITE.sub(sub, m["text"])
    CAN.rewrite_chat(c, fix)
    _assert_clean(c, w16, "W16")
    _selftest(c, w16, CAN.inject_w16, "W16-canary", lambda info, m: any(info["tag"] in x for x in m))
    return c


@metric(id="W16", title="Page cites whose quote is not on that page of the source text", root="R1", p0=("P0-3",), level="B", control=_w16_control)
def w16(ctx: Ctx) -> Result:
    items, scope, skipped = w16_items(_P(ctx))
    extra = f" Undecidable (chunk count != page count): {len(skipped)} cites, listed in evidence only." if skipped else ""
    r = _result(items, "page cites without a matching quote on that page = 0",
                "page = form-feed chunk of sources/<file>.txt; quote compared whitespace-normalised and case-folded; a page cite to a file "
                "with no text is a miss; files whose chunk count differs from the quality file's page count are skipped" + extra,
                [ctx.ev(p, "chat") for p in sorted((ctx.project / "chats").glob("*.jsonl"))], scope)
    return r


# ============================================================================= W25(b)
_REMOVE_VERB = re.compile(r"\b(remove|delete|drop|get rid|take (?:it |them )?out|discard|erase|cancel|without)\b", re.I)


def _names(item: dict) -> list[str]:
    kind = (item.get("kind") or "").lower()
    out = [str(item.get("id", "")).lower()]
    if kind:
        out += [kind, kind.replace("_", " "), kind.replace("_", "-")]
    if kind == "keepout":
        out += ["keep-out", "keep out"]
    return [x for x in out if x]


def w25b_items(P: PO.Project, chat: list | None = None) -> tuple[list, int]:
    out, scope = [], 0
    chat = P.chat if chat is None else chat
    vs = P.versions
    for prev, cur in zip(vs, vs[1:]):
        before = {i["id"]: i for i in (prev["idea"].get("constraints") or {}).get("items", [])}
        after = {i["id"] for i in (cur["idea"].get("constraints") or {}).get("items", [])}
        scope += len(before)
        for iid, item in before.items():
            if iid in after:
                continue
            asked = [m for m in chat if m.get("role") == "user"
                     and PO.tkey(prev["ts"]) < PO.tkey(m["ts"]) <= PO.tkey(cur["ts"], ".999")
                     and _REMOVE_VERB.search(m.get("text", "")) and any(n in m["text"].lower() for n in _names(item))]
            if not asked:
                out.append(f"{iid} ({item.get('kind')}) removed in idea v{cur['n']} at {cur['ts'][11:19]} with no student request")
    return out, scope


def _w25b_control(ctx: Ctx) -> Ctx:
    c = ctx.writable_copy("W25b-control")
    P = _P(c)
    removed = []
    for s in w25b_items(P)[0]:
        removed.append(s.split()[0])
    # a legitimate version of the story: the student explicitly asked for the removal in chat before the save
    vs = P.versions
    last_ts = vs[-1]["ts"]
    prev_ts = vs[-2]["ts"]
    txt = "Please remove the keep-out requirements " + ", ".join(removed)
    mid = prev_ts[:19]
    CAN.append_chat(c, {"ts": mid[:-2] + "30" if mid[-2:] < "30" else mid, "role": "user", "text": txt})
    _assert_clean(c, w25b, "W25(b)")
    _selftest(c, w25b, CAN.inject_w25b, "W25b-canary", lambda info, m: any(x.startswith(info["id"] + " ") for x in m) and not any(x.startswith(info["twin"] + " ") for x in m))
    return c


@metric(id="W25(b)", title="Requirement removed between idea versions without an explicit student request", root="R4", p0=("P0-3", "P0-1"),
        level="B", control=_w25b_control)
def w25b(ctx: Ctx) -> Result:
    items, scope = w25b_items(_P(ctx))
    return _result(items, "requirements removed with no student removal request = 0",
                   "removal = a constraints.items id present in version k-1 and absent in k; the request must be a user chat message between "
                   "the two saves that has a removal verb and names the id or its kind. Whether the check was failing is NOT evaluated here "
                   "(PcbDoc side belongs to W25(a))",
                   _ev(ctx, "idea-versions.json") + [ctx.ev(p, "chat") for p in sorted((ctx.project / "chats").glob("*.jsonl"))], scope)


# ============================================================================= W36
_RISK_HEAD = re.compile(r"risk|requirement|decision|condition|finding|accepted|ledger", re.I)


def _risk_sections(text: str) -> str:
    """Lines of a markdown text that sit under a heading naming risks, requirements, decisions, conditions or findings."""
    keep, on = [], False
    for ln in text.splitlines():
        if ln.lstrip().startswith("#"):
            on = bool(_RISK_HEAD.search(ln))
            continue
        if on:
            keep.append(ln)
    return "\n".join(keep)


def w36_items(P: PO.Project) -> tuple[list, int]:
    texts = P.export_texts()
    blob = "\n".join(_risk_sections(t) for t in texts.values())

    def listed(i: str) -> bool:
        return bool(re.search(r"(?<![A-Za-z0-9_])" + re.escape(i) + r"(?![A-Za-z0-9_])", blob))
    items, scope = [], 0
    for mp in P.order_manifests():
        for r in PO.read_json(mp).get("accepted_risks", []):
            scope += 1
            if not listed(str(r.get("line"))):
                items.append(f"accepted risk {r.get('line')} not listed in {sorted(texts)}")
    for it in ((P.idea.get("constraints") or {}).get("items") or []):
        scope += 1
        if not listed(str(it["id"])):
            items.append(f"requirement {it['id']} not listed in {sorted(texts)}")
    for name in ("ledger.json", "findings.json"):
        lp = P.path(name)
        if lp.is_file():
            d = PO.read_json(lp)
            for it in (d.get("items", []) if isinstance(d, dict) else d):
                if str(it.get("status", "open")) in ("open", "accepted"):
                    scope += 1
                    if not listed(str(it.get("id"))):
                        items.append(f"ledger item {it.get('id')} not listed")
    return items, scope


def _w36_control(ctx: Ctx) -> Ctx:
    c = ctx.writable_copy("W36-control")
    P = _P(c)
    ids = [re.search(r"(?:risk|requirement|item) (\S+)", s).group(1) for s in w36_items(P)[0]]
    p = c.project / "notes.md"
    p.write_text(p.read_text(encoding="utf-8") + "\n## Open risks and requirements (ids)\n\n" + "\n".join(f"- {i}" for i in ids) + "\n", encoding="utf-8")
    _assert_clean(c, w36, "W36")
    _selftest(c, w36, CAN.inject_w36, "W36-canary", lambda info, m: any(info["id"] in x for x in m))
    return c


@metric(id="W36", title="Recorded items (accepted risks, requirements, ledger) missing by id from the README/notes export", root="R1",
        p0=("P0-1",), level="B", control=_w36_control)
def w36(ctx: Ctx) -> Result:
    items, scope = w36_items(_P(ctx))
    return _result(items, "recorded items not listed by id = 0",
                   "recorded = order_manifest accepted_risks[].line, idea constraints items[].id, ledger.json/findings.json open or accepted "
                   "items; export text = README.md, notes.md, exports/*.md|txt; an id counts as listed when it occurs as a whole token on a line "
                   "inside a section whose heading names risks, requirements, decisions, conditions or findings. Ledger files found: "
                   + str(sum(1 for n in ("ledger.json", "findings.json") if (ctx.project / n).is_file())),
                   _ev(ctx, "idea.json", "notes.md", "README.md") + [ctx.ev(p, "manifest") for p in _P(ctx).order_manifests()], scope)


# ============================================================================= F-J(b)
def fjb_items(P: PO.Project) -> tuple[list, int]:
    out = [f"{l['key']}: lcsc={l.get('lcsc')!r} code={l.get('code')!r}" for l in P.bom
           if (l.get("lcsc") or "") != (l.get("code") or "")]
    return out, sum(1 for l in P.bom if l.get("lcsc") or l.get("code"))


def _fjb_control(ctx: Ctx) -> Ctx:
    c = ctx.writable_copy("FJb-control")
    d = json.loads((c.project / "bom.json").read_text(encoding="utf-8"))
    lines = d["lines"] if isinstance(d, dict) else d
    for l in lines:
        if l.get("code") and l.get("lcsc") != l["code"]:
            l["lcsc"] = l["code"]
    (c.project / "bom.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    _assert_clean(c, fjb, "F-J(b)")
    _selftest(c, fjb, CAN.inject_fjb, "FJb-canary", lambda info, m: any(x.startswith(info["key"] + ":") for x in m))
    return c


@metric(id="F-J(b)", title="BOM lines whose lcsc field differs from the supplier code", root="R3", p0=("P0-1",), level="B", control=_fjb_control)
def fjb(ctx: Ctx) -> Result:
    items, scope = fjb_items(_P(ctx))
    return _result(items, "lines where lcsc != code = 0", "compared as strings, empty == absent", _ev(ctx, "bom.json"), scope)


# ============================================================================= U5
def u5_items(P: PO.Project) -> tuple[list, int]:
    out, scope = [], 0
    for mp in P.order_manifests():
        for r in PO.read_json(mp).get("accepted_risks", []):
            scope += 1
            if not str(r.get("reason") or "").strip():
                out.append(f"{r.get('line')} ({r.get('basis')}): accepted with an empty reason")
    return out, scope


def _u5_control(ctx: Ctx) -> Ctx:
    c = ctx.writable_copy("U5-control")
    for mp in _P(c).order_manifests():
        d = json.loads(mp.read_text(encoding="utf-8"))
        for r in d.get("accepted_risks", []):
            if not str(r.get("reason") or "").strip():
                r["reason"] = "reviewed: the fab accepts this finding on this design"
        mp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    _assert_clean(c, u5, "U5")
    _selftest(c, u5, CAN.inject_u5, "U5-canary", lambda info, m: any(x.startswith(info["line"] + " ") for x in m))
    return c


@metric(id="U5", title="Accepted risks in the order manifest with an empty reason", root="R5", level="B", control=_u5_control)
def u5(ctx: Ctx) -> Result:
    P = _P(ctx)
    items, scope = u5_items(P)
    return _result(items, "accepted risks with an empty reason = 0", "reason compared after strip()",
                   [ctx.ev(p, "manifest") for p in P.order_manifests()], scope, empty_status="not_run")
