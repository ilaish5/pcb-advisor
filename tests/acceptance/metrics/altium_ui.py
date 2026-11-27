"""Behaviour metrics read from the rendered page of a live server, with Altium (or Altium's own files) as the judge.

Run: python -I tests/acceptance/run.py --live http://127.0.0.1:8941 --live-project Acc-A --only W15,U3,...
Each metric = observe (cached, one Altium operation per observation) + judge (pure function of the observation). The judges are
exercised on synthetic good/bad observations by live_altium/controls.py (a pass state that does not need the product).

Ids here: W15, U3, F-H(a), F-H(d), F-F, F-C(e), F-A(est).
"""
from __future__ import annotations

import hashlib
import pathlib
import re

from lib import Result, metric, not_run
from live_altium import obs, altium_probe as ap
from oracle import pcbdoc as opcb

DISPLAY_TOL_MM = 0.01          # display rounding of a pitch (ACCEPTANCE W15: +-0.01 mm)
CONTROLS: dict = {}            # id -> (judge, good observation, bad observation), used by live_altium/controls.py


def _err(msg: str) -> Result:
    return Result("error", detail=msg)


# =============================================================================== W15  footprint preview pitch
def oracle_pitch(pads) -> list[float]:
    """Centre spacings (mm) of the largest rows of equal, equally spaced pads (same shape and size, collinear on x or y). A row is a
    maximal run of equal consecutive gaps (within 0.005 mm). Returns the pitch of every largest row (ties give several)."""
    rows: list[tuple[int, float]] = []
    groups: dict = {}
    for p in pads:
        size = (p.shape, round(p.xs, 2), round(p.ys, 2))
        groups.setdefault(("x", size, round(p.y, 2)), []).append(p.x)
        groups.setdefault(("y", size, round(p.x, 2)), []).append(p.y)
    for pos in groups.values():
        pos = sorted(pos)
        if len(pos) < 2:
            continue
        gaps = [b - a for a, b in zip(pos, pos[1:])]
        i = 0
        while i < len(gaps):
            j = i
            while j + 1 < len(gaps) and abs(gaps[j + 1] - gaps[i]) <= 0.005:
                j += 1
            if gaps[i] > 0.05:
                rows.append((j - i + 2, round(sum(gaps[i:j + 1]) / (j - i + 1), 4)))
            i = j + 1
    if not rows:
        return []
    top = max(n for n, _ in rows)
    return sorted({pitch for n, pitch in rows if n == top})


def judge_w15(o: dict) -> Result:
    bad = []
    for r in o["rows"]:
        want = r["oracle"]
        if not want or r["shown"] is None:
            continue
        if not any(abs(r["shown"] - w) <= DISPLAY_TOL_MM for w in want):
            bad.append({"line": r["line"], "footprint": r["footprint"], "shown_mm": r["shown"], "oracle_mm": want})
    if not o["rows"]:
        return _err("no footprint line could be compared with the PcbLib")
    return Result("pass" if not bad else "fail", measured=bad,
                  expected=f"footprints whose displayed pitch differs from the PcbLib row pitch by more than {DISPLAY_TOL_MM} mm = 0",
                  detail=f"{len(o['rows'])} footprints compared, {o['unmatched']} lines had no footprint of that name in the PcbLib")


