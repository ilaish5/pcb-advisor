"""
A datasheet's pin table, read from its text, and a part's pins compared with it.

A row is ONE line that starts with the pin number(s) and then names the pin (`3  OUT  O  Output`; or, in a table whose first
column is the name, `GND  2  2  2  Ground`). A number in prose, in another row or in a pin diagram is never a row, so
"1" near "GND" proves nothing. A table has a heading (Pin Configuration / Pin Functions / Pin Description / Terminal ...) above it.
Several numbering columns (SOIC / DIP / QFN) belong to the packages named in the header: the column of the part's package is
used, and when the package cannot be told and the columns differ the answer is "unchecked", never "pass".

    check(texts, pins, package=..., mpn=..., pads=[...]) -> {"verify", "issues", "notes", "evidence"}

Used by skills/verify_part.py; no file or project is read here. The rule behind every answer: only what the text proves is
"pass"; whatever the parser cannot read stays "unchecked" with the reason.
"""
import re

import pinnames

HEADING = re.compile(r"\b(pins?|terminals?|pads?|balls?)\b", re.I)
SECTION_END = re.compile(r"^\s*(table\s+[\d.-]+\.?\s+)?(pin|terminal)\s+(configurations?|functions?|descriptions?|assignments?|definitions?)\b"
                         r"|^\s*[\d.]+\s+(pin|terminal)\s+(configurations?|functions?|descriptions?)\b", re.I)
MAX_GAP = 10                    # lines of wrapped description / page footer allowed between two rows of one table
HEADING_REACH = 14              # lines between a heading and the first row (figure text, column headings)

_DASHES = {"-", "—", "–", "--", "---", "n/a", "na"}
_NUMBER = r"(?:[A-Za-z]{1,2}[1-9]\d{0,2}|[1-9]\d{0,2}|0)"
_CELL = re.compile(rf"^{_NUMBER}(?:,{_NUMBER})*$")
_RANGE = re.compile(r"^([1-9]\d{0,2})[-–]([1-9]\d{0,2})$")
_ANNOT = re.compile(r"^\(\w{1,4}\)$")
_VOLTAGE_NAME = re.compile(r"^[1-9][Vv][0-9]\w*$")          # a supply pin named by its voltage: 3V3, 1V8, 5V0
_NAMEFIRST = re.compile(r"^[A-Za-z~/#_+-][A-Za-z0-9_/#~+\-]*$")

POWER_TYPES = {"P", "PWR", "POWER", "S", "SUPPLY", "PI", "PO"}
GROUND_TYPES = {"G", "GND", "GROUND"}
IO_TYPES = {"I", "O", "I/O", "IO", "INPUT", "OUTPUT", "AI", "AO", "B", "I/OD", "OD", "IN", "OUT"}
TYPES = POWER_TYPES | GROUND_TYPES | IO_TYPES | {"NC", "PASSIVE", "—", "-", "–"}

_TYPE_ONLY = {"I", "O", "I/O", "IO", "AI", "AO", "B", "P", "G", "S", "PWR", "—", "-", "–"}     # codes no pin is named
# A package family is read in any case (`Sot-23`, `sot-23-5 package`); the short ones that are also words (`Connect to GND`,
# `so that`) only in capitals and with a size (TO-220, SC-70, SO-8). A size in mils is no pin count, also when two sizes share
# it (`SOIC 150/208-mil` is SOIC, not SOIC-150)
_PKG = re.compile(r"\b((?:PDIP|CDIP|DIP|SOIC|TSSOP|VSSOP|SSOP|MSOP|SOP|SOT|SOD|SC|SO|TSOT|DSBGA|WLCSP|FBGA|NFBGA|BGA|UFQFPN|UQFN|VQFN|WQFN|"
                  r"QFN|WSON|USON|DFN|SON|LQFP|TQFP|LFCSP|QFP|TO|DPAK|SMA|SMB|SMC|PQFN|LGA))"
                  r"(?:[\s-]*(\d{1,3}(?:-\d{1,2})?)(?![\d.]|\s?[x×]|\s?mm|\s?/\s?\d{2,3}\s?-?\s?mil)(?:[\s-]*mil)?)?"
                  r"(?![A-Za-z])", re.I)
_WORDLIKE = {"TO", "SC", "SO"}      # also words of a sentence: a package only as printed, in capitals and with a size
_EP = re.compile(r"\b(thermal|exposed|power)[\s-]?pad\b|\bepad\b|\bpowerpad\b|^\W*(?:[\d,]+\W+)?(?:ep|pad)\b", re.I)    # an exposed-pad row
_SIZED = {"tsot", "so", "tssop", "ssop", "vssop", "msop", "dip", "qfn", "dfn", "lqfp", "tqfp", "qfp", "ufqfpn", "bga", "sot"}


# ------------------------------------------------------------------ one line

def _tokens(line):
    """[(text, gap)]: gap = two or more spaces before it (a column break in layout text)."""
    return [(m.group(2), len(m.group(1)) >= 2) for m in re.finditer(r"(\s*)(\S+)", line)]


def _cell(tok):
    """A pin-number cell: [numbers] ('' list for a dash: the pin has no number in this package), or None."""
    t = tok.strip().rstrip(";")
    if t.lower() in _DASHES:
        return []
    if _CELL.match(t.rstrip(",")):
        return t.rstrip(",").split(",")
    if "," in t and "-" in t:             # a list that holds ranges: `1,2,11,14,36-53` (each part a number or a range, nothing else)
        out = []
        for piece in t.rstrip(",").split(","):
            one = _cell(piece) if not _is_mixed(piece) else None
            if not one:
                return None
            out += one
        return out
    m = _RANGE.match(t)
    if m and 0 < int(m.group(2)) - int(m.group(1)) <= 64:
        return [str(n) for n in range(int(m.group(1)), int(m.group(2)) + 1)]
    return None


def _is_mixed(piece):
    return "," in piece


def _is_alnum_cell(cell):
    return any(not n.isdigit() for n in cell)


_PAD_WORDS = {"thermal", "exposed", "power", "heat", "die"}


