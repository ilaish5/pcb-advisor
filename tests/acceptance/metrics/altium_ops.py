"""Behaviour metrics that run an Altium operation (route, place, library build ...) on the scratch copy and judge the page and the
files with Altium's own reports. Observations are cached per operation. Ids: U4, F-A, U2, ... (see each metric)."""
from __future__ import annotations

import hashlib
import pathlib
import random
import re
import shutil
import time

from lib import Result, metric, not_run
from live_altium import obs, altium_probe as ap
from oracle.pcbdoc import PcbDoc
from metrics.altium_ui import oracle_pitch

CONTROLS: dict = {}


def _err(msg: str) -> Result:
    return Result("error", detail=msg)


def _sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _observe_route(ctx) -> dict:
    """One 'Route board' run on the scratch board: the page every 3 s (notes with their full text), the step-status the page reads,
    the file hash before and after, and Altium's own DRC report of the board as it is on disk afterwards."""
    pcb = obs.scratch_pcb(ctx)
    work = obs.scratch_altium(ctx) / "oracle"
    work.mkdir(exist_ok=True)
    before = _sha(pcb)
    shutil.copy2(pcb, work / "before-route.PcbDoc")
    obs.wait_owner_idle()
    out = {"sha_before": before, "snaps": [], "replace_clicked": False}
    t0 = time.time()
    with obs.browser(ctx) as b:
        b.goto_tab("pcb", 1.5)
        obs.click_step(b, "Route board")
        s1 = obs.watch(b, 120, every=2, label="route1")
        out["snaps"] += s1
        if obs.click_replace(b, "route"):
            out["replace_clicked"] = True
            out["snaps"] += obs.watch(b, 1200, every=3, label="route2", settle_s=30)
        out["end"] = b.snap("end")
        out["end_view"] = b.text("#view")
        out["buttons_end"] = out["end"]["buttons"]
        out["seconds"] = round(time.time() - t0)
        # the answer later: after a reload
        b.reload()
        b.goto_tab("pcb", 1.5)
        out["after_reload"] = b.snap("reload")
    out["sha_after"] = _sha(pcb)
    out["backup_dir"] = str(obs.scratch_altium(ctx) / ".advisor-backup")
    txt = ap.drc_report(pcb, work)
    out["report_total"] = ap.drc_total(txt)
    out["report_counts"] = ap.drc_counts(txt)
    out["report_text"] = txt
    return out


def route_obs(ctx) -> dict:
    return obs.cached("route", lambda: _observe_route(ctx))


# ------------------------------------------------------------------------------------------------ infeasible width (F-H b, F-A, P0-4)
MIN_WIDTH_MM = 0.4               # a PcbDoc width rule that asks for 0.4 mm on one net: a 0.3 mm wide pad at 0.5 mm pitch leaves 0.15 mm to its neighbour, below the 6 mil rule


def pin_rich_nets(pcb: pathlib.Path) -> list[tuple[str, str]]:
    """[(net, 'REF-pad')] of the signal nets that have a pad on the board's largest fine-pitch part (oracle reads the PcbDoc)."""
    with PcbDoc(pcb) as doc:
        by_ref: dict = {}
        for p in doc.pads():
            if p.ref and p.net:
                by_ref.setdefault(p.ref, []).append(p)
        best, n_best = None, 0
        for ref, pads in by_ref.items():
            pitches = oracle_pitch(pads) if len(pads) >= 16 else []
            if pitches and min(pitches) <= 0.65 and len(pads) > n_best:
                best, n_best = ref, len(pads)
        out = []
        for p in by_ref.get(best, []):
            if not re.match(r"^(GND|VSS|NC|\+?\d|V[A-Z]*\d*$)", p.net, re.I) and not p.net.startswith("Net") and len(p.net) <= 18:
                out.append((p.net, f"{best}-{p.name}"))
        return out


