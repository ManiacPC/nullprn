"""
NullPrn Tray - redirects a parallel/legacy port (LPT1 by default) to the Windows
null device, so legacy software that prints to LPT1/USB001/... no longer fails on
Windows 10/11. Everything the program writes to the port "prints" OK and is discarded
(or captured to a file with --target).

Requirements:  pip install pystray pillow
Run:           pythonw nullprn_tray.py
               pythonw nullprn_tray.py --port LPT1 --port USB001
               pythonw nullprn_tray.py --port LPT1 --target C:\\temp\\capture.prn
"""
import argparse
import ctypes
import msvcrt
import os
import sys
import tempfile
from ctypes import wintypes

import pystray
from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# Win32 bindings
# ---------------------------------------------------------------------------
DDD_RAW_TARGET_PATH = 0x1
DDD_REMOVE_DEFINITION = 0x2
DDD_EXACT_MATCH_ON_REMOVE = 0x4

NULL_DEVICE = r"\Device\Null"
APP_NAME = "NullPrn"

# Single-instance guard: an OS-level lock on a file in %TEMP%. The lock is held
# for the whole process lifetime and released automatically by the OS on exit
# (even on a crash or force-kill), so it never leaves a stale lock behind.
_instance_lock = None
LOCK_PATH = os.path.join(tempfile.gettempdir(), "nullprn.lock")


def acquire_single_instance():
    """Return True if we are the only instance, False if one is already running."""
    global _instance_lock
    try:
        _instance_lock = open(LOCK_PATH, "a+")
        _instance_lock.seek(0)
        msvcrt.locking(_instance_lock.fileno(), msvcrt.LK_NBLCK, 1)
        return True
    except OSError:
        if _instance_lock is not None:
            _instance_lock.close()
            _instance_lock = None
        return False


k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.DefineDosDeviceW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR]
k32.DefineDosDeviceW.restype = wintypes.BOOL
k32.QueryDosDeviceW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
k32.QueryDosDeviceW.restype = wintypes.DWORD


# ---------------------------------------------------------------------------
# Target resolution
# ---------------------------------------------------------------------------
def resolve_target(target):
    """Return the NT raw target path for DefineDosDeviceW.

    - None / "nul" / "null"  -> the null device (discard everything).
    - any other value        -> a file path, mapped as \\??\\<absolute path>.
    """
    if target is None or target.lower() in ("nul", "null"):
        return NULL_DEVICE
    abspath = os.path.abspath(target)
    os.makedirs(os.path.dirname(abspath) or ".", exist_ok=True)
    return r"\??" + "\\" + abspath


# ---------------------------------------------------------------------------
# Device redirection (per login session; does not survive reboot by itself)
# ---------------------------------------------------------------------------
def current_target(port):
    buf = ctypes.create_unicode_buffer(1024)
    if k32.QueryDosDeviceW(port, buf, len(buf)):
        return buf.value  # first target in the list
    return None


def port_active(port, nt_target):
    return current_target(port) == nt_target


def activate_port(port, nt_target):
    if not port_active(port, nt_target):
        if not k32.DefineDosDeviceW(DDD_RAW_TARGET_PATH, port, nt_target):
            raise ctypes.WinError(ctypes.get_last_error())


def deactivate_port(port, nt_target):
    flags = DDD_RAW_TARGET_PATH | DDD_REMOVE_DEFINITION | DDD_EXACT_MATCH_ON_REMOVE
    while port_active(port, nt_target):  # remove only our definition
        if not k32.DefineDosDeviceW(flags, port, nt_target):
            break


# ---------------------------------------------------------------------------
# Auto-start (shortcut in the user's Startup folder)
#
# We deliberately use a Startup-folder shortcut instead of the HKCU "Run"
# registry key: writing to Run is a behaviour that antivirus heuristics flag
# (it is the classic malware persistence trick), whereas dropping a .lnk in the
# Startup folder is a plain, user-visible file the user can also remove by hand.
# ---------------------------------------------------------------------------
_ole32 = ctypes.oledll.ole32


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", wintypes.BYTE * 8)]

    def __init__(self, s):
        super().__init__()
        _ole32.CLSIDFromString(s, ctypes.byref(self))


_CLSID_ShellLink = _GUID("{00021401-0000-0000-C000-000000000046}")
_IID_IShellLinkW = _GUID("{000214F9-0000-0000-C000-000000000046}")
_IID_IPersistFile = _GUID("{0000010B-0000-0000-C000-000000000046}")
_CLSCTX_INPROC_SERVER = 1


def _com_method(ptr, index, *argtypes):
    vtable = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p))[0]
    fn_addr = ctypes.cast(vtable, ctypes.POINTER(ctypes.c_void_p))[index]
    proto = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, *argtypes)
    return proto(fn_addr)


def startup_shortcut_path():
    startup = os.path.join(os.environ["APPDATA"],
                           r"Microsoft\Windows\Start Menu\Programs\Startup")
    return os.path.join(startup, APP_NAME + ".lnk")


def _launch_target(ports, target):
    """Return (exe, arguments) to relaunch this app at login."""
    if getattr(sys, "frozen", False) or "__compiled__" in globals():
        exe = os.path.abspath(sys.argv[0])
    else:
        pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        exe = pyw if os.path.exists(pyw) else sys.executable
    args = []
    if not (getattr(sys, "frozen", False) or "__compiled__" in globals()):
        args.append(f'"{os.path.abspath(__file__)}"')
    for p in ports:
        args += ["--port", p]
    if target is not None:
        args += ["--target", f'"{os.path.abspath(target)}"']
    return exe, " ".join(args)


