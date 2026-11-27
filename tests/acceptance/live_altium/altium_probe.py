"""The oracle's own line to Altium (A2): a separate DelphiScript (probe/OracleProbe.pas, in its own exchange folder) that only reads
or writes Altium's own report files. It shares nothing with the product's bridge but the running Altium.

    run_probe([("DRC", pcb, report)])          -> list of log lines
    drc_report(pcb, scratch)                   -> the text Altium wrote (the file is read, not a bridge summary)
    compile_nets(prj, scratch)                 -> {"violations": [...], "nets": {name: [pin full names]}}
    close_scratch(folder)                      -> documents under folder closed without saving
    x2_dialogs()                               -> the dialogs X2.EXE owns right now (class, title, texts); read only
"""
from __future__ import annotations

import ctypes
import hashlib
import os
import pathlib
import re
import shutil
import subprocess
import time
from ctypes import wintypes

HERE = pathlib.Path(__file__).resolve().parent
EXCHANGE = pathlib.Path(os.environ.get("PUBLIC") or r"C:\Users\Public") / "acc-probe"      # the .pas uses the same folder
STAGE = pathlib.Path(os.environ.get("LOCALAPPDATA") or str(pathlib.Path.home() / "AppData" / "Local")) / "acc-probe-stage"


class ProbeError(RuntimeError):
    pass


def x2_exe() -> str:
    p = os.environ.get("ALTIUM_EXE")
    if p and pathlib.Path(p).is_file():
        return p
    for cand in sorted(pathlib.Path(r"C:\Program Files\Altium").glob("AD*/X2.EXE"), reverse=True):
        return str(cand)
    raise ProbeError("Altium X2.EXE not found (set ALTIUM_EXE)")


def x2_running() -> bool:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq X2.EXE", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    return "X2.EXE" in out.upper()


def x2_dialogs() -> list[dict]:
    """Visible #32770 / TMessageForm windows owned by X2.EXE: [{"cls", "title", "texts": [...]}]. Read only."""
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq X2.EXE", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    pids = {int(m) for m in re.findall(r'"X2\.EXE","(\d+)"', out, re.I)}
    user32 = ctypes.windll.user32
    found: list[dict] = []

    def text_of(h):
        buf = ctypes.create_unicode_buffer(1024)
        user32.GetWindowTextW(h, buf, 1024)
        return buf.value.strip()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, cls, 64)
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if cls.value in ("#32770", "TMessageForm") and pid.value in pids:
                texts: list[str] = []

                @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
                def child(h, _l):
                    t = text_of(h)
                    if t:
                        texts.append(t)
                    return True
                user32.EnumChildWindows(hwnd, child, 0)
                found.append({"cls": cls.value, "title": text_of(hwnd), "texts": texts, "hwnd": int(hwnd)})
        return True

    user32.EnumWindows(each, 0)
    return found


def _stage() -> pathlib.Path:
    src = HERE / "probe"
    h = hashlib.sha256()
    for n in ("OracleProbe.PrjScr", "OracleProbe.pas"):
        h.update((src / n).read_bytes())
    dst = STAGE / f"OracleProbe-{h.hexdigest()[:12]}"
    if not (dst / "OracleProbe.PrjScr").is_file():
        dst.mkdir(parents=True, exist_ok=True)
        for n in ("OracleProbe.PrjScr", "OracleProbe.pas"):
            shutil.copy2(src / n, dst / n)
    return dst / "OracleProbe.PrjScr"


def _stop_executor() -> None:
    try:
        subprocess.Popen(f'"{x2_exe()}" -REditScript:Stop')
    except OSError:
        pass
    time.sleep(2)


