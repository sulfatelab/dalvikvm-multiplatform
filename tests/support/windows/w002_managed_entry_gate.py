#!/usr/bin/env python3
"""Run the W-002 OSR or attached-thread managed matrix without a host shell."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys


_SUPPORT_ROOT = Path(__file__).parents[1]
if str(_SUPPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_SUPPORT_ROOT))

import runtime_gate  # noqa: E402


def _case_contract(
    case: str, mode: str, jni_dir: Path | None
) -> tuple[str, list[str], list[str], dict[str, str], list[str]]:
    environment = {
        "ART_WINDOWS_X64_JIT": "1",
        "ART_WINDOWS_X64_NTERP": "1" if mode == "nterp" else "0",
        "ART_WINDOWS_X64_JIT_LOG_COMPILES": "1",
    }
    forbidden = [
        "AssertionError",
        "ART Win32 VEH",
        "ART Win32 UEF",
        "minidump written",
    ]
    if case == "osr":
        environment["ART_WINDOWS_X64_JIT_FILTER"] = "W002OsrProbe.osrLoop"
        expected = [
            "warmup_threshold=100, optimize_threshold=100",
            "W002OsrProbe OK checksum=65553463744",
            "kind=Baseline",
            "kind=Osr",
            "Jumping to long W002OsrProbe.osrLoop(int)",
            "main end exception=0",
        ]
        completion = "Done running OSR code for long W002OsrProbe.osrLoop(int)"
        if mode == "switch":
            expected.append(completion)
        else:
            forbidden.append(completion)
        return (
            "W002OsrProbe",
            ["-verbose:jit", "-Xjitwarmupthreshold:100", "-Xjitthreshold:100"],
            expected,
            environment,
            forbidden,
        )

    if jni_dir is None:
        raise runtime_gate.GateError("attached-thread case requires --jni-dir")
    environment["ART_WINDOWS_X64_JIT_FILTER"] = "W002AttachProbe.attachedCallback"
    return (
        "W002AttachProbe",
        ["-Xjitthreshold:0", f"-Djava.library.path={jni_dir}"],
        [
            "W002AttachProbe OK completed=16",
            "Windows x64 CompileMethod done success=1 method=long "
            "W002AttachProbe.attachedCallback(boolean, int)",
            "main end exception=0",
        ],
        environment,
        forbidden,
    )


def run_gate(
    *,
    case: str,
    target_id: str,
    dalvikvm: Path,
    boot_jar: Path,
    app_jar: Path,
    work_root: Path,
    icu_data: Path,
    jni_dir: Path | None,
    library_dirs: list[Path],
    repetitions: int,
    timeout: int,
) -> None:
    work_root = runtime_gate._managed_path(work_root, allow_missing=True)
    if jni_dir is not None:
        jni_dir = runtime_gate._managed_path(jni_dir)
    if work_root.exists() or work_root.is_symlink():
        runtime_gate._reject_tree_links(work_root)
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True)

    records: list[dict[str, object]] = []
    for mode in ("nterp", "switch"):
        main_class, vm_options, expected, environment, forbidden = _case_contract(
            case, mode, jni_dir
        )
        for repetition in range(1, repetitions + 1):
            case_root = work_root / f"{mode}-{repetition}"
            runtime_gate.run_managed(
                target_id=target_id,
                dalvikvm=dalvikvm,
                boot_jar=boot_jar,
                app_jar=app_jar,
                main_class=main_class,
                work_root=case_root,
                icu_data=icu_data,
                library_dirs=library_dirs,
                vm_options=vm_options,
                main_args=[],
                expected=expected,
                forbidden=forbidden,
                expected_exit=0,
                timeout=timeout,
                environment_overrides=environment,
            )
            records.append(
                {
                    "mode": mode,
                    "repetition": repetition,
                    "runtime": json.loads(
                        (case_root / "result.json").read_text(encoding="utf-8")
                    ),
                }
            )

    dumps = sorted(path.name for path in work_root.rglob("*.dmp"))
    record = {
        "schema_version": 1,
        "target_id": target_id,
        "case": case,
        "requested_modes": 2,
        "repetitions_per_mode": repetitions,
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
        raise runtime_gate.GateError(f"W-002 {case} created dump files: {dumps}")
    print(
        f"W-002 {case} passed for {target_id}: "
        f"modes=2, repetitions={repetitions}, runs={len(records)}, dumps=0"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=("osr", "attach"), required=True)
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--dalvikvm", type=Path, required=True)
    parser.add_argument("--boot-jar", type=Path, required=True)
    parser.add_argument("--app-jar", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--icu-data", type=Path, required=True)
    parser.add_argument("--jni-dir", type=Path)
    parser.add_argument("--library-dir", type=Path, action="append", default=[])
    parser.add_argument("--repeat", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=120)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.repeat < 1 or args.timeout < 1:
            raise runtime_gate.GateError("repeat and timeout must be positive")
        run_gate(
            case=args.case,
            target_id=args.target_id,
            dalvikvm=args.dalvikvm,
            boot_jar=args.boot_jar,
            app_jar=args.app_jar,
            work_root=args.work_root,
            icu_data=args.icu_data,
            jni_dir=args.jni_dir,
            library_dirs=args.library_dir,
            repetitions=args.repeat,
            timeout=args.timeout,
        )
        return 0
    except (runtime_gate.GateError, OSError, UnicodeError) as exc:
        print(f"w002_managed_entry_gate.py: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
