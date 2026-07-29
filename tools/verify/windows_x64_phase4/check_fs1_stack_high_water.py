#!/usr/bin/env python3
"""Validate one FS-1 stack-overflow high-water runtime log."""

from __future__ import annotations

import argparse
from pathlib import Path
import re


PREFIX = "stack_overflow_high_water "
HEX_FIELDS = (
    "stack_low",
    "guarantee_top",
    "native_boundary",
    "default_stack_end",
    "lowest_rsp",
    "explicit_check",
    "quick_entry",
    "quick_frame",
    "throw_entry",
    "expanded",
    "construct",
    "constructed",
    "restored",
    "delivery",
    "long_jump",
)
COMMON_PHASES = (
    "explicit_check",
    "throw_entry",
    "expanded",
    "construct",
    "constructed",
    "restored",
)
QUICK_PHASES = ("quick_entry", "quick_frame", "delivery", "long_jump")


def fail(message: str) -> None:
    raise SystemExit(f"FS-1 log validation FAIL: {message}")


def parse_record(line: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for token in line[len(PREFIX) :].split():
        if "=" not in token:
            fail(f"malformed record token {token!r}")
        key, value = token.split("=", 1)
        if key in fields:
            fail(f"duplicate record field {key!r}")
        fields[key] = value
    return fields


def number(fields: dict[str, str], name: str, base: int = 10) -> int:
    try:
        return int(fields[name], base)
    except KeyError:
        fail(f"missing field {name!r}")
    except ValueError:
        fail(f"invalid integer {name}={fields[name]!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--mode", choices=("switch", "nterp", "jit"), required=True)
    parser.add_argument("--art-reserve", type=int, default=8192)
    args = parser.parse_args()

    text = args.log.read_text(encoding="utf-8", errors="replace")
    lines = [line for line in text.splitlines() if line.startswith(PREFIX)]
    if len(lines) != 4:
        fail(f"{args.mode}: expected four records, found {len(lines)}")

    records = [parse_record(line) for line in lines]
    labels = [record.get("label") for record in records]
    expected_labels = ["main-1", "main-2", "child-1", "child-2"]
    if labels != expected_labels:
        fail(f"{args.mode}: labels {labels!r}, expected {expected_labels!r}")

    expected_path = "switch" if args.mode == "switch" else "quick"
    thread_sequences: dict[str, list[int]] = {"main": [], "child": []}
    lowest_margin: int | None = None
    for record in records:
        label = record["label"]
        if record.get("path") != expected_path:
            fail(f"{args.mode}/{label}: path={record.get('path')!r}, expected {expected_path!r}")
        if record.get("complete") != "1":
            fail(f"{args.mode}/{label}: record is incomplete")

        values = {name: number(record, name, 16) for name in HEX_FIELDS}
        guarantee = number(record, "guarantee")
        reserve = number(record, "art_reserve")
        margin = number(record, "margin_to_guarantee")
        native_margin = number(record, "margin_to_native")
        used = number(record, "art_reserve_used")
        remaining = number(record, "art_reserve_remaining")
        sequence = number(record, "sequence")

        if guarantee < 4 * 4096 or guarantee % 4096 != 0:
            fail(f"{args.mode}/{label}: invalid configured guarantee {guarantee}")
        if reserve != args.art_reserve:
            fail(
                f"{args.mode}/{label}: ART reserve is {reserve}, "
                f"expected {args.art_reserve}"
            )
        if values["default_stack_end"] - values["native_boundary"] != reserve:
            fail(f"{args.mode}/{label}: default/native boundary does not equal ART reserve")
        if values["lowest_rsp"] - values["guarantee_top"] != margin:
            fail(f"{args.mode}/{label}: guarantee-margin arithmetic mismatch")
        if values["lowest_rsp"] - values["native_boundary"] != native_margin:
            fail(f"{args.mode}/{label}: native-margin arithmetic mismatch")
        reserve_sample = min(values["lowest_rsp"], values["default_stack_end"])
        if reserve_sample - values["native_boundary"] != remaining:
            fail(f"{args.mode}/{label}: reserve-remaining arithmetic mismatch")
        if values["default_stack_end"] - reserve_sample != used:
            fail(f"{args.mode}/{label}: reserve-used arithmetic mismatch")
        if margin <= 0 or native_margin <= 0:
            fail(
                f"{args.mode}/{label}: non-positive safety margin "
                f"guarantee={margin} native={native_margin}"
            )
        if used < 0 or used + remaining != reserve:
            fail(
                f"{args.mode}/{label}: invalid reserve split "
                f"used={used} remaining={remaining} reserve={reserve}"
            )

        nonzero_phases = [values[name] for name in COMMON_PHASES]
        if any(value == 0 for value in nonzero_phases):
            fail(f"{args.mode}/{label}: a common phase was not sampled")
        if expected_path == "quick":
            if any(values[name] == 0 for name in QUICK_PHASES):
                fail(f"{args.mode}/{label}: a quick phase was not sampled")
            nonzero_phases.extend(values[name] for name in QUICK_PHASES)
        elif any(values[name] != 0 for name in QUICK_PHASES):
            fail(f"{args.mode}/{label}: switch record contains a quick-only phase")
        if min(nonzero_phases) != values["lowest_rsp"]:
            fail(f"{args.mode}/{label}: lowest_rsp is not the phase minimum")

        thread = label.split("-", 1)[0]
        thread_sequences[thread].append(sequence)
        lowest_margin = (
            native_margin if lowest_margin is None else min(lowest_margin, native_margin)
        )

    for thread, sequences in thread_sequences.items():
        if len(sequences) != 2 or sequences[1] != sequences[0] + 1:
            fail(f"{args.mode}/{thread}: non-consecutive sequences {sequences!r}")

    marker = f"FS1StackHighWaterProbe OK mode={args.mode} main=2 child=2"
    if marker not in text:
        fail(f"{args.mode}: missing completion marker")
    if re.search(r"ART Win32 (?:VEH|UEF)|minidump written", text):
        fail(f"{args.mode}: handled overflow reached fatal diagnostics")
    if args.mode == "jit":
        for method in ("recurse", "runRounds"):
            pattern = rf"Windows x64 CompileMethod done success=1 method=.*FS1StackHighWaterProbe\.{method}\("
            if re.search(pattern, text) is None:
                fail(f"jit: method {method} was not compiled")
    elif "Windows x64 CompileMethod done success=1 method=" in text:
        fail(f"{args.mode}: managed code was unexpectedly compiled")

    print(
        f"FS-1 {args.mode} high-water log: PASS "
        f"(records=4 minimum_native_margin={lowest_margin})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
