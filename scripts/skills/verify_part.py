"""
Verify a library part's pins against its datasheet text.

    python scripts/skills/verify_part.py <project> <line>

For every pin of the part's netlist entry that has a number, the datasheet text
must contain that pin number next to its name. Anything it cannot find is listed
as an issue. The result is written to library-log.jsonl as verify=pass|mismatch
(or "unchecked" when there is no datasheet text to compare with). The agent cannot
set it, and 'pass' alone does not make a part verified: the student has to accept
it too.
"""
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import oscompat  # noqa: E402
import sources   # noqa: E402
import store     # noqa: E402


def _near(text, num, name, span=40):
    n, m = re.escape(num), re.escape(name)
    return bool(re.search(rf"\b{n}\b.{{0,{span}}}{m}|{m}.{{0,{span}}}\b{n}\b", text, re.I | re.S))


def verify(project, key):
    line = next((l for l in store.bom_lines(project) if l["key"] == key), None)
    if not line:
        raise SystemExit(f"no BOM line {key!r}")
    ds = line.get("datasheet") or sources.find_for(project, line.get("mpn"))
    if not ds:
        result = {"verify": "unchecked", "issues": "no datasheet stored for this part"}
    else:
        try:
            text = re.sub(r"\s+", " ", sources.text_of(ds, store.pdir(project) / "sources"))
        except FileNotFoundError:
            text = None
        if text is None:
            result = {"verify": "unchecked",
                      "issues": f"{ds} is not in the library; run scripts/sources.py restore"}
        else:
            bad, checked = [], 0
            for sheet in store.sheet_ids(project):
                for part in store.load_sheet(project, sheet).get("parts", []):
                    if part["ref"] not in line.get("refs", []):
                        continue
                    for pin in part.get("pins", []):
                        num, name = str(pin.get("num") or "").strip(), str(pin.get("name") or "").strip()
                        if num and num != "*" and name:
                            checked += 1
                            if not _near(text, num, name):
                                bad.append(f"{part['ref']} pin {num} {name}")
            if bad:
                result = {"verify": "mismatch", "issues": "not found in the datasheet: " + "; ".join(bad[:12])}
            elif not checked:
                result = {"verify": "unchecked", "issues": "no pins of this part on a sheet to check"}
            else:
                result = {"verify": "pass", "issues": ""}
    changes = {**result, "verified_at": store.now()}
    if result["verify"] != "pass":
        changes["accepted"] = False          # a part that fails is no longer accepted
    store.add_library(project, key, changes, by="verify_part")
    return {"line": key, **result}


if __name__ == "__main__":
    oscompat.utf8_stdio()
    if len(sys.argv) < 3:
        raise SystemExit("usage: verify_part.py <project> <line>")
    print(json.dumps(verify(sys.argv[1], sys.argv[2]), ensure_ascii=False, indent=2))
