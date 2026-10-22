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
import partlib_order  # noqa: E402
import project as project_mod  # noqa: E402
import rule_kinds  # noqa: E402
import rules as rules_mod  # noqa: E402
import store  # noqa: E402
import workspace  # noqa: E402
from altium import AltiumReadError, registry  # noqa: E402
from altium.lib import read_pcblib, read_schlib  # noqa: E402
from altium.prjpcb import read_prjpcb as _read_prjpcb  # noqa: E402
from altium.schdoc import read_schdoc  # noqa: E402

BRIDGE_DIR = pathlib.Path(__file__).resolve().parent / "bridge"
SCRIPT_PROJECT = BRIDGE_DIR / "AdvisorBridge.PrjScr"
EXCHANGE = pathlib.Path(os.environ.get("PUBLIC") or r"C:\Users\Public") / "pcb-advisor-bridge"   # the .pas uses the same
TAG = "[advisor]"                       # first word of every text frame we draw; how a re-run finds its own frames
BACKUP_DIR = ".advisor-backup"
MIN_PRJPCB = "[Design]\r\nVersion=1.0\r\n"      # Altium fills in the rest when it saves
_lock = threading.Lock()


class BridgeError(ValueError):      # a ValueError, so apply_actions reports it as a refused action
    pass


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


def _ascii(text):
    """The script reads the request as ANSI text: keep it plain ASCII (a letter that does not fit becomes '?')."""
    return str(text).encode("ascii", "replace").decode("ascii")


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


def run_commands(commands, start_timeout=45, stall_timeout=60, total_timeout=300):
    """Send command lines (tab separated fields) to Altium, wait for DONE. Returns the script's log lines.
    Raises BridgeError with the last step when the script does not start, stops logging or reports an error.
    While the script runs we only look at whether start.flag / end.flag exist and whether log.txt grows."""
    exe = _exe()
    if not SCRIPT_PROJECT.is_file():
        raise BridgeError(f"bridge script missing: {SCRIPT_PROJECT}")
    with _lock:
        EXCHANGE.mkdir(parents=True, exist_ok=True)
        for name in ("response.txt", "log.txt", "start.flag", "end.flag"):
            (EXCHANGE / name).unlink(missing_ok=True)
        body = "\r\n".join("\t".join(_ascii(f) for f in c) for c in commands) + "\r\n"
        (EXCHANGE / "request.txt").write_bytes(body.encode("ascii"))     # bytes: text mode would double the CR on Windows
        cold = not _running()          # Altium has to start first: that takes a while
        for attempt in (1, 2):
            subprocess.Popen(f'"{exe}" -RScriptingSystem:RunScript(ProjectName="{SCRIPT_PROJECT}"|ProcName="AdvisorBridge>Run")')
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
    out = {"windows": sys.platform == "win32", "exe": "", "running": False, "executor": "not tested", "error": ""}
    try:
        out["exe"] = _exe()
    except BridgeError as exc:
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
        raise BridgeError("No Altium project is linked to this project yet. Create one first.")
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


def _find_doc(prj_file, name_or_id, kind=".schdoc"):
    """The project's document that belongs to a sheet id (its name starts with '<id> ') or has exactly that name."""
    summary = read_prjpcb(prj_file)
    for d in summary["documents"]:
        base = pathlib.PureWindowsPath(d).name
        if base.lower().endswith(kind) and (base.lower() == str(name_or_id).lower() or base.startswith(f"{name_or_id} ")):
            return prj_file.parent / pathlib.Path(d.replace("\\", "/"))
    return None


def _doc_key(prj, rel):
    """A PrjPcb DocumentPath as one comparable string: relative to the PrjPcb folder, slashes and case ignored."""
    return os.path.normcase(os.path.normpath(str(prj.parent / pathlib.Path(str(rel).replace("\\", "/")))))


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


def add_sheet(project, name):
    prj = _linked(project)
    fname = _file_name(name, "Sheet")
    fname = fname if fname.lower().endswith(".schdoc") else fname + ".SchDoc"
    target = prj.parent / fname
    if target.exists():
        raise BridgeError(f"{fname} already exists in the Altium project.")
    backup = _backup(prj, [prj])
    run_commands([("PROJECT", str(prj)), ("SCH", str(target)), ("SAVEPRJ", str(prj))])
    if not target.is_file():
        raise BridgeError("Altium ran the script but did not write the sheet. Check Altium for a dialog box.")
    _log(project, "add-sheet", file=str(target), backup=backup)
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
    cmds, todo, existing, new_docs = [("PROJECT", str(prj))], [], [], []
    if planned:
        for sid, title, sh in planned:
            doc = _find_doc(prj, sid)
            if doc is None:
                doc = prj.parent / _sch_name(sid, title)
                new_docs.append(doc)
            else:
                existing.append(doc)
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
    _log(project, "skeleton", sheets=[str(d) for d, _, _ in todo], created=[str(d) for d in new_docs], backup=backup)
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


