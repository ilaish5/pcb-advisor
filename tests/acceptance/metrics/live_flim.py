"""F-LIM (tool limits, said or unsaid): the frozen list of 15 limits (corpora/flim_limits.json, from REPORT's table), tried in a
random order with a random student wording. Each attempt must end in either a verified artifact change, or a refusal at the
control in the DOM (not in the chat) plus an open ledger item naming it. Silent, a false limit claim, or a limit stated only in
the chat = fail.

F-LIM(a): the 5 limits whose attempt needs no Altium (measured here). F-LIM(b): the 10 Altium limits, the local Altium leg.
The chat leg replays the 27/11 pattern: the student asks, the agent (the oracle's fake engine) states the limit in the chat."""
from __future__ import annotations

import json
import re

from lib import Result, metric, not_run
from live import common, corpora, faults, seed
from live.driver import Page

REFUSE = re.compile(r"cannot|can.t|could not|couldn.t|not able|unable|not supported|not (?:checked|compared)|needs|requires|"
                    r"only (?:you|in)|not possible|outside|by hand", re.I)


def _ledger(srv) -> list[str]:
    """Open ledger items as text (the product's ledger API; none at 2dcd691)."""
    for path in ("/api/ledger", "/api/findings"):
        st, body = srv.get(path)
        if st == 200 and isinstance(body, (dict, list)):
            items = body if isinstance(body, list) else body.get("items") or []
            return [json.dumps(i, ensure_ascii=False) for i in items if isinstance(i, dict) and i.get("state") == "open"]
    return []


def _control_refusal(P, page: str, words: str) -> list[str]:
    """Lines on the limit's own page (not the chat) that state the limit in words, still there after a reload."""
    P.reload()
    if page == "sources":
        P.eval("go('sources')")
        P.page.wait_for_timeout(1500)
    else:
        P.stage(page)
    main = P.eval("() => (document.querySelector('main') || document.body).innerText")
    rx = re.compile(words, re.I)
    return [ln.strip() for ln in main.splitlines() if rx.search(ln) and REFUSE.search(ln) and len(ln.split()) >= 4]


def _artifact(lim: dict, pdir, before: dict) -> bool:
    """The limit's artifact change, verified on the files: what the attempt asked for exists now."""
    k = lim["id"]
    if k == "url-fetch":
        return len(list((pdir / "sources").glob("*"))) > before["sources"]
    if k == "stm32-pin-table":
        bom = json.loads((pdir / "bom.json").read_text(encoding="utf-8"))
        mcu = next((ln for ln in bom if ln.get("key") == before["mcu"]), {})
        return mcu.get("pins_status") == "verified" and bool(mcu.get("pins_evidence"))
    if k == "readme-order-note":
        return any(re.search(r"order[ _-]?note|readme", f.name, re.I) for f in (pdir / "exports").glob("*"))
    return False                              # jlc-dfm-signin, pcba-preview: only JLC can do it; a refusal is the right end


@metric(id="F-LIM(a)", title="Tool limits without Altium: each attempt ends in an artifact change or a refusal at the control + an open ledger item",
        root="R5", p0=("P0-1", "P0-2"), level="B", kind="behaviour")
def flim_a(ctx):
    lims, note = corpora.load("flim_limits", "limits")
    by_id = {}
    for lm in lims:                                       # both halves carry the same 15 limits; their wordings pool
        by_id.setdefault(lm["id"], {**lm, "wordings": []})["wordings"] += lm["wordings"]
    todo = [lm for lm in by_id.values() if not lm["altium"]]
    ctx.rng.shuffle(todo)
    nf = faults.not_found_server()
    rows = []
    srv = common.private(ctx, "F-LIM", fresh=True)
    try:
        srv.project = seed.seed_fixture(srv.projects, root=ctx.root)
        srv.restart()
        pdir = srv.projects / srv.project
        bom = json.loads((pdir / "bom.json").read_text(encoding="utf-8"))
        mcu = next((ln["key"] for ln in bom if ln.get("pins_status") not in ("verified", "accepted") and ln.get("datasheet")
                    and len(ln.get("refs") or []) == 1 and re.match(r"U\d", ln["key"])), None)
        with Page(srv.url, srv.project) as P:
            P.open()
            for lm in todo:
                wording = ctx.rng.choice(lm["wordings"])
                before = {"sources": len(list((pdir / "sources").glob("*"))), "mcu": mcu}
                # 1. the control, as a student uses it
                if lm["id"] == "url-fetch":
                    P.eval("go('sources')")
                    P.page.wait_for_timeout(1200)
                    P.eval("document.querySelector('[data-act=addurl]').click()")
                    dlg = P.page.locator("dialog input, [role=dialog] input").first
                    dlg.fill(f"http://127.0.0.1:{nf.server_address[1]}/an/{ctx.rng.randrange(10**6)}.pdf")
                    dlg.press("Enter")
                    P.page.wait_for_timeout(4000)
                elif lm["id"] == "stm32-pin-table":
                    P.stage("checks")
                    b = P.page.get_by_role("button", name=re.compile(r"check datasheets", re.I))
                    if b.count():
                        b.first.click()
                        P.page.wait_for_timeout(8000)
                else:
                    P.stage(lm["page"])
                # 2. the chat: the student asks in their own words, the agent states the limit (27/11 pattern)
                common.queue_turn(srv, {"final": f"I cannot do that here: {wording.lower()} is not something this tool can do."},
                                  name=f"F-LIM {lm['id']}")
                srv.post("/api/chat", {"text": wording})
                at_control = _control_refusal(P, lm["page"], lm["words"])
                ledger = [i for i in _ledger(srv) if re.search(lm["words"], i, re.I)]
                changed = _artifact(lm, pdir, before)
                ok = changed or (at_control and ledger)
                rows.append({"limit": lm["id"], "wording": wording, "artifact_change": changed, "refusal_at_control": at_control[:2],
                             "open_ledger_item": bool(ledger), "ok": bool(ok)})
    finally:
        srv.stop()
        nf.shutdown()
    bad = [r for r in rows if not r["ok"]]
    return Result("pass" if not bad else "fail", measured=f"{len(bad)}/{len(rows)}",
                  expected="non-Altium limits ending silent, chat-only or with no ledger item = 0 of 5",
                  detail=f"{note}; " + "; ".join(f"{r['limit']}: control={bool(r['refusal_at_control'])} ledger={r['open_ledger_item']}" for r in bad),
                  evidence=[common.save(ctx, "F-LIM(a)", rows), ctx.ev(corpora.VISIBLE / "flim_limits.json", "F-LIM list")])


@metric(id="F-LIM(b)", title="Tool limits that need Altium (10 of the 15)", root="R5", p0=("P0-1", "P0-2"), level="L", kind="behaviour")
def flim_b(ctx):
    ids = [lm["id"] for lm in corpora.header("flim_limits")["limits"] if lm["altium"]]
    return not_run(f"local Altium leg: {', '.join(ids)}", expected="each ends in a verified artifact change or a refusal at the control + an open ledger item")
