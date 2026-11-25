"""Design findings the netlist sheets and the BOM can prove on their own, before anything is drawn in Altium (E2E kiln E2).

1. interface_nc: a part's pins whose names say they form a functional interface (SIM, USB data, antenna/RF, SWD, BOOT0, a
   modem's UART) all sit on the NC net. One finding per part and interface: "U6 SIM interface not connected (VSIM, SIM_DAT,
   SIM_CLK, SIM_RST)". Only some of them NC is an info row ("partly"), since one NC pin of a group (SIM_DET) is often fine.
2. requirement_uncovered: an Idea requirement (an agreed item or the goal) names a keyword (SIM, antenna, USB, thermocouple,
   display, flash, ...), a BOM line's role, value or description names the same thing, but the line's refs are on no netlist
   sheet: "Requirement 'nano-SIM': J3 (Nano-SIM socket) is in the BOM but on no sheet". A requirement no keyword matches, or a
   keyword no BOM line names, gets no finding: nothing is guessed. requirement_coverage() also gives the covered rows.

3. edge_uncovered: a confirmed requirement says "<part> on the <side> edge" and no confirmed edge constraint holds it. Needs
   only the BOM, not the sheets.

Pure functions over plain data (sheets: [{"id", "parts": [{"ref", "pins": [{"name", "num", "net"}]}]}], BOM lines as
store.bom_lines gives them, the idea dict). design_findings(project) reads the project and leaves out what the student marked
"intended" (dismiss(), kept in design-findings.json per finding key and instance: the same finding with other words comes back).
"""
import hashlib
import json
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pinnames  # noqa: E402

# ------------------------------------------------------------------ 1. interface pins on NC

_MODEM_RE = re.compile(r"modem|\bLTE\b|\bGSM\b|GPRS|NB-?IoT|Cat[- .]?M1?\b|Cat[- .]?1\b|(?<![.\d])\b[2345]G\b|cellular|WCDMA|UMTS", re.I)

# (key, label, pin-name regex, modem parts only); a name is the pin name, upper case, as the sheet has it
INTERFACES = (
    ("sim", "SIM", re.compile(r"^V?U?SIM(?:\d|_|$)|^U?SIM\d?_|^VSIM|^VUSIM|^USIM"), False),
    ("usb", "USB", re.compile(r"^USB\d?_?(?:D[PMN+\-]|DATA[PMN+\-])|^USB\d?_?D?[PN]$|^D[+\-]$"), False),
    ("rf", "antenna/RF", re.compile(r"^ANT(?!I)|^RF(?!U)(?:_|\d|IN|OUT|IO|$)"), False),
    ("swd", "SWD debug", re.compile(r"^SWD(?:IO|CLK|CK)$|^SWCLK$|^SW(?:DIO|CLK)$"), False),
    ("boot", "BOOT0", re.compile(r"^BOOT0?$"), False),
    ("uart", "UART", re.compile(r"^(?:MAIN_)?(?:UART\d?_)?(?:TXD?|RXD?)\d?$"), True),
)
_SKIP_RE = re.compile(r"DBG|DEBUG", re.I)          # a modem's debug UART is left open on purpose


def _pin_name(pin):
    return str(pin.get("name") or "").strip().upper()


def interface_of(name, modem=False):
    """(key, label) of the interface a pin name belongs to, or None."""
    if not name or _SKIP_RE.search(name):
        return None
    for key, label, rx, modem_only in INTERFACES:
        if modem_only and not modem:
            continue
        if rx.search(name):
            return key, label
    return None


def _line_text(line):
    return " ".join(str(line.get(k) or "") for k in ("role", "value", "description", "mpn"))


def _is_modem(ref, part, by_ref):
    return bool(_MODEM_RE.search(" ".join([str(part.get("value") or ""), str(part.get("kind") or ""),
                                           _line_text(by_ref.get(ref) or {})])))


