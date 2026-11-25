"""U9: every command form the runtime documents is on the Claude Code allowlist, and a denied combined command comes back to the
agent as a "run them one by one" hint. U11: the empty states say what the system cannot do yet."""
import fnmatch
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _documented():
    found = set()
    for f in [REPO / "runtime" / "AGENTS.md", *(REPO / "runtime" / "skills").rglob("*.md")]:
        found |= set(re.findall(r"python3? <repo>/(scripts/[A-Za-z0-9_/.-]+\.py)", f.read_text(encoding="utf-8")))
    return found


def test_allowlist_covers_every_documented_command_form():
    cfg = json.loads((REPO / "config" / "defaults.json").read_text(encoding="utf-8"))
    rules = [r for r in cfg["agent"]["providers"]["claude_code"]["tools"]["allowed"] if r.startswith("Bash({python} {repo}/")]
    pats = [r[len("Bash({python} {repo}/"):-1] for r in rules]
    docs = _documented()
    assert "scripts/order_check.py" in docs and "scripts/skills/check_availability.py" in docs
    gaps = sorted(d for d in docs if not any(fnmatch.fnmatchcase(d + " proj --x", p) for p in pats))
    assert not gaps, gaps


def test_agents_md_says_one_command_per_call_and_no_giving_up_on_stock():
    t = (REPO / "runtime" / "AGENTS.md").read_text(encoding="utf-8")
    assert len(t.splitlines()) <= 150
    assert "One interpreter command per tool call" in t and "Several scripts = several calls" in t
    assert "never say you cannot check stock" in t


def test_compound_denial_becomes_a_retry_hint():
    import serve
    den = [{"tool": "PowerShell", "input": {"command": "cd x; python a.py | head"}, "reason": "", "compound": False}]
    assert serve.compound_denials(den) == ["cd x; python a.py | head"]
    assert serve.compound_denials([{"tool": "Bash", "input": {"command": "python a.py"}, "compound": False}]) == []
    assert serve.followup_worthy([], [], den) and not serve.followup_worthy([], [], [])
    msg = serve.followup_message([], [], {}, den)
    assert "one per tool call" in msg and "cd x; python a.py | head" in msg and "text-only" not in msg and "tool calls" in msg
    assert "Do not tell the student to allow" in msg
    both = serve.followup_message([], ["netlist.write:01 refused: x"], {}, den)
    assert "refused: netlist.write" in both and "one per tool call" in both


def test_quoted_operators_are_not_compound_and_a_recovered_turn_needs_no_followup():
    import serve
    cd = lambda c: [{"tool": "PowerShell", "input": {"command": c}, "compound": False}]
    for c in ('python C:/r/scripts/jlc.py search ">=10uF"', 'python C:/r/scripts/jlc.py search "10k|1%"',
              "python C:/r/scripts/jlc.py search 'a;b'", 'python C:/r/scripts/sources.py get p "http://x/a?b=1&c=2"'):
        assert serve.compound_denials(cd(c)) == [], c
    assert serve.compound_denials(cd('python C:/r/scripts/jlc.py search x | head')) != []
    den = cd("cd C:/r; python C:/r/scripts/skills/check_availability.py p")
    ran = [{"t": "Running check_availability.py p", "st": "ok"}]
    assert serve.compound_denials(den, ran) == []
    assert serve.compound_denials(den, [{**ran[0], "st": "bad"}]) != []
    assert not serve.followup_worthy([], [], den, ran) and serve.followup_worthy([], [], den, [])


def test_recovery_compares_each_part_with_its_arguments():
    import serve
    den = [{"tool": "PowerShell", "input": {"command": "python C:/r/scripts/jlc.py part A && python C:/r/scripts/jlc.py part B"}, "compound": True}]
    a = {"t": "Running jlc.py part A", "st": "ok"}
    b = {"t": "Running jlc.py part B", "st": "ok"}
    assert serve.compound_denials(den, [a]) != []
    assert serve.compound_denials(den, [a, {**b, "st": "bad"}]) != []
    assert serve.compound_denials(den, [a, b]) == []
    quoted = [{"tool": "Bash", "input": {"command": 'cd x; python C:/r/scripts/jlc.py search "10k 1%"'}, "compound": False}]
    assert serve.compound_denials(quoted, [{"t": "Running jlc.py search 10k 1%", "st": "ok"}]) == []


def test_followup_messages_allow_tools_only_when_a_split_is_asked():
    import serve
    den = [{"tool": "PowerShell", "input": {"command": "a.py; b.py"}, "compound": True}]
    m = serve.followup_message(["x"], [], {}, den)
    assert "text-only" not in m and "only the ```json actions block is ignored" in m
    plain = serve.followup_message([], ["altium.draw_schematic: no"], {}, [])
    assert "This is a text-only reply: no actions will run" in plain and "tool calls" not in plain
    src = (REPO / "scripts" / "serve.py").read_text(encoding="utf-8")
    import turn_truth
    assert turn_truth.msg("not_run", "en", what=turn_truth.msg("denied_not_rerun", "en")).startswith("(Not run: the denied command was not run again")
    assert 'turn_truth.msg("denied_not_rerun", lang)' in src and 'rec["split_retry"] = True' in src


def test_empty_states_state_the_limits():
    ui = REPO / "ui" / "js"
    kit = (ui / "kit.js").read_text(encoding="utf-8")
    assert "function emptyState(title, text, actions, limits)" in kit and 'class="limits"' in kit
    pv = (ui / "views" / "previews.js").read_text(encoding="utf-8")
    assert "SCH_LIMITS)" in pv and pv.count("PCB_LIMITS)") >= 2
    assert "split into several separate blocks" in pv and "too big for one A4 sheet" in pv and "sub-parts" not in pv and "between two sheets are not drawn" in pv
    assert "two-layer boards, with no differential pairs" in pv
    out = (ui / "views" / "outputs.js").read_text(encoding="utf-8")
    # since E1/E3/E12 the one gate is the server's (unrouted nets, open pins, a draft); unverified pins only warn
    assert "Altium outputs and the Gerber zip are refused until the blocker above is fixed" in out and "production files" not in out
    lim = out[out.index("function outLimits"):]
    lim = lim[:lim.index("\n}")]
    assert "if (outBlockWhy()) r.push('The Altium outputs" in lim       # said only while the gate is closed
    # each claim is enforced in code
    draw = (REPO / "scripts" / "altium" / "draw.py").read_text(encoding="utf-8")
    assert "multi-part symbols cannot be drawn" in draw and "does not fit on one A4 sheet" in draw
    assert "(TOP, BOT)" in (REPO / "scripts" / "altium" / "route.py").read_text(encoding="utf-8")
