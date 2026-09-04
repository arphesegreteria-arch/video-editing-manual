"""Per-user Windows DPAPI storage for the tunnel runtime API key.

The secret is never accepted as a command-line argument. ``set`` prompts on the
console and writes only a DPAPI ciphertext blob.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import getpass
import os
from pathlib import Path
import sys
import tempfile


CRYPTPROTECT_UI_FORBIDDEN = 0x1
_DESCRIPTION = "ARPHE_WINDOWS_BRIDGE_RUNTIME_V1:PC_SEGRETERIA"
_ENTROPY = b"ARPHE_WINDOWS_BRIDGE_RUNTIME_V1|PC_SEGRETERIA|CONTROL_PLANE_API_KEY"


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _require_windows() -> None:
    if os.name != "nt":
        raise RuntimeError("Windows DPAPI is available only on Windows")


def _input_blob(data: bytes) -> tuple[DATA_BLOB, object]:
    buffer = ctypes.create_string_buffer(data)
    blob = DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    return blob, buffer


def _dpapi(protect: bool, data: bytes) -> bytes:
    _require_windows()
    source, source_buffer = _input_blob(data)
    entropy, entropy_buffer = _input_blob(_ENTROPY)
    output = DATA_BLOB()
    description = ctypes.c_wchar_p()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptProtectData.argtypes = (
        ctypes.POINTER(DATA_BLOB), wintypes.LPCWSTR, ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB),
    )
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = (
        ctypes.POINTER(DATA_BLOB), ctypes.POINTER(ctypes.c_wchar_p), ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB),
    )
    kernel32.LocalFree.restype = ctypes.c_void_p
    kernel32.LocalFree.argtypes = (ctypes.c_void_p,)
    if protect:
        ok = crypt32.CryptProtectData(
            ctypes.byref(source), _DESCRIPTION, ctypes.byref(entropy), None, None,
            CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(output)
        )
    else:
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(source), ctypes.byref(description), ctypes.byref(entropy), None, None,
            CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(output)
        )
    # Keep input buffers alive until the native call has returned.
    del source_buffer, entropy_buffer
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        if output.pbData:
            kernel32.LocalFree(output.pbData)
        if description:
            kernel32.LocalFree(description)


def store_secret(path: Path, secret: str) -> None:
    if not secret or "\x00" in secret:
        raise ValueError("The runtime API key must be non-empty and contain no NUL characters")
    ciphertext = _dpapi(True, secret.encode("utf-8"))
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(ciphertext)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_secret(path: Path) -> str:
    plaintext = bytearray(_dpapi(False, path.read_bytes()))
    try:
        secret = plaintext.decode("utf-8")
        if not secret:
            raise ValueError("Stored runtime API key is empty")
        return secret
    finally:
        for index in range(len(plaintext)):
            plaintext[index] = 0


def delete_secret(path: Path) -> bool:
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


def _main() -> int:
    parser = argparse.ArgumentParser(description="Manage the per-user DPAPI runtime API key")
    parser.add_argument("action", choices=("set", "status", "delete"))
    parser.add_argument("--path", required=True, type=Path)
    args = parser.parse_args()
    if args.action == "status":
        print("present" if args.path.is_file() else "missing")
        return 0 if args.path.is_file() else 1
    if args.action == "delete":
        print("deleted" if delete_secret(args.path) else "already absent")
        return 0
    first = getpass.getpass("Runtime API key (input hidden): ")
    second = getpass.getpass("Repeat runtime API key: ")
    if first != second:
        print("The two values do not match.", file=sys.stderr)
        return 2
    store_secret(args.path, first)
    print("Runtime API key stored with Windows DPAPI for the current user.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
