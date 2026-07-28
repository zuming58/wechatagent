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
import hashlib
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .weixin41_pe import PeAnalysisError, PeAnchorReport, analyze_pe_bytes, select_capture_hook_rva
from .wx_cli import WxCliConnector

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_VM_READ = 0x0010
LIST_MODULES_64BIT = 0x02
ERROR_ACCESS_DENIED = 5
SUPPORTED_VERSION = "4.1.12.24"


@dataclass(frozen=True)
class ProcessPreflight:
    pid: int
    image_name: str
    image_version: str | None
    image_path_available: bool
    handle_opened: bool
    header_readable: bool
    pe_report: PeAnchorReport | None
    module_sha256: str | None = None
    error_code: str | None = None

    @property
    def capture_ready(self) -> bool:
        if not (
            self.image_version == SUPPORTED_VERSION
            and self.image_path_available
            and self.handle_opened
            and self.header_readable
            and self.pe_report is not None
            and self.module_sha256
            and len(self.module_sha256) == 64
            and self.error_code is None
        ):
            return False
        try:
            select_capture_hook_rva(self.pe_report)
        except PeAnalysisError:
            return False
        return True


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
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def _close(handle: int) -> None:
    close_handle = ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    close_handle(handle)


def _inspect_open_process(pid: int, handle: int) -> ProcessPreflight:
    image_path = _query_image_path(handle)
    image_path_available = bool(image_path and image_path.is_file())
    try:
        version = WxCliConnector._executable_version(image_path) if image_path else None
    except (OSError, subprocess.SubprocessError):
        version = None
    module_path = _find_weixin_dll(image_path, version) if image_path_available and image_path else None
    report = None
    module_sha256 = None
    module_error = None
    readable = _read_module_header(handle, "Weixin.exe")
    if module_path:
        try:
            module_bytes = module_path.read_bytes()
            module_sha256 = hashlib.sha256(module_bytes).hexdigest()
            report = analyze_pe_bytes(module_bytes)
            select_capture_hook_rva(report)
        except PeAnalysisError as error:
            module_error = error.error_code
        except (OSError, ValueError):
            module_error = "module_analysis_failed"

    error_code = None
    if not image_path_available:
        error_code = "image_path_unavailable"
    elif not readable:
        error_code = "process_header_unreadable"
    elif version is None:
        error_code = "version_unavailable"
    elif version != SUPPORTED_VERSION:
        error_code = "unsupported_version"
    elif module_path is None:
        error_code = "module_missing"
    elif module_error:
        error_code = module_error
    return ProcessPreflight(
        pid=pid,
        image_name="Weixin.exe",
        image_version=version,
        image_path_available=image_path_available,
        handle_opened=True,
        header_readable=readable,
        pe_report=report,
        module_sha256=module_sha256,
        error_code=error_code,
    )


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
        return ProcessPreflight(
            pid=pid,
            image_name="Weixin.exe",
            image_version=None,
            image_path_available=False,
            handle_opened=False,
            header_readable=False,
            pe_report=None,
            error_code=f"win32:{error}",
        )
    try:
        return _inspect_open_process(pid, handle)
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
            f"pid={result.pid};ready={result.capture_ready};handle={result.handle_opened};header={result.header_readable};"
            f"x64={bool(report and report.is_x64)};anchors={len(report.anchor_rvas) if report else 0};"
            f"refs={len(report.rip_relative_reference_rvas) if report else 0};"
            f"candidates={len(report.candidate_function_rvas) if report else 0};error={result.error_code or 'none'}"
        )
    return 0 if all(item.capture_ready for item in results) else 3


if __name__ == "__main__":
    raise SystemExit(main())
