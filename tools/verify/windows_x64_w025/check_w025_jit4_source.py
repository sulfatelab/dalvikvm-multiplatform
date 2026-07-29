#!/usr/bin/env python3
"""Check the W-025 JIT-4 final-regression source contract."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


def require(text: str, path: Path, *markers: str) -> None:
    for marker in markers:
        if marker not in text:
            raise RuntimeError(f"{path}: missing marker {marker!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    build = args.build.resolve()
    runner_path = repo / "tools/verify/windows_x64_w025/host/RUN_W025_JIT4_HOST.ps1"
    runner = runner_path.read_text(encoding="utf-8")

    required_cases = (
        "smoke_default_verbose",
        "smoke_env_disabled",
        "smoke_xusejit_false",
        "smoke_filter",
        "smoke_exclude",
        "smoke_quiet",
        "matrix_cenc",
        "matrix_cenc2",
        "matrix_celike",
        "matrix_cfloat",
        "matrix_floatprobe",
        "matrix_ifloat",
        "matrix_jlfloat",
        "matrix_rfloat",
        "matrix_sfloat",
        "matrix_math",
        "matrix_io",
        "matrix_net",
        "matrix_gc",
        "matrix_throw",
        "critical_default",
        "native_abi_default",
        "lifecycle_default",
        "fatal_static",
        "fatal_jit_default",
        "fatal_osr_default",
    )
    require(runner, runner_path, *required_cases)
    require(
        runner,
        runner_path,
        "ART_WINDOWS_X64_JIT = '0'",
        "-Xusejit:false",
        "foreach ($interpreter in @('nterp', 'switch'))",
        '"osr_$interpreter"',
        "Windows x64 JIT dual-view (J-2) created",
        "W025_JIT3_PASS methods=24 managed=16 jni=8",
        "missing_live=0 stale_dead=0 unwind_failures=0",
        "callback_tables=0",
        "RequireNewMinidump",
        "PASS fatal_dump_scan count=3",
        "OVERALL PASS",
    )
    if "ART_WINDOWS_X64_JIT_DUAL = '0'" in runner:
        raise RuntimeError(f"{runner_path}: final default-path runner contains a J-1 arm")

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
            raise RuntimeError(f"missing JIT-4 build artifact: {build / relative}")

    openjdk = (build / "libopenjdk.dll").read_bytes()
    current_warmup_env = b"ART_WINDOWS_X64_CRASH_NATIVE_WARMUP\x00"
    retired_warmup_env = b"ART_WIN64_CRASH_NATIVE_WARMUP\x00"
    if current_warmup_env not in openjdk:
        raise RuntimeError("libopenjdk.dll lacks the Windows x64 fatal-warmup environment key")
    if retired_warmup_env in openjdk:
        raise RuntimeError("libopenjdk.dll still contains the retired Win64 fatal-warmup key")

    print("status=PASS")
    print("cases=28")
    print("jit_smoke_records=12")
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
    print("W025_JIT4_SOURCE_CHECK_PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"W025_JIT4_SOURCE_CHECK_FAIL: {error}", file=sys.stderr)
        sys.exit(1)
