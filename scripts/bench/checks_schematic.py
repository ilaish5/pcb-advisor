"""Benchmark detectors for schematic-review incidents 6, 7, 9.

They read only the fixture's state files and call the shared rules in
scripts/checks/schematic.py. The emitted code is the incident family label.
"""
import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from bench.detectors import register  # noqa: E402
from checks import schematic as sch  # noqa: E402


def _load(d):
    d = pathlib.Path(d)
    need = [d / "netlist.json", d / "parts.csv", d / "datasheet_facts.json"]
    if not all(p.is_file() for p in need):
        return None
    netlist = json.loads(need[0].read_text(encoding="utf-8")).get("nets", {})
    with need[1].open(encoding="utf-8", newline="") as fh:
        parts = {r["ref"]: r for r in csv.DictReader(fh)}
    facts = json.loads(need[2].read_text(encoding="utf-8"))
    return netlist, parts, facts


def _wrap(code, found):
    return [{"code": code, "refs": f["refs"], "message": f["message"], "source": f["source"]}
            for f in found]


@register("vcc_cap_over_max")
def pin_cap_over_max(fixture_dir, incident):
    st = _load(fixture_dir)
    return _wrap("vcc_cap_over_max", sch.check_pin_capacitance_max(*st)) if st else []


@register("fault_output_type_unverified")
def output_type_unverified(fixture_dir, incident):
    st = _load(fixture_dir)
    return _wrap("fault_output_type_unverified", sch.check_output_type_unverified(*st)) if st else []


@register("f411_swap_vcap_missing")
def swap_requirements(fixture_dir, incident):
    st = _load(fixture_dir)
    swap = pathlib.Path(fixture_dir) / "swap_request.md"
    if not st or not swap.is_file():
        return []
    return _wrap("f411_swap_vcap_missing",
                 sch.check_swap_requirements(*st, swap.read_text(encoding="utf-8")))
