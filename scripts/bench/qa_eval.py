"""Altium Q&A eval (PLAN.md section 5): ~25 real student-style "how do I do X in Altium" questions.

Contract (used by the bench runner):
    run(provider: str | None, out_dir=None) -> {"name", "score", "total", "rows", "needs_engine"}
    provider None  -> nothing is asked; score None, rows list the cases (scored False).
    provider "x"   -> each question goes through agent.respond(model, question, history=[], backend=provider)
                      (the normal advisor path, with the runtime pack synced), the answer is graded and saved to
                      <out_dir>/qa-<id>.md. Default out_dir: local/bench-runs/<date>-<provider>/.

Grading, per answer (all deterministic, no model involved):

    cite   = max over the expected sources of  (file_hit + 0.5 * heading_hit) / 1.5      in 0..1
             file_hit    1 if the answer names the expected file: full path, file name, or stem
                         (e.g. "m19-pcb-rules-and-panels", with or without ".en"/".he"/".md").
             heading_hit 1 if the answer contains the heading text (case/space-insensitive, numbering
                         optional: "Rule Priorities" counts) or its section number ("19.3.2", >= 2 parts, or
                         "[17]" style for the unit files). Heading credit does not need the file hit.
    length = 1 if words <= max_words, then falls linearly to 0 at 2 * max_words.
    lang   = 1 if the prose is in the question's language, else 0. Prose = answer without code blocks, inline
             code, URLs and paths. Hebrew question: Hebrew letters >= 40% of (Hebrew + Latin) letters
             (technical terms stay English, so not 50%). English question: Hebrew letters <= 10%.

    score_of_answer = 0.5 * cite + 0.25 * length + 0.25 * lang        (an empty/error answer scores 0)
    score           = mean over all questions                          (errors count as 0, never skipped)

Limits: citation is a string match, so an answer that name-drops a file without using it still scores; it
measures "does the product point at the right course place", not whether the steps are right.
"""
import datetime
import json
import os
import pathlib
import re
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SCRIPTS = HERE.parent
REPO = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

DATA = HERE / "qa" / "questions.json"
DOCS = REPO / "local" / "bench-runs"

HE = re.compile(r"[֐-׿]")
LATIN = re.compile(r"[A-Za-z]")


# ------------------------------------------------------------------ shared helpers (behaviour.py reuses them)

def load(path=None):
    return json.loads(pathlib.Path(path or DATA).read_text(encoding="utf-8"))


def prose(text):
    """The answer minus code blocks, inline code, URLs and file paths."""
    t = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    t = re.sub(r"`[^`]*`", " ", t)
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"(?:[A-Za-z]:)?[\w.\-]*[/\\][\w./\\\-]+", " ", t)
    t = re.sub(r"\b[\w\-]+(?:\.(?:en|he))?\.md\b", " ", t)       # cited file names are not prose
    t = re.sub(r"\bm\d\d-[\w\-]+", " ", t)                       # nor are module stems
    return t


def hebrew_share(text):
    p = prose(text)
    he, la = len(HE.findall(p)), len(LATIN.findall(p))
    return he / (he + la) if he + la else 0.0


def lang_ok(text, want):
    share = hebrew_share(text)
    return share >= 0.4 if want == "he" else share <= 0.1


def word_count(text):
    return len(re.findall(r"\S+", prose(text)))


def _norm(s):
    return re.sub(r"\s+", " ", s.lower().replace("\\", "/")).strip()


def file_hit(answer, rel):
    a = _norm(answer)
    name = rel.rsplit("/", 1)[-1]
    stem = re.sub(r"\.(en|he)\.md$|\.md$", "", name)
    return any(c.lower() in a for c in (rel, name, stem))


def heading_hit(answer, heading):
    a = _norm(answer)
    h = heading.strip()
    if not h:
        return False
    if _norm(h) in a:
        return True
    m = re.match(r"^(\d+(?:\.\d+)+)\s+(.*)$", h)            # "19.3.2 Rule Priorities"
    if m:
        return m.group(1) in a or (len(m.group(2)) > 6 and _norm(m.group(2)) in a)
    m = re.match(r"^\[(\d+)\]\s+(.*)$", h)                  # "[17] Calculating ..."
    if m:
        return (len(m.group(2)) > 6 and _norm(m.group(2)) in a)
    return False


def cite_score(answer, sources):
    best = 0.0
    for s in sources:
        v = (1.0 * file_hit(answer, s["file"]) + 0.5 * heading_hit(answer, s["heading"])) / 1.5
        best = max(best, v)
    return best


def length_score(words, max_words):
    if max_words <= 0 or words <= max_words:
        return 1.0
    return max(0.0, 1.0 - (words - max_words) / max_words)


