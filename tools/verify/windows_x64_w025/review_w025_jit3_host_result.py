#!/usr/bin/env python3
"""Independently review a returned W-025 JIT-3 native result archive."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
import zipfile


EXPECTED_CASES = {
    "jit3_j2_stress": (24, "j2"),
    "jit3_j1_compare": (12, "j1"),
    "jit3_j2_repeat_a": (8, "j2"),
    "jit3_j2_repeat_b": (8, "j2"),
}

BAD_PATTERNS = (
    "W025_JIT3_FAIL",
    "Unhandled page fault",
    "Unhandled exception",
    "Access violation",
    "STATUS_ACCESS_VIOLATION",
    "0xc0000005",
    "AssertionError",
    "missing_marker=",
    "forbidden_marker=",
    "launch_error=",
)


def fail(message: str) -> None:
    raise RuntimeError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace").replace("\r\n", "\n")


def require(text: str, case: str, *markers: str) -> None:
    for marker in markers:
        if marker not in text:
            fail(f"{case}: missing marker {marker!r}")


def safe_extract(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as source:
        bad_member = source.testzip()
        if bad_member is not None:
            fail(f"ZIP CRC failure: {bad_member}")
        for info in source.infolist():
            member = PurePosixPath(info.filename)
            if member.is_absolute() or ".." in member.parts:
                fail(f"unsafe ZIP member: {info.filename}")
            unix_mode = (info.external_attr >> 16) & 0o170000
            if unix_mode == 0o120000:
                fail(f"symbolic links are not accepted: {info.filename}")
        source.extractall(destination)


def payload_root(extracted: Path) -> Path:
    if (extracted / "BUILD_INFO.txt").is_file():
        return extracted
    candidates = [path for path in extracted.iterdir() if path.is_dir()]
    if len(candidates) == 1 and (candidates[0] / "BUILD_INFO.txt").is_file():
        return candidates[0]
    fail("returned archive does not contain one identifiable package root")


def compare_identity(returned: Path, issued: Path) -> None:
    for name in (
        "BUILD_INFO.txt",
        "MANIFEST.json",
        "SHA256SUMS.txt",
        "W025_JIT3_SOURCE_REPORT.txt",
    ):
        returned_path = returned / name
        issued_path = issued / name
        if not returned_path.is_file() or returned_path.read_bytes() != issued_path.read_bytes():
            fail(f"returned immutable identity differs from issued package: {name}")

    manifest = json.loads((returned / "MANIFEST.json").read_text(encoding="utf-8"))
    entries = manifest.get("files")
    if not isinstance(entries, list) or manifest.get("count") != len(entries):
        fail("returned MANIFEST.json count is invalid")
    for entry in entries:
        path = returned / entry["path"]
        if not path.is_file() or path.stat().st_size != entry.get("bytes"):
            fail(f"returned payload size mismatch: {entry['path']}")
        if sha256(path) != entry.get("sha256"):
            fail(f"returned payload hash mismatch: {entry['path']}")


def parse_pass_record(text: str, case: str, cycles: int) -> dict[str, int]:
    match = re.search(r"^W025_JIT3_PASS (.+)$", text, re.MULTILINE)
    if match is None:
        fail(f"{case}: W025_JIT3_PASS record is missing")
    values: dict[str, int] = {}
    for key, value in re.findall(r"([a-z_]+)=(\d+)", match.group(1)):
        values[key] = int(value)
    expected = {
        "methods": 24,
        "managed": 16,
        "jni": 8,
        "unique_allocations": 24,
        "cycles": cycles,
        "collections": cycles,
        "compilations": 24 * (cycles + 1),
        "exact_reuse": 24 * cycles,
        "missing_live": 0,
        "stale_dead": 0,
        "unwind_failures": 0,
        "callback_tables": 0,
    }
    for key, expected_value in expected.items():
        if values.get(key) != expected_value:
            fail(f"{case}: {key}={values.get(key)} expected={expected_value}")
    for key in ("live_lookups", "dead_lookups", "virtual_unwinds"):
        if values.get(key, 0) <= 0:
            fail(f"{case}: {key} is not positive")
    if values.get("lookup_maximum_ns", -1) < values.get("lookup_average_ns", 0):
        fail(f"{case}: lookup maximum is below average")
    return values


def review_logs(root: Path) -> tuple[int, int, int, int, int]:
    logs = root / "logs"
    if not logs.is_dir():
        fail("returned logs directory is missing")
    combined = {
        path.stem: path
        for path in logs.glob("*.log")
        if not path.name.endswith((".stdout.log", ".stderr.log"))
    }
    if set(combined) != set(EXPECTED_CASES):
        fail(f"child case mismatch missing={sorted(set(EXPECTED_CASES) - set(combined))} "
             f"extra={sorted(set(combined) - set(EXPECTED_CASES))}")

    total_collections = 0
    total_compilations = 0
    total_reuse = 0
    for name, path in sorted(combined.items()):
        cycles, mode = EXPECTED_CASES[name]
        text = read_text(path)
        for marker in (f"name={name}", "exit=0", "expected_exit=0", "timed_out=False"):
            require(text, name, marker)
        for pattern in BAD_PATTERNS:
            if pattern.lower() in text.lower():
                fail(f"{name}: forbidden log pattern {pattern!r}")
        for suffix, heading in (("stdout", "--- stdout ---"), ("stderr", "--- stderr ---")):
            child = logs / f"{name}.{suffix}.log"
            if not child.is_file() or heading not in text:
                fail(f"{name}: missing {suffix} evidence")
            child_text = read_text(child).strip()
            if child_text and child_text not in text:
                fail(f"{name}: combined log does not contain {suffix} output")
        require(
            text,
            name,
            "missing_live=0 stale_dead=0 unwind_failures=0",
            "callback_tables=0",
            f"W025JitLifecycleStressProbe PASS cycles={cycles}",
            "jni_values=pass",
            "main end exception=0",
        )
        dual_marker = "Windows x64 JIT dual-view (J-2) created: capacity=16MiB"
        if mode == "j2":
            require(text, name, dual_marker)
        elif dual_marker in text:
            fail(f"{name}: J-1 comparison unexpectedly used J-2")
        values = parse_pass_record(text, name, cycles)
        total_collections += values["collections"]
        total_compilations += values["compilations"]
        total_reuse += values["exact_reuse"]

    result = read_text(logs / "RESULT_W025_JIT3.txt").splitlines()
    pass_count = sum(line.startswith("PASS ") for line in result)
    fail_count = sum(line.startswith("FAIL ") for line in result)
    if not result or result[-1] != "OVERALL PASS":
        fail("aggregate result does not end in OVERALL PASS")
    if pass_count != 9 or fail_count != 0:
        fail(f"aggregate count mismatch pass={pass_count} fail={fail_count}")
    if read_text(logs / "DMP_SCAN.txt").strip() != "NO_DMP_FILES":
        fail("dump scan is not NO_DMP_FILES")
    if list(root.rglob("*.dmp")) or list(root.rglob("*.trace")):
        fail("returned archive contains a dump or trace")
    if any((root / "jit-temp").rglob("*")):
        fail("returned archive contains a JIT temporary file")
    host_info = read_text(logs / "HOST_INFO.txt")
    build_match = re.search(r"^build=(\d+)$", host_info, re.MULTILINE)
    if build_match is None or int(build_match.group(1)) < 17134:
        fail("host build is absent or below Windows 10 RS4")
    return pass_count, fail_count, total_collections, total_compilations, total_reuse


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--issued", type=Path, required=True)
    args = parser.parse_args()
    archive = args.archive.resolve()
    issued = args.issued.resolve()
    if not archive.is_file():
        fail(f"returned archive does not exist: {archive}")
    if not issued.is_dir():
        fail(f"issued package directory does not exist: {issued}")

    with tempfile.TemporaryDirectory(prefix="w025-jit3-review-") as directory:
        extracted = Path(directory)
        safe_extract(archive, extracted)
        returned = payload_root(extracted)
        compare_identity(returned, issued)
        pass_count, fail_count, collections, compilations, reuse = review_logs(returned)

    print(
        "W-025 JIT-3 native host result review: PASS "
        f"cases={len(EXPECTED_CASES)} aggregate_pass={pass_count} failures={fail_count} "
        f"collections={collections} compilations={compilations} exact_reuse={reuse} "
        f"archive_sha256={sha256(archive)}"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        print(f"W-025 JIT-3 native host result review: FAIL: {error}", file=sys.stderr)
        sys.exit(1)