def set_width_rule(pcb: pathlib.Path, net: str, min_mm: float) -> dict:
    """The oracle's own edit of the SCRATCH board copy (never the owner's): the first Width rule whose scope is not 'All' gets the scope
    InNet('<net>') and a minimum width of min_mm, as bytes of the same length inside the Rules6 stream (the student's Rules page writes the
    same record). Read back through the oracle's reader before it is relied on."""
    import olefile
    o = olefile.OleFileIO(str(pcb), write_mode=True)
    try:
        d = o.openstream("Rules6/Data").read()
        for m in re.finditer(rb"\|RULEKIND=Width\|[^\x00]*?SCOPE1EXPRESSION=([^|]+)\|[^\x00]*?MINLIMIT=([0-9.]+mil)", d):
            scope = m.group(1)
            if scope.strip().lower() == b"all":
                continue
            new_scope = f"InNet('{net}')".encode("ascii").ljust(len(scope))
            mil = f"{min_mm / 0.0254:.3f}mil".encode("ascii")
            if len(new_scope) != len(scope) or len(mil) != len(m.group(2)):
                raise obs.NotObservable(f"the width rule record cannot take {net!r} / {mil!r} in place")
            nd = bytearray(d)
            nd[m.start(1):m.end(1)] = new_scope
            nd[m.start(2):m.end(2)] = mil
            o.write_stream("Rules6/Data", bytes(nd))
            return {"scope": new_scope.decode().strip(), "min_mil": mil.decode()}
        raise obs.NotObservable("the board has no net-scoped width rule to edit")
    finally:
        o.close()


def _observe_width(ctx, seed: int | None = None) -> dict:
    """A width rule (0.4 mm minimum) on one random signal net of the board's fine-pitch part, written into a copy of the board the student
    keeps (scratch), then Route: no copper can be drawn at that width at the pins of that part. The page every 2 s from the click to the
    end, a reload at a random time (30-90 s) mid-run and another one at the end. The board is put back afterwards."""
    pcb = obs.scratch_pcb(ctx)
    rnd = random.Random(seed if seed is not None else int(time.time()))
    cands = pin_rich_nets(pcb)
    if not cands:
        raise obs.NotObservable("no signal net with a pad on a fine-pitch part in the scratch board")
    net, _ = rnd.choice(sorted(set(cands)))
    pins_of_net = sorted({pn for n, pn in cands if n == net})
    obs.wait_owner_idle()
    keep = obs.scratch_altium(ctx) / "oracle" / "before-width.PcbDoc"
    keep.parent.mkdir(exist_ok=True)
    shutil.copy2(pcb, keep)
    out = {"net": net, "pins": pins_of_net, "min_mm": MIN_WIDTH_MM, "sha_before": _sha(pcb), "snaps": [], "reload_at": round(rnd.uniform(30, 90))}
    try:
        out["rule"] = set_width_rule(pcb, net, MIN_WIDTH_MM)
        with PcbDoc(pcb) as doc:
            ok = any(r.get("RULEKIND") == "Width" and f"InNet('{net}')" in r.get("SCOPE1EXPRESSION", "") and abs(
                float(re.sub(r"[a-z]", "", r.get("MINLIMIT", "0"))) * 0.0254 - MIN_WIDTH_MM) < 0.01 for r in doc.rules())
        if not ok:
            raise obs.NotObservable("the width rule written into the scratch board does not read back")
        out["sha_edited"] = _sha(pcb)
        with obs.browser(ctx) as b:
            b.goto_tab("pcb", 1.5)
            obs.click_step(b, "Route board")
            out["snaps"] += obs.watch(b, 20, every=1, label="ask", until_idle=False)
            if not obs.click_replace(b, "route"):
                out["no_replace_button"] = True
            out["t_click"] = time.time()
            first = obs.watch(b, out["reload_at"], every=2, label="run1", started_grace=3)
            out["snaps"] += first
            if first[-1]["running"]:
                reload_s = b.reload()
                b.goto_tab("pcb", 1.5)
                s = b.snap("after-reload-mid")
                s["status"] = obs.step_status(b)
                out["snaps"].append(s)
                out["mid_reload"] = {"running": bool(s["status"].get("running")), "notes": s["notes"], "t": s["t"], "reload_s": round(reload_s, 1)}
                out["snaps"] += obs.watch(b, 1500, every=3, label="run2", settle_s=30)
            end = b.snap("end")
            end["running"] = obs.step_running(b)
            out["end"] = end
            out["t_end"] = next((x["t"] for x in out["snaps"] if x.get("label", "").startswith("run") and not x.get("running")
                                 and not any("pv-run" in n["cls"] for n in x["notes"])), end["t"])
            b.reload()
            b.goto_tab("pcb", 1.5)
            out["after_reload"] = b.snap("reload-end")
        out["sha_after"] = _sha(pcb)
    finally:
        t0 = time.time()
        while time.time() - t0 < 1500:            # never put the board back while the product's step is still using it
            code, body = obs.api(ctx, "/api/altium/step-status")
            if not (code == 200 and isinstance(body, dict) and body.get("running")):
                break
            time.sleep(5)
        try:
            shutil.copy2(keep, pcb)
        except OSError:
            pass
    return out


