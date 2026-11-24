#!/usr/bin/env python3
"""
Two-way link to a running Altium Designer: create the project, add documents, draw a schematic skeleton.

    python scripts/altium/bridge.py status
    python scripts/altium/bridge.py new-project <project>      PrjPcb + one PcbDoc + one SchDoc per sheet, linked
    python scripts/altium/bridge.py add-sheet <project> <name> | add-pcb <project>
    python scripts/altium/bridge.py skeleton <project> [<sheet>]  title block, parameters, one text frame per section;
                                                                 no components, safe to repeat
    python scripts/altium/bridge.py draw-schematic <project> [<sheet>] [--replace]
                                                                 the netlist drawn as a schematic: parts from the project SchLib,
                                                                 a stub + net label / power port per pin, checked after the save
    python scripts/altium/bridge.py import-rules <project>       the advisor's rule set into the linked PcbDoc, by rule name
    python scripts/altium/bridge.py run-outjob <project>         Gerber, NC drill, BOM, pick and place into the outputs folder
    python scripts/altium/bridge.py open <project>
    python scripts/altium/bridge.py build-library <project>      the project's Altium library (SchLib, PcbLib, 3D, LibPkg,
                                                                 compiled IntLib, installed and added to the Altium
                                                                 project as a project library) next to the Altium project

How: Altium runs a DelphiScript from scripts/altium/bridge/ (`X2.EXE -RScriptingSystem:RunScript(...)`); the request
and the answer go through files in a fixed folder. The script mechanism is adapted from altium-mcp (MIT, Copyright (c)
2025 Siddharth Ahuja, see bridge/LICENSE-altium-mcp). A script runtime error leaves Altium's script executor paused;
we notice (the script never starts or stops logging), release it with `X2.EXE -REditScript:Stop` and say so.

import-rules adds or updates the rules the preset, the Rules tab's extra rules and rules-off.json call for (matched by
name; the student's own rules are never deleted) and reads the PcbDoc back to confirm. run-outjob adds our OutJob
(scripts/outjob.py) to the project when it has none, then runs its Folder Structure containers.

build-library turns library/build/ (scripts/partlib.py prepare, run first when it is stale) into
<altium project>/Library/<Project>-Lib.SchLib / .PcbLib / 3D/*.step / .LibPkg and the IntLib, always from the shipped
templates (bridge/templates), so a rebuild never duplicates parts, then reads the files back to count and check them.

Only the server changes Altium: the CLI above is for the person running the tool, and an agent working in the student's
shell gets "Altium changes go through actions". Developers set PCB_ADVISOR_DEV=1 to use the writing operations by hand.

Every write copies the files it will change into <altium project>/.advisor-backup/<time>/ first (undo = copy back)
and is logged in the advisor project's altium-log.jsonl. Windows with Altium Designer only; elsewhere every
operation says so instead of failing obscurely. Components and routes are never touched.
"""
import argparse
import configparser
import datetime as dt
import json
import math
import os
import pathlib
import re
import shutil
import subprocess
import sys
import threading
import time

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import jlc_upload  # noqa: E402
import outjob  # noqa: E402
import partlib  # noqa: E402
import partlib_mech  # noqa: E402
import partlib_order  # noqa: E402
import project as project_mod  # noqa: E402
import rule_kinds  # noqa: E402
import rules as rules_mod  # noqa: E402
import runlog  # noqa: E402
import store  # noqa: E402
import workspace  # noqa: E402
from altium import AltiumReadError, registry  # noqa: E402
from altium.lib import read_pcblib, read_schlib  # noqa: E402
from altium.prjpcb import read_prjpcb as _read_prjpcb  # noqa: E402
from altium.schdoc import read_schdoc  # noqa: E402

BRIDGE_DIR = pathlib.Path(__file__).resolve().parent / "bridge"
SCRIPT_PROJECT = BRIDGE_DIR / "AdvisorBridge.PrjScr"      # the shipped source; Altium runs a staged copy (stage_script)
SCRIPT_FILES = ("AdvisorBridge.PrjScr", "AdvisorBridge.pas")
STAGE_PREFIX = "AdvisorBridge-"
STAGE_KEEP = 2
EXCHANGE = pathlib.Path(os.environ.get("PUBLIC") or r"C:\Users\Public") / "pcb-advisor-bridge"   # the .pas uses the same
TAG = "[advisor]"                       # first word of every text frame we draw; how a re-run finds its own frames
BACKUP_DIR = ".advisor-backup"
MIN_PRJPCB = "[Design]\r\nVersion=1.0\r\n"      # Altium fills in the rest when it saves
_lock = threading.Lock()


class BridgeError(ValueError):      # a ValueError, so apply_actions reports it as a refused action
    pass


# The refusals a retry may fix without asking again (W3): the server assigns the code where it raises, never infers it from the
# wording. Frozen: a new code is a new consent decision (pinned by test_agent_retry).
NEUTRAL_CODES = frozenset({"pins.unmapped", "sheet.too_big", "prereq.library_not_built", "prereq.no_project", "prereq.no_netlist",
                           "prereq.rules_not_imported"})


class Fixable(BridgeError):
    """A refusal with a server-assigned code from NEUTRAL_CODES: the fix changes how the action runs, not what or whether."""

    def __init__(self, code, message):
        if code not in NEUTRAL_CODES:
            raise ValueError(f"not a neutral code: {code}")
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------- Altium side

def _exe():
    if sys.platform != "win32":
        raise BridgeError("The Altium bridge works on Windows with Altium Designer installed; this computer is not Windows.")
    path = workspace.get("altium.install_path", "")
    if path and (pathlib.Path(path) / "X2.EXE").is_file():
        return str(pathlib.Path(path) / "X2.EXE")
    for inst in registry.find_installs():
        if inst.get("exe"):
            return inst["exe"]
    raise BridgeError("Altium Designer was not found. Set its folder in Settings (altium.install_path).")


def stage_root():
    """Where the content-addressed script copies live (not the install folder: that one is replaced by updates)."""
    base = os.environ.get("LOCALAPPDATA") or str(pathlib.Path.home() / "AppData" / "Local")
    return pathlib.Path(base) / "pcb-advisor" / "script-stage"


def stage_script(src_dir=None, root=None, keep=STAGE_KEEP):
    """Copy AdvisorBridge.PrjScr + .pas into <root>/AdvisorBridge-<sha12 of both>/ and return the staged .PrjScr path.
    Altium keeps the compiled script of a script project it has opened, so a changed .pas under the same path is never
    reloaded (new commands fail as 'unknown command'). A different content gives a different project path, which Altium
    loads fresh. Same content -> same path (nothing copied twice). Older staged folders beyond `keep` are deleted
    (newest by use first; the one just staged always stays)."""
    import hashlib
    src_dir = pathlib.Path(src_dir) if src_dir else BRIDGE_DIR
    root = pathlib.Path(root) if root else stage_root()
    h = hashlib.sha256()
    for name in SCRIPT_FILES:
        f = src_dir / name
        if not f.is_file():
            raise BridgeError(f"bridge script missing: {f}")
        h.update(name.encode("ascii") + b"\x00" + f.read_bytes() + b"\x00")
    dest = root / f"{STAGE_PREFIX}{h.hexdigest()[:12]}"
    if not all((dest / n).is_file() for n in SCRIPT_FILES):
        tmp = root / f".tmp-{os.getpid()}-{time.time_ns()}"
        tmp.mkdir(parents=True, exist_ok=True)
        try:
            for name in SCRIPT_FILES:
                shutil.copy2(src_dir / name, tmp / name)
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            tmp.rename(dest)
        except OSError:
            shutil.rmtree(tmp, ignore_errors=True)
            if not all((dest / n).is_file() for n in SCRIPT_FILES):
                raise
    try:
        os.utime(dest, None)            # "last used", so cleanup keeps the copies still in use
        olds = sorted((d for d in root.iterdir() if d.is_dir() and d.name.startswith(STAGE_PREFIX) and d != dest),
                      key=lambda d: d.stat().st_mtime, reverse=True)
        for d in olds[max(0, keep - 1):]:
            shutil.rmtree(d, ignore_errors=True)
    except OSError:
        pass
    return dest / "AdvisorBridge.PrjScr"


def _running():
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq X2.EXE", "/FO", "CSV", "/NH"], capture_output=True,
                             text=True, timeout=15).stdout
        return "X2.EXE" in out.upper()
    except (OSError, subprocess.SubprocessError):
        return False


