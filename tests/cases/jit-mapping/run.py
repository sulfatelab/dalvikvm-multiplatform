#!/usr/bin/env python3
"""Run the W-025 64-MiB and 1-GiB ART JIT mapping audits."""

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


def _stage_probe(source: Path, work_root: Path) -> None:
    source = runtime_gate._regular_file(str(source))
    for name in ("libw025jitmappingprobe.dll", "w025jitmappingprobe.dll"):
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

    records: list[dict[str, object]] = []
    for capacity in (64, 1024):
        case_root = work_root / f"capacity-{capacity}m"
        case_root.mkdir()
        _stage_probe(probe, case_root)
        capacity_bytes = capacity * 1024 * 1024
        runtime_gate.run_managed(
            target_id=target_id,
            dalvikvm=dalvikvm,
            boot_jar=boot_jar,
            app_jar=app_jar,
            main_class="W025JitMappingProbe",
            work_root=case_root,
            icu_data=icu_data,
            library_dirs=[case_root, *library_dirs],
            vm_options=[
                "-Xjitwarmupthreshold:1",
                "-Xjitthreshold:1",
                f"-Xjitmaxsize:{capacity}M",
                "-Djava.library.path=.",
            ],
            main_args=[str(capacity), "false"],
            expected=[
                f"Windows x64 JIT dual-view (J-2) created: capacity={capacity}MiB",
                "roles primary_data=R primary_code=RX alias_data=RW alias_code=RW "
                f"type=MEM_MAPPED rwx=0 contiguous_low=1 capacity_bytes={capacity_bytes}",
                "primary_name_length=0",
                "W025_JIT_MAPPING_PASS",
                "success=1 method=int W025JitMappingProbe.target(int)",
                f"W025JitMappingProbe PASS capacity_bytes={capacity_bytes} require_cfg=false",
                "main end exception=0",
            ],
            forbidden=[
                "W025_JIT_MAPPING_FAIL",
                "AssertionError",
                "ART Win32 VEH",
                "ART Win32 UEF",
                "minidump written",
                "falling back to single-view (J-1)",
            ],
            expected_exit=0,
            timeout=timeout,
            environment_overrides={
                "ART_WINDOWS_X64_JIT_FILTER": "W025JitMappingProbe",
                "ART_WINDOWS_X64_JIT_LOG_COMPILES": "1",
            },
        )
        dumps = sorted(path.name for path in case_root.rglob("*.dmp"))
        if dumps:
            raise runtime_gate.GateError(
                f"JIT mapping capacity {capacity} MiB created dumps: {dumps}"
            )
        records.append({
            "capacity_mib": capacity,
            "capacity_bytes": capacity_bytes,
            "runtime": json.loads((case_root / "result.json").read_text(encoding="utf-8")),
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
    print(f"W-025 JIT mapping passed for {target_id}: capacities=64,1024 MiB")


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
    parser.add_argument("--timeout", type=int, default=600)
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
        print(f"jit-mapping run.py: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
