"""Live metrics on design checks the product must run itself, fed with frozen corpora (A15) through the product's own
inputs (idea requirements, BOM cards, netlist sheets, datasheet text): W3, W6, W13, W20, W22, W37.

The oracle knows the injected answer (it built the input); it reads the page and the API for the product's verdict.
"""
from __future__ import annotations

import json
import re
import time

from lib import Result, metric
from live import common, corpora, seed
from live.driver import Page

CONFLICT = re.compile(r"conflict|contradict|incompatib|inconsistent|cannot both|can.t both|clash|at odds|mutually exclusive", re.I)


def _conflict_shown(texts: list[str], t1: str, t2: str) -> bool:
    """A conflict naming both item ids (here: the requirement topics) in one visible message."""
    for t in texts:
        if CONFLICT.search(t) and t1.lower() in t.lower() and t2.lower() in t.lower():
            return True
    return False


def _messages(P) -> list[str]:
    """Every line of prose a student can read on the page (a line of at least 4 words), toasts and chat included. A
    rendered drawing (one label per line) is not prose, so a ref and a pin name drawn next to each other never count as
    a message about them."""
    blocks = P.eval("""() => [...document.querySelectorAll('main, [role=alert], .toast, [class*=chat], aside, dialog')]
        .filter(e => e.getBoundingClientRect().height > 0).map(e => e.innerText || '')""")
    out = []
    for b in blocks:
        for line in b.splitlines():
            line = line.strip()
            if len(line.split()) >= 4 and line not in out:
                out.append(line)
    return out


@metric(id="W3", title="Contradictory requirements are flagged before Confirm, naming both items; consistent twins are not",
        root="R3", level="B", kind="behaviour")
def w3(ctx):
    pairs, note = corpora.load("w3_contradictions", "pairs")
    fillers = corpora.header("w3_contradictions")["fillers"]
    srv = common.private(ctx, "W3", fresh=True)
    rows = []
    try:
        plan = []
        for p in pairs:
            for twin in (False, True):
                name = f"w3-{p['id']}-{'twin' if twin else 'pair'}"
                need = {"topic": p["need"]["topic"], "text": ctx.rng.choice(p["need"]["wordings"])}
                prov = {"topic": p["provision"]["topic"], "text": ctx.rng.choice(p["twin_wordings"] if twin else p["provision"]["wordings"])}
                if prov["topic"] == need["topic"]:
                    prov["topic"] += " (2)"
                items = [f for f in ctx.rng.sample(fillers, 3) if f["topic"] not in (need["topic"], prov["topic"])] + [need, prov]
                ctx.rng.shuffle(items)
                seed.seed_synthetic(srv.projects, name, {})
                plan.append((p, twin, name, need, prov, items))
        srv.start()
        with Page(srv.url, "x") as P:
            for p, twin, name, need, prov, items in plan:
                P.project = name
                for it in items:
                    srv.post("/api/idea/item", it, project=name)
                P.open("idea")
                before = _messages(P)
                btn = P.page.get_by_role("button", name=re.compile(r"^\s*confirm( the)? idea", re.I))
                clicked = False
                if btn.count():
                    btn.first.click()
                    clicked = True
                else:
                    srv.post("/api/idea/confirm", {}, project=name)
                P.page.wait_for_timeout(2500)
                after = _messages(P) + before
                st, state = srv.get("/api/state", project=name)
                confirmed = bool(((state or {}).get("idea") or {}).get("confirmed"))
                flagged = _conflict_shown(after, need["topic"], prov["topic"])
                rows.append({"pair": p["id"], "half": p["half"], "twin": twin, "need": need, "provision": prov,
                             "flagged": flagged, "confirmed_anyway": confirmed, "clicked_confirm": clicked})
    finally:
        srv.stop()
    real = [r for r in rows if not r["twin"]]
    twins = [r for r in rows if r["twin"]]
    found = sum(r["flagged"] for r in real)
    false = sum(r["flagged"] for r in twins)
    ok = found == len(real) and false == 0
    return Result("pass" if ok else "fail", measured={"flagged": f"{found}/{len(real)}", "false_on_twins": false},
                  expected=f"contradictions flagged naming both items {len(real)}/{len(real)}; false conflicts on consistent twins 0",
                  detail=f"{note}; confirmed despite a contradiction: {sum(r['confirmed_anyway'] for r in real)}",
                  evidence=[common.save(ctx, "W3-runs", rows),
                            ctx.ev(corpora.VISIBLE / "w3_contradictions.json", "W3 corpus (visible half)")])


# ------------------------------------------------------------------ synthetic sheets (W22, W6)
def _part(ref, kind, value, pins):
    return {"ref": ref, "section": "A", "kind": kind, "value": value,
            "pins": [{"num": str(n), "name": str(nm), "net": net} for n, nm, net in pins]}


def _cap(ref, a, b, value="100nF"):
    return _part(ref, "cap", value, [("1", "1", a), ("2", "2", b)])


def _res(ref, a, b, value="10k"):
    return _part(ref, "res", value, [("1", "1", a), ("2", "2", b)])


