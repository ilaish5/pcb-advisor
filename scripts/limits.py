"""What the tool cannot do (F-LIM): one frozen list of 15 limits (REPORT.md, "Tool limits"), each either WORKING (and checkable) or REFUSED
at the control on its page with an open ledger item once the student meets it. A limit that exists only in chat text is a defect: when
the agent or a refusal says one in chat, `track_text` opens the item and the chat shows its id.

  status "works"    the tool does it; `evidence` names the code path that proves it (the old claim that it cannot is false).
  status "refused"  the page shows `says` + `instead` at the control; `hit` / `track_text` open the ledger item (kind "limit").
"""
import re
import sys

import ext

LIMITS = [
    {"id": "L01", "title": "A document at a web address that cannot be fetched", "page": "sources", "control": "addurl", "status": "refused",
     "says": "The server could not download the document (the site may block automatic downloads, ask for a sign-in, or be unreachable).",
     "instead": "Save the PDF from your browser and add the file with Add file.",
     "match": r"could not fetch|fetch(?:ing)? (?:of )?(?:the )?(?:url|document|page)[^.\n]{0,40}(?:fail|cannot|can.t)"},
    {"id": "L02", "title": "Plane clearance and differential pair rules in Altium", "page": "rules", "control": "add-extra-rule", "status": "refused",
     "says": "These kinds go into the downloaded .RUL file, but 'Apply rules in Altium' cannot write them to the board yet.",
     "instead": "Import the downloaded .RUL in Altium (Design > Rules > Import Rules), or add the rule there by hand.",
     "match": r"plane ?clearance|differential pair rule|DiffPairsRouting|kind of rule cannot be written"},
    {"id": "L03", "title": "JLC's own DFM verdict", "page": "checks", "control": "dfm-report", "status": "refused",
     "says": "JLC shows its DFM verdict only after you sign in on their site, so the tool cannot fetch it.",
     "instead": "Upload the Gerbers on JLC's page, save the JLCDFM report as a PDF, and add that PDF here.",
     "match": r"JLC(?:PCB)?'?s? (?:DFM|gerber viewer)[^.\n]{0,60}(?:sign[- ]?in|log[- ]?in)|(?:sign[- ]?in|log[- ]?in)[^.\n]{0,60}JLC"},
    {"id": "L04", "title": "Changing the layer stack", "page": "pcb", "control": "board-layers", "status": "works",
     "says": "The tool sets a 4-layer stack-up itself when the board is made for 4 layers (it adds the two inner layers).",
     "instead": "Choose the layer count in the Idea; Place and Route add the inner layers.",
     "evidence": "scripts/altium/bridge.py ensure_stack",
     "match": r"(?:cannot|can.t|unable to|not able to)\s+(?:change|add|set|modify|edit)\s+(?:the )?(?:number of |count of )?(?:layers?|layer count|stack)"},
    {"id": "L05", "title": "Reading some chips' pin tables (for example STM32)", "page": "bom", "control": "pins-confirm", "status": "refused",
     "says": "The pin checker cannot read this datasheet's pin table, so these pins stay 'not checked' until you confirm them.",
     "instead": "Open the datasheet page it shows and confirm the pins yourself.",
     "match": r"cannot parse (?:the )?pin table|pin table[^.\n]{0,40}(?:cannot|can.t|not) (?:be )?(?:read|parsed)"},
    {"id": "L06", "title": "Fixing footprints (exposed pad paste, thermal vias, courtyard, origin, 3D offset)", "page": "bom", "control": "library-build",
     "status": "refused",
     "says": "The tool does not edit a footprint after the library is built, and a rebuild overwrites a hand fix.",
     "instead": "Fix it in the PcbLib in Altium after the last build, and keep that file.",
     "match": r"(?:cannot|can.t|does not|doesn.t) (?:edit|fix|change) (?:the )?(?:footprint|courtyard|paste|3D|origin)"},
    {"id": "L07", "title": "Placing a part next to a pin, or moving one part", "page": "pcb", "control": "place", "status": "refused",
     "says": "The placer places the whole board; it cannot put one part next to one pin or move a single part.",
     "instead": "Move the part in Altium, then press Check board.",
     "match": r"(?:cannot|can.t|no way to) (?:move|place) (?:a )?(?:single|one|individual) (?:part|component)|near[- ]a[- ]pin placement"},
    {"id": "L08", "title": "Tenting vias, editing pads or mask, moving silk, deleting rules", "page": "pcb", "control": "route", "status": "refused",
     "says": "The tool cannot tent vias, edit a pad or its mask opening, move silkscreen, or delete a rule in Altium.",
     "instead": "Do it in Altium by hand, then press Check board.",
     "match": r"(?:cannot|can.t) (?:tent|edit (?:a )?pads?|move (?:the )?silk|delete (?:a )?rules?)"},
    {"id": "L09", "title": "90 ohm / differential pair routing", "page": "pcb", "control": "route", "status": "refused",
     "says": "The router does not route differential pairs or controlled impedance.",
     "instead": "Route the pair by hand in Altium with an impedance profile, then press Check board.",
     "match": r"90 ?ohm|differential[- ]pair routing|controlled impedance"},
    {"id": "L10", "title": "Ports and nets that cross sheets", "page": "sch", "control": "draw", "status": "refused",
     "says": "The drawer does not draw ports or wires between sheets; a circuit that needs more than one sheet is refused with a plan.",
     "instead": "Draw that part by hand in Altium, or split the design as the plan says.",
     "match": r"cross[- ]sheet|(?:cannot|can.t) draw (?:a )?ports?|needs about \d+ sheets"},
    {"id": "L11", "title": "Compile and ERC in Altium", "page": "sch", "control": "draw", "status": "refused",
     "says": "There is no Compile or ERC step: the tool cannot prove the drawn connectivity in Altium.",
     "instead": "In Altium run Project > Compile and read the Messages panel, then fix or accept what it lists.",
     "match": r"no (?:altium )?(?:compile|ERC)|(?:cannot|can.t) (?:run|do) (?:an? )?(?:compile|ERC)"},
    {"id": "L12", "title": "README and order-note files", "page": "outputs", "control": "outputs", "status": "refused",
     "says": "The outputs do not include a README or an order note file.",
     "instead": "Write the note yourself; the order page copy is in the manifest.",
     "match": r"no (?:README|order[- ]note)|(?:cannot|can.t) (?:write|make) (?:a )?(?:README|order note)"},
    {"id": "L13", "title": "Keep-outs in the PcbLib", "page": "bom", "control": "library-build", "status": "refused",
     "says": "Keep-out areas are not stored in the PcbLib the tool builds, so they do not follow the footprint.",
     "instead": "Draw the keep-out on the board in Altium.",
     "match": r"keep-?outs? (?:are )?not (?:kept|stored|in the PcbLib)"},
    {"id": "L14", "title": "Updating one part of a drawn schematic", "page": "sch", "control": "draw", "status": "refused",
     "says": "There is no incremental update: changing one part means redrawing the sheet, which replaces what is drawn.",
     "instead": "Edit the one part in Altium by hand, or accept the redraw.",
     "match": r"no incremental|replace(?:s)? (?:the )?(?:main|sheet)[^.\n]{0,30}wipe"},
    {"id": "L15", "title": "JLC's assembly (PCBA) preview", "page": "outputs", "control": "jlc-order", "status": "refused",
     "says": "JLC's PCBA preview needs the board in a JLC cart, which only you can create on their site.",
     "instead": "Upload the Gerbers and the BOM/CPL on JLC's site and continue there.",
     "match": r"PCBA preview|JLC cart|in (?:a|the) (?:JLC )?cart"},
]
BY_ID = {x["id"]: x for x in LIMITS}
_NEG = re.compile(r"\b(?:cannot|can.t|can not|no|not|n.t|unable|without|does not|doesn.t|never|needs?|refused|could not)\b", re.I)
for _l in LIMITS:
    _l["rx"] = re.compile(_l["match"], re.I)


