"""Minimal OLE (CFB) rewriter for building corrected copies of PcbDoc / PcbLib files (controls and canaries only).

Reads every stream of a source file with `olefile`, applies replacements, and writes a NEW compound file (version 4, 4096-byte sectors,
mini-stream for streams under 4096 bytes). Nothing is written in place, so a stream can grow or shrink freely. The result is valid for
olefile and for this oracle's readers; it is not meant to be opened in Altium (directory tree is a flat sibling chain, no CLSIDs).
A reference design for in-place growth exists on branch claude/stack-write-spike-7271f9 (tools/stack_write_spike.py `grow_stream`);
this module re-implements the idea as a full rewrite, which needs no free-sector or FAT-growth special cases.
"""
from __future__ import annotations

import pathlib
import struct

import olefile

SECTOR = 4096
MINI = 64
CUTOFF = 4096
FREE, END, FATSECT = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD
NOSTREAM = 0xFFFFFFFF


def read_all(path) -> dict[str, bytes]:
    """{ 'Storage/Stream': bytes } for every stream of the compound file."""
    ole = olefile.OleFileIO(str(path))
    try:
        return {"/".join(e): ole.openstream(e).read() for e in ole.listdir(streams=True, storages=False)}
    finally:
        ole.close()


def _pad(b: bytes, n: int) -> bytes:
    r = (-len(b)) % n
    return b + b"\0" * r


