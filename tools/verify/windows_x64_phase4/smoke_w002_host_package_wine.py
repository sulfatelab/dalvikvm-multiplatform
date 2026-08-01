#!/usr/bin/env python3
"""Re-run the historical focused W-002 package matrix under Wine."""

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

W002_ENV = (
    "ART_WINDOWS_X64_JIT",
    "ART_WINDOWS_X64_JIT_DUAL",
    "ART_WINDOWS_X64_JIT_EXCLUDE",
    "ART_WINDOWS_X64_JIT_FILTER",
    "ART_WINDOWS_X64_JIT_LOG_COMPILES",
    "ART_WINDOWS_X64_NTERP",
    "ART_WINDOWS_X64_QUICK_INVOKE",
)


def run_case(
    root: Path,
    name: str,
    arguments: list[str],
    markers: list[str],
    extra_env: dict[str, str],
    forbidden: list[str] | None = None,
) -> None:
    env = os.environ.copy()
    for key in W002_ENV:
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
        tail = "\n".join(output.splitlines()[-120:])
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

    osr_markers = [
        "warmup_threshold=100, optimize_threshold=100",
        "W002OsrProbe OK checksum=65553463744",
        "kind=Baseline",
        "kind=Osr",
        "Jumping to long W002OsrProbe.osrLoop(int)",
        "main end exception=0",
    ]
    attach_markers = [
        "W002AttachProbe OK completed=16",
        (
            "Windows x64 CompileMethod done success=1 method=long "
            "W002AttachProbe.attachedCallback(boolean, int)"
        ),
        "main end exception=0",
    ]
    switch_completion = (
        "Done running OSR code for long W002OsrProbe.osrLoop(int)"
    )

    for mode, dual in (("dual", "1"), ("j1", "0")):
        for interpreter in ("default", "switch"):
            base_env = {"ART_WINDOWS_X64_JIT_DUAL": dual}
            if interpreter == "switch":
                base_env["ART_WINDOWS_X64_NTERP"] = "0"

            osr_env = {
                **base_env,
                "ART_WINDOWS_X64_JIT_FILTER": "W002OsrProbe.osrLoop",
                "ART_WINDOWS_X64_JIT_LOG_COMPILES": "1",
            }
            required = list(osr_markers)
            forbidden: list[str] = []
            if interpreter == "switch":
                required.append(switch_completion)
            else:
                forbidden.append(switch_completion)
            run_case(
                root,
                f"osr_{mode}_{interpreter}",
                [
                    "-verbose:jit",
                    "-Xjitwarmupthreshold:100",
                    "-Xjitthreshold:100",
                    "-cp",
                    "run/w002osrprobe.jar",
                    "W002OsrProbe",
                ],
                required,
                osr_env,
                forbidden,
            )

            attach_env = {
                **base_env,
                "ART_WINDOWS_X64_JIT_FILTER": "W002AttachProbe.attachedCallback",
                "ART_WINDOWS_X64_JIT_LOG_COMPILES": "1",
            }
            run_case(
                root,
                f"attach_{mode}_{interpreter}",
                [
                    "-Xjitthreshold:0",
                    "-Djava.library.path=.",
                    "-cp",
                    "run/w002attachprobe.jar",
                    "W002AttachProbe",
                ],
                attach_markers,
                attach_env,
            )

    print("W-002 host package Wine smoke: PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as error:
        print(f"W-002 host package Wine smoke: FAIL: {error}", file=sys.stderr)
        sys.exit(1)
