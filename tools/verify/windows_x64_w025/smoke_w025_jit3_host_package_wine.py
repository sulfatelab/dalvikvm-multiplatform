#!/usr/bin/env python3
"""Run the staged W-025 JIT-3 package under Wine in J-2 and J-1 modes."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


def run_case(root: Path, name: str, dual: str, cycles: int) -> None:
    env = os.environ.copy()
    for key in (
        "ART_WINDOWS_X64_JIT",
        "ART_WINDOWS_X64_JIT_DUAL",
        "ART_WINDOWS_X64_JIT_EXCLUDE",
        "ART_WINDOWS_X64_JIT_FILTER",
        "ART_WINDOWS_X64_JIT_LOG_COMPILES",
    ):
        env.pop(key, None)
    env.update(
        {
            "ANDROID_ROOT": "run",
            "ANDROID_ART_ROOT": "run",
            "ANDROID_I18N_ROOT": "run",
            "ANDROID_DATA": "run/data",
            "ICU_DATA": "run/icu",
            "WINEDEBUG": os.environ.get("WINEDEBUG", "-all"),
            "ART_WINDOWS_X64_JIT_DUAL": dual,
            "ART_WINDOWS_X64_JIT_FILTER": "W025JitLifecycleStressProbe",
        }
    )
    command = [
        "wine64",
        "./dalvikvm.exe",
        "-Xbootclasspath:run/boot.jar",
        "-Xbootclasspath-locations:run/boot.jar",
        "-Ximage:/nonexistent-no-boot-image",
        "-XjdwpProvider:none",
        "-Xjitwarmupthreshold:65535",
        "-Xjitthreshold:65535",
        "-Xjitinitialsize:4M",
        "-Xjitmaxsize:16M",
        "-Xms64m",
        "-Xmx512m",
        "-Djava.library.path=.;run",
        "-cp",
        "run/w025jitlifecyclestressprobe.jar",
        "W025JitLifecycleStressProbe",
        str(cycles),
    ]
    try:
        result = subprocess.run(
            command,
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
            timeout=240,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"{name} timed out after {error.timeout} seconds") from error
    output = result.stdout + "\n" + result.stderr
    compilations = 24 * (cycles + 1)
    reuse = 24 * cycles
    markers = (
        f"W025_JIT3_PASS methods=24 managed=16 jni=8 unique_allocations=24 "
        f"cycles={cycles} collections={cycles} compilations={compilations} exact_reuse={reuse}",
        "missing_live=0 stale_dead=0 unwind_failures=0",
        "callback_tables=0",
        f"W025JitLifecycleStressProbe PASS cycles={cycles}",
        "jni_values=pass",
        "main end exception=0",
    )
    missing = [marker for marker in markers if marker not in output]
    dual_marker = "Windows x64 JIT dual-view (J-2) created: capacity=16MiB"
    mode_bad = (dual == "1" and dual_marker not in output) or (dual == "0" and dual_marker in output)
    bad = any(
        marker in output
        for marker in ("W025_JIT3_FAIL", "Unhandled page fault", "AssertionError")
    )
    if result.returncode != 0 or missing or mode_bad or bad:
        tail = "\n".join(output.splitlines()[-200:])
        raise RuntimeError(
            f"{name} failed exit={result.returncode} missing={missing} "
            f"mode_bad={mode_bad} bad={bad}\n{tail}"
        )
    print(f"PASS {name} cycles={cycles}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    root = args.package.resolve()
    if not (root / "dalvikvm.exe").is_file():
        raise RuntimeError(f"invalid package directory: {root}")
    run_case(root, "jit3_j2", "1", 4)
    run_case(root, "jit3_j1", "0", 4)
    print("W-025 JIT-3 host package Wine smoke: PASS modes=J-2,J-1 cycles=4")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as error:
        print(f"W-025 JIT-3 host package Wine smoke: FAIL: {error}", file=sys.stderr)
        sys.exit(1)
