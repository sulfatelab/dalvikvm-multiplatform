#!/usr/bin/env python3
"""Run the Windows JVMTI forced-interpreter matrix without a host shell."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys


_SUPPORT_ROOT = Path(__file__).parents[2] / "support"
if str(_SUPPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_SUPPORT_ROOT))

import runtime_gate  # noqa: E402


_VALUES = (
    "normalRegistered=137.75 fastRegistered=237.75 "
    "criticalRegistered=337.75 normalDlsym=437.75 "
    "fastDlsym=537.75 criticalDlsym=637.75"
)
_COMPILED_METHODS = (
    "double JvmtiForceProbe.normalRegistered(",
    "double JvmtiForceProbe.fastRegistered(",
)
_FORBIDDEN = (
    "AssertionError",
    "ART Win32 VEH",
    "ART Win32 UEF",
    "minidump written",
    "success=1 method=double JvmtiForceProbe.criticalRegistered(",
    "success=1 method=double JvmtiForceProbe.criticalDlsym(",
)


def _combined(case_root: Path) -> str:
    return (
        (case_root / "stdout.txt").read_text(encoding="utf-8")
        + "\n"
        + (case_root / "stderr.txt").read_text(encoding="utf-8")
    )


def _stage(source: Path, case_root: Path, *names: str) -> None:
    source = runtime_gate._regular_file(str(source))
    for name in names:
        destination = case_root / name
        shutil.copyfile(source, destination)
        runtime_gate._regular_file(str(destination))


def _validate_output(output: str, repetition: int) -> dict[str, int]:
    match = re.search(
        r"JvmtiForceProbe steps before=([0-9]+) during=([0-9]+) "
        r"disabled=([0-9]+) final=([0-9]+)",
        output,
    )
    if match is None:
        raise runtime_gate.GateError(
            f"JVMTI repetition {repetition} lacks the single-step transition"
        )
    before, during, disabled, final = (int(value) for value in match.groups())
    if before != 0 or during <= before or disabled < during or final != disabled:
        raise runtime_gate.GateError(
            f"JVMTI repetition {repetition} has invalid step counts: "
            f"before={before}, during={during}, disabled={disabled}, final={final}"
        )
    for method in _COMPILED_METHODS:
        count = output.count(f"success=1 method={method}")
        if count != 1:
            raise runtime_gate.GateError(
                f"JVMTI repetition {repetition} has {count} compile records for {method}"
            )
    return {
        "before": before,
        "during": during,
        "disabled": disabled,
        "final": final,
    }


def run_gate(
    *,
    target_id: str,
    dalvikvm: Path,
    boot_jar: Path,
    app_jar: Path,
    agent: Path,
    plugin: Path,
    work_root: Path,
    icu_data: Path,
    library_dirs: list[Path],
    repetitions: int,
    timeout: int,
) -> None:
    if repetitions < 1 or timeout < 1:
        raise runtime_gate.GateError("repeat and timeout must be positive")
    work_root = runtime_gate._managed_path(work_root, allow_missing=True)
    if work_root.exists() or work_root.is_symlink():
        runtime_gate._reject_tree_links(work_root)
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True)

    records: list[dict[str, object]] = []
    for repetition in range(1, repetitions + 1):
        case_root = work_root / f"run-{repetition:03d}"
        case_root.mkdir()
        _stage(
            agent,
            case_root,
            "libjvmtiforceprobe.dll",
            "jvmtiforceprobe.dll",
        )
        _stage(plugin, case_root, "openjdkjvmti.dll")
        runtime_gate.run_managed(
            target_id=target_id,
            dalvikvm=dalvikvm,
            boot_jar=boot_jar,
            app_jar=app_jar,
            main_class="JvmtiForceProbe",
            work_root=case_root,
            icu_data=icu_data,
            library_dirs=[case_root, *library_dirs],
            vm_options=[
                "-Xplugin:openjdkjvmti.dll",
                "-agentpath:libjvmtiforceprobe.dll",
                "-Xjitthreshold:0",
                "-Djava.library.path=.",
            ],
            main_args=[],
            expected=[
                *(f"JvmtiForceProbe {phase} {_VALUES}" for phase in ("before", "during", "after")),
                "JvmtiForceProbe OK",
                "main end exception=0",
            ],
            forbidden=list(_FORBIDDEN),
            expected_exit=0,
            timeout=timeout,
            environment_overrides={
                "ART_WINDOWS_X64_JIT_FILTER": "JvmtiForceProbe",
                "ART_WINDOWS_X64_JIT_LOG_COMPILES": "1",
            },
        )
        steps = _validate_output(_combined(case_root), repetition)
        records.append({
            "repetition": repetition,
            "steps": steps,
            "runtime": json.loads(
                (case_root / "result.json").read_text(encoding="utf-8")
            ),
        })

    dumps = sorted(path.name for path in work_root.rglob("*.dmp"))
    record = {
        "schema_version": 1,
        "target_id": target_id,
        "requested_repetitions": repetitions,
        "completed_runs": len(records),
        "dump_files": dumps,
        "runs": records,
    }
    temporary = work_root / "result.json.tmp"
    temporary.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, work_root / "result.json")
    if dumps:
        raise runtime_gate.GateError(f"JVMTI force gate created dump files: {dumps}")
    print(
        f"JVMTI forced-interpreter gate passed for {target_id}: "
        f"runs={len(records)}, compiled_targets=2, dumps=0"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--dalvikvm", type=Path, required=True)
    parser.add_argument("--boot-jar", type=Path, required=True)
    parser.add_argument("--app-jar", type=Path, required=True)
    parser.add_argument("--agent", type=Path, required=True)
    parser.add_argument("--plugin", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--icu-data", type=Path, required=True)
    parser.add_argument("--library-dir", type=Path, action="append", default=[])
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=180)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        run_gate(
            target_id=args.target_id,
            dalvikvm=args.dalvikvm,
            boot_jar=args.boot_jar,
            app_jar=args.app_jar,
            agent=args.agent,
            plugin=args.plugin,
            work_root=args.work_root,
            icu_data=args.icu_data,
            library_dirs=args.library_dir,
            repetitions=args.repeat,
            timeout=args.timeout,
        )
        return 0
    except (runtime_gate.GateError, OSError, UnicodeError) as exc:
        print(f"jvmti-force run.py: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
