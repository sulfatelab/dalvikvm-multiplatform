#!/usr/bin/env python3
"""Run the W-025 default-J-2 collection/reuse/unwind stress gate."""

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


_SUMMARY = (
    "W025_JIT3_PASS methods=24 managed=16 jni=8 unique_allocations=24 "
    "cycles=8 collections=8 compilations=216 exact_reuse=192"
)


def _stage_probe(source: Path, work_root: Path) -> None:
    source = runtime_gate._regular_file(str(source))
    for name in (
        "libw025jitlifecyclestressprobe.dll",
        "w025jitlifecyclestressprobe.dll",
    ):
        destination = work_root / name
        shutil.copyfile(source, destination)
        runtime_gate._regular_file(str(destination))


def run_gate(
    *,
    target_id: str,
    probe: Path,
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
    _stage_probe(probe, work_root)

    runtime_gate.run_managed(
        target_id=target_id,
        dalvikvm=dalvikvm,
        boot_jar=boot_jar,
        app_jar=app_jar,
        main_class="W025JitLifecycleStressProbe",
        work_root=work_root,
        icu_data=icu_data,
        library_dirs=[work_root, *library_dirs],
        vm_options=[
            "-Xjitwarmupthreshold:65535",
            "-Xjitthreshold:65535",
            "-Xjitinitialsize:4M",
            "-Xjitmaxsize:16M",
            "-XX:DumpJITInfoOnShutdown",
            "-Djava.library.path=.",
        ],
        main_args=["8"],
        expected=[
            "Windows x64 JIT dual-view (J-2) created: capacity=16MiB",
            _SUMMARY,
            "missing_live=0 stale_dead=0 unwind_failures=0",
            "callback_tables=0",
            "jni_values=pass",
            "W025JitLifecycleStressProbe PASS cycles=8",
            "main end exception=0",
        ],
        forbidden=[
            "W025_JIT3_FAIL",
            "AssertionError",
            "ART Win32 VEH",
            "ART Win32 UEF",
            "minidump written",
            "Check failed",
            "Fatal signal",
            "falling back to single-view (J-1)",
        ],
        expected_exit=0,
        timeout=timeout,
        environment_overrides={
            "ART_WINDOWS_X64_JIT_FILTER": "W025JitLifecycleStressProbe",
        },
    )
    dumps = sorted(path.name for path in work_root.rglob("*.dmp"))
    temp_files = sorted(
        path.name for path in (work_root / "runtime" / "tmp").rglob("*") if path.is_file()
    )
    if dumps or temp_files:
        raise runtime_gate.GateError(
            f"JIT stress left dumps or temporary files: dumps={dumps}, temp={temp_files}"
        )
    record = {
        "schema_version": 1,
        "target_id": target_id,
        "cycles": 8,
        "collections": 8,
        "compilations": 216,
        "exact_reuse": 192,
        "dump_files": dumps,
        "temporary_files": temp_files,
        "runtime": json.loads((work_root / "result.json").read_text(encoding="utf-8")),
    }
    (work_root / "result.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"W-025 JIT lifecycle stress passed for {target_id}: "
        "cycles=8, collections=8, compilations=216, exact_reuse=192"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--dalvikvm", type=Path, required=True)
    parser.add_argument("--boot-jar", type=Path, required=True)
    parser.add_argument("--app-jar", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--icu-data", type=Path, required=True)
    parser.add_argument("--library-dir", type=Path, action="append", default=[])
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    try:
        if args.timeout < 1:
            raise runtime_gate.GateError("timeout must be positive")
        run_gate(
            target_id=args.target_id,
            probe=args.probe,
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
        print(f"jit-lifecycle-stress run.py: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
