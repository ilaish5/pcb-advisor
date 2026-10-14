"""The Idea skill's diagram reference: its examples must be accepted by the server, and it carries the default style."""
import pathlib
import re

import store

REPO = pathlib.Path(__file__).resolve().parent.parent
DOC = (REPO / "runtime" / "skills" / "idea-and-requirements" / "references" / "diagram-ops.md").read_text(encoding="utf-8")
SKILL = (REPO / "runtime" / "skills" / "idea-and-requirements" / "SKILL.md").read_text(encoding="utf-8")


def test_every_domain_in_the_examples_is_one_the_server_accepts():
    # "sensor" and "digital" used to be in the examples; the server refuses them ("invalid domain")
    used = set(re.findall(r'"domain":\s*"([^"]*)"', DOC))
    assert used, "the examples name domains"
    assert used <= store.VALID_DOMAINS, sorted(used - store.VALID_DOMAINS)
    listed = re.search(r"optional colour domain: (.+?) \(", DOC).group(1)
    assert set(re.findall(r"`(\w+)`", listed)) <= store.VALID_DOMAINS


def test_the_system_block_diagram_is_the_default_style():
    assert "## Default style: the system block diagram" in DOC
    for must in ("Board frame", "outside", "Colour by domain", "label", "dashed"):
        assert must in DOC, must
    assert "Default layout for a new diagram" in SKILL and "system block diagram" in SKILL
