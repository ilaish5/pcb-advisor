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

VALID = {"computed", "standard", "datasheet", "check_your_part", "convention"}


def check(path, producible=frozenset()):
    cas = yaml.safe_load(path.read_text(encoding="utf-8"))
    errors, warnings, stats = [], [], {k: 0 for k in VALID}
    node_ids, lock_ids = set(), set()
    deferred = []
    dead_ends = []

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
        # An option that records nothing and gates nothing closes its topic
        # having learned nothing. Sometimes that is honest - sometimes, as with
        # "Bench or room" for a board whose sensor hangs in a freezer, it means
        # the question could not express the case and the design goes silently
        # under-constrained. Either way the author should see it.
        for o in opts:
            if o.get("locks") or o.get("blocks") or o.get("opens"):
                continue
            dead_ends.append((nid, o.get("id", "?"), o.get("label", "")))

        if with_costs and silent:
            warnings.append(
                f"{nid}: {', '.join(o.get('id', '?') for o in silent)} add parts or rules "
                f"but have no 'costs' prose while a sibling does - write theirs too, "
                f"or costs reads as a verdict on the options that have it")
        # A default decides for the student, so it answers to the same contract
        # as a constraint. A wrong default is worse than a question, because
        # nobody examines it - which is the whole reason it must be authored,
        # justified and badged rather than inferred.
        spec = node.get("default")
        if spec is not None:
            rules = spec if isinstance(spec, list) else [spec]
            opt_ids = {o.get("id") for o in (node.get("options") or [])}
            for i, rule in enumerate(rules):
                if not isinstance(rule, dict):
                    errors.append(f"{nid}: a default must be a mapping")
                    continue
                if rule.get("option") not in opt_ids:
                    errors.append(f"{nid}: default picks {rule.get('option')!r}, "
                                  f"which is not one of its options")
                if not rule.get("why"):
                    errors.append(f"{nid}: a default must say why - that sentence is "
                                  f"the only thing the student will read about it")
                if rule.get("provenance") not in VALID:
                    errors.append(f"{nid}: default needs a provenance from "
                                  f"{sorted(VALID)}, got {rule.get('provenance')!r}")
                for key in (rule.get("when") or {}):
                    deferred.append((nid, key))
                # the last rule is the fallback and may be unconditional; an
                # unconditional rule anywhere earlier makes the rest dead code
                if not rule.get("when") and i < len(rules) - 1:
                    errors.append(f"{nid}: default rule {i + 1} has no `when`, so no "
                                  f"rule after it can ever match")

        # A node asks for a CHOICE or for a NUMBER, never both and never neither.
        # The two carry their rules in different places - an options node on the
        # option, a quantity node on the node - and a node with both would have
        # two answers for one question.
        spec = node.get("answer") or None
        if spec and node.get("options"):
            errors.append(f"{nid}: has both `options` and `answer` - a question "
                          f"asks for a choice or for a number, not both")
        elif spec:
            if spec.get("kind") != "quantity":
                errors.append(f"{nid}: answer.kind must be 'quantity', "
                              f"got {spec.get('kind')!r}")
            if not spec.get("unit"):
                errors.append(f"{nid}: a number without a unit cannot be compared "
                              f"with anything - answer.unit is required")
            lo, hi = spec.get("min"), spec.get("max")
            if lo is not None and hi is not None and lo >= hi:
                errors.append(f"{nid}: answer.min {lo} is not below answer.max {hi}")
            if not node.get("locks"):
                warnings.append(f"{nid}: asks for a number and records nothing - "
                                f"the student types it and nothing follows")
            for lock in node.get("locks") or []:
                if "{value}" not in (lock.get("text") or ""):
                    warnings.append(f"{lock.get('id', nid)}: follows from a number "
                                    f"but never mentions it - use {{value}}")
        elif node.get("locks"):
            errors.append(f"{nid}: has `locks` but asks for a choice - rules belong "
                          f"on the option that locks them")
        elif not node.get("options"):
            errors.append(f"{nid}: no options")

        if spec and node.get("default"):
            errors.append(f"{nid}: a number cannot have a default option - if the "
                          f"corpus knows the value, this is not a question")

        for opt in (node.get("options") or []) + ([node] if spec else []):
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

                # Each class carries what makes it checkable, and the checks
                # differ because they are not the same kind of claim.
                if prov == "computed" and not lock.get("calculation"):
                    # the arithmetic itself, not a `doc` field holding a sum
                    errors.append(f"{lid}: provenance=computed needs a `calculation`")
                if prov == "standard":
                    if not src.get("doc"):
                        errors.append(f"{lid}: provenance=standard needs source.doc")
                    if not src.get("locator"):
                        errors.append(f"{lid}: provenance=standard needs source.locator")
                if prov == "check_your_part":
                    # not a citation: an instruction to go and read whichever
                    # part the student chose. It must say WHERE to look.
                    if not src.get("locator"):
                        errors.append(f"{lid}: provenance=check_your_part needs source."
                                      f"locator - say where in the datasheet to look")
                    if src.get("url") or src.get("cached"):
                        errors.append(f"{lid}: provenance=check_your_part must not cite a "
                                      f"document - if you have one, this is a datasheet rule")
                # a constraint may declare that it only applies when a part is
                # on the board. The part has to be one the corpus can actually
                # put there, or the rule is unreachable and nobody would notice
                need = lock.get("needs_block")
                if need and producible and need not in producible:
                    errors.append(f"{lid}: needs_block {need!r} is a part no cascade "
                                  f"can put on a board")

                if prov != "datasheet" and "verified" in lock:
                    warnings.append(f"{lid}: `verified` means nothing on a "
                                    f"{prov} rule - only a datasheet claims a quote")
                if prov == "datasheet":
                    # A datasheet rule names a REAL document. A role noun like
                    # "regulator datasheet" is not one - no student can fetch it
                    # and no validator can check it - yet eleven of these passed
                    # silently as though they were citations.
                    if not src.get("doc"):
                        errors.append(f"{lid}: provenance=datasheet needs source.doc")
                    if not src.get("locator"):
                        errors.append(f"{lid}: provenance=datasheet needs source.locator")
                    if not src.get("url"):
                        errors.append(f"{lid}: provenance=datasheet needs source.url - a "
                                      f"document nobody can fetch is not a citation. If it "
                                      f"depends on the student's own part, this is "
                                      f"check_your_part")
                    if lock.get("verified"):
                        if not src.get("cached"):
                            errors.append(f"{lid}: marked verified but names no cached file")
                        if not src.get("quote"):
                            errors.append(f"{lid}: marked verified but has no verbatim quote")
                    else:
                        warnings.append(f"{lid}: cites {src.get('doc')!r} but no quote has "
                                        f"been pulled from it yet - scripts/sources.py verify")

    for nid, key in deferred:
        if key not in node_ids:
            errors.append(f"{nid}: default keys on {key!r}, which is not a question "
                          f"in this domain")

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

    gated = {(k, v) for node in cas.get("nodes", [])
             for k, v in (node.get("requires") or {}).items()}
    for nid, oid, label in dead_ends:
        if (nid, oid) in gated:
            continue
        warnings.append(f"{nid}: '{label}' records nothing and opens nothing - "
                        f"choosing it closes the topic having learned nothing")

    return errors, warnings, len(node_ids), stats


def producible_blocks():
    """Every part the whole corpus can put on a board, plus the sketch kinds it
    keys on. Cross-file on purpose: a rule in the analog cascade may depend on a
    regulator that only the power cascade contributes."""
    out = set()
    for path in sorted(workspace.cascade_dir().glob("*.yaml")):
        cas = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        out.update(cas.get("blocks") or [])                    # the sketch kinds
        for b in cas.get("base_blocks") or []:
            out.add(b["id"])
        for node in cas.get("nodes", []) or []:
            for opt in node.get("options", []) or []:
                for b in opt.get("blocks") or []:
                    out.add(b["id"])
    return out


def main():
    failed = False
    totals = {k: 0 for k in VALID}
    producible = producible_blocks()
    for path in sorted(workspace.cascade_dir().glob("*.yaml")):
        errors, warnings, n_nodes, stats = check(path, producible)
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
