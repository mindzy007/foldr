"""foldr core: Windows folder icon logic (pure ctypes, no admin needed for normal folders)."""
import configparser
import ctypes
import hashlib
import io
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes

from PIL import Image

ICON_PREFIX = ".foldr_icon"
ICON_NAME = ICON_PREFIX + ".ico"  # legacy name kept for compatibility
EXTS = (".ico", ".png", ".jpg", ".jpeg")
CACHE = os.path.join(tempfile.gettempdir(), "foldr_cache")
LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()), "foldr")

SEC = ".ShellClassInfo"
KEYS = ("iconresource", "iconfile", "iconindex")
FA_RO, FA_HIDDEN, FA_SYSTEM = 0x1, 0x2, 0x4
LINK_TAGS = (0xA000000C, 0xA0000003)  # symlink, junction (NOT OneDrive/cloud placeholders)

if hasattr(ctypes, "windll"):
    _k32 = ctypes.windll.kernel32
    _k32.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
    _k32.GetFileAttributesW.restype = wintypes.DWORD
    _k32.SetFileAttributesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    _k32.SetFileAttributesW.restype = wintypes.BOOL
    _shell = ctypes.windll.shell32
    _shell.SHChangeNotify.argtypes = [ctypes.c_long, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_wchar_p]
else:  # not Windows (only so the module can be imported for testing)
    _k32 = _shell = None


# ------------------------------------------------------------ admin
def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_admin():
    """Restart elevated (UAC prompt). True if launched."""
    if getattr(sys, "frozen", False):
        exe, args = sys.executable, ""
    else:
        exe = sys.executable.replace("python.exe", "pythonw.exe")
        args = f'"{os.path.abspath(sys.argv[0])}"'
    return ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, args, None, 1) > 32


# ------------------------------------------------------------ paths / attributes
def _lp(p):
    """Long-path form (\\\\?\\...) so very deep folders work."""
    if os.name != "nt":
        return p
    p = os.path.abspath(p)
    if p.startswith("\\\\"):
        return p
    return "\\\\?\\" + p


def _un(p):
    return p[4:] if p.startswith("\\\\?\\") and not p.startswith("\\\\?\\UNC") else p


def _attrs(path):
    a = _k32.GetFileAttributesW(_lp(path))
    return None if a == 0xFFFFFFFF else a


def _set(path, add=0, remove=0):
    a = _attrs(path)
    if a is None:
        return
    a = (a | add) & ~remove
    if not _k32.SetFileAttributesW(_lp(path), a or 0x80):
        raise ctypes.WinError()


def _is_link(path):
    try:
        st = os.lstat(path)
        return stat.S_ISLNK(st.st_mode) or getattr(st, "st_reparse_tag", 0) in LINK_TAGS
    except OSError:
        return False


def _notify(path=None, directory=False):
    """Tell Explorer to refresh."""
    if _shell is None:
        return
    if path:
        _shell.SHChangeNotify(0x00001000 if directory else 0x00002000, 0x0005, path, None)
    else:
        _shell.SHChangeNotify(0x08000000, 0x1000, None, None)  # ASSOCCHANGED + flush


def _refresh_icon_cache():
    try:
        subprocess.run(["ie4uinit.exe", "-ClearIconCache"], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=0x08000000, timeout=10)
        subprocess.run(["ie4uinit.exe", "-show"], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=0x08000000, timeout=10)
    except Exception:
        pass


# ------------------------------------------------------------ desktop.ini
def _new_cp():
    cp = configparser.ConfigParser(interpolation=None, strict=False, allow_no_value=True)
    cp.optionxform = str
    return cp


def _load_ini(path):
    cp = _new_cp()
    if os.path.exists(_lp(path)):
        try:
            with open(_lp(path), "rb") as f:
                raw = f.read()
            if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
                text = raw.decode("utf-16", "replace")
            else:
                text = raw.decode("utf-8-sig", "replace")
            cp.read_string(text)
        except Exception:
            cp = _new_cp()
    return cp


def _save_ini(cp, path):
    buf = io.StringIO()
    cp.write(buf, space_around_delimiters=False)
    text = buf.getvalue().strip() + "\n"
    with open(_lp(path), "w", encoding="ascii" if text.isascii() else "utf-16", newline="\r\n") as f:
        f.write(text)


def _is_ours(cp):
    return cp.has_section(SEC) and any(
        k.lower() in KEYS and ICON_PREFIX.lower() in (cp[SEC][k] or "").lower()
        for k in cp[SEC])


def _foldr_icon_files(folder):
    """Return current and legacy Foldr icon files stored beside desktop.ini."""
    try:
        return [os.path.join(folder, name) for name in os.listdir(_lp(folder))
                if name.lower().startswith(ICON_PREFIX.lower()) and name.lower().endswith(".ico")]
    except OSError:
        return []


