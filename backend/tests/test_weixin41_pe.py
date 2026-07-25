import struct

from app.connectors.weixin41_pe import DEFAULT_ANCHOR, analyze_pe


def make_synthetic_pe(path):
    data = bytearray(0x600)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\x00\x00"
    struct.pack_into("<HHIIIHH", data, 0x84, 0x8664, 2, 0, 0, 0, 0xF0, 0)
    optional_offset = 0x98
    struct.pack_into("<H", data, optional_offset, 0x20B)
    section_offset = optional_offset + 0xF0
    data[section_offset : section_offset + 8] = b".text\x00\x00\x00"
    struct.pack_into("<IIII", data, section_offset + 8, 0x100, 0x300, 0x100, 0x300)
    data[section_offset + 40 : section_offset + 48] = b".rdata\x00\x00"
    struct.pack_into("<IIII", data, section_offset + 48, 0x100, 0x400, 0x100, 0x400)
    anchor_rva = 0x410
    data[0x410 : 0x410 + len(DEFAULT_ANCHOR)] = DEFAULT_ANCHOR
    instruction_rva = 0x320
    displacement = anchor_rva - (instruction_rva + 7)
    data[0x320 : 0x327] = b"\x48\x8D\x0D" + struct.pack("<i", displacement)
    data[0x310 : 0x312] = b"\x40\x53"
    path.write_bytes(data)


def test_analyze_pe_finds_wcdb_anchor_and_rip_reference(tmp_path):
    binary = tmp_path / "Weixin.dll"
    make_synthetic_pe(binary)

    report = analyze_pe(binary)

    assert report.is_x64
    assert report.anchor_rvas == (0x410,)
    assert report.rip_relative_reference_rvas == (0x320,)
    assert report.candidate_function_rvas == (0x310,)


def test_analyze_pe_rejects_non_pe_file(tmp_path):
    binary = tmp_path / "not-a-pe.bin"
    binary.write_bytes(b"not-pe")

    try:
        analyze_pe(binary)
    except ValueError as error:
        assert str(error) == "not a PE file"
    else:
        raise AssertionError("expected invalid PE failure")
