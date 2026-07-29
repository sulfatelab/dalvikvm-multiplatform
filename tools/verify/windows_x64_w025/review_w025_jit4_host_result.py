#!/usr/bin/env python3
"""Independently review a returned W-025 JIT-4 native result archive."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
import zipfile


MATRIX_CASES = {
    "matrix_cenc": "main end exception=0",
    "matrix_cenc2": "main end exception=0",
    "matrix_celike": "main end exception=0",
    "matrix_cfloat": "main end exception=0",
    "matrix_floatprobe": "FloatProbe OK",
    "matrix_ifloat": "IFloat OK",
    "matrix_jlfloat": "main end exception=0",
    "matrix_rfloat": "main end exception=0",
    "matrix_sfloat": "main end exception=0",
    "matrix_math": "MathProbe.done=ok",
    "matrix_io": "IoProbe.done=ok",
    "matrix_net": "NetProbe.done=ok",
    "matrix_gc": "GcProbe.done=ok",
    "matrix_throw": "phase3-throw-ok",
}
FATAL_CASES = {"fatal_static", "fatal_jit_default", "fatal_osr_default"}
EXPECTED_CASES = {
    "smoke_default_verbose",
    "smoke_env_disabled",
    "smoke_xusejit_false",
    "smoke_filter",
    "smoke_exclude",
    "smoke_quiet",
    *MATRIX_CASES,
    "critical_default",
    "native_abi_default",
    "osr_nterp",
    "osr_switch",
    "lifecycle_default",
    *FATAL_CASES,
}
BAD_NONFATAL = (
    "Check failed:",
    "Fatal signal",
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


def forbid(text: str, case: str, *markers: str) -> None:
    lowered = text.lower()
    for marker in markers:
        if marker.lower() in lowered:
            fail(f"{case}: forbidden marker {marker!r}")


def safe_extract(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as source:
        bad_member = source.testzip()
        if bad_member is not None:
            fail(f"ZIP CRC failure: {bad_member}")
        for info in source.infolist():
            member = PurePosixPath(info.filename)
            if member.is_absolute() or ".." in member.parts:
                fail(f"unsafe ZIP member: {info.filename}")
            if ((info.external_attr >> 16) & 0o170000) == 0o120000:
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
        "W025_JIT4_SOURCE_REPORT.txt",
    ):
        if not (returned / name).is_file() or (returned / name).read_bytes() != (issued / name).read_bytes():
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


def process_logs(root: Path) -> dict[str, str]:
    logs = root / "logs"
    combined = {
        path.stem: path
        for path in logs.glob("*.log")
        if not path.name.endswith((".stdout.log", ".stderr.log"))
    }
    if set(combined) != EXPECTED_CASES:
        fail(
            f"child case mismatch missing={sorted(EXPECTED_CASES - set(combined))} "
            f"extra={sorted(set(combined) - EXPECTED_CASES)}"
        )
    texts: dict[str, str] = {}
    for name, path in combined.items():
        text = read_text(path)
        texts[name] = text
        require(text, name, f"name={name}", "timed_out=False")
        exit_match = re.search(r"^exit=(-?\d+)$", text, re.MULTILINE)
        if exit_match is None:
            fail(f"{name}: exit metadata is missing")
        exit_code = int(exit_match.group(1))
        if name in FATAL_CASES:
            require(text, name, "require_nonzero=True", "new_minidump=")
            if exit_code == 0:
                fail(f"{name}: fatal child unexpectedly returned zero")
        elif exit_code != 0:
            fail(f"{name}: nonfatal child returned {exit_code}")
        for suffix, heading in (("stdout", "--- stdout ---"), ("stderr", "--- stderr ---")):
            child = logs / f"{name}.{suffix}.log"
            if not child.is_file() or heading not in text:
                fail(f"{name}: missing {suffix} evidence")
            child_text = read_text(child).strip()
            if child_text and child_text not in text:
                fail(f"{name}: combined log does not contain {suffix} output")
        if name not in FATAL_CASES:
            forbid(text, name, *BAD_NONFATAL)
    return texts


def review_nonfatal(texts: dict[str, str]) -> None:
    hello = ("Hello from dalvikvm!", "main end exception=0")
    require(
        texts["smoke_default_verbose"],
        "smoke_default_verbose",
        *hello,
        "JitCodeCache::Create OK",
        "Windows x64 JIT dual-view (J-2) created",
        "Windows x64 CompileMethod done success=1 method=java.lang.StringBuilder",
        "Windows x64 CompileMethod done success=1 method=java.lang.StringFactory.newStringFromBytes",
    )
    for case in (
        "smoke_env_disabled",
        "smoke_xusejit_false",
        "smoke_filter",
        "smoke_exclude",
        "smoke_quiet",
    ):
        require(texts[case], case, *hello)
    forbid(
        texts["smoke_env_disabled"],
        "smoke_env_disabled",
        "Windows x64 CompileMethod done success=1",
    )
    require(
        texts["smoke_filter"],
        "smoke_filter",
        "Windows x64 CompileMethod done success=1 method=java.lang.StringBuilder",
    )
    forbid(
        texts["smoke_exclude"],
        "smoke_exclude",
        "Windows x64 CompileMethod done success=1 method=java.lang.StringBuilder",
    )
    forbid(texts["smoke_quiet"], "smoke_quiet", "Windows x64 CompileMethod done success=1")

    for case, marker in MATRIX_CASES.items():
        require(
            texts[case],
            case,
            marker,
            "main end exception=0",
            "Windows x64 JIT dual-view (J-2) created",
        )

    require(
        texts["critical_default"],
        "critical_default",
        "CriticalNativeProbe instrumentation OK",
        "CriticalNativeDlsymProbe postTracing OK",
        "main end exception=0",
        "Windows x64 JIT dual-view (J-2) created",
    )
    if not re.search(
        r"CriticalNativeProbe tracingMode before=0 during=[1-9][0-9]* after=0 traceFileDeleted=true",
        texts["critical_default"],
    ):
        fail("critical_default: tracing transition marker mismatch")

    native = texts["native_abi_default"]
    require(
        native,
        "native_abi_default",
        "FastNativeAbiProbe OK",
        "main end exception=0",
        "Windows x64 JIT dual-view (J-2) created",
    )
    for method in (
        "double FastNativeAbiProbe.normalRegistered(",
        "double FastNativeAbiProbe.fastRegistered(",
        "double FastNativeAbiProbe.normalDlsym(",
        "double FastNativeAbiProbe.fastDlsym(",
        "double FastNativeAbiProbe.normalInstance(",
        "double FastNativeAbiProbe.fastInstance(",
        "int FastNativeAbiProbe.callMask(",
    ):
        if native.count("success=1 method=" + method) != 1:
            fail(f"native_abi_default: expected one compile for {method}")

    osr_common = (
        "warmup_threshold=100, optimize_threshold=100",
        "W002OsrProbe OK checksum=65553463744",
        "kind=Baseline",
        "kind=Osr",
        "Jumping to long W002OsrProbe.osrLoop(int)",
        "main end exception=0",
        "Windows x64 JIT dual-view (J-2) created",
    )
    require(texts["osr_nterp"], "osr_nterp", *osr_common)
    forbid(texts["osr_nterp"], "osr_nterp", "Done running OSR code for long W002OsrProbe.osrLoop(int)")
    require(
        texts["osr_switch"],
        "osr_switch",
        *osr_common,
        "Done running OSR code for long W002OsrProbe.osrLoop(int)",
    )

    lifecycle = texts["lifecycle_default"]
    require(
        lifecycle,
        "lifecycle_default",
        "W025_JIT3_PASS methods=24 managed=16 jni=8 unique_allocations=24 cycles=8 collections=8 compilations=216 exact_reuse=192",
        "missing_live=0 stale_dead=0 unwind_failures=0",
        "callback_tables=0",
        "W025JitLifecycleStressProbe PASS cycles=8",
        "jni_values=pass",
        "main end exception=0",
        "Windows x64 JIT dual-view (J-2) created: capacity=16MiB",
    )


def review_fatal(root: Path, texts: dict[str, str]) -> None:
    common = (
        "ART Win32 VEH: exception 0xc0000005",
        "ART Win32 UEF: exception 0xc0000005",
        "minidump written",
        "new_minidump=",
    )
    require(texts["fatal_static"], "fatal_static", "CrashNativeProbe.start", *common)
    require(
        texts["fatal_jit_default"],
        "fatal_jit_default",
        "CrashNativeProbe.jit_ready calls=20000",
        "Windows x64 CompileMethod done success=1 method=void CrashNativeProbe.jitCrashCaller(int)",
        "Windows x64 CompileMethod done success=1 method=void CrashNativeProbe.nativeSegfault()",
        "Windows x64 JIT dual-view (J-2) created",
        *common,
    )
    require(
        texts["fatal_osr_default"],
        "fatal_osr_default",
        "CrashNativeProbe.osr_armed count=2000000",
        "kind=Baseline",
        "kind=Osr",
        "Jumping to long CrashNativeProbe.osrCrashLoop(int)",
        "Windows x64 JIT dual-view (J-2) created",
        *common,
    )
    forbid(
        texts["fatal_osr_default"],
        "fatal_osr_default",
        "Done running OSR code for long CrashNativeProbe.osrCrashLoop(int)",
        "CrashNativeProbe.osr_unexpected_return",
        "CrashNativeProbe.unexpected_continue",
    )

    scan = read_text(root / "logs/FATAL_DMP_SCAN.txt")
    records = {
        (int(size), digest)
        for size, digest in re.findall(r"bytes=(\d+)\s+sha256=([0-9a-f]{64})", scan)
    }
    dumps = sorted(root.rglob("*.dmp"))
    if len(dumps) != 3 or len(records) != 3:
        fail(f"fatal dump count mismatch files={len(dumps)} records={len(records)}")
    for dump in dumps:
        if dump.stat().st_size <= 4096 or dump.read_bytes()[:4] != b"MDMP":
            fail(f"invalid minidump: {dump}")
        if (dump.stat().st_size, sha256(dump)) not in records:
            fail(f"minidump absent from scan: {dump}")


def review(root: Path) -> tuple[int, int]:
    texts = process_logs(root)
    review_nonfatal(texts)
    review_fatal(root, texts)
    result = read_text(root / "logs/RESULT_W025_JIT4.txt").splitlines()
    pass_count = sum(line.startswith("PASS ") for line in result)
    fail_count = sum(line.startswith("FAIL ") for line in result)
    if not result or result[-1] != "OVERALL PASS" or pass_count != 34 or fail_count != 0:
        fail(f"aggregate mismatch pass={pass_count} fail={fail_count} final={result[-1:]}")
    if any((root / "jit-temp").rglob("*")):
        fail("returned JIT temp directory is not empty")
    if list(root.rglob("*.trace")):
        fail("returned archive contains a trace")
    host = read_text(root / "logs/HOST_INFO.txt")
    match = re.search(r"^build=(\d+)$", host, re.MULTILINE)
    if match is None or int(match.group(1)) < 17134:
        fail("host build is absent or below Windows 10 RS4")
    return pass_count, fail_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--issued", type=Path, required=True)
    args = parser.parse_args()
    archive = args.archive.resolve()
    issued = args.issued.resolve()
    if not archive.is_file() or not issued.is_dir():
        fail("returned archive or issued package is missing")
    with tempfile.TemporaryDirectory(prefix="w025-jit4-review-") as directory:
        extracted = Path(directory)
        safe_extract(archive, extracted)
        returned = payload_root(extracted)
        compare_identity(returned, issued)
        pass_count, fail_count = review(returned)
    print(
        "W-025 JIT-4 native host result review: PASS "
        f"cases={len(EXPECTED_CASES)} aggregate_pass={pass_count} failures={fail_count} "
        f"fatal_dumps=3 archive_sha256={sha256(archive)}"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        print(f"W-025 JIT-4 native host result review: FAIL: {error}", file=sys.stderr)
        sys.exit(1)