def draw_schematic(project, sheet=None, replace=False):
    """Draw the netlist sheet(s) of the project in Altium: every part from the project SchLib (pin count checked), a wire stub
    on every connected pin ending in a power port or a net label, a No ERC cross on NC pins. Then the saved SchDoc is read back
    and compared with the netlist. Refuses a sheet that already has components unless replace is true (the old SchDoc is
    copied to .advisor-backup first). The SchDoc comes from the PrjPcb (a new one is added when there is none)."""
    from altium import draw
    from altium.schdoc import read_schdoc
    prj = _linked(project)
    lp = library_paths(project)
    if not lp["schlib"].is_file():
        raise BridgeError("The project library is not built yet: run library.build first, the parts are drawn from it.")
    planned = _sheets(project)
    if sheet is not None:
        planned = [s for s in planned if s[0] == str(sheet)]
    if not planned:
        raise BridgeError("There is no netlist sheet to draw" + (f" (no sheet {sheet})" if sheet is not None else "")
                          + ": write the netlist first (netlist.write).")
    bom_refs = {r for l in store.bom_lines(project) for r in (l.get("refs") or [l["key"]])}
    lib_symbols = {s["name"]: s for s in read_schlib(lp["schlib"])["symbols"]}
    manifest = store.library_manifest(project)
    key = {r: l["key"] for l in store.bom_lines(project) for r in (l.get("refs") or [l["key"]])}
    plans, existing, new_docs = [], [], []
    for sid, title, sh in planned:
        errors, _ = store.check_sheet(sh, bom_refs)
        if errors:
            raise BridgeError(f"Sheet {sid} cannot be drawn: " + "; ".join(errors[:6]))
        doc = _find_doc(prj, sid)
        if doc is None:
            doc = prj.parent / _sch_name(sid, title)
            new_docs.append(doc)
        elif doc.is_file():
            existing.append(doc)
            have = sum(len(read_schdoc(doc).get(k, [])) for k in DRAWN_KINDS)
            if have and not replace:
                raise BridgeError(f"{doc.name} already has {have} objects (parts, wires, labels). I never wipe a drawing: say so if it "
                                  "should be redrawn (replace), the old file is kept in .advisor-backup.")
        plan = draw.plan_sheet(sh, _sheet_symbols(project, sh, lib_symbols), lp["schlib"], doc, replace=replace)
        if plan["errors"]:
            raise BridgeError(f"Sheet {sid} cannot be drawn: " + "; ".join(plan["errors"][:8]))
        plans.append((sid, doc, plan, {r: (manifest.get(key.get(r)) or {}).get("footprint") for r in key}))
    backup = _backup(prj, existing + ([prj] if new_docs else []))
    if existing:        # Altium's own view first: unsaved changes in an open sheet, or anything on it, stop the run before it touches anything
        run_commands([("PROJECT", str(prj))] + [("DRAWCHECK", str(d), "1" if replace else "0") for d in existing])
    cmds = [("PROJECT", str(prj))] + [("SCH", str(d)) for d in new_docs]
    for _, _, plan, _fp in plans:
        cmds += plan["commands"]
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
    problems, warnings, parts, nets = [], [], 0, set()
    for sid, doc, plan, fps in plans:
        warnings += plan["warnings"]
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
    _log(project, "draw-schematic", sheets=[str(d) for _, d, _, _ in plans], parts=parts, nets=len(nets), replace=bool(replace),
         created=[str(d) for d in new_docs], backup=backup, problems=problems, warnings=warnings)
    res = {"sheets": [str(d) for _, d, _, _ in plans], "parts": parts, "nets": sorted(nets), "warnings": warnings,
           "problems": problems, "backup": backup, "created": [str(d) for d in new_docs]}
    if problems:
        raise BridgeError(f"Drawn and saved {parts} parts, but the sheet does not match the netlist: " + "; ".join(problems[:6])
                          + (f" (+{len(problems) - 6} more)" if len(problems) > 6 else ""))
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
    """The batch design rule check text report: {"rules": {rule text: count}, "violations": [message], "unrouted": n, "total": n}."""
    try:
        text = pathlib.Path(path).read_text(encoding="cp1252", errors="replace")
    except OSError:
        return None
    rules, violations = {}, []
    for line in text.splitlines():
        parts = line.split("|")
        if len(parts) == 3 and parts[0].startswith("Rule Violations") and parts[2].strip().isdigit():
            rules[parts[1].strip()] = int(parts[2])
        elif len(parts) >= 4 and parts[1] == "" and parts[2] == "":
            violations.append(f"{parts[0].strip()}: {parts[3].strip()}")
    total = sum(rules.values())
    unrouted = sum(v for k, v in rules.items() if k.startswith("Un-Routed Net"))
    return {"rules": rules, "violations": violations, "unrouted": unrouted, "total": total}


