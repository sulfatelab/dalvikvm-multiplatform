#!/usr/bin/env python3
"""Run W-010 managed abort and fatal native-unwind contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys


_SUPPORT_ROOT = Path(__file__).parents[2] / "support"
if str(_SUPPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_SUPPORT_ROOT))

import runtime_gate  # noqa: E402


_FATAL_COMMON = (
    "ART Win32 VEH: exception 0xc0000005",
    "ART Win32 UEF: exception 0xc0000005",
    "minidump written",
)


def _run_managed(
    *,
    target_id: str,
    dalvikvm: Path,
    boot_jar: Path,
    app_jar: Path,
    main_class: str,
    main_args: list[str],
    case_root: Path,
    icu_data: Path,
    library_dirs: list[Path],
    vm_options: list[str],
    expected: list[str],
    forbidden: list[str],
    environment: dict[str, str],
    timeout: int,
) -> dict[str, object]:
    case_root.mkdir(parents=True)
    crash_root = case_root / "run" / "crash"
    crash_root.mkdir(parents=True)
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
        main_args=main_args,
        expected=expected,
        forbidden=forbidden,
        expected_exit=0,
        timeout=timeout,
        environment_overrides=environment,
        require_nonzero=True,
    )
    dumps = sorted(crash_root.glob("*.dmp"))
    dump_records: list[dict[str, object]] = []
    for dump in dumps:
        if dump.stat().st_size <= 4096 or dump.read_bytes()[:4] != b"MDMP":
            raise runtime_gate.GateError(f"invalid minidump: {dump.name}")
        dump_records.append({
            "name": dump.name,
            "size": dump.stat().st_size,
            "sha256": runtime_gate._sha256(dump),
        })
    return {
        "runtime": json.loads((case_root / "result.json").read_text(encoding="utf-8")),
        "dumps": dump_records,
    }


def run_gate(
    *,
    mode: str,
    target_id: str,
    dalvikvm: Path,
    boot_jar: Path,
    app_jar: Path,
    work_root: Path,
    icu_data: Path,
    library_dirs: list[Path],
    timeout: int,
) -> None:
    work_root = runtime_gate._managed_path(work_root, allow_missing=True)
    if work_root.exists() or work_root.is_symlink():
        runtime_gate._reject_tree_links(work_root)
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True)

    if mode == "abort":
        result = _run_managed(
            target_id=target_id,
            dalvikvm=dalvikvm,
            boot_jar=boot_jar,
            app_jar=app_jar,
            main_class="CrashAbortProbe",
            main_args=[],
            case_root=work_root / "abort",
            icu_data=icu_data,
            library_dirs=library_dirs,
            vm_options=["-Xint"],
            expected=["CrashAbortProbe.start", "RuntimeException", "phase4-abort-ok"],
            forbidden=["minidump written"],
            environment={},
            timeout=timeout,
        )
        if result["dumps"]:
            raise runtime_gate.GateError("managed abort unexpectedly created a minidump")
        records = [{"name": "abort", **result}]
    else:
        cases = (
            (
                "static",
                [],
                ["-Xint"],
                {"ART_WINDOWS_X64_JIT": "0", "ART_WINDOWS_X64_NTERP": "1"},
                ["CrashNativeProbe.start", *_FATAL_COMMON],
                ["CrashNativeProbe.unexpected_continue"],
                timeout,
            ),
            (
                "jit",
                ["jit"],
                ["-verbose:jit", "-Xjitwarmupthreshold:0", "-Xjitthreshold:0"],
                {
                    "ART_WINDOWS_X64_CRASH_NATIVE_WARMUP": "20000",
                    "ART_WINDOWS_X64_JIT": "1",
                    "ART_WINDOWS_X64_NTERP": "1",
                    "ART_WINDOWS_X64_JIT_FILTER": "CrashNativeProbe",
                    "ART_WINDOWS_X64_JIT_LOG_COMPILES": "1",
                },
                [
                    "CrashNativeProbe.jit_ready calls=20000",
                    "Windows x64 CompileMethod done success=1 method=void CrashNativeProbe.jitCrashCaller(int)",
                    "Windows x64 CompileMethod done success=1 method=void CrashNativeProbe.nativeSegfault()",
                    "Windows x64 JIT dual-view (J-2) created",
                    *_FATAL_COMMON,
                ],
                ["CrashNativeProbe.unexpected_continue"],
                timeout,
            ),
            (
                "osr",
                ["osr"],
                ["-verbose:jit", "-Xjitwarmupthreshold:100", "-Xjitthreshold:100"],
                {
                    "ART_WINDOWS_X64_JIT": "1",
                    "ART_WINDOWS_X64_NTERP": "0",
                    "ART_WINDOWS_X64_JIT_FILTER": "CrashNativeProbe.osrCrashLoop",
                    "ART_WINDOWS_X64_JIT_LOG_COMPILES": "1",
                },
                [
                    "CrashNativeProbe.osr_armed count=2000000",
                    "warmup_threshold=100, optimize_threshold=100",
                    "kind=Baseline",
                    "kind=Osr",
                    "Windows x64 CompileMethod done success=1 method=long CrashNativeProbe.osrCrashLoop(int)",
                    "Jumping to long CrashNativeProbe.osrCrashLoop(int)",
                    "Windows x64 JIT dual-view (J-2) created",
                    *_FATAL_COMMON,
                ],
                [
                    "Done running OSR code for long CrashNativeProbe.osrCrashLoop(int)",
                    "CrashNativeProbe.osr_unexpected_return",
                    "CrashNativeProbe.unexpected_continue",
                ],
                max(timeout, 180),
            ),
        )
        records = []
        for name, args, options, environment, expected, forbidden, case_timeout in cases:
            result = _run_managed(
                target_id=target_id,
                dalvikvm=dalvikvm,
                boot_jar=boot_jar,
                app_jar=app_jar,
                main_class="CrashNativeProbe",
                main_args=args,
                case_root=work_root / name,
                icu_data=icu_data,
                library_dirs=library_dirs,
                vm_options=options,
                expected=expected,
                forbidden=forbidden,
                environment=environment,
                timeout=case_timeout,
            )
            if len(result["dumps"]) != 1:
                raise runtime_gate.GateError(
                    f"fatal case {name} produced {len(result['dumps'])} minidumps"
                )
            records.append({"name": name, **result})

    record = {
        "schema_version": 1,
        "target_id": target_id,
        "mode": mode,
        "completed_cases": len(records),
        "dump_count": sum(len(record["dumps"]) for record in records),
        "cases": records,
    }
    (work_root / "result.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"W-010 fatal-runtime {mode} gate passed for {target_id}: "
        f"cases={len(records)}, dumps={record['dump_count']}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("abort", "native"), required=True)
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--dalvikvm", type=Path, required=True)
    parser.add_argument("--boot-jar", type=Path, required=True)
    parser.add_argument("--app-jar", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--icu-data", type=Path, required=True)
    parser.add_argument("--library-dir", type=Path, action="append", default=[])
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    try:
        if args.timeout < 1:
            raise runtime_gate.GateError("timeout must be positive")
        run_gate(
            mode=args.mode,
            target_id=args.target_id,
            dalvikvm=args.dalvikvm,
            boot_jar=args.boot_jar,
            app_jar=args.app_jar,
            work_root=args.work_root,
            icu_data=args.icu_data,
            library_dirs=args.library_dir,
            timeout=args.timeout,
        )
        return 0
    except (runtime_gate.GateError, OSError, UnicodeError) as exc:
        print(f"fatal-runtime run.py: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
