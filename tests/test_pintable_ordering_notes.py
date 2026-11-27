"""R2 / W20: a datasheet note for this ordering code settles a pin whose table cell shows only the default function."""
import pintable

PINS = [("1", "/CS"), ("2", "DO"), ("3", "/WP"), ("4", "GND"), ("5", "DI"), ("6", "CLK"), ("7", "/HOLD"), ("8", "VCC")]
MPN = "W25Q128JVSIQ"


def _page(note, cell5="RSVD(1)"):
    rows = [f"{n}  {cell5 if n == '5' else nm}  I/O" for n, nm in PINS]
    return "Pin description\n\nPin No.  Pin name  Type\n" + "\n".join(rows) + "\n\n" + note + "\n"


def test_the_note_for_this_ordering_code_is_not_a_conflict():
    r = pintable.check([_page(f"Note 1: for the ordering code {MPN}, pin 5 is DI.")], PINS, "SOIC-8", None, mpn=MPN)
    assert r["verify"] == "pass" and any("ordering code" in n for n in r["notes"])


def test_without_the_part_number_the_note_cannot_be_applied():
    r = pintable.check([_page(f"Note 1: for the ordering code {MPN}, pin 5 is DI.")], PINS, "SOIC-8", None)
    assert r["verify"] == "mismatch"


def test_a_note_for_another_ordering_code_is_no_evidence():
    r = pintable.check([_page("Note 1: for the ordering code W25Q64FVSSIG, pin 5 is DI.")], PINS, "SOIC-8", None, mpn=MPN)
    assert r["verify"] == "mismatch"


def test_a_note_naming_another_function_stays_a_conflict_and_names_the_pin():
    r = pintable.check([_page(f"Note 1: for the ordering code {MPN}, pin 5 is DO.")], PINS, "SOIC-8", None, mpn=MPN)
    assert r["verify"] == "mismatch" and "pin 5" in r["issues"][0]


def test_a_true_rename_without_any_note_is_still_found():
    r = pintable.check([_page("Note 1: nothing about this code.", cell5="DQ9")], PINS, "SOIC-8", None, mpn=MPN)
    assert r["verify"] == "mismatch" and "pin 5" in r["issues"][0]
