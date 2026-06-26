from __future__ import annotations

import ctypes
import sys
from pathlib import Path
from typing import Sequence

from ctypes import wintypes


class RecycleError(RuntimeError):
    pass


def move_to_recycle_bin(paths: Sequence[str | Path]) -> None:
    items = [str(Path(path)) for path in paths]
    if not items:
        return
    if not sys.platform.startswith("win"):
        raise RecycleError("La Corbeille Windows est disponible uniquement sous Windows.")

    packed_paths = "\0".join(items) + "\0\0"

    operation = SHFILEOPSTRUCTW()
    operation.wFunc = FO_DELETE
    operation.pFrom = packed_paths
    operation.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_WANTNUKEWARNING

    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if result != 0:
        raise RecycleError(f"Windows a refuse l'operation: code {result}")
    if operation.fAnyOperationsAborted:
        raise RecycleError("Operation annulee.")


FO_DELETE = 0x0003
FOF_NOCONFIRMATION = 0x0010
FOF_ALLOWUNDO = 0x0040
FOF_WANTNUKEWARNING = 0x4000


class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", wintypes.USHORT),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", wintypes.LPVOID),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


ctypes.windll.shell32.SHFileOperationW.argtypes = [ctypes.POINTER(SHFILEOPSTRUCTW)]
ctypes.windll.shell32.SHFileOperationW.restype = ctypes.c_int

