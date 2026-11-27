"""F-D (agent answers contradict or overreach), behaviour legs.
(a) every factual claim about project or part state in a final message has an evidence link or is phrased as unverified;
(b) repeat consistency: the T-F machinery (real engine, oracle judge) on its own draw of probe questions;
(c) a price is labelled with the quantity break actually used (the supply log written when the price was fetched)."""
from __future__ import annotations

import os
import re

from lib import Result, metric, not_run
from live import common, corpora, seed

REF = r"\b(?:U|C|R|J|Y|D|L|F|SW|Q)\d{1,3}\b"
FACT = re.compile(REF + r"[^.]{0,80}\b(?:is|are|has|have|sits|measures|was|now|uses|runs|carries|equals|meets|passes)\b|"
                  r"\b\d+(?:\.\d+)?\s*(?:parts|lines|mm|mil|nets|violations|vias|tracks|pF|nF|uF|µF|mA|A|V|W|°C|C/W)\b", re.I)
UNVERIFIED = re.compile(r"unverified|not (?:yet )?(?:verified|checked|confirmed)|assum|I could not (?:verify|check|read)|"
                        r"(?:to|please) (?:check|verify|confirm)|I (?:have not|haven.t) (?:checked|verified)|unknown", re.I)
CITE = re.compile(r"\{\{src:[^}]+\}\}")


@metric(id="F-D(a)", title="Factual claims in final messages carry an evidence link or are phrased as unverified",
        root="R1", p0=("P0-3",), level="B", kind="behaviour")
def fd_a(ctx):
    run = common.Run(ctx)
    bad, total = [], 0
    for r in common.chat_rows(run.project_dir):
        if r.get("role") != "agent" or r.get("by") == "button":
            continue
        backed_msg = bool(r.get("evidence") or r.get("claims_evidence"))
        for sent in re.split(r"(?<=[.!?])\s+|\n+", str(r.get("text", ""))):
            if len(sent) < 12 or not FACT.search(sent) or sent.strip().endswith("?"):
                continue
            total += 1
            if not (backed_msg or CITE.search(sent) or UNVERIFIED.search(sent)):
                bad.append({"ts": r.get("ts"), "claim": sent.strip()[:160]})
    return Result("pass" if not bad else "fail", measured=len(bad),
                  expected="factual claims (a part or project fact) with no evidence link and not phrased as unverified = 0",
                  detail=f"{len(bad)} of {total} claim sentences; e.g. {[b['claim'] for b in bad[:3]]}",
                  evidence=[common.save(ctx, "F-D(a)", bad)] + [ctx.ev(f, "chat record") for f in sorted((run.project_dir / "chats").glob("*.jsonl"))])


@metric(id="F-D(b)", title="Repeat consistency: 10 probe questions asked twice agree (the T-F machinery, its own draw)",
        root="R1", p0=("P0-3",), level="E", kind="behaviour")
def fd_b(ctx):
    if os.environ.get("ACCEPTANCE_REAL_ENGINE") != "1":
        return not_run("needs the real agent engine (ACCEPTANCE_REAL_ENGINE=1); same machinery as T-F", expected="10/10 consistent")
    from metrics import live_themes as T
    qs, note = corpora.load("probe_questions", "questions")
    import random
    draw = random.Random(ctx.seed ^ 0xFD).sample(qs, 10)          # F-D's own draw from the same frozen pool
    srv = common.private(ctx, "F-D(b)", engine="real", fresh=True)
    rows = []
    try:
        srv.project = seed.seed_fixture(srv.projects, root=ctx.root)
        srv.restart()
        for q in draw:
            a1, a2 = T._ask(srv, srv.project, q["text"]), T._ask(srv, srv.project, q["text"])
            rows.append({"q": q["text"], "half": q["half"], "a1": a1, "a2": a2, "judge": T._judge(q["text"], a1, a2)})
    finally:
        srv.stop()
    bad = [r for r in rows if r["judge"].get("agree") is not True]
    return Result("pass" if not bad else "fail", measured=f"{len(bad)}/{len(rows)}",
                  expected="answers whose facts disagree (or the judge could not decide) = 0 of 10",
                  detail=f"{note}; e.g. {[r['judge'].get('contradiction') for r in bad[:2]]}", evidence=[common.save(ctx, "F-D(b)", rows)])


PRICE = re.compile(r"\$\s?(\d+(?:\.\d+)?)[^.\n]{0,60}?\bat\s+(\d+)\s*(boards?|pcs|pieces|units|qty)\b|"
                   r"\bat\s+(\d+)\s*(boards?|pcs|pieces|units)\b[^.\n]{0,60}?\$\s?(\d+(?:\.\d+)?)", re.I)


@metric(id="F-D(c)", title="A price is labelled with the quantity break actually used (equal to the supply log)",
        root="R1", p0=("P0-3",), level="B", kind="behaviour")
def fd_c(ctx):
    run = common.Run(ctx)
    supply = common.seed.read_jsonl(run.project_dir / "supply-log.jsonl")
    bad, seen = [], 0
    for r in common.chat_rows(run.project_dir):
        if r.get("role") != "agent":
            continue
        breaks = {s.get("qty_break") for s in supply if s.get("ts", "") <= str(r.get("ts", "")) and s.get("qty_break")} or \
            {s.get("qty_break") for s in supply if s.get("qty_break")}     # a price fetched before the log began: the breaks it records
        for m in PRICE.finditer(str(r.get("text", ""))):
            seen += 1
            n = int(m.group(2) or m.group(4))
            per_board = re.search(r"board", m.group(3) or m.group(5) or "", re.I)
            used = sorted(breaks)
            ctx_txt = str(r.get("text", ""))[max(0, m.start() - 120):m.end() + 120]
            states_break = any(re.search(rf"\b(?:qty|quantity|break)\D{{0,12}}{b}\b|\b{b}[- ]piece", ctx_txt, re.I) for b in used)
            if used and n not in used and not (per_board and states_break):
                bad.append({"ts": r.get("ts"), "price": m.group(0)[:120], "stated_qty": n, "breaks_used": used})
    return Result("pass" if not bad else "fail", measured=len(bad),
                  expected="prices stated at a quantity that is not the break the supply log used, without naming that break = 0",
                  detail=f"{len(bad)} of {seen} quantity-labelled prices; {bad[:3]}",
                  evidence=[common.save(ctx, "F-D(c)", bad), ctx.ev(run.project_dir / "supply-log.jsonl", "supply log")])