def _observe_w15(ctx) -> dict:
    code, st = obs.api(ctx, "/api/state")
    if code != 200:
        raise obs.NotObservable(f"/api/state answered {code}")
    lib = next(iter(sorted(obs.scratch_altium(ctx).glob("Library/*.PcbLib"))), None)
    if lib is None:
        raise obs.NotObservable("no PcbLib in the scratch Altium copy")
    fps = {f.name: f for f in opcb.read_pcblib(lib)}
    rows, unmatched = [], 0
    with obs.browser(ctx) as b:
        b.goto_tab("bom", 1.2)
        for entry in st.get("library", []):
            if not entry.get("footprint"):
                continue
            line = entry["line"]
            code, pv = obs.api(ctx, f"/api/library/preview?line={line}&kind=footprint")
            if code != 200 or not isinstance(pv, dict) or "pads" not in pv:
                continue
            fp = fps.get(pv.get("name"))
            if fp is None:
                unmatched += 1
                continue
            shown = None
            sel = f'[data-act="lib-preview"][data-line="{line}"][data-kind="footprint"]'
            if b.page.query_selector(sel):
                b.page.click(sel)
                b.page.wait_for_selector("dialog.mp-dlg[open]", timeout=8000)
                try:
                    b.page.wait_for_function("() => /pads span/.test((document.querySelector('dialog.mp-dlg')||{}).innerText||'')", timeout=8000)
                except Exception:
                    pass                                    # a caption that never appears is read as 'no pitch shown'
                cap = b.page.inner_text("dialog.mp-dlg")
                m = re.search(r"pitch\s+([0-9.]+)\s*mm", cap)
                shown = float(m.group(1)) if m else None
                b.page.keyboard.press("Escape")
                b.page.wait_for_timeout(250)
            rows.append({"line": line, "footprint": pv["name"], "shown": shown, "api": pv.get("pitch"),
                         "oracle": oracle_pitch(fp.pads), "n_pads": len(fp.pads)})
    return {"rows": rows, "unmatched": unmatched, "pcblib": str(lib)}


@metric(id="W15", title="the footprint preview's pad pitch equals the PcbLib row pitch", root="R4", level="B", kind="behaviour")
def w15(ctx):
    try:
        o = obs.cached("w15", lambda: _observe_w15(ctx))
    except (obs.NotObservable, FileNotFoundError, ValueError) as e:
        return _err(str(e))
    r = judge_w15(o)
    r.detail += "; ACCEPTANCE red on 27/11 = 2 (J1 0.65 vs 0.50, Y1 1.778 vs 1.76)"
    return r


class _P:                                   # a synthetic pad for the control
    def __init__(self, x, y, xs=0.3, ys=1.3, shape=2):
        self.x, self.y, self.xs, self.ys, self.shape = x, y, xs, ys, shape


def _syn_fp(pitch: float, n: int = 8):
    row = [_P(i * pitch, 2.0) for i in range(n)]
    tabs = [_P(-4.0, 0.0, 1.2, 1.8), _P(4.0, 0.0, 1.2, 1.8), _P(-3.2, 2.0, 0.6, 1.3), _P(n * pitch + 1.0, 2.0, 0.6, 1.3)]
    return row + tabs


def _w15_control():
    good = {"rows": [], "unmatched": 0}
    badr = {"rows": [], "unmatched": 0}
    for pitch in (0.4, 0.5, 0.65, 0.8, 1.27, 2.54):
        want = oracle_pitch(_syn_fp(pitch))
        good["rows"].append({"line": "L", "footprint": "x", "shown": want[0], "oracle": want})
        badr["rows"].append({"line": "L", "footprint": "x", "shown": want[0] + 0.15, "oracle": want})
    return good, badr


CONTROLS["W15"] = (judge_w15, *_w15_control())


# =============================================================================== Check board: U3, F-H(a), F-H(d)
def _observe_check_board(ctx) -> dict:
    """The page through one 'Check board' run on the scratch board, then Altium's own DRC report of the same file on disk."""
    pcb = obs.scratch_pcb(ctx)
    before = hashlib.sha256(pcb.read_bytes()).hexdigest()
    obs.wait_owner_idle()
    out = {"snaps": [], "tabs": {}}
    with obs.browser(ctx) as b:
        b.goto_tab("pcb", 1.5)
        obs.click_step(b, "Check board")
        out["snaps"] = obs.watch(b, 240, label="check")
        out["end"] = b.snap("end")
        out["end_view"] = b.text("#view")
        # does the page list the violations, and with what class?
        out["page_rows"] = b.page.evaluate("""() => [...document.querySelectorAll('#view li, #view tr, #view p, #view .drc-row, #view [class*=drc]')]
              .map(e => ({cls: String(e.className || ''), text: (e.innerText || '').trim().slice(0, 200)})).filter(r => /violat|clearance|sliver|annular|silk/i.test(r.text)).slice(0, 600)""")
        # a reload: what the page says about the same result later
        b.reload()
        b.goto_tab("pcb", 1.2)
        out["after_reload"] = b.snap("reload")
        b.goto_tab("rules", 1.2)
        out["rules_snap"] = b.snap("rules")
    sha = hashlib.sha256(pcb.read_bytes()).hexdigest()
    out["pcb_unchanged_by_check"] = (sha == before)
    txt = ap.drc_report(pcb, obs.scratch_altium(ctx) / "oracle")
    out["report_total"] = ap.drc_total(txt)
    out["report_counts"] = ap.drc_counts(txt)
    out["report_text"] = txt
    return out


