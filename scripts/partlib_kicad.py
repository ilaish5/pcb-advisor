"""KiCad's official footprint and 3D libraries as the source for standard packages.

The footprints (kicad-footprints) and STEP models (kicad-packages3D) come from KiCad's GitLab, no login.
They are licensed CC-BY-SA 4.0 with the KiCad library exception (the design exception: boards made with
them may be used and distributed under any license). Same method as the kiln board's fetch_kicad3d.py.
Downloads are untrusted data and are cached under projects/<name>/library/kicad/<Library>/.
"""
import re
import urllib.parse
import urllib.request

BASE = "https://gitlab.com/kicad/libraries"
MAX_BYTES = 30_000_000
METRIC = {"0402": "0402_1005Metric", "0603": "0603_1608Metric", "0805": "0805_2012Metric", "1206": "1206_3216Metric"}
CHIP_LIB = {"C": ("Capacitor_SMD", "C"), "L": ("Inductor_SMD", "L"), "FB": ("Inductor_SMD", "L"),
            "LED": ("LED_SMD", "LED"), "D": ("Diode_SMD", "D"), "TVS": ("Diode_SMD", "D"), "ZD": ("Diode_SMD", "D"),
            "F": ("Fuse", "Fuse")}
FIXED = {"SOD-123": ("Diode_SMD", "D_SOD-123"), "SOD-323": ("Diode_SMD", "D_SOD-323"),
         "SOT-23-3": ("Package_TO_SOT_SMD", "SOT-23"), "SOT-23-5": ("Package_TO_SOT_SMD", "SOT-23-5"),
         "SOT-23-6": ("Package_TO_SOT_SMD", "SOT-23-6"), "SOT-223": ("Package_TO_SOT_SMD", "SOT-223-3_TabPin2"),
         "SOIC-8": ("Package_SO", "SOIC-8_3.9x4.9mm_P1.27mm"), "SOIC-14": ("Package_SO", "SOIC-14_3.9x8.7mm_P1.27mm"),
         "SOIC-16": ("Package_SO", "SOIC-16_3.9x9.9mm_P1.27mm"), "TSSOP-8": ("Package_SO", "TSSOP-8_4.4x3mm_P0.65mm"),
         "TSSOP-14": ("Package_SO", "TSSOP-14_4.4x5mm_P0.65mm"), "TSSOP-16": ("Package_SO", "TSSOP-16_4.4x5mm_P0.65mm"),
         "TSSOP-20": ("Package_SO", "TSSOP-20_4.4x6.5mm_P0.65mm")}
NAME_RE = re.compile(r"^[A-Za-z0-9_.+-]{1,80}$")


def kicad_footprint(key, prefix):
    """(library, footprint name) in KiCad's official library for a canonical package key, or None."""
    if key in METRIC:
        lib, letter = CHIP_LIB.get(prefix, ("Resistor_SMD", "R"))
        return lib, f"{letter}_{METRIC[key]}" if letter != "Fuse" else f"Fuse_{METRIC[key]}"
    m = re.fullmatch(r"PinHeader-(\d)x(\d+)_P2\.54mm", key)
    if m:
        return "Connector_PinHeader_2.54mm", f"PinHeader_{m.group(1)}x{m.group(2)}_P2.54mm_Vertical"
    return FIXED.get(key)


def _get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("file too large")
    return data


def fetch_kicad(lib, name, dest):
    """Download <lib>/<name>.kicad_mod and its STEP into dest. Returns (ok, message); a missing STEP is not a failure."""
    if not (NAME_RE.match(lib) and NAME_RE.match(name)):
        return False, "bad footprint name"
    dest.mkdir(parents=True, exist_ok=True)
    for repo, path, ext in (("kicad-footprints", f"{lib}.pretty/{name}.kicad_mod", ".kicad_mod"),
                            ("kicad-packages3D", f"{lib}.3dshapes/{name}.step", ".step")):
        url = f"{BASE}/{repo}/-/raw/master/{urllib.parse.quote(path)}"
        try:
            (dest / (name + ext)).write_bytes(_get(url))
        except Exception as e:                       # network, 404, too large: reported, never worked around
            if ext == ".kicad_mod":
                return False, f"{type(e).__name__}: {str(e)[:100]}"
    return True, "downloaded"
