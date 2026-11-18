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
import os
import sys
import winreg
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
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

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
# Auto-start (HKEY_CURRENT_USER Run key)
# ---------------------------------------------------------------------------
def _launch_command(ports, target):
    """Rebuild the command line used to relaunch this app at login."""
    if getattr(sys, "frozen", False) or "__compiled__" in globals():
        parts = [f'"{os.path.abspath(sys.argv[0])}"']
    else:
        pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        exe = pyw if os.path.exists(pyw) else sys.executable
        parts = [f'"{exe}"', f'"{os.path.abspath(__file__)}"']
    for p in ports:
        parts += ["--port", p]
    if target is not None:
        parts += ["--target", f'"{os.path.abspath(target)}"']
    return " ".join(parts)


def autostart_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except FileNotFoundError:
        return False


def set_autostart(enabled, ports, target):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ,
                              _launch_command(ports, target))
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
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
    ports, target = parse_args()
    NullPrnApp(ports, target).run()


if __name__ == "__main__":
    main()
