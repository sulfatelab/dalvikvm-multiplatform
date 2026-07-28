#!/usr/bin/env python3
"""Validate the W-025 JIT-2 native-Windows acceptance package."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


def fail(message: str) -> None:
    raise RuntimeError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(*command: str) -> str:
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode != 0:
        fail(f"command failed ({result.returncode}): {' '.join(command)}\n"
             f"{result.stdout}{result.stderr}")
    return result.stdout


def check_manifest(root: Path) -> None:
    manifest_path = root / "MANIFEST.json"
    sums_path = root / "SHA256SUMS.txt"
    if not manifest_path.is_file() or not sums_path.is_file():
        fail("package manifest files are missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest.get("files")
    if not isinstance(entries, list) or manifest.get("count") != len(entries):
        fail("MANIFEST.json count does not match its file list")
    expected_paths = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and "logs" not in path.relative_to(root).parts
        and "jit-temp" not in path.relative_to(root).parts
        and path.name not in {"MANIFEST.json", "SHA256SUMS.txt"}
    }
    listed = {entry.get("path") for entry in entries}
    if listed != expected_paths:
        fail(f"manifest path mismatch missing={sorted(expected_paths - listed)} "
             f"extra={sorted(listed - expected_paths)}")
    for entry in entries:
        path = root / entry["path"]
        if path.stat().st_size != entry.get("bytes") or sha256(path) != entry.get("sha256"):
            fail(f"manifest identity mismatch: {entry['path']}")

    sums: dict[str, str] = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  \./(.+)", line)
        if match is None:
            fail(f"invalid SHA256SUMS line: {line!r}")
        sums[Path(match.group(2)).as_posix()] = match.group(1)
    if set(sums) != expected_paths | {"MANIFEST.json"}:
        fail("SHA256SUMS path set does not match package payload")
    for relative, expected in sums.items():
        if sha256(root / relative) != expected:
            fail(f"SHA256SUMS mismatch: {relative}")


def check_package(root: Path) -> None:
    required = (
        "dalvikvm.exe",
        "art.dll",
        "libw025jitmappingprobe.dll",
        "W025SectionPolicyProbe.exe",
        "W025PolicyLauncher.exe",
        "run/boot.jar",
        "run/hello.jar",
        "run/w025jitmappingprobe.jar",
        "scripts/RUN_W025_JIT2_HOST.ps1",
        "W025_JIT2_HOST_CHECKLIST.md",
        "W025_STRUCTURAL_REPORT.txt",
        "BUILD_INFO.txt",
        "README_HOST.md",
    )
    for relative in required:
        if not (root / relative).is_file():
            fail(f"required package file is missing: {relative}")
    for directory in ("logs", "jit-temp", "run/data"):
        if not (root / directory).is_dir():
            fail(f"required package directory is missing: {directory}")
    if list((root / "logs").iterdir()) or list((root / "jit-temp").iterdir()):
        fail("package logs and jit-temp directories must be empty")

    report = (root / "W025_STRUCTURAL_REPORT.txt").read_text(encoding="utf-8")
    for marker in (
        "status=PASS",
        "pagefile_section=INVALID_HANDLE_VALUE",
        "section_name=unnamed",
        "primary_view=low_R_RX",
        "alias_view=unrestricted_RW_RW",
        "source_filesystem_calls=0",
        "probe_cfg_instrumented=1",
        "W025_JIT2_SOURCE_CHECK_PASS",
    ):
        if marker not in report:
            fail(f"structural report is missing marker: {marker}")

    build_info = (root / "BUILD_INFO.txt").read_text(encoding="utf-8")
    for key in ("root_commit", "art_commit", "windows_minimum_build"):
        if not re.search(rf"^{key}=\S+$", build_info, re.MULTILINE):
            fail(f"BUILD_INFO is missing {key}")

    runner = (root / "scripts/RUN_W025_JIT2_HOST.ps1").read_text(encoding="utf-8")
    for marker in (
        "section_basic",
        "low_va_failure",
        "sec_commit_pressure",
        "runtime_mapping_64m",
        "runtime_mapping_1024m",
        "cfg_section_call",
        "cfg_runtime_mapping",
        "dynamic_code_jit_rejected",
        "dynamic_code_nojit",
        "no_jit_temp_files",
        "RESULT_W025_JIT2.txt",
        "NO_DMP_FILES",
        "OVERALL PASS",
    ):
        if marker not in runner:
            fail(f"host runner is missing contract text: {marker}")

    load_config = run("llvm-readobj", "--coff-load-config", str(root / "W025SectionPolicyProbe.exe"))
    for marker in ("CF_INSTRUMENTED", "CF_FUNCTION_TABLE_PRESENT"):
        if marker not in load_config:
            fail(f"section probe load config is missing {marker}")
    check_manifest(root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    root = args.package.resolve()
    if not root.is_dir():
        fail(f"package directory does not exist: {root}")
    check_package(root)
    print("W-025 JIT-2 host package check: PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"W-025 JIT-2 host package check: FAIL: {error}", file=sys.stderr)
        sys.exit(1)