def run_probe(commands: list[tuple], start_timeout: float = 45, total_timeout: float = 300, stall: float = 90) -> list[str]:
    """Run the probe script in the running Altium. Raises ProbeError (with the dialogs seen) when it does not finish."""
    if not x2_running():
        raise ProbeError("Altium is not running")
    EXCHANGE.mkdir(parents=True, exist_ok=True)
    for n in ("response.txt", "log.txt", "start.flag", "end.flag"):
        (EXCHANGE / n).unlink(missing_ok=True)
    body = "\r\n".join("\t".join(str(f) for f in c) for c in commands) + "\r\n"
    (EXCHANGE / "request.txt").write_bytes(body.encode("cp1252", "replace"))
    script = _stage()
    subprocess.Popen(f'"{x2_exe()}" -RScriptingSystem:RunScript(ProjectName="{script}"|ProcName="OracleProbe>Run")')
    t0 = time.time()
    while not (EXCHANGE / "start.flag").exists():
        if time.time() - t0 > start_timeout:
            d = x2_dialogs()
            _stop_executor()
            raise ProbeError(f"the probe script did not start; dialogs: {d}")
        time.sleep(0.5)
    t_log, last = time.time(), None
    while not (EXCHANGE / "end.flag").exists():
        try:
            st = (EXCHANGE / "log.txt").stat()
            now = (st.st_size, st.st_mtime)
        except OSError:
            now = None
        if now != last:
            last, t_log = now, time.time()
        if time.time() - t_log > stall or time.time() - t0 > total_timeout:
            d = x2_dialogs()
            _stop_executor()
            raise ProbeError(f"the probe stalled; dialogs: {d}")
        time.sleep(0.5)
    resp = (EXCHANGE / "response.txt").read_text(encoding="cp1252", errors="replace").splitlines()
    log = (EXCHANGE / "log.txt").read_text(encoding="cp1252", errors="replace").splitlines()
    errs = [r for r in resp if r.startswith("ERR")]
    if errs:
        raise ProbeError("; ".join(errs))
    return log


class AsyncProbe:
    """A probe batch that is started and left running (a MODAL command blocks it until somebody closes the box)."""

    def __init__(self, commands: list[tuple]):
        self.commands = commands
        self.t_start = None

    def start(self, start_timeout: float = 45) -> "AsyncProbe":
        if not x2_running():
            raise ProbeError("Altium is not running")
        EXCHANGE.mkdir(parents=True, exist_ok=True)
        for n in ("response.txt", "log.txt", "start.flag", "end.flag"):
            (EXCHANGE / n).unlink(missing_ok=True)
        body = "\r\n".join("\t".join(str(f) for f in c) for c in self.commands) + "\r\n"
        (EXCHANGE / "request.txt").write_bytes(body.encode("cp1252", "replace"))
        subprocess.Popen(f'"{x2_exe()}" -RScriptingSystem:RunScript(ProjectName="{_stage()}"|ProcName="OracleProbe>Run")')
        t0 = time.time()
        while not (EXCHANGE / "start.flag").exists():
            if time.time() - t0 > start_timeout:
                raise ProbeError("the probe script did not start (Altium was busy); dialogs: " + str(x2_dialogs()))
            time.sleep(0.3)
        self.t_start = time.time()
        return self

    def ended(self) -> bool:
        return (EXCHANGE / "end.flag").exists()

    def log(self) -> list[str]:
        try:
            return (EXCHANGE / "log.txt").read_text(encoding="cp1252", errors="replace").splitlines()
        except OSError:
            return []


def close_scratch(folder: pathlib.Path) -> None:
    """Close (no save) every open document under `folder` (the scratch Altium copy); the owner's documents are elsewhere."""
    run_probe([("CLOSE", str(folder))])


def open_docs(folder: pathlib.Path, tmp: pathlib.Path) -> list[tuple[str, str, int]]:
    """(kind, path, modified) of the scratch project(s) and their open documents; kind is PRJ or DOC."""
    out = tmp / "open.txt"
    out.unlink(missing_ok=True)
    run_probe([("OPEN", str(folder), str(out))])
    rows = []
    if out.is_file():
        for line in out.read_text(encoding="cp1252", errors="replace").splitlines():
            p = line.split("\t")
            if p and p[0] in ("PRJ", "DOC"):
                rows.append((p[0], p[1], int(p[2]) if len(p) > 2 and p[2].lstrip("-").isdigit() else 0))
    return rows


