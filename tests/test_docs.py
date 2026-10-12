"""Tests verifying documentation freshness and UI localization consistency."""
import pathlib
import re
import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent

DOC_FILES = (
    "README.md",
    "docs/ARCHITECTURE.md",
    "runtime/AGENTS.md",
)


@pytest.mark.parametrize("doc_path", DOC_FILES)
def test_scripts_named_in_docs_exist(doc_path):
    target = REPO / doc_path
    assert target.is_file(), f"{doc_path} must exist"
    text = target.read_text(encoding="utf-8")
    scripts = sorted(set(re.findall(r"scripts/[\w/.-]+\.py", text)))
    assert len(scripts) > 0, f"Expected {doc_path} to reference at least one script"
    missing = [s for s in scripts if not (REPO / s).is_file()]
    assert not missing, f"{doc_path} references non-existent script(s): {missing}"


def test_ui_index_html_no_hebrew_outside_comments():
    html_path = REPO / "ui" / "index.html"
    assert html_path.is_file(), "ui/index.html must exist"
    content = html_path.read_text(encoding="utf-8")
    # Strip HTML comments: <!-- ... -->
    clean_html = re.sub(r"<!--.*?-->", "", content, flags=re.S)
    hebrew_matches = re.findall(r"[\u0590-\u05FF]+", clean_html)
    assert not hebrew_matches, f"Found Hebrew text in ui/index.html outside comments: {hebrew_matches}"
