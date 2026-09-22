"""Wipe a project's state back to empty. The corpus and your notes are untouched."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import project    # noqa: E402
import workspace  # noqa: E402

name = sys.argv[1] if len(sys.argv) > 1 else workspace.default_project()
print(f"reset {project.reset(name)}")
