"""
The guards on the knowledge itself.

These run the real validators against the real corpus, and then against
deliberately broken copies of it - because a validator that has never rejected
anything is indistinguishable from one that cannot.
"""
import pathlib
import sys

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import validate_cascade  # noqa: E402


CASCADES = sorted((REPO / "cascade").glob("*.yaml"))


@pytest.fixture
def broken(tmp_path, monkeypatch):
    """A copy of the corpus with one thing changed, validated on its own."""
    import workspace

    def make(edit):
        d = tmp_path / "cascade"
        d.mkdir(exist_ok=True)
        for src in CASCADES:
            (d / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        edit(d)
        monkeypatch.setattr(workspace, "cascade_dir", lambda: d)
        producible = validate_cascade.producible_blocks()
        out = []
        for path in sorted(d.glob("*.yaml")):
            errors, _, _, _ = validate_cascade.check(path, producible)
            out.extend(errors)
        return out

    return make


# ---------------------------------------------------------------- as shipped

@pytest.mark.parametrize("path", CASCADES, ids=lambda p: p.name)
def test_the_shipped_corpus_validates(path):
    producible = validate_cascade.producible_blocks()
    errors, _, _, _ = validate_cascade.check(path, producible)
    assert errors == []


def test_every_rule_declares_how_it_is_known():
    for path in CASCADES:
        cas = yaml.safe_load(path.read_text(encoding="utf-8"))
        for node in cas.get("nodes", []):
            for opt in node.get("options", []) or []:
                for lock in opt.get("locks", []) or []:
                    assert lock.get("provenance") in validate_cascade.VALID, lock["id"]


def test_no_rule_claims_a_document_that_cannot_be_fetched():
    """Eleven rules used to cite "regulator datasheet" and "ADC datasheet".
    Those are not documents. They are instructions to read whichever part the
    student chose, and they now say so."""
    for path in CASCADES:
        cas = yaml.safe_load(path.read_text(encoding="utf-8"))
        for node in cas.get("nodes", []):
            for opt in node.get("options", []) or []:
                for lock in opt.get("locks", []) or []:
                    if lock.get("provenance") == "datasheet":
                        assert (lock.get("source") or {}).get("url"), lock["id"]


# ---------------------------------------------------------------- the guards

def test_a_role_noun_dressed_as_a_citation_is_rejected(broken):
    def edit(d):
        p = d / "power.yaml"
        p.write_text(p.read_text().replace(
            "provenance: check_your_part", "provenance: datasheet", 1), encoding="utf-8")
    assert any("needs source.url" in e for e in broken(edit))


def test_a_computed_rule_without_its_arithmetic_is_rejected(broken):
    def edit(d):
        p = d / "power.yaml"
        p.write_text(p.read_text().replace(
            'calculation: "1 mA x 8760 h = 8.76 Ah per year"', "", 1), encoding="utf-8")
    assert any("needs a `calculation`" in e for e in broken(edit))


def test_a_check_your_part_rule_that_cites_a_document_is_rejected(broken):
    """If you have the document, it is a citation and must be verifiable."""
    def edit(d):
        p = d / "power.yaml"
        p.write_text(p.read_text().replace(
            'source: {doc: "regulator datasheet", locator: "Electrical Characteristics - Dropout Voltage"}',
            'source: {doc: "regulator datasheet", locator: "Dropout", url: "http://e.com/x.pdf"}',
            1), encoding="utf-8")
    assert any("must not cite a document" in e for e in broken(edit))


def test_a_rule_needing_a_part_nothing_can_place_is_rejected(broken):
    def edit(d):
        p = d / "analog.yaml"
        p.write_text(p.read_text().replace("needs_block: U_REG", "needs_block: U_NOPE", 1),
                     encoding="utf-8")
    assert any("no cascade can put on a board" in e for e in broken(edit))


def test_a_dangling_dependency_is_rejected(broken):
    def edit(d):
        p = d / "power.yaml"
        p.write_text(p.read_text().replace(
            "depends_on: [req.source, req.vout, req.iload]",
            "depends_on: [req.source, req.nope]", 1), encoding="utf-8")
    assert any("depends_on unknown node" in e for e in broken(edit))


def test_a_duplicate_rule_id_is_rejected(broken):
    def edit(d):
        p = d / "power.yaml"
        p.write_text(p.read_text().replace("- id: pwr.iq", "- id: pwr.in.range", 1),
                     encoding="utf-8")
    assert any("duplicate constraint id" in e for e in broken(edit))
