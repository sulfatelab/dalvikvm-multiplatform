#!/usr/bin/env python3
"""Shell-free native ART runtime and ELF DSO acceptance gates."""

from __future__ import annotations

import argparse
import ctypes
import os
from pathlib import Path
import struct
import subprocess
import sys


class GateError(RuntimeError):
    """A runtime artifact did not satisfy its declared acceptance contract."""


def _regular_file(value: str) -> Path:
    path = Path(value)
    if path.is_symlink() or not path.is_file():
        raise GateError(f"required regular file is missing: {path}")
    return path


def _elf_needed(path: Path) -> list[str]:
    """Read DT_NEEDED entries without relying on readelf or a POSIX tool layer."""
    data = path.read_bytes()
    if len(data) < 16 or data[:4] != b"\x7fELF":
        raise GateError(f"not an ELF artifact: {path}")

    elf_class = data[4]
    byte_order = data[5]
    if elf_class not in (1, 2) or byte_order not in (1, 2):
        raise GateError(f"unsupported ELF class or byte order: {path}")
    endian = "<" if byte_order == 1 else ">"
    if elf_class == 1:
        header_format = endian + "HHIIIIIHHHHHH"
        program_format = endian + "IIIIIIII"
        dynamic_format = endian + "iI"
    else:
        header_format = endian + "HHIQQQIHHHHHH"
        program_format = endian + "IIQQQQQQ"
        dynamic_format = endian + "qQ"

    header_size = struct.calcsize(header_format)
    if len(data) < 16 + header_size:
        raise GateError(f"truncated ELF header: {path}")
    header = struct.unpack_from(header_format, data, 16)
    program_offset = header[4]
    program_entry_size = header[8]
    program_count = header[9]
    expected_program_size = struct.calcsize(program_format)
    if program_entry_size < expected_program_size:
        raise GateError(f"invalid ELF program-header size: {path}")

    load_segments: list[tuple[int, int, int]] = []
    dynamic_segment: tuple[int, int] | None = None
    for index in range(program_count):
        offset = program_offset + index * program_entry_size
        if offset + expected_program_size > len(data):
            raise GateError(f"truncated ELF program headers: {path}")
        values = struct.unpack_from(program_format, data, offset)
        if elf_class == 1:
            segment_type, file_offset, virtual_address = values[:3]
            file_size = values[4]
        else:
            segment_type = values[0]
            file_offset, virtual_address = values[2:4]
            file_size = values[5]
        if segment_type == 1:  # PT_LOAD
            load_segments.append((virtual_address, file_offset, file_size))
        elif segment_type == 2:  # PT_DYNAMIC
            dynamic_segment = (file_offset, file_size)

    if dynamic_segment is None:
        raise GateError(f"ELF artifact has no PT_DYNAMIC segment: {path}")

    dynamic_entry_size = struct.calcsize(dynamic_format)
    dynamic_offset, dynamic_size = dynamic_segment
    needed_offsets: list[int] = []
    string_address: int | None = None
    string_size: int | None = None
    for offset in range(
        dynamic_offset, dynamic_offset + dynamic_size, dynamic_entry_size
    ):
        if offset + dynamic_entry_size > len(data):
            raise GateError(f"truncated ELF dynamic segment: {path}")
        tag, value = struct.unpack_from(dynamic_format, data, offset)
        if tag == 0:  # DT_NULL
            break
        if tag == 1:  # DT_NEEDED
            needed_offsets.append(value)
        elif tag == 5:  # DT_STRTAB
            string_address = value
        elif tag == 10:  # DT_STRSZ
            string_size = value
    if string_address is None or string_size is None:
        raise GateError(f"ELF dynamic string table is missing: {path}")

    string_offset: int | None = None
    for virtual_address, file_offset, file_size in load_segments:
        if virtual_address <= string_address < virtual_address + file_size:
            string_offset = file_offset + string_address - virtual_address
            break
    if string_offset is None or string_offset + string_size > len(data):
        raise GateError(f"ELF dynamic string table is out of range: {path}")

    needed: list[str] = []
    for relative_offset in needed_offsets:
        if relative_offset >= string_size:
            raise GateError(f"ELF DT_NEEDED string is out of range: {path}")
        start = string_offset + relative_offset
        end = data.find(b"\0", start, string_offset + string_size)
        if end < 0:
            raise GateError(f"unterminated ELF DT_NEEDED string: {path}")
        needed.append(data[start:end].decode("utf-8", errors="strict"))
    return needed


def run_show_version(dalvikvm: Path, expected: str) -> None:
    result = subprocess.run(
        [str(dalvikvm), "-showversion"],
        cwd=dalvikvm.parent,
        shell=False,
        check=False,
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    if result.returncode != 0:
        raise GateError(f"dalvikvm -showversion exited {result.returncode}: {output}")
    if expected not in output:
        raise GateError(f"dalvikvm output is missing {expected!r}: {output}")
    print(expected)


def run_dso_topology(
    runtime: Path,
    compiler: Path,
    compiler_needed: str,
    runtime_forbidden: str,
) -> None:
    runtime_needed = _elf_needed(runtime)
    compiler_dependencies = _elf_needed(compiler)
    if compiler_needed not in compiler_dependencies:
        raise GateError(
            f"{compiler.name} does not depend on required {compiler_needed}: "
            f"{compiler_dependencies}"
        )
    if runtime_forbidden in runtime_needed:
        raise GateError(
            f"{runtime.name} has forbidden reverse dependency {runtime_forbidden}"
        )

    mode = getattr(os, "RTLD_NOW", 0) | getattr(os, "RTLD_LOCAL", 0)
    ctypes.CDLL(str(runtime), mode=mode)
    ctypes.CDLL(str(compiler), mode=mode)
    print(f"loaded {runtime.name} and {compiler.name}")
    print(f"{compiler.name} -> {compiler_needed}; no reverse dependency")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    show = subparsers.add_parser("show-version")
    show.add_argument("--dalvikvm", type=_regular_file, required=True)
    show.add_argument("--expect", required=True)
    topology = subparsers.add_parser("dso-topology")
    topology.add_argument("--runtime", type=_regular_file, required=True)
    topology.add_argument("--compiler", type=_regular_file, required=True)
    topology.add_argument("--compiler-needed", required=True)
    topology.add_argument("--runtime-forbidden", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "show-version":
            run_show_version(args.dalvikvm, args.expect)
        else:
            run_dso_topology(
                args.runtime,
                args.compiler,
                args.compiler_needed,
                args.runtime_forbidden,
            )
        return 0
    except (GateError, OSError, UnicodeError) as exc:
        print(f"runtime_gate.py: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