def _name_cell(toks):
    """The tokens of the name cell: the first word and the words joined to it (`/HOLD or /RESET`, `SDA / SDI`, `PA13 (SWDIO)`,
    `Thermal Pad`). What follows is the description: its words are never part of the name (`IN Input from the VCC rail`)."""
    if not toks:
        return []
    out = [toks[0][0]]
    i = 1
    while i < len(toks):
        t, prev = toks[i][0], out[-1].lower()
        if t.lower() in ("or", "and", "&") or t.startswith("/") or prev in ("or", "and", "&") or prev.endswith(("/", ",")):
            out.append(t)
        elif t.startswith("(") and not toks[i][1]:            # `DO (IO1)`, `GND (Thermal pad)`: a group ends at its ")"
            j = i
            while j < len(toks) and j < i + 4 and not toks[j][0].endswith(")"):
                j += 1
            if j >= len(toks) or not toks[j][0].endswith(")"):
                break
            out += [x for x, _ in toks[i:j + 1]]
            i = j
        elif len(out) == 1 and out[0].lower() in _PAD_WORDS and t.lower().rstrip("s") in ("pad", "paddle"):
            out.append(t)
        else:
            break
        i += 1
    return out


def _row(nums, rest):
    name = _name_cell(rest)
    if not name or not re.match(r"[~/#_+-]*(?:[A-Za-z]|[1-9][Vv][0-9]\w*$)", name[0]) or (name[0].islower() and len(name[0]) > 2 and name[0].isalpha()):
        return None
    after = [t for t, _ in rest[len(name):len(name) + 1]]
    typ = after[0].upper() if after and after[0].upper() in TYPES else ""
    tail = rest[len(name):]
    return {"nums": nums, "name": " ".join(name), "type": typ, "rest": " ".join(t for t, _ in tail),
            "isolated": not tail or tail[0][1]}       # a column break (layout text) after the name cell: the cell is told from the description


def parse_number_first(line):
    """`1  4  8  VIN  Input Voltage` -> {"nums": [["1"], ["4"], ["8"]], "name": "VIN", "type": ""}; None when the line is not a row."""
    if re.search(r"\.{4,}", line):
        return None
    line = re.sub(r"(?<=\d)\s*,\s+(?=\d)", ",", line)
    toks = _tokens(line)
    cells, i = [], 0                         # (cell, index after it)
    while i < len(toks):
        c = _cell(toks[i][0])
        if c is None:
            break
        i += 1
        if i < len(toks) and _ANNOT.match(toks[i][0]):
            i += 1
        cells.append((c, i))
    while len(cells) > 1 and cells[-1][0] and _is_alnum_cell(cells[-1][0]):     # `A3 A1 I/O`: the second A1 is the name
        cells.pop()
    if not cells or cells[-1][1] >= len(toks):
        return None
    return _row([c for c, _ in cells], toks[cells[-1][1]:])


def parse_name_first(line):
    """`MR  3  —  4  I  Manual reset` (a table whose first column is the name) -> row, or None."""
    if re.search(r"\.{4,}", line):
        return None
    toks = _tokens(re.sub(r"(?<=\d)\s*,\s+(?=\d)", ",", line))
    if len(toks) < 2 or not (_NAMEFIRST.match(toks[0][0]) or _VOLTAGE_NAME.match(toks[0][0])) or not re.search(r"[A-Za-z]", toks[0][0]):
        return None
    cells, i = [], 1
    while i < len(toks):
        c = _cell(toks[i][0])
        if c is None or (c and _is_alnum_cell(c)):
            break
        cells.append(c)
        i += 1
    if not cells or all(not c for c in cells):
        return None
    typ = toks[i][0].upper() if i < len(toks) and toks[i][0].upper() in TYPES else ""
    return {"nums": cells, "name": toks[0][0], "type": typ, "rest": " ".join(t for t, _ in toks[i:])}


# ------------------------------------------------------------------ packages

def _canon(label):
    s = re.sub(r"\d+\s*-?\s*mil\b", "", label.lower())
    s = re.sub(r"[^a-z0-9]", "", s)
    s = re.sub(r"^[pc]dip", "dip", s)
    s = re.sub(r"^(soic|sop)", "so", s)
    s = re.sub(r"^[uvw]qfn", "qfn", s)
    s = re.sub(r"^(wson|uson|son)", "dfn", s)
    s = re.sub(r"^sot23(\d)$", r"sot2\1", s)            # SOT-23-5 is SOT25
    m = re.match(r"^sot(2[5-8])(\d)$", s)               # SOT-25-5 is SOT25 (the count repeated); SOT-25-6 is not
    if m and {"25": "5", "26": "6", "28": "8"}.get(m.group(1)) == m.group(2):
        s = "sot" + m.group(1)
    return s


def package_labels(text):
    """Package names written in a piece of text: ['SOIC-8', 'DIP-8', 'SOT25'] (a size in mils is not a pin count)."""
    out = []
    for m in _PKG.finditer(text or ""):
        digits = m.group(2) or ""
        if digits and re.search(r"mil", m.group(0), re.I) and int(digits.split("-")[0]) >= 100:
            digits = ""
        if m.group(1).upper() in _WORDLIKE and (not digits or not m.group(1).isupper()):
            continue
        label = (m.group(1) + ("-" + digits if digits else "")).upper()
        if label not in out:
            out.append(label)
    return out


def package_relation(label, package):
    """'exact' (the same package), 'family' (the same package family, one side without a size) or ''."""
    a, b = _canon(label), _canon(package)
    if not a or not b:
        return ""
    if a == b:
        return "exact"
    fa, ra = re.match(r"([a-z]+)(\d*)", a).groups()
    fb, rb = re.match(r"([a-z]+)(\d*)", b).groups()
    if fa == fb and fa in _SIZED and (not ra or not rb or fa == "sot" and "sot23" in (a, b)):      # "5-Pin SOT-23" is any SOT-23-N
        return "family"
    return ""


_IPC = re.compile(r"^[A-Z]+\d+P\d+X\d+(?:X\d+)?-(\d{1,3})[A-Z]*$", re.I)