def interface_nc(sheets, bom=()):
    """Findings for interface pins on the NC net, one per (part, interface)."""
    by_ref = {r: l for l in bom or [] for r in l.get("refs") or []}
    groups = {}                    # (ref, key) -> {"label", "sheet", "nc": [names], "wired": [names]}
    for sh in sheets or []:
        for part in sh.get("parts") or []:
            if not isinstance(part, dict) or not part.get("ref"):
                continue
            ref = str(part["ref"])
            modem = _is_modem(ref, part, by_ref)
            for pin in part.get("pins") or []:
                if not isinstance(pin, dict):
                    continue
                name = _pin_name(pin)
                hit = interface_of(name, modem)
                if not hit:
                    continue
                g = groups.setdefault((ref, hit[0]), {"label": hit[1], "sheet": sh.get("id"), "nc": [], "wired": []})
                net = str(pin.get("net") or "").strip()
                if pinnames.is_nc_net(net):
                    g["nc"].append(str(pin.get("name") or pin.get("num")))
                elif net:
                    g["wired"].append(str(pin.get("name") or pin.get("num")))
    _usb = re.compile(r"\bUSB", re.I)
    out = []
    for (ref, key), g in groups.items():
        if not g["nc"]:
            continue
        if key == "usb" and not any(_usb.search(_line_text(l)) for l in bom or [] if ref not in (l.get("refs") or [])):
            continue          # an MCU's USB pins left open on a board with no USB part elsewhere: not used, nothing to say
        names = ", ".join(dict.fromkeys(g["nc"]))
        if g["wired"]:
            msg = (f"{ref} {g['label']} interface partly not connected: {names} on NC while "
                   f"{', '.join(dict.fromkeys(g['wired']))} {'is' if len(g['wired']) == 1 else 'are'} wired")
            sev = "info"
        else:
            msg = f"{ref} {g['label']} interface not connected ({names})"
            sev = "warning"
        out.append({"id": "interface_nc", "key": f"interface_nc:{ref}:{key}", "severity": sev, "refs": [ref],
                    "sheet": g["sheet"], "message": msg,
                    "fix": (f"Wire the {g['label']} pins of {ref} to the part that serves them, or mark this intended. "
                            "If the module has it on board, the datasheet page must say so.")})
    return out


# ------------------------------------------------------------------ 2. requirement coverage

# (key, regex on the requirement text, regex on the BOM line's role/value/description)
KEYWORDS = (
    ("sim", r"\b(?:nano|micro|mini)?[- ]?U?SIM\b|\beSIM\b|SIM[- ]card", r"\bSIM\b|SIM[- ]?card|nano-?SIM|micro-?SIM"),
    ("antenna", r"antenna|U\.FL|\bIPEX\b|\bSMA\b", r"antenna|U\.FL|\bIPEX\b|\bSMA\b"),
    ("usb", r"\bUSB", r"\bUSB"),
    ("thermocouple", r"thermocouple|\btype[- ]K\b", r"thermocouple|MAX3185\d|MAX6675"),
    ("display", r"display|\bLCD\b|\bOLED\b|\bTFT\b|e-?paper|7-?seg", r"display|\bLCD\b|\bOLED\b|\bTFT\b|e-?paper|7-?seg"),
    ("flash", r"\bflash\b(?!ing)|\bEEPROM\b", r"\bflash\b|\bEEPROM\b|W25Q"),
    ("sd", r"micro-?SD|\bSD[- ]card|\bTF[- ]card", r"micro-?SD|\bSD[- ]card|\bTF[- ]card"),
    ("gnss", r"\bGNSS\b|\bGPS\b", r"\bGNSS\b|\bGPS\b"),
    ("ethernet", r"ethernet|\bRJ-?45\b", r"ethernet|\bRJ-?45\b|magnetics|\bPHY\b"),
    ("can", r"\bCAN(?:[- ]?bus|[- ]?FD)?\b", r"\bCAN\b|CAN[- ]?(?:bus|FD|transceiver)"),
    ("rs485", r"RS-?485", r"RS-?485"),
    ("relay", r"\brelays?\b", r"\brelay\b"),
    ("buzzer", r"buzzer|beeper", r"buzzer|beeper"),
    ("battery", r"\bbattery|\bLi-?(?:ion|po)\b|\bcoin cell", r"battery|\bLi-?(?:ion|po)\b|coin cell|\bCR20\d\d\b"),
    ("rtc", r"\bRTC\b|real[- ]time clock", r"\bRTC\b|real[- ]time clock"),
)
_KEYWORDS = tuple((k, re.compile(rq, 0 if k == "can" else re.I), re.compile(rb, 0 if k == "can" else re.I))   # CAN in capitals: not the word "can"
                  for k, rq, rb in KEYWORDS)


def requirements_of(idea):
    """[(topic, text)]: the idea's agreed items (a rejected one left out) and its goal."""
    idea = idea or {}
    out = []
    for a in idea.get("agreed") or []:
        if isinstance(a, dict) and str(a.get("text") or "").strip() and a.get("status") != "rejected":
            out.append((str(a.get("topic") or ""), str(a["text"])))
    if str(idea.get("goal") or "").strip():
        out.append(("Goal", str(idea["goal"])))
    return out


def _bom_role_text(line):
    return " ".join(str(line.get(k) or "") for k in ("role", "value", "description"))


def _line_label(line):
    for k in ("value", "description", "role"):
        if str(line.get(k) or "").strip():
            return str(line[k]).strip()
    return str(line.get("key") or "")