def _create_shortcut(lnk, exe, args, workdir, icon):
    _ole32.CoInitialize(None)
    psl = ctypes.c_void_p()
    _ole32.CoCreateInstance(ctypes.byref(_CLSID_ShellLink), None,
                            _CLSCTX_INPROC_SERVER, ctypes.byref(_IID_IShellLinkW),
                            ctypes.byref(psl))
    _com_method(psl, 20, wintypes.LPCWSTR)(psl, exe)                     # SetPath
    _com_method(psl, 11, wintypes.LPCWSTR)(psl, args)                    # SetArguments
    _com_method(psl, 9, wintypes.LPCWSTR)(psl, workdir)                  # SetWorkingDirectory
    _com_method(psl, 17, wintypes.LPCWSTR, ctypes.c_int)(psl, icon, 0)   # SetIconLocation
    ppf = ctypes.c_void_p()
    _com_method(psl, 0, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p))(
        psl, ctypes.byref(_IID_IPersistFile), ctypes.byref(ppf))         # QueryInterface
    _com_method(ppf, 6, wintypes.LPCWSTR, ctypes.c_int)(ppf, lnk, 1)     # Save
    _com_method(ppf, 2)(ppf)   # Release IPersistFile
    _com_method(psl, 2)(psl)   # Release IShellLink


def autostart_enabled():
    return os.path.exists(startup_shortcut_path())


def set_autostart(enabled, ports, target):
    lnk = startup_shortcut_path()
    if enabled:
        if os.path.exists(lnk):  # already created with our fixed name -> no-op
            return
        exe, args = _launch_target(ports, target)
        _create_shortcut(lnk, exe, args, os.path.dirname(exe), exe)
    else:
        try:
            os.remove(lnk)
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------------------
# Icon
# ---------------------------------------------------------------------------
def make_icon(on):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    color = (40, 170, 80) if on else (150, 150, 150)
    d.rectangle((10, 22, 54, 46), fill=color)            # body
    d.rectangle((18, 8, 46, 22), fill=(230, 230, 230))   # paper (top)
    d.rectangle((18, 46, 46, 58), fill=(230, 230, 230))  # paper (bottom)
    return img


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
class NullPrnApp:
    def __init__(self, ports, target):
        self.ports = ports
        self.target = target
        self.nt_target = resolve_target(target)
        self.target_label = "nul" if self.nt_target == NULL_DEVICE else os.path.abspath(target)

    # -- state ------------------------------------------------------------
    def is_active(self):
        return all(port_active(p, self.nt_target) for p in self.ports)

    def activate(self):
        for p in self.ports:
            activate_port(p, self.nt_target)

    def deactivate(self):
        for p in self.ports:
            deactivate_port(p, self.nt_target)

    # -- ui ---------------------------------------------------------------
    def mapping_text(self, _item):
        rows = []
        for p in self.ports:
            cur = current_target(p)
            shown = "nul" if cur == NULL_DEVICE else (cur or "—")
            rows.append(f"{p} -> {shown}")
        return "   |   ".join(rows)

    def refresh(self, icon):
        on = self.is_active()
        icon.icon = make_icon(on)
        ports = ", ".join(self.ports)
        icon.title = (f"NullPrn: {ports} -> {self.target_label}" if on
                      else f"NullPrn: {ports} normal")
        icon.update_menu()

    def toggle(self, icon, _item):
        try:
            self.deactivate() if self.is_active() else self.activate()
        except OSError as e:
            icon.notify(str(e), "NullPrn error")
        self.refresh(icon)

    def toggle_autostart(self, icon, _item):
        try:
            set_autostart(not autostart_enabled(), self.ports, self.target)
        except OSError as e:
            icon.notify(str(e), "NullPrn error")
        icon.update_menu()

    def quit(self, icon, _item):
        self.deactivate()
        icon.stop()

    def run(self):
        self.activate()
        icon = pystray.Icon(
            "nullprn",
            make_icon(True),
            menu=pystray.Menu(
                pystray.MenuItem("Active", self.toggle,
                                 checked=lambda i: self.is_active(), default=True),
                pystray.MenuItem(self.mapping_text, None, enabled=False),
                pystray.MenuItem("Start with Windows", self.toggle_autostart,
                                 checked=lambda i: autostart_enabled()),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", self.quit),
            ),
        )
        self.refresh(icon)
        icon.run()


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        prog="NullPrn",
        description="Redirect a legacy/parallel port to the null device (or a file).")
    ap.add_argument("--port", action="append", metavar="PORT",
                    help='Port to redirect, e.g. LPT1 or USB001. '
                         'Repeat for several ports. Default: LPT1.')
    ap.add_argument("--target", metavar="PATH", default=None,
                    help='Where writes go: "nul" (default, discard) or a file path '
                         'to capture printed data.')
    args = ap.parse_args(argv)
    ports = [p.upper() for p in (args.port or ["LPT1"])]
    return ports, args.target


def main():
    if not acquire_single_instance():
        # MB_OK | MB_ICONINFORMATION | MB_SETFOREGROUND
        ctypes.windll.user32.MessageBoxW(
            0, "NullPrn is already running. Check the system tray icon.",
            "NullPrn", 0x40 | 0x10000)
        return
    ports, target = parse_args()
    NullPrnApp(ports, target).run()


if __name__ == "__main__":
    main()
