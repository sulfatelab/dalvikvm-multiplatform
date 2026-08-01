#!/usr/bin/env python3
"""Run the unified Windows JIT control and managed-workload matrix."""

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


_COMMON_EXPECTED = ["Hello from dalvikvm!", "main end exception=0"]
_COMMON_FORBIDDEN = [
    "AssertionError",
    "ART Win32 VEH",
    "ART Win32 UEF",
    "Check failed",
    "Fatal signal",
    "minidump written",
    "falling back to single-view (J-1)",
]
_COMPILE_MARKER = "Windows x64 CompileMethod done success=1 method="
_BASE_ENVIRONMENT = {
    "ART_WINDOWS_X64_JIT": "",
    "ART_WINDOWS_X64_JIT_FILTER": "",
    "ART_WINDOWS_X64_JIT_EXCLUDE": "",
    "ART_WINDOWS_X64_JIT_LOG_COMPILES": "",
    "ART_WINDOWS_X64_JIT_DUAL": "",
}


def _read_output(case_root: Path) -> str:
    return "\n".join(
        (case_root / name).read_text(encoding="utf-8", errors="replace")
        for name in ("stdout.txt", "stderr.txt")
    )


def _run_case(
    *,
    target_id: str,
    name: str,
    dalvikvm: Path,
    boot_jar: Path,
    app_jar: Path,
    main_class: str,
    work_root: Path,
    icu_data: Path,
    library_dirs: list[Path],
    vm_options: list[str],
    environment: dict[str, str],
    expected: list[str],
    forbidden: list[str],
    timeout: int,
    require_nonzero: bool = False,
    required_compile_substrings: tuple[str, ...] = (),
    forbidden_compile_substrings: tuple[str, ...] = (),
    require_zero_compiles: bool = False,
    minimum_compile_records: int = 0,
) -> dict[str, object]:
    case_root = work_root / name
    case_root.mkdir()
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
        main_args=[],
        expected=expected,
        forbidden=forbidden,
        expected_exit=0,
        timeout=timeout,
        environment_overrides={**_BASE_ENVIRONMENT, **environment},
        require_nonzero=require_nonzero,
    )
    output = _read_output(case_root)
    compile_lines = [
        line for line in output.splitlines() if _COMPILE_MARKER in line
    ]
    for marker in required_compile_substrings:
        if not any(marker in line for line in compile_lines):
            raise runtime_gate.GateError(
                f"JIT control case {name} has no successful compile for {marker}"
            )
    for marker in forbidden_compile_substrings:
        if any(marker in line for line in compile_lines):
            raise runtime_gate.GateError(
                f"JIT control case {name} unexpectedly compiled {marker}"
            )
    if require_zero_compiles and compile_lines:
        raise runtime_gate.GateError(
            f"JIT control case {name} emitted {len(compile_lines)} compile records"
        )
    if len(compile_lines) < minimum_compile_records:
        raise runtime_gate.GateError(
            f"JIT control case {name} emitted {len(compile_lines)} successful "
            f"compile records; expected at least {minimum_compile_records}"
        )
    nested = json.loads((case_root / "result.json").read_text(encoding="utf-8"))
    return {
        "name": name,
        "main_class": main_class,
        "compile_records": len(compile_lines),
        "runtime": nested,
    }