def drc_report(pcb: pathlib.Path, tmp: pathlib.Path, reopen: bool = True) -> str:
    """Altium's batch design rule check on `pcb`, run by the probe on the board as it is on disk: any open copy under the scratch
    folder is closed without saving first (A2: saved, closed, reopened), then Altium writes the report file, which is read here."""
    rep = tmp / f"drc-{int(time.time())}.txt"
    rep.unlink(missing_ok=True)
    cmds = []
    if reopen:
        cmds.append(("CLOSE", str(pcb.parent)))
    cmds.append(("DRC", str(pcb), str(rep)))
    cmds.append(("CLOSE", str(pcb.parent)))
    run_probe(cmds)
    return rep.read_text(encoding="utf-16" if rep.read_bytes()[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8", errors="replace")


# ------------------------------------------------------------------------------------------- report parsing (Altium's own format)
def drc_counts(text: str) -> dict[str, int]:
    """Violation count per rule from the summary lines of Altium's text DRC report: `Rule Violations|<rule text>|<n>`."""
    counts: dict[str, int] = {}
    for line in text.splitlines():
        m = re.match(r"^Rule Violations\|(.+)\|(\d+)\s*$", line.strip())
        if m and m.group(1) != "Total":
            counts[m.group(1)] = counts.get(m.group(1), 0) + int(m.group(2))
    return counts


def drc_total(text: str) -> int:
    m = re.search(r"^Violations\|Total\|(\d+)", text, re.M)
    return int(m.group(1)) if m else sum(drc_counts(text).values())


def compile_nets(prj: pathlib.Path, tmp: pathlib.Path) -> dict:
    out = tmp / f"compile-{int(time.time())}.txt"
    out.unlink(missing_ok=True)
    run_probe([("COMPILE", str(prj), str(out))])
    res: dict = {"violations": [], "nets": {}}
    for line in out.read_text(encoding="cp1252", errors="replace").splitlines():
        p = line.split("\t")
        if p[0] == "V" and len(p) >= 4:
            res["violations"].append({"level": p[1], "short": p[2], "long": p[3]})
        elif p[0] == "P" and len(p) >= 3:
            res["nets"].setdefault(p[1], []).append(p[2])
    return res


# ------------------------------------------------------------------------------------------------- modal dialogs raised by Altium
def close_dialog(hwnd: int, wait: float = 5.0) -> bool:
    """Close one Altium dialog by its window handle: its default button is clicked (BM_CLICK on the first push button), else WM_CLOSE.
    Only called for a dialog this harness provoked (it was not on screen before the injected step started)."""
    user32 = ctypes.windll.user32
    BM_CLICK, WM_CLOSE = 0x00F5, 0x0010
    buttons: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def child(h, _l):
        cls = ctypes.create_unicode_buffer(32)
        user32.GetClassNameW(h, cls, 32)
        if cls.value.lower() in ("button", "tbutton") and user32.IsWindowVisible(h):
            buttons.append(int(h))
        return True
    user32.EnumChildWindows(hwnd, child, 0)
    if buttons:
        user32.PostMessageW(buttons[0], BM_CLICK, 0, 0)
    else:
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    t0 = time.time()
    while time.time() - t0 < wait:
        if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd):
            return True
        time.sleep(0.3)
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    time.sleep(1)
    return not user32.IsWindowVisible(hwnd)


def dialog_keys(ds: list[dict]) -> set:
    return {(d["cls"], d["title"], tuple(d["texts"])) for d in ds}


class Held:
    """A handle on `path` that denies other processes write and delete access (share mode READ only): the file is 'locked' as an
    open document is. Entering raises OSError when the file cannot be locked (then the lock is not established and the metric errors)."""

    def __init__(self, path: pathlib.Path):
        self.path = pathlib.Path(path)
        self.h = None

    def __enter__(self) -> "Held":
        k32 = ctypes.windll.kernel32
        k32.CreateFileW.restype = ctypes.c_void_p
        h = k32.CreateFileW(str(self.path), 0x80000000, 0x1, None, 3, 0x80, None)      # GENERIC_READ, FILE_SHARE_READ, OPEN_EXISTING
        if h in (None, ctypes.c_void_p(-1).value):
            raise OSError(f"could not lock {self.path} (error {ctypes.GetLastError()})")
        self.h = h
        return self

    def __exit__(self, *exc) -> None:
        if self.h:
            ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(self.h))
            self.h = None

    def confirmed(self) -> bool:
        """Independent check that a writer is refused now."""
        try:
            with open(self.path, "r+b"):
                return False
        except OSError:
            return True
