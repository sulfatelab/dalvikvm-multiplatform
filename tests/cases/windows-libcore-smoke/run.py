#!/usr/bin/env python3
"""Run one accepted Windows libcore smoke case without shell tooling."""

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


_MATRIX_PATH = Path(__file__).with_name("runtime-matrix.json")
_COMMON_FORBIDDEN = [
    "AssertionError",
    "ART Win32 VEH",
    "ART Win32 UEF",
    "Check failed",
    "Fatal signal",
    "minidump written",
]


def load_matrix(path: Path = _MATRIX_PATH) -> dict[str, dict[str, object]]:
    path = runtime_gate._regular_file(str(path))
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise runtime_gate.GateError(f"invalid libcore matrix: {exc}") from exc
    if not isinstance(document, dict) or set(document) != {"schema_version", "cases"}:
        raise runtime_gate.GateError(
            "libcore matrix must contain exactly schema_version and cases"
        )
    if document["schema_version"] != 1:
        raise runtime_gate.GateError(
            f"unsupported libcore matrix schema: {document['schema_version']!r}"
        )
    raw_cases = document["cases"]
    if not isinstance(raw_cases, dict) or not raw_cases:
        raise runtime_gate.GateError("libcore matrix cases must be a non-empty object")

    allowed = {"expected_markers", "forbidden_markers", "require_nonzero", "timeout_seconds"}
    cases: dict[str, dict[str, object]] = {}
    for name, raw_case in raw_cases.items():
        if not isinstance(name, str) or not name.isidentifier():
            raise runtime_gate.GateError(f"invalid libcore main class: {name!r}")
        if not isinstance(raw_case, dict) or not set(raw_case) <= allowed:
            raise runtime_gate.GateError(f"libcore case {name} has unknown fields")
        expected = raw_case.get("expected_markers")
        forbidden = raw_case.get("forbidden_markers", [])
        require_nonzero = raw_case.get("require_nonzero", False)
        timeout = raw_case.get("timeout_seconds")
        if not isinstance(expected, list) or not expected or not all(
            isinstance(marker, str) and marker for marker in expected
        ):
            raise runtime_gate.GateError(
                f"libcore case {name} expected markers must be non-empty strings"
            )
        if not isinstance(forbidden, list) or not all(
            isinstance(marker, str) and marker for marker in forbidden
        ):
            raise runtime_gate.GateError(
                f"libcore case {name} forbidden markers must be strings"
            )
        if not isinstance(require_nonzero, bool):
            raise runtime_gate.GateError(
                f"libcore case {name} require_nonzero must be boolean"
            )
        if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout < 1:
            raise runtime_gate.GateError(
                f"libcore case {name} timeout_seconds must be a positive integer"
            )
        cases[name] = {
            "expected_markers": list(expected),
            "forbidden_markers": [*_COMMON_FORBIDDEN, *forbidden],
            "require_nonzero": require_nonzero,
            "timeout_seconds": timeout,
        }
    return cases


def run_gate(
    *,
    case: str,
    target_id: str,
    dalvikvm: Path,
    boot_jar: Path,
    app_jar: Path,
    work_root: Path,
    icu_data: Path,
    library_dirs: list[Path],
) -> None:
    matrix = load_matrix()
    if case not in matrix:
        raise runtime_gate.GateError(f"unknown Windows libcore case: {case}")
    config = matrix[case]

    work_root = runtime_gate._managed_path(work_root, allow_missing=True)
    if work_root.exists() or work_root.is_symlink():
        runtime_gate._reject_tree_links(work_root)
        shutil.rmtree(work_root)

    runtime_gate.run_managed(
        target_id=target_id,
        dalvikvm=dalvikvm,
        boot_jar=boot_jar,
        app_jar=app_jar,
        main_class=case,
        work_root=work_root,
        icu_data=icu_data,
        library_dirs=library_dirs,
        vm_options=["-Xint"],
        main_args=[],
        expected=config["expected_markers"],
        forbidden=config["forbidden_markers"],
        expected_exit=0,
        timeout=config["timeout_seconds"],
        require_nonzero=config["require_nonzero"],
    )
    runtime_gate._reject_tree_links(work_root)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--dalvikvm", type=Path, required=True)
    parser.add_argument("--boot-jar", type=Path, required=True)
    parser.add_argument("--app-jar", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--icu-data", type=Path, required=True)
    parser.add_argument("--library-dir", type=Path, action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        run_gate(
            case=args.case,
            target_id=args.target_id,
            dalvikvm=args.dalvikvm,
            boot_jar=args.boot_jar,
            app_jar=args.app_jar,
            work_root=args.work_root,
            icu_data=args.icu_data,
            library_dirs=args.library_dir,
        )
        return 0
    except (runtime_gate.GateError, OSError, UnicodeError) as exc:
        print(f"windows-libcore-smoke/run.py: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
