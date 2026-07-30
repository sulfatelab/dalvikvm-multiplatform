"""Run one subprocess without a shell and atomically capture its stdout."""

from __future__ import annotations

import sys

# This file is also invoked as a script by generated Ninja rules.  In that
# mode Python puts this package directory first on sys.path; its ast.py would
# shadow the standard-library ast module imported by argparse/dataclasses.
_script_dir = __file__.rsplit("/", 1)[0]
if sys.path and sys.path[0].endswith(_script_dir):
    sys.path.pop(0)

import argparse
import os
import subprocess
import tempfile
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bp2cmake.capture_output")
    parser.add_argument("--output", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    command = list(args.command)
    if command and command[0] == "--":
        command.pop(0)
    if not command:
        parser.error("a command is required after --")

    result = subprocess.run(command, shell=False, check=True, stdout=subprocess.PIPE)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.read_bytes() == result.stdout:
        return 0

    handle, staged_name = tempfile.mkstemp(prefix=output.name + ".", dir=output.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(result.stdout)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staged_name, output)
    except BaseException:
        try:
            os.unlink(staged_name)
        except FileNotFoundError:
            pass
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
