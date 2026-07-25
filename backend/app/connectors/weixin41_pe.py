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


@dataclass(frozen=True)
class PeSection:
    name: str
    virtual_address: int
    raw_offset: int
    raw_size: int


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


def _parse_header(data: bytes) -> tuple[int, int, tuple[PeSection, ...]]:
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
    section_offset = optional_offset + optional_size
    sections: list[PeSection] = []
    for index in range(section_count):
        offset = section_offset + index * 40
        if offset + 40 > len(data):
            raise ValueError("truncated PE section table")
        raw_name = data[offset : offset + 8].split(b"\x00", 1)[0]
        name = raw_name.decode("ascii", errors="replace")
        virtual_address, raw_size, raw_offset = struct.unpack_from("<III", data, offset + 12)[0:3]
        if raw_offset + raw_size > len(data):
            raise ValueError(f"section {name!r} exceeds file bounds")
        sections.append(PeSection(name, virtual_address, raw_offset, raw_size))
    return machine, optional_magic, tuple(sections)


def _find_rip_relative_refs(section: PeSection, data: bytes, targets: set[int]) -> list[int]:
    refs: list[int] = []
    search_from = 0
    while True:
        index = data.find(b"\x48\x8D", search_from)
        if index < 0 or index + 7 > len(data):
            break
        search_from = index + 2
        # x64 LEA r64, [RIP + disp32], with any destination register.
        modrm = data[index + 2]
        if modrm & 0xC7 != 0x05:
            continue
        displacement = struct.unpack_from("<i", data, index + 3)[0]
        target_rva = section.virtual_address + index + 7 + displacement
        if target_rva in targets:
            refs.append(section.virtual_address + index)
    return refs


def _find_function_candidates(section: PeSection, data: bytes, refs: list[int]) -> list[int]:
    prologues = (b"\x40\x53", b"\x48\x83\xEC", b"\x48\x89\x5C\x24")
    candidates: set[int] = set()
    for reference_rva in refs:
        start = reference_rva - section.virtual_address
        for index in range(max(0, start - 0x800), start + 1):
            if any(data.startswith(prologue, index) for prologue in prologues):
                candidates.add(section.virtual_address + index)
    return sorted(candidates)


def analyze_pe(path: str | Path, anchor: bytes = DEFAULT_ANCHOR) -> PeAnchorReport:
    data = Path(path).read_bytes()
    machine, optional_magic, sections = _parse_header(data)
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
        candidates.extend(_find_function_candidates(section, section_data, section_refs))
    return PeAnchorReport(
        machine,
        optional_magic,
        sections,
        tuple(sorted(set(anchor_rvas))),
        tuple(sorted(set(references))),
        tuple(sorted(set(candidates))),
    )
