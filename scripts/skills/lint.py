#!/usr/bin/env python3
"""
Skill linter: checks runtime/skills/*/SKILL.md against the skill format spec, the eval files in
scripts/bench/skill_evals/, and the routing table in runtime/AGENTS.md.

    python scripts/skills/lint.py [--only NAME]      (also: python pcb.py skills lint [--only NAME])

Exit code 1 when there is any problem. `lint()` returns a list of {"skill", "rule", "message"}.
"""
import json
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
SKILLS_DIR = REPO / "runtime" / "skills"
EVALS_DIR = REPO / "scripts" / "bench" / "skill_evals"

SKILLS_12 = (
    "idea-and-requirements", "parts-and-stock", "part-models", "project-library",
    "schematic-preview", "schematic-review", "rules-and-calcs", "placement-and-routing-plan",
    "board-review", "manufacturer-and-dfm", "altium-help", "project-keeping",
)
SECTIONS = ("When to use", "Steps", "Scripts", "References", "Pitfalls", "Output")
MAX_SKILL_LINES, MAX_LINE, MAX_REF_LINES, MAX_DESC = 150, 160, 200, 600
FORBIDDEN = re.compile(r"real-project|mcp__altium|DelphiScript|run_altium_script|C:\\Users", re.I)
CASE_KEYS = {"id", "lang", "question", "expect_skill", "must", "must_not", "cite"}
CODEWORD = "KESTREL-31"


def _p(skill, rule, message):
    return {"skill": skill, "rule": rule, "message": message}


