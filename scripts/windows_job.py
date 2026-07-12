from __future__ import annotations

import os
from typing import Any


class WindowsJob:
    """Best-effort Windows Job Object with kill-on-close process containment."""

    def __init__(self) -> None:
        self.handle: int | None = None
        self.assigned = False
        self.created = False
        self.closed = False
        self.error: str | None = None

    def _append_error(self, detail: str) -> None:
        self.error = detail if not self.error else self.error + "; " + detail

    def create(self) -> bool:
        if os.name != "nt":
            self._append_error("Windows Job Object is unavailable on this platform")
            return False
        try:
            import ctypes
            from ctypes import wintypes

            class IO_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("ReadOperationCount", ctypes.c_ulonglong),
                    ("WriteOperationCount", ctypes.c_ulonglong),
                    ("OtherOperationCount", ctypes.c_ulonglong),
                    ("ReadTransferCount", ctypes.c_ulonglong),
                    ("WriteTransferCount", ctypes.c_ulonglong),
                    ("OtherTransferCount", ctypes.c_ulonglong),
                ]

            class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("PerProcessUserTimeLimit", ctypes.c_longlong),
                    ("PerJobUserTimeLimit", ctypes.c_longlong),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD),
                ]

            class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                    ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t),
                ]

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
            kernel32.CreateJobObjectW.restype = wintypes.HANDLE
            kernel32.SetInformationJobObject.argtypes = [
                wintypes.HANDLE,
                ctypes.c_int,
                ctypes.c_void_p,
                wintypes.DWORD,
            ]
            kernel32.SetInformationJobObject.restype = wintypes.BOOL

            handle = kernel32.CreateJobObjectW(None, None)
            if not handle:
                raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
            self.handle = int(handle)
            self.created = True

            information = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            information.BasicLimitInformation.LimitFlags = 0x00002000
            ok = kernel32.SetInformationJobObject(
                handle,
                9,
                ctypes.byref(information),
                ctypes.sizeof(information),
            )
            if not ok:
                raise OSError(
                    ctypes.get_last_error(),
                    "SetInformationJobObject failed",
                )
            return True
        except (OSError, ValueError) as exc:
            self._append_error(f"{type(exc).__name__}: {exc}")
            self.close()
            return False

    def assign(self, pid: int) -> bool:
        if os.name != "nt" or self.handle is None:
            return False
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.argtypes = [
                wintypes.DWORD,
                wintypes.BOOL,
                wintypes.DWORD,
            ]
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.AssignProcessToJobObject.argtypes = [
                wintypes.HANDLE,
                wintypes.HANDLE,
            ]
            kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL

            process_handle = kernel32.OpenProcess(0x0001 | 0x0100, False, pid)
            if not process_handle:
                raise OSError(ctypes.get_last_error(), "OpenProcess failed")
            try:
                if not kernel32.AssignProcessToJobObject(
                    wintypes.HANDLE(self.handle),
                    process_handle,
                ):
                    raise OSError(
                        ctypes.get_last_error(),
                        "AssignProcessToJobObject failed",
                    )
            finally:
                kernel32.CloseHandle(process_handle)
            self.assigned = True
            return True
        except (OSError, ValueError) as exc:
            self._append_error(f"{type(exc).__name__}: {exc}")
            return False

    def terminate(self, exit_code: int = 124) -> bool:
        if os.name != "nt" or self.handle is None or not self.assigned:
            return False
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
            kernel32.TerminateJobObject.restype = wintypes.BOOL
            if not kernel32.TerminateJobObject(
                wintypes.HANDLE(self.handle),
                exit_code,
            ):
                raise OSError(
                    ctypes.get_last_error(),
                    "TerminateJobObject failed",
                )
            return True
        except (OSError, ValueError) as exc:
            self._append_error(f"{type(exc).__name__}: {exc}")
            return False

    def close(self) -> None:
        if self.closed or self.handle is None or os.name != "nt":
            self.closed = True
            return
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            if not kernel32.CloseHandle(wintypes.HANDLE(self.handle)):
                self._append_error(
                    f"CloseHandle error {ctypes.get_last_error()}"
                )
        except (OSError, ValueError) as exc:
            self._append_error(f"{type(exc).__name__}: {exc}")
        finally:
            self.handle = None
            self.closed = True

    def evidence(self) -> dict[str, Any]:
        return {
            "created": self.created,
            "assigned": self.assigned,
            "closed": self.closed,
            "error": self.error,
        }
