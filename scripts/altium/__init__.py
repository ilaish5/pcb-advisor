"""Read-only Altium Designer file readers (SchDoc, PcbDoc, PrjPcb, RUL)."""
import pathlib

from .ole import AltiumReadError, kv, open_doc, stream, text_records
from .pcbdoc import mil_to_mm, pad_net_map, read_pcbdoc
from .prjpcb import read_prjpcb
from .rul import parse_rul_bytes, read_rul
from .schdoc import read_schdoc

__all__ = [
    "AltiumReadError",
    "kv",
    "mil_to_mm",
    "open_doc",
    "pad_net_map",
    "parse_rul_bytes",
    "read_any",
    "read_pcbdoc",
    "read_prjpcb",
    "read_rul",
    "read_schdoc",
    "stream",
    "text_records",
]


def read_any(path):
    """Read any supported Altium file, dispatching on extension (case-insensitive)."""
    p = pathlib.Path(path)
    ext = p.suffix.lower()
    if ext == ".schdoc":
        return read_schdoc(path)
    if ext == ".pcbdoc":
        return read_pcbdoc(path)
    if ext == ".prjpcb":
        return read_prjpcb(path)
    if ext == ".rul":
        return read_rul(path)
    raise AltiumReadError(str(path), f"unsupported Altium file type: '{p.suffix}'")
