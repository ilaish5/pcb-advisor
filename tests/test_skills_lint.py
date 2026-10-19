"""The skill linter: each rule on a tmp_path pack, then the shipped runtime pack."""
import json
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from skills import lint as L  # noqa: E402

GOOD = """---
name: alpha
description: Does a thing for the student. Use when the student asks "do the thing" (עשה את הדבר).
---

# Alpha

## When to use
- The student wants the thing.
- Not for: beta.

## Steps
1. Open the file.
2. Run the script.

## Scripts
- `python <repo>/scripts/real.py` returns a number.
- (planned, stage I9) later.py - not automated yet; read the files.

## References
- `<repo>/docs/x.md#heading` and `<repo>/docs/x.md|Heading`
- `references/extra.md`

## Pitfalls
- A trap: why it bites; what to check.

## Output
A short list. Source: `{{src:file|heading}}`.
"""

EVALS = {"skill": "alpha", "cases": [
    {"id": "alpha-01", "lang": "en", "question": "q1", "expect_skill": True, "must": [["a", "b"]], "cite": True},
    {"id": "alpha-02", "lang": "he", "question": "q2", "expect_skill": True, "must": [["a"]], "must_not": ["x"], "cite": False},
    {"id": "alpha-03", "lang": "en", "question": "q3", "expect_skill": False, "must": [["a"]], "cite": False},
]}

AGENTS = "KESTREL-31\n\n# SKILLS\n| skill | use it when |\n|---|---|\n| alpha | the thing |\n"


def pack(tmp_path, skill=GOOD, evals=EVALS, agents=AGENTS, name="alpha"):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "real.py").write_text("")
    (repo / "docs").mkdir()
    (repo / "docs" / "x.md").write_text("x")
    sk = repo / "runtime" / "skills"
    if skill is not None:
        (sk / name / "references").mkdir(parents=True)
        (sk / name / "SKILL.md").write_text(skill, encoding="utf-8")
        (sk / name / "references" / "extra.md").write_text("extra\n")
    else:
        sk.mkdir(parents=True)
    if agents is not None:
        (repo / "runtime" / "AGENTS.md").write_text(agents, encoding="utf-8")
    ev = repo / "evals"
    ev.mkdir()
    if evals is not None:
        (ev / "alpha.json").write_text(json.dumps(evals, ensure_ascii=False), encoding="utf-8")
    return repo


def run(repo, **kw):
    return L.lint(repo / "runtime" / "skills", repo / "evals", repo, expected=None, **kw)


def rules(probs):
    return {p["rule"] for p in probs}


def test_good_skill_passes(tmp_path):
    assert run(pack(tmp_path)) == []


def test_problem_shape(tmp_path):
    probs = run(pack(tmp_path, skill=GOOD.replace("name: alpha", "name: zzz")))
    assert probs and set(probs[0]) == {"skill", "rule", "message"}


def test_no_frontmatter(tmp_path):
    assert "frontmatter" in rules(run(pack(tmp_path, skill=GOOD.split("---\n", 2)[2])))


def test_name_must_equal_folder(tmp_path):
    assert "name" in rules(run(pack(tmp_path, skill=GOOD.replace("name: alpha", "name: beta"))))


def test_description_rules(tmp_path):
    assert "description" in rules(run(pack(tmp_path, skill=GOOD.replace("Use when", "Useful if"))))
    long = GOOD.replace("Does a thing", "x" * 600)
    assert "description" in rules(run(pack(tmp_path / "b", skill=long)))
    folded = GOOD.replace("description: Does", "description: >-\n  Does")
    assert "description" in rules(run(pack(tmp_path / "c", skill=folded)))


@pytest.mark.parametrize("heading", L.SECTIONS)
def test_each_section_required(tmp_path, heading):
    probs = run(pack(tmp_path, skill=GOOD.replace(f"## {heading}\n", f"## {heading} x\n")))
    assert any(p["rule"] == "sections" and heading in p["message"] for p in probs)


def test_sections_order(tmp_path):
    swapped = GOOD.replace("## Steps", "## TMP").replace("## Scripts", "## Steps").replace("## TMP", "## Scripts")
    assert "sections" in rules(run(pack(tmp_path, skill=swapped)))


def test_length_limits(tmp_path):
    assert "length" in rules(run(pack(tmp_path, skill=GOOD + "- filler\n" * 150)))
    assert "length" in rules(run(pack(tmp_path / "b", skill=GOOD + "- " + "w" * 170 + "\n")))
    r = pack(tmp_path / "c")
    (r / "runtime" / "skills" / "alpha" / "references" / "extra.md").write_text("l\n" * 201)
    assert "length" in rules(run(r))