class _Refs:
    """Random designators per sheet (A9: nothing in the check knows a fixed ref)."""

    def __init__(self, rng):
        self.rng, self.used = rng, set()

    def __call__(self, prefix):
        while True:
            r = f"{prefix}{self.rng.randrange(2, 60)}"
            if r not in self.used:
                self.used.add(r)
                return r


def _w22_sheet(cls: dict, part: dict, rng, defect: bool):
    R = _Refs(rng)
    parts, target = [], None
    k = cls["id"]
    if k == "decap_missing":
        target = R("U")
        parts.append(_part(target, "ic", part["value"], [(n, nm, "+3V3") for n, nm in part["supply_pins"]] +
                           [(n, nm, "GND") for n, nm in part["gnd"]]))
        if not defect:
            parts += [_cap(R("C"), "+3V3", "GND") for _ in part["supply_pins"]]
    elif k == "i3c_shared_spi":
        target, flash = R("U"), R("U")
        bus = ["SPI1_SCK", "SPI1_MOSI", "SPI1_MISO"]
        own = bus if defect else ["SPI2_SCK", "SPI2_MOSI", "SPI2_MISO"]
        nets = {"SCL": own[0], "SDA": own[1], "SDO": own[2], "CS": "IMU_CS"}
        pins = []
        for n, nm in part["pins"]:
            key = next(x for x in ("CS", "SDO", "SCL", "SDA") if x in nm.upper().replace("AD0", "SDO"))
            pins.append((n, nm, nets[key]))
        parts.append(_part(target, "ic", part["value"], pins + [("90", "VDD", "+3V3"), ("91", "GND", "GND")]))
        parts.append(_part(flash, "ic", "W25Q128JVSIQ", [("1", "/CS", "FL_CS"), ("2", "DO", bus[2]), ("5", "DI", bus[1]),
                                                          ("6", "CLK", bus[0]), ("8", "VCC", "+3V3"), ("4", "GND", "GND")]))
        parts += [_cap(R("C"), "+3V3", "GND"), _cap(R("C"), "+3V3", "GND")]
    elif k == "od_no_pullup":
        target, host = R("U"), R("U")
        parts.append(_part(target, "ic", part["value"], [(part["pins"][0][0], part["pins"][0][1], "I2C_SCL"),
                                                          (part["pins"][1][0], part["pins"][1][1], "I2C_SDA"),
                                                          ("90", "VDD", "+3V3"), ("91", "GND", "GND")]))
        parts.append(_part(host, "ic", "STM32F411CEU6", [("42", "PB6", "I2C_SCL"), ("43", "PB7", "I2C_SDA"),
                                                          ("1", "VBAT", "+3V3"), ("23", "VSS", "GND")]))
        parts += [_cap(R("C"), "+3V3", "GND"), _cap(R("C"), "+3V3", "GND")]
        if not defect:
            parts += [_res(R("R"), "I2C_SCL", "+3V3", "4.7k"), _res(R("R"), "I2C_SDA", "+3V3", "4.7k")]
    elif k == "ep_not_gnd":
        target = R("U")
        parts.append(_part(target, "ic", part["value"], [("1", "VDD", "+3V3"), ("2", "VSS", "GND"),
                                                          (part["ep"][0], part["ep"][1], "+3V3" if defect else "GND")]))
        parts.append(_cap(R("C"), "+3V3", "GND"))
    elif k == "xtal_no_caps":
        target, host = R("Y"), R("U")
        parts.append(_part(target, "xtal", part["value"], [("1", "1", part["net_in"]), ("2", "2", part["net_out"])]))
        parts.append(_part(host, "ic", "STM32F411CEU6", [("5", "PH0-OSC_IN", part["net_in"]), ("6", "PH1-OSC_OUT", part["net_out"]),
                                                          ("1", "VBAT", "+3V3"), ("23", "VSS", "GND")]))
        parts.append(_cap(R("C"), "+3V3", "GND"))
        if not defect:
            parts += [_cap(R("C"), part["net_in"], "GND", "12pF"), _cap(R("C"), part["net_out"], "GND", "12pF")]
    return {"id": "Main", "title": "Main", "sections": [{"id": "A", "title": "Sheet"}], "notes": [], "parts": parts}, target


def _bom_for(sheet):
    out = []
    for p in sheet["parts"]:
        out.append({"key": p["ref"], "refs": [p["ref"]], "value": p["value"], "mpn": p["value"], "qty": 1, "role": p["kind"]})
    return out


def _review(P, srv, name: str, final: str) -> list[str]:
    """Open the Schematic page, then press the page's own review chip; the fake engine answers `final` (a model-only
    review). Returns every message the student can read afterwards (page + chat)."""
    P.project = name
    P.open("sch")
    msgs = _messages(P)
    common.queue_turn(srv, {"steps": [{"tool": "Read", "input": {"file_path": "netlist/Main.json"}, "delay": 0.3}],
                            "final": final}, name=f"review {name}")
    chip = P.page.get_by_role("button", name=re.compile(r"review this sheet", re.I))
    if chip.count():
        chip.first.click()
        for _ in range(40):
            P.page.wait_for_timeout(500)
            if final[:20] in P.text():
                break
    return msgs + _messages(P)


