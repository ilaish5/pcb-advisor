"""
Structural guard against invented design rules.

A constraint must declare HOW it is known, and each provenance class has to
carry what makes it checkable:

    computed    needs a source describing the calculation
    standard    needs a document and a locator
    datasheet   needs a document and a locator; a url + verbatim quote to be
                counted as verified
    convention  allowed, but must say so out loud - this is the honest label
                for craft knowledge with no citable source

The old version only checked that a `source` string was non-empty, which let
`source: practice` through as if it were a citation.  It isn't.
"""
import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import workspace  # noqa: E402

VALID = {"computed", "standard", "datasheet", "convention"}


def check(path):
    cas = yaml.safe_load(path.read_text(encoding="utf-8"))
    errors, warnings, stats = [], [], {k: 0 for k in VALID}
    node_ids, lock_ids = set(), set()

    for node in cas.get("nodes", []):
        nid = node.get("id")
        if not nid:
            errors.append("node with no id")
            continue
        if nid in node_ids:
            errors.append(f"duplicate node id {nid}")
        node_ids.add(nid)
        for field in ("type", "question"):
            if not node.get(field):
                errors.append(f"{nid}: missing {field}")
        if not node.get("why"):
            warnings.append(f"{nid}: no 'why'")

        # `costs` is the nuance the structural fields cannot express - NOT a
        # verdict on which option to avoid. Authored on one option only, it
        # reads as one, which is why the renderer now weighs options by locks
        # and blocks instead. An uneven node is still worth flagging to whoever
        # writes the corpus: the missing prose is the part only a human can add.
        opts = node.get("options") or []
        with_costs = [o for o in opts if o.get("costs")]
        silent = [o for o in opts
                  if not o.get("costs") and not o.get("note")
                  and (o.get("locks") or o.get("blocks"))]
        if with_costs and silent:
            warnings.append(
                f"{nid}: {', '.join(o.get('id', '?') for o in silent)} add parts or rules "
                f"but have no 'costs' prose while a sibling does - write theirs too, "
                f"or costs reads as a verdict on the options that have it")
        if not node.get("options"):
            errors.append(f"{nid}: no options")

        for opt in node.get("options", []) or []:
            oid = opt.get("id", "?")
            for lock in opt.get("locks", []) or []:
                lid = lock.get("id")
                if not lid:
                    errors.append(f"{nid}.{oid}: constraint with no id")
                    continue
                if lid in lock_ids:
                    errors.append(f"duplicate constraint id {lid}")
                lock_ids.add(lid)
                if not lock.get("text"):
                    errors.append(f"{lid}: no text")

                prov = lock.get("provenance")
                if prov not in VALID:
                    errors.append(f"{lid}: provenance must be one of {sorted(VALID)}, got {prov!r}")
                    continue
                stats[prov] += 1
                src = lock.get("source") or {}

                if prov in ("computed", "standard", "datasheet"):
                    if not src.get("doc"):
                        errors.append(f"{lid}: provenance={prov} needs source.doc")
                    if prov != "computed" and not src.get("locator"):
                        errors.append(f"{lid}: provenance={prov} needs source.locator")
                if prov == "datasheet":
                    if lock.get("verified"):
                        if not src.get("url"):
                            errors.append(f"{lid}: marked verified but has no source.url")
                        if not src.get("quote"):
                            errors.append(f"{lid}: marked verified but has no verbatim quote")
                    else:
                        warnings.append(f"{lid}: citation claimed but unverified "
                                        f"- no quote pulled from the real document yet")

    for node in cas.get("nodes", []):
        for dep in node.get("depends_on", []) or []:
            if dep not in node_ids:
                errors.append(f"{node['id']}: depends_on unknown node {dep!r}")
        for g in (node.get("requires") or {}):
            if g not in node_ids:
                errors.append(f"{node['id']}: requires unknown node {g!r}")
        for opt in node.get("options", []) or []:
            for nxt in opt.get("opens", []) or []:
                if nxt not in node_ids:
                    errors.append(f"{node['id']}.{opt.get('id')}: opens unknown node {nxt!r}")

    return errors, warnings, len(node_ids), stats


def main():
    failed = False
    totals = {k: 0 for k in VALID}
    for path in sorted(workspace.cascade_dir().glob("*.yaml")):
        errors, warnings, n_nodes, stats = check(path)
        for k, v in stats.items():
            totals[k] += v
        breakdown = "  ".join(f"{k}={v}" for k, v in stats.items() if v)
        print(f"\n{path.name}: {n_nodes} nodes   {breakdown}")
        for w in warnings:
            print(f"  warn  {w}")
        for e in errors:
            print(f"  FAIL  {e}")
        failed = failed or bool(errors)

    print("\ntotals: " + "  ".join(f"{k}={v}" for k, v in totals.items()))
    print("FAILED" if failed else "ok - every constraint declares how it is known")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
