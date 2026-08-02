#!/usr/bin/env python3
"""Generate Conscrypt NativeConstants.java with a host plain-Clang tool."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile


class GenerationError(RuntimeError):
    """The host constants generator violated its build contract."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--include-dir", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--package", default="com.android.org.conscrypt")
    parser.add_argument("--compile-option", action="append", default=[])
    parser.add_argument("--link-option", action="append", default=[])
    return parser


def _managed_path(path: Path, *, allow_missing: bool = False) -> Path:
    path = Path(os.path.abspath(path))
    missing = False
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            missing = True
            continue
        if missing:
            raise GenerationError(f"existing path below missing component: {current}")
        attributes = getattr(info, "st_file_attributes", 0)
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if stat.S_ISLNK(info.st_mode) or attributes & reparse:
            raise GenerationError(f"link/reparse path is forbidden: {current}")
    if not allow_missing and not path.exists():
        raise GenerationError(f"managed path does not exist: {path}")
    return path


def _regular_file(path: Path) -> Path:
    path = _managed_path(path)
    if not path.is_file():
        raise GenerationError(f"required regular file is missing: {path}")
    return path


def _driver_options(values: list[str], kind: str) -> list[str]:
    result = []
    for value in values:
        if not value or "\0" in value or "\n" in value or "\r" in value:
            raise GenerationError(f"invalid host {kind} option: {value!r}")
        result.append(value)
    return result


def generate(args: argparse.Namespace) -> None:
    compiler = _regular_file(args.compiler)
    if compiler.name not in ("clang++", "clang++.exe"):
        raise GenerationError(f"plain Clang++ driver required: {compiler}")
    source = _regular_file(args.source)
    include_dir = _managed_path(args.include_dir)
    work_root = _managed_path(args.work_root, allow_missing=True)
    output = _managed_path(args.output, allow_missing=True)
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", args.package) is None:
        raise GenerationError(f"invalid Java package: {args.package!r}")
    work_root.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    _managed_path(work_root)
    _managed_path(output.parent)

    suffix = ".exe" if os.name == "nt" else ""
    executable = work_root / f"conscrypt-generate-constants{suffix}"
    compile_options = _driver_options(args.compile_option, "compile")
    link_options = _driver_options(args.link_option, "link")
    command = [
        str(compiler),
        "-std=c++17",
        "-O0",
        *compile_options,
        f"-I{include_dir}",
        str(source),
        "-o",
        str(executable),
        *link_options,
    ]
    compiled = subprocess.run(
        command, text=True, capture_output=True, check=False, shell=False
    )
    (work_root / "compile.stdout.txt").write_text(
        compiled.stdout, encoding="utf-8"
    )
    (work_root / "compile.stderr.txt").write_text(
        compiled.stderr, encoding="utf-8"
    )
    if compiled.returncode:
        raise GenerationError(
            f"host Clang++ failed with exit code {compiled.returncode}"
        )
    _regular_file(executable)

    generated = subprocess.run(
        [str(executable), args.package],
        text=True,
        capture_output=True,
        check=False,
        shell=False,
    )
    (work_root / "generator.stderr.txt").write_text(
        generated.stderr, encoding="utf-8"
    )
    marker = f"package {args.package};"
    if generated.returncode or marker not in generated.stdout:
        raise GenerationError(
            "Conscrypt constants generator failed or emitted the wrong package"
        )

    handle, staged = tempfile.mkstemp(prefix=output.name + ".", dir=output.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(generated.stdout.replace("\r\n", "\n"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staged, output)
    except BaseException:
        try:
            os.unlink(staged)
        except FileNotFoundError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        generate(args)
        return 0
    except (GenerationError, OSError, subprocess.SubprocessError) as exc:
        print(f"generate_conscrypt_constants.py: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
