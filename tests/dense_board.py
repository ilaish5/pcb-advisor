"""A dense real 4 layer board as it was placed, without any routed copper (pad geometry, nets and rules only), for the router tests.
It is one project's data, so it is not part of the repository: it is read from local/ (ignored by git) of this checkout or of a
checkout above it (a worktree), and the tests that need it are skipped where it is not there. load() gives (doc, box, rules) for
route.plan_routes as bridge.route_on builds them."""
import json
import pathlib

import pytest

NAME = pathlib.Path("local") / "router_dense_board.json"


def load():
    found = next((p / NAME for p in pathlib.Path(__file__).resolve().parents if (p / NAME).is_file()), None)
    if found is None:
        pytest.skip(f"the private dense board ({NAME.as_posix()}) is not on this machine")
    data = json.loads(found.read_text(encoding="utf-8"))
    box, rules = data.pop("box"), data.pop("rules")
    rules.update(net_current=data.pop("currents"), net_estimate=data.pop("estimates"), allow_narrow=True, keepout_rects=data.pop("keepouts"),
                 **data.pop("copper"))
    return data, box, rules
