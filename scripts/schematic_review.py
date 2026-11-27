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
_SUPPLY = re.compile(r"^(?:[ADP]?V(?:DD|CC|BAT)[A-Z0-9_]*|VDD\w*)$", re.I)
_EP = re.compile(r"^(?:EP|EPAD|E-PAD|PAD|TAB|THERMAL\w*|EXP\w*|EXPOSED\w*|DAP)$", re.I)
_NC = re.compile(r"^(?:NC|N/C|NO[_-]?CONNECT|\*|)$", re.I)
_I2C_NET = re.compile(r"I2C|SCL|SDA", re.I)


def _is_gnd(net):
    return bool(_GND.match(str(net or "").strip()))


def _is_rail(net):
    n = str(net or "").strip()
    return bool(n) and not _is_gnd(n) and bool(_RAIL.search(n)) and not re.match(r"^[-~]", n)


def _pref(ref):
    return re.match(r"[A-Za-z]*", str(ref)).group(0).upper()


def _parts(project):
    out = []
    for sh in store.sheet_ids(project):
        try:
            out += [p for p in store.load_sheet(project, sh).get("parts", []) if p.get("ref")]
        except (OSError, ValueError, KeyError):
            continue
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

    caps = {}                      # rail net -> [cap refs with the other pin on ground]
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

    for ref, p in by_ref.items():
        if not is_ic(ref):
            continue
        pins = _pins(p)
        # decoupling: supply pins per rail against capacitors on that rail
        per_rail = {}
        for n, nm, net in pins:
            if _SUPPLY.match(nm.strip()) and _is_rail(net):
                per_rail.setdefault(net, []).append(nm)
        for net, names in per_rail.items():
            have = len(caps_to_gnd.get(net, []))
            if have < len(names):
                add("decap_missing", ref, f"decoupling capacitor missing: {len(names)} supply pin(s) ({', '.join(names)}) on {net} but only {have} "
                    f"capacitor(s) from {net} to ground; the datasheet asks for a bypass capacitor at each supply pin")
        # I2C/I3C device on a shared SPI bus
        names = [nm.upper() for _, nm, _ in pins]
        if any("SCL" in n for n in names) and any("SDA" in n for n in names) and any(n.split("/")[0] in ("CS", "NCS", "/CS") or n == "CS" for n in names):
            for n, nm, net in pins:
                if "SCL" in nm.upper() and net:
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
    for ref, p in by_ref.items():
        if (str(p.get("kind") or "") == "xtal" or _pref(ref) in ("Y", "X")) and two_pin(ref):
            lacking = [net for _, _, net in _pins(p) if net and not caps_to_gnd.get(net)]
            if lacking:
                add("xtal_no_caps", ref, f"crystal without load capacitors: {', '.join(lacking)} has no capacitor to ground "
                    "(load caps CL are needed on both crystal pins)")
    scope = (f"Scope: the tool checked {len(by_ref)} part(s) of the netlist for {len(CLASSES)} rule classes: "
             + "; ".join(CLASSES.values()) + ". Not checked: component values against their datasheets, any other electrical rule, the board.")
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
