"""W11 (a review chip started side effects; Stop did not stop the plan; the end message did not list them), behaviour legs.
(a) a review / read-only chip makes no side effect (only proposals), and chips still answer;
(b) side effects after Stop: the 27/11 case is an Altium project created after Stop; on Linux the product cannot start one,
    so (b) is the local Altium leg;
(c) the turn's end message lists every side effect, item by item.
The agent's reply is the oracle's fake engine replaying the 27/11 pattern: a review answer that also carries change actions.
A side effect = a project file (not a log, chat or proposal record) that differs after the turn."""
from __future__ import annotations

import json
import re

from lib import Result, metric, not_run
from live import common, seed
from live.driver import Page
from metrics.live_fc import _files


def _changed(before: dict, after: dict) -> list[str]:
    """Changed project files, without the previews re-rendered from them (artifacts/: derived, not a side effect of its own)."""
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k) and not k.startswith("artifacts"))


def _actions(ctx, tag: str) -> tuple[list, dict]:
    sheet = f"Z{ctx.rng.randrange(10, 99)}"
    topic = f"Note {tag} {ctx.rng.randrange(1000)}"
    goal = f"USB-C sensor logger, revision {ctx.rng.randrange(100)}"
    acts = [{"type": "idea.describe", "text": goal},
            {"type": "idea.propose", "topic": topic, "text": "Added by the review"},
            {"type": "netlist.write", "sheet": sheet, "data": {"id": sheet, "title": sheet, "sections": [{"id": "A", "title": "A"}],
                                                               "notes": [], "parts": [{"ref": f"R{ctx.rng.randrange(80, 99)}", "section": "A", "kind": "res",
                                                                                       "pins": [{"num": "1", "name": "1", "net": "+3V3"},
                                                                                                {"num": "2", "name": "2", "net": "GND"}]}]}}]
    return acts, {"goal": goal, "topic": topic, "sheet": sheet}


@metric(id="W11(a)", title="A review or read-only chip starts no side effect (proposals only), and the chip still answers",
        root="R5", p0=("P0-1",), level="B", kind="behaviour")
def w11_a(ctx):
    srv = common.private(ctx, "W11(a)", fresh=True)
    rec = {}
    try:
        srv.project = seed.seed_fixture(srv.projects, root=ctx.root)
        srv.restart()
        pdir = srv.projects / srv.project
        acts, names = _actions(ctx, "chip")
        answer = f"Here is what is open on the board ({ctx.rng.randrange(10**5)})."
        common.queue_turn(srv, {"steps": [{"tool": "Read", "input": {"file_path": "board-facts.json"}, "delay": 0.3}],
                                "final": answer + common.actions_block(acts)}, name="W11 chip")
        with Page(srv.url, srv.project) as P:
            P.open(ctx.rng.choice(["outputs", "pcb", "sch"]))
            chips = P.eval("""() => [...document.querySelectorAll('button')].filter(b => b.getBoundingClientRect().height > 0 &&
                 /^(what is wrong|review|check the|what is still open|what should i)/i.test(b.innerText.trim())).map(b => b.innerText.trim())""")
            if not chips:
                return Result("error", detail="no review / read-only chip on the page (nothing to measure)")
            chip = ctx.rng.choice(chips)
            before = _files(pdir)
            P.page.get_by_role("button", name=chip, exact=True).first.click()
            for _ in range(40):
                P.page.wait_for_timeout(500)
                if answer[:30] in P.text():
                    break
            answered = answer[:30] in P.text()
            changed = _changed(before, _files(pdir))
        rec = {"chip": chip, "answered": answered, "side_effects": changed}
    finally:
        srv.stop()
    v = len(rec["side_effects"]) + (0 if rec["answered"] else 1)
    return Result("pass" if v == 0 else "fail", measured=len(rec["side_effects"]),
                  expected="project files changed by a turn a review chip started = 0 (proposals only), and the chip's answer is shown",
                  detail=json.dumps(rec), evidence=[common.save(ctx, "W11(a)", rec)])


@metric(id="W11(b)", title="Side effects executed after Stop in that turn = 0 (an Altium project created after Stop)",
        root="R5", p0=("P0-1",), level="L", kind="behaviour")
def w11_b(ctx):
    return not_run("local Altium leg: the 27/11 side effect after Stop was an Altium project and skeleton; the product cannot start "
                   "one on Linux, and the non-Altium actions are checked against Stop before each one runs",
                   expected="side effects after Stop = 0")


@metric(id="W11(c)", title="The turn's end message lists every side effect, item by item",
        root="R5", p0=("P0-1",), level="B", kind="behaviour")
def w11_c(ctx):
    srv = common.private(ctx, "W11(c)", fresh=True)
    rec = {}
    try:
        srv.project = seed.seed_fixture(srv.projects, root=ctx.root)
        srv.restart()
        pdir = srv.projects / srv.project
        acts, names = _actions(ctx, "turn")
        answer = f"Done, I made the changes ({ctx.rng.randrange(10**5)})."
        common.queue_turn(srv, {"final": answer + common.actions_block(acts)}, name="W11 turn")
        with Page(srv.url, srv.project) as P:
            P.open("idea")
            before = _files(pdir)
            box = P.page.get_by_placeholder(re.compile(r"ask", re.I)).first
            box.fill("Please update the description, add a note and write the new sheet.")
            box.press("Enter")
            for _ in range(40):
                P.page.wait_for_timeout(500)
                if answer[:20] in P.text():
                    break
            P.page.wait_for_timeout(1000)
            # the turn's end message: the agent's reply to this message and any agent note after it (generous on purpose)
            end = P.eval("""t => { const ms = [...document.querySelectorAll('[class*=msg]')].filter(x => /\\b(agent|user)\\b/.test(x.className));
                 let i = ms.map(m => m.innerText).findIndex(x => x.includes(t)); if (i < 0) return '';
                 return ms.slice(i).filter(m => /\\bagent\\b/.test(m.className)).map(m => m.innerText).join('\\n'); }""", answer[:20])
            changed = _changed(before, _files(pdir))
    finally:
        srv.stop()
    # each side effect the files show must be named in the end message: the description, the new item (its topic), the sheet
    items = []
    if any(c.startswith("idea") for c in changed):
        items.append(("description", r"descri|goal"))
        idea_txt = " ".join(f.read_text(encoding="utf-8") for f in (pdir / "idea.json", pdir / "idea-draft.json") if f.is_file())
        if names["topic"] in idea_txt:
            items.append(("requirement " + names["topic"], re.escape(names["topic"])))
    if any(c.startswith("netlist") for c in changed):
        items.append(("sheet " + names["sheet"], r"(?<![\w])" + re.escape(names["sheet"]) + r"(?![\w])"))
    missing = [i for i, rx in items if not re.search(rx, end, re.I)]
    rec = {"changed": changed, "items": [i for i, _ in items], "end_message": end[:800], "missing": missing}
    return Result("pass" if not missing and items else "fail", measured=len(missing),
                  expected="side effects (from the files) not named one by one in the turn's end message = 0",
                  detail=json.dumps(rec)[:1500], evidence=[common.save(ctx, "W11(c)", rec)])
