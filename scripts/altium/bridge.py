#!/usr/bin/env python3
"""
Two-way link to a running Altium Designer: create the project, add documents, draw a schematic skeleton.

    python scripts/altium/bridge.py status
    python scripts/altium/bridge.py new-project <project>      PrjPcb + one PcbDoc + one SchDoc per sheet, linked
    python scripts/altium/bridge.py add-sheet <project> <name> | add-pcb <project>
    python scripts/altium/bridge.py skeleton <project> [<sheet>]  title block, parameters, one text frame per section;
                                                                 no components, safe to repeat
    python scripts/altium/bridge.py import-rules <project>       the advisor's rule set into the linked PcbDoc, by rule name
    python scripts/altium/bridge.py run-outjob <project>         Gerber, NC drill, BOM, pick and place into the outputs folder
    python scripts/altium/bridge.py open <project>

How: Altium runs a DelphiScript from scripts/altium/bridge/ (`X2.EXE -RScriptingSystem:RunScript(...)`); the request
and the answer go through files in a fixed folder. The script mechanism is adapted from altium-mcp (MIT, Copyright (c)
2025 Siddharth Ahuja, see bridge/LICENSE-altium-mcp). A script runtime error leaves Altium's script executor paused;
we notice (the script never starts or stops logging), release it with `X2.EXE -REditScript:Stop` and say so.

import-rules adds or updates the rules the preset, the Rules tab's extra rules and rules-off.json call for (matched by
name; the student's own rules are never deleted) and reads the PcbDoc back to confirm. run-outjob adds our OutJob
(scripts/outjob.py) to the project when it has none, then runs its Folder Structure containers.

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
import project as project_mod  # noqa: E402
import rule_kinds  # noqa: E402
import rules as rules_mod  # noqa: E402
import store  # noqa: E402
import workspace  # noqa: E402
from altium import AltiumReadError, registry  # noqa: E402
from altium.prjpcb import read_prjpcb as _read_prjpcb  # noqa: E402

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
    """Close the dialog boxes Altium left open (class #32770 or a script error box, owned by X2.EXE), so the next script can run."""
    try:
        import ctypes
        from ctypes import wintypes
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq X2.EXE", "/FO", "CSV", "/NH"], capture_output=True,
                             text=True, timeout=15).stdout
        pids = {int(m) for m in re.findall(r'"X2\.EXE","(\d+)"', out, re.I)}
        user32 = ctypes.windll.user32
        closed = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def each(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                cls = ctypes.create_unicode_buffer(64)
                user32.GetClassNameW(hwnd, cls, 64)
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if cls.value == "#32770" and pid.value in pids:
                    user32.PostMessageW(hwnd, 0x0010, 0, 0)       # WM_CLOSE
                    closed.append(hwnd)
                elif cls.value == "TMessageForm" and pid.value in pids:     # a script error box: only its OK button ends it
                    user32.PostMessageW(hwnd, 0x0100, 13, 0)      # WM_KEYDOWN, VK_RETURN
                    user32.PostMessageW(hwnd, 0x0101, 13, 0)      # WM_KEYUP
                    closed.append(hwnd)
            return True

        user32.EnumWindows(each, 0)
        return len(closed)
    except Exception:
        return 0


def release_executor():
    """Stop a script that Altium left paused after a runtime error (every later script would silently do nothing)."""
    _close_dialogs()
    try:
        subprocess.Popen(f'"{_exe()}" -REditScript:Stop')
    except OSError:
        pass
    time.sleep(2)


def _ascii(text):
    """The script reads the request as ANSI text: keep it plain ASCII (a letter that does not fit becomes '?')."""
    return str(text).encode("ascii", "replace").decode("ascii")


def _read(path):
    try:
        return pathlib.Path(path).read_text(encoding="ascii", errors="replace").splitlines()
    except OSError:
        return []


def run_commands(commands, start_timeout=45, stall_timeout=60, total_timeout=300):
    """Send command lines (tab separated fields) to Altium, wait for DONE. Returns the script's log lines.
    Raises BridgeError with the last step when the script does not start, stops logging or reports an error."""
    exe = _exe()
    if not SCRIPT_PROJECT.is_file():
        raise BridgeError(f"bridge script missing: {SCRIPT_PROJECT}")
    with _lock:
        EXCHANGE.mkdir(parents=True, exist_ok=True)
        for name in ("response.txt", "log.txt"):
            (EXCHANGE / name).unlink(missing_ok=True)
        body = "\r\n".join("\t".join(_ascii(f) for f in c) for c in commands) + "\r\n"
        (EXCHANGE / "request.txt").write_bytes(body.encode("ascii"))     # bytes: text mode would double the CR on Windows
        cold = not _running()          # Altium has to start first: that takes a while
        for attempt in (1, 2):
            subprocess.Popen(f'"{exe}" -RScriptingSystem:RunScript(ProjectName="{SCRIPT_PROJECT}"|ProcName="AdvisorBridge>Run")')
            t0 = time.time()
            started = False
            while time.time() - t0 < start_timeout * (8 if cold else 1):
                if "START" in _read(EXCHANGE / "response.txt"):
                    started = True
                    break
                time.sleep(0.5)
            if started:
                break
            release_executor()          # a paused executor ignores new scripts: release it and try once more
            if attempt == 2:
                raise BridgeError("Altium did not start the script (a script error or a dialog box was blocking it). "
                                  "I released the script executor and closed dialogs; try again.")
        t_log, last_size, t0 = time.time(), -1, time.time()
        while True:
            resp = _read(EXCHANGE / "response.txt")
            log = _read(EXCHANGE / "log.txt")
            errs = [r for r in resp if r.startswith("ERR")]
            if "DONE" in resp or errs:
                break
            if len(log) != last_size:
                last_size, t_log = len(log), time.time()
            if time.time() - t_log > stall_timeout or time.time() - t0 > total_timeout:
                release_executor()
                raise BridgeError("Altium stopped in the middle of the script, after: "
                                  f"{log[-1] if log else 'nothing'}. I released the script executor.")
            time.sleep(0.5)
        if errs:
            raise BridgeError("Altium refused a step: " + "; ".join(e[4:] for e in errs) + f" (last step: {log[-1] if log else '-'})")
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
    _log(project, "new-project", project_file=str(prj), documents=summary["documents"])
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


def rule_plan(project, pcb):
    """What the PcbDoc needs: ([(record, script values)] to add or change, [{name, kind, why}] skipped). The record set is
    what the Download .RUL gives (preset minus the rules turned off, existing rules of the same kind and scope updated,
    extra rules added); a rule the board already has in the same state is left alone."""
    off = {n for n in _json_list(project, "rules-off.json") if isinstance(n, str)}
    preset = [r for r in rules_mod.get_preset_rule_records(project_mod.board(project)) if r.get("NAME") not in off]
    records = rule_kinds.append_extra_records(rules_mod.board_rul_records(pcb, preset), _json_list(project, "rules.json"))
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
    return cmds + [("SAVE", str(pcb))]


def import_rules(project):
    """Put the advisor's rules into the linked PcbDoc. Returns {created, updated, skipped, unconfirmed, backup}."""
    prj = _linked(project)
    pcb = _project_pcb(project)
    todo, skipped = rule_plan(project, pcb)
    res = {"created": [], "updated": [], "skipped": skipped, "unconfirmed": [], "backup": ""}
    if not todo:
        return res
    before = {r.get("NAME") for r in rules_mod.read_pcbdoc(pcb).get("rules", [])}
    res["backup"] = _backup(prj, [pcb])
    run_commands([("PROJECT", str(prj)), *rule_commands(pcb, todo)])
    after = {r.get("NAME"): r for r in rules_mod.read_pcbdoc(pcb).get("rules", [])}
    for rec, vals in todo:
        got = after.get(rec["NAME"])
        (res["updated"] if rec["NAME"] in before else res["created"]).append(rec["NAME"])
        if got is None or not _same_values(vals, _rule_values(got) or {}):
            res["unconfirmed"].append(rec["NAME"])      # Altium did not keep what we wrote: the Rules tab will show it
    _log(project, "import-rules", pcb=str(pcb), backup=res["backup"], skipped=[s["name"] for s in skipped],
         **{k: res[k] for k in ("created", "updated", "unconfirmed")})
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
    _log(project, "run-outjob", outjob=str(target), added=added, files=len(files), backup=backup)
    return {"outjob": str(target), "added": added, "containers": [m for m, _ in boxes], "files": sorted(files), "backup": backup}


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


# ---------------------------------------------------------------- CLI

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="op", required=True)
    sub.add_parser("status")
    for op in ("new-project", "add-pcb", "open", "import-rules", "run-outjob"):
        sub.add_parser(op).add_argument("project")
    p = sub.add_parser("add-sheet")
    p.add_argument("project")
    p.add_argument("name")
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
        elif a.op == "import-rules":
            res = import_rules(a.project)
        elif a.op == "run-outjob":
            res = run_outjob(a.project)
        else:
            res = open_project(a.project)
    except (BridgeError, AltiumReadError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
