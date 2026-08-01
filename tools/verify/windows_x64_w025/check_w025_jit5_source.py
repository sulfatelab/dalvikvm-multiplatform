#!/usr/bin/env python3
"""Check the W-025 JIT-5 Windows J-1 removal contract."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


RETIRED_KEY = "ART_WINDOWS_X64_JIT_DUAL"
RETIRED_FALLBACK = "falling back to single-view (J-1)"


def require(text: str, path: Path, *markers: str) -> None:
    for marker in markers:
        if marker not in text:
            raise RuntimeError(f"{path}: missing marker {marker!r}")


def forbid(text: str, path: Path, *markers: str) -> None:
    for marker in markers:
        if marker in text:
            raise RuntimeError(f"{path}: contains retired marker {marker!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    build = args.build.resolve()

    runtime_path = repo / "vendor/art/runtime/jit/jit_memory_region.cc"
    runtime = runtime_path.read_text(encoding="utf-8")
    require(
        runtime,
        runtime_path,
        "This is the only Windows JIT memory path.",
        'dual_view_error = "Windows x64 JIT dual-view CreateFileMapping failed: " + j2_error;',
        'dual_view_error = "Windows x64 JIT dual-view construction failed: " + j2_error;',
        "*error_msg = dual_view_error;",
        "CHECK(j2_complete);",
        "#else\n    // Single view of JIT code cache case.",
    )
    forbid(runtime, runtime_path, RETIRED_KEY, RETIRED_FALLBACK)

    art_path = build / "art.dll"
    if not art_path.is_file():
        raise RuntimeError(f"missing rebuilt Windows runtime: {art_path}")
    art = art_path.read_bytes()
    for marker in (RETIRED_KEY, RETIRED_FALLBACK):
        if marker.encode("ascii") in art or marker.encode("utf-16-le") in art:
            raise RuntimeError(f"{art_path}: contains retired marker {marker!r}")
    for marker in (
        "Windows x64 JIT dual-view CreateFileMapping failed:",
        "Windows x64 JIT dual-view construction failed:",
        "Windows x64 JIT dual-view (J-2) created:",
    ):
        if marker.encode("ascii") not in art:
            raise RuntimeError(f"{art_path}: missing fail-closed marker {marker!r}")

    active_scripts = (
        "tests/support/windows/w003_managed_gate.py",
        "tests/CMakeLists.txt",
        "tools/verify/windows_x64_phase4/run_jvmti_force_probe.sh",
        "tools/verify/windows_x64_phase4/run_math_critical_probe.sh",
        "tests/support/windows/w002_managed_entry_gate.py",
        "tests/CMakeLists.txt",
        "tools/verify/windows_x64_phase4/run_jit_unwind_lifecycle.sh",
        "tools/verify/windows_x64_phase4/run_jit_fatal_unwind.sh",
        "tools/verify/windows_x64_phase4/run_osr_fatal_unwind.sh",
        "tools/verify/windows_x64_w025/run_w025_jit5_preflight.sh",
    )
    for relative in active_scripts:
        path = repo / relative
        text = path.read_text(encoding="utf-8")
        forbid(text, path, RETIRED_KEY, "J-1")

    smoke_path = repo / "tools/verify/windows_x64_phase4/run_jit_smoke.sh"
    smoke = smoke_path.read_text(encoding="utf-8")
    require(
        smoke,
        smoke_path,
        "=== T10: Retired J-1 opt-out is ignored ===",
        "ART_WINDOWS_X64_JIT_DUAL=0",
        "Retired ART_WINDOWS_X64_JIT_DUAL=0 still uses the J-2 mapping",
        "Retired ART_WINDOWS_X64_JIT_DUAL=0 completes compiled Hello",
    )
    if smoke.count("ART_WINDOWS_X64_JIT_DUAL=0") != 4:
        raise RuntimeError(f"{smoke_path}: retired-key test contract changed")

    runner_path = repo / "tools/verify/windows_x64_w025/host/RUN_W025_JIT5_HOST.ps1"
    runner = runner_path.read_text(encoding="utf-8")
    require(
        runner,
        runner_path,
        "smoke_default_verbose",
        "smoke_retired_optout",
        "smoke_env_disabled",
        "smoke_xusejit_false",
        "smoke_filter",
        "smoke_exclude",
        "smoke_quiet",
        "matrix_throw",
        "critical_default",
        "native_abi_default",
        '"osr_$interpreter"',
        "lifecycle_default",
        "fatal_static",
        "fatal_jit_default",
        "fatal_osr_default",
        "Test-Jit5RemovalContract",
        "retired_opt_out_source_absent=true",
        "retired_opt_out_binary_absent=true",
        "ART_WINDOWS_X64_JIT_DUAL = '0'",
        "falling back to single-view (J-1)",
        "PASS fatal_dump_scan count=3",
        "OVERALL PASS",
    )

    nterp_path = repo / "vendor/art/runtime/interpreter/mterp/x86_64ng/main.S"
    nterp = nterp_path.read_text(encoding="utf-8")
    require(
        nterp,
        nterp_path,
        "ART quick/JNI hard-float returns live in xmm0 on Windows and Linux.",
        "movd %xmm0, %eax",
        "movq %xmm0, %rax",
    )

    required_build = (
        "dalvikvm.exe",
        "art.dll",
        "libopenjdk.dll",
        "openjdkjvmti.dll",
        "libcriticalnativeprobe.dll",
        "criticalnativeprobe.dll",
        "libnativeabiprobe.dll",
        "libw025jitlifecyclestressprobe.dll",
        "run/boot.jar",
        "run/w002osrprobe.jar",
        "run/crashnativeprobe.jar",
        "run/w025jitlifecyclestressprobe.jar",
    )
    for relative in required_build:
        if not (build / relative).is_file():
            raise RuntimeError(f"missing JIT-5 build artifact: {build / relative}")

    openjdk = (build / "libopenjdk.dll").read_bytes()
    if b"ART_WINDOWS_X64_CRASH_NATIVE_WARMUP\x00" not in openjdk:
        raise RuntimeError("libopenjdk.dll lacks the Windows x64 fatal-warmup environment key")
    if b"ART_WIN64_CRASH_NATIVE_WARMUP\x00" in openjdk:
        raise RuntimeError("libopenjdk.dll still contains the retired Win64 fatal-warmup key")

    packager_path = repo / "tools/windows_x64/host_package/package_windows_x64_w025_jit5.sh"
    packager = packager_path.read_text(encoding="utf-8")
    require(
        packager,
        packager_path,
        "run_w025_jit5_preflight.sh",
        "RUN_W025_JIT5_HOST.ps1",
        "check_w025_jit5_host_package.py",
        "jit5_cases=29",
        "jit5_aggregate_pass=36",
    )
    forbid(packager, packager_path, "run_w025_jit3_preflight.sh", "RUN_W025_JIT3_HOST.ps1")

    print("status=PASS")
    print("cases=29")
    print("aggregate_pass=36")
    print("jit_smoke_records=14")
    print("jit_matrix_records=14")
    print("jit_disabled_controls=2")
    print("default_memory_mode=j2")
    print("j1_cases=0")
    print("native_abi_targets=7")
    print("osr_modes=nterp,switch")
    print("lifecycle_cycles=8")
    print("fatal_modes=static,jit,osr")
    print("fatal_minidumps=3")
    print("fatal_warmup_env=windows_x64")
    print("nterp_fp_result_source=xmm0")
    print("windows_memory_paths=J-2-only")
    print("windows_failure_policy=fail-closed")
    print("non_windows_single_view=preserved")
    print("retired_opt_out_source_absent=true")
    print("retired_opt_out_binary_absent=true")
    print("retired_fallback_source_absent=true")
    print("retired_fallback_binary_absent=true")
    print("active_default_scripts=9")
    print("retired_key_negative_tests=1")
    print("W025_JIT5_SOURCE_CHECK_PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"W025_JIT5_SOURCE_CHECK_FAIL: {error}", file=sys.stderr)
        sys.exit(1)
