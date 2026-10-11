"""Read Altium .RUL exported design rule files."""
import pathlib

from .ole import AltiumReadError, kv


def parse_rul_bytes(b: bytes) -> list[dict[str, str]]:
    """Parse Altium .RUL export byte content into a list of rule dicts."""
    out = []
    for line in b.splitlines():
        line = line.strip().rstrip(b"\xb6\x00\0").strip()
        if not line:
            continue
        txt = line.decode("latin-1", "replace")
        d = kv(txt)
        if d:
            out.append(d)
    return out


def read_rul(path) -> list[dict[str, str]]:
    """Read an Altium .RUL design rules file into a list of rule dicts."""
    p = pathlib.Path(path)
    if not p.is_file():
        raise AltiumReadError(str(path), "file not found")
    try:
        data = p.read_bytes()
    except Exception as exc:
        raise AltiumReadError(str(path), f"cannot read file: {exc}") from exc
    return parse_rul_bytes(data)
