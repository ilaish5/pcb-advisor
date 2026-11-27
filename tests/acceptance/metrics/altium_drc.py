"""Altium-judged advice metric: W30. A DRC fix advice names the rules that really have violations in Altium's DRC report file and quotes
Altium's count; it never blames a rule with 0 violations (the 27/11 case: "disable the extra 10 mil SilkToSolderMaskClearance to clear 157"
while that rule had 0 and the 6 mil JLC rule had the 157).

The unit is the RULE (kind + its parameter + its scope), not the rule kind: the fixture board carries two Silk To Solder Mask rules
(Clearance 6 mil All/All and Clearance 10 mil IsPad/All), which is exactly the 27/11 confusion.

Observation, N trials (default 5): trial 0 is the fixture board as the student had it; trials 1.. are canaries: a random rule that has
violations gets its parameter set to zero in the scratch PcbDoc (same-length edit of the Rules6 stream, read back), the product's own
'Check board' is run, Altium's own batch DRC report of the same file is the ground truth, and then one real agent turn asks how to fix the
silk violations. The board is put back after the trials. Judge: rule by rule against the report, no LLM judge."""
from __future__ import annotations

import hashlib
import pathlib
import random
import re
import shutil

from lib import Result, metric
from live_altium import agent, altium_probe as ap, obs

CONTROLS: dict = {}
TRIALS = 5

FIX_VERBS = re.compile(r"\b(move|moving|change|increase|reduce|decrease|delete|remove|resize|widen|shift|set|edit|adjust|shrink|enlarge|"
                       r"drag|fix|raise|lower|replace|add|clear|nudge|offset|disable|relax|loosen|turn off|switch off|lift)\b", re.I)

QUESTIONS = (
    "Altium's design rule check on the board reports silk screen violations (Silk To Solder Mask). What exactly do I have to change to clear them? Name the rule and say how many there are.",
    "The DRC in Altium still shows the silkscreen-to-solder-mask violations. Tell me how to fix them: which rule do they come from, how many are there, and what do I change?",
    "How do I get rid of the silk screen violations Altium reports? Please go by the rule names and counts in the DRC.",
)

# Rules6 RULEKIND -> (the kind as Altium's report spells it, the key that holds the rule's number, set to 0 by the canary)
KINDS = {
    "SilkToSolderMaskClearance": ("Silk To Solder Mask", "MINSILKSCREENTOMASKGAP"),
    "SilkToSilkClearance": ("Silk to Silk", "SILKTOSILKCLEARANCE"),
    "MinimumSolderMaskSliver": ("Minimum Solder Mask Sliver", "MINSOLDERMASKWIDTH"),
    "MinimumAnnularRing": ("Minimum Annular Ring", "MINIMUMRING"),
    "BoardOutlineClearance": ("Board Clearance Constraint", "GAP"),
}
# how an advice may spell a kind (letters only, lower case); longest first when matching
ALIASES = {
    "Silk To Solder Mask": ["silktosoldermask", "silkscreentosoldermask", "silktomask"],
    "Silk to Silk": ["silktosilk", "silkscreentosilk"],
    "Minimum Solder Mask Sliver": ["minimumsoldermasksliver", "soldermasksliver", "masksliver"],
    "Minimum Annular Ring": ["minimumannularring", "annularring"],
    "Board Clearance Constraint": ["boardclearanceconstraint", "boardoutlineclearance", "boardclearance"],
}


def _err(msg: str) -> Result:
    return Result("error", detail=msg)


# ------------------------------------------------------------------------------------------------ the report, rule by rule
def short_rule(full: str) -> str:
    """'Silk To Solder Mask (Clearance=6mil) (All),(All)' -> 'Silk To Solder Mask' (the rule kind, without its parameters)."""
    return re.split(r"\s*[\(]", full, 1)[0].strip()


def rules_of(report_counts: dict[str, int]) -> list[dict]:
    """One row per rule of Altium's report: kind, its first number in mil (the rule's parameter), its scope text and the violation count."""
    rows = []
    for full, n in report_counts.items():
        m = re.search(r"=\s*(\d+(?:\.\d+)?)\s*mil", full)
        rows.append({"kind": short_rule(full), "param_mil": float(m.group(1)) if m else None, "text": full, "count": int(n)})
    return rows


