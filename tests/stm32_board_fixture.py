"""Synthetic STM32 board for the offline end-to-end test (no Altium): ~60 parts, 2 layers, 50 x 40 mm.
Builds the netlist parts + footprint models used by layout.plan_placement and, from a placement plan, the saved-board dict
(pads with absolute positions) that route.plan_routes and layout.verify_layout read. Generic: nothing under projects/."""
from altium import layout

MIL = 0.0254
OUTLINE = [0.0, 0.0, 50.0, 40.0]


def fp(name, pads):
    """pads: [(name, x_mm, y_mm, w_mm, h_mm)]"""
    return {"name": name, "pads": [{"name": n, "x": x / MIL, "y": y / MIL, "xsize": w / MIL, "ysize": h / MIL, "layer": 1}
                                   for n, x, y, w, h in pads]}


def _lqfp48():
    """7 x 7 mm body, 0.5 mm pitch, pads 1.5 x 0.28 mm; pin 1 top left, counter-clockwise (y up): left 1-12, bottom 13-24, right 25-36, top 37-48."""
    pads = []
    for k in range(12):
        o = -2.75 + 0.5 * k
        pads.append((str(1 + k), -4.2, -o, 1.5, 0.28))
        pads.append((str(13 + k), o, -4.2, 0.28, 1.5))
        pads.append((str(25 + k), 4.2, o, 1.5, 0.28))
        pads.append((str(37 + k), -o, 4.2, 0.28, 1.5))
    return fp("LQFP48", pads)


_USBC_ROW = [("A1B12", -3.2, 0.6), ("A4B9", -2.4, 0.6), ("B8", -1.75, 0.3), ("A5", -1.25, 0.3), ("B7", -0.75, 0.3), ("A6", -0.25, 0.3),
             ("A7", 0.25, 0.3), ("B6", 0.75, 0.3), ("A8", 1.25, 0.3), ("B5", 1.75, 0.3), ("B4A9", 2.4, 0.6), ("B1A12", 3.2, 0.6)]
_USBC_NET = ["GND", "VBUS", "SBU2", "CC1", "USB_DM", "USB_DP", "USB_DM", "USB_DP", "SBU1", "CC2", "VBUS", "GND"]
_USBC_NAME = ["GND", "VBUS", "SBU2", "CC1", "D-", "D+", "D-", "D+", "SBU1", "CC2", "VBUS", "GND"]

FPS = {
    "LQFP48": _lqfp48(),
    "USBC16": fp("USBC16", [(n, x, 0.0, w, 1.15) for n, x, w in _USBC_ROW] +
                 [("S1", -4.3, -1.6, 1.0, 1.6), ("S2", 4.3, -1.6, 1.0, 1.6), ("S3", -4.3, -5.4, 1.0, 1.6), ("S4", 4.3, -5.4, 1.0, 1.6)]),
    "XTAL3225": fp("XTAL3225", [("1", -1.1, 0, 1.4, 1.9), ("2", 1.1, 0, 1.4, 1.9)]),
    "SOT223": fp("SOT223", [("1", -2.3, 3.15, 0.95, 1.5), ("2", 0.0, 3.15, 0.95, 1.5), ("3", 2.3, 3.15, 0.95, 1.5), ("4", 0.0, -3.15, 3.3, 2.1)]),
    "HDR1X4": fp("HDR1X4", [(str(i + 1), 0, -1.905 + 1.27 * i, 1.7, 1.0) for i in range(4)]),
    "HDR1X5": fp("HDR1X5", [(str(i + 1), 0, -2.54 + 1.27 * i, 1.7, 1.0) for i in range(5)]),
    "C0603": fp("C0603", [("1", -0.75, 0, 0.8, 0.9), ("2", 0.75, 0, 0.8, 0.9)]),
    "C0402": fp("C0402", [("1", -0.5, 0, 0.6, 0.6), ("2", 0.5, 0, 0.6, 0.6)]),
    "R0402": fp("R0402", [("1", -0.5, 0, 0.6, 0.6), ("2", 0.5, 0, 0.6, 0.6)]),
    "LED0603": fp("LED0603", [("1", -0.8, 0, 0.8, 0.9), ("2", 0.8, 0, 0.8, 0.9)]),
    "FB0603": fp("FB0603", [("1", -0.8, 0, 0.8, 0.9), ("2", 0.8, 0, 0.8, 0.9)]),
    "SW": fp("SW", [("1", -2.0, 0, 1.0, 1.4), ("2", 2.0, 0, 1.0, 1.4)]),
}

# STM32F103C8T6 (LQFP-48) pin names, pin 1..48
_MCU_NAMES = ["VBAT", "PC13", "PC14-OSC32_IN", "PC15-OSC32_OUT", "PD0-OSC_IN", "PD1-OSC_OUT", "NRST", "VSSA", "VDDA", "PA0", "PA1", "PA2",
              "PA3", "PA4", "PA5", "PA6", "PA7", "PB0", "PB1", "PB2", "PB10", "PB11", "VSS", "VDD", "PB12", "PB13", "PB14", "PB15",
              "PA8", "PA9", "PA10", "PA11", "PA12", "PA13-SWDIO", "VSS", "VDD", "PA14-SWCLK", "PA15", "PB3", "PB4", "PB5", "PB6", "PB7",
              "BOOT0", "PB8", "PB9", "VSS", "VDD"]
