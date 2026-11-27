"""Behaviour metrics that need Altium to fail, stall or be blocked, or Altium's own files as the judge: library build (B1, P0-2, P0-4),
Altium modal dialogs (B1(b), P0-2), locked IntLib (B1(d)). Observations are cached per operation; every judge is separate from its
observation and has a synthetic control (live_altium/controls.py)."""
from __future__ import annotations

import hashlib
import json
import pathlib
import random
import re
import shutil
import time

import thresholds as TH
from lib import Result, metric
from live_altium import obs, env, altium_probe as ap, failview

CONTROLS: dict = {}


def _err(msg: str) -> Result:
    return Result("error", detail=msg)


# ------------------------------------------------------------------------------------------------ library build observation
_SKIP_TOP = {"FileHeader", "FileVersionInfo", "SectionKeys", "Library", "Storage", "Models"}


def stream_hashes(lib: pathlib.Path) -> dict[str, str]:
    """{component: sha256 of every stream under that component's storage} of a SchLib/PcbLib (oracle reads the OLE file itself)."""
    import olefile
    out: dict[str, str] = {}
    if not lib.is_file():
        return out
    o = olefile.OleFileIO(str(lib))
    try:
        by: dict[str, list] = {}
        for path in o.listdir(streams=True, storages=False):
            if len(path) > 1 and path[0] not in _SKIP_TOP:
                by.setdefault(path[0], []).append(path)
        for comp, paths in by.items():
            h = hashlib.sha256()
            for p in sorted(paths):
                h.update("/".join(p).encode())
                h.update(o.openstream(p).read())
            out[comp] = h.hexdigest()
    finally:
        o.close()
    return out


def line_status(bom: list[dict]) -> dict[str, str]:
    """{line key: JSON of what the student decided or Altium verified for it}: the pin decision, the verify state and acceptance."""
    out = {}
    for l in bom:
        e = l.get("library_entry") or {}
        pd = l.get("pin_decision") or e.get("pin_decision") or {}
        out[l["key"]] = json.dumps({"verify": e.get("verify"), "accepted": e.get("accepted"), "pins_accepted": e.get("pins_accepted"),
                                    "method": e.get("method"), "verified_at": e.get("verified_at"), "pin": pd.get("status"),
                                    "pin_id": pd.get("id"), "pins_status": l.get("pins_status")}, sort_keys=True)
    return out