def _netlist_parts(project):
    """[{ref, footprint, symbol, pins}] of every netlist sheet: the footprint and symbol come from the library manifest."""
    manifest = store.library_manifest(project)
    key = {r: l["key"] for l in store.bom_lines(project) for r in (l.get("refs") or [l["key"]])}
    parts, seen = [], set()
    for _sid, _title, sh in _sheets(project):
        for p in sh.get("parts", []):
            if not isinstance(p, dict) or not p.get("ref") or p["ref"] in seen:
                continue
            seen.add(p["ref"])
            m = manifest.get(key.get(p["ref"])) or {}
            parts.append({"ref": p["ref"], "footprint": m.get("footprint") or "", "symbol": m.get("symbol") or "",
                          "lib_ref": m.get("symbol") or "", "pins": p.get("pins", [])})
    return parts


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


def place_on(prj, pcb, pcblib, parts, size=None, clearance_mm=0.0, replace=False, connector_dirs=None, edge_copper_mm=0.3):
    """Place `parts` ([{ref, footprint, lib_ref, pins}]) from the PcbLib on the PcbDoc, create the outline from `size` when the board
    only has the placeholder outline of a new PcbDoc (an outline somebody drew is kept), save, and read the file back.
    Refuses a board that already has parts or copper unless replace is true; the PcbDoc is copied to .advisor-backup first.
    Returns {"placed", "outline", "outline_created", "warnings", "backup", "problems", "drc"}; problems non-empty = placed but
    the saved file does not match the netlist."""
    from altium import layout
    from altium.pcbdoc import read_pcbdoc
    prj, pcb, pcblib = pathlib.Path(prj), pathlib.Path(pcb), pathlib.Path(pcblib)
    if not pcblib.is_file():
        raise BridgeError("The project library is not built yet: run library.build first, the footprints are placed from it.")
    if not parts:
        raise BridgeError("There are no parts in the netlist to place: write the netlist first (netlist.write).")
    bad = layout.text_problems(parts)
    if bad:
        raise BridgeError("; ".join(bad[:6]))
    fps = {f["name"]: f for f in read_pcblib(pcblib)["footprints"]}
    missing = sorted({p["ref"] for p in parts if p.get("footprint") not in fps})
    if missing:
        raise BridgeError(f"No footprint in the project library for {', '.join(missing[:8])}: run library.build first.")
    log = run_commands([("PROJECT", str(prj)), ("PCBCHECK", str(pcb), "1" if replace else "0")])     # Altium's own view first
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
    if placeholder:
        outline = layout.plan_outline(size)
        if outline is None:
            raise BridgeError("The board has no outline yet and the project does not say how big the board is (idea: board size). "
                              "Ask the student for the width and height in mm, or draw the outline in Altium first.")
        create = True
    else:
        outline = [round(v * MM_PER_MIL, 3) for v in info["box_mil"]]
        create = False
    plan = layout.plan_placement(parts, fps, outline, clearance_mm=clearance_mm, connector_dirs=connector_dirs,
                                 edge_copper_mm=edge_copper_mm)
    if plan["errors"]:
        raise BridgeError("The parts cannot be placed: " + "; ".join(plan["errors"][:6]))
    warnings += plan["warnings"]
    backup = _backup(prj, [pcb])
    links = _sch_links(prj)
    parts = [dict(p, uid=links[p["ref"]][0], sheet=links[p["ref"]][1]) if p["ref"] in links else p for p in parts]
    cmds = layout.plan_commands(pcb, outline, create, plan["places"], fps, parts, pcblib, replace=replace)
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
    try:                                                 # the outline Altium really holds, after the save
        after = _pcbcheck_info(run_commands([("PROJECT", str(prj)), ("PCBCHECK", str(pcb), "1")]))
    except BridgeError:
        after = None
    if after is not None:
        got = [v * MM_PER_MIL for v in after["box_mil"]]
        if any(abs(a - b) > 0.05 for a, b in zip(got, outline)) or not after["rect"]:
            problems.append(f"the saved board outline is {[round(v, 2) for v in got]} mm with {after['points']} points, planned {outline}")
    try:
        from checks import board as board_checks
        drills = [f["message"] for f in board_checks.check_drills(saved)]
    except Exception:                                    # a check that cannot run must not hide the placement result
        drills = []
    restored = False
    if problems and backup:
        restored = _restore(prj, pcb, backup)
    return {"placed": [p["ref"] for p in plan["places"]], "outline": outline, "outline_created": create, "warnings": warnings,
            "backup": backup, "problems": problems, "pads": len(saved.get("pads", [])), "restored": restored,
            "places": plan["places"], "drill_findings": drills}