def _close_dialogs():
    """Close the dialog boxes Altium left open (class #32770 or a script error box, owned by X2.EXE), so the next script
    can run. Returns one "title: text" line per dialog closed; each is logged first, so a stall can be explained."""
    try:
        import ctypes
        from ctypes import wintypes
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq X2.EXE", "/FO", "CSV", "/NH"], capture_output=True,
                             text=True, timeout=15).stdout
        pids = {int(m) for m in re.findall(r'"X2\.EXE","(\d+)"', out, re.I)}
        user32 = ctypes.windll.user32
        closed = []

        def text_of(hwnd):
            buf = ctypes.create_unicode_buffer(1024)
            user32.GetWindowTextW(hwnd, buf, 1024)
            return buf.value.strip()

        def describe(hwnd, cls):
            parts = []

            @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            def child(h, _):
                t = text_of(h)
                if t:
                    parts.append(t)
                return True
            user32.EnumChildWindows(hwnd, child, 0)
            return f"[{cls}] {text_of(hwnd)}: " + " / ".join(parts)

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def each(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                cls = ctypes.create_unicode_buffer(64)
                user32.GetClassNameW(hwnd, cls, 64)
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if cls.value in ("#32770", "TMessageForm") and pid.value in pids:
                    closed.append(describe(hwnd, cls.value))
                    if cls.value == "#32770":
                        user32.PostMessageW(hwnd, 0x0010, 0, 0)       # WM_CLOSE
                    else:                                             # a script error box: only its OK button ends it
                        user32.PostMessageW(hwnd, 0x0100, 13, 0)      # WM_KEYDOWN, VK_RETURN
                        user32.PostMessageW(hwnd, 0x0101, 13, 0)      # WM_KEYUP
            return True

        user32.EnumWindows(each, 0)
        for line in closed:
            DIALOG_LOG.append(line)
        return closed
    except Exception:
        return []


DIALOG_LOG = []         # every dialog closed this session, "[class] title: text"


def release_executor():
    """Stop a script that Altium left paused after a runtime error (every later script would silently do nothing).
    Closes the dialogs first (and notes what they said), also the script error window, so that a retry can start.
    Returns the dialog texts."""
    seen = _close_dialogs()
    try:
        subprocess.Popen(f'"{_exe()}" -REditScript:Stop')
    except OSError:
        pass
    time.sleep(2)
    seen += _close_dialogs()            # the error window can appear only once the executor is stopped
    return seen


_PATH_FIELD = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")


def _ascii(text):
    """The script reads the request as ANSI text: keep it plain ASCII. Text that is shown (a title, a label) is transliterated
    (draw.transliterate: Hebrew letters by a table, accents dropped, anything else '_'), never '?'. A file path with a character
    that does not fit cannot be fixed that way (another path would be opened): that is an error."""
    text = str(text)
    if text.isascii():
        return text
    if _PATH_FIELD.match(text):
        raise BridgeError(f"The path {text!r} has a character that Altium's script cannot read (the script reads plain ASCII only). "
                          "Move the project to a folder whose whole path is letters, digits and spaces only (e.g. C:\\Users\\Public\\Documents\\Altium).")
    from altium import draw
    return draw.transliterate(text)


def _read(path):
    try:
        return pathlib.Path(path).read_text(encoding="ascii", errors="replace").splitlines()
    except OSError:
        return []


def _stat(path):
    """(size, mtime) of a file, or None. Only a stat: Altium writes log.txt and response.txt without sharing, so we must
    never open them while the script runs (a read at the wrong moment makes Altium's save fail and the script freeze)."""
    try:
        st = os.stat(path)
        return st.st_size, st.st_mtime_ns
    except OSError:
        return None


READ_ONLY = {"PING", "PROJECT", "PCBCHECK", "PCBEXTENT", "FPINFO", "DRAWCHECK", "CHECKINST", "DRC", "DOCSTATE"}   # all other commands change Altium
_server = False


def allow_writes():
    """Called once by the server process: from then on this process may send Altium-changing commands (its actions and the
    student's own buttons). Other processes (the agent's shell, the CLI) cannot, unless PCB_ADVISOR_DEV=1."""
    global _server
    _server = True


def _check_writes_allowed(commands):
    if _server or os.environ.get("PCB_ADVISOR_DEV") == "1":
        return
    bad = sorted({str(c[0]).upper() for c in commands if str(c[0]).upper() not in READ_ONLY})
    if bad:
        raise BridgeError("Altium changes go through actions (altium.draw_schematic, altium.place_pcb, altium.route_pcb, "
                          "library.build, ...); the CLI is read-only for agents. Refused: " + ", ".join(bad) + ". Nothing was changed.")


def _cmd_args(commands):
    """The commands as sent (name and fields), each cut, at most 40 of them: what a debugger needs to replay a batch."""
    out = []
    for c in list(commands)[:40]:
        try:
            out.append([str(x)[:200] for x in c][:12])
        except Exception:
            out.append([repr(c)[:200]])
    return out


def run_commands(commands, start_timeout=45, stall_timeout=60, total_timeout=300):
    """_run_commands, with one run-log record per batch: the commands with their fields, seconds, ok or the full error (it carries the dialog
    texts), the script's last log lines, and the project it ran for (when the server set one)."""
    t0 = time.time()
    names = [str(c[0]) for c in commands]
    project = getattr(runlog.ctx, "project", "") or ""
    try:
        log = _run_commands(commands, start_timeout, stall_timeout, total_timeout)
    except BaseException as exc:
        runlog.event("altium", commands=names, args=_cmd_args(commands), project=project, seconds=round(time.time() - t0, 1), ok=False,
                     error=f"{type(exc).__name__}: {exc}", dialogs=DIALOG_LOG[-10:])
        raise
    runlog.event("altium", commands=names, args=_cmd_args(commands), project=project, seconds=round(time.time() - t0, 1), ok=True,
                 result=[str(x)[:300] for x in (log or [])[-15:]] if isinstance(log, (list, tuple)) else "")
    return log


def _run_commands(commands, start_timeout=45, stall_timeout=60, total_timeout=300):
    """Send command lines (tab separated fields) to Altium, wait for DONE. Returns the script's log lines.
    Raises BridgeError with the last step when the script does not start, stops logging or reports an error.
    While the script runs we only look at whether start.flag / end.flag exist and whether log.txt grows."""
    _check_writes_allowed(commands)
    exe = _exe()
    script = stage_script()            # a changed script is a new project path: Altium loads it fresh
    with _lock:
        EXCHANGE.mkdir(parents=True, exist_ok=True)
        for name in ("response.txt", "log.txt", "start.flag", "end.flag"):
            (EXCHANGE / name).unlink(missing_ok=True)
        body = "\r\n".join("\t".join(_ascii(f) for f in c) for c in commands) + "\r\n"
        (EXCHANGE / "request.txt").write_bytes(body.encode("ascii"))     # bytes: text mode would double the CR on Windows
        cold = not _running()          # Altium has to start first: that takes a while
        for attempt in (1, 2):
            subprocess.Popen(f'"{exe}" -RScriptingSystem:RunScript(ProjectName="{script}"|ProcName="AdvisorBridge>Run")')
            t0 = time.time()
            started = False
            while time.time() - t0 < start_timeout * (8 if cold else 1):
                if (EXCHANGE / "start.flag").exists():
                    started = True
                    break
                time.sleep(0.5)
            if started:
                break
            shown = release_executor()          # a paused executor ignores new scripts: release it and try once more
            if attempt == 2:
                if any(s.startswith("[TMessageForm]") for s in shown):
                    # Altium's own message box: its text is a TLabel (not a window), so it cannot be read. On a cold start the
                    # usual cause is that Altium is not signed in to an account / licence (seen 2026-11-11).
                    raise BridgeError("Altium did not start the script because a message box in Altium is blocking it (its text cannot "
                                      "be read from here). Open Altium, sign in if it asks you to, close any message box that is "
                                      "open, and then try again. Dialog: " + " | ".join(shown))
                raise BridgeError("Altium did not start the script (a script error or a dialog box was blocking it"
                                  + (f": {' | '.join(shown)}" if shown else "") + "). "
                                  "I released the script executor and closed dialogs; try again.")
        t_log, last, t0 = time.time(), _stat(EXCHANGE / "log.txt"), time.time()
        while not (EXCHANGE / "end.flag").exists():
            now = _stat(EXCHANGE / "log.txt")
            if now != last:
                last, t_log = now, time.time()
            if time.time() - t_log > stall_timeout or time.time() - t0 > total_timeout:
                shown = release_executor()
                log = _read(EXCHANGE / "log.txt")           # the script is stopped now: safe to read
                raise BridgeError("Altium stopped in the middle of the script, after: "
                                  f"{log[-1] if log else 'nothing'}. I released the script executor."
                                  + (f" Dialogs: {' | '.join(shown)}" if shown else ""))
            time.sleep(0.5)
        resp, log = _read(EXCHANGE / "response.txt"), _read(EXCHANGE / "log.txt")
        errs = [r for r in resp if r.startswith("ERR")]
        if errs:
            raise BridgeError("Altium refused a step: " + "; ".join(e[4:] for e in errs) + f" (last step: {log[-1] if log else '-'})")
        if "DONE" not in resp:
            raise BridgeError(f"Altium ended the script without finishing it, after: {log[-1] if log else 'nothing'}.")
        return log


def status():
    out = {"windows": sys.platform == "win32", "exe": "", "running": False, "executor": "not tested", "error": "", "script": ""}
    try:
        out["exe"] = _exe()
    except BridgeError as exc:
        out["error"] = str(exc)
        return out
    try:
        out["script"] = str(stage_script())
    except (BridgeError, OSError) as exc:
        out["error"] = str(exc)
        return out
    out["running"] = _running()
    if out["running"]:
        try:
            run_commands([("PING",)], start_timeout=20)
            out["executor"] = "ok"
        except BridgeError as exc:
            out["executor"] = "blocked"
            out["error"] = str(exc)
    return out


# ---------------------------------------------------------------- the Altium project on disk

def altium_base():
    """Where Altium projects live: config altium.projects_dir, else the Altium folder of the Public profile."""
    cfg = (workspace.get("altium.projects_dir", "") or "").strip()
    if cfg:
        return pathlib.Path(cfg).expanduser()
    return pathlib.Path(os.environ.get("PUBLIC") or r"C:\Users\Public") / "Documents" / "Altium"


def _file_name(text, fallback):
    """A Windows file name that stays ASCII (Altium's script reads ANSI)."""
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", _ascii(text))
    s = re.sub(r"[?\s]+", " ", s).strip(" .")[:60].strip(" .")
    return s or fallback


def _stamp():
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def _backup(prj_file, files):
    """Copy the files that exist into <project>/.advisor-backup/<time>/; returns that folder (or '' if nothing to save)."""
    files = [pathlib.Path(f) for f in files if pathlib.Path(f).is_file()]
    if not files:
        return ""
    dest = pathlib.Path(prj_file).parent / BACKUP_DIR / _stamp()
    dest.mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.copy2(f, dest / f.name)
    return str(dest)


SAME_NAME = "uninstalled same-name "          # the script's log line for an installed library of our file name


def _log(project, op, **fields):
    store.append(project, "altium-log.jsonl", {"ts": store.now(), "by": "altium-bridge", "op": op, **fields})


def read_prjpcb(prj):
    try:
        return _read_prjpcb(prj)
    except AltiumReadError as exc:
        raise BridgeError(str(exc)) from exc


def _linked(project):
    prj = project_mod.altium_link(project).get("project_file")
    if not prj or not pathlib.Path(prj).is_file():
        raise Fixable("prereq.no_project", "No Altium project is linked to this project yet. Create one first.")
    return pathlib.Path(prj)


def _sheets(project):
    """[(id, title, sheet dict)] of the advisor sheets, in order."""
    out = []
    for sid in store.sheet_ids(project):
        sh = store.load_sheet(project, sid)
        out.append((sid, str(sh.get("title") or sid), sh))
    return out


def _sch_name(sid, title):
    return f"{sid} {_file_name(title, 'Sheet')}.SchDoc"


def _find_doc(prj_file, name_or_id, kind=".schdoc", bare=False, skip=()):
    """The project's document that belongs to a sheet id (its name starts with '<id> ') or has exactly that name. bare: only the one
    named by the bare id ('02.SchDoc'; _sheet_doc takes it only when this tool made it or it is empty). skip: lower-cased file names
    that another sheet owns: they are passed over and the search goes on."""
    summary = read_prjpcb(prj_file)
    for d in summary["documents"]:
        base = pathlib.PureWindowsPath(d).name
        if not base.lower().endswith(kind):
            continue
        if bare:
            hit = base[:-len(kind)].lower() == str(name_or_id).lower()
        else:
            hit = base.lower() == str(name_or_id).lower() or base.startswith(f"{name_or_id} ")
        if hit and base.lower() not in skip:
            return prj_file.parent / pathlib.Path(d.replace("\\", "/"))
    return None


def _fresh_doc(project, prj, sid, title, used=()):
    """The path of a SchDoc made for sheet `sid` ('<id> <title>.SchDoc'). It must be new: a file that exists, is a document of the
    project, or is the file of another sheet (the record, or `used` in this call) is an error, never overwritten or shared."""
    target = prj.parent / _sch_name(sid, title)
    low = target.name.lower()
    owner = [k for k, v in _logged_sheet_docs(project).items() if v.lower() == low and k != str(sid)]
    in_prj = {pathlib.PureWindowsPath(d).name.lower() for d in read_prjpcb(prj)["documents"]}
    if target.exists() or low in in_prj or low in {pathlib.Path(u).name.lower() for u in used} or owner:
        raise BridgeError(f"{target.name} is taken already" + (f" (it holds sheet {owner[0]})" if owner else "") + f", so sheet {sid} cannot "
                          "get a new file with that name. Nothing was changed: rename or remove that file in Altium, or give sheet "
                          f"{sid} another title.")
    return target


PLACEHOLDER_SHEET = "Main.SchDoc"       # the sheet new_project makes when no sheet is planned yet


def _logged_sheet_docs(project):
    """{sheet id: SchDoc file name} as recorded in altium-log.jsonl (store.sheet_docs)."""
    return store.sheet_docs(project)


def _blank_after_save(prj, doc):
    """Whether `doc` is an empty sheet once Altium's unsaved changes to it are saved: a hand drawing that is not saved yet counts. A
    save that fails is a 'no' (the sheet is then not taken over), never an error that stops the action."""
    from altium.schdoc import is_blank_sheet
    try:
        save_open_sheets(prj, [doc])
    except BridgeError:
        return False
    return is_blank_sheet(doc)


def _sheet_doc(project, prj, sid, taken=(), adopt=True, how=None):
    """The project SchDoc that holds advisor sheet `sid`, or None (a new one is made then): the one recorded for it (add_sheet,
    skeleton, draw), else the one named after it ('<id> ...'), else a bare '<id>.SchDoc' this tool made or that is empty, else the
    empty placeholder this tool made (Main.SchDoc, made when no sheet was planned yet) when no other sheet uses it: the first sheet is
    drawn on it instead of leaving it behind empty. A sheet that is taken over (a bare '<id>.SchDoc', the placeholder, or the file
    of a removed sheet of the same id) is saved first when Altium holds unsaved changes to it and is checked empty then; `how` (a
    list) gets "adopted", and the draw never wipes it. Only a candidate is saved. A recorded file that is no longer in the project
    (renamed or removed in Altium) is an error, never a reason to make a second copy of the sheet. `taken`: paths already given to
    another sheet in the same call; adopt=False: nothing is taken over or saved (the file that would hold the sheet, for reports)."""
    from altium.schdoc import is_blank_sheet
    sheets = read_prjpcb(prj)["sheets"]
    in_prj = {pathlib.PureWindowsPath(d).name.lower(): prj.parent / pathlib.Path(d.replace("\\", "/")) for d in sheets}
    logged = _logged_sheet_docs(project)
    claimed = {v.lower() for k, v in logged.items() if k != str(sid)}          # one file, one sheet: what another sheet is drawn on is not free
    claimed |= {pathlib.Path(t).name.lower() for t in taken}

    name = logged.get(str(sid))
    if name:
        if name.lower() in claimed:
            raise BridgeError(f"Sheet {sid} and another sheet are both recorded on {name}. Nothing was changed: one file holds one sheet; "
                              "give one of them its own file (rename the sheet's file in Altium to start with its id).")
        if name.lower() in in_prj:
            return in_prj[name.lower()]
        moved = _find_doc(prj, sid, skip=claimed)          # renamed in Altium to a name that starts with the sheet id: that file holds it now
        if moved is not None:
            _log(project, "sheet-docs", sheet_docs={str(sid): moved.name}, was=name)
            return moved
        raise BridgeError(f"Sheet {sid} was drawn on {name}, which is no longer in the Altium project (renamed or removed there?). "
                          f"Nothing was changed, so that no second copy of sheet {sid} is made: put {name} back in the project, "
                          f"or give the sheet file that now holds it a name that starts with '{sid} ' (e.g. '{sid} <title>.SchDoc').")
    def take(doc):
        if how is not None:
            how.append("adopted")
        return doc

    doc = _find_doc(prj, sid, skip=claimed)
    if doc is not None:
        if not adopt or str(sid) not in store.sheet_docs_reset(project):
            return doc
        if doc.is_file() and _blank_after_save(prj, doc):      # the file of a removed sheet with this id: only when empty
            return take(doc)
        raise BridgeError(f"{doc.name} belongs to an earlier sheet {sid} that was removed, and it still holds a drawing. Nothing was "
                          f"changed: rename or remove {doc.name} in Altium (it is not wiped for the new sheet {sid}).")
    made = _tool_made_sheets(project)
    doc = _find_doc(prj, sid, bare=True, skip=claimed)       # a plan sheet whose id is the file's name owns that file before the placeholder rule below
    if doc is not None and doc.is_file():
        if not adopt:
            if doc.name.lower() in made or is_blank_sheet(doc):
                return doc
        elif _blank_after_save(prj, doc) or doc.name.lower() in made:
            return take(doc)                             # never wiped: a drawing on it stops the draw
    ph = in_prj.get(PLACEHOLDER_SHEET.lower())
    if not adopt or ph is None or ph in taken or not ph.is_file() or PLACEHOLDER_SHEET.lower() not in made:
        return None
    if PLACEHOLDER_SHEET.lower() in claimed:
        return None                                      # another sheet is drawn on it
    stem = PLACEHOLDER_SHEET[:-len(".SchDoc")].lower()
    if any(str(o).lower() == stem for o in store.sheet_ids(project) if str(o) != str(sid)):
        return None                                      # a planned sheet is named after it (id Main): that sheet owns it, not the first other sheet
    if not _blank_after_save(prj, ph):
        return None
    return take(ph)


def _doc_key(prj, rel):
    """A PrjPcb DocumentPath as one comparable string: relative to the PrjPcb folder, slashes and case ignored. A PrjPcb holds
    Altium (Windows) paths, so case is ignored on every host: os.path.normcase alone keeps the case off Windows."""
    return os.path.normcase(os.path.normpath(str(prj.parent / pathlib.Path(str(rel).replace("\\", "/"))))).casefold()


def intlib_in_project(prj, intlib):
    """True when the PrjPcb file lists the IntLib as one of its documents (a project library)."""
    want = _doc_key(prj, intlib)
    return any(_doc_key(prj, d) == want for d in read_prjpcb(prj)["documents"])


def add_intlib_to_project(prj, intlib):
    """Make the IntLib a document of the Altium project. Altium's installed-libraries list does not feed the schematic ECO
    (Update PCB says Footprint Not Found); a project library does. Idempotent. Returns True when the saved PrjPcb lists it."""
    prj, intlib = pathlib.Path(prj), pathlib.Path(intlib)
    try:
        if not intlib.is_file() or not prj.is_file():
            return False
        if not intlib_in_project(prj, intlib):
            run_commands([("PROJECT", str(prj)), ("ADDDOC", str(prj), str(intlib)), ("SAVEPRJ", str(prj))])
        return intlib_in_project(prj, intlib)
    except (BridgeError, AltiumReadError, OSError, ValueError):
        return False


def ensure_sheets_in_project(prj, files):
    """Every SchDoc in `files` must be a document of the saved PrjPcb. Altium's own add can miss a new sheet (it lands in the project
    that has the focus), so a missing one is added by hand once (ADDDOC + SAVEPRJ) and the PrjPcb read again; a sheet still missing
    then is an error that names it. Returns the files that had to be added by hand."""
    prj = pathlib.Path(prj)
    files = [pathlib.Path(f) for f in files]

    def missing():
        have = {_doc_key(prj, d) for d in read_prjpcb(prj)["documents"]}
        return [f for f in files if _doc_key(prj, f) not in have]

    lost = missing()
    if lost:
        cmds = [("PROJECT", str(prj))] + [("ADDDOC", str(prj), str(f)) for f in lost if f.is_file()] + [("SAVEPRJ", str(prj))]
        run_commands(cmds)
        still = missing()
        if still:
            raise BridgeError(f"The sheet file(s) {', '.join(f.name for f in still)} are not in the Altium project {prj.name} "
                              "(Altium did not add them). Add them by hand: right-click the project > Add Existing to Project, then File > Save All.")
    return lost


def new_project(project):
    """Create the Altium project for an advisor project: PrjPcb, one PcbDoc, one SchDoc per sheet. Links it."""
    meta = project_mod.load_meta(project)
    name = _file_name(meta.get("title") or project, _file_name(project, "Project"))
    folder = altium_base() / name
    if folder.is_dir() and any(f.suffix.lower() == ".prjpcb" for f in folder.iterdir()):
        raise BridgeError(f"{folder} already holds an Altium project; I never overwrite one. Link it instead.")
    sheets = _sheets(project)
    sch_files = [_sch_name(sid, title) for sid, title, _ in sheets] or ["Main.SchDoc"]
    prj = folder / f"{name}.PrjPcb"
    pcb = folder / f"{name}.PcbDoc"
    folder.mkdir(parents=True, exist_ok=True)
    prj.write_bytes(MIN_PRJPCB.encode("ascii"))
    cmds = [("PROJECT", str(prj))]
    cmds += [("SCH", str(folder / f)) for f in sch_files]
    cmds += [("PCB", str(pcb)), ("SAVEPRJ", str(prj))]
    run_commands(cmds)
    ensure_sheets_in_project(prj, [folder / f for f in sch_files])
    summary = read_prjpcb(prj)
    if not pcb.is_file() or len(summary["sheets"]) != len(sch_files):
        raise BridgeError("Altium ran the script but the project does not list all its documents: "
                          f"{summary['documents']}. Check Altium for a dialog box.")
    project_mod.set_altium_link(project, project_file=str(prj), pcb_file=str(pcb))
    intlib = library_paths(project)["intlib"]
    lib_in = add_intlib_to_project(prj, intlib) if intlib.is_file() else None      # a library built before the project existed
    if lib_in:
        summary = read_prjpcb(prj)
    _log(project, "new-project", project_file=str(prj), documents=summary["documents"], library_in_project=lib_in)
    return {"project_file": str(prj), "pcb_file": str(pcb), "documents": summary["documents"]}


def _planned_sheet(project, name):
    """(id, title, by_title) of the advisor sheet `name` means: by its id ('02', '02 Logic', '02 Logic.SchDoc'; by_title False) or,
    when no id matches, by its title alone (by_title True; a title two sheets share is an error asking for the id). None: no plan sheet."""
    key = str(name or "").strip().lower()
    if not key:
        return None
    sheets = _sheets(project)
    for sid, title, _sh in sheets:
        if key in (str(sid).lower(), f"{sid} {title}".lower(), _sch_name(sid, title).lower()):
            return sid, title, False
    by_title = [(sid, title) for sid, title, _sh in sheets if str(title).lower() == key]
    if len(by_title) > 1:
        raise BridgeError(f"'{name}' is the title of sheets {', '.join(s for s, _ in by_title)}: name the sheet by its id. Nothing was added.")
    return (by_title[0][0], by_title[0][1], True) if by_title else None


def add_sheet(project, name):
    """A new SchDoc in the Altium project. A planned sheet (named by its id or title) gets the file the draw and skeleton steps use
    for it: the empty Main.SchDoc the project started with when no sheet uses it yet, else <id> <title>.SchDoc; when it has a file
    already nothing is made (by its id: that file is returned; by its title alone: an error that names the file). No empty look-alike
    is left next to the drawn sheet. The file is recorded for the sheet (sheet_docs)."""
    prj = _linked(project)
    planned = _planned_sheet(project, name)
    if planned:
        sid, title, by_title = planned
        how = []
        have = _sheet_doc(project, prj, sid, how=how)
        if have is not None and not how:
            if by_title:
                raise BridgeError(f"'{name}' is the title of planned sheet {sid}, which has its file already ({have.name}); nothing was "
                                  "added. Give a separate sheet another name, or name the planned sheet by its id.")
            return {"file": str(have), "backup": "", "existing": True}
        if have is not None:              # the empty Main.SchDoc: this sheet's file from now on, nothing new is made
            _log(project, "add-sheet", file=str(have), adopted=True, sheet_docs={sid: have.name})
            return {"file": str(have), "backup": "", "adopted": True}
        name = _sch_name(sid, title)
    fname = _file_name(name, "Sheet")
    fname = fname if fname.lower().endswith(".schdoc") else fname + ".SchDoc"
    target = prj.parent / fname
    if target.exists() or fname.lower() in {v.lower() for v in _logged_sheet_docs(project).values()}:
        raise BridgeError(f"{fname} already exists in the Altium project.")
    backup = _backup(prj, [prj])
    run_commands([("PROJECT", str(prj)), ("SCH", str(target)), ("SAVEPRJ", str(prj))])
    if not target.is_file():
        raise BridgeError("Altium ran the script but did not write the sheet. Check Altium for a dialog box.")
    ensure_sheets_in_project(prj, [target])
    _log(project, "add-sheet", file=str(target), backup=backup, **({"sheet_docs": {planned[0]: target.name}} if planned else {}))
    return {"file": str(target), "backup": backup}


def add_pcb(project):
    prj = _linked(project)
    n = len(read_prjpcb(prj)["pcbs"])
    target = prj.parent / (f"{prj.stem}.PcbDoc" if n == 0 else f"{prj.stem} {n + 1}.PcbDoc")
    if target.exists():
        raise BridgeError(f"{target.name} already exists.")
    backup = _backup(prj, [prj])
    run_commands([("PROJECT", str(prj)), ("PCB", str(target)), ("SAVEPRJ", str(prj))])
    if not target.is_file():
        raise BridgeError("Altium ran the script but did not write the PCB. Check Altium for a dialog box.")
    if not project_mod.altium_link(project).get("pcb_file"):
        project_mod.set_altium_link(project, project_file=str(prj), pcb_file=str(target))
    _log(project, "add-pcb", file=str(target), backup=backup)
    return {"file": str(target), "backup": backup}


# ---------------------------------------------------------------- the skeleton

def _clip(items, limit):
    text = ", ".join(items)
    return text if len(text) <= limit else text[:limit].rsplit(",", 1)[0] + ", ..."


def section_frames(sheet):
    """[(heading, [lines])] one per planned section: the refs and nets that belong there."""
    parts = [p for p in sheet.get("parts", []) if isinstance(p, dict) and p.get("ref")]
    sections = [s for s in sheet.get("sections", []) if isinstance(s, dict) and s.get("id")]
    if not sections:
        sections = [{"id": "", "title": "All parts"}]
    first = sections[0]["id"]
    ids = {s["id"] for s in sections}
    out = []
    for s in sections:
        mine = [p for p in parts if (p.get("section") if p.get("section") in ids else first) == s["id"]]
        nets = []
        for p in mine:
            for pin in p.get("pins", []):
                n = (pin.get("net") or "").strip() if isinstance(pin, dict) else ""
                if n and n.upper() != "NC" and n not in nets:     # NC marks an unconnected pin, not a net
                    nets.append(n)
        head = f"{s['id']} - {s.get('title') or ''}".strip(" -") if s["id"] else str(s.get("title") or "")
        out.append((head, [f"Parts: {_clip([str(p['ref']) for p in mine], 300) or '(none yet)'}",
                           f"Nets: {_clip(nets, 300) or '(none yet)'}"]))
    return out


def skeleton_commands(path, sheet_title, project_title, author, frames):
    """The script lines that (re)draw one sheet's skeleton. Frames made earlier are removed first (they carry TAG)."""
    p = str(path)
    cmds = [("CLEAR", p), ("TITLEBLOCK", p), ("PARAM", p, "Title", sheet_title), ("PARAM", p, "ProjectName", project_title)]
    if author:
        cmds.append(("PARAM", p, "Author", author))
    cols = 2 if len(frames) <= 6 else 3
    rows = max(1, math.ceil(len(frames) / cols))
    gap, left, top = 200, 500, 7000                      # mils, on an A4 sheet (11500 x 7600 drawing area)
    w = (10500 - gap * (cols - 1)) // cols
    h = min(2200, (6200 - gap * (rows - 1)) // rows)
    for i, (head, lines) in enumerate(frames):
        r, c = divmod(i, cols)
        x, y = left + c * (w + gap), top - (r + 1) * h - r * gap
        text = "\\n".join([f"{TAG} {head}"] + lines)
        cmds.append(("FRAME", p, str(x), str(y), str(w), str(h), text))
    cmds.append(("SAVE", p))
    return cmds


def skeleton(project, sheet=None):
    """Title block, parameters and one text frame per planned section on each SchDoc. No components. Safe to repeat."""
    prj = _linked(project)
    meta = project_mod.load_meta(project)
    ptitle = str(meta.get("title") or project)
    author = str(workspace.get("user.name", "") or "")
    planned = _sheets(project)
    if sheet is not None:
        planned = [s for s in planned if s[0] == str(sheet)]
        if not planned:
            raise BridgeError(f"No sheet {sheet} in this project.")
    cmds, todo, existing, new_docs, sheet_docs = [("PROJECT", str(prj))], [], [], [], {}
    if planned:
        for sid, title, sh in planned:
            doc = _sheet_doc(project, prj, sid, taken=existing)
            if doc is None:
                doc = _fresh_doc(project, prj, sid, title, existing + new_docs)
                new_docs.append(doc)
            else:
                existing.append(doc)
            sheet_docs[sid] = doc.name
            todo.append((doc, title, section_frames(sh)))
    else:
        doc = _find_doc(prj, "Main.SchDoc")
        if doc is None and read_prjpcb(prj)["sheets"]:
            doc = prj.parent / pathlib.Path(read_prjpcb(prj)["sheets"][0].replace("\\", "/"))
        if doc is None:
            doc = prj.parent / "Main.SchDoc"
            new_docs.append(doc)
        else:
            existing.append(doc)
        todo.append((doc, ptitle, [("No sheets planned yet", ["Parts: (none yet)", "Nets: (none yet)"])]))
    backup = _backup(prj, existing + ([prj] if new_docs else []))
    cmds += [("SCH", str(d)) for d in new_docs]
    for doc, title, frames in todo:
        cmds += skeleton_commands(doc, title, ptitle, author, frames)
    if new_docs:
        cmds.append(("SAVEPRJ", str(prj)))
    run_commands(cmds)
    _log(project, "skeleton", sheets=[str(d) for d, _, _ in todo], created=[str(d) for d in new_docs], backup=backup, sheet_docs=sheet_docs)
    return {"sheets": [str(d) for d, _, _ in todo], "created": [str(d) for d in new_docs], "backup": backup}


# ---------------------------------------------------------------- drawing the schematic

DRAWN_KINDS = ("components", "wires", "net_labels", "power_ports", "ports", "junctions", "no_erc")   # what a redraw wipes


def _sheet_symbols(project, sheet, lib_symbols):
    """{ref: library symbol dict} for the parts of one netlist sheet: BOM line -> library manifest -> the SchLib's symbol."""
    manifest = store.library_manifest(project)
    key = {r: l["key"] for l in store.bom_lines(project) for r in (l.get("refs") or [l["key"]])}
    out = {}
    for part in sheet.get("parts", []):
        ref = part.get("ref")
        sym = (manifest.get(key.get(ref)) or {}).get("symbol")
        if sym and sym in lib_symbols:
            out[ref] = lib_symbols[sym]
    return out


def circular_pin_warnings(project, refs):
    """One warning per ref whose library symbol was generated from the netlist itself and whose pins no datasheet pin table
    verified (and no student accepted): the draw step's comparison of netlist and symbol is then the netlist against itself."""
    manifest = store.library_manifest(project)
    out = []
    for line in store.bom(project, write=False):
        if not set(line.get("refs") or []) & set(refs) or line.get("pins_status") in ("verified", "accepted", ""):
            continue
        if partlib.symbol_from_netlist(manifest.get(line["key"])):
            out.append(f"{', '.join(r for r in line['refs'] if r in refs)}: pins UNVERIFIED: the symbol was generated from the netlist, "
                       "so matching the netlist against it proves nothing; only the datasheet's pin table (verify_part) or the student's accept does")
    return out


class AliasError(BridgeError):
    """The drawn net names clash: nothing that depends on the nets can be trusted until the student renames one net."""


def drawn_names(project, extra=()):
    """{net: drawn name} of the project (draw.alias_map), a BridgeError instead of the conflict."""
    from altium import draw
    try:
        return draw.alias_map(project, extra)
    except draw.AliasConflict as exc:
        raise AliasError(f"Net names clash after the schematic's plain-ASCII renaming: {exc}. Nothing was changed.") from exc


def _file_sig(path):
    try:
        st = pathlib.Path(path).stat()
        return st.st_mtime_ns, st.st_size
    except OSError:
        return None


SAVE_BY_HAND = ("In Altium click that sheet's tab, press Ctrl+S (or close the sheet and answer Yes to Save), then ask me to draw again. "
                "Nothing was changed.")


def save_open_sheets(prj, docs):
    """Saves the sheets Altium holds open with unsaved changes (the student's own edits: nothing is lost, the backup that follows
    then covers them). Returns the file names saved. A sheet that is closed or clean is left alone. A save that did not happen (the
    file is unchanged, or Altium still reports unsaved changes) is an error, before anything else is done."""
    state = run_commands([("PROJECT", str(prj))] + [("DOCSTATE", str(d)) for d in docs])
    states = [l for l in state if l.startswith("docstate ")]
    dirty = [d for d, l in zip(docs, states) if "modified=1" in l] if len(states) == len(docs) else []
    if not dirty:
        return []
    before = {d: _file_sig(d) for d in dirty}
    run_commands([("PROJECT", str(prj))] + [("SAVE", str(d)) for d in dirty])
    again = run_commands([("PROJECT", str(prj))] + [("DOCSTATE", str(d)) for d in dirty])
    still = [d for d, l in zip(dirty, [l for l in again if l.startswith("docstate ")]) if "modified=1" in l]
    unchanged = [d for d in dirty if _file_sig(d) == before[d]]
    if still or unchanged:
        names = ", ".join(d.name for d in (still or unchanged))
        raise BridgeError(f"I tried to save {names} in Altium but the save did not happen. " + SAVE_BY_HAND)
    return [d.name for d in dirty]


def refuse_footprint_errors(project, refs, what):
    """Fail closed: a part whose library footprint has converter errors (store.footprint_errors) is not placed on the board (what="place").
    One message names every such part, what is wrong and how to fix it. Nothing has been changed when this raises. The draw does not call
    this any more: the schematic carries no copper, so such a part is drawn with its real symbol and listed (draw_schematic)."""
    msg = store.footprint_error_text(store.footprint_error_parts(project, refs=set(refs)), f"Cannot {what}")
    if msg:
        raise BridgeError(msg + " Nothing was changed.")


def draft_library_path(project):
    """The SchLib the placeholder symbols of a draft draw live in: next to the project library, never inside it (the library build
    starts from the template and verify_library_files refuses a symbol that is not ours)."""
    lp = library_paths(project)
    return lp["folder"] / f"{lp['name']}-Draft.SchLib"


def _project_symbols(lp):
    """({symbol name: symbol} of the project SchLib, why it has none): a SchLib that is missing or cannot be read gives no symbols (every
    part is then drawn as a placeholder), never an error."""
    if not lp["schlib"].is_file():
        return {}, "the project library is not built yet"
    try:
        return {s["name"]: s for s in read_schlib(lp["schlib"])["symbols"]}, ""
    except Exception as exc:                  # noqa: BLE001  a broken file of any kind: the draft draw goes on without it
        return {}, f"the project library could not be read ({str(exc)[:80]})"


def _placeholder_reasons(sheet, symbols, lib_why):
    """{ref: {"why", "detail"}} of the parts of one netlist sheet that cannot be drawn from the project library: no symbol for the part
    (or no library), a symbol whose pins do not fit the netlist's, a symbol of several parts. {} = every part has a symbol that fits."""
    from altium import draw
    out = {}
    for part in sheet.get("parts", []):
        if not isinstance(part, dict) or not part.get("ref"):
            continue
        sym = symbols.get(part["ref"])
        if sym is None:
            out[part["ref"]] = {"why": draw.NO_SYMBOL, "detail": lib_why or "the library has no symbol for this part"}
            continue
        problems = draw.symbol_problems(part, sym)
        if problems:
            multi = all("several parts" in m for m in problems)
            out[part["ref"]] = {"why": draw.MULTI_SYMBOL if multi else draw.BAD_SYMBOL, "detail": problems[0]}
    return out


def _draft_close_args(path):
    return [str(path.with_suffix(e)) if e != ".SchLib" else str(path) for e in (".LibPkg", ".SchLib", ".PcbLib", ".IntLib")]


def draw_needs_library(project, sheet=None):
    """True when the draw would draw a part as a placeholder only because the library is OLDER than the design (a part with no symbol in a
    library that library_stale says is out of date): building the library first may give it a symbol. A library that is up to date, or
    none to read, or a part the build cannot give a symbol, is False. File checks only; never raises."""
    from altium import draw
    try:
        if not library_stale(project):
            return False
        symbols, _why = _project_symbols(library_paths(project))
        for sid, _t, sh in _sheets(project):
            if sheet is not None and sid != str(sheet):
                continue
            if any(r["why"] == draw.NO_SYMBOL for r in _placeholder_reasons(sh, _sheet_symbols(project, sh, symbols), "").values()):
                return True
    except Exception:                         # noqa: BLE001  a check that fails plans nothing: the draw then gives its own answer
        pass
    return False


def build_draft_library(project, items):
    """Make the draft SchLib holding `items` ({symbol name: draw.placeholder()}) through Altium, then read it back and compare every symbol
    (pins, comment, designator) with what was asked. Returns the file. A BridgeError names what differs; nothing is drawn from it then."""
    path = draft_library_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    run_commands([("LIBCLOSE", *_draft_close_args(path))])      # closes what is open, ignores what is not there
    _check_unlocked([path])
    shutil.copyfile(TEMPLATES / "Template.SchLib", path)
    work = store.pdir(project) / "draft-library"
    work.mkdir(parents=True, exist_ok=True)
    _write_ansi(work / "symbols_spec.txt", "\n".join([f"LIBRARY|{path}"] + [ln for it in items.values() for ln in it["spec"]]) + "\n")
    _write_ansi(work / "props.txt", "".join(it["props"] + "\n" for it in items.values()))
    run_commands([("SYMBATCH", str(path), str(work / "symbols_spec.txt")), ("SYMREMOVE", str(path), TEMPLATE_SYMBOL),
                  ("SYMPROPS", str(path), str(work / "props.txt")), ("SAVELIB", str(path), "SchLib")], stall_timeout=120, total_timeout=300)
    got = {s["name"]: s for s in read_schlib(path)["symbols"]}
    bad = [f"{n} is not in the draft library" for n in items if n not in got] + [f"{n} is not ours" for n in got if n not in items]
    for n, it in items.items():
        s = got.get(n)
        if s is None:
            continue
        want = sorted((p["number"], p["name"], "Passive") for p in it["symbol"]["pins"])
        if sorted((p["number"], p["name"], p["electrical"]) for p in s["pins"]) != want:
            bad.append(f"{n}: its pins differ ({len(s['pins'])} made, {len(want)} asked)")
        if s["comment"] != it["symbol"]["comment"] or s["designator"] != it["symbol"]["designator"]:
            bad.append(f"{n}: its comment or designator differs")
    if bad:
        raise BridgeError("The placeholder symbols could not be made in Altium: " + "; ".join(bad[:6]) + ". Nothing was drawn.")
    return path


def _close_draft_library(project):
    """Best effort: the draft SchLib is only read while the parts are placed; it is not left open in Altium."""
    try:
        run_commands([("LIBCLOSE", *_draft_close_args(draft_library_path(project)))])
    except (BridgeError, OSError):
        pass


def draw_schematic(project, sheet=None, replace=False):
    """Draw the netlist sheet(s) of the project in Altium: every part from the project SchLib, a wire stub on every connected pin
    ending in a power port or a net label, a No ERC cross on NC pins. Then the saved SchDoc is read back and compared with the netlist.
    Always a DRAFT when it has to be: a part the library has no symbol for (or none was built, or its symbol does not fit the
    netlist's pins) is drawn as a PLACEHOLDER, a rectangle with the netlist's own pins (draw.placeholder), every net still connected;
    the result and the log list them (`placeholders`), the sheet's heading says DRAFT, and store.manufacturing_warning blocks the
    outputs until a later draw has the real symbols. A part whose library footprint is in error is drawn with its symbol (the
    schematic carries no copper); the placement still refuses it. Refuses a sheet that already has components unless replace is true
    (the old SchDoc is copied to .advisor-backup first). The SchDoc comes from the PrjPcb (a new one is added when there is none)."""
    from altium import draw
    from altium.schdoc import read_schdoc
    prj = _linked(project)
    lp = library_paths(project)
    planned = _sheets(project)
    if sheet is not None:
        planned = [s for s in planned if s[0] == str(sheet)]
    if not planned:
        raise Fixable("prereq.no_netlist", "There is no netlist sheet to draw" + (f" (no sheet {sheet})" if sheet is not None else "")
                      + ": write the netlist first (netlist.write).")
    all_refs = {p.get("ref") for _s, _t, sh in planned for p in sh.get("parts", []) if isinstance(p, dict)}
    fp_bad = {r: i["footprint"] for i in store.footprint_error_parts(project, refs=all_refs) for r in i["refs"]}
    bom_refs = {r for l in store.bom_lines(project) for r in (l.get("refs") or [l["key"]])}
    lib_symbols, lib_why = _project_symbols(lp)
    manifest = store.library_manifest(project)
    key = {r: l["key"] for l in store.bom_lines(project) for r in (l.get("refs") or [l["key"]])}
    plans, existing, new_docs, adopted = [], [], [], set()
    draft_items, draft_names = {}, set()
    # one drawn name per net for the whole design (a net on two sheets keeps one name; two names never share one)
    aliases = drawn_names(project)
    for sid, title, sh in planned:
        errors, _ = store.check_sheet(sh, bom_refs)
        if errors:
            raise BridgeError(f"Sheet {sid} cannot be drawn: " + "; ".join(errors[:6]))
        how = []
        doc = _sheet_doc(project, prj, sid, taken=existing, how=how)
        if how:
            adopted.add(doc)
        if doc is None:
            doc = _fresh_doc(project, prj, sid, title, existing + new_docs)
            new_docs.append(doc)
        elif doc.is_file():
            existing.append(doc)
            have = sum(len(read_schdoc(doc).get(k, [])) for k in DRAWN_KINDS)
            if have and not replace:
                raise BridgeError(f"{doc.name} already has {have} objects (parts, wires, labels). I never wipe a drawing: say so if it "
                                  "should be redrawn (replace), the old file is kept in .advisor-backup.")
        syms = _sheet_symbols(project, sh, lib_symbols)
        phs = _placeholder_reasons(sh, syms, lib_why)
        by_ref = {p.get("ref"): p for p in sh.get("parts", []) if isinstance(p, dict)}
        for ref, ph in phs.items():
            name, n = draw.placeholder_name(ref), 1
            while name in draft_names:
                n += 1
                name = f"{draw.placeholder_name(ref)}_{n}"
            draft_names.add(name)
            ph["name"], ph["schlib"], ph["sheet"] = name, str(draft_library_path(project)), sid
            draft_items[name] = draw.placeholder(by_ref[ref], ph["why"], name)
        plan = draw.plan_sheet(sh, syms, lp["schlib"], doc, replace=replace and doc not in adopted,
                               aliases=aliases, placeholders=phs)      # a sheet taken over as empty is never wiped: anything on it stops the draw
        if plan["errors"]:
            msg = f"Sheet {sid} cannot be drawn: " + "; ".join(plan["errors"][:8])
            raise Fixable(plan["fix_code"], msg) if plan.get("fix_code") in NEUTRAL_CODES else BridgeError(msg)
        plan["draft"] = [{"sheet": sid, "ref": r, "why": ph["why"], "detail": ph["detail"]} for r, ph in phs.items()]
        # a footprint link is checked on the sheet only for a part that has one: a placeholder has none, and a footprint in error was never
        # written to the PcbLib (the part's schematic symbol is fine; the placement refuses it)
        plans.append((sid, doc, plan, {r: (None if r in phs or r in fp_bad else (manifest.get(key.get(r)) or {}).get("footprint")) for r in key}))
    saved_first = save_open_sheets(prj, existing) if existing else []      # before the backup, so the backup holds the student's latest edits
    backup = _backup(prj, existing + ([prj] if new_docs else []))
    if existing:        # Altium's own view first: anything on the sheet stops the run before it touches anything
        try:
            run_commands([("PROJECT", str(prj))] + [("DRAWCHECK", str(d), "1" if replace and d not in adopted else "0") for d in existing])
        except BridgeError as exc:
            if "unsaved changes" in str(exc):
                raise BridgeError((f"I saved {', '.join(saved_first)}, but Altium reports new unsaved changes in a sheet. "
                                   if saved_first else "A sheet is open in Altium with unsaved changes that could not be saved from here. ")
                                  + SAVE_BY_HAND) from exc
            raise
    if draft_items:        # the placeholder symbols are made and read back before anything is drawn
        build_draft_library(project, draft_items)
    cmds = [("PROJECT", str(prj))] + [("SCH", str(d)) for d in new_docs]
    titles = {sid: title for sid, title, _ in planned}
    for sid, doc, plan, _fp in plans:
        pc = list(plan["commands"])
        if doc.name.lower() == PLACEHOLDER_SHEET.lower() and pc:      # the empty sheet the project started with, drawn on: its title block
            pc[1:1] = [("PARAM", str(doc), "Title", titles.get(sid, sid))]      # gets the sheet's title, not the project's
        cmds += pc
    if new_docs:
        cmds.append(("SAVEPRJ", str(prj)))
    try:
        run_commands(cmds, total_timeout=900)
    except BridgeError as exc:
        # a half-drawn sheet must not be saveable by the student: close it without saving (the file on disk is still the old one)
        closed = ""
        try:
            run_commands([("PROJECT", str(prj))] + [("REVERT", str(d)) for _, d, _, _ in plans])
            closed = " The unfinished sheet was closed in Altium without saving; the file on disk is as it was."
        except BridgeError:
            closed = " Close the sheet in Altium WITHOUT saving: it is half drawn."
        raise BridgeError(str(exc) + closed) from exc
    finally:
        if draft_items:
            _close_draft_library(project)
    # the sheets are in the Altium project now: their files are recorded before anything below can fail, so a later run never
    # makes a second copy of a sheet whose check broke off
    _log(project, "sheet-docs", sheet_docs={sid: d.name for sid, d, _, _ in plans}, created=[str(d) for d in new_docs])
    if new_docs:
        ensure_sheets_in_project(prj, new_docs)      # every new sheet, not only the first one, must be in the saved project
    problems, warnings, parts, nets = [], [], 0, set()
    for sid, doc, plan, fps in plans:
        warnings += plan["warnings"] + circular_pin_warnings(project, [p["ref"] for p in plan["parts"] if isinstance(p, dict) and p.get("ref")])
        parts += len(plan["parts"])
        nets |= set(plan["expected"])
        try:
            saved = read_schdoc(doc)
        except (AltiumReadError, OSError) as exc:
            problems.append(f"sheet {sid}: the saved SchDoc could not be read back: {exc}")
            continue
        problems += [f"sheet {sid}: {m}" for m in draw.verify_sheet(plan, saved, fps)]
        if str(sid).strip():
            from checks.schematic import check_schematic
            found = [f for f in check_schematic(doc)["findings"] if f.get("severity") == "error"]
            problems += [f"sheet {sid}: {f['message']}" for f in found[:5]]
    draft = {sid: [{"ref": x["ref"], "why": x["why"], "detail": x["detail"]} for x in plan["draft"]] for sid, _d, plan, _fp in plans}
    drafted = [x for _sid, _d, plan, _fp in plans for x in plan["draft"]]
    fp_listed = sorted(p["ref"] for _sid, _d, plan, _fp in plans for p in plan["parts"] if p["ref"] in fp_bad)
    if fp_listed:
        warnings.append(f"{', '.join(fp_listed[:12])}: the library footprint is in error, so the part has no footprint to place yet "
                        "(drawn with its symbol; fix the footprint and build the library)")
    _log(project, "draw-schematic", sheets=[str(d) for _, d, _, _ in plans], parts=parts, nets=len(nets), replace=bool(replace),
         created=[str(d) for d in new_docs], backup=backup, problems=problems, warnings=warnings,
         sheet_docs={sid: d.name for sid, d, _, _ in plans}, draft=draft, footprint_errors=fp_listed)
    if saved_first:
        warnings.insert(0, f"saved {', '.join(saved_first)} before drawing (it had unsaved changes in Altium)")
    renamed = {n: a for _, _, plan, _ in plans for n, a in plan.get("renamed", {}).items()}
    res = {"sheets": [str(d) for _, d, _, _ in plans], "parts": parts, "nets": sorted(nets), "warnings": warnings,
           "problems": problems, "backup": backup, "created": [str(d) for d in new_docs], "saved_first": saved_first,
           "renamed_nets": renamed, "placeholders": drafted, "footprint_errors": fp_listed}
    if not problems:
        res["stale"] = remove_stale_sheets(project, prj)
        res["warnings"] += [f"{x['name']} was left in the project: {x['why']}" for x in res["stale"]["left"] if x["name"]]
    if problems:
        raise BridgeError(f"Drawn and saved {parts} parts, but the sheet does not match the netlist: " + "; ".join(problems[:6])
                          + (f" (+{len(problems) - 6} more)" if len(problems) > 6 else ""))
    return res


def _tool_made_sheets(project):
    """Lower-cased file names of the SchDocs this tool created for the project (altium-log.jsonl: new-project, add-sheet, skeleton,
    draw-schematic)."""
    out = set()
    for e in store.read_jsonl(store.pdir(project) / "altium-log.jsonl"):
        names = list(e.get("created") or []) + list(e.get("documents") or []) + ([e["file"]] if e.get("file") else [])
        out |= {pathlib.PureWindowsPath(str(n)).name.lower() for n in names if str(n).lower().endswith(".schdoc")}
    return out


def remove_stale_sheets(project, prj):
    """After a draw: REPORT (never remove) the SchDocs of the project that this tool created, that no sheet of the design uses any
    more (a placeholder such as Main.SchDoc, or a sheet renamed when the netlist was split) and that hold nothing of a design.
    Removal through Altium's script API was tried on a live project and left duplicate [Document] sections in the PrjPcb, and the
    bridge cannot close and reload a project, so the tool does not touch the project's document list or any file. The student
    removes them in Altium (right-click > Remove from Project). A sheet with content, or one the student made, is not named at all.
    Returns {"removed": [] (always), "left": [{"name", "why"}]}; never raises."""
    from altium.schdoc import is_blank_sheet
    res = {"removed": [], "left": []}
    try:
        keep = {_sheet_doc(project, prj, sid, adopt=False) for sid, _t, _s in _sheets(project)}
        keep = {os.path.normcase(str(d)) for d in keep if d}
        made = _tool_made_sheets(project)
        for d in read_prjpcb(prj)["sheets"]:
            doc = prj.parent / pathlib.Path(d.replace("\\", "/"))
            if os.path.normcase(str(doc)) in keep or doc.name.lower() not in made or not doc.is_file():
                continue
            if is_blank_sheet(doc):
                res["left"].append({"name": doc.name, "why": "it is empty and no sheet of the design uses it any more; remove it in Altium "
                                                             "(right-click it in the Projects panel > Remove from Project)"})
    except (BridgeError, AltiumReadError, OSError, ValueError) as exc:
        res["left"].append({"name": "", "why": f"the empty leftover sheets could not be checked: {exc}"})
    return res


# ---------------------------------------------------------------- placing the parts on the PCB

NEW_BOARD_BOX_MIL = (1000, 1000, 7000, 5000)       # the outline a new PcbDoc starts with: a placeholder, not a drawn board
MM_PER_MIL = 0.0254


def _pcbcheck_info(log):
    """What the PCBCHECK step logged: {objects, parts, tracks, points, box_mil (x0, y0, x1, y1)} (None when it did not log)."""
    for line in reversed(log):
        if line.startswith("pcbcheck "):
            kv = dict(re.findall(r"(\w+)=(\S+)", line))
            try:
                box = tuple(int(v) for v in kv["box_mil"].split(","))
                pts = int(kv["outline_pts"])
                # rect=1: the four points are an axis aligned rectangle (the Pascal side checks the corners); a log without the
                # flag (older script) can only say how many points there are
                return {"objects": int(kv["objects"]), "parts": int(kv["parts"]), "tracks": int(kv["tracks"]),
                        "points": pts, "box_mil": box, "rect": (kv["rect"] == "1") if "rect" in kv else pts == 4}
            except (KeyError, ValueError):
                return None
    return None


def parse_drc(path):
    """The batch design rule check text report: {"rules": {rule text: count}, "violations": [message], "unrouted": n, "total": n,
    "complete": bool, "clean": bool}. The "Rule Violations|Total|N" line is not a rule: it is the report's own total. total is the sum
    of the rules; complete is True only when that Total line exists AND equals the sum (a truncated report fails this), at least one
    rule line was read, every "Rule Violations" line has a whole-number count, no rule is listed twice with different counts, and
    details do not appear under a zero total. clean = complete and total == 0: anything else is unchecked."""
    try:
        text = pathlib.Path(path).read_text(encoding="cp1252", errors="replace")
    except OSError:
        return None
    rules, violations = {}, []
    complete = True
    stated = None
    for line in text.splitlines():
        parts = line.split("|")
        if parts[0].startswith("Rule Violations"):
            if len(parts) == 3 and parts[1].strip() and parts[2].strip().isdigit():
                name, n = parts[1].strip(), int(parts[2])
                if name.lower() == "total":
                    if stated is not None and stated != n:
                        complete = False
                    stated = n
                    continue
                if rules.get(name, n) != n:
                    complete = False
                rules[name] = n
            else:
                complete = False                    # a rule line that cannot be read: its count is unknown
        elif len(parts) >= 4 and parts[1] == "" and parts[2] == "":
            violations.append(f"{parts[0].strip()}: {parts[3].strip()}")
    total = sum(rules.values())
    if not rules or stated is None or stated != total or (violations and total == 0):
        complete = False
    unrouted = sum(v for k, v in rules.items() if k.startswith("Un-Routed Net"))
    return {"rules": rules, "violations": violations, "unrouted": unrouted, "total": total,
            "complete": complete, "clean": bool(complete and total == 0)}


def drc_clean(res):
    """True only for a fully parsed report with no violation at all; a missing, partial or unknown-format report is never clean."""
    return bool(isinstance(res, dict) and res.get("complete") is True and res.get("total") == 0 and res.get("rules"))


def _drc_short(name):
    """"Clearance Constraint (Gap=0.127mm) (All),(All)" -> "Clearance": the rule's name without the values Altium appends."""
    return re.split(r" \(|:", name, maxsplit=1)[0].replace(" Constraint", "").strip()


def drc_line(res):
    """Every rule of the report with its violation count, absolute numbers ("Clearance 0, Width 0, Un-Routed Net 3, ... total 3"), or
    "unchecked" when the report is missing or was not read in full."""
    if not isinstance(res, dict) or not res.get("rules"):
        return "unchecked (no readable design rule check report)"
    shown = {}                                   # two rules of one kind (other scope or value) are one name: their counts add up
    for k, v in res["rules"].items():
        shown[_drc_short(k)] = shown.get(_drc_short(k), 0) + v
    body = ", ".join(f"{k} {v}" for k, v in shown.items())
    if not res.get("complete"):
        return f"unchecked (the report was not read in full; read so far: {body}, total {res.get('total', 0)})"
    return f"{body}, total {res['total']}" + (" (clean)" if drc_clean(res) else "")


def _netlist_parts(project):
    """[{ref, footprint, symbol, pins}] of every netlist sheet: the footprint and symbol come from the library manifest."""
    manifest = store.library_manifest(project)
    lines = {l["key"]: l for l in store.bom_lines(project)}
    key = {r: l["key"] for l in lines.values() for r in (l.get("refs") or [l["key"]])}
    parts, seen = [], set()
    for _sid, _title, sh in _sheets(project):
        for p in sh.get("parts", []):
            if not isinstance(p, dict) or not p.get("ref") or p["ref"] in seen:
                continue
            seen.add(p["ref"])
            m = manifest.get(key.get(p["ref"])) or {}
            line = lines.get(key.get(p["ref"])) or {}
            parts.append({"ref": p["ref"], "footprint": m.get("footprint") or "", "symbol": m.get("symbol") or "",
                          "lib_ref": m.get("symbol") or "", "pins": p.get("pins", []),
                          # the BOM line, for the placement rules (cap value, regulator, crystal); not "value": PLACEFP sets that into Altium
                          "bom_value": line.get("value") or "", "bom_description": line.get("description") or "",
                          "bom_role": line.get("role") or "",
                          # a radio module's antenna side (library manifest rf, a heuristic): the placer puts it at an edge, antenna out
                          "rf_antenna_deg": partlib_mech.rf_side_degrees(m.get("rf"))})
    from altium import draw
    return draw.alias_parts(parts, drawn_names(project))          # the pads carry the names the schematic was drawn with


def board_fit_check(project):
    """Early check of the board size against the BOM's parts (when the BOM is approved, before Place): the layout.board_fit result for
    one side of the board, or None when the project has no board size or no parts yet. The real footprints are used when the library
    is built, the package of each BOM line otherwise. Never changes anything and never raises."""
    from altium import layout
    try:
        size = _board_size(project)
        manifest = store.library_manifest(project)
        parts = []
        for line in store.bom_lines(project):
            for ref in line.get("refs") or []:
                parts.append({"ref": ref, "footprint": (manifest.get(line["key"]) or {}).get("footprint") or "",
                              "package": line.get("package") or "", "description": line.get("description") or ""})
        fps = {}
        try:
            pcblib = library_paths(project)["pcblib"]          # needs a linked Altium project; without one there is no library yet
            fps = {f["name"]: f for f in read_pcblib(pcblib)["footprints"]} if pcblib.is_file() else {}
        except (BridgeError, AltiumReadError, OSError, KeyError, ValueError):
            fps = {}
        fit = layout.board_fit(parts, size, fps)
        return dict(fit, size=size, text=layout.fit_text(fit, size)) if fit else None
    except Exception:                                    # an estimate must never stop a step
        return None


def _board_size(project):
    from altium import layout
    path = store.pdir(project) / "idea.json"
    try:
        idea = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        idea = {}
    return layout.board_size(idea)


def _clearance_mm(project):
    try:
        return float(project_mod.board(project).get("min_clearance_mm") or 0)
    except (TypeError, ValueError):
        return 0.0


def _revert(prj, pcb, what):
    try:
        run_commands([("PROJECT", str(prj)), ("REVERT", str(pcb))])
        return f" The unfinished board was closed in Altium without saving; the file on disk is as it was."
    except BridgeError:
        return f" Close the board in Altium WITHOUT saving: it is half {what}."


def _restore(prj, pcb, backup):
    """Put the backed-up PcbDoc back after a placement that did not verify: Altium closes the board without saving, then the file
    is copied back. True when the file on disk is the backup again."""
    saved = pathlib.Path(backup) / pathlib.Path(pcb).name
    if not saved.is_file():
        return False
    try:
        run_commands([("PROJECT", str(prj)), ("REVERT", str(pcb))])
    except BridgeError:
        pass
    try:
        shutil.copy2(saved, pcb)
    except OSError:
        return False
    return True


def _sch_links(prj):
    """{ref: (SchDoc unique id, sheet name)} of the components drawn in the project's SchDocs: what ECO stores in a placed part
    (SourceUniqueId, SourceHierarchicalPath) so that a later Update PCB finds the part instead of adding it twice."""
    out = {}
    try:
        for sh in read_prjpcb(prj)["sheets"]:
            path = pathlib.Path(sh) if pathlib.Path(sh).is_absolute() else pathlib.Path(prj).parent / sh
            if not path.is_file():
                continue
            for c in read_schdoc(path).get("components", []):
                if c.get("ref") and c.get("unique_id"):
                    out.setdefault(c["ref"], (c["unique_id"], path.stem))
    except Exception:                                    # no drawn schematic yet: the part is placed without the link
        pass
    return out


def _shape_differs(pcb, box):
    """The board shape Altium holds (BoardRegions) when it is not the rectangle `box` [x0, y0, x1, y1] mm, else None (also when it
    cannot be read: nothing is known to be wrong then)."""
    from altium.pcbdoc import board_shape_box
    try:
        shape = board_shape_box(pcb)
    except (AltiumReadError, OSError):
        return None
    return shape if shape and any(abs(a - b) > 0.1 for a, b in zip(shape, box)) else None


def _write_shape(pcb, box):
    """Write `box` as the board shape into the closed PcbDoc and read it back. "" when the file holds it now, else why not.
    Altium's scripting changes the outline corners only; the shape a pour is clipped to is a separate record that stays at the
    shape of a new board (T24), so it is written in the file (pcbdoc.set_board_shape)."""
    from altium.pcbdoc import board_shape_box, set_board_shape
    try:
        if not set_board_shape(pcb, box):
            return "the board shape record is not a plain rectangle"
        got = board_shape_box(pcb)
    except Exception as exc:        # noqa: BLE001 - an old olefile raises NotImplementedError; any failure falls back to the warning
        return f"the board shape could not be written ({exc})"
    if not got or any(abs(a - b) > 0.1 for a, b in zip(got, box)):
        return "the board shape written is not the one read back"
    return ""


def _fit_shape(prj, pcb, box):
    """After placing: make the board shape Altium holds the outline `box` (mm), closing the saved board first. "" when it is (or
    cannot be told to be anything else), else the reason it could not be set."""
    if _shape_differs(pcb, box) is None:
        return ""
    try:
        state = run_commands([("PROJECT", str(prj)), ("DOCSTATE", str(pcb))])
        if any(l.startswith("docstate open modified=1") for l in state):
            return "the board is open in Altium with unsaved changes"
        run_commands([("PROJECT", str(prj)), ("REVERT", str(pcb))])
    except BridgeError as exc:
        return str(exc)
    return _write_shape(pcb, box)


def _mechanical_parts(items, outline, fps, parts, refs_lines=None, size=None):
    """The mounting holes (H1..) and keep-outs (KO1..) of the student's confirmed constraints for a board outline, as extra parts to
    place, plus the placement rules the constraints give the planner. Returns (holes, keepouts, rules, warnings): holes and keepouts
    are part dicts {ref, footprint, pins: [], mech: "hole"|"keepout", x, y}; rules is layout.plan_placement's `rules`.
    A footprint the project library does not hold yet is a warning (build the library), never a silent skip."""
    import constraints
    refs, lines = refs_lines if refs_lines else (None, None)
    pl = constraints.plan_for_board(items, outline, refs, lines, size=size)
    warnings = list(pl["findings"])
    out = {"hole": [], "keepout": []}
    for kind, lst in (("hole", pl["holes"]), ("keepout", pl["keepouts"])):
        for m in lst:
            if m["footprint"] not in fps:
                warnings.append(f"constraint {m['item']}: the project library has no footprint {m['footprint']} yet, so the {kind} "
                                "was not placed: run library.build, then place again")
                continue
            out[kind].append({"ref": m["ref"], "footprint": m["footprint"], "symbol": "", "lib_ref": "", "pins": [], "mech": kind,
                              "x": m["x"], "y": m["y"], "rect": m.get("rect")})
    have = {p["ref"] for p in parts}
    rules = {"fixed": {h["ref"]: (h["x"], h["y"], 0) for h in out["hole"]}, "keepouts": [k["rect"] for k in out["keepout"]],
             "edge": {r: s for r, s in pl["edge"].items() if r in have}, "apart": [], "antenna": {}}
    for r in pl["edge"]:
        if r not in have:
            warnings.append(f"constraint: {r} is not in the netlist, so it was not put at an edge")
    for a, b, mm in pl["apart"]:
        if a in have and b in have:
            rules["apart"].append((a, b, mm))
        else:
            warnings.append(f"constraint: {a if a not in have else b} is not in the netlist, so the {mm:g} mm distance to it is not enforced")
    for p in parts:                      # a radio module (library manifest rf) goes to an edge with its antenna outwards
        if p.get("rf_antenna_deg") is not None:
            rules["antenna"][p["ref"]] = p["rf_antenna_deg"]
    return out["hole"], out["keepout"], rules, warnings


def _routing_lost(pcb):
    """{tracks, vias, pours} of copper on the saved PcbDoc: what a new placement deletes. {} when the file cannot be read (the
    caller then says it without numbers, never guesses them)."""
    from altium.pcbdoc import read_pcbdoc
    try:
        doc = read_pcbdoc(pathlib.Path(pcb))
    except Exception:          # only wording depends on this: a parse error (struct.error ...) must not abort the chat turn
        return {}
    cu = lambda it: isinstance(it.get("layer"), int) and 1 <= it["layer"] <= 32
    return {"tracks": sum(1 for t in doc.get("tracks", []) if cu(t)), "vias": len(doc.get("vias", [])),
            "pours": len(doc.get("polygons", []))}


def _routing_words(lost):
    """"12 tracks, 3 vias and 1 pour" for the counts of _routing_lost, '' when nothing is there or nothing is known."""
    bits = [f"{n} {w if n != 1 else w.rstrip('s')}" for w, n in (("tracks", lost.get("tracks", 0)), ("vias", lost.get("vias", 0)),
                                                                  ("pours", lost.get("pours", 0))) if n]
    return ", ".join(bits[:-1]) + (" and " if len(bits) > 1 else "") + bits[-1] if bits else ""


def place_on(prj, pcb, pcblib, parts, size=None, clearance_mm=0.0, replace=False, connector_dirs=None, edge_copper_mm=0.3,
             constraint_items=None, refs_lines=None):
    """Place `parts` ([{ref, footprint, lib_ref, pins}]) from the PcbLib on the PcbDoc, create the outline from `size` when the board
    only has the placeholder outline of a new PcbDoc (an outline somebody drew is kept), save, and read the file back.
    Refuses a board that already has parts or copper unless replace is true; the PcbDoc is copied to .advisor-backup first.
    Returns {"placed", "outline", "outline_created", "warnings", "backup", "problems", "drc"}; problems non-empty = placed but
    the saved file does not match the netlist."""
    from altium import layout
    from altium.pcbdoc import read_pcbdoc
    prj, pcb, pcblib = pathlib.Path(prj), pathlib.Path(pcb), pathlib.Path(pcblib)
    if not pcblib.is_file():
        raise Fixable("prereq.library_not_built", "The project library is not built yet: run library.build first, the footprints are placed from it.")
    if not parts:
        raise Fixable("prereq.no_netlist", "There are no parts in the netlist to place: write the netlist first (netlist.write).")
    bad = layout.text_problems(parts)
    if bad:
        raise BridgeError("; ".join(bad[:6]))
    fps = {f["name"]: f for f in read_pcblib(pcblib)["footprints"]}
    missing = sorted({p["ref"] for p in parts if p.get("footprint") not in fps})
    if missing:
        raise Fixable("prereq.library_not_built", f"No footprint in the project library for {', '.join(missing[:8])}: run library.build first.")
    lost = _routing_lost(pcb) if pathlib.Path(pcb).is_file() else {}
    routed = _routing_words(lost)
    try:
        log = run_commands([("PROJECT", str(prj)), ("PCBCHECK", str(pcb), "1" if replace else "0")])     # Altium's own view first
    except BridgeError as exc:
        if routed and re.search(r"the board already has \d+ parts or copper objects", str(exc)):
            # the refusal says what is lost, in numbers: the one confirm (Replace) is then an informed one
            said = re.sub(r"(the board already has \d+ parts or copper objects)",
                          rf"\1, among them routing of {routed} that placing again deletes", str(exc), count=1)
            raise BridgeError(said + ". Replacing deletes that routing and places every part anew; the student's own edits in "
                                     "Altium are lost with it (the board file is copied to a backup first).") from exc
        raise
    info = _pcbcheck_info(log)
    if info is None:
        raise BridgeError("Altium did not report the state of the board.")
    placeholder = info["box_mil"] == NEW_BOARD_BOX_MIL and info["points"] == 4 and info["parts"] == 0
    if info["box_mil"] == NEW_BOARD_BOX_MIL and info["points"] == 4 and info["parts"] > 0:
        raise BridgeError("The board has parts and an outline of exactly the size of a new board: I cannot tell whether that outline was "
                          "drawn on purpose. Ask the student whether it is the real board outline.")
    if not placeholder and not info["rect"]:
        raise BridgeError("The board outline is not a rectangle, so I cannot tell whether the parts fit inside it. Draw a rectangular "
                          "outline in Altium (or delete the outline so I create one from the board size) and try again.")
    warnings = []
    if replace and routed:
        warnings.append(f"Placing again deleted the routing of the board ({routed}); the earlier file is in the backup folder.")
    if placeholder:
        outline = layout.plan_outline(size)
        if outline is None:
            raise BridgeError("The board has no outline yet and the project does not say how big the board is (idea: board size). "
                              "Ask the student for the board width and height in mm (do not guess), record it with idea.update, or draw the outline in Altium first. Nothing was changed.")
        create = True
    else:
        outline = [round(v * MM_PER_MIL, 3) for v in info["box_mil"]]
        create = False
    # which way each connector opens: read from its footprint (a connector whose opening cannot be told is still warned about by the
    # planner); an explicit entry of the caller wins. Without this every connector got the "check the mating face" warning.
    derived = {p["ref"]: layout.opening_dir(fps[p["footprint"]]) for p in parts if layout.is_connector(p["ref"]) and p.get("footprint") in fps}
    connector_dirs = {**{r: d for r, d in derived.items() if d is not None}, **(connector_dirs or {})}
    holes, keepouts, rules, mech_warnings = _mechanical_parts(constraint_items or [], outline, fps, parts, refs_lines, size)
    plan = layout.plan_placement(parts + holes, fps, outline, clearance_mm=clearance_mm, connector_dirs=connector_dirs,
                                 edge_copper_mm=edge_copper_mm, rules=rules)
    if plan["errors"]:
        raise BridgeError("The parts cannot be placed: " + "; ".join(plan["errors"][:6]))
    warnings += mech_warnings + plan["warnings"]
    plan["places"] = plan["places"] + [{"ref": k["ref"], "footprint": k["footprint"], "x": k["x"], "y": k["y"], "rot": 0,
                                        "label": [k["x"], k["y"]], "label_h": layout.LABEL_H, "label_rot": 0} for k in keepouts]
    parts = parts + holes + keepouts
    backup = _backup(prj, [pcb])
    links = _sch_links(prj)
    parts = [dict(p, uid=links[p["ref"]][0], sheet=links[p["ref"]][1]) if p["ref"] in links else p for p in parts]
    try:                                                 # did somebody already draw the outline? (it is then never touched)
        before_tracks, before_arcs = layout.outline_layer_free(read_pcbdoc(pcb))
        had_drawing = bool(before_tracks or before_arcs)
    except (AltiumReadError, OSError):
        had_drawing = False
    cmds = layout.plan_commands(pcb, outline, create, plan["places"], fps, parts, pcblib, replace=replace, draw_outline=True)
    try:
        run_commands([("PROJECT", str(prj))] + cmds, total_timeout=900)
    except BridgeError as exc:
        raise BridgeError(str(exc) + _revert(prj, pcb, "placed")) from exc
    problems = []
    try:
        saved = read_pcbdoc(pcb, geometry=True)
    except (AltiumReadError, OSError) as exc:
        back = _restore(prj, pcb, backup) if backup else False
        raise BridgeError(f"Placed and saved, but the PcbDoc could not be read back: {exc}"
                          + (" The board file was put back as it was before (backup kept)." if back else f" The backup is in {backup}.")) from exc
    problems += layout.verify_layout(saved, parts, outline, clearance_mm, places=plan["places"], footprints=fps,
                                     edge_copper_mm=edge_copper_mm)
    warnings += layout.decap_distance_warnings(saved, parts)      # a far decoupling cap is a warning, never a reason to undo the placement
    drawing = layout.outline_drawing_problems(saved, outline)      # a closed drawing of the board shape on the outline layer
    if had_drawing:                                      # the student's own drawing stays; a mismatch is theirs to look at
        warnings += drawing
    else:
        problems += drawing
    try:                                                 # the outline Altium really holds, after the save
        after = _pcbcheck_info(run_commands([("PROJECT", str(prj)), ("PCBCHECK", str(pcb), "1")]))
    except BridgeError:
        after = None
    if after is not None:
        got = [v * MM_PER_MIL for v in after["box_mil"]]
        if any(abs(a - b) > 0.05 for a, b in zip(got, outline)) or not after["rect"]:
            problems.append(f"the saved board outline is {[round(v, 2) for v in got]} mm with {after['points']} points, planned {outline}")
    if not problems:                                     # the shape a pour is clipped to must be the outline too (T24)
        why = _fit_shape(prj, pcb, [v * MM_PER_MIL for v in after["box_mil"]] if after is not None else outline)
        if why:
            warnings.append(f"The board shape Altium holds is not the board outline and could not be set ({why}). A ground pour would stay "
                            "empty: redefine the board shape in Altium (Design > Board Shape > Redefine Board Shape) before routing")
    try:
        from checks import board as board_checks
        drills = [f["message"] for f in board_checks.check_drills(saved)]
    except Exception:                                    # a check that cannot run must not hide the placement result
        drills = []
    restored = False
    if problems and backup:
        restored = _restore(prj, pcb, backup)
    warnings = list(dict.fromkeys(warnings))             # the planner and the check of the saved board can say the same thing: once, order kept
    mech = {p["ref"] for p in holes + keepouts}
    return {"placed": [p["ref"] for p in plan["places"] if p["ref"] not in mech], "outline": outline, "outline_created": create,
            "warnings": warnings, "backup": backup, "problems": problems, "pads": len(saved.get("pads", [])), "restored": restored,
            "places": plan["places"], "drill_findings": drills,
            "mechanical": {"holes": [h["ref"] for h in holes], "keepouts": [k["ref"] for k in keepouts]}}


def place_pcb(project, replace=False):
    """altium.place_pcb: the netlist's parts on the project's PcbDoc (footprints from the project PcbLib, linked and netted like
    Update PCB does it), board outline from the idea's board size when the PcbDoc has none yet."""
    prj = _linked(project)
    pcb = _project_pcb(project)
    lp = library_paths(project)
    parts = _netlist_parts(project)
    refuse_footprint_errors(project, {p["ref"] for p in parts}, "place")
    draft = store.draft_parts(project)
    if draft:           # the one place a draft schematic stops work: the redraw that replaces a placeholder gives the part a new schematic id
        refs = [x["ref"] for x in draft]
        raise BridgeError(f"The schematic is still a draft: {', '.join(refs[:8])}{' ...' if len(refs) > 8 else ''} "
                          f"{'is a placeholder' if len(refs) == 1 else 'are placeholders'}, not the library symbol. Build the library and draw the "
                          "schematic again (Schematic page), then place the parts: a part placed now is linked to the placeholder's schematic id, "
                          "the redraw makes a new component with a new id, and Update PCB would then add the part again. Nothing was changed.")
    links = _sch_links(prj)
    undrawn = sorted({p["ref"] for p in parts if p["ref"] not in links})
    if undrawn:                  # parts placed without their schematic link are added a second time by the first Update PCB
        raise BridgeError("The schematic is not drawn in Altium for " + ", ".join(undrawn[:8]) + (" ..." if len(undrawn) > 8 else "")
                          + ": draw it first (altium.draw_schematic, with the student's agreement). A part placed without the link to its "
                          "schematic symbol is duplicated by the first Update PCB. Nothing was changed.")
    fit = board_fit_check(project)                       # the same estimate the BOM approval gave; the figures also go in the refusal
    import constraints
    items = constraints.confirmed(store.load_idea(project))      # the SAVED idea: only what the student confirmed with Save
    res = place_on(prj, pcb, lp["pcblib"], parts, size=_board_size(project), clearance_mm=_clearance_mm(project), replace=replace,
                   constraint_items=items, refs_lines=constraints.known_refs(project) if items else None)
    if not res["problems"]:
        _record_board_facts(project, pcb, outline=res["outline"])
    if res.get("mechanical", {}).get("holes") or res.get("mechanical", {}).get("keepouts"):
        res["warnings"] = list(res["warnings"]) + [
            "Mounting holes / keep-outs (" + ", ".join(res["mechanical"]["holes"] + res["mechanical"]["keepouts"]) + ") are not in the "
            "schematic: Altium's Update PCB will offer to remove them. Do not accept those removals."]
    if fit and fit["text"]:
        res["warnings"] = [fit["text"]] + list(res["warnings"])
    _log(project, "place-pcb", pcb=str(pcb), parts=len(res["placed"]), outline=res["outline"], replace=bool(replace),
         backup=res["backup"], problems=res["problems"], warnings=res["warnings"])
    res["warnings"] = list(dict.fromkeys(res["warnings"] + [f"drill check: {m}" for m in res["drill_findings"][:6]]
                                         + [f"design vs board: {m}" for m in design_problems(project)[:6]]))
    if res["problems"]:
        raise BridgeError(f"Placed {len(res['placed'])} parts but the saved board does not check out: "
                          + "; ".join(res["problems"][:6]) + (f" (+{len(res['problems']) - 6} more)" if len(res["problems"]) > 6 else "")
                          + (" The board file was put back as it was before (backup kept)." if res["restored"] else " The backup is in " + str(res["backup"]) + "."))
    return res


DRC_WATCHED = ("Clearance Constraint", "Short-Circuit", "Un-Routed Net", "Width Constraint", "Hole To Hole", "Minimum Annular Ring")


def _drc_counts(res):
    """{watched rule: count} of a parse_drc result (prefix match: Altium appends the rule values to the name)."""
    out = {}
    for name, n in (res or {}).get("rules", {}).items():
        for w in DRC_WATCHED:
            if name.startswith(w):
                out[w] = out.get(w, 0) + n
    return out


def _partial_ok(problem):
    """A problem that a partly routed board (agreed with the student) has by definition: nets left open."""
    return problem.startswith(("not routed", "too narrow")) or "open nets" in problem or "un-routed connection" in problem


def route_on(prj, pcb, replace=False, seconds=120, keep_partial=False, pitch=0.1, pour=True, currents=None, estimates=None, copper=None, names=None, stale_library=None,
             keepout_fn=None):
    """Route the placed PcbDoc with the agent's own router (scripts/altium/route.py; Altium's autorouter cannot be run from a
    script), draw the tracks and vias, save, then check the saved file two ways: our own unrouted() on the read-back file and
    Altium's batch design rule check (no new clearance / short / width / un-routed violations over the check made before routing).
    A net that cannot be routed is reported with the reason; without keep_partial nothing is drawn then. Any failed check puts the
    backed-up file back. Returns {routed, failed, tracks, vias, problems, restored, backup, drc_before, drc_after, summary, ...}."""
    import tempfile
    from altium import layout, route
    from altium.pcbdoc import read_pcbdoc, poured_copper
    prj, pcb = pathlib.Path(prj), pathlib.Path(pcb)
    log = run_commands([("PROJECT", str(prj)), ("PCBCHECK", str(pcb), "1" if replace else "0", "route")])   # unsaved / existing copper
    info = _pcbcheck_info(log)
    if info is None:
        raise BridgeError("Altium did not report the state of the board.")
    if info["parts"] == 0:
        raise BridgeError("There are no parts on the board: place the parts first (altium.place_pcb).")
    if not info["rect"] or info["box_mil"] == NEW_BOARD_BOX_MIL:
        raise BridgeError("The board outline is not a rectangle drawn for this board (or is still the placeholder of a new board): "
                          "place the parts first so that it gets its outline.")
    box = [v * MM_PER_MIL for v in info["box_mil"]]
    doc = read_pcbdoc(pcb)
    if replace:      # the copper that is about to be removed is no obstacle: only what belongs to a footprint stays
        doc = dict(doc, tracks=[t for t in doc.get("tracks", []) if t.get("in_component")],
                   arcs=[a for a in doc.get("arcs", []) if a.get("in_component")], vias=[],
                   fills=[f for f in doc.get("fills", []) if f.get("in_component")],
                   regions=[g for g in doc.get("regions", []) if g.get("in_component")])
    if not doc.get("nets"):
        raise BridgeError("The board has no nets: the pads carry none, so there is nothing to route (place the parts again).")
    rules = route.rules_from_doc(doc)
    rules.update(net_current=currents or {}, net_estimate=estimates or {}, allow_narrow=bool(keep_partial), **(copper or {}))      # widths by current (netcurrent.py)
    cap_warn = []
    py_keepouts = []
    if keepout_fn:          # the keep-outs this program holds itself: obstacles of the router and cut-outs of the pour, whatever Altium keeps
        py_keepouts = keepout_fn(box, doc)
        rules["keepout_rects"] = py_keepouts
    refused = route.capability_check(doc, rules, box, pitch, warnings=cap_warn)      # what this router cannot do is said before anything is run or drawn
    if refused:
        return {"routed": [], "failed": [], "tracks": 0, "vias": 0, "stats": {}, "rules": {}, "widths": {}, "backup": "",
                "problems": ["not routed, nothing was drawn: " + "; ".join(refused)], "refusals": refused, "restored": False,
                "drc_before": {}, "drc_after": {}, "drc_line": "unchecked (not run)", "drc_clean": False, "drills": [], "written": False,
                "pour": None, "pour_warning": "", "pour_warnings": [],
                "summary": "not routed, nothing was drawn: " + "; ".join(refused)}
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="advisor-drc-"))
    drc_before_full = run_drc(prj, pcb, tmp / "before.txt")
    drc_before = _drc_counts(drc_before_full)
    pour_net = route.pour_net_for(doc) if pour else None
    shape = _shape_differs(pcb, box) if pour_net else None      # a pour is clipped to the board shape Altium holds: set it to the outline below
    # The ground is planned as poured (each pad dropped to the pour by a short stub and a via) only when the pour is certain to be drawn
    # as planned: a board shape that has to be rewritten first could fail, and then the ground would have no copper; that board is
    # planned with the ground routed by tracks (the pour is still drawn on top).
    plan = route.plan_routes(doc, box, rules, pitch=pitch, seconds=seconds, pour_net=None if shape else pour_net)
    pour_dep = bool(plan.get("pour") and plan["pour"].get("mode") == "drops")       # some ground pad is joined by the pour alone
    names = names or {}                  # {drawn name: netlist name}: the PcbDoc carries the drawn names, the student knows the netlist's
    shown = {names.get(n, n): w for n, w in plan["widths"].items()}
    pour_skipped = ""
    res = {"routed": plan["routed"], "failed": plan["failed"], "tracks": plan["stats"]["tracks"], "vias": plan["stats"]["vias"],
           "stats": plan["stats"], "rules": {k: v for k, v in rules.items() if k not in ("net_width", "net_current", "net_estimate")}, "widths": shown, "backup": "", "problems": [],
           "restored": False, "drc_before": drc_before, "drc_after": {}, "drills": [], "written": False, "pour": pour_net, "pour_warning": pour_skipped,
           "pour_warnings": [], "capability_warnings": cap_warn, "drc_line": "unchecked (not run)", "drc_clean": False,
           "keepouts_held": len(py_keepouts)}
    if plan["failed"] and not keep_partial:
        res["summary"] = "no tracks drawn: could not route " + "; ".join(f"{n} ({why})" for n, why in plan["failed"])
        return res
    from altium import netcurrent as netcurrent_mod
    narrow = netcurrent_mod.width_problems(plan["widths"], names)      # only with keep_partial a net is drawn narrower than its current needs
    bad = route.violations(doc, plan["items"], rules, box)          # our own exact check of what we are about to draw
    if bad:
        res["problems"] = ["the route would break the rules (nothing drawn): " + "; ".join(bad[:5])]
        res["summary"] = res["problems"][0]
        return res
    res["backup"] = _backup(prj, [pcb])
    try:
        # A board that was placed in this same Altium session is still held with the pad nets of the placing script: a pour made on
        # it keeps no clearance from other-net through-hole pads (seen 2026-11-11, T28: the DRC found shorts to J1-1 and J2-1). The
        # board is saved and unchanged here (checked again just now: the first PCBCHECK ran before the DRC and the planning, minutes ago,
        # and REVERT closes without asking), so closing it and drawing on the file's own state is safe.
        state = run_commands([("PROJECT", str(prj)), ("DOCSTATE", str(pcb))])
        if any(l.startswith("docstate open modified=1") for l in state):
            raise BridgeError("The board is open in Altium with unsaved changes; save or close it first (click the PCB tab in Altium and press "
                              "Ctrl+S). Nothing was changed.")
        run_commands([("PROJECT", str(prj)), ("REVERT", str(pcb))])
        if shape:       # the board is closed and saved: set the shape it holds to the outline (backup taken above), then pour as usual
            why = _write_shape(pcb, box)
            if why:
                name, pour_net, res["pour"] = pour_net, None, None
                res["pour_warning"] = (f"no {name} pour: the board shape Altium holds ({', '.join(f'{v:g}' for v in shape)} mm) is not the board "
                                                      f"outline ({', '.join(f'{v:g}' for v in box)} mm) and could not be set ({why}), so a pour would stay empty. Redefine the "
                                                      "board shape in Altium (Design > Board Shape > Redefine Board Shape) and route again if you want a ground plane")
            else:
                res["shape_fixed"] = [round(v, 3) for v in box]
        run_commands([("PROJECT", str(prj))] + route.route_commands(pcb, plan["items"], replace, pour_net=pour_net, box=box,
                                                                     edge=rules["edge"], keepouts=_footprint_keepouts(doc) + py_keepouts), total_timeout=1500)
    except BridgeError as exc:
        if str(exc).startswith("The board is open in Altium with unsaved changes"):      # nothing was drawn: leave the student's edits alone
            raise
        raise BridgeError(str(exc) + _revert(prj, pcb, "routed")) from exc
    res["written"] = True
    probs = []
    open_nets = []
    after = {}
    try:        # whatever goes wrong from here on (read back, reload, the check itself) puts the backed-up board back
        saved = read_pcbdoc(pcb, geometry=True)
        open_nets = layout.unrouted(saved)
        if pour_dep:      # unrouted() does not read pours: the ground pads that the pour joins show as open here; the pour is checked below
            open_nets = [(n, t) for n, t in open_nets if n != pour_net]
        if open_nets:
            probs.append("the saved board still has open nets: " + "; ".join(f"{n} ({', '.join(t[:4])})" for n, t in open_nets[:5]))
        try:    # Altium checks connectivity from what it loaded: close the board (saved, nothing lost) so the check reads the file again
            run_commands([("PROJECT", str(prj)), ("REVERT", str(pcb))])
        except BridgeError as exc:
            probs.append(f"the board could not be reloaded for the design rule check: {exc}")
        drc = run_drc(prj, pcb, tmp / "after.txt")
    except (BridgeError, AltiumReadError, OSError) as exc:
        res["restored"] = _restore(prj, pcb, res["backup"])
        res["problems"] = [f"after drawing, the board could not be read back or checked ({exc})"]
        res["summary"] = res["problems"][0] + (" The board file was put back as it was before (backup kept)." if res["restored"]
                                              else f" The backup is in {res['backup']}.")
        res["written"] = True
        return res
    after = _drc_counts(drc)

    def drc_problems(after, drc):
        out = []
        if after.get("Un-Routed Net", 0) > 0:
            out.append(f"Altium's design rule check reports {after['Un-Routed Net']} un-routed connections")
        for w in ("Clearance Constraint", "Short-Circuit", "Width Constraint"):
            if after.get(w, 0) > drc_before.get(w, 0):
                out.append(f"Altium's design rule check reports {after[w] - drc_before.get(w, 0)} new {w} violations "
                           f"({'; '.join(v for v in drc['violations'] if w.split()[0].lower() in v.lower())[:300]})")
        return out

    new_probs = drc_problems(after, drc)
    if pour_net and new_probs and not pour_dep:       # the pour may be all that is wrong: take only the polygon off, keep the tracks, and check again
        # (not when the ground was routed to the pour: without the pour its pads are not connected, so the board is put back as it was)
        only_pour = all(after.get(w, 0) - drc_before.get(w, 0) <= sum(1 for v in drc["violations"] if v.startswith(w) and "polygon" in v.lower())
                        for w in ("Clearance Constraint", "Short-Circuit", "Width Constraint")) and after.get("Un-Routed Net", 0) == 0
        if only_pour:
            try:
                run_commands([("PROJECT", str(prj)), ("POLYDEL", str(pcb)), ("PCBSAVE", str(pcb))])
                run_commands([("PROJECT", str(prj)), ("REVERT", str(pcb))])
                drc2 = run_drc(prj, pcb, tmp / "after-nopour.txt")
                saved2 = read_pcbdoc(pcb, geometry=True)       # the numbers below come from the file as it is now, without the polygon
                open2 = layout.unrouted(saved2)
                left = poured_copper(pcb)
            except (BridgeError, AltiumReadError, OSError) as exc:
                res["restored"] = _restore(prj, pcb, res["backup"])
                res["problems"] = [f"the {pour_net} pour broke the rules and taking it off failed ({exc})"]
                res["summary"] = res["problems"][0] + (" The board file was put back as it was before (backup kept)." if res["restored"]
                                                      else f" The backup is in {res['backup']}.")
                return res
            else:
                after2 = _drc_counts(drc2)
                new_probs2 = drc_problems(after2, drc2)
                if not new_probs2 and not left:        # no polygon copper may be left in the file
                    after, drc, new_probs = after2, drc2, []
                    saved, open_nets = saved2, open2
                    if open_nets:
                        probs.append("the saved board still has open nets: " + "; ".join(f"{n} ({', '.join(t[:4])})" for n, t in open_nets[:5]))
                    res["pour"], pour_net = None, None
                    res["pour_warning"] = ("the ground pour was taken off again: Altium's design rule check found it too close to other copper. "
                                           + ("" if pour_dep else "All GND pads are connected by tracks; ")
                                           + "add a pour in Altium (Place > Polygon Pour) if you want a ground plane")
    res["drc_after"] = after
    res.update(drc_rules=dict(drc.get("rules") or {}), drc_total=drc.get("total"), drc_clean=drc_clean(drc), drc_complete=bool(drc.get("complete")), drc_line=drc_line(drc))
    res.update(_drc_explained(drc_before_full, drc, saved))
    if not drc.get("complete"):
        probs.append("Altium's design rule check report could not be read in full, so the board is unchecked (not clean): "
                     "run the design rule check in Altium (Tools > Design Rule Check) and look at the list")
    elif not drc_before_full.get("complete"):
        probs.append("the design rule check made before routing could not be read in full, so new violations cannot be told from old ones: unchecked")
    probs += new_probs
    if pour_net:       # Altium can accept the polygon and still leave it empty: look for copper in the saved file
        try:
            filled = poured_copper(pcb)
        except (AltiumReadError, OSError):
            filled = None
        if filled is None:      # not checked is not the same as empty
            res["pour"] = None
            res["pour_warning"] = (f"the {pour_net} pour could not be checked in the saved file: look at the bottom layer in Altium, "
                                   "and repour it with Tools > Polygon Pours > Repour All if it is empty")
        elif not filled:
            res["pour"] = None
            res["pour_warning"] = (f"the {pour_net} pour was drawn but Altium did not fill it (no copper): repour it in Altium with "
                                   "Tools > Polygon Pours > Repour All, or route without it")
    if pour_dep and not res["pour"]:       # fail closed: the ground was routed to the pour, so without the pour it is not routed at all
        probs.append(f"{pour_net} was routed to the pour on the bottom layer but the pour is not in the saved board (see the pour warning): "
                     f"the {pour_net} pads are not connected")
    if res["pour"]:         # the pour exists in the file: islands (cut-off copper) and pads it does not reach
        pc_probs, res["pour_warnings"] = _pour_findings(saved, pour_net)
        probs += pc_probs
    try:
        from checks import board as board_checks
        res["drills"] = [f["message"] for f in board_checks.check_drills(saved)]
        res["footprint_findings"] = [f["message"] for f in board_checks.check_footprint_rules(saved, stale_library)]
    except Exception:
        pass
    probs += narrow                      # drawn narrow as agreed: the step is not finished
    if plan["failed"]:
        probs.append("not routed: " + "; ".join(f"{n} ({why})" for n, why in plan["failed"]))
    res["problems"] = probs
    res["saved_open"] = [n for n, _ in open_nets]        # nets still open on the saved board (the route plan's own "failed" list may name fewer)
    if probs and not (keep_partial and all(_partial_ok(p) for p in probs)):
        res["restored"] = _restore(prj, pcb, res["backup"])
    res["summary"] = (f"{len(plan['routed'])} nets routed with {res['tracks']} tracks and {res['vias']} vias"
                      + (f", {pour_net} poured on the bottom layer" if res["pour"] else "") + f", saved; own check: "
                      f"{'no open nets' if not open_nets else str(len(open_nets)) + ' open nets'}; Altium DRC: "
                      f"{res['drc_line']} ({drc_before.get('Clearance Constraint', 0)} clearance before routing)"
                      + ("; " + wl if (wl := _width_line(shown)) else ""))
    return res