def build(streams: dict[str, bytes]) -> bytes:
    """Compound file (v4) holding `streams` ('A/B/Data' = storage A, storage B, stream Data)."""
    # directory entries: 0 root, then storages and streams
    storages: dict[str, int] = {}
    entries: list[dict] = [{"name": "Root Entry", "type": 5, "path": "", "child": NOSTREAM, "right": NOSTREAM, "left": NOSTREAM,
                            "start": END, "size": 0}]
    storages[""] = 0
    children_of: dict[int, list[int]] = {0: []}

    def ensure_storage(p: str) -> int:
        if p in storages:
            return storages[p]
        parent = ensure_storage(p.rsplit("/", 1)[0] if "/" in p else "")
        entries.append({"name": p.rsplit("/", 1)[-1], "type": 1, "path": p, "child": NOSTREAM, "right": NOSTREAM, "left": NOSTREAM,
                        "start": 0, "size": 0})
        sid = len(entries) - 1
        storages[p] = sid
        children_of[sid] = []
        children_of[parent].append(sid)
        return sid

    for name in streams:
        parent_path = name.rsplit("/", 1)[0] if "/" in name else ""
        parent = ensure_storage(parent_path)
        entries.append({"name": name.rsplit("/", 1)[-1], "type": 2, "path": name, "child": NOSTREAM, "right": NOSTREAM,
                        "left": NOSTREAM, "start": END, "size": len(streams[name])})
        children_of[parent].append(len(entries) - 1)
    for parent, kids in children_of.items():
        if kids:
            entries[parent]["child"] = kids[0]
            for a, b in zip(kids, kids[1:]):
                entries[a]["right"] = b

    # mini stream and regular streams
    mini_data = bytearray()
    mini_fat: list[int] = []
    regular: list[tuple[int, bytes]] = []
    for sid, e in enumerate(entries):
        if e["type"] != 2:
            continue
        data = streams[e["path"]]
        if len(data) == 0:
            e["start"] = END
        elif len(data) < CUTOFF:
            first = len(mini_fat)
            n = -(-len(data) // MINI)
            for k in range(n):
                mini_fat.append(first + k + 1 if k < n - 1 else END)
            mini_data += _pad(data, MINI)
            e["start"] = first
        else:
            regular.append((sid, data))

    dir_sectors = -(-len(entries) // (SECTOR // 128))
    mini_fat_sectors = -(-len(mini_fat) * 4 // SECTOR) if mini_fat else 0
    mini_cont = -(-len(mini_data) // SECTOR) if mini_data else 0
    data_sectors = sum(-(-len(d) // SECTOR) for _, d in regular)
    body = dir_sectors + mini_fat_sectors + mini_cont + data_sectors
    fat_sectors = 1
    while fat_sectors * (SECTOR // 4) < body + fat_sectors:
        fat_sectors += 1
    if fat_sectors > 109:
        raise ValueError("file too large for this writer (needs DIFAT sectors)")
    total = body + fat_sectors

    fat = [FREE] * (fat_sectors * (SECTOR // 4))
    cursor = 0

    def chain(first: int, n: int) -> None:
        for k in range(n):
            fat[first + k] = first + k + 1 if k < n - 1 else END

    out = bytearray()
    # layout: FAT sectors, directory, mini FAT, mini container, regular data
    fat_first = cursor
    for k in range(fat_sectors):
        fat[cursor + k] = FATSECT
    cursor += fat_sectors
    dir_first = cursor
    chain(cursor, dir_sectors)
    cursor += dir_sectors
    mf_first = cursor if mini_fat_sectors else END
    if mini_fat_sectors:
        chain(cursor, mini_fat_sectors)
        cursor += mini_fat_sectors
    mc_first = cursor if mini_cont else END
    if mini_cont:
        chain(cursor, mini_cont)
        cursor += mini_cont
    regular_blobs = []
    for sid, d in regular:
        n = -(-len(d) // SECTOR)
        entries[sid]["start"] = cursor
        chain(cursor, n)
        regular_blobs.append(_pad(d, SECTOR))
        cursor += n
    assert cursor == total, (cursor, total)

    entries[0]["start"] = mc_first
    entries[0]["size"] = len(mini_data)

    # header (512 bytes of fields, padded to one sector for v4)
    hdr = bytearray(512)
    hdr[0:8] = bytes.fromhex("D0CF11E0A1B11AE1")
    struct.pack_into("<HHHHH", hdr, 24, 0x3E, 4, 0xFFFE, 12, 6)
    struct.pack_into("<I", hdr, 40, dir_sectors)            # number of directory sectors (v4)
    struct.pack_into("<I", hdr, 44, fat_sectors)
    struct.pack_into("<I", hdr, 48, dir_first)
    struct.pack_into("<I", hdr, 56, CUTOFF)
    struct.pack_into("<I", hdr, 60, mf_first)
    struct.pack_into("<I", hdr, 64, mini_fat_sectors)
    struct.pack_into("<I", hdr, 68, END)                    # first DIFAT sector
    struct.pack_into("<I", hdr, 72, 0)
    for k in range(109):
        struct.pack_into("<I", hdr, 76 + 4 * k, fat_first + k if k < fat_sectors else FREE)
    out += _pad(bytes(hdr), SECTOR)

    out += b"".join(struct.pack("<I", v) for v in fat)
    d = bytearray()
    for e in entries:
        nm = e["name"].encode("utf-16-le")
        rec = bytearray(128)
        rec[0:len(nm)] = nm
        struct.pack_into("<H", rec, 64, len(nm) + 2)
        rec[66] = e["type"]
        rec[67] = 1
        struct.pack_into("<III", rec, 68, e["left"], e["right"], e["child"])
        struct.pack_into("<I", rec, 116, e["start"] if e["type"] != 1 else 0)
        struct.pack_into("<Q", rec, 120, e["size"])
        d += rec
    out += _pad(bytes(d), SECTOR)
    if mini_fat_sectors:
        out += _pad(b"".join(struct.pack("<I", v) for v in mini_fat), SECTOR)
    if mini_cont:
        out += _pad(bytes(mini_data), SECTOR)
    for b in regular_blobs:
        out += b
    return bytes(out)


def rewrite(src, dst, replace: dict[str, bytes] | None = None, header_counts: dict[str, int] | None = None) -> pathlib.Path:
    """Copy `src` to `dst` with the streams in `replace` swapped. `header_counts` = {'Tracks6': n} also rewrites '<name>/Header'
    (a uint32 record count) so the reader's header check still holds."""
    streams = read_all(src)
    for k, v in (replace or {}).items():
        if k not in streams:
            raise KeyError(f"no stream {k} in {src}")
        streams[k] = v
    for k, n in (header_counts or {}).items():
        streams[k + "/Header"] = struct.pack("<I", n) + streams[k + "/Header"][4:]
    pathlib.Path(dst).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(dst).write_bytes(build(streams))
    return pathlib.Path(dst)
