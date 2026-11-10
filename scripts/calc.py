"""Engineering calculators for PCB design.

Calculators:
  1. trace_width_ipc2221: IPC-2221 trace width for a current (arithmetic in trace_width.py)
  2. voltage_divider: Resistor divider calculation with E24 standard values
  3. led_resistor: Series current-limiting resistor for LEDs
  4. via_current: Via barrel current carrying capacity
  5. microstrip_impedance: IPC-2141 surface microstrip characteristic impedance

Each function returns a dict containing at minimum:
  {"value": ..., "formula": "...", "source": "..."}
"""
import argparse
import math
import sys

import trace_width

# JLCPCB: "18 um average copper in the barrel" (shared/reference/jlc/pcb-capabilities.en.md, P1)
PLATING_UM_JLC = 18.0

# Standard E24 decade multipliers (1.0 to 9.1)
E24_BASE = [
    1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
    3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1,
]


def _get_e24_values(min_val=10.0, max_val=1000000.0):
    """Generate all E24 resistor values within the given range."""
    values = []
    decade = 1.0
    while decade <= max_val:
        for b in E24_BASE:
            v = round(b * decade, 2 if decade < 10 else 1 if decade < 100 else 0)
            if min_val <= v <= max_val:
                values.append(v)
        decade *= 10.0
    return sorted(values)


def nearest_e24(target: float, round_up: bool = False) -> float:
    """Find the nearest standard E24 resistor value."""
    all_vals = _get_e24_values(min_val=1.0, max_val=10000000.0)
    if round_up:
        candidates = [v for v in all_vals if v >= target]
        return candidates[0] if candidates else all_vals[-1]
    return min(all_vals, key=lambda v: abs(v - target))


def trace_width_ipc2221(
    current_a: float,
    temp_rise_c: float = 10.0,
    copper_oz: float = 1.0,
    internal: bool = False,
) -> dict:
    """Trace width from the IPC-2221 formula I = k * dT^0.44 * A^0.725.

    A in mil^2, k = 0.048 external / 0.024 internal, 1 oz copper = 1.378 mil.
    The arithmetic lives in trace_width.py (the one implementation).
    """
    if current_a <= 0:
        raise ValueError("current_a must be positive")
    if temp_rise_c <= 0:
        raise ValueError("temp_rise_c must be positive")
    if copper_oz <= 0:
        raise ValueError("copper_oz must be positive")

    layer = "internal" if internal else "external"
    width_mm = trace_width.width_mm(current_a, layer, temp_rise_c, copper_oz)
    width_mil = width_mm / 0.0254

    warnings = []
    if current_a > 35.0:
        warnings.append("current above 35 A: outside the IPC-2221 chart range")
    if not 10.0 <= temp_rise_c <= 100.0:
        warnings.append("temperature rise outside 10-100 C: outside the IPC-2221 chart range")
    if width_mil > 400.0:
        warnings.append("width above 400 mil: outside the IPC-2221 chart range")

    return {
        "value": round(width_mm, 4),
        "width_mm": round(width_mm, 4),
        "width_mil": round(width_mil, 2),
        "current_a": float(current_a),
        "temp_rise_c": float(temp_rise_c),
        "copper_oz": float(copper_oz),
        "layer": layer,
        "formula": trace_width.FORMULA,
        "source": trace_width.SOURCE,
        "limits": trace_width.LIMITS,
        "warnings": warnings,
    }


