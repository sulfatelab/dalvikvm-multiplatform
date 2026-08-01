#!/usr/bin/env python3
"""Run the W-010 managed NPE/SOE recovery matrix without a host shell."""

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


_FATAL_FORBIDDEN = ("ART Win32 VEH", "ART Win32 UEF", "minidump written")
_NPE = "W010ManagedFaultProbe NPE OK read=64 write=64 recovery=128 gc=16"
_SO = "W010ManagedFaultProbe SO OK main=2 child=2 recovery=4 gc=4"


def _run(
    *,
    target_id: str,
    dalvikvm: Path,
    boot_jar: Path,
    app_jar: Path,
    case_root: Path,
    icu_data: Path,
    library_dirs: list[Path],
    mode: str,
    vm_options: list[str],
    environment: dict[str, str],
    expected: list[str],
    forbidden: list[str],
    timeout: int,
    require_nonzero: bool = False,
) -> None:
    case_root.mkdir(parents=True)
    (case_root / "run" / "crash").mkdir(parents=True)
    runtime_gate.run_managed(
        target_id=target_id,
        dalvikvm=dalvikvm,
        boot_jar=boot_jar,
        app_jar=app_jar,
        main_class="W010ManagedFaultProbe",
        work_root=case_root,
        icu_data=icu_data,
        library_dirs=library_dirs,
        vm_options=vm_options,
        main_args=[mode],
        expected=expected,
        forbidden=forbidden,
        expected_exit=0,
        timeout=timeout,
        environment_overrides=environment,
        require_nonzero=require_nonzero,
    )
    dumps = list((case_root / "run" / "crash").glob("*.dmp"))
    if dumps:
        raise runtime_gate.GateError(
            f"handled managed fault created dumps: {[path.name for path in dumps]}"
        )


def run_gate(
    *,
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

    base_environment = {"ART_WINDOWS_X64_QUICK_INVOKE": "1"}
    cases = (
        (
            "no-sig-chain",
            "npe",
            ["-Xno-sig-chain", "-Xint"],
            {**base_environment, "ART_WINDOWS_X64_JIT": "0", "ART_WINDOWS_X64_NTERP": "1"},
            ["A started runtime should have sig chain enabled"],
            ["W010ManagedFaultProbe OK"],
            True,
        ),
        (
            "switch-so",
            "so",
            ["-Xusejit:false"],
            {**base_environment, "ART_WINDOWS_X64_JIT": "0", "ART_WINDOWS_X64_NTERP": "0"},
            [_SO, "W010ManagedFaultProbe OK mode=so", "main end exception=0"],
            [*_FATAL_FORBIDDEN, "Windows x64 CompileMethod done success=1 method="],
            False,
        ),
        (
            "nterp-npe",
            "npe",
            ["-Xusejit:false"],
            {**base_environment, "ART_WINDOWS_X64_JIT": "0", "ART_WINDOWS_X64_NTERP": "1"},
            [_NPE, "W010ManagedFaultProbe OK mode=npe", "main end exception=0"],
            [*_FATAL_FORBIDDEN, "Windows x64 CompileMethod done success=1 method="],
            False,
        ),
        (
            "nterp-so",
            "so",
            ["-Xusejit:false"],
            {**base_environment, "ART_WINDOWS_X64_JIT": "0", "ART_WINDOWS_X64_NTERP": "1"},
            [_SO, "W010ManagedFaultProbe OK mode=so", "main end exception=0"],
            [*_FATAL_FORBIDDEN, "Windows x64 CompileMethod done success=1 method="],
            False,
        ),
        (
            "jit-npe",
            "npe",
            ["-verbose:jit", "-Xjitwarmupthreshold:0", "-Xjitthreshold:0"],
            {
                **base_environment,
                "ART_WINDOWS_X64_JIT": "1",
                "ART_WINDOWS_X64_NTERP": "1",
                "ART_WINDOWS_X64_JIT_FILTER": "W010ManagedFaultProbe",
                "ART_WINDOWS_X64_JIT_LOG_COMPILES": "1",
            },
            [
                _NPE,
                "Windows x64 CompileMethod done success=1 method=void W010ManagedFaultProbe.runNullChecks()",
                "W010ManagedFaultProbe OK mode=npe",
                "main end exception=0",
            ],
            list(_FATAL_FORBIDDEN),
            False,
        ),
        (
            "jit-so",
            "so",
            ["-verbose:jit", "-Xjitwarmupthreshold:0", "-Xjitthreshold:0"],
            {
                **base_environment,
                "ART_WINDOWS_X64_JIT": "1",
                "ART_WINDOWS_X64_NTERP": "1",
                "ART_WINDOWS_X64_JIT_FILTER": "W010ManagedFaultProbe",
                "ART_WINDOWS_X64_JIT_LOG_COMPILES": "1",
            },
            [
                _SO,
                "Windows x64 CompileMethod done success=1 method=int W010ManagedFaultProbe.recurse(int)",
                "Windows x64 CompileMethod done success=1 method=int W010ManagedFaultProbe.runStackOverflowRounds()",
                "W010ManagedFaultProbe OK mode=so",
                "main end exception=0",
            ],
            list(_FATAL_FORBIDDEN),
            False,
        ),
    )
    records: list[dict[str, object]] = []
    for name, mode, options, environment, expected, forbidden, nonzero in cases:
        case_root = work_root / name
        _run(
            target_id=target_id,
            dalvikvm=dalvikvm,
            boot_jar=boot_jar,
            app_jar=app_jar,
            case_root=case_root,
            icu_data=icu_data,
            library_dirs=library_dirs,
            mode=mode,
            vm_options=options,
            environment=environment,
            expected=expected,
            forbidden=forbidden,
            timeout=timeout,
            require_nonzero=nonzero,
        )
        records.append({
            "name": name,
            "result": json.loads((case_root / "result.json").read_text(encoding="utf-8")),
        })

    record = {
        "schema_version": 1,
        "target_id": target_id,
        "completed_cases": len(records),
        "dump_files": [],
        "cases": records,
    }
    (work_root / "result.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"W-010 managed-fault gate passed for {target_id}: cases={len(records)}, dumps=0")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--dalvikvm", type=Path, required=True)
    parser.add_argument("--boot-jar", type=Path, required=True)
    parser.add_argument("--app-jar", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--icu-data", type=Path, required=True)
    parser.add_argument("--library-dir", type=Path, action="append", default=[])
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    try:
        if args.timeout < 1:
            raise runtime_gate.GateError("timeout must be positive")
        run_gate(
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
        print(f"managed-fault-recovery run.py: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
