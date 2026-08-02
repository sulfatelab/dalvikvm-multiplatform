#!/usr/bin/env python3
"""Shell-free native ART runtime and ELF DSO acceptance gates."""

from __future__ import annotations

import argparse
import ctypes
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


def run_native(
    *,
    target_id: str,
    probe: Path,
    work_root: Path,
    library_dirs: list[Path],
    probe_args: list[str],
    expected: list[str],
    forbidden: list[str],
    expected_exit: int,
    repetitions: int,
    timeout: int,
) -> None:
    probe = _regular_file(str(probe))
    library_dirs = [_managed_path(path) for path in library_dirs]
    work_root = _managed_path(work_root, allow_missing=True)
    if work_root.exists() or work_root.is_symlink():
        _reject_tree_links(work_root)
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True)
    _managed_path(work_root)

    environment = os.environ.copy()
    if os.name == "nt":
        system_root = environment.get("SystemRoot", r"C:\Windows")
        environment["PATH"] = os.pathsep.join(
            [*(str(path) for path in library_dirs), str(Path(system_root) / "System32")]
        )
    elif library_dirs:
        environment["LD_LIBRARY_PATH"] = os.pathsep.join(
            str(path) for path in library_dirs
        )

    cases: list[dict[str, object]] = []
    failure: str | None = None
    for iteration in range(1, repetitions + 1):
        try:
            result = subprocess.run(
                [str(probe), *probe_args],
                cwd=probe.parent,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
                shell=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            cases.append({
                "iteration": iteration,
                "actual_exit": None,
                "timed_out": True,
                "missing_markers": list(expected),
                "forbidden_markers": [],
            })
            failure = f"iteration {iteration} timed out after {timeout} seconds"
            break

        (work_root / f"stdout-{iteration:03d}.txt").write_text(
            result.stdout, encoding="utf-8"
        )
        (work_root / f"stderr-{iteration:03d}.txt").write_text(
            result.stderr, encoding="utf-8"
        )
        combined = result.stdout + "\n" + result.stderr
        missing = [marker for marker in expected if marker not in combined]
        present_forbidden = [marker for marker in forbidden if marker in combined]
        cases.append({
            "iteration": iteration,
            "actual_exit": result.returncode,
            "timed_out": False,
            "missing_markers": missing,
            "forbidden_markers": present_forbidden,
        })
        if result.returncode != expected_exit or missing or present_forbidden:
            tail = "\n".join(combined.splitlines()[-80:])
            failure = (
                f"iteration {iteration} failed: exit={result.returncode}, "
                f"expected={expected_exit}, missing={missing}, "
                f"forbidden={present_forbidden}\n{tail}"
            )
            break

    record = {
        "schema_version": 1,
        "target_id": target_id,
        "probe": {"name": probe.name, "sha256": _sha256(probe)},
        "argument_count": len(probe_args),
        "expected_exit": expected_exit,
        "expected_markers": expected,
        "forbidden_markers": forbidden,
        "requested_repetitions": repetitions,
        "attempted_repetitions": len(cases),
        "completed_repetitions": sum(
            case["actual_exit"] == expected_exit
            and not case["timed_out"]
            and not case["missing_markers"]
            and not case["forbidden_markers"]
            for case in cases
        ),
        "cases": cases,
    }
    temporary = work_root / "result.json.tmp"
    temporary.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, work_root / "result.json")
    if failure is not None:
        raise GateError(f"{probe.name} {failure}")
    print(
        f"{probe.name} passed for {target_id}: repetitions={repetitions}, "
        f"markers={len(expected)}"
    )