def _record_board_facts(project, pcb, drc_total=None, outline=None, doc=None):
    """Measure the saved board against the confirmed constraints and keep it (constraints.record_facts): what the agent may state
    about the board comes from this and from nothing else. Never raises; returns the facts or None."""
    try:
        import constraints
        from altium import pcbdoc
        doc = doc or pcbdoc.read_pcbdoc(pcb, geometry=True)
        outline = outline or pcbdoc.board_shape_box(pcb) or (constraints.load_facts(project) or {}).get("outline")
        return constraints.record_facts(project, doc, outline, pcb=pcb, drc_total=drc_total, size=_board_size(project))
    except Exception:                       # noqa: BLE001
        return None


def _footprint_keepouts(doc):
    """[[x0, y0, x1, y1]] mm keep-out areas that footprints carry (an antenna area, a keep-out of a constraint): the ground pour is
    drawn around them. [] when the board has none or they cannot be read."""
    try:
        from checks import requirements
        return requirements.component_keepouts(doc)
    except Exception:                       # noqa: BLE001 - a pour without the cut-out is the old behaviour, never a failed route
        return []


def _drc_explained(before, after, doc=None):
    """{"drc_origin": table, "new_unwatched": [...]} of the route's design rule check: each rule's violations by origin (footprint,
    router, placement) with the JLC item it maps to, and the rules the pass criteria (DRC_WATCHED) do not watch that got worse
    by the route. Never raises: this only explains, it does not decide."""
    try:
        from checks import drc_origin
        return {"drc_origin": drc_origin.table(after, doc),
                "new_unwatched": drc_origin.new_unwatched((before or {}).get("rules"), (after or {}).get("rules"), DRC_WATCHED)}
    except Exception:                       # noqa: BLE001
        return {"drc_origin": [], "new_unwatched": []}


