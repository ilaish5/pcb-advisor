"""Stream A: the stage model. One server-derived stages[] that every dot, Next button and gate reads, instead of each view guessing from
the data it happens to hold. Registered with ext.MODEL (model keys: rev, stages, stage_sheets, board_check).

    stages: [{id, state, severity, reason, open, gate: {blocked, why, page, gaps?}, next: {label, act}, primary}]
      state     not_started | in_progress | issues | clean | blocked
      severity  "" | "warn" | "bad": the dot's colour when the state is not clean (clean is green, blocked is red, not_started is neutral)
      open      the number the dot's hint shows (what is left to do), 0 when none
      primary   true for the first stage that is not clean: where the work goes on
    rev: a digest of name / size / mtime of the files the stages are made from. Stat only: it is computed on every poll.

Nothing here is a new fact: each rule reads a number the model already holds (or the board log, or the gate store.manufacturing_warning).
"""
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ext  # noqa: E402
import store  # noqa: E402

ORDER = ("idea", "bom", "sch", "pcb", "rules", "outputs", "checks")
LABELS = {"idea": "Idea", "bom": "BOM", "sch": "Schematic", "pcb": "Layout", "rules": "Rules", "outputs": "Outputs", "checks": "DFM"}
STATES = ("not_started", "in_progress", "issues", "clean", "blocked")


def _plural(n, one, many=None):
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _stage(sid, state, reason="", severity="", open_=0, gate=None, next_=None):
    return {"id": sid, "state": state, "severity": severity, "reason": reason, "open": int(open_ or 0),
            "gate": gate or {"blocked": False, "why": "", "page": ""}, "next": next_ or {"label": "", "act": ""}, "primary": False}


def _go(sid, label=None):
    return {"label": label or LABELS[sid], "act": "go:" + sid}


# ---------------------------------------------------------------- the rules, one per stage

def idea_stage(model):
    idea = model.get("idea") or {}
    if idea.get("confirmed"):
        return _stage("idea", "clean", "Confirmed", next_=_go("bom", "Next: BOM"))
    draft = (model.get("idea_draft") or {}).get("active")
    has = bool(draft or idea.get("items") or idea.get("goal") or idea.get("description") or idea.get("requirements"))
    return _stage("idea", "in_progress" if has else "not_started", "Not confirmed yet", next_={"label": "Confirm the idea", "act": "go:idea"})


def bom_stage(model):
    """The BOM's counts, server side (what shell.js stageStatus('bom') used to count in the browser)."""
    total = out = wrong = review = unchecked = 0
    for l in model.get("bom") or []:
        if l.get("dnp") or l.get("nobuy"):
            continue
        total += 1
        supply = l.get("supply")
        if any(isinstance(v, dict) and v.get("code_mismatch") for v in (supply or {}).values()):
            wrong += 1
        elif supply is None:
            unchecked += 1
        elif not store.best_offer(l):
            out += 1
        elif l.get("library") in ("review", "missing"):
            review += 1
    if not total:
        return _stage("bom", "not_started", "No parts yet", next_=_go("idea"))
    parts = []
    if out:
        parts.append(f"{out} out of stock")
    if wrong:
        parts.append(f"{wrong} with the wrong LCSC code")
    if review:
        parts.append(f"{review} to review in the library")
    if unchecked:
        parts.append(f"{unchecked} not checked yet")
    nxt = _go("sch", "Next: Schematic")
    if out + wrong:
        return _stage("bom", "issues", ", ".join(parts), "bad", out + wrong, next_={"label": "Fix the BOM", "act": "go:bom"})
    if review + unchecked:
        return _stage("bom", "in_progress" if unchecked and not review else "issues", ", ".join(parts), "warn", review + unchecked, next_={"label": "Review the BOM", "act": "go:bom"})
    return _stage("bom", "clean", f"{_plural(total, 'part line')}, all in stock", next_=nxt)


def sheets_counts(model):
    """The one sheet count the Schematic dot, the Layout header and the Schematic header read: the plan's sheets, the sheets only
    Altium has (read from the linked project), and the total a person is told."""
    rows = model.get("sheets") or []
    plan = sum(1 for s in rows if not s.get("altium"))
    alt = sum(1 for s in rows if s.get("altium"))
    return {"plan": plan, "altium": alt, "total": plan or alt}


