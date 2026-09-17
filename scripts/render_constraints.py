"""constraints.md is DERIVED. Never edit it by hand - it is rewritten every run."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import model  # noqa: E402


def render(project="demo"):
    m = model.build(project=project)
    out = [
        f"# אילוצי תכן — {m['title']}",
        "",
        "**נגזר אוטומטית. אל תערוך ידנית** — הקובץ נכתב מחדש בכל הרצה של "
        "`scripts/render_constraints.py`. המקור הוא `decisions.jsonl`.",
        "",
        f"{m['progress']['answered']}/{m['progress']['total']} החלטות · "
        f"{len(m['constraints'])} אילוצים פעילים",
        "",
    ]
    if m["answered"]:
        out += ["## החלטות שהתקבלו", "", "| החלטה | נבחר | מי |", "|---|---|---|"]
        for n in m["answered"]:
            opt = next((o for o in n["options"] if o["id"] == n["chosen"]), {})
            out.append(f"| {n['question']} | {opt.get('label', n['chosen'])} | {n['chosen_by']} |")
        out.append("")
    if m["constraints"]:
        out += ["## אילוצים פעילים", ""]
        for c in m["constraints"]:
            out += [
                f"### `{c['id']}`",
                "",
                c["text"],
                "",
                f"- **נובע מ:** {c['from_node']} = {c['from_label']}",
                f"- **מקור:** {c['source']}",
                "",
            ]
    if m["open"]:
        out += ["## שאלות פתוחות", ""]
        out += [f"- `{n['id']}` — {n['question']}" for n in m["open"]]
        out.append("")
    if m["blocked"]:
        out += ["## חסום", ""]
        out += [f"- `{n['id']}` — ממתין ל: {', '.join(n['waiting_on'])}" for n in m["blocked"]]
    return "\n".join(out)


if __name__ == "__main__":
    proj = sys.argv[1] if len(sys.argv) > 1 else "demo"
    path = model.project_dir(proj) / "constraints.md"
    path.write_text(render(proj), encoding="utf-8")
    print(f"wrote {path}")