def _pour_findings(saved, net):
    """(problems, warnings) of pourcheck.check on the board read back after the pour was drawn. A pad the pour and the tracks do not
    join is a problem; a cut-off piece of copper is a warning (with the Remove Dead Copper note when that is off); a check that did not
    run, or raised, is the warning "pour not checked": never ok."""
    from altium import pourcheck
    try:
        pc = pourcheck.check(saved, net=net)
    except Exception as exc:        # noqa: BLE001 - whatever goes wrong, the pour is not known to be fine
        return [], [f"{net} pour not checked ({type(exc).__name__}: {exc}): look at the pour in Altium for cut-off copper and unconnected pads"]
    if not isinstance(pc, dict) or pc.get("checked") is not True:
        why = (pc.get("note") if isinstance(pc, dict) else "") or "no answer"
        return [], [f"{net} pour not checked: {why} Look at the pour in Altium for cut-off copper and unconnected pads"]
    probs = [f"pad {u.get('ref')}-{u.get('name')} ({net}) is not joined by the pour or a track" for u in pc.get("unjoined_pads", [])]
    warns = []
    if pc.get("islands"):
        warns.append(f"{len(pc['islands'])} cut-off piece(s) of {net} copper in the pour (" + ", ".join(
            f"{i.get('area_mm2')} mm2 at {i.get('bbox_mm')}" for i in pc["islands"][:4]) + "); " + (pc.get("note") or ""))
    return probs, warns


