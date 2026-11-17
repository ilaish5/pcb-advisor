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
_NAMEFIRST = re.compile(r"^[A-Za-z~/#_+][A-Za-z0-9_/#~+\-]*$")

POWER_TYPES = {"P", "PWR", "POWER", "S", "SUPPLY", "PI", "PO"}
GROUND_TYPES = {"G", "GND", "GROUND"}
IO_TYPES = {"I", "O", "I/O", "IO", "INPUT", "OUTPUT", "AI", "AO", "B", "I/OD", "OD", "IN", "OUT"}
TYPES = POWER_TYPES | GROUND_TYPES | IO_TYPES | {"NC", "PASSIVE", "—", "-", "–"}

_TYPE_ONLY = {"I", "O", "I/O", "IO", "AI", "AO", "B", "P", "G", "S", "PWR", "—", "-", "–"}     # codes no pin is named
_PKG = re.compile(r"\b(PDIP|CDIP|DIP|SOIC|TSSOP|VSSOP|SSOP|MSOP|SOP|SOT|SOD|SC|SO|TSOT|DSBGA|WLCSP|FBGA|NFBGA|BGA|UFQFPN|UQFN|VQFN|WQFN|"
                  r"QFN|WSON|USON|DFN|SON|LQFP|TQFP|LFCSP|QFP|TO|DPAK|SMA|SMB|SMC|PQFN|LGA)(?:[\s-]*(\d{1,3}(?:-\d{1,2})?)(?![\d.]|\s?[x×]|\s?mm)(?:[\s-]*mil)?)?"
                  r"(?![A-Za-z])", re.I)
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
    m = _RANGE.match(t)
    if m and 0 < int(m.group(2)) - int(m.group(1)) <= 64:
        return [str(n) for n in range(int(m.group(1)), int(m.group(2)) + 1)]
    return None


def _is_alnum_cell(cell):
    return any(not n.isdigit() for n in cell)


def _name_cell(toks):
    """The tokens of the name cell: up to the next column break in layout text; in plain text the first word and what a
    name continues with (`/HOLD or /RESET (IO3)`, `PA13 (SWDIO)`)."""
    if not toks:
        return []
    if any(gap for _, gap in toks[1:]):
        out = [toks[0][0]]
        for t, gap in toks[1:]:
            if gap:
                break
            out.append(t)
        return out
    out = [toks[0][0]]
    for t, _ in toks[1:]:
        prev = out[-1].lower()
        if t.lower() in ("or", "and", "&") or t.startswith(("/", "(")) or prev in ("or", "and", "&") or prev.endswith(("/", ",")):
            out.append(t)
        else:
            break
    return out


def _row(nums, rest):
    name = _name_cell(rest)
    if not name or not re.match(r"[~/#_]*[A-Za-z]", name[0]) or (name[0].islower() and len(name[0]) > 2 and name[0].isalpha()):
        return None
    after = [t for t, _ in rest[len(name):len(name) + 1]]
    typ = after[0].upper() if after and after[0].upper() in TYPES else ""
    return {"nums": nums, "name": " ".join(name), "type": typ}


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
    if len(toks) < 2 or not _NAMEFIRST.match(toks[0][0]) or not re.search(r"[A-Za-z]", toks[0][0]):
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
    return {"nums": cells, "name": toks[0][0], "type": typ}


# ------------------------------------------------------------------ packages

def _canon(label):
    s = re.sub(r"\d+\s*-?\s*mil\b", "", label.lower())
    s = re.sub(r"[^a-z0-9]", "", s)
    s = re.sub(r"^[pc]dip", "dip", s)
    s = re.sub(r"^(soic|sop)", "so", s)
    s = re.sub(r"^[uvw]qfn", "qfn", s)
    s = re.sub(r"^(wson|uson|son)", "dfn", s)
    s = re.sub(r"^sot23(\d)$", r"sot2\1", s)            # SOT-23-5 is SOT25
    return s


def package_labels(text):
    """Package names written in a piece of text: ['SOIC-8', 'DIP-8', 'SOT25'] (a size in mils is not a pin count)."""
    out = []
    for m in _PKG.finditer(text or ""):
        digits = m.group(2) or ""
        if digits and re.search(r"mil", m.group(0), re.I) and int(digits.split("-")[0]) >= 100:
            digits = ""
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
                tables.append({"heading": " ".join(x.strip() for x in lines[max(0, h - 2):j] if x.strip())[:200],
                               "labels": package_labels(" ".join(lines[max(0, h - 2):j])), "rows": rows})
            break
    big = [t for t in tables if len(t["rows"]) >= 3]
    return big or tables           # a 2-row 'table' beside real ones is a figure's text


def _columns(table):
    """The table's numbering columns: [{"index", "label"}]. A row has the table's usual number of cells (K) or is not used."""
    def bare_size(nums):                 # a dash at the end may be the pin type (`GND 7 —`) rather than a column
        n = len(nums)
        while n and not nums[n - 1]:
            n -= 1
        return n
    sizes = [bare_size(r["nums"]) for r in table["rows"]]
    k = max(set(sizes), key=lambda n: (sizes.count(n), n))
    rows = []
    for r in table["rows"]:
        if len(r["nums"]) == k + 1 and not r["nums"][-1]:        # `GND 7 —`: the dash is the pin type, not a column
            r = {**r, "nums": r["nums"][:-1], "type": r["type"] or "—"}
        if len(r["nums"]) == k:
            rows.append(r)
    labels = table["labels"]
    cols = []
    for i in range(k):
        label = labels[i] if k > 1 and len(labels) == k else None
        cols.append({"index": i, "label": label, "scope": labels if label is None else [label], "k": k, "rows": rows,
                     "mapped": k == 1 or len(labels) == k, "heading": table["heading"]})
    return cols


