"""
Self-awareness: what the advisor did, what it cost, which version it is, and whether its outputs still hold.

Every engine turn adds one line to projects/<p>/turns-log.jsonl. The server writes it; the agent only reads it:

    ts, session, kind (chat | memory), engine, model, seconds, ok, error, tokens in/out, cost_usd,
    the scripts the agent listed as run, actions applied / proposed / refused,
    and for a reply that gives engineering numbers, whether it also gives a source (a citation or a script run)

    python scripts/introspect.py <project> [summary | turns [N] | errors [N] | scripts | outputs | version]

The agent runs this when the student asks about the advisor itself ("what did you run", "what did this cost",
"which version are you", "are the outputs up to date") instead of guessing from the conversation.
"""
import collections
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import store       # noqa: E402
import workspace   # noqa: E402

LOG = "turns-log.jsonl"
UPDATE_STATUS = "update-status.json"     # the server's last update check, in the workspace

# A number with a unit, or a price: the claims rule 5 of AGENTS.md wants a source for.
NUMBER = re.compile(r"(?:\$\s?\d|\d(?:[.,]\d+)?\s?(?:mm|mil|oz|mA|A|mV|V|mW|W|k?Ω|ohm|kHz|MHz|GHz|[uµnp]F|[uµn]H|°C|%)"
                    r"(?![A-Za-z]))")


def _tokens(meta, key):
    v = (meta.get("usage") or {}).get(key)
    return v if isinstance(v, int) else None


def record(project, session, kind, res, seconds, reply="", applied=0, proposed=0, refused=0) -> dict:
    """One line per engine turn. `res` is what agent.respond / agent.compact got back from the gateway."""
    meta = res.get("usage") or {}
    tools = [t.get("t") for t in res.get("tools") or [] if isinstance(t, dict) and t.get("t")]
    rec = {"ts": store.now(), "session": session or "", "kind": kind, "engine": res.get("provider") or "",
           "model": res.get("model") or ", ".join(meta.get("models") or []), "seconds": round(seconds, 1),
           "ok": not res.get("error"),
           "tokens_in": sum(t for t in (_tokens(meta, "input_tokens"), _tokens(meta, "cache_read_input_tokens"),
                                        _tokens(meta, "cache_creation_input_tokens")) if t) or None,
           "tokens_out": _tokens(meta, "output_tokens"), "cost_usd": meta.get("cost_usd"),
           "engine_turns": meta.get("turns"), "tools": tools,
           "applied": applied, "proposed": proposed, "refused": refused}
    if res.get("error"):
        rec["error"] = str(res.get("reply") or res.get("error"))[:300]
    if kind == "chat" and reply:
        rec["numbers"] = bool(NUMBER.search(reply))
        rec["sourced"] = "{{src:" in reply or bool(tools)
    rec = {k: v for k, v in rec.items() if v is not None}
    try:
        store.append(project, LOG, rec)
    except OSError:
        pass                        # a full disk must not lose the answer the student is waiting for
    return rec


def turns(project) -> list:
    return store.read_jsonl(store.pdir(project) / LOG)