def rule_counts(report_counts: dict[str, int]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rules_of(report_counts):
        out[r["kind"]] = out.get(r["kind"], 0) + r["count"]
    return out


# ------------------------------------------------------------------------------------------------ the advice
UNIT = re.compile(r"(\d+(?:\.\d+)?)\s*(mil|mm|µm|um)\b", re.I)
# a sentence that says the rule is clean ("0 here", "no violations", "is clean", "nothing to fix") does not blame it
SAYS_ZERO = re.compile(r"(?<![\w.])0(?![\w.])|zero|no (?:\w+ )?violations?|none|clean|nothing to (?:fix|change)|no longer|already (?:clear|clean|pass)", re.I)
VIOL = re.compile(r"(?<![\w.])(\d{1,6})\s+(?:\w+\s+){0,2}?(?:violations?|errors?|hits?)\b", re.I)


def _letters(s: str) -> str:
    return re.sub(r"[^a-z]", "", s.lower())


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?:])\s+|\n+", text) if s.strip()]


def _to_mil(v: float, unit: str) -> float:
    u = unit.lower()
    return v if u == "mil" else v / 0.0254 if u == "mm" else v / 25.4


def mentions(text: str, rules: list[dict]) -> list[dict]:
    """Every (sentence, rule kind) pair of the advice: a sentence with a fix verb or a number that names a kind (any spelling in ALIASES, also
    run together like SilkToSolderMaskClearance). The rules it refers to: those of the kind whose parameter equals a mil / mm value in the same
    sentence (10 mil, 0.254 mm), else every rule of the kind. `quoted` = the numbers said as 'N violations'."""
    kinds = sorted({r["kind"] for r in rules})
    out = []
    for s in _sentences(text):
        if not FIX_VERBS.search(s) and not re.search(r"\d", s):
            continue
        work = _letters(s)
        found = []
        for alias, kind in sorted(((a, k) for k in kinds for a in ALIASES.get(k, [_letters(k)])), key=lambda t: -len(t[0])):
            while alias and alias in work:
                i = work.index(alias)
                work = work[:i] + "#" * len(alias) + work[i + len(alias):]
                if kind not in found:
                    found.append(kind)
        if not found:
            continue
        mils = [_to_mil(float(v), u) for v, u in UNIT.findall(s)]
        for kind in found:
            cand = [r for r in rules if r["kind"] == kind]
            by_param = [r for r in cand if r["param_mil"] is not None and any(abs(r["param_mil"] - m) <= max(0.02 * m, 0.05) for m in mils)]
            out.append({"kind": kind, "by_parameter": bool(by_param), "rules": by_param or cand,
                        "quoted": [int(x) for x in VIOL.findall(s)], "says_zero": bool(SAYS_ZERO.search(s)), "sentence": s.strip()[:240]})
    return out


def judge_trial(report_counts: dict[str, int], reply: str) -> dict:
    rules = rules_of(report_counts)
    total = sum(r["count"] for r in rules)
    ms = mentions(reply, rules)
    zero, miscounted, named = [], [], []
    for m in ms:
        counts = [r["count"] for r in m["rules"]]
        label = f"{m['kind']} ({'; '.join(r['text'][len(m['kind']):].strip()[:48] for r in m['rules'])})"
        named.append(label)
        if counts and max(counts) == 0 and not m["says_zero"]:
            zero.append(f"{label} has 0 violations in Altium's report: «{m['sentence']}»")
        ok = set(counts) | {sum(counts), total}
        bad = [q for q in m["quoted"] if q not in ok and q not in {r["count"] for r in rules}]
        if bad and max(counts or [0]) > 0:
            miscounted.append(f"{label}: advice quotes {bad}, Altium has {sorted(set(counts))}: «{m['sentence']}»")
    problems = zero + miscounted
    if not ms:
        problems.append("the advice names no rule of Altium's report")
    return {"problems": problems, "named": named, "zero_rules_named": zero, "count_wrong": miscounted,
            "rules_with_violations": {r["text"]: r["count"] for r in rules if r["count"]}}


