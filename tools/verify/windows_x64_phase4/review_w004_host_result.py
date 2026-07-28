#!/usr/bin/env python3
"""Independently review a returned W-004 native-Windows result archive."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
import zipfile


EXPECTED_CASES = {
    "nterp_xint",
    "jit_dual",
    "float_threshold0_dual",
    "critical_dual",
    "critical_j1",
    "native_abi_dual",
    "native_abi_j1",
    "jvmti_dual",
    "jvmti_j1",
    "gcstress",
    "threadheavy",
    "handleleak",
    *(f"repeat_hello_{index:02d}" for index in range(1, 11)),
}

BAD_PATTERNS = (
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


def require(texts: dict[str, str], case: str, *markers: str) -> None:
    for marker in markers:
        if marker not in texts[case]:
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
                fail(f"symbolic links are not accepted in returned evidence: {info.filename}")
        source.extractall(destination)


def compare_identity(returned: Path, issued: Path) -> None:
    for name in ("BUILD_INFO.txt", "MANIFEST.json", "SHA256SUMS.txt"):
        returned_path = returned / name
        issued_path = issued / name
        if not returned_path.is_file():
            fail(f"returned metadata is missing: {name}")
        if returned_path.read_bytes() != issued_path.read_bytes():
            fail(f"returned metadata differs from issued package: {name}")
    returned_report = returned / "logs/W004_STRUCTURAL_REPORT.txt"
    issued_report = issued / "W004_STRUCTURAL_REPORT.txt"
    if not returned_report.is_file():
        fail("returned structural report is missing")
    if returned_report.read_bytes() != issued_report.read_bytes():
        fail("returned structural report differs from issued package")


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
        missing = sorted(EXPECTED_CASES - set(combined))
        extra = sorted(set(combined) - EXPECTED_CASES)
        fail(f"child case set mismatch: missing={missing} extra={extra}")

    texts: dict[str, str] = {}
    for name, path in sorted(combined.items()):
        text = read_text(path)
        texts[name] = text
        for marker in (f"name={name}", "exit=0", "expected_exit=0", "timed_out=False"):
            if marker not in text:
                fail(f"{name}: missing process metadata {marker!r}")
        lowered = text.lower()
        for pattern in BAD_PATTERNS:
            if pattern.lower() in lowered:
                fail(f"{name}: forbidden log pattern {pattern!r}")
        for suffix, section in (("stdout", "--- stdout ---"), ("stderr", "--- stderr ---")):
            child = logs / f"{name}.{suffix}.log"
            if not child.is_file():
                fail(f"{name}: missing {suffix} log")
            if section not in text:
                fail(f"{name}: combined log is missing {section}")
            child_text = read_text(child).strip()
            if child_text and child_text not in text:
                fail(f"{name}: combined log does not contain its {suffix} log")

    require(texts, "nterp_xint", "Hello from dalvikvm!", "main end exception=0")
    require(
        texts,
        "jit_dual",
        "JitCodeCache::Create OK",
        "Windows x64 CompileMethod done success=1 method=java.lang.StringBuilder",
        "Hello from dalvikvm!",
        "main end exception=0",
    )
    require(texts, "float_threshold0_dual", "FloatProbe OK", "main end exception=0")

    critical_values = (
        "CriticalNativeProbe values longs=190 doubles=91.0 mixed=159.5 "
        "mixed32=87 floatReturn=15.25 calls=63 branchSeen=true"
    )
    dlsym_post = (
        "CriticalNativeDlsymProbe postTracing values longs=190 doubles=91.0 "
        "mixed=159.5 mixed32=87 floatReturn=15.25 calls=63 branchSeen=true"
    )
    for case in ("critical_dual", "critical_j1"):
        require(
            texts,
            case,
            critical_values,
            dlsym_post,
            "CriticalNativeProbe instrumentation OK",
            "CriticalNativeDlsymProbe postTracing OK",
            "main end exception=0",
        )
        if not re.search(
            r"CriticalNativeProbe tracingMode before=0 during=[1-9][0-9]* "
            r"after=0 traceFileDeleted=true",
            texts[case],
        ):
            fail(f"{case}: tracing transition marker mismatch")

    native_methods = (
        "double FastNativeAbiProbe.normalRegistered(",
        "double FastNativeAbiProbe.fastRegistered(",
        "double FastNativeAbiProbe.normalDlsym(",
        "double FastNativeAbiProbe.fastDlsym(",
        "double FastNativeAbiProbe.normalInstance(",
        "double FastNativeAbiProbe.fastInstance(",
        "int FastNativeAbiProbe.callMask(",
    )
    for case in ("native_abi_dual", "native_abi_j1"):
        require(texts, case, "FastNativeAbiProbe OK", "main end exception=0")
        if not re.search(
            r"FastNativeAbiProbe tracingMode before=0 during=[1-9][0-9]* "
            r"after=0 traceFileDeleted=true",
            texts[case],
        ):
            fail(f"{case}: tracing transition marker mismatch")
        for method in native_methods:
            count = texts[case].count("success=1 method=" + method)
            if count != 1:
                fail(f"{case}: compile count {count}, expected 1 for {method}")

    jvmti_values = (
        "normalRegistered=137.75 fastRegistered=237.75 "
        "criticalRegistered=337.75 normalDlsym=437.75 "
        "fastDlsym=537.75 criticalDlsym=637.75"
    )
    for case in ("jvmti_dual", "jvmti_j1"):
        for phase in ("before", "during", "after"):
            require(texts, case, f"JvmtiForceProbe {phase} {jvmti_values}")
        require(texts, case, "JvmtiForceProbe OK", "main end exception=0")
        if not re.search(
            r"JvmtiForceProbe steps before=0 during=[1-9][0-9]* "
            r"disabled=[1-9][0-9]* final=[1-9][0-9]*",
            texts[case],
        ):
            fail(f"{case}: single-step transition marker mismatch")
        for method in (
            "double JvmtiForceProbe.normalRegistered(",
            "double JvmtiForceProbe.fastRegistered(",
        ):
            count = texts[case].count("success=1 method=" + method)
            if count != 1:
                fail(f"{case}: compile count {count}, expected 1 for {method}")
        for method in ("criticalRegistered(", "criticalDlsym("):
            if "success=1 method=double JvmtiForceProbe." + method in texts[case]:
                fail(f"{case}: CriticalNative unexpectedly compiled: {method}")

    require(texts, "gcstress", "gcstress.ok=true", "GcStressProbe.done=ok")
    require(texts, "threadheavy", "threadheavy.ok=true", "ThreadHeavyProbe.done=ok")
    require(texts, "handleleak", "handleleak.ok=true", "HandleLeakProbe.done=ok")
    for index in range(1, 11):
        require(
            texts,
            f"repeat_hello_{index:02d}",
            "Hello from dalvikvm!",
            "main end exception=0",
        )

    result = read_text(logs / "RESULT_W004.txt").splitlines()
    pass_count = sum(line.startswith("PASS ") for line in result)
    fail_count = sum(line.startswith("FAIL ") for line in result)
    if not result or result[-1] != "OVERALL PASS":
        fail("aggregate result does not end in OVERALL PASS")
    if pass_count != 28 or fail_count != 0:
        fail(f"aggregate count mismatch: pass={pass_count} fail={fail_count}")
    if read_text(logs / "DMP_SCAN.txt").strip() != "NO_DMP_FILES":
        fail("dump scan is not NO_DMP_FILES")
    if list(root.rglob("*.dmp")):
        fail("returned archive contains crash dumps")
    if list(root.rglob("*.trace")):
        fail("returned archive contains trace files")
    return pass_count, fail_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument(
        "--issued",
        type=Path,
        required=True,
        help="issued package directory retained on the Linux build host",
    )
    args = parser.parse_args()
    archive = args.archive.resolve()
    issued = args.issued.resolve()
    if not archive.is_file():
        fail(f"returned archive does not exist: {archive}")
    if not issued.is_dir():
        fail(f"issued package directory does not exist: {issued}")

    with tempfile.TemporaryDirectory(prefix="w004-host-review-") as directory:
        returned = Path(directory)
        safe_extract(archive, returned)
        compare_identity(returned, issued)
        pass_count, fail_count = review_logs(returned)

    print(
        "W-004 native host result review: PASS "
        f"cases={len(EXPECTED_CASES)} aggregate_pass={pass_count} "
        f"failures={fail_count} archive_sha256={sha256(archive)}"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as error:
        print(f"W-004 native host result review: FAIL: {error}", file=sys.stderr)
        sys.exit(1)
