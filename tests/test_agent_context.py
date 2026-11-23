"""What the agent is told matches what the server does (docs/AGENT-CONTEXT-MAP-2026-11-23.md).

- every action kind the server accepts is documented in runtime/AGENTS.md (REPLY FORMAT AND ACTIONS), and every kind AGENTS.md or a
  skill documents exists on the server. Kinds are read statically (AST): running an action to see whether it is known would drive Altium.
- every script AGENTS.md or a skill tells the agent to run exists and is covered by the engine's allow-list (else it is denied).
- CURRENT STATE carries where the project stands (stages) and no copy of the diagram.
"""
import ast
import fnmatch
import json
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

AGENTS = REPO / "runtime" / "AGENTS.md"
SKILLS = REPO / "runtime" / "skills"
FILE_EXT = re.compile(r"\.(?:py|md|json|jsonl|pdf|txt|RUL|zip|csv|svg|jpg|SchDoc|PcbDoc|PrjPcb|OutJob)$", re.I)


def _str_consts(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return []


def _is_type_get(node):
    """action.get("type") / a.get("type")"""
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get"
            and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == "type")


def server_kinds():
    """Kinds serve._apply_actions branches on (kind == / in, ALTIUM_ACTIONS resolved), plus the kinds the extension modules claim
    (action.get("type") == / != "...")."""
    tree = ast.parse((REPO / "scripts" / "serve.py").read_text(encoding="utf-8"))
    consts = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            consts[node.targets[0].id] = _str_consts(node.value)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_apply_actions")
    kinds = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) and node.left.id == "kind":
            for op, comp in zip(node.ops, node.comparators):
                if isinstance(op, (ast.Eq, ast.NotEq, ast.In)):
                    kinds.update(_str_consts(comp))
                    if isinstance(comp, ast.Name):
                        kinds.update(consts.get(comp.id, []))
    import ext
    for mod in ext.MODULES:
        src = (REPO / "scripts" / f"{mod}.py").read_text(encoding="utf-8")
        found = set()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Compare) and _is_type_get(node.left):
                for comp in node.comparators:
                    found.update(_str_consts(comp))
        # a module that registers an action handler must name its kind the way this reads it, or the parity check is blind to it
        assert found or '@ext.register("action")' not in src, f"{mod}: action handler with no action.get(\"type\") kind"
        kinds |= found
    return {k for k in kinds if "." in k}


def _actions_section():
    text = AGENTS.read_text(encoding="utf-8")
    start = text.index("# REPLY FORMAT AND ACTIONS")
    end = text.index("\n# ", start + 1)
    return text[start:end]


def documented_kinds(text):
    """`"type": "x"` anywhere, plus backticked dotted names (not files, not paths) in the given text."""
    kinds = set(re.findall(r'"type":\s*"([a-z_]+(?:\.[a-z_]+)+)"', text))
    for tok in re.findall(r"`([a-z_]+(?:\.[a-z_]+)+)`", text):
        if not FILE_EXT.search(tok):
            kinds.add(tok)
    return kinds


def test_server_kinds_are_found():
    kinds = server_kinds()
    # the extractor itself works: a built-in, an Altium action from the tuple, and an extension's kind
    assert {"bom.propose", "altium.run_outjob", "altium.route_pcb", "idea.constrain", "chat.ask"} <= kinds


def test_every_server_action_is_documented_for_the_agent():
    missing = sorted(server_kinds() - documented_kinds(_actions_section()))
    assert not missing, f"action kinds the server accepts but AGENTS.md (REPLY FORMAT AND ACTIONS) never documents: {missing}"


def test_every_documented_action_exists_on_the_server():
    server = server_kinds()
    unknown = {}
    for name, text in [("AGENTS.md", _actions_section())] + [
            (str(p.relative_to(REPO)), p.read_text(encoding="utf-8")) for p in sorted(SKILLS.rglob("*.md"))]:
        # skills: only the explicit {"type": ...} form (their backticks name state fields and files too)
        kinds = documented_kinds(text) if name == "AGENTS.md" else set(re.findall(r'"type":\s*"([a-z_]+(?:\.[a-z_]+)+)"', text))
        bad = sorted(kinds - server)
        if bad:
            unknown[name] = bad
    assert not unknown, f"documented action kinds the server does not accept: {unknown}"


