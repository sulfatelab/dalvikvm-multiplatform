#!/usr/bin/env python3
"""Smoke the focused W-003 native-host package under Wine."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
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

W003_ENV = (
    "ART_WIN64_JIT",
    "ART_WIN64_JIT_DUAL",
    "ART_WIN64_JIT_EXCLUDE",
    "ART_WIN64_JIT_FILTER",
    "ART_WIN64_JIT_LOG_COMPILES",
    "ART_WIN64_NTERP",
    "ART_WIN64_QUICK_INVOKE",
)

BAD_MARKERS = (
    "Check failed:",
    "Fatal signal",
    "Unhandled page fault",
    "Unhandled exception",
    "Access violation",
    "STATUS_ACCESS_VIOLATION",
    "0xc0000005",
    "ART Win64 VEH",
    "ART Win64 UEF",
)


def run_case(
    root: Path,
    name: str,
    arguments: list[str],
    markers: list[str],
    extra_env: dict[str, str],
) -> str:
    env = os.environ.copy()
    for key in W003_ENV:
        env.pop(key, None)
    env.update(
        {
            "ANDROID_ROOT": "run",
            "ANDROID_ART_ROOT": "run",
            "ANDROID_I18N_ROOT": "run",
            "ANDROID_DATA": "run/data",
            "ICU_DATA": "run/icu",
            "WINEDEBUG": os.environ.get("WINEDEBUG", "-all"),
            "ART_WIN64_QUICK_INVOKE": "1",
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
    lowered_output = output.lower()
    forbidden = [marker for marker in BAD_MARKERS if marker.lower() in lowered_output]
    if result.returncode != 0 or missing or forbidden:
        tail = "\n".join(output.splitlines()[-140:])
        raise RuntimeError(
            f"{name} failed: exit={result.returncode} missing={missing} "
            f"forbidden={forbidden}\n{tail}"
        )
    print(f"PASS {name}")
    return output


def frame_counter(output: str, mode: str, phase: str, family: str) -> int:
    pattern = re.compile(
        rf"^W003FrameProbe mode={re.escape(mode)} phase={re.escape(phase)} "
        rf"counts=.*\b{re.escape(family)}:([0-9]+).* checksum=-?[0-9]+$",
        re.MULTILINE,
    )
    matches = pattern.findall(output)
    if not matches:
        raise RuntimeError(f"missing {mode}/{phase}/{family} frame counter")
    return int(matches[-1])


def frame_mode(root: Path, mode: str) -> None:
    env: dict[str, str] = {}
    args: list[str] = []
    if mode == "int":
        env.update(ART_WIN64_JIT="0", ART_WIN64_NTERP="0")
        args.append("-Xint")
    elif mode == "switch":
        env.update(ART_WIN64_JIT="0", ART_WIN64_NTERP="0")
    elif mode == "nterp":
        env.update(ART_WIN64_JIT="0", ART_WIN64_NTERP="1")
    elif mode == "jit":
        env.update(
            ART_WIN64_JIT="1",
            ART_WIN64_NTERP="1",
            ART_WIN64_JIT_FILTER="W003FrameProbe",
            ART_WIN64_JIT_LOG_COMPILES="1",
        )
        args.extend(["-verbose:jit", "-Xjitwarmupthreshold:0", "-Xjitthreshold:0"])
    else:
        raise RuntimeError(f"unknown frame mode: {mode}")

    args.extend(
        [
            f"-Dw003.mode={mode}",
            "-Djava.library.path=.",
            "-cp",
            "run/w003frameprobe.jar",
            "W003FrameProbe",
        ]
    )
    markers = [
        f"W003FrameProbe mode={mode} phase=refs_only counts=",
        f"W003FrameProbe mode={mode} phase=refs_and_args counts=",
        f"W003FrameProbe mode={mode} phase=all_callee_saves counts=",
        f"W003FrameProbe mode={mode} phase=everything counts=",
        f"W003FrameProbe OK mode={mode}",
        "main end exception=0",
    ]
    output = run_case(root, f"frame_{mode}", args, markers, env)
    if frame_counter(output, mode, "refs_and_args", "refs_and_args") <= 0:
        raise RuntimeError(f"{mode}: refs-and-args counter is zero")
    if frame_counter(output, mode, "everything", "everything") <= 0:
        raise RuntimeError(f"{mode}: save-everything counter is zero")
    if mode in {"nterp", "jit"}:
        if frame_counter(output, mode, "refs_only", "refs_only") <= 0:
            raise RuntimeError(f"{mode}: refs-only counter is zero")
        if frame_counter(output, mode, "all_callee_saves", "all_callee_saves") <= 0:
            raise RuntimeError(f"{mode}: all-callee-saves counter is zero")


def xmm_mode(root: Path, mode: str) -> None:
    env: dict[str, str] = {}
    args: list[str] = []
    if mode == "nterp":
        env.update(ART_WIN64_JIT="0", ART_WIN64_NTERP="1")
    elif mode == "switch":
        env.update(ART_WIN64_JIT="0", ART_WIN64_NTERP="0")
    elif mode == "jit":
        env.update(
            ART_WIN64_JIT="1",
            ART_WIN64_NTERP="1",
            ART_WIN64_JIT_FILTER="W003XmmSentinelProbe.managedCallback",
            ART_WIN64_JIT_LOG_COMPILES="1",
        )
        args.extend(["-verbose:jit", "-Xjitwarmupthreshold:0", "-Xjitthreshold:0"])
    else:
        raise RuntimeError(f"unknown XMM mode: {mode}")
    args.extend(
        [
            f"-Dw003.mode={mode}",
            "-Djava.library.path=.",
            "-cp",
            "run/w003xmmsentinelprobe.jar",
            "W003XmmSentinelProbe",
        ]
    )
    markers = [
        f"W003XmmSentinelProbe mode={mode}",
        "mask=0 selfTestMask=63 iterations=128",
        "fullSelfTestMask=1023",
        "W003XmmSentinelProbe OK",
        "main end exception=0",
    ]
    if mode == "jit":
        markers.append("success=1 method=int W003XmmSentinelProbe.managedCallback(")
    run_case(root, f"xmm_{mode}", args, markers, env)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    root = args.package.resolve()
    if not (root / "dalvikvm.exe").is_file():
        raise RuntimeError(f"invalid package directory: {root}")

    product = root / "art.product.dll"
    instrumented = root / "art.frame-probe.dll"
    active = root / "art.dll"
    try:
        shutil.copy2(instrumented, active)
        for mode in ("int", "switch", "nterp", "jit"):
            frame_mode(root, mode)
        shutil.copy2(product, active)
        for mode in ("nterp", "switch", "jit"):
            xmm_mode(root, mode)
    finally:
        shutil.copy2(product, active)

    if any(path.is_file() and path.suffix.lower() == ".dmp" for path in root.rglob("*")):
        raise RuntimeError("Wine smoke produced crash dumps")
    print("W-003 host package Wine smoke: PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as error:
        print(f"W-003 host package Wine smoke: FAIL: {error}", file=sys.stderr)
        sys.exit(1)
