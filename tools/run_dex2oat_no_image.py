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


LOGICAL_BOOT_JAR = "/system/framework/boot.jar"
LOGICAL_INPUT_JAR = "/data/local/tmp/win32-oat-probe.jar"
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
        f"--oat-file={oat}",
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
        "--force-determinism",
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
