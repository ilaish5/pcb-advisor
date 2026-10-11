"""Windows registry inspection for Altium Designer installs and recent projects."""
import os
import pathlib
import re

__all__ = ["find_installs", "recent_projects"]


def _version_key(v: str) -> tuple[int, ...]:
    parts = []
    for p in str(v or "").split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _open_key(reg, root, path):
    try:
        return reg.OpenKey(root, path, 0, getattr(reg, "KEY_READ", 0))
    except (TypeError, AttributeError):
        return reg.OpenKey(root, path)


class _KeyContext:
    def __init__(self, reg, handle):
        self.reg = reg
        self.handle = handle

    def __enter__(self):
        if hasattr(self.handle, "__enter__"):
            return self.handle.__enter__()
        return self.handle

    def __exit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self.handle, "__exit__"):
            return self.handle.__exit__(exc_type, exc_val, exc_tb)
        if hasattr(self.reg, "CloseKey"):
            try:
                self.reg.CloseKey(self.handle)
            except Exception:
                pass
        elif hasattr(self.handle, "Close"):
            try:
                self.handle.Close()
            except Exception:
                pass


def _enum_keys(reg, key_handle):
    subkeys = []
    i = 0
    while True:
        try:
            subkeys.append(reg.EnumKey(key_handle, i))
            i += 1
        except OSError:
            break
    return subkeys


def _enum_values(reg, key_handle):
    values = []
    i = 0
    while True:
        try:
            values.append(reg.EnumValue(key_handle, i))
            i += 1
        except OSError:
            break
    return values


def _query_value(reg, key_handle, name):
    try:
        val, _ = reg.QueryValueEx(key_handle, name)
        return val
    except (OSError, AttributeError):
        for vname, vval, *_ in _enum_values(reg, key_handle):
            if vname.lower() == name.lower():
                return vval
        return None


def find_installs(reg=None) -> list[dict]:
    """Find installed Altium Designer builds from HKLM\\SOFTWARE\\Altium\\Builds\\*."""
    if reg is None:
        try:
            import winreg
            reg = winreg
        except ImportError:
            return []

    root = getattr(reg, "HKEY_LOCAL_MACHINE", None)
    if root is None:
        return []

    try:
        k = _open_key(reg, root, r"SOFTWARE\Altium\Builds")
    except OSError:
        return []

    with _KeyContext(reg, k) as builds_k:
        build_names = _enum_keys(reg, builds_k)

    installs = []
    for b_name in build_names:
        try:
            sub_k = _open_key(reg, root, rf"SOFTWARE\Altium\Builds\{b_name}")
        except OSError:
            continue
        with _KeyContext(reg, sub_k) as bk:
            path_val = _query_value(reg, bk, "ProgramsInstallPath") or ""
            version_val = _query_value(reg, bk, "Version") or ""

        p_str = str(path_val)
        exe_path = ""
        if p_str:
            try:
                candidate = pathlib.Path(p_str) / "X2.EXE"
                if candidate.is_file():
                    exe_path = str(candidate)
            except OSError:
                exe_path = ""

        installs.append({
            "build": b_name,
            "version": str(version_val),
            "path": p_str,
            "exe": exe_path,
        })

    installs.sort(key=lambda x: _version_key(x["version"]), reverse=True)
    return installs


def recent_projects(reg=None, limit: int = 20) -> list[dict]:
    """Find recent .PrjPcb projects across all builds in HKCU\\Software\\Altium."""
    if reg is None:
        try:
            import winreg
            reg = winreg
        except ImportError:
            return []

    root = getattr(reg, "HKEY_CURRENT_USER", None)
    if root is None:
        return []

    try:
        k = _open_key(reg, root, r"Software\Altium")
    except OSError:
        return []

    with _KeyContext(reg, k) as altium_k:
        subkeys = _enum_keys(reg, altium_k)

    ordered_builds = []
    try:
        for inst in find_installs(reg):
            b = inst.get("build")
            if b and b in subkeys and b not in ordered_builds:
                ordered_builds.append(b)
    except Exception:
        pass
    for b in subkeys:
        if b not in ordered_builds:
            ordered_builds.append(b)

    seen = set()
    results = []

    for build in ordered_builds:
        rec_path = rf"Software\Altium\{build}\DesignExplorer\Recent Documents"
        try:
            rec_k = _open_key(reg, root, rec_path)
        except OSError:
            continue
        with _KeyContext(reg, rec_k) as rk:
            vals = _enum_values(reg, rk)

        doc_pairs = []
        for item in vals:
            if not item or len(item) < 2:
                continue
            vname, vval = item[0], item[1]
            m = re.match(r"^RecentDocument(\d+)$", str(vname), re.IGNORECASE)
            if m and isinstance(vval, str):
                doc_pairs.append((int(m.group(1)), vval))

        doc_pairs.sort(key=lambda x: x[0])

        for _, raw in doc_pairs:
            raw_stripped = raw.strip()
            if not raw_stripped.lower().endswith(".prjpcb"):
                continue
            norm = os.path.normcase(os.path.normpath(raw_stripped))
            if norm in seen:
                continue
            seen.add(norm)

            p = pathlib.Path(raw_stripped)
            try:
                exists = p.is_file()
            except OSError:
                exists = False

            results.append({
                "path": str(p),
                "name": p.stem,
                "exists": bool(exists),
                "build": build,
            })
            if len(results) >= limit:
                return results

    return results[:limit]
