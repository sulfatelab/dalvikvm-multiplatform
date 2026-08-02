#!/usr/bin/env python3
"""Run the shared Math CriticalNative xint/JIT acceptance matrix."""

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


_TARGETS = {
    "linux-x86_64-gnu",
    "linux-aarch64-gnu",
    "windows-x86_64-msvc",
}
_COMPILE_MARKER = "Windows x64 CompileMethod done success=1 method="
_EXPECTED = [
    "MathCriticalProbe native ceil=true floor=true cases=23 rounds=2000 "
    "checksum=0x2900b87ac0cf269a",
    "MathCriticalProbe OK",
    "main end exception=0",
]
_FORBIDDEN = [
    "AssertionError",
    "ART Win32 VEH",
    "ART Win32 UEF",
    "Check failed",
    "Fatal signal",
    "minidump written",
]


def run_gate(
    *,
    target_id: str,
    dalvikvm: Path,
    boot_jar: Path,
    app_jar: Path,
    work_root: Path,
    icu_data: Path,
    library_dirs: list[Path],
    repetitions: int,
    timeout: int,
    runner: Path | None = None,
    runner_args: list[str] | None = None,
) -> None:
    if target_id not in _TARGETS:
        raise runtime_gate.GateError(
            f"Math CriticalNative is not accepted for {target_id}"
        )
    if repetitions < 1 or timeout < 1:
        raise runtime_gate.GateError("repeat and timeout must be positive")
    work_root = runtime_gate._managed_path(work_root, allow_missing=True)
    if work_root.exists() or work_root.is_symlink():
        runtime_gate._reject_tree_links(work_root)
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True)
    runner_args = [] if runner_args is None else runner_args

    records: list[dict[str, object]] = []
    modes = (
        ("xint", ["-Xint"], {}),
        (
            "jit",
            ["-verbose:jit", "-Xjitwarmupthreshold:0", "-Xjitthreshold:0"],
            {
                "ART_WINDOWS_X64_JIT_FILTER": "MathCriticalProbe",
                "ART_WINDOWS_X64_JIT_LOG_COMPILES": "1",
            }
            if target_id.startswith("windows-")
            else {},
        ),
    )
    for mode, vm_options, environment in modes:
        for iteration in range(1, repetitions + 1):
            case_root = work_root / f"{mode}-{iteration:03d}"
            case_root.mkdir()
            runtime_gate.run_managed(
                target_id=target_id,
                dalvikvm=dalvikvm,
                boot_jar=boot_jar,
                app_jar=app_jar,
                main_class="MathCriticalProbe",
                work_root=case_root,
                icu_data=icu_data,
                library_dirs=library_dirs,
                vm_options=vm_options,
                main_args=[],
                expected=list(_EXPECTED),
                forbidden=list(_FORBIDDEN),
                expected_exit=0,
                timeout=timeout,
                environment_overrides=environment,
                runner=runner,
                runner_args=runner_args,
            )
            output = "\n".join(
                (case_root / name).read_text(
                    encoding="utf-8", errors="replace"
                )
                for name in ("stdout.txt", "stderr.txt")
            )
            compile_records = sum(
                _COMPILE_MARKER in line and "MathCriticalProbe" in line
                for line in output.splitlines()
            )
            if mode == "jit" and target_id.startswith("windows-") and not compile_records:
                raise runtime_gate.GateError(
                    f"Math CriticalNative JIT iteration {iteration} has no compile record"
                )
            nested = json.loads(
                (case_root / "result.json").read_text(encoding="utf-8")
            )
            records.append({
                "mode": mode,
                "iteration": iteration,
                "compile_records": compile_records,
                "runtime": nested,
            })

    dumps = sorted(path.name for path in work_root.rglob("*.dmp"))
    if dumps:
        raise runtime_gate.GateError(f"Math CriticalNative created dumps: {dumps}")
    runtime_gate._reject_tree_links(work_root)
    result = {
        "schema_version": 1,
        "target_id": target_id,
        "requested_repetitions_per_mode": repetitions,
        "completed_cases": len(records),
        "dump_files": dumps,
        "cases": records,
    }
    (work_root / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"Math CriticalNative passed for {target_id}: "
        f"xint={repetitions}, jit={repetitions}, dumps=0"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--dalvikvm", type=Path, required=True)
    parser.add_argument("--boot-jar", type=Path, required=True)
    parser.add_argument("--app-jar", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--icu-data", type=Path, required=True)
    parser.add_argument("--library-dir", type=Path, action="append", default=[])
    parser.add_argument("--repeat", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=180)
    runtime_gate._add_runner_arguments(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        run_gate(
            target_id=args.target_id,
            dalvikvm=args.dalvikvm,
            boot_jar=args.boot_jar,
            app_jar=args.app_jar,
            work_root=args.work_root,
            icu_data=args.icu_data,
            library_dirs=args.library_dir,
            repetitions=args.repeat,
            timeout=args.timeout,
            runner=args.runner,
            runner_args=args.runner_arg,
        )
        return 0
    except (runtime_gate.GateError, OSError, UnicodeError) as exc:
        print(f"math-critical/run.py: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