def voltage_divider(
    vin: float,
    vout: float = None,
    r1: float = None,
    r2: float = None,
) -> dict:
    """Calculate voltage divider output or select best E24 standard resistors.

    Formula: Vout = Vin * (R2 / (R1 + R2))
    """
    if vin <= 0:
        raise ValueError("vin must be positive")

    if r1 is not None and r2 is not None:
        if r1 < 0 or r2 <= 0:
            raise ValueError("resistors must be non-negative, R2 > 0")
        calc_vout = vin * (r2 / (r1 + r2))
        ratio = r2 / (r1 + r2)
        return {
            "value": round(calc_vout, 4),
            "vout": round(calc_vout, 4),
            "vin": float(vin),
            "r1": float(r1),
            "r2": float(r2),
            "ratio": round(ratio, 4),
            "formula": "Vout = Vin * (R2 / (R1 + R2))",
            "source": "Ohm's Law / Voltage Divider Equation",
        }

    if vout is not None:
        if vout >= vin:
            raise ValueError("vout must be less than vin for a passive divider")
        target_ratio = vout / vin

        # Search standard E24 combinations (1k to 1M)
        e24_pool = _get_e24_values(min_val=100.0, max_val=1000000.0)
        best_pair = None
        min_err = float("inf")

        # Sample standard decades to find optimal pair
        for cand_r2 in [100.0, 1000.0, 4700.0, 10000.0, 47000.0, 100000.0]:
            ideal_r1 = cand_r2 * (vin - vout) / vout
            cand_r1 = nearest_e24(ideal_r1)
            actual_vout = vin * (cand_r2 / (cand_r1 + cand_r2))
            err = abs(actual_vout - vout)
            if err < min_err:
                min_err = err
                best_pair = (cand_r1, cand_r2, actual_vout)

        r1_best, r2_best, act_vout = best_pair
        err_pct = (abs(act_vout - vout) / vout) * 100.0

        return {
            "value": round(act_vout, 4),
            "vout": round(act_vout, 4),
            "target_vout": float(vout),
            "vin": float(vin),
            "r1": float(r1_best),
            "r2": float(r2_best),
            "error_pct": round(err_pct, 2),
            "formula": "Vout = Vin * (R2 / (R1 + R2))",
            "source": "Ohm's Law / Standard E24 Resistor Pair Selection",
        }

    raise ValueError("Either (r1, r2) or target vout must be provided")


def led_resistor(
    v_supply: float,
    v_forward: float,
    i_forward_ma: float,
) -> dict:
    """Calculate the required series current-limiting resistor for an LED.

    R = (V_supply - Vf) / If
    P = (V_supply - Vf) * If
    """
    if v_supply <= v_forward:
        raise ValueError("v_supply must be greater than v_forward")
    if i_forward_ma <= 0:
        raise ValueError("i_forward_ma must be positive")

    i_a = i_forward_ma / 1000.0
    v_drop = v_supply - v_forward
    r_exact = v_drop / i_a
    r_std = nearest_e24(r_exact, round_up=True)
    power_w = v_drop * i_a

    return {
        "value": round(r_exact, 2),
        "r_exact_ohm": round(r_exact, 2),
        "r_standard_ohm": float(r_std),
        "power_w": round(power_w, 4),
        "v_supply": float(v_supply),
        "v_forward": float(v_forward),
        "i_forward_ma": float(i_forward_ma),
        "formula": "R = (V_supply - Vf) / If; P = (V_supply - Vf) * If",
        "source": "Ohm's Law / LED Series Current Limiting",
    }