def _numbers(col):
    out = []
    for r in col["rows"]:
        out += [n.upper() for n in r["nums"][col["index"]]]
    return out


def _name_forms(name):
    forms = {name} | pinnames.spellings(name)
    forms |= {pinnames.bare(f) for f in forms}
    return {s for s in (re.sub(r"[^A-Z0-9+]", "", f.upper()) for f in forms) if s}


def _cell_forms(cell):
    out = set()
    for word in re.split(r"[\s(),]+", cell):
        for part in [word] + word.split("/"):
            s = re.sub(r"[^A-Z0-9+]", "", pinnames.bare(part).upper())
            if s:
                out.add(s)
    squashed = re.sub(r"[^A-Z0-9+]", "", pinnames.bare(cell.replace(" ", "")).upper())
    if squashed:
        out.add(squashed)
    return out


def name_matches(name, cell):
    """The netlist's pin name is the table's name for the pin, in the spelling of the table or another (RESET/RST, /CS = CS#)."""
    return bool(_name_forms(name) & _cell_forms(cell))


def _complete(nums):
    """The table's numbers are 1..N without a gap: it is the whole pin list, so a count and a missing pin mean something."""
    plain = [n for n in nums if n.isdigit()]
    return bool(plain) and len(plain) == len(nums) and set(map(int, plain)) == set(range(1, max(map(int, plain)) + 1))


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


def _evaluate(col, pins, pads):
    """One numbering column against the part's pins: {"conflict": [...], "absent": [...], "notes": [...], "count": n|None, "pins": n}."""
    nums = _numbers(col)
    label = col["label"] or (col["scope"][0] if len(col["scope"]) == 1 else "")
    out = {"conflict": [], "absent": [], "notes": [], "count": None, "label": label, "nums": nums}
    complete = _complete(nums)
    for num, name in pins:
        hits = [r for r in col["rows"] if num.upper() in {n.upper() for n in r["nums"][col["index"]]}]
        if not hits:
            if re.fullmatch(r"N\.?/?C\.?|DNC|NC\d*|NO_?CONNECT|NO_?CONN", name.strip().upper()) and num.upper() not in nums:
                out["notes"].append(f"pin {num} {name}: the pin table lists no row for it (no-connect pins often are not listed)")
            elif complete:
                out["conflict"].append(f"pin {num} {name}: the datasheet's pin table has {len(set(nums))} pins, none is {num}")
            else:
                out["absent"].append(f"pin {num} {name}")
            continue
        good = [r for r in hits if name_matches(name, r["name"])]
        if not good:
            others = [str(r["nums"][col["index"]][0]) for r in col["rows"]
                      if name_matches(name, r["name"]) and r["nums"][col["index"]]]
            out["conflict"].append(f"pin {num} {name}: the datasheet calls pin {num} {' / '.join(dict.fromkeys(r['name'] for r in hits))}"
                                   + (f" and puts {name} on pin {', '.join(dict.fromkeys(others))}" if others else ""))
            continue
        note = _type_note(name, good[0]["type"])
        if note:
            out["notes"].append(f"pin {num}: {note}")
    if complete:
        out["count"] = len(set(nums))
        if pads is not None:
            have = {str(p).strip().upper() for p in pads}
            want = {n.upper() for n in nums}
            missing = sorted(want - have, key=lambda s: (len(s), s))
            extra = sorted(have - want, key=lambda s: (len(s), s))
            top = max(map(int, nums))
            extra = [e for e in extra if not (not e.isdigit() or e == str(top + 1) and len(extra) == 1)]     # an exposed / mechanical pad
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
    labels = package_labels(package) if package and not count else []
    if not labels:
        if count and len(units) > 1:
            units = [u for u in units if len(set(_numbers(u))) == count] or units
        return _by_pads(units, pads), ""
    mine = labels[0]
    rank = []
    for u in units:
        rels = [package_relation(lb, mine) for lb in u["scope"]] if u["scope"] else [None]
        rank.append("exact" if "exact" in rels else "family" if "family" in rels else "any" if rels == [None] else "")
    for want in ("exact", "family", "any"):
        found = [u for u, r in zip(units, rank) if r == want]
        if found:
            pins = package_pins(mine)
            if len(found) > 1 and pins:
                same = [u for u in found if len(set(_numbers(u))) == pins]
                found = same or found
            return _by_pads(found, pads), ""
    seen = sorted({lb for u in units for lb in u["scope"]})
    return [], f"the datasheet's pin tables are for {', '.join(seen)}, the package of this part is {mine}"


def check(texts, pins, package="", pads=None):
    """texts: the document's text, best layout first ([layout, plain]); pins: [(number, name)]. Answer:
    {"verify": "pass"|"mismatch"|"unchecked", "issues": [...], "notes": [...], "evidence": str}."""
    tables = []
    for text in texts:
        if text:
            tables = find_tables(text)
            if tables:
                break
    if not tables:
        return {"verify": "unchecked", "notes": [], "evidence": "",
                "issues": ["no pin table found in the datasheet text (a pin diagram or prose alone is not compared)"]}
    units, why = _units(tables, package, pads)
    if not units:
        return {"verify": "unchecked", "notes": [], "evidence": "", "issues": [why]}
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
    return {"verify": "unchecked", "notes": [], "evidence": "",
            "issues": ["not found as a row of the datasheet's pin table: " + "; ".join(dict.fromkeys(absent))[:300]]}
