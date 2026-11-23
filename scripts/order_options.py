"""
The order's own choices, one place: how many boards (N) and whether JLC also assembles them (PCBA).

N used to be a config constant (`jlc.build_qty`) that only the stock check read, and PCBA was nowhere: the BOM and the
pick and place file (CPL) were made or not made by whoever clicked what. Now the project says it (project.json "order"):

    boards      how many boards the order is for (the stock check needs boards x parts per board)
    assembly    true: JLC places the parts, so the outputs must hold the BOM and the CPL; false: bare boards only

    python scripts/order_options.py <project> [--boards N] [--assembly yes|no]
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import project as project_mod  # noqa: E402
import workspace  # noqa: E402

MAX_BOARDS = 100000


def get(project: str) -> dict:
    """{boards, assembly, set}: the project's choice, else the config default (jlc.build_qty, 5) and bare boards.
    `set` is False while the student has not said (the defaults are then shown as defaults)."""
    saved = project_mod.load_meta(project).get("order")
    saved = saved if isinstance(saved, dict) else {}
    try:
        default = max(1, int(workspace.get("jlc.build_qty", 5)))
    except (TypeError, ValueError):
        default = 5
    try:
        boards = int(saved["boards"])
        boards = boards if 1 <= boards <= MAX_BOARDS else default
    except (KeyError, TypeError, ValueError):
        boards = default
    return {"boards": boards, "assembly": bool(saved.get("assembly", False)), "set": bool(saved)}


def boards(project: str) -> int:
    return get(project)["boards"]


def set_options(project: str, boards=None, assembly=None) -> dict:
    """Save what is given; raises ValueError for a count that is not a whole number from 1 up."""
    cur = project_mod.load_meta(project).get("order")
    cur = dict(cur) if isinstance(cur, dict) else {}
    if boards is not None:
        if isinstance(boards, bool) or not str(boards).strip().lstrip("-").isdigit():
            raise ValueError("the number of boards must be a whole number")
        n = int(str(boards).strip())
        if not 1 <= n <= MAX_BOARDS:
            raise ValueError(f"the number of boards must be from 1 to {MAX_BOARDS}")
        cur["boards"] = n
    if assembly is not None:
        cur["assembly"] = bool(assembly)
    meta = project_mod.load_meta(project)
    meta["order"] = cur
    project_mod.save_meta(project, meta)
    return get(project)


def main(argv=None):
    ap = argparse.ArgumentParser(description="the order's number of boards and assembly choice")
    ap.add_argument("project")
    ap.add_argument("--boards", type=int, default=None)
    ap.add_argument("--assembly", choices=["yes", "no"], default=None)
    a = ap.parse_args(argv)
    res = set_options(a.project, a.boards, None if a.assembly is None else a.assembly == "yes") \
        if a.boards is not None or a.assembly else get(a.project)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
