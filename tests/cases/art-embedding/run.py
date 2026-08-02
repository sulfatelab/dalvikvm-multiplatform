#!/usr/bin/env python3
"""Run the native Windows ART embedding contract without a host shell."""

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


_TARGET_ID = "windows-x86_64-msvc"
_REQUIRED_RUNTIME_DLLS = frozenset({
    "art.dll",
    "icu_jni.dll",
    "javacore.dll",
    "openjdk.dll",
})
_EXPECTED = (
    "WIN32_ART_EMBED start",
    "WIN32_ART_EMBED runtime_create result=0",
    "WIN32_ART_EMBED predecessor_uef armed=1",
    "WIN32_ART_EMBED predecessor_uef resumed calls=1",
    "WIN32_ART_EMBED frame_seh armed phase=runtime-active",
    "WIN32_ART_EMBED frame_seh caught phase=runtime-active",
    "WIN32_ART_EMBED late_uef installed predecessor_is_art=1",
    "WIN32_ART_EMBED runtime_destroy detach=0 destroy=0",
    "WIN32_ART_EMBED teardown late_uef_preserved=1",
    "WIN32_ART_EMBED frame_seh armed phase=runtime-unloaded",
    "WIN32_ART_EMBED frame_seh caught phase=runtime-unloaded",
    "WIN32_ART_EMBED result foreign_veh_calls=3 predecessor_uef_calls=1 "
    "late_uef_calls=0 frame_seh_calls=2",
    "WIN32_ART_EMBED PASS",
    "ART Win32 crash: minidump written to ",
)
_FORBIDDEN = (
    "WIN32_ART_EMBED FAIL",
    "WIN32_ART_EMBED late_uef unexpected_call=1",
    "Check failed",
    "Fatal signal",
    "ART Win32 crash: CreateFile dump failed",
    "ART Win32 crash: MiniDumpWriteDump failed",
)
_EXACT_COUNTS = {
    "WIN32_ART_EMBED foreign_veh search=1": 3,
    "WIN32_ART_EMBED predecessor_uef continue=1": 1,
    "WIN32_ART_EMBED frame_seh caught phase=runtime-active": 1,
    "WIN32_ART_EMBED frame_seh caught phase=runtime-unloaded": 1,
}


def _validate_output(output: str) -> tuple[list[str], list[str], list[str]]:
    missing = [marker for marker in _EXPECTED if marker not in output]
    forbidden = [marker for marker in _FORBIDDEN if marker in output]
    count_errors = [
        f"{marker!r}: expected {expected}, found {output.count(marker)}"
        for marker, expected in _EXACT_COUNTS.items()
        if output.count(marker) != expected
    ]
    return missing, forbidden, count_errors


def _stage_runtime_dlls(library_dirs: list[Path], destination: Path) -> list[Path]:
    staged: dict[str, Path] = {}
    for library_dir in library_dirs:
        for candidate in sorted(library_dir.iterdir(), key=lambda path: path.name.lower()):
            if candidate.suffix.lower() != ".dll":
                continue
            source = runtime_gate._regular_file(str(candidate))
            key = source.name.lower()
            if key in staged:
                raise runtime_gate.GateError(
                    f"duplicate runtime DLL basename: {source.name}"
                )
            target = destination / source.name
            shutil.copyfile(source, target)
            staged[key] = runtime_gate._regular_file(str(target))
    missing = sorted(_REQUIRED_RUNTIME_DLLS - staged.keys())
    if missing:
        raise runtime_gate.GateError(
            f"runtime DLL closure is missing required files: {missing}"
        )
    return [staged[name] for name in sorted(staged)]


