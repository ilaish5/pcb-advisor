"""Dev helper, not part of the advisor: rebuild examples/led-chaser/ through the real stores.

    python tools/build_example_led_chaser.py

Builds the project in a throwaway workspace (so projects/ is never touched), then copies it to
examples/led-chaser/ without the derived files (bom.json, design-model.json, artifacts/). The BOM goes
through propose_bom + decide, the idea through the idea stores and the sheet through write_sheet, so the
example is exactly what the UI would have written.
"""
import os
import pathlib
import shutil
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
NAME = "led-chaser"
DEST = REPO / "examples" / NAME


def P(name, num, net, side=None):
    d = {"name": name, "num": num, "net": net}
    if side:
        d["side"] = side
    return d


def two(ref, section, kind, a, b):
    return {"ref": ref, "section": section, "kind": kind, "pins": [P("1", "1", a), P("2", "2", b)]}


QPINS = [3, 2, 4, 7, 10, 1, 5, 6, 9, 11]          # CD4017 pins of Q0..Q9

# (key, refs, value, description, mpn, manufacturer, package, role)
BOM = [
    ("J1", ["J1"], "USB-C", "USB-C receptacle, power only (VBUS, GND, CC1, CC2)", "", "", "USB-C SMD 16-pin", "5 V input"),
    ("R4", ["R4", "R5"], "5.1k", "CC pull-downs: ask the charger for 5 V", "", "", "0603", "USB-C CC1/CC2 pull-down"),
    ("U1", ["U1"], "NE555", "Timer, astable clock", "NE555DR", "Texas Instruments", "SOIC-8", "~2 Hz clock"),
    ("U2", ["U2"], "CD4017", "Decade counter, 10 decoded outputs", "CD4017BM96", "Texas Instruments", "SOIC-16", "steps the lit LED"),
    ("R1", ["R1"], "10k", "Astable R_A (VCC to DIS)", "", "", "0603", "clock timing"),
    ("R2", ["R2"], "68k", "Astable R_B (DIS to THR/TRIG)", "", "", "0603", "clock timing"),
    ("C1", ["C1"], "4.7uF", "Timing capacitor (THR/TRIG to GND)", "", "", "0805", "clock timing"),
    ("C2", ["C2"], "10nF", "NE555 CTRL decoupling", "", "", "0603", "decoupling"),
    ("C3", ["C3", "C4"], "100nF", "Decoupling, one per IC (U1, U2)", "", "", "0603", "decoupling"),
    ("C5", ["C5"], "10uF", "Bulk capacitor on VBUS", "", "", "0805", "bulk"),
    ("D1", [f"D{i}" for i in range(1, 11)], "red", "Red LED", "", "", "0805", "the running light"),
    ("R3", ["R3"], "470R", "Common LED resistor (LED cathodes to GND, one LED on at a time)", "", "", "0603", "LED current"),
]

BLOCKS = [
    ("usb", "USB-C 5 V", "J1, R4, R5, C5", "power", 40, 120),
    ("clk", "NE555 clock", "U1, R1, R2, C1, C2", "mcu", 300, 120),
    ("cnt", "CD4017 counter", "U2, one output at a time", "mcu", 560, 120),
    ("led", "10 LEDs", "D1..D10, R3", "drive", 820, 120),
]
LINKS = [("usb", "clk", "+5 V"), ("usb", "cnt", "+5 V"), ("clk", "cnt", "CLK"), ("cnt", "led", "Q0..Q9")]

AGREED = [
    ("Function", "Ten red LEDs light one at a time in a loop, a running light. About 2 steps per second."),
    ("Power", "USB-C, 5 V only. J1 has VBUS, GND, CC1 and CC2; R4 and R5 (5.1k) on CC1/CC2 make the charger give 5 V. "
              "C5 10uF on VBUS."),
    ("Clock", "U1 NE555 astable: f = 1.44 / ((R1 + 2*R2) * C1) = 1.44 / (146k * 4.7uF), about 2.1 Hz. "
              "C2 10nF on CTRL."),
    ("Counter and LEDs", "U2 CD4017 counts the clock and raises Q0..Q9 in turn, each driving one LED anode. "
                         "All cathodes share R3 470R to GND, so one LED is on at a time (about 7 mA)."),
    ("Board", "Two layers, 0603/0805 parts, SOIC-8 and SOIC-16 for the two ICs. One 100nF decoupling cap per IC."),
]


