"""
Re-check every claimed quote against the document it claims to come from.

This is the difference between a citation and a citation-shaped string.
Run it in CI.  A quote that is not literally in the cached document fails.
"""
import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sources  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main():
    checked = passed = failed = skipped = 0
    for path in sorted((ROOT / "cascade").glob("*.yaml")):
        cas = yaml.safe_load(path.read_text(encoding="utf-8"))
        for node in cas.get("nodes", []):
            for opt in node.get("options", []) or []:
                for lock in opt.get("locks", []) or []:
                    src = lock.get("source") or {}
                    quote, cached = src.get("quote"), src.get("cached")
                    if not lock.get("verified"):
                        skipped += 1
                        continue
                    checked += 1
                    if not quote or not cached:
                        print(f"  FAIL  {lock['id']}: verified but no quote/cached document")
                        failed += 1
                        continue
                    res = sources.verify(cached, quote)
                    if res["ok"]:
                        print(f"  ok    {lock['id']}  <- {cached}")
                        passed += 1
                    else:
                        print(f"  FAIL  {lock['id']}: {res['reason']}")
                        failed += 1
    print(f"\n{passed} verified, {failed} failed, {skipped} unverified (citation claimed, "
          f"quote not pulled yet)")
    if failed:
        print("FAILED")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
