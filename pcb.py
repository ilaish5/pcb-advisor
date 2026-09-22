#!/usr/bin/env python3
"""
pcb-advisor — one entry point for the whole workspace.

    python3 pcb.py init                 create the folders and config.json
    python3 pcb.py serve                start the server, open the browser
    python3 pcb.py new "usb sensor"     start a project from the template
    python3 pcb.py list                 what is in the workspace
    python3 pcb.py show [project]       where the design stands
    python3 pcb.py engines              which LLM engines are wired up
    python3 pcb.py config [key] [value] read or set a setting
    python3 pcb.py check                validate the corpus and the citations
    python3 pcb.py reset [project]      wipe a project's state
    python3 pcb.py trace 1.5            IPC-2221 trace width

Everything is local files. Nothing here talks to a server you do not run.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts"))

import gateway     # noqa: E402
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
    print("\nnext: python3 pcb.py serve")


def cmd_serve(args):
    import serve
    serve.main(args)


def cmd_new(args):
    if not args:
        raise SystemExit('usage: pcb.py new "project name"')
    name = args[0]
    created = project.create(name, title=name)
    print(f"created projects/{created}")
    print(f"open:   python3 pcb.py serve --project {created}")


def cmd_list(args):
    rows = project.list_all()
    if not rows:
        print("no projects yet — python3 pcb.py new \"my board\"")
        return
    for p in rows:
        mark = "✓" if p["confirmed"] else "·"
        print(f"{mark} {p['name']:24} {p['decisions']:>3} decisions  "
              f"{p['updated'][:16]:16}  {p['brief'][:44]}")


def cmd_show(args):
    import model
    m = model.write(args[0] if args else None)
    pr = m["progress"]
    print(f"{m['project']}: stage={m['stage']} domains={m['domains'] or '-'}")
    print(f"  {pr['answered']}/{pr['total']} answered · {pr['constraints']} constraints "
          f"({pr['unverified']} unverified) · {pr['conflicts']} conflicts")
    for n in m["open"]:
        print(f"  OPEN   {n['id']}  {n['question']}")
    for n in m["blocked"]:
        print(f"  next   {n['id']}  ({n['reason']})")


def cmd_engines(args):
    for d in gateway.describe_all():
        mark = "*" if d["active"] else " "
        state = "ready" if d["available"] else d["reason"]
        print(f"{mark} {d['id']:14} {d['status']:12} {state}")
        if d.get("tools"):
            print(f"{'':17}tools: {d['tools']}")
    print("\n* = active. Change with: python3 pcb.py config agent.provider <id>")


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
    import validate_cascade
    import verify_sources
    bad = validate_cascade.main()
    try:
        failed = verify_sources.main()
    except SystemExit as exc:
        failed = exc.code
    return 1 if (bad or failed) else 0


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


COMMANDS = {
    "init": cmd_init, "serve": cmd_serve, "new": cmd_new, "list": cmd_list,
    "show": cmd_show, "engines": cmd_engines, "config": cmd_config,
    "check": cmd_check, "reset": cmd_reset, "trace": cmd_trace,
}


def main():
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
    raise SystemExit(main())
