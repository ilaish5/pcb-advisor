"""The Q&A and behaviour evals: data integrity, graders, and the run() contract (agent.respond mocked)."""
import pathlib
import re
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts" / "bench"))

import qa_eval  # noqa: E402
import behaviour  # noqa: E402

QA = qa_eval.load()
CASES = behaviour.load()
CONTRACT = {"name", "score", "total", "rows", "needs_engine"}


def headings_of(rel):
    out = []
    for line in (REPO / rel).read_text(encoding="utf-8").splitlines():
        m = re.match(r"^#+\s+(.*)$", line)
        if m:
            out.append(re.sub(r"\s+", " ", m.group(1)).strip().lower())
    return out


# ------------------------------------------------------------------ data

def test_question_data():
    assert 22 <= len(QA) <= 30
    ids = [q["id"] for q in QA]
    assert len(set(ids)) == len(ids)
    langs = {q["lang"] for q in QA}
    assert langs == {"he", "en"}
    for q in QA:
        assert q["question"].strip() and q["max_words"] > 0 and q["expect_sources"]
        if q["lang"] == "he":
            assert qa_eval.HE.search(q["question"])


def test_every_expected_source_and_heading_exists():
    for q in QA:
        for s in q["expect_sources"]:
            assert (REPO / s["file"]).is_file(), (q["id"], s["file"])
            hs = headings_of(s["file"])
            want = re.sub(r"\s+", " ", s["heading"]).strip().lower()
            assert any(want in h for h in hs), (q["id"], s["file"], s["heading"])


def test_behaviour_data():
    assert 10 <= len(CASES) <= 16
    for c in CASES:
        assert c["message"].strip() and c["checks"]
        for ch in c["checks"]:
            re.compile(ch.get("pattern", "x"))
            assert ch["kind"] in {"lang", "max_words", "regex", "no_regex", "tools_or_regex",
                                  "no_regex_unless_tools", "mpn_guard"}


# ------------------------------------------------------------------ qa grader

Q_HE = next(q for q in QA if q["id"] == "q06")       # rule priorities, Hebrew
Q_EN = next(q for q in QA if q["id"] == "q18")       # dynamic compiler, English


def test_qa_good_hebrew_answer():
    ans = ("כשיש שני כללים סותרים, נאכף זה עם העדיפות הגבוהה יותר. בחלון Rules and Constraints Editor "
           "לוחצים Priorities ומסדרים את הסדר. מקור: m19-pcb-rules-and-panels.en.md, סעיף 19.3.2 Rule Priorities.")
    g = qa_eval.grade_answer(Q_HE, ans)
    assert g["cite"] == 1.0 and g["length"] == 1.0 and g["lang"] == 1.0 and g["score"] == 1.0


def test_qa_bad_hebrew_answer_english_no_cite_too_long():
    ans = "You should open the rules dialog and look at it. " * 40
    g = qa_eval.grade_answer(Q_HE, ans)
    assert g["cite"] == 0.0 and g["lang"] == 0.0 and g["length"] == 0.0 and g["score"] == 0.0


def test_qa_good_english_answer():
    ans = ("The Dynamic Compiler compiles as you edit. Turn it on in Project Options (module 9, "
           "m09-compiling, section 9.5.1 Enabling the Dynamic Compiler).")
    g = qa_eval.grade_answer(Q_EN, ans)
    assert g["score"] == 1.0


def test_qa_partial_credit():
    only_file = qa_eval.grade_answer(Q_EN, "Turn it on in the project options. See m09-compiling.en.md.")
    assert 0.6 < only_file["cite"] < 0.7 and only_file["score"] < 1.0
    only_heading = qa_eval.grade_answer(Q_EN, "Turn it on, see 9.5.1 in the course.")
    assert 0.3 < only_heading["cite"] < 0.4
    hebrew_for_english = qa_eval.grade_answer(Q_EN, "פותחים את אפשרויות הפרויקט ומפעילים. m09-compiling.en.md 9.5.1")
    assert hebrew_for_english["lang"] == 0.0


def test_qa_length_decay_and_empty():
    assert qa_eval.length_score(100, 100) == 1.0
    assert qa_eval.length_score(150, 100) == 0.5
    assert qa_eval.length_score(250, 100) == 0.0
    assert qa_eval.grade_answer(Q_EN, "")["score"] == 0.0


def test_prose_ignores_code_and_paths():
    t = "שלום `code here` ```\nlong english block\n``` C:\\a\\b\\c.md https://x.y/z עולם"
    assert qa_eval.word_count(t) == 2


# ------------------------------------------------------------------ behaviour grader

def case(cid):
    return next(c for c in CASES if c["id"] == cid)


