#!/usr/bin/env python3
"""Run the meaningful Wine subset of the staged W-025 JIT-2 package."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


def run_case(
    root: Path,
    name: str,
    command: list[str],
    markers: tuple[str, ...],
    extra_env: dict[str, str] | None = None,
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
            ["wine64", *command],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
            timeout=240,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"{name} timed out after {error.timeout} seconds") from error
    output = result.stdout + "\n" + result.stderr
    missing = [marker for marker in markers if marker not in output]
    if result.returncode != 0 or missing:
        tail = "\n".join(output.splitlines()[-160:])
        raise RuntimeError(f"{name} failed exit={result.returncode} missing={missing}\n{tail}")
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
        "section_basic",
        ["./W025SectionPolicyProbe.exe", "--basic"],
        (
            "roles=R_RX_RW type=MEM_MAPPED rwx=0 mapped_names=0",
            "W025_SECTION_POLICY_PASS mode=basic",
        ),
    )
    run_case(
        root,
        "runtime_mapping_64m",
        [
            "./dalvikvm.exe",
            "-Xbootclasspath:run/boot.jar",
            "-Xbootclasspath-locations:run/boot.jar",
            "-Ximage:/nonexistent-no-boot-image",
            "-XjdwpProvider:none",
            "-Xjitwarmupthreshold:1",
            "-Xjitthreshold:1",
            "-Xjitmaxsize:64M",
            "-Xms64m",
            "-Xmx512m",
            "-Djava.library.path=.;run",
            "-cp",
            "run/w025jitmappingprobe.jar",
            "W025JitMappingProbe",
            "64",
            "false",
        ],
        (
            "Windows x64 JIT dual-view (J-2) created: capacity=64MiB",
            "roles primary_data=R primary_code=RX alias_data=RW alias_code=RW "
            "type=MEM_MAPPED rwx=0 contiguous_low=1 capacity_bytes=67108864",
            "W025_JIT_MAPPING_PASS",
            "W025JitMappingProbe PASS capacity_bytes=67108864 require_cfg=false",
        ),
        {
            "ART_WINDOWS_X64_JIT_DUAL": "1",
            "ART_WINDOWS_X64_JIT_FILTER": "W025JitMappingProbe",
            "ART_WINDOWS_X64_JIT_LOG_COMPILES": "1",
        },
    )
    print(
        "W-025 JIT-2 host package Wine smoke: PASS "
        "native_only=SEC_COMMIT,low-VA,CFG,dynamic-code-policy"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as error:
        print(f"W-025 JIT-2 host package Wine smoke: FAIL: {error}", file=sys.stderr)
        sys.exit(1)