def _named(msgs: list[str], ref: str, words: str) -> list[str]:
    rx = re.compile(words, re.I)
    return [m for m in msgs if re.search(r"(?<![\w])" + re.escape(ref) + r"(?![\w])", m) and rx.search(m)]


@metric(id="W22", title="Schematic review: 5 required rule classes detected on synthetic sheets, clean twins quiet, no model-only '0 errors'",
        root="R2", p0=("P0-3",), level="B", kind="behaviour")
def w22(ctx):
    classes, note = corpora.load("w22_rule_classes", "classes")
    by_id = {}
    for c in classes:                         # both halves: the parts of a class are pooled
        by_id.setdefault(c["id"], {"id": c["id"], "words": c["words"], "parts": []})["parts"] += c["parts"]
    srv = common.private(ctx, "W22", fresh=True)
    rows, zero_claims = [], 0
    final = "I reviewed the sheet: 0 errors, everything is connected correctly."
    try:
        plan = []
        for cid, cls in by_id.items():
            part = ctx.rng.choice(cls["parts"])
            for defect in (True, False):
                sheet, target = _w22_sheet(cls, part, ctx.rng, defect)
                name = f"w22-{cid}-{'bad' if defect else 'twin'}"
                seed.seed_synthetic(srv.projects, name, {"netlist/Main.json": sheet, "bom.json": _bom_for(sheet)})
                plan.append((cls, part, defect, name, target))
        srv.start()
        with Page(srv.url, "x") as P:
            for cls, part, defect, name, target in plan:
                msgs = _review(P, srv, name, final)
                hits = _named(msgs, target, cls["words"])
                shown_zero = any(re.search(r"\b0 errors\b|\bno errors\b|no issues", m, re.I) and
                                 not re.search(r"\b\d+ of \d+\b|scope|checked:", m, re.I) for m in msgs)
                zero_claims += shown_zero and defect
                rows.append({"class": cls["id"], "part": part.get("value"), "defect": defect, "target": target,
                             "detected": bool(hits), "hits": hits[:2], "model_only_zero_errors_shown": shown_zero})
    finally:
        srv.stop()
    det = sum(r["detected"] for r in rows if r["defect"])
    false = sum(r["detected"] for r in rows if not r["defect"])
    n = sum(1 for r in rows if r["defect"])
    ok = det == n and false == 0 and zero_claims == 0
    return Result("pass" if ok else "fail", measured={"detected": f"{det}/{n}", "false_on_twins": false, "model_only_0_errors": zero_claims},
                  expected=f"detected {n}/{n} naming the injected part; clean twins 0; a model-only review rendered as '0 errors' 0",
                  detail=note, evidence=[common.save(ctx, "W22-runs", rows), ctx.ev(corpora.VISIBLE / "w22_rule_classes.json", "W22 corpus")])


def _w6_sheet(fam: dict, rng, drop: str | None):
    R = _Refs(rng)
    mcu = R("U")
    pins, parts = [], []
    for s in fam["straps"]:
        net = f"{(s.get('alias') or s['name']).replace('-', '_')}_STRAP"
        pins.append((s["pin"], s["name"], net))
        if s["name"] == drop:                         # the strap goes to a header pin and nothing sets its level
            parts.append(_part(R("J"), "conn", "1x2 header", [("1", "1", net), ("2", "2", "GND")]))
        else:
            parts.append(_res(R("R"), net, "GND" if s["level"] == "0" else "+3V3"))
    pins += [("90", "VDD", "+3V3"), ("91", "VSS", "GND")]
    parts.insert(0, _part(mcu, "ic", fam["mpn"], pins))
    parts.append(_cap(R("C"), "+3V3", "GND"))
    return {"id": "Main", "title": "Main", "sections": [{"id": "A", "title": "MCU"}], "notes": [], "parts": parts}, mcu


@metric(id="W6", title="Every boot/strap pin the MCU's boot table lists is tied at a stated level; a removed strap is flagged by name",
        root="R3", level="B", kind="behaviour")
def w6(ctx):
    fams, note = corpora.load("w6_boot_straps", "families")
    srv = common.private(ctx, "W6", fresh=True)
    rows = []
    try:
        plan = []
        for fam in fams:
            drop = ctx.rng.choice(fam["straps"])["name"]          # one strap removed at random from a correct plan
            for defect in (True, False):
                sheet, mcu = _w6_sheet(fam, ctx.rng, drop if defect else None)
                name = f"w6-{re.sub(r'[^a-z0-9]+', '-', fam['mpn'].lower())}-{'bad' if defect else 'twin'}"
                seed.seed_synthetic(srv.projects, name, {"netlist/Main.json": sheet, "bom.json": _bom_for(sheet)})
                strap = next(s for s in fam["straps"] if s["name"] == drop)
                plan.append((fam, strap, defect, name, mcu))
        srv.start()
        with Page(srv.url, "x") as P:
            for fam, strap, defect, name, mcu in plan:
                msgs = _review(P, srv, name, "The pin plan looks complete.")
                names = [strap["name"]] + ([strap["alias"]] if strap.get("alias") else [])
                hits = [m for m in msgs if any(re.search(r"(?<![\w])" + re.escape(x) + r"(?![\w])", m) for x in names)
                        and re.search(r"boot|strap|level|tie|tied|pull|float", m, re.I) and not m.startswith("The pin plan")]
                rows.append({"family": fam["family"], "half": fam["half"], "strap": strap["name"], "defect": defect,
                             "flagged": bool(hits), "hits": hits[:2]})
    finally:
        srv.stop()
    miss = sum(1 for r in rows if r["defect"] and not r["flagged"])
    false = sum(1 for r in rows if not r["defect"] and r["flagged"])
    # corroboration: the 27/11 pin plan in the chat (ACCEPTANCE: PB2 not assigned at 01:25:16)
    return Result("pass" if miss == 0 and false == 0 else "fail", measured={"missed": miss, "false_on_twins": false},
                  expected="removed straps not flagged by name = 0; flags on correct plans = 0",
                  detail=note, evidence=[common.save(ctx, "W6-runs", rows), ctx.ev(corpora.VISIBLE / "w6_boot_straps.json", "W6 corpus")])


