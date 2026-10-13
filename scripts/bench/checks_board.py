"""Board / manufacturer benchmark detectors (connector faces inward, outline in every Gerber,
CPL rotation vs JLC models). They read only the fixture's state files and call scripts/checks."""
import json

import outjob
from bench.detectors import register
from checks import board


def _read(fixture_dir, name):
    p = fixture_dir / name
    return p.read_text(encoding="utf-8") if p.exists() else None


def _wrap(findings, source):
    return [{"code": f["id"], "refs": f["refs"], "message": f["message"], "source": source} for f in findings]


@register("connector_faces_inward")
def connector_faces_inward(fixture_dir, incident):
    placement, spec_text = _read(fixture_dir, "placement.csv"), _read(fixture_dir, "connectors.json")
    if placement is None or spec_text is None:
        return []
    spec = json.loads(spec_text)
    outline = (spec.get("board") or {}).get("outline_mm")
    if not outline:
        return []
    specs = {c["ref"]: c for c in spec.get("connectors", []) if "ref" in c}
    return _wrap(board.check_connectors_from_placement(board.parse_placement_csv(placement), outline, specs),
                 "checks.board.check_connectors_from_placement")


@register("outline_in_all_gerber_layers")
def outline_in_all_gerber_layers(fixture_dir, incident):
    cfg = _read(fixture_dir, "outjob_gerber_config.txt")
    if cfg is None:
        return []
    layers = _read(fixture_dir, "gerber_layers.json")
    bad = []
    if layers:
        bad = [f["file"] for f in json.loads(layers).get("files", [])
               if f.get("contains_outline_line") and not f.get("expected_outline")]
    return _wrap(outjob.check_gerber_plot_config(cfg, bad), "outjob.check_gerber_plot_config")


@register("cpl_rotation_mismatch")
def cpl_rotation_mismatch(fixture_dir, incident):
    cpl, rot = _read(fixture_dir, "cpl.csv"), _read(fixture_dir, "jlc_model_rotation.json")
    if cpl is None or rot is None:
        return []
    offsets = {p["ref"]: p["jlc_model_offset_vs_our_footprint_deg"] for p in json.loads(rot).get("parts", [])}
    return _wrap(board.check_cpl_vs_model_rotation(board.parse_placement_csv(cpl), offsets),
                 "checks.board.check_cpl_vs_model_rotation")
