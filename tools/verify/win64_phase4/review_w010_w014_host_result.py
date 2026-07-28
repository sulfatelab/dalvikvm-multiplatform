#!/usr/bin/env python3
"""Review returned native-Windows W-010/W-014 Stage E evidence."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import sys
import tempfile
import zipfile


IDENTITY_FILES = (
    "BUILD_INFO.txt",
    "MANIFEST.json",
    "SHA256SUMS.txt",
    "W010_W014_STRUCTURAL_REPORT.txt",
)

EXPECTED_PASS_RECORDS = 30
HANDLED_FAULT_FORBIDDEN = (
    "ART Win64 VEH",
    "ART Win64 UEF",
    "minidump written",
    "unexpected_continue",
)
OSR_UNWIND_MARKERS = (
    "win32_osr_unwind_probe failures=0",
    "entry_frame_register=R12 compiled_frame_register=RBP",
    "entry_frame_offset=0 return_prologue=0 fixed_frame=248 xmm_count=10 "
    "invoke_records=2 generic_jni_records=1 generic_jni_native_return=0xc5 "
    "switch_impl_records=1 switch_impl_call_return=0xd "
    "variable_rsp_delta=256",
    "win32_osr_unwind_probe OK",
)


def fail(message: str) -> None:
    raise RuntimeError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_extract(archive: Path, output: Path) -> None:
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            target = (output / member.filename).resolve()
            if output.resolve() not in target.parents and target != output.resolve():
                fail(f"archive contains an unsafe path: {member.filename}")
        source.extractall(output)


def find_package_root(root: Path, required: str) -> Path:
    if (root / required).is_file():
        return root
    required_path = Path(required)
    candidates = sorted(
        path.parents[len(required_path.parts) - 1]
        for path in root.rglob(required_path.name)
        if path.as_posix().endswith(required_path.as_posix())
    )
    unique = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    if len(unique) != 1:
        fail(f"expected one package root containing {required}, found {len(unique)}")
    return unique[0]


def read_sums(path: Path) -> dict[str, str]:
    sums: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            fail(f"invalid SHA256SUMS line: {line!r}")
        relative = match.group(2)
        if relative.startswith("./"):
            relative = relative[2:]
        sums[Path(relative).as_posix()] = match.group(1)
    return sums


def verify_issued_payload(returned: Path, issued: Path) -> str:
    for relative in IDENTITY_FILES:
        returned_path = returned / relative
        issued_path = issued / relative
        if not returned_path.is_file():
            fail(f"returned evidence is missing identity file: {relative}")
        if not issued_path.is_file():
            fail(f"issued package is missing identity file: {relative}")
        if returned_path.read_bytes() != issued_path.read_bytes():
            fail(f"returned {relative} does not match the issued package")

    issued_sums = read_sums(issued / "SHA256SUMS.txt")
    payload_paths = [relative for relative in issued_sums if relative not in IDENTITY_FILES]
    returned_payload = [relative for relative in payload_paths if (returned / relative).is_file()]
    if not returned_payload:
        return "evidence-only"
    if len(returned_payload) != len(payload_paths):
        missing = sorted(set(payload_paths) - set(returned_payload))
        fail(f"returned package has a partial issued payload; missing: {missing}")
    for relative, expected in issued_sums.items():
        path = returned / relative
        if not path.is_file():
            fail(f"returned package is missing issued file: {relative}")
        if sha256(path) != expected:
            fail(f"returned package changed issued file: {relative}")
    return "full-package"


def require_markers(path: Path, markers: tuple[str, ...], forbidden: tuple[str, ...] = ()) -> str:
    if not path.is_file():
        fail(f"required evidence file is missing: {path.relative_to(path.parents[1])}")
    text = path.read_text(encoding="utf-8", errors="replace")
    for marker in markers:
        if marker not in text:
            fail(f"{path.name} is missing marker: {marker}")
    for marker in forbidden:
        if marker in text:
            fail(f"{path.name} contains forbidden marker: {marker}")
    return text


def require_exit(log_text: str, *, nonzero: bool) -> None:
    match = re.search(r"^exit=(-?\d+)\s*$", log_text, re.MULTILINE)
    if match is None:
        fail("process log does not contain an exit code")
    exit_code = int(match.group(1))
    if nonzero and exit_code == 0:
        fail("process log unexpectedly reports exit=0")
    if not nonzero and exit_code != 0:
        fail(f"process log reports nonzero exit={exit_code}")
    if "timed_out=False" not in log_text:
        fail("process log does not prove timed_out=False")


def review_osr_log(logs: Path) -> None:
    osr_text = require_markers(
        logs / "osr_unwind.log",
        OSR_UNWIND_MARKERS,
        HANDLED_FAULT_FORBIDDEN,
    )
    require_exit(osr_text, nonzero=False)


def review_xmm_log(logs: Path, name: str, mode: str) -> None:
    markers = [
        f"W003XmmSentinelProbe mode={mode}",
        "mask=0 selfTestMask=63 iterations=128",
        "fullSelfTestMask=1023",
        "W003XmmSentinelProbe OK",
        "main end exception=0",
    ]
    forbidden = list(HANDLED_FAULT_FORBIDDEN)
    if mode == "jit":
        markers.append("success=1 method=int W003XmmSentinelProbe.managedCallback(")
    else:
        forbidden.append("Win64 CompileMethod done success=1 method=")
    text = require_markers(logs / f"{name}.log", tuple(markers), tuple(forbidden))
    require_exit(text, nonzero=False)


def review(returned: Path, issued: Path) -> None:
    return_form = verify_issued_payload(returned, issued)
    logs = returned / "logs"
    if not logs.is_dir():
        fail("returned package has no logs directory")

    result_path = logs / "RESULT_W010_W014.txt"
    if not result_path.is_file():
        fail("RESULT_W010_W014.txt is missing")
    result_lines = result_path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not result_lines or result_lines[-1] != "OVERALL PASS":
        fail("RESULT_W010_W014.txt does not end with OVERALL PASS")
    if any(line.startswith("FAIL ") or line == "OVERALL FAIL" for line in result_lines):
        fail("RESULT_W010_W014.txt contains a failure record")

    required_result_prefixes = (
        "PASS host_os build=",
        "PASS package_integrity",
        "PASS structural_report",
        "PASS cet_policy exit=0 ",
        "PASS hsp_policy",
        "PASS osr_unwind exit=0 ",
        "PASS xmm_full_nterp_run01 exit=0 ",
        "PASS xmm_full_nterp_run02 exit=0 ",
        "PASS xmm_full_switch_run01 exit=0 ",
        "PASS xmm_full_switch_run02 exit=0 ",
        "PASS xmm_full_jit_run01 exit=0 ",
        "PASS xmm_full_jit_run02 exit=0 ",
        "PASS thread_stack exit=0 ",
        "PASS stack_page exit=0 ",
        "PASS fault_record exit=0 ",
        "PASS sigchain exit=0 ",
        "PASS no_sig_chain_rejection exit=",
        "PASS switch_so exit=0 ",
        "PASS nterp_npe exit=0 ",
        "PASS nterp_so exit=0 ",
        "PASS jit_npe exit=0 ",
        "PASS jit_so exit=0 ",
        "PASS handled_log_scan",
        "PASS handled_dump_scan NO_HANDLED_DMP_FILES",
        "PASS crashnative exit=",
        "PASS jit_fatal_j2 exit=",
        "PASS jit_fatal_j1 exit=",
        "PASS osr_fatal_j2 exit=",
        "PASS osr_fatal_j1 exit=",
        "PASS fatal_dump_scan count=",
    )
    for prefix in required_result_prefixes:
        if not any(line.startswith(prefix) for line in result_lines):
            fail(f"RESULT_W010_W014.txt is missing result: {prefix}")
    pass_lines = [line for line in result_lines if line.startswith("PASS ")]
    if len(pass_lines) != EXPECTED_PASS_RECORDS:
        fail(
            f"expected {EXPECTED_PASS_RECORDS} PASS records, "
            f"found {len(pass_lines)}"
        )

    version_text = require_markers(
        logs / "WINDOWS_VERSION.txt", ("BuildNumber", "OSArchitecture")
    )
    build_match = re.search(r"BuildNumber\s*:\s*(\d+)", version_text)
    if build_match is None or int(build_match.group(1)) < 17134:
        fail("native result does not prove Windows 10 RS4 build 17134 or later")
    windows_build = int(build_match.group(1))

    copied_report = logs / "W010_W014_STRUCTURAL_REPORT.txt"
    if not copied_report.is_file():
        fail("returned logs do not contain W010_W014_STRUCTURAL_REPORT.txt")
    if copied_report.read_bytes() != (issued / "W010_W014_STRUCTURAL_REPORT.txt").read_bytes():
        fail("returned structural report does not match the issued report")

    cet_text = require_markers(logs / "cet_policy.log", ("WIN32_CET_POLICY_PROBE PASS",))
    require_exit(cet_text, nonzero=False)
    if windows_build >= 19041:
        if "actual=disabled" not in cet_text:
            fail("Windows build 19041+ did not prove disabled user shadow stacks")
        if "known_incompatible=0x00000000" not in cet_text:
            fail("Windows build 19041+ reported an incompatible named shadow-stack policy field")
    elif not any(
        marker in cet_text
        for marker in ("actual=disabled", "actual=unavailable-on-older-windows")
    ):
        fail("older Windows did not report a disabled or unavailable shadow-stack policy")

    common_handled_forbidden = HANDLED_FAULT_FORBIDDEN
    review_osr_log(logs)
    for mode in ("nterp", "switch", "jit"):
        for repeat in (1, 2):
            review_xmm_log(logs, f"xmm_full_{mode}_run{repeat:02d}", mode)
    thread_text = require_markers(
        logs / "thread_stack.log",
        (
            "requested=65536 actual=65536",
            "requested=262144 actual=262144",
            "requested=1048576",
            "requested=2097152",
            "requested=9437184",
            "join_stress count=512",
            "detach_stress count=128",
            "win32_thread_stack_probe failures=0 join_stress=512 detach_stress=128",
            "runtime=native reservation_rounding=request wine_default_clamps=0",
            "win32_thread_stack_probe OK",
        ),
        common_handled_forbidden,
    )
    require_exit(thread_text, nonzero=False)
    stack_page_text = require_markers(
        logs / "stack_page.log",
        (
            "selection_cases count=8",
            "reserved_case size=1048576 iterations=64",
            "win32_stack_page_probe failures=0 committed_restore_iterations=64 reserved_restore_iterations=64 faults=258",
            "win32_stack_page_probe OK",
        ),
        common_handled_forbidden,
    )
    require_exit(stack_page_text, nonzero=False)
    fault_record_text = require_markers(
        logs / "fault_record.log",
        ("win32_fault_record_probe failures=0 cases=8", "win32_fault_record_probe OK"),
        common_handled_forbidden,
    )
    require_exit(fault_record_text, nonzero=False)
    sigchain_text = require_markers(
        logs / "sigchain.log",
        (
            "win32_sigchain_probe calls=2 first=0 second=0",
            "action_calls=3 foreign_before=2 foreign_after=2",
            "frame_with_action=1 frame_after_remove=1 sequence=1,2,1,2",
            "win32_sigchain_probe OK",
        ),
        common_handled_forbidden,
    )
    require_exit(sigchain_text, nonzero=False)

    no_chain_text = require_markers(
        logs / "no_sig_chain_rejection.log",
        ("A started runtime should have sig chain enabled",),
        ("W010ManagedFaultProbe OK",),
    )
    require_exit(no_chain_text, nonzero=True)

    managed_cases = {
        "switch_so": (
            "W010ManagedFaultProbe SO OK main=2 child=2 recovery=4 gc=4",
            "W010ManagedFaultProbe OK mode=so",
            "main end exception=0",
        ),
        "nterp_npe": (
            "W010ManagedFaultProbe NPE OK read=64 write=64 recovery=128 gc=16",
            "W010ManagedFaultProbe OK mode=npe",
            "main end exception=0",
        ),
        "nterp_so": (
            "W010ManagedFaultProbe SO OK main=2 child=2 recovery=4 gc=4",
            "W010ManagedFaultProbe OK mode=so",
            "main end exception=0",
        ),
        "jit_npe": (
            "W010ManagedFaultProbe NPE OK read=64 write=64 recovery=128 gc=16",
            "Win64 CompileMethod done success=1 method=void W010ManagedFaultProbe.runNullChecks()",
            "W010ManagedFaultProbe OK mode=npe",
            "main end exception=0",
        ),
        "jit_so": (
            "W010ManagedFaultProbe SO OK main=2 child=2 recovery=4 gc=4",
            "Win64 CompileMethod done success=1 method=int W010ManagedFaultProbe.recurse(int)",
            "Win64 CompileMethod done success=1 method=int W010ManagedFaultProbe.runStackOverflowRounds()",
            "W010ManagedFaultProbe OK mode=so",
            "main end exception=0",
        ),
    }
    for name, markers in managed_cases.items():
        forbidden = common_handled_forbidden
        if name in {"switch_so", "nterp_npe", "nterp_so"}:
            forbidden = (*forbidden, "Win64 CompileMethod done success=1 method=")
        text = require_markers(logs / f"{name}.log", markers, forbidden)
        require_exit(text, nonzero=False)

    require_markers(logs / "HANDLED_DMP_SCAN.txt", ("NO_HANDLED_DMP_FILES",))
    fatal_text = require_markers(
        logs / "crashnative.log",
        (
            "CrashNativeProbe.start",
            "ART Win64 VEH: exception 0xc0000005",
            "ART Win64 UEF: exception 0xc0000005",
            "minidump written",
            "new_minidump=",
        ),
        ("CrashNativeProbe.unexpected_continue",),
    )
    require_exit(fatal_text, nonzero=True)

    for mode in ("j2", "j1"):
        jit_markers = (
            "CrashNativeProbe.jit_ready calls=20000",
            "Win64 CompileMethod done success=1 method=void CrashNativeProbe.jitCrashCaller(int)",
            "Win64 CompileMethod done success=1 method=void CrashNativeProbe.nativeSegfault()",
            "ART Win64 VEH: exception 0xc0000005",
            "ART Win64 UEF: exception 0xc0000005",
            "minidump written",
            "new_minidump=",
        )
        jit_forbidden = ("CrashNativeProbe.unexpected_continue",)
        if mode == "j2":
            jit_markers = (*jit_markers, "Win64 JIT dual-view (J-2) created")
        else:
            jit_forbidden = (*jit_forbidden, "Win64 JIT dual-view (J-2) created")
        text = require_markers(
            logs / f"jit_fatal_{mode}.log", jit_markers, jit_forbidden
        )
        require_exit(text, nonzero=True)

        osr_markers = (
            "CrashNativeProbe.osr_armed count=2000000",
            "warmup_threshold=100, optimize_threshold=100",
            "kind=Baseline",
            "kind=Osr",
            "Win64 CompileMethod done success=1 method=long CrashNativeProbe.osrCrashLoop(int)",
            "Jumping to long CrashNativeProbe.osrCrashLoop(int)",
            "ART Win64 VEH: exception 0xc0000005",
            "ART Win64 UEF: exception 0xc0000005",
            "minidump written",
            "new_minidump=",
        )
        osr_forbidden = (
            "Done running OSR code for long CrashNativeProbe.osrCrashLoop(int)",
            "CrashNativeProbe.osr_unexpected_return",
            "CrashNativeProbe.unexpected_continue",
        )
        if mode == "j2":
            osr_markers = (*osr_markers, "Win64 JIT dual-view (J-2) created")
        else:
            osr_forbidden = (*osr_forbidden, "Win64 JIT dual-view (J-2) created")
        text = require_markers(
            logs / f"osr_fatal_{mode}.log", osr_markers, osr_forbidden
        )
        require_exit(text, nonzero=True)

    scan_text = require_markers(logs / "FATAL_DMP_SCAN.txt", ("path=", "bytes=", "sha256="))
    scan_records: list[tuple[int, str]] = []
    for line in scan_text.splitlines():
        match = re.search(r"bytes=(\d+)\s+sha256=([0-9a-f]{64})", line)
        if match:
            scan_records.append((int(match.group(1)), match.group(2)))
    if len(scan_records) < 5:
        fail("FATAL_DMP_SCAN.txt contains fewer than five dump records")

    dumps = sorted(returned.rglob("*.dmp"))
    if len(dumps) < 5:
        fail("returned evidence contains fewer than five fatal minidumps")
    for dump in dumps:
        if dump.stat().st_size < 4096 or dump.read_bytes()[:4] != b"MDMP":
            fail(f"returned dump is not a valid minidump: {dump}")
        record = (dump.stat().st_size, sha256(dump))
        if record not in scan_records:
            fail(f"returned minidump is absent from FATAL_DMP_SCAN.txt: {dump}")

    print(
        "W-010/W-014 native Stage E result: PASS "
        f"(build={windows_build}, pass_records={EXPECTED_PASS_RECORDS}, "
        f"dumps={len(dumps)}, return={return_form})"
    )


def materialize(path: Path, temporary: Path, required: str, label: str) -> Path:
    if path.is_dir():
        return find_package_root(path.resolve(), required)
    if not path.is_file() or not zipfile.is_zipfile(path):
        fail(f"not a package directory or ZIP archive: {path}")
    output = temporary / label
    output.mkdir()
    safe_extract(path, output)
    return find_package_root(output, required)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("returned", type=Path)
    parser.add_argument("--issued", required=True, type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="w010-w014-review-") as temp:
        temporary = Path(temp)
        returned = materialize(
            args.returned, temporary, "logs/RESULT_W010_W014.txt", "returned"
        )
        issued = materialize(args.issued, temporary, "SHA256SUMS.txt", "issued")
        review(returned, issued)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as error:
        print(f"W-010/W-014 native Stage E result: FAIL: {error}", file=sys.stderr)
        sys.exit(1)