_LED_PINS = ["PA0", "PA1", "PA2", "PA3", "PA4", "PA5", "PA6", "PA7", "PB0", "PB1", "PB2", "PB10", "PB11", "PB12", "PB13", "PB14", "PB15"]
_SPECIAL = {"VBAT": "+3V3", "VDD": "+3V3", "VDDA": "VDDA", "VSS": "GND", "VSSA": "GND", "PA13-SWDIO": "SWDIO", "PA14-SWCLK": "SWCLK",
            "PA11": "USB_DM", "PA12": "USB_DP", "NRST": "NRST", "BOOT0": "BOOT0", "PD0-OSC_IN": "OSC_IN", "PD1-OSC_OUT": "OSC_OUT",
            "PB6": "SCL", "PB7": "SDA"}


def build_parts(n_leds=14):
    """-> parts [{ref, footprint, value, pins:[{num, net, name}]}] in the form plan_placement and verify_layout take."""
    parts = []

    def add(ref, footprint, value, nets, names=None, nums=None):
        parts.append({"ref": ref, "footprint": footprint, "value": value,
                      "pins": [{"num": (nums[i] if nums else str(i + 1)), "net": n, **({"name": names[i]} if names else {})}
                               for i, n in enumerate(nets)]})

    pin_net = {nm: _SPECIAL.get(nm, f"IO_{nm}") for nm in _MCU_NAMES}
    add("U1", "LQFP48", "STM32F103C8T6", [pin_net[n] for n in _MCU_NAMES], _MCU_NAMES)
    add("J1", "USBC16", "USB-C", _USBC_NET + ["GND"] * 4, _USBC_NAME + ["SHELL"] * 4, [r[0] for r in _USBC_ROW] + ["S1", "S2", "S3", "S4"])
    add("R1", "R0402", "5.1k", ["CC1", "GND"])
    add("R2", "R0402", "5.1k", ["CC2", "GND"])
    add("Y1", "XTAL3225", "8MHz", ["OSC_IN", "OSC_OUT"])
    add("C20", "C0402", "20pF", ["OSC_IN", "GND"])
    add("C21", "C0402", "20pF", ["OSC_OUT", "GND"])
    add("U2", "SOT223", "AMS1117-3.3", ["GND", "+3V3", "VBUS", "+3V3"], ["GND", "VOUT", "VIN", "VOUT"])
    add("C30", "C0603", "4.7uF", ["VBUS", "GND"])
    add("C31", "C0603", "4.7uF", ["+3V3", "GND"])
    add("J2", "HDR1X5", "SWD", ["+3V3", "SWDIO", "SWCLK", "NRST", "GND"])
    add("J3", "HDR1X4", "I2C", ["+3V3", "SDA", "SCL", "GND"])
    k = 1
    for rail in ["+3V3", "+3V3", "+3V3", "+3V3", "VDDA", "+3V3", "+3V3", "+3V3"]:      # 100 nF: one per VDD pin and VBAT, VDDA, extras
        add(f"C{k}", "C0402", "100nF", [rail, "GND"])
        k += 1
    for _ in range(2):                                                                   # 4.7 uF bulk
        add(f"C{k}", "C0603", "4.7uF", ["+3V3", "GND"])
        k += 1
    add("FB1", "FB0603", "BLM18", ["+3V3", "VDDA"])
    add("C40", "C0402", "1uF", ["VDDA", "GND"])
    add("R3", "R0402", "10k", ["NRST", "+3V3"])
    add("C41", "C0402", "100nF", ["NRST", "GND"])
    add("SW1", "SW", "RESET", ["NRST", "GND"])
    add("R4", "R0402", "10k", ["BOOT0", "GND"])
    add("R5", "R0402", "4.7k", ["SCL", "+3V3"])
    add("R6", "R0402", "4.7k", ["SDA", "+3V3"])
    for i, pn in enumerate(_LED_PINS[:n_leds]):
        add(f"R{10 + i}", "R0402", "1k", [pin_net[pn], f"LED{i}"])
        add(f"D{1 + i}", "LED0603", "LED", [f"LED{i}", "GND"])
    add("R9", "R0402", "1k", ["+3V3", "PWR_LED"])
    add("D20", "LED0603", "GREEN", ["PWR_LED", "GND"])
    return parts


def doc_from_plan(parts, plan):
    """The saved-board dict (what read_pcbdoc gives) of a placement plan: components with pads at absolute positions."""
    byref = {p["ref"]: p for p in parts}
    doc = {"components": [], "pads": [], "tracks": [], "vias": []}
    for pl in plan["places"]:
        part, f = byref[pl["ref"]], FPS[pl["footprint"]]
        nets = {str(p["num"]): p["net"] for p in part["pins"]}
        names = {str(p["num"]): p.get("name", "") for p in part["pins"]}
        doc["components"].append({"ref": pl["ref"], "pattern": pl["footprint"], "x_mm": pl["x"], "y_mm": pl["y"], "rotation": pl["rot"],
                                  "body_bbox_mm": None, "outline_bbox_mm": None})
        for q in f["pads"]:
            rx, ry = layout.rot_point(q["x"] * MIL, q["y"] * MIL, pl["rot"])
            w, h = q["xsize"] * MIL, q["ysize"] * MIL
            if int(pl["rot"]) % 180 == 90:
                w, h = h, w
            net = nets.get(q["name"], "")
            doc["pads"].append({"ref": pl["ref"], "name": q["name"], "pin_name": names.get(q["name"], ""),
                                "x_mm": round(pl["x"] + rx, 4), "y_mm": round(pl["y"] + ry, 4), "sx_mm": w, "sy_mm": h, "rot": 0,
                                "net": "" if net.upper() in ("NC", "N/C") else net, "layer": 1})
    return doc
