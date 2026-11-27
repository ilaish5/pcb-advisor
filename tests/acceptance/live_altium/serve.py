"""Start (or stop) the pre-fix product server of the Altium-judged metrics, in the background.

    python -I tests/acceptance/live_altium/serve.py start [--tree pre|b1b] [--tag a] [--port 8941] [--fresh]
    python -I tests/acceptance/live_altium/serve.py stop  [--port 8941]

`--fresh` rebuilds the home and the scratch Altium copy from the frozen fixture first (needs ACCEPTANCE_FIXTURE).
Prints the URL and the project name for `run.py --live <url> --live-project <name>`.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from live_altium import env  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["start", "stop"])
    ap.add_argument("--tree", default="pre", choices=list(env.TREES))
    ap.add_argument("--tag", default="a")
    ap.add_argument("--port", type=int, default=env.PORT_DEFAULT)
    ap.add_argument("--fresh", action="store_true")
    a = ap.parse_args(argv)
    srv = env.Server(a.tree, a.tag, a.port)
    if a.what == "stop":
        srv.stop()
        print("stopped")
        return 0
    if a.fresh or not srv.home.exists():
        env.make_home(a.tag, port=a.port)
    srv.start()
    print(f"server up: {srv.url}   project: {env.NAME}   tree: {env.TREES[a.tree]}   home: {srv.home}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
