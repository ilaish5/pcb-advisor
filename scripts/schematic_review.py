"""The tool's own review of the schematic: rule classes checked on the project's netlist, with the scope stated (R2, ACCEPTANCE W22).

    review(project) -> {"findings": [{"class", "ref", "text"}], "classes": [...], "scope": str, "text": str, "sheets": n, "parts": n}

A review the model alone wrote ("0 errors") has no scope: it read some files, ran no check, and says nothing about what it looked at. This
module is the check that has one. It reads every sheet of the netlist and applies five rule classes; each finding names the part, the net
and what to do. `text` is what the student reads: the findings, then the scope (what was checked, and what was not). With no finding it
says "no finding in these rule classes", never "0 errors".

Rule classes (each is a netlist check, none is a guess about values):
  decap_missing    a supply pin whose own datasheet asks a capacitor (value by value) that the rail does not have left for it
  i3c_shared_spi   an I2C/I3C-capable device (SCL + SDA + CS pins) whose SCL net is also another device's SPI clock
  od_no_pullup     an I2C-named open-drain bus with no resistor from the net to a supply rail
  ep_not_gnd       an exposed / thermal pad pin that is not on a ground net
  xtal_no_caps     a 2-pin crystal with no load capacitor to ground on one of its two nets
"""
import math
import re
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import store  # noqa: E402
import decap_requirements  # noqa: E402

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
    """The capacitance in farads of a BOM value text ('100nF', '4.7uF', '10 pF' and the infix forms '4u7', '2n2', '100n', '1u0'), None when not readable."""
    unit = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "μ": 1e-6, "m": 1e-3, "": 1.0}
    t = str(value or "")
    m = re.match(r"^\s*(\d+)([pnuµμ])(\d+)\s*f?(?![A-Za-z0-9])", t, re.I)
    if m:
        return float(f"{m.group(1)}.{m.group(3)}") * unit[m.group(2).lower()]
    m = re.match(r"^\s*(\d*\.?\d+)\s*([pnuµμm]?)\s*f?\b", t, re.I)
    if not m:
        return None
    return float(m.group(1)) * unit[m.group(2).lower()]


_DNP_VALUE = re.compile(r"^\s*(?:dnp|dni|dnf|np|nm|not\s+(?:fitted|populated)|do\s+not\s+(?:fit|populate|place))\b", re.I)


def _is_dnp(part):
    """A part that is not fitted: it is not a capacitor, a resistor or anything else on the board."""
    return bool(part.get("dnp") or part.get("nobuy")) or bool(_DNP_VALUE.match(str(part.get("value") or "")))


def _fmt_farads(f):
    return f"{f * 1e6:g} uF" if f >= 1e-6 * 0.999 else f"{f * 1e9:g} nF"


def _datasheets(project):
    """{ref: the text of the part's datasheet} for the BOM lines whose datasheet file has readable text."""
    out = {}
    try:
        import sources
        folder = store.pdir(project) / "sources"
        for line in store.bom(project, write=False):
            ds = line.get("datasheet")
            if not ds:
                continue
            try:
                text = sources.text_of(ds, folder)
            except (OSError, ValueError, KeyError):
                continue
            if text and text.strip():
                for r in line.get("refs") or []:
                    out[r] = text
    except Exception:           # noqa: BLE001 - no datasheet text means every pin is "not checked", never a guess
        return {}
    return out


def _pref(ref):
    return re.match(r"[A-Za-z]*", str(ref)).group(0).upper()


def _parts(project):
    out = []
    for sh in store.sheet_ids(project):
        try:
            out += [dict(p) for p in store.load_sheet(project, sh).get("parts", []) if p.get("ref")]
        except (OSError, ValueError, KeyError):
            continue
    try:                           # a capacitor's size, an IC's part number and a do-not-fit mark are in the BOM, not on the sheet
        lines = {r: l for l in store.bom(project, write=False) for r in (l.get("refs") or [])}
    except Exception:       # noqa: BLE001 - without the BOM every capacitor counts as one of unknown size and no part number is known
        lines = {}
    for p in out:
        l = lines.get(p["ref"]) or {}
        if not p.get("value") and l.get("value"):
            p["value"] = l["value"]
        if not p.get("mpn") and l.get("mpn"):
            p["mpn"] = l["mpn"]
        if l.get("dnp") or l.get("nobuy"):
            p["dnp"] = True
    return out


def _pins(part):
    return [(str(p.get("num", p.get("number", ""))), str(p.get("name") or ""), str(p.get("net") or "").strip()) for p in part.get("pins", [])]


