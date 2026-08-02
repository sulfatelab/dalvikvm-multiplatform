#!/usr/bin/env python3
"""Shell-free in-repository CI entry point for the unified ART build."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_FRONTEND = REPO_ROOT / "tools" / "build_art.py"
VCS_AUDIT = REPO_ROOT / "tools" / "check_vcs_files.py"
CI_CONFIG_ENV = "ART_BUILD_CI_CONFIG"
CI_RUN_KEY_ENV = "ART_BUILD_CI_RUN_KEY"


class CIError(RuntimeError):
    """Raised for a deterministic CI contract failure."""


@dataclass(frozen=True)
class Cell:
    name: str
    host_platform: str
    host_arch: str
    target_id: str | None
    parallel: int | None
    run_target_tests: bool


CELLS = {
    "host-checks": Cell("host-checks", "linux", "x86_64", None, None, False),
    "linux-product": Cell(
        "linux-product", "linux", "x86_64", "linux-x86_64-gnu", 32, True
    ),
    "windows-cross": Cell(
        "windows-cross", "linux", "x86_64", "windows-x86_64-msvc", 32, False
    ),
    "windows-native": Cell(
        "windows-native", "windows", "x86_64", "windows-x86_64-msvc", 16, True
    ),
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ci_art.py")
    parser.add_argument("--cell", choices=tuple(CELLS), required=True)
    parser.add_argument("--run-key")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _canonical_host_arch(value: str) -> str:
    normalized = value.lower()
    return {
        "amd64": "x86_64",
        "x64": "x86_64",
        "arm64": "aarch64",
        "i386": "x86",
        "i686": "x86",
    }.get(normalized, normalized)


def _validate_host(cell: Cell) -> None:
    actual_platform = platform.system().lower()
    actual_arch = _canonical_host_arch(platform.machine())
    if actual_platform != cell.host_platform or actual_arch != cell.host_arch:
        raise CIError(
            f"cell {cell.name} requires {cell.host_platform}-{cell.host_arch}, "
            f"got {actual_platform}-{actual_arch}"
        )


def _validated_run_key(explicit: str | None) -> str:
    value = explicit or os.environ.get(CI_RUN_KEY_ENV)
    if not value:
        raise CIError(f"set {CI_RUN_KEY_ENV} or pass --run-key")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", value):
        raise CIError("CI run key must be 1-96 portable filename characters")
    return value


def _frontend_command(
    action: str,
    cell: Cell,
    output_root: Path,
) -> list[str]:
    assert cell.target_id is not None
    command = [
        sys.executable,
        str(BUILD_FRONTEND),
        action,
        "--target-id",
        cell.target_id,
        "--output-root",
        str(output_root),
    ]
    if action in ("build", "test"):
        assert cell.parallel is not None
        command.extend(("--parallel", str(cell.parallel)))
    return command


def commands_for_cell(cell: Cell, output_root: Path | None) -> list[list[str]]:
    commands = [[sys.executable, str(VCS_AUDIT)]]
    if cell.target_id is None:
        commands.append(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tools/bp2cmake/tests",
                "tests/host",
            ]
        )
        return commands
    assert output_root is not None
    commands.extend(
        (
            _frontend_command("configure", cell, output_root),
            _frontend_command("check-generated", cell, output_root),
            _frontend_command("build", cell, output_root),
            _frontend_command("build", cell, output_root),
        )
    )
    if cell.run_target_tests:
        commands.append(_frontend_command("test", cell, output_root))
    commands.append(_frontend_command("stage", cell, output_root))
    return commands


def _run(command: list[str], environment: dict[str, str]) -> None:
    print("ci_art.py: " + json.dumps(command), flush=True)
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=environment,
        shell=False,
        check=False,
    )
    if result.returncode:
        raise CIError(
            f"command failed with exit code {result.returncode}: {command[1]}"
        )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    cell = CELLS[args.cell]
    try:
        if not args.dry_run:
            _validate_host(cell)
        output_root = None
        if cell.target_id is not None:
            run_key = _validated_run_key(args.run_key)
            output_root = REPO_ROOT / "out" / "ci" / run_key / cell.name
            if output_root.exists():
                raise CIError(
                    f"fresh CI output root already exists: {output_root}"
                )
            if not args.dry_run and not os.environ.get(CI_CONFIG_ENV):
                raise CIError(
                    f"product cells require {CI_CONFIG_ENV} to name the "
                    "machine-local TOML configuration"
                )
        commands = commands_for_cell(cell, output_root)
        if args.dry_run:
            for command in commands:
                print(json.dumps(command))
            return 0
        environment = dict(os.environ)
        pythonpath = str(REPO_ROOT / "tools" / "bp2cmake")
        previous = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = pythonpath + (
            os.pathsep + previous if previous else ""
        )
        for command in commands:
            _run(command, environment)
        return 0
    except (CIError, OSError) as exc:
        print(f"ci_art.py: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