def _check_board(ctx) -> dict:
    (obs.scratch_altium(ctx) / "oracle").mkdir(exist_ok=True)
    return obs.cached("check_board", lambda: _observe_check_board(ctx))


# -- U3: the tone of the result under which the violations are shown
def judge_u3(o: dict) -> Result:
    total = o["report_total"]
    shown = [s for s in o["snaps"][-4:] if obs.notes_with(s, r"\d+|violation|DRC")]
    notes = []
    for s in o["snaps"][-4:]:
        notes += obs.notes_with(s, r"DRC|violation|total \d+")
    green = [n for n in notes if obs.tone(n["cls"]) == "ok"]
    if total == 0:
        return _err("Altium's report has 0 violations: the red condition was not met on this board")
    if not notes:
        return _err("the page showed no result note after the run")
    n_green = total if green else 0
    return Result("pass" if n_green == 0 else "fail", measured=n_green,
                  expected="violations shown under a green tone = 0 (green only if JLC-reject = 0 and unclassified = 0)",
                  detail=f"Altium's DRC report holds {total} violations; the page's result note was tone "
                         f"{sorted({obs.tone(n['cls']) or 'neutral' for n in notes})}: {notes[-1]['text'][:120]!r}",
                  evidence=[])


@metric(id="U3", title="Check board never shows a green tone over Altium's violations", root="R2", level="B", kind="behaviour", p0=("P0-3",))
def u3(ctx):
    try:
        o = _check_board(ctx)
    except (obs.NotObservable, ap.ProbeError, OSError) as e:
        return _err(str(e))
    r = judge_u3(o)
    r.detail += "; ACCEPTANCE red on 27/11 = 421 under green"
    return r


def _snap(cls, text):
    return {"notes": [{"cls": cls, "text": text, "bold": [], "details": [], "rect": [0, 0, 1, 1]}]}


CONTROLS["U3"] = (judge_u3, {"report_total": 424, "snaps": [_snap("note bad", "Altium: DRC total 424")]},
                  {"report_total": 424, "snaps": [_snap("note ok", "Altium: DRC total 424")]})


# -- F-H(a): the DRC violations are classed JLC-reject / JLC-accept / cosmetic, and the class counts equal the oracle's classifier
# The oracle classifies each line of Altium's own report from the measured value Altium prints on that line, against the fab minima of
# shared/reference/jlc/pcb-capabilities.en.md (A7: cited, not tunable):
MIL = 0.0254
import thresholds as TH
FAB = {
    "mask_bridge_mm": TH.MASK_BRIDGE_MIN_MM["value"]["green"],    # the default mask colour; black/white need 0.13 (the board's colour is not on the page)
    "annular_mm": TH.ANNULAR_RING_MIN_MM["value"],
    "edge_mm": TH.EDGE_COPPER_MIN_MM["value"],
}
CLASSES = ("JLC-reject", "JLC-accept", "cosmetic")


def classify_violation(line: str) -> str | None:
    """Class of one violation line of Altium's text report (the part after `rule|||`), or None when the oracle cannot decide it."""
    if "Silk" in line.split("|||")[0]:
        return "cosmetic"                                  # "JLC does not check silkscreen" (pcb-capabilities, Silkscreen)
    val = re.search(r"\((?:([\d.]+)mil|Collision)\s*<", line)
    m_act = re.search(r"\[([\d.]+)mil\]\s*$", line.strip())
    mil = float(val.group(1)) if val and val.group(1) else (0.0 if val else (float(m_act.group(1)) if m_act else None))
    if mil is None:
        return None
    mm = mil * MIL
    head = line.split("|||")[0]
    if head.startswith("Minimum Solder Mask Sliver"):
        return "JLC-reject" if mm < FAB["mask_bridge_mm"] else "JLC-accept"
    if head.startswith("Minimum Annular Ring"):
        return "JLC-reject" if mm < FAB["annular_mm"] else "JLC-accept"
    if head.startswith("Board Clearance"):
        return "JLC-reject" if mm < FAB["edge_mm"] else "JLC-accept"
    return None


