import json

import pytest

import gateway
from bench import detectors, incidents, runner


def make_incident(root, n=1, slug="demo", reality="E", target="C", refs=("U1",),
                  keywords=(("ldo", "regulator"), ("5v",)), state_text="U1 is a 5V part\n"):
    d = root / f"{n:02d}-{slug}"
    d.mkdir(parents=True)
    (d / "board.txt").write_text(state_text, encoding="utf-8")
    data = {"id": n, "slug": slug, "title": f"Incident {n}", "pain": ["it burned"],
            "reality": {"stage": reality, "when": "2025", "evidence": ["photo"]},
            "target_stage": target,
            "expect": {"code": "PWR-1", "refs": list(refs), "keywords": [list(g) for g in keywords]},
            "question": "Is this fine?", "state": ["board.txt"], "detector_stage": "I4", "notes": ""}
    (d / "incident.json").write_text(json.dumps(data), encoding="utf-8")
    return d


@pytest.fixture(autouse=True)
def clean_registry(monkeypatch):
    monkeypatch.setattr(detectors, "REGISTRY", [])


def test_validation_names_file_and_key(tmp_path):
    d = make_incident(tmp_path)
    p = d / "incident.json"
    data = json.loads(p.read_text())
    del data["expect"]["code"]
    p.write_text(json.dumps(data))
    with pytest.raises(incidents.IncidentError) as e:
        incidents.load_one(d)
    assert "incident.json" in str(e.value) and "expect.code" in str(e.value)

    data["expect"]["code"] = "X"
    data["target_stage"] = "Z"
    p.write_text(json.dumps(data))
    with pytest.raises(incidents.IncidentError, match="target_stage"):
        incidents.load_one(d)

    data["target_stage"] = "C"
    data["state"] = ["missing.txt"]
    p.write_text(json.dumps(data))
    with pytest.raises(incidents.IncidentError, match="missing.txt"):
        incidents.load_one(d)


def test_load_all_reports_broken_without_stopping(tmp_path):
    make_incident(tmp_path, 1)
    bad = tmp_path / "02-bad"
    bad.mkdir()
    (bad / "incident.json").write_text("{nope")
    found, problems = incidents.load_all(tmp_path)
    assert [i["id"] for i in found] == [1]
    assert len(problems) == 1 and "02-bad" in problems[0]


def test_detector_caught_and_ref_mismatch(tmp_path):
    make_incident(tmp_path, 1, refs=("U1",))
    make_incident(tmp_path, 2, slug="other", refs=("U9",))

    @detectors.register("PWR-1")
    def fake(fixture_dir, incident):
        return [{"code": "PWR-1", "refs": ["U1"], "message": "m", "source": "fake"}]

    items, _ = incidents.load_all(tmp_path)
    res = runner.run_incidents(items)
    assert [r["det"] for r in res["rows"]] == [True, False]
    assert res["rows"][0]["earlier"] is True and res["rows"][1]["earlier"] is False


def test_empty_expect_refs_matches_any(tmp_path):
    make_incident(tmp_path, 1, refs=())
    detectors.register("PWR-1")(lambda d, i: [{"code": "PWR-1", "refs": ["Q5"]}])
    items, _ = incidents.load_all(tmp_path)
    assert runner.run_incidents(items)["rows"][0]["det"] is True


def test_raising_detector_recorded_others_run(tmp_path):
    make_incident(tmp_path, 1)

    @detectors.register("BOOM")
    def boom(d, i):
        raise RuntimeError("kaput")

    detectors.register("PWR-1")(lambda d, i: [{"code": "PWR-1", "refs": ["U1"]}])
    items, _ = incidents.load_all(tmp_path)
    row = runner.run_incidents(items)["rows"][0]
    assert row["det"] is True
    assert any("kaput" in e for e in row["errors"])


def test_not_earlier_when_target_not_before_reality(tmp_path):
    make_incident(tmp_path, 1, reality="C", target="C")
    detectors.register("PWR-1")(lambda d, i: [{"code": "PWR-1", "refs": ["U1"]}])
    items, _ = incidents.load_all(tmp_path)
    assert runner.run_incidents(items)["rows"][0]["earlier"] is False


