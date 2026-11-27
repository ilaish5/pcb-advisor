"""Gates that keep the oracle honest (ACCEPTANCE.md A2, A3, A9).

    .venv/Scripts/python.exe -I tests/acceptance/gate.py imports            # A2: no product import anywhere under tests/acceptance
    .venv/Scripts/python.exe -I tests/acceptance/gate.py frozen [--base acceptance-v1]   # A3: fix branch did not touch the oracle
    .venv/Scripts/python.exe -I tests/acceptance/gate.py special            # A9: no fixture-only literal in product code
    .venv/Scripts/python.exe -I tests/acceptance/gate.py all

Exit 0 = pass. Any finding prints and exits 1.
"""
from __future__ import annotations

import argparse
import ast
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
FROZEN_PATHS = ["tests/acceptance", "docs/e2e-2026-11-27/ACCEPTANCE.md", "shared/reference"]
PRODUCT_DIRS = ["scripts", "ui", "config"]
PRODUCT_FILES = ["pcb.py"]
# Literals that exist only because of the 27/11 fixture or the oracle. Product code containing one is special-casing (A9).
SPECIAL_LITERALS = [r"Final-E2E-4L", r"final-e2e-4l", r"acceptance-fixtures", r"tests[/\\]acceptance",
                    r"ACCEPTANCE_SEED", r"acceptance-v1", r"acceptance-runs"]
ACCEPTANCE_LOCAL = {"lib", "run", "gate", "thresholds", "oracle", "metrics", "canaries", "live"}


def product_module_names() -> set[str]:
    names = {"scripts", "pcb", "ui"}
    for d in ("scripts",):
        for p in (REPO / d).rglob("*.py"):
            names.add(p.stem)
        for p in (REPO / d).rglob("*"):
            if p.is_dir() and not p.name.startswith((".", "__")):
                names.add(p.name)
    return names - set(sys.stdlib_module_names) - ACCEPTANCE_LOCAL


def gate_imports() -> list[str]:
    bad = []
    forbidden = product_module_names()
    for py in HERE.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                mods = [node.module]
            for m in mods:
                top = m.split(".")[0]
                if top in forbidden:
                    bad.append(f"{py.relative_to(REPO)}:{node.lineno} imports {m!r} (product code; A2)")
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") in ("insert", "append") \
                    and any(isinstance(a, ast.Constant) and isinstance(a.value, str) and "scripts" in a.value for a in node.args):
                bad.append(f"{py.relative_to(REPO)}:{node.lineno} puts a scripts/ path on sys.path (A2)")
        if re.search(r"""['"][^'"]*scripts[/\\]""", py.read_text(encoding="utf-8")) and py.name != "gate.py":
            for i, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"""['"][^'"]*scripts[/\\][^'"]*\.py['"]""", line) and "import" in line:
                    bad.append(f"{py.relative_to(REPO)}:{i} loads a product .py by path (A2)")
    return bad


def gate_frozen(base: str) -> list[str]:
    r = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--verify", base], capture_output=True, text=True)
    if r.returncode != 0:
        return [f"base {base!r} does not exist (the owner has not tagged the oracle yet)"]
    r = subprocess.run(["git", "-C", str(REPO), "diff", "--name-only", f"{base}...HEAD", "--", *FROZEN_PATHS],
                       capture_output=True, text=True, check=True)
    return [f"frozen path changed since {base}: {line}" for line in r.stdout.splitlines() if line.strip()]


def gate_special() -> list[str]:
    bad = []
    pat = re.compile("|".join(SPECIAL_LITERALS))
    files = [REPO / f for f in PRODUCT_FILES]
    for d in PRODUCT_DIRS:
        files += [p for p in (REPO / d).rglob("*") if p.is_file() and p.suffix in (".py", ".js", ".pas", ".json", ".html", ".css", ".toml", ".yaml", ".yml")]
    for p in files:
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if pat.search(line):
                bad.append(f"{p.relative_to(REPO)}:{i}: {line.strip()[:100]}")
    return bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("which", choices=["imports", "frozen", "special", "all"])
    ap.add_argument("--base", default="acceptance-v1")
    a = ap.parse_args(argv)
    found = []
    if a.which in ("imports", "all"):
        found += gate_imports()
    if a.which in ("frozen", "all"):
        found += gate_frozen(a.base)
    if a.which in ("special", "all"):
        found += gate_special()
    for f in found:
        print(f)
    print("GATE " + ("PASS" if not found else f"FAIL ({len(found)})"))
    return 0 if not found else 1


if __name__ == "__main__":
    sys.exit(main())
