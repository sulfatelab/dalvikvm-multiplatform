#!/usr/bin/env python3
"""Run the W-025 CFG and dynamic-code process-policy gates."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys


_SUPPORT_ROOT = Path(__file__).parents[2] / "support"
if str(_SUPPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_SUPPORT_ROOT))

import runtime_gate  # noqa: E402


_COMMON_FORBIDDEN = (
    "W025_POLICY_LAUNCHER_FAIL",
    "W025_SECTION_POLICY_FAIL",
    "W025_JIT_MAPPING_FAIL",
    "ART Win32 VEH",
    "ART Win32 UEF",
    "minidump written",
    "Check failed",
    "Fatal signal",
    "falling back to single-view (J-1)",
)


def _copy_regular(source: Path, destination: Path) -> Path:
    source = runtime_gate._regular_file(str(source))
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return runtime_gate._regular_file(str(destination))


def _stage_inputs(
    *,
    work_root: Path,
    launcher: Path,
    section_probe: Path,
    mapping_probe: Path,
    boot_jar: Path,
    mapping_jar: Path,
    hello_jar: Path,
    icu_data: Path,
) -> dict[str, Path]:
    inputs = work_root / "inputs"
    return {
        "launcher": _copy_regular(launcher, inputs / launcher.name),
        "section_probe": _copy_regular(section_probe, inputs / section_probe.name),
        "mapping_probe": _copy_regular(mapping_probe, inputs / mapping_probe.name),
        "boot_jar": _copy_regular(boot_jar, inputs / "boot.jar"),
        "mapping_jar": _copy_regular(mapping_jar, inputs / "mapping.jar"),
        "hello_jar": _copy_regular(hello_jar, inputs / "hello.jar"),
        "icu_data": _copy_regular(icu_data, inputs / icu_data.name),
    }


def _runtime_layout(case_root: Path, icu_data: Path) -> Path:
    runtime_root = case_root / "runtime"
    (runtime_root / "data").mkdir(parents=True)
    (runtime_root / "icu").mkdir()
    (runtime_root / "tmp").mkdir()
    _copy_regular(icu_data, runtime_root / "icu" / icu_data.name)
    return runtime_root


def _environment(
    *,
    runtime_root: Path | None,
    library_dirs: list[Path],
    overrides: dict[str, str] | None = None,
) -> dict[str, str]:
    environment = os.environ.copy()
    checked_library_dirs = [runtime_gate._managed_path(path) for path in library_dirs]
    if os.name == "nt":
        system_root = environment.get("SystemRoot", r"C:\Windows")
        environment["PATH"] = os.pathsep.join(
            [
                *(str(path) for path in checked_library_dirs),
                str(Path(system_root) / "System32"),
            ]
        )
    elif checked_library_dirs:
        environment["LD_LIBRARY_PATH"] = os.pathsep.join(
            str(path) for path in checked_library_dirs
        )
    if runtime_root is not None:
        environment.update({
            "ANDROID_ROOT": str(runtime_root),
            "ANDROID_ART_ROOT": str(runtime_root),
            "ANDROID_I18N_ROOT": str(runtime_root),
            "ANDROID_DATA": str(runtime_root / "data"),
            "ICU_DATA": str(runtime_root / "icu"),
            "TMP": str(runtime_root / "tmp"),
            "TEMP": str(runtime_root / "tmp"),
            "TMPDIR": str(runtime_root / "tmp"),
        })
    for name, value in (overrides or {}).items():
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None:
            raise runtime_gate.GateError(f"invalid environment variable name: {name!r}")
        if not isinstance(value, str) or "\0" in value:
            raise runtime_gate.GateError(f"invalid environment value for {name}")
        environment[name] = value
    return environment


def _managed_arguments(
    *,
    boot_jar: Path,
    runtime_root: Path,
    app_jar: Path,
    main_class: str,
    vm_options: list[str],
    main_args: list[str],
) -> list[str]:
    return [
        f"-Xbootclasspath:{boot_jar}",
        f"-Xbootclasspath-locations:{boot_jar}",
        f"-Ximage:{runtime_root / 'nonexistent-boot-image'}",
        "-XjdwpProvider:none",
        "-Xms64m",
        "-Xmx512m",
        *vm_options,
        "-cp",
        str(app_jar),
        main_class,
        *main_args,
    ]


def _run_case(
    *,
    target_id: str,
    name: str,
    launcher: Path,
    policy: str,
    child: Path,
    child_arguments: list[str],
    case_root: Path,
    environment: dict[str, str],
    expected: list[str],
    forbidden: list[str],
    timeout: int,
) -> dict[str, object]:
    launcher = runtime_gate._regular_file(str(launcher))
    child = runtime_gate._regular_file(str(child))
    command = [
        str(launcher),
        policy,
        "zero",
        str(child),
        *child_arguments,
    ]
    try:
        result = subprocess.run(
            command,
            cwd=case_root,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            shell=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise runtime_gate.GateError(
            f"W-025 policy case {name} timed out after {timeout} seconds"
        ) from exc
    (case_root / "stdout.txt").write_text(result.stdout, encoding="utf-8")
    (case_root / "stderr.txt").write_text(result.stderr, encoding="utf-8")
    combined = result.stdout + "\n" + result.stderr
    missing = [marker for marker in expected if marker not in combined]
    present_forbidden = [marker for marker in forbidden if marker in combined]
    record: dict[str, object] = {
        "name": name,
        "target_id": target_id,
        "policy": policy,
        "actual_exit": result.returncode,
        "missing_markers": missing,
        "forbidden_markers": present_forbidden,
        "child": child.name,
        "child_argument_count": len(child_arguments),
    }
    if result.returncode != 0 or missing or present_forbidden:
        tail = "\n".join(combined.splitlines()[-100:])
        raise runtime_gate.GateError(
            f"W-025 policy case {name} failed: exit={result.returncode}, "
            f"missing={missing}, forbidden={present_forbidden}\n{tail}"
        )
    return record


def run_gate(
    *,
    target_id: str,
    launcher: Path,
    section_probe: Path,
    mapping_probe: Path,
    dalvikvm: Path,
    boot_jar: Path,
    mapping_jar: Path,
    hello_jar: Path,
    work_root: Path,
    icu_data: Path,
    library_dirs: list[Path],
    timeout: int,
) -> None:
    dalvikvm = runtime_gate._regular_file(str(dalvikvm))
    work_root = runtime_gate._managed_path(work_root, allow_missing=True)
    if work_root.exists() or work_root.is_symlink():
        runtime_gate._reject_tree_links(work_root)
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True)
    staged = _stage_inputs(
        work_root=work_root,
        launcher=launcher,
        section_probe=section_probe,
        mapping_probe=mapping_probe,
        boot_jar=boot_jar,
        mapping_jar=mapping_jar,
        hello_jar=hello_jar,
        icu_data=icu_data,
    )

    records: list[dict[str, object]] = []
    section_root = work_root / "cfg-section"
    section_root.mkdir()
    records.append(_run_case(
        target_id=target_id,
        name="cfg-section-call",
        launcher=staged["launcher"],
        policy="cfg",
        child=staged["section_probe"],
        child_arguments=["--cfg-call"],
        case_root=section_root,
        environment=_environment(runtime_root=None, library_dirs=library_dirs),
        expected=[
            "W025_POLICY_CHILD policy=cfg",
            "cfg_enabled=1",
            "W025_SECTION_MAPPING label=default",
            "execute=1",
            "W025_SECTION_POLICY_PASS mode=cfg-call",
            "W025_POLICY_LAUNCHER_PASS policy=cfg child_exit=0 expected=zero",
        ],
        forbidden=list(_COMMON_FORBIDDEN),
        timeout=timeout,
    ))

    cfg_root = work_root / "cfg-managed-mapping"
    cfg_root.mkdir()
    cfg_runtime = _runtime_layout(cfg_root, staged["icu_data"])
    for name in ("libw025jitmappingprobe.dll", "w025jitmappingprobe.dll"):
        _copy_regular(staged["mapping_probe"], cfg_root / name)
    cfg_args = _managed_arguments(
        boot_jar=staged["boot_jar"],
        runtime_root=cfg_runtime,
        app_jar=staged["mapping_jar"],
        main_class="W025JitMappingProbe",
        vm_options=[
            "-Xjitwarmupthreshold:1",
            "-Xjitthreshold:1",
            "-Xjitmaxsize:64M",
            "-Djava.library.path=.",
        ],
        main_args=["64", "true"],
    )
    records.append(_run_case(
        target_id=target_id,
        name="cfg-managed-mapping",
        launcher=staged["launcher"],
        policy="cfg",
        child=dalvikvm,
        child_arguments=cfg_args,
        case_root=cfg_root,
        environment=_environment(
            runtime_root=cfg_runtime,
            library_dirs=[cfg_root, *library_dirs],
            overrides={
                "ART_WINDOWS_X64_JIT_FILTER": "W025JitMappingProbe",
                "ART_WINDOWS_X64_JIT_LOG_COMPILES": "1",
            },
        ),
        expected=[
            "W025_POLICY_CHILD policy=cfg",
            "cfg_enabled=1",
            "Windows x64 JIT dual-view (J-2) created: capacity=64MiB",
            "W025_JIT_MAPPING_PASS",
            "success=1 method=int W025JitMappingProbe.target(int)",
            "W025JitMappingProbe PASS capacity_bytes=67108864 require_cfg=true",
            "W025_POLICY_LAUNCHER_PASS policy=cfg child_exit=0 expected=zero",
        ],
        forbidden=list(_COMMON_FORBIDDEN),
        timeout=timeout,
    ))

    dynamic_root = work_root / "dynamic-code-jit"
    dynamic_root.mkdir()
    dynamic_runtime = _runtime_layout(dynamic_root, staged["icu_data"])
    dynamic_args = _managed_arguments(
        boot_jar=staged["boot_jar"],
        runtime_root=dynamic_runtime,
        app_jar=staged["hello_jar"],
        main_class="Hello",
        vm_options=[],
        main_args=[],
    )
    records.append(_run_case(
        target_id=target_id,
        name="dynamic-code-jit-fail-closed",
        launcher=staged["launcher"],
        policy="dynamic",
        child=dalvikvm,
        child_arguments=dynamic_args,
        case_root=dynamic_root,
        environment=_environment(
            runtime_root=dynamic_runtime,
            library_dirs=library_dirs,
        ),
        expected=[
            "W025_POLICY_CHILD policy=dynamic dynamic_prohibit=1",
            "Windows x64 JIT dual-view construction failed:",
            "failed: 1655",
            "Failed to create JIT Code Cache:",
            "Hello from dalvikvm!",
            "main end exception=0",
            "W025_POLICY_LAUNCHER_PASS policy=dynamic child_exit=0 expected=zero",
        ],
        forbidden=[*_COMMON_FORBIDDEN, "JitCodeCache::Create OK"],
        timeout=timeout,
    ))

    nojit_root = work_root / "dynamic-code-nojit"
    nojit_root.mkdir()
    nojit_runtime = _runtime_layout(nojit_root, staged["icu_data"])
    nojit_args = _managed_arguments(
        boot_jar=staged["boot_jar"],
        runtime_root=nojit_runtime,
        app_jar=staged["hello_jar"],
        main_class="Hello",
        vm_options=["-Xusejit:false"],
        main_args=[],
    )
    records.append(_run_case(
        target_id=target_id,
        name="dynamic-code-nojit-control",
        launcher=staged["launcher"],
        policy="dynamic",
        child=dalvikvm,
        child_arguments=nojit_args,
        case_root=nojit_root,
        environment=_environment(
            runtime_root=nojit_runtime,
            library_dirs=library_dirs,
        ),
        expected=[
            "W025_POLICY_CHILD policy=dynamic dynamic_prohibit=1",
            "Hello from dalvikvm!",
            "main end exception=0",
            "W025_POLICY_LAUNCHER_PASS policy=dynamic child_exit=0 expected=zero",
        ],
        forbidden=[
            *_COMMON_FORBIDDEN,
            "JitCodeCache::Create OK",
            "Failed to create JIT Code Cache:",
            "Windows x64 JIT dual-view (J-2) created:",
        ],
        timeout=timeout,
    ))

    dumps = sorted(path.name for path in work_root.rglob("*.dmp"))
    temporary_files = sorted(
        path.name
        for runtime_tmp in work_root.rglob("runtime/tmp")
        for path in runtime_tmp.rglob("*")
        if path.is_file()
    )
    reparse_paths: list[str] = []
    for current, directories, files in os.walk(work_root, followlinks=False):
        for name in (*directories, *files):
            path = Path(current) / name
            info = os.lstat(path)
            attributes = getattr(info, "st_file_attributes", 0)
            reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            if stat.S_ISLNK(info.st_mode) or attributes & reparse:
                reparse_paths.append(path.name)
    if dumps or temporary_files or reparse_paths:
        raise runtime_gate.GateError(
            "W-025 policy gate left forbidden outputs: "
            f"dumps={dumps}, temporary={temporary_files}, reparse={reparse_paths}"
        )
    record = {
        "schema_version": 1,
        "target_id": target_id,
        "completed_cases": len(records),
        "dump_files": dumps,
        "temporary_files": temporary_files,
        "reparse_paths": reparse_paths,
        "artifacts": {
            key: {"name": path.name, "sha256": runtime_gate._sha256(path)}
            for key, path in sorted(staged.items())
        },
        "cases": records,
    }
    (work_root / "result.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"W-025 process-policy gate passed for {target_id}: "
        "cases=4, dumps=0, temporary=0, reparse=0"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--launcher", type=Path, required=True)
    parser.add_argument("--section-probe", type=Path, required=True)
    parser.add_argument("--mapping-probe", type=Path, required=True)
    parser.add_argument("--dalvikvm", type=Path, required=True)
    parser.add_argument("--boot-jar", type=Path, required=True)
    parser.add_argument("--mapping-jar", type=Path, required=True)
    parser.add_argument("--hello-jar", type=Path, required=True)
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
            launcher=args.launcher,
            section_probe=args.section_probe,
            mapping_probe=args.mapping_probe,
            dalvikvm=args.dalvikvm,
            boot_jar=args.boot_jar,
            mapping_jar=args.mapping_jar,
            hello_jar=args.hello_jar,
            work_root=args.work_root,
            icu_data=args.icu_data,
            library_dirs=args.library_dir,
            timeout=args.timeout,
        )
        return 0
    except (runtime_gate.GateError, OSError, UnicodeError) as exc:
        print(f"jit-section-policy run.py: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
