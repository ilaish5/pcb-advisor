"""An applied action whose result carries a warning is stored with it (rec["warned"]) so the chat shows an amber chip."""
import serve


def test_warning_forms_are_found():
    assert serve.warning_of("altium.place_pcb: 11 parts placed (2 warnings: C3 far; J1 turned)") == "C3 far; J1 turned"
    assert serve.warning_of("jlc.gerber_zip:x.zip (11 files, missing Board outline)").startswith("missing Board outline")
    assert "does not match" in serve.warning_of("jlc.gerber_zip:x.zip (11 files). WARNING: The board does not match")
    assert serve.warning_of("library.build: 3 of 3 lines built (1 with issues)")
    assert serve.warning_of("x: Could not read the outline").startswith("Could not")


def test_clean_results_have_none():
    for a in ("idea.describe", "library.add:R1", "altium.run_outjob: 22 files", "altium.route_pcb: 9 nets routed, saved"):
        assert serve.warning_of(a) == ""
    assert serve.warned_map(["idea.describe", "a: x (warnings: y)"]) == {"a: x (warnings: y)": "y"}
