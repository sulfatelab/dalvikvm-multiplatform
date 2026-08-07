import argparse
import json
from pathlib import Path
import struct
import subprocess
import zlib

import pytest

from tools import run_dex2oat_no_image


def _args(tmp_path: Path) -> argparse.Namespace:
    dex2oat = tmp_path / "bin" / "dex2oat.exe"
    boot_jar = tmp_path / "managed" / "boot.jar"
    input_jar = tmp_path / "managed" / "hello.jar"
    dex2oat.parent.mkdir(parents=True)
    boot_jar.parent.mkdir()
    dex2oat.write_bytes(b"tool")
    boot_jar.write_bytes(b"boot-dex")
    input_jar.write_bytes(b"input-dex")
    return argparse.Namespace(
        target_id="windows-x86_64-msvc",
        dex2oat=dex2oat,
        boot_jar=boot_jar,
        input_jar=input_jar,
        output_root=tmp_path / "results" / "dex2oat-no-image",
        instruction_set="x86_64",
        library_dir=[dex2oat.parent],
        parallel=2,
        timeout=30,
    )


def _fake_oat(alignment: int = 64 * 1024) -> bytes:
    names = b"\0.rodata\0.text\0.dynamic\0.dynsym\0.dynstr\0.shstrtab\0"
    name_offsets = {
        name: names.index(name.encode("ascii"))
        for name in (".rodata", ".text", ".dynamic", ".dynsym", ".dynstr", ".shstrtab")
    }
    data = bytearray(0x800)
    program_offset = 64
    program_count = 2
    section_offset = 0x500
    section_count = 7
    ident = b"\x7fELF" + bytes((2, 1, 1, 3, 0)) + bytes(7)
    struct.pack_into(
        "<16sHHIQQQIHHHHHH",
        data,
        0,
        ident,
        3,
        62,
        1,
        0,
        program_offset,
        section_offset,
        0,
        64,
        56,
        program_count,
        64,
        section_count,
        6,
    )
    struct.pack_into("<IIQQQQQQ", data, program_offset, 1, 5, 0, 0, 0, len(data), len(data), alignment)
    struct.pack_into("<IIQQQQQQ", data, program_offset + 56, 2, 4, 0x200, 0x200, 0, 0x20, 0x20, 8)
    data[0x300:0x308] = b"oat\n265\0"
    data[0x400 : 0x400 + len(names)] = names
    section_values = [
        (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        (name_offsets[".rodata"], 1, 2, 0x300, 0x300, 0x20, 0, 0, 4, 0),
        (name_offsets[".text"], 1, 6, 0x340, 0x340, 0x20, 0, 0, 16, 0),
        (name_offsets[".dynamic"], 6, 3, 0x200, 0x200, 0x20, 5, 0, 8, 16),
        (name_offsets[".dynsym"], 11, 2, 0x240, 0x240, 0x18, 5, 0, 8, 24),
        (name_offsets[".dynstr"], 3, 2, 0x280, 0x280, 0x20, 0, 0, 1, 0),
        (name_offsets[".shstrtab"], 3, 0, 0, 0x400, len(names), 0, 0, 1, 0),
    ]
    for index, values in enumerate(section_values):
        struct.pack_into("<IIQQQQIIQQ", data, section_offset + index * 64, *values)
    return bytes(data)


def _fake_vdex() -> bytes:
    data = bytearray(88)
    struct.pack_into("<4s4sI", data, 0, b"vdex", b"027\0", 4)
    sections = [
        (0, 60, 4),
        (1, 64, 16),
        (2, 80, 4),
        (3, 84, 4),
    ]
    for index, values in enumerate(sections):
        struct.pack_into("<III", data, 12 + index * 12, *values)
    data[60:64] = b"\x78\x56\x34\x12"
    data[64:72] = b"dex\n039\0"
    return bytes(data)


def _fake_windows_boot_oat() -> bytes:
    section_names = (
        b"\0.rodata\0.text\0.oat_unwind.windows\0.oat_cfg.windows\0"
        b".bss\0.dynsym\0.dynstr\0.shstrtab\0"
    )
    section_name_offsets = {
        name: section_names.index(name.encode("ascii"))
        for name in (
            ".rodata",
            ".text",
            ".oat_unwind.windows",
            ".oat_cfg.windows",
            ".bss",
            ".dynsym",
            ".dynstr",
            ".shstrtab",
        )
    }
    dynamic_names = (
        b"\0oatunwindwindows\0oatunwindwindowslastword\0"
        b"oatcfgwindows\0oatcfgwindowslastword\0"
    )
    dynamic_name_offsets = {
        name: dynamic_names.index(name.encode("ascii"))
        for name in (
            "oatunwindwindows",
            "oatunwindwindowslastword",
            "oatcfgwindows",
            "oatcfgwindowslastword",
        )
    }

    data = bytearray(0x1000)
    program_offset = 64
    program_count = 3
    section_offset = 0x900
    section_count = 9
    section_names_index = 8
    # `oatdata` itself need not have code alignment. OAT code offsets are
    # relative to this address, while CFG alignment applies to the resulting
    # target virtual address.
    rodata_address = 0x10208
    text_address = 0x20300
    text_size = 0x100
    unwind_address = 0x30500
    unwind_file_offset = 0x500
    entry_count = 7
    entries_offset = 48
    unwind_blob_offset = entries_offset + entry_count * 12
    unwind_payload = bytearray(unwind_blob_offset + 4)
    struct.pack_into(
        "<4s11I",
        unwind_payload,
        0,
        b"ouw\n",
        1,
        48,
        0x8664,
        12,
        entry_count,
        entries_offset,
        unwind_blob_offset,
        4,
        text_address - rodata_address,
        text_address - rodata_address + text_size,
        0,
    )
    for index in range(entry_count):
        begin = text_address - rodata_address + index * 0x10
        struct.pack_into(
            "<III",
            unwind_payload,
            entries_offset + index * 12,
            begin,
            begin + 8,
            unwind_address - rodata_address + unwind_blob_offset,
        )
    unwind_payload[unwind_blob_offset:] = b"\x01\0\0\0"
    struct.pack_into(
        "<I", unwind_payload, 44, zlib.adler32(unwind_payload) & 0xFFFFFFFF
    )
    cfg_file_offset = unwind_file_offset + len(unwind_payload)
    cfg_address = unwind_address + len(unwind_payload)
    target_count = 9
    cfg_payload = bytearray(48 + target_count * 8)
    code_begin = text_address - rodata_address
    struct.pack_into(
        "<4s11I",
        cfg_payload,
        0,
        b"ocfg",
        1,
        48,
        0x8664,
        1,
        8,
        target_count,
        48,
        code_begin,
        code_begin + text_size,
        0,
        0,
    )
    for index in range(target_count):
        kind_flags = 1 if index == 0 else 2 if index == 1 else 4
        struct.pack_into(
            "<II", cfg_payload, 48 + index * 8, code_begin + index * 0x10, kind_flags
        )
    struct.pack_into("<I", cfg_payload, 40, zlib.adler32(cfg_payload) & 0xFFFFFFFF)

    ident = b"\x7fELF" + bytes((2, 1, 1, 3, 0)) + bytes(7)
    struct.pack_into(
        "<16sHHIQQQIHHHHHH",
        data,
        0,
        ident,
        3,
        62,
        1,
        0,
        program_offset,
        section_offset,
        0,
        64,
        56,
        program_count,
        64,
        section_count,
        section_names_index,
    )
    program_headers = (
        (1, 4, 0x208, rodata_address, 0, 0x80, 0x80, 0x10000),
        (1, 5, 0x300, text_address, 0, text_size, text_size, 0x10000),
        (
            1,
            4,
            unwind_file_offset,
            unwind_address,
            0,
            len(unwind_payload) + len(cfg_payload),
            len(unwind_payload) + len(cfg_payload),
            0x10000,
        ),
    )
    for index, values in enumerate(program_headers):
        struct.pack_into("<IIQQQQQQ", data, program_offset + index * 56, *values)

    data[0x208:0x210] = b"oat\n265\0"
    data[unwind_file_offset : unwind_file_offset + len(unwind_payload)] = unwind_payload
    data[cfg_file_offset : cfg_file_offset + len(cfg_payload)] = cfg_payload
    dynsym_offset = 0x700
    dynstr_offset = 0x780
    data[dynstr_offset : dynstr_offset + len(dynamic_names)] = dynamic_names
    struct.pack_into(
        "<IBBHQQ",
        data,
        dynsym_offset + 24,
        dynamic_name_offsets["oatunwindwindows"],
        0x11,
        0,
        3,
        unwind_address,
        len(unwind_payload),
    )
    struct.pack_into(
        "<IBBHQQ",
        data,
        dynsym_offset + 48,
        dynamic_name_offsets["oatunwindwindowslastword"],
        0x11,
        0,
        3,
        unwind_address + len(unwind_payload) - 4,
        4,
    )
    struct.pack_into(
        "<IBBHQQ",
        data,
        dynsym_offset + 72,
        dynamic_name_offsets["oatcfgwindows"],
        0x11,
        0,
        4,
        cfg_address,
        len(cfg_payload),
    )
    struct.pack_into(
        "<IBBHQQ",
        data,
        dynsym_offset + 96,
        dynamic_name_offsets["oatcfgwindowslastword"],
        0x11,
        0,
        4,
        cfg_address + len(cfg_payload) - 4,
        4,
    )
    section_names_offset = 0xB80
    data[section_names_offset : section_names_offset + len(section_names)] = section_names
    section_values = (
        (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        (section_name_offsets[".rodata"], 1, 2, rodata_address, 0x208, 0x80, 0, 0, 4, 0),
        (section_name_offsets[".text"], 1, 6, text_address, 0x300, text_size, 0, 0, 16, 0),
        (
            section_name_offsets[".oat_unwind.windows"],
            1,
            2,
            unwind_address,
            unwind_file_offset,
            len(unwind_payload),
            0,
            0,
            0x10000,
            0,
        ),
        (
            section_name_offsets[".oat_cfg.windows"],
            1,
            2,
            cfg_address,
            cfg_file_offset,
            len(cfg_payload),
            0,
            0,
            4,
            0,
        ),
        (section_name_offsets[".bss"], 8, 3, 0x40000, 0x600, 0x80, 0, 0, 0x10000, 0),
        (section_name_offsets[".dynsym"], 11, 2, 0x10100, dynsym_offset, 120, 7, 1, 8, 24),
        (
            section_name_offsets[".dynstr"],
            3,
            2,
            0x10180,
            dynstr_offset,
            len(dynamic_names),
            0,
            0,
            1,
            0,
        ),
        (
            section_name_offsets[".shstrtab"],
            3,
            0,
            0,
            section_names_offset,
            len(section_names),
            0,
            0,
            1,
            0,
        ),
    )
    for index, values in enumerate(section_values):
        struct.pack_into("<IIQQQQIIQQ", data, section_offset + index * 64, *values)
    return bytes(data)


def _rewrite_fake_unwind_checksum(data: bytearray) -> None:
    unwind_file_offset = 0x500
    unwind_size = struct.unpack_from("<Q", data, 0x900 + 3 * 64 + 32)[0]
    struct.pack_into("<I", data, unwind_file_offset + 44, 0)
    checksum = zlib.adler32(
        data[unwind_file_offset : unwind_file_offset + unwind_size]
    ) & 0xFFFFFFFF
    struct.pack_into("<I", data, unwind_file_offset + 44, checksum)


def _rewrite_fake_cfg_checksum(data: bytearray) -> None:
    cfg_section_offset = 0x900 + 4 * 64
    cfg_file_offset, cfg_size = struct.unpack_from("<QQ", data, cfg_section_offset + 24)
    struct.pack_into("<I", data, cfg_file_offset + 40, 0)
    checksum = zlib.adler32(data[cfg_file_offset : cfg_file_offset + cfg_size]) & 0xFFFFFFFF
    struct.pack_into("<I", data, cfg_file_offset + 40, checksum)


def test_no_image_probe_runs_shell_free_and_validates_outputs(tmp_path, monkeypatch):
    args = _args(tmp_path)
    calls = []

    def run(command, **options):
        calls.append((command, options))
        oat = Path(next(value.split("=", 1)[1] for value in command if value.startswith("--oat-file=")))
        if not oat.is_absolute():
            oat = Path(options["cwd"]) / oat
        oat.write_bytes(_fake_oat())
        oat.with_suffix(".vdex").write_bytes(_fake_vdex())
        return subprocess.CompletedProcess(command, 0, stdout="compiled\n", stderr="")

    monkeypatch.setattr(run_dex2oat_no_image.subprocess, "run", run)
    output = run_dex2oat_no_image.run_probe(args)

    command, options = calls[0]
    assert options["shell"] is False
    assert "--force-determinism" not in command
    assert "--avoid-storing-invocation" in command
    assert "--swap-dex-size-threshold=0" in command
    assert not any(value == "--no-watch-dog" for value in command)
    assert any(value.endswith("missing-boot.art") for value in command)
    assert "-Xbootclasspath-locations:/system/framework/boot.jar" in command
    assert "--oat-file=probe.oat" in command
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert result["target_id"] == "windows-x86_64-msvc"
    assert result["image_mode"] == "none"
    assert result["logical_oat"] == "probe.oat"
    assert result["windows_aot_identity"]["component_topology"] == "single"
    assert (
        result["windows_aot_identity"]["startup_image_location"]
        == "runtime/boot-image/boot.art"
    )
    assert result["watchdog"] == "enabled"
    assert result["elf"]["segment_alignment"] == 64 * 1024
    assert result["elf"]["oat_version"] == "265"
    assert result["vdex"]["version"] == "027"
    assert result["vdex"]["section_count"] == 4
    assert result["vdex"]["dex_file_count"] == 1


def test_oat_validator_rejects_linux_alignment_for_windows(tmp_path):
    oat = tmp_path / "probe.oat"
    oat.write_bytes(_fake_oat(16 * 1024))
    with pytest.raises(run_dex2oat_no_image.Dex2OatProbeError, match="alignment"):
        run_dex2oat_no_image.validate_oat_elf(oat, expected_alignment=64 * 1024)


def test_windows_unwind_validator_accepts_canonical_transport(tmp_path):
    oat = tmp_path / "boot.oat"
    oat.write_bytes(_fake_windows_boot_oat())

    result = run_dex2oat_no_image.validate_windows_oat_unwind(oat)

    assert result["section"] == ".oat_unwind.windows"
    assert result["target_machine"] == 0x8664
    assert result["entry_count"] == 7
    assert result["unique_unwind_info_count"] == 1


def test_windows_unwind_validator_rejects_header_checksum_corruption(tmp_path):
    oat = tmp_path / "boot.oat"
    data = bytearray(_fake_windows_boot_oat())
    data[0x500 + 8] ^= 1
    oat.write_bytes(data)

    with pytest.raises(run_dex2oat_no_image.Dex2OatProbeError, match="header"):
        run_dex2oat_no_image.validate_windows_oat_unwind(oat)


def test_windows_unwind_validator_rejects_entry_corruption(tmp_path):
    oat = tmp_path / "boot.oat"
    data = bytearray(_fake_windows_boot_oat())
    struct.pack_into("<I", data, 0x500 + 48 + 4, 0x20000)
    _rewrite_fake_unwind_checksum(data)
    oat.write_bytes(data)

    with pytest.raises(run_dex2oat_no_image.Dex2OatProbeError, match="entry 0"):
        run_dex2oat_no_image.validate_windows_oat_unwind(oat)


def test_windows_unwind_validator_rejects_blob_corruption(tmp_path):
    oat = tmp_path / "boot.oat"
    data = bytearray(_fake_windows_boot_oat())
    data[0x500 + 132] = 2
    _rewrite_fake_unwind_checksum(data)
    oat.write_bytes(data)

    with pytest.raises(run_dex2oat_no_image.Dex2OatProbeError, match="flags/version"):
        run_dex2oat_no_image.validate_windows_oat_unwind(oat)


def test_windows_cfg_validator_accepts_canonical_transport(tmp_path):
    oat = tmp_path / "boot.oat"
    oat.write_bytes(_fake_windows_boot_oat())

    result = run_dex2oat_no_image.validate_windows_oat_cfg(oat)

    assert result["section"] == ".oat_cfg.windows"
    assert result["target_machine"] == 0x8664
    assert result["target_count"] == 9
    assert result["quick_candidate_count"] == 1
    assert result["jni_candidate_count"] == 1
    assert result["trampoline_candidate_count"] == 7


def test_windows_cfg_corruption_corpus_rejects_all_semantic_mutations(tmp_path):
    oat = tmp_path / "boot.oat"
    vdex = tmp_path / "boot.vdex"
    output = tmp_path / "cfg-corruption"
    oat.write_bytes(_fake_windows_boot_oat())
    vdex.write_bytes(_fake_vdex())

    record = run_dex2oat_no_image.build_windows_oat_cfg_corruption_corpus(
        oat, vdex, output
    )

    assert record["case_count"] == 18
    assert record["canonical_open_count"] == 2
    assert record["rejection_open_count"] == 36
    assert record["total_open_count"] == 38
    assert run_dex2oat_no_image.validate_windows_oat_cfg(output / "canonical.oat")
    cases = (output / "cases.txt").read_text(encoding="ascii").splitlines()
    assert cases == record["cases"]
    assert len(set(cases)) == 18
    for name in cases:
        assert (output / f"{name}.vdex").is_file()
        with pytest.raises(run_dex2oat_no_image.Dex2OatProbeError):
            run_dex2oat_no_image.validate_windows_oat_cfg(output / f"{name}.oat")


def test_windows_cfg_validator_rejects_checksum_corruption(tmp_path):
    oat = tmp_path / "boot.oat"
    data = bytearray(_fake_windows_boot_oat())
    data[0x588 + 48] ^= 0x10
    oat.write_bytes(data)

    with pytest.raises(run_dex2oat_no_image.Dex2OatProbeError, match="checksum"):
        run_dex2oat_no_image.validate_windows_oat_cfg(oat)


@pytest.mark.parametrize(
    ("entry_index", "code_offset", "kind_flags"),
    (
        (1, 0x10109, 2),  # Target virtual address is not 16-byte aligned.
        (1, 0x100f8, 2),  # Not strictly ascending/unique.
        (1, 0x10108, 0),  # No target role.
        (1, 0x10108, 0x10),  # Unknown serialized role.
        (8, 0x101f8, 4),  # Outside the half-open code range.
    ),
)
def test_windows_cfg_validator_rejects_invalid_target(
    tmp_path, entry_index, code_offset, kind_flags
):
    oat = tmp_path / "boot.oat"
    data = bytearray(_fake_windows_boot_oat())
    struct.pack_into("<II", data, 0x588 + 48 + entry_index * 8, code_offset, kind_flags)
    _rewrite_fake_cfg_checksum(data)
    oat.write_bytes(data)

    with pytest.raises(run_dex2oat_no_image.Dex2OatProbeError, match="target"):
        run_dex2oat_no_image.validate_windows_oat_cfg(oat)


def test_windows_cfg_validator_rejects_missing_trampoline_role(tmp_path):
    oat = tmp_path / "boot.oat"
    data = bytearray(_fake_windows_boot_oat())
    struct.pack_into("<I", data, 0x588 + 48 + 2 * 8 + 4, 1)
    _rewrite_fake_cfg_checksum(data)
    oat.write_bytes(data)

    with pytest.raises(run_dex2oat_no_image.Dex2OatProbeError, match="seven trampolines"):
        run_dex2oat_no_image.validate_windows_oat_cfg(oat)


def test_windows_cfg_validator_rejects_anchor_corruption(tmp_path):
    oat = tmp_path / "boot.oat"
    data = bytearray(_fake_windows_boot_oat())
    struct.pack_into("<Q", data, 0x700 + 72 + 8, 0x30580)
    oat.write_bytes(data)

    with pytest.raises(run_dex2oat_no_image.Dex2OatProbeError, match="anchor"):
        run_dex2oat_no_image.validate_windows_oat_cfg(oat)


def test_elf_section_reader_accepts_nobits_beyond_file_bytes():
    names = b"\0.bss\0.shstrtab\0"
    data = bytearray(3 * 64 + len(names))
    names_offset = 3 * 64
    sections = [
        (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        (names.index(b".bss"), 8, 3, 0x10000, 0x10000, 0x2000, 0, 0, 0x1000, 0),
        (
            names.index(b".shstrtab"),
            3,
            0,
            0,
            names_offset,
            len(names),
            0,
            0,
            1,
            0,
        ),
    ]
    for index, values in enumerate(sections):
        struct.pack_into("<IIQQQQIIQQ", data, index * 64, *values)
    data[names_offset:] = names

    parsed = run_dex2oat_no_image._read_elf_sections(
        bytes(data),
        section_offset=0,
        section_entry_size=64,
        section_count=3,
        section_names_index=2,
    )

    assert parsed[".bss"] == (0x10000, 0x2000)


def test_vdex_validator_rejects_trailing_bytes(tmp_path):
    vdex = tmp_path / "probe.vdex"
    vdex.write_bytes(_fake_vdex() + b"padding")
    with pytest.raises(run_dex2oat_no_image.Dex2OatProbeError, match="section layout"):
        run_dex2oat_no_image.validate_vdex(vdex)


def test_probe_preserves_failure_logs(tmp_path, monkeypatch):
    args = _args(tmp_path)
    monkeypatch.setattr(
        run_dex2oat_no_image.subprocess,
        "run",
        lambda command, **options: subprocess.CompletedProcess(
            command, 3, stdout="", stderr="runtime initialization failed\n"
        ),
    )
    with pytest.raises(run_dex2oat_no_image.Dex2OatProbeError, match="exit=3"):
        run_dex2oat_no_image.run_probe(args)
    assert (args.output_root / "stderr.txt").read_text(encoding="utf-8") == (
        "runtime initialization failed\n"
    )