def _width_line(widths):
    from altium import netcurrent
    return netcurrent.width_line(widths)


def net_current_inputs(project, strict=True):
    """What route_on sizes the tracks by: {currents (set by the student, approved), estimates (a regulator's rated output current from
    the BOM), copper {copper_oz, temp_rise_c} from project.json board.* if present, names {drawn name: netlist name}}. The nets are
    keyed by the name the PcbDoc carries (draw.alias_map: a Hebrew net is drawn under an ASCII alias). strict=False (the Rules tab)
    keeps the netlist names when the aliases clash instead of raising."""
    from altium import netcurrent
    import project as projects
    board = projects.load_meta(project).get("board") or {}
    copper = {k: float(board[k]) for k in ("copper_oz", "temp_rise_c") if isinstance(board.get(k), (int, float)) and board[k] > 0}
    cur = store.net_currents(project)
    est = netcurrent.regulator_currents(store.bom_lines(project), [sh for _, _, sh in _sheets(project)])
    try:
        al = drawn_names(project, list(cur) + list(est))
    except AliasError:
        if strict:
            raise
        al = {}
    names = {a: n for n, a in al.items() if a != n}
    return {"currents": {al.get(n, n): v for n, v in cur.items()}, "copper": copper,
            "estimates": {al.get(n, n): v for n, v in est.items()}, "names": names}