def oracle_classes(report_text: str) -> dict:
    counts = {c: 0 for c in CLASSES}
    undecided = 0
    for ln in report_text.splitlines():
        if "|||" not in ln:
            continue
        c = classify_violation(ln)
        if c is None:
            undecided += 1
        else:
            counts[c] += 1
    counts["undecided"] = undecided
    return counts


_CLS_RX = [re.compile(r"(\d+)\s*(?:violations?\s*)?(?:are\s*|:|\()?\s*(JLC[- ]reject|JLC[- ]accept|cosmetic)", re.I),
           re.compile(r"(JLC[- ]reject|JLC[- ]accept|cosmetic)\w*\s*[:(]?\s*(\d+)", re.I)]


def page_class_counts(text: str) -> dict:
    out: dict = {}
    for rx in _CLS_RX:
        for m in rx.finditer(text):
            a, b = m.groups()
            num, name = (a, b) if a.isdigit() else (b, a)
            key = {"jlc-reject": "JLC-reject", "jlc-accept": "JLC-accept", "cosmetic": "cosmetic"}[re.sub(r"[ ]", "-", name.lower())]
            out.setdefault(key, int(num))
    return out


def judge_fh_a(o: dict) -> Result:
    total = o["report_total"]
    want = oracle_classes(o["report_text"])
    if total == 0:
        return _err("Altium's report has 0 violations")
    if want["undecided"]:
        return _err(f"the oracle classifier cannot decide {want['undecided']} lines (extend FAB with a cited value)")
    text = " ".join([o["end_view"]] + [n["text"] for s in o["snaps"][-4:] for n in s["notes"]] + [n["text"] for n in o["after_reload"]["notes"]])
    shown = page_class_counts(text)
    classed = sum(shown.get(c, 0) for c in CLASSES)
    unclassified = max(total - classed, 0)
    wrong = {c: {"page": shown.get(c, 0), "oracle": want[c]} for c in CLASSES if shown.get(c, 0) != want[c]}
    ok = unclassified == 0 and not wrong
    return Result("pass" if ok else "fail", measured={"unclassified": unclassified, "wrong_classes": wrong},
                  expected="unclassified violations on the page = 0 and each class count = the oracle classifier's count",
                  detail=f"Altium report {total} violations; oracle classes {({c: want[c] for c in CLASSES})}; page shows {shown or 'no class counts'}; "
                         "ACCEPTANCE red on 27/11 = unclassified 421")


@metric(id="F-H(a)", title="DRC violations are classed JLC-reject / JLC-accept / cosmetic and the counts equal the oracle's", root="R4", level="B",
        kind="behaviour")
def fh_a(ctx):
    try:
        return judge_fh_a(_check_board(ctx))
    except (obs.NotObservable, ap.ProbeError, OSError) as e:
        return _err(str(e))


_FHA_TXT = ("Minimum Solder Mask Sliver (Gap=6mil) (All),(All)|||Minimum Solder Mask Sliver Constraint: (3.685mil < 6mil) Between Pad A and Via B [Top Solder] Mask Sliver [3.685mil]\n"
            "Silk to Silk (Clearance=10mil) (All),(All)|||Silk To Silk Clearance Constraint: (5.733mil < 10mil) Between Text A And Text B Silk Text to Silk Clearance [5.733mil]\n"
            "Board Clearance Constraint (Gap=0mil) (All)|||Board Outline Clearance(Outline Edge): (11.811mil < 12mil) Between Board Edge And Pad J-1 on Top Layer\n")