def ipc_pins(package):
    """The pin count of an IPC-7351 footprint name (SOT95P285X140-5N -> 5); None for any other text."""
    m = _IPC.match((package or "").strip())
    return int(m.group(1)) if m else None


def package_pins(package):
    c = _canon(package)
    m = re.match(r"([a-z]+)(\d+)$", c)
    if not m:
        return None
    if m.group(1) == "sot":
        return {"23": 3, "25": 5, "26": 6, "28": 8}.get(m.group(2))
    return int(m.group(2)) if m.group(1) in _SIZED else None


# ------------------------------------------------------------------ tables

def _name_first_header(header_lines):
    """The table's first column is the name (`NAME  NO.  TYPE`, or a NAME line and device columns), not the number."""
    lines = [ln.strip().upper() for ln in header_lines]
    num = r"(NO\.?|NUMBER|NUM|#)"
    if any(re.search(rf"\bNAME\b.*\b{num}(\s|$)", ln) for ln in lines):
        return True
    if any(re.search(rf"\b{num}(\s|$)", ln) for ln in lines):
        return False
    return any(re.match(r"NAME\b", ln) for ln in lines)


def _plausible(rows):
    """A table whose 'names' are mostly pin types (I/O, O, —) was read in the wrong column order: not a table."""
    return sum(r["name"].upper() in _TYPE_ONLY for r in rows) * 2 < len(rows)


_FUNC_COL = re.compile(r"(?<![A-Za-z0-9])(?:F|AF|ALT|FUNC)\s?\d{1,2}(?![A-Za-z0-9])")


def _function_table(header_lines):
    """A function-select (alternate function) table: `GPIO  F1  F2 ... F9`, `AF0 AF1 ...`. Its numbers are GPIO numbers and
    its first cells peripheral functions (SPI0 RX, UART0 TX): never the package pinout, whatever its heading says. A pin table
    with a name column beside its IO MUX columns (`No.  Name  Type  F0  F1  F2`, ESP32 "Pin Overview") is a pinout: its
    number and name are read, the function columns are only its description."""
    funcs = any(len(set(_FUNC_COL.findall(ln))) >= 3 for ln in header_lines)
    return funcs and not any(re.search(r"\bname\b", ln, re.I) for ln in header_lines)


def _modal(rows):
    """(K, rows): the table's usual number of numbering cells and the rows that have it. A dash at the end may be the pin
    type (`GND 7 —`) rather than a column."""
    def bare_size(nums):
        n = len(nums)
        while n and not nums[n - 1]:
            n -= 1
        return n
    sizes = [bare_size(r["nums"]) for r in rows]
    k = max(set(sizes), key=lambda n: (sizes.count(n), n))
    out = []
    for r in rows:
        if len(r["nums"]) == k + 1 and not r["nums"][-1]:        # `GND 7 —`: the dash is the pin type, not a column
            r = {**r, "nums": r["nums"][:-1], "type": r["type"] or "—"}
        if len(r["nums"]) == k:
            out.append(r)
    return k, out


def _repeating_columns(rows):
    """The numbering columns (of the usual row width) that give one number to two rows. Such a column is not a pin numbering:
    a truth table (`0  0  X`, `0  1  Hardware`), or a package that bonds several pins to one (an SO8 column of an STM32G0
    table); the other columns of the table stay. Rows of the variants of one part (`NR  4  Noise reduction, fixed version
    only` beside `FB  4  Feedback, adjustable version only`) give one number twice and are a pinout: see _variant_rows."""
    k, use = _modal(rows)
    out = set()
    for i in range(k):
        nums = [n.upper() for r in use for n in r["nums"][i]]
        if len(nums) != len(set(nums)) and not (k == 1 and _variant_rows(use, i)):
            out.add(i)
    return out, k


_VARIANT = re.compile(r"\b(only|versions?|fixed|adjustable)\b", re.I)


def _variant_rows(rows, i):
    """Every row whose number another row also has says it is for one variant of the part (only, version, fixed,
    adjustable): either reading of that pin is the part's."""
    count = {}
    for r in rows:
        for n in r["nums"][i]:
            count[n.upper()] = count.get(n.upper(), 0) + 1
    twice = [r for r in rows if any(count[n.upper()] > 1 for n in r["nums"][i])]
    return bool(twice) and all(_VARIANT.search(f"{r['name']} {r.get('rest', '')}") for r in twice)


_CAPTION = re.compile(r"\b(figure|fig\.|top view|bottom view|package drawing)\b", re.I)
_HEADER_CELL = re.compile(r"(?:(?:PINS?|TERMINALS?|NAME|NO\.?|NUM\.?|NUMBER|#)\s*)+")      # `PIN`, `NAME`, `NO.`, `PIN NO.`: as printed, upper case


def _header_labels(line):
    """The package names of a column-header row, in the order of its cells; None when the line is not a column-header row.
    A header row is tabular (two or more cells divided by a column break: two spaces or more) and holds a column word
    (NAME, NO., PIN, TERMINAL: a whole cell, upper case); the package names are its other cells. A line of package names
    alone never is one, and neither is a sentence:
    `The VSSOP and SOIC packages have no exposed pad`, `Numbering of VSSOP and SOIC`, a caption, a title."""
    if _CAPTION.search(line) or SECTION_END.search(line) or re.match(r"\s*table\s+[\d.-]+", line, re.I):
        return None
    cells = [c.strip() for c in re.split(r"\s{2,}|\t", line.strip()) if c.strip()]
    if len(cells) < 2:
        return None
    if not any(_HEADER_CELL.fullmatch(c) for c in cells):
        return None                  # a line of package names alone (side-by-side pin diagram labels) widens the scope, ties nothing
    return [package_labels(c)[0] for c in cells if len(package_labels(c)) == 1 and len(c.split()) <= 2]


