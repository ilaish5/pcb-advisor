import os
import json

def update_model():
    with open('scripts/model.py', 'r') as f:
        content = f.read()

    new_content = content.replace(
        '"memory": session_mod.read_memory(project, sess),',
        '"memory": session_mod.read_memory(project, sess),\n        "bom": (project_dir(project) / "BOM.md").read_text(encoding="utf-8") if (project_dir(project) / "BOM.md").exists() else "",'
    )
    with open('scripts/model.py', 'w') as f:
        f.write(new_content)

update_model()
