import argparse
import json
from pathlib import Path
import struct
import subprocess

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
    assert "--force-determinism" in command
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