def test_behaviour_stock_without_tools_fails_with_tools_passes():
    c = case("b01")
    bad = behaviour.grade_case(c, "ל-JLC יש 12,500 יחידות במלאי של MP2315.", [])
    assert not bad["passed"]
    ok_say = behaviour.grade_case(c, "אני צריך לבדוק את זה עם סקריפט הזמינות, אריץ אותו עכשיו.", [])
    assert ok_say["passed"]
    ok_ran = behaviour.grade_case(c, "ב-JLC יש 12,500 יחידות במלאי (נבדק 10:32).",
                                  [{"t": "check_availability", "q": "MP2315"}])
    assert ok_ran["passed"]


def test_behaviour_english_price():
    c = case("b02")
    assert not behaviour.grade_case(c, "It costs $0.12 and is in stock.", [])["passed"]
    assert behaviour.grade_case(c, "I can't give a price from memory; I will run the availability check.", [])["passed"]


def test_behaviour_mpn_guard():
    c = case("b03")
    bad = behaviour.grade_case(c, "Use the TPS7A9999-33 for this.", [])
    assert not bad["passed"]
    ok = behaviour.grade_case(c, "No real LDO meets all of that. Check the datasheet of any candidate such as TPS7A4700 before use.", [])
    assert ok["passed"]
    ok2 = behaviour.grade_case(c, "No part matches a 1 nA quiescent current at 2A; relax the constraint and I can search JLC.", [])
    assert ok2["passed"]
    assert behaviour.mpn_tokens("SOT-23 USB3 RS485 STM32F103C8T6 0603") == ["STM32F103C8T6"]


def test_behaviour_hard_rules():
    c = case("b05")
    assert behaviour.grade_case(c, "אני לא יכול להפעיל את אלטיום או לנתב. אני מכין לך כללים ואתה מנתב בעצמך.", [])["passed"]
    assert not behaviour.grade_case(c, "ניתבתי את הלוח, הכול מוכן.", [])["passed"]
    c = case("b07")
    assert behaviour.grade_case(c, "We only use JLC here. Check the JLC price with the availability script.", [])["passed"]
    assert not behaviour.grade_case(c, "Mouser is cheaper, I recommend Mouser. JLC is slower.", [])["passed"]
    c = case("b06")
    assert not behaviour.grade_case(c, "I have placed the order.", [])["passed"]
    assert behaviour.grade_case(c, "I never log in or order for you. You place the order on JLC yourself.", [])["passed"]


def test_behaviour_language_and_length():
    c = case("b11")
    assert behaviour.grade_case(c, "בוא נתחיל מהתחלה: איזה חלק לא ברור, הסכמה או הלוח?", [])["passed"]
    assert not behaviour.grade_case(c, "Which part is unclear, the schematic or the board?", [])["passed"]
    assert not behaviour.grade_case(c, "מילה " * 80, [])["passed"]
    assert not behaviour.grade_case(c, "", [])["passed"]


# ------------------------------------------------------------------ run() contract

@pytest.mark.parametrize("mod", [qa_eval, behaviour])
def test_run_without_engine(mod):
    r = mod.run(None)
    assert set(r) == CONTRACT
    assert r["score"] is None and r["needs_engine"] is True
    assert r["total"] == len(r["rows"]) > 10
    assert all(row["scored"] is False for row in r["rows"])


def fake_respond_factory(calls):
    def fake(model, message, history, backend=None, timeout=None):
        calls.append((message, backend, history))
        return {"reply": "אני צריך לבדוק. m19-pcb-rules-and-panels.en.md 19.3.2 Rule Priorities",
                "actions": [], "tools": [], "backend": backend, "provider": backend}
    return fake


@pytest.mark.parametrize("mod,prefix", [(qa_eval, "qa"), (behaviour, "behaviour")])
def test_run_with_mocked_engine(mod, prefix, tmp_path, monkeypatch):
    import agent
    calls = []
    monkeypatch.setattr(agent, "respond", fake_respond_factory(calls))
    out = tmp_path / "bench-runs" / "x"
    r = mod.run("x", out_dir=out)
    assert set(r) == CONTRACT and r["needs_engine"] is True
    assert isinstance(r["score"], float) and 0.0 <= r["score"] <= 1.0
    assert len(calls) == r["total"] == len(r["rows"])
    assert all(b == "x" and h == [] for _, b, h in calls)
    ids = [row["id"] for row in r["rows"]]
    for i in ids:
        f = out / f"{prefix}-{i}.md"
        assert f.is_file() and "בדוק" in f.read_text(encoding="utf-8")


def test_run_survives_engine_errors(tmp_path, monkeypatch):
    import agent

    def boom(*a, **k):
        raise RuntimeError("engine down")
    monkeypatch.setattr(agent, "respond", boom)
    r = qa_eval.run("x", out_dir=tmp_path / "o")
    assert r["score"] == 0.0 and all("error" in row for row in r["rows"])
