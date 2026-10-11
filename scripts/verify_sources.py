"""
Every citation in a project must resolve to a document in Sources.

The agent cites with {{src:<file name>|<locator>}}; the UI turns that into a chip
that opens the Sources page. A chip pointing at nothing is a citation-shaped
string, so this check fails on it. A quoted sentence is checked separately, word
for word, by `scripts/sources.py verify <name> "<quote>"` before the agent shows it.

    python scripts/verify_sources.py [project ...]

A document that is listed (it has its .json sidecar) but whose file is not on this
machine is reported as "not here", not as a failure: the vendor PDFs are not in git.
Run `python scripts/sources.py restore` to fetch them.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import model      # noqa: E402
import oscompat   # noqa: E402
import project    # noqa: E402


def main(projects=None):
    projects = projects or [p["name"] for p in project.list_all()]
    failed = missing = ok = 0
    for name in projects:
        known = {s["name"]: s for s in model.list_sources(name)}
        for cited, where in sorted(model.citations(name).items()):
            if cited not in known:
                print(f"  FAIL  {name}: cites {cited!r} ({len(where)}x), which is not in Sources")
                failed += 1
            elif not known[cited]["present"]:
                print(f"  not here  {name}: {cited} is listed but the file is not on this machine")
                missing += 1
            else:
                ok += 1
    print(f"\n{ok} cited source{'' if ok == 1 else 's'} resolved, {failed} failed, {missing} not here")
    if missing:
        print(oscompat.py("Run:  python3 scripts/sources.py restore"))
    return 1 if failed else 0


if __name__ == "__main__":
    oscompat.utf8_stdio()
    sys.exit(main(sys.argv[1:] or None))
