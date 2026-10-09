"""
Re-check every claimed quote against the document it claims to come from.

This is the difference between a citation and a citation-shaped string.
Run it in CI.  A quote that is not literally in the cached document fails.
"""
import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import oscompat   # noqa: E402
import sources    # noqa: E402
import workspace  # noqa: E402


def main():
    passed = failed = pending = 0
    missing = False
    by_class = {}
    for path in sorted(workspace.cascade_dir().glob("*.yaml")):
        cas = yaml.safe_load(path.read_text(encoding="utf-8"))
        for node in cas.get("nodes", []):
            for opt in node.get("options", []) or []:
                for lock in opt.get("locks", []) or []:
                    prov = lock.get("provenance", "convention")
                    by_class[prov] = by_class.get(prov, 0) + 1
                    # Only a datasheet rule claims a quote. Counting conventions
                    # and check-your-part instructions as "unverified" made the
                    # debt look four times its real size, and hid which of them
                    # was actually a citation nobody had checked.
                    if prov != "datasheet":
                        continue
                    src = lock.get("source") or {}
                    quote, cached = src.get("quote"), src.get("cached")
                    if not lock.get("verified"):
                        pending += 1
                        print(f"  todo  {lock['id']}: cites {src.get('doc')!r}, "
                              f"no quote pulled yet")
                        continue
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
                        missing = missing or "not in the cache" in res["reason"]

    print(f"\n{passed} quote{'' if passed == 1 else 's'} verified, {failed} failed"
          + (f", {pending} citation{'' if pending == 1 else 's'} still to check"
             if pending else ""))
    rest = "  ".join(f"{k}={v}" for k, v in sorted(by_class.items()) if k != "datasheet")
    if rest:
        print(f"nothing to verify in: {rest}")
    if missing:
        # a clean clone hits this every time: the vendor PDFs are correctly
        # gitignored, so the first run fails until the cache is warmed
        print("\nThe cited documents are not in git - they are vendor PDFs.")
        print(oscompat.py("Run:  python3 scripts/sources.py restore"))
    if failed:
        print("FAILED")
    return 1 if failed else 0


if __name__ == "__main__":
    import oscompat
    oscompat.utf8_stdio()
    sys.exit(main())