def sheet():
    parts = [
        {"ref": "J1", "section": "PWR", "kind": "conn", "pins": [
            P("VBUS", "A4B9", "+5V"), P("GND", "A1B12", "GND"), P("CC1", "A5", "CC1"), P("CC2", "B5", "CC2"),
            P("SHIELD", "S1", "GND")]},
        two("R4", "PWR", "res", "CC1", "GND"), two("R5", "PWR", "res", "CC2", "GND"),
        two("C5", "PWR", "cap", "+5V", "GND"),
        {"ref": "U1", "section": "CLK", "kind": "ic", "pins": [
            P("GND", "1", "GND", "left"), P("TRIG", "2", "THR", "left"), P("OUT", "3", "CLK", "left"),
            P("RESET", "4", "+5V", "left"), P("CTRL", "5", "CTRL", "right"), P("THR", "6", "THR", "right"),
            P("DIS", "7", "DIS", "right"), P("VCC", "8", "+5V", "right")]},
        two("R1", "CLK", "res", "+5V", "DIS"), two("R2", "CLK", "res", "DIS", "THR"),
        two("C1", "CLK", "cap", "THR", "GND"), two("C2", "CLK", "cap", "CTRL", "GND"),
        two("C3", "CLK", "cap", "+5V", "GND"),
        {"ref": "U2", "section": "CNT", "kind": "ic", "pins": [
            P("VSS", "8", "GND", "left"), P("CLK", "14", "CLK", "left"), P("CLK INH", "13", "GND", "left"),
            P("RESET", "15", "GND", "left"), P("CO", "12", "NC", "left"), P("VDD", "16", "+5V", "left"),
            *[P(f"Q{i}", str(n), f"Q{i}", "right") for i, n in enumerate(QPINS)]]},
        two("C4", "CNT", "cap", "+5V", "GND"),
        two("R3", "LED", "res", "LED_K", "GND"),
    ]
    for i in range(10):
        parts.append({"ref": f"D{i + 1}", "section": "LED", "kind": "diode", "pins": [
            P("A", "2", f"Q{i}"), P("K", "1", "LED_K")]})
    return {
        "id": "01", "title": "LED chaser",
        "sections": [
            {"id": "PWR", "title": "USB-C 5 V in"},
            {"id": "CLK", "title": "U1 NE555 clock, about 2 Hz"},
            {"id": "CNT", "title": "U2 CD4017 decade counter"},
            {"id": "LED", "title": "D1..D10 and the shared resistor R3"},
        ],
        "parts": parts,
        "notes": [
            {"section": "CLK", "text": "f = 1.44 / ((R1 + 2*R2) * C1), about 2.1 Hz. THR and TRIG are one net."},
            {"section": "LED", "text": "All cathodes meet at LED_K; one LED is on at a time, so one resistor is enough."},
        ],
    }


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="led-chaser-"))
    os.environ["PCB_ADVISOR_HOME"] = str(tmp)
    os.environ["PCB_ADVISOR_CONFIG"] = str(tmp / "config.json")
    import project
    import store
    import workspace
    workspace.load(reload=True)

    project.create(NAME, title="LED chaser",
                   brief="USB-C powered running light: NE555 clock, CD4017 counter, 10 LEDs.")
    p = NAME

    store.set_idea_goal(p, "A 5 V USB-C powered running light. An NE555 makes a clock of about 2 Hz, a CD4017 decade "
                           "counter steps through ten outputs, and each output lights one red LED. Two ICs only.")
    for topic, text in AGREED:
        store.propose_idea(p, topic, text, by="student")
    idea = store.load_idea(p)
    idea["blocks"] = [{"id": i, "label": l, "role": r, "domain": d, "x": float(x), "y": float(y)}
                      for i, l, r, d, x, y in BLOCKS]
    idea["links"] = [{"from": a, "to": b, "label": lab} for a, b, lab in LINKS]
    idea.pop("diagram", None)
    store.save_idea(p, idea)
    store.confirm_idea(p)

    for key, refs, value, desc, mpn, mfr, pkg, role in BOM:
        changes = {"refs": refs, "value": value, "description": desc, "package": pkg, "role": role, "sheet": "01"}
        if mpn:
            changes.update(mpn=mpn, manufacturer=mfr)
        prop = store.propose_bom(p, key, changes, reason="Example project", new=True)
        store.decide(p, prop["id"], "approved")

    res = store.write_sheet(p, "01", sheet())
    assert res["ok"], res
    (tmp / "projects" / p / "notes.md").write_text(
        "# Notes\n\nExample project that ships with the install. USB-C 5 V -> NE555 (about 2 Hz) -> CD4017 -> 10 LEDs.\n"
        "The schematic sheet is written; the Altium project is yours to make.\n"
        "LCSC codes are empty on purpose: the availability check fills them.\n", encoding="utf-8")

    src = tmp / "projects" / p
    if DEST.exists():
        shutil.rmtree(DEST)
    shutil.copytree(src, DEST, ignore=shutil.ignore_patterns("bom.json", "design-model.json", "artifacts", "__pycache__"))
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"wrote {DEST}")


if __name__ == "__main__":
    main()