def place_pcb(project, replace=False):
    """altium.place_pcb: the netlist's parts on the project's PcbDoc (footprints from the project PcbLib, linked and netted like
    Update PCB does it), board outline from the idea's board size when the PcbDoc has none yet."""
    prj = _linked(project)
    pcb = _project_pcb(project)
    lp = library_paths(project)
    parts = _netlist_parts(project)
    links = _sch_links(prj)
    undrawn = sorted({p["ref"] for p in parts if p["ref"] not in links})
    if undrawn:                  # parts placed without their schematic link are added a second time by the first Update PCB
        raise BridgeError("The schematic is not drawn in Altium for " + ", ".join(undrawn[:8]) + (" ..." if len(undrawn) > 8 else "")
                          + ": draw it first (altium.draw_schematic, with the student's agreement). A part placed without the link to its "
                          "schematic symbol is duplicated by the first Update PCB. Nothing was changed.")
    res = place_on(prj, pcb, lp["pcblib"], parts, size=_board_size(project), clearance_mm=_clearance_mm(project), replace=replace)
    _log(project, "place-pcb", pcb=str(pcb), parts=len(res["placed"]), outline=res["outline"], replace=bool(replace),
         backup=res["backup"], problems=res["problems"], warnings=res["warnings"])
    res["warnings"] = res["warnings"] + [f"drill check: {m}" for m in res["drill_findings"][:6]] +         [f"design vs board: {m}" for m in design_problems(project)[:6]]
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
    return problem.startswith("not routed") or "open nets" in problem or "un-routed connection" in problem


