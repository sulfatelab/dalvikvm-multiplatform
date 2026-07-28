#!/usr/bin/env python3
"""Validate the focused W-003 native-Windows acceptance package."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


FRAME_JNI_EXPORTS = {
    "Java_W003FrameProbe_nativeEcho",
    "Java_W003FrameProbe_resetCounters",
    "Java_W003FrameProbe_snapshotCounters",
}
XMM_JNI_EXPORT = "Java_W003XmmSentinelProbe_runXmmSentinel"
ART_PROBE_EXPORTS = {
    "art_w003_frame_probe_reset",
    "art_w003_frame_probe_snapshot",
}


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


def exported_names(readobj: str, path: Path) -> set[str]:
    output = run(readobj, "--coff-exports", str(path))
    return {
        match.group(1)
        for match in re.finditer(r"^\s*Name: (\S+)\s*$", output, re.MULTILINE)
    }


def parse_report(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    required = {
        "status": "PASS",
        "product_probe_exports": "0",
        "frame_probe_exports": "2",
        "frame_counter_symbols": "4",
        "frame_jni_exports": "3",
        "xmm_jni_exports": "1",
        "xmm_unwind_saves": "10",
        "host_llvm_tools_required": "no",
    }
    for key, expected in required.items():
        if values.get(key) != expected:
            fail(f"structural report has {key}={values.get(key)!r}, expected {expected!r}")
    if "W-003 quick-boundary structural check: PASS" not in values.get(
        "checker_output", ""
    ):
        fail("structural report does not contain the W-003 checker PASS marker")
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
        "art.product.dll",
        "art.frame-probe.dll",
        "libw003frameprobe.dll",
        "libw003xmmsentinel.dll",
        "run/boot.jar",
        "run/w003frameprobe.jar",
        "run/w003xmmsentinelprobe.jar",
        "scripts/RUN_W003_HOST.ps1",
        "W003_HOST_CHECKLIST.md",
        "W003_STRUCTURAL_REPORT.txt",
        "BUILD_INFO.txt",
    ]
    for relative in required_files:
        if not (root / relative).is_file():
            fail(f"required package file is missing: {relative}")

    report = parse_report(root / "W003_STRUCTURAL_REPORT.txt")
    for relative, key in (
        ("art.product.dll", "product_art_sha256"),
        ("art.frame-probe.dll", "frame_art_sha256"),
        ("libw003frameprobe.dll", "frame_probe_dll_sha256"),
        ("libw003xmmsentinel.dll", "xmm_probe_dll_sha256"),
    ):
        if report.get(key) != sha256(root / relative):
            fail(f"structural report hash mismatch for {relative}")
    if sha256(root / "art.dll") != sha256(root / "art.product.dll"):
        fail("issued package art.dll is not the product variant")

    runner = (root / "scripts/RUN_W003_HOST.ps1").read_text(encoding="utf-8")
    required_runner_text = [
        "17134",
        "Test-PackageIntegrity",
        "Test-StructuralReport",
        "PreflightPassed",
        "FAIL test_matrix skipped_preflight",
        "Set-ArtVariant",
        "art.frame-probe.dll",
        "art.product.dll",
        "Test-FrameCounters",
        "foreach ($mode in @('int', 'switch', 'nterp', 'jit'))",
        "foreach ($repeat in 1..2)",
        "foreach ($mode in @('nterp', 'switch', 'jit'))",
        "W003FrameProbe OK mode=",
        "W003XmmSentinelProbe OK",
        "selfTestMask=63",
        "fullSelfTestMask=1023",
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
    product_exports = exported_names(readobj, root / "art.product.dll")
    frame_exports = exported_names(readobj, root / "art.frame-probe.dll")
    if product_exports & ART_PROBE_EXPORTS:
        fail("product ART unexpectedly exports W-003 probe functions")
    if not ART_PROBE_EXPORTS <= frame_exports:
        fail("instrumented ART is missing W-003 probe functions")
    frame_jni = exported_names(readobj, root / "libw003frameprobe.dll")
    if not FRAME_JNI_EXPORTS <= frame_jni:
        fail("frame-probe JNI exports are incomplete")
    xmm_jni = exported_names(readobj, root / "libw003xmmsentinel.dll")
    if XMM_JNI_EXPORT not in xmm_jni:
        fail("XMM-sentinel JNI export is missing")

    if any(path.is_file() and path.suffix.lower() == ".dmp" for path in root.rglob("*")):
        fail("issued package contains crash dumps")
    if any(
        path.is_file() and path.suffix.lower() == ".trace" for path in root.rglob("*")
    ):
        fail("issued package contains trace files")
    check_manifest(root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    root = args.package.resolve()
    if not root.is_dir():
        fail(f"package directory does not exist: {root}")
    check_package(root)
    print("W-003 host package check: PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"W-003 host package check: FAIL: {error}", file=sys.stderr)
        sys.exit(1)
