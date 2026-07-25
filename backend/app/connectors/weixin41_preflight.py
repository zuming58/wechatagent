"""Read-only Windows Weixin 4.1 process preflight.

This command verifies that the current user (or one explicitly elevated run)
can query the Weixin process and read its executable header.  It deliberately
does not install software, set breakpoints, write process memory, or inspect
chat databases.
"""

from __future__ import annotations

import csv
import ctypes
import ctypes.wintypes as wintypes
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .weixin41_pe import PeAnchorReport, analyze_pe
from .wx_cli import WxCliConnector

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_VM_READ = 0x0010
LIST_MODULES_64BIT = 0x02
ERROR_ACCESS_DENIED = 5


@dataclass(frozen=True)
class ProcessPreflight:
    pid: int
    image_name: str
    image_version: str | None
    image_path_available: bool
    handle_opened: bool
    header_readable: bool
    pe_report: PeAnchorReport | None
    error_code: str | None = None


class MODULEINFO(ctypes.Structure):
    _fields_ = [
        ("lpBaseOfDll", ctypes.c_void_p),
        ("SizeOfImage", wintypes.DWORD),
        ("EntryPoint", ctypes.c_void_p),
    ]


def _process_rows() -> list[tuple[int, int]]:
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq Weixin.exe", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        encoding="mbcs",
        errors="replace",
        timeout=10,
        check=False,
    )
    rows: list[tuple[int, int]] = []
    for row in csv.reader(line for line in result.stdout.splitlines() if line.strip()):
        if len(row) < 5 or row[0].lower() != "weixin.exe":
            continue
        try:
            pid = int(row[1])
            memory_kb = int(row[4].replace(",", "").replace(" K", "").strip())
        except ValueError:
            continue
        rows.append((pid, memory_kb))
    return sorted(rows, key=lambda item: item[1], reverse=True)


def _query_image_path(handle: int) -> Path | None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    query = kernel32.QueryFullProcessImageNameW
    query.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    query.restype = wintypes.BOOL
    size = wintypes.DWORD(32768)
    buffer = ctypes.create_unicode_buffer(size.value)
    if not query(handle, 0, buffer, ctypes.byref(size)):
        return None
    return Path(buffer.value)


def _read_module_header(handle: int, module_name: str) -> bool:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    enum_modules = psapi.EnumProcessModulesEx
    enum_modules.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.HMODULE),
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.DWORD,
    ]
    enum_modules.restype = wintypes.BOOL
    get_info = psapi.GetModuleInformation
    get_info.argtypes = [wintypes.HANDLE, wintypes.HMODULE, ctypes.POINTER(MODULEINFO), wintypes.DWORD]
    get_info.restype = wintypes.BOOL
    get_name = psapi.GetModuleBaseNameW
    get_name.argtypes = [wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    get_name.restype = wintypes.DWORD
    read_memory = kernel32.ReadProcessMemory
    read_memory.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    read_memory.restype = wintypes.BOOL

    modules = (wintypes.HMODULE * 1024)()
    used = wintypes.DWORD()
    if not enum_modules(handle, modules, ctypes.sizeof(modules), ctypes.byref(used), LIST_MODULES_64BIT):
        return False
    module_count = used.value // ctypes.sizeof(wintypes.HMODULE)
    for index in range(module_count):
        module = modules[index]
        name_buffer = ctypes.create_unicode_buffer(32768)
        if not get_name(handle, module, name_buffer, len(name_buffer)):
            continue
        if name_buffer.value.lower() != module_name.lower():
            continue
        info = MODULEINFO()
        if not get_info(handle, module, ctypes.byref(info), ctypes.sizeof(info)):
            return False
        header = ctypes.create_string_buffer(2)
        read = ctypes.c_size_t()
        return bool(read_memory(handle, info.lpBaseOfDll, header, 2, ctypes.byref(read))) and header.raw == b"MZ"
    return False


def _find_weixin_dll(image_path: Path, version: str | None) -> Path | None:
    candidates = [image_path.parent / "Weixin.dll"]
    if version:
        candidates.insert(0, image_path.parent / version / "Weixin.dll")
    return next((candidate for candidate in candidates if candidate.exists()), None)


def _close(handle: int) -> None:
    ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(handle)


def preflight_pid(pid: int) -> ProcessPreflight:
    if platform.system() != "Windows":
        raise RuntimeError("unsupported_platform")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    open_process.restype = wintypes.HANDLE
    handle = open_process(PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        return ProcessPreflight(pid, "Weixin.exe", None, False, False, False, None, f"win32:{error}")
    try:
        image_path = _query_image_path(handle)
        report = None
        readable = _read_module_header(handle, "Weixin.exe")
        version = WxCliConnector._wechat_version()
        if image_path and image_path.exists():
            module_path = _find_weixin_dll(image_path, version)
            if module_path:
                report = analyze_pe(module_path)
        return ProcessPreflight(
            pid,
            "Weixin.exe",
            version,
            image_path is not None,
            True,
            readable,
            report,
            None if readable else f"win32:{ctypes.get_last_error()}",
        )
    finally:
        _close(handle)


def run_preflight() -> list[ProcessPreflight]:
    return [preflight_pid(pid) for pid, _memory_kb in _process_rows()]


def main() -> int:
    results = run_preflight()
    if not results:
        print("WEIXIN_PREFLIGHT=wechat_offline")
        return 2
    for result in results:
        report = result.pe_report
        print(
            "WEIXIN_PREFLIGHT="
            f"pid={result.pid};handle={result.handle_opened};header={result.header_readable};"
            f"x64={bool(report and report.is_x64)};anchors={len(report.anchor_rvas) if report else 0};"
            f"refs={len(report.rip_relative_reference_rvas) if report else 0};"
            f"candidates={len(report.candidate_function_rvas) if report else 0};error={result.error_code or 'none'}"
        )
    return 0 if all(item.header_readable for item in results) else 3


if __name__ == "__main__":
    raise SystemExit(main())