# ------------------------------------------------------------------ W13
def _numbers_near(text: str, value: float, rel: float = 0.05) -> bool:
    for m in re.finditer(r"(\d+(?:\.\d+)?)", text):
        x = float(m.group(1))
        if value and abs(x - value) <= rel * abs(value):
            return True
    return False


def _card_texts(srv, name: str, P, resp) -> list[str]:
    """What the student sees about a proposed card: the propose answer's error (a refusal), the card record the page
    renders (proposals in /api/state), and the BOM page's lines."""
    out = []
    if isinstance(resp, dict) and resp.get("error"):
        out.append(str(resp["error"]))
    st, state = srv.get("/api/state", project=name)
    for pr in (state or {}).get("proposals") or []:
        out.append(json.dumps(pr, ensure_ascii=False))
    P.project = name
    P.open("bom")
    out += _messages(P)
    return out


@metric(id="W13", title="BOM cards run the datasheet-mandated checks (crystal gm_crit, LDO Tj) and flag a failing part with the numbers",
        root="R3", level="B", kind="behaviour")
def w13(ctx):
    import math
    pool, note = corpora.load("w13_parts", "mcu_osc")
    ldos, _ = corpora.load("w13_parts", "ldos")
    srv = common.private(ctx, "W13", fresh=True)
    rows, plan = [], []
    try:
        rng = ctx.rng
        for i, osc in enumerate(pool):
            for canary in (True, False):
                F = rng.choice(osc["freq_hz"])
                c0, cl = rng.uniform(1.0, 7.0) * 1e-12, rng.choice([6, 8, 10, 12, 18, 20]) * 1e-12
                target = osc["gm_crit_max"] * (rng.uniform(1.25, 2.5) if canary else rng.uniform(0.3, 0.8))
                esr = target / (4 * (2 * math.pi * F) ** 2 * (c0 + cl) ** 2)
                gm = 4 * esr * (2 * math.pi * F) ** 2 * (c0 + cl) ** 2
                scale = 1e3 if osc["unit"] == "mA/V" else 1e6
                ref, mcu_ref = f"Y{rng.randrange(2, 40)}", f"U{rng.randrange(2, 40)}"
                xtal = f"SYN-XTAL-{rng.randrange(10**5)}"
                name = f"w13-xtal-{i}-{'canary' if canary else 'twin'}"
                files = {
                    f"sources/{osc['mpn']}.pdf.txt": osc["excerpt"], f"sources/{osc['mpn']}.pdf": b"%PDF-1.4\n%synthetic\n",
                    f"sources/{xtal}.pdf.txt": (f"{xtal} crystal unit\nNominal frequency {F / 1e6:g} MHz\nEquivalent series resistance ESR max "
                                                f"{esr:.0f} Ohm\nShunt capacitance C0 {c0 * 1e12:.2f} pF\nLoad capacitance CL {cl * 1e12:.0f} pF\n"),
                    f"sources/{xtal}.pdf": b"%PDF-1.4\n%synthetic\n",
                    "bom.json": [{"key": mcu_ref, "refs": [mcu_ref], "mpn": osc["mpn"], "value": osc["mpn"], "qty": 1,
                                  "role": "MCU", "datasheet": f"{osc['mpn']}.pdf"}]}
                seed.seed_synthetic(srv.projects, name, files)
                card = {"line": ref, "changes": {"mpn": xtal, "value": f"{F / 1e6:g} MHz {cl * 1e12:.0f} pF", "qty": 1, "refs": [ref],
                                                 "role": f"{osc['osc']} crystal for {mcu_ref}", "datasheet": f"{xtal}.pdf"},
                        "reason": f"{osc['osc']} crystal for the MCU"}
                plan.append({"kind": "crystal", "name": name, "card": card, "canary": canary, "want": gm * scale,
                             "unit": osc["unit"], "words": r"\bgm|g_m|transconductance|gain margin|critical", "half": osc["half"]})
        for i, ldo in enumerate(ldos):
            for canary in (True, False):
                tamb = rng.choice([40, 50, 55, 60, 70])
                vin = 5.0
                need_pd = ((ldo["tj_max"] - tamb) / ldo["theta_ja"]) * (rng.uniform(1.2, 2.0) if canary else rng.uniform(0.3, 0.7))
                iout = round(need_pd / (vin - ldo["vout"]), 3)
                tj = tamb + (vin - ldo["vout"]) * iout * ldo["theta_ja"]
                ref = f"U{rng.randrange(2, 40)}"
                name = f"w13-ldo-{i}-{'canary' if canary else 'twin'}"
                files = {
                    f"sources/{ldo['mpn']}.pdf.txt": (f"{ldo['mpn']} low-dropout regulator, {ldo['package']}\nOutput voltage {ldo['vout']} V\n"
                                                      f"Thermal resistance junction-to-ambient RthJA {ldo['theta_ja']:.0f} C/W\n"
                                                      f"Maximum junction temperature TJ max {ldo['tj_max']:.0f} C\n"),
                    f"sources/{ldo['mpn']}.pdf": b"%PDF-1.4\n%synthetic\n",
                    "idea.json": {"goal": "Sensor board", "agreed": [
                        {"topic": "Environment", "text": f"Ambient temperature up to {tamb} C", "by": "student", "status": "confirmed"},
                        {"topic": "Power", "text": f"5 V USB in; the {ldo['vout']} V rail draws up to {iout:g} A", "by": "student", "status": "confirmed"}],
                        "blocks": [], "links": [], "confirmed": True}}
                seed.seed_synthetic(srv.projects, name, files)
                card = {"line": ref, "changes": {"mpn": ldo["mpn"], "value": f"{ldo['vout']} V LDO", "qty": 1, "refs": [ref],
                                                 "role": f"{ldo['vout']} V regulator from 5 V USB, load {iout:g} A", "datasheet": f"{ldo['mpn']}.pdf"},
                        "reason": "regulator for the logic rail"}
                plan.append({"kind": "ldo", "name": name, "card": card, "canary": canary, "want": tj, "unit": "C",
                             "words": r"\bTj\b|junction", "half": ldo["half"]})
        srv.start()
        with Page(srv.url, "x") as P:
            for it in plan:
                # the card arrives the way the agent proposes a new part: a bom.propose action in its reply (new: true)
                act = {"type": "bom.propose", "new": True, **it["card"]}
                common.queue_turn(srv, {"steps": [{"tool": "Read", "input": {"file_path": "sources"}, "delay": 0.3}],
                                        "final": f"I proposed {it['card']['changes']['mpn']} for {it['card']['line']}." +
                                        common.actions_block([act])}, name=it["name"])
                st, resp = srv.post("/api/chat", {"text": f"Pick a part for {it['card']['changes']['role']}"}, project=it["name"])
                resp = {"error": (resp or {}).get("error")} if isinstance(resp, dict) else {}
                texts = _card_texts(srv, it["name"], P, resp)
                hit = [t for t in texts if re.search(it["words"], t, re.I) and _numbers_near(t, it["want"])]
                seen = any(it["card"]["changes"]["mpn"] in t for t in texts)      # the card exists (else the run proves nothing)
                rows.append({**{k: v for k, v in it.items() if k != "card"}, "propose_status": st, "flagged": bool(hit), "card_seen": seen,
                             "hit": hit[:1], "card": it["card"]})
    finally:
        srv.stop()
    missed = sum(1 for r in rows if r["canary"] and not r["flagged"])
    false = sum(1 for r in rows if not r["canary"] and r["flagged"])
    n = sum(1 for r in rows if r["canary"])
    unseen = [r["name"] for r in rows if not r["card_seen"]]
    if unseen:
        return Result("error", measured=None, detail=f"cards never reached the product (no measurement): {unseen}",
                      evidence=[common.save(ctx, "W13-runs", rows)])
    return Result("pass" if missed == 0 and false == 0 else "fail", measured={"missed": f"{missed}/{n}", "false_on_twins": false},
                  expected="failing crystals / LDOs proposed on a card and not refused or flagged with the oracle's number = 0; passing twins flagged = 0",
                  detail=note + "; MCU decoupling-figure sub-check not built here (needs the figure-table corpus)",
                  evidence=[common.save(ctx, "W13-runs", rows), ctx.ev(corpora.VISIBLE / "w13_parts.json", "W13 corpus")])


