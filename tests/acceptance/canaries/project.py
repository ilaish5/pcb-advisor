"""Canary injectors for the project-data metrics (A5).

Every injector takes a WRITABLE Ctx (a copy of a corrected control), plants one defect of the metric's kind at a seeded random
place (`ctx.rng`) and returns a dict naming what it planted. The metric must then FAIL and name that item; a metric that does
not is blind and its control raises. Nothing here imports product code; files are changed as plain JSON / JSONL.
"""
from __future__ import annotations

import json
import pathlib
import shutil


# ----------------------------------------------------------------------------- file helpers
def _rd(p: pathlib.Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _wr(p: pathlib.Path, d) -> None:
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def _rd_l(p: pathlib.Path) -> list[dict]:
    if not p.is_file():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def _wr_l(p: pathlib.Path, rows: list[dict]) -> None:
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


def _tag(c, n: int = 3) -> str:
    return "".join(c.rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(n))


def _late(c) -> str:
    """A time stamp later than anything in the project, distinct per call (seeded)."""
    return "2026-11-29T%02d:%02d:%02d.%03d" % (c.rng.randint(0, 23), c.rng.randint(0, 59), c.rng.randint(0, 59), c.rng.randint(0, 999))


def _bom_lines(c):
    d = _rd(c.project / "bom.json")
    return d, (d["lines"] if isinstance(d, dict) else d)


def rewrite_chat(c, fn) -> None:
    """Apply fn(message_dict) to every chat message of every session file (in place), then save."""
    for p in sorted((c.project / "chats").glob("*.jsonl")):
        rows = _rd_l(p)
        for m in rows:
            fn(m)
        _wr_l(p, rows)


def append_chat(c, row: dict) -> None:
    files = sorted((c.project / "chats").glob("*.jsonl"))
    rows = _rd_l(files[-1])
    rows.append(row)
    _wr_l(files[-1], rows)


# ----------------------------------------------------------------------------- injectors
def inject_w2(c) -> dict:
    p = c.project / "idea.json"
    idea = _rd(p)
    w, h = 90 + c.rng.randint(1, 9), 70 + c.rng.randint(1, 9)
    tok = f"{w} x {h} mm"
    idea["goal"] = idea.get("goal", "") + f" The board is {tok}."
    _wr(p, idea)
    return {"token": tok}


def inject_w5a(c) -> dict:
    p = c.project / "idea.json"
    idea = _rd(p)
    topic = "Zz" + _tag(c)
    idea.setdefault("agreed", []).append({"topic": topic, "text": "a guessed value (assumed)", "by": "agent", "status": "confirmed",
                                          "ts": _late(c)})
    _wr(p, idea)
    return {"topic": topic}


def inject_w5b(c) -> dict:
    p = c.project / "idea-versions.json"
    vs = _rd(p)
    base = json.loads(json.dumps(vs[-1]))
    n0 = max(v["n"] for v in vs)
    t_conf, t_item, t_twin = "2026-11-29T01:00:00.000", "2026-11-29T01:10:00.000", "2026-11-29T01:20:00.000"
    bad = json.loads(json.dumps(base))
    bad.update(n=n0 + 1, ts=t_item)
    bad["idea"]["confirmed"], bad["idea"]["confirmed_at"] = True, t_conf
    for k in ("changed_since_confirm", "needs_reconfirm", "confirm_stale"):
        bad["idea"].pop(k, None)
    bad["idea"].setdefault("agreed", []).append({"topic": "Zz" + _tag(c), "text": "changed after confirmation", "by": "student",
                                                 "status": "confirmed", "ts": t_item})
    twin = json.loads(json.dumps(bad))
    twin.update(n=n0 + 2, ts=t_twin)               # same agreed items as `bad`: a save that changed nothing
    twin["idea"]["confirmed_at"] = t_conf
    _wr(p, vs + [bad, twin])
    return {"n_bad": n0 + 1, "n_twin": n0 + 2}


def inject_w7(c) -> dict:
    p = c.project / "bom-log.jsonl"
    rows = _rd_l(p)
    key = "ZW" + _tag(c, 2)
    rows.append({"ts": _late(c), "by": "agent-approved", "line": key,
                 "changes": {"value": "10k", "role": "I2C pull-ups 2 x (SDA, SCL)", "refs": [key + "1"]},
                 "before": {}, "reason": "canary", "sources": [], "proposal": None})
    _wr_l(p, rows)
    return {"line": key}


def inject_w8a(c) -> dict:
    p = c.project / "proposals.jsonl"
    rows = _rd_l(p)
    pid = "pZZ" + _tag(c)
    ts = _late(c)
    mpn = "ZZ" + _tag(c, 4) + "99"
    rows.append({"id": pid, "ts": ts, "kind": "bom", "line": "U1", "changes": {"mpn": mpn}, "before": {"mpn": mpn},
                 "reason": "canary", "sources": [], "status": "pending"})
    rows.append({"id": pid, "ts": ts[:-3] + "999", "status": "approved", "by": "student"})
    _wr_l(p, rows)
    return {"id": pid}


def inject_w8b(c) -> dict:
    ts = "2026-11-29T%02d:%02d:%02d" % (c.rng.randint(0, 23), c.rng.randint(0, 59), c.rng.randint(0, 59))
    append_chat(c, {"ts": ts, "role": "agent", "text": "The BOM has 9999 parts and is ready."})
    return {"ts": ts}


def inject_w9(src: pathlib.Path | None):
    """Factory: `src` is the original altium folder whose .advisor-backup holds the time-faithful SchDoc copies
    (writable copies drop that folder)."""
    def inject(c) -> dict:
        if src is not None and (src / ".advisor-backup").is_dir():
            for d in (src / ".advisor-backup").iterdir():
                for f in d.glob("*.SchDoc"):
                    (c.altium / ".advisor-backup" / d.name).mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, c.altium / ".advisor-backup" / d.name / f.name)
        line = "ZV" + _tag(c, 2)
        pid = "pZV" + _tag(c)
        ts = "2026-11-29T%02d:%02d:%02d" % (c.rng.randint(0, 23), c.rng.randint(0, 59), c.rng.randint(0, 59))
        p = c.project / "proposals.jsonl"
        rows = _rd_l(p)
        rows.append({"id": pid, "ts": ts + ".100", "kind": "bom", "line": line, "changes": {"mpn": "ZV123"}, "before": {},
                     "status": "pending"})
        rows.append({"id": pid, "ts": ts + ".500", "status": "approved", "by": "student"})
        _wr_l(p, rows)
        append_chat(c, {"ts": ts, "role": "agent", "decision": "approved", "proposal": pid,
                        "text": f"Approved. {line} is now placed on the schematic."})
        return {"line": line}
    return inject


