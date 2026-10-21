"""Is a candidate the same part electrically? The pieces footprint_match needs beyond the land pattern: pin functions
for ICs and polar parts, value, kind and ratings for plain 2-pin resistors, capacitors and inductors. Anything that cannot be
read gives None / "unknown": nothing here guesses."""
import re

NONPOLAR = ("R", "C", "L")
POLAR_NAMES = {"+", "-", "A", "K", "POS", "NEG", "ANODE", "CATHODE"}
POLAR_WORDS = re.compile(r"electrolytic|tantalum|polar|alumin", re.I)
SPECIAL = {"thermistor": ("thermistor", "ntc", "ptc"), "varistor": ("varistor",), "potentiometer": ("potentiometer", "trimmer"),
           "fuse": ("fuse",), "photoresistor": ("photoresistor", "ldr"), "ferrite": ("ferrite", "bead"),
           "choke": ("choke", "transformer"), "varactor": ("varactor",)}
MAIN = {"R": "resistor", "C": "capacitor", "L": "inductor"}
MULT = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "": 1.0, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9}
NUM = r"(\d+(?:\.\d+)?)"


def norm_pin(name):
    return re.sub(r"[^A-Z0-9+\-]", "", str(name or "").upper())


def pin_diff(mine, theirs, typed=False):
    """The pins whose number is missing on one side, whose name differs, or (typed) whose electrical type differs."""
    a, b = {str(p["num"]): p for p in mine}, {str(p["num"]): p for p in theirs}
    out = []
    for n in sorted(set(a) | set(b), key=lambda s: (len(s), s)):
        if n not in a or n not in b:
            out.append(f"pin {n} is only on the {'line' if n in a else 'candidate'}")
        elif norm_pin(a[n]["name"]) != norm_pin(b[n]["name"]):
            out.append(f"pin {n} is {a[n]['name']} on the line, {b[n]['name']} on the candidate")
        elif typed and a[n].get("type") != b[n].get("type"):
            out.append(f"pin {n} ({a[n]['name']}) is {a[n].get('type')} on the line, {b[n].get('type')} on the candidate")
    return out


def is_polar(prefix, text, pins):
    """A 2-pin part whose pins have a direction: diodes and LEDs, electrolytic and tantalum capacitors."""
    if prefix not in NONPOLAR:
        return True
    return bool(POLAR_WORDS.search(text or "")) or any(norm_pin(p["name"]) in POLAR_NAMES for p in pins)


def value(prefix, text):
    """The value of a resistor (ohm), capacitor (F) or inductor (H) as a number, or None: 10k, 10K, 10kΩ, 4K7, 10000 are
    one value; 100nF and 0.1uF are one value."""
    t = str(text or "").replace("µ", "u").replace("μ", "u").replace("Ω", "R").replace("Ω", "R")
    if prefix == "R":
        m = re.search(r"(?<![\w.])(\d+)([kKMGR])(\d+)(?!\w)", t)
        if m:
            return float(f"{m[1]}.{m[3]}") * (1 if m[2] == "R" else MULT[m[2]])
        m = re.search(r"(?<![\w.])" + NUM + r"\s*([kKMG]?)\s*(?:R|[Oo]hms?)(?![A-Za-z])", t) or re.search(r"(?<![\w.])" + NUM + r"\s*([kKMG])(?![A-Za-z0-9])", t) or re.fullmatch(r"\s*" + NUM + r"\s*([kKMG]?)\s*", t)
    elif prefix == "C":
        m = re.search(r"(?<![\w.])" + NUM + r"\s*([pnu])\s*F(?![A-Za-z])", t) or re.fullmatch(r"\s*" + NUM + r"\s*([pnu])F?\s*", t)
    elif prefix == "L":
        m = re.search(r"(?<![\w.])" + NUM + r"\s*([num])\s*H(?![A-Za-z])", t) or re.fullmatch(r"\s*" + NUM + r"\s*([num])H?\s*", t)
    else:
        return None
    return float(m[1]) * MULT[m[2]] if m else None


