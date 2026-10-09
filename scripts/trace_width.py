"""
IPC-2221 trace width.  A deterministic script, not a model answer.

    python3 scripts/trace_width.py 1.5 --layer external --rise 10 --oz 1
"""
import argparse

# IPC-2221 constants: A = (I / (k * dT^b)) ** (1/c),  A in mils^2
K = {"external": 0.048, "internal": 0.024}
B, C = 0.44, 0.725
OZ_TO_MILS = 1.378


def width_mm(current_a, layer="external", rise_c=10.0, oz=1.0):
    area_mils2 = (current_a / (K[layer] * rise_c ** B)) ** (1 / C)
    width_mils = area_mils2 / (oz * OZ_TO_MILS)
    return width_mils * 0.0254


if __name__ == "__main__":
    import oscompat
    oscompat.utf8_stdio()
    ap = argparse.ArgumentParser()
    ap.add_argument("current", type=float, help="amps")
    ap.add_argument("--layer", choices=list(K), default="external")
    ap.add_argument("--rise", type=float, default=10.0, help="allowed temp rise, C")
    ap.add_argument("--oz", type=float, default=1.0, help="copper weight, oz")
    a = ap.parse_args()
    w = width_mm(a.current, a.layer, a.rise, a.oz)
    print(f"{a.current} A, {a.layer}, {a.oz} oz, dT {a.rise} C  ->  {w:.3f} mm "
          f"({w/0.0254:.1f} mil)")
    print("source: IPC-2221 section 6.2")
