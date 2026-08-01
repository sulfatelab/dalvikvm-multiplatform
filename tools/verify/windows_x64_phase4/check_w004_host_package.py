#!/usr/bin/env python3
"""Validate an already issued historical W-004 native-Windows package."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


RUNTIME_INSTANCE = "?instance_@Runtime@art@@0PEAV12@EA"
RETIRED_HELPER = "art_Runtime_instance_ptr"


def fail(message: str) -> None:
    raise RuntimeError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(tool: str, *args: str) -> str:
    result = subprocess.run([tool, *args], text=True, capture_output=True)
    if result.returncode != 0:
        fail(
            f"command failed ({result.returncode}): {tool} {' '.join(args)}\n"
            f"{result.stdout}{result.stderr}"
        )
    return result.stdout


def parse_report(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    required = {
        "status": "PASS",
        "retired_helper_references": "0",
        "runtime_instance_exports": "1",
        "openjdkjvmti_runtime_instance_imports": "1",
    }
    for key, expected in required.items():
        if values.get(key) != expected:
            fail(f"structural report has {key}={values.get(key)!r}, expected {expected!r}")
    try:
        if int(values.get("direct_total", "0")) <= 0:
            fail("structural report has no direct Runtime::instance_ relocations")
    except ValueError as error:
        fail(f"invalid direct_total in structural report: {error}")
    return values


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
        and path.name not in {"MANIFEST.json", "SHA256SUMS.txt"}
    }
    listed_paths = {entry.get("path") for entry in entries}
    if listed_paths != expected_paths:
        missing = sorted(expected_paths - listed_paths)
        extra = sorted(listed_paths - expected_paths)
        fail(f"MANIFEST.json path mismatch: missing={missing} extra={extra}")
    for entry in entries:
        path = root / entry["path"]
        if entry.get("bytes") != path.stat().st_size:
            fail(f"manifest size mismatch: {entry['path']}")
        if entry.get("sha256") != sha256(path):
            fail(f"manifest hash mismatch: {entry['path']}")

    sums: dict[str, str] = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            fail(f"invalid SHA256SUMS line: {line!r}")
        relative = match.group(2)
        if relative.startswith("./"):
            relative = relative[2:]
        sums[Path(relative).as_posix()] = match.group(1)
    sum_paths = expected_paths | {"MANIFEST.json"}
    if set(sums) != sum_paths:
        fail("SHA256SUMS.txt path set does not match package payload")
    for relative, expected in sums.items():
        if sha256(root / relative) != expected:
            fail(f"SHA256SUMS mismatch: {relative}")


def check_package(root: Path) -> None:
    required_files = [
        "dalvikvm.exe",
        "art.dll",
        "openjdkjvmti.dll",
        "libcriticalnativeprobe.dll",
        "criticalnativeprobe.dll",
        "libnativeabiprobe.dll",
        "libjvmtiforceprobe.dll",
        "jvmtiforceprobe.dll",
        "run/boot.jar",
        "run/hello.jar",
        "run/FloatProbe.jar",
        "run/criticalnativeprobe.jar",
        "run/fastnativeabiprobe.jar",
        "run/jvmtiforceprobe.jar",
        "run/gcstressprobe.jar",
        "run/threadheavyprobe.jar",
        "scripts/RUN_W004_HOST.ps1",
        "W004_HOST_CHECKLIST.md",
        "W004_STRUCTURAL_REPORT.txt",
        "BUILD_INFO.txt",
    ]
    for relative in required_files:
        if not (root / relative).is_file():
            fail(f"required package file is missing: {relative}")
    if not (root / "empty-native-dir").is_dir():
        fail("empty-native-dir is missing")

    report = parse_report(root / "W004_STRUCTURAL_REPORT.txt")
    for relative, key in (
        ("art.dll", "art_sha256"),
        ("openjdkjvmti.dll", "openjdkjvmti_sha256"),
    ):
        actual = sha256(root / relative)
        if report.get(key) != actual:
            fail(f"structural report hash mismatch for {relative}")

    runner = (root / "scripts/RUN_W004_HOST.ps1").read_text(encoding="utf-8")
    required_runner_text = [
        "17134",
        "Test-PackageIntegrity",
        "Test-StructuralReport",
        "nterp_xint",
        "jit_dual",
        "float_threshold0_dual",
        "critical_$mode",
        "native_abi_$mode",
        "jvmti_$mode",
        "gcstress",
        "threadheavy",
        "repeat_hello_",
        "DMP_SCAN.txt",
        "OVERALL PASS",
    ]
    for marker in required_runner_text:
        if marker not in runner:
            fail(f"host runner is missing required contract text: {marker}")
    if "llvm-readobj" in runner or "llvm-objdump" in runner:
        fail("host runner must not require LLVM inspection tools")

    readobj = shutil.which("llvm-readobj")
    if readobj is None:
        fail("llvm-readobj is required for Linux-side package validation")
    exports = run(readobj, "--coff-exports", str(root / "art.dll"))
    if exports.count(f"Name: {RUNTIME_INSTANCE}") != 1:
        fail("packaged art.dll does not export Runtime::instance_ exactly once")
    if RETIRED_HELPER in exports:
        fail("packaged art.dll exports the retired helper")
    imports = run(readobj, "--coff-imports", str(root / "openjdkjvmti.dll"))
    if imports.count(f"Symbol: {RUNTIME_INSTANCE}") != 1:
        fail("packaged openjdkjvmti.dll does not import Runtime::instance_ exactly once")
    if RETIRED_HELPER in imports:
        fail("packaged openjdkjvmti.dll imports the retired helper")

    check_manifest(root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    root = args.package.resolve()
    if not root.is_dir():
        fail(f"package directory does not exist: {root}")
    check_package(root)
    print("W-004 host package check: PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"W-004 host package check: FAIL: {error}", file=sys.stderr)
        sys.exit(1)