def route_on(prj, pcb, replace=False, seconds=120, keep_partial=False, pitch=0.1, pour=True):
    """Route the placed PcbDoc with the agent's own router (scripts/altium/route.py; Altium's autorouter cannot be run from a
    script), draw the tracks and vias, save, then check the saved file two ways: our own unrouted() on the read-back file and
    Altium's batch design rule check (no new clearance / short / width / un-routed violations over the check made before routing).
    A net that cannot be routed is reported with the reason; without keep_partial nothing is drawn then. Any failed check puts the
    backed-up file back. Returns {routed, failed, tracks, vias, problems, restored, backup, drc_before, drc_after, summary, ...}."""
    import tempfile
    from altium import layout, route
    from altium.pcbdoc import read_pcbdoc
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
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="advisor-drc-"))
    drc_before = _drc_counts(run_drc(prj, pcb, tmp / "before.txt"))
    plan = route.plan_routes(doc, box, rules, pitch=pitch, seconds=seconds)
    pour_net = route.pour_net_for(doc) if pour else None
    res = {"routed": plan["routed"], "failed": plan["failed"], "tracks": plan["stats"]["tracks"], "vias": plan["stats"]["vias"],
           "stats": plan["stats"], "rules": {k: v for k, v in rules.items() if k != "net_width"}, "backup": "", "problems": [],
           "restored": False, "drc_before": drc_before, "drc_after": {}, "drills": [], "written": False, "pour": pour_net}
    if plan["failed"] and not keep_partial:
        res["summary"] = "no tracks drawn: could not route " + "; ".join(f"{n} ({why})" for n, why in plan["failed"])
        return res
    bad = route.violations(doc, plan["items"], rules, box)          # our own exact check of what we are about to draw
    if bad:
        res["problems"] = ["the route would break the rules (nothing drawn): " + "; ".join(bad[:5])]
        res["summary"] = res["problems"][0]
        return res
    res["backup"] = _backup(prj, [pcb])
    try:
        run_commands([("PROJECT", str(prj))] + route.route_commands(pcb, plan["items"], replace, pour_net=pour_net, box=box,
                                                                     edge=rules["edge"]), total_timeout=1500)
    except BridgeError as exc:
        raise BridgeError(str(exc) + _revert(prj, pcb, "routed")) from exc
    res["written"] = True
    probs = []
    open_nets = []
    after = {}
    try:        # whatever goes wrong from here on (read back, reload, the check itself) puts the backed-up board back
        saved = read_pcbdoc(pcb, geometry=True)
        open_nets = layout.unrouted(saved)
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
    res["drc_after"] = after
    if after.get("Un-Routed Net", 0) > 0:
        probs.append(f"Altium's design rule check reports {after['Un-Routed Net']} un-routed connections")
    for w in ("Clearance Constraint", "Short-Circuit", "Width Constraint"):
        if after.get(w, 0) > drc_before.get(w, 0):
            probs.append(f"Altium's design rule check reports {after[w] - drc_before.get(w, 0)} new {w} violations "
                         f"({'; '.join(v for v in drc['violations'] if w.split()[0].lower() in v.lower())[:300]})")
    try:
        from checks import board as board_checks
        res["drills"] = [f["message"] for f in board_checks.check_drills(saved)]
    except Exception:
        pass
    if plan["failed"]:
        probs.append("not routed: " + "; ".join(f"{n} ({why})" for n, why in plan["failed"]))
    res["problems"] = probs
    if probs and not (keep_partial and all(_partial_ok(p) for p in probs)):
        res["restored"] = _restore(prj, pcb, res["backup"])
    res["summary"] = (f"{len(plan['routed'])} nets routed with {res['tracks']} tracks and {res['vias']} vias"
                      + (f", {pour_net} poured on the bottom layer" if pour_net else "") + f", saved; own check: "
                      f"{'no open nets' if not open_nets else str(len(open_nets)) + ' open nets'}; Altium DRC: "
                      f"{after.get('Un-Routed Net', 0)} un-routed, {after.get('Clearance Constraint', 0)} clearance, "
                      f"{after.get('Short-Circuit', 0)} short ({drc_before.get('Clearance Constraint', 0)} clearance before routing)")
    return res


def route_pcb(project, replace=False, keep_partial=False):
    """altium.route_pcb: the placed board routed by the agent's router (see route_on). Raises BridgeError with the reason when it did
    not end up with a fully routed, rule-clean board; the file is then as it was (backup kept)."""
    prj = _linked(project)
    pcb = _project_pcb(project)
    res = route_on(prj, pcb, replace=replace, keep_partial=keep_partial)
    _log(project, "route-pcb", pcb=str(pcb), routed=res["routed"], failed=[n for n, _ in res["failed"]], tracks=res["tracks"],
         vias=res["vias"], replace=bool(replace), keep_partial=bool(keep_partial), backup=res["backup"], problems=res["problems"],
         restored=res["restored"], drc_before=res["drc_before"], drc_after=res["drc_after"])
    if res["problems"] or res["failed"] or not res["written"]:
        raise BridgeError(res["summary"] if not res["written"] else
                          "The route does not check out: " + "; ".join(res["problems"][:5])
                          + (" The board file was put back as it was before (backup kept)." if res["restored"]
                             else f" Tracks stay on the board (partial, as agreed); backup in {res['backup']}." if keep_partial
                             else f" Backup in {res['backup']}."))
    res["warnings"] = [f"drill check: {m}" for m in res["drills"][:6]] + [f"design vs board: {m}" for m in design_problems(project)[:6]]
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
    return rule_kinds.append_extra_records(rules_mod.board_rul_records(pcb, preset), _json_list(project, "rules.json"))


def rules_missing(project):
    """Names of the advisor rules import_rules writes that the linked PcbDoc FILE does not have ([] without a PcbDoc)."""
    try:
        pcb = _project_pcb(project)
        have = {r.get("NAME") for r in rules_mod.read_pcbdoc(pcb).get("rules", [])}
        return [r["NAME"] for r in _plan_records(project, pcb)
                if r.get("RULEKIND") in RULE_PROPS and r.get("NAME") and r["NAME"] not in have and _rule_values(r) is not None]
    except (BridgeError, AltiumReadError, OSError):
        return []


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
        out = [f["message"] for f in schematic.check_intent_vs_board([store.load_sheet(project, s) for s in store.sheet_ids(project)], pcb)
               if f["severity"] == "error"]
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