def width_obs(ctx) -> dict:
    return obs.cached("width", lambda: _observe_width(ctx))


def end_note(snap: dict) -> dict | None:
    """The end message among the notes of a snapshot: the last visible note that is not the running state."""
    notes = [n for n in snap.get("notes", []) if n.get("text") and "pv-run" not in n["cls"] and "loading" not in n["cls"]]
    return notes[-1] if notes else None


def judge_width_early(o: dict) -> Result:
    """F-H(b): an infeasible width is reported before routing, naming the pin, within 10 s."""
    seconds = round(o["t_end"] - o["t_click"], 1)
    note = end_note(o["end"]) or {}
    text = note.get("full", "") or note.get("text", "")
    pins = [p for p in o["pins"] if re.search(r"(?<![\w])" + re.escape(p) + r"(?![\w])", text, re.I)]
    ok = seconds < 10 and bool(pins)
    return Result("pass" if ok else "fail", measured=f"{seconds} s to the message; pin named: {', '.join(pins) or 'none'}",
                  expected="< 10 s and the pin named (a pin of net " + o["net"] + ")",
                  detail=f"net {o['net']} given a {o['min_mm']} mm minimum width rule; message: {text[:160]!r}")


@metric(id="F-H(b)", title="an infeasible width is reported before routing, naming the pin, within 10 s", root="R4", level="L", kind="behaviour")
def fh_b(ctx):
    try:
        o = width_obs(ctx)
    except (obs.NotObservable, FileNotFoundError, ValueError, OSError) as e:
        return _err(str(e))
    r = judge_width_early(o)
    r.detail += "; ACCEPTANCE red on 27/11 = 1 late failure (about 5 min at U1-9)"
    if o["sha_edited"] != o["sha_after"]:
        r.detail += "; NOTE: the route DREW on the board (the width was not infeasible for the product)"
    return r


def _clock(text: str) -> int | None:
    m = re.search(r"\b(\d{1,2}):(\d\d)\b", text or "")
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


_ESTIMATE = re.compile(r"(?:\babout|\baround|\busually|\btypically|\btakes?|\bexpect\w*|~)\s*\d|\b\d+\s*(?:-|–|to)\s*\d+\s*(?:min|s\b|sec)|"
                       r"\ba (?:couple|few) of minutes|\b\d+\s*(?:min|minutes|seconds|sec)\b", re.I)


def estimate_texts(snaps: list[dict]) -> list[str]:
    """Texts of the running notes that state how long the step takes (clock readings like 6:03 are not an estimate)."""
    found = []
    for s in snaps:
        for n in s.get("notes", []):
            if "pv-run" in n["cls"] or "loading" in n["cls"]:
                t = re.sub(r"\b\d{1,2}:\d\d\b", "", n.get("full") or n["text"])
                m = _ESTIMATE.search(t)
                if m:
                    found.append(t.strip()[:200])
    return found