# ------------------------------------------------------------------ W37
# Thresholds, cited (A7): shared/reference/jlc/pcb-capabilities.en.md
MASK_WEB_MIN_MM = 0.10      # § Solder mask: "Mask bridge (dam between pads), 1 oz copper: 0.10 mm for green" [P1]
NPTH_TO_COPPER_MM = 0.20    # § Traces and spacing: "NPTH to track 0.2 mm" [P1]
EDGE_TO_COPPER_MM = 0.20    # § Outline, board size and thickness: "Copper to edge: routed edge ... >= 0.2 mm" [P1]


def _gerber(body: list[str], apertures: dict[str, str]) -> str:
    head = ["G04 oracle-built synthetic set (tests/acceptance)*", "%FSLAX46Y46*%", "%MOMM*%", "%LPD*%"]
    head += [f"%ADD{k}{v}*%" for k, v in apertures.items()]
    return "\n".join(head + body + ["M02*"]) + "\n"


_ORIGIN = [0.0, 0.0]


def _xy(x: float, y: float) -> str:
    return f"X{round((x + _ORIGIN[0]) * 1e6)}Y{round((y + _ORIGIN[1]) * 1e6)}"


def _w37_set(rng, defects: bool, outline=None) -> tuple[dict, list[dict]]:
    """A board on the given outline [x0, y0, x1, y1] (mm; the seeded project's own): a few pads and tracks, one NPTH, and
    (defects=True) three injected defects at random places. Coordinates are written relative to the outline origin and
    shifted back, so every reported location can be compared in either frame. Returns ({...}, [{kind, x, y, value}])."""
    x0, y0, x1, y1 = outline or (0.0, 0.0, 50.0, 40.0)
    W, H = x1 - x0, y1 - y0
    hole = (rng.uniform(8, W - 8), rng.uniform(8, H - 8), 3.2)
    inj, cu, mask = [], ["D10*"], ["D11*"]
    pads = []
    for _ in range(6):                                    # ordinary pads with safe gaps
        x, y = rng.uniform(5, W - 5), rng.uniform(5, H - 5)
        if (x - hole[0]) ** 2 + (y - hole[1]) ** 2 > 6 ** 2:
            pads.append((x, y))
    cu += ["D11*"] + [_xy(x, y) + "D03*" for x, y in pads]
    mask += [_xy(x, y) + "D03*" for x, y in pads]
    tw = 0.25
    if defects:
        # (a) mask web < 0.10 mm: two 1.0 x 0.6 pads whose 1.1 x 0.7 mask openings are `gap` apart
        gap = rng.uniform(0.03, 0.08)
        mx, my = rng.uniform(6, W - 10), rng.uniform(4, H - 6)
        if (mx - hole[0]) ** 2 + (my - hole[1]) ** 2 < 8 ** 2:
            my = hole[1] - 7 if hole[1] > 10 else hole[1] + 7
        p2x = mx + 1.1 + gap
        cu += [_xy(mx, my) + "D03*", _xy(p2x, my) + "D03*"]
        mask += [_xy(mx, my) + "D03*", _xy(p2x, my) + "D03*"]
        inj.append({"kind": "mask web", "x": (mx + p2x) / 2, "y": my, "value": round(gap, 3)})
        # (b) copper < 0.2 mm from the NPTH wall: a vertical track whose edge is `d` from the hole wall
        d = rng.uniform(0.05, 0.15)
        tx = hole[0] + hole[2] / 2 + d + tw / 2
        cu += ["D10*", _xy(tx, hole[1] - 3) + "D02*", _xy(tx, hole[1] + 3) + "D01*"]
        inj.append({"kind": "copper to NPTH", "x": tx, "y": hole[1], "value": round(d, 3)})
        # (c) copper < 0.2 mm from the routed edge: a horizontal track `e` from the bottom edge
        e = rng.uniform(0.03, 0.15)
        ex = rng.uniform(10, W - 15)
        cu += [_xy(ex, e + tw / 2) + "D02*", _xy(ex + 5, e + tw / 2) + "D01*"]
        inj.append({"kind": "copper to edge", "x": ex + 2.5, "y": 0.0, "value": round(e, 3)})
    aps_cu = {"10": f"C,{tw:.3f}", "11": "R,1.000X0.600"}
    aps_mask = {"11": "R,1.100X0.700"}
    outline = ["D10*", _xy(0, 0) + "D02*", _xy(W, 0) + "D01*", _xy(W, H) + "D01*", _xy(0, H) + "D01*", _xy(0, 0) + "D01*"]
    files = {"GTL": _gerber(cu, aps_cu), "GBL": _gerber(["D10*"], aps_cu), "GTS": _gerber(mask, aps_mask),
             "GBS": _gerber(["D11*"], aps_mask), "GTO": _gerber(["D10*"], {"10": "C,0.150"}),
             "GM1": _gerber(outline, {"10": "C,0.100"})}
    drill = ["M48", "METRIC,TZ", f"T1C{hole[2]:.3f}", "%", "G90", "G05", "T1",
             f"X{hole[0] + _ORIGIN[0]:.3f}Y{hole[1] + _ORIGIN[1]:.3f}", "M30"]
    return {"gerbers": files, "npth": "\n".join(drill) + "\n", "size": (W, H)}, inj