def update_status() -> dict:
    """The server's last check (written at its start), so the agent never fetches from GitHub itself."""
    try:
        return json.loads((workspace.home() / UPDATE_STATUS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def summary(project) -> dict:
    rows = turns(project)
    chat = [r for r in rows if r.get("kind") == "chat"]
    by_engine = collections.defaultdict(lambda: {"turns": 0, "seconds": 0.0, "cost_usd": 0.0, "costed": 0,
                                                 "tokens_in": 0, "tokens_out": 0})
    for r in rows:
        e = by_engine[r.get("engine") or "?"]
        e["turns"] += 1
        e["seconds"] += r.get("seconds") or 0
        e["tokens_in"] += r.get("tokens_in") or 0
        e["tokens_out"] += r.get("tokens_out") or 0
        if isinstance(r.get("cost_usd"), (int, float)):
            e["cost_usd"] += r["cost_usd"]
            e["costed"] += 1
    with_numbers = [r for r in chat if r.get("numbers")]
    scripts = collections.Counter(t for r in rows for t in r.get("tools") or [])
    errors = [r for r in rows if not r.get("ok", True)]
    out = {"project": project, "turns": len(rows), "chat_turns": len(chat), "memory_turns": len(rows) - len(chat),
           "first": rows[0]["ts"] if rows else None, "last": rows[-1]["ts"] if rows else None,
           "failed": len(errors), "last_error": errors[-1] if errors else None,
           "seconds": round(sum(e["seconds"] for e in by_engine.values()), 1),
           "cost_usd": round(sum(e["cost_usd"] for e in by_engine.values()), 4),
           "uncosted_turns": sum(e["turns"] - e["costed"] for e in by_engine.values()),
           "engines": {k: {**v, "seconds": round(v["seconds"], 1), "cost_usd": round(v["cost_usd"], 4)}
                       for k, v in by_engine.items()},
           "with_numbers": len(with_numbers), "sourced": sum(1 for r in with_numbers if r.get("sourced")),
           "applied": sum(r.get("applied") or 0 for r in rows), "refused": sum(r.get("refused") or 0 for r in rows),
           "scripts": dict(scripts.most_common())}
    out["sourced_pct"] = round(100 * out["sourced"] / out["with_numbers"]) if out["with_numbers"] else None
    return out


def outputs(project) -> dict:
    import lineage
    rows = lineage.status(project)
    counts = collections.Counter(r["status"] for r in rows)
    return {"counts": dict(counts), "problems": [r for r in rows if r["status"] != "fresh"]}


def version() -> dict:
    import update
    return {**update.version(), "update": update_status()}


# ---------------------------------------------------------------- CLI

def _money(x):
    return f"${x:.2f}" if x >= 0.01 or x == 0 else f"${x:.4f}"


def _print_version():
    v = version()
    u = v["update"]
    line = f"pcb-advisor {v['commit'] or '(not a git install)'}" + (f" ({v['date'][:10]}, {v['branch']})" if v["commit"] else "")
    if u.get("behind"):
        line += f"; {u['behind']} newer change(s) on GitHub (checked {str(u.get('checked', ''))[:16]})"
        line += "; the Update button in the tool applies them" if u.get("can_update") else f"; {u.get('reason', '')}"
    elif u:
        line += f"; up to date at the last check ({str(u.get('checked', ''))[:16]})"
    print(line)


def _print_turn(r):
    mark = "ok " if r.get("ok", True) else "ERR"
    cost = f" {_money(r['cost_usd'])}" if isinstance(r.get("cost_usd"), (int, float)) else ""
    tok = f" {r.get('tokens_in', 0)}/{r.get('tokens_out', 0)} tok" if r.get("tokens_in") or r.get("tokens_out") else ""
    tools = f"  ran: {', '.join(r['tools'])}" if r.get("tools") else ""
    print(f"{mark} {r['ts'][:16]} {r.get('kind', ''):6} {r.get('engine', '')} {r.get('seconds', 0):5.1f}s{tok}{cost}{tools}")
    if r.get("error"):
        print(f"      {r['error'][:200]}")


def main(argv=None):
    import oscompat
    oscompat.utf8_stdio()
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        raise SystemExit("usage: introspect.py <project> [summary | turns [N] | errors [N] | scripts | outputs | version]")
    project = workspace.safe_name(args[0])
    cmd = args[1] if len(args) > 1 else "summary"
    n = int(args[2]) if len(args) > 2 and args[2].isdigit() else 10

    if cmd == "version":
        _print_version()
    elif cmd in ("turns", "errors"):
        rows = [r for r in turns(project) if cmd == "turns" or not r.get("ok", True)]
        for r in rows[-n:]:
            _print_turn(r)
        if not rows:
            print("none")
    elif cmd == "scripts":
        s = summary(project)["scripts"]
        for name, count in s.items():
            print(f"{count:4}  {name}")
        if not s:
            print("no script runs recorded")
    elif cmd == "outputs":
        o = outputs(project)
        print(", ".join(f"{v} {k}" for k, v in sorted(o["counts"].items())) or "no outputs yet")
        for r in o["problems"]:
            print(f"  {r['status']:7} {r['output']}: {'; '.join(r['reasons'])}")
    elif cmd == "summary":
        _print_version()
        s = summary(project)
        if not s["turns"]:
            print(f"project {project}: no engine turns recorded yet")
        else:
            print(f"project {project}: {s['turns']} engine turns ({s['chat_turns']} chat, {s['memory_turns']} memory) "
                  f"{s['first'][:10]} to {s['last'][:10]}, {s['failed']} failed")
            cost = _money(s["cost_usd"]) + (f" (+{s['uncosted_turns']} turns whose engine reports no cost)"
                                             if s["uncosted_turns"] else "")
            print(f"  engine time {s['seconds'] / 60:.1f} min, cost {cost}")
            for name, e in s["engines"].items():
                print(f"  {name}: {e['turns']} turns, {e['seconds'] / 60:.1f} min, "
                      f"{e['tokens_in']} tokens in / {e['tokens_out']} out")
            if s["with_numbers"]:
                print(f"  sourced: {s['sourced']} of {s['with_numbers']} replies with engineering numbers cite a source "
                      f"or a script run ({s['sourced_pct']}%)")
            if s["scripts"]:
                print("  scripts run: " + ", ".join(f"{k} {v}" for k, v in list(s["scripts"].items())[:8]))
            print(f"  actions: {s['applied']} applied, {s['refused']} refused")
            if s["last_error"]:
                print(f"  last error {s['last_error']['ts'][:16]}: {s['last_error'].get('error', '')[:160]}")
        o = outputs(project)
        if o["counts"]:
            print("outputs: " + ", ".join(f"{v} {k}" for k, v in sorted(o["counts"].items())))
            for r in o["problems"]:
                print(f"  {r['status']:7} {r['output']}: {'; '.join(r['reasons'])}")
    else:
        raise SystemExit(f"unknown command {cmd}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