def _last_drawn_widths(project):
    """{netlist net: width drawn} of the last route that was saved without problems (altium-log.jsonl), else {}."""
    for e in reversed(store.read_jsonl(store.pdir(project) / "altium-log.jsonl")):
        if e.get("op") == "route-pcb":
            return {} if e.get("problems") or e.get("restored") or e.get("failed") else (e.get("drawn_widths") or {})
    return {}


def net_current_rows(project):
    """What the Rules tab shows: {nets: [{net, current_a, source, width_mm, note, drawn_mm}], copper_oz, temp_rise_c}. Rows are the
    supply (rail) nets of the netlist, every net with a current and every regulator output. Widths come from the same rules the router
    uses (the linked PcbDoc's width rules, InNet rules included, when there is one; else the JLC defaults); drawn_mm is the width of
    the last saved route."""
    from altium import netcurrent, route
    inp = net_current_inputs(project, strict=False)
    al = {n: a for a, n in inp["names"].items()}                     # netlist name -> drawn name
    listed = {(p.get("net") or "").strip() for _, _, sh in _sheets(project) for part in sh.get("parts", []) for p in part.get("pins", [])}
    listed.discard("")
    drawn = {n: al.get(n, n) for n in listed}
    nets = sorted(n for n in listed if route._RAIL.match(drawn[n]) or drawn[n] in inp["currents"] or drawn[n] in inp["estimates"])
    rules = None
    try:
        from altium import pcbdoc
        rules = route.rules_from_doc(pcbdoc.read_pcbdoc(_project_pcb(project)))
    except (BridgeError, AltiumReadError, OSError):
        pass
    rules = rules or route.rules_from_doc({})
    oz, rise = inp["copper"].get("copper_oz", 1.0), inp["copper"].get("temp_rise_c", 10.0)
    w = netcurrent.net_widths([drawn[n] for n in nets], rules, inp["currents"], inp["estimates"], oz, rise,
                              is_rail=lambda n: bool(route._RAIL.match(n)))
    last = _last_drawn_widths(project)
    return {"nets": [{"net": n, **w[drawn[n]], "drawn_mm": last.get(n)} for n in nets], "copper_oz": oz, "temp_rise_c": rise,
            "all_nets": sorted(listed)}


def route_pcb(project, replace=False, keep_partial=False):
    """altium.route_pcb: the placed board routed by the agent's router (see route_on). Raises BridgeError with the reason when it did
    not end up with a fully routed, rule-clean board; the file is then as it was (backup kept)."""
    prj = _linked(project)
    pcb = _project_pcb(project)
    missing = rules_missing(project)      # widths, clearances and vias come from the board rules: Altium's defaults are not JLC's
    if missing:
        raise Fixable("prereq.rules_not_imported", "Import the JLC rules first (altium.import_rules), then route: the board does not have "
                      + ", ".join(missing[:6]) + (" ..." if len(missing) > 6 else "") + ". Nothing was changed.")
    try:
        stale = partlib.converter_stale(project)        # tells the silk-to-mask finding whether "rebuild the library" is true
    except Exception:
        stale = None
    caps = capabilities_cached()
    res = route_on(prj, pcb, replace=replace, keep_partial=keep_partial, stale_library=stale, **net_current_inputs(project),
                   keepout_fn=lambda box, doc: python_keepouts(project, doc, box))
    if caps is not None and not caps.get("keepout_layer", True) and res.get("keepouts_held"):
        res.setdefault("capability_warnings", []).append(keepout_notice(caps))
    from altium import netcurrent
    _log(project, "route-pcb", pcb=str(pcb), routed=res["routed"], failed=[n for n, _ in res["failed"]], tracks=res["tracks"],
         vias=res["vias"], replace=bool(replace), keep_partial=bool(keep_partial), backup=res["backup"], problems=res["problems"],
         restored=res["restored"], drc_before=res["drc_before"], drc_after=res["drc_after"],
         drawn_widths={n: w["width_mm"] for n, w in res["widths"].items() if w["width_mm"] is not None})
    open_nets = list(dict.fromkeys([n for n, _ in res["failed"]] + list(res.get("saved_open") or [])))     # every open net, not only the ones the plan failed on
    why = dict(res["failed"])
    partial_kept = bool(keep_partial and open_nets and res["written"] and not res["restored"] and res["problems"]
                        and all(_partial_ok(p) for p in res["problems"]))        # the student asked for it: tracks stay, the answer names the open nets
    if not partial_kept and (res["problems"] or res["failed"] or not res["written"]):
        err = BridgeError(res["summary"] if not res["written"] else
                          "The route does not check out: " + "; ".join(res["problems"][:5])
                          + f" Altium DRC, every rule: {res.get('drc_line') or 'unchecked'}."
                          + (" The board file was put back as it was before (backup kept)." if res["restored"]
                             else f" Tracks stay on the board (partial, as agreed); backup in {res['backup']}." if keep_partial
                             else f" Backup in {res['backup']}."))
        if res["failed"] and not res["written"] and not keep_partial:
            err.open_nets = open_nets          # the page offers "route the rest and leave these open": the student's click is the consent
        raise err
    res["warnings"] = ([res["pour_warning"]] if res.get("pour_warning") and not res["restored"] else []) + res.get("pour_warnings", []) + res.get("capability_warnings", []) + [f"drill check: {m}" for m in res["drills"][:6]] + [f"footprint: {m}" for m in res.get("footprint_findings", [])[:6]] + [f"design vs board: {m}" for m in design_problems(project)[:6]]
    res["warnings"] += [f"track width: {m}" for m in netcurrent.width_warnings(res["widths"])]
    res["warnings"] += [f"not in the route's pass criteria, got worse: {m}" for m in res.get("new_unwatched", [])]
    _record_board_facts(project, pcb, drc_total=res.get("drc_total"))
    if partial_kept:
        res["open_nets"] = open_nets
        res["summary"] += "; PARTIAL ROUTE, left open: " + ", ".join(f"{n} ({why[n]})" if n in why else n for n in open_nets)
        res["warnings"] = [f"open nets, not routed: {', '.join(open_nets)}"] + [f"route check: {m}" for m in res["problems"] if not m.startswith("not routed")] + res["warnings"]
    return res


def run_drc(prj, pcb, report):
    """The design rule check of Altium on the board, by script (no dialog). Returns parse_drc(report)."""
    run_commands([("PROJECT", str(prj)), ("DRC", str(pcb), str(report))])
    res = parse_drc(report)
    if res is None:
        raise BridgeError("Altium did not write the design rule check report.")
    return res


# ---------------------------------------------------------------- the rules

# kind -> {.RUL record key: the Altium rule property that script sets}. Lengths go over as Altium's internal unit
# (1 mil = 10000); a property that starts with "Layer" is set on every signal layer; ViasUnderSMD's flag is 0 or 1.
RULE_PROPS = {
    "Clearance": {"GAP": "Gap"},
    "BoardOutlineClearance": {"GAP": "Gap"},
    "Width": {"MINLIMIT": "LayerMinWidth", "MAXLIMIT": "LayerMaxWidth", "PREFEREDWIDTH": "LayerFavoredWidth"},
    "RoutingVias": {"MINHOLEWIDTH": "MinHoleWidth", "MAXHOLEWIDTH": "MaxHoleWidth", "HOLEWIDTH": "PreferedHoleWidth",
                    "MINWIDTH": "MinWidth", "MAXWIDTH": "MaxWidth", "WIDTH": "PreferedWidth"},
    "HoleSize": {"MINLIMIT": "MinLimit", "MAXLIMIT": "MaxLimit"},
    "MinimumAnnularRing": {"MINIMUMRING": "MinimumRing"},
    "SolderMaskExpansion": {"EXPANSION": "Expansion"},
    "PasteMaskExpansion": {"EXPANSION": "Expansion"},
    "HoleToHoleClearance": {"GAP": "Gap"},
    "SilkToSolderMaskClearance": {"MINSILKSCREENTOMASKGAP": "SilkToMaskGap"},
    "SilkToSilkClearance": {"SILKTOSILKCLEARANCE": "SilkToSilkClearance"},
    "ComponentClearance": {"GAP": "Gap", "VERTICALGAP": "VerticalGap"},
    "MinimumSolderMaskSliver": {"MINSOLDERMASKWIDTH": "MinSolderMaskSliver"},
    "ViasUnderSMD": {"ALLOWED": "Allowed"},
}
COORD_PER_MM = 10000 / 0.0254        # Altium's internal length unit per mm
COORD_SLACK = 50                     # 0.005 mil: the board file rounds what we wrote


def _coord(text):
    mm = rules_mod.to_mm(text)
    return None if mm is None else int(round(mm * COORD_PER_MM))


def _rule_values(rec):
    """{script property: integer} of one rule record, or None when a value of it is not a length."""
    out = {}
    for key, prop in RULE_PROPS[rec["RULEKIND"]].items():
        if key not in rec:
            continue
        val = int(str(rec[key]).strip().upper() == "TRUE") if prop == "Allowed" else _coord(rec[key])
        if val is None:
            return None
        out[prop] = val
    return out


def _same_values(want, got):
    """The board's values (a script property each) equal the wanted ones, within the file's rounding."""
    return all(abs(got.get(k, -10 ** 9) - v) <= (0 if k == "Allowed" else COORD_SLACK) for k, v in want.items())


def _project_pcb(project):
    link = project_mod.altium_link(project)
    name = link.get("pcb_file")
    pcb = pathlib.Path(name) if name else None
    if pcb and not pcb.is_file() and link.get("project_file"):
        pcb = pathlib.Path(link["project_file"]).parent / name
    if not pcb or not pcb.is_file():
        raise BridgeError("The linked Altium project has no PcbDoc yet. Add one first (add-pcb).")
    return pcb


