"""Live metrics on conversation and navigation behaviour: F-E (consent), F-G and T-H (start-up and first use).

F-E drives the product's real consent path: the oracle's fake engine asks the yes/no replace question, the student answers
with a phrasing from the frozen corpus, and the engine then sends the place action. The product's own record of that turn
says whether the action ran past its consent gate (applied, or failed later in Altium) or was refused for consent.
"""
from __future__ import annotations

import json
import re

from lib import Result, metric
from live import common, corpora, seed
from live.driver import Page

CONSENT_REFUSAL = re.compile(r"not run\.", re.I)


def _consent_trial(srv, name: str, phrase: str) -> dict:
    q = corpora.header("fe_consent")["question"]
    common.queue_turn(srv, {"final": q + common.actions_block([{"type": "chat.ask", "options": ["yes", "no"]}])}, name=f"{name}-ask")
    srv.post("/api/chat", {"text": "Please place the parts on the board for me."}, project=name)
    common.queue_turn(srv, {"steps": [{"tool": "Read", "input": {"file_path": "bom.json"}, "delay": 0.2}],
                            "final": "Replacing the placement now." +
                            common.actions_block([{"type": "altium.place_pcb", "replace": True, "student_said": phrase}])},
                      name=f"{name}-act")
    st, body = srv.post("/api/chat", {"text": phrase}, project=name)
    rows = common.chat_rows(srv.projects / name)
    last = [r for r in rows if r.get("role") == "agent"][-1] if rows else {}
    blob = json.dumps(last, ensure_ascii=False)
    place = [x for x in (last.get("refused") or []) + (last.get("applied") or []) if "altium.place_pcb" in str(x)]
    refused = any("altium.place_pcb" in str(x) and CONSENT_REFUSAL.search(str(x)) for x in last.get("refused") or []) or \
        bool(re.search(r"altium\.place_pcb: not run\.", blob))
    return {"phrase": phrase, "refused_for_consent": refused, "record": place[:2] or blob[:400],
            "announced": "Replacing the placement now." in str(last.get("text", ""))}


@metric(id="F-E", title="Consent: affirmative replies with extra text grant the action, negations never do; nothing announced before consent",
        root="R5", level="B", kind="behaviour")
def fe(ctx):
    affs, note = [], ""
    vis = corpora.header("fe_consent")
    pool_a = [dict(phrase=p, half="visible") for p in vis["affirmative"]]
    pool_n = [dict(phrase=p, half="visible") for p in vis["negative"]]
    hp = corpora.HIDDEN / "fe_consent.json"
    if hp.is_file():
        h = json.loads(hp.read_text(encoding="utf-8"))
        pool_a += [dict(phrase=p, half="hidden") for p in h["affirmative"]]
        pool_n += [dict(phrase=p, half="hidden") for p in h["negative"]]
        note = f"fe_consent: visible + hidden ({len(pool_a)} affirmative, {len(pool_n)} negative)"
    else:
        note = f"fe_consent: VISIBLE HALF ONLY ({len(pool_a)} + {len(pool_n)})"
    ctx.rng.shuffle(pool_a)
    ctx.rng.shuffle(pool_n)
    srv = common.private(ctx, "F-E", fresh=True)
    rows = []
    try:
        names = []
        for i, it in enumerate(pool_a + pool_n):
            nm = f"fe-{i}"
            seed.seed_synthetic(srv.projects, nm, {})
            names.append((nm, it, it in pool_a))
        srv.start()
        for nm, it, positive in names:
            r = _consent_trial(srv, nm, it["phrase"])
            r.update(positive=positive, half=it["half"])
            rows.append(r)
    finally:
        srv.stop()
    refused_yes = [r["phrase"] for r in rows if r["positive"] and r["refused_for_consent"]]
    granted_no = [r["phrase"] for r in rows if not r["positive"] and not r["refused_for_consent"]]
    announced = [r["phrase"] for r in rows if r["refused_for_consent"] and r["announced"]]
    n = len(refused_yes) + len(granted_no) + len(announced)
    return Result("pass" if n == 0 else "fail",
                  measured={"affirmatives_refused": f"{len(refused_yes)}/{sum(r['positive'] for r in rows)}",
                            "negations_granted": len(granted_no), "announced_before_consent": len(announced)},
                  expected="affirmatives accepted 100%; negations granted 0; a reply announcing the action shown as said while it was refused 0",
                  detail=f"{note}; refused yes e.g. {refused_yes[:3]}; granted no: {granted_no[:3]}",
                  evidence=[common.save(ctx, "F-E-trials", rows), ctx.ev(corpora.VISIBLE / "fe_consent.json", "F-E corpus")])