def _read_state(pdir: pathlib.Path, adir: pathlib.Path) -> dict:
    bom = json.loads((pdir / "bom.json").read_text(encoding="utf-8"))
    try:
        man = json.loads((pdir / "library" / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        man = {}
    lib = adir / "Library"
    sch = next(iter(sorted(lib.glob("*.SchLib"))), None)
    pcb = next(iter(sorted(lib.glob("*.PcbLib"))), None)
    files = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for pat in ("*.SchLib", "*.PcbLib", "*.LibPkg", "*.IntLib") for f in sorted(lib.glob(pat))}
    return {"files": files, "status": line_status(bom), "lines": [l["key"] for l in bom],
            "no_entry": [l["key"] for l in bom if not l.get("library_entry")],
            "manifest": {k: {"symbol": v.get("symbol"), "footprint": v.get("footprint"), "built": v.get("built")} for k, v in man.items()},
            "sch": stream_hashes(sch) if sch else {}, "pcb": stream_hashes(pcb) if pcb else {}}


def _log_entries(pdir: pathlib.Path, since: float) -> list[dict]:
    out = []
    for f in ("altium-log.jsonl", "library-log.jsonl"):
        for r in env.jsonl(pdir / f):
            ts = str(r.get("ts", ""))
            try:
                t = time.mktime(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S"))
            except ValueError:
                continue
            if t >= since - 2:
                out.append({"file": f, **{k: (str(v)[:300] if not isinstance(v, (int, float, bool)) else v) for k, v in r.items()}})
    return out


def _build_done(pdir: pathlib.Path, since: float) -> bool:
    return any(r.get("file") == "altium-log.jsonl" and "build-library" in json.dumps(r) and "retry" not in r
               for r in _log_entries(pdir, since))


_RESTORE: list = []
_HELD: list = []


def add_one_line(pdir: pathlib.Path, rnd: random.Random) -> tuple[str, str, str]:
    """The oracle's own edit of the SCRATCH project's bom.json, as a student's 'add a part' does it: one new passive line, a copy of a random
    existing R/C line with the next free designator of its kind (no designator is hard-coded). Returns (new key, source key, original text)."""
    f = pdir / "bom.json"
    text = f.read_text(encoding="utf-8")
    bom = json.loads(text)
    passives = [l for l in bom if re.match(r"^[RC]\d+$", l["key"]) and l.get("mpn")]
    if not passives:
        raise obs.NotObservable("the scratch BOM has no passive line to copy")
    src = rnd.choice(sorted(passives, key=lambda l: l["key"]))
    pre = src["key"][0]
    n = max(int(l["key"][1:]) for l in bom if re.match(rf"^{pre}\d+$", l["key"])) + 1
    new = json.loads(json.dumps(src))
    new["key"], new["refs"] = f"{pre}{n}", [f"{pre}{n}"]
    new["library_entry"] = None
    new["on_sheet"], new["off_sheet"] = [], []
    bom.append(new)
    _RESTORE.append((f, text))
    f.write_text(json.dumps(bom, indent=2, ensure_ascii=False), encoding="utf-8")
    return new["key"], src["key"], text


def _observe_libbuild_inner(ctx, seed: int | None = None, lock: bool = False, hold_open_s: float = 150.0) -> dict:
    """Build library on the scratch project while a BOM line (the project's last line, which the E2E added and which has no library
    entry yet) is the only change. The page every 2 s, a reload at a random time (30-90 s) mid-build, and one more at the end; the
    oracle reads the library files and the BOM before and after (hashes per component, status per line) and the Altium dialogs."""
    srv = obs.server(ctx)
    pdir, adir = env.project_dir(srv, obs.proj(ctx)), env.altium_dir(srv)
    rnd = random.Random(seed if seed is not None else int(time.time()))
    obs.wait_owner_idle()
    if ap.x2_dialogs():
        raise obs.NotObservable("an Altium dialog is open (not mine): not touching it")
    before = _read_state(pdir, adir)
    bom_text, new_key, src_key = None, None, None
    if not lock:
        new_key, src_key, bom_text = add_one_line(pdir, rnd)
    out = {"before": before, "changed": [new_key] if new_key else [], "copied_from": src_key, "snaps": [], "reload_at": round(rnd.uniform(3, 9), 1), "dialogs": [], "lock": lock}
    held = None
    if lock:
        intlib = adir / "Library" / f"Project Outputs for {obs.proj(ctx)}-Lib" / f"{obs.proj(ctx)}-Lib.IntLib"
        if not intlib.is_file():
            raise obs.NotObservable(f"{intlib.name} does not exist yet: nothing to lock (run the unlocked build first)")
        out["intlib"] = intlib.name
        out["intlib_sha"] = hashlib.sha256(intlib.read_bytes()).hexdigest()
        libs = [adir / "Library" / f"{obs.proj(ctx)}-Lib.SchLib", adir / "Library" / f"{obs.proj(ctx)}-Lib.PcbLib"]
        out["reload_at"] = 10 ** 6
    seen = set(ap.dialog_keys(ap.x2_dialogs()))
    with obs.browser(ctx) as b:
        b.goto_tab("bom", 2.0)
        t0 = time.time()
        out["t_click"] = t0
        b.page.click('#view [data-act="libbuild"]')
        reloaded = False
        end_seen = None
        while time.time() - t0 < 1500:
            s = b.snap("build")
            s["btn"] = [x["text"] for x in s["buttons"] if x["act"] == "libbuild"]
            s["done_in_log"] = _build_done(pdir, t0)
            out["snaps"].append(s)
            new = [d for d in ap.x2_dialogs() if (d["cls"], d["title"], tuple(d["texts"])) not in seen]
            for d in new:
                seen.add((d["cls"], d["title"], tuple(d["texts"])))
                out["dialogs"].append({"t": time.time(), "cls": d["cls"], "title": d["title"], "texts": d["texts"], "hwnd": d["hwnd"]})
            if lock and held is None and all(f.is_file() and f.stat().st_mtime > t0 for f in libs):
                # the product's own up-front check ("is the file writable") is behind us and Altium has written the new libraries: the IntLib
                # is locked now, as an open or installed library is, and Altium meets the lock when it compiles
                try:
                    held = ap.Held(intlib).__enter__()
                    _HELD.append(held)
                    out["locked_after_s"] = round(time.time() - t0, 1)
                    out["lock_confirmed"] = held.confirmed()
                except OSError as e:
                    out["lock_error"] = str(e)
                    held = False
            if lock and new and "modal_t" not in out:
                out["modal_t"] = time.time()
            if lock and out.get("modal_t") and time.time() - out["modal_t"] > hold_open_s and "closed_by_oracle" not in out:
                for d in ap.x2_dialogs():
                    if (d["cls"], d["title"], tuple(d["texts"])) in seen and any(
                            x["texts"] == d["texts"] for x in out["dialogs"]):
                        out["closed_by_oracle"] = ap.close_dialog(d["hwnd"])        # only a box the injected lock provoked
            if not reloaded and time.time() - t0 >= out["reload_at"] and not s["done_in_log"]:
                took = b.reload()
                b.goto_tab("bom", 1.5)
                r = b.snap("after-reload-mid")
                r["btn"] = [x["text"] for x in r["buttons"] if x["act"] == "libbuild"]
                r["reload_took"] = took
                r["done_in_log"] = _build_done(pdir, t0)
                out["after_reload_mid"] = r
                out["snaps"].append(r)
                reloaded = True
                continue
            if s["done_in_log"]:
                end_seen = end_seen or time.time()
                if time.time() - end_seen > 25:
                    break
            time.sleep(1 if lock else 2)
        out["t_end"] = end_seen
        out["end"] = b.snap("end")
        out["end"]["btn"] = [x["text"] for x in out["end"]["buttons"] if x["act"] == "libbuild"]
        b.reload()
        b.goto_tab("bom", 1.5)
        out["after_reload_end"] = b.snap("reload-end")
        out["after_reload_end"]["btn"] = [x["text"] for x in out["after_reload_end"]["buttons"] if x["act"] == "libbuild"]
    while _HELD:
        _HELD.pop().__exit__(None, None, None)
    if lock:
        out["intlib_sha_after"] = hashlib.sha256(intlib.read_bytes()).hexdigest()
    out["after"] = _read_state(pdir, adir)
    if bom_text is not None:
        (pdir / "bom.json").write_text(bom_text, encoding="utf-8")      # the scratch BOM as the student had it
    out["log"] = _log_entries(pdir, t0)
    for d in ap.x2_dialogs():            # a box the build left open is the product's to close; the oracle only reports it
        if (d["cls"], d["title"], tuple(d["texts"])) not in seen:
            out["left_open"] = d["texts"]
    return out


def _observe_libbuild(ctx, seed: int | None = None, lock: bool = False, hold_open_s: float = 150.0) -> dict:
    try:
        return _observe_libbuild_inner(ctx, seed, lock, hold_open_s)
    finally:
        while _HELD:
            _HELD.pop().__exit__(None, None, None)
        while _RESTORE:
            f, text = _RESTORE.pop()
            f.write_text(text, encoding="utf-8")        # the scratch BOM as the student had it, whatever happened


def libbuild_obs(ctx) -> dict:
    return obs.cached("libbuild", lambda: _observe_libbuild(ctx))


# ------------------------------------------------------------------------------------------------ B1(c): a build touches only what changed
def judge_b1c(o: dict) -> Result:
    """Lines other than the changed ones whose pin / verify state changed, and library components other than the changed lines'
    whose streams changed (a pass state exists: a build that leaves them as they are)."""
    changed = set(o["changed"])
    others = [k for k in o["before"]["status"] if k not in changed]
    reset = [k for k in others if o["after"]["status"].get(k) != o["before"]["status"][k]]
    names = set()
    for k in changed:
        m = o["after"]["manifest"].get(k) or {}
        names |= {str(m.get("symbol") or "").lower(), str(m.get("footprint") or "").lower()}
    stream_hits = []
    for kind in ("sch", "pcb"):
        b, a = o["before"][kind], o["after"][kind]
        for comp in sorted(set(b) | set(a)):
            if comp.lower() in names:
                continue
            if b.get(comp) != a.get(comp):
                stream_hits.append(f"{kind}:{comp}")
    n = len(reset) + len(stream_hits)
    detail = (f"changed lines {sorted(changed)}; other lines whose pin/verify state changed: {len(reset)} of {len(others)}"
              f"{' (' + ', '.join(reset[:6]) + ('...' if len(reset) > 6 else '') + ')' if reset else ''}; "
              f"library components of other lines whose streams changed: {len(stream_hits)} "
              f"of {len(o['before']['sch']) + len(o['before']['pcb'])}")
    return Result("pass" if n == 0 else "fail", measured={"lines_reset": len(reset), "of_lines": len(others), "streams_changed": len(stream_hits)},
                  expected="lines other than the changed ones, reset or rewritten by the build = 0", detail=detail)


@metric(id="B1(c)", title="A library build after one added line leaves every other line's pins/verify state and library streams alone",
        root="R1", level="L", kind="behaviour", p0=("P0-1",))
def b1c(ctx) -> Result:
    try:
        return judge_b1c(libbuild_obs(ctx))
    except obs.NotObservable as e:
        return _err(str(e))


def _synth_b1c(reset: int) -> dict:
    keys = [f"L{i}" for i in range(31)]
    st = {k: json.dumps({"verify": "ok", "pin": "accepted"}) for k in keys}
    after = dict(st)
    for k in keys[:reset]:
        after[k] = json.dumps({"verify": "unchecked", "pin": None})
    man = {k: {"symbol": f"S{k}", "footprint": f"F{k}"} for k in keys}
    return {"changed": ["L30"], "before": {"status": st, "sch": {f"S{k}": "h" for k in keys}, "pcb": {f"F{k}": "h" for k in keys}},
            "after": {"status": after, "manifest": man, "sch": {f"S{k}": "h" for k in keys}, "pcb": {f"F{k}": "h" for k in keys}}}


CONTROLS["B1(c)"] = (judge_b1c, _synth_b1c(0), _synth_b1c(30))


# ------------------------------------------------------------------------------------------------ P0-2 on a long operation (B1(a), P0-2(altium))
PHASE_RX = re.compile(r"\b(prepar\w+|convert\w+|download\w+|symbols?|footprints?|3d|compil\w+|install\w+|writ(?:e|ing)\w*|read(?:ing)?|check\w*|"
                      r"verif\w+|draw\w*|plac\w+|rout\w+|net \S+|pad \S+)\b", re.I)
PROGRESS_RX = re.compile(r"\b\d+\s*(?:s|sec|secs|seconds?|min|mins|minutes?)\b|\b\d+\s*(?:/|of)\s*\d+\b|\b\d+\s*-\s*\d+\s*min", re.I)
END_RX = re.compile(r"\b(built|done|finished|failed|could not|couldn.t|cancelled|stopped|error)\b", re.I)
GAP_MAX_S, FIRST_MAX_S, STALL_S = (TH.P02_UPDATE_GAP_S["value"], TH.P02_FIRST_STATE_S["value"], TH.P02_NO_PROGRESS_S["value"])   # cited in thresholds.py


def _run_text(s: dict, rx_note: str) -> str:
    """The text of the page that belongs to the running operation: its notes and the label of its button."""
    parts = [n["text"] for n in s.get("notes", []) if re.search(rx_note, n["text"], re.I)]
    parts += [t for t in s.get("btn", []) if re.search(rx_note, t, re.I)]
    return " | ".join(parts)


def judge_p02(o: dict, what: str, rx_note: str = r"build|librar|altium") -> Result:
    """o: {t_click, t_end, snaps[{t, notes, btn}], after_reload_mid, after_reload_end}. Pass = visible running state with a phase name within 2 s,
    no gap over 10 s between changes of the running text, an elapsed time or step count on the page, the running state still on the page after a
    reload mid-operation, and an end message on the page after a reload at the end."""
    t0, t1 = o["t_click"], o.get("t_end") or o["snaps"][-1]["t"]
    run = [s for s in o["snaps"] if t0 <= s["t"] <= t1 and s.get("label") != "after-reload-mid"]
    probs, m = [], {}
    first = next((s for s in run if _run_text(s, rx_note) and PHASE_RX.search(_run_text(s, rx_note))), None)
    m["first_phase_s"] = round(first["t"] - t0, 1) if first else None
    if not first:
        probs.append("no phase name on the page during the run")
    elif first["t"] - t0 > FIRST_MAX_S + 3:     # 3 s: the oracle's own polling and page paint
        probs.append(f"the first phase name appeared after {first['t'] - t0:.0f} s (limit {FIRST_MAX_S:.0f})")
    last_change, last_text, gap = t0, None, 0.0
    for s in run:
        tx = _run_text(s, rx_note)
        if tx != last_text:
            gap = max(gap, s["t"] - last_change)
            last_change, last_text = s["t"], tx
    gap = max(gap, t1 - last_change)
    m["max_gap_s"] = round(gap, 1)
    if gap > GAP_MAX_S:
        probs.append(f"the page text did not change for {gap:.0f} s (limit {GAP_MAX_S:.0f})")
    prog = any(PROGRESS_RX.search(_run_text(s, rx_note)) for s in run)
    m["elapsed_or_steps_on_page"] = prog
    if not prog:
        probs.append("no elapsed time, step count or expected time on the page")
    mid = o.get("after_reload_mid")
    if mid is not None:
        txt = _run_text(mid, rx_note)
        still = bool(re.search(r"building|running|working|in progress|\.\.\.|…", txt, re.I)) and not mid.get("done_in_log")
        m["running_after_reload"] = still
        if not still:
            probs.append("after a reload during the run the page does not show that the operation is still running")
    end = o.get("after_reload_end")
    if end is not None:
        has_end = any(END_RX.search(n["text"]) and re.search(rx_note, n["text"], re.I) for n in end.get("notes", []))
        m["end_message_after_reload"] = has_end
        if not has_end:
            probs.append("no end message on the page after a reload at the end")
    return Result("pass" if not probs else "fail", measured=m, expected=f"{what}: phase within 2 s, no gap over 10 s, elapsed/steps, running and end state survive a reload",
                  detail="; ".join(probs) or "all of it shown")


def _synth_run(good: bool) -> dict:
    t0 = 1000.0
    snaps = []
    for i in range(0, 60, 2):
        t = t0 + i
        txt = (f"Building the library: converting symbols ({i // 10 + 1}/6), {i} s so far, about 5 min in all" if good
               else "Building in Altium. It can take a few minutes and Altium may flash while it works.")
        snaps.append({"t": t + 0.5, "notes": [{"cls": "banner info", "text": txt}], "btn": ["Building…"], "label": "build"})
    mid = {"t": t0 + 30, "notes": [{"cls": "banner info", "text": snaps[15]["notes"][0]["text"]}] if good else [], "btn": ["Building…"] if good else ["Build library"],
           "label": "after-reload-mid"}
    end = {"t": t0 + 70, "notes": [{"cls": "banner ok", "text": "Library built: 31 of 31 lines"}] if good else [], "btn": ["Build library"]}
    return {"t_click": t0, "t_end": t0 + 60, "snaps": snaps + [mid], "after_reload_mid": mid, "after_reload_end": end}


@metric(id="B1(a)", title="Library build shows a running state with its phase, an update at least every 10 s, and its end after a reload",
        root="R1", level="B", kind="behaviour", p0=("P0-2",))
def b1a(ctx) -> Result:
    try:
        return judge_p02(libbuild_obs(ctx), "library build")
    except obs.NotObservable as e:
        return _err(str(e))


CONTROLS["B1(a)"] = (lambda o: judge_p02(o, "library build"), _synth_run(True), _synth_run(False))


# ------------------------------------------------------------------------------------------------ locked IntLib: modal, failed restore, failure view
def locked_obs(ctx) -> dict:
    return obs.cached("libbuild-locked", lambda: _observe_libbuild(ctx, lock=True))


MODAL_WORDS = re.compile(r"error box|message box|dialog|pop-?up|window|Altium (?:is )?(?:showing|waiting|asks|stopped|shows)|needs you|click OK|"
                         r"could not create|integrated library|blocked", re.I)
STALL_WORDS = re.compile(r"no progress|not responding|has not (?:answered|responded|moved)|stalled|waiting for Altium|nothing (?:has )?changed|"
                         r"no sign of|still waiting|has stopped", re.I)
MODAL_MAX_S = TH.B1B_MODAL_IN_DOM_S["value"]      # cited in thresholds.py


def _tokens(texts: list[str]) -> set[str]:
    return {w.lower() for t in texts for w in re.findall(r"[A-Za-z]{5,}", t)}


def _note_texts(snap: dict) -> str:
    return " ".join(n["text"] for n in snap.get("notes", []))


def modal_latency(o: dict) -> list[dict]:
    """For every modal the oracle saw: the seconds from its appearance (the oracle polls every ~2 s) to the first page snapshot that
    carries it in words (a note with words about a box / dialog / the dialog's own words), or None."""
    out = []
    for d in o["dialogs"]:
        own = _tokens(d["texts"])
        t_in = None
        for s in o["snaps"]:
            if s["t"] < d["t"] - 3:
                continue
            txt = _note_texts(s)
            if MODAL_WORDS.search(txt) or len(own & _tokens([txt])) >= 2:
                t_in = s["t"] - d["t"]
                break
        out.append({"texts": d["texts"], "seen_in_dom_after_s": None if t_in is None else round(max(t_in, 0), 1)})
    return out


def judge_b1b(o: dict) -> Result:
    lat = modal_latency(o)
    if not lat:
        raise obs.NotObservable("the locked IntLib raised no Altium modal: the injected condition did not happen")
    bad = [x for x in lat if x["seen_in_dom_after_s"] is None or x["seen_in_dom_after_s"] > MODAL_MAX_S + 3]
    return Result("pass" if not bad else "fail", measured={"undetected_modals": len(bad), "of": len(lat), "latency_s": [x["seen_in_dom_after_s"] for x in lat]},
                  expected=f"Altium modals not in the DOM in words within {MODAL_MAX_S:.0f} s = 0",
                  detail="; ".join(f"modal {x['texts']!r}: " + ("never in the page" if x["seen_in_dom_after_s"] is None else f"in the page after {x['seen_in_dom_after_s']} s")
                                   for x in lat))


@metric(id="B1(b)", title="Every Altium modal raised during a library build is in the page in words within 15 s",
        root="R1", level="B", kind="behaviour", p0=("P0-2",))
def b1b(ctx) -> Result:
    try:
        return judge_b1b(locked_obs(ctx))
    except obs.NotObservable as e:
        return _err(str(e))


def _synth_locked(good: bool) -> dict:
    t0 = 1000.0
    d = {"t": t0 + 40, "cls": "#32770", "title": "X2", "texts": ["Could not create integrated library Acc-A-Lib.IntLib"]}
    snaps = []
    for i in range(0, 200, 2):
        t = t0 + i
        if good and t >= d["t"] + 6:
            txt = "Altium is showing an error box: could not create the integrated library. No progress for %d s." % max(i - 40, 0)
        else:
            txt = "Building in Altium. It can take a few minutes."
        snaps.append({"t": t, "notes": [{"cls": "banner info", "text": txt}], "btn": ["Building…"]})
    return {"dialogs": [d], "snaps": snaps, "t_click": t0, "modal_t": d["t"]}


CONTROLS["B1(b)"] = (judge_b1b, _synth_locked(True), _synth_locked(False))


def judge_p02_modal(o: dict) -> Result:
    """P0-2 with Altium blocked by a box: the box in words within 15 s (as B1(b)) and, as the backend makes no progress, the page says that in
    words by 60 s after the box (a timer that keeps ticking does not count: the words must say nothing is moving)."""
    r = judge_b1b(o)
    t_m = o["modal_t"]
    stalled_at = None
    for s in o["snaps"]:
        if s["t"] >= t_m and re.search(r"building|running|working|\.\.\.|…", " ".join(s.get("btn", [])), re.I) and STALL_WORDS.search(_note_texts(s)):
            stalled_at = s["t"] - t_m
            break
    probs = [] if r.status == "pass" else [r.detail]
    ok_stall = stalled_at is not None and stalled_at <= STALL_S + 5
    if not ok_stall:
        probs.append("no 'no progress' statement in words within 60 s of the box" if stalled_at is None else f"the no-progress statement came after {stalled_at:.0f} s")
    m = dict(r.measured)
    m["no_progress_said_after_s"] = None if stalled_at is None else round(stalled_at, 1)
    return Result("pass" if not probs else "fail", measured=m, expected="modal in words within 15 s and a 'no progress' statement within 60 s",
                  detail="; ".join(probs) or "both said")


@metric(id="P0-2(altium)", title="Altium blocked by a modal: the page says so within 15 s and says nothing moves within 60 s",
        root="R1", level="B", kind="behaviour", p0=("P0-2",))
def p02_altium(ctx) -> Result:
    try:
        return judge_p02_modal(locked_obs(ctx))
    except obs.NotObservable as e:
        return _err(str(e))


CONTROLS["P0-2(altium)"] = (judge_p02_modal, _synth_locked(True), _synth_locked(False))


# ---- B1(d)
RESTORE_WORDS = re.compile(r"put back|restor\w+|earlier library|previous library|rolled back|old library", re.I)


def judge_b1d(o: dict) -> Result:
    """A failed restore (the locked IntLib could not be put back) produces a message in the page that names the file and says what happened,
    and an entry in the project log that names it too. The restore failure is confirmed by the oracle: the Library files after the run differ
    from before it (the earlier library was not fully put back) or the log says so."""
    name = o["intlib"]
    lf_b, lf_a = o["before"].get("files", {}), o["after"].get("files", {})
    incomplete = [f for f in lf_b if lf_b[f] != lf_a.get(f)]
    log_txt = json.dumps(o.get("log", []), ensure_ascii=False)
    log_restore = [r for r in o.get("log", []) if RESTORE_WORDS.search(json.dumps(r, ensure_ascii=False)) and name.lower() in json.dumps(r).lower()]
    if not incomplete and not re.search(r"could not be put back|NOT installed", log_txt):
        raise obs.NotObservable("the restore did not fail after the failed build (the Library files are as before): nothing to report")
    pages = [o.get("end"), o.get("after_reload_end")] + [s for s in o["snaps"][-8:]]
    dom = [n["text"] for s in pages if s for n in s.get("notes", []) if RESTORE_WORDS.search(n["text"]) or "could not" in n["text"].lower()]
    blob = " ".join(dom).lower()
    named = [f for f in incomplete if f.lower() in blob]
    missing = [f for f in incomplete if f.lower() not in blob]
    m = {"files_not_restored": incomplete, "named_in_page": named, "dom_message": bool(dom), "log_entry_names_the_file": bool(log_restore)}
    probs = []
    if not dom:
        probs.append("nothing in the page says the earlier library could not be put back")
    elif missing:
        probs.append("the page message does not name " + ", ".join(missing) + " (still the half-built file, not put back)")
    if not log_restore:
        probs.append(f"no log entry about the restore that names {name}")
    return Result("pass" if not probs else "fail", measured=m, expected="failed restore: a page message naming the file + a log entry naming it",
                  detail="; ".join(probs) or "both present")


@metric(id="B1(d)", title="A failed restore of the library files is said on the page, naming the file, and logged",
        root="R1", level="B", kind="behaviour", p0=("P0-1",))
def b1d(ctx) -> Result:
    try:
        return judge_b1d(locked_obs(ctx))
    except obs.NotObservable as e:
        return _err(str(e))


def _synth_restore(good: bool) -> dict:
    n = {"cls": "banner bad", "text": ("Library build failed. Acc-A-Lib.IntLib is locked by Altium; the earlier library could not be put back: Acc-A-Lib.SchLib and Acc-A-Lib.PcbLib are still the new half-built files." if good else "The earlier library could not be put back ([WinError 32]). Acc-A-Lib.IntLib is locked")}
    return {"intlib": "Acc-A-Lib.IntLib", "before": {"files": {"Acc-A-Lib.SchLib": "1", "Acc-A-Lib.PcbLib": "2"}},
            "after": {"files": {"Acc-A-Lib.SchLib": "9", "Acc-A-Lib.PcbLib": "9"}},
            "log": [{"restored": "The earlier library could not be put back: Acc-A-Lib.IntLib"}] if good else [{"error": "x"}],
            "end": {"notes": [n]}, "after_reload_end": {"notes": []}, "snaps": []}


CONTROLS["B1(d)"] = (judge_b1d, _synth_restore(True), _synth_restore(False))


# ------------------------------------------------------------------------------------------------ P0-4: readable failures
def failure_note(snap: dict, rx: str) -> dict | None:
    """The failure message among a snapshot's notes: a note in the bad tone (or with failure words) that is about `rx`."""
    notes = [n for n in snap.get("notes", []) if n.get("text") and re.search(rx, n["text"], re.I)
             and (obs.tone(n["cls"]) == "bad" or re.search(r"\b(failed|could not|couldn.t|no tracks|error)\b", n["text"], re.I))]
    return notes[-1] if notes else None


def judge_p04(o: dict) -> Result:
    """o: {path name: (note or None, object token groups)}. Every failure path must pass the collapsed-view judge (live_altium/failview.py)."""
    bad, per = [], {}
    for name, (note, groups) in o.items():
        ok, why = failview.judge(note, groups)
        per[name] = "ok" if ok else why
        if not ok:
            bad.append(f"{name}: " + "; ".join(why[:4]))
    return Result("pass" if not bad else "fail", measured={k: (v if v == "ok" else len(v)) for k, v in per.items()},
                  expected="every failure view: bold title <= 70 chars naming the action and object, <= 3 lines, Details collapsed, no paths / error classes / raw Altium text / float noise",
                  detail=" || ".join(bad) or "all readable")


@metric(id="P0-4(altium)", title="Failures from Altium (route that cannot be drawn, locked library) are readable at a glance",
        root="R1", level="B", kind="behaviour", p0=("P0-4",))
def p04_altium(ctx) -> Result:
    from metrics import altium_ops as ops
    try:
        wd = ops.width_obs(ctx)
        lk = locked_obs(ctx)
    except (obs.NotObservable, FileNotFoundError, ValueError, OSError) as e:
        return _err(str(e))
    route_note = failure_note(wd["end"], r"rout|track")
    lib_note = failure_note(lk["end"], r"librar|build|altium")
    return judge_p04({"route cannot be drawn": (route_note, [["rout"], [wd["net"]]]),
                      "library build with a locked IntLib": (lib_note, [["librar"]])})


def _synth_fail(good: bool) -> dict:
    n_good = {"cls": "note bad", "text": "Route failed on +3V3\nNo track fits at 0.4 mm next to U1.\nDetails", "bold": ["Route failed on +3V3"],
              "details": [{"open": False, "summary": "Details"}]}
    n_bad = {"cls": "note bad", "text": "no tracks drawn: could not route U1-9 (net SDIO_D1): width 0.399999 mm C:\\x\\y.py OSError", "bold": [], "details": []}
    n = n_good if good else n_bad
    return {"route cannot be drawn": (dict(n), [["rout"], ["+3V3"]]),
            "library build with a locked IntLib": (dict(n, text=n["text"].replace("Route failed on +3V3", "Library build failed").replace("route", "library"),
                                                        bold=["Library build failed"] if good else []), [["librar"]])}


CONTROLS["P0-4(altium)"] = (judge_p04, _synth_fail(True), _synth_fail(False))
