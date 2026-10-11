"""OLE container and record-level helpers for Altium Designer binary documents."""
import contextlib
import pathlib
import struct
import olefile


class AltiumReadError(Exception):
    """Raised when an Altium file or stream cannot be read or parsed."""

    def __init__(self, path: str, reason: str):
        super().__init__(f"{path}: {reason}")
        self.path = str(path)
        self.reason = reason


def kv(text: str) -> dict[str, str]:
    """Parse pipe-delimited |KEY=VAL| text records into an uppercase-key dict."""
    d = {}
    for part in text.split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            d[k.upper()] = v
    return d


def text_records(blob: bytes, prefix: int = 0) -> list[dict[str, str]]:
    """Parse length-prefixed text records; skip binary records (flag in high byte)."""
    out = []
    i = 0
    while i + prefix + 4 <= len(blob):
        i += prefix
        n = struct.unpack("<I", blob[i:i + 4])[0]
        flag = n >> 24
        n &= 0xFFFFFF
        body = blob[i + 4:i + 4 + n]
        i += 4 + n
        if flag:
            continue
        out.append(kv(body.rstrip(b"\0").decode("latin-1", "replace")))
    return out


def stream(ole: olefile.OleFileIO, name: str) -> bytes:
    """Read an OLE stream by name; raise AltiumReadError if missing."""
    path = getattr(ole, "_altium_path", getattr(getattr(ole, "fp", None), "name", "<ole>"))
    parts = name.split("/") if "/" in name else name
    if not ole.exists(parts):
        raise AltiumReadError(str(path), f"missing stream {name}")
    try:
        return ole.openstream(parts).read()
    except Exception as exc:
        raise AltiumReadError(str(path), f"cannot read stream {name}: {exc}") from exc


@contextlib.contextmanager
def open_doc(path):
    """Context manager yielding an OleFileIO; raises AltiumReadError on failure."""
    p = pathlib.Path(path)
    if not p.is_file():
        raise AltiumReadError(str(path), "file not found")
    if not olefile.isOleFile(str(path)):
        raise AltiumReadError(str(path), "not an OLE compound document")
    try:
        ole = olefile.OleFileIO(str(path))
    except Exception as exc:
        raise AltiumReadError(str(path), f"cannot open OLE document: {exc}") from exc
    ole._altium_path = str(path)
    try:
        yield ole
    finally:
        ole.close()
