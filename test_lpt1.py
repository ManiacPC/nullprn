"""
test_lpt1.py - prints to a legacy port the way an old program would, to verify
that NullPrn is redirecting it correctly.

Usage:  python test_lpt1.py                 (tests LPT1)
        python test_lpt1.py --port USB001    (another port)
        python test_lpt1.py --port LPT1 --port LPT2
"""
import argparse
import ctypes
import sys
import threading
import time
from ctypes import wintypes

TIMEOUT = 5  # seconds

GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
INVALID_HANDLE = wintypes.HANDLE(-1).value
NULL_DEVICE = r"\Device\Null"

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                            wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
k32.CreateFileW.restype = wintypes.HANDLE
k32.WriteFile.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, wintypes.DWORD,
                          ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
k32.WriteFile.restype = wintypes.BOOL
k32.CloseHandle.argtypes = [wintypes.HANDLE]
k32.QueryDosDeviceW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
k32.QueryDosDeviceW.restype = wintypes.DWORD

# Test text with typical ESC/P codes (reset, bold, condensed, form feed)
ESC = b"\x1b"


def build_data(port):
    return (
        ESC + b"@"
        + ESC + b"E" + b"PRINT TEST\r\n" + ESC + b"F"
        + b"Port:  " + port.encode() + b"\r\n"
        + b"Date:  " + time.strftime("%Y-%m-%d %H:%M:%S").encode() + b"\r\n"
        + b"\x0f" + b"Condensed text 0123456789\r\n" + b"\x12"
        + b"-" * 40 + b"\r\n"
        + b"\x0c"
    )


def show_mapping(port):
    buf = ctypes.create_unicode_buffer(1024)
    if k32.QueryDosDeviceW(port, buf, len(buf)):
        target = buf.value
        tag = "  <- NullPrn active" if target == NULL_DEVICE else ""
        print(f"[i] {port} points to: {target}{tag}")
    else:
        print(f"[!] {port} is not a device (error {ctypes.get_last_error()})")


def write_port(port, data, result):
    h = k32.CreateFileW(port, GENERIC_WRITE, 0, None, OPEN_EXISTING, 0, None)
    if h == INVALID_HANDLE:
        result["error"] = f"Could not open {port}: {ctypes.WinError(ctypes.get_last_error())}"
        return
    try:
        written = wintypes.DWORD(0)
        ok = k32.WriteFile(h, data, len(data), ctypes.byref(written), None)
        if not ok:
            result["error"] = f"Write failed: {ctypes.WinError(ctypes.get_last_error())}"
        else:
            result["written"] = written.value
    finally:
        k32.CloseHandle(h)


def test_port(port):
    data = build_data(port)
    show_mapping(port)
    print(f"[>] Sending {len(data)} bytes to {port}...")
    result = {}
    t0 = time.perf_counter()
    th = threading.Thread(target=write_port, args=(port, data, result), daemon=True)
    th.start()
    th.join(TIMEOUT)
    ms = (time.perf_counter() - t0) * 1000

    if th.is_alive():
        print(f"[X] Blocked for more than {TIMEOUT}s: the port exists but nobody is receiving.")
        return 2
    if "error" in result:
        print(f"[X] {result['error']}")
        return 1
    if result["written"] != len(data):
        print(f"[!] Partial write: {result['written']}/{len(data)} bytes")
        return 1
    print(f"[OK] {result['written']} bytes 'printed' on {port} in {ms:.1f} ms")
    return 0


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        prog="test_lpt1",
        description="Print a test page to a legacy port to verify NullPrn.")
    ap.add_argument("--port", action="append", metavar="PORT",
                    help="Port to test, e.g. LPT1 or USB001. Repeat for several. Default: LPT1.")
    # Backwards compat: allow a bare positional port (old usage: test_lpt1.py LPT2)
    ap.add_argument("ports_pos", nargs="*", metavar="PORT",
                    help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    ports = args.port or args.ports_pos or ["LPT1"]
    return [p.upper() for p in ports]


def main():
    ports = parse_args()
    rc = 0
    for port in ports:
        rc = max(rc, test_port(port))
    sys.exit(rc)


if __name__ == "__main__":
    main()