def requirement_coverage(idea, bom, sheets):
    """One row per (requirement, keyword) that a BOM line answers: {"requirement", "topic", "keyword", "status": "covered" |
    "missing", "on_sheet": [refs], "missing_parts": [{"line", "refs", "label"}]}. Empty while no sheet holds a part (the
    BOM stage: nothing is drawn yet, so nothing can be missing from a drawing)."""
    drawn = {str(p.get("ref")) for sh in sheets or [] for p in sh.get("parts") or [] if isinstance(p, dict) and p.get("ref")}
    if not drawn:
        return []
    lines = [l for l in bom or [] if l.get("refs") and not (l.get("dnp") or l.get("nobuy"))]
    rows = []
    for topic, text in requirements_of(idea):
        for key, rq, rb in _KEYWORDS:
            m = rq.search(text)
            if not m:
                continue
            hits = [l for l in lines if rb.search(_bom_role_text(l))]
            if not hits:
                continue                                  # no part names it: say nothing rather than guess
            on_sheet, missing = [], []
            for l in hits:
                refs = [str(r) for r in l["refs"]]
                gone = [r for r in refs if r not in drawn]
                on_sheet += [r for r in refs if r in drawn]
                if gone:
                    missing.append({"line": l.get("key"), "refs": gone, "label": _line_label(l)})
            rows.append({"requirement": m.group(0).strip(), "topic": topic, "keyword": key,
                         "status": "missing" if missing else "covered", "on_sheet": on_sheet, "missing_parts": missing})
    return rows


def coverage_findings(rows):
    out, seen = [], set()
    for r in rows:
        if r["status"] != "missing":
            continue
        if r["keyword"] in seen:                          # the goal and an agreed item naming the same thing: once
            continue
        seen.add(r["keyword"])
        parts = ", ".join(f"{', '.join(p['refs'])} ({p['label']})" for p in r["missing_parts"])
        n = sum(len(p["refs"]) for p in r["missing_parts"])
        out.append({"id": "requirement_uncovered", "key": f"requirement_uncovered:{r['keyword']}", "severity": "warning",
                    "refs": [x for p in r["missing_parts"] for x in p["refs"]],
                    "message": f"Requirement '{r['requirement']}': {parts} {'is' if n == 1 else 'are'} in the BOM but on no sheet",
                    "fix": "Draw these parts on a netlist sheet and wire them, or mark this intended."})
    return out


# ------------------------------------------------------------------ 3. "X on the left edge" with no constraint holding it

# "side" only for left / right: "all parts on the top side" is the assembly side of the board, not an edge
_EDGE_RE = re.compile(r"\b(?:on|at|along)\s+(?:the\s+)?(?:(left|right)(?:[- ]hand)?\s+(?:board\s+)?(?:edge|side)"
                      r"|(top|bottom)\s+(?:board\s+)?edge)\b", re.I)
_NOT_A_PART = re.compile(r"\b(?:no|not|nothing|never|clear|free|holes?)\b", re.I)
_LEAD = re.compile(r"^(?:(?:and|with|place|put|keep|the|a|an|one|its)\b\s*)+", re.I)
_TAIL = re.compile(r"(?:\s*\b(?:must|should|will|shall|to|be|is|are|sits?|goes|placed|mounted|located|sitting)\b)+$", re.I)


def _subjects(text):
    """[(subject, side, form)] of the "<part> on the <side> edge" phrases of a requirement (form: "edge" or "side"). A list after
    a colon ("Connectors on the left edge: USB-C and I2C") is the subject; the words before it only name the group."""
    out = []
    for clause in re.split(r"[;\n]|\.(?=\s|$)", text):
        start = 0
        for m in _EDGE_RE.finditer(clause):
            listed = re.match(r"\s*:\s*(.+)$", clause[m.end():])
            if listed:
                subject, start = listed.group(1), len(clause)
            else:
                subject, start = clause[start:m.start()].split(":")[-1], m.end()
            subject = _TAIL.sub("", _LEAD.sub("", subject.strip(" ,-"))).strip(" ,-")
            if subject and not _NOT_A_PART.search(subject):
                out.append((subject, (m.group(1) or m.group(2)).lower(), "edge" if re.search(r"edge", m.group(0), re.I) else "side"))
    return out


def _named_in(piece, bom, blocks):
    """The references of the parts a sentence fragment names anywhere in it ("Power enters through a USB-C connector": J1)."""
    import constraints
    words, found = re.findall(r"[A-Za-z0-9][A-Za-z0-9.+-]*", piece), []
    for n in (4, 3, 2, 1):
        for i in range(len(words) - n + 1):
            gram = " ".join(words[i:i + n])
            if len(gram) >= 3:
                found += [r for r in constraints.match_part(gram, bom, blocks, loose=True)["refs"] if r not in found]
    return found


