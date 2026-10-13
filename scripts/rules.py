"""Altium .RUL design rules writer, JLC preset rules, and PcbDoc diff tool."""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent

from altium import parse_rul_bytes, read_pcbdoc, read_rul  # noqa: E402


def format_rul_bytes(rules: list[dict[str, str]]) -> bytes:
    """Serialize a list of rule dicts to Altium .RUL byte format.

    Inverse of scripts/altium/rul.py: records separated by pipe-delimited
    key-value pairs, latin-1 encoding, with line ends \\xb6\\r\\n.
    """
    lines = []
    for r in rules:
        parts = [f"{k}={v}" for k, v in r.items()]
        line_str = "|" + "|".join(parts) + "|\xb6\r\n"
        lines.append(line_str.encode("latin-1"))
    return b"".join(lines)


def write_rul(rules: list[dict[str, str]], path) -> pathlib.Path:
    """Write rule dicts to an Altium .RUL export file."""
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(format_rul_bytes(rules))
    return p


def get_jlc_preset() -> dict:
    """Load the JLC preset rules from config/defaults.json."""
    cfg_path = REPO / "config" / "defaults.json"
    if not cfg_path.is_file():
        return {"rules": [], "capabilities_url": "https://jlcpcb.com/capabilities/pcb-capabilities"}
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        return data.get("jlc_rules", {})
    except Exception:
        return {"rules": [], "capabilities_url": "https://jlcpcb.com/capabilities/pcb-capabilities"}


def get_preset_rule_records() -> list[dict[str, str]]:
    """Return raw Altium record dicts for all rules in the JLC preset."""
    preset = get_jlc_preset()
    records = []
    for r in preset.get("rules", []):
        attrs = r.get("attributes")
        if attrs:
            records.append(attrs)
    return records


def rule_display_value(rule: dict[str, str]) -> str:
    """Extract a concise human-readable value representation for a rule."""
    kind = rule.get("RULEKIND", "")
    if kind == "Clearance":
        return rule.get("GAP") or rule.get("GENERICCLEARANCE", "")
    elif kind == "Width":
        min_w = rule.get("MINLIMIT", "")
        pref_w = rule.get("PREFEREDWIDTH", "")
        max_w = rule.get("MAXLIMIT", "")
        return f"Min: {min_w}, Pref: {pref_w}, Max: {max_w}"
    elif kind == "RoutingVias":
        hole = rule.get("HOLEWIDTH", rule.get("MINHOLEWIDTH", ""))
        dia = rule.get("WIDTH", rule.get("MINWIDTH", ""))
        return f"Hole: {hole}, Dia: {dia}"
    elif kind == "MinimumAnnularRing":
        return rule.get("MINIMUMRING", rule.get("MINIMUM", ""))
    elif kind == "HoleSize":
        min_h = rule.get("MINLIMIT", "")
        max_h = rule.get("MAXLIMIT", "")
        return f"Min: {min_h}, Max: {max_h}"
    elif kind == "SilkToSolderMaskClearance":
        return rule.get("MINSILKSCREENTOMASKGAP", "")
    elif kind == "SilkToSilkClearance":
        return rule.get("SILKTOSILKCLEARANCE", "")
    elif kind == "SolderMaskExpansion":
        return rule.get("EXPANSION", "")
    elif kind == "MinimumSolderMaskSliver":
        return rule.get("MINSOLDERMASKWIDTH", "")
    elif kind == "HoleToHoleClearance":
        return rule.get("GAP", "")
    elif kind == "ComponentClearance":
        return rule.get("GAP", "")
    elif kind == "PlaneClearance":
        return rule.get("CLEARANCE", "")
    else:
        # Generic fallback
        for key in ("GAP", "CLEARANCE", "WIDTH", "EXPANSION", "MINIMUMRING"):
            if key in rule:
                return rule[key]
        return "—"


def _normalize_val(val: str) -> str:
    """Normalize whitespace and case for value comparison."""
    if not val:
        return ""
    return "".join(val.lower().split())


