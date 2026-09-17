"""Wipe a project's state back to empty. The corpus is untouched."""
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
proj = ROOT / "projects" / (sys.argv[1] if len(sys.argv) > 1 else "demo")
for f in ("decisions.jsonl", "threads.jsonl", "design-model.json", "constraints.md"):
    (proj / f).unlink(missing_ok=True)
shutil.rmtree(proj / "artifacts", ignore_errors=True)
proj.mkdir(parents=True, exist_ok=True)
(proj / "decisions.jsonl").touch()
(proj / "threads.jsonl").touch()
print(f"reset {proj.name}")
