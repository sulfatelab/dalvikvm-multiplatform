#!/usr/bin/env python3
"""Run W-038 managed-exception and fatal boot-OAT unwind contracts."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys


_REPO_ROOT = Path(__file__).parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools import run_windows_boot_image  # noqa: E402


_PROBE_NAME = "w038aotunwindprobe"
_TRACE_ENV = "ART_WINDOWS_X64_FATAL_UNWIND_TRACE"
_ARM_RE = re.compile(
    r"^W038_FATAL_ARM target=(.*?) oat_base=0x([0-9a-f]+) "
    r"begin=0x([0-9a-f]+) end=0x([0-9a-f]+) jit=disabled$",
    re.MULTILINE | re.IGNORECASE,
)
_FRAME_RE = re.compile(
    r"^ART_WINDOWS_X64_UNWIND_TRACE frame=(\d+) pc=0x([0-9a-f]+) "
    r"rsp=0x([0-9a-f]+) lookup=1 image=0x([0-9a-f]+) "
    r"begin=0x([0-9a-f]+) end=0x([0-9a-f]+)",
    re.MULTILINE | re.IGNORECASE,
)


def _arguments(
    args: argparse.Namespace,
    *,
    work_root: Path,
    main_class: str,
    expected: list[str],
    forbidden: list[str],
) -> argparse.Namespace:
    return argparse.Namespace(
        target_id=args.target_id,
        dalvikvm=args.dalvikvm,
        boot_jar=args.boot_jar,
        app_jar=args.app_jar,
        boot_image_dir=args.boot_image_dir,
        icu_data=args.icu_data,
        work_root=work_root,
        library_dir=args.library_dir,
        main_class=main_class,
        execution_mode="aot",
        probe=args.probe,
        probe_name=_PROBE_NAME,
        policy_launcher=None,
        cfg_corruption_matrix=False,
        expect=expected,
        forbid=forbidden,
        timeout=args.timeout,
    )


def _read_result(root: Path) -> dict[str, object]:
    return json.loads((root / "result.json").read_text(encoding="utf-8"))


def _validate_target_unwind(stdout: str, stderr: str) -> dict[str, object]:
    arm = _ARM_RE.search(stdout)
    if arm is None:
        raise run_windows_boot_image.WindowsBootImageError(
            "fatal output has no parseable boot-OAT target marker"
        )
    target, oat_text, begin_text, end_text = arm.groups()
    oat_base = int(oat_text, 16)
    begin = int(begin_text, 16)
    end = int(end_text, 16)
    if oat_base == 0 or begin >= end:
        raise run_windows_boot_image.WindowsBootImageError(
            "fatal boot-OAT target marker has invalid bounds"
        )

    matched: tuple[int, int, int] | None = None
    for frame in _FRAME_RE.finditer(stderr):
        frame_index, pc_text, rsp_text, image_text, frame_begin_text, frame_end_text = (
            frame.groups()
        )
        pc = int(pc_text, 16)
        rsp = int(rsp_text, 16)
        if (
            int(image_text, 16) == oat_base
            and int(frame_begin_text, 16) == begin
            and int(frame_end_text, 16) == end
            and oat_base + begin <= pc < oat_base + end
        ):
            matched = (int(frame_index), pc, rsp)
            break
    if matched is None:
        raise run_windows_boot_image.WindowsBootImageError(
            "fatal unwind trace did not reach the armed boot-OAT function"
        )

    frame_index, pc, rsp = matched
    step = re.search(
        rf"^ART_WINDOWS_X64_UNWIND_TRACE step={frame_index} kind=virtual "
        rf"next_pc=0x([0-9a-f]+) next_rsp=0x([0-9a-f]+)",
        stderr,
        re.MULTILINE | re.IGNORECASE,
    )
    if step is None or int(step.group(2), 16) <= rsp:
        raise run_windows_boot_image.WindowsBootImageError(
            "armed boot-OAT frame did not complete a progressing virtual unwind"
        )
    return {
        "target": target,
        "oat_base": f"0x{oat_base:x}",
        "begin": f"0x{begin:x}",
        "end": f"0x{end:x}",
        "frame": frame_index,
        "pc": f"0x{pc:x}",
        "next_pc": f"0x{int(step.group(1), 16):x}",
        "next_rsp": f"0x{int(step.group(2), 16):x}",
    }


def run_gate(args: argparse.Namespace) -> None:
    work_root = run_windows_boot_image._prepare_output_root(args.work_root)
    caught_root = work_root / "managed-exception"
    run_windows_boot_image.run_gate(
        _arguments(
            args,
            work_root=caught_root,
            main_class="W038BootOatManagedExceptionProbe",
            expected=[
                "W038_MANAGED_EXCEPTION_PASS",
                "type=explicit caught=1 trace=nonempty trace_target=1",
                "entry_unchanged=1 jit=disabled",
                "W038BootOatManagedExceptionProbe PASS exception=caught",
                "main end exception=0",
            ],
            forbidden=["W038_BOOT_OAT_UNWIND_FAIL", "AssertionError"],
        )
    )

    fatal_root = work_root / "fatal-unwind"
    previous_trace = os.environ.get(_TRACE_ENV)
    os.environ[_TRACE_ENV] = "1"
    failed_as_expected = False
    try:
        run_windows_boot_image.run_gate(
            _arguments(
                args,
                work_root=fatal_root,
                main_class="W038BootOatFatalUnwindProbe",
                expected=[
                    "W038_FATAL_ARM target=",
                    "W038_FATAL_CRASH_ENTER native_callback=1",
                    "ART Win32 VEH: exception 0xc0000005",
                    "ART_WINDOWS_X64_UNWIND_TRACE begin code=0xc0000005",
                    "ART_WINDOWS_X64_UNWIND_TRACE end frames=",
                    "ART Win32 UEF: exception 0xc0000005",
                    "minidump written",
                ],
                forbidden=[
                    "W038_BOOT_OAT_UNWIND_FAIL",
                    "W038_FATAL_UNEXPECTED_RETURN",
                    "main end exception=0",
                    "AssertionError",
                ],
            )
        )
    except run_windows_boot_image.WindowsBootImageError:
        result = _read_result(fatal_root)
        failed_as_expected = (
            isinstance(result.get("actual_exit"), int)
            and result["actual_exit"] != 0
            and result.get("missing_markers") == []
            and result.get("forbidden_markers") == []
        )
        if not failed_as_expected:
            raise
    finally:
        if previous_trace is None:
            os.environ.pop(_TRACE_ENV, None)
        else:
            os.environ[_TRACE_ENV] = previous_trace
    if not failed_as_expected:
        raise run_windows_boot_image.WindowsBootImageError(
            "fatal boot-OAT process returned successfully"
        )

    stdout = (fatal_root / "stdout.txt").read_text(encoding="utf-8")
    stderr = (fatal_root / "stderr.txt").read_text(encoding="utf-8")
    unwind = _validate_target_unwind(stdout, stderr)
    dumps = sorted((fatal_root / "package" / "run" / "crash").glob("*.dmp"))
    if len(dumps) != 1 or dumps[0].stat().st_size <= 4096 or dumps[0].read_bytes()[:4] != b"MDMP":
        raise run_windows_boot_image.WindowsBootImageError(
            f"fatal boot-OAT process produced {len(dumps)} valid minidumps"
        )

    record = {
        "schema_version": 1,
        "target_id": args.target_id,
        "completed_cases": 2,
        "managed_exception": _read_result(caught_root),
        "fatal_unwind": _read_result(fatal_root),
        "boot_oat_frame": unwind,
        "minidump": {
            "name": dumps[0].name,
            "size": dumps[0].stat().st_size,
            "sha256": run_windows_boot_image._sha256(dumps[0]),
        },
    }
    (work_root / "result.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "W-038 boot-OAT exception/fatal-unwind gate passed: "
        f"cases=2 target={unwind['target']} frame={unwind['frame']} dumps=1"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--dalvikvm", type=Path, required=True)
    parser.add_argument("--boot-jar", type=Path, required=True)
    parser.add_argument("--app-jar", type=Path, required=True)
    parser.add_argument("--boot-image-dir", type=Path, required=True)
    parser.add_argument("--icu-data", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--library-dir", type=Path, action="append", default=[])
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    try:
        if args.timeout < 1:
            raise run_windows_boot_image.WindowsBootImageError("timeout must be positive")
        run_gate(args)
        return 0
    except (
        OSError,
        run_windows_boot_image.WindowsBootImageError,
        run_windows_boot_image.windows_aot_identity.WindowsAotIdentityError,
    ) as exc:
        print(f"aot-exception-fatal-unwind run.py: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