def judge_w30(o: dict) -> Result:
    trials = o["trials"]
    if not trials:
        return _err("no trial was observed")
    rows, red, errs = [], [], []
    for i, t in enumerate(trials):
        if t.get("code") != 200 or not str(t.get("reply", "")).strip():
            errs.append(f"trial {i}: the agent gave no answer (engine not available)")
            continue
        if not any(t["report_counts"].values()):
            errs.append(f"trial {i}: Altium's report has no violation")
            continue
        j = judge_trial(t["report_counts"], t["reply"])
        j.update({"trial": i, "canary": t.get("canary"), "question": t["question"], "reply": t["reply"][:1200]})
        rows.append(j)
        if j["problems"]:
            red.append(i)
    if errs and not rows:
        return _err("; ".join(errs))
    return Result("fail" if red else "pass",
                  measured={"trials": len(rows), "red_trials": red, "red_rate": f"{len(red)}/{len(rows)}",
                            "per_trial": [{"trial": j["trial"], "canary": j["canary"], "problems": j["problems"], "named": j["named"], "reply": j["reply"][:900]} for j in rows]},
                  expected="every rule an advice names has violations > 0 in Altium's report and the count it quotes is Altium's, in every trial",
                  detail=f"{len(red)} of {len(rows)} trials red; " + " | ".join(p for j in rows for p in j["problems"])[:1500]
                         + ("; errors: " + "; ".join(errs) if errs else "")
                         + ". Not built: the predicted after-fix count vs a DRC re-run AFTER the fix is applied (the advice's own fix is free text). "
                           "ACCEPTANCE: 27/11 'disable the extra 10 mil SilkToSolderMaskClearance to clear 157' while that rule had 0 (disputed id).")


# ------------------------------------------------------------------------------------------------ the observation
def zero_rule(pcb: pathlib.Path, name: str) -> dict:
    """The canary: the rule `name` of the SCRATCH board gets the number 0 (digits replaced by zeros, same length, so the Rules6 stream keeps
    its record lengths). Read back through the oracle's reader before it is relied on."""
    import olefile
    from oracle.pcbdoc import PcbDoc
    with PcbDoc(pcb) as d:
        rec = next((r for r in d.rules() if r.get("NAME") == name), None)
    if rec is None or rec.get("RULEKIND") not in KINDS:
        raise obs.NotObservable(f"rule {name!r} not found / not a canary kind in the scratch board")
    key = KINDS[rec["RULEKIND"]][1]
    old = rec.get(key, "")
    new = re.sub(r"\d", "0", old)
    o = olefile.OleFileIO(str(pcb), write_mode=True)
    try:
        data = bytearray(o.openstream("Rules6/Data").read())
        pat = re.compile(rb"\|NAME=" + re.escape(name.encode()) + rb"\|", re.I)
        done = False
        for m in pat.finditer(bytes(data)):
            start = bytes(data).rfind(b"|RULEKIND=", 0, m.start())
            end = bytes(data).find(b"\x00", m.end())
            seg = bytes(data[start:end])
            kv = re.search(rb"\|" + key.encode() + rb"=" + re.escape(old.encode()) + rb"(?=\||$)", seg)
            if start >= 0 and kv and len(new) == len(old):
                a = start + kv.start() + len(key) + 2
                data[a:a + len(old)] = new.encode()
                done = True
                break
        if not done:
            raise obs.NotObservable(f"the record of {name!r} cannot take {new!r} for {key} in place")
        o.write_stream("Rules6/Data", bytes(data))
    finally:
        o.close()
    with PcbDoc(pcb) as d:
        back = next((r for r in d.rules() if r.get("NAME") == name), {})
    if back.get(key) != new:
        raise obs.NotObservable(f"the canary on {name!r} does not read back ({back.get(key)!r})")
    return {"rule": name, "kind": rec["RULEKIND"], "key": key, "was": old, "now": new}


def _canary_names(pcb: pathlib.Path, baseline: dict[str, int], rnd: random.Random, n: int) -> list[str]:
    """Rules of the scratch board that have violations in the baseline report (matched by kind and number), in random order."""
    from oracle.pcbdoc import PcbDoc
    rep = rules_of(baseline)
    out = []
    with PcbDoc(pcb) as d:
        for r in d.rules():
            k = KINDS.get(r.get("RULEKIND", ""))
            if not k:
                continue
            mil = re.search(r"(\d+(?:\.\d+)?)\s*mil", r.get(k[1], ""))
            if mil and any(x["kind"] == k[0] and x["param_mil"] == float(mil.group(1)) and x["count"] > 0 for x in rep):
                out.append(r["NAME"])
    rnd.shuffle(out)
    return out[:n]