@metric(id="W37", title="Pre-order checks find mask webs < 0.10 mm, copper < 0.2 mm from NPTH and from the routed edge, with location",
        root="R2", p0=("P0-3",), level="B", kind="behaviour")
def w37(ctx):
    srv = common.private(ctx, "W37", fresh=True)
    rows = []
    words = {"mask web": r"mask|web|dam|bridge|sliver", "copper to NPTH": r"NPTH|non-plated|hole", "copper to edge": r"edge|outline"}
    try:
        plan = []
        for defects in (True, False):
            # a board the product has checked (the fixture: PcbDoc + its board check on record), whose Gerber set the
            # oracle then replaces with its own; only then do the pre-order checks run at all
            name = seed.seed_fixture(srv.projects, name=f"w37-{'bad' if defects else 'twin'}", root=ctx.root)
            facts = json.loads((srv.projects / name / "board-facts.json").read_text(encoding="utf-8"))
            _ORIGIN[:] = facts["outline"][:2]
            data, inj = _w37_set(ctx.rng, defects, facts["outline"])
            alt = srv.home / "altium" / name
            outs = sorted(alt.glob("Project Outputs for */Gerber"))
            g = outs[0]
            d = g.parent / "NC Drill"
            stem = sorted(g.glob("*.GTL"))[0].stem
            for f in list(g.iterdir()) + list(d.iterdir()):
                if f.is_file():
                    f.unlink()
            for ext, text in data["gerbers"].items():
                (g / f"{stem}.{ext}").write_text(text, encoding="ascii")
            (d / f"{stem}-RoundHoles-NonPlated.TXT").write_text(data["npth"], encoding="ascii")
            for k in inj:                        # locations in the board's own frame and in absolute Gerber coordinates
                k["abs_x"], k["abs_y"] = k["x"] + _ORIGIN[0], k["y"] + _ORIGIN[1]
            plan.append((name, defects, inj))
        srv.start()
        with Page(srv.url, "x") as P:
            for name, defects, inj in plan:
                P.project = name
                P.open("checks")
                before = set(_messages(P))
                st, resp = srv.post("/api/jlc/gerber-zip", {}, project=name)       # what "Get the Gerber zip" posts
                P.reload()
                # what the build added: new lines on the page, and the build's own answer
                msgs = [m for m in _messages(P) if m not in before] + [json.dumps(resp, ensure_ascii=False)[:20000]]
                for k in (inj if defects else [{"kind": k, "x": None, "y": None} for k in words]):
                    rx = re.compile(words[k["kind"]], re.I)
                    hits = [m for m in msgs if rx.search(m) and re.search(r"too close|below|less than|<|minimum|min\b|violat|fail|reject", m, re.I)]
                    if k["x"] is not None:
                        hits = [m for m in hits if any(abs(float(n) - k[c]) <= 0.5 for n in re.findall(r"\d+(?:\.\d+)?", m)
                                                       for c in ("x", "abs_x"))]
                    rows.append({"set": name, "defect": defects, **k, "reported": bool(hits), "hit": hits[:1], "zip_status": st,
                                 "zip_answer": (resp.get("error") if isinstance(resp, dict) else str(resp))})
    finally:
        srv.stop()
    found = sum(r["reported"] for r in rows if r["defect"])
    n = sum(1 for r in rows if r["defect"])
    false = sum(r["reported"] for r in rows if not r["defect"])
    return Result("pass" if found == n and false == 0 else "fail", measured={"reported_with_location": f"{found}/{n}", "false_on_clean_twin": false},
                  expected=f"injected Gerber defects reported with location {n}/{n}; clean twin 0",
                  detail=("defect (d) 'DRC summary rule value != Rules6 value' needs a PcbDoc writer: local phase. "
                          f"Thresholds: mask web {MASK_WEB_MIN_MM} mm, NPTH {NPTH_TO_COPPER_MM} mm, edge {EDGE_TO_COPPER_MM} mm (pcb-capabilities)."),
                  evidence=[common.save(ctx, "W37-runs", rows)])