def _json_list(project, name):
    try:
        val = json.loads((store.pdir(project) / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return val if isinstance(val, list) else []


def _plan_records(project, pcb):
    off = {n for n in _json_list(project, "rules-off.json") if isinstance(n, str)}
    preset = [r for r in rules_mod.get_preset_rule_records(project_mod.board(project)) if r.get("NAME") not in off]
    records = rule_kinds.append_extra_records(rules_mod.board_rul_records(pcb, preset), _json_list(project, "rules.json"))
    return _drawn_rule_records(project, records)


def _drawn_rule_records(project, records):
    """The rule records under the names the board carries: InNet('...') in a scope is the net's drawn name (the one source: the
    project's alias map), and a rule name that is not plain ASCII is its transliteration (kept in the same file, so the next
    import finds the rule again by the same exact name)."""
    from altium import draw
    nets = [n for r in records for k in ("SCOPE1EXPRESSION", "SCOPE2EXPRESSION") for n in draw.scope_nets(r.get(k))]
    al = drawn_names(project, nets)
    out = []
    for r in records:
        r = dict(r)
        for k in ("SCOPE1EXPRESSION", "SCOPE2EXPRESSION"):
            if k in r:
                r[k] = draw.alias_scope(r[k], al)
        out.append(r)
    names = [r.get("NAME", "") for r in out]
    if not all(draw._plain(n) for n in names):
        path = store.pdir(project) / "rule-names.json"
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            saved = {}
        try:
            got, changed = draw.assign_aliases(saved if isinstance(saved, dict) else {}, names, guard_power=False)
        except draw.AliasConflict as exc:
            raise AliasError(f"Two rules would get the same plain-ASCII name: {exc}. Rename one of the rules. Nothing was changed.") from exc
        if changed:
            path.write_text(json.dumps(got, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        for r in out:
            r["NAME"] = got.get(r.get("NAME", ""), r.get("NAME", ""))
    return out


def rules_missing(project):
    """Names of the advisor rules import_rules writes that the linked PcbDoc FILE does not have ([] without a PcbDoc)."""
    try:
        pcb = _project_pcb(project)
        have = {r.get("NAME") for r in rules_mod.read_pcbdoc(pcb).get("rules", [])}
        return [r["NAME"] for r in _plan_records(project, pcb)
                if r.get("RULEKIND") in RULE_PROPS and r.get("NAME") and r["NAME"] not in have and _rule_values(r) is not None]
    except AliasError:
        raise                  # never "nothing missing": the rules could not be planned, the caller must say so
    except (BridgeError, AltiumReadError, OSError):
        return []


def rules_never_imported(project):
    """True when the linked PcbDoc lacks advisor rules and no import into THIS PcbDoc is in the project's Altium log: the board
    still has Altium's defaults. Once an import ran, what is missing or different on the board is the student's own edit. (The
    rule names cannot tell: the plan merges the JLC values into the board's own rules, under the board's names.)"""
    try:
        pcb = _project_pcb(project)
        if not rules_missing(project):
            return False
        here = str(pathlib.Path(pcb)).lower()
        return not any(r.get("op") == "import-rules" and "error" not in r and str(r.get("pcb", "")).lower() == here
                       for r in store.read_jsonl(store.pdir(project) / "altium-log.jsonl"))
    except AliasError:
        return True            # the import step will refuse with the reason
    except (BridgeError, AltiumReadError, OSError):
        return False


def drill_problems(project):
    """Messages for vias and holes JLC cannot make, read from the linked PcbDoc file ([] without one). Runs with the outputs."""
    try:
        from checks import board
        return [f["message"] for f in board.check_drills(rules_mod.read_pcbdoc(_project_pcb(project))) if f["severity"] == "error"]
    except (BridgeError, AltiumReadError, OSError, ImportError):
        return []


def design_problems(project):
    """Messages for a PcbDoc that does not carry the design: the agent's netlist (intent) against the board's pads, and
    the SchDocs (nets with one pin) and SchDoc-vs-board connectivity. [] without a PcbDoc. Runs with the outputs."""
    try:
        from checks import schematic
        pcb = rules_mod.read_pcbdoc(_project_pcb(project))
        from altium import draw
        al = drawn_names(project)
        out = [f["message"] for f in schematic.check_intent_vs_board(
                   [dict(sh, parts=draw.alias_parts(sh.get("parts", []), al)) for sh in (store.load_sheet(project, s) for s in store.sheet_ids(project))], pcb)
               if f["severity"] == "error"]
    except AliasError as exc:
        return [f"the design could not be compared with the board: {exc}"]
    except (BridgeError, AltiumReadError, OSError, ImportError):
        return []
    try:
        prj = _linked(project)
        if read_prjpcb(prj)["sheets"]:
            res = schematic.check_schematic(prj, board=pcb)
            out += [f["message"] for f in res["findings"]
                    if f["id"] == "board_netlist_mismatch" or (f["id"] == "single_pin_net" and f["message"].startswith("Net '"))]
    except Exception:                                   # an unreadable SchDoc must not hide the intent findings
        pass
    return out


def rules_in_altium(log):
    """Rule names of Altium's in-memory board from a RULESIN run's log, or None when the log has no complete list."""
    names, total = [], None
    for ln in log:
        if ln.startswith("RULEIN "):
            names.append(ln[7:])
        elif ln.startswith("RULESIN ") and ln[8:].strip().isdigit():
            total = int(ln[8:])
    return names if total is not None and total == len(names) else None


def rule_plan(project, pcb):
    """What the PcbDoc needs: ([(record, script values)] to add or change, [{name, kind, why}] skipped). The record set is
    what the Download .RUL gives (preset minus the rules turned off, existing rules of the same kind and scope updated,
    extra rules added); a rule the board already has in the same state is left alone."""
    records = _plan_records(project, pcb)
    board = {r.get("NAME"): r for r in rules_mod.read_pcbdoc(pcb).get("rules", [])}
    todo, skipped = [], []
    for rec in records:
        name, kind, have = rec.get("NAME", ""), rec.get("RULEKIND", ""), board.get(rec.get("NAME"))
        if kind not in RULE_PROPS:
            if have is None or any(have.get(k) != v for k, v in rec.items()):
                skipped.append({"name": name, "kind": kind, "why": "this kind of rule cannot be written to Altium yet"})
            continue
        if have is not None and have.get("RULEKIND") != kind:
            skipped.append({"name": name, "kind": kind, "why": f"the board has a {have.get('RULEKIND')} rule with this name"})
            continue
        vals = _rule_values(rec)
        text = name + rec.get("SCOPE1EXPRESSION", "") + rec.get("SCOPE2EXPRESSION", "")
        if vals is None or any(ord(c) < 32 for c in text):
            skipped.append({"name": name, "kind": kind, "why": "a value or the name is not usable"})
            continue
        if (have is not None and _same_values(vals, _rule_values(have) or {})
                and rules_mod._rule_scopes(have) == rules_mod._rule_scopes(rec)):     # the priority is not ours to set
            continue
        todo.append((rec, vals))
    return todo, skipped


def rule_commands(pcb, todo):
    cmds = [("RULE", str(pcb), rec["RULEKIND"], rec["NAME"], rec.get("SCOPE1EXPRESSION", "All"),
             rec.get("SCOPE2EXPRESSION", "All"), str(rules_mod._prio(rec)), *[f"{k}={v}" for k, v in vals.items()])
            for rec, vals in todo]
    return cmds + [("SAVE", str(pcb)), ("RULESIN", str(pcb))]


def import_rules(project):
    """Put the advisor's rules into the linked PcbDoc. Returns {created, updated, skipped, unconfirmed, backup}."""
    prj = _linked(project)
    pcb = _project_pcb(project)
    todo, skipped = rule_plan(project, pcb)
    res = {"created": [], "updated": [], "skipped": skipped, "unconfirmed": [], "not_in_altium": [], "backup": "", "message": ""}
    if not todo:
        return res
    before = {r.get("NAME") for r in rules_mod.read_pcbdoc(pcb).get("rules", [])}
    res["backup"] = _backup(prj, [pcb])
    log = run_commands([("PROJECT", str(prj)), *rule_commands(pcb, todo)])
    mem = rules_in_altium(log or [])         # what Altium holds in memory: a save from Altium writes this, not our file
    after = {r.get("NAME"): r for r in rules_mod.read_pcbdoc(pcb).get("rules", [])}
    for rec, vals in todo:
        got = after.get(rec["NAME"])
        (res["updated"] if rec["NAME"] in before else res["created"]).append(rec["NAME"])
        if got is None or not _same_values(vals, _rule_values(got) or {}):
            res["unconfirmed"].append(rec["NAME"])      # Altium did not keep what we wrote: the Rules tab will show it
        if mem is not None and rec["NAME"] not in mem:
            res["not_in_altium"].append(rec["NAME"])
            if rec["NAME"] not in res["unconfirmed"]:
                res["unconfirmed"].append(rec["NAME"])
    if res["not_in_altium"]:
        res["message"] = (f"Altium's open board does not have {', '.join(res['not_in_altium'])}: a save from Altium would drop "
                          "them. Import again with the board open.")
    _log(project, "import-rules", pcb=str(pcb), backup=res["backup"], skipped=[s["name"] for s in skipped],
         **{k: res[k] for k in ("created", "updated", "unconfirmed", "not_in_altium")})
    return res


# ---------------------------------------------------------------- the OutJob

def outjob_containers(path):
    """[(medium name, base path)] of the OutJob's Folder Structure containers: the ones that write files."""
    cp = configparser.RawConfigParser(strict=False, interpolation=None)
    cp.optionxform = str
    cp.read(str(path), encoding="latin-1")
    out = []
    for sec in cp.sections():
        if not sec.startswith("OutputGroup"):
            continue
        for key, val in cp.items(sec):
            m = re.fullmatch(r"OutputMedium(\d+)", key)
            if m and cp.get(sec, key + "_Type", fallback="") == "GeneratedFiles" and val not in [o[0] for o in out]:
                out.append((val, cp.get("PublishSettings", f"OutputBasePath{m.group(1)}", fallback="")))
    return out


def repair_outline(prj, pcb):
    """A board placed before the outline was drawn has its board shape set but nothing on Mechanical 1, so the outline Gerber
    (.GM1) comes out empty. When that layer holds no drawing of its own and the board shape is a real rectangle, draw the shape
    there (4 tracks, like Design > Board Shape > Create Primitives From Board Shape), save with a backup and read the file back.
    Anything else is left alone. Returns {"drawn": bool, "backup": str, "warning": str}."""
    from altium import layout
    from altium.pcbdoc import read_pcbdoc
    out = {"drawn": False, "backup": "", "warning": ""}
    try:
        doc = read_pcbdoc(pcb)
    except (AltiumReadError, OSError):
        return out
    tracks, arcs = layout.outline_layer_free(doc)
    if tracks or arcs:
        return out                                       # somebody's drawing: never touched (a mismatch is reported by the checks)
    info = _pcbcheck_info(run_commands([("PROJECT", str(prj)), ("PCBCHECK", str(pcb), "1")]))     # refuses unsaved changes
    if info is None or (info["box_mil"] == NEW_BOARD_BOX_MIL and info["parts"] == 0):
        return out                                       # no board yet (the placeholder of a new PcbDoc): nothing to draw
    if not info["rect"] or info["box_mil"] == NEW_BOARD_BOX_MIL:
        out["warning"] = ("The outline layer (Mechanical 1) has no drawing and the board shape is not a plain rectangle (or still the "
                          "placeholder of a new board), so I did not draw it: use Design > Board Shape > Create Primitives From Board Shape "
                          "in Altium, or the outline Gerber will be empty.")
        return out
    box = [round(v * MM_PER_MIL, 3) for v in info["box_mil"]]
    backup = _backup(prj, [pcb])
    cmds = [("PROJECT", str(prj)), ("OUTLINEDRAW", str(pcb)) + tuple(f"{v:g}" for v in box) + (f"{layout.OUTLINE_WIDTH_MM:g}",),
            ("PCBSAVE", str(pcb))]
    try:
        run_commands(cmds)
        probs = layout.outline_drawing_problems(read_pcbdoc(pcb), box)
    except (BridgeError, AltiumReadError, OSError) as exc:
        probs = [str(exc)]
    if probs:
        back = _restore(prj, pcb, backup) if backup else False
        out["warning"] = ("I tried to draw the missing board outline on Mechanical 1 but it did not check out (" + "; ".join(probs[:3]) + ")"
                          + ("; the board file was put back as it was." if back else "; the backup is in " + str(backup) + "."))
        return out
    return {"drawn": True, "backup": backup, "warning": "", "box": box}


def _new_outjob(project, prj, summary):
    """Write our OutJob next to the project file. -> (file, the backup of the project file, the Altium commands that add it to the project)."""
    if summary["outjobs"]:
        raise BridgeError("The project's OutJob has no Folder Structure output to run.")
    target = prj.parent / f"{prj.stem}.OutJob"
    backup = _backup(prj, [prj])
    if not target.exists():          # a file already there (an earlier add that failed halfway, or the student's own) is added as it is, never overwritten
        outjob.generate_outjob(project, filename=target.name, out_dir=prj.parent)
    return target, backup, [("ADDDOC", str(prj), str(target)), ("SAVEPRJ", str(prj))]


def add_outjob(project):
    """Make our OutJob and add it to the Altium project (the visible first step of the Generate outputs button). Nothing is run.
    Returns {file, backup}; a project that already lists an OutJob is left as it is."""
    prj = _linked(project)
    summary = read_prjpcb(prj)
    if summary["outjobs"]:
        return {"file": "", "backup": ""}
    target, backup, cmds = _new_outjob(project, prj, summary)
    run_commands([("PROJECT", str(prj)), *cmds])
    _log(project, "add-outjob", outjob=str(target), backup=backup)
    return {"file": str(target), "backup": backup}


def unsaved_documents(prj):
    """Names of the project's documents that Altium holds open with unsaved changes (DOCSTATE, read only), [] when all are
    saved. Raises BridgeError when Altium cannot be asked. Outputs made then may not match the files on disk."""
    summary = read_prjpcb(prj)
    docs = [prj.parent / pathlib.Path(rel.replace("\\", "/")) for rel in summary["sheets"] + summary["pcbs"]]
    docs = [d for d in docs if d.is_file()] + [prj]
    state = [l for l in run_commands([("PROJECT", str(prj))] + [("DOCSTATE", str(d)) for d in docs]) if l.startswith("docstate ")]
    if len(state) != len(docs):
        return []                                      # an answer that does not match what was asked says nothing
    return [d.name for d, l in zip(docs, state) if "modified=1" in l]


def run_outjob(project):
    """Run the project's OutJob (ours is added first when it has none). Before the outputs, a board whose outline layer is empty gets
    its rectangular board shape drawn on Mechanical 1 (repair_outline). Returns {outjob, added, containers, files, backup, warnings,
    outline_drawn}."""
    prj = _linked(project)
    outline_note, outline_drawn = [], False
    try:
        try:
            pcb_file = _project_pcb(project)
        except BridgeError:
            pcb_file = None                              # no PcbDoc in the project: nothing to repair
        fix = repair_outline(prj, pcb_file) if pcb_file else {"drawn": False, "warning": ""}
        outline_drawn = fix["drawn"]
        if fix["drawn"]:
            outline_note.append(f"The outline layer (Mechanical 1) was empty: drew the board shape {fix['box']} mm there (backup {fix['backup']}).")
        elif fix["warning"]:
            outline_note.append(fix["warning"])
    except BridgeError as exc:
        outline_note.append(f"Could not check the outline layer ({exc}); if the outline Gerber is empty, draw the board shape on Mechanical 1.")
    summary = read_prjpcb(prj)
    target, added, backup = None, False, ""
    for rel in summary["outjobs"]:
        cand = prj.parent / pathlib.Path(rel.replace("\\", "/"))
        if cand.is_file() and outjob_containers(cand):
            target = cand
            break
    unsaved = []
    try:                                                 # outputs made from a project with unsaved edits do not match its files
        unsaved = unsaved_documents(prj)
    except BridgeError as exc:
        outline_note.append(f"Could not check whether Altium holds unsaved changes ({exc}).")
    if unsaved:
        outline_note.insert(0, f"Altium has unsaved changes in {', '.join(unsaved)}: the outputs may not match the saved files. "
                               "Save them in Altium (Ctrl+S) and generate the outputs again.")
    cmds = [("PROJECT", str(prj))]
    if target is None:
        target, backup, add_cmds = _new_outjob(project, prj, summary)
        cmds += add_cmds
        added = True
    boxes = outjob_containers(target)
    cmds += [("OUTJOB", str(target), medium, base) for medium, base in boxes]
    t0 = time.time() - 2
    run_commands(cmds, total_timeout=600)
    roots = jlc_upload._roots(project) or [prj.parent / "Outputs"]     # the linked folder, Altium's "Project Outputs for ..."
    files = []
    for root in roots:
        for dirpath, dirs, names in os.walk(root):
            dirs[:] = [d for d in dirs if d.lower() != BACKUP_DIR]
            files += [str(pathlib.Path(dirpath, n)) for n in names if pathlib.Path(dirpath, n).stat().st_mtime >= t0]
    if not files:
        raise BridgeError(f"Altium ran the OutJob but wrote no files under {roots[0]}. Open the OutJob in Altium and check its containers.")
    bom_files, bom_notes = _bom_into_outputs(project, roots, files)
    files += bom_files
    real = {r for l in store.bom_lines(project) for r in (l.get("refs") or [])}
    mech_gone = []
    for f in files:             # the OutJob's Pick Place output has no designator filter: holes and keep-outs are taken out of the CSV here
        mech_gone += outjob.strip_mechanical_rows(f, real)
    if mech_gone:
        bom_notes = list(bom_notes) + [f"Left {', '.join(sorted(set(mech_gone)))} (mounting holes / keep-outs, no parts) out of Altium's pick-and-place file."]
    try:
        missing = rules_missing(project)
    except AliasError as exc:
        missing = []
        outline_note = list(outline_note) + [f"The JLC rules could not be checked: {exc}"]
    warnings = outline_note + ([f"The JLC rules ({', '.join(missing)}) are no longer in the PcbDoc; DRC and outputs ran against Altium's "
                                "defaults. Import the rules again."] if missing else [])
    drills = drill_problems(project)
    if drills:
        warnings.append(f"{len(drills)} hole(s) JLC cannot make: " + "; ".join(drills[:5]) + (" ..." if len(drills) > 5 else ""))
    design = design_problems(project)
    if design:
        warnings.append(f"The board does not match the design ({len(design)} problem(s)): " + " | ".join(design[:5])
                        + (" ..." if len(design) > 5 else "") + " Fix this before ordering.")
    warnings += bom_notes                  # the least urgent: last
    import order_options
    import outputs_check
    opts = order_options.get(project)
    cpl_files = []
    if opts["assembly"]:                   # an order with assembly needs the CPL: made here from the placed board, never left to a click
        try:
            from skills import export_cpl
            cpl = export_cpl.export_cpl(project)
            home = workspace.home()
            cpl_path = pathlib.Path(cpl["file"])
            cpl_files = [str(cpl_path if cpl_path.is_absolute() else home / cpl_path)]
            warnings += cpl.get("warnings", [])
        except Exception as exc:
            warnings.append(f"The pick and place file (CPL) could not be made ({type(exc).__name__}: {exc}). Export it on the Outputs page.")
    check = outputs_check.verify(project, files, outjob=target, options=opts, extra=cpl_files)
    check["unsaved"] = unsaved
    outputs_check.save(project, check)
    warnings = list(check["warnings"]) + warnings          # what is missing comes first: it decides whether the step did its job
    _log(project, "run-outjob", outjob=str(target), added=added, files=len(files), backup=backup, rules_missing=missing,
         missing=check["missing"], empty=check["empty"], unsaved=unsaved)
    return {"outjob": str(target), "added": added, "containers": [m for m, _ in boxes], "files": sorted(files), "backup": backup,
            "warnings": warnings, "outline_drawn": outline_drawn, "outputs_check": check}


def _is_bom(path):
    """A BOM file by its own name or folder, whatever OutJob wrote it (ours: BOM/..., a student's: Assembly/Bill of Materials-X.xlsx)."""
    import outputs_check
    return outputs_check.is_bom_path(path)       # one classifier for the BOM fallback and the outputs check


def _bom_into_outputs(project, roots, written):
    """Altium's BOM output writes nothing on a machine without Excel (the OutJob's BOM folder stayed empty, T23): when no BOM
    file came out of this run, the advisor's own JLC BOM (the one Export writes) goes into the empty BOM folder Altium made, else
    into a BOM folder beside the files this run wrote. Returns (files added, warnings); never raises: a BOM that cannot be made
    is a warning, not a reason to fail the outputs."""
    if any(_is_bom(f) for f in written):
        return [], []
    try:
        from skills import export_bom
        res = export_bom.export(project, "jlc")
        if not res.get("lines"):
            return [], ["Altium wrote no BOM and the project's BOM has no lines to export."]
        src = pathlib.Path(res["file"])
        src = src if src.is_absolute() else workspace.home() / src
        empty = [d for root in roots for d in pathlib.Path(root).rglob("*")
                 if d.is_dir() and d.name.lower() == "bom" and BACKUP_DIR not in (x.lower() for x in d.parts) and not any(d.iterdir())]
        here = pathlib.Path(os.path.commonpath([str(pathlib.Path(f).parent) for f in written])) if written else pathlib.Path(roots[0])
        if here.name.lower() in ("gerber", "nc drill", "pick place", "bom"):          # the run's own output-type folder: go up one
            here = here.parent
        dest = (empty[0] if empty else here / "BOM") / src.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        note = (f"Altium wrote no BOM, so {dest.parent.name}/{dest.name} is the advisor's JLC BOM (the one Export writes)"
                + (f"; {len(res['needs_lcsc'])} line(s) have no LCSC number ({', '.join(res['needs_lcsc'][:5])}): run Check stock"
                   if res.get("needs_lcsc") else "") + "." + (" " + res["left_out_text"] if res.get("left_out_text") else ""))
        return [str(dest)], [note]
    except Exception as exc:
        return [], [f"Altium wrote no BOM and the advisor's could not be made ({type(exc).__name__}: {exc}). Export it on the BOM page."]


def open_project(project):
    prj = _linked(project)
    run_commands([("PROJECT", str(prj))])
    return {"project_file": str(prj)}


def create(project):
    """new-project + skeleton: what the Create button and the agent's altium.create_project run."""
    res = new_project(project)
    try:
        res["skeleton"] = skeleton(project)
    except (BridgeError, AltiumReadError) as exc:
        # the project exists and is linked by now: report the skeleton as a warning, it can be redrawn alone
        res["skeleton_error"] = f"The project was created, but its title block and frames were not drawn: {exc}"
    return res


# ---------------------------------------------------------------- the project library

TEMPLATES = BRIDGE_DIR / "templates"
TEMPLATE_SYMBOL = "__ADVISOR_TEMPLATE__"                 # the dummy part each template library holds; removed after the real ones are in
TEMPLATE_FOOTPRINT = "__ADVISOR_TEMPLATE__"
LIB_INPUTS = ("bom-log.jsonl", "supply-log.jsonl")      # (and netlist/): what partlib.prepare reads

KEEPOUT_LAYER_CODE = 56
CAPS_SPEC = ["FPLIB|<PCBLIB>", "FOOTPRINT|CAPS_TEST|capability probe of the advisor (scratch library, never installed)",
             "PAD|1|0|0|0|Top Layer|1|0|0|0|0|40|40|1|",
             "PAD||200|0|0|Multi-Layer|0|125.984|0|0|0|125.984|125.984|1|",            # an unplated hole (a mounting hole)
             "PAD||400|0|0|Multi-Layer|0|40|2|120|0|120|80|1|",                        # a slotted unplated hole
             "REGION|Keep-Out Layer|0|-100|-100|100|-100|100|100|-100|100",
             "TRACK|-100|-100|100|-100|10|Keep-Out Layer", "TRACK|100|-100|100|100|10|Keep-Out Layer",
             "TRACK|100|100|-100|100|10|Keep-Out Layer", "TRACK|-100|100|-100|-100|10|Keep-Out Layer"]


def _script_hash():
    import hashlib
    h = hashlib.sha256()
    for name in SCRIPT_FILES:
        f = BRIDGE_DIR / name
        h.update(name.encode("ascii") + b"\x00" + (f.read_bytes() if f.is_file() else b"") + b"\x00")
    return h.hexdigest()[:12]


def capabilities_path():
    return stage_root().parent / "capabilities.json"


def capabilities(force=False, runner=None, cache=None):
    """What this Altium and this script can do with the mechanical footprints (holes, keep-outs), found out by a probe, not assumed:
    a scratch PcbLib with one footprint holding a Keep-Out layer region and tracks, an unplated hole and a slotted hole is made by the
    existing FPBATCH, saved, and read back with read_pcblib. Cached per script hash in `cache` (default: next to the staged scripts):
    the probe runs once for a script version, `force` runs it again.
    Returns {"pas_hash", "checked_at", "keepout_layer": bool, "npth": bool, "slot": None (the reader does not tell a slot: look in
    Altium), "problems": [str], "cached": bool}. A keepout_layer of False means the Keep-Out layer name did not take: the caller
    keeps the keep-out in the placer / router / pour only (Python side) and says so. Raises BridgeError when Altium cannot be run."""
    import tempfile
    cache = pathlib.Path(cache) if cache else capabilities_path()
    h = _script_hash()
    if not force:
        try:
            got = json.loads(cache.read_text(encoding="utf-8"))
            if got.get("pas_hash") == h:
                return dict(got, cached=True)
        except (OSError, ValueError):
            pass
    run = runner or run_commands
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="advisor-caps-"))
    problems = []
    try:
        lib = tmp / "caps.PcbLib"
        shutil.copyfile(TEMPLATES / "Template.PcbLib", lib)
        spec = tmp / "caps_spec.txt"
        _write_ansi(spec, "\r\n".join(CAPS_SPEC).replace("<PCBLIB>", str(lib)) + "\r\n")
        run([("FPBATCH", str(lib), str(spec)), ("SAVELIB", str(lib), "PcbLib")], stall_timeout=120, total_timeout=300)
        fp = next((f for f in read_pcblib(lib)["footprints"] if f["name"] == "CAPS_TEST"), None)
        if fp is None:
            problems.append("the probe footprint is not in the scratch library")
            keepout = npth = False
        else:
            keepout = fp.get("layers", {}).get(KEEPOUT_LAYER_CODE, 0) >= 5
            npth = any(p.get("hole", 0) > 0 and p.get("plated") is False for p in fp["pads"])
            if not keepout:
                problems.append("objects on 'Keep-Out Layer' did not arrive on the keep-out layer")
            if not npth:
                problems.append("an unplated hole did not arrive unplated")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    res = {"pas_hash": h, "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "keepout_layer": keepout, "npth": npth, "slot": None,
           "problems": problems}
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(res, indent=1), encoding="utf-8")
    except OSError:
        pass
    return dict(res, cached=False)


def _capabilities_notice(project):
    """A line for the library build when the project holds holes / keep-outs (or a radio module's antenna keep-out) and the probe found
    that Altium does not keep them; "" otherwise. A probe that cannot run is a line too: never assumed fine."""
    try:
        needs = bool(partlib_mech.mech_specs(project)) or any((e or {}).get("rf", {}).get("keepout_box")
                                                              for e in store.library_manifest(project).values())
    except Exception:                       # noqa: BLE001
        needs = False
    if not needs:
        return ""
    try:
        caps = capabilities()
    except (BridgeError, AltiumReadError, OSError) as exc:
        return f"Could not check that Altium keeps keep-out and unplated-hole objects in a footprint ({exc}): look at them in the PcbLib."
    return keepout_notice(caps)


def keepout_notice(caps):
    """What the keep-outs protect, said exactly, from a capabilities() answer: "" when Altium keeps them. When the Keep-Out layer did not
    take, they are not objects of the PcbLib / PcbDoc: this program's placer, router and ground pour still keep the confirmed
    keep-out rectangles and a radio module's antenna area clear (they are passed to them directly); Altium's own checks, its
    autorouter and anything the student draws or moves by hand are not stopped."""
    out = []
    if not caps.get("keepout_layer", True):
        out.append("Altium did not keep objects on the Keep-Out layer in a footprint, so the keep-outs (confirmed constraints, a radio "
                   "module's antenna area) are not objects of the library or the board. Protected: this program's placer, router and "
                   "ground pour keep those rectangles clear (checked after the route). Not protected: Altium's own design rule check, "
                   "its autorouter, and anything moved or routed by hand. Look at the PcbLib.")
    if not caps.get("npth", True):
        out.append("Altium did not keep an unplated mounting hole unplated in a footprint: look at the holes in the PcbLib.")
    if not out and caps.get("problems"):
        out.append("Altium did not keep these in a footprint (" + "; ".join(caps["problems"]) + "). Look at the PcbLib.")
    return " ".join(out)


def capabilities_cached():
    """The saved capabilities() answer for this script version, or None (never runs Altium)."""
    try:
        got = json.loads(capabilities_path().read_text(encoding="utf-8"))
        return got if got.get("pas_hash") == _script_hash() else None
    except (OSError, ValueError):
        return None


def _rotate_box(box, rot, bottom, x, y):
    """A footprint-frame box [x0, y0, x1, y1] on a component at (x, y) turned `rot` degrees counter-clockwise (mirrored in x when it is
    on the bottom layer), as a board-frame box."""
    import math
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    pts = []
    for px, py in ((box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3])):
        px = -px if bottom else px
        pts.append((x + px * c - py * s, y + px * s + py * c))
    xs, ys = [q[0] for q in pts], [q[1] for q in pts]
    return [round(min(xs), 3), round(min(ys), 3), round(max(xs), 3), round(max(ys), 3)]


def python_keepouts(project, doc, outline):
    """[[x0, y0, x1, y1]] mm: the keep-out areas this program holds itself, as obstacles for the router and the pour whatever Altium
    keeps: the student's CONFIRMED keep-out constraints (board mm from the outline) and the antenna keep-out of every radio module on
    the board (library manifest `rf.keepout_box`, placed with the component's position, rotation and side)."""
    import constraints
    rects = []
    try:
        items = constraints.confirmed(store.load_idea(project))
        if items:
            plan = constraints.plan_for_board(items, outline, *constraints.known_refs(project), size=_board_size(project))
            rects += [k["rect"] for k in plan["keepouts"]]
    except Exception:                       # noqa: BLE001 - a constraint that cannot be read is a missing protection, said by the notice
        pass
    try:
        man = store.library_manifest(project)
        by_ref = {r: l["key"] for l in store.bom_lines(project) for r in (l.get("refs") or [])}
        for c in doc.get("components", []):
            box = ((man.get(by_ref.get(c.get("ref"))) or {}).get("rf") or {}).get("keepout_box")
            if box:
                rects.append(_rotate_box(box, float(c.get("rotation") or 0), str(c.get("layer") or "").lower().startswith("bottom"),
                                         c["x_mm"], c["y_mm"]))
    except Exception:                       # noqa: BLE001
        pass
    return rects


def library_paths(project):
    """Where the project's Altium library goes: <altium project folder>/Library/<Project>-Lib.*"""
    prj = _linked(project)
    name = f"{_file_name(prj.stem, 'Project')}-Lib"
    folder = prj.parent / "Library"
    return {"prj": prj, "name": name, "folder": folder, "schlib": folder / f"{name}.SchLib",
            "pcblib": folder / f"{name}.PcbLib", "libpkg": folder / f"{name}.LibPkg", "d3": folder / "3D",
            "intlib": folder / f"Project Outputs for {name}" / f"{name}.IntLib"}


def library_stale(project):
    """True when library/build is missing, was made by other converter code, or is older than the BOM, a netlist sheet or
    a vendor zip (one in Sources, or a Downloads zip carrying a BOM line's MPN), or a stock check changed a line's LCSC code."""
    lib = partlib.library_dir(project)
    man = lib / "manifest.json"
    if not man.is_file() or not (lib / "build" / "parts.json").is_file():
        return True
    try:
        if (lib / "converter.txt").read_text(encoding="utf-8").strip() != partlib.converter_fingerprint():
            return True
    except OSError:
        return True
    try:                                    # the holes / keep-outs of the confirmed constraints are part of the library
        if (lib / "mech.sig").read_text(encoding="utf-8").strip() != partlib_mech.mech_signature(project):
            return True
    except OSError:
        if partlib_mech.mech_specs(project):
            return True
    pd = store.pdir(project)
    inputs = [pd / n for n in LIB_INPUTS] + (sorted((pd / "netlist").rglob("*")) if (pd / "netlist").is_dir() else [])
    since = man.stat().st_mtime
    if partlib.vendor_zip_newer(project, since):
        return True
    newer = [f for f in inputs if f.is_file() and f.stat().st_mtime > since]
    if any(f.name != "supply-log.jsonl" for f in newer):
        return True
    if not newer:
        return False
    return partlib_order.supply_codes_changed(project)      # a stock check is stale only when it changed a line's LCSC code