def sch_stage(project, model):
    counts = sheets_counts(model)
    if not counts["total"]:
        return _stage("sch", "not_started", "No schematic yet", next_=_go("bom"))
    gaps = store.pin_gaps(project)
    sg = model.get("sheet_gaps") or {}
    missing_parts = list(sg.get("parts") or [])
    n_open, n_unl = len(gaps["open"]), len(gaps["unlisted"])
    opened = n_open + n_unl + len(missing_parts)
    if opened:
        said = []
        if n_open:
            said.append(f"{_plural(n_open, 'open pin')}")
        if n_unl:
            said.append(f"{_plural(n_unl, 'pin')} missing from the netlist")
        if missing_parts:
            said.append(f"{_plural(len(missing_parts), 'part')} not in the BOM or not approved yet")
        return _stage("sch", "issues", ", ".join(said), "warn", opened, next_={"label": "Fix the schematic", "act": "go:sch"})
    drawn = bool(store.sheet_docs(project))
    if not drawn:
        return _stage("sch", "in_progress", f"{_plural(counts['total'], 'sheet')} planned, not drawn in Altium yet", next_={"label": "Draw in Altium", "act": "go:sch"})
    return _stage("sch", "clean", _plural(counts["total"], "sheet"), next_=_go("pcb", "Next: Layout"))


def board_check_of(lt):
    """The board_check the page shows from board_results.latest(): None when no check was ever recorded."""
    chk = (lt or {}).get("board_check")
    if not chk:
        return None
    d = chk.get("drc") or {}
    rules = {k: n for k, n in (d.get("rules") or {}).items() if n}
    return {"op": chk.get("op"), "ts": chk.get("ts"), "total": d.get("total"), "unrouted": d.get("unrouted") or 0, "clean": bool(d.get("clean")),
            "complete": d.get("complete", True), "stale": bool(chk.get("stale")), "rules": rules, "violations": len(d.get("violations") or [])}


def _drc_words(chk):
    names = [f"{store_short(k)} {n}" for k, n in list(chk["rules"].items())[:3]]
    return _plural(chk["total"], "violation") + (f" ({', '.join(names)})" if names else "")


def store_short(name):
    import re
    return re.split(r" \(|:", name, maxsplit=1)[0].replace(" Constraint", "").strip()


def pcb_stage(project, model, lt):
    ok_log = model.get("altium_ok") or {}
    place, route = lt.get("place"), lt.get("route")
    placed = bool((place and place.get("ok")) or (route and route.get("ok")) or ok_log.get("place-pcb") or ok_log.get("route-pcb"))
    routed = bool((route and route.get("ok")) or ok_log.get("route-pcb"))
    if routed and place and place.get("ok") and route and place.get("seq", -1) > route.get("seq", -1):
        routed = False         # placed again after the last route: the copper is gone
    if not placed:
        return _stage("pcb", "not_started", "Parts not placed yet", next_={"label": "Place parts", "act": "go:pcb"})
    chk = board_check_of(lt)
    if not routed:
        return _stage("pcb", "in_progress", "Placed, not routed yet", next_={"label": "Route the board", "act": "go:pcb"})
    open_nets = list(((route or {}).get("summary") or {}).get("open_nets") or []) if route and route.get("ok") else []
    if open_nets:
        return _stage("pcb", "issues", f"{_plural(len(open_nets), 'net')} left open: {', '.join(open_nets[:6])}", "bad", len(open_nets), next_={"label": "Finish the routing", "act": "go:pcb"})
    if not chk:
        return _stage("pcb", "in_progress", "Routed, board check not run", next_={"label": "Check the board", "act": "go:pcb"})
    if not chk["complete"]:
        return _stage("pcb", "in_progress", "The board check report was incomplete: run it again", "warn", 0, next_={"label": "Check the board", "act": "go:pcb"})
    if chk["total"]:
        extra = "; the board changed since" if chk["stale"] else ""
        return _stage("pcb", "issues", "Board check: " + _drc_words(chk) + extra, "bad", chk["total"], next_={"label": "Fix the board", "act": "go:pcb"})
    if chk["stale"]:
        return _stage("pcb", "issues", "The board changed since the last check: check it again", "warn", 1, next_={"label": "Check the board", "act": "go:pcb"})
    return _stage("pcb", "clean", "Board check clean", next_=_go("rules", "Next: Rules"))


# the rules diff reads the PcbDoc: kept until the PcbDoc or the rule files change
_RULES_MEMO = {}


def _stat(path):
    try:
        st = pathlib.Path(path).stat()
        return (st.st_size, st.st_mtime_ns)
    except OSError:
        return None


