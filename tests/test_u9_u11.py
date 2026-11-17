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
    assert "one per tool call" in msg and "cd x; python a.py | head" in msg and "text-only" in msg
    assert "Do not tell the student to allow" in msg
    both = serve.followup_message([], ["netlist.write:01 refused: x"], {}, den)
    assert "refused: netlist.write" in both and "one per tool call" in both


def test_empty_states_state_the_limits():
    ui = REPO / "ui" / "js"
    kit = (ui / "kit.js").read_text(encoding="utf-8")
    assert "function emptyState(title, text, actions, limits)" in kit and 'class="limits"' in kit
    pv = (ui / "views" / "previews.js").read_text(encoding="utf-8")
    assert "SCH_LIMITS)" in pv and pv.count("PCB_LIMITS)") >= 2
    assert "several sub-parts" in pv and "too big for one A4 sheet" in pv
    assert "two-layer boards, with no differential pairs" in pv
    out = (ui / "views" / "outputs.js").read_text(encoding="utf-8")
    assert "refused while a part has unverified pins" in out
    # each claim is enforced in code
    draw = (REPO / "scripts" / "altium" / "draw.py").read_text(encoding="utf-8")
    assert "multi-part symbols cannot be drawn" in draw and "does not fit on one A4 sheet" in draw
    assert "(TOP, BOT)" in (REPO / "scripts" / "altium" / "route.py").read_text(encoding="utf-8")
