"""Windows kill-on-close job ownership for isolated plugin workers."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Any


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("ProcessTime", ctypes.c_int64), ("JobTime", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD), ("MinWorkingSet", ctypes.c_size_t),
        ("MaxWorkingSet", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IOCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in (
        "ReadOps", "WriteOps", "OtherOps", "ReadBytes", "WriteBytes", "OtherBytes"
    )]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimits), ("IoInfo", _IOCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class WindowsJob:
    """Own a suspended worker and descendants before its first instruction."""

    def __init__(self, process: Any) -> None:
        # Loaded only on Windows; Any keeps Linux type checking platform neutral.
        api: Any = ctypes
        self.kernel = api.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD
        ]
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise OSError("Could not create the VST worker job.")
        limits = _ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        try:
            if not self.kernel.SetInformationJobObject(
                self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
            ):
                raise OSError("Could not configure the VST worker job.")
            if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
                raise OSError("Could not contain the VST worker in a process job.")
            ntdll = api.WinDLL("ntdll")
            ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
            ntdll.NtResumeProcess.restype = wintypes.LONG
            if ntdll.NtResumeProcess(int(process._handle)) != 0:
                raise OSError("Could not resume the contained VST worker.")
        except BaseException:
            self.close()
            process.kill()
            process.wait()
            raise

    def close(self) -> None:
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
