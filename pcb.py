#!/usr/bin/env python3
"""
pcb-advisor — one entry point for the whole workspace.

    python3 pcb.py init                 create the folders and config.json
    python3 pcb.py serve                start the server, open the browser (also: run)
    python3 pcb.py new "usb sensor"     start a project from the template
    python3 pcb.py list                 what is in the workspace
    python3 pcb.py show [project]       where the design stands
    python3 pcb.py seed                 the worked example: projects/lte-tracker
    python3 pcb.py engines              which LLM engines are wired up
    python3 pcb.py tools [--clear]      what the engine may touch on your machine
    python3 pcb.py probe [--engine X]   prove the engine loads the runtime pack (claude_code|antigravity|all)
    python3 pcb.py bench [--engine X] [--evals] [--only 1,5]  real-incident replay -> docs/BENCHMARK.md
    python3 pcb.py skills lint [--only NAME]  check runtime/skills against the skill format
    python3 pcb.py chats [project]    conversations, and when memory was rewritten
    python3 pcb.py config [key] [value] read or set a setting
    python3 pcb.py check [project]      every sheet validates, every citation resolves
    python3 pcb.py reset [project]      wipe a project's state
    python3 pcb.py trace 1.5            IPC-2221 trace width
    python3 pcb.py rules preset|export|diff   JLC rules preset, .RUL export, board vs rules diff
    python3 pcb.py calc trace-width|divider|led|via|microstrip   engineering calculators
    python3 pcb.py library search|check-package|build-script     parts library tools

Everything is local files. Nothing here talks to a server you do not run.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts"))

import gateway     # noqa: E402
import oscompat    # noqa: E402
import project     # noqa: E402
import workspace   # noqa: E402


def cmd_init(args):
    report = workspace.init(force="--force" in args)
    default = workspace.default_project()
    if not project.exists(default):
        project.create(default, title=default)
        report["created"].append(f"projects/{default}")
    print(f"workspace  {report['home']}")
    print(f"config     {report['config']}")
    for made in report["created"]:
        print(f"  created  {made}")
    if not report["created"]:
        print("  already set up — nothing to do")
    print(oscompat.py("\nnext: python3 pcb.py serve"))


def cmd_serve(args):
    import serve
    serve.main(args)


def cmd_new(args):
    if not args:
        raise SystemExit('usage: pcb.py new "project name"')
    name = args[0]
    created = project.create(name, title=name)
    print(f"created projects/{created}")
    print(oscompat.py(f"open:   python3 pcb.py serve --project {created}"))


def cmd_list(args):
    rows = project.list_all()
    if not rows:
        print(oscompat.py("no projects yet — python3 pcb.py new \"my board\"  (or: python3 pcb.py seed)"))
        return
    for p in rows:
        mark = "✓" if p["confirmed"] else "·"
        print(f"{mark} {p['name']:24} {p['lines']:>3} BOM lines  {p['sheets']} sheets  "
              f"{p['updated'][:16]:16}  {p['brief'][:44]}")


def cmd_show(args):
    import model
    m = model.write(args[0] if args else None)
    t = m["totals"]
    print(f"{m['project']}: idea {'confirmed' if m['idea']['confirmed'] else 'open'} · "
          f"{t['lines']} BOM lines · {len(m['sheets'])} sheets")
    print(f"  {t['parts']} parts to place · ${t['cost']:.2f} parts/board · "
          f"{t['out_of_stock']} out of stock · {t['checking']} checking · {t['to_verify']} to verify")
    for p in m["proposals"]:
        if p["status"] == "pending":
            print(f"  PENDING  {p['id']}  {p['line']}: {', '.join(p['changes'])}  ({p['reason'][:60]})")
    for r in m["requirements"]:
        print(f"  {'✓' if r['ok'] else '·' if r['ok'] is None else '✗'} {r['text']} {r['detail']}")


def cmd_seed(args):
    import seed
    res = seed.seed(force="--force" in args)
    print(("created" if res["created"] else "already there:"), f"projects/{res['project']}")
    print(oscompat.py(f"open:   python3 pcb.py serve --project {res['project']}"))


def cmd_engines(args):
    for d in gateway.describe_all():
        mark = "*" if d["active"] else " "
        state = "ready" if d["available"] else d["reason"]
        hands = "in the workspace" if d.get("workspace") else "text only"
        print(f"{mark} {d['id']:14} {d['status']:12} {state}")
        print(f"{'':17}{hands}" + (f" · tools: {d['tools']}" if d.get("tools") else ""))
    print(oscompat.py("\n* = active. Change with: python3 pcb.py config agent.provider <id>"))


# THIS SHIPS AS THE DEFAULT, in config/defaults.json. Read the workspace and run
# the scripts; never edit a file directly. It has to be the default: without an
# allow-list the CLI asks for approval, and print mode has nobody to approve, so
# the scripts never run and the engine reports that it could not compute.
RECOMMENDED_TOOLS = {
    "allowed": [
        "Read", "Skill", "Grep", "Glob",
        "Bash({python} {repo}/scripts/trace_width.py *)",
        "Bash({python} {repo}/scripts/sources.py *)",
        "Bash({python} {repo}/scripts/model.py *)",
        "Bash({python} {repo}/scripts/skills/*.py *)",
    ],
    "disallowed": ["Write", "Edit", "NotebookEdit"],
}


def cmd_tools(args):
    """What the engine may touch. The working policy is the shipped default;
    --clear hands control back to the CLI's own settings, --apply restores it."""
    if "--clear" in args:
        for key in ("available", "allowed", "disallowed", "permission_mode"):
            workspace.set_value(f"agent.providers.claude_code.tools.{key}", None)
        print("cleared - the CLI's own settings decide now.")
        print("The engine will ask for approval before running scripts/trace_width.py,")
        print("and print mode has nobody to approve, so it will report that it could")
        print(oscompat.py("not compute. Restore with: python3 pcb.py tools --apply"))
        return
    if "--apply" in args:
        for key, value in RECOMMENDED_TOOLS.items():
            workspace.set_value(f"agent.providers.claude_code.tools.{key}", value)
        print(f"restored the default policy in {workspace.config_path()}")

    current = workspace.get("agent.providers.claude_code.tools") or {}
    set_keys = {k: v for k, v in current.items() if v is not None}
    print("claude_code may touch:")
    if set_keys:
        for key, value in set_keys.items():
            print(oscompat.py(f"  {key:16} {json.dumps(value, ensure_ascii=False)}"))
        if set_keys == RECOMMENDED_TOOLS:
            print("\n  (the shipped default: read and compute, never write)")
    else:
        print("  nothing set - the CLI's own settings decide, and the scripts")
        print(oscompat.py("  will not run. python3 pcb.py tools --apply restores the default."))


