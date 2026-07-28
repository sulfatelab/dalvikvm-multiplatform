#!/usr/bin/env python3
"""Validate the focused W-002 native-Windows acceptance package."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


ATTACH_EXPORTS = {
    "JNI_OnLoad",
    "Java_W002AttachProbe_runAttachMatrix",
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


def parse_report(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    required = {
        "status": "PASS",
        "attach_exports": "2",
        "host_llvm_tools_required": "no",
    }
    for key, expected in required.items():
        if values.get(key) != expected:
            fail(f"structural report has {key}={values.get(key)!r}, expected {expected!r}")
    if "W-002 managed-entry structural check: PASS" not in values.get(
        "checker_output", ""
    ):
        fail("structural report does not contain the W-002 checker PASS marker")
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
        "libw002attachprobe.dll",
        "run/boot.jar",
        "run/w002osrprobe.jar",
        "run/w002attachprobe.jar",
        "scripts/RUN_W002_HOST.ps1",
        "W002_HOST_CHECKLIST.md",
        "W002_STRUCTURAL_REPORT.txt",
        "BUILD_INFO.txt",
    ]
    for relative in required_files:
        if not (root / relative).is_file():
            fail(f"required package file is missing: {relative}")

    report = parse_report(root / "W002_STRUCTURAL_REPORT.txt")
    for relative, key in (
        ("art.dll", "art_sha256"),
        ("libw002attachprobe.dll", "attach_dll_sha256"),
    ):
        actual = sha256(root / relative)
        if report.get(key) != actual:
            fail(f"structural report hash mismatch for {relative}")

    runner = (root / "scripts/RUN_W002_HOST.ps1").read_text(encoding="utf-8")
    required_runner_text = [
        "17134",
        "Test-PackageIntegrity",
        "Test-StructuralReport",
        "foreach ($mode in @('dual', 'j1'))",
        "foreach ($interpreter in @('default', 'switch'))",
        "foreach ($repeat in 1..2)",
        "-Xjitwarmupthreshold:100",
        "warmup_threshold=100, optimize_threshold=100",
        "W002OsrProbe OK checksum=65553463744",
        "W002AttachProbe OK completed=16",
        "ART_WINDOWS_X64_NTERP",
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
    exports = run(readobj, "--coff-exports", str(root / "libw002attachprobe.dll"))
    found = {
        match.group(1)
        for match in re.finditer(r"^\s*Name: (\S+)\s*$", exports, re.MULTILINE)
        if match.group(1) in ATTACH_EXPORTS
    }
    if found != ATTACH_EXPORTS:
        fail(f"attach DLL exports mismatch: expected={sorted(ATTACH_EXPORTS)} found={sorted(found)}")

    check_manifest(root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    root = args.package.resolve()
    if not root.is_dir():
        fail(f"package directory does not exist: {root}")
    check_package(root)
    print("W-002 host package check: PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"W-002 host package check: FAIL: {error}", file=sys.stderr)
        sys.exit(1)
