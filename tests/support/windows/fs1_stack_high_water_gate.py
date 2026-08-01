#!/usr/bin/env python3
"""Run the instrumented Win32 FS-1 managed matrix without a host shell."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import os
import shutil
import subprocess
import sys


_SUPPORT_ROOT = Path(__file__).parents[1]
if str(_SUPPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_SUPPORT_ROOT))

import runtime_gate  # noqa: E402


def run_gate(
    *,
    target_id: str,
    dalvikvm: Path,
    boot_jar: Path,
    app_jar: Path,
    work_root: Path,
    icu_data: Path,
    jni_dir: Path,
    library_dirs: list[Path],
    validator: Path,
    art_reserve: int,
    timeout: int,
) -> None:
    jni_dir = runtime_gate._managed_path(jni_dir)
    validator = runtime_gate._regular_file(str(validator))
    work_root = runtime_gate._managed_path(work_root, allow_missing=True)
    if work_root.exists() or work_root.is_symlink():
        runtime_gate._reject_tree_links(work_root)
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True)

    modes = (
        (
            "switch",
            {"ART_WINDOWS_X64_JIT": "0", "ART_WINDOWS_X64_NTERP": "0"},
            ["-Xusejit:false"],
        ),
        (
            "nterp",
            {"ART_WINDOWS_X64_JIT": "0", "ART_WINDOWS_X64_NTERP": "1"},
            ["-Xusejit:false"],
        ),
        (
            "jit",
            {
                "ART_WINDOWS_X64_JIT": "1",
                "ART_WINDOWS_X64_NTERP": "1",
                "ART_WINDOWS_X64_JIT_FILTER": "FS1StackHighWaterProbe",
                "ART_WINDOWS_X64_JIT_LOG_COMPILES": "1",
            },
            ["-verbose:jit", "-Xjitwarmupthreshold:0", "-Xjitthreshold:0"],
        ),
    )
    records: list[dict[str, object]] = []
    for mode, environment, mode_options in modes:
        case_root = work_root / mode
        vm_options = [f"-Djava.library.path={jni_dir}", *mode_options]
        if art_reserve == 40960:
            vm_options.append("-XX:ThreadSuspendTimeout=30000")
        runtime_gate.run_managed(
            target_id=target_id,
            dalvikvm=dalvikvm,
            boot_jar=boot_jar,
            app_jar=app_jar,
            main_class="FS1StackHighWaterProbe",
            work_root=case_root,
            icu_data=icu_data,
            library_dirs=[jni_dir, *library_dirs],
            vm_options=vm_options,
            main_args=[mode],
            expected=[
                f"FS1StackHighWaterProbe OK mode={mode} main=2 child=2",
                "main end exception=0",
            ],
            forbidden=[
                "AssertionError",
                "ART Win32 VEH",
                "ART Win32 UEF",
                "minidump written",
            ],
            expected_exit=0,
            timeout=timeout,
            environment_overrides=environment,
        )
        combined = case_root / "combined.txt"
        combined.write_text(
            (case_root / "stdout.txt").read_text(encoding="utf-8")
            + "\n"
            + (case_root / "stderr.txt").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        validation = subprocess.run(
            [
                sys.executable,
                str(validator),
                "--log",
                str(combined),
                "--mode",
                mode,
                "--art-reserve",
                str(art_reserve),
            ],
            cwd=work_root,
            text=True,
            capture_output=True,
            check=False,
            shell=False,
            timeout=60,
        )
        (case_root / "validator-stdout.txt").write_text(
            validation.stdout, encoding="utf-8"
        )
        (case_root / "validator-stderr.txt").write_text(
            validation.stderr, encoding="utf-8"
        )
        if validation.returncode != 0:
            raise runtime_gate.GateError(
                f"FS-1 {mode} validator exited {validation.returncode}: "
                f"{validation.stdout}{validation.stderr}"
            )
        records.append({
            "mode": mode,
            "runtime": json.loads(
                (case_root / "result.json").read_text(encoding="utf-8")
            ),
            "validator_exit": validation.returncode,
        })

    dumps = sorted(path.name for path in work_root.rglob("*.dmp"))
    record = {
        "schema_version": 1,
        "target_id": target_id,
        "build_type": "Debug" if art_reserve == 40960 else "RelWithDebInfo",
        "art_reserve": art_reserve,
        "validator": {
            "name": validator.name,
            "sha256": runtime_gate._sha256(validator),
        },
        "requested_modes": len(modes),
        "completed_modes": len(records),
        "dump_files": dumps,
        "cases": records,
    }
    temporary = work_root / "result.json.tmp"
    temporary.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, work_root / "result.json")
    if dumps:
        raise runtime_gate.GateError(f"FS-1 created dump files: {dumps}")
    print(
        f"FS-1 stack high-water passed for {target_id}: "
        f"modes={len(records)}, art_reserve={art_reserve}, dumps=0"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--dalvikvm", type=Path, required=True)
    parser.add_argument("--boot-jar", type=Path, required=True)
    parser.add_argument("--app-jar", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--icu-data", type=Path, required=True)
    parser.add_argument("--jni-dir", type=Path, required=True)
    parser.add_argument("--library-dir", type=Path, action="append", default=[])
    parser.add_argument("--validator", type=Path, required=True)
    parser.add_argument("--art-reserve", type=int, required=True)
    parser.add_argument("--timeout", type=int, default=180)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.art_reserve < 1 or args.timeout < 1:
            raise runtime_gate.GateError("art reserve and timeout must be positive")
        run_gate(
            target_id=args.target_id,
            dalvikvm=args.dalvikvm,
            boot_jar=args.boot_jar,
            app_jar=args.app_jar,
            work_root=args.work_root,
            icu_data=args.icu_data,
            jni_dir=args.jni_dir,
            library_dirs=args.library_dir,
            validator=args.validator,
            art_reserve=args.art_reserve,
            timeout=args.timeout,
        )
        return 0
    except (runtime_gate.GateError, OSError, UnicodeError) as exc:
        print(f"fs1_stack_high_water_gate.py: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