def public():
    return [{k: v for k, v in l.items() if k not in ("rx", "match")} for l in LIMITS]


def for_page(page):
    return [x for x in public() if x["page"] == page]


def key(limit_id):
    return f"limit:{limit_id}"


def hit(project, limit_id, context=""):
    """The student met this limit (a refused control, a failed fetch, a refused action): its ledger item is open. A limit that WORKS
    opens nothing. Returns the item or None."""
    import ledger
    lim = BY_ID[limit_id]
    if lim["status"] != "refused":
        return None
    detail = f"{lim['says']} {lim['instead']}" + (f" ({context})" if context else "")
    return ledger.add(project, key(limit_id), "limit", lim["title"], detail, page=lim["page"], source="tool limit",
                      severity="info", extra={"limit": limit_id})


def false_claims(text):
    """Limit ids whose WORKING status the text denies (the W26 case: 'cannot change layers'): the caller shows a correction."""
    return [l["id"] for l in LIMITS if l["status"] == "works" and l["rx"].search(str(text or ""))]


def track_text(project, text):
    """Limits that a text (an agent reply, a refusal) states: each one gets its item. Returns [item]. Never raises."""
    out = []
    try:
        sents = [x for x in re.split(r"(?<=[.!?])\s+|\n+", str(text or "")) if _NEG.search(x)]
        for l in LIMITS:
            if l["status"] == "refused" and any(l["rx"].search(x) for x in sents):
                it = hit(project, l["id"], "")
                if it:
                    out.append(it)
    except Exception as exc:       # noqa: BLE001
        print(f"(limits: not tracked: {type(exc).__name__}: {exc})", file=sys.stderr)
    return out


def correction(ids, lang="en"):
    """The line that corrects a false 'cannot' claim."""
    lines = [f"Correction: {BY_ID[i]['says']}" for i in ids if i in BY_ID]
    return " ".join(lines)


@ext.register("get")
def _get(handler, path, q):
    if path == "/api/limits":
        import ledger
        doc = ledger.view(handler.project())
        tracked = {i.get("limit"): i for i in doc["items"] if i.get("limit")}
        out = []
        for l in public():
            it = tracked.get(l["id"])
            out.append({**l, "item": ({"id": it["id"], "state": it["state"]} if it else None)})
        return {"limits": out}
    return None


@ext.register("post")
def _post(handler, path, body):
    if path != "/api/limits/hit":
        return None
    lid = str(body.get("id") or "")
    if lid not in BY_ID:
        raise ext.HTTPError(404, f"no limit {lid!r}")
    it = hit(handler.project(), lid, str(body.get("context") or "")[:200])
    return {"limit": lid, "item": ({"id": it["id"], "state": it["state"]} if it else None)}
