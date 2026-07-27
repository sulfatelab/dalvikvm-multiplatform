#!/usr/bin/env python3
"""Smoke the staged W-010/W-014 native package under Wine before transfer."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


def fail(message: str) -> None:
    raise RuntimeError(message)


def run_case(
    root: Path,
    name: str,
    command: list[str],
    *,
    markers: tuple[str, ...],
    forbidden: tuple[str, ...] = (),
    env_extra: dict[str, str] | None = None,
    require_nonzero: bool = False,
) -> str:
    env = os.environ.copy()
    env.update(
        {
            "ANDROID_ROOT": "run",
            "ANDROID_ART_ROOT": "run",
            "ANDROID_I18N_ROOT": "run",
            "ANDROID_DATA": "run/data",
            "ICU_DATA": "run/icu",
            "WINEDEBUG": env.get("WINEDEBUG", "-all"),
        }
    )
    for key in (
        "ART_WIN64_JIT",
        "ART_WIN64_JIT_DUAL",
        "ART_WIN64_JIT_EXCLUDE",
        "ART_WIN64_JIT_FILTER",
        "ART_WIN64_JIT_LOG_COMPILES",
        "ART_WIN64_NTERP",
        "ART_WIN64_QUICK_INVOKE",
        "ART_WIN64_CRASH_NATIVE_WARMUP",
        "ART_WIN64_FATAL_UNWIND_TRACE",
    ):
        env.pop(key, None)
    if env_extra:
        env.update(env_extra)

    result = subprocess.run(
        ["timeout", "180", *command],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
    )
    output = result.stdout + "\n" + result.stderr
    exit_ok = result.returncode != 0 if require_nonzero else result.returncode == 0
    if not exit_ok:
        fail(f"{name} exit={result.returncode}\n{output[-12000:]}")
    for marker in markers:
        if marker not in output:
            fail(f"{name} is missing marker {marker!r}\n{output[-12000:]}")
    for marker in forbidden:
        if marker in output:
            fail(f"{name} contains forbidden marker {marker!r}\n{output[-12000:]}")
    print(f"PASS {name} exit={result.returncode}")
    return output


def run_fatal_case(
    root: Path,
    name: str,
    command: list[str],
    *,
    markers: tuple[str, ...],
    forbidden: tuple[str, ...] = (),
    env_extra: dict[str, str] | None = None,
) -> str:
    crash = root / "run/crash"
    before = {
        path: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in crash.glob("*.dmp")
    }
    output = run_case(
        root,
        name,
        command,
        markers=markers,
        forbidden=forbidden,
        env_extra=env_extra,
        require_nonzero=True,
    )
    valid = []
    for path in crash.glob("*.dmp"):
        state = (path.stat().st_size, path.stat().st_mtime_ns)
        if before.get(path) == state or path.stat().st_size <= 32:
            continue
        if path.read_bytes()[:4] == b"MDMP":
            preserved = crash / f"{name}-{path.name}"
            if preserved.exists():
                fail(f"{name} minidump preservation path already exists: {preserved}")
            path.replace(preserved)
            valid.append(preserved)
    if not valid:
        fail(f"{name} did not create a new valid minidump")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    root = args.package.resolve()
    if not root.is_dir():
        fail(f"package directory does not exist: {root}")

    checker = Path(__file__).with_name("check_w010_w014_host_package.py")
    subprocess.run([sys.executable, str(checker), str(root)], check=True)

    wine = os.environ.get("WINE", "wine64")
    handled_forbidden = (
        "ART Win64 VEH",
        "ART Win64 UEF",
        "minidump written",
        "unexpected_continue",
    )
    crash = root / "run/crash"
    crash.mkdir(parents=True, exist_ok=True)
    for dump in crash.glob("*.dmp"):
        dump.unlink()

    run_case(
        root,
        "cet_policy",
        [wine, "./win32_cet_policy_probe.exe"],
        markers=("WIN32_CET_POLICY_PROBE PASS",),
    )
    run_case(
        root,
        "osr_unwind",
        [wine, "./win32_osr_unwind_probe.exe"],
        markers=(
            "win32_osr_unwind_probe failures=0",
            "entry_frame_register=R12 compiled_frame_register=RBP",
            "entry_frame_offset=0 return_prologue=0 fixed_frame=248 "
            "xmm_count=10 invoke_records=2 generic_jni_records=1 "
            "generic_jni_native_return=0xc5 variable_rsp_delta=256",
            "win32_osr_unwind_probe OK",
        ),
    )
    run_case(
        root,
        "thread_stack",
        [wine, "./win32_thread_stack_probe.exe"],
        markers=(
            "requested=65536",
            "requested=262144",
            "requested=1048576",
            "requested=2097152",
            "requested=9437184",
            "win32_thread_stack_probe failures=0 join_stress=512 detach_stress=128",
            "runtime=wine reservation_rounding=request",
            "win32_thread_stack_probe OK",
        ),
    )
    run_case(
        root,
        "stack_page",
        [wine, "./win32_stack_page_probe.exe"],
        markers=(
            "selection_cases count=8",
            "win32_stack_page_probe failures=0 committed_restore_iterations=64 reserved_restore_iterations=64 faults=258",
            "win32_stack_page_probe OK",
        ),
    )
    for mode, terminal in (
        ("baseline", "caught=0xc00000fd"),
        ("writable", "caught=0xc00000fd"),
        ("direct", "caught=0xc0000005"),
    ):
        run_case(
            root,
            f"stack_growth_{mode}",
            [wine, "./win32_stack_growth_probe.exe", mode],
            markers=(
                f"stack_growth mode={mode}",
                terminal,
                f"win32_stack_growth_probe mode={mode} failures=0 worker_exit=0",
                "win32_stack_growth_probe OK",
            ),
        )
    run_case(
        root,
        "uef_seh",
        [wine, "./win32_uef_probe.exe", "seh"],
        markers=(
            "WIN32_UEF_PROBE VEH enter code=0xc0000005",
            "WIN32_UEF_PROBE PASS seh",
        ),
        forbidden=("WIN32_UEF_PROBE UEF first", "WIN32_UEF_PROBE UEF second"),
    )
    run_case(
        root,
        "uef_unhandled",
        [wine, "./win32_uef_probe.exe", "unhandled"],
        markers=(
            "WIN32_UEF_PROBE main armed=1",
            "WIN32_UEF_PROBE VEH enter code=0xc0000005",
            "WIN32_UEF_PROBE UEF first code=0xc0000005",
        ),
        require_nonzero=True,
    )
    run_case(
        root,
        "uef_chain",
        [wine, "./win32_uef_probe.exe", "chain"],
        markers=(
            "WIN32_UEF_PROBE UEF second chaining=1",
            "WIN32_UEF_PROBE UEF first code=0xc0000005",
        ),
        require_nonzero=True,
    )
    run_case(
        root,
        "uef_thread",
        [wine, "./win32_uef_probe.exe", "thread"],
        markers=(
            "WIN32_UEF_PROBE worker armed=1",
            "WIN32_UEF_PROBE VEH enter code=0xc0000005",
            "WIN32_UEF_PROBE UEF first code=0xc0000005",
        ),
        require_nonzero=True,
    )
    run_case(
        root,
        "fault_record",
        [wine, "./win32_fault_record_probe.exe"],
        markers=(
            "win32_fault_record_probe failures=0 cases=8",
            "win32_fault_record_probe OK",
        ),
    )
    run_case(
        root,
        "sigchain",
        [wine, "./win32_sigchain_probe.exe"],
        markers=(
            "win32_sigchain_probe calls=2 first=0 second=0",
            "action_calls=3 foreign_before=2 foreign_after=2",
            "frame_with_action=1 frame_after_remove=1 sequence=1,2,1,2",
            "win32_sigchain_probe OK",
        ),
    )

    common = [
        wine,
        "./dalvikvm.exe",
        "-Xbootclasspath:run/boot.jar",
        "-Xbootclasspath-locations:run/boot.jar",
        "-Ximage:/nonexistent-no-boot-image",
        "-XjdwpProvider:none",
        "-Xms64m",
        "-Xmx512m",
    ]
    for mode in ("nterp", "switch", "jit"):
        env_extra = {"ART_WIN64_QUICK_INVOKE": "1"}
        vm_args: list[str] = []
        if mode == "nterp":
            env_extra.update(ART_WIN64_JIT="0", ART_WIN64_NTERP="1")
        elif mode == "switch":
            env_extra.update(ART_WIN64_JIT="0", ART_WIN64_NTERP="0")
        else:
            env_extra.update(
                ART_WIN64_JIT="1",
                ART_WIN64_NTERP="1",
                ART_WIN64_JIT_FILTER="W003XmmSentinelProbe.managedCallback",
                ART_WIN64_JIT_LOG_COMPILES="1",
            )
            vm_args.extend(
                ["-verbose:jit", "-Xjitwarmupthreshold:0", "-Xjitthreshold:0"]
            )
        markers = [
            f"W003XmmSentinelProbe mode={mode}",
            "mask=0 selfTestMask=63 iterations=128",
            "fullSelfTestMask=1023",
            "W003XmmSentinelProbe OK",
            "main end exception=0",
        ]
        forbidden = list(handled_forbidden)
        if mode == "jit":
            markers.append("success=1 method=int W003XmmSentinelProbe.managedCallback(")
        else:
            forbidden.append("Win64 CompileMethod done success=1 method=")
        run_case(
            root,
            f"xmm_full_{mode}",
            [
                *common,
                *vm_args,
                f"-Dw003.mode={mode}",
                "-Djava.library.path=.",
                "-cp",
                "run/w003xmmsentinelprobe.jar",
                "W003XmmSentinelProbe",
            ],
            markers=tuple(markers),
            forbidden=tuple(forbidden),
            env_extra=env_extra,
        )
    run_case(
        root,
        "no_sig_chain_rejection",
        [
            *common,
            "-Xno-sig-chain",
            "-Xint",
            "-cp",
            "run/w010managedfaultprobe.jar",
            "W010ManagedFaultProbe",
            "npe",
        ],
        markers=("A started runtime should have sig chain enabled",),
        forbidden=("W010ManagedFaultProbe OK",),
        require_nonzero=True,
    )
    run_case(
        root,
        "switch_so",
        [
            *common,
            "-Xusejit:false",
            "-cp",
            "run/w010managedfaultprobe.jar",
            "W010ManagedFaultProbe",
            "so",
        ],
        markers=(
            "W010ManagedFaultProbe SO OK main=2 child=2 recovery=4 gc=4",
            "W010ManagedFaultProbe OK mode=so",
            "main end exception=0",
        ),
        forbidden=(*handled_forbidden, "Win64 CompileMethod done success=1 method="),
        env_extra={"ART_WIN64_NTERP": "0"},
    )
    for fault_mode, marker in (
        ("npe", "W010ManagedFaultProbe NPE OK read=64 write=64 recovery=128 gc=16"),
        ("so", "W010ManagedFaultProbe SO OK main=2 child=2 recovery=4 gc=4"),
    ):
        run_case(
            root,
            f"nterp_{fault_mode}",
            [
                *common,
                "-Xusejit:false",
                "-cp",
                "run/w010managedfaultprobe.jar",
                "W010ManagedFaultProbe",
                fault_mode,
            ],
            markers=(marker, f"W010ManagedFaultProbe OK mode={fault_mode}", "main end exception=0"),
            forbidden=(*handled_forbidden, "Win64 CompileMethod done success=1 method="),
        )
    for fault_mode, markers in (
        (
            "npe",
            (
                "W010ManagedFaultProbe NPE OK read=64 write=64 recovery=128 gc=16",
                "Win64 CompileMethod done success=1 method=void W010ManagedFaultProbe.runNullChecks()",
            ),
        ),
        (
            "so",
            (
                "W010ManagedFaultProbe SO OK main=2 child=2 recovery=4 gc=4",
                "Win64 CompileMethod done success=1 method=int W010ManagedFaultProbe.recurse(int)",
                "Win64 CompileMethod done success=1 method=int W010ManagedFaultProbe.runStackOverflowRounds()",
            ),
        ),
    ):
        run_case(
            root,
            f"jit_{fault_mode}",
            [
                *common,
                "-verbose:jit",
                "-Xjitwarmupthreshold:0",
                "-Xjitthreshold:0",
                "-cp",
                "run/w010managedfaultprobe.jar",
                "W010ManagedFaultProbe",
                fault_mode,
            ],
            markers=(*markers, f"W010ManagedFaultProbe OK mode={fault_mode}", "main end exception=0"),
            forbidden=handled_forbidden,
            env_extra={
                "ART_WIN64_JIT_FILTER": "W010ManagedFaultProbe",
                "ART_WIN64_JIT_LOG_COMPILES": "1",
            },
        )

    handled_dumps = list(crash.glob("*.dmp"))
    if handled_dumps:
        fail(f"handled package smoke produced dumps: {handled_dumps}")
    print("PASS handled_dump_scan NO_HANDLED_DMP_FILES")

    run_fatal_case(
        root,
        "crashnative",
        [
            *common,
            "-Xint",
            "-cp",
            "run/crashnativeprobe.jar",
            "CrashNativeProbe",
        ],
        markers=(
            "CrashNativeProbe.start",
            "ART Win64 VEH: exception 0xc0000005",
            "ART Win64 UEF: exception 0xc0000005",
            "minidump written",
        ),
        forbidden=("CrashNativeProbe.unexpected_continue",),
    )
    for name, argument, mode_markers in (
        ("art_late_uef_jni_av", "uef-av", ()),
        (
            "art_late_uef_native_worker",
            "uef-thread",
            ("WIN32_JNI_NATIVE_WORKER created", "WIN32_JNI_NATIVE_WORKER enter"),
        ),
    ):
        run_fatal_case(
            root,
            name,
            [
                *common,
                "-Xint",
                "-cp",
                "run/crashnativeprobe.jar",
                "CrashNativeProbe",
                argument,
            ],
            markers=(
                "WIN32_LATE_UEF_INSTALL",
                "is_art=1 debugger=0",
                f"CrashNativeProbe.uef_armed mode={argument}",
                *mode_markers,
                "WIN32_LATE_UEF enter code=0xc0000005",
                "ART Win64 UEF: exception 0xc0000005",
                "minidump written",
                "ART_WIN64_UNWIND_TRACE begin",
                "ART_WIN64_UNWIND_TRACE frame=",
                "ART_WIN64_UNWIND_TRACE end",
            ),
            forbidden=(
                "CrashNativeProbe.unexpected_continue",
                "WIN32_JNI_NATIVE_WORKER unexpected_return",
            ),
            env_extra={"ART_WIN64_FATAL_UNWIND_TRACE": "1"},
        )
    run_case(
        root,
        "art_late_uef_jni_raise",
        [
            *common,
            "-Xint",
            "-cp",
            "run/crashnativeprobe.jar",
            "CrashNativeProbe",
            "uef-raise",
        ],
        markers=(
            "WIN32_LATE_UEF_INSTALL",
            "is_art=1 debugger=0",
            "CrashNativeProbe.uef_armed mode=uef-raise",
            "WIN32_JNI_RAISE_AV",
            "WIN32_LATE_UEF enter code=0xc0000005",
            "ART Win64 UEF: exception 0xc0000005",
            "minidump written",
            "CrashNativeProbe.unexpected_continue",
            "ART_WIN64_UNWIND_TRACE begin",
            "ART_WIN64_UNWIND_TRACE frame=",
            "ART_WIN64_UNWIND_TRACE end",
        ),
        env_extra={"ART_WIN64_FATAL_UNWIND_TRACE": "1"},
    )

    for mode in ("j2", "j1"):
        forbidden = ("CrashNativeProbe.unexpected_continue",)
        markers = (
            "CrashNativeProbe.jit_ready calls=20000",
            "Win64 CompileMethod done success=1 method=void CrashNativeProbe.jitCrashCaller(int)",
            "Win64 CompileMethod done success=1 method=void CrashNativeProbe.nativeSegfault()",
            "ART Win64 VEH: exception 0xc0000005",
            "ART Win64 UEF: exception 0xc0000005",
            "minidump written",
        )
        if mode == "j2":
            markers += ("Win64 JIT dual-view (J-2) created",)
        else:
            forbidden += ("Win64 JIT dual-view (J-2) created",)
        run_fatal_case(
            root,
            f"jit_fatal_{mode}",
            [
                *common,
                "-verbose:jit",
                "-Xjitwarmupthreshold:0",
                "-Xjitthreshold:0",
                "-cp",
                "run/crashnativeprobe.jar",
                "CrashNativeProbe",
                "jit",
            ],
            markers=markers,
            forbidden=forbidden,
            env_extra={
                "ART_WIN64_CRASH_NATIVE_WARMUP": "20000",
                "ART_WIN64_JIT_DUAL": "1" if mode == "j2" else "0",
                "ART_WIN64_JIT_FILTER": "CrashNativeProbe",
                "ART_WIN64_JIT_LOG_COMPILES": "1",
            },
        )

    for mode in ("j2", "j1"):
        forbidden = (
            "Done running OSR code for long CrashNativeProbe.osrCrashLoop(int)",
            "CrashNativeProbe.osr_unexpected_return",
            "CrashNativeProbe.unexpected_continue",
        )
        markers = (
            "CrashNativeProbe.osr_armed count=2000000",
            "warmup_threshold=100, optimize_threshold=100",
            "kind=Baseline",
            "kind=Osr",
            "Win64 CompileMethod done success=1 method=long CrashNativeProbe.osrCrashLoop(int)",
            "Jumping to long CrashNativeProbe.osrCrashLoop(int)",
            "ART Win64 VEH: exception 0xc0000005",
            "ART Win64 UEF: exception 0xc0000005",
            "minidump written",
        )
        if mode == "j2":
            markers += ("Win64 JIT dual-view (J-2) created",)
        else:
            forbidden += ("Win64 JIT dual-view (J-2) created",)
        run_fatal_case(
            root,
            f"osr_fatal_{mode}",
            [
                *common,
                "-verbose:jit",
                "-Xjitwarmupthreshold:100",
                "-Xjitthreshold:100",
                "-cp",
                "run/crashnativeprobe.jar",
                "CrashNativeProbe",
                "osr",
            ],
            markers=markers,
            forbidden=forbidden,
            env_extra={
                "ART_WIN64_NTERP": "0",
                "ART_WIN64_JIT_DUAL": "1" if mode == "j2" else "0",
                "ART_WIN64_JIT_FILTER": "CrashNativeProbe.osrCrashLoop",
                "ART_WIN64_JIT_LOG_COMPILES": "1",
            },
        )

    fatal_dumps = list(crash.glob("*.dmp"))
    if len(fatal_dumps) < 5:
        fail(f"fatal package smoke produced fewer than five minidumps: {fatal_dumps}")
    for dump in fatal_dumps:
        if dump.stat().st_size < 4096 or dump.read_bytes()[:4] != b"MDMP":
            fail(f"invalid minidump: {dump}")
    print(f"PASS fatal_dump_scan count={len(fatal_dumps)}")
    print("W-010/W-014 host package Wine smoke: PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"W-010/W-014 host package Wine smoke: FAIL: {error}", file=sys.stderr)
        sys.exit(1)
