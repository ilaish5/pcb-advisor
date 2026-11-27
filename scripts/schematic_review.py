"""The tool's own review of the schematic: rule classes checked on the project's netlist, with the scope stated (R2, ACCEPTANCE W22).

    review(project) -> {"findings": [{"class", "ref", "text"}], "classes": [...], "scope": str, "text": str, "sheets": n, "parts": n}

A review the model alone wrote ("0 errors") has no scope: it read some files, ran no check, and says nothing about what it looked at. This
module is the check that has one. It reads every sheet of the netlist and applies five rule classes; each finding names the part, the net
and what to do. `text` is what the student reads: the findings, then the scope (what was checked, and what was not). With no finding it
says "no finding in these rule classes", never "0 errors".

Rule classes (each is a netlist check, none is a guess about values):
  decap_missing    an IC with more supply pins on a rail than capacitors from that rail to ground
  i3c_shared_spi   an I2C/I3C-capable device (SCL + SDA + CS pins) whose SCL net is also another device's SPI clock
  od_no_pullup     an I2C-named open-drain bus with no resistor from the net to a supply rail
  ep_not_gnd       an exposed / thermal pad pin that is not on a ground net
  xtal_no_caps     a 2-pin crystal with no load capacitor to ground on one of its two nets
"""
import re
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import store  # noqa: E402

CLASSES = {
    "decap_missing": "decoupling capacitor per supply pin",
    "i3c_shared_spi": "I2C/I3C-capable device on a shared SPI bus",
    "od_no_pullup": "pull-up on open-drain buses",
    "ep_not_gnd": "exposed pad on ground",
    "xtal_no_caps": "crystal load capacitors",
}
_GND = re.compile(r"^(?:[ADP]?GND\w*|VSS\w*|GROUND|0V|PGND\w*|\+?0V0?)$", re.I)
_RAIL = re.compile(r"^\+|VCC|VDD|VIN|VBAT|VBUS|\d+V\d*|^V\+", re.I)
_SUPPLY_ONE = re.compile(r"^(?:[ADP]?V(?:DD|CC|BAT|REF\+?|BUS)[A-Z0-9_+]*|VDD\w*)$", re.I)
_SCL = re.compile(r"(?<![A-Z0-9])SCL(?![A-Z])", re.I)       # SCL, I2C_SCL, SCL1, SCL/SPC; not SPI_SCLK
_SDA = re.compile(r"(?<![A-Z0-9])SDA(?![A-Z])", re.I)


def _is_supply_name(name):
    """A supply pin name, also when the pin is shared: VDDA/VREF+ is a supply pin of the part."""
    return any(_SUPPLY_ONE.match(x.strip()) for x in str(name or "").split("/"))
_EP = re.compile(r"^(?:EP|EPAD|E-PAD|PAD|TAB|THERMAL\w*|EXP\w*|EXPOSED\w*|DAP)$", re.I)
_NC = re.compile(r"^(?:NC|N/C|NO[_-]?CONNECT|\*|)$", re.I)
_I2C_NET = re.compile(r"I2C|SCL|SDA", re.I)


def _is_gnd(net):
    return bool(_GND.match(str(net or "").strip()))


def _is_rail(net):
    n = str(net or "").strip()
    return bool(n) and not _is_gnd(n) and bool(_RAIL.search(n)) and not re.match(r"^[-~]", n)


_ANALOG = re.compile(r"^(?:A?VDDA|AVDD\w*|AVCC|VREF\+?|VREFP)$", re.I)


def _is_analog_supply(name):
    return any(_ANALOG.match(x.strip()) for x in str(name or "").split("/"))


def _farads(value):
    """The capacitance in farads of a BOM value text ('100nF', '4.7uF', '10 pF'), or None when it is not readable."""
    m = re.match(r"^\s*(\d*\.?\d+)\s*([pnuµμm]?)\s*f?\b", str(value or ""), re.I)
    if not m:
        return None
    return float(m.group(1)) * {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "μ": 1e-6, "m": 1e-3, "": 1.0}[m.group(2).lower()]


def _pref(ref):
    return re.match(r"[A-Za-z]*", str(ref)).group(0).upper()


