"""The Live-STM32 test board as layout.py placed it in Altium (synthetic, no student data), frozen by scripts/freeze_live_board.py.
load() gives (doc, box, rules) for route.plan_routes exactly as bridge.route_on builds them (replace=True: in-footprint copper only)."""
import json
import pathlib

_DIR = pathlib.Path(__file__).parent / "fixtures"


def load(name="live_stm32_placed"):
    """name: the fixture file (without .json): live_stm32_placed (first placement) or live_stm32_rebuilt (after the library rebuild)."""
    data = json.loads((_DIR / f"{name}.json").read_text(encoding="utf-8"))
    box = data.pop("box")
    rules = data.pop("rules")
    rules.update(net_current={}, net_estimate={}, allow_narrow=False)
    return data, box, rules