def review(project, parts=None, datasheets=None):
    datasheets = (_datasheets(project) if parts is None else {}) if datasheets is None else datasheets
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
        if _pref(ref) == "C" and two_pin(ref) and not _is_dnp(p):
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

    # decoupling. A decap belongs to the pin's NET (a capacitor from that rail to ground, wherever on the schematic it is drawn; how near it sits is a
    # board check). What each supply pin asks comes from a SOURCE that says it (decap_requirements: the cited family table, else a strict row of the
    # part's own datasheet text); a pin with no such source is "not checked" with the reason, never a guess from prose or from the part family. Slots:
    # a high-frequency slot takes a ceramic of 1x to 10x the value, a bulk slot 0.4x to 10x; a capacitor serves one slot. A capacitor that is not fitted
    # (DNP) is not a capacitor; one whose value cannot be read fills no slot and makes the pin "not checked" (naming the part) when slots stay empty.
    pool = {}                      # rail net -> [cap refs]
    for net, refs in caps_to_gnd.items():
        pool[net] = sorted(refs, key=lambda r: (len(r), r))
    groups = {}                    # (ic ref, pin name, net) -> pin numbers
    for ref, p in sorted(by_ref.items()):
        if is_ic(ref) and not _is_dnp(p):
            for n, nm, net in _pins(p):
                if _is_supply_name(nm) and _is_rail(net):
                    groups.setdefault((ref, nm, net), []).append(n)
    not_checked = []
    used = {}                      # rail net -> caps already assigned
    device_done = set()            # (ref, source) whose per-device slots were asked already
    for (ref, nm, net), nums in sorted(groups.items(), key=lambda kv: (not _is_analog_supply(kv[0][1]), kv[0])):
        nums = [n for n in nums if n]
        pins_txt = (f"pin{'s' if len(nums) > 1 else ''} {', '.join(nums)} ({nm})" if nums else f"supply pin {nm}") + f" on {net}"
        if not pool.get(net):
            add("decap_missing", ref, f"decoupling capacitor missing: {pins_txt} has no capacitor to ground on the net at all")
            continue
        text = (datasheets or {}).get(ref)
        mpn = by_ref[ref].get("mpn") or by_ref[ref].get("value") or ""
        req = decap_requirements.requirement(nm, mpn, text or "")
        if not req:
            why = ("no cited requirement for this part (not in the family table) and its datasheet text is not available" if not text else
                   "no cited requirement for this part (not in the family table) and its datasheet text has no power-supply row for this pin")
            not_checked.append(f"{ref} {nm} on {net}: {why}")
            continue
        taken = used.setdefault(net, set())
        free0 = [c for c in pool[net] if c not in taken]
        unreadable = [c for c in free0 if _farads(by_ref[c].get("value")) is None]
        best = None                # (missing slots, assigned caps, scheme)
        for sch in req["schemes"]:
            slots = []             # (role, farads, label)
            for n in (nums or [""]):
                lab = f"pin {n} ({nm})" if n else f"pin {nm}"
                slots += [(s["role"], s["farads"], lab) for s in sch.get("per_pin", [])]
            key = (ref, req["group"])
            if key not in device_done:
                slots += [(s["role"], s["farads"], "the part") for s in sch.get("per_device", [])]
            slots.sort(key=lambda s: (s[0] != "bulk", -s[1]))        # the bulk capacitors first, so a 1 uF never goes to a 100 nF slot it fits only by ratio
            free = list(free0)
            got, miss = [], []
            for role, want, lab in slots:
                cand = [c for c in free if decap_requirements.fits(role, want, _farads(by_ref[c].get("value")))]
                cand.sort(key=lambda c: abs(math.log(_farads(by_ref[c].get("value")) / want)))
                if cand:
                    free.remove(cand[0])
                    got.append(cand[0])
                else:
                    miss.append((role, want, lab))
            if best is None or len(miss) < len(best[0]):
                best = (miss, got, sch, key)
            if not miss:
                break
        miss, got, sch, key = best
        taken.update(got)
        device_done.add(key)
        if not miss:
            continue
        if unreadable:
            not_checked.append(f"{ref} {nm} on {net}: the value of " + ", ".join(f"{c} ({by_ref[c].get('value') or 'no value'})" for c in unreadable[:4])
                               + " cannot be read, so the slots it may fill cannot be counted")
            continue
        left = [f"{c} {by_ref[c].get('value')}" for c in pool[net] if c not in taken][:4]
        for role, want, lab in miss:
            add("decap_missing", ref, f"decoupling capacitor missing: {lab} on {net} needs a {_fmt_farads(want)} {'bulk' if role == 'bulk' else 'ceramic'} capacitor of its own "
                f"({sch['why']}); the rail has {len(pool[net])} capacitor(s) to ground, each serves one slot and none is left that fits"
                + (f" (left unused: {', '.join(left)})" if left else ""))
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
             + (f"; crystals it could not read: {', '.join(skipped)}" if skipped else "")
             + (f"; decoupling not checked ({len(not_checked)}): {'; '.join(not_checked[:8])}" + (f"; and {len(not_checked) - 8} more (all of them are listed under the answer)" if len(not_checked) > 8 else "") if not_checked else "") + ".")
    if findings:
        text = (f"The tool's check of this sheet found {len(findings)} thing(s) to look at:\n" + "\n".join("- " + f["text"] for f in findings)
                + "\n\n" + scope)
    else:
        text = "The tool's check of this sheet found nothing in these rule classes (this is not a statement that the sheet is correct).\n\n" + scope
    return {"findings": findings, "classes": list(CLASSES), "not_checked": not_checked, "scope": scope, "text": text, "sheets": len(store.sheet_ids(project)) if parts is None else 1,
            "parts": len(by_ref)}


_ASKS = re.compile(r"^\s*(?:please\s+)?(?:review|check)\s+(?:this|the|my)\s+(?:schematic\s+)?(?:sheet|schematic)\b", re.I)


def is_review_request(text):
    """Is this message the Schematic page's "Review this sheet" (or the same said another way)? Then the tool's own check runs first."""
    return bool(_ASKS.match(str(text or "")))