def test_documented_idea_constrain_examples_are_valid():
    """The idea.constrain examples the agent copies (AGENTS.md, the placement skill) pass the server's own validation."""
    import constraints
    texts = [AGENTS.read_text(encoding="utf-8"), (SKILLS / "placement-and-routing-plan" / "SKILL.md").read_text(encoding="utf-8")]
    found = 0
    for text in texts:
        for raw in re.findall(r'`(\{"type": "idea\.constrain".*?\}\})`', text):
            a = json.loads(raw)
            assert a["op"] in ("add", "update", "remove")
            constraints.validate_item(a["item"])
            found += 1
    assert found == 2


def test_idea_constrain_fields_are_documented():
    import constraints
    sec = _actions_section()
    line = next(l for l in sec.splitlines() if '"idea.constrain"' in l)
    for word in ("op", "item", *constraints.KINDS, *constraints.ATTRS):
        assert word in line, word


def _allowed_patterns():
    cfg = json.loads((REPO / "config" / "defaults.json").read_text(encoding="utf-8"))
    allowed = cfg["agent"]["providers"]["claude_code"]["tools"]["allowed"]
    out = []
    for rule in allowed:
        m = re.fullmatch(r"Bash\(\{python\} \{repo\}/(scripts/\S+) \*\)", rule)
        if m:
            out.append(m.group(1))
    return out


def named_scripts():
    """{scripts/x.py: [where]} for every `python <repo>/scripts/....py` in AGENTS.md and the skills."""
    found = {}
    for p in [AGENTS, *sorted(SKILLS.rglob("*.md"))]:
        for rel in re.findall(r"python3? <repo>/(scripts/[\w/.-]+\.py)", p.read_text(encoding="utf-8")):
            found.setdefault(rel, []).append(str(p.relative_to(REPO)))
    return found


def test_named_scripts_exist():
    found = named_scripts()
    assert len(found) > 15
    gone = {rel: where for rel, where in found.items() if not (REPO / rel).is_file()}
    assert not gone, f"scripts the agent is told to run that do not exist: {gone}"


def test_named_scripts_are_allowed_for_the_engine():
    pats = _allowed_patterns()
    denied = {rel: where for rel, where in named_scripts().items() if not any(fnmatch.fnmatch(rel, p) for p in pats)}
    assert not denied, f"scripts the agent is told to run that the claude_code allow-list denies: {denied}"


# ---------------------------------------------------------------- CURRENT STATE


def test_state_says_where_the_project_stands_once(lte):
    import agent
    import model
    s = json.loads(agent._summary(model.build(project=lte)))
    assert s["stages"] and {"id", "state"} <= set(s["stages"][0])
    import stages
    assert [r["id"] for r in s["stages"]] == list(stages.ORDER)
    assert "diagram" in s and "diagram" not in s["idea"]
    for a in s["idea"].get("agreed") or []:
        assert not ({"ts", "prev_text"} & set(a))


def test_stage_reason_is_clipped_and_gate_marked():
    import agent
    rows = agent._stages({"stages": [{"id": "outputs", "state": "blocked", "reason": "x" * 1000, "primary": True,
                                      "gate": {"blocked": True, "why": "x"}, "next": {"label": "Fix the schematic", "act": "go:sch"}}]})
    assert len(rows[0]["why"]) == agent.STAGE_REASON_CUT and "…" in rows[0]["why"]
    assert rows[0]["blocked"] and rows[0]["current"] and rows[0]["next"] == "Fix the schematic"


def test_waiting_pins_and_reference_pointer():
    import agent
    m = {"project": "", "stages": [], "pin_decisions": {"remaining": [{"line": "U1", "refs": ["U1"], "mpn": "X", "issues": ""}]},
         "sources": [{"name": "course/a.en.md", "origin": "Reference library"}, {"name": "U1.pdf", "origin": "lcsc.com"}]}
    s = json.loads(agent._summary(m))
    assert s["pins_waiting"] == [{"line": "U1", "refs": ["U1"], "status": "unverified"}]
    assert s["sources"] == ["U1.pdf"] and "1 course" in s["reference_library"]


