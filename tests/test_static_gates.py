"""Static gates: JS syntax, Python lint (ruff), UI file references, AdvisorBridge.pas structure."""
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "ui"


# ---- JS syntax ------------------------------------------------------------------------------------------------
def _js_errors(src: str):
    """(line, col) of every syntax error found by the tree-sitter JavaScript grammar (modern ES, offline)."""
    tsj = pytest.importorskip("tree_sitter_javascript")
    from tree_sitter import Language, Parser
    root = Parser(Language(tsj.language())).parse(src.encode("utf-8")).root_node
    out = []

    def walk(n):
        if n.is_missing or n.type == "ERROR":
            out.append((n.start_point[0] + 1, n.start_point[1] + 1))
        elif n.has_error:
            for c in n.children:
                walk(c)
    if root.has_error:
        walk(root)
    return out


def _shipped_js():
    skip = {"projects", ".venv", "node_modules", ".claude", "runtime"}
    return sorted(p for p in ROOT.rglob("*.js") if not skip & set(p.relative_to(ROOT).parts[:-1]))


def test_js_files_found():
    assert any(p.name == "outputs.js" for p in _shipped_js())


def test_js_syntax_gate_catches_unescaped_apostrophe():
    # the bug that broke the Outputs/DFM tabs
    assert _js_errors("const note = 'No outputs yet. Pick what you'd like to build.';\n")


def test_js_syntax_gate_accepts_modern_syntax():
    assert not _js_errors("const a = x?.y ?? 1; class C { #p = 1; async m() { return `${a}`; } }\nconst {...r} = o;")


@pytest.mark.parametrize("path", _shipped_js(), ids=lambda p: str(p.relative_to(ROOT)))
def test_js_syntax(path):
    errs = _js_errors(path.read_text(encoding="utf-8"))
    assert not errs, f"{path.relative_to(ROOT)}: syntax error at line:col {errs[:3]}"


# ---- Python lint ----------------------------------------------------------------------------------------------
def test_ruff_clean():
    pytest.importorskip("ruff")
    r = subprocess.run([sys.executable, "-m", "ruff", "check", "--output-format", "concise", str(ROOT)],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr


# ---- HTML references ------------------------------------------------------------------------------------------
def _local(ref: str):
    ref = ref.split("?")[0].split("#")[0]
    if not ref or re.match(r"^(https?:|//|data:|blob:|mailto:|javascript:)", ref):
        return None
    return ref


def test_ui_references_exist():
    missing = []
    for html in UI.rglob("*.html"):
        text = html.read_text(encoding="utf-8")
        for ref in re.findall(r'<script[^>]+src=["\']([^"\']+)', text) + re.findall(r'<link[^>]+href=["\']([^"\']+)', text):
            ref = _local(ref)
            if ref is None:
                continue
            target = ROOT / ref.lstrip("/") if ref.startswith("/") else html.parent / ref
            if not target.exists():
                missing.append(f"{html.relative_to(ROOT)}: {ref}")
    for js in _shipped_js():
        if UI in js.parents:
            for ref in re.findall(r'^\s*import\s[^;\n]*?from\s+["\'](\.{1,2}/[^"\']+)', js.read_text(encoding="utf-8"), re.M):
                if not (js.parent / ref).exists():
                    missing.append(f"{js.relative_to(ROOT)}: {ref}")
    assert not missing, "missing files: " + "; ".join(missing)


# ---- AdvisorBridge.pas ----------------------------------------------------------------------------------------
_PAS_TOKEN = re.compile(r"'(?:[^'\n]|'')*'|(?P<badq>')|//[^\n]*|\{[^}]*\}|\(\*.*?\*\)|\b(?P<kw>begin|case|try|end)\b", re.I | re.S)


def _pas_problems(src: str):
    """Cheap structural check: a quote that never closes on its line, and unbalanced begin/case/try ... end."""
    problems = []
    depth = 0
    for m in _PAS_TOKEN.finditer(src):
        line = src.count("\n", 0, m.start()) + 1
        if m.group("badq"):
            problems.append(f"line {line}: unbalanced quote")
        elif m.group("kw"):
            depth += -1 if m.group("kw").lower() == "end" else 1
            if depth < 0:
                problems.append(f"line {line}: end without begin")
                depth = 0
    if depth:
        problems.append(f"{depth} begin/case/try without end")
    return problems


def test_pas_structure_gate_detects_problems():
    assert _pas_problems("procedure P;\nbegin\n  x := 'abc;\nend;\n")
    assert _pas_problems("procedure P;\nbegin\n  x := 1;\n")
    assert not _pas_problems("procedure P;\nbegin\n  x := 'it''s'; // end\nend;\n")


def test_advisor_bridge_pas_structure():
    pas = next(ROOT.rglob("AdvisorBridge.pas"), None)
    assert pas is not None
    assert not _pas_problems(pas.read_text(encoding="utf-8", errors="replace"))
