#!/usr/bin/env python3
"""Run the W-025 JIT unwind invalidation/collection/reuse gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import sys


_SUPPORT_ROOT = Path(__file__).parents[2] / "support"
if str(_SUPPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_SUPPORT_ROOT))

import runtime_gate  # noqa: E402


_FORBIDDEN = (
    "Windows x64 JIT unwind lifecycle FAIL",
    "ART Win32 VEH",
    "ART Win32 UEF",
    "minidump written",
    "Check failed",
    "Fatal signal",
)


def _stage_probe(source: Path, work_root: Path) -> None:
    source = runtime_gate._regular_file(str(source))
    for name in ("libjitunwindlifecycleprobe.dll", "jitunwindlifecycleprobe.dll"):
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
        main_class="JitUnwindLifecycleProbe",
        work_root=work_root,
        icu_data=icu_data,
        library_dirs=[work_root, *library_dirs],
        vm_options=[
            "-Xjitwarmupthreshold:1",
            "-Xjitthreshold:1",
            "-Xjitinitialsize:4M",
            "-Xjitmaxsize:16M",
            "-XX:DumpJITInfoOnShutdown",
            "-Djava.library.path=.",
        ],
        main_args=[],
        expected=[
            "Windows x64 JIT dual-view (J-2) created",
            "invalidated=present collected=absent reused=yes recompiled=present",
            "JitUnwindLifecycleProbe OK result=",
            "main end exception=0",
        ],
        forbidden=list(_FORBIDDEN),
        expected_exit=0,
        timeout=timeout,
        environment_overrides={
            "ART_WINDOWS_X64_JIT_FILTER": "JitUnwindLifecycleProbe",
        },
    )
    combined = (
        (work_root / "stdout.txt").read_text(encoding="utf-8")
        + "\n"
        + (work_root / "stderr.txt").read_text(encoding="utf-8")
    )
    matches = re.findall(
        r"Total number of JIT code cache collections: ([0-9]+)", combined
    )
    if not matches or int(matches[-1]) < 1:
        raise runtime_gate.GateError("JIT lifecycle recorded no code-cache collection")
    dumps = sorted(path.name for path in work_root.rglob("*.dmp"))
    temp_files = sorted(
        path.name for path in (work_root / "runtime" / "tmp").rglob("*") if path.is_file()
    )
    if dumps or temp_files:
        raise runtime_gate.GateError(
            f"JIT lifecycle left dumps or temporary files: dumps={dumps}, temp={temp_files}"
        )
    record = {
        "schema_version": 1,
        "target_id": target_id,
        "collections": int(matches[-1]),
        "dump_files": dumps,
        "temporary_files": temp_files,
        "runtime": json.loads((work_root / "result.json").read_text(encoding="utf-8")),
    }
    (work_root / "result.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"W-025 JIT unwind lifecycle passed for {target_id}: "
        f"collections={record['collections']}, dumps=0"
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
    parser.add_argument("--timeout", type=int, default=300)
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
        print(f"jit-unwind-lifecycle run.py: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