def _spec_lines(path):
    try:
        return pathlib.Path(path).read_text(encoding="cp1252", errors="replace").splitlines()
    except OSError:
        return []


def spec_symbols(path):
    """{symbol: [(pin number, name, type)]} of a symbols_spec.txt"""
    out, cur = {}, None
    for ln in _spec_lines(path):
        f = ln.split("|")
        if f[0] == "SYMBOL":
            cur = out.setdefault(f[1], [])
        elif f[0] == "PIN" and cur is not None:
            cur.append((f[1], f[2], f[3].replace("eElectric", "")))
    return out


def spec_footprints(path):
    """{footprint: pad count} of a footprints_spec.txt"""
    out, cur = {}, None
    for ln in _spec_lines(path):
        f = ln.split("|")
        if f[0] == "FOOTPRINT":
            cur = f[1]
            out[cur] = 0
        elif f[0] == "PAD" and cur is not None:
            out[cur] += 1
    return out


def check_ansi(lp, build):
    """Refuse, with the offending text, what Altium would receive as '?'. A path goes to Altium inside the request, which
    is plain ASCII; the spec files are read as Windows ANSI (cp1252), so a Hebrew name or a Chinese description cannot go in."""
    bad = []
    for label, path in (("the Altium project path", lp["prj"]), ("the library folder", lp["folder"])):
        if not str(path).isascii():
            bad.append(f"{label} {path} has letters outside plain ASCII")
    for name, enc in (("symbols_spec.txt", "cp1252"), ("footprints_spec.txt", "cp1252"), ("links.txt", "utf-8"), ("props.txt", "utf-8")):
        f = build / name
        if not f.is_file():
            continue
        try:
            text = f.read_bytes().decode(enc)
            text.encode("cp1252")
        except UnicodeError as exc:
            bad.append(f"{name} has text that is not Windows (cp1252) text: {str(exc)[:80]}")
    try:
        parts = json.loads((build / "parts.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        parts = {}
    texts = [(f"parameter {k} of {n}", str(v)) for n, s in parts.get("symbols", {}).items() for k, v in s.get("params", {}).items()]
    texts += [("footprint name", n) for n in parts.get("footprints", {})] + [("symbol name", n) for n in parts.get("symbols", {})]
    for label, text in texts:
        try:
            text.encode("cp1252")
        except UnicodeEncodeError as exc:
            bad.append(f"{label} has {exc.object[exc.start]!r}: {text[:60]!r}")
    if bad:
        raise BridgeError("Altium's library scripts can only read Windows (cp1252) text and an ASCII path, so I did not "
                          "build: " + "; ".join(bad[:6]) + ". Rename it, or move the Altium project to a plain-letter folder.")


def _write_ansi(path, text):
    pathlib.Path(path).write_bytes(text.encode("cp1252", "replace"))


def library_files(project, lp):
    """Write the spec files Altium reads (real paths in; single backslashes) into library/build/altium/.
    Returns (paths, expected) where expected describes what the finished library must hold."""
    lib = partlib.library_dir(project)
    build = lib / "build"
    out = build / "altium"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    parts = json.loads((build / "parts.json").read_text(encoding="utf-8"))
    sym_spec = (build / "symbols_spec.txt").read_text(encoding="cp1252", errors="replace")
    fp_spec = (build / "footprints_spec.txt").read_text(encoding="cp1252", errors="replace")
    _write_ansi(out / "symbols_spec.txt", sym_spec.replace("<SCHLIB>", str(lp["schlib"])))
    _write_ansi(out / "footprints_spec.txt", fp_spec.replace("<PCBLIB>", str(lp["pcblib"])))
    _write_ansi(out / "links.txt", (build / "links.txt").read_text(encoding="utf-8"))
    _write_ansi(out / "props.txt", (build / "props.txt").read_text(encoding="utf-8"))
    params = [f"{n}|{k}|{v}" for n, s in parts["symbols"].items() for k, v in s.get("params", {}).items() if str(v).strip()]
    _write_ansi(out / "params.txt", "\r\n".join(params) + "\r\n")
    links = dict(ln.split("=", 1) for ln in (build / "links.txt").read_text(encoding="utf-8").splitlines() if "=" in ln)
    props = dict(ln.split("=", 1) for ln in (build / "props.txt").read_text(encoding="utf-8").splitlines() if "=" in ln)
    lp["d3"].mkdir(parents=True, exist_ok=True)
    attach = [f"LIB|{lp['pcblib']}"]
    bodies = {}
    for fpn, info in parts["footprints"].items():
        steps = [lib / s for s in info.get("steps", []) if (lib / s).is_file()]
        if not steps or info.get("errors"):         # a footprint in error is not in the spec: no body to attach to it
            continue
        dest = lp["d3"] / f"{_file_name(fpn, 'model')}.step"
        shutil.copyfile(steps[0], dest)
        m = info.get("model") or {}
        seat = m.get("seat", 0 if info.get("tht") else 1)
        attach.append("FP|" + "|".join(str(v) for v in (fpn, dest, m.get("rx", 0), m.get("ry", 0), m.get("rz", 0),
                                                        m.get("dx", 0), m.get("dy", 0), seat)))
        bodies[fpn] = dest.name
    _write_ansi(out / "attach3d.txt", "\r\n".join(attach) + "\r\n")
    _write_ansi(out / "hide.txt", "".join(f"{n}=1\r\n" for n, s in parts["symbols"].items() if s.get("hide_pin_names")))
    pins = spec_symbols(out / "symbols_spec.txt")
    expected = {"symbols": {n: {"pins": pins.get(n, []), "footprint": links.get(n, ""), "props": props.get(n, "|").split("|", 1),
                                "hide": bool(s.get("hide_pin_names")), "params": s.get("params", {})}
                            for n, s in parts["symbols"].items()},
                "footprints": spec_footprints(out / "footprints_spec.txt"), "bodies": bodies}
    return {k: out / v for k, v in (("symbols", "symbols_spec.txt"), ("footprints", "footprints_spec.txt"), ("links", "links.txt"),
                                    ("props", "props.txt"), ("params", "params.txt"), ("attach", "attach3d.txt"),
                                    ("hide", "hide.txt"))}, expected


def write_libpkg(lp):
    text = ("[Design]\r\nVersion=1.0\r\nOutputPath=\r\n\r\n"
            f"[Document1]\r\nDocumentPath={lp['schlib'].name}\r\n\r\n[Document2]\r\nDocumentPath={lp['pcblib'].name}\r\n")
    lp["libpkg"].write_bytes(text.encode("ascii"))


def verify_library_files(lp, expected):
    """Read the SchLib and PcbLib back. Returns (problems [str], per-symbol problems {symbol: [str]},
    per-footprint problems, counts)."""
    problems, per_symbol, per_fp = [], {}, {}
    sch, pcb = read_schlib(lp["schlib"]), read_pcblib(lp["pcblib"])
    syms = {s["name"]: s for s in sch["symbols"]}
    fps = {f["name"]: f for f in pcb["footprints"]}

    def sym_bad(name, msg):
        per_symbol.setdefault(name, []).append(msg)

    def fp_bad(name, msg):
        per_fp.setdefault(name, []).append(msg)
    for extra in sorted(set(syms) - set(expected["symbols"])):
        problems.append(f"the SchLib holds a symbol that is not ours: {extra}")
    for extra in sorted(set(fps) - set(expected["footprints"])):
        problems.append(f"the PcbLib holds a footprint that is not ours: {extra}")
    for name, want in expected["symbols"].items():
        got = syms.get(name)
        if got is None:
            sym_bad(name, "not in the SchLib")
            continue
        pins = [(p["number"], p["name"], p["electrical"]) for p in got["pins"]]
        if sorted(pins) != sorted(want["pins"]):
            sym_bad(name, f"pins differ: {len(pins)} in the library, {len(want['pins'])} in the spec")
        if want["hide"] and any(p["show_name"] for p in got["pins"]):
            sym_bad(name, "pin names are still shown on a 2-pin part" if len(want["pins"]) == 2
                    else "pin names are still shown although they do not fit in the symbol body")
        prefix, comment = (want["props"] + ["", ""])[:2]
        if got["designator"] != f"{prefix}?":
            sym_bad(name, f"designator {got['designator']!r}, expected {prefix}?")
        if got["comment"] != comment:
            sym_bad(name, f"comment {got['comment']!r}, expected {comment!r}")
        for k, v in want["params"].items():
            if str(v).strip() and got["params"].get(k) != str(v).strip():
                sym_bad(name, f"parameter {k} is {got['params'].get(k)!r}, expected {v!r}")
        if got["footprints"] != [want["footprint"]]:
            sym_bad(name, f"footprint link {got['footprints']}, expected {want['footprint']}")
        elif want["footprint"] not in fps:
            sym_bad(name, f"linked footprint {want['footprint']} is not in the PcbLib")
        if got["pinned_paths"]:
            sym_bad(name, "the footprint link is pinned to a file path")
    for name, pads in expected["footprints"].items():
        got = fps.get(name)
        if got is None:
            fp_bad(name, "not in the PcbLib")
            continue
        if len(got["pads"]) != pads:
            fp_bad(name, f"{len(got['pads'])} pads in the library, {pads} in the spec")
        if any(pad["layer"] == 0 for pad in got["pads"]):
            fp_bad(name, "a pad is on no layer")
        want_bodies = 1 if name in expected["bodies"] else 0
        if len(got["bodies"]) != want_bodies:
            fp_bad(name, f"{len(got['bodies'])} 3D bodies, expected {want_bodies}")
    counts = {"symbols": len(syms), "footprints": len(fps), "pads": sum(len(f["pads"]) for f in fps.values()),
              "bodies": sum(len(f["bodies"]) for f in fps.values()), "models": len(pcb["models"])}
    return problems, per_symbol, per_fp, counts


def _mark_built(project, expected, per_symbol, per_fp, ok_intlib):
    """Write `built` (and `built_issues`) on every line of library/manifest.json; returns {line: bool}."""
    path = partlib.library_dir(project) / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    res = {}
    for key, e in manifest.items():
        sym, fp = e.get("symbol"), e.get("footprint")
        issues = []
        if not sym:
            issues.append("no symbol was made for this line")
        else:
            issues += per_symbol.get(sym, []) + per_fp.get(fp, [])
            if sym not in expected["symbols"]:
                issues.append("not part of this build")
            if not ok_intlib:
                issues.append("the IntLib was not compiled and installed")
        e["built"] = not issues
        if issues:
            e["built_issues"] = issues
        else:
            e.pop("built_issues", None)
        res[key] = e["built"]
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return res


def _check_unlocked(files):
    """Refuse up front when a library file cannot be opened for writing (Altium still holds it): saying so now beats
    a script that stalls for minutes on it."""
    for f in files:
        if pathlib.Path(f).is_file():
            try:
                with open(f, "r+b"):
                    pass
            except OSError as exc:
                raise BridgeError(f"{f} is locked ({exc.strerror or exc}): Altium still has the library open or installed. "
                                  "Close the library project in Altium (or restart Altium) and build again.") from exc


def _mark_failed(project, reason):
    """Every line of the manifest becomes built: false after a build that did not finish (a stale true would lie)."""
    path = partlib.library_dir(project) / "manifest.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    for e in manifest.values():
        if isinstance(e, dict):
            e["built"] = False
            e["built_issues"] = [reason]
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _restore_library(project, lp, backup):
    """After a failed build: put the previous SchLib, PcbLib, LibPkg, IntLib and 3D models back from the backup and install
    the old IntLib again. Without a backup (a first build) the half-made files are removed. Returns a sentence for the error."""
    try:
        run_commands([("LIBCLOSE", str(lp["libpkg"]), str(lp["schlib"]), str(lp["pcblib"]), str(lp["intlib"]))])
    except BridgeError:
        pass
    try:
        for step in (lp["d3"].glob("*.step") if lp["d3"].is_dir() else []):
            step.unlink()
        if not backup:
            for k in ("schlib", "pcblib", "libpkg", "intlib"):
                lp[k].unlink(missing_ok=True)
            return "There was no earlier library, so the half-made files were removed."
        for f in pathlib.Path(backup).iterdir():
            dest = {".schlib": lp["schlib"], ".pcblib": lp["pcblib"], ".libpkg": lp["libpkg"], ".intlib": lp["intlib"]}.get(f.suffix.lower())
            if f.suffix.lower() == ".step":
                dest = lp["d3"] / f.name
            if dest is not None:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)
    except OSError as exc:
        return f"The earlier library could not be put back ({exc}); it is in {backup}."
    if (pathlib.Path(backup) / lp["intlib"].name).is_file():
        try:
            run_commands([("INSTALL", str(lp["intlib"]))])
            return "The earlier library was put back and installed again."
        except BridgeError as exc:
            return f"The earlier library files were put back but its IntLib is NOT installed in Altium ({exc})."
    return "The earlier library files were put back."


def _create_libraries(project, lp):
    """Steps 1 and 2 of build_library; safe to run again (every run starts from the templates).
    Returns (expected, per-symbol problems, per-footprint problems, other problems, counts)."""
    # 1. nothing of the old library may stay open or installed in Altium; then the files are ours to replace
    lp["folder"].mkdir(parents=True, exist_ok=True)
    run_commands([("LIBCLOSE", str(lp["libpkg"]), str(lp["schlib"]), str(lp["pcblib"]), str(lp["intlib"]))])
    _check_unlocked([lp["intlib"], lp["schlib"], lp["pcblib"], lp["libpkg"]])
    for old_step in (lp["d3"].glob("*.step") if lp["d3"].is_dir() else []):
        old_step.unlink()
    shutil.copyfile(TEMPLATES / "Template.SchLib", lp["schlib"])
    shutil.copyfile(TEMPLATES / "Template.PcbLib", lp["pcblib"])
    files, expected = library_files(project, lp)
    write_libpkg(lp)
    # 2. footprints, symbols, links, properties, pin names, 3D bodies; then read the two files back
    cmds = [("FPBATCH", str(lp["pcblib"]), str(files["footprints"])),
            ("FPREMOVE", str(lp["pcblib"]), TEMPLATE_FOOTPRINT), ("SAVELIB", str(lp["pcblib"]), "PcbLib"),
            ("SYMBATCH", str(lp["schlib"]), str(files["symbols"])),
            ("SYMREMOVE", str(lp["schlib"]), TEMPLATE_SYMBOL),
            ("SYMLINK", str(lp["schlib"]), str(files["links"])),
            ("SYMPROPS", str(lp["schlib"]), str(files["props"])),
            ("SYMPARAMS", str(lp["schlib"]), str(files["params"])),
            ("HIDEPINS", str(lp["schlib"]), str(files["hide"])), ("SAVELIB", str(lp["schlib"]), "SchLib")]
    if expected["bodies"]:
        cmds.append(("ATTACH3D", str(files["attach"])))
    run_commands(cmds, stall_timeout=120, total_timeout=900)
    return (expected, *verify_library_files(lp, expected))


def build_library(project, fetch=True):
    """Build the project's Altium library from library/build and install the IntLib. Returns the result dict."""
    lp = library_paths(project)
    prj = lp["prj"]
    prepared = False
    if library_stale(project) or partlib_order.params_stale(project):      # an order-only swap leaves Altium's parameters old
        partlib.prepare(project, fetch=fetch)
        prepared = True
    build = partlib.library_dir(project) / "build"
    check_ansi(lp, build)
    syms, _fps = spec_symbols(build / "symbols_spec.txt"), spec_footprints(build / "footprints_spec.txt")
    if not syms or not (build / "parts.json").is_file():
        raise BridgeError("The library data has no symbols to build. Prepare the part library first and fix its issues.")
    old = [lp[k] for k in ("schlib", "pcblib", "libpkg", "intlib")] + (sorted(lp["d3"].glob("*.step")) if lp["d3"].is_dir() else [])
    backup = _backup(prj, old)
    t0 = time.time() - 2
    marked = False
    try:
        for attempt in (1, 2):         # Altium sometimes stops in the middle of a batch; a rebuild from the templates is safe
            try:
                expected, problems, per_symbol, per_fp, counts = _create_libraries(project, lp)
                break
            except BridgeError as exc:
                if attempt == 2 or "stopped in the middle" not in str(exc):
                    raise
                _log(project, "build-library", retry=str(exc))
        if problems or per_symbol or per_fp:
            _mark_built(project, expected, per_symbol, per_fp, False)
            marked = True
            detail = problems + [f"{n}: {'; '.join(m)}" for n, m in {**per_symbol, **per_fp}.items()]
            raise BridgeError("The library was built but the files read back wrong, so it was not compiled: "
                              + " | ".join(detail[:8]))
        # 3. compile and install; then the IntLib file and Altium's list of installed libraries are checked. The first compile
        #    of a new project's library once stopped on an Altium error box (Blinker 555, 15/11) and the same build passed when
        #    run again; compiling only reads the saved libraries, so it is run once more
        for attempt in (1, 2):
            try:
                log = run_commands([("COMPILE", str(lp["libpkg"]), str(lp["intlib"])), ("CHECKINST", str(lp["intlib"]))],
                                   stall_timeout=180, total_timeout=900)
                break
            except BridgeError as exc:
                if attempt == 2 or "stopped in the middle" not in str(exc):
                    raise
                _log(project, "build-library", retry=f"compile: {exc}")
    except (BridgeError, AltiumReadError, OSError) as exc:
        if not marked:
            _mark_failed(project, f"the build did not finish: {exc}")
        note = _restore_library(project, lp, backup)
        _log(project, "build-library", error=str(exc), backup=backup, restored=note)
        raise BridgeError(f"{exc} {note}") from exc
    installed = any(ln.startswith("INSTALLED yes") for ln in log)
    intlib = lp["intlib"]
    fresh = intlib.is_file() and intlib.stat().st_size > 0 and intlib.stat().st_mtime >= t0
    issues = []
    if not fresh:
        issues.append(f"The IntLib {intlib} was not written by this build (an installed library can stay locked; "
                      "restart Altium and build again).")
    if not installed:
        issues.append("Altium does not list the IntLib as installed.")
    caps_notice = _capabilities_notice(project)
    notices = ([caps_notice] if caps_notice else []) + [f"Another installed library had the same name and was removed from Altium's installed list: "
               f"{ln[len(SAME_NAME):].strip()} (Altium matches libraries by file name)."
               for ln in log if ln.startswith(SAME_NAME)]
    # the installed list is not what the schematic ECO reads: the IntLib must be a library of the Altium project itself
    in_project = add_intlib_to_project(prj, intlib) if fresh else False
    if not in_project:
        issues.append(f"The project library is not part of {prj.name}: the ECO will say Footprint Not Found. "
                      f"Add {intlib} to the project in Altium (Projects panel, right-click the project, Add Existing to Project) and save it.")
    built = _mark_built(project, expected, {}, {}, fresh and installed)
    if fresh and installed:
        partlib_order.clear_params_stale(project)
    res = {"schlib": str(lp["schlib"]), "pcblib": str(lp["pcblib"]), "libpkg": str(lp["libpkg"]), "intlib": str(intlib),
           "folder_3d": str(lp["d3"]), "counts": counts, "intlib_fresh": fresh, "installed": installed,
           "in_project": in_project,
           "built": sum(built.values()), "lines": len(built), "prepared": prepared, "backup": backup, "issues": issues,
           "notices": notices}
    _log(project, "build-library", **res)
    if issues:
        raise BridgeError(" ".join(issues))
    return res


# ---------------------------------------------------------------- CLI

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="op", required=True)
    sub.add_parser("status")
    for op in ("new-project", "add-pcb", "open", "import-rules", "run-outjob", "build-library"):
        sub.add_parser(op).add_argument("project")
    p = sub.add_parser("add-sheet")
    p.add_argument("project")
    p.add_argument("name")
    p = sub.add_parser("draw-schematic")
    p.add_argument("project")
    p.add_argument("sheet", nargs="?")
    p.add_argument("--replace", action="store_true")
    p = sub.add_parser("skeleton")
    p.add_argument("project")
    p.add_argument("sheet", nargs="?")
    a = ap.parse_args(argv)
    try:
        if a.op == "status":
            res = status()
        elif a.op == "new-project":
            res = create(a.project)
        elif a.op == "add-sheet":
            res = add_sheet(a.project, a.name)
        elif a.op == "add-pcb":
            res = add_pcb(a.project)
        elif a.op == "skeleton":
            res = skeleton(a.project, a.sheet)
        elif a.op == "draw-schematic":
            res = draw_schematic(a.project, a.sheet, a.replace)
        elif a.op == "import-rules":
            res = import_rules(a.project)
        elif a.op == "run-outjob":
            blocked = store.manufacturing_warning(a.project)
            if blocked:
                print(f"Error: {blocked}", file=sys.stderr)
                return 1
            res = run_outjob(a.project)
        elif a.op == "build-library":
            res = build_library(a.project)
        else:
            res = open_project(a.project)
    except (BridgeError, AltiumReadError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