def run_outjob(project):
    """Run the project's OutJob (ours is added first when it has none). Returns {outjob, added, containers, files, backup}."""
    prj = _linked(project)
    summary = read_prjpcb(prj)
    target, added, backup = None, False, ""
    for rel in summary["outjobs"]:
        cand = prj.parent / pathlib.Path(rel.replace("\\", "/"))
        if cand.is_file() and outjob_containers(cand):
            target = cand
            break
    cmds = [("PROJECT", str(prj))]
    if target is None:
        if summary["outjobs"]:
            raise BridgeError("The project's OutJob has no Folder Structure output to run.")
        target = prj.parent / f"{prj.stem}.OutJob"
        if target.exists():
            raise BridgeError(f"{target.name} is in the project folder but not in the project; add it to the project first.")
        backup = _backup(prj, [prj])
        outjob.generate_outjob(project, filename=target.name, out_dir=prj.parent)
        cmds += [("ADDDOC", str(prj), str(target)), ("SAVEPRJ", str(prj))]
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
    missing = rules_missing(project)
    warnings = [f"The JLC rules ({', '.join(missing)}) are no longer in the PcbDoc; DRC and outputs ran against Altium's "
                "defaults. Import the rules again."] if missing else []
    drills = drill_problems(project)
    if drills:
        warnings.append(f"{len(drills)} hole(s) JLC cannot make: " + "; ".join(drills[:5]) + (" ..." if len(drills) > 5 else ""))
    design = design_problems(project)
    if design:
        warnings.append(f"The board does not match the design ({len(design)} problem(s)): " + " | ".join(design[:5])
                        + (" ..." if len(design) > 5 else "") + " Fix this before ordering.")
    _log(project, "run-outjob", outjob=str(target), added=added, files=len(files), backup=backup, rules_missing=missing)
    return {"outjob": str(target), "added": added, "containers": [m for m, _ in boxes], "files": sorted(files), "backup": backup,
            "warnings": warnings}


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
        if not steps:
            continue
        dest = lp["d3"] / f"{_file_name(fpn, 'model')}.step"
        shutil.copyfile(steps[0], dest)
        m = info.get("model") or {}
        seat = m.get("seat", 0 if info.get("tht") else 1)
        attach.append("FP|" + "|".join(str(v) for v in (fpn, dest, m.get("rx", 0), m.get("ry", 0), m.get("rz", 0),
                                                        m.get("dx", 0), m.get("dy", 0), seat)))
        bodies[fpn] = dest.name
    _write_ansi(out / "attach3d.txt", "\r\n".join(attach) + "\r\n")
    pins = spec_symbols(out / "symbols_spec.txt")
    expected = {"symbols": {n: {"pins": pins.get(n, []), "footprint": links.get(n, ""), "props": props.get(n, "|").split("|", 1),
                                "hide": bool(s.get("hide_pin_names")), "params": s.get("params", {})}
                            for n, s in parts["symbols"].items()},
                "footprints": spec_footprints(out / "footprints_spec.txt"), "bodies": bodies}
    return {k: out / v for k, v in (("symbols", "symbols_spec.txt"), ("footprints", "footprints_spec.txt"), ("links", "links.txt"),
                                    ("props", "props.txt"), ("params", "params.txt"), ("attach", "attach3d.txt"))}, expected


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
        if len(want["pins"]) == 2 and want["hide"] and any(p["show_name"] for p in got["pins"]):
            sym_bad(name, "pin names are still shown on a 2-pin part")
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
            ("HIDEPINS", str(lp["schlib"])), ("SAVELIB", str(lp["schlib"]), "SchLib")]
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
    syms, fps = spec_symbols(build / "symbols_spec.txt"), spec_footprints(build / "footprints_spec.txt")
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
        # 3. compile and install; then the IntLib file and Altium's list of installed libraries are checked
        log = run_commands([("COMPILE", str(lp["libpkg"]), str(lp["intlib"])), ("CHECKINST", str(lp["intlib"]))],
                           stall_timeout=180, total_timeout=900)
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
    notices = [f"Another installed library had the same name and was removed from Altium's installed list: "
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
