"""Does a BOM line hold as many parts as its role names? "CC1/CC2 pull-downs" on R1 alone orders one resistor of two.

The rule is deliberately narrow (a false alarm costs trust). It never edits the BOM; it only returns the finding.
It looks at R, C, L and FB lines only (a connector, an IC or an ESD array serves several signals with one part) and
needs one of:
  - an explicit count: "2x", "x2", "pair of", "caps pair", "two resistors", "both" with a plural noun;
  - two or more DIFFERENT nets named next to a passive noun: the same name with another number or sign (CC1/CC2, D+/D-)
    or a known signal group (SDA/SCL, TX/RX, input/output ...). Two names of one net or bus ("I2C/SMBus") are neither.
    The noun must be plural, or a pull-up / pull-down (one pull resistor cannot serve two nets; one termination
    resistor or capacitor can, so those need the plural). "between" / "across" means one part bridges the two.
Lines with the same role are counted together (the parts may be split over lines with different values)."""
import re

PASSIVE = re.compile(r"(?:R|C|L|FB)\d+", re.I)
_PLURAL = r"(?:resistors|caps|capacitors|inductors|ferrites|beads|pull[- ]?ups|pull[- ]?downs)"
_NOUN = re.compile(rf"\b(?:{_PLURAL}|pull[- ]?up|pull[- ]?down)\b", re.I)
_PLURAL_RE = re.compile(rf"\b{_PLURAL}\b", re.I)
_BRIDGES = re.compile(r"\b(?:between|across)\b", re.I)

# "2x VDD" counts parts; "2x gain" does not
# "100nF x2" counts only after a value ("X2" alone is the safety-capacitor class or a crystal's pin 2)
_TIMES = (re.compile(r"(?<![\w.])([2-9]|1\d)\s*[x×]\s+(?=[A-Za-z0-9])", re.I),
          re.compile(r"(?<![\w.])\d[\w.µΩ%]*\s+[x×]\s?([2-9]|1\d)(?![\w.])", re.I))
_RATIO = re.compile(r"gain|attenuat|oversampl|multipli|\bAAA?\b|safety|mains|class\s*[XY]", re.I)
_DESIGNATOR = re.compile(r"(?:R|C|L|FB)\d+", re.I)
_PAIR = re.compile(r"(?<!differential )(?<!diff )(?<!twisted )\bpair of\b|\b(?:caps?|capacitors?|resistors?|pull[- ]?(?:up|down)s?) pair\b", re.I)
_WORDS = {"two": 2, "three": 3, "four": 4}
_WORD_COUNT = re.compile(rf"\b(two|three|four)\s+(?:[\w-]+\s+){{0,2}}?{_PLURAL}\b", re.I)

_ITEM = r"(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9_]*(?:[+](?![A-Za-z0-9])|-(?![A-Za-z0-9]))?"
_RUN = re.compile(rf"{_ITEM}(?:\s*(?:/|,|&|\band\b)\s*{_ITEM})+")
_GROUPS = ({"sda", "scl"}, {"tx", "rx"}, {"txd", "rxd"}, {"input", "output"}, {"in", "out"}, {"vin", "vout"}, {"dp", "dm"},
           {"canh", "canl"}, {"mosi", "miso", "sck", "sclk", "cs", "nss"}, {"sdi", "sdo"}, {"swdio", "swclk"}, {"rts", "cts"},
           {"tms", "tck", "tdi", "tdo"}, {"xin", "xout"})
_NUMBERED = re.compile(r"([a-z_]*[a-z_])(\d{1,2}|[+-])")


def _different_nets(a, b):
    a, b = a.lower(), b.lower()
    if a == b:
        return False
    head = a[:a.rfind("_") + 1]
    if head and b.startswith(head):          # USB_DP / USB_DM, UART_TX / UART_RX
        a, b = a[len(head):], b[len(head):]
    if any(a in g and b in g for g in _GROUPS):
        return True
    ma, mb = _NUMBERED.fullmatch(a), _NUMBERED.fullmatch(b)
    return bool(ma and mb and ma.group(1) == mb.group(1) and ma.group(2) != mb.group(2))


def parts_named(role):
    """How many parts the role says there are; 0 when it does not say (see the module's rule)."""
    role = str(role or "")
    counts = [0]
    if not _RATIO.search(role):
        counts += [int(m.group(1)) for rx in _TIMES for m in rx.finditer(role)]
    if _PAIR.search(role) or (re.search(r"\bboth\b", role, re.I) and _PLURAL_RE.search(role) and not _BRIDGES.search(role)):
        counts.append(2)
    counts += [_WORDS[m.group(1).lower()] for m in _WORD_COUNT.finditer(role)]
    if _NOUN.search(role) and not _BRIDGES.search(role):
        for run in _RUN.finditer(role):
            items = re.findall(_ITEM, run.group(0))
            nets = {x.lower() for x in items if any(_different_nets(x, y) for y in items)}
            counts.append(len(nets))
    return max(counts)


def designators(role):
    """The designators ("R1/R2") an enumeration of the role names: the parts are named, so they count wherever they are."""
    out = set()
    for run in _RUN.finditer(str(role or "")):
        items = re.findall(_ITEM, run.group(0))
        out |= {x.upper() for x in items if _DESIGNATOR.fullmatch(x)}
    return out


def _key(role):
    return " ".join(str(role or "").split()).casefold()


def finding(line, lines=()):
    """The finding for BOM line `line` ({"key", "role", "refs"}), or "". `lines`: the other lines of the BOM, to count
    those that carry the same role."""
    role, refs = str(line.get("role") or "").strip(), list(line.get("refs") or [])
    if not refs or not all(PASSIVE.fullmatch(str(r)) for r in refs):
        return ""
    want = parts_named(role)
    # a role that names designators (R1/R2 on R1, "(top)" / "(bottom)"): one held by another line of the BOM is not missing
    elsewhere = {str(r).upper() for o in lines for r in (o.get("refs") or []) if o.get("key") != line.get("key")}
    want -= len(designators(role) & elsewhere - {str(r).upper() for r in refs})
    if len(refs) >= want:
        return ""
    held = len(refs) + sum(len(o.get("refs") or []) for o in lines
                           if o.get("key") != line.get("key") and _key(o.get("role")) == _key(role))
    if held >= want:
        return ""
    return (f'{line.get("key")}: the role "{role}" names {want} parts but there {"is" if held == 1 else "are"} {held} '
            f'({", ".join(map(str, refs))}): add the missing refs or change the role')
