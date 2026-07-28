#!/usr/bin/env python3
"""Validate the focused W-010/W-014 native-Windows Stage E package."""

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


def parse_report(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    required = {
        "status": "PASS",
        "windows_minimum_build": "17134",
        "requested_stack_sizes": "0,65536,262144,1048576,2097152,9437184",
        "sigchain_action_calls": "3",
        "sigchain_foreign_before_calls": "2",
        "sigchain_foreign_after_calls": "2",
        "sigchain_sequence": "1,2,1,2",
        "managed_npe_read_rounds": "64",
        "managed_npe_write_rounds": "64",
        "managed_so_main_rounds": "2",
        "managed_so_child_rounds": "2",
        "xmm_boundary_registers": "10",
        "xmm_self_test_mask": "1023",
        "fatal_dispatch_modes": "static,jit-j2,jit-j1,osr-j2,osr-j1",
        "diagnostic_fatal_modes": "jni-av,jni-raise,native-worker",
        "fatal_unwind_trace": "bounded-32-live-veh",
        "fatal_minidumps_required": "5",
        "host_llvm_tools_required": "no",
        "stack_overflow_delivery": "explicit-rsp-below-guarantee-aware-thread-stack-end",
        "win32_implicit_so_checks": "false",
        "windows_stack_mapping_ownership": "os",
        "windows_stack_guarantee": "minimum-four-pages-preserve-larger-query-actual",
        "windows_excluded_low": "sum-memory-prefix-guarantee-moving-guard",
        "art_stack_overflow_reserve": "8192",
        "linux_stack_probe_contract": "implicit-rsp-minus-8192",
    }
    for key, expected in required.items():
        if values.get(key) != expected:
            fail(f"structural report has {key}={values.get(key)!r}, expected {expected!r}")
    if not values.get("cet_contract", "").startswith("WIN32_CET_CONTRACT PASS "):
        fail("structural report does not contain the CET contract PASS marker")
    if not values.get("boundary_unwind", "").startswith(
        "win32_boundary_unwind OK "
    ):
        fail("structural report does not contain the boundary unwind PASS marker")
    if values.get("explicit_stack_checks") != (
        "Windows x64 explicit stack-check contract: PASS (Windows x64 object, Linux object)"
    ):
        fail(
            "structural report does not contain the cross-target explicit "
            "stack-check PASS marker"
        )
    if not re.fullmatch(
        r"win32_osr_unwind_probe failures=0 prologue=\d+ "
        r"entry_frame_register=R12 compiled_frame_register=RBP "
        r"entry_frame_offset=0 return_prologue=0 fixed_frame=248 "
        r"xmm_count=10 invoke_records=2 generic_jni_records=1 "
        r"generic_jni_native_return=0xc5 switch_impl_records=1 "
        r"switch_impl_call_return=0xd interpreter_bridge_records=2 "
        r"interpreter_bridge_call_return=0x82 interpreter_bridge_pending=0x140 "
        r"interpreter_bridge_frame=200 interpreter_bridge_pending_frame=88 "
        r"variable_rsp_delta=256",
        values.get("osr_unwind", ""),
    ):
        fail("structural report does not contain the OSR unwind PASS marker")
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
        and path.suffix.lower() != ".dmp"
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
        missing = sorted(sum_paths - set(sums))
        extra = sorted(set(sums) - sum_paths)
        fail(f"SHA256SUMS.txt path mismatch: missing={missing} extra={extra}")
    for relative, expected in sums.items():
        if sha256(root / relative) != expected:
            fail(f"SHA256SUMS mismatch: {relative}")


def check_package(root: Path) -> None:
    required_files = [
        "dalvikvm.exe",
        "art.dll",
        "sigchain.dll",
        "win32_cet_policy_probe.exe",
        "win32_thread_stack_probe.exe",
        "win32_stack_page_probe.exe",
        "win32_stack_growth_probe.exe",
        "win32_uef_probe.exe",
        "win32_fault_record_probe.exe",
        "win32_sigchain_probe.exe",
        "win32_osr_unwind_probe.exe",
        "libw003xmmsentinel.dll",
        "run/boot.jar",
        "run/w010managedfaultprobe.jar",
        "run/w003xmmsentinelprobe.jar",
        "run/crashnativeprobe.jar",
        "run/crash/README.txt",
        "scripts/RUN_W010_W014_HOST.ps1",
        "scripts/RUN_W010_W014_DIAGNOSTICS.ps1",
        "W010_W014_HOST_CHECKLIST.md",
        "W010_W014_DIAGNOSTICS.md",
        "W010_W014_STRUCTURAL_REPORT.txt",
        "BUILD_INFO.txt",
    ]
    for relative in required_files:
        if not (root / relative).is_file():
            fail(f"required package file is missing: {relative}")

    build_info = (root / "BUILD_INFO.txt").read_text(encoding="utf-8").splitlines()
    if "stage=E9-configured-guarantee-explicit-stack-checks" not in build_info:
        fail("BUILD_INFO.txt does not identify the E9 configured-guarantee explicit-stack-check stage")

    if list(root.rglob("*.dmp")):
        fail("clean issued package unexpectedly contains a crash dump")

    report = parse_report(root / "W010_W014_STRUCTURAL_REPORT.txt")
    for relative, key in (
        ("dalvikvm.exe", "dalvikvm_sha256"),
        ("art.dll", "art_sha256"),
        ("sigchain.dll", "sigchain_sha256"),
        ("win32_osr_unwind_probe.exe", "osr_probe_sha256"),
        ("run/w010managedfaultprobe.jar", "managed_jar_sha256"),
        ("libw003xmmsentinel.dll", "xmm_probe_sha256"),
        ("run/w003xmmsentinelprobe.jar", "xmm_jar_sha256"),
    ):
        if report.get(key) != sha256(root / relative):
            fail(f"structural report hash mismatch for {relative}")

    runner = (root / "scripts/RUN_W010_W014_HOST.ps1").read_text(encoding="utf-8")
    required_runner_text = [
        "17134",
        "Test-PackageIntegrity",
        "Test-StructuralReport",
        "win32_cet_policy_probe.exe",
        "win32_osr_unwind_probe.exe",
        "entry_frame_register=R12 compiled_frame_register=RBP",
        "entry_frame_offset=0 return_prologue=0 fixed_frame=248 "
        "xmm_count=10 invoke_records=2 generic_jni_records=1 "
        "generic_jni_native_return=0xc5 switch_impl_records=1 "
        "switch_impl_call_return=0xd interpreter_bridge_records=2 "
        "interpreter_bridge_call_return=0x82 interpreter_bridge_pending=0x140 "
        "interpreter_bridge_frame=200 interpreter_bridge_pending_frame=88 "
        "variable_rsp_delta=256",
        "explicit_stack_checks=Windows x64 explicit stack-check contract: PASS",
        "stack_overflow_delivery=explicit-rsp-below-guarantee-aware-thread-stack-end",
        "win32_implicit_so_checks=false",
        "windows_stack_mapping_ownership=os",
        "windows_stack_guarantee=minimum-four-pages-preserve-larger-query-actual",
        "windows_excluded_low=sum-memory-prefix-guarantee-moving-guard",
        "art_stack_overflow_reserve=8192",
        "linux_stack_probe_contract=implicit-rsp-minus-8192",
        "actual=disabled",
        "known_incompatible=0x00000000",
        "requested=65536 actual=65536",
        "runtime=native reservation_rounding=request wine_default_clamps=0",
        "requested=9437184",
        "stack_guarantee label=main before=",
        "stack_guarantee label=pthread before=",
        "minimum=16384",
        "action_calls=3 foreign_before=2 foreign_after=2",
        "frame_with_action=1 frame_after_remove=1 sequence=1,2,1,2",
        "A started runtime should have sig chain enabled",
        "ART_WINDOWS_X64_NTERP = '0'",
        "W010ManagedFaultProbe NPE OK read=64 write=64 recovery=128 gc=16",
        "W010ManagedFaultProbe SO OK main=2 child=2 recovery=4 gc=4",
        "Windows x64 CompileMethod done success=1 method=void W010ManagedFaultProbe.runNullChecks()",
        "foreach ($mode in @('nterp', 'switch', 'jit'))",
        "xmm_full_{0}_run{1:D2}",
        "mask=0 selfTestMask=63 iterations=128",
        "fullSelfTestMask=1023",
        "success=1 method=int W003XmmSentinelProbe.managedCallback(",
        "HANDLED_DMP_SCAN.txt",
        "FATAL_DMP_SCAN.txt",
        "jit_fatal_$fatalMode",
        "osr_fatal_$fatalMode",
        "RequireNewMinidump",
        "CrashNativeProbe.osr_armed count=2000000",
        "ART Win32 UEF: exception 0xc0000005",
        "OVERALL PASS",
    ]
    for marker in required_runner_text:
        if marker not in runner:
            fail(f"host runner is missing required contract text: {marker}")
    if "llvm-readobj" in runner or "llvm-objdump" in runner:
        fail("host runner must not require LLVM inspection tools")

    checklist = (root / "W010_W014_HOST_CHECKLIST.md").read_text(encoding="utf-8")
    checklist_normalized = " ".join(checklist.split())
    for marker in (
        "Hardware-enforced Stack Protection",
        "NO_HANDLED_DMP_FILES",
        "static `-Xint` fatal JNI native AV",
        "live split OSR lookup and virtual unwind",
        "full XMM6-XMM15",
        "JIT-origin and OSR-origin fatal dispatch",
        "debugger",
        "forced-policy",
        "review_w010_w014_host_result.py",
        "explicit `RSP < Thread::stack_end_` checks",
        "test-only page-state diagnostics",
    ):
        if marker not in checklist_normalized:
            fail(f"host checklist is missing required scope text: {marker}")

    diagnostics = (root / "scripts/RUN_W010_W014_DIAGNOSTICS.ps1").read_text(
        encoding="utf-8"
    )
    for marker in (
        "win32_stack_growth_probe.exe",
        "win32_uef_probe.exe",
        "CrashNativeProbe $($mode.Argument)",
        "uef-raise",
        "uef-thread",
        "WIN32_JNI_RAISE_AV",
        "WIN32_JNI_NATIVE_WORKER enter",
        "WIN32_LATE_UEF_INSTALL",
        "ART_WINDOWS_X64_FATAL_UNWIND_TRACE",
        "ART_WINDOWS_X64_UNWIND_TRACE begin",
        "ART_WINDOWS_X64_UNWIND_TRACE end",
        "unwind_frames=",
        "DIAGNOSTICS COMPLETE",
    ):
        if marker not in diagnostics:
            fail(f"diagnostic runner is missing required text: {marker}")

    check_manifest(root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    root = args.package.resolve()
    if not root.is_dir():
        fail(f"package directory does not exist: {root}")
    check_package(root)
    print("W-010/W-014 host package check: PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"W-010/W-014 host package check: FAIL: {error}", file=sys.stderr)
        sys.exit(1)