def find_tables(text):
    """Every pin table of the text: [{"heading", "labels", "rows"}], in the order of the document."""
    lines = (text or "").replace("\f", "\n").splitlines()
    tables, seen = [], set()           # seen: lines already part of a table
    for h, line in enumerate(lines):
        if h in seen or not HEADING.search(line) or re.search(r"\.{4,}", line):
            continue
        for j in range(h + 1, min(len(lines), h + 1 + HEADING_REACH)):
            header = lines[h:j]
            parse = parse_name_first if _name_first_header(header) else parse_number_first
            if parse(lines[j]) is None:
                continue
            if j in seen:
                break
            rows, gap, k = [], 0, j
            while k < len(lines) and gap <= MAX_GAP:
                r = parse(lines[k])
                if r:
                    rows.append(r)
                    gap = 0
                else:
                    gap += 1
                    if k > j and SECTION_END.search(lines[k]):
                        break
                k += 1
            if len({tuple(map(tuple, r["nums"])) for r in rows}) >= 2 and _plausible(rows):
                seen.update(range(h, k))
                repeating, width = _repeating_columns(rows)
                if _function_table(lines[h:j]) or len(repeating) == width:
                    break                   # not the pinout; its lines are taken, so a later "pin" line does not find it again
                # columns are tied to packages only by a column-header row (see _header_labels); the scope of the table is its
                # heading and header lines, never a figure caption
                label_lines = [lb for lb in (_header_labels(lines[i]) for i in range(h + 1, j)) if lb]
                scope = [lb for lb in package_labels(" ".join(x for x in lines[h:j] if not _CAPTION.search(x)))]
                tables.append({"heading": " ".join(x.strip() for x in lines[h:j] if x.strip())[:200],
                               "labels": scope,
                               "label_lines": label_lines, "rows": rows,
                               "ep_lines": [x for x in lines[j:k] if _EP.search(x)]})
            break
    big = [t for t in tables if len(t["rows"]) >= 3]
    return big or tables           # a 2-row 'table' beside real ones is a figure's text


def _columns(table):
    """The table's numbering columns: [{"index", "label"}]. A row has the table's usual number of cells (K) or is not used."""
    k, rows = _modal(table["rows"])
    repeating, _ = _repeating_columns(table["rows"])
    labels, per_line = table["labels"], table.get("label_lines", [])
    # Several columns are tied to package names only when ONE header line names exactly K packages (its text order is the
    # column order); names spread over lines, or a different count, tie nothing: every column stays a candidate
    tied = k > 1 and len(per_line) == 1 and len(per_line[0]) == k
    cols = []
    for i in range(k):
        label = per_line[0][i] if tied else None
        if i in repeating:               # one number on two rows: not a pin numbering (see _repeating_columns)
            table.setdefault("dropped", []).append(label)
            continue
        cols.append({"index": i, "label": label, "scope": labels if label is None else [label], "k": k, "rows": rows,
                     "mapped": k == 1 or tied, "heading": table["heading"], "ep_lines": table.get("ep_lines", []),
                     "variants": k == 1 and _variant_rows(rows, i)})
    return cols


def _numbers(col):
    out = []
    for r in col["rows"]:
        out += [n.upper() for n in r["nums"][col["index"]]]
    return out


_SUPPLY_PAIRS = [{"VCC", "VDD"}, {"GND", "VSS"}]       # the only names taken for one another beside pinnames.ALIASES (VIN stays apart)


def _squash(text):
    """The name in capitals without punctuation. A leading or trailing sign is one form: IN+ = +IN, IN- = -IN (never + with -)."""
    t = str(text).strip().replace("\u2212", "-").replace("\u2013", "-")
    m = re.fullmatch(r"([+-])?(.*?)([+-])?", t, re.S)
    lead, core, trail = m.groups()
    core = re.sub(r"[^A-Z0-9+]", "", core.upper())
    return core + (trail or lead or "") if core else re.sub(r"[^A-Z0-9+]", "", t.upper())


def _low_marked(cell):
    """The table's name carries an active-low mark (~RESET, /CS, CS#, RESET_N, nRESET)."""
    return bool(re.search(r"(?:^|[\s(,])[~!/]\w|\w#|_[Nn]\b|(?:^|[\s(,])n[A-Z]{2}", cell))


def _name_forms(name, with_bare=True, table_names=None):
    """table_names: every name the table uses (squashed). VCC~VDD / GND~VSS holds unless the table uses both spellings: a table
    with a VDD row and a VCC row has two different pins, and neither name stands for the other."""
    forms = {name}
    if with_bare:
        forms |= pinnames.spellings(name)
        forms |= {pinnames.bare(f) for f in forms}
    out = {f for f in map(_squash, forms) if f}
    for group in _SUPPLY_PAIRS:
        if out & group:
            if table_names is None or not group <= table_names:
                out |= group
    return out


def _cell_forms(cell):
    """What a table's name cell can be called: the whole cell, each `/` or `or` alternative, each parenthesised group.
    The words of a longer text are never forms of their own (`Input from the VCC rail` does not name VCC)."""
    out = set()

    def add(text):
        for f in (text, pinnames.bare(text.strip())):
            f = _squash(f)
            if f:
                out.add(f)

    groups = re.findall(r"\(([^)]*)\)", cell)
    for chunk in groups + [re.sub(r"\([^)]*\)", " ", cell)]:
        for alt in re.split(r"\s+(?:or|and)\s+|\s*[&,;]\s*", chunk, flags=re.I):
            if alt.strip():
                add(alt)
                for part in alt.split("/"):
                    if part.strip():
                        add(part)
    return out


_ACTIVE_LOW = {"RST", "RESET", "CS", "SS", "INT", "IRQ", "WP", "HOLD", "OE", "WE", "RD", "WR", "CE", "SHDN", "STBY", "FAULT", "ALERT",
               "PG", "PGOOD", "NMI", "SLEEP", "WAKE"}


def _plain_n(name, cell):
    """CLK_N against a cell with no active-low mark: the negative side of a pair or an active-low clock, not the plain CLK.
    A function that is active-low by nature (RESET_N, CS_N) keeps matching the plain RESET, CS: the text loses the overbar."""
    m = re.fullmatch(r"(.+)_N", str(name).strip(), re.I)
    return bool(m) and m.group(1).upper() not in _ACTIVE_LOW and not _low_marked(cell)


def table_names_of(rows):
    return {f for r in rows for f in _cell_forms(r["name"])}