def via_current(
    drill_mm: float,
    temp_rise_c: float = 10.0,
    plating_thickness_um: float = PLATING_UM_JLC,
) -> dict:
    """Calculate via barrel current-carrying capacity.

    drill_mm is the finished hole diameter (the size JLCPCB quotes).
    A_barrel = pi * (d + t) * t  (annulus: outer diameter d + 2t, inner d)
    I_max = 0.048 * dT^0.44 * A^0.725  (IPC-2221 external formula applied to the
    barrel copper area; an estimate, IPC-2221 has no via-specific rating)
    """
    if drill_mm <= 0:
        raise ValueError("drill_mm must be positive")
    if temp_rise_c <= 0:
        raise ValueError("temp_rise_c must be positive")
    if plating_thickness_um <= 0:
        raise ValueError("plating_thickness_um must be positive")

    drill_mil = drill_mm / 0.0254
    plating_mil = plating_thickness_um / 25.4
    area_mil2 = math.pi * (drill_mil + plating_mil) * plating_mil

    i_max = 0.048 * (temp_rise_c ** 0.44) * (area_mil2 ** 0.725)

    if plating_thickness_um == PLATING_UM_JLC:
        plating_note = (f"Plating thickness {plating_thickness_um:g} um is the JLCPCB-stated average barrel copper "
                        "(shared/reference/jlc/pcb-capabilities.en.md, source P1).")
    else:
        plating_note = (f"Plating thickness {plating_thickness_um:g} um is an assumption you supplied; JLCPCB states "
                        f"{PLATING_UM_JLC:g} um average barrel copper. Check it against your order.")

    return {
        "value": round(i_max, 3),
        "current_a": round(i_max, 3),
        "barrel_area_mil2": round(area_mil2, 2),
        "drill_mm": float(drill_mm),
        "temp_rise_c": float(temp_rise_c),
        "plating_thickness_um": float(plating_thickness_um),
        "formula": "A_barrel = pi * (d_hole + t_plating) * t_plating; I_max = 0.048 * dT^0.44 * A_barrel^0.725",
        "source": "Estimate: IPC-2221 external formula applied to the via barrel copper area",
        "plating_note": plating_note,
        "limits": "Not a standard via rating; using the external-trace constant (k = 0.048) on a barrel is an approximation. "
                  "Ignores heat sinking into planes and the pads. " + plating_note,
    }


def microstrip_impedance(
    width_mm: float,
    height_mm: float,
    copper_thickness_mm: float = 0.035,
    er: float = 4.4,
) -> dict:
    """Calculate characteristic impedance of a surface microstrip line using IPC-2141.

    Formula: Z0 = (87 / sqrt(Er + 1.41)) * ln(5.98 * h / (0.8 * w + t))
    Commonly stated as valid for 0.1 < w/h < 2.0 and 1 < Er < 15; outside that a warning is returned.
    """
    if width_mm <= 0:
        raise ValueError("width_mm must be positive")
    if height_mm <= 0:
        raise ValueError("height_mm must be positive")
    if er <= 1.0:
        raise ValueError("er must be greater than 1.0")

    denominator = 0.8 * width_mm + copper_thickness_mm
    numerator = 5.98 * height_mm
    if numerator / denominator <= 1.0:
        raise ValueError("Invalid geometry: 5.98 * h must be greater than (0.8 * w + t)")

    z0 = (87.0 / math.sqrt(er + 1.41)) * math.log(numerator / denominator)

    warnings = []
    ratio = width_mm / height_mm
    if not 0.1 < ratio < 2.0:
        warnings.append(f"w/h = {ratio:.2f} is outside the commonly stated range 0.1 to 2.0; "
                        "the result is an extrapolation and may be inaccurate")
    if not 1.0 < er < 15.0:
        warnings.append(f"Er = {er:g} is outside the commonly stated range 1 to 15; "
                        "the result may be inaccurate")

    return {
        "value": round(z0, 2),
        "z0_ohm": round(z0, 2),
        "width_mm": float(width_mm),
        "height_mm": float(height_mm),
        "copper_thickness_mm": float(copper_thickness_mm),
        "er": float(er),
        "formula": "Z0 = (87 / sqrt(Er + 1.41)) * ln(5.98 * h / (0.8 * w + t))",
        "source": "IPC-2141 Section 3.2.1 Surface Microstrip Approximation",
        "w_over_h": round(ratio, 3),
        "in_range": not warnings,
        "warnings": warnings,
    }