# ------------------------------------------------------------------ W20
ALTS = ["GPIO", "TIM_CH", "ADC_IN", "SPI_NSS", "UART_TX", "EVENTOUT", "AF7", "TEST", "RSVD"]


def _symbol_pins(path) -> list[tuple[str, str]]:
    """(number, name) of every pin in a KiCad symbol file, read by the oracle; ~{X} (overbar) is written /X."""
    txt = path.read_text(encoding="utf-8", errors="replace")
    pins = re.findall(r'\(name "([^"]*)"[^\n]*\n\s*\(number "([^"]*)"', txt)
    out = []
    for name, num in pins:
        name = re.sub(r"~\{([^}]*)\}", r"/\1", name)
        if (num, name) not in out:
            out.append((num, name))
    return out


def _page(style: str, mpn: str, pins: list[tuple[str, str]], rng, pkg: str = "") -> str:
    lines = [f"{mpn}", "", "Pin description", ""]
    note = []
    if style == "number-first":
        lines += ["Pin No.  Pin name  Type  Description"] + [f"{n}  {nm}  I/O  function of pin {n}" for n, nm in pins]
    elif style == "multi-function":
        lines += ["Pin  Functions  Type"] + [f"{n}  {rng.choice(ALTS)}{n} / {rng.choice(ALTS)} ({nm})  I/O" for n, nm in pins]
    elif style == "ordering-code-note":
        k = rng.randrange(len(pins))
        lines += ["Pin No.  Pin name  Type"] + [f"{n}  {('RSVD(1)' if i == k else nm)}  I/O" for i, (n, nm) in enumerate(pins)]
        note = ["", f"Note 1: for the ordering code {mpn}, pin {pins[k][0]} is {pins[k][1]}."]
    elif style == "name-first":
        lines += ["Name  Pin  Type  Description"] + [f"{nm}  {n}  I/O  function of {nm}" for n, nm in pins]
    elif style == "two-packages":
        other = "LQFP" if "QFN" in pkg.upper() else "QFN"
        mine = pkg or "SOP"
        lines += [f"{other} pin  {mine} pin  Pin name  Type"] + [f"{int(n) + 3 if n.isdigit() else n}  {n}  {nm}  I/O" for n, nm in pins]
        lines.insert(0, f"Package: {mine} (this part, {mpn}); {other} pin numbers are given for reference only.")
    else:
        lines += ["Pin  Name  Type"] + [f"{n}  {nm} [{rng.choice(ALTS)}, {rng.choice(ALTS)}]  I/O" for n, nm in pins]
        note = ["", "Names in brackets are alternate functions selected in firmware."]
    return "\n".join(lines + note) + "\n"