def cmd_probe(args):
    """Sync the runtime pack, then ask each engine for two codes that exist only in
    the pack (one in a skill file, one in AGENTS.md). PASS = it loaded both."""
    import runtime_pack
    want = args[args.index("--engine") + 1] if "--engine" in args and args.index("--engine") + 1 < len(args) else "all"
    engines = ["claude_code", "antigravity"] if want == "all" else [want]
    try:
        print(f"engine home  {runtime_pack.sync()}")
    except runtime_pack.RuntimePackError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    failed = 0
    for eng in engines:
        try:
            ok, secs, detail = runtime_pack.probe(eng)
        except KeyError as exc:
            print(f"  {eng:12} FAIL  {exc}")
            failed += 1
            continue
        if ok is None:
            print(f"  {eng:12} SKIP  {detail}")
            continue
        print(f"  {eng:12} {'PASS' if ok else 'FAIL'}  {secs:5.1f}s  {detail}")
        failed += 0 if ok else 1
    return 1 if failed else 0


def cmd_bench(args):
    from bench import runner

    def opt(name):
        i = args.index(name) + 1 if name in args else 0
        return args[i] if 0 < i < len(args) else None
    only = [int(x) for x in opt("--only").split(",")] if opt("--only") else None
    res = runner.run(engine=opt("--engine"), evals="--evals" in args, only=only)
    print(res["text"])
    for p in res["problems"]:
        print(f"  problem: {p}", file=sys.stderr)
    print(f"written {res['path']}")


