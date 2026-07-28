"""Read-only PE anchor analysis for the Windows Weixin 4.1 preflight.

The analyzer never opens a process.  It only inspects an explicitly supplied
PE file and returns offsets, allowing the future capture helper to fail closed
when a build does not contain the expected WCDB anchor.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

PE_SIGNATURE = b"PE\x00\x00"
PE64_MACHINE = 0x8664
DEFAULT_ANCHOR = b"com.Tencent.WCDB.Config.Cipher"
EXCEPTION_DIRECTORY_INDEX = 3
RUNTIME_FUNCTION_SIZE = 12
MAX_REFERENCE_DISTANCE = 0x400


class PeAnalysisError(RuntimeError):
    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


@dataclass(frozen=True)
class PeSection:
    name: str
    virtual_address: int
    raw_offset: int
    raw_size: int
    virtual_size: int = 0


@dataclass(frozen=True)
class PeAnchorReport:
    machine: int
    optional_magic: int
    sections: tuple[PeSection, ...]
    anchor_rvas: tuple[int, ...]
    rip_relative_reference_rvas: tuple[int, ...]
    candidate_function_rvas: tuple[int, ...]

    @property
    def is_x64(self) -> bool:
        return self.machine == PE64_MACHINE and self.optional_magic == 0x20B


def _parse_header(data: bytes) -> tuple[int, int, tuple[PeSection, ...], int, int]:
    if len(data) < 0x40 or data[:2] != b"MZ":
        raise ValueError("not a PE file")
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if pe_offset + 24 > len(data) or data[pe_offset : pe_offset + 4] != PE_SIGNATURE:
        raise ValueError("invalid PE signature")
    machine, section_count, _timestamp, _symbol_table, _symbol_count, optional_size, _characteristics = struct.unpack_from(
        "<HHIIIHH", data, pe_offset + 4
    )
    optional_offset = pe_offset + 24
    if optional_offset + optional_size > len(data) or optional_size < 2:
        raise ValueError("truncated PE optional header")
    optional_magic = struct.unpack_from("<H", data, optional_offset)[0]
    exception_rva = 0
    exception_size = 0
    if optional_magic == 0x20B:
        data_directories_offset = optional_offset + 112
        exception_offset = data_directories_offset + EXCEPTION_DIRECTORY_INDEX * 8
        if exception_offset + 8 <= optional_offset + optional_size:
            exception_rva, exception_size = struct.unpack_from("<II", data, exception_offset)
    section_offset = optional_offset + optional_size
    sections: list[PeSection] = []
    for index in range(section_count):
        offset = section_offset + index * 40
        if offset + 40 > len(data):
            raise ValueError("truncated PE section table")
        raw_name = data[offset : offset + 8].split(b"\x00", 1)[0]
        name = raw_name.decode("ascii", errors="replace")
        virtual_size, virtual_address, raw_size, raw_offset = struct.unpack_from("<IIII", data, offset + 8)
        if raw_offset + raw_size > len(data):
            raise ValueError(f"section {name!r} exceeds file bounds")
        sections.append(PeSection(name, virtual_address, raw_offset, raw_size, virtual_size))
    return machine, optional_magic, tuple(sections), exception_rva, exception_size


def _find_rip_relative_refs(section: PeSection, data: bytes, targets: set[int]) -> list[int]:
    refs: list[int] = []
    for index in range(max(0, len(data) - 6)):
        # REX.W LEA r64, [RIP + disp32], including r8-r15 destinations.
        if not 0x48 <= data[index] <= 0x4F or data[index + 1] != 0x8D:
            continue
        modrm = data[index + 2]
        if modrm & 0xC7 != 0x05:
            continue
        displacement = struct.unpack_from("<i", data, index + 3)[0]
        target_rva = section.virtual_address + index + 7 + displacement
        if target_rva in targets:
            refs.append(section.virtual_address + index)
    return refs


def _rva_to_file_offset(sections: tuple[PeSection, ...], rva: int, size: int) -> int | None:
    for section in sections:
        span = max(section.virtual_size, section.raw_size)
        if section.virtual_address <= rva and rva + size <= section.virtual_address + span:
            offset = section.raw_offset + rva - section.virtual_address
            if offset + size <= section.raw_offset + section.raw_size:
                return offset
    return None


def _runtime_functions(
    data: bytes,
    sections: tuple[PeSection, ...],
    exception_rva: int,
    exception_size: int,
) -> tuple[tuple[int, int], ...]:
    if not exception_rva or not exception_size:
        return ()
    if exception_size % RUNTIME_FUNCTION_SIZE:
        raise ValueError("invalid PE exception directory size")
    offset = _rva_to_file_offset(sections, exception_rva, exception_size)
    if offset is None:
        raise ValueError("PE exception directory exceeds file bounds")
    functions: list[tuple[int, int]] = []
    for entry_offset in range(offset, offset + exception_size, RUNTIME_FUNCTION_SIZE):
        begin, end, _unwind = struct.unpack_from("<III", data, entry_offset)
        if begin == end == 0:
            continue
        if begin >= end:
            raise ValueError("invalid PE runtime function range")
        functions.append((begin, end))
    return tuple(functions)


def _find_function_candidates(refs: list[int], functions: tuple[tuple[int, int], ...]) -> list[int]:
    return sorted({begin for reference in refs for begin, end in functions if begin <= reference < end})


def select_capture_hook_rva(report: PeAnchorReport) -> int:
    if not report.is_x64:
        raise PeAnalysisError("unsupported_architecture")
    if len(report.anchor_rvas) != 1:
        raise PeAnalysisError("wcdb_anchor_ambiguous")
    if len(report.rip_relative_reference_rvas) != 1:
        raise PeAnalysisError("wcdb_reference_ambiguous")
    reference = report.rip_relative_reference_rvas[0]
    containing = [candidate for candidate in report.candidate_function_rvas if candidate <= reference]
    if len(containing) != 1:
        raise PeAnalysisError("capture_hook_ambiguous" if containing else "capture_hook_missing")
    hook = containing[0]
    if reference - hook > MAX_REFERENCE_DISTANCE:
        raise PeAnalysisError("capture_hook_too_distant")
    return hook


def analyze_pe_bytes(data: bytes, anchor: bytes = DEFAULT_ANCHOR) -> PeAnchorReport:
    machine, optional_magic, sections, exception_rva, exception_size = _parse_header(data)
    anchor_rvas: list[int] = []
    references: list[int] = []
    candidates: list[int] = []
    for section in sections:
        section_data = data[section.raw_offset : section.raw_offset + section.raw_size]
        search_from = 0
        while True:
            index = section_data.find(anchor, search_from)
            if index < 0:
                break
            anchor_rvas.append(section.virtual_address + index)
            search_from = index + 1
    anchor_targets = set(anchor_rvas)
    for section in sections:
        if section.name not in {".text", "CODE"}:
            continue
        section_data = data[section.raw_offset : section.raw_offset + section.raw_size]
        section_refs = _find_rip_relative_refs(section, section_data, anchor_targets)
        references.extend(section_refs)
    functions = _runtime_functions(data, sections, exception_rva, exception_size)
    candidates.extend(_find_function_candidates(references, functions))
    return PeAnchorReport(
        machine,
        optional_magic,
        sections,
        tuple(sorted(set(anchor_rvas))),
        tuple(sorted(set(references))),
        tuple(sorted(set(candidates))),
    )


def analyze_pe(path: str | Path, anchor: bytes = DEFAULT_ANCHOR) -> PeAnchorReport:
    return analyze_pe_bytes(Path(path).read_bytes(), anchor)
