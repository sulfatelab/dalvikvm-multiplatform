#!/usr/bin/env python3
"""Run and validate the first native Windows dex2oat no-image gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import sys
import time
import zlib

if __package__:
    from .windows_aot_identity import (
        LOGICAL_BOOT_JAR,
        LOGICAL_PROBE_INPUT_JAR,
        LOGICAL_PROBE_OAT,
        contract_record,
    )
else:
    from windows_aot_identity import (  # type: ignore[no-redef]
        LOGICAL_BOOT_JAR,
        LOGICAL_PROBE_INPUT_JAR,
        LOGICAL_PROBE_OAT,
        contract_record,
    )


LOGICAL_INPUT_JAR = LOGICAL_PROBE_INPUT_JAR
LOGICAL_OAT = LOGICAL_PROBE_OAT
OAT_VERSION = b"265\0"
VDEX_VERSION = b"027\0"
WINDOWS_X64_ELF_ALIGNMENT = 64 * 1024


class Dex2OatProbeError(RuntimeError):
    """The command or its output violated the no-image bring-up contract."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--dex2oat", type=Path, required=True)
    parser.add_argument("--boot-jar", type=Path, required=True)
    parser.add_argument("--input-jar", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--instruction-set", default="x86_64")
    parser.add_argument("--library-dir", type=Path, action="append", default=[])
    parser.add_argument("--parallel", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=600)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        run_probe(args)
        return 0
    except (Dex2OatProbeError, OSError, subprocess.SubprocessError) as exc:
        print(f"run_dex2oat_no_image.py: error: {exc}", file=sys.stderr)
        return 2


def run_probe(args: argparse.Namespace) -> Path:
    if args.target_id != "windows-x86_64-msvc":
        raise Dex2OatProbeError(
            f"the initial gate accepts only windows-x86_64-msvc, got {args.target_id!r}"
        )
    if args.instruction_set != "x86_64":
        raise Dex2OatProbeError(
            f"the initial gate accepts only x86_64, got {args.instruction_set!r}"
        )
    if not 1 <= args.parallel <= 64:
        raise Dex2OatProbeError("parallelism must be between 1 and 64")
    if args.timeout < 1:
        raise Dex2OatProbeError("timeout must be positive")

    dex2oat = _regular_file(args.dex2oat)
    boot_jar = _regular_file(args.boot_jar)
    input_jar = _regular_file(args.input_jar)
    library_dirs = [_directory(path) for path in args.library_dir]
    if dex2oat.parent not in library_dirs:
        library_dirs.insert(0, dex2oat.parent)

    output_root = _prepare_output_root(args.output_root)
    runtime_root = output_root / "runtime"
    for directory in (
        runtime_root,
        runtime_root / "data",
        runtime_root / "icu",
        runtime_root / "tmp",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    oat = output_root / "probe.oat"
    vdex = output_root / "probe.vdex"
    missing_image = output_root / "missing-boot.art"
    swap = output_root / "probe.swap"
    command = [
        str(dex2oat),
        f"--dex-file={input_jar}",
        f"--dex-location={LOGICAL_INPUT_JAR}",
        f"--oat-file={LOGICAL_OAT}",
        f"--instruction-set={args.instruction_set}",
        "--compiler-filter=speed",
        f"--boot-image={missing_image}",
        "--runtime-arg",
        f"-Xbootclasspath:{boot_jar}",
        "--runtime-arg",
        f"-Xbootclasspath-locations:{LOGICAL_BOOT_JAR}",
        "--runtime-arg",
        "-Xms64m",
        "--runtime-arg",
        "-Xmx512m",
        "--runtime-arg",
        "-Xnorelocate",
        f"--android-root={runtime_root}",
        f"--swap-file={swap}",
        "--swap-dex-size-threshold=0",
        "--swap-dex-count-threshold=0",
        "--avoid-storing-invocation",
        f"-j{args.parallel}",
    ]

    environment = dict(os.environ)
    environment.update(
        {
            "ANDROID_ROOT": str(runtime_root),
            "ANDROID_ART_ROOT": str(runtime_root),
            "ANDROID_I18N_ROOT": str(runtime_root),
            "ANDROID_DATA": str(runtime_root / "data"),
            "ICU_DATA": str(runtime_root / "icu"),
            "TMP": str(runtime_root / "tmp"),
            "TEMP": str(runtime_root / "tmp"),
            "TMPDIR": str(runtime_root / "tmp"),
        }
    )
    if os.name == "nt":
        system_root = environment.get("SystemRoot", r"C:\Windows")
        environment["PATH"] = os.pathsep.join(
            [*(str(path) for path in library_dirs), str(Path(system_root) / "System32")]
        )
    else:
        environment["LD_LIBRARY_PATH"] = os.pathsep.join(
            str(path) for path in library_dirs
        )

    started = time.monotonic()
    result = subprocess.run(
        command,
        cwd=output_root,
        env=environment,
        shell=False,
        check=False,
        capture_output=True,
        text=True,
        timeout=args.timeout,
    )
    elapsed = time.monotonic() - started
    (output_root / "stdout.txt").write_text(result.stdout, encoding="utf-8")
    (output_root / "stderr.txt").write_text(result.stderr, encoding="utf-8")

    missing = [path.name for path in (oat, vdex) if not path.is_file()]
    empty = [
        path.name
        for path in (oat, vdex)
        if path.is_file() and path.stat().st_size == 0
    ]
    if result.returncode != 0 or missing or empty:
        tail = "\n".join((result.stdout + "\n" + result.stderr).splitlines()[-80:])
        raise Dex2OatProbeError(
            f"dex2oat failed: exit={result.returncode}, missing={missing}, empty={empty}\n{tail}"
        )
    if missing_image.exists():
        raise Dex2OatProbeError("the no-image gate unexpectedly created missing-boot.art")
    unexpected_art = sorted(path.name for path in output_root.glob("*.art"))
    if unexpected_art:
        raise Dex2OatProbeError(
            f"the no-image gate unexpectedly produced ART images: {unexpected_art}"
        )

    elf = validate_oat_elf(oat, expected_alignment=WINDOWS_X64_ELF_ALIGNMENT)
    vdex_info = validate_vdex(vdex)
    manifest = {
        "schema_version": 1,
        "target_id": args.target_id,
        "instruction_set": args.instruction_set,
        "logical_boot_jar": LOGICAL_BOOT_JAR,
        "logical_input_jar": LOGICAL_INPUT_JAR,
        "logical_oat": LOGICAL_OAT,
        "windows_aot_identity": contract_record(),
        "compiler_filter": "speed",
        "image_mode": "none",
        "watchdog": "enabled",
        "swap_file_requested": True,
        "elapsed_seconds": round(elapsed, 3),
        "elf": elf,
        "vdex": vdex_info,
        "artifacts": [
            {
                "path": path.name,
                "size": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in (oat, vdex)
        ],
    }
    (output_root / "result.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "native dex2oat no-image gate passed: "
        f"oat={oat.stat().st_size}, vdex={vdex.stat().st_size}, "
        f"PT_LOAD={elf['load_segment_count']}, alignment={elf['segment_alignment']}"
    )
    return output_root


def validate_oat_elf(path: Path, *, expected_alignment: int) -> dict[str, object]:
    data = _regular_file(path).read_bytes()
    header_format = "<16sHHIQQQIHHHHHH"
    header_size = struct.calcsize(header_format)
    if len(data) < header_size:
        raise Dex2OatProbeError("probe.oat has a truncated ELF header")
    values = struct.unpack_from(header_format, data)
    (
        ident,
        elf_type,
        machine,
        version,
        entry,
        program_offset,
        section_offset,
        flags,
        elf_header_size,
        program_entry_size,
        program_count,
        section_entry_size,
        section_count,
        section_names_index,
    ) = values
    if ident[:4] != b"\x7fELF" or ident[4:7] != bytes((2, 1, 1)):
        raise Dex2OatProbeError("probe.oat is not ELF64 little-endian version 1")
    if ident[7] != 3 or ident[8] != 0:
        raise Dex2OatProbeError(
            f"probe.oat changed Linux ELF identity: EI_OSABI={ident[7]}, ABI={ident[8]}"
        )
    if (elf_type, machine, version, entry, flags) != (3, 62, 1, 0, 0):
        raise Dex2OatProbeError(
            "probe.oat has an unexpected ET_DYN/x86-64 header: "
            f"type={elf_type}, machine={machine}, version={version}, "
            f"entry={entry}, flags={flags}"
        )
    if elf_header_size != header_size or program_entry_size != 56:
        raise Dex2OatProbeError("probe.oat has unexpected ELF/program header sizes")
    if not 1 <= program_count <= 64:
        raise Dex2OatProbeError(f"probe.oat has invalid program-header count {program_count}")
    if program_offset + program_count * program_entry_size > len(data):
        raise Dex2OatProbeError("probe.oat has truncated program headers")

    load_count = 0
    dynamic_count = 0
    program_format = "<IIQQQQQQ"
    for index in range(program_count):
        values = struct.unpack_from(
            program_format, data, program_offset + index * program_entry_size
        )
        segment_type, segment_flags = values[:2]
        file_offset, virtual_address = values[2:4]
        file_size, memory_size, alignment = values[5:8]
        if file_size > memory_size or file_offset + file_size > len(data):
            raise Dex2OatProbeError(f"probe.oat has invalid program header {index}")
        if segment_type == 1:  # PT_LOAD
            load_count += 1
            if alignment != expected_alignment:
                raise Dex2OatProbeError(
                    f"PT_LOAD {index} alignment is {alignment}, expected {expected_alignment}"
                )
            if file_offset % alignment != virtual_address % alignment:
                raise Dex2OatProbeError(f"PT_LOAD {index} violates ELF congruence")
            if segment_flags & 2 and segment_flags & 1:
                raise Dex2OatProbeError(f"PT_LOAD {index} is writable and executable")
        elif segment_type == 2:  # PT_DYNAMIC
            dynamic_count += 1
    if load_count == 0 or dynamic_count != 1:
        raise Dex2OatProbeError(
            f"probe.oat requires PT_LOAD and one PT_DYNAMIC, got {load_count}/{dynamic_count}"
        )

    sections = _read_elf_sections(
        data,
        section_offset=section_offset,
        section_entry_size=section_entry_size,
        section_count=section_count,
        section_names_index=section_names_index,
    )
    required_sections = {".rodata", ".text", ".dynamic", ".dynsym", ".dynstr"}
    missing_sections = sorted(required_sections.difference(sections))
    if missing_sections:
        raise Dex2OatProbeError(f"probe.oat is missing sections: {missing_sections}")
    rodata_offset, rodata_size = sections[".rodata"]
    if rodata_size < 8 or data[rodata_offset : rodata_offset + 4] != b"oat\n":
        raise Dex2OatProbeError("probe.oat .rodata does not start with an OAT header")
    oat_version = data[rodata_offset + 4 : rodata_offset + 8]
    if oat_version != OAT_VERSION:
        raise Dex2OatProbeError(
            f"probe.oat logical version is {oat_version!r}, expected {OAT_VERSION!r}"
        )
    return {
        "class": "ELF64",
        "endianness": "little",
        "ei_osabi": ident[7],
        "ei_abi_version": ident[8],
        "type": elf_type,
        "machine": machine,
        "flags": flags,
        "load_segment_count": load_count,
        "segment_alignment": expected_alignment,
        "oat_version": oat_version.rstrip(b"\0").decode("ascii"),
    }


def _read_windows_boot_oat_layout(
    path: Path,
) -> tuple[
    bytes,
    list[tuple[int, ...]],
    list[tuple[int, ...]],
    dict[str, tuple[int, tuple[int, ...]]],
]:
    """Read the common Windows boot-OAT ELF envelope used by metadata validators."""
    data = _regular_file(path).read_bytes()
    header_format = "<16sHHIQQQIHHHHHH"
    header_size = struct.calcsize(header_format)
    if len(data) < header_size:
        raise Dex2OatProbeError("boot.oat has a truncated ELF header")
    header = struct.unpack_from(header_format, data)
    ident = header[0]
    if ident[:4] != b"\x7fELF" or ident[4:7] != bytes((2, 1, 1)):
        raise Dex2OatProbeError("boot.oat is not ELF64 little-endian version 1")
    if ident[7:9] != bytes((3, 0)):
        raise Dex2OatProbeError("boot.oat changed the Linux ELF identity")
    if header[1:5] != (3, 62, 1, 0) or header[7] != 0:
        raise Dex2OatProbeError("boot.oat has an unexpected ELF header")
    program_offset = header[5]
    program_entry_size = header[9]
    program_count = header[10]
    section_offset = header[6]
    section_entry_size = header[11]
    section_count = header[12]
    section_names_index = header[13]
    program_format = "<IIQQQQQQ"
    if (
        program_entry_size != struct.calcsize(program_format)
        or not 1 <= program_count <= 64
        or program_offset + program_count * program_entry_size > len(data)
    ):
        raise Dex2OatProbeError("boot.oat has invalid program-header dimensions")
    load_segments = []
    for index in range(program_count):
        segment = struct.unpack_from(
            program_format, data, program_offset + index * program_entry_size
        )
        segment_type, segment_flags = segment[:2]
        file_offset, virtual_address = segment[2:4]
        file_size, memory_size, alignment = segment[5:8]
        if file_size > memory_size or file_offset + file_size > len(data):
            raise Dex2OatProbeError(f"boot.oat has invalid program header {index}")
        if segment_type == 1:  # PT_LOAD
            if alignment != WINDOWS_X64_ELF_ALIGNMENT:
                raise Dex2OatProbeError(
                    f"boot.oat PT_LOAD {index} has invalid Windows alignment"
                )
            if file_offset % alignment != virtual_address % alignment:
                raise Dex2OatProbeError(
                    f"boot.oat PT_LOAD {index} violates ELF congruence"
                )
            if segment_flags & 3 == 3:
                raise Dex2OatProbeError(f"boot.oat PT_LOAD {index} is writable/executable")
            load_segments.append(segment)
    if not load_segments:
        raise Dex2OatProbeError("boot.oat has no loadable segments")
    section_format = "<IIQQQQIIQQ"
    if (
        section_entry_size != struct.calcsize(section_format)
        or not 1 <= section_count <= 256
        or section_names_index >= section_count
        or section_offset + section_count * section_entry_size > len(data)
    ):
        raise Dex2OatProbeError("boot.oat has invalid section-header dimensions")
    raw_sections = [
        struct.unpack_from(section_format, data, section_offset + i * section_entry_size)
        for i in range(section_count)
    ]
    names_header = raw_sections[section_names_index]
    names_offset, names_size = names_header[4:6]
    if names_offset + names_size > len(data):
        raise Dex2OatProbeError("boot.oat has an invalid section-name table")
    names = data[names_offset : names_offset + names_size]
    sections: dict[str, tuple[int, tuple[int, ...]]] = {}
    for index, section in enumerate(raw_sections):
        name_offset = section[0]
        if name_offset >= len(names):
            raise Dex2OatProbeError(f"boot.oat has an invalid section name {index}")
        name_end = names.find(b"\0", name_offset)
        if name_end < 0:
            raise Dex2OatProbeError(f"boot.oat has an unterminated section name {index}")
        name = names[name_offset:name_end].decode("ascii", errors="strict")
        if name in sections:
            raise Dex2OatProbeError(f"boot.oat repeats section {name!r}")
        sections[name] = (index, section)
    return data, load_segments, raw_sections, sections


def validate_windows_oat_unwind(path: Path) -> dict[str, object]:
    """Validate the boot-only .oat_unwind.windows transport and its anchors."""
    data, load_segments, raw_sections, sections = _read_windows_boot_oat_layout(path)

    required = (".rodata", ".text", ".oat_unwind.windows", ".dynsym", ".dynstr")
    missing = [name for name in required if name not in sections]
    if missing:
        raise Dex2OatProbeError(f"boot.oat is missing Windows unwind sections: {missing}")
    unwind_index, unwind_section = sections[".oat_unwind.windows"]
    _, rodata_section = sections[".rodata"]
    _, text_section = sections[".text"]
    unwind_type, unwind_flags = unwind_section[1:3]
    unwind_address, unwind_file_offset, unwind_section_size = unwind_section[3:6]
    unwind_alignment = unwind_section[8]
    if (
        unwind_type != 1
        or unwind_flags != 2
        or unwind_alignment != WINDOWS_X64_ELF_ALIGNMENT
        or unwind_section_size < 48
        or unwind_file_offset + unwind_section_size > len(data)
    ):
        raise Dex2OatProbeError("boot.oat has an invalid .oat_unwind.windows section")
    if ".bss" in sections and unwind_index >= sections[".bss"][0]:
        raise Dex2OatProbeError(".oat_unwind.windows does not precede .bss")
    if ".data.img.rel.ro" in sections and sections[".data.img.rel.ro"][0] >= unwind_index:
        raise Dex2OatProbeError(".oat_unwind.windows does not follow .data.img.rel.ro")
    if not any(
        segment[1] == 4
        and segment[2] <= unwind_file_offset
        and unwind_file_offset + unwind_section_size <= segment[2] + segment[5]
        and segment[3] <= unwind_address
        and unwind_address + unwind_section_size <= segment[3] + segment[6]
        for segment in load_segments
    ):
        raise Dex2OatProbeError(
            ".oat_unwind.windows is not contained by one read-only PT_LOAD"
        )

    payload = data[unwind_file_offset : unwind_file_offset + unwind_section_size]
    fields = struct.unpack_from("<4s11I", payload)
    (
        magic,
        format_version,
        serialized_header_size,
        target_machine,
        entry_size,
        entry_count,
        entries_offset,
        unwind_offset,
        unwind_size,
        code_begin,
        code_end,
        stored_checksum,
    ) = fields
    if (
        magic != b"ouw\n"
        or format_version != 1
        or serialized_header_size != 48
        or target_machine != 0x8664
        or entry_size != 12
        or entry_count < 7
        or entries_offset != 48
        or (entries_offset + entry_count * entry_size + 3) & ~3 != unwind_offset
        or unwind_offset % 4
        or unwind_offset + unwind_size != len(payload)
    ):
        raise Dex2OatProbeError("boot.oat has an invalid Windows unwind header")
    checksum_payload = bytearray(payload)
    checksum_payload[44:48] = b"\0\0\0\0"
    computed_checksum = zlib.adler32(checksum_payload) & 0xFFFFFFFF
    if stored_checksum != computed_checksum:
        raise Dex2OatProbeError(
            "boot.oat Windows unwind checksum mismatch: "
            f"stored={stored_checksum:#x}, computed={computed_checksum:#x}"
        )

    rodata_address = rodata_section[3]
    text_address, text_size = text_section[3], text_section[5]
    expected_code_begin = text_address - rodata_address
    expected_code_end = expected_code_begin + text_size
    if (code_begin, code_end) != (expected_code_begin, expected_code_end):
        raise Dex2OatProbeError("boot.oat Windows unwind code bounds do not match .text")
    section_oat_offset = unwind_address - rodata_address
    previous_end = code_begin
    unique_unwind_offsets: set[int] = set()
    for index in range(entry_count):
        entry_offset = entries_offset + index * entry_size
        begin_offset, end_offset, unwind_info_offset = struct.unpack_from(
            "<III", payload, entry_offset
        )
        if (
            begin_offset < code_begin
            or begin_offset < previous_end
            or end_offset <= begin_offset
            or end_offset > code_end
            or unwind_info_offset % 4
            or unwind_info_offset < section_oat_offset + unwind_offset
            or unwind_info_offset >= section_oat_offset + len(payload)
        ):
            raise Dex2OatProbeError(f"boot.oat has an invalid Windows unwind entry {index}")
        previous_end = end_offset
        unique_unwind_offsets.add(unwind_info_offset)

    for unwind_info_offset in unique_unwind_offsets:
        local_offset = unwind_info_offset - section_oat_offset
        if local_offset + 4 > len(payload):
            raise Dex2OatProbeError("boot.oat has truncated x64 UNWIND_INFO")
        version_and_flags, _prologue_size, slot_count, _frame = struct.unpack_from(
            "<4B", payload, local_offset
        )
        if version_and_flags != 1:
            raise Dex2OatProbeError("boot.oat has unsupported x64 UNWIND_INFO flags/version")
        descriptor_size = 4 + ((slot_count + 1) & ~1) * 2
        if local_offset + descriptor_size > len(payload):
            raise Dex2OatProbeError("boot.oat has truncated x64 unwind slots")

    _validate_dynamic_symbol(
        data,
        raw_sections,
        sections,
        "oatunwindwindows",
        unwind_index,
        unwind_address,
        unwind_section_size,
    )
    _validate_dynamic_symbol(
        data,
        raw_sections,
        sections,
        "oatunwindwindowslastword",
        unwind_index,
        unwind_address + unwind_section_size - 4,
        4,
    )
    return {
        "section": ".oat_unwind.windows",
        "format_version": format_version,
        "target_machine": target_machine,
        "entry_count": entry_count,
        "unique_unwind_info_count": len(unique_unwind_offsets),
        "checksum": f"{stored_checksum:08x}",
        "code_begin": code_begin,
        "code_end": code_end,
        "size": unwind_section_size,
    }


def validate_windows_oat_cfg(path: Path) -> dict[str, object]:
    """Validate the boot-only .oat_cfg.windows target manifest and anchors."""
    data, load_segments, raw_sections, sections = _read_windows_boot_oat_layout(path)
    required = (".rodata", ".text", ".oat_cfg.windows", ".dynsym", ".dynstr")
    missing = [name for name in required if name not in sections]
    if missing:
        raise Dex2OatProbeError(f"boot.oat is missing Windows CFG sections: {missing}")

    cfg_index, cfg_section = sections[".oat_cfg.windows"]
    _, rodata_section = sections[".rodata"]
    _, text_section = sections[".text"]
    cfg_type, cfg_flags = cfg_section[1:3]
    cfg_address, cfg_file_offset, cfg_section_size = cfg_section[3:6]
    cfg_alignment = cfg_section[8]
    if (
        cfg_type != 1
        or cfg_flags != 2
        or cfg_alignment != 4
        or cfg_section_size < 48
        or cfg_file_offset + cfg_section_size > len(data)
    ):
        raise Dex2OatProbeError("boot.oat has an invalid .oat_cfg.windows section")
    if ".bss" in sections and cfg_index >= sections[".bss"][0]:
        raise Dex2OatProbeError(".oat_cfg.windows does not precede .bss")
    if ".data.img.rel.ro" in sections and sections[".data.img.rel.ro"][0] >= cfg_index:
        raise Dex2OatProbeError(".oat_cfg.windows does not follow .data.img.rel.ro")
    if ".oat_unwind.windows" in sections and sections[".oat_unwind.windows"][0] >= cfg_index:
        raise Dex2OatProbeError(".oat_cfg.windows does not follow .oat_unwind.windows")
    if not any(
        segment[1] == 4
        and segment[2] <= cfg_file_offset
        and cfg_file_offset + cfg_section_size <= segment[2] + segment[5]
        and segment[3] <= cfg_address
        and cfg_address + cfg_section_size <= segment[3] + segment[6]
        for segment in load_segments
    ):
        raise Dex2OatProbeError(
            ".oat_cfg.windows is not contained by one read-only PT_LOAD"
        )

    payload = data[cfg_file_offset : cfg_file_offset + cfg_section_size]
    (
        magic,
        format_version,
        serialized_header_size,
        target_machine,
        table_flags,
        target_size,
        target_count,
        targets_offset,
        code_begin,
        code_end,
        stored_checksum,
        reserved,
    ) = struct.unpack_from("<4s11I", payload)
    if (
        magic != b"ocfg"
        or format_version != 1
        or serialized_header_size != 48
        or target_machine != 0x8664
        or table_flags != 1
        or target_size != 8
        or target_count == 0
        or targets_offset != 48
        or targets_offset + target_count * target_size != len(payload)
        or reserved != 0
    ):
        raise Dex2OatProbeError("boot.oat has an invalid Windows CFG header")
    checksum_payload = bytearray(payload)
    checksum_payload[40:44] = b"\0\0\0\0"
    computed_checksum = zlib.adler32(checksum_payload) & 0xFFFFFFFF
    if stored_checksum != computed_checksum:
        raise Dex2OatProbeError(
            "boot.oat Windows CFG checksum mismatch: "
            f"stored={stored_checksum:#x}, computed={computed_checksum:#x}"
        )

    rodata_address = rodata_section[3]
    text_address, text_size = text_section[3], text_section[5]
    expected_code_begin = text_address - rodata_address
    expected_code_end = expected_code_begin + text_size
    if (code_begin, code_end) != (expected_code_begin, expected_code_end):
        raise Dex2OatProbeError("boot.oat Windows CFG code bounds do not match .text")

    previous_offset: int | None = None
    role_counts = {"quick": 0, "jni": 0, "trampoline": 0, "thunk": 0}
    for index in range(target_count):
        target_offset = targets_offset + index * target_size
        code_offset, kind_flags = struct.unpack_from("<II", payload, target_offset)
        if (
            code_offset < code_begin
            or code_offset >= code_end
            or (rodata_address + code_offset) % 16
            or (previous_offset is not None and code_offset <= previous_offset)
            or kind_flags == 0
            or kind_flags & ~0xF
        ):
            raise Dex2OatProbeError(f"boot.oat has an invalid Windows CFG target {index}")
        previous_offset = code_offset
        role_counts["quick"] += bool(kind_flags & 0x1)
        role_counts["jni"] += bool(kind_flags & 0x2)
        role_counts["trampoline"] += bool(kind_flags & 0x4)
        role_counts["thunk"] += bool(kind_flags & 0x8)
    if role_counts["trampoline"] != 7:
        raise Dex2OatProbeError(
            "boot.oat Windows CFG table does not contain exactly seven trampolines"
        )

    _validate_dynamic_symbol(
        data,
        raw_sections,
        sections,
        "oatcfgwindows",
        cfg_index,
        cfg_address,
        cfg_section_size,
    )
    _validate_dynamic_symbol(
        data,
        raw_sections,
        sections,
        "oatcfgwindowslastword",
        cfg_index,
        cfg_address + cfg_section_size - 4,
        4,
    )
    return {
        "section": ".oat_cfg.windows",
        "format_version": format_version,
        "target_machine": target_machine,
        "target_count": target_count,
        "quick_candidate_count": role_counts["quick"],
        "jni_candidate_count": role_counts["jni"],
        "trampoline_candidate_count": role_counts["trampoline"],
        "thunk_candidate_count": role_counts["thunk"],
        "checksum": f"{stored_checksum:08x}",
        "code_begin": code_begin,
        "code_end": code_end,
        "size": cfg_section_size,
    }


def build_windows_oat_cfg_corruption_corpus(
    oat_path: Path, vdex_path: Path, output_root: Path
) -> dict[str, object]:
    """Create semantic CFG corruptions for both ART ElfOatFile open modes."""
    oat_path = _regular_file(oat_path)
    vdex_path = _regular_file(vdex_path)
    output_root = Path(os.path.abspath(output_root))
    if output_root.is_symlink():
        raise Dex2OatProbeError(
            f"refusing symbolic-link CFG corruption root: {output_root}"
        )
    if output_root.exists():
        if not output_root.is_dir():
            raise Dex2OatProbeError(
                f"CFG corruption root is not a directory: {output_root}"
            )
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    original = oat_path.read_bytes()
    _data, _loads, _raw_sections, sections = _read_windows_boot_oat_layout(oat_path)
    if ".oat_cfg.windows" not in sections:
        raise Dex2OatProbeError("boot.oat is missing .oat_cfg.windows")
    _, cfg_section = sections[".oat_cfg.windows"]
    cfg_offset, cfg_size = cfg_section[4], cfg_section[5]
    if cfg_size < 64 or cfg_offset + cfg_size > len(original):
        raise Dex2OatProbeError("boot.oat has an unusable CFG mutation section")
    header = struct.unpack_from("<4s11I", original, cfg_offset)
    target_count = header[6]
    targets_offset = header[7]
    code_begin = header[8]
    code_end = header[9]
    if target_count < 2 or targets_offset + target_count * 8 != cfg_size:
        raise Dex2OatProbeError("boot.oat CFG target array cannot support mutation")

    def rewrite_checksum(data: bytearray) -> None:
        struct.pack_into("<I", data, cfg_offset + 40, 0)
        checksum = zlib.adler32(data[cfg_offset : cfg_offset + cfg_size]) & 0xFFFFFFFF
        struct.pack_into("<I", data, cfg_offset + 40, checksum)

    mutations: list[tuple[str, int, int, bool]] = [
        ("magic", 0, original[cfg_offset] ^ 0x01, True),
        ("version", 4, 2, True),
        ("header-size", 8, 52, True),
        ("target-machine", 12, 0xAA64, True),
        ("table-flags", 16, 3, True),
        ("target-size", 20, 12, True),
        ("target-count", 24, 0, True),
        ("targets-offset", 28, 52, True),
        ("code-begin", 32, code_begin + 1, True),
        ("code-end", 36, code_end - 1, True),
        ("checksum", 40, header[10] ^ 0x01, False),
        ("reserved", 44, 1, True),
    ]
    cases: list[str] = []

    def link_vdex(name: str) -> None:
        destination = output_root / f"{name}.vdex"
        try:
            os.link(vdex_path, destination)
        except OSError:
            shutil.copyfile(vdex_path, destination)

    (output_root / "canonical.oat").write_bytes(original)
    link_vdex("canonical")
    for name, relative_offset, value, update_checksum in mutations:
        data = bytearray(original)
        if name == "magic":
            data[cfg_offset + relative_offset] = value
        else:
            struct.pack_into("<I", data, cfg_offset + relative_offset, value)
        if update_checksum:
            rewrite_checksum(data)
        (output_root / f"{name}.oat").write_bytes(data)
        link_vdex(name)
        cases.append(name)

    first_entry = cfg_offset + targets_offset
    second_entry = first_entry + 8
    last_entry = first_entry + (target_count - 1) * 8
    first_code_offset, first_kind = struct.unpack_from("<II", original, first_entry)
    entry_mutations = (
        ("entry-before-code", first_entry, code_begin - 1, first_kind),
        ("entry-at-code-end", last_entry, code_end, 4),
        ("entry-misaligned", first_entry, first_code_offset + 1, first_kind),
        ("entry-duplicate", second_entry, first_code_offset, 1),
        ("entry-zero-kind", first_entry, first_code_offset, 0),
        ("entry-unknown-kind", first_entry, first_code_offset, 0x10),
    )
    for name, offset, code_offset, kind_flags in entry_mutations:
        data = bytearray(original)
        struct.pack_into("<II", data, offset, code_offset, kind_flags)
        rewrite_checksum(data)
        (output_root / f"{name}.oat").write_bytes(data)
        link_vdex(name)
        cases.append(name)

    (output_root / "cases.txt").write_text("\n".join(cases) + "\n", encoding="ascii")
    return {
        "case_count": len(cases),
        "cases": cases,
        "canonical_open_count": 2,
        "rejection_open_count": len(cases) * 2,
        "total_open_count": (len(cases) + 1) * 2,
    }


def _validate_dynamic_symbol(
    data: bytes,
    raw_sections: list[tuple[int, ...]],
    sections: dict[str, tuple[int, tuple[int, ...]]],
    name: str,
    expected_section_index: int,
    expected_value: int,
    expected_size: int,
) -> None:
    _, dynsym = sections[".dynsym"]
    dynsym_offset, dynsym_size, dynstr_index, dynsym_entry_size = (
        dynsym[4],
        dynsym[5],
        dynsym[6],
        dynsym[9],
    )
    if dynstr_index >= len(raw_sections) or dynsym_entry_size != 24:
        raise Dex2OatProbeError("boot.oat has invalid dynamic-symbol metadata")
    dynstr = raw_sections[dynstr_index]
    dynstr_offset, dynstr_size = dynstr[4:6]
    if dynsym_offset + dynsym_size > len(data) or dynstr_offset + dynstr_size > len(data):
        raise Dex2OatProbeError("boot.oat has out-of-range dynamic-symbol metadata")
    if dynsym_size % dynsym_entry_size:
        raise Dex2OatProbeError("boot.oat has a partial dynamic-symbol entry")
    strings = data[dynstr_offset : dynstr_offset + dynstr_size]
    symbol_format = "<IBBHQQ"
    for offset in range(dynsym_offset, dynsym_offset + dynsym_size, dynsym_entry_size):
        name_offset, _info, _other, section_index, value, size = struct.unpack_from(
            symbol_format, data, offset
        )
        if name_offset >= len(strings):
            raise Dex2OatProbeError("boot.oat has an invalid dynamic-symbol name")
        name_end = strings.find(b"\0", name_offset)
        if name_end < 0:
            raise Dex2OatProbeError("boot.oat has an unterminated dynamic-symbol name")
        if strings[name_offset:name_end].decode("ascii", errors="strict") == name:
            if (section_index, value, size) != (
                expected_section_index,
                expected_value,
                expected_size,
            ):
                raise Dex2OatProbeError(f"boot.oat has an invalid {name} anchor")
            return
    raise Dex2OatProbeError(f"boot.oat is missing dynamic anchor {name}")


def _read_elf_sections(
    data: bytes,
    *,
    section_offset: int,
    section_entry_size: int,
    section_count: int,
    section_names_index: int,
) -> dict[str, tuple[int, int]]:
    section_format = "<IIQQQQIIQQ"
    expected_size = struct.calcsize(section_format)
    if section_entry_size != expected_size or not 1 <= section_count <= 256:
        raise Dex2OatProbeError("probe.oat has invalid section-header dimensions")
    if section_names_index >= section_count:
        raise Dex2OatProbeError("probe.oat has an invalid section-name table index")
    if section_offset + section_count * section_entry_size > len(data):
        raise Dex2OatProbeError("probe.oat has truncated section headers")
    raw_sections = [
        struct.unpack_from(section_format, data, section_offset + i * section_entry_size)
        for i in range(section_count)
    ]
    names_header = raw_sections[section_names_index]
    names_offset, names_size = names_header[4:6]
    if names_offset + names_size > len(data):
        raise Dex2OatProbeError("probe.oat has an out-of-range section-name table")
    names = data[names_offset : names_offset + names_size]
    result: dict[str, tuple[int, int]] = {}
    for index, section in enumerate(raw_sections):
        name_offset = section[0]
        section_type = section[1]
        file_offset, size = section[4:6]
        # SHT_NOBITS sections such as ART's .bss and .dex describe virtual
        # storage and deliberately have no corresponding file bytes.
        file_range_invalid = section_type != 8 and file_offset + size > len(data)
        if name_offset >= len(names) or file_range_invalid:
            raise Dex2OatProbeError(f"probe.oat has an invalid section header {index}")
        end = names.find(b"\0", name_offset)
        if end < 0:
            raise Dex2OatProbeError(f"probe.oat has an unterminated section name {index}")
        name = names[name_offset:end].decode("ascii", errors="strict")
        if name in result:
            raise Dex2OatProbeError(f"probe.oat repeats section {name!r}")
        result[name] = (file_offset, size)
    return result


def validate_vdex(path: Path) -> dict[str, object]:
    data = _regular_file(path).read_bytes()
    file_header_format = "<4s4sI"
    file_header_size = struct.calcsize(file_header_format)
    if len(data) < file_header_size:
        raise Dex2OatProbeError("probe.vdex has a truncated file header")
    magic, version, section_count = struct.unpack_from(file_header_format, data)
    if magic != b"vdex":
        raise Dex2OatProbeError("probe.vdex does not start with the VDEX magic")
    if version != VDEX_VERSION:
        raise Dex2OatProbeError(
            f"probe.vdex version is {version!r}, expected {VDEX_VERSION!r}"
        )
    if section_count != 4:
        raise Dex2OatProbeError(
            f"probe.vdex has {section_count} sections, expected 4"
        )

    section_format = "<III"
    section_header_size = struct.calcsize(section_format)
    payload_start = file_header_size + section_count * section_header_size
    if payload_start > len(data):
        raise Dex2OatProbeError("probe.vdex has truncated section headers")
    sections = []
    for index in range(section_count):
        kind, offset, size = struct.unpack_from(
            section_format, data, file_header_size + index * section_header_size
        )
        if kind != index:
            raise Dex2OatProbeError(
                f"probe.vdex section {index} has unexpected kind {kind}"
            )
        if offset < payload_start or offset + size > len(data):
            raise Dex2OatProbeError(
                f"probe.vdex section {index} has an invalid file range"
            )
        sections.append((offset, size))
    computed_size = max(payload_start, *(offset + size for offset, size in sections))
    if computed_size != len(data):
        raise Dex2OatProbeError(
            f"probe.vdex size is {len(data)}, section layout describes {computed_size}"
        )

    checksum_offset, checksum_size = sections[0]
    if checksum_offset != payload_start or checksum_size != 4:
        raise Dex2OatProbeError(
            "probe.vdex does not describe exactly one input DEX checksum"
        )
    dex_offset, dex_size = sections[1]
    if dex_size < 8 or data[dex_offset : dex_offset + 4] != b"dex\n":
        raise Dex2OatProbeError("probe.vdex does not contain the expected DEX section")
    return {
        "version": version.rstrip(b"\0").decode("ascii"),
        "section_count": section_count,
        "dex_file_count": checksum_size // 4,
    }


def _prepare_output_root(path: Path) -> Path:
    path = _managed_path(path, allow_missing=True)
    if path == Path(path.anchor) or path == path.parent:
        raise Dex2OatProbeError(f"unsafe output root: {path}")
    parent = _managed_path(path.parent, allow_missing=True)
    parent.mkdir(parents=True, exist_ok=True)
    parent = _managed_path(parent)
    if not parent.is_dir():
        raise Dex2OatProbeError(f"output parent is not a directory: {parent}")
    if path.exists() or path.is_symlink():
        _directory(path)
        _reject_tree_links(path)
        shutil.rmtree(path)
    path.mkdir()
    return _directory(path)


def _managed_path(path: Path, *, allow_missing: bool = False) -> Path:
    path = Path(os.path.abspath(path))
    missing_seen = False
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            missing_seen = True
            continue
        if missing_seen:
            raise Dex2OatProbeError(f"existing path below a missing component: {current}")
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & reparse:
            raise Dex2OatProbeError(f"link/reparse path is forbidden: {current}")
    if not allow_missing and not path.exists():
        raise Dex2OatProbeError(f"path does not exist: {path}")
    return path


def _regular_file(path: Path) -> Path:
    path = _managed_path(path)
    if not path.is_file():
        raise Dex2OatProbeError(f"required regular file is missing: {path}")
    return path


def _directory(path: Path) -> Path:
    path = _managed_path(path)
    if not path.is_dir():
        raise Dex2OatProbeError(f"required directory is missing: {path}")
    return path


def _reject_tree_links(root: Path) -> None:
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in [*directories, *files]:
            _managed_path(current_path / name)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