def _mini_pdf(text: str) -> bytes:
    """A small valid one-page PDF holding `text` (so a product that re-extracts the text finds the same page)."""
    lines = [ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for ln in text.splitlines()]
    stream = "BT /F1 8 Tf 40 800 Td 10 TL " + " ".join(f"({ln}) '" for ln in lines) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream", "<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>"]
    out, offs = "%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out.encode("latin-1", "replace")))
        out += f"{i} 0 obj\n{o}\nendobj\n"
    x = len(out.encode("latin-1", "replace"))
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offs)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n"
    return out.encode("latin-1", "replace")


@metric(id="W20", title="Pin verification: no false conflicts on multi-function cells / ordering-code notes; true renames found",
        root="R2", p0=("P0-3",), level="B", kind="behaviour")
def w20(ctx):
    styles, note = corpora.load("w20_pin_tables", "styles")
    srv = common.private(ctx, "W20", fresh=True)
    rows = []
    try:
        name = seed.seed_fixture(srv.projects, name="w20", root=ctx.root)
        pdir = srv.projects / name
        man = json.loads((pdir / "library" / "manifest.json").read_text(encoding="utf-8"))
        bom = {ln["key"]: ln for ln in json.loads((pdir / "bom.json").read_text(encoding="utf-8"))}
        parts = []
        for key, ent in man.items():          # every built part with a symbol file and at least 4 pins (a rule, no names)
            f = pdir / "library" / "easyeda" / str(ent.get("lcsc")) / "lib.kicad_sym"
            if key in bom and f.is_file():
                pins = _symbol_pins(f)
                named = sum(1 for _, nm in pins if re.search(r"[A-Za-z]", nm))
                if len(pins) >= 4 and named * 2 >= len(pins):           # a pin table to compare: most pins carry names
                    parts.append((key, ent.get("mpn") or bom[key].get("mpn"), pins, ent.get("package") or bom[key].get("package") or ""))
        ctx.rng.shuffle(parts)
        plan = []
        for i, (key, mpn, pins, pkg) in enumerate(parts[:10]):
            style = styles[i % len(styles)]
            for renamed in (False, True):
                pp = list(pins)
                hit = None
                if renamed:                      # a true rename: one random pin carries another real name in the datasheet
                    j = ctx.rng.randrange(len(pp))
                    other = ctx.rng.choice([nm for _, nm in pins if nm != pp[j][1]] or ["NC"])
                    hit = {"pin": pp[j][0], "symbol": pp[j][1], "datasheet": other}
                    pp[j] = (pp[j][0], other)
                text = _page(style["id"], mpn, pp, ctx.rng, pkg)
                doc = f"ACC-{key}-{style['id']}-{'ren' if renamed else 'ok'}-{ctx.rng.randrange(10**5)}.pdf"
                (pdir / "sources" / doc).write_bytes(_mini_pdf(text))
                (pdir / "sources" / (doc + ".txt")).write_text(text, encoding="utf-8")
                plan.append((key, mpn, style, renamed, hit, doc))
        srv.restart()
        for key, mpn, style, renamed, hit, doc in plan:
            st, body = srv.post("/api/parts/attach_datasheet", {"line": key, "name": doc}, project=name)
            res = (body or {}).get("attached") or {} if isinstance(body, dict) else {}
            status, issues = res.get("status"), str(res.get("issues") or (body or {}).get("error", ""))
            conflict = status == "mismatch"
            named = bool(hit) and (re.search(rf"\bpin {re.escape(hit['pin'])}\b", issues) or hit["datasheet"] in issues)
            rows.append({"line": key, "style": style["id"], "half": style["half"], "renamed": renamed, "inject": hit,
                         "http": st, "status": status, "issues": issues[:300]})
            rows[-1]["false_conflict"] = (not renamed) and conflict
            rows[-1]["rename_found"] = renamed and conflict and bool(named)
    finally:
        srv.stop()
    twins = [r for r in rows if not r["renamed"]]
    ren = [r for r in rows if r["renamed"]]
    false = sum(r["false_conflict"] for r in twins)
    found = sum(r["rename_found"] for r in ren)
    unchecked = sum(1 for r in twins if r["status"] not in ("verified", "mismatch"))
    ok = false == 0 and found == len(ren)
    return Result("pass" if ok else "fail", measured={"false_conflicts": f"{false}/{len(twins)}", "renames_found": f"{found}/{len(ren)}",
                                                     "twins_not_verified (info)": unchecked},
                  expected=f"false conflicts 0/{len(twins)}; injected renames found naming the pin {len(ren)}/{len(ren)}; every correct twin verified",
                  detail=note, evidence=[common.save(ctx, "W20-runs", rows), ctx.ev(corpora.VISIBLE / "w20_pin_tables.json", "W20 corpus")])
