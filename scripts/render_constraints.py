"""constraints.md is DERIVED. Never edit it by hand - it is rewritten every run."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import model      # noqa: E402
import workspace  # noqa: E402


def _source(c):
    """The provenance line. A constraint that cannot say how it is known says so."""
    src = c.get("source") or {}
    bits = [f"{c['icon']} {c['provenance']}"]
    if src.get("doc"):
        bits.append(src["doc"])
    if src.get("locator"):
        bits.append(src["locator"])
    if src.get("url"):
        bits.append(src["url"])
    if c["provenance"] != "computed":
        bits.append("verified" if c.get("verified") else "**unverified**")
    return " · ".join(bits)


def render(project=None):
    m = model.build(project=project)
    p = m["progress"]
    out = [
        f"# Design constraints — {m['title']}",
        "",
        "**Derived. Do not edit by hand** — this file is rewritten on every run of "
        "`scripts/render_constraints.py`. The source is `decisions.jsonl`.",
        "",
        f"{p['answered']}/{p['total']} decisions · {len(m['constraints'])} active "
        f"constraints · {p['unverified']} unverified",
        "",
    ]
    if m["answered"]:
        out += ["## Decisions made", "", "| Question | Chosen | By |", "|---|---|---|"]
        for n in m["answered"]:
            opt = next((o for o in n["options"] if o["id"] == n["chosen"]), {})
            out.append(f"| {n['question']} | {opt.get('label', n['chosen'])} | {n['chosen_by']} |")
        out.append("")
    if m["constraints"]:
        out += ["## Active constraints", ""]
        for c in m["constraints"]:
            out += [
                f"### `{c['id']}`",
                "",
                c["text"],
                "",
                f"- **Follows from:** {c['from_node']} = {c['from_label']}",
                f"- **How we know it:** {_source(c)}",
                "",
            ]
    if m["conflicts"]:
        out += ["## Conflicts", ""]
        out += [f"- `{cf['a']}` vs `{cf['b']}` — {cf['note']}" for cf in m["conflicts"]]
        out.append("")
    if m["open"]:
        out += ["## Open questions", ""]
        out += [f"- `{n['id']}` — {n['question']}" for n in m["open"]]
        out.append("")
    if m["blocked"]:
        out += ["## Blocked", ""]
        out += [f"- `{n['id']}` — {n.get('reason', '?')}" for n in m["blocked"]]
        out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    import oscompat
    oscompat.utf8_stdio()
    proj = sys.argv[1] if len(sys.argv) > 1 else workspace.default_project()
    path = model.project_dir(proj) / "constraints.md"
    path.write_text(render(proj), encoding="utf-8")
    print(f"wrote {path}")
