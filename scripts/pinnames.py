"""Pin names that mean the same pin.

A schematic names a pin by a short form, a datasheet or a library symbol often by the long one (NE555: RST on one,
RESET on the other), with or without an active-low mark (~RST, /RESET, RST#, nRESET, RESET_N), and a diode's pins
are A/K on one and +/- on another. Used by the datasheet pin check (skills/verify_part.py) and by netlist.write when
it takes pin numbers from a built library symbol by name.
"""
import re

# each group is one pin function
ALIASES = [{"RST", "RESET"}, {"CTRL", "CONT", "CV", "CONTROL"}, {"THR", "THRES", "THRESH", "THRESHOLD"},
           {"DIS", "DISCH", "DISCHARGE"}, {"TRIG", "TRIGGER"}, {"GND", "GROUND"}, {"OUT", "OUTPUT"},
           {"EN", "ENABLE"}, {"SHDN", "SHUTDOWN"}, {"FB", "FEEDBACK"}, {"ADJ", "ADJUST"}]
# a two-pin diode or LED only: on a larger part "A" or "+" is some other pin
POLARITY = [{"A", "ANODE", "+"}, {"K", "CATHODE", "-"}]


def bare(name):
    """The name without an active-low mark."""
    out = re.sub(r"^[~/!]|#$|_[Nn]$", "", str(name or "").strip())
    return re.sub(r"^n(?=[A-Z]{2})", "", out)


def spellings(name):
    """Other spellings of the name: without its active-low mark, and its aliases. Never the name itself, never shorter
    than two letters (a bare "~" would match anything)."""
    b = bare(name)
    out = {b} if len(b) >= 2 else set()
    for group in ALIASES:
        if b.upper() in group:
            out |= group
    return out - {name}


def forms(name, two_pin=False):
    """Every upper-case spelling a pin name stands for, itself included (for comparing two names)."""
    up = str(name or "").strip().upper()
    out = {up} | {s.upper() for s in spellings(str(name or "").strip())}
    if two_pin:
        for group in POLARITY:
            if up in group:
                out |= group
    return out


def forms_among(name, names, two_pin=False):
    """forms() of a pin on a part whose pins are `names`: a _N pin with a _P twin is the negative side of a differential
    pair (CLK_N, CLK_P), not an active-low CLK, so it stands only for itself."""
    up = str(name or "").strip().upper()
    if re.search(r"_N$", up) and up[:-2] + "_P" in {str(n or "").strip().upper() for n in names}:
        return {up}
    return forms(name, two_pin)



NC_NETS = ("NC", "N/C", "NO_ERC")      # the nets the drawing and the checks treat as "pin deliberately unconnected"


def is_nc_net(net):
    """True for a pin net that means no-connect (NC, N/C, NO_ERC): the one definition draw, the schematic checks, the pin
    fingerprint and the open-pin gate share."""
    return str(net or "").strip().upper() in NC_NETS