def inject_w10(c) -> dict:
    p = c.project / "bom-log.jsonl"
    rows = _rd_l(p)
    ref = "RZ" + str(c.rng.randint(10, 99))
    for k in ("a", "b"):
        rows.append({"ts": _late(c), "by": "agent-approved", "line": "ZD" + k + ref,
                     "changes": {"value": "1k", "refs": [ref]}, "before": {}, "reason": "canary", "sources": []})
    rows.sort(key=lambda r: r["ts"] if "." in r["ts"] else r["ts"] + ".000")
    _wr_l(p, rows)
    return {"ref": ref}


def inject_w12(c) -> dict:
    srcs = sorted(x.name[:-4] for x in (c.project / "sources").glob("*.txt"))
    ds = c.rng.choice(srcs)
    line = "ZL" + _tag(c, 2)
    p = c.project / "bom-log.jsonl"
    rows = _rd_l(p)
    rows.append({"ts": _late(c), "by": "agent-approved", "line": line,
                 "changes": {"mpn": "QQA" + str(c.rng.randint(100, 999)), "datasheet": ds, "refs": [line]}, "before": {}, "reason": "canary"})
    t2 = "2026-11-30T%02d:00:00.000" % c.rng.randint(0, 23)
    rows.append({"ts": t2, "by": "agent-approved", "line": line,
                 "changes": {"mpn": "QQB" + str(c.rng.randint(100, 999)), "lcsc": "C1"}, "before": {}, "reason": "canary"})
    _wr_l(p, rows)
    return {"line": line}