def judge_fa(rt: dict, wd: dict) -> Result:
    """F-A for the Altium steps: a stated estimate falls in the measured range; the running state and the end message survive a reload."""
    problems = []
    est = estimate_texts(rt["snaps"] + wd["snaps"])
    dur = rt["seconds"]
    if not est:
        problems.append(f"no expected duration on the page while Routing ran {dur} s")
    mid = wd.get("mid_reload")
    if not mid:
        problems.append("the infeasible-width run ended before the reload (no mid-run reload to judge)")
    else:
        run_note = next((n for n in mid["notes"] if "pv-run" in n["cls"]), None)
        if not mid["running"] or not run_note:
            problems.append("after a reload mid-run the page did not show that the step is still running")
        else:
            c = _clock(run_note["text"])
            since = mid["t"] - wd["t_click"]
            if c is None or c < since - 15:
                problems.append(f"after the reload the running note shows {c} s elapsed, the step had run {since:.0f} s")
    end0, end1 = end_note(wd["end"]), end_note(wd["after_reload"])
    if not end0:
        problems.append("the infeasible-width run left no end message")
    elif not end1 or end1["text"][:40] != end0["text"][:40]:
        problems.append("the end message is gone after a reload")
    return Result("fail" if problems else "pass",
                  measured=f"route {dur} s; estimate on page: {est[0] if est else 'none'}; reload mid-run kept 'running': "
                           f"{bool(mid and mid['running'])}; end message after reload: {bool(end1)}",
                  expected="a stated estimate inside the measured range; running state and end message survive a reload",
                  detail="; ".join(problems) or "all held")


@metric(id="F-A", title="long waits state an expected time and survive a reload", root="R1", level="B", kind="behaviour", p0=("P0-2",))
def f_a(ctx):
    try:
        wd = width_obs(ctx)
        rt = route_obs(ctx)
    except (obs.NotObservable, FileNotFoundError, ValueError, OSError) as e:
        return _err(str(e))
    r = judge_fa(rt, wd)
    r.detail += "; ACCEPTANCE red on 27/11 = route 'a couple of minutes' vs 5-7 min measured. Not measured here: reload after a SERVER restart (10 trials), the library build's client-only libBusy (see B1(a))."
    return r


# ----------------------------------------------------------------------------------------------------------------------- controls
def _note(cls, text, bold=()):
    return {"cls": cls, "text": text, "full": text, "bold": list(bold), "details": [], "rect": [0, 0, 600, 40]}


def _snap(t, notes, running=False, label="run1"):
    return {"t": t, "label": label, "notes": notes, "running": running}


def _width_control(good: bool) -> dict:
    run = lambda t, c: _snap(t, [_note("pv-note pv-run", f"Routing: pad U1-29 of SDIO_D1\n0:0{c}" if good else f"Altium is routing the board.\n0:0{c}")], True)
    est = "Routing usually takes 5 to 8 minutes. " if good else ""
    msg = ("Route stopped: SDIO_D1 cannot reach U1-29" if good else
           "no tracks drawn: could not route SDIO_D1 (pad U1-29 is too close to other copper for a 0.399999 mm track)")
    end = _snap(110 if not good else 14, [_note("note bad", msg)])
    o = {"net": "SDIO_D1", "pins": ["U1-29"], "min_mm": 0.4, "sha_edited": "a", "sha_after": "a", "t_click": 10, "t_end": 14 if good else 520,
         "snaps": [run(11, 1), run(12, 2)], "end": end, "after_reload": end if good else _snap(530, [_note("note bad", "Board DRC: 397 violations")]),
         "mid_reload": {"running": True, "t": 40, "reload_s": 1.0, "notes": [_note("pv-note pv-run", f"{est}Altium is routing the board.\n0:31")]}}
    if good:
        o["snaps"] = [_snap(11, [_note("pv-note pv-run", "Routing usually takes 5 to 8 minutes. Planning the route\n0:01")], True)]
    return o


def _route_control(good: bool) -> dict:
    txt = "Routing usually takes 5 to 8 minutes. Altium is routing the board.\n0:30" if good else "Altium is routing the board.\n0:30"
    return {"seconds": 383, "snaps": [_snap(1, [_note("pv-note pv-run", txt)], True)]}


def _fa_judge(pair):
    return judge_fa(pair[0], pair[1])


CONTROLS["F-H(b)"] = (judge_width_early, _width_control(True), _width_control(False))
CONTROLS["F-A"] = (_fa_judge, (_route_control(True), _width_control(True)), (_route_control(False), _width_control(False)))


