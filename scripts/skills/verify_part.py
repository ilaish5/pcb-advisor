"""
Verify a library part's pins against its datasheet's pin table.

    python scripts/skills/verify_part.py <project> <line>

The datasheet must be about this part (its first pages name the MPN or its family), and every pin of the part's netlist entry
that has a number and a name must be a ROW of the datasheet's pin table: number and name in the same row (scripts/pintable.py).
The table's pin count is compared with the footprint's pads. A number in prose, in another row or in a diagram proves nothing.
The result is written to library-log.jsonl as verify=pass|mismatch (or "unchecked" when the text cannot prove it, with the
reason in issues). The agent cannot set it, and 'pass' alone does not make a part verified: the student has to accept it too.
The symbol is never evidence: a generated symbol is built from the netlist itself (partlib.symbol_from_netlist).
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import oscompat  # noqa: E402
import pintable  # noqa: E402
import sources   # noqa: E402
import store     # noqa: E402

_NO_MPN = ("", "—", "-")


def _pins_of(project, line):
    """[(ref, [(number, name)])] of the line's parts on the sheets; pins without a number, a name or a real name are left out."""
    out = []
    for sheet in store.sheet_ids(project):
        for part in store.load_sheet(project, sheet).get("parts", []):
            if part["ref"] not in line.get("refs", []):
                continue
            pins = []
            for pin in part.get("pins", []):
                num, name = str(pin.get("num") or "").strip(), str(pin.get("name") or "").strip()
                if num and num != "*" and name:
                    pins.append((num, name))
            out.append((part["ref"], pins))
    return out


def _judge(project, line, ds):
    """{"verify", "issues", ...} for a line whose datasheet `ds` is known."""
    folder = store.pdir(project) / "sources"
    try:
        text = sources.text_of(ds, folder)
    except FileNotFoundError:
        return {"verify": "unchecked", "issues": f"{ds} is not in the library; run scripts/sources.py restore"}
    if not text.strip():
        return {"verify": "unchecked", "issues": f"{ds} has no text to read (a scan?)"}
    names = [m for m in (line.get("mpn"), line.get("value")) if m and str(m).strip() not in _NO_MPN]
    if not names:
        return {"verify": "unchecked", "issues": "the BOM line has no MPN to match the datasheet to"}
    head = sources.head_of(ds, folder)
    if not any(sources.mentions_part(head, n) for n in names):
        return {"verify": "unchecked", "issues": f"{ds} does not mention {names[0]}: it may be the datasheet of another part"}
    parts = [(ref, pins) for ref, pins in _pins_of(project, line) if pins]
    if not parts:
        return {"verify": "unchecked", "issues": "no pins of this part on a sheet to check"}
    layout = sources.layout_text_of(ds, folder)
    try:
        import partlib
        pads = partlib.footprint_pads(project, line["key"])
        footprint = (store.library_manifest(project).get(line["key"]) or {}).get("footprint") or ""
    except (ImportError, OSError, ValueError, KeyError):
        pads, footprint = None, ""
    package = line.get("package") or footprint
    results = []
    for ref, pins in parts:
        named = [(n, nm) for n, nm in pins if nm.strip().upper() != n.strip().upper()]
        if not named:
            r = {"verify": "unchecked", "issues": ["the pins are named only by their numbers: nothing to compare with the table"],
                 "notes": [], "evidence": ""}
        else:
            r = pintable.check([layout, text], named, package, pads)
        results.append((ref, r))
    bad = [(ref, r) for ref, r in results if r["verify"] == "mismatch"]
    if bad:
        issues = [f"{ref}: {i}" for ref, r in bad for i in r["issues"]]
        return {"verify": "mismatch", "issues": "not as in the datasheet's pin table: " + "; ".join(issues[:12])}
    weak = [(ref, r) for ref, r in results if r["verify"] != "pass"]
    if weak:
        return {"verify": "unchecked", "issues": "; ".join(f"{ref}: {i}" for ref, r in weak for i in r["issues"])[:600]}
    notes = [f"{ref}: {n}" for ref, r in results for n in r["notes"]]
    return {"verify": "pass", "issues": ("note: " + "; ".join(notes[:6])) if notes else "", "method": "pin-table",
            "evidence": f"{ds}: " + results[0][1]["evidence"]}


def verify(project, key):
    line = next((l for l in store.bom_lines(project) if l["key"] == key), None)
    if not line:
        raise SystemExit(f"no BOM line {key!r}")
    if store._polarised_only(line):
        # a regex cannot tell anode from cathode: only the student's accept clears a diode/LED, nothing is written
        return {"line": key, "verify": "unchecked", "issues": "polarity of a diode/LED is confirmed by the student, not by text matching"}
    ds = line.get("datasheet") or sources.find_for(project, line.get("mpn"))
    result = _judge(project, line, ds) if ds else {"verify": "unchecked", "issues": "no datasheet stored for this part"}
    changes = {**result, "verified_at": store.now()}
    if result["verify"] != "pass":
        changes["accepted"] = False          # a part that fails is no longer accepted
        changes["method"] = ""               # the earlier pass's method and evidence do not describe this result
        changes["evidence"] = ""
    if result["verify"] == "mismatch":
        changes["pins_accepted"] = False     # new conflicting pins: the student decides again
    store.add_library(project, key, changes, by="verify_part")
    store.refresh_pins_source(project)       # clears the "unverified" mark on the sheet parts, or leaves it
    return {"line": key, **result}


if __name__ == "__main__":
    oscompat.utf8_stdio()
    if len(sys.argv) < 3:
        raise SystemExit("usage: verify_part.py <project> <line>")
    print(json.dumps(verify(sys.argv[1], sys.argv[2]), ensure_ascii=False, indent=2))