def _prio(r: dict) -> int:
    try:
        return int(r.get("PRIORITY", "9999"))
    except ValueError:
        return 9999


def _scope_all(r: dict) -> bool:
    return (r.get("SCOPE1EXPRESSION", "All").strip().lower() in ("all", "")
            and r.get("SCOPE2EXPRESSION", "All").strip().lower() in ("all", ""))


def _effective_index(rules, kind, skip=()):
    """Index of the highest-priority enabled scope-All rule of a kind, or None."""
    best = None
    for i, r in enumerate(rules):
        if i in skip or r.get("RULEKIND") != kind or not _scope_all(r):
            continue
        if r.get("ENABLED", "TRUE").upper() == "FALSE":
            continue
        if best is None or _prio(r) < _prio(rules[best]):
            best = i
    return best


_CONTROL_KEYS = {"NAME", "RULEKIND", "SCOPE1EXPRESSION", "SCOPE2EXPRESSION", "ENABLED", "PRIORITY"}


def _uid(name: str) -> str:
    import hashlib
    h = hashlib.sha1(name.encode("utf-8")).digest()
    return "".join(chr(65 + b % 26) for b in h[:8])


def board_rul_records(pcbdoc_path, preset=None) -> list[dict[str, str]]:
    """Full rule set for Altium "Replace existing rules": the board's rules
    unchanged, except that per preset kind the effective scope-All rule gets
    the JLC values (NAME, UNIQUEID, PRIORITY and other keys kept). Preset
    kinds with no scope-All rule are appended at the lowest priority of that
    kind (so scoped board rules keep winning inside their scope)."""
    if preset is None:
        preset = get_preset_rule_records()
    board = [dict(r) for r in read_pcbdoc(pcbdoc_path).get("rules", [])]
    names = {r.get("NAME") for r in board}
    for pr in preset:
        kind = pr.get("RULEKIND")
        values = {k: v for k, v in pr.items() if k not in _CONTROL_KEYS}
        idx = _effective_index(board, kind)
        if idx is not None:
            board[idx].update(values)
            continue
        same = [r for r in board if r.get("RULEKIND") == kind]
        name = pr.get("NAME", kind)
        while name in names:
            name += "_JLC"
        names.add(name)
        rec = {
            "LAYER": "TOP", "LOCKED": "FALSE", "POLYGONOUTLINE": "FALSE",
            "USERROUTED": "TRUE", "KEEPOUT": "FALSE", "UNIONINDEX": "0",
            "RULEKIND": kind,
            "NETSCOPE": "DifferentNets" if kind == "Clearance" else "AnyNet",
            "LAYERKIND": "SameLayer",
            "SCOPE1EXPRESSION": "All", "SCOPE2EXPRESSION": "All",
            "NAME": name, "ENABLED": "TRUE",
            "PRIORITY": str(max((_prio(r) for r in same), default=0) + 1),
            "COMMENT": "JLC preset", "UNIQUEID": _uid(name),
            "DEFINEDBYLOGICALDOCUMENT": "FALSE",
        }
        rec.update(values)
        board.append(rec)
    return board


