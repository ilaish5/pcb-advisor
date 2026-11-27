"""Altium-judged advice metrics that compare what the page or the agent says with Altium's own DRC report file.
W30: a DRC fix advice names the rules that really have violations, and quotes the count Altium reports.

Observation: Altium's batch DRC report of the scratch board (the same cached observation as U3 / F-H) and one real agent turn asking how to fix
the DRC result (the agent's reply is the advice). Judge: rule by rule against the report, no LLM judge."""
from __future__ import annotations

import random
import re

from lib import Result, metric
from live_altium import agent, obs

CONTROLS: dict = {}

FIX_VERBS = re.compile(r"\b(move|moving|change|increase|reduce|decrease|delete|remove|resize|widen|shift|set|edit|adjust|shrink|enlarge|"
                       r"drag|fix|raise|lower|replace|add|clear|nudge|offset|enlarge)\b", re.I)

QUESTIONS = (
    "Altium's design rule check on the board still reports violations. What exactly do I have to change to fix them? Go rule by rule.",
    "I ran the DRC in Altium and it is not clean. Tell me how to fix the violations, and say which rules they come from and how many there are.",
    "What do I need to change on the layout so Altium's DRC passes? Please name the rules.",
)


def _err(msg: str) -> Result:
    return Result("error", detail=msg)


def short_rule(full: str) -> str:
    """'Silk To Solder Mask (Clearance=6mil) (All),(All)' -> 'Silk To Solder Mask' (the rule kind, without its parameters)."""
    return re.split(r"\s*[\(]", full, 1)[0].strip()


def rule_counts(report_counts: dict[str, int]) -> dict[str, int]:
    """{rule kind: violations in Altium's report}, summed over the rules of one kind."""
    out: dict[str, int] = {}
    for full, n in report_counts.items():
        out[short_rule(full)] = out.get(short_rule(full), 0) + int(n)
    return out


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?:])\s+|\n+", text) if s.strip()]


def advice_mentions(text: str, kinds: list[str]) -> dict[str, list[str]]:
    """{rule kind: the numbers quoted with it} for every rule kind the advice names in a sentence with a fix verb. A number counts as
    quoted with the rule when it stands within 40 characters after the name or before it (inside the same sentence)."""
    found: dict[str, list[str]] = {}
    for s in _sentences(text):
        if not FIX_VERBS.search(s) and not re.search(r"\d", s):
            continue
        work = s
        for k in kinds:                                   # longest kind first; a matched name is blanked so 'Clearance Constraint' is not read inside 'Board Clearance Constraint'
            for m in list(re.finditer(re.escape(k), work, re.I)):
                near = work[max(0, m.start() - 40): m.end() + 40]
                work = work[:m.start()] + " " * (m.end() - m.start()) + work[m.end():]
                nums = [int(x) for x in re.findall(r"(?<![\w.])(\d{1,6})(?![\w.])(?!\s*(?:mil|mm|um|µm))", near)]
                found.setdefault(k, []).extend(str(n) for n in nums)
    return found


def judge_w30(o: dict) -> Result:
    counts = rule_counts(o["report_counts"])
    if not any(counts.values()):
        return _err("Altium's report has no violation: the condition of the metric is not met on this board")
    reply = o["reply"]
    if o.get("code") != 200 or not reply.strip():
        return _err("the agent gave no answer (engine not available)")
    named = advice_mentions(reply, sorted(counts, key=len, reverse=True))
    problems: list[str] = []
    wrong_named = [k for k in named if counts.get(k, 0) == 0]
    unquoted = [k for k in named if counts.get(k, 0) > 0 and not named[k]]
    miscounted = [k for k in named if counts.get(k, 0) > 0 and named[k] and str(counts[k]) not in named[k]]
    absent = [k for k, n in counts.items() if n > 0 and k not in named]
    if not named:
        problems.append("the advice names no rule of the report")
    if wrong_named:
        problems.append(f"names rules with 0 violations in Altium's report: {wrong_named}")
    if unquoted:
        problems.append(f"does not quote Altium's count for: {unquoted}")
    if miscounted:
        problems.append("quotes a count that is not Altium's for: " + "; ".join(f"{k} (Altium {counts[k]}, advice {named[k]})" for k in miscounted))
    m = {"rules_with_violations": {k: n for k, n in counts.items() if n}, "named": {k: v for k, v in named.items()},
         "named_with_zero_violations": wrong_named, "count_not_quoted": unquoted, "count_wrong": miscounted, "rules_not_named": absent}
    return Result("pass" if not problems else "fail", measured=m,
                  expected="every rule named in a fix advice has violations > 0 in Altium's report, and the count quoted is Altium's",
                  detail=("; ".join(problems) or "all named rules are real and their counts are Altium's")
                         + f"; question: {o['question']!r}; answer: {reply[:240]!r}. "
                         "Legs not built: the predicted after-fix count vs the re-run count (needs an applied fix and a second Altium DRC), "
                         "and the canary that toggles a random rule on the live board (the control below does it on a synthetic report).")


def _observe_w30(ctx) -> dict:
    from metrics.altium_ui import _check_board        # the U3 observation: Altium's DRC report of the scratch board (cached)
    cb = _check_board(ctx)
    rng = random.Random(ctx.seed ^ 0x30AD)
    q = rng.choice(QUESTIONS)
    res = agent.ask(obs.base(ctx), obs.proj(ctx), q, timeout=900)
    return {"report_counts": cb["report_counts"], "question": q, "reply": res["reply"], "code": res["code"]}


@metric(id="W30", title="A DRC fix advice names the rules Altium reports and quotes Altium's count", root="R1", level="L", kind="behaviour", p0=("P0-3",))
def w30(ctx):
    try:
        o = obs.cached("w30", lambda: _observe_w30(ctx))
    except (obs.NotObservable, RuntimeError, OSError, ValueError, KeyError) as e:
        return _err(str(e))
    r = judge_w30(o)
    r.detail += " ACCEPTANCE: the 27/11 silk fix was advised for rules that could not be fixed that way (disputed id)."
    return r


# ---- controls: a report, a good advice (names real rules with Altium's count) and a bad one (a rule toggled to 0, a wrong count)
_REPORT = {"Silk To Solder Mask (Clearance=6mil) (All),(All)": 160, "Silk To Solder Mask (Clearance=10mil) (IsPad),(All)": 0,
           "Minimum Annular Ring (Minimum=8mil) (IsPad)": 4, "Minimum Solder Mask Sliver (Gap=6mil) (All),(All)": 252,
           "Short-Circuit Constraint (Allowed=No) (All),(All)": 0, "Board Clearance Constraint (Gap=0mil) (All)": 7}


def _w30_obs(reply: str) -> dict:
    return {"report_counts": _REPORT, "question": "q", "reply": reply, "code": 200}


CONTROLS["W30"] = (
    judge_w30,
    _w30_obs("Silk To Solder Mask has 160 violations: move the designators off the pads. Minimum Annular Ring has 4: increase the pad hole "
             "size. Minimum Solder Mask Sliver has 252: shrink the mask expansion. Board Clearance has 7: move the parts inside the outline."),
    _w30_obs("Fix the Short-Circuit Constraint by moving the track. Silk To Solder Mask has 150 violations: move the designators. "
             "Reduce the mask expansion."),
)