def _observe_w30(ctx, trials: int = TRIALS) -> dict:
    pcb = obs.scratch_pcb(ctx)
    adir = obs.scratch_altium(ctx)
    work = adir / "oracle"
    work.mkdir(exist_ok=True)
    rnd = random.Random(ctx.seed ^ 0x30AD)
    keep = work / "before-w30.PcbDoc"
    shutil.copy2(pcb, keep)
    sha0 = hashlib.sha256(pcb.read_bytes()).hexdigest()
    obs.wait_owner_idle()
    out: dict = {"trials": [], "sha_before": sha0}
    plan: list[str | None] = [None]
    try:
        for i in range(trials):
            ap.close_scratch(adir)                              # no document of the scratch copy open while its file is replaced
            shutil.copy2(keep, pcb)
            canary = None
            if i > 0:
                if len(plan) == 1:                              # the baseline report decides which rules can be toggled
                    plan += _canary_names(pcb, out["trials"][0]["report_counts"], rnd, trials - 1)
                if i >= len(plan):
                    break
                canary = zero_rule(pcb, plan[i])
            with obs.browser(ctx) as b:                         # the student presses Check board first
                b.goto_tab("pcb", 1.5)
                obs.click_step(b, "Check board")
                obs.watch(b, 240, label=f"w30-check-{i}")
            txt = ap.drc_report(pcb, work)                      # Altium's own report of the same file on disk = the ground truth
            q = QUESTIONS[i % len(QUESTIONS)] if i else rnd.choice(QUESTIONS)
            res = agent.ask(obs.base(ctx), obs.proj(ctx), q, timeout=900)
            out["trials"].append({"canary": canary, "report_counts": ap.drc_counts(txt), "report_total": ap.drc_total(txt),
                                  "question": q, "reply": res["reply"], "code": res["code"]})
    finally:
        try:
            ap.close_scratch(adir)
        finally:
            shutil.copy2(keep, pcb)
    out["sha_after"] = hashlib.sha256(pcb.read_bytes()).hexdigest()
    return out


@metric(id="W30", title="A DRC fix advice names only rules with violations in Altium's report and quotes Altium's count", root="R1", level="L", kind="behaviour", p0=("P0-3",))
def w30(ctx):
    try:
        o = obs.cached("w30", lambda: _observe_w30(ctx))
    except (obs.NotObservable, RuntimeError, OSError, ValueError, KeyError, ap.ProbeError) as e:
        return _err(str(e))
    r = judge_w30(o)
    r.detail += f"; board put back: {o['sha_before'] == o['sha_after']}"
    return r


# ---- controls: a report with the 27/11 shape (two silk rules: 6 mil with violations, 10 mil IsPad with none), a good and a bad advice
_REPORT = {"Silk To Solder Mask (Clearance=6mil) (All),(All)": 160, "Silk To Solder Mask (Clearance=10mil) (IsPad),(All)": 0,
           "Minimum Annular Ring (Minimum=8mil) (IsPad)": 4, "Minimum Solder Mask Sliver (Gap=6mil) (All),(All)": 252,
           "Short-Circuit Constraint (Allowed=No) (All),(All)": 0, "Board Clearance Constraint (Gap=0mil) (All)": 7}


def _w30_obs(reply: str) -> dict:
    return {"trials": [{"canary": None, "report_counts": _REPORT, "question": "q", "reply": reply, "code": 200}]}


CONTROLS["W30"] = (
    judge_w30,
    _w30_obs("The 6 mil Silk To Solder Mask rule has 160 violations: move the designators off the pads. Minimum Annular Ring has 4 violations: "
             "increase the pad size. Minimum Solder Mask Sliver has 252 violations: shrink the mask expansion."),
    _w30_obs("Disable the extra 10 mil SilkToSolderMaskClearance rule to clear 160 violations. Then move the designators."),
)