def main(argv=None):
    import oscompat
    oscompat.utf8_stdio()
    ap = argparse.ArgumentParser(description="PCB engineering calculators")
    sub = ap.add_subparsers(dest="calc")

    # Trace width
    p_tw = sub.add_parser("trace-width", help="IPC-2221 trace width calculator")
    p_tw.add_argument("amps", type=float, help="Current in amperes")
    p_tw.add_argument("--rise", type=float, default=10.0, help="Allowed temperature rise in C")
    p_tw.add_argument("--oz", type=float, default=1.0, help="Copper weight in oz")
    p_tw.add_argument("--internal", action="store_true", help="Internal conductor layer")

    # Divider
    p_div = sub.add_parser("divider", help="Voltage divider calculator")
    p_div.add_argument("vin", type=float, help="Input voltage (V)")
    p_div.add_argument("vout", type=float, nargs="?", default=None, help="Desired output voltage (V)")
    p_div.add_argument("--r1", type=float, default=None, help="Resistor R1 (ohms)")
    p_div.add_argument("--r2", type=float, default=None, help="Resistor R2 (ohms)")

    # LED
    p_led = sub.add_parser("led", help="LED series current limiting resistor")
    p_led.add_argument("v_supply", type=float, help="Supply voltage (V)")
    p_led.add_argument("v_forward", type=float, help="LED forward voltage Vf (V)")
    p_led.add_argument("i_ma", type=float, help="LED forward current If (mA)")

    # Via
    p_via = sub.add_parser("via", help="Via current capacity calculator")
    p_via.add_argument("drill_mm", type=float, help="Via drill hole diameter (mm)")
    p_via.add_argument("--rise", type=float, default=10.0, help="Allowed temperature rise (C)")
    p_via.add_argument("--plating", type=float, default=PLATING_UM_JLC, help="Plating thickness (um, default: JLCPCB 18)")

    # Microstrip
    p_ms = sub.add_parser("microstrip", help="Surface microstrip characteristic impedance")
    p_ms.add_argument("width_mm", type=float, help="Trace width (mm)")
    p_ms.add_argument("height_mm", type=float, help="Dielectric height (mm)")
    p_ms.add_argument("--er", type=float, default=4.4, help="Dielectric constant Er (default 4.4)")
    p_ms.add_argument("--copper", type=float, default=0.035, help="Copper thickness (mm, default 0.035)")

    args = ap.parse_args(argv)

    if args.calc == "trace-width":
        res = trace_width_ipc2221(args.amps, args.rise, args.oz, args.internal)
        print(f"Trace width (IPC-2221): {res['value']} mm ({res['width_mil']} mil)")
        print(f"Formula: {res['formula']}")
        print(f"Source:  {res['source']}")
        print(f"Limits:  {res['limits']}")
        for w in res["warnings"]:
            print(f"Warning: {w}")
        return 0

    elif args.calc == "divider":
        if args.r1 is not None and args.r2 is not None:
            res = voltage_divider(args.vin, r1=args.r1, r2=args.r2)
            print(f"Vout: {res['value']} V (Vin={res['vin']} V, R1={res['r1']} Ω, R2={res['r2']} Ω)")
        elif args.vout is not None:
            res = voltage_divider(args.vin, vout=args.vout)
            print(f"Recommended E24 pair: R1={res['r1']} Ω, R2={res['r2']} Ω -> Vout={res['value']} V (error {res['error_pct']}%)")
        else:
            print("Error: provide either vout or both --r1 and --r2", file=sys.stderr)
            return 2
        print(f"Formula: {res['formula']}")
        print(f"Source:  {res['source']}")
        return 0

    elif args.calc == "led":
        res = led_resistor(args.v_supply, args.v_forward, args.i_ma)
        print(f"Calculated: {res['value']} Ω | Nearest E24: {res['r_standard_ohm']} Ω | Power: {res['power_w']} W")
        print(f"Formula: {res['formula']}")
        print(f"Source:  {res['source']}")
        return 0

    elif args.calc == "via":
        res = via_current(args.drill_mm, args.rise, args.plating)
        print(f"Via max current: {res['value']} A (drill={res['drill_mm']} mm, rise={res['temp_rise_c']} C)")
        print(f"Formula: {res['formula']}")
        print(f"Source:  {res['source']}")
        return 0

    elif args.calc == "microstrip":
        res = microstrip_impedance(args.width_mm, args.height_mm, args.copper, args.er)
        print(f"Microstrip Z0: {res['value']} Ω (w={res['width_mm']} mm, h={res['height_mm']} mm, Er={res['er']})")
        print(f"Formula: {res['formula']}")
        print(f"Source:  {res['source']}")
        return 0

    else:
        ap.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
