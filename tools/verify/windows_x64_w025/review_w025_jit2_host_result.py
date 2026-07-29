#!/usr/bin/env python3
"""Independently review a returned W-025 JIT-2 native result archive."""

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
    "section_basic",
    "low_va_failure",
    "sec_commit_pressure",
    "runtime_mapping_64m",
    "runtime_mapping_1024m",
    "cfg_section_call",
    "cfg_runtime_mapping",
    "dynamic_code_jit_rejected",
    "dynamic_code_nojit",
}

BAD_PATTERNS = (
    "Unhandled page fault",
    "Unhandled exception",
    "Access violation",
    "STATUS_ACCESS_VIOLATION",
    "0xc0000005",
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
        "W025_STRUCTURAL_REPORT.txt",
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


def review_logs(root: Path) -> tuple[int, int]:
    logs = root / "logs"
    if not logs.is_dir():
        fail("returned logs directory is missing")
    combined = {
        path.stem: path
        for path in logs.glob("*.log")
        if not path.name.endswith((".stdout.log", ".stderr.log"))
    }
    if set(combined) != EXPECTED_CASES:
        fail(f"child case mismatch missing={sorted(EXPECTED_CASES - set(combined))} "
             f"extra={sorted(set(combined) - EXPECTED_CASES)}")

    texts: dict[str, str] = {}
    for name, path in sorted(combined.items()):
        text = read_text(path)
        texts[name] = text
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
        texts["section_basic"],
        "section_basic",
        "roles=R_RX_RW type=MEM_MAPPED rwx=0 mapped_names=0",
        "execute=1",
        "W025_SECTION_POLICY_PASS mode=basic",
    )
    require(
        texts["low_va_failure"],
        "low_va_failure",
        "W025_LOW_VA_PASS",
        "rejected=1",
        "no_high_fallback=1",
        "recovery=1",
        "W025_SECTION_POLICY_PASS mode=low-va",
    )
    low_match = re.search(r"reservations=(\d+).*rejection_error=(\d+)", texts["low_va_failure"])
    if low_match is None or int(low_match.group(1)) == 0 or int(low_match.group(2)) == 0:
        fail("low_va_failure: invalid reservation or rejection record")

    require(
        texts["sec_commit_pressure"],
        "sec_commit_pressure",
        "W025_SEC_COMMIT_PASS capacity_bytes=1073741824",
        "primary_low=1 alias=1",
        "W025_SECTION_POLICY_PASS mode=pressure",
    )
    commit_match = re.search(r"commit_delta=(\d+)", texts["sec_commit_pressure"])
    if commit_match is None or int(commit_match.group(1)) < 512 * 1024 * 1024:
        fail("sec_commit_pressure: commit delta is below 512 MiB")

    for case, capacity_mib, capacity_bytes, require_cfg in (
        ("runtime_mapping_64m", 64, 67108864, "false"),
        ("runtime_mapping_1024m", 1024, 1073741824, "false"),
        ("cfg_runtime_mapping", 64, 67108864, "true"),
    ):
        require(
            texts[case],
            case,
            f"Windows x64 JIT dual-view (J-2) created: capacity={capacity_mib}MiB",
            "roles primary_data=R primary_code=RX alias_data=RW alias_code=RW "
            f"type=MEM_MAPPED rwx=0 contiguous_low=1 capacity_bytes={capacity_bytes}",
            "primary_name_length=0",
            "W025_JIT_MAPPING_PASS",
            "success=1 method=int W025JitMappingProbe.target(int)",
            f"W025JitMappingProbe PASS capacity_bytes={capacity_bytes} require_cfg={require_cfg}",
        )

    require(
        texts["cfg_section_call"],
        "cfg_section_call",
        "W025_POLICY_CHILD policy=cfg",
        "cfg_enabled=1",
        "W025_SECTION_POLICY_PASS mode=cfg-call",
        "W025_POLICY_LAUNCHER_PASS policy=cfg child_exit=0 expected=zero",
    )
    require(
        texts["cfg_runtime_mapping"],
        "cfg_runtime_mapping",
        "W025_POLICY_CHILD policy=cfg",
        "cfg_enabled=1",
        "W025_POLICY_LAUNCHER_PASS policy=cfg child_exit=0 expected=zero",
    )
    require(
        texts["dynamic_code_jit_rejected"],
        "dynamic_code_jit_rejected",
        "W025_POLICY_CHILD policy=dynamic dynamic_prohibit=1",
        "Windows x64 JIT dual-view construction failed:",
        "failed: 1655; falling back to single-view (J-1)",
        "Failed to create JIT Code Cache:",
        "VirtualProtect RemapAtEnd(",
        "failed: 1655",
        "Hello from dalvikvm!",
        "main end exception=0",
        "W025_POLICY_LAUNCHER_PASS policy=dynamic child_exit=0 expected=zero",
    )
    if "JitCodeCache::Create OK" in texts["dynamic_code_jit_rejected"]:
        fail("dynamic_code_jit_rejected: JIT cache was unexpectedly created")

    require(
        texts["dynamic_code_nojit"],
        "dynamic_code_nojit",
        "W025_POLICY_CHILD policy=dynamic dynamic_prohibit=1",
        "Hello from dalvikvm!",
        "main end exception=0",
        "W025_POLICY_LAUNCHER_PASS policy=dynamic child_exit=0 expected=zero",
    )
    if "JitCodeCache::Create OK" in texts["dynamic_code_nojit"]:
        fail("dynamic_code_nojit: JIT cache was unexpectedly created")

    result = read_text(logs / "RESULT_W025_JIT2.txt").splitlines()
    pass_count = sum(line.startswith("PASS ") for line in result)
    fail_count = sum(line.startswith("FAIL ") for line in result)
    if not result or result[-1] != "OVERALL PASS":
        fail("aggregate result does not end in OVERALL PASS")
    if pass_count != 14 or fail_count != 0:
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
    return pass_count, fail_count


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

    with tempfile.TemporaryDirectory(prefix="w025-jit2-review-") as directory:
        extracted = Path(directory)
        safe_extract(archive, extracted)
        returned = payload_root(extracted)
        compare_identity(returned, issued)
        pass_count, fail_count = review_logs(returned)

    print(
        "W-025 JIT-2 native host result review: PASS "
        f"cases={len(EXPECTED_CASES)} aggregate_pass={pass_count} "
        f"failures={fail_count} archive_sha256={sha256(archive)}"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        print(f"W-025 JIT-2 native host result review: FAIL: {error}", file=sys.stderr)
        sys.exit(1)