def run_gate(
    *,
    target_id: str,
    dalvikvm: Path,
    boot_jar: Path,
    hello_jar: Path,
    math_jar: Path,
    io_jar: Path,
    net_jar: Path,
    gc_jar: Path,
    throw_jar: Path,
    work_root: Path,
    icu_data: Path,
    library_dirs: list[Path],
    timeout: int,
) -> None:
    if target_id != "windows-x86_64-msvc":
        raise runtime_gate.GateError(
            f"JIT runtime controls are not accepted for {target_id}"
        )
    work_root = runtime_gate._managed_path(work_root, allow_missing=True)
    if work_root.exists() or work_root.is_symlink():
        runtime_gate._reject_tree_links(work_root)
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True)

    common = dict(
        target_id=target_id,
        dalvikvm=dalvikvm,
        boot_jar=boot_jar,
        work_root=work_root,
        icu_data=icu_data,
        library_dirs=library_dirs,
        timeout=timeout,
        forbidden=list(_COMMON_FORBIDDEN),
    )
    records: list[dict[str, object]] = []
    verbose_options = ["-verbose:jit", "-Xjitwarmupthreshold:0", "-Xjitthreshold:0"]
    records.append(_run_case(
        name="default-verbose",
        app_jar=hello_jar,
        main_class="Hello",
        vm_options=verbose_options,
        environment={"ART_WINDOWS_X64_JIT_LOG_COMPILES": "1"},
        expected=[
            *_COMMON_EXPECTED,
            "JitCodeCache::Create OK",
            "Windows x64 JIT dual-view (J-2) created",
        ],
        minimum_compile_records=1,
        **common,
    ))
    records.append(_run_case(
        name="retired-optout",
        app_jar=hello_jar,
        main_class="Hello",
        vm_options=verbose_options,
        environment={
            "ART_WINDOWS_X64_JIT_DUAL": "0",
            "ART_WINDOWS_X64_JIT_FILTER": "Hello",
            "ART_WINDOWS_X64_JIT_LOG_COMPILES": "1",
        },
        expected=[*_COMMON_EXPECTED, "Windows x64 JIT dual-view (J-2) created"],
        required_compile_substrings=("Hello",),
        **common,
    ))
    records.append(_run_case(
        name="environment-disabled",
        app_jar=hello_jar,
        main_class="Hello",
        vm_options=verbose_options,
        environment={
            "ART_WINDOWS_X64_JIT": "0",
            "ART_WINDOWS_X64_JIT_LOG_COMPILES": "1",
        },
        expected=list(_COMMON_EXPECTED),
        require_zero_compiles=True,
        **common,
    ))
    records.append(_run_case(
        name="xusejit-disabled",
        app_jar=hello_jar,
        main_class="Hello",
        vm_options=["-Xusejit:false"],
        environment={"ART_WINDOWS_X64_JIT_LOG_COMPILES": "1"},
        expected=list(_COMMON_EXPECTED),
        require_zero_compiles=True,
        **common,
    ))
    records.append(_run_case(
        name="filter",
        app_jar=hello_jar,
        main_class="Hello",
        vm_options=verbose_options,
        environment={
            "ART_WINDOWS_X64_JIT_FILTER": "StringBuilder",
            "ART_WINDOWS_X64_JIT_LOG_COMPILES": "1",
        },
        expected=list(_COMMON_EXPECTED),
        required_compile_substrings=("StringBuilder",),
        **common,
    ))
    records.append(_run_case(
        name="exclude",
        app_jar=hello_jar,
        main_class="Hello",
        vm_options=verbose_options,
        environment={
            "ART_WINDOWS_X64_JIT_EXCLUDE": "StringBuilder",
            "ART_WINDOWS_X64_JIT_LOG_COMPILES": "1",
        },
        expected=list(_COMMON_EXPECTED),
        forbidden_compile_substrings=("StringBuilder",),
        **common,
    ))
    records.append(_run_case(
        name="quiet",
        app_jar=hello_jar,
        main_class="Hello",
        vm_options=["-Xjitwarmupthreshold:0", "-Xjitthreshold:0"],
        environment={},
        expected=list(_COMMON_EXPECTED),
        require_zero_compiles=True,
        **common,
    ))

    workloads = (
        (
            "math-critical",
            math_jar,
            "MathCriticalProbe",
            [
                "MathCriticalProbe native ceil=true floor=true cases=23 rounds=2000",
                "MathCriticalProbe OK",
                "main end exception=0",
            ],
            False,
        ),
        ("io", io_jar, "IoProbe", ["match=true", "IoProbe.done=ok"], False),
        (
            "net",
            net_jar,
            "NetProbe",
            ["match=true", "echoMatch=true", "NetProbe.done=ok"],
            False,
        ),
        (
            "gc",
            gc_jar,
            "GcProbe",
            ["los.ok=true", "gc.ok=true", "GcProbe.done=ok"],
            False,
        ),
        (
            "throw",
            throw_jar,
            "ThrowProbe",
            ["ThrowProbe.start", "RuntimeException: phase3-throw-ok"],
            True,
        ),
    )
    for name, app_jar, main_class, expected, require_nonzero in workloads:
        records.append(_run_case(
            name=f"workload-{name}",
            app_jar=app_jar,
            main_class=main_class,
            vm_options=verbose_options,
            environment={
                "ART_WINDOWS_X64_JIT_FILTER": main_class,
                "ART_WINDOWS_X64_JIT_LOG_COMPILES": "1",
            },
            expected=expected,
            require_nonzero=require_nonzero,
            required_compile_substrings=(main_class,),
            **common,
        ))

    dumps = sorted(path.name for path in work_root.rglob("*.dmp"))
    if dumps:
        raise runtime_gate.GateError(f"JIT runtime controls created dumps: {dumps}")
    runtime_gate._reject_tree_links(work_root)
    result = {
        "schema_version": 1,
        "target_id": target_id,
        "completed_cases": len(records),
        "dump_files": dumps,
        "cases": records,
    }
    (work_root / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"Windows JIT runtime controls passed for {target_id}: "
        f"controls=7, workloads=5, dumps=0"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--dalvikvm", type=Path, required=True)
    parser.add_argument("--boot-jar", type=Path, required=True)
    parser.add_argument("--hello-jar", type=Path, required=True)
    parser.add_argument("--math-jar", type=Path, required=True)
    parser.add_argument("--io-jar", type=Path, required=True)
    parser.add_argument("--net-jar", type=Path, required=True)
    parser.add_argument("--gc-jar", type=Path, required=True)
    parser.add_argument("--throw-jar", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--icu-data", type=Path, required=True)
    parser.add_argument("--library-dir", type=Path, action="append", default=[])
    parser.add_argument("--timeout", type=int, default=300)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.timeout < 1:
            raise runtime_gate.GateError("timeout must be positive")
        run_gate(
            target_id=args.target_id,
            dalvikvm=args.dalvikvm,
            boot_jar=args.boot_jar,
            hello_jar=args.hello_jar,
            math_jar=args.math_jar,
            io_jar=args.io_jar,
            net_jar=args.net_jar,
            gc_jar=args.gc_jar,
            throw_jar=args.throw_jar,
            work_root=args.work_root,
            icu_data=args.icu_data,
            library_dirs=args.library_dir,
            timeout=args.timeout,
        )
        return 0
    except (runtime_gate.GateError, OSError, UnicodeError) as exc:
        print(f"jit-runtime-controls/run.py: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
