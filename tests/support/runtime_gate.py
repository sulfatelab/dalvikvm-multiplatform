#!/usr/bin/env python3
"""Shell-free native ART runtime and ELF DSO acceptance gates."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import sys


class GateError(RuntimeError):
    """A runtime artifact did not satisfy its declared acceptance contract."""


def _regular_file(value: str) -> Path:
    path = _managed_path(Path(value))
    if not path.is_file():
        raise GateError(f"required regular file is missing: {path}")
    return path


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
            raise GateError(f"existing path below a missing component: {current}")
        attributes = getattr(info, "st_file_attributes", 0)
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if stat.S_ISLNK(info.st_mode) or attributes & reparse:
            raise GateError(f"link/reparse path is forbidden: {current}")
    if not allow_missing and not path.exists():
        raise GateError(f"managed path does not exist: {path}")
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


def run_managed(
    *,
    target_id: str,
    dalvikvm: Path,
    boot_jar: Path,
    app_jar: Path,
    main_class: str,
    work_root: Path,
    icu_data: Path,
    library_dirs: list[Path],
    vm_options: list[str],
    main_args: list[str],
    expected: list[str],
    forbidden: list[str],
    expected_exit: int,
    timeout: int,
) -> None:
    dalvikvm = _regular_file(str(dalvikvm))
    boot_jar = _regular_file(str(boot_jar))
    app_jar = _regular_file(str(app_jar))
    icu_data = _regular_file(str(icu_data))
    library_dirs = [_managed_path(path) for path in library_dirs]
    work_root = _managed_path(work_root, allow_missing=True)
    work_root.mkdir(parents=True, exist_ok=True)
    _managed_path(work_root)
    runtime_root = work_root / "runtime"
    if runtime_root.exists() or runtime_root.is_symlink():
        _reject_tree_links(runtime_root)
        shutil.rmtree(runtime_root)
    (runtime_root / "data").mkdir(parents=True)
    (runtime_root / "icu").mkdir()
    (runtime_root / "tmp").mkdir()
    staged_icu = runtime_root / "icu" / icu_data.name
    shutil.copyfile(icu_data, staged_icu)

    command = [
        str(dalvikvm),
        f"-Xbootclasspath:{boot_jar}",
        f"-Xbootclasspath-locations:{boot_jar}",
        f"-Ximage:{runtime_root / 'nonexistent-boot-image'}",
        "-XjdwpProvider:none",
        "-Xms64m",
        "-Xmx512m",
        *vm_options,
        "-cp",
        str(app_jar),
        main_class,
        *main_args,
    ]
    environment = os.environ.copy()
    environment.update({
        "ANDROID_ROOT": str(runtime_root),
        "ANDROID_ART_ROOT": str(runtime_root),
        "ANDROID_I18N_ROOT": str(runtime_root),
        "ANDROID_DATA": str(runtime_root / "data"),
        "ICU_DATA": str(runtime_root / "icu"),
        "TMP": str(runtime_root / "tmp"),
        "TEMP": str(runtime_root / "tmp"),
        "TMPDIR": str(runtime_root / "tmp"),
    })
    if os.name == "nt":
        system_root = environment.get("SystemRoot", r"C:\Windows")
        environment["PATH"] = os.pathsep.join(
            [*(str(path) for path in library_dirs), str(Path(system_root) / "System32")]
        )
    else:
        environment["LD_LIBRARY_PATH"] = os.pathsep.join(
            str(path) for path in library_dirs
        )
    try:
        result = subprocess.run(
            command,
            cwd=work_root,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            shell=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise GateError(f"{main_class} timed out after {timeout} seconds") from exc
    (work_root / "stdout.txt").write_text(result.stdout, encoding="utf-8")
    (work_root / "stderr.txt").write_text(result.stderr, encoding="utf-8")
    combined = result.stdout + "\n" + result.stderr
    missing = [marker for marker in expected if marker not in combined]
    present_forbidden = [marker for marker in forbidden if marker in combined]
    record = {
        "schema_version": 1,
        "target_id": target_id,
        "main_class": main_class,
        "expected_exit": expected_exit,
        "actual_exit": result.returncode,
        "missing_markers": missing,
        "forbidden_markers": present_forbidden,
        "boot_jar": {"name": boot_jar.name, "sha256": _sha256(boot_jar)},
        "app_jar": {"name": app_jar.name, "sha256": _sha256(app_jar)},
    }
    (work_root / "result.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if result.returncode != expected_exit or missing or present_forbidden:
        tail = "\n".join(combined.splitlines()[-80:])
        raise GateError(
            f"{main_class} failed: exit={result.returncode}, expected={expected_exit}, "
            f"missing={missing}, forbidden={present_forbidden}\n{tail}"
        )
    print(
        f"{main_class} passed for {target_id}: exit={result.returncode}, "
        f"markers={len(expected)}"
    )


def _reject_tree_links(root: Path) -> None:
    _managed_path(root)
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        for name in (*directories, *files):
            _managed_path(Path(current) / name)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    managed = subparsers.add_parser("managed")
    managed.add_argument("--target-id", required=True)
    managed.add_argument("--dalvikvm", type=_regular_file, required=True)
    managed.add_argument("--boot-jar", type=_regular_file, required=True)
    managed.add_argument("--app-jar", type=_regular_file, required=True)
    managed.add_argument("--main-class", required=True)
    managed.add_argument("--work-root", type=Path, required=True)
    managed.add_argument("--icu-data", type=_regular_file, required=True)
    managed.add_argument("--library-dir", type=Path, action="append", default=[])
    managed.add_argument("--vm-option", action="append", default=[])
    managed.add_argument("--main-arg", action="append", default=[])
    managed.add_argument("--expect", action="append", default=[])
    managed.add_argument("--forbid", action="append", default=[])
    managed.add_argument("--expected-exit", type=int, default=0)
    managed.add_argument("--timeout", type=int, default=180)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "show-version":
            run_show_version(args.dalvikvm, args.expect)
        elif args.command == "dso-topology":
            run_dso_topology(
                args.runtime,
                args.compiler,
                args.compiler_needed,
                args.runtime_forbidden,
            )
        else:
            run_managed(
                target_id=args.target_id,
                dalvikvm=args.dalvikvm,
                boot_jar=args.boot_jar,
                app_jar=args.app_jar,
                main_class=args.main_class,
                work_root=args.work_root,
                icu_data=args.icu_data,
                library_dirs=args.library_dir,
                vm_options=args.vm_option,
                main_args=args.main_arg,
                expected=args.expect,
                forbidden=args.forbid,
                expected_exit=args.expected_exit,
                timeout=args.timeout,
            )
        return 0
    except (GateError, OSError, UnicodeError) as exc:
        print(f"runtime_gate.py: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
