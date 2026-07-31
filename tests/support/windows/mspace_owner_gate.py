#!/usr/bin/env python3
"""Run the W-013 mspace-owner success and fatal-contract cases without a shell."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import sys


DEATH_CASES = {
    "missing-provider": "Unattached ART mspace",
    "use-after-detach": "Unattached ART mspace",
    "wrong-owner-detach": "state->extp == provider",
    "double-attach": "state->extp == nullptr",
}
SUCCESS_MARKER = "W013_MSPACE_OWNER_PASS"


class GateError(RuntimeError):
    """The mspace-owner executable did not satisfy its fatal contract."""


def managed_path(path: Path, *, allow_missing: bool = False) -> Path:
    path = Path(os.path.abspath(path))
    missing_seen = False
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            missing_seen = True
            continue
        if missing_seen:
            raise GateError(f"existing path below a missing component: {current}")
        attributes = getattr(info, "st_file_attributes", 0)
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if stat.S_ISLNK(info.st_mode) or attributes & reparse:
            raise GateError(f"link/reparse path is forbidden: {current}")
    if not allow_missing and not path.exists():
        raise GateError(f"managed path does not exist: {path}")
    return path


def run_case(
    probe: Path,
    mode: str,
    expected_marker: str,
    environment: dict[str, str],
    timeout: int,
    *,
    expect_success: bool,
) -> dict[str, object]:
    try:
        result = subprocess.run(
            [str(probe), mode],
            cwd=probe.parent,
            env=environment,
            shell=False,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise GateError(f"{mode} timed out after {timeout} seconds") from error
    combined = result.stdout + "\n" + result.stderr
    exit_ok = result.returncode == 0 if expect_success else result.returncode != 0
    marker_ok = expected_marker in combined
    if not exit_ok or not marker_ok:
        tail = "\n".join(combined.splitlines()[-80:])
        expected_exit = "zero" if expect_success else "nonzero"
        raise GateError(
            f"{mode} failed: exit={result.returncode}, expected={expected_exit}, "
            f"marker={expected_marker!r}, found={marker_ok}\n{tail}"
        )
    return {
        "mode": mode,
        "return_code": result.returncode,
        "expected_exit": "zero" if expect_success else "nonzero",
        "expected_marker": expected_marker,
        "marker_found": True,
        "timed_out": False,
    }


def run_gate(
    *,
    target_id: str,
    probe: Path,
    result_path: Path,
    library_dirs: list[Path],
    timeout: int,
) -> dict[str, object]:
    probe = managed_path(probe)
    if not probe.is_file():
        raise GateError(f"probe is not a regular file: {probe}")
    library_dirs = [managed_path(path) for path in library_dirs]
    result_path = managed_path(result_path, allow_missing=True)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    managed_path(result_path.parent)

    environment = os.environ.copy()
    if os.name == "nt":
        system_root = environment.get("SystemRoot", r"C:\Windows")
        environment["PATH"] = os.pathsep.join(
            [*(str(path) for path in library_dirs), str(Path(system_root) / "System32")]
        )
    elif library_dirs:
        environment["LD_LIBRARY_PATH"] = os.pathsep.join(str(path) for path in library_dirs)

    cases = [
        run_case(
            probe,
            "success",
            SUCCESS_MARKER,
            environment,
            timeout,
            expect_success=True,
        )
    ]
    for mode, marker in DEATH_CASES.items():
        cases.append(
            run_case(
                probe,
                mode,
                marker,
                environment,
                timeout,
                expect_success=False,
            )
        )

    record = {
        "schema_version": 1,
        "target_id": target_id,
        "probe": probe.name,
        "success_cases": 1,
        "death_cases": len(DEATH_CASES),
        "cases": cases,
    }
    temporary = result_path.with_name(result_path.name + ".tmp")
    temporary.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, result_path)
    print(
        f"W013_MSPACE_OWNER_GATE_PASS target={target_id} "
        f"success=1 death={len(DEATH_CASES)}"
    )
    return record


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--target-id", required=True)
    result.add_argument("--probe", type=Path, required=True)
    result.add_argument("--result", type=Path, required=True)
    result.add_argument("--library-dir", type=Path, action="append", default=[])
    result.add_argument("--timeout", type=int, default=10)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.timeout < 1:
        print("mspace_owner_gate.py: error: --timeout must be positive", file=sys.stderr)
        return 2
    try:
        run_gate(
            target_id=args.target_id,
            probe=args.probe,
            result_path=args.result,
            library_dirs=args.library_dir,
            timeout=args.timeout,
        )
        return 0
    except (GateError, OSError, UnicodeError) as error:
        print(f"mspace_owner_gate.py: error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
