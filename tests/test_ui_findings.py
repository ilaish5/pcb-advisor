"""Runtime-verification fixes: a new project never gets a silent numbered name, and the UI contracts of the compact step note,
the Outputs/DFM reasons, the Altium-only readiness rows, the board size row and the resumed chat."""
import re

from test_chat_turns import call, server  # noqa: F401
from ui_source import ui_js


def test_new_project_with_a_taken_name_is_refused_with_the_existing_name(server, empty):
    code, body = call(server, "POST", "/api/projects/new", empty, {"name": "Kiln"})
    assert code == 200 and body["created"] == "Kiln" and "note" not in body
    code, body = call(server, "POST", "/api/projects/new", empty, {"name": "Kiln"})
    assert code == 409 and body["exists"] == "Kiln"
    code, body = call(server, "POST", "/api/projects/new", empty, {"name": "Kiln", "allow_copy": True})
    assert code == 200 and body["created"] == "Kiln-2" and body["folder"] == "Kiln-2" and "Kiln-2" in body["note"]


def test_new_project_with_odd_characters_names_the_folder_used(server, empty):
    code, body = call(server, "POST", "/api/projects/new", empty, {"name": "a/b<c>"})
    assert code == 200 and body["created"] == "a-b-c" and "a-b-c" in body["note"]


def test_the_ui_contracts():
    js = ui_js()
    assert "function pvCompact" in js and "Show ${c.warnings.length}" in js          # compact step note, warnings behind a toggle
    assert "function outLimits" in js and "needs Altium. The Altium outputs" not in js
    assert "dfm-zip-why" in js                                                       # the disabled zip button says why in text
    assert "READY_ALTIUM_IDS" in js and "readyShow" in js
    assert re.search(r"placeholder=\"e\.g\. 30\"", js)
    assert "chatResume" in js and "Ran ${items.length} steps" in js
    assert "askChoice" in js and "allow_copy" in js


def _pv_regexes():
    """The step note's two regexes, read from previews.js so the Python mirror below runs the very same patterns."""
    js = ui_js()
    tail = re.search(r"const PV_TAIL_RE = /(.*)/;", js).group(1)
    drc = re.search(r"const PV_DRC_RE = /(.*)/g;", js).group(1)
    return re.compile(tail.replace("[^]", r"[\s\S]")), re.compile(drc)


def _compact(text, warnings=()):          # line for line the JS pvCompact
    tail_re, drc_re = _pv_regexes()
    t, warns = text, list(warnings)
    m = tail_re.search(t)
    if m:
        t = t[:m.start()]
        if not warns:
            warns = [x for x in m.group(2).split("; ") if x]
    alerts = [w for w in warns if w.startswith("placement error")]
    warns = [w for w in warns if not w.startswith("placement error")]

    def rep(m):
        items = m.group(2).split(", ")
        total = items.pop()
        bad = [i for i in items if not re.search(r" 0$", i)]
        return m.group(1) + (", ".join(bad) + ", " + total if bad else "clean" if m.group(3) else total)
    t = drc_re.sub(rep, t)
    segs, depth, start = [], 0, 0          # pvSegments: "; " outside brackets
    for i, ch in enumerate(t):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and t[i:i + 2] == "; ":
            segs.append(t[start:i])
            start = i + 2
    segs.append(t[start:])
    if len(segs) > 1:
        keep = lambda x, i: i == 0 or re.search(r"^own check|Altium DRC|^PARTIAL ROUTE", x)  # noqa: E731
        return ("; ".join(x for i, x in enumerate(segs) if keep(x, i)), "; ".join(x for i, x in enumerate(segs) if not keep(x, i)), warns, alerts)
    return t, "", warns, alerts


LIVE = ("Altium: 17 nets routed with 168 tracks and 37 vias, saved; own check: 1 open nets; Altium DRC: Clearance 0, Short-Circuit 0, "
        "Un-Routed Net 4, Width 0, Routing Topology Rule(Topology=Shortest) 0, Minimum Annular Ring 0, Minimum Annular Ring 4, "
        "Minimum Solder Mask Sliver 86, Silk To Solder Mask 0, Silk To Solder Mask 20, Height 0, total 114 (0 clearance before routing); "
        "track widths: +3V3 0.3 mm (rail default); PARTIAL ROUTE, left open: USB_DM (no way from R4-1 to J1-B7 (after moving +3V3, GND)) "
        "(3 warnings: open nets, not routed: USB_DM; route check: x; w3)")


def test_the_step_note_head_keeps_the_essentials_of_the_real_live_string():
    head, rest, warns, alerts = _compact(LIVE)
    assert "Un-Routed Net 4, Minimum Annular Ring 4, Minimum Solder Mask Sliver 86, Silk To Solder Mask 20, total 114" in head
    assert "PARTIAL ROUTE, left open: USB_DM" in head and "Clearance 0" not in head and "Topology" not in head
    assert "track widths" in rest and len(warns) == 3 and not alerts


def test_the_step_note_leaves_an_unchecked_drc_line_and_clean_runs_alone():
    unchecked = "Altium: routed; Altium DRC: unchecked (the report was not read in full; read so far: Clearance 0, Width 0, total 0)"
    assert "unchecked (the report was not read in full; read so far: Clearance 0, Width 0, total 0)" in _compact(unchecked)[0]
    assert _compact("Altium: ok; Altium DRC: Clearance 0, Width 0, total 0 (clean)")[0].endswith("Altium DRC: clean")
    assert _compact("x; y; Altium DRC: Clearance 0, Routing Topology Rule(Topology=Shortest) 0, total 0")[0].endswith("DRC: total 0")


def test_placement_errors_stay_in_the_head():
    _, _, warns, alerts = _compact("Altium: 3 parts placed (2 warnings: placement error: C1 too far; U1: a)")
    assert alerts == ["placement error: C1 too far"] and warns == ["U1: a"]