# ------------------------------------------------------------ icons
def to_ico(path):
    """Return a .ico path, converting PNG/JPG into a temp cache when needed."""
    if path.lower().endswith(".ico"):
        return path
    os.makedirs(CACHE, exist_ok=True)
    with open(path, "rb") as source:
        data = source.read()
    digest = hashlib.sha256(data).hexdigest()
    out = os.path.join(CACHE, f"{digest}.ico")
    if not os.path.exists(out):
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        img.save(out, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return out


def iter_folders(top, recurse=True, hidden=False, on_skip=None):
    """Yield the folder itself, then every subfolder.
    Always skipped: system folders, symlinks/junctions. Hidden ones only if hidden=False."""
    skip = on_skip or (lambda path, why: None)
    yield top
    if not recurse:
        return
    for dirpath, dirnames, _ in os.walk(
            _lp(top), onerror=lambda e: skip(_un(str(e.filename or "")), "unreadable")):
        keep = []
        for d in dirnames:
            p = os.path.join(dirpath, d)
            a = _attrs(p) or 0
            why = ("link" if _is_link(p) else "system" if a & FA_SYSTEM
                   else "hidden" if (a & FA_HIDDEN and not hidden) else None)
            if why:
                skip(_un(p), why)
            else:
                keep.append(d)
        dirnames[:] = keep
        for d in keep:
            yield _un(os.path.join(dirpath, d))


def set_icon(folder, ico_path):
    ini = os.path.join(folder, "desktop.ini")
    cp = _load_ini(ini)  # keep any settings the folder already had
    with open(_lp(ico_path), "rb") as source:
        icon_tag = hashlib.sha256(source.read()).hexdigest()[:16]
    icon_name = f"{ICON_PREFIX}_{icon_tag}.ico"
    dest = os.path.join(folder, icon_name)
    for f in (ini, *_foldr_icon_files(folder)):
        if os.path.exists(_lp(f)):
            _set(f, remove=FA_RO | FA_HIDDEN | FA_SYSTEM)
            if f != dest:
                os.remove(_lp(f))
    shutil.copyfile(ico_path, _lp(dest))  # icon travels with the folder
    if not cp.has_section(SEC):
        cp.add_section(SEC)
    for k in list(cp[SEC]):
        if k.lower() in KEYS:
            cp.remove_option(SEC, k)
    cp[SEC]["IconResource"] = icon_name + ",0"
    cp[SEC]["IconFile"] = icon_name
    cp[SEC]["IconIndex"] = "0"
    _save_ini(cp, ini)
    _set(ini, add=FA_HIDDEN | FA_SYSTEM)
    _set(dest, add=FA_HIDDEN | FA_SYSTEM)
    _set(folder, add=FA_RO)  # Explorer only reads desktop.ini on read-only/system folders
    # verify it really stuck
    if not os.path.exists(_lp(ini)) or not (_attrs(folder) or 0) & FA_RO:
        raise OSError("could not verify icon was written")
    _notify(folder)


def reset_icon(folder):
    ini = os.path.join(folder, "desktop.ini")
    cp = _load_ini(ini)
    if not _is_ours(cp):
        return False  # not a foldr folder: leave untouched
    _set(ini, remove=FA_RO | FA_HIDDEN | FA_SYSTEM)
    for k in list(cp[SEC]):
        if k.lower() in KEYS:
            cp.remove_option(SEC, k)
    if not cp[SEC] and len(cp.sections()) == 1:
        os.remove(_lp(ini))
        _set(folder, remove=FA_RO)
    else:
        _save_ini(cp, ini)
        _set(ini, add=FA_HIDDEN | FA_SYSTEM)
    for dest in _foldr_icon_files(folder):
        if os.path.exists(_lp(dest)):
            _set(dest, remove=FA_RO | FA_HIDDEN | FA_SYSTEM)
            os.remove(_lp(dest))
    _notify(folder)
    return True


# ------------------------------------------------------------ batch
def _try(fn, folder, tries=3):
    """Retry a few times (Explorer / antivirus can briefly lock files)."""
    for i in range(tries):
        try:
            return fn(folder)
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(0.2)


def _batch(fn, folders, recurse, hidden, progress):
    ok, failed, skipped, done = 0, [], [], []
    for top in folders:
        for f in iter_folders(top, recurse, hidden, lambda p, why: skipped.append((p, why))):
            try:
                if _try(fn, f) is not False:
                    ok += 1
                    done.append(f)
            except Exception as e:
                denied = isinstance(e, PermissionError) or getattr(e, "winerror", None) == 5
                failed.append((f, str(e), denied))
            if progress:
                progress(ok + len(failed))
    for parent in {os.path.dirname(f) for f in done}:
        _notify(parent, directory=True)
    _notify(None)
    if done:
        _refresh_icon_cache()
    return {"ok": ok, "failed": failed, "skipped": skipped}


def apply_icon(folders, icon, recurse=True, hidden=False, progress=None):
    ico = to_ico(icon)
    return _batch(lambda f: set_icon(f, ico), folders, recurse, hidden, progress)


def reset_icons(folders, recurse=True, hidden=False, progress=None):
    return _batch(reset_icon, folders, recurse, hidden, progress)


def write_log(res, title):
    """Save what happened to a text file; returns its path."""
    os.makedirs(LOG_DIR, exist_ok=True)
    path = os.path.join(LOG_DIR, "last_run.txt")
    lines = [f"foldr - {title}", f"OK: {res['ok']}", ""]
    lines.append(f"FAILED ({len(res['failed'])})")
    lines += [f"  {p}\n    -> {m}" for p, m, _ in res["failed"]]
    lines += ["", f"SKIPPED ({len(res['skipped'])})"]
    lines += [f"  [{why}] {p}" for p, why in res["skipped"]]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path
