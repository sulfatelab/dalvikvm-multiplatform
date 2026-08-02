#!/usr/bin/env python3
"""Build a relocatable ART boot image with target dex2oat and no shell."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile


LOGICAL_BOOT_JAR = "/system/framework/boot.jar"
IMAGE_BASE = "0x70000000"
IMAGE_FILES = ("boot.art", "boot.oat", "boot.vdex")
INSTRUCTION_SETS = frozenset({"arm", "arm64", "riscv64", "x86", "x86_64"})


class BootImageError(RuntimeError):
    """The boot image command or its output violated the product contract."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--dex2oat", type=Path, required=True)
    parser.add_argument("--boot-jar", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--instruction-set", required=True)
    parser.add_argument("--parallel", type=int, required=True)
    parser.add_argument("--library-dir", type=Path, action="append", default=[])
    parser.add_argument("--timeout", type=int, default=1800)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        build_boot_image(args)
        return 0
    except (BootImageError, OSError, subprocess.SubprocessError) as exc:
        print(f"build_boot_image.py: error: {exc}", file=sys.stderr)
        return 2


def build_boot_image(args: argparse.Namespace) -> Path:
    if re.fullmatch(r"[a-z0-9][a-z0-9_-]*(?:-[a-z0-9_]+)+", args.target_id) is None:
        raise BootImageError(f"non-canonical target ID: {args.target_id!r}")
    if args.instruction_set not in INSTRUCTION_SETS:
        raise BootImageError(
            f"unsupported ART instruction set: {args.instruction_set!r}"
        )
    if not 1 <= args.parallel <= 64:
        raise BootImageError("parallelism must be between 1 and 64")
    if args.timeout < 1:
        raise BootImageError("timeout must be positive")

    dex2oat = _regular_file(args.dex2oat)
    boot_jar = _regular_file(args.boot_jar)
    library_dirs = [_directory(path) for path in args.library_dir]
    if dex2oat.parent not in library_dirs:
        library_dirs.insert(0, dex2oat.parent)

    output_root = _path(args.output_root, allow_missing=True)
    if output_root.name != "boot-image":
        raise BootImageError("output root must be a target-local boot-image directory")
    output_parent = _path(output_root.parent, allow_missing=True)
    output_parent.mkdir(parents=True, exist_ok=True)
    output_parent = _directory(output_parent)
    if output_root.exists() or output_root.is_symlink():
        _directory(output_root)
        _reject_tree_links(output_root)

    work_root = Path(
        tempfile.mkdtemp(prefix=".boot-image-work-", dir=output_parent)
    )
    image_root = work_root / "image"
    image_dir = image_root / args.instruction_set
    runtime_root = work_root / "runtime"
    for directory in (
        image_dir,
        runtime_root / "data",
        runtime_root / "icu",
        runtime_root / "tmp",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    command = [
        str(dex2oat),
        f"--dex-file={boot_jar}",
        f"--dex-location={LOGICAL_BOOT_JAR}",
        f"--image={image_dir / 'boot.art'}",
        f"--oat-file={image_dir / 'boot.oat'}",
        f"--base={IMAGE_BASE}",
        f"--instruction-set={args.instruction_set}",
        "--image-format=uncompressed",
        "--compiler-filter=speed",
        "--no-watch-dog",
        "--runtime-arg",
        f"-Xbootclasspath:{boot_jar}",
        "--runtime-arg",
        f"-Xbootclasspath-locations:{LOGICAL_BOOT_JAR}",
        "--runtime-arg",
        "-Xms64m",
        "--runtime-arg",
        "-Xmx512m",
        "--avoid-storing-invocation",
        "--force-determinism",
        f"-j{args.parallel}",
    ]
    environment = dict(os.environ)
    environment.update(
        {
            "ANDROID_ROOT": str(runtime_root),
            "ANDROID_ART_ROOT": str(runtime_root),
            "ANDROID_I18N_ROOT": str(runtime_root),
            "ANDROID_DATA": str(runtime_root / "data"),
            "ICU_DATA": str(runtime_root / "icu"),
            "TMP": str(runtime_root / "tmp"),
            "TEMP": str(runtime_root / "tmp"),
            "TMPDIR": str(runtime_root / "tmp"),
        }
    )
    if os.name == "nt":
        system_root = environment.get("SystemRoot", r"C:\Windows")
        environment["PATH"] = os.pathsep.join(
            [
                *(str(path) for path in library_dirs),
                str(Path(system_root) / "System32"),
            ]
        )
    else:
        environment["LD_LIBRARY_PATH"] = os.pathsep.join(
            str(path) for path in library_dirs
        )

    try:
        result = subprocess.run(
            command,
            cwd=output_parent,
            env=environment,
            shell=False,
            check=False,
            capture_output=True,
            text=True,
            timeout=args.timeout,
        )
        expected = [image_dir / name for name in IMAGE_FILES]
        missing = [path.name for path in expected if not path.is_file()]
        if result.returncode or missing:
            tail = "\n".join((result.stdout + "\n" + result.stderr).splitlines()[-80:])
            raise BootImageError(
                f"dex2oat failed: exit={result.returncode}, missing={missing}\n{tail}"
            )
        for path in expected:
            _regular_file(path)
            if path.stat().st_size == 0:
                raise BootImageError(f"dex2oat produced an empty artifact: {path.name}")
        _reject_embedded_machine_paths(
            expected,
            (
                dex2oat,
                dex2oat.parent,
                boot_jar,
                boot_jar.parent,
                output_parent,
                work_root,
                *library_dirs,
            ),
        )

        log = image_root / "dex2oat.log"
        log.write_text(
            "stdout:\n" + result.stdout + "\nstderr:\n" + result.stderr,
            encoding="utf-8",
        )
        manifest = {
            "schema_version": 1,
            "target_id": args.target_id,
            "instruction_set": args.instruction_set,
            "logical_boot_jar": LOGICAL_BOOT_JAR,
            "boot_jar_sha256": _sha256(boot_jar),
            "image_base": IMAGE_BASE,
            "compiler_filter": "speed",
            "runtime_heap": {"initial": "64m", "maximum": "512m"},
            "artifacts": [
                {
                    "path": f"{args.instruction_set}/{path.name}",
                    "sha256": _sha256(path),
                    "size": path.stat().st_size,
                }
                for path in expected
            ],
        }
        (image_root / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _replace_output_tree(image_root, output_root)
    finally:
        if work_root.exists():
            shutil.rmtree(work_root)

    print(
        f"built boot image for {args.target_id}: "
        + ", ".join(
            f"{path.name}={path.stat().st_size}"
            for path in sorted(
                (output_root / args.instruction_set).iterdir(),
                key=lambda value: value.name,
            )
            if path.name in IMAGE_FILES
        )
    )
    return output_root


def _replace_output_tree(staged: Path, destination: Path) -> None:
    backup = destination.parent / f".{destination.name}.previous"
    if backup.exists() or backup.is_symlink():
        _directory(backup)
        _reject_tree_links(backup)
        shutil.rmtree(backup)
    had_destination = destination.exists()
    if had_destination:
        os.replace(destination, backup)
    try:
        os.replace(staged, destination)
    except BaseException:
        if had_destination and backup.exists():
            os.replace(backup, destination)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def _reject_embedded_machine_paths(paths: list[Path], inputs: tuple[Path, ...]) -> None:
    needles: set[bytes] = set()
    for path in inputs:
        value = str(path)
        for spelling in (value, value.replace("\\", "/"), value.replace("/", "\\")):
            if len(spelling) >= 4:
                needles.add(spelling.encode("utf-8"))
    for path in paths:
        data = path.read_bytes()
        if any(needle in data for needle in needles):
            raise BootImageError(f"{path.name} embeds a build-machine path")


def _path(path: Path, *, allow_missing: bool = False) -> Path:
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
            raise BootImageError(f"existing path below a missing component: {current}")
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & reparse:
            raise BootImageError(f"link/reparse path is forbidden: {current}")
    if not allow_missing and not path.exists():
        raise BootImageError(f"managed path does not exist: {path}")
    return path


def _regular_file(path: Path) -> Path:
    path = _path(path)
    if not path.is_file():
        raise BootImageError(f"required regular file is missing: {path}")
    return path


def _directory(path: Path) -> Path:
    path = _path(path)
    if not path.is_dir():
        raise BootImageError(f"required directory is missing: {path}")
    return path


def _reject_tree_links(root: Path) -> None:
    _path(root)
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in (*directories, *files):
            _path(current_path / name)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