def test_waiting_pins_are_what_the_manufacturing_gate_holds(lte, monkeypatch):
    """pins_waiting is store.pins_to_resolve (unverified and mismatch), the list store.manufacturing_warning refuses on."""
    import agent
    import store
    rows = [{"line": "U1", "refs": ["U1"], "status": "mismatch", "mpn": "X"}, {"line": "U2", "refs": ["U2"], "status": "unverified"}]
    monkeypatch.setattr(store, "pins_to_resolve", lambda project, **kw: rows)
    assert [r["status"] for r in agent._pins_waiting({"project": lte})] == ["mismatch", "unverified"]


def test_workspace_text_agrees_with_the_rules(lte):
    """WORKSPACE once said 'run sources.py verify BEFORE you quote' and 'NEVER state stock without running' the check: both against
    AGENTS.md (CITING; rule 4)."""
    import workspace
    words = json.dumps(workspace.describe(lte))
    assert "BEFORE you quote" not in words
    assert "NEVER state stock or price without running" not in words
    rules = AGENTS.read_text(encoding="utf-8")
    assert "Do not run `sources.py verify` before answering" in rules


# ---------------------------------------------------------------- prompt structure (Prompting 101: tagged, stable first, reminder last)


def _prompt(lte, monkeypatch, tmp_path, **kw):
    import agent
    import gateway
    import model
    monkeypatch.setenv("PCB_ADVISOR_ENGINE_HOME", str(tmp_path / "engine"))
    seen = {}

    def route(req, name=None):
        seen["req"] = req
        return gateway.Result(text="fine", provider="claude_code")
    monkeypatch.setattr(gateway, "route", route)
    m = model.build(project=lte)
    agent.respond(m, kw.pop("message", "hello"), kw.pop("history", m["chat"]), backend="claude_code", **kw)
    return seen["req"].prompt


def test_prompt_sections_are_tagged_stable_first_and_end_with_the_reminder(lte, monkeypatch, tmp_path):
    p = _prompt(lte, monkeypatch, tmp_path)
    # the rules name the tags too: a section is its tag on a line of its own
    order = [p.index(f"\n<{t}>\n") for t in ("workspace", "current_state", "conversation", "student_message", "reminder")]
    assert order == sorted(order)
    assert p.rstrip().endswith("</reminder>")
    assert "Reply language: English" in p.split("\n<reminder>\n")[1]
    assert "\n<server_message>\n" not in p


def test_a_follow_up_is_the_servers_message_not_the_students(lte, monkeypatch, tmp_path):
    p = _prompt(lte, monkeypatch, tmp_path, message="Results of your actions: none", typed="draw it", from_server=True)
    assert "<server_message>\nResults of your actions: none\n</server_message>" in p
    assert "\n<student_message>\n" not in p


def test_bom_rows_carry_role_jlc_type_and_price():
    import agent
    m = {"project": "", "stages": [], "bom": [{"key": "U1", "refs": ["U1"], "value": "MCU", "mpn": "X", "role": "main MCU",
                                                "supply": {"LCSC": {"stock": 5, "unit_price": 2.5, "library_type": "Extended",
                                                                    "checked_at": "2026-11-23T10:00:00"}}}]}
    row = json.loads(agent._summary(m))["bom"][0]
    assert row["role"] == "main MCU" and row["jlc_type"] == "Extended" and row["unit_usd"] == 2.5


def test_a_server_round_sends_the_last_exchange_not_the_whole_conversation(lte, monkeypatch, tmp_path):
    """P3: a follow-up or retry answers the server's report on the last exchange: the student's last message (the quote) and the
    agent replies since; older turns stay out. A student turn keeps the full window."""
    chat = [{"role": "user", "text": f"old question {i}"} if i % 2 == 0 else {"role": "agent", "text": f"old answer {i}"}
            for i in range(6)]
    chat += [{"role": "user", "text": "draw it yourself please"}, {"role": "agent", "text": "Drawing sheet 01."},
             {"role": "agent", "text": "Retry: building the library first."}]
    p = _prompt(lte, monkeypatch, tmp_path, message="Results of your actions: none", typed="draw it yourself please",
                from_server=True, history=chat)
    convo = p.split("\n<conversation>\n")[1].split("\n</conversation>")[0]
    assert convo.splitlines() == ["user: draw it yourself please", "agent: Drawing sheet 01.", "agent: Retry: building the library first."]
    p = _prompt(lte, monkeypatch, tmp_path, message="and now?", history=chat)
    assert "old question 2" in p.split("\n<conversation>\n")[1]
