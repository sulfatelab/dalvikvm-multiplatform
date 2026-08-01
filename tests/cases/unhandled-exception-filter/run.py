#!/usr/bin/env python3
"""Run the standalone W-010 SEH/UEF matrix without a host shell."""

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


_CASES = (
    (
        "seh",
        False,
        ("WIN32_UEF_PROBE VEH enter code=0xc0000005", "WIN32_UEF_PROBE PASS seh"),
        ("WIN32_UEF_PROBE UEF first", "WIN32_UEF_PROBE UEF second"),
    ),
    (
        "unhandled",
        True,
        (
            "WIN32_UEF_PROBE main armed=1",
            "WIN32_UEF_PROBE VEH enter code=0xc0000005",
            "WIN32_UEF_PROBE UEF first code=0xc0000005",
        ),
        ("unexpected_return=1",),
    ),
    (
        "chain",
        True,
        (
            "WIN32_UEF_PROBE UEF second chaining=1",
            "WIN32_UEF_PROBE UEF first code=0xc0000005",
        ),
        ("unexpected_return=1",),
    ),
    (
        "thread",
        True,
        (
            "WIN32_UEF_PROBE worker armed=1",
            "WIN32_UEF_PROBE VEH enter code=0xc0000005",
            "WIN32_UEF_PROBE UEF first code=0xc0000005",
        ),
        ("unexpected_return=1", "unexpected_process_survival=1"),
    ),
)


def run_gate(*, target_id: str, probe: Path, work_root: Path, timeout: int) -> None:
    probe = runtime_gate._regular_file(str(probe))
    work_root = runtime_gate._managed_path(work_root, allow_missing=True)
    if work_root.exists() or work_root.is_symlink():
        runtime_gate._reject_tree_links(work_root)
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True)

    records: list[dict[str, object]] = []
    for mode, require_nonzero, expected, forbidden in _CASES:
        try:
            result = subprocess.run(
                [str(probe), mode],
                cwd=work_root,
                env=os.environ.copy(),
                text=True,
                capture_output=True,
                check=False,
                shell=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise runtime_gate.GateError(
                f"UEF mode {mode} timed out after {timeout} seconds"
            ) from exc
        (work_root / f"{mode}.stdout.txt").write_text(result.stdout, encoding="utf-8")
        (work_root / f"{mode}.stderr.txt").write_text(result.stderr, encoding="utf-8")
        output = result.stdout + "\n" + result.stderr
        missing = [marker for marker in expected if marker not in output]
        present_forbidden = [marker for marker in forbidden if marker in output]
        exit_ok = result.returncode != 0 if require_nonzero else result.returncode == 0
        records.append({
            "mode": mode,
            "exit_contract": "nonzero" if require_nonzero else "zero",
            "actual_exit": result.returncode,
            "missing_markers": missing,
            "forbidden_markers": present_forbidden,
        })
        if not exit_ok or missing or present_forbidden:
            raise runtime_gate.GateError(
                f"UEF mode {mode} failed: exit={result.returncode}, "
                f"missing={missing}, forbidden={present_forbidden}"
            )

    record = {
        "schema_version": 1,
        "target_id": target_id,
        "probe": {"name": probe.name, "sha256": runtime_gate._sha256(probe)},
        "completed_cases": len(records),
        "cases": records,
    }
    (work_root / "result.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"W-010 UEF matrix passed for {target_id}: cases={len(records)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    try:
        if args.timeout < 1:
            raise runtime_gate.GateError("timeout must be positive")
        run_gate(
            target_id=args.target_id,
            probe=args.probe,
            work_root=args.work_root,
            timeout=args.timeout,
        )
        return 0
    except (runtime_gate.GateError, OSError, UnicodeError) as exc:
        print(f"unhandled-exception-filter run.py: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