def grade_answer(case, answer):
    """-> dict with cite, length, lang, words, score (0..1)."""
    if not (answer or "").strip():
        return {"cite": 0.0, "length": 0.0, "lang": 0.0, "words": 0, "score": 0.0}
    words = word_count(answer)
    cite = cite_score(answer, case["expect_sources"])
    length = length_score(words, case["max_words"])
    lang = 1.0 if lang_ok(answer, case["lang"]) else 0.0
    return {"cite": round(cite, 3), "length": round(length, 3), "lang": lang, "words": words,
            "score": round(0.5 * cite + 0.25 * length + 0.25 * lang, 3)}


def resolve_out_dir(out_dir, provider):
    if out_dir:
        d = pathlib.Path(out_dir)
    else:
        d = DOCS / f"{datetime.date.today().isoformat()}-{provider}"
    d.mkdir(parents=True, exist_ok=True)
    return d


class Session:
    """A throwaway workspace (PCB_ADVISOR_HOME in a temp dir) with one demo project, so the real advisor
    path runs without touching projects/. Use as a context manager; ask() returns agent.respond's dict."""

    def __init__(self, provider):
        self.provider = provider
        self.tmp = None
        self.old_env = None
        self.project = None

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="pcb-eval-")
        self.old_env = os.environ.get("PCB_ADVISOR_HOME")
        os.environ["PCB_ADVISOR_HOME"] = self.tmp.name
        try:
            import workspace
            if hasattr(workspace, "_cache"):
                workspace._cache = None
            import project
            self.project = project.create("eval-demo", title="Eval demo")
        except BaseException:           # project template missing etc: the eval still runs without a project
            self.project = None
        return self

    def __exit__(self, *exc):
        if self.old_env is None:
            os.environ.pop("PCB_ADVISOR_HOME", None)
        else:
            os.environ["PCB_ADVISOR_HOME"] = self.old_env
        try:
            import workspace
            if hasattr(workspace, "_cache"):
                workspace._cache = None
        except Exception:
            pass
        self.tmp.cleanup()

    def model(self):
        return {"project": self.project, "bom": [], "sheets": [], "proposals": [], "sources": [],
                "requirements": None, "totals": None, "idea": {}}

    def ask(self, message):
        import agent
        import runtime_pack
        runtime_pack.sync()
        return agent.respond(self.model(), message, history=[], backend=self.provider)


def save_answer(out_dir, prefix, case, res, grade):
    text = (res or {}).get("reply") or ""
    head = (f"# {prefix}-{case['id']}\n\n**Question ({case['lang']}):** {case['question']}\n\n"
            f"**Grade:** {json.dumps(grade, ensure_ascii=False)}\n\n")
    tools = (res or {}).get("tools")
    if tools:
        head += f"**Tools:** {json.dumps(tools, ensure_ascii=False)}\n\n"
    head += "---\n\n"
    (out_dir / f"{prefix}-{case['id']}.md").write_text(head + text + "\n", encoding="utf-8")


# ------------------------------------------------------------------ entry point

def run(provider=None, out_dir=None, cases=None):
    cases = cases if cases is not None else load()
    base = {"name": "qa", "total": len(cases), "needs_engine": True}
    if not provider:
        rows = [{"id": c["id"], "lang": c["lang"], "question": c["question"], "scored": False} for c in cases]
        return {**base, "score": None, "rows": rows}
    out = resolve_out_dir(out_dir, provider)
    rows = []
    with Session(provider) as s:
        for c in cases:
            row = {"id": c["id"], "lang": c["lang"], "question": c["question"], "scored": True}
            try:
                res = s.ask(c["question"])
                if res.get("error") or res.get("reply") is None:
                    grade = {"cite": 0.0, "length": 0.0, "lang": 0.0, "words": 0, "score": 0.0}
                    row["error"] = str(res.get("reply"))[:200]
                else:
                    grade = grade_answer(c, res["reply"])
                save_answer(out, "qa", c, res, grade)
            except Exception as exc:  # one broken case must not kill the run
                grade = {"cite": 0.0, "length": 0.0, "lang": 0.0, "words": 0, "score": 0.0}
                row["error"] = f"{type(exc).__name__}: {exc}"[:200]
            row.update(grade)
            rows.append(row)
    score = sum(r["score"] for r in rows) / len(rows) if rows else None
    return {**base, "score": round(score, 3) if score is not None else None, "rows": rows}


if __name__ == "__main__":
    r = run(sys.argv[1] if len(sys.argv) > 1 else None)
    print(json.dumps({k: v for k, v in r.items() if k != "rows"}, indent=1))
    for row in r["rows"]:
        print(row)
