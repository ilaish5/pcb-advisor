"""Read Altium PrjPcb project files."""
import pathlib
import re

from .ole import AltiumReadError


def read_prjpcb(path) -> dict:
    """Read an Altium .PrjPcb project file and return document structure and status."""
    p = pathlib.Path(path)
    if not p.is_file():
        raise AltiumReadError(str(path), "file not found")
    try:
        content = p.read_bytes().decode("latin-1")
    except Exception as exc:
        raise AltiumReadError(str(path), f"cannot read project file: {exc}") from exc

    current_sec = None
    sec_data: dict[str, str] = {}
    doc_sections: list[tuple[str, dict[str, str]]] = []

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current_sec = line[1:-1].strip()
            sec_data = {}
            doc_sections.append((current_sec, sec_data))
        elif "=" in line and current_sec is not None:
            k, v = line.split("=", 1)
            sec_data[k.strip().upper()] = v.strip()

    documents = []
    for sec_name, data in doc_sections:
        m = re.match(r"^Document\d+$", sec_name, re.IGNORECASE)
        if m and "DOCUMENTPATH" in data:
            documents.append(data["DOCUMENTPATH"])

    parent = p.parent
    sheets = [d for d in documents if d.lower().endswith((".schdoc", ".sch"))]
    pcbs = [d for d in documents if d.lower().endswith((".pcbdoc", ".pcb"))]
    outjobs = [d for d in documents if d.lower().endswith((".outjob",))]
    other = [d for d in documents if d not in sheets and d not in pcbs and d not in outjobs]

    missing = []
    for d in documents:
        target = parent / pathlib.Path(d.replace("\\", "/"))
        if not target.exists():
            missing.append(d)

    return {
        "file": p.name,
        "name": p.stem,
        "documents": documents,
        "sheets": sheets,
        "pcbs": pcbs,
        "outjobs": outjobs,
        "other": other,
        "missing": missing,
    }