def _frontmatter(text):
    """(dict, body_start_line_index) or (None, 0). Minimal YAML: `key: value`, indented lines continue a value."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, 0
    out, key = {}, None
    for i in range(1, len(lines)):
        ln = lines[i]
        if ln.strip() == "---":
            return out, i + 1
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", ln)
        if m and not ln.startswith(" "):
            key = m.group(1)
            out[key] = m.group(2).strip().strip('"').strip("'")
        elif key and ln.strip():
            out[key] += " " + ln.strip()
    return None, 0   # never closed


def _sections(lines):
    """{heading: [lines]} for `## ` headings outside code fences, plus the heading order."""
    order, body, cur, fence = [], {}, None, False
    for ln in lines:
        if ln.lstrip().startswith("```"):
            fence = not fence
        if not fence and ln.startswith("## "):
            cur = ln[3:].strip()
            order.append(cur)
            body.setdefault(cur, [])
        elif cur is not None:
            body[cur].append(ln)
    return order, body


def _strip_ref(raw):
    raw = re.split(r"[#|]", raw, 1)[0]
    return raw.rstrip(".,;:)")


def _lint_skill(name, folder, repo):
    probs = []
    add = lambda rule, msg: probs.append(_p(name, rule, msg))
    f = folder / "SKILL.md"
    if not f.is_file():
        add("skill-file", f"{f.name} is missing in {folder.name}/")
        return probs
    text = f.read_text(encoding="utf-8")
    lines = text.splitlines()

    fm, start = _frontmatter(text)
    if fm is None:
        add("frontmatter", "no YAML frontmatter (--- name/description ---) at the top")
        start = 0
        fm = {}
    if fm.get("name", "") != name:
        add("name", f"frontmatter name '{fm.get('name', '')}' must equal the folder name '{name}'")
    desc = fm.get("description", "")
    if not desc:
        add("description", "frontmatter description is missing")
    elif re.search(r"^description:\s*[>|]", text, re.M):
        # one line: simple frontmatter readers (and our own tests) do not fold YAML blocks
        add("description", "description must be one line, not a folded YAML block")
    else:
        if len(desc) > MAX_DESC:
            add("description", f"description is {len(desc)} chars, limit {MAX_DESC}")
        if "use when" not in desc.lower():
            add("description", 'description must contain "Use when ..." with the trigger phrases')

    if len(lines) > MAX_SKILL_LINES:
        add("length", f"SKILL.md has {len(lines)} lines, limit {MAX_SKILL_LINES}")
    for n, ln in enumerate(lines, 1):
        if n > start and len(ln) > MAX_LINE:   # the frontmatter description may be one long line
            add("length", f"line {n} is {len(ln)} chars, limit {MAX_LINE}")
            break
    refdir = folder / "references"
    if refdir.is_dir():
        for r in sorted(refdir.glob("*.md")):
            n = len(r.read_text(encoding="utf-8").splitlines())
            if n > MAX_REF_LINES:
                add("length", f"references/{r.name} has {n} lines, limit {MAX_REF_LINES}")

    order, body = _sections(lines[start:])
    missing = [s for s in SECTIONS if s not in order]
    for s in missing:
        add("sections", f"missing section '## {s}'")
    present = [s for s in order if s in SECTIONS]
    if not missing and present != list(SECTIONS):
        add("sections", "sections out of order: " + ", ".join(present) + "; expected: " + ", ".join(SECTIONS))

    for path in [f, *sorted(refdir.glob("*.md"))] if refdir.is_dir() else [f]:
        m = FORBIDDEN.search(path.read_text(encoding="utf-8"))
        if m:
            add("forbidden", f"{path.name} contains forbidden text '{m.group(0)}'")

    refs = "\n".join(body.get("References", []))
    for raw in re.findall(r"<repo>/([^\s`'\"<>()\[\]]+)", refs):
        rel = _strip_ref(raw)
        if rel and not (repo / rel).exists():
            add("reference", f"<repo>/{rel} does not exist")
    for rel in re.findall(r"(?<![\w/.<>-])references/([\w.-]+\.md)", "\n".join(body.get("References", []) + body.get("Steps", []))):
        if not (refdir / rel).is_file():
            add("reference", f"references/{rel} does not exist in {folder.name}/")

    for ln in body.get("Scripts", []):
        if "(planned" in ln:
            continue
        for rel in re.findall(r"scripts/([\w/.-]+\.py)", ln):
            if not (repo / "scripts" / rel).is_file():
                add("scripts", f"scripts/{rel} does not exist and the line is not marked '(planned, stage In)'")
    return probs


def _lint_evals(name, evals_dir):
    probs = []
    add = lambda rule, msg: probs.append(_p(name, rule, msg))
    f = evals_dir / f"{name}.json"
    if not f.is_file():
        add("evals", f"eval file {f.name} is missing in {evals_dir}")
        return probs
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except ValueError as exc:
        add("evals", f"{f.name} is not valid JSON: {exc}")
        return probs
    if not isinstance(data, dict) or data.get("skill") != name:
        add("evals", f"{f.name}: \"skill\" must be '{name}'")
    cases = data.get("cases") if isinstance(data, dict) else None
    if not isinstance(cases, list):
        add("evals", f"{f.name}: \"cases\" must be a list")
        return probs
    if len(cases) < 3:
        add("evals", f"{f.name}: {len(cases)} cases, need at least 3")
    seen = set()
    for i, c in enumerate(cases):
        tag = f"{f.name} case {i + 1}"
        if not isinstance(c, dict):
            add("evals", f"{tag}: not an object")
            continue
        cid = c.get("id")
        if not isinstance(cid, str) or not cid:
            add("evals", f"{tag}: id missing")
        elif cid in seen:
            add("evals", f"{tag}: duplicate id '{cid}'")
        else:
            seen.add(cid)
        extra = set(c) - CASE_KEYS
        if extra:
            add("evals", f"{tag}: unknown keys {sorted(extra)}")
        if c.get("lang") not in ("en", "he"):
            add("evals", f"{tag}: lang must be 'en' or 'he'")
        if not isinstance(c.get("question"), str) or not c.get("question", "").strip():
            add("evals", f"{tag}: question missing")
        if not isinstance(c.get("expect_skill"), bool):
            add("evals", f"{tag}: expect_skill must be true or false")
        must = c.get("must")
        if not (isinstance(must, list) and must and all(isinstance(g, list) and g and all(isinstance(x, str) for x in g) for g in must)):
            add("evals", f"{tag}: must must be a non-empty list of non-empty lists of strings")
        mn = c.get("must_not", [])
        if not (isinstance(mn, list) and all(isinstance(x, str) for x in mn)):
            add("evals", f"{tag}: must_not must be a list of strings")
        if not isinstance(c.get("cite"), bool):
            add("evals", f"{tag}: cite must be true or false")
    if cases and not any(isinstance(c, dict) and c.get("lang") == "he" for c in cases):
        add("evals", f"{f.name}: needs at least one Hebrew (lang 'he') case")
    return probs


def routing_table(agents_text):
    """Skill names in the first column of the table under '# SKILLS'."""
    m = re.search(r"^# SKILLS\s*$(.*?)(?=^# |\Z)", agents_text, re.M | re.S)
    names = []
    for ln in (m.group(1) if m else "").splitlines():
        c = re.match(r"^\|\s*([a-z][a-z0-9-]*)\s*\|", ln)
        if c and c.group(1) != "skill":
            names.append(c.group(1))
    return names


def lint(skills_dir=SKILLS_DIR, evals_dir=EVALS_DIR, repo=REPO, only=None, expected=SKILLS_12):
    """Problems as dicts {skill, rule, message}. `expected` = the names the routing table must hold (None = skip)."""
    skills_dir, evals_dir, repo = pathlib.Path(skills_dir), pathlib.Path(evals_dir), pathlib.Path(repo)
    probs = []
    folders = sorted(d.name for d in skills_dir.iterdir() if d.is_dir()) if skills_dir.is_dir() else []

    agents = skills_dir.parent / "AGENTS.md"
    table = []
    if not agents.is_file():
        probs.append(_p("AGENTS.md", "agents", f"{agents} is missing"))
    else:
        text = agents.read_text(encoding="utf-8")
        if CODEWORD not in text:
            probs.append(_p("AGENTS.md", "agents", f"codeword {CODEWORD} is missing (pcb.py probe needs it)"))
        table = routing_table(text)
        if not table:
            probs.append(_p("AGENTS.md", "agents", "no skills routing table under '# SKILLS'"))
        if len(set(table)) != len(table):
            probs.append(_p("AGENTS.md", "agents", "a skill appears twice in the routing table"))
        if expected is not None:
            for n in sorted(set(expected) - set(table)):
                probs.append(_p("AGENTS.md", "routing", f"routing table lacks skill '{n}'"))
            for n in sorted(set(table) - set(expected)):
                probs.append(_p("AGENTS.md", "routing", f"routing table has unknown skill '{n}'"))
    for n in sorted(set(table) - set(folders)):
        probs.append(_p(n, "routing", f"in the AGENTS.md routing table but runtime/skills/{n}/ does not exist"))
    for n in sorted(set(folders) - set(table)):
        probs.append(_p(n, "routing", f"skill folder {n}/ is not in the AGENTS.md routing table"))

    names = sorted(set(folders) | set(table))
    if only is not None:
        if only not in names:
            return [_p(only, "unknown-skill", f"no skill named '{only}' (folders: {', '.join(folders) or 'none'})")]
        names = [only]
    for n in names:
        if n in folders:
            probs += _lint_skill(n, skills_dir / n, repo)
        probs += _lint_evals(n, evals_dir)
    if only is not None:
        probs = [p for p in probs if p["skill"] in (only, "AGENTS.md")]
    return probs


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    only = None
    if "--only" in argv:
        i = argv.index("--only")
        if i + 1 >= len(argv):
            print("usage: lint.py [--only NAME]", file=sys.stderr)
            return 2
        only = argv[i + 1]
    probs = lint(only=only)
    for p in probs:
        print(f"{p['skill']:28} {p['rule']:12} {p['message']}")
    print(f"{len(probs)} problem(s)" if probs else "skills lint: ok")
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main())