def _parts(project):
    out = []
    for sh in store.sheet_ids(project):
        try:
            out += [dict(p) for p in store.load_sheet(project, sh).get("parts", []) if p.get("ref")]
        except (OSError, ValueError, KeyError):
            continue
    try:                           # a capacitor's size is in the BOM, not on the sheet
        values = {r: l.get("value") for l in store.bom(project, write=False) for r in (l.get("refs") or [])}
    except Exception:       # noqa: BLE001 - without values every capacitor counts as one of unknown size
        values = {}
    for p in out:
        if not p.get("value") and values.get(p["ref"]):
            p["value"] = values[p["ref"]]
    return out


def _pins(part):
    return [(str(p.get("num", p.get("number", ""))), str(p.get("name") or ""), str(p.get("net") or "").strip()) for p in part.get("pins", [])]


def review(project, parts=None):
    parts = _parts(project) if parts is None else parts
    nets = {}                      # net -> [(ref, pin number, pin name)]
    by_ref = {}
    for p in parts:
        by_ref[p["ref"]] = p
        for n, nm, net in _pins(p):
            if net and not _NC.match(net):
                nets.setdefault(net, []).append((p["ref"], n, nm))

    def two_pin(ref):
        return len(by_ref[ref].get("pins", [])) == 2

    caps_to_gnd = {}               # any net -> [cap refs from that net to ground]
    for ref, p in by_ref.items():
        if _pref(ref) == "C" and two_pin(ref):
            a, b = [net for _, _, net in _pins(p)]
            for x, y in ((a, b), (b, a)):
                if _is_gnd(y) and x:
                    caps_to_gnd.setdefault(x, []).append(ref)
    findings = []

    def add(cls, ref, text):
        findings.append({"class": cls, "ref": ref, "text": f"{ref}: {text}"})

    def is_ic(ref):
        p = by_ref[ref]
        return _pref(ref) not in ("C", "R", "L", "D", "F", "FB", "TP", "J", "P", "SW", "Y", "X") or str(p.get("kind") or "") == "ic"

    # decoupling: every IC supply pin needs a capacitor of its own, taken one-to-one from the capacitors of its sheet area on that rail
    # (netlist adjacency: the same schematic section and the same net). A bulk capacitor does not stand in for a bypass capacitor, and an analog
    # supply pin (VDDA, AVDD, VREF+) asks two: a ~10 nF and a ~1 uF (the usual STM32 / mixed-signal datasheet rule).
    pool = {}                      # (section, rail net) -> [cap refs]
    for net, refs in caps_to_gnd.items():
        for c in refs:
            pool.setdefault((by_ref[c].get("section") or "", net), []).append(c)
    pins_of = {}                   # (section, rail net) -> [(ic ref, pin name, analog)]
    for ref, p in sorted(by_ref.items()):
        if is_ic(ref):
            for n, nm, net in _pins(p):
                if _is_supply_name(nm) and _is_rail(net):
                    pins_of.setdefault((p.get("section") or "", net), []).append((ref, nm, _is_analog_supply(nm)))
    for (sec, net), need in sorted(pins_of.items()):
        free = list(pool.get((sec, net), []))

        def take(lo, hi, prefer=None):
            known = [c for c in free if _farads(by_ref[c].get("value")) is not None and lo <= _farads(by_ref[c].get("value")) <= hi]
            if prefer:
                known.sort(key=lambda c: abs(_farads(by_ref[c].get("value")) - prefer))
            pick = (known or [c for c in free if _farads(by_ref[c].get("value")) is None] or [None])[0]
            if pick:
                free.remove(pick)
            return pick
        for ref, nm, analog in [x for x in need if x[2]]:
            for label, lo, hi, pref in (("10 nF", 1e-9, 4.7e-8, 1e-8), ("1 uF", 4.7e-7, 1e-5, 1e-6)):
                if not take(lo, hi, pref):
                    add("decap_missing", ref, f"decoupling capacitor missing: analog supply pin {nm} on {net} has no {label} capacitor of its own "
                        f"(the part's sheet area has {len(pool.get((sec, net), []))} capacitor(s) on {net}; a capacitor serves one pin, and a bulk "
                        "capacitor does not replace a bypass capacitor)")
        for ref, nm, analog in [x for x in need if not x[2]]:
            if not take(1e-9, 1e-6, 1e-7):
                add("decap_missing", ref, f"decoupling capacitor missing: supply pin {nm} on {net} has no capacitor of its own "
                    f"(the part's sheet area has {len(pool.get((sec, net), []))} capacitor(s) on {net}, each serving one pin; a bulk capacitor does "
                    "not replace a bypass capacitor); the datasheet asks for a bypass capacitor at each supply pin")
    for ref, p in by_ref.items():
        if not is_ic(ref):
            continue
        pins = _pins(p)
        # I2C/I3C device on a shared SPI bus
        names = [nm.upper() for _, nm, _ in pins]
        if any(_SCL.search(n) for n in names) and any(_SDA.search(n) for n in names) and any(n.split("/")[0] in ("CS", "NCS", "/CS") or n == "CS" for n in names):
            for n, nm, net in pins:
                if _SCL.search(nm) and net:
                    others = [(r, pn) for r, _, pn in nets.get(net, []) if r != ref and re.search(r"SCK|SCLK|CLK|SPC", pn, re.I)]
                    if others:
                        add("i3c_shared_spi", ref, f"I2C/I3C-capable device on a shared SPI bus: its {nm} pin is on {net}, which is also the clock of "
                            f"{others[0][0]}; it can answer or glitch on the shared bus, so disable its I3C/I2C interface (tie the interface select) "
                            f"or give it its own bus")
                        break
        # exposed pad not on ground
        for n, nm, net in pins:
            if _EP.match(nm.strip()) and net and not _is_gnd(net):
                add("ep_not_gnd", ref, f"exposed pad {nm} (pin {n}) is on {net}, not on ground: the thermal pad / EP of an IC is normally ground")
    # open-drain buses: I2C-named nets with an IC pin and no resistor to a rail
    for net, pl in sorted(nets.items()):
        if not _I2C_NET.search(net) or _is_gnd(net) or _is_rail(net):
            continue
        ics = sorted({r for r, _, _ in pl if is_ic(r)})
        if not ics:
            continue
        pulled = False
        for r, _, _ in pl:
            if _pref(r) == "R" and two_pin(r):
                other = [pn for pn in _pins(by_ref[r]) if pn[2] != net]
                if other and _is_rail(other[0][2]):
                    pulled = True
        if not pulled:
            for r in ics:
                add("od_no_pullup", r, f"open-drain bus {net} has no pull-up resistor to a supply rail (nothing pulls it high)")
    # crystals: both nets want a load capacitor to ground
    skipped = []
    for ref, p in by_ref.items():
        if str(p.get("kind") or "") == "xtal" or _pref(ref) in ("Y", "X"):
            pins = _pins(p)
            if len(pins) not in (2, 4):
                skipped.append(f"{ref} ({len(pins)}-pin crystal or oscillator)")
                continue
            # a 4-pin crystal has two signal pins and two case grounds: the load caps belong on the signal pins only
            signal = [net for _, _, net in pins if net and not _is_gnd(net)]
            if len(pins) == 4 and len(signal) != 2:
                skipped.append(f"{ref} (4-pin part whose signal pins could not be told from its grounds)")
                continue
            lacking = [net for net in signal if not caps_to_gnd.get(net)]
            if lacking:
                add("xtal_no_caps", ref, f"crystal without load capacitors: {', '.join(lacking)} has no capacitor to ground "
                    "(load caps CL are needed on both crystal pins)")
    scope = (f"Scope: the tool checked {len(by_ref)} part(s) of the netlist for {len(CLASSES)} rule classes: "
             + "; ".join(CLASSES.values()) + ". Not checked: component values against their datasheets, any other electrical rule, the board"
             + (f"; crystals it could not read: {', '.join(skipped)}" if skipped else "") + ".")
    if findings:
        text = (f"The tool's check of this sheet found {len(findings)} thing(s) to look at:\n" + "\n".join("- " + f["text"] for f in findings)
                + "\n\n" + scope)
    else:
        text = "The tool's check of this sheet found nothing in these rule classes (this is not a statement that the sheet is correct).\n\n" + scope
    return {"findings": findings, "classes": list(CLASSES), "scope": scope, "text": text, "sheets": len(store.sheet_ids(project)) if parts is None else 1,
            "parts": len(by_ref)}


_ASKS = re.compile(r"^\s*(?:please\s+)?(?:review|check)\s+(?:this|the|my)\s+(?:schematic\s+)?(?:sheet|schematic)\b", re.I)


def is_review_request(text):
    """Is this message the Schematic page's "Review this sheet" (or the same said another way)? Then the tool's own check runs first."""
    return bool(_ASKS.match(str(text or "")))
