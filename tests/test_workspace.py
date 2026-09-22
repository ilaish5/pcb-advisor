"""
Where things live, and what the user configured.

Every other module asks this one for a path, so a mistake here is a mistake
everywhere - and two of these are the kind that only show up on someone else's
machine, with someone else's alphabet.
"""
import json

import pytest

import workspace


# ---------------------------------------------------------------- names

def test_a_hebrew_project_name_survives(home):
    """An allowlist of ASCII turned every Hebrew name into "untitled" - the
    student's own folder, silently renamed, on the first project they made."""
    assert workspace.safe_name("חיישן דלת") == "חיישן-דלת"


def test_a_name_cannot_escape_the_projects_folder(home):
    for bad in ("../../etc/passwd", "a/b", "a\\b", "..", "."):
        safe = workspace.safe_name(bad)
        assert "/" not in safe and "\\" not in safe
        assert safe not in ("", ".", "..")


def test_windows_reserved_characters_are_removed(home):
    assert workspace.safe_name('a<b>c:d"e|f?g*h') == "a-b-c-d-e-f-g-h"


def test_an_empty_name_still_gives_a_folder(home):
    assert workspace.safe_name("") == "untitled"
    assert workspace.safe_name(None) == "untitled"


def test_a_very_long_name_is_bounded(home):
    assert len(workspace.safe_name("x" * 500)) <= 60


# ---------------------------------------------------------------- layering

def test_config_json_holds_only_what_differs_from_the_defaults(home):
    """A three-line config is what lets you inherit future defaults instead of
    freezing today's."""
    workspace.set_value("server.port", 9999)
    written = json.loads((home / "config.json").read_text(encoding="utf-8"))
    assert written == {"server": {"port": 9999}}
    assert workspace.get("server.host") == "127.0.0.1"      # still from defaults


def test_the_environment_wins_over_the_file(home, monkeypatch):
    workspace.set_value("server.port", 9999)
    monkeypatch.setenv("PCB_ADVISOR_PORT", "7777")
    assert workspace.load(reload=True)["server"]["port"] == 7777


def test_a_key_no_default_declares_is_reported(home):
    (home / "config.json").write_text(
        json.dumps({"server": {"prot": 8931}}), encoding="utf-8")
    workspace.load(reload=True)
    assert "server.prot" in workspace.unknown_keys()


def test_your_own_engine_may_be_registered_without_a_warning(home):
    """Provider blocks are open on purpose - the gateway exists to take engines
    this repo has never heard of."""
    (home / "config.json").write_text(json.dumps(
        {"agent": {"providers": {"my_engine": {"enabled": True}}}}), encoding="utf-8")
    workspace.load(reload=True)
    assert workspace.unknown_keys() == []


def test_broken_json_fails_loudly_rather_than_falling_back(home):
    (home / "config.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(SystemExit):
        workspace.load(reload=True)


# ---------------------------------------------------------------- the split

def test_your_work_follows_the_home_and_the_corpus_stays_with_the_install(home):
    """This is the whole reason PCB_ADVISOR_HOME exists: a design is your data,
    the knowledge is part of the program."""
    assert workspace.projects_dir().is_relative_to(home)
    assert workspace.shared_dir().is_relative_to(home)
    assert workspace.cascade_dir().is_relative_to(workspace.REPO)
    assert workspace.ui_dir().is_relative_to(workspace.REPO)


def test_an_absolute_path_in_the_config_is_used_as_it_stands(home, tmp_path):
    elsewhere = tmp_path / "dropbox" / "boards"
    workspace.set_value("workspace.projects_dir", str(elsewhere))
    assert workspace.projects_dir() == elsewhere


# ---------------------------------------------------------------- the map

def test_the_map_given_to_an_engine_is_generated_not_hardcoded(home):
    """A hardcoded map becomes a lie the first time someone moves a folder."""
    workspace.set_value("workspace.projects_dir", "designs")
    places = {p["path"] for p in workspace.describe("demo")["places"]}
    assert any(p.startswith("designs/demo") for p in places)


def test_the_map_never_offers_write_access_to_an_append_only_log(home):
    for place in workspace.describe("demo")["places"]:
        if place["path"].endswith(".jsonl") or "chats" in place["path"]:
            assert place["write"] is False, place["path"]


def test_the_corpus_is_never_writable_from_the_map(home):
    """A constraint invented there is served to every future project, and
    `convention` provenance requires no source at all - so validation would
    never catch it."""
    corpus = [p for p in workspace.describe("demo")["places"]
              if p["path"].endswith("cascade/*.yaml")]
    assert corpus and all(p["write"] is False for p in corpus)


def test_the_map_gives_an_absolute_path_once_the_home_has_moved(home):
    """With PCB_ADVISOR_HOME elsewhere the corpus is no longer under it, and a
    path relative to the wrong root is one the engine cannot open."""
    corpus = next(p for p in workspace.describe("demo")["places"]
                  if p["path"].endswith("cascade/*.yaml"))
    assert corpus["path"].startswith(str(workspace.REPO))
