#!/usr/bin/env python3
"""Validate the W-025 JIT-4 native-Windows final-regression package."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


def fail(message: str) -> None:
    raise RuntimeError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    root = args.package.resolve()
    if not root.is_dir():
        fail(f"package directory does not exist: {root}")

    required = (
        "BUILD_INFO.txt",
        "MANIFEST.json",
        "SHA256SUMS.txt",
        "W025_JIT4_SOURCE_REPORT.txt",
        "W025_JIT4_HOST_CHECKLIST.md",
        "dalvikvm.exe",
        "art.dll",
        "libopenjdk.dll",
        "openjdkjvmti.dll",
        "libcriticalnativeprobe.dll",
        "criticalnativeprobe.dll",
        "libnativeabiprobe.dll",
        "libw025jitlifecyclestressprobe.dll",
        "run/boot.jar",
        "run/hello.jar",
        "run/CEnc.jar",
        "run/CEnc2.jar",
        "run/CELike.jar",
        "run/CFloat.jar",
        "run/FloatProbe.jar",
        "run/IFloat.jar",
        "run/JLFloat.jar",
        "run/RFloat.jar",
        "run/SFloat.jar",
        "run/MathProbe.jar",
        "run/ioprobe.jar",
        "run/netprobe.jar",
        "run/gcprobe.jar",
        "run/throwprobe.jar",
        "run/criticalnativeprobe.jar",
        "run/fastnativeabiprobe.jar",
        "run/w002osrprobe.jar",
        "run/crashnativeprobe.jar",
        "run/w025jitlifecyclestressprobe.jar",
        "scripts/RUN_W025_JIT4_HOST.ps1",
    )
    for relative in required:
        if not (root / relative).is_file():
            fail(f"required package file is missing: {relative}")

    report = (root / "W025_JIT4_SOURCE_REPORT.txt").read_text(encoding="utf-8")
    report_values: dict[str, str] = {}
    for line in report.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            report_values[key] = value
    expected_report = {
        "status": "PASS",
        "cases": "28",
        "jit_smoke_records": "12",
        "jit_matrix_records": "14",
        "jit_disabled_controls": "2",
        "default_memory_mode": "j2",
        "j1_cases": "0",
        "native_abi_targets": "7",
        "osr_modes": "nterp,switch",
        "lifecycle_cycles": "8",
        "fatal_modes": "static,jit,osr",
        "fatal_minidumps": "3",
        "fatal_warmup_env": "windows_x64",
        "nterp_fp_result_source": "xmm0",
    }
    for key, value in expected_report.items():
        if report_values.get(key) != value:
            fail(f"source report mismatch: {key}={report_values.get(key)!r}")
    if "W025_JIT4_SOURCE_CHECK_PASS" not in report:
        fail("source report lacks PASS marker")

    openjdk = (root / "libopenjdk.dll").read_bytes()
    if b"ART_WINDOWS_X64_CRASH_NATIVE_WARMUP\x00" not in openjdk:
        fail("libopenjdk.dll lacks the Windows x64 fatal-warmup environment key")
    if b"ART_WIN64_CRASH_NATIVE_WARMUP\x00" in openjdk:
        fail("libopenjdk.dll contains the retired Win64 fatal-warmup key")

    build_info = (root / "BUILD_INFO.txt").read_text(encoding="utf-8")
    for marker in (
        "windows_minimum_build=17134",
        "jit4_cases=28",
        "jit4_default_memory_mode=j2",
        "jit4_j1_cases=0",
        "jit4_fatal_minidumps=3",
    ):
        if marker not in build_info:
            fail(f"BUILD_INFO.txt lacks {marker!r}")
    for key in ("root_commit", "art_commit"):
        if re.search(rf"^{key}=[0-9a-f]{{40}}$", build_info, re.MULTILINE) is None:
            fail(f"BUILD_INFO.txt has invalid {key}")

    manifest = json.loads((root / "MANIFEST.json").read_text(encoding="utf-8"))
    entries = manifest.get("files")
    if not isinstance(entries, list) or manifest.get("count") != len(entries):
        fail("MANIFEST.json count is invalid")
    manifest_paths: set[str] = set()
    for entry in entries:
        relative = entry.get("path")
        if not isinstance(relative, str) or relative in manifest_paths:
            fail(f"invalid or duplicate manifest path: {relative!r}")
        manifest_paths.add(relative)
        path = root / relative
        if not path.is_file() or path.stat().st_size != entry.get("bytes"):
            fail(f"manifest size mismatch: {relative}")
        if sha256(path) != entry.get("sha256"):
            fail(f"manifest hash mismatch: {relative}")
    if manifest_paths != {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and "logs" not in path.relative_to(root).parts
        and "jit-temp" not in path.relative_to(root).parts
        and path.name not in {"MANIFEST.json", "SHA256SUMS.txt"}
        and path.suffix.lower() not in {".dmp", ".trace"}
    }:
        fail("manifest file set differs from immutable package payload")

    sums: dict[str, str] = {}
    for line in (root / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  \./(.+)", line)
        if match is None:
            fail(f"invalid SHA256SUMS line: {line!r}")
        sums[match.group(2)] = match.group(1)
    if sums != {path: sha256(root / path) for path in manifest_paths | {"MANIFEST.json"}}:
        fail("SHA256SUMS entries differ from manifest payload")

    runner = (root / "scripts/RUN_W025_JIT4_HOST.ps1").read_text(encoding="utf-8")
    for marker in (
        "smoke_default_verbose",
        "smoke_env_disabled",
        "matrix_throw",
        "critical_default",
        "native_abi_default",
        '"osr_$interpreter"',
        "lifecycle_default",
        "fatal_static",
        "fatal_jit_default",
        "fatal_osr_default",
        "PASS fatal_dump_scan count=3",
        "OVERALL PASS",
    ):
        if marker not in runner:
            fail(f"host runner lacks marker {marker!r}")
    if "ART_WINDOWS_X64_JIT_DUAL = '0'" in runner:
        fail("JIT-4 host runner contains a J-1 arm")

    if any((root / "logs").glob("*")):
        fail("issued package logs directory is not empty")
    if any((root / "jit-temp").rglob("*")):
        fail("issued package JIT temp directory is not empty")
    if list(root.rglob("*.dmp")) or list(root.rglob("*.trace")):
        fail("issued package contains a dump or trace")

    print("W-025 JIT-4 host package check: PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"W-025 JIT-4 host package check: FAIL: {error}", file=sys.stderr)
        sys.exit(1)
