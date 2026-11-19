"""The activity report zip holds no home path (2026-11-20: run-project.jsonl, doctor.json and JSON-in-JSON paths in turns-log kept the name)."""
import json
import zipfile

import runlog
from test_project_report import story  # noqa: F401  (fixture)
from test_runlog import logs  # noqa: F401  (fixture)

NAME = "zebulon_q"
HOME_FORMS = [
    "C:\\Users\\zebulon_q\\AppData\\Local\\Temp\\drc.txt",
    "C:\\\\Users\\\\zebulon_q\\\\AppData\\\\Local\\\\Temp\\\\drc.txt",
    "C:\\\\\\\\Users\\\\\\\\zebulon_q\\\\\\\\AppData\\\\\\\\agy.EXE",
    "C:/Users/zebulon_q/AppData/Local/agy.EXE",
    "file:///C:/Users/zebulon_q/AppData/x.json",
    "C%3A%5CUsers%5Czebulon_q%5CAppData%5Cx",
    "C%3A%2FUsers%2Fzebulon_q%2Fx",
    "c:\\\\Users\\\\zebulon_q",
]


def test_home_paths_covers_every_written_form():
    for form in HOME_FORMS:
        assert NAME not in runlog.home_paths(f"x {form} y"), form
    assert runlog.home_paths("C:\\Users\\Public\\Documents\\x") == "C:\\Users\\Public\\Documents\\x"      # shared folders stay
    assert runlog.home_paths("C:\\\\Users\\\\Public\\\\x") == "C:\\\\Users\\\\Public\\\\x"


def test_no_file_of_the_project_report_holds_the_user_name(story, logs):  # noqa: F811
    import workspace
    p = workspace.projects_dir() / story
    blob = " ".join(HOME_FORMS)
    row = {"ts": "2026-11-18T10:00:42", "kind": "chat",
           "calls": [{"tool": "Bash", "input": {"command": blob}, "result": json.dumps({"inner": json.dumps({"p": blob})})}]}
    with open(p / "turns-log.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    with open(logs / "run-2026-11-18.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": "2026-11-18T10:01:40.000", "kind": "altium", "commands": ["DRC"], "args": [["DRC", HOME_FORMS[0]]],
                             "project": story, "ok": True, "result": [blob]}) + "\n")
    z = zipfile.ZipFile(runlog.make_report(doctor={"checks": [{"id": "agy", "detail": HOME_FORMS[2], "path": blob}]}, project=story))
    for name in z.namelist():
        assert NAME not in z.read(name).decode("utf-8", errors="replace"), name
    assert "%USERPROFILE%" in z.read("doctor.json").decode()
    assert "%USERPROFILE%" in z.read("logs/run-project.jsonl").decode()