CONTROLS["F-H(a)"] = (judge_fh_a,
                      {"report_total": 3, "report_text": _FHA_TXT, "end_view": "3 violations: 1 JLC-reject, 1 JLC-accept, 1 cosmetic", "snaps": [], "after_reload": {"notes": []}},
                      {"report_total": 3, "report_text": _FHA_TXT, "end_view": "Altium DRC: total 3", "snaps": [], "after_reload": {"notes": []}})


# =============================================================================== F-H(d): a count on the Rules page equals the list it counts
_RULES_JS = r"""() => {
  const rows = t => [...t.querySelectorAll('tbody tr')].filter(r => r.querySelector('td')).length;
  const out = [];
  document.querySelectorAll('#view details').forEach(d => {
    d.open = true;
    const s = (d.querySelector('summary') || {innerText: ''}).innerText.trim();
    const t = d.querySelector('table');
    out.push({label: s, rows: t ? rows(t) : null});
  });
  return out;
}"""


def _observe_rules_counts(ctx) -> dict:
    with obs.browser(ctx) as b:
        b.goto_tab("rules", 1.5)
        head = b.text("#view")
        sections = b.page.evaluate(_RULES_JS)
        b.page.wait_for_timeout(500)
        show_all = None
        m = re.search(r"Show all (\d+)", head)
        if m:
            b.page.click(f"text=Show all {m.group(1)}")
            b.page.wait_for_timeout(800)
            show_all = {"label": m.group(0), "claimed": int(m.group(1)),
                        "rows": b.page.evaluate("() => [...document.querySelectorAll('#view table')].map(t => [...t.querySelectorAll('tbody tr')].filter(r => r.querySelector('td')).length)")}
        hm = re.search(r"^(\d+)\s+(.+rules?)\s*$", head, re.M)
    return {"sections": sections, "show_all": show_all, "header": ({"claimed": int(hm.group(1)), "label": hm.group(2)} if hm else None)}


def judge_fh_d(o: dict) -> Result:
    bad, checked = [], 0
    for s in o["sections"]:
        if s["rows"] is None:
            continue
        m = re.search(r"\((\d+)(?:\s+of\s+(\d+))?[^)]*\)", s["label"])
        if not m:
            continue
        claimed = int(m.group(2) or m.group(1))
        checked += 1
        if claimed != s["rows"]:
            bad.append({"badge": s["label"], "listed": s["rows"]})
    sa = o.get("show_all")
    if sa:
        checked += 1
        if sa["claimed"] not in sa["rows"] and sa["claimed"] != sum(sa["rows"]):
            bad.append({"badge": sa["label"], "listed_per_table": sa["rows"]})
    hd = o.get("header")
    if hd:
        checked += 1
        preset = next((s["rows"] for s in o["sections"] if re.search(r"preset", s["label"], re.I) and s["rows"] is not None), None)
        if preset is not None and hd["claimed"] != preset:
            bad.append({"badge": f"{hd['claimed']} {hd['label']}", "listed": preset})
    if not checked:
        return _err("the Rules page showed no count that could be compared with a list")
    return Result("pass" if not bad else "fail", measured=bad, expected="Rules-page counts that differ from the number of rows they count = 0",
                  detail=f"{checked} counts compared; ACCEPTANCE red on 27/11 names F-H(d) as a requirement without a counted red value")


@metric(id="F-H(d)", title="every count on the Rules page equals the number of listed items", root="R4", level="B", kind="behaviour")
def fh_d(ctx):
    try:
        o = obs.cached("rules_counts", lambda: _observe_rules_counts(ctx))
    except (obs.NotObservable, OSError) as e:
        return _err(str(e))
    return judge_fh_d(o)


CONTROLS["F-H(d)"] = (judge_fh_d,
                      {"sections": [{"label": "Extra rules (2)", "rows": 2}, {"label": "JLC preset (13 of 13 rules on)", "rows": 13}],
                       "show_all": {"label": "Show all 42", "claimed": 42, "rows": [42]}, "header": {"claimed": 13, "label": "preset rules"}},
                      {"sections": [{"label": "Extra rules (3)", "rows": 2}], "show_all": None, "header": None})
