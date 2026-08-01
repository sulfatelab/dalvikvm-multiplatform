#!/usr/bin/env python3
"""Run target-resolved W-003 managed ABI/frame matrices without a host shell."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys


_SUPPORT_ROOT = Path(__file__).parent
if str(_SUPPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_SUPPORT_ROOT))

import runtime_gate  # noqa: E402


_FORBIDDEN = (
    "AssertionError",
    "ART Win32 VEH",
    "ART Win32 UEF",
    "Check failed",
    "Fatal signal",
    "minidump written",
)

_JNI_ABI_TARGETS = {"linux-x86_64-gnu", "windows-x86_64-msvc"}

_CRITICAL_VALUES = (
    "longs=190 doubles=91.0 mixed=159.5 mixed32=87 "
    "floatReturn=15.25 calls=63 branchSeen=true"
)

_NATIVE_PHASES = {
    "initial": (
        "normalRegistered=743.75 fastRegistered=1743.75 "
        "normalDlsym=2755.75 fastDlsym=3755.75 normalInstance=4743.75 "
        "fastInstance=5743.75 calls=63"
    ),
    "unregistered": (
        "normalRegistered=10743.75 fastRegistered=11743.75 "
        "normalDlsym=12755.75 fastDlsym=13755.75 normalInstance=14743.75 "
        "fastInstance=15743.75 calls=63"
    ),
    "reregistered": (
        "normalRegistered=20743.75 fastRegistered=21743.75 "
        "normalDlsym=22755.75 fastDlsym=23755.75 normalInstance=24743.75 "
        "fastInstance=25743.75 calls=63"
    ),
    "tracing": (
        "normalRegistered=20743.75 fastRegistered=21743.75 "
        "normalDlsym=22755.75 fastDlsym=23755.75 normalInstance=24743.75 "
        "fastInstance=25743.75 calls=63"
    ),
    "postTracing": (
        "normalRegistered=20743.75 fastRegistered=21743.75 "
        "normalDlsym=22755.75 fastDlsym=23755.75 normalInstance=24743.75 "
        "fastInstance=25743.75 calls=63"
    ),
}

_NATIVE_COMPILE_MARKERS = (
    "double FastNativeAbiProbe.normalRegistered(",
    "double FastNativeAbiProbe.fastRegistered(",
    "double FastNativeAbiProbe.normalDlsym(",
    "double FastNativeAbiProbe.fastDlsym(",
    "double FastNativeAbiProbe.normalInstance(",
    "double FastNativeAbiProbe.fastInstance(",
    "int FastNativeAbiProbe.callMask(",
)


def _combined(case_root: Path) -> str:
    return (
        (case_root / "stdout.txt").read_text(encoding="utf-8")
        + "\n"
        + (case_root / "stderr.txt").read_text(encoding="utf-8")
    )


def _stage_probe(source: Path, case_root: Path, *names: str) -> None:
    source = runtime_gate._regular_file(str(source))
    for name in names:
        destination = case_root / name
        shutil.copyfile(source, destination)
        runtime_gate._regular_file(str(destination))


def _target_platform(target_id: str) -> str:
    if target_id in _JNI_ABI_TARGETS:
        return target_id.split("-", 1)[0]
    raise runtime_gate.GateError(f"W-003 has no accepted runner for {target_id}")


def _target_jit_options(platform: str) -> list[str]:
    options = ["-Xjitthreshold:0"]
    if platform == "linux":
        options[:0] = ["-verbose:jit", "-Xjitwarmupthreshold:0"]
    return options


def _target_jit_environment(platform: str, main_class: str) -> dict[str, str]:
    if platform != "windows":
        return {}
    return {
        "ART_WINDOWS_X64_JIT": "1",
        "ART_WINDOWS_X64_NTERP": "1",
        "ART_WINDOWS_X64_JIT_FILTER": main_class,
        "ART_WINDOWS_X64_JIT_LOG_COMPILES": "1",
    }


def _run_managed(
    *,
    target_id: str,
    dalvikvm: Path,
    boot_jar: Path,
    app_jar: Path,
    case_root: Path,
    icu_data: Path,
    library_dirs: list[Path],
    main_class: str,
    vm_options: list[str],
    expected: list[str],
    environment: dict[str, str],
    timeout: int,
) -> str:
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
        expected=[*expected, "main end exception=0"],
        forbidden=list(_FORBIDDEN),
        expected_exit=0,
        timeout=timeout,
        environment_overrides=environment,
    )
    return _combined(case_root)


def _run_critical(
    *,
    target_id: str,
    dalvikvm: Path,
    boot_jar: Path,
    app_jar: Path,
    probe: Path,
    work_root: Path,
    icu_data: Path,
    library_dirs: list[Path],
    repetitions: int,
    timeout: int,
) -> list[dict[str, object]]:
    platform = _target_platform(target_id)
    library_separator = ";" if platform == "windows" else ":"
    records: list[dict[str, object]] = []
    for repetition in range(1, repetitions + 1):
        load_mode = "absolute" if repetition % 2 == 0 else "library"
        for instrumentation in (False, True):
            mode = "instrumentation" if instrumentation else "default"
            case_root = work_root / f"{mode}-{load_mode}-{repetition}"
            case_root.mkdir(parents=True)
            (case_root / "empty-native-dir").mkdir()
            staged_names = [probe.name]
            if platform == "windows" and "criticalnativeprobe.dll" not in staged_names:
                staged_names.append("criticalnativeprobe.dll")
            _stage_probe(probe, case_root, *staged_names)
            expected = [
                f"CriticalNativeProbe load={load_mode}",
                f"CriticalNativeProbe values {_CRITICAL_VALUES}",
                f"CriticalNativeDlsymProbe values {_CRITICAL_VALUES}",
                "CriticalNativeProbe OK",
                "CriticalNativeDlsymProbe OK",
            ]
            if instrumentation:
                expected.extend(
                    [
                        f"CriticalNativeProbe tracing values {_CRITICAL_VALUES}",
                        f"CriticalNativeDlsymProbe tracing values {_CRITICAL_VALUES}",
                        f"CriticalNativeProbe postTracing values {_CRITICAL_VALUES}",
                        f"CriticalNativeDlsymProbe postTracing values {_CRITICAL_VALUES}",
                        "CriticalNativeProbe instrumentation OK",
                        "CriticalNativeDlsymProbe tracing OK",
                        "CriticalNativeDlsymProbe postTracing OK",
                    ]
                )
            output = _run_managed(
                target_id=target_id,
                dalvikvm=dalvikvm,
                boot_jar=boot_jar,
                app_jar=app_jar,
                case_root=case_root,
                icu_data=icu_data,
                library_dirs=[case_root, *library_dirs],
                main_class="CriticalNativeProbe",
                vm_options=[
                    *_target_jit_options(platform),
                    f"-Dcritical.load={load_mode}",
                    f"-Dcritical.absolute.library={probe.name}",
                    f"-Dcritical.instrumentation={int(instrumentation)}",
                    f"-Djava.library.path=empty-native-dir{library_separator}.",
                ],
                expected=expected,
                environment=_target_jit_environment(platform, "CriticalNativeProbe"),
                timeout=timeout,
            )
            if instrumentation and re.search(
                r"CriticalNativeProbe tracingMode before=0 during=[1-9][0-9]* "
                r"after=0 traceFileDeleted=true",
                output,
            ) is None:
                raise runtime_gate.GateError(
                    f"CriticalNative {mode} run lacks the tracing transition"
                )
            records.append({
                "mode": mode,
                "load_mode": load_mode,
                "repetition": repetition,
                "runtime": json.loads(
                    (case_root / "result.json").read_text(encoding="utf-8")
                ),
            })
    return records


def _run_native_abi(
    *,
    target_id: str,
    dalvikvm: Path,
    boot_jar: Path,
    app_jar: Path,
    probe: Path,
    work_root: Path,
    icu_data: Path,
    library_dirs: list[Path],
    repetitions: int,
    timeout: int,
) -> list[dict[str, object]]:
    platform = _target_platform(target_id)
    library_separator = ";" if platform == "windows" else ":"
    records: list[dict[str, object]] = []
    for repetition in range(1, repetitions + 1):
        for instrumentation in (False, True):
            mode = "instrumentation" if instrumentation else "default"
            case_root = work_root / f"{mode}-{repetition}"
            case_root.mkdir(parents=True)
            (case_root / "empty-native-dir").mkdir()
            _stage_probe(probe, case_root, probe.name)
            phases = ["initial", "unregistered", "reregistered"]
            if instrumentation:
                phases.extend(("tracing", "postTracing"))
            output = _run_managed(
                target_id=target_id,
                dalvikvm=dalvikvm,
                boot_jar=boot_jar,
                app_jar=app_jar,
                case_root=case_root,
                icu_data=icu_data,
                library_dirs=[case_root, *library_dirs],
                main_class="FastNativeAbiProbe",
                vm_options=[
                    *_target_jit_options(platform),
                    f"-Dnative.abi.instrumentation={int(instrumentation)}",
                    f"-Djava.library.path=empty-native-dir{library_separator}.",
                ],
                expected=[
                    *(f"FastNativeAbiProbe {phase} {_NATIVE_PHASES[phase]}" for phase in phases),
                    "FastNativeAbiProbe OK",
                ],
                environment=_target_jit_environment(platform, "FastNativeAbiProbe"),
                timeout=timeout,
            )
            compile_records = None
            if platform == "windows":
                for marker in _NATIVE_COMPILE_MARKERS:
                    count = output.count(f"success=1 method={marker}")
                    if count != 1:
                        raise runtime_gate.GateError(
                            f"FastNative {mode} run has {count} compile records "
                            f"for {marker!r}"
                        )
                compile_records = len(_NATIVE_COMPILE_MARKERS)
            if instrumentation and re.search(
                r"FastNativeAbiProbe tracingMode before=0 during=[1-9][0-9]* "
                r"after=0 traceFileDeleted=true",
                output,
            ) is None:
                raise runtime_gate.GateError(
                    "FastNative instrumentation run lacks the tracing transition"
                )
            records.append({
                "mode": mode,
                "repetition": repetition,
                "compile_records": compile_records,
                "runtime": json.loads(
                    (case_root / "result.json").read_text(encoding="utf-8")
                ),
            })
    return records


def _frame_mode(mode: str) -> tuple[list[str], dict[str, str]]:
    environment = {
        "ART_WINDOWS_X64_QUICK_INVOKE": "1",
        "ART_WINDOWS_X64_JIT": "0",
        "ART_WINDOWS_X64_NTERP": "0",
    }
    if mode == "int":
        return ["-Xint"], environment
    if mode == "switch":
        return [], environment
    if mode == "nterp":
        environment["ART_WINDOWS_X64_NTERP"] = "1"
        return [], environment
    environment.update({
        "ART_WINDOWS_X64_JIT": "1",
        "ART_WINDOWS_X64_NTERP": "1",
        "ART_WINDOWS_X64_JIT_FILTER": "W003FrameProbe",
        "ART_WINDOWS_X64_JIT_LOG_COMPILES": "1",
    })
    return ["-verbose:jit", "-Xjitwarmupthreshold:0", "-Xjitthreshold:0"], environment


def _validate_frame_output(output: str, mode: str) -> None:
    counters: dict[str, dict[str, int]] = {}
    pattern = re.compile(
        rf"W003FrameProbe mode={re.escape(mode)} phase=([a-z_]+) "
        r"counts=refs_only:([0-9]+),refs_and_args:([0-9]+),"
        r"all_callee_saves:([0-9]+),everything:([0-9]+) checksum=-?[0-9]+"
    )
    for phase, refs, args, callee, everything in pattern.findall(output):
        counters[phase] = {
            "refs_only": int(refs),
            "refs_and_args": int(args),
            "all_callee_saves": int(callee),
            "everything": int(everything),
        }
    for phase in ("refs_only", "refs_and_args", "all_callee_saves", "everything"):
        if phase not in counters:
            raise runtime_gate.GateError(f"W-003 frame {mode} lacks phase {phase}")
    if counters["refs_and_args"]["refs_and_args"] < 1:
        raise runtime_gate.GateError(f"W-003 frame {mode} did not reach refs-and-args")
    if counters["everything"]["everything"] < 1:
        raise runtime_gate.GateError(f"W-003 frame {mode} did not reach everything")
    if mode in ("nterp", "jit"):
        for phase in ("refs_only", "all_callee_saves"):
            if counters[phase][phase] < 1:
                raise runtime_gate.GateError(
                    f"W-003 frame {mode} did not reach {phase.replace('_', '-')}"
                )


def _run_frame(
    *,
    target_id: str,
    dalvikvm: Path,
    boot_jar: Path,
    app_jar: Path,
    probe: Path,
    work_root: Path,
    icu_data: Path,
    library_dirs: list[Path],
    repetitions: int,
    timeout: int,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for mode in ("int", "switch", "nterp", "jit"):
        mode_options, environment = _frame_mode(mode)
        for repetition in range(1, repetitions + 1):
            case_root = work_root / f"{mode}-{repetition}"
            case_root.mkdir(parents=True)
            _stage_probe(probe, case_root, "libw003frameprobe.dll")
            output = _run_managed(
                target_id=target_id,
                dalvikvm=dalvikvm,
                boot_jar=boot_jar,
                app_jar=app_jar,
                case_root=case_root,
                icu_data=icu_data,
                library_dirs=[case_root, *library_dirs],
                main_class="W003FrameProbe",
                vm_options=[*mode_options, f"-Dw003.mode={mode}", "-Djava.library.path=."],
                expected=[f"W003FrameProbe OK mode={mode}"],
                environment=environment,
                timeout=timeout,
            )
            _validate_frame_output(output, mode)
            records.append({
                "mode": mode,
                "repetition": repetition,
                "runtime": json.loads(
                    (case_root / "result.json").read_text(encoding="utf-8")
                ),
            })
    return records


def _xmm_mode(mode: str) -> tuple[list[str], dict[str, str]]:
    environment = {
        "ART_WINDOWS_X64_QUICK_INVOKE": "1",
        "ART_WINDOWS_X64_JIT": "0",
        "ART_WINDOWS_X64_NTERP": "1" if mode == "nterp" else "0",
    }
    if mode != "jit":
        return [], environment
    environment.update({
        "ART_WINDOWS_X64_JIT": "1",
        "ART_WINDOWS_X64_NTERP": "1",
        "ART_WINDOWS_X64_JIT_FILTER": "W003XmmSentinelProbe",
        "ART_WINDOWS_X64_JIT_LOG_COMPILES": "1",
    })
    return ["-verbose:jit", "-Xjitwarmupthreshold:0", "-Xjitthreshold:0"], environment


def _run_xmm(
    *,
    target_id: str,
    dalvikvm: Path,
    boot_jar: Path,
    app_jar: Path,
    probe: Path,
    work_root: Path,
    icu_data: Path,
    library_dirs: list[Path],
    repetitions: int,
    timeout: int,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for mode in ("nterp", "switch", "jit"):
        mode_options, environment = _xmm_mode(mode)
        for repetition in range(1, repetitions + 1):
            case_root = work_root / f"{mode}-{repetition}"
            case_root.mkdir(parents=True)
            _stage_probe(probe, case_root, "libw003xmmsentinel.dll")
            output = _run_managed(
                target_id=target_id,
                dalvikvm=dalvikvm,
                boot_jar=boot_jar,
                app_jar=app_jar,
                case_root=case_root,
                icu_data=icu_data,
                library_dirs=[case_root, *library_dirs],
                main_class="W003XmmSentinelProbe",
                vm_options=[*mode_options, f"-Dw003.mode={mode}", "-Djava.library.path=."],
                expected=[
                    "mask=0 selfTestMask=63 iterations=128 fullSelfTestMask=1023",
                    "exceptionMask=0 exceptionCaught=32 exceptionIterations=32 "
                    "exceptionSelfTestMask=1023",
                    "W003XmmSentinelProbe OK",
                ],
                environment=environment,
                timeout=timeout,
            )
            if re.search(
                rf"W003XmmSentinelProbe mode={mode} expected=-?[0-9]+ "
                r"warmChecksum=-?[0-9]+",
                output,
            ) is None:
                raise runtime_gate.GateError(f"W-003 XMM {mode} lacks its value line")
            if mode == "jit":
                for marker in (
                    "success=1 method=int W003XmmSentinelProbe.managedCallback(",
                    "success=1 method=int W003XmmSentinelProbe.managedExceptionCallback(",
                ):
                    if marker not in output:
                        raise runtime_gate.GateError(
                            f"W-003 XMM JIT run lacks compile marker {marker!r}"
                        )
            records.append({
                "mode": mode,
                "repetition": repetition,
                "runtime": json.loads(
                    (case_root / "result.json").read_text(encoding="utf-8")
                ),
            })
    return records


def run_gate(
    *,
    case: str,
    target_id: str,
    dalvikvm: Path,
    boot_jar: Path,
    app_jar: Path,
    probe: Path,
    work_root: Path,
    icu_data: Path,
    library_dirs: list[Path],
    repetitions: int,
    timeout: int,
) -> None:
    if case in ("critical-native", "native-abi"):
        if target_id not in _JNI_ABI_TARGETS:
            raise runtime_gate.GateError(
                f"W-003 {case} is not accepted for {target_id}"
            )
    elif target_id != "windows-x86_64-msvc":
        raise runtime_gate.GateError(
            f"W-003 {case} is not accepted for {target_id}"
        )
    work_root = runtime_gate._managed_path(work_root, allow_missing=True)
    if work_root.exists() or work_root.is_symlink():
        runtime_gate._reject_tree_links(work_root)
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True)

    common = {
        "target_id": target_id,
        "dalvikvm": dalvikvm,
        "boot_jar": boot_jar,
        "app_jar": app_jar,
        "probe": probe,
        "work_root": work_root,
        "icu_data": icu_data,
        "library_dirs": library_dirs,
        "repetitions": repetitions,
        "timeout": timeout,
    }
    runners = {
        "critical-native": _run_critical,
        "native-abi": _run_native_abi,
        "frame": _run_frame,
        "xmm": _run_xmm,
    }
    records = runners[case](**common)
    dumps = sorted(path.name for path in work_root.rglob("*.dmp"))
    record = {
        "schema_version": 1,
        "target_id": target_id,
        "case": case,
        "requested_repetitions": repetitions,
        "completed_runs": len(records),
        "dump_files": dumps,
        "runs": records,
    }
    temporary = work_root / "result.json.tmp"
    temporary.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, work_root / "result.json")
    if dumps:
        raise runtime_gate.GateError(f"W-003 {case} created dump files: {dumps}")
    print(
        f"W-003 {case} passed for {target_id}: "
        f"repetitions={repetitions}, runs={len(records)}, dumps=0"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case",
        choices=("critical-native", "native-abi", "frame", "xmm"),
        required=True,
    )
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--dalvikvm", type=Path, required=True)
    parser.add_argument("--boot-jar", type=Path, required=True)
    parser.add_argument("--app-jar", type=Path, required=True)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--icu-data", type=Path, required=True)
    parser.add_argument("--library-dir", type=Path, action="append", default=[])
    parser.add_argument("--repeat", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=180)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.repeat < 1 or args.timeout < 1:
            raise runtime_gate.GateError("repeat and timeout must be positive")
        run_gate(
            case=args.case,
            target_id=args.target_id,
            dalvikvm=args.dalvikvm,
            boot_jar=args.boot_jar,
            app_jar=args.app_jar,
            probe=args.probe,
            work_root=args.work_root,
            icu_data=args.icu_data,
            library_dirs=args.library_dir,
            repetitions=args.repeat,
            timeout=args.timeout,
        )
        return 0
    except (runtime_gate.GateError, OSError, UnicodeError) as exc:
        print(f"w003_managed_gate.py: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