def run_gate(
    *,
    target_id: str,
    probe: Path,
    boot_jar: Path,
    work_root: Path,
    icu_data: Path,
    library_dirs: list[Path],
    repetitions: int,
    timeout: int,
) -> None:
    if target_id != _TARGET_ID:
        raise runtime_gate.GateError(
            f"ART embedding has no accepted runner for {target_id}"
        )
    if repetitions < 1 or timeout < 1:
        raise runtime_gate.GateError("repeat and timeout must be positive")

    probe = runtime_gate._regular_file(str(probe))
    boot_jar = runtime_gate._regular_file(str(boot_jar))
    icu_data = runtime_gate._regular_file(str(icu_data))
    library_dirs = [runtime_gate._managed_path(path) for path in library_dirs]
    work_root = runtime_gate._managed_path(work_root, allow_missing=True)
    if work_root.exists() or work_root.is_symlink():
        runtime_gate._reject_tree_links(work_root)
        shutil.rmtree(work_root)

    binary_root = work_root / "bin"
    runs_root = work_root / "runs"
    binary_root.mkdir(parents=True)
    runs_root.mkdir()
    staged_probe = binary_root / probe.name
    shutil.copyfile(probe, staged_probe)
    runtime_gate._regular_file(str(staged_probe))
    staged_libraries = _stage_runtime_dlls(library_dirs, binary_root)

    base_environment = os.environ.copy()
    system_root = Path(base_environment.get("SystemRoot", r"C:\Windows"))
    base_environment["PATH"] = ";".join(
        [str(binary_root), str(system_root / "System32")]
    )

    records: list[dict[str, object]] = []
    failure: str | None = None
    for repetition in range(1, repetitions + 1):
        repetition_root = runs_root / f"{repetition:03d}"
        run_root = repetition_root / "run"
        for directory in (
            run_root,
            run_root / "crash",
            run_root / "data",
            run_root / "icu",
            run_root / "tmp",
        ):
            directory.mkdir(parents=True, exist_ok=True)
        staged_boot = run_root / "boot.jar"
        staged_icu = run_root / "icu" / icu_data.name
        shutil.copyfile(boot_jar, staged_boot)
        shutil.copyfile(icu_data, staged_icu)
        runtime_gate._regular_file(str(staged_boot))
        runtime_gate._regular_file(str(staged_icu))
        environment = base_environment.copy()
        environment.update({
            "ANDROID_ROOT": str(run_root),
            "ANDROID_ART_ROOT": str(run_root),
            "ANDROID_I18N_ROOT": str(run_root),
            "ANDROID_DATA": str(run_root / "data"),
            "ICU_DATA": str(run_root / "icu"),
            "TMP": str(run_root / "tmp"),
            "TEMP": str(run_root / "tmp"),
            "TMPDIR": str(run_root / "tmp"),
        })
        try:
            result = subprocess.run(
                [str(staged_probe)],
                cwd=repetition_root,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
                shell=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            records.append({
                "repetition": repetition,
                "actual_exit": None,
                "timed_out": True,
                "missing_markers": list(_EXPECTED),
                "forbidden_markers": [],
                "count_errors": [],
                "dump_files": [],
                "dump_count_error": "expected one intentional dump, found 0",
            })
            failure = f"repetition {repetition} timed out after {timeout} seconds"
            break

        (work_root / f"stdout-{repetition:03d}.txt").write_text(
            result.stdout, encoding="utf-8"
        )
        (work_root / f"stderr-{repetition:03d}.txt").write_text(
            result.stderr, encoding="utf-8"
        )
        output = result.stdout + "\n" + result.stderr
        missing, forbidden, count_errors = _validate_output(output)
        repetition_dumps = sorted(
            path.relative_to(work_root).as_posix()
            for path in repetition_root.rglob("*.dmp")
        )
        dump_count_error = (
            None
            if len(repetition_dumps) == 1
            else f"expected one intentional dump, found {len(repetition_dumps)}"
        )
        records.append({
            "repetition": repetition,
            "actual_exit": result.returncode,
            "timed_out": False,
            "missing_markers": missing,
            "forbidden_markers": forbidden,
            "count_errors": count_errors,
            "dump_files": repetition_dumps,
            "dump_count_error": dump_count_error,
        })
        if (
            result.returncode != 0
            or missing
            or forbidden
            or count_errors
            or dump_count_error is not None
        ):
            failure = (
                f"repetition {repetition} failed: exit={result.returncode}, "
                f"missing={missing}, forbidden={forbidden}, counts={count_errors}, "
                f"dump={dump_count_error}"
            )
            break

    dumps = sorted(
        path.relative_to(work_root).as_posix()
        for path in work_root.rglob("*.dmp")
    )
    runtime_gate._reject_tree_links(work_root)
    record = {
        "schema_version": 1,
        "target_id": target_id,
        "probe": {"name": probe.name, "sha256": runtime_gate._sha256(probe)},
        "boot_jar": {
            "name": boot_jar.name,
            "sha256": runtime_gate._sha256(boot_jar),
        },
        "runtime_libraries": [
            {"name": path.name, "sha256": runtime_gate._sha256(path)}
            for path in staged_libraries
        ],
        "requested_repetitions": repetitions,
        "completed_repetitions": sum(
            item["actual_exit"] == 0
            and not item["timed_out"]
            and not item["missing_markers"]
            and not item["forbidden_markers"]
            and not item["count_errors"]
            and item["dump_count_error"] is None
            for item in records
        ),
        "dump_files": dumps,
        "runs": records,
    }
    temporary = work_root / "result.json.tmp"
    temporary.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, work_root / "result.json")
    if failure is not None:
        raise runtime_gate.GateError(failure)
    print(
        f"ART embedding passed for {target_id}: "
        f"repetitions={repetitions}, intentional_dumps={len(dumps)}"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--boot-jar", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--icu-data", type=Path, required=True)
    parser.add_argument("--library-dir", type=Path, action="append", default=[])
    parser.add_argument("--repeat", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=180)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        run_gate(
            target_id=args.target_id,
            probe=args.probe,
            boot_jar=args.boot_jar,
            work_root=args.work_root,
            icu_data=args.icu_data,
            library_dirs=args.library_dir,
            repetitions=args.repeat,
            timeout=args.timeout,
        )
    except runtime_gate.GateError as exc:
        print(f"art-embedding: error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