def name_matches(name, cell, table_names=None):
    """The netlist's pin name is the table's name for the pin, in the spelling of the table or another (RESET/RST, /CS = CS#,
    VCC = VDD, GND = VSS). `A` is one of the alternatives of `A/B` (one pin, two functions). A netlist name of several
    functions `A/B` is the table's when one of them is the cell's own name (outside its brackets) and every other one is in
    the cell too or nowhere in the table: `DO/IO1` is `DO (IO1)`, `~{HOLD}/~{RESET}/IO3` is `/HOLD or /RESET` (IO3 is no other
    row), `USART2_TX/PA2` is `PA2 (USART2_TX)`; `TIM2_CH1/PA5` is never `PA0 (TIM2_CH1)`, nor `USART2_TX/PA3` `PA2 (USART2_TX)`.
    CLK_N is not a plain CLK."""
    cells = _cell_forms(cell)

    def forms(text):
        return _name_forms(text, with_bare=not _plain_n(text, cell), table_names=table_names)

    if forms(name) & cells:
        return True
    if any(_pn_same(name, alt) for alt in re.split(r"\s+(?:or|and)\s+|/", re.sub(r"\([^)]*\)", " ", str(cell))) if alt.strip()):
        return True
    alts = _alternatives(name)
    primary = _cell_forms(re.sub(r"\([^)]*\)", " ", str(cell)))
    if not alts or not any(forms(a) & primary for a in alts):
        return False
    return all(forms(a) & cells or (table_names is not None and not forms(a) & table_names) for a in alts)


def _pn_key(name):
    """The name with the side of a pair written as a letter, or "" when its last word names no side: USB_D- = USB_DM = USB_DN,
    USB_D+ = USB_DP, CLK+ = CLKP, CLK- = CLKN. A + is never a - (the two sides stay apart)."""
    tokens = [t for t in re.split(r"[_.\s]+|-(?=.)", str(name).strip().upper()) if t]
    if not tokens:
        return "", False
    last, marked = tokens[-1], True
    if last in ("D+", "DP"):
        last = "DP"
    elif last in ("D-", "DM", "DN"):
        last = "DN"
    elif len(last) > 1 and last[-1] in "+-":
        last = last[:-1] + ("P" if last[-1] == "+" else "N")
    else:
        marked = False
    return re.sub(r"[^A-Z0-9]", "", "".join(tokens[:-1] + [last])), marked


def _pn_same(a, b):
    """One pin of a pair spelt two ways (USB_D- / USB_DM, CLK+ / CLKP): the same letters once a side mark is a letter."""
    (ka, ma), (kb, mb) = _pn_key(a), _pn_key(b)
    return bool(ka) and ka == kb and (ma or mb)


def _alternatives(name):
    """The functions of a netlist name `A/B/C` (a leading `/` is an active-low mark, not a divider); [] for a single name."""
    parts = [p for p in re.split(r"(?<=[^\s/])/(?=[^\s/])", str(name).strip()) if p.strip()]
    return parts if len(parts) > 1 else []


def polarity_unclear(name, cell, table_names=None):
    """CLK_N against a plain CLK: they would match but for the mark, which the text may have lost (an overbar)."""
    return (_plain_n(name, cell) and not name_matches(name, cell, table_names)
            and bool(_name_forms(name, table_names=table_names) & _cell_forms(cell)))


_GROUND = re.compile(r"^(?:[ADPS]?GND\w*|VSS\w*|GROUND\w*)$")
_EP_NAME = re.compile(r"^(?:EP|EPAD|PAD|DAP|TAB|THERMAL\w*|EXPOSED\w*|POWERPAD|PPAD|HEATSINK)$")


def _is_ep_row(row):
    """A row of the exposed (thermal) pad: Thermal Pad, EP, PAD, Exposed Pad, PowerPAD."""
    first = _squash(row["name"].split()[0]) if row["name"].split() else ""
    return bool(_EP_NAME.match(first)) or bool(_EP.search(row["name"]))


_NET_TOKEN = re.compile(r"[+-]?V(?:CC|DD|IN|OUT|EE|BAT|BUS|REF|S|SW|CCA|CCB|DDA|DDIO)\w*[+-]?|V[+-]|[+-]V", re.I)
_NET_WORDS = {"SW", "LX", "OUT", "IN", "EN", "FB", "BOOT", "PG", "PGOOD", "SS"}                  # as printed, upper case
_CONNECT_GND = re.compile(r"\bconnect(?:ed)?\s+(?:it\s+|them\s+)?to\s+(?:the\s+)?(?:GND|ground|VSS)\b", re.I)
_NEGATED = re.compile(r"\b(?:not|never|n't)\b[^.;]{0,20}\bconnect", re.I)
_EP_FAMILY = re.compile(r"^(?:EP|EPAD|PAD|DAP|POWERPAD|PPAD|THERMAL\w*|EXPOSED\w*)$")


def _nets_in(text):
    """(grounds, others): the net names a piece of text names: GND, VSS, ground names / V-, VIN, VOUT, SW, ..."""
    grounds, others = set(), set()
    for tok in re.split(r"[\s/(),;:]+", str(text)):
        tok = tok.rstrip(".")
        if not tok:
            continue
        if _GROUND.match(_squash(tok)):
            grounds.add(_squash(tok))
        elif _NET_TOKEN.fullmatch(tok) or tok in _NET_WORDS:
            others.add(_squash(tok))
    return grounds, others


def _ep_ok(name, rows, lines):
    """May the exposed pad (rows: its table rows, lines: text lines about it) carry this netlist pin name? True only when
    - the name cell of the pad row names exactly this net or an alias of it (`PAD (VIN)`, `EP/GND`), or
    - the pin is named for the pad itself (EP, PAD, Thermal Pad) and the table has a pad row or a line about it, or
    - it is a ground, and the pad row's text says "connect to GND / ground" and names no other net anywhere (name cell,
      description, lines).
    Everything else is not shown: unchecked. That is a net named only in a description, a ground beside another named net,
    TAB, and a pad the table says nothing about (a footprint's extra pad proves a pad, not its net: an op-amp's is V-)."""
    up = _squash(name)
    cells = set().union(*[_cell_forms(r["name"]) for r in rows]) if rows else set()
    if _name_forms(name) & cells:
        return True
    text = " ".join([f"{r['name']} {r.get('rest', '')}" for r in rows] + list(lines))
    if _EP_FAMILY.match(up):
        return bool(rows or lines)
    if not _GROUND.match(up):
        return False
    if not rows and not lines:
        return False
    grounds, others = _nets_in(text)
    return bool(_CONNECT_GND.search(text)) and not others and not _NEGATED.search(text)