def edge_findings(idea, bom):
    """One finding per part (or named thing) a confirmed requirement puts at a named edge while no confirmed edge constraint holds
    it there: the placer reads constraints only. A name that is no part of the BOM is a finding only when it is short and the
    requirement says "edge"; an ambiguous one is left to the student. [] while there is no BOM."""
    import constraints
    bom = [l for l in bom or [] if l.get("refs")]
    if not bom:
        return []
    blocks = (idea or {}).get("blocks") or []
    held = []                     # (refs, the target as written, side, subjects the student pointed at it)
    for it in constraints.confirmed(idea):
        if it["kind"] == "edge":
            got = constraints.match_part(it["target"], bom, blocks)["refs"]
            held.append((set(got), it["target"].lower(), it["side"], {h.lower() for h in it.get("holds", [])}))
    out = {}
    for a in (idea or {}).get("agreed") or []:
        if not isinstance(a, dict) or a.get("status") not in (None, "confirmed"):
            continue
        for subject, side, form in _subjects(str(a.get("text") or "")):
            for piece in (p for p in (_LEAD.sub("", x.strip()).strip() for x in re.split(r",|&|\band\b", subject)) if p):
                m = constraints.match_part(piece, bom, blocks)
                refs = m["refs"]
                if not refs and not m["candidates"] and form == "edge":
                    refs = _named_in(piece, bom, blocks)
                if not refs and (m["candidates"] or form != "edge" or len(piece.split()) > 3):
                    continue
                low = piece.lower()
                if any(s == side and (set(refs) <= got if refs else target == low or low in holds) for got, target, s, holds in held):
                    continue
                who = ", ".join(refs) or piece
                why = ("Add the edge constraint (one click on the Layout page), or mark this intended." if refs else
                       f"\"{piece}\" is not a part of the BOM: pick its part on the Layout page, or mark this intended.")
                out[f"edge_uncovered:{who}:{side}"] = {
                    "id": "edge_uncovered", "key": f"edge_uncovered:{who}:{side}", "severity": "warning", "refs": refs,
                    "side": side, "subject": piece, "message": f"Requirement says {who} on the {side} edge, no constraint holds it",
                    "fix": why}
    return list(out.values())


# ------------------------------------------------------------------ project level, with the student's "intended" marks

def _instance(f):
    return hashlib.sha1(f["message"].encode("utf-8")).hexdigest()[:8]


def _path(project):
    import store
    return store.pdir(project) / "design-findings.json"


def _marks(project):
    try:
        data = json.loads(_path(project).read_text(encoding="utf-8"))
        return data.get("intended") or {} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _sheets(project):
    import store
    return [dict(store.load_sheet(project, sid), id=sid) for sid in store.sheet_ids(project)]


def all_findings(project):
    """Every finding of these checks, each with its key, instance and "intended" (the student marked this very one)."""
    import store
    sheets, bom = _sheets(project), store.bom_lines(project)
    idea = store.load_idea(project)
    found = interface_nc(sheets, bom) + coverage_findings(requirement_coverage(idea, bom, sheets)) + edge_findings(idea, bom)
    marks = _marks(project)
    for f in found:
        f["instance"] = _instance(f)
        f["intended"] = (marks.get(f["key"]) or {}).get("instance") == f["instance"]
    return found


def design_findings(project):
    """{"open": [findings], "intended": [findings], "coverage": [rows]}; never raises (the state must always build)."""
    try:
        import store
        found = all_findings(project)
        cov = requirement_coverage(store.load_idea(project), store.bom_lines(project), _sheets(project))
    except Exception as exc:                  # noqa: BLE001
        return {"open": [], "intended": [], "coverage": [], "error": str(exc)}
    return {"open": [f for f in found if not f["intended"]], "intended": [f for f in found if f["intended"]],
            "coverage": [{k: r[k] for k in ("requirement", "topic", "status", "on_sheet")} |
                         {"missing": [x for p in r["missing_parts"] for x in p["refs"]]} for r in cov]}


def mark(project, key, intended=True):
    """The student's one click: this finding, as it reads now, is intended (or, intended=False, not any more)."""
    import store
    now = {f["key"]: f for f in all_findings(project)}
    if intended and key not in now:
        raise ValueError(f"no such finding now: {key}")
    marks = _marks(project)
    if intended:
        marks[key] = {"instance": now[key]["instance"], "message": now[key]["message"], "by": "student",
                      "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
    else:
        marks.pop(key, None)
    store._atomic_write_json(_path(project), {"intended": marks})
    return {"ok": True, "key": key, "intended": intended}
