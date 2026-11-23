"""The real round trip to a live Altium Designer: the only tests here that start X2.EXE (every other bridge test fakes it).

Marked `altium` and `windows`: skipped unless os.name == "nt" and PCB_ADVISOR_ALTIUM=1 (tests/conftest.py). On the Altium PC:
    set PCB_ADVISOR_ALTIUM=1
    python -m pytest -q -m "windows or altium" < NUL
"""
import pytest

from altium import bridge

pytestmark = [pytest.mark.windows, pytest.mark.altium]


def test_altium_is_found_and_the_bridge_script_stages():
    st = bridge.status()
    assert st["exe"].upper().endswith("X2.EXE"), st
    assert st["script"] and not st["error"], st


def test_a_ping_comes_back_from_the_running_script():
    log = bridge.run_commands([("PING",)], start_timeout=120)     # a cold start of Altium takes a while
    assert any("ping" in str(line).lower() for line in log), log