# ------------------------------------------------------------------------------------------------ Place (U2) and Draw (W21)
def _observe_step(ctx, tab: str, label: str, step: str, keep: list[pathlib.Path], max_s: float = 1500) -> dict:
    """One Altium step of the page (Place parts / Draw in Altium) on the scratch copy: the page every 2 s from the click to the end, the
    files named in `keep` copied before and put back afterwards (the scratch copy stays as the student had it)."""
    adir = obs.scratch_altium(ctx)
    store = adir / "oracle" / f"before-{step}"
    store.mkdir(parents=True, exist_ok=True)
    for f in keep:
        shutil.copy2(f, store / f.name)
    obs.wait_owner_idle()
    out = {"step": step, "snaps": [], "sha_before": {f.name: _sha(f) for f in keep}}
    try:
        with obs.browser(ctx) as b:
            b.goto_tab(tab, 1.5)
            obs.click_step(b, label)
            out["snaps"] += obs.watch(b, 20, every=1, label="ask", until_idle=False)
            out["replace_clicked"] = obs.click_replace(b, step)
            out["t_click"] = time.time()
            out["snaps"] += obs.watch(b, max_s, every=3, label="run", settle_s=30)
            out["end"] = b.snap("end")
            out["t_end"] = out["snaps"][-1]["t"]
            out["view_text"] = b.text("#view")
        out["sha_after"] = {f.name: _sha(f) for f in keep}
    finally:
        pass
    return out


def _put_back_from(store: pathlib.Path, keep: list[pathlib.Path]) -> None:
    """The scratch files as the student had them (the copies made before the step), whatever happened in between."""
    for f in keep:
        if (store / f.name).is_file():
            try:
                shutil.copy2(store / f.name, f)
            except OSError:
                pass


def place_obs(ctx) -> dict:
    def run():
        pcb = obs.scratch_pcb(ctx)
        try:
            o = _observe_step(ctx, "pcb", "Place parts", "place", [pcb])
        finally:
            _put_back_from(obs.scratch_altium(ctx) / "oracle" / "before-place", [pcb])
        return o
    return obs.cached("place", run)


OPEN_RX = re.compile(r"(\d+)\s+(?:open\s+)?(?:warnings?|findings?|issues?|problems?|notes? to check)", re.I)


def judge_u2(o: dict) -> Result:
    """The placement banner's tone equals the worst open placement finding: green over open warnings = 0 (ACCEPTANCE U2)."""
    end = o["end"]
    banner = None
    for n in end.get("notes", []):
        if re.search(r"placed|placement|checked|netlist", n.get("text", ""), re.I) and obs.tone(n["cls"]) in ("ok", "warn", "bad"):
            banner = n
            break
    if banner is None:
        raise obs.NotObservable("no placement banner with a tone on the page after the step")
    texts = [n.get("full", "") or n.get("text", "") for n in end["notes"]] + [o.get("view_text", "")]
    opened = max([int(m.group(1)) for t in texts for m in OPEN_RX.finditer(t)] or [0])
    tone = obs.tone(banner["cls"])
    green = tone == "ok"
    return Result("fail" if (green and opened > 0) else "pass", measured=f"banner tone {tone!r} (class {banner['cls']!r}) with {opened} open warnings on the page",
                  expected="green banner with open placement warnings = 0",
                  detail=f"banner: {banner['text'][:160]!r}; only the tone clause is judged: the wording clause (scope next to the count) is not decided by the oracle, the banner still says 'checked against the netlist' over a separate 'Show n warnings' control")


@metric(id="U2", title="The placement banner is not green while placement warnings are open and states its scope", root="R2", level="B",
        kind="behaviour", p0=("P0-3",))
def u2(ctx):
    try:
        return judge_u2(place_obs(ctx))
    except (obs.NotObservable, FileNotFoundError, ValueError, OSError) as e:
        return _err(str(e))


def _u2_synth(green_over_open: bool) -> dict:
    tone = "note ok" if green_over_open else "note warn"
    return {"end": {"notes": [{"cls": tone, "text": "Placed 31 parts, checked against the netlist", "full": "Placed 31 parts, checked against the netlist"},
                              {"cls": "note", "text": "8 warnings", "full": "8 warnings"}]}, "view_text": ""}


CONTROLS["U2"] = (judge_u2, _u2_synth(False), _u2_synth(True))