def test_repo_reference_must_exist(tmp_path):
    bad = GOOD.replace("`<repo>/docs/x.md#heading`", "`<repo>/docs/nope.md#heading`")
    probs = run(pack(tmp_path, skill=bad))
    assert any(p["rule"] == "reference" and "nope.md" in p["message"] for p in probs)


def test_local_reference_must_exist(tmp_path):
    probs = run(pack(tmp_path, skill=GOOD.replace("references/extra.md", "references/gone.md")))
    assert any(p["rule"] == "reference" and "gone.md" in p["message"] for p in probs)


@pytest.mark.parametrize("bad", ["C:\\Users\\bob"])
def test_forbidden_content(tmp_path, bad):
    assert "forbidden" in rules(run(pack(tmp_path, skill=GOOD + f"- {bad}\n")))


def test_scripts_must_exist_or_be_planned(tmp_path):
    bad = GOOD.replace("scripts/real.py", "scripts/missing.py")
    assert "scripts" in rules(run(pack(tmp_path, skill=bad)))
    planned = GOOD.replace("- `python <repo>/scripts/real.py` returns", "- (planned, stage I4) `scripts/missing.py` returns")
    assert run(pack(tmp_path / "c", skill=planned)) == []


def test_eval_file_required_and_valid(tmp_path):
    assert "evals" in rules(run(pack(tmp_path, evals=None)))
    few = {"skill": "alpha", "cases": EVALS["cases"][:2]}
    assert "evals" in rules(run(pack(tmp_path / "b", evals=few)))


def test_eval_needs_hebrew(tmp_path):
    en = {"skill": "alpha", "cases": [dict(c, lang="en") for c in EVALS["cases"]]}
    assert any("Hebrew" in p["message"] for p in run(pack(tmp_path, evals=en)))


def test_eval_keys_and_ids(tmp_path):
    dup = json.loads(json.dumps(EVALS))
    dup["cases"][1]["id"] = "alpha-01"
    assert any("duplicate" in p["message"] for p in run(pack(tmp_path, evals=dup)))
    odd = json.loads(json.dumps(EVALS))
    odd["cases"][0]["bogus"] = 1
    odd["cases"][1]["lang"] = "fr"
    odd["cases"][2]["must"] = ["notalist"]
    msgs = " ".join(p["message"] for p in run(pack(tmp_path / "b", evals=odd)))
    assert "unknown keys" in msgs and "lang must" in msgs and "must must" in msgs


def test_eval_skill_field_and_bad_json(tmp_path):
    assert "evals" in rules(run(pack(tmp_path, evals=dict(EVALS, skill="other"))))
    r = pack(tmp_path / "b")
    (r / "evals" / "alpha.json").write_text("{nope")
    assert "evals" in rules(run(r))


def test_routing_both_directions(tmp_path):
    probs = run(pack(tmp_path, agents=AGENTS + "| beta | other |\n"))
    assert any(p["rule"] == "routing" and p["skill"] == "beta" for p in probs)
    r = pack(tmp_path / "b")
    (r / "runtime" / "skills" / "orphan").mkdir()
    assert any(p["rule"] == "routing" and p["skill"] == "orphan" for p in run(r))


def test_routing_expected_names(tmp_path):
    r = pack(tmp_path)
    probs = L.lint(r / "runtime" / "skills", r / "evals", r)
    assert any("lacks skill" in p["message"] for p in probs)
    assert len(L.SKILLS_12) == 12


def test_agents_needs_codeword_and_table(tmp_path):
    probs = run(pack(tmp_path, agents=AGENTS.replace("KESTREL-31", "x")))
    assert any("KESTREL-31" in p["message"] for p in probs)
    assert "agents" in rules(run(pack(tmp_path / "b", agents=None)))


def test_only(tmp_path):
    r = pack(tmp_path)
    assert run(r, only="alpha") == []
    assert run(r, only="nope")[0]["rule"] == "unknown-skill"


def test_the_real_routing_table_holds_the_twelve_skills():
    text = (REPO / "runtime" / "AGENTS.md").read_text(encoding="utf-8")
    assert sorted(L.routing_table(text)) == sorted(L.SKILLS_12)
    assert L.CODEWORD in text


def test_main_exit_codes(monkeypatch, capsys):
    monkeypatch.setattr(L, "lint", lambda **kw: [{"skill": "s", "rule": "r", "message": "m"}])
    assert L.main([]) == 1 and "m" in capsys.readouterr().out
    monkeypatch.setattr(L, "lint", lambda **kw: [])
    assert L.main([]) == 0


def test_the_shipped_runtime_pack_is_clean():
    probs = L.lint(REPO / "runtime" / "skills", REPO / "scripts" / "bench" / "skill_evals", REPO)
    assert probs == [], "\n".join(f"{p['skill']}: {p['rule']}: {p['message']}" for p in probs)