def _linked_pcb(project):
    try:
        import lineage
        return lineage.linked_pcb(project)
    except Exception:       # noqa: BLE001
        return None


def rules_result_key(d):
    """Python twin of rules.js rulesResult(): 'below' | 'missing' | 'extra' | 'match' | 'stricter' | 'tighter' | 'differs'."""
    verdict, st = d.get("verdict"), d.get("status") or d.get("Status")
    if verdict == "below_fab_min":
        return "below"
    if st == "missing_on_board":
        return "missing"
    if st == "extra_on_board":
        return "extra"
    if st == "match" or verdict == "same":
        return "match"
    if verdict == "safer":
        return "stricter"
    if verdict == "tighter_ok":
        return "tighter"
    return "differs"


def rules_state(project):
    """{"linked", "below", "differ", "missing_in_pcb": [names]} or None when it cannot be told (never a guess). Memoised on the stat
    of the PcbDoc and the rule files: a poll that finds none changed reads nothing."""
    pcb = _linked_pcb(project)
    if not pcb:
        return {"linked": False, "below": 0, "differ": 0, "missing_in_pcb": []}
    pdir = store.pdir(project)
    key = (str(pcb), _stat(pcb), _stat(pdir / "rules.json"), _stat(pdir / "rules-off.json"), _stat(pdir / "project.json"))
    hit = _RULES_MEMO.get(project)
    if hit and hit[0] == key:
        return hit[1]
    try:
        import project as project_mod
        import rules as rules_mod
        from altium import bridge, read_pcbdoc
        off = []
        try:
            val = json.loads((pdir / "rules-off.json").read_text(encoding="utf-8"))
            off = [n for n in val if isinstance(n, str)] if isinstance(val, list) else []
        except (OSError, ValueError):
            pass
        preset = rules_mod.get_jlc_preset(project_mod.board(project))
        doc = read_pcbdoc(pcb)
        diff = rules_mod.diff_rules(doc.get("rules", []), [r for r in preset.get("rules", []) if r.get("name") not in off], board_geom=doc)
        keys = [rules_result_key(d) for d in diff]
        res = {"linked": True, "below": keys.count("below"), "differ": sum(1 for k in keys if k in ("missing", "tighter", "differs")),
               "missing_in_pcb": list(bridge.rules_missing(project))}
    except Exception:       # noqa: BLE001 - the dot stays neutral
        res = None
    _RULES_MEMO[project] = (key, res)
    return res


def rules_stage(project):
    rs = rules_state(project)
    nxt = _go("outputs", "Next: Outputs")
    if rs is None:
        return _stage("rules", "not_started", "", next_={"label": "Rules", "act": "go:rules"})
    if not rs["linked"]:
        return _stage("rules", "not_started", "No board linked, so nothing to compare", next_={"label": "Rules", "act": "go:rules"})
    gone = len(rs["missing_in_pcb"])
    fix = {"label": "Apply the rules", "act": "go:rules"}
    if rs["below"]:
        return _stage("rules", "issues", _plural(rs["below"], "rule") + " below the JLC minimum" + (f", {gone} missing from the PcbDoc" if gone else ""), "bad", rs["below"] + gone, next_=fix)
    if gone or rs["differ"]:
        said = ([f"{_plural(gone, 'rule')} missing from the PcbDoc"] if gone else []) + ([f"{_plural(rs['differ'], 'rule')} differ from the preset"] if rs["differ"] else [])
        return _stage("rules", "issues", ", ".join(said), "warn", gone + rs["differ"], next_=fix)
    return _stage("rules", "clean", "The rule set matches the JLC preset", next_=nxt)


def outputs_stage(project, model):
    """Blocked exactly when store.manufacturing_warning says so: one gate for the button, the dot, the banner and the agent."""
    why = ""
    try:
        why = store.manufacturing_warning(project)
    except Exception:       # noqa: BLE001
        why = ""
    if why:
        gaps = store.pin_gaps(project)
        has_pins = bool(gaps["open"] or gaps["unlisted"])
        gate = {"blocked": True, "why": why, "page": "sch" if has_pins else "checks"}
        if has_pins:
            gate["gaps"] = gaps
            gate["nc_proposal"] = store.nc_proposal(project)
        return _stage("outputs", "blocked", why, "bad", len(gaps["open"]) + len(gaps["unlisted"]) or 1, gate=gate,
                      next_={"label": "Resolve the blocker", "act": "go:" + gate["page"]})
    ex = model.get("exports") or []
    if not ex:
        return _stage("outputs", "not_started", "Nothing generated yet", next_={"label": "Generate outputs", "act": "go:outputs"})
    old = [e for e in ex if (e.get("lineage") or {}).get("status") in ("stale", "edited")]
    if old:
        return _stage("outputs", "issues", f"{_plural(len(old), 'file')} out of date with the design: export again", "warn", len(old), next_={"label": "Export again", "act": "go:outputs"})
    return _stage("outputs", "clean", _plural(len(ex), "file"), next_=_go("checks", "Next: DFM"))