def _words_of(text):
    return {w for w in map(_squash, re.split(r"[\s/(),;]+", text)) if w}


def _complete(nums):
    """The table's numbers are 1..N without a gap: it is the whole pin list, so a count and a missing pin mean something."""
    plain = [n for n in nums if n.isdigit()]
    return (bool(plain) and len(plain) == len(nums) and len(set(plain)) == len(plain)          # every pin once
            and set(map(int, plain)) == set(range(1, max(map(int, plain)) + 1)))


def _type_note(ref_name, typ):
    if not typ:
        return ""
    up = ref_name.upper()
    gnd = re.match(r"^[ADP]?GND\w*$|^VSS\w*$", up)
    pwr = re.match(r"^V(CC|DD|BAT|BUS)\w*$|^\+\d", up)
    io = re.match(r"^(GPIO|IO)\d+$|^P[A-K]\d+$", up)
    if gnd and typ in IO_TYPES:
        return f"{ref_name} is a ground name, the datasheet types the pin {typ}"
    if pwr and typ in ("I/O", "IO", "B"):
        return f"{ref_name} is a supply name, the datasheet types the pin {typ}"
    if io and (typ in POWER_TYPES or typ in GROUND_TYPES):
        return f"{ref_name} is a signal name, the datasheet types the pin {typ}"
    return ""


_SIDES = {}
for _group, _sides in {"sign": [("P", "+", "DP", "D+", "POS", "PLUS"), ("N", "-", "DM", "DN", "D-", "NEG", "MINUS")],
                       "dir": [("I", "IN", "INPUT", "XI"), ("O", "OUT", "OUTPUT", "XO")],
                       "uart": [("TX", "TXD"), ("RX", "RXD")], "spi": [("MISO",), ("MOSI",)],
                       "color": [("R", "RED"), ("G", "GREEN"), ("B", "BLUE")], "level": [("H", "HIGH"), ("L", "LOW")]}.items():
    for _i, _words in enumerate(_sides):
        for _w in _words:
            _SIDES.setdefault(_w, set()).add((_group, _i))


def _polar_tokens(text):
    """The words of a name (`USB_D-` -> USB, D-), a trailing sign kept on its word."""
    first = str(text).split()[0] if str(text).split() else ""
    return [t for t in re.split(r"[_.~{}/#!]+|-(?=.)", first.upper()) if t]


def _sides(token):
    out = set(_SIDES.get(token, ()))
    if len(token) > 1 and token[-1] in "+-":
        out |= _SIDES[token[-1]]
    return out


def _polar(name, cell):
    """The two names are the two sides of a pair (+/-, P/N, DP/DM, IN/OUT, I/O, TX/RX, MISO/MOSI, R/G/B, H/L, A/B, any two
    single letters): different pins, never one spelt two ways."""
    ta, tb = _polar_tokens(name), _polar_tokens(cell)
    for x in ta:
        for y in tb:
            if x != y and ({g for g, _ in _sides(x)} & {g for g, _ in _sides(y)} or (len(x) == 1 and len(y) == 1 and x.isalpha() and y.isalpha())):
                if not (_sides(x) & _sides(y)):
                    return True
    return False


_SELECT_WORDS = [{"CS", "CSN", "NCS", "SS", "SSN", "NSS"}]      # a chip select by its other names (near, never a match)


def _near(name, cell):
    """Two names that may be one pin spelt two ways: the same numbers, and one is the other with letters left out (VREG_IN /
    VREG_VIN) or both are the same prefix with another last word (QSPI_SS / QSPI_CSn). GPIO3 / GPIO4, RESET / OUT and GND /
    VIN are different pins."""
    a, b = _squash(pinnames.bare(str(name).strip())), _squash(pinnames.bare(str(cell).split()[0] if str(cell).split() else ""))
    if not a or not b or re.findall(r"\d+", a) != re.findall(r"\d+", b) or _polar(name, cell):
        return False
    short, long_ = sorted((a, b), key=len)
    it = iter(long_)
    if len(short) >= 3 and short[0] == long_[0] and all(ch in it for ch in short):
        return True
    ta = [t for t in re.split(r"[_\-.]", str(name).strip().upper()) if t]
    tb = [t for t in re.split(r"[_\-.]", str(cell).split()[0].upper() if str(cell).split() else "") if t]
    if not (len(ta) >= 2 and len(ta) == len(tb) and ta[:-1] == tb[:-1] and len(ta[0]) >= 2):
        return False
    x, y = _squash(ta[-1]), _squash(tb[-1])          # the last words: one select name (SS / CSn), or one inside the other
    short, long_ = sorted((x, y), key=len)
    it = iter(long_)
    return (any(x in g and y in g for g in _SELECT_WORDS)
            or (len(short) >= 2 and short[0] == long_[0] and all(ch in it for ch in short)))


