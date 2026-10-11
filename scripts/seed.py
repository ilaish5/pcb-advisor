"""
Seed project: lte-tracker, the worked example (the mock's data, as real files).

    python pcb.py seed            # creates projects/lte-tracker if it is missing

Everything is written through the same stores the server uses, so the example is
a project like any other: delete it and nothing else notices. Stock and prices
here are SAMPLE data and say so (source: "sample"): the real numbers come from
the check_availability skill, with a time.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import project as project_mod  # noqa: E402
import session                 # noqa: E402
import store                   # noqa: E402
import workspace               # noqa: E402

NAME = "lte-tracker"
SAMPLE_TS = "2026-10-08T09:12:00"


def P(name, num, net, side=None):
    d = {"name": name, "num": num, "net": net}
    if side:
        d["side"] = side
    return d


def two(ref, section, kind, a, b):
    return {"ref": ref, "section": section, "kind": kind, "pins": [P("1", "1", a), P("2", "2", b)]}


SHEET_03 = {
    "id": "03", "title": "Modem",
    "sections": [
        {"id": "A", "title": "U4 SIMCom A7670G (LTE modem, I/O = 1.8V)"},
        {"id": "B", "title": "VBAT: bulk + small caps and TVS on +3V8"},
        {"id": "C", "title": "PWRKEY driver: MCU pulse -> Q3 -> modem on/off"},
        {"id": "D", "title": "U5 TXS0104E: 1.8V (modem) <-> 3.3V (MCU)"},
        {"id": "E", "title": "Antenna: pi-network + U.FL"},
        {"id": "F", "title": "SIM: 22R series resistors + ESD + holder"},
        {"id": "G", "title": "Test points (pads only)"},
    ],
    "parts": [
        {"ref": "U4", "section": "A", "kind": "ic", "pins": [
            P("VBAT", "55", "+3V8", "left"), P("VBAT", "56", "+3V8", "left"), P("VBAT", "57", "+3V8", "left"),
            P("GND", "*", "GND", "left"), P("PWRKEY", "1", "PWRKEY_N", "left"), P("RESET", "16", "NC", "left"),
            P("USB_BOOT", "6", "USB_BOOT", "left"), P("UART_LOG_TX", "23", "UART_LOG_TX", "left"),
            P("USB_VBUS", "24", "MDM_USB_VBUS", "left"), P("USB_DP", "27", "MDM_USB_DP", "left"),
            P("USB_DM", "28", "MDM_USB_DM", "left"),
            P("TXD", "9", "MDM_TXD_1V8", "right"), P("RXD", "10", "MDM_RXD_1V8", "right"),
            P("STATUS", "66", "MDM_STATUS_1V8", "right"), P("VDD_EXT", "15", "VDD_EXT", "right"),
            P("RF_ANT", "60", "RF_ANT", "right"), P("USIM_VDD", "30", "SIM_VDD", "right"),
            P("USIM_DATA", "31", "SIM_DATA_M", "right"), P("USIM_CLK", "32", "SIM_CLK_M", "right"),
            P("USIM_RST", "33", "SIM_RST_M", "right"), P("USIM_DET", "34", "NC", "right")]},
        two("C30", "B", "cap", "+3V8", "GND"), two("C31", "B", "cap", "+3V8", "GND"),
        two("C36", "B", "cap", "+3V8", "GND"), two("C32", "B", "cap", "+3V8", "GND"),
        two("C33", "B", "cap", "+3V8", "GND"), two("D30", "B", "tvs", "+3V8", "GND"),
        two("R30", "C", "res", "MDM_PWRKEY", "Q3_G"), two("R31", "C", "res", "Q3_G", "GND"),
        {"ref": "TP12", "section": "C", "kind": "tp", "pins": [P("1", "1", "MDM_PWRKEY")]},
        {"ref": "Q3", "section": "C", "kind": "q", "pins": [
            P("G", "1", "Q3_G", "left"), P("S", "2", "GND", "left"), P("D", "3", "PWRKEY_N", "right")]},
        {"ref": "U5", "section": "D", "kind": "ic", "pins": [
            P("VCCA", "1", "VDD_EXT", "left"), P("A1", "2", "MDM_TXD_1V8", "left"), P("A2", "3", "MDM_RXD_1V8", "left"),
            P("A3", "4", "MDM_STATUS_1V8", "left"), P("A4", "5", "NC", "left"), P("NC", "6", "NC", "left"),
            P("GND", "7", "GND", "left"),
            P("VCCB", "14", "+3V3", "right"), P("B1", "13", "MDM_TX", "right"), P("B2", "12", "MDM_RX", "right"),
            P("B3", "11", "MDM_STATUS", "right"), P("B4", "10", "NC", "right"), P("NC", "9", "NC", "right"),
            P("OE", "8", "VDD_EXT", "right")]},
        two("C35", "D", "cap", "+3V3", "GND"), two("C34", "D", "cap", "VDD_EXT", "GND"),
        two("R40", "E", "res", "RF_ANT", "RF_OUT"), two("C40", "E", "cap", "RF_ANT", "GND"),
        two("C41", "E", "cap", "RF_OUT", "GND"),
        {"ref": "J6", "section": "E", "kind": "conn", "pins": [P("SIG", "1", "RF_OUT"), P("GND", "2", "GND")]},
        two("R43", "F", "res", "SIM_RST_M", "SIM_RST"), two("R42", "F", "res", "SIM_CLK_M", "SIM_CLK"),
        two("R41", "F", "res", "SIM_DATA_M", "SIM_DATA"),
        {"ref": "D31", "section": "F", "kind": "ic", "pins": [
            P("I/O1", "", "SIM_VDD", "left"), P("I/O2", "", "SIM_RST", "left"), P("I/O3", "", "SIM_CLK", "left"),
            P("I/O4", "", "SIM_DATA", "left"), P("GND", "", "GND", "right")]},
        two("C42", "F", "cap", "SIM_VDD", "GND"),
        {"ref": "J7", "section": "F", "kind": "conn", "pins": [
            P("VCC", "C1", "SIM_VDD"), P("RST", "C2", "SIM_RST"), P("CLK", "C3", "SIM_CLK"),
            P("I/O", "C7", "SIM_DATA"), P("GND", "C5", "GND"), P("VPP", "C6", "NC")]},
        {"ref": "TP13", "section": "G", "kind": "tp", "pins": [P("1", "1", "USB_BOOT")]},
        {"ref": "TP14", "section": "G", "kind": "tp", "pins": [P("1", "1", "GND")]},
        {"ref": "TP15", "section": "G", "kind": "tp", "pins": [P("1", "1", "UART_LOG_TX")]},
        {"ref": "TP16", "section": "G", "kind": "tp", "pins": [P("1", "1", "MDM_USB_VBUS")]},
        {"ref": "TP17", "section": "G", "kind": "tp", "pins": [P("1", "1", "MDM_USB_DP")]},
        {"ref": "TP18", "section": "G", "kind": "tp", "pins": [P("1", "1", "MDM_USB_DM")]},
    ],
    "notes": [
        {"section": "A", "text": "* GND = every GND pin of U4, each with its own GND symbol."},
        {"section": "A", "text": "Unused pins (DTR, RI, DCD, GPIO, ADC ...): Generic No ERC."},
        {"section": "B", "text": "All within 3 mm of U4 pins 55-57 in the layout."},
        {"section": "C", "text": "MCU high 100 ms -> Q3 on -> PWRKEY_N low -> modem on / off."},
        {"section": "E", "text": "C40/C41: footprint only, not assembled."},
        {"section": "F", "text": "D31 pin numbers NOT verified."},
        {"section": "G", "text": "Short TP14 to TP13 before power-up = firmware-download mode."},
    ],
}

# key, refs, value, description, mpn, manufacturer, package, flags, datasheet, note
BOM = [
    ("U4", ["U4"], "A7670G", "LTE Cat-1 modem", "A7670G-LABE", "SIMCom", "LCC+LGA", {}, "A7670G_datasheet.pdf", "All GND pins connected"),
    ("U5", ["U5"], "TXS0104E", "4-ch level shifter", "TXS0104EPWR", "Texas Instruments", "TSSOP-14", {}, "txs0104e.pdf", ""),
    ("U1", ["U1"], "STM32G030", "MCU, Cortex-M0+", "STM32G030F6P6", "STMicroelectronics", "TSSOP-20", {"sheet": "02"}, "STM32G030_datasheet.pdf", "Sheet 02, not drawn yet"),
    ("Q3", ["Q3"], "2N7002", "N-MOSFET, PWRKEY switch", "2N7002,215", "Nexperia", "SOT-23", {"library": "std"}, None, ""),
    ("D30", ["D30"], "TVS", "ESD protection on VBAT", "ESD56301D05", "Not identified", "—", {}, None, ""),
    ("D31", ["D31"], "ESDA6V1W5", "ESD protection, SIM lines", "ESDA6V1W5", "STMicroelectronics", "SOT-323-5", {}, "esda6v1w5.pdf", "Symbol pin numbers do not match the datasheet"),
    ("J6", ["J6"], "U.FL", "Antenna connector", "U.FL-R-SMT-1(10)", "Hirose", "U.FL SMT", {}, "U.FL-R-SMT.pdf", ""),
    ("J7", ["J7"], "Nano-SIM", "Nano-SIM holder", "786800001", "Molex", "Nano-SIM 6P", {}, "786800001.pdf", ""),
    ("C30", ["C30"], "330µF", "Bulk cap, tantalum", "TAJD337K006RNJ", "KYOCERA AVX", "D (7343)", {"library": "std"}, None, "Within 3 mm of pins 55–57"),
    ("C31", ["C31"], "1µF", "Ceramic cap", "CL05A105KA5NQNC", "Samsung", "0402", {"library": "std"}, None, ""),
    ("C100", ["C34", "C35", "C36", "C42"], "100nF", "Decoupling cap", "CL05B104KO5NNNC", "Samsung", "0402", {"library": "std"}, None, ""),
    ("C32", ["C32"], "33pF", "RF cap", "CL05C330JB5NNNC", "Samsung", "0402", {"library": "std"}, None, ""),
    ("C33", ["C33"], "10pF", "RF cap", "CL05C100JB5NNNC", "Samsung", "0402", {"library": "std"}, None, ""),
    ("C40", ["C40", "C41"], "DNP", "Pi-network, not fitted", "—", "—", "0402", {"library": "std", "dnp": True}, None, "Footprint only"),
    ("R30", ["R30"], "1k", "Gate resistor", "0402WGF1001TCE", "UNI-ROYAL", "0402", {"library": "std"}, None, ""),
    ("R31", ["R31"], "100k", "Gate pull-down", "0402WGF1003TCE", "UNI-ROYAL", "0402", {"library": "std"}, None, ""),
    ("R40", ["R40"], "0R", "Pi-network bridge", "0402WGF0000TCE", "UNI-ROYAL", "0402", {"library": "std"}, None, ""),
    ("R22", ["R41", "R42", "R43"], "22R", "SIM series resistor", "0402WGF220JTCE", "UNI-ROYAL", "0402", {"library": "std"}, None, ""),
    ("TP", ["TP12", "TP13", "TP14", "TP15", "TP16", "TP17", "TP18"], "Test pad", "Test point", "—", "—", "TP 1.0mm", {"library": "std", "nobuy": True}, None, "Pad only, not purchased"),
]

# sample supply: (LCSC stock, price), (Mouser), (DigiKey)
SUPPLY = {
    "U4": [(1240, 14.80), (0, None), (85, 17.20)], "U5": [(12400, 0.42), (8650, 0.71), (23110, 0.68)],
    "U1": [(21000, 1.10), (8400, 1.35), (13800, 1.42)],
    "Q3": [(386000, 0.019), (120000, 0.10), (250000, 0.12)], "D30": [(0, None), (0, None), (0, None)],
    "D31": [(9300, 0.16), (14500, 0.38), (11800, 0.41)], "J6": [(5100, 0.38), (62000, 0.62), (48000, 0.66)],
    "J7": [(640, 0.92), (2100, 1.35), (1800, 1.41)], "C30": [(3200, 0.58), (9800, 1.12), (6400, 1.20)],
    "C31": [(2400000, 0.0017), (310000, 0.10), (540000, 0.10)], "C100": [(5600000, 0.0011), (880000, 0.10), (1200000, 0.10)],
    "C32": [(880000, 0.0021), (96000, 0.10), (140000, 0.10)], "C33": [(920000, 0.0019), (88000, 0.10), (160000, 0.10)],
    "R30": [(9800000, 0.0009), (0, None), (0, None)], "R31": [(7400000, 0.0009), (0, None), (0, None)],
    "R40": [(12600000, 0.0008), (0, None), (0, None)], "R22": [(3100000, 0.0009), (0, None), (0, None)],
}

# line -> (symbol, footprint, step, model source, verify, accepted, issues)
LIBRARY = {
    "U4": (True, True, False, "Built by the agent from the datasheet", "pass", True, ""),
    "U5": (True, True, True, "Ultra Librarian", "pass", True, ""),
    "U1": (True, True, True, "SnapEDA", "pass", True, ""),
    "D31": (True, True, True, "SnapEDA", "mismatch", False, "Symbol pin numbers do not match the datasheet"),
    "J6": (True, True, True, "SnapEDA", "pass", True, ""),
    "J7": (True, True, False, "Built by the agent from the drawing", "pass", True, ""),
}

SOURCES = [   # name, kind-agnostic metadata for the sidecars (the files themselves are not shipped)
    ("A7670G_datasheet.pdf", "https://datasheet.lcsc.com/lcsc/A7670G.pdf"),
    ("STM32G030_datasheet.pdf", "https://www.st.com/resource/en/datasheet/stm32g030f6.pdf"),
    ("txs0104e.pdf", "https://www.ti.com/lit/ds/symlink/txs0104e.pdf"),
    ("esda6v1w5.pdf", "https://www.st.com/resource/en/datasheet/esda6v1w5.pdf"),
    ("PESD5V0S1BL.pdf", "https://assets.nexperia.com/documents/data-sheet/PESD5V0S1BL.pdf"),
    ("U.FL-R-SMT.pdf", "https://www.hirose.com/product/document?clcode=&productname=U.FL-R-SMT"),
    ("786800001.pdf", "https://www.molex.com/pdm_docs/sd/786800001_sd.pdf"),
]

IDEA = {
    "goal": "A bike tracker that sends its location to a server every 5 minutes and runs a week on one charge. "
            "It has to fit under the saddle.",
    "confirmed": True,
    "agreed": [
        {"topic": "Cellular", "text": "LTE Cat-1 with the SIMCom A7670G. Israel's 2G/3G networks are shutting down, so a 2G modem is out.", "by": "agent", "status": "confirmed"},
        {"topic": "Location", "text": "Separate GNSS module on sheet 04.", "by": "agent", "status": "proposed"},
        {"topic": "Power", "text": "1S Li-ion. +3V8 for the modem with bulk capacitance for transmit peaks, +3V3 for the MCU.", "by": "agent", "status": "confirmed"},
        {"topic": "MCU", "text": "STM32G0. UART to the modem through a 1.8 V <-> 3.3 V level shifter.", "by": "student", "status": "confirmed"},
    ],
    "blocks": [
        {"id": "BAT", "kind": "power_in", "label": "Li-ion 1S", "sub": "3.7 V"},
        {"id": "PWR", "kind": "power", "label": "01 Power", "sub": "+3V8 · +3V3"},
        {"id": "MCU", "kind": "mcu", "label": "02 MCU", "sub": "STM32G0"},
        {"id": "MDM", "kind": "modem", "label": "03 Modem", "sub": "A7670G · SIM · U.FL", "sheet": "03"},
        {"id": "GNSS", "kind": "gnss", "label": "04 GNSS", "sub": "not chosen yet", "open": True},
    ],
    "links": [["BAT", "PWR"], ["PWR", "MCU"], ["MCU", "MDM"], ["MCU", "GNSS"]],
}


def seed(name=NAME, force=False):
    root = workspace.project_dir(name)
    if root.exists() and not force:
        return {"project": name, "created": False}
    project_mod.ensure(name)
    meta = project_mod.load_meta(name)
    meta.update(title="LTE Tracker", brief=IDEA["goal"], status="draft")
    project_mod.save_meta(name, meta)
    store.save_idea(name, IDEA)
    for path in ("bom-log.jsonl", "supply-log.jsonl", "library-log.jsonl", "proposals.jsonl"):
        (root / path).write_text("", encoding="utf-8")

    for key, refs, value, desc, mpn, mfr, pkg, flags, ds, note in BOM:
        changes = {"refs": refs, "value": value, "description": desc, "mpn": mpn, "manufacturer": mfr,
                   "package": pkg, "note": note, "sheet": "03", **flags}
        if ds:
            changes["datasheet"] = ds
        store.append(name, "bom-log.jsonl", {"ts": SAMPLE_TS, "by": "agent-approved", "line": key,
                                             "changes": changes, "reason": "initial BOM"})
    for key, rows in SUPPLY.items():
        mpn = next(b[4] for b in BOM if b[0] == key)
        for supplier, (stock, price) in zip(store.SUPPLIERS, rows):
            store.append(name, "supply-log.jsonl", {
                "ts": SAMPLE_TS, "line": key, "mpn": mpn, "supplier": supplier, "stock": stock,
                "unit_price": price, "qty_break": 10, "source": "sample"})
    for key, (sym, fp, step, src, verify, accepted, issues) in LIBRARY.items():
        store.add_library(name, key, {"symbol": sym, "footprint": fp, "step": step, "model_source": src,
                                      "verify": verify, "accepted": accepted, "issues": issues})

    res = store.write_sheet(name, "03", SHEET_03)
    assert res["ok"], res

    side = root / "sources"
    side.mkdir(exist_ok=True)
    for fname, url in SOURCES:
        (side / (fname + ".json")).write_text(json.dumps(
            {"name": fname, "url": url, "origin": url.split("/")[2], "note": "sidecar only: run "
             "`python scripts/sources.py restore` to fetch the file"}, indent=2), encoding="utf-8")

    store.propose_bom(
        name, "D30",
        {"mpn": "PESD5V0S1BL", "manufacturer": "Nexperia", "package": "SOD-882", "value": "TVS 5V",
         "datasheet": "PESD5V0S1BL.pdf"},
        reason="ESD56301D05 is not listed at any supplier. PESD5V0S1BL has a 5 V working voltage, above a full cell (4.2 V).",
        sources=["PESD5V0S1BL.pdf"],
        library={"symbol": True, "footprint": True, "step": True, "model_source": "Ultra Librarian",
                 "verify": "pass", "accepted": False, "issues": ""})

    # conversations
    for row in session.list_all(name):
        session.delete(name, row["id"])
    idea_sid = session.create(name, title="Idea refinement", sid="idea")
    main_sid = session.create(name, title="Modem sheet: parts & library", sid="main")
    chat = [
        (idea_sid, "user", "I want to build a GPS tracker for my bike that reports its location over cellular."),
        (idea_sid, "agent", "Three questions before we pick parts:\n1. How often should it report?\n2. How long between charges?\n3. Any size limit?"),
        (idea_sid, "user", "Every 5 minutes, a week on one charge, and it has to fit under the saddle."),
        (idea_sid, "agent", "Then I suggest LTE Cat-1 (SIMCom A7670G), since Israel's 2G/3G networks are shutting down. Add a separate GNSS module, an STM32G0 and a 1S Li-ion cell. I put the block diagram in the Idea tab. Does it match what you meant?"),
        (idea_sid, "user", "Yes, confirmed."),
        (main_sid, "user", "Check availability for every part on the modem sheet, and build me an Altium library for anything that is not in the default libraries."),
    ]
    for sid, role, text in chat:
        session.append(name, sid, {"ts": SAMPLE_TS, "role": role, "text": text})
    pid = store.proposals(name)[0]["id"]
    session.append(name, main_sid, {
        "ts": SAMPLE_TS, "role": "agent",
        "tools": [{"t": "Check availability", "d": "18 lines · LCSC, Mouser, DigiKey", "st": "warn"},
                  {"t": "Verify pins vs datasheet", "d": "5 parts · 1 mismatch", "st": "warn"}],
        "text": "Done. Two things need you:\n- {{ref:D30}} ESD56301D05 isn't listed at any supplier. I proposed a replacement below.\n"
                "- {{ref:D31}} The SnapEDA symbol numbers its pins differently from the datasheet table. I marked it \"to review\" and changed nothing.\n"
                "{{src:esda6v1w5.pdf|p. 2, Pin configuration}}",
        "proposal": pid})
    session.touch(name, idea_sid)
    return {"project": name, "created": True}


if __name__ == "__main__":
    import oscompat
    oscompat.utf8_stdio()
    print(json.dumps(seed(force="--force" in sys.argv), indent=2))