# ---- W21: "pins x and y are one terminal" claims, judged by Altium's compile
JOIN_RX = re.compile(r"\b([A-Z]{1,3}\d+[A-Z]?)\s*:\s*pins\s+([\w, ]+?)\s+are one terminal", re.I)


def join_claims(text: str) -> set[tuple[str, tuple[str, ...]]]:
    out = set()
    for m in JOIN_RX.finditer(text):
        pins = tuple(p for p in re.split(r"\s*(?:,|and)\s*", m.group(2).strip()) if p)
        out.add((m.group(1), pins))
    return out


def draw_obs(ctx) -> dict:
    def run():
        adir = obs.scratch_altium(ctx)
        sheets = sorted(adir.glob("*.SchDoc"))
        try:
            o = _observe_step(ctx, "sch", "Draw in Altium", "draw", sheets, max_s=2400)
            tmp = adir / "oracle"
            try:
                o["compile"] = ap.compile_nets(obs.scratch_prj(ctx), tmp)
            except ap.ProbeError as e:
                raise obs.NotObservable(f"Altium's compile could not be run by the probe: {e}")
            ap.close_scratch(adir)                  # the documents the compile opened, without saving
        finally:
            _put_back_from(adir / "oracle" / "before-draw", sheets)
        return o
    return obs.cached("draw", run)


def judge_w21(o: dict) -> Result:
    """Every 'pins x and y are one terminal' claim the page makes is true in Altium's compile of the drawn sheets (the two pins are on one net
    there). False joins = 0. A pass state exists: a draw that says it only for a symbol whose drawing really joins the pins."""
    text = " ".join(n.get("full", "") or n.get("text", "") for s in o["snaps"][-6:] for n in s.get("notes", [])) + " " + o.get("view_text", "")
    if "NETS" not in o["compile"].get("sections", ["NETS"]):
        raise obs.NotObservable("Altium's compile was read without its net list (a guarded read failed, see the probe log): nothing to judge against")
    nets = o["compile"]["nets"]
    where: dict[str, str] = {}
    for net, pins in nets.items():
        for p in pins:
            where[p.upper()] = net
    claims = join_claims(text)
    if not claims and not o["compile"]["nets"]:
        raise obs.NotObservable("Altium's compile returned no nets for the drawn sheets")
    false, true = [], []
    for ref, pins in sorted(claims):
        n = {where.get(f"{ref}-{p}".upper()) for p in pins}
        (true if len(n) == 1 and None not in n else false).append(f"{ref} pins {' and '.join(pins)}")
    return Result("pass" if not false else "fail", measured={"false_joins": len(false), "claims": len(claims), "false": false, "true": true},
                  expected="'pins x and y are one terminal' claims that Altium's compile does not confirm = 0",
                  detail=f"{len(claims)} claim(s) on the page after the draw, {len(false)} not confirmed by the compile: {', '.join(false) or '-'}")


@metric(id="W21", title="A 'pins are one terminal' claim after a draw is confirmed by Altium's compile", root="R2", level="L", kind="behaviour", p0=("P0-3",))
def w21(ctx):
    try:
        return judge_w21(draw_obs(ctx))
    except obs.NotObservable as e:
        if str(e).startswith("Altium's compile could not be run by the probe"):
            # the oracle's compile read-out is not usable in this Altium (three attempts raised Altium's own error box, 27/11): the
            # draw was observed but nothing can be judged against Altium, so the metric says not_run with the reason, never a pass or fail
            return not_run(str(e) + " (W21 not judged; the probe's COMPILE read-out raised an Altium error box in three attempts)")
        return _err(str(e))
    except (FileNotFoundError, ValueError, OSError) as e:
        return _err(str(e))


def _w21_synth(false_join: bool) -> dict:
    t = "D1: pins 2 and 5 are one terminal in library symbol X (a line joins them) but the netlist puts them on different nets"
    nets = {"A": ["D1-2", "D1-5"]} if not false_join else {"A": ["D1-2"], "B": ["D1-5"]}
    return {"snaps": [{"notes": [{"cls": "note warn", "text": t, "full": t}]}], "view_text": "", "compile": {"nets": nets, "violations": []}}


CONTROLS["W21"] = (judge_w21, _w21_synth(False), _w21_synth(True))