def diff_rules(board_rules: list[dict[str, str]], preset_rules: list[dict] = None) -> list[dict]:
    """Compare a PcbDoc's rules against the preset rules.

    Returns a table of:
        {rule, kind, board value, preset value, status}
    where status is one of:
        'match'            board value matches preset value
        'differs'          board value differs from preset value
        'missing_on_board' preset rule not present in the board
        'extra_on_board'   custom board rule not in preset
    """
    if preset_rules is None:
        preset_info = get_jlc_preset()
        preset_rules = preset_info.get("rules", [])

    matched_board_indices = set()
    table = []

    # 1. Compare each preset rule against board rules
    for pr in preset_rules:
        p_name = pr.get("name", "")
        p_kind = pr.get("kind", "")
        p_val = pr.get("value")
        if not p_val and pr.get("attributes"):
            p_val = rule_display_value(pr["attributes"])
        p_val = p_val or "—"

        # Effective rule per kind: highest priority (lowest PRIORITY number)
        # among enabled scope-All rules; fall back to a same-name rule.
        matched_idx = _effective_index(board_rules, p_kind, matched_board_indices)
        if matched_idx is None:
            for i, br in enumerate(board_rules):
                if i not in matched_board_indices and br.get("NAME") == p_name and br.get("RULEKIND") == p_kind:
                    matched_idx = i
                    break

        if matched_idx is not None:
            matched_board_indices.add(matched_idx)
            br = board_rules[matched_idx]
            b_val = rule_display_value(br)
            b_name = br.get("NAME", p_name)

            if _normalize_val(b_val) == _normalize_val(p_val):
                status = "match"
            else:
                status = "differs"

            row = {
                "rule": b_name,
                "kind": p_kind,
                "board value": b_val,
                "preset value": p_val,
                "status": status,
                "board_value": b_val,
                "preset_value": p_val,
            }
        else:
            row = {
                "rule": p_name,
                "kind": p_kind,
                "board value": "—",
                "preset value": p_val,
                "status": "missing_on_board",
                "board_value": "—",
                "preset_value": p_val,
            }
        table.append(row)

    # 2. Add extra board rules that were not matched to any preset rule
    for i, br in enumerate(board_rules):
        if i in matched_board_indices:
            continue
        b_name = br.get("NAME", f"Rule_{i+1}")
        b_kind = br.get("RULEKIND", "")
        b_val = rule_display_value(br)
        row = {
            "rule": b_name,
            "kind": b_kind,
            "board value": b_val,
            "preset value": "—",
            "status": "extra_on_board",
            "board_value": b_val,
            "preset_value": "—",
        }
        table.append(row)

    return table


def main(argv=None):
    import oscompat
    oscompat.utf8_stdio()
    ap = argparse.ArgumentParser(description="PCB design rules reader, writer, and diff tool")
    sub = ap.add_subparsers(dest="cmd")

    diff_p = sub.add_parser("diff", help="Diff PcbDoc rules against JLC preset")
    diff_p.add_argument("pcbdoc", help="Path to .PcbDoc file")

    exp_p = sub.add_parser("export", help="Export JLC preset rules to .RUL file")
    exp_p.add_argument("output", help="Output .RUL file path")
    exp_p.add_argument("--board", help="PcbDoc: write the board's full rule set with JLC values (use Replace existing rules)")

    sub.add_parser("preset", help="Print JLC preset design rules")

    args = ap.parse_args(argv)

    if args.cmd == "diff":
        doc = read_pcbdoc(args.pcbdoc)
        board_rules = doc.get("rules", [])
        diff = diff_rules(board_rules)
        print(f"Rules diff for {args.pcbdoc} vs JLC preset ({len(diff)} rules):")
        print(f"{'Rule':<25} {'Kind':<25} {'Board Value':<30} {'Preset Value':<30} {'Status':<15}")
        print("-" * 125)
        for r in diff:
            print(f"{r['rule']:<25} {r['kind']:<25} {r['board value']:<30} {r['preset value']:<30} {r['status']:<15}")
        return 0

    elif args.cmd == "export":
        if args.board:
            records = board_rul_records(args.board)
            out = write_rul(records, args.output)
            print(f"Exported {len(records)} board-aware rules to {out} (import with 'Replace existing rules')")
        else:
            records = get_preset_rule_records()
            out = write_rul(records, args.output)
            print(f"Exported {len(records)} preset rules to {out} (import with 'Merge', then raise *_1 rules in Priorities)")
        return 0

    elif args.cmd == "preset":
        preset = get_jlc_preset()
        print(f"JLC Preset Rules (source: {preset.get('capabilities_url', 'JLC Capabilities')})")
        for r in preset.get("rules", []):
            print(f"  {r.get('name', ''):<25} {r.get('kind', ''):<25} {r.get('value', ''):<30} {r.get('description', '')}")
        return 0

    else:
        ap.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