def cmd_chats(args):
    import session
    proj = args[0] if args else workspace.default_project()
    rows = session.list_all(proj)
    if not rows:
        print("no conversations yet")
        return
    for r in rows:
        due, since = session.due_for_compaction(proj, r["id"])
        mem = len(session.read_memory(proj, r["id"]))
        state = "memory due" if due else f"{since} since rewrite"
        print(f"{r['id']:18} {r['messages']:>4} msgs  {state:18} "
              f"memory {mem:>4}c  {r['title']}")


def cmd_config(args):
    if not args:
        print(json.dumps(workspace.load(), ensure_ascii=False, indent=2))
        for k in workspace.unknown_keys():
            print(f"  warning: unknown config key {k}", file=sys.stderr)
        return
    key = args[0]
    if len(args) == 1:
        print(json.dumps(workspace.get(key), ensure_ascii=False, indent=2))
        return
    raw = args[1]
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = raw
    workspace.set_value(key, value)
    print(f"{key} = {json.dumps(value, ensure_ascii=False)}  ->  {workspace.config_path()}")


def cmd_check(args):
    """Every sheet validates against the BOM, every citation resolves to a source."""
    import model
    import store
    import verify_sources
    projects = args or [p["name"] for p in project.list_all()]
    bad = 0
    refs = None
    for name in projects:
        refs = {r for l in store.bom_lines(name) for r in l.get("refs", [])}
        for sid in store.sheet_ids(name):
            errors = store.validate_sheet(store.load_sheet(name, sid), refs)
            for e in errors:
                print(f"  FAIL  {name}/{sid}: {e}")
            bad += len(errors)
        print(f"  ok    {name}: {len(store.sheet_ids(name))} sheet(s) checked")
    return 1 if (bad or verify_sources.main(projects)) else 0


def cmd_reset(args):
    print(f"reset {project.reset(args[0] if args else workspace.default_project())}")


def cmd_trace(args):
    import trace_width
    if not args:
        raise SystemExit("usage: pcb.py trace <amps> [--project NAME] "
                         "[--layer external] [--oz 1] [--rise 10]")
    opts = dict(zip(args[1::2], args[2::2]))
    # unstated options come from the board you are actually designing
    board = project.board(opts.get("--project", workspace.default_project()))
    w = trace_width.width_mm(
        float(args[0]),
        opts.get("--layer", board.get("trace_layer", "external")),
        float(opts.get("--rise", board.get("max_temp_rise_c", 10))),
        float(opts.get("--oz", board.get("copper_oz", 1.0))))
    print(f"{w:.3f} mm ({w / 0.0254:.1f} mil)   source: IPC-2221 section 6.2")


def cmd_skills(args):
    if not args or args[0] != "lint":
        raise SystemExit("usage: pcb.py skills lint [--only NAME]")
    from skills import lint
    return lint.main(args[1:])


def cmd_rules(args):
    import rules
    return rules.main(args)


def cmd_calc(args):
    import calc
    return calc.main(args)


def cmd_library(args):
    import library
    return library.main(args)


COMMANDS = {
    "init": cmd_init, "serve": cmd_serve, "run": cmd_serve, "new": cmd_new, "list": cmd_list,
    "show": cmd_show, "seed": cmd_seed, "engines": cmd_engines, "tools": cmd_tools,
    "chats": cmd_chats, "probe": cmd_probe, "bench": cmd_bench,
    "config": cmd_config,
    "skills": cmd_skills, "check": cmd_check, "reset": cmd_reset, "trace": cmd_trace,
    "rules": cmd_rules, "calc": cmd_calc, "library": cmd_library,
}


def main():
    oscompat.utf8_stdio()
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    cmd = COMMANDS.get(args[0])
    if cmd is None:
        print(f"unknown command '{args[0]}'. Try: {', '.join(COMMANDS)}", file=sys.stderr)
        return 2
    return cmd(args[1:]) or 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        # piping into `head` closes the pipe early; that is not an error
        sys.stderr.close()
        raise SystemExit(0)
