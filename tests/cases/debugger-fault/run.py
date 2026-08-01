#!/usr/bin/env python3
"""Run W-010 debugger continuation checks in an isolated runtime directory."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


_SUPPORT_ROOT = Path(__file__).parents[2] / "support"
if str(_SUPPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_SUPPORT_ROOT))

import runtime_gate  # noqa: E402


_FORBIDDEN = ("ART Win32 VEH", "ART Win32 UEF", "minidump written")


def _copy(source: Path, destination: Path) -> None:
    source = runtime_gate._regular_file(str(source))
    destination.parent.mkdir(parents=True, exist_ok=True)
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
    probe = runtime_gate._regular_file(str(probe))
    dalvikvm = runtime_gate._regular_file(str(dalvikvm))
    work_root = runtime_gate._managed_path(work_root, allow_missing=True)
    if work_root.exists() or work_root.is_symlink():
        runtime_gate._reject_tree_links(work_root)
        shutil.rmtree(work_root)
    (work_root / "run" / "data").mkdir(parents=True)
    (work_root / "run" / "icu").mkdir()
    (work_root / "run" / "crash").mkdir()
    _copy(probe, work_root / probe.name)
    _copy(boot_jar, work_root / "run" / "boot.jar")
    _copy(app_jar, work_root / "run" / "w010managedfaultprobe.jar")
    _copy(icu_data, work_root / "run" / "icu" / Path(icu_data).name)

    environment = os.environ.copy()
    system_root = environment.get("SystemRoot", r"C:\Windows")
    environment.update({
        "ANDROID_ROOT": str(work_root / "run"),
        "ANDROID_ART_ROOT": str(work_root / "run"),
        "ANDROID_I18N_ROOT": str(work_root / "run"),
        "ANDROID_DATA": str(work_root / "run" / "data"),
        "ICU_DATA": str(work_root / "run" / "icu"),
        "ART_WINDOWS_X64_QUICK_INVOKE": "1",
        "ART_WINDOWS_X64_JIT": "1",
        "ART_WINDOWS_X64_NTERP": "1",
        "ART_WINDOWS_X64_JIT_FILTER": "W010ManagedFaultProbe",
        "ART_WINDOWS_X64_JIT_LOG_COMPILES": "1",
        "PATH": os.pathsep.join([
            str(work_root),
            *(str(runtime_gate._managed_path(path)) for path in library_dirs),
            str(Path(system_root) / "System32"),
        ]),
    })
    cases = {
        "npe": (
            "WIN32_DEBUGGER_PROBE first_chance_av stop=1 continue=DBG_EXCEPTION_NOT_HANDLED",
            "WIN32_DEBUGGER_PROBE result mode=npe child_exit=0",
            "first_stack_overflow=0",
            "WIN32_DEBUGGER_PROBE PASS mode=npe",
            "W010ManagedFaultProbe NPE OK read=64 write=64 recovery=128 gc=16",
        ),
        "so": (
            "WIN32_DEBUGGER_PROBE result mode=so child_exit=0 first_av=0",
            "first_stack_overflow=0",
            "first_hardware=0",
            "WIN32_DEBUGGER_PROBE PASS mode=so",
            "W010ManagedFaultProbe SO OK main=2 child=2 recovery=4 gc=4",
        ),
    }
    records: list[dict[str, object]] = []
    for mode, expected in cases.items():
        try:
            result = subprocess.run(
                [str(work_root / probe.name), str(dalvikvm), mode],
                cwd=work_root,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
                shell=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise runtime_gate.GateError(
                f"debugger mode {mode} timed out after {timeout} seconds"
            ) from exc
        (work_root / f"{mode}.stdout.txt").write_text(result.stdout, encoding="utf-8")
        (work_root / f"{mode}.stderr.txt").write_text(result.stderr, encoding="utf-8")
        output = result.stdout + "\n" + result.stderr
        missing = [marker for marker in expected if marker not in output]
        present_forbidden = [marker for marker in _FORBIDDEN if marker in output]
        records.append({
            "mode": mode,
            "actual_exit": result.returncode,
            "missing_markers": missing,
            "forbidden_markers": present_forbidden,
        })
        if result.returncode != 0 or missing or present_forbidden:
            raise runtime_gate.GateError(
                f"debugger mode {mode} failed: exit={result.returncode}, "
                f"missing={missing}, forbidden={present_forbidden}"
            )

    dumps = sorted(path.name for path in (work_root / "run" / "crash").glob("*.dmp"))
    if dumps:
        raise runtime_gate.GateError(f"debugger continuation created dumps: {dumps}")
    record = {
        "schema_version": 1,
        "target_id": target_id,
        "probe": {"name": probe.name, "sha256": runtime_gate._sha256(probe)},
        "completed_cases": len(records),
        "dump_files": dumps,
        "cases": records,
    }
    (work_root / "result.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"W-010 debugger gate passed for {target_id}: cases={len(records)}, dumps=0")


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
    parser.add_argument("--timeout", type=int, default=180)
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
        print(f"debugger-fault run.py: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