def _load_native_matrix(path: Path) -> tuple[Path, list[dict[str, object]]]:
    path = _regular_file(str(path))
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GateError(f"invalid native matrix JSON {path.name}: {exc}") from exc
    if not isinstance(document, dict) or set(document) != {"schema_version", "cases"}:
        raise GateError(
            "native matrix must contain exactly schema_version and cases"
        )
    if document["schema_version"] != 1:
        raise GateError(
            f"unsupported native matrix schema: {document['schema_version']!r}"
        )
    raw_cases = document["cases"]
    if not isinstance(raw_cases, list) or not raw_cases:
        raise GateError("native matrix cases must be a non-empty list")

    allowed = {
        "name",
        "arguments",
        "expected_exit",
        "expected_markers",
        "forbidden_markers",
        "repetitions",
        "timeout_seconds",
    }
    cases: list[dict[str, object]] = []
    names: set[str] = set()
    for index, raw_case in enumerate(raw_cases, start=1):
        if not isinstance(raw_case, dict) or not set(raw_case) <= allowed:
            raise GateError(f"native matrix case {index} has unknown fields")
        name = raw_case.get("name")
        if not isinstance(name, str) or re.fullmatch(r"[a-z0-9][a-z0-9._-]*", name) is None:
            raise GateError(f"native matrix case {index} has an invalid name")
        if name in names:
            raise GateError(f"native matrix case name is duplicated: {name}")
        names.add(name)

        arguments = raw_case.get("arguments", [])
        expected = raw_case.get("expected_markers", [])
        forbidden = raw_case.get("forbidden_markers", [])
        if not isinstance(arguments, list) or not all(
            isinstance(value, str) for value in arguments
        ):
            raise GateError(f"native matrix case {name} arguments must be strings")
        if not isinstance(expected, list) or not expected or not all(
            isinstance(value, str) and value for value in expected
        ):
            raise GateError(
                f"native matrix case {name} expected_markers must be non-empty strings"
            )
        if not isinstance(forbidden, list) or not all(
            isinstance(value, str) and value for value in forbidden
        ):
            raise GateError(
                f"native matrix case {name} forbidden_markers must be strings"
            )
        expected_exit = raw_case.get("expected_exit", 0)
        repetitions = raw_case.get("repetitions", 1)
        timeout = raw_case.get("timeout_seconds", 60)
        for field, value, positive in (
            ("expected_exit", expected_exit, False),
            ("repetitions", repetitions, True),
            ("timeout_seconds", timeout, True),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or (
                positive and value < 1
            ):
                qualifier = "a positive integer" if positive else "an integer"
                raise GateError(
                    f"native matrix case {name} {field} must be {qualifier}"
                )
        cases.append({
            "name": name,
            "arguments": arguments,
            "expected_exit": expected_exit,
            "expected_markers": expected,
            "forbidden_markers": forbidden,
            "repetitions": repetitions,
            "timeout_seconds": timeout,
        })
    return path, cases


def run_native_matrix(
    *,
    target_id: str,
    probe: Path,
    work_root: Path,
    library_dirs: list[Path],
    matrix: Path,
) -> None:
    probe = _regular_file(str(probe))
    matrix, cases = _load_native_matrix(matrix)
    work_root = _managed_path(work_root, allow_missing=True)
    if work_root.exists() or work_root.is_symlink():
        _reject_tree_links(work_root)
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True)

    records: list[dict[str, object]] = []
    failure: GateError | None = None
    for case in cases:
        name = str(case["name"])
        try:
            run_native(
                target_id=target_id,
                probe=probe,
                work_root=work_root / name,
                library_dirs=library_dirs,
                probe_args=list(case["arguments"]),
                expected=list(case["expected_markers"]),
                forbidden=list(case["forbidden_markers"]),
                expected_exit=int(case["expected_exit"]),
                repetitions=int(case["repetitions"]),
                timeout=int(case["timeout_seconds"]),
            )
        except GateError as exc:
            failure = exc
        result_path = work_root / name / "result.json"
        if not result_path.is_file():
            raise GateError(f"native matrix case {name} produced no result record")
        records.append({
            "name": name,
            "arguments": case["arguments"],
            "result": json.loads(result_path.read_text(encoding="utf-8")),
        })
        if failure is not None:
            break

    record = {
        "schema_version": 1,
        "target_id": target_id,
        "probe": {"name": probe.name, "sha256": _sha256(probe)},
        "matrix": {"name": matrix.name, "sha256": _sha256(matrix)},
        "requested_cases": len(cases),
        "attempted_cases": len(records),
        "completed_cases": sum(
            case["result"]["completed_repetitions"]
            == case["result"]["requested_repetitions"]
            for case in records
        ),
        "cases": records,
    }
    temporary = work_root / "result.json.tmp"
    temporary.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, work_root / "result.json")
    if failure is not None:
        raise failure
    repetitions = sum(int(case["repetitions"]) for case in cases)
    print(
        f"{probe.name} matrix passed for {target_id}: "
        f"cases={len(cases)}, repetitions={repetitions}"
    )


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
    environment_overrides: dict[str, str] | None = None,
    require_nonzero: bool = False,
    cacerts_dir: Path | None = None,
    security_properties: Path | None = None,
    boot_image_dir: Path | None = None,
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
    runtime_assets: dict[str, object] = {}
    if (cacerts_dir is None) != (security_properties is None):
        raise GateError(
            "managed security packaging requires both cacerts and security properties"
        )
    if cacerts_dir is not None and security_properties is not None:
        security_properties = _regular_file(str(security_properties))
        staged_properties = runtime_root / "etc" / "security" / "security.properties"
        staged_properties.parent.mkdir(parents=True)
        shutil.copyfile(security_properties, staged_properties)
        copied_cacerts = _copy_regular_tree(
            cacerts_dir, runtime_root / "etc" / "security" / "cacerts"
        )
        certificates = [
            path
            for path in copied_cacerts
            if re.fullmatch(r"[0-9a-f]{8}\.[0-9]+", path.name)
        ]
        if not certificates:
            raise GateError("managed security packaging has zero CA certificates")
        (runtime_root / "data" / "misc" / "keychain" / "cacerts-added").mkdir(
            parents=True
        )
        (runtime_root / "data" / "misc" / "keychain" / "cacerts-removed").mkdir()
        runtime_assets = {
            "security_properties": {
                "name": staged_properties.name,
                "sha256": _sha256(staged_properties),
            },
            "cacerts": {
                "count": len(certificates),
                "tree_sha256": _tree_sha256(copied_cacerts),
            },
            "keystore_type": "AndroidCAStore",
        }

    if boot_image_dir is None:
        boot_image_option = runtime_root / "nonexistent-boot-image"
        boot_classpath_location = str(boot_jar)
        boot_image_record: dict[str, object] = {"status": "imageless"}
    else:
        boot_image_record = _stage_boot_image(
            boot_image_dir,
            runtime_root / "boot-image",
            target_id=target_id,
            boot_jar=boot_jar,
        )
        boot_image_option = runtime_root / "boot-image" / "boot.art"
        boot_classpath_location = "/system/framework/boot.jar"

    command = [
        str(dalvikvm),
        f"-Xbootclasspath:{boot_jar}",
        f"-Xbootclasspath-locations:{boot_classpath_location}",
        f"-Ximage:{boot_image_option}",
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
    for name, value in (environment_overrides or {}).items():
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None:
            raise GateError(f"invalid managed environment variable name: {name!r}")
        if not isinstance(value, str) or "\0" in value:
            raise GateError(f"invalid managed environment value for {name}")
        environment[name] = value
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
    exit_ok = result.returncode != 0 if require_nonzero else result.returncode == expected_exit
    record = {
        "schema_version": 1,
        "target_id": target_id,
        "main_class": main_class,
        "exit_contract": "nonzero" if require_nonzero else "exact",
        "expected_exit": None if require_nonzero else expected_exit,
        "actual_exit": result.returncode,
        "missing_markers": missing,
        "forbidden_markers": present_forbidden,
        "boot_jar": {"name": boot_jar.name, "sha256": _sha256(boot_jar)},
        "app_jar": {"name": app_jar.name, "sha256": _sha256(app_jar)},
        "boot_image": boot_image_record,
        "runtime_assets": runtime_assets,
    }
    (work_root / "result.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if not exit_ok or missing or present_forbidden:
        tail = "\n".join(combined.splitlines()[-80:])
        expected_description = "nonzero" if require_nonzero else str(expected_exit)
        raise GateError(
            f"{main_class} failed: exit={result.returncode}, "
            f"expected={expected_description}, "
            f"missing={missing}, forbidden={present_forbidden}\n{tail}"
        )
    print(
        f"{main_class} passed for {target_id}: exit={result.returncode}, "
        f"markers={len(expected)}"
    )


def _stage_boot_image(
    source_root: Path,
    destination_root: Path,
    *,
    target_id: str,
    boot_jar: Path,
) -> dict[str, object]:
    source_root = _managed_path(source_root)
    if not source_root.is_dir():
        raise GateError(f"boot image root is not a directory: {source_root}")
    manifest_path = _regular_file(str(source_root / "manifest.json"))
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise GateError(f"invalid boot image manifest: {exc}") from exc
    if (
        manifest.get("schema_version") != 1
        or manifest.get("target_id") != target_id
        or manifest.get("boot_jar_sha256") != _sha256(boot_jar)
        or manifest.get("logical_boot_jar") != "/system/framework/boot.jar"
    ):
        raise GateError("boot image manifest does not match the runtime inputs")
    instruction_set = manifest.get("instruction_set")
    artifacts = manifest.get("artifacts")
    if not isinstance(instruction_set, str) or not isinstance(artifacts, list):
        raise GateError("boot image manifest omits instruction set or artifacts")
    expected = {
        f"{instruction_set}/boot.art",
        f"{instruction_set}/boot.oat",
        f"{instruction_set}/boot.vdex",
    }
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw in artifacts:
        if not isinstance(raw, dict) or not isinstance(raw.get("path"), str):
            raise GateError("boot image artifact record is malformed")
        relative = raw["path"].replace("\\", "/")
        if relative not in expected or relative in seen:
            raise GateError(f"unexpected boot image artifact: {relative}")
        source = _regular_file(str(source_root / Path(relative)))
        digest = _sha256(source)
        if raw.get("sha256") != digest or raw.get("size") != source.stat().st_size:
            raise GateError(f"boot image artifact identity changed: {relative}")
        destination = destination_root / Path(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        _managed_path(destination.parent)
        shutil.copyfile(source, destination)
        records.append({"path": relative, "sha256": digest})
        seen.add(relative)
    if seen != expected:
        raise GateError(
            f"boot image artifact set is incomplete: {sorted(expected - seen)}"
        )
    destination_root.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(manifest_path, destination_root / "manifest.json")
    return {
        "status": "verified",
        "instruction_set": instruction_set,
        "artifacts": sorted(records, key=lambda value: str(value["path"])),
    }


def _copy_regular_tree(source_root: Path, destination_root: Path) -> list[Path]:
    source_root = _managed_path(source_root)
    if not source_root.is_dir():
        raise GateError(f"runtime asset tree is not a directory: {source_root}")
    destination_root = _managed_path(destination_root, allow_missing=True)
    destination_root.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for current, directories, files in os.walk(
        source_root, topdown=True, followlinks=False
    ):
        current_path = Path(current)
        for name in sorted(directories):
            _managed_path(current_path / name)
        directories.sort()
        for name in sorted(files):
            source = _regular_file(str(current_path / name))
            relative = source.relative_to(source_root)
            destination = destination_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            copied.append(_regular_file(str(destination)))
    return copied


def _tree_sha256(files: list[Path]) -> str:
    digest = hashlib.sha256()
    common = Path(os.path.commonpath([str(path.parent) for path in files]))
    for path in sorted(files, key=lambda item: item.as_posix()):
        digest.update(path.relative_to(common).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(_sha256(path)))
    return digest.hexdigest()


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
    native = subparsers.add_parser("native")
    native.add_argument("--target-id", required=True)
    native.add_argument("--probe", type=_regular_file, required=True)
    native.add_argument("--work-root", type=Path, required=True)
    native.add_argument("--library-dir", type=Path, action="append", default=[])
    native.add_argument("--probe-arg", action="append", default=[])
    native.add_argument("--expect", action="append", default=[])
    native.add_argument("--forbid", action="append", default=[])
    native.add_argument("--expected-exit", type=int, default=0)
    native.add_argument("--repeat", type=int, default=1)
    native.add_argument("--timeout", type=int, default=60)
    native_matrix = subparsers.add_parser("native-matrix")
    native_matrix.add_argument("--target-id", required=True)
    native_matrix.add_argument("--probe", type=_regular_file, required=True)
    native_matrix.add_argument("--work-root", type=Path, required=True)
    native_matrix.add_argument(
        "--library-dir", type=Path, action="append", default=[]
    )
    native_matrix.add_argument("--matrix", type=_regular_file, required=True)
    managed = subparsers.add_parser("managed")
    managed.add_argument("--target-id", required=True)
    managed.add_argument("--dalvikvm", type=_regular_file, required=True)
    managed.add_argument("--boot-jar", type=_regular_file, required=True)
    managed.add_argument("--app-jar", type=_regular_file, required=True)
    managed.add_argument("--main-class", required=True)
    managed.add_argument("--work-root", type=Path, required=True)
    managed.add_argument("--icu-data", type=_regular_file, required=True)
    managed.add_argument("--cacerts-dir", type=Path)
    managed.add_argument("--security-properties", type=_regular_file)
    managed.add_argument("--boot-image-dir", type=Path)
    managed.add_argument("--library-dir", type=Path, action="append", default=[])
    managed.add_argument("--vm-option", action="append", default=[])
    managed.add_argument("--main-arg", action="append", default=[])
    managed.add_argument("--expect", action="append", default=[])
    managed.add_argument("--forbid", action="append", default=[])
    managed.add_argument("--expected-exit", type=int, default=0)
    managed.add_argument("--require-nonzero", action="store_true")
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
        elif args.command == "native":
            if args.repeat < 1 or args.timeout < 1:
                raise GateError("native repeat and timeout must be positive")
            run_native(
                target_id=args.target_id,
                probe=args.probe,
                work_root=args.work_root,
                library_dirs=args.library_dir,
                probe_args=args.probe_arg,
                expected=args.expect,
                forbidden=args.forbid,
                expected_exit=args.expected_exit,
                repetitions=args.repeat,
                timeout=args.timeout,
            )
        elif args.command == "native-matrix":
            run_native_matrix(
                target_id=args.target_id,
                probe=args.probe,
                work_root=args.work_root,
                library_dirs=args.library_dir,
                matrix=args.matrix,
            )
        else:
            if args.timeout < 1:
                raise GateError("managed timeout must be positive")
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
                require_nonzero=args.require_nonzero,
                cacerts_dir=args.cacerts_dir,
                security_properties=args.security_properties,
                boot_image_dir=args.boot_image_dir,
            )
        return 0
    except (GateError, OSError, UnicodeError) as exc:
        print(f"runtime_gate.py: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