def same_value(a, b):
    return abs(a - b) <= 1e-6 * max(abs(a), abs(b), 1e-12)


def kind(prefix, text, default=True):
    """What the text says the part is: a special kind (thermistor, fuse ...), else the plain kind of the prefix
    (resistor ...) when `default` or when the text names it, else None."""
    t = (text or "").lower()
    for k, words in SPECIAL.items():
        if any(re.search(r"\b" + w, t) for w in words):
            return k
    if default or MAIN.get(prefix, "\0") in t:
        return MAIN.get(prefix)
    return None


# ---------------------------------------------------------------- ratings: a part may replace another only if it is as good
DIEL = re.compile(r"(?<![A-Za-z0-9])(X[5-8][RSTUV]|C0G|NP0|NPO|Y5V|Z5U)(?![A-Za-z0-9])", re.I)
RATINGS = {  # prefix -> the ratings compared; the candidate must be at least as high, the tolerance at most as loose
    "C": ["volts", "tol", "diel"], "R": ["watts", "tol"], "L": ["amps", "tol"]}
ONE = r"(?<![\w.])"


def _num(s):
    a, _, b = s.partition("/")
    return float(a) / float(b) if b else float(a)


def ratings(name, text):
    """Every figure of one rating stated in `text` (volts, watts, amps, tolerance in %), or the dielectric class; [] if absent.
    An inductor may state two currents (Isat, Irms): the comparison takes the worst of each side."""
    t = str(text or "")
    if name == "volts":
        return [float(m[1]) for m in re.finditer(ONE + r"(\d+(?:\.\d+)?)\s*V(?:DC|dc)?(?![A-Za-z0-9])", t)]
    if name == "watts":
        return [_num(m[1]) * (1e-3 if m[2] else 1) for m in re.finditer(ONE + r"(\d+/\d+|\d+(?:\.\d+)?)\s*(m?)W(?![A-Za-z0-9])", t)]
    if name == "amps":
        return [float(m[1]) * (1e-3 if m[2] else 1) for m in re.finditer(ONE + r"(\d+(?:\.\d+)?)\s*(m?)A(?![A-Za-z0-9])", t)]
    if name == "tol":
        return [float(m[1]) for m in re.finditer(r"(\d+(?:\.\d+)?)\s*%", t)]
    if name == "diel":
        return [("C0G" if m[1].upper() in ("NP0", "NPO") else m[1].upper()) for m in DIEL.finditer(t)]
    return []


def rating(name, text):
    """The first figure of one rating stated in `text`, or None."""
    got = ratings(name, text)
    return got[0] if got else None


LABEL = {"volts": "voltage rating", "watts": "power rating", "amps": "current rating", "tol": "tolerance", "diel": "dielectric"}


def ratings_check(prefix, mine_text, their_text, code):
    """(None, "") when the candidate is as good as the line on every rating the line states; ("different", why) when one
    is worse or another dielectric class; ("unknown", why) when the line states a rating the candidate's text does not.
    A rating the line does not state is not compared."""
    unknown = ""
    for name in RATINGS.get(prefix, ()):
        mine, theirs = ratings(name, mine_text), ratings(name, their_text)
        if not mine:
            continue
        if not theirs:
            a = mine[0]
            unknown = unknown or f"the {LABEL[name]} of {code} is not in its description (the line states {a})"
            continue
        if name == "diel":
            a, b = mine[0], theirs[0]
            if set(theirs) != {a}:
                return "different", f"{code} is {b}, the line {a}: another dielectric class"
            continue
        a, b = (min(mine), max(theirs)) if name == "tol" else (max(mine), min(theirs))
        if (name == "tol" and b > a) or (name != "tol" and b < a):
            return "different", f"the {LABEL[name]} of {code} ({b:g}) is {'looser' if name == 'tol' else 'lower'} than the line's ({a:g})"
    return ("unknown", unknown) if unknown else (None, "")
