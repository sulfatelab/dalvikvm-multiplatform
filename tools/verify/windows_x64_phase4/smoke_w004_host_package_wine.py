#!/usr/bin/env python3
"""Run a focused Wine smoke against the staged W-004 host package."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


COMMON = [
    "-Xbootclasspath:run/boot.jar",
    "-Xbootclasspath-locations:run/boot.jar",
    "-Ximage:/nonexistent-no-boot-image",
    "-XjdwpProvider:none",
    "-Xms64m",
    "-Xmx512m",
]


def run_case(
    root: Path,
    name: str,
    arguments: list[str],
    markers: list[str],
    extra_env: dict[str, str] | None = None,
    forbidden: list[str] | None = None,
) -> None:
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
        }
    )
    if extra_env:
        env.update(extra_env)
    try:
        result = subprocess.run(
            ["wine64", "./dalvikvm.exe", *COMMON, *arguments],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"{name} timed out after {error.timeout} seconds") from error
    output = result.stdout + "\n" + result.stderr
    missing = [marker for marker in markers if marker not in output]
    present_forbidden = [marker for marker in (forbidden or []) if marker in output]
    if result.returncode != 0 or missing or present_forbidden:
        tail = "\n".join(output.splitlines()[-100:])
        raise RuntimeError(
            f"{name} failed: exit={result.returncode} missing={missing} "
            f"forbidden={present_forbidden}\n{tail}"
        )
    print(f"PASS {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    root = args.package.resolve()
    if not (root / "dalvikvm.exe").is_file():
        raise RuntimeError(f"invalid package directory: {root}")

    run_case(
        root,
        "nterp_xint",
        ["-Xint", "-cp", "run/hello.jar", "Hello"],
        ["Hello from dalvikvm!", "main end exception=0"],
    )
    run_case(
        root,
        "jit_dual",
        ["-cp", "run/hello.jar", "Hello"],
        [
            "JitCodeCache::Create OK",
            "Windows x64 CompileMethod done success=1 method=java.lang.StringBuilder",
            "Hello from dalvikvm!",
            "main end exception=0",
        ],
        {"ART_WINDOWS_X64_JIT_DUAL": "1", "ART_WINDOWS_X64_JIT_LOG_COMPILES": "1"},
    )
    run_case(
        root,
        "float_threshold0_dual",
        ["-Xjitthreshold:0", "-cp", "run/FloatProbe.jar", "FloatProbe"],
        ["FloatProbe OK", "main end exception=0"],
        {"ART_WINDOWS_X64_JIT_DUAL": "1"},
    )
    run_case(
        root,
        "critical_dual",
        [
            "-Xjitthreshold:0",
            "-Dcritical.load=library",
            "-Dcritical.instrumentation=1",
            "-Djava.library.path=empty-native-dir;.",
            "-cp",
            "run/criticalnativeprobe.jar",
            "CriticalNativeProbe",
        ],
        [
            "CriticalNativeProbe instrumentation OK",
            "CriticalNativeDlsymProbe postTracing OK",
            "main end exception=0",
        ],
        {"ART_WINDOWS_X64_JIT_DUAL": "1"},
    )
    run_case(
        root,
        "native_abi_dual",
        [
            "-Xjitthreshold:0",
            "-Dnative.abi.instrumentation=1",
            "-Djava.library.path=empty-native-dir;.",
            "-cp",
            "run/fastnativeabiprobe.jar",
            "FastNativeAbiProbe",
        ],
        [
            "FastNativeAbiProbe OK",
            "FastNativeAbiProbe tracingMode before=0",
            "main end exception=0",
        ],
        {
            "ART_WINDOWS_X64_JIT_DUAL": "1",
            "ART_WINDOWS_X64_JIT_FILTER": "FastNativeAbiProbe",
            "ART_WINDOWS_X64_JIT_LOG_COMPILES": "1",
        },
    )
    run_case(
        root,
        "jvmti_dual",
        [
            "-Xplugin:openjdkjvmti.dll",
            "-agentpath:libjvmtiforceprobe.dll",
            "-Xjitthreshold:0",
            "-Djava.library.path=.",
            "-cp",
            "run/jvmtiforceprobe.jar",
            "JvmtiForceProbe",
        ],
        [
            "JvmtiForceProbe OK",
            "JvmtiForceProbe after normalRegistered=137.75",
            "main end exception=0",
        ],
        {
            "ART_WINDOWS_X64_JIT_DUAL": "1",
            "ART_WINDOWS_X64_JIT_FILTER": "JvmtiForceProbe",
            "ART_WINDOWS_X64_JIT_LOG_COMPILES": "1",
        },
        ["success=1 method=double JvmtiForceProbe.criticalRegistered("],
    )
    run_case(
        root,
        "gcstress",
        ["-cp", "run/gcstressprobe.jar", "GcStressProbe"],
        ["gcstress.ok=true", "GcStressProbe.done=ok"],
        {"ART_WINDOWS_X64_JIT_DUAL": "1"},
    )
    run_case(
        root,
        "threadheavy",
        ["-cp", "run/threadheavyprobe.jar", "ThreadHeavyProbe"],
        ["threadheavy.ok=true", "ThreadHeavyProbe.done=ok"],
        {"ART_WINDOWS_X64_JIT_DUAL": "1"},
    )
    for index in range(1, 4):
        run_case(
            root,
            f"repeat_hello_{index:02d}",
            ["-cp", "run/hello.jar", "Hello"],
            ["Hello from dalvikvm!", "main end exception=0"],
            {"ART_WINDOWS_X64_JIT_DUAL": "1"},
        )
    print("W-004 host package Wine smoke: PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as error:
        print(f"W-004 host package Wine smoke: FAIL: {error}", file=sys.stderr)
        sys.exit(1)
