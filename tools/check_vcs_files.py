#!/usr/bin/env python3
"""Reject generated binaries and package archives tracked by the main repo."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]

# This list is intentionally extension-based and portable. Content-level binary
# detection is not stable across Git/Windows hosts and does not replace review.
FORBIDDEN_SUFFIXES = frozenset(
    {
        ".7z",
        ".a",
        ".class",
        ".dex",
        ".dll",
        ".dmp",
        ".exe",
        ".exp",
        ".gz",
        ".ilk",
        ".jar",
        ".lib",
        ".o",
        ".obj",
        ".pdb",
        ".so",
        ".tar",
        ".tgz",
        ".txz",
        ".wasm",
        ".xz",
        ".zip",
    }
)

# AOSP's pinned R8 archive supplies D8. It is deliberately retained because a
# reproducible source build is not currently available to this project.
TRACKED_BINARY_EXCEPTIONS = frozenset({"vendor/r8/r8.jar"})


def tracked_paths(repo_root: Path = REPO_ROOT) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "-z"],
        check=True,
        stdout=subprocess.PIPE,
    )
    return [os.fsdecode(item) for item in result.stdout.split(b"\0") if item]


def forbidden_tracked_paths(paths: Iterable[str]) -> list[str]:
    rejected: list[str] = []
    for raw_path in paths:
        path = raw_path.replace("\\", "/")
        if path in TRACKED_BINARY_EXCEPTIONS:
            continue
        if PurePosixPath(path).suffix.lower() in FORBIDDEN_SUFFIXES:
            rejected.append(path)
    return sorted(rejected)


def main() -> int:
    rejected = forbidden_tracked_paths(tracked_paths())
    if not rejected:
        print("VCS binary/archive audit passed")
        return 0
    print("generated binary/archive files must not be tracked:", file=sys.stderr)
    for path in rejected:
        print(f"  {path}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