def checks_stage(model):
    cs = model.get("checks") or []
    if not cs:
        return _stage("checks", "not_started", "No reports yet", next_={"label": "Add a DFM report", "act": "go:checks"})
    real = sum(int(c.get("triage_real") or 0) for c in cs)
    open_ = sum(int(c.get("triage_open") or 0) for c in cs)
    empty = sum(1 for c in cs if not c.get("triage_count"))
    fix = {"label": "Review the DFM report", "act": "go:checks"}
    if real:
        return _stage("checks", "issues", _plural(real, "real issue") + (f", {open_} to review" if open_ else ""), "bad", real + open_, next_=fix)
    if open_:
        return _stage("checks", "issues", f"{open_} to review", "warn", open_, next_=fix)
    if empty:       # a report whose findings were never read in is not a clean report
        return _stage("checks", "in_progress", _plural(len(cs), "report") + ", none of it triaged yet", "", 0, next_=fix)
    return _stage("checks", "clean", "All reviewed")


# ---------------------------------------------------------------- the model

def derive(project, model):
    """The stages of the project from the model dict built so far (+ the board log and the gate)."""
    import board_results
    lt = board_results.latest(project)
    stages = [idea_stage(model), bom_stage(model), sch_stage(project, model), pcb_stage(project, model, lt), rules_stage(project),
              outputs_stage(project, model), checks_stage(model)]
    for s in stages:
        if s["state"] != "clean":
            s["primary"] = True
            break
    return stages, board_check_of(lt)


def rev(project):
    """A digest of what the stages are made from: name, size and mtime_ns of the logs, the idea files, the netlist, the library
    manifest, the rule files, the check reports and the linked PcbDoc. Stat only, never a read: this runs on every poll."""
    pdir = store.pdir(project)
    paths = []
    try:
        paths += [p for pat in ("*.jsonl", "idea*.json", "rules*.json", "project.json") for p in pdir.glob(pat)]
        paths += list((pdir / "netlist").glob("*")) + list((pdir / "checks").glob("*/*.json")) + list((pdir / "exports").glob("*"))
        paths.append(pdir / "library" / "manifest.json")
    except OSError:
        pass
    pcb = _linked_pcb(project)
    if pcb:
        paths.append(pcb)
    rows = []
    for p in paths:
        st = _stat(p)
        if st:
            rows.append((str(p.name), p.parent.name, st[0], st[1]))
    return hashlib.sha1(json.dumps(sorted(rows)).encode("utf-8")).hexdigest()[:16]


@ext.register("model")
def _model(project, model):
    stages, chk = derive(project, model)
    return {"rev": rev(project), "stages": stages, "stage_sheets": sheets_counts(model), "board_check": chk,
            "nc_proposal": store.nc_proposal(project)}


@ext.register("post")
def _post(handler, path, body):
    """POST /api/nc/mark {items?: [{sheet, ref, num}]}: mark the open and unlisted pins NC (all of them without items; the UI always
    sends the exact list it shows). POST /api/nc/approve {items?}: the student's one click on the agent's NC proposal (items = the
    ones left ticked; none = all). POST /api/nc/dismiss: drop the proposal."""
    if path not in ("/api/nc/mark", "/api/nc/approve", "/api/nc/dismiss"):
        return None
    project = handler.project()
    items = body.get("items") if isinstance(body, dict) else None
    if items is not None and not (isinstance(items, list) and all(isinstance(i, dict) for i in items)):
        raise ext.HTTPError(400, "\"items\" must be a list of {sheet, ref, num}")
    if path == "/api/nc/dismiss":
        store.clear_nc_proposal(project)
        return {"ok": True}
    try:
        res = store.approve_nc(project, items) if path == "/api/nc/approve" else store.mark_pins_nc(project, items)
    except ValueError as exc:
        raise ext.HTTPError(400, str(exc))
    return {"ok": True, **res}
