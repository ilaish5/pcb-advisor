"""Tests for scripts/calc.py engineering calculators."""
import pathlib
import subprocess
import sys
import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from calc import (  # noqa: E402
    led_resistor,
    microstrip_impedance,
    trace_width_ipc2152,
    via_current,
    voltage_divider,
)


def test_trace_width_ipc2152():
    """Verify IPC-2152 trace width calculator returns value, formula, and source."""
    res_ext = trace_width_ipc2152(1.5, temp_rise_c=10.0, copper_oz=1.0, internal=False)
    assert "value" in res_ext
    assert "formula" in res_ext
    assert "source" in res_ext
    assert "IPC-2152" in res_ext["source"]
    assert res_ext["value"] > 0
    assert res_ext["width_mm"] == res_ext["value"]

    # Internal traces need more cross-sectional area (less heat dissipation)
    res_int = trace_width_ipc2152(1.5, temp_rise_c=10.0, copper_oz=1.0, internal=True)
    assert res_int["value"] > res_ext["value"]
    assert "Internal" in res_int["source"]


def test_voltage_divider():
    """Verify voltage divider calculation with given resistors and target Vout."""
    # Direct calculation with known resistors
    res1 = voltage_divider(5.0, r1=1000.0, r2=1000.0)
    assert "value" in res1
    assert "formula" in res1
    assert "source" in res1
    assert abs(res1["value"] - 2.5) < 0.001

    # E24 resistor selection for target Vout
    res2 = voltage_divider(5.0, vout=3.3)
    assert "value" in res2
    assert "formula" in res2
    assert "source" in res2
    assert res2["r1"] > 0
    assert res2["r2"] > 0
    assert abs(res2["value"] - 3.3) < 0.1
    assert res2["error_pct"] < 5.0


def test_led_resistor():
    """Verify LED series resistor and power dissipation calculation."""
    res = led_resistor(5.0, v_forward=2.0, i_forward_ma=20.0)
    assert "value" in res
    assert "formula" in res
    assert "source" in res
    # (5.0 - 2.0) / 0.02 = 150 ohms
    assert abs(res["value"] - 150.0) < 0.01
    assert res["r_standard_ohm"] == 150.0
    # Power = 3.0 * 0.02 = 0.06 W
    assert abs(res["power_w"] - 0.06) < 0.001


def test_via_current():
    """Verify via barrel current capacity calculation."""
    res = via_current(0.3, temp_rise_c=10.0, plating_thickness_um=25.0)
    assert "value" in res
    assert "formula" in res
    assert "source" in res
    assert "IPC-2152" in res["source"] or "IPC-2221" in res["source"]
    assert res["value"] > 1.0  # Typically ~1.5 - 2 A for 0.3mm drill


def test_microstrip_impedance():
    """Verify IPC-2141 microstrip impedance approximation."""
    res = microstrip_impedance(width_mm=0.3, height_mm=0.2, copper_thickness_mm=0.035, er=4.4)
    assert "value" in res
    assert "formula" in res
    assert "source" in res
    assert "IPC-2141" in res["source"]
    # Standard 0.3mm trace on 0.2mm FR4 yields around 50 ohms (~53 ohm)
    assert 45.0 <= res["value"] <= 60.0


def test_calc_invalid_inputs():
    """Verify calculators raise ValueError on non-physical inputs."""
    with pytest.raises(ValueError):
        trace_width_ipc2152(-1.0)
    with pytest.raises(ValueError):
        voltage_divider(5.0, vout=6.0)  # passive divider cannot boost
    with pytest.raises(ValueError):
        led_resistor(2.0, v_forward=3.0, i_forward_ma=20.0)  # supply < Vf
    with pytest.raises(ValueError):
        via_current(-0.3)
    with pytest.raises(ValueError):
        microstrip_impedance(-0.3, 0.2)


def test_calc_cli_subcommands():
    """Verify all 5 subcommands run from CLI and print formula + source."""
    calcs = [
        ["trace-width", "2.0"],
        ["divider", "5.0", "3.3"],
        ["led", "5.0", "2.0", "20"],
        ["via", "0.3"],
        ["microstrip", "0.3", "0.2"],
    ]
    for sub in calcs:
        cmd = [sys.executable, str(REPO / "scripts" / "calc.py")] + sub
        proc = subprocess.run(cmd, capture_output=True, text=True)
        assert proc.returncode == 0, f"Failed CLI command: {sub}: {proc.stderr}"
        assert "Formula:" in proc.stdout
        assert "Source:" in proc.stdout