def _evaluate(col, pins, pads):
    """One numbering column against the part's pins: {"conflict": [...], "absent": [...], "notes": [...], "count": n|None, "pins": n}."""
    nums = _numbers(col)
    label = col["label"] or (col["scope"][0] if len(col["scope"]) == 1 else "")
    out = {"conflict": [], "absent": [], "notes": [], "count": None, "label": label, "nums": nums}
    complete = _complete(list(dict.fromkeys(nums)) if col.get("variants") else nums)     # variant rows: each pin once
    top = max(int(n) for n in nums if n.isdigit()) if complete else 0
    ep_rows = [r for r in col["rows"] if _is_ep_row(r)]
    ep_lines = list(col.get("ep_lines") or [])
    names = table_names_of(col["rows"])
    have = {str(p).strip().upper() for p in pads} if pads is not None else None
    extra_pads = bool(have) and any(not h.isdigit() or h == "0" or (complete and int(h) > top) for h in have if h not in set(nums))
    ep_evidence = bool(ep_rows or col.get("ep_lines") or extra_pads)
    beyond = sorted(int(n) for n, _ in pins if complete and n.isdigit() and int(n) > top)
    # EP pin top+1, or split into top+1 .. top+k: a few pads past a real pin list, never most of the part's pins past a 1- or
    # 2-row "table"
    ep_split = bool(beyond) and beyond == list(range(top + 1, top + 1 + len(beyond))) and len(beyond) <= top // 2
    for num, name in pins:
        hits = [r for r in col["rows"] if num.upper() in {n.upper() for n in r["nums"][col["index"]]}]
        if not hits:
            ep_like = num == "0" or num.upper() in ("EP", "EPAD", "PAD", "TAB", "DAP") or (ep_split and num.isdigit() and int(num) in beyond)
            if re.fullmatch(r"N\.?/?C\.?|DNC|NC\d*|NO_?CONNECT|NO_?CONN", name.strip().upper()) and num.upper() not in nums:
                out["notes"].append(f"pin {num} {name}: the pin table lists no row for it (no-connect pins often are not listed)")
            elif ep_like:
                if not ep_evidence:
                    out["absent"].append(f"pin {num} {name}: no pin of the table, and neither the table nor the footprint shows an exposed pad")
                elif _ep_ok(name, ep_rows, ep_lines):
                    out["notes"].append(f"pin {num} {name}: taken for the exposed pad of the datasheet")
                elif not ep_rows and not ep_lines:
                    out["absent"].append(f"pin {num} {name}: exposed pad: the datasheet's table does not say its net")
                else:
                    out["absent"].append(f"pin {num} {name}: the datasheet does not show the exposed pad on the net {name}")
            elif (complete and not col.get("pkg_match") and num.isdigit() and int(num) in beyond
                  and beyond == list(range(top + 1, top + 1 + len(beyond)))):
                # pins top+1 .. top+k, too many for an exposed pad: the table may be cut short (a page break, a partial list)
                out["absent"].append(f"pin {num} {name}: the datasheet's pin table lists {len(set(nums))} pins, the part has more "
                                     f"(the table may be cut short)")
            elif complete:
                out["conflict"].append(f"pin {num} {name}: the datasheet's pin table has {len(set(nums))} pins, none is {num}")
            else:
                out["absent"].append(f"pin {num} {name}")
            continue
        good = [r for r in hits if name_matches(name, r["name"], names) or (_is_ep_row(r) and _ep_ok(name, [r], ep_lines))]
        if not good:
            unclear = [r for r in hits if polarity_unclear(name, r["name"], names)]
            swallowed = [r for r in hits if not r.get("isolated", True) and _name_forms(name, table_names=names) & _words_of(r.get("rest", ""))]
            if any(_is_ep_row(r) for r in hits):
                out["absent"].append(f"pin {num} {name}: the datasheet's exposed pad row ({hits[0]['name']}) does not name the net {name}")
            elif unclear:
                out["absent"].append(f"pin {num} {name}: the datasheet's name {unclear[0]['name']} has no active-low mark; "
                                     f"the text may have lost it")
            elif swallowed:
                out["absent"].append(f"pin {num} {name}: the name cell of the datasheet row ({swallowed[0]['name']}) cannot be told "
                                     f"from its description")
            else:
                others = [str(r["nums"][col["index"]][0]) for r in col["rows"]
                          if name_matches(name, r["name"], names) and r["nums"][col["index"]]]
                # VREG_IN / VREG_VIN, QSPI_SS / QSPI_CSn: a spelling, not proof of a wrong pin; only when the name is near this
                # one row of the table and no other pin of the part sits crosswise on it (its name near this row, and this
                # name near the row at its number)
                near = [r for r in hits if _near(name, r["name"])]
                near_all = [r for r in col["rows"] if _near(name, r["name"])]
                cross = any(n2 != num and _near(nm2, near[0]["name"])
                            and any(_near(name, r["name"]) for r in col["rows"]
                                    if n2.upper() in {x.upper() for x in r["nums"][col["index"]]})
                            for n2, nm2 in pins) if near else False
                if near and not others and len(near_all) == 1 and not cross:
                    out["absent"].append(f"pin {num} {name}: the datasheet calls pin {num} {near[0]['name']}, which may be "
                                         f"another spelling of {name}")
                    continue
                out["conflict"].append(f"pin {num} {name}: the datasheet calls pin {num} {' / '.join(dict.fromkeys(r['name'] for r in hits))}"
                                       + (f" and puts {name} on pin {', '.join(dict.fromkeys(others))}" if others else ""))
            continue
        note = _type_note(name, good[0]["type"])
        if note:
            out["notes"].append(f"pin {num}: {note}")
    if complete:
        out["count"] = len(set(nums))
        if pads is not None:
            want = {n.upper() for n in nums}
            ep_nums = {n.upper() for r in ep_rows for n in r["nums"][col["index"]]}
            missing = sorted(want - have - ep_nums, key=lambda s: (len(s), s))
            extra = sorted(have - want - {"0"}, key=lambda s: (len(s), s))          # a pad 0 is the exposed pad
            beyond_pads = sorted(int(e) for e in extra if e.isdigit())
            split_ok = bool(ep_rows or col.get("ep_lines")) and beyond_pads == list(range(top + 1, top + 1 + len(beyond_pads)))
            extra = [e for e in extra if not (not e.isdigit() or (e == str(top + 1) and len(extra) == 1) or split_ok)]    # an exposed / mechanical pad
            if missing or extra:
                out["conflict"].append(f"the datasheet {label or 'pin table'} lists {len(want)} pins, the footprint has "
                                       f"{len(have)} pads" + (f" (no pad {', '.join(missing)})" if missing else "")
                                       + (f" (extra pad {', '.join(extra)})" if extra else ""))
    return out


