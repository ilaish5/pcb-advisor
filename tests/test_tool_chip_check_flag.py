"""R2 / W22: a tool chip records which script ran and whether it is a check of the design, so the chat never decides it from the label words."""
import agent


def _chips(*labels):
    return agent.real_tools({"stream": True, "runs": [{"label": lab} for lab in labels]})


def test_a_check_script_chip_carries_check_and_the_script():
    chips = _chips("Running python scripts/schematic.py Final", "Running python scripts/checks/board.py --pcb x.PcbDoc")
    assert [(c["script"], c.get("check")) for c in chips] == [("schematic.py", True), ("board.py", True)]


def test_a_document_read_or_search_chip_is_not_a_check():
    chips = _chips("Reading notes.md", "Running python scripts/jlc.py search x", "Running python scripts/export_bom.py")
    assert not any(c.get("check") or "script" in c for c in chips)


def test_a_failed_check_run_is_not_a_check_that_ran():
    chips = agent.real_tools({"stream": True, "runs": [{"label": "Running python scripts/board.py x", "failed": True}]})
    assert not chips[0].get("check")