def inject_w14(c) -> dict:
    d, lines = _bom_lines(c)
    key = "D" + str(c.rng.randint(50, 99))
    lines.append({"key": key, "refs": [key], "value": "LED", "role": "status LED", "pins_status": "unverified"})
    _wr(c.project / "bom.json", d)
    return {"key": key}


def inject_w16(c) -> dict:
    cands = []
    for p in sorted((c.project / "sources").glob("*.txt")):
        if p.name.endswith(".quality.txt"):
            continue
        q = p.with_name(p.name[:-4] + ".quality.txt")
        n = len(p.read_text(encoding="utf-8", errors="replace").split(""))
        if q.is_file():                       # only sources whose page numbering is decidable (chunks == pages)
            try:
                if json.loads(q.read_text(encoding="utf-8")).get("pages") != n:
                    continue
            except ValueError:
                continue
        cands.append(p)
    p = c.rng.choice(cands)
    name = p.name[:-4]
    ts = "2026-11-29T%02d:%02d:%02d" % (c.rng.randint(0, 23), c.rng.randint(0, 59), c.rng.randint(0, 59))
    quote = "zzq" + _tag(c, 6).lower() + " is not in this document"
    append_chat(c, {"ts": ts, "role": "agent", "text": "See {{src:%s|p. 1, %s}}." % (name, quote)})
    return {"tag": f"{ts[11:19]} {name} p. 1"}


def inject_w25b(c) -> dict:
    p = c.project / "idea-versions.json"
    vs = _rd(p)
    n0 = max(v["n"] for v in vs)
    a, b = "zza" + _tag(c).lower(), "zzb" + _tag(c).lower()
    t1, t2 = "2026-11-29T05:00:00.000", "2026-11-29T05:30:00.000"
    v1 = json.loads(json.dumps(vs[-1]))
    v1.update(n=n0 + 1, ts=t1)
    items = v1["idea"].setdefault("constraints", {"version": 1, "items": []}).setdefault("items", [])
    items += [{"id": a, "kind": a, "by": "student", "status": "confirmed"}, {"id": b, "kind": b, "by": "student", "status": "confirmed"}]
    v2 = json.loads(json.dumps(v1))
    v2.update(n=n0 + 2, ts=t2)
    v2["idea"]["constraints"]["items"] = [i for i in items if i["id"] not in (a, b)]
    _wr(p, vs + [v1, v2])
    append_chat(c, {"ts": "2026-11-29T05:15:00", "role": "user", "text": f"Please remove the {b} requirement."})
    return {"id": a, "twin": b}


def inject_w36(c) -> dict:
    mp = sorted((c.project / "exports").glob("*order_manifest.json"))[0]
    d = _rd(mp)
    rid = "ZR" + _tag(c, 3) + str(c.rng.randint(10, 99))
    d.setdefault("accepted_risks", []).append({"line": rid, "refs": [rid], "mpn": "X", "basis": "datasheet_page", "reason": "canary",
                                               "ts": "2026-11-29T00:00:00"})
    _wr(mp, d)
    return {"id": rid}


def inject_fjb(c) -> dict:
    d, lines = _bom_lines(c)
    ok = [l for l in lines if l.get("code") and l.get("lcsc") == l["code"]]
    l = c.rng.choice(ok)
    l["lcsc"] = ""
    _wr(c.project / "bom.json", d)
    return {"key": l["key"]}


def inject_u5(c) -> dict:
    mp = sorted((c.project / "exports").glob("*order_manifest.json"))[0]
    d = _rd(mp)
    rid = "ZU" + _tag(c, 3) + str(c.rng.randint(10, 99))
    d.setdefault("accepted_risks", []).append({"line": rid, "refs": [rid], "mpn": "X", "basis": "datasheet_page", "reason": "",
                                               "ts": "2026-11-29T00:00:00"})
    _wr(mp, d)
    return {"line": rid}