def _by_pads(units, pads):
    """Of several numbering columns, those whose pin numbers are the footprint's pad numbers (an exposed pad aside): the package
    shows in the footprint even when the BOM's package text (an IPC name such as SOT95P285X140-5N) says nothing."""
    want = {str(p).strip().upper() for p in pads or [] if str(p).strip().isdigit()}
    if not want or len(units) < 2:
        return units
    same = [u for u in units if {n for n in _numbers(u) if n.isdigit()} == want]
    return same or units


def _units(tables, package, pads=None):
    """The numbering columns that can be this part's: all, or those of its package and footprint; (units, why_none)."""
    units = [c for t in tables for c in _columns(t)]
    count = ipc_pins(package)
    labels = package_labels(package.upper()) if package and not count else []      # the BOM's spelling may be lower case
    if not labels:
        if count and len(units) > 1:
            units = [u for u in units if len(set(_numbers(u))) == count] or units
        return _by_pads(units, pads), ""
    mine = labels[0]
    rank = []
    for u in units:
        rels = [package_relation(lb, mine) for lb in u["scope"]] if u["scope"] else [None]
        rank.append("exact" if "exact" in rels else "family" if "family" in rels else "any" if rels == [None] else "")
        u["pkg_match"] = rank[-1] in ("exact", "family")         # the table names this part's package
    for want in ("exact", "family", "any"):
        found = [u for u, r in zip(units, rank) if r == want]
        if found:
            pins = package_pins(mine)
            if len(found) > 1 and pins:
                same = [u for u in found if len(set(_numbers(u))) == pins]
                found = same or found
            return _by_pads(found, pads), ""
    seen = sorted({lb for u in units for lb in u["scope"]})
    dropped = [lb for t in tables for lb in t.get("dropped", []) if lb and package_relation(lb, mine)]
    if dropped:
        return [], (f"the datasheet's {dropped[0]} column (the package of this part, {mine}) gives one pin number to several "
                    f"rows (pins bonded together), so it is not compared" + (f"; the other columns are for {', '.join(seen)}"
                                                                             if seen else ""))
    return [], f"the datasheet's pin tables are for {', '.join(seen)}, the package of this part is {mine}"


def _known(col, pins):
    """How many of the part's pins the column's table names, at any number (a name of several functions counts when one of
    them is in the table: a swapped `USART2_TX/PA3` still belongs to the table of PA2 and PA3)."""
    names = table_names_of(col["rows"])
    return sum(1 for _, name in pins
               if any(name_matches(name, r["name"], names) for r in col["rows"])
               or any(_name_forms(a, table_names=names) & names for a in _alternatives(name)))


def check(texts, pins, package="", pads=None):
    """texts: the document's text, best layout first ([layout, plain]); pins: [(number, name)]. Answer:
    {"verify": "pass"|"mismatch"|"unchecked", "issues": [...], "notes": [...], "evidence": str}."""
    # The first text (layout, then plain) with a table that can be this part's decides. A table that names fewer than half of
    # the part's pins (at any number) is not this part's pin table (a register map, a function-select or a partial list):
    # what it says at a number is no evidence against the part, so it is passed over, never a conflict. A part with swapped
    # pins still has its names in its table, and conflicts. The next text is read only then: a table of another package
    # stops here (the plain text, without the table's package line, must not make it this part's).
    units, reasons, split = [], [], False
    for text in texts:
        tables = find_tables(text) if text else []
        if not tables:
            continue
        found, why = _units(tables, package, pads)
        if not found:
            reasons.append(why)
            break
        # a complete table of this part's own package is its pin table, however few of its names the symbol uses
        units = [u for u in found if _known(u, pins) * 2 >= len(pins) or (u.get("pkg_match") and _complete(_numbers(u)))]
        if units:
            split = any(0 < _known(u, pins) for u in found if u not in units)
            break
        best = max(_known(u, pins) for u in found)
        reasons.append(f"no pin table of the datasheet lists this part's pins (the best names {best} of its {len(pins)}): "
                       f"a pin diagram, a function table or a partial list is not compared")
    if not units:
        return {"verify": "unchecked", "notes": [], "evidence": "",
                "issues": [reasons[0] if reasons else
                           "no pin table found in the datasheet text (a pin diagram or prose alone is not compared)"]}
    results = [_evaluate(u, pins, pads) for u in units]
    clean = [r for r in results if not r["conflict"] and not r["absent"]]
    bad = [r for r in results if r["conflict"]]
    if len(clean) == len(results):
        names = sorted({u["label"] or "" for u in results if u["label"]})
        return {"verify": "pass", "issues": [], "notes": sorted({n for r in results for n in r["notes"]}),
                "evidence": f"pin table of the datasheet ({len(pins)} pins matched by number and name"
                            + (f", {', '.join(names)}" if names else "") + ")"}
    if len(bad) == len(results):
        first = min(bad, key=lambda r: len(r["conflict"]))
        return {"verify": "mismatch", "issues": first["conflict"][:12], "notes": first["notes"], "evidence": ""}
    if clean and len(units) > 1:
        labels = sorted({lb for u in units for lb in u["scope"]}) or [f"{len(units)} tables"]
        return {"verify": "unchecked", "notes": [], "evidence": "",
                "issues": ["the datasheet's numbering columns (" + ", ".join(labels)
                           + f") give these pins different numbers and none can be chosen as this part's (package {package or 'not given'})"]}
    absent = [a for r in results for a in r["absent"]]
    labels = sorted({lb for u in units for lb in u["scope"]})
    if len(units) > 1 and labels:
        return {"verify": "unchecked", "notes": [], "evidence": "",
                "issues": [f"the datasheet's table has numbering columns for {', '.join(labels)} that its text does not tie to "
                           f"one package, and no column lists every pin of this part (package {package or 'not given'}): "
                           + "; ".join(dict.fromkeys(absent))[:240]]}
    where = ("the datasheet's pin list is split over several tables, which are not combined; not found as a row of the table "
             "that names most of its pins: ") if split else "not found as a row of the datasheet's pin table: "
    return {"verify": "unchecked", "notes": [], "evidence": "",
            "issues": [where + "; ".join(dict.fromkeys(absent))[:300]]}
