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
    trace_width_ipc2221,
    via_current,
    voltage_divider,
)


def test_trace_width_ipc2221():
    """IPC-2221 width: exact figure from I = k * dT^0.44 * A^0.725."""
    res = trace_width_ipc2221(1.0, temp_rise_c=10.0, copper_oz=1.0, internal=False)
    a_mil2 = (1.0 / (0.048 * 10.0 ** 0.44)) ** (1 / 0.725)
    exp_mm = a_mil2 / 1.378 * 0.0254
    assert abs(res["value"] - exp_mm) < 1e-3
    assert abs(res["value"] - 0.300) < 0.005
    assert res["width_mm"] == res["value"]
    assert abs(res["width_mil"] - exp_mm / 0.0254) < 0.01
    assert "IPC-2221" in res["source"] and "IPC-2221" in res["formula"]
    assert res["warnings"] == [] and "35 A" in res["limits"]

    # Internal traces need more copper (k = 0.024)
    res_int = trace_width_ipc2221(1.0, temp_rise_c=10.0, copper_oz=1.0, internal=True)
    assert res_int["value"] > res["value"]
    assert res_int["layer"] == "internal"


def test_trace_width_single_implementation():
    """calc.py and trace_width.py return the same number; nothing claims IPC-2152."""
    import trace_width
    for layer in ("external", "internal"):
        for amps, rise, oz in ((1.0, 10.0, 1.0), (3.0, 20.0, 2.0)):
            res = trace_width_ipc2221(amps, rise, oz, internal=(layer == "internal"))
            assert abs(res["value"] - trace_width.width_mm(amps, layer, rise, oz)) < 1e-4
            # IPC-2152 may appear only in the limits, as "not implemented"
            assert "2152" not in res["source"] + res["formula"]
            assert "not implemented" in res["limits"]
    assert not hasattr(sys.modules["calc"], "trace_width_ipc2152")
    assert "2152" not in via_current(0.3)["source"] + via_current(0.3)["formula"]
    assert trace_width_ipc2221(40.0)["warnings"]


def test_via_barrel_is_annulus():
    res = via_current(0.3, temp_rise_c=10.0, plating_thickness_um=25.0)
    d, t = 0.3 / 0.0254, 25.0 / 25.4
    outer, inner = d + 2 * t, d
    import math
    assert abs(res["barrel_area_mil2"] - math.pi / 4 * (outer ** 2 - inner ** 2)) < 0.01
    assert "IPC-2221" in res["source"] and "Estimate" in res["source"]


def test_trace_width_warnings_and_internal():
    assert any("temperature rise" in w for w in trace_width_ipc2221(1.0, temp_rise_c=5.0)["warnings"])
    assert any("temperature rise" in w for w in trace_width_ipc2221(1.0, temp_rise_c=120.0)["warnings"])
    # 30 A at 10 C on 1 oz is far wider than 400 mil
    assert any("400 mil" in w for w in trace_width_ipc2221(30.0)["warnings"])
    # Internal, 1 A, 10 C, 1 oz, k = 0.024. By hand:
    #   10^0.44 = 2.7542; k * that = 0.066101; 1 / 0.066101 = 15.129
    #   A = 15.129^(1/0.725) = 15.129^1.37931 = 42.2 mil^2 (ln 15.129 = 2.7167; x1.37931 = 3.7472; e^ = 42.43)
    #   width = 42.43 / 1.378 mil = 30.79 mil = 0.782 mm
    res = trace_width_ipc2221(1.0, temp_rise_c=10.0, copper_oz=1.0, internal=True)
    assert abs(res["width_mil"] - 30.79) < 0.1
    assert abs(res["value"] - 0.782) < 0.003


def test_via_plating_default_is_sourced_and_flagged():
    res = via_current(0.3)
    assert res["plating_thickness_um"] == 18.0 and "JLCPCB" in res["limits"] and "P1" in res["limits"]
    assert "approximation" in res["limits"]
    res = via_current(0.3, plating_thickness_um=25.0)
    assert "assumption" in res["limits"]


def test_microstrip_range_warning():
    assert microstrip_impedance(0.3, 0.2)["in_range"] is True   # w/h = 1.5
    res = microstrip_impedance(0.01, 0.2)  # w/h = 0.05
    assert res["in_range"] is False and res["warnings"]
    res = microstrip_impedance(0.5, 0.2)   # w/h = 2.5: between 2 and 3 must warn
    assert res["in_range"] is False and any("w/h" in w for w in res["warnings"])
    res = microstrip_impedance(0.3, 0.2, er=20.0)
    assert any("Er" in w for w in res["warnings"])


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
    assert "IPC-2221" in res["source"]
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
        trace_width_ipc2221(-1.0)
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
