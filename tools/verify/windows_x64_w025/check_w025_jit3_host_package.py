#!/usr/bin/env python3
"""Validate the W-025 JIT-3 native-Windows acceptance package."""

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
        "libw025jitlifecyclestressprobe.dll",
        "run/boot.jar",
        "run/w025jitlifecyclestressprobe.jar",
        "scripts/RUN_W025_JIT3_HOST.ps1",
        "W025_JIT3_HOST_CHECKLIST.md",
        "W025_JIT3_SOURCE_REPORT.txt",
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

    report = (root / "W025_JIT3_SOURCE_REPORT.txt").read_text(encoding="utf-8")
    for marker in (
        "status=PASS",
        "managed_methods=16",
        "jni_methods=8",
        "synthetic_rbp=1",
        "active_unwind_quiescence=1",
        "lifecycle_invalidate_collect_reuse=1",
        "nterp_fp_result_source=xmm0",
        "callback_tables=0",
        "probe_exports=9",
        "W025_JIT3_SOURCE_CHECK_PASS",
    ):
        if marker not in report:
            fail(f"source report is missing marker: {marker}")

    build_info = (root / "BUILD_INFO.txt").read_text(encoding="utf-8")
    for key in (
        "root_commit",
        "art_commit",
        "windows_minimum_build",
        "jit3_default_stress_cycles",
        "jit3_comparison_cycles",
    ):
        if not re.search(rf"^{key}=\S+$", build_info, re.MULTILINE):
            fail(f"BUILD_INFO is missing {key}")

    runner = (root / "scripts/RUN_W025_JIT3_HOST.ps1").read_text(encoding="utf-8")
    for marker in (
        "jit3_j2_stress",
        "jit3_j1_compare",
        "jit3_j2_repeat_a",
        "jit3_j2_repeat_b",
        "RtlLookupFunctionEntry",
        "missing_live=0 stale_dead=0 unwind_failures=0",
        "callback_tables=0",
        "jni_values=pass",
        "RESULT_W025_JIT3.txt",
        "NO_DMP_FILES",
        "OVERALL PASS",
        "[System.Diagnostics.Stopwatch]::StartNew()",
        "$timer.ElapsedMilliseconds",
    ):
        if marker not in runner:
            fail(f"host runner is missing contract text: {marker}")
    if "[DateTime]::UtcNow" in runner:
        fail("host runner uses wall-clock time for child deadlines")

    exports = run(
        "llvm-readobj",
        "--coff-exports",
        str(root / "libw025jitlifecyclestressprobe.dll"),
    )
    for symbol in (
        "Java_W025JitLifecycleStressProbe_nativeRun",
        "Java_W025JitLifecycleStressProbe_nativeD",
        "Java_W025JitLifecycleStressProbe_nativeF",
        "Java_W025JitLifecycleStressProbe_nativeV",
    ):
        if f"Name: {symbol}" not in exports:
            fail(f"probe DLL is missing export: {symbol}")
    check_manifest(root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    root = args.package.resolve()
    if not root.is_dir():
        fail(f"package directory does not exist: {root}")
    check_package(root)
    print("W-025 JIT-3 host package check: PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"W-025 JIT-3 host package check: FAIL: {error}", file=sys.stderr)
        sys.exit(1)
