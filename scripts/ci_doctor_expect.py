"""CI helper for .github/workflows/install.yml: read `pcb.py doctor --json` output and check it is what an install
WITHOUT the Claude CLI must give. Not part of the app."""
import json
import sys


def main(argv):
    with open(argv[0], encoding="utf-8-sig") as f:
        res = json.load(f)
    by = {c["id"]: c for c in res["checks"]}
    problems = []
    if by["claude"]["status"] != "fix" or not (by["claude"]["fix"] or {}).get("command"):
        problems.append(f"claude should be 'fix' with a command, got {by['claude']}")
    for cid in ("python", "venv", "requirements", "workspace"):
        if by[cid]["status"] != "ok":
            problems.append(f"{cid} should be ok, got {by[cid]}")
    if not res["can_start"]:
        problems.append("can_start should be true (only the engine is missing)")
    if res["ok"]:
        problems.append("ok should be false while the Claude CLI is missing")
    if "--zip" in argv and by["git"]["status"] != "warn":
        problems.append(f"git should be 'warn' for a ZIP install, got {by['git']}")
    if "--zip" not in argv and by["git"]["status"] != "ok":
        problems.append(f"git should be ok for a clone, got {by['git']}")
    for p in problems:
        print("FAIL:", p)
    print("doctor result as expected" if not problems else "")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