def test_engine_mode(tmp_path, monkeypatch):
    make_incident(tmp_path / "fx", 1, state_text="SECRET-STATE-LINE\n")
    make_incident(tmp_path / "fx", 2, slug="two")
    items, _ = incidents.load_all(tmp_path / "fx")
    seen = []
    answers = iter(["The LDO is fed 5V.", "just fine"])

    def fake_route(request, name=None):
        seen.append((request, name))
        return gateway.Result(text=next(answers), provider="claude_code")

    monkeypatch.setattr(gateway, "route", fake_route)
    res = runner.run_incidents(items, engine="claude_code", repo=tmp_path,
                               runs_dir=tmp_path / "runs", today="2026-01-02")
    assert [r["engine"] for r in res["rows"]] == [True, False]
    prompt = seen[0][0].prompt
    assert "SECRET-STATE-LINE" in prompt and "board.txt" in prompt
    assert "Is this fine?" in prompt and "briefly" in prompt
    assert "regulator" not in prompt.lower()          # keywords never leak into the prompt
    assert seen[0][0].options["add_dirs"] == [str(tmp_path)]
    saved = tmp_path / "runs" / "2026-01-02-claude_code" / "01-demo.md"
    assert saved.is_file() and "LDO is fed 5V" in saved.read_text(encoding="utf-8")


def test_engine_error_recorded(tmp_path, monkeypatch):
    make_incident(tmp_path / "fx", 1)
    items, _ = incidents.load_all(tmp_path / "fx")
    monkeypatch.setattr(gateway, "route", lambda r, n=None: gateway.Result(error="down"))
    row = runner.run_incidents(items, engine="claude_code", runs_dir=tmp_path / "r")["rows"][0]
    assert row["engine"] is False and "down" in row["errors"][0]


def test_keyword_groups():
    g = [["ldo", "regulator"], ["5v"]]
    assert runner.keywords_hit("An LDO at 5V", g)
    assert not runner.keywords_hit("An LDO", g)
    assert not runner.keywords_hit("5V only", g)


def test_report_and_history_across_runs(tmp_path):
    make_incident(tmp_path / "fx", 1)
    md = tmp_path / "docs" / "BENCHMARK.md"
    r1 = runner.run(fixtures=tmp_path / "fx", out_md=md, now="2026-01-01 10:00")
    r2 = runner.run(fixtures=tmp_path / "fx", out_md=md, now="2026-01-02 10:00")
    text = md.read_text(encoding="utf-8")
    assert "deterministic caught 0/1, engine not run, earlier than reality 0" in text
    assert "| 1 | Incident 1 |" in text
    hist = [l for l in text.split("## History", 1)[1].splitlines() if l.startswith("- ")]
    assert len(hist) == 2 and "2026-01-01" in hist[0] and "2026-01-02" in hist[1]
    assert r2["summary"] == r1["summary"]


def test_evals_missing_modules_are_fine(tmp_path, monkeypatch):
    make_incident(tmp_path / "fx", 1)
    monkeypatch.setattr(runner, "EVAL_MODULES", ("no_such_eval",))
    res = runner.run(fixtures=tmp_path / "fx", out_md=tmp_path / "B.md", evals=True)
    assert res["evals"] == []


def test_evals_summary_included(tmp_path, monkeypatch):
    make_incident(tmp_path / "fx", 1)
    monkeypatch.setattr(runner, "run_evals", lambda p: [
        {"name": "qa", "score": 0.5, "total": 4, "rows": [], "needs_engine": True}])
    res = runner.run(fixtures=tmp_path / "fx", out_md=tmp_path / "B.md", evals=True)
    assert "- qa: score 0.50 over 4 (needs an engine)" in res["text"]


def test_missing_fixtures_folder_is_reported(tmp_path):
    res = runner.run(fixtures=tmp_path / "nope", out_md=tmp_path / "B.md")
    assert res["rows"] == [] and res["problems"]
