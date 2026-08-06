#!/usr/bin/env python3
"""Stage and run the experimental boot-only Windows ART package."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

if __package__:
    from . import windows_aot_identity
else:
    import windows_aot_identity  # type: ignore[no-redef]


class WindowsBootImageError(RuntimeError):
    """The generated boot set or package startup violated its contract."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--dalvikvm", type=Path, required=True)
    parser.add_argument("--boot-jar", type=Path, required=True)
    parser.add_argument("--app-jar", type=Path, required=True)
    parser.add_argument("--boot-image-dir", type=Path, required=True)
    parser.add_argument("--icu-data", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--library-dir", type=Path, action="append", default=[])
    parser.add_argument("--main-class", default="Hello")
    parser.add_argument(
        "--execution-mode", choices=("interpreter", "aot"), default="interpreter"
    )
    parser.add_argument("--probe", type=Path)
    parser.add_argument("--probe-name")
    parser.add_argument("--expect", action="append", default=[])
    parser.add_argument("--forbid", action="append", default=[])
    parser.add_argument("--timeout", type=int, default=180)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        run_gate(args)
        return 0
    except (
        OSError,
        subprocess.SubprocessError,
        WindowsBootImageError,
        windows_aot_identity.WindowsAotIdentityError,
    ) as exc:
        print(f"run_windows_boot_image.py: error: {exc}", file=sys.stderr)
        return 2


def run_gate(args: argparse.Namespace) -> Path:
    if args.target_id != windows_aot_identity.TARGET_ID:
        raise WindowsBootImageError(
            "the experimental launcher accepts only "
            f"{windows_aot_identity.TARGET_ID}, got {args.target_id!r}"
        )
    if args.timeout < 1:
        raise WindowsBootImageError("timeout must be positive")

    dalvikvm = _regular_file(args.dalvikvm)
    boot_jar = _regular_file(args.boot_jar)
    app_jar = _regular_file(args.app_jar)
    icu_data = _regular_file(args.icu_data)
    image_root = _directory(args.boot_image_dir)
    library_dirs = [_directory(path) for path in args.library_dir]
    if dalvikvm.parent not in library_dirs:
        library_dirs.insert(0, dalvikvm.parent)

    manifest = _validate_image_manifest(image_root, boot_jar, args.target_id)
    main_class = getattr(args, "main_class", "Hello")
    execution_mode = getattr(args, "execution_mode", "interpreter")
    probe_arg = getattr(args, "probe", None)
    probe_name = getattr(args, "probe_name", None)
    if not main_class or any(character.isspace() for character in main_class):
        raise WindowsBootImageError("main class must be one nonempty token")
    if execution_mode not in ("interpreter", "aot"):
        raise WindowsBootImageError(f"unsupported execution mode: {execution_mode!r}")
    if (probe_arg is None) != (probe_name is None):
        raise WindowsBootImageError("--probe and --probe-name must be supplied together")
    if probe_name is not None and (
        not probe_name or not all(character.isalnum() or character == "_" for character in probe_name)
    ):
        raise WindowsBootImageError("probe name must contain only letters, digits, or underscore")
    work_root = _prepare_output_root(args.work_root)
    package_root = work_root / "package"
    runtime_root = package_root / "runtime"
    image_destination = runtime_root / "boot-image"
    for directory in (
        runtime_root / "data",
        runtime_root / "icu",
        runtime_root / "tmp",
        image_destination / windows_aot_identity.INSTRUCTION_SET,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    shutil.copyfile(boot_jar, runtime_root / "boot.jar")
    shutil.copyfile(app_jar, runtime_root / "hello.jar")
    if probe_arg is not None:
        probe = _regular_file(probe_arg)
        for filename in (f"lib{probe_name}.dll", f"{probe_name}.dll"):
            shutil.copyfile(probe, package_root / filename)
    shutil.copyfile(icu_data, runtime_root / "icu" / icu_data.name)
    artifact_records: list[dict[str, object]] = []
    for record in manifest["artifacts"]:
        relative = str(record["path"])
        source = _regular_file(image_root / Path(relative))
        destination = image_destination / Path(relative)
        shutil.copyfile(source, destination)
        artifact_records.append(
            {
                "path": f"runtime/boot-image/{relative}",
                "size": destination.stat().st_size,
                "sha256": _sha256(destination),
            }
        )
    shutil.copyfile(image_root / "manifest.json", image_destination / "manifest.json")

    generation_identity = windows_aot_identity.identity_from_contract_record(
        manifest["windows_aot_identity"]
    )
    rejected: list[dict[str, str]] = []
    for name, startup, expected_field in (
        windows_aot_identity.intentional_startup_mismatches()
    ):
        try:
            _startup_command(
                dalvikvm,
                startup,
                main_class=main_class,
                execution_mode=execution_mode,
                probe_name=probe_name,
            )
        except windows_aot_identity.WindowsAotIdentityError as exc:
            if exc.field != expected_field:
                raise WindowsBootImageError(
                    f"launcher mismatch {name} reported {exc.field!r}, "
                    f"expected {expected_field!r}"
                ) from exc
            rejected.append(
                {"case": name, "field": exc.field, "diagnostic": str(exc)}
            )
        else:
            raise WindowsBootImageError(f"launcher accepted intentional mismatch {name}")

    command = _startup_command(
        dalvikvm,
        generation_identity,
        main_class=main_class,
        execution_mode=execution_mode,
        probe_name=probe_name,
    )
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
            [*(str(path) for path in library_dirs), str(Path(system_root) / "System32")]
        )
    else:
        environment["LD_LIBRARY_PATH"] = os.pathsep.join(
            str(path) for path in library_dirs
        )
    result = subprocess.run(
        command,
        cwd=package_root,
        env=environment,
        shell=False,
        check=False,
        capture_output=True,
        text=True,
        timeout=args.timeout,
    )
    (work_root / "stdout.txt").write_text(result.stdout, encoding="utf-8")
    (work_root / "stderr.txt").write_text(result.stderr, encoding="utf-8")
    combined = result.stdout + "\n" + result.stderr
    required = tuple(getattr(args, "expect", ())) or (
        "Hello from dalvikvm!",
        "main end exception=0",
    )
    forbidden = (
        "Attempting to fall back to imageless running",
        "InitWithoutImage",
        "Failed to load oat file",
        *tuple(getattr(args, "forbid", ())),
    )
    missing = [marker for marker in required if marker not in combined]
    present = [marker for marker in forbidden if marker in combined]

    record = {
        "schema_version": 1,
        "target_id": args.target_id,
        "windows_aot_identity": windows_aot_identity.contract_record(),
        "startup_options": list(windows_aot_identity.startup_options()),
        "main_class": main_class,
        "execution_mode": execution_mode,
        "working_directory": "package",
        "actual_exit": result.returncode,
        "missing_markers": missing,
        "forbidden_markers": present,
        "launcher_rejected_mismatches": rejected,
        "boot_jar_sha256": _sha256(runtime_root / "boot.jar"),
        "artifacts": sorted(artifact_records, key=lambda item: str(item["path"])),
    }
    (work_root / "result.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if result.returncode != 0 or missing or present:
        tail = "\n".join(combined.splitlines()[-100:])
        raise WindowsBootImageError(
            f"boot-image startup failed: exit={result.returncode}, "
            f"missing={missing}, forbidden={present}\n{tail}"
        )
    print(
        "native Windows boot-image gate passed: "
        f"artifacts={len(artifact_records)}, mismatches={len(rejected)}"
    )
    return work_root


def _startup_command(
    dalvikvm: Path,
    startup: windows_aot_identity.IdentityUse,
    *,
    main_class: str = "Hello",
    execution_mode: str = "interpreter",
    probe_name: str | None = None,
) -> list[str]:
    windows_aot_identity.validate_generation_startup(
        windows_aot_identity.CANONICAL_IDENTITY, startup
    )
    boot_locations = ":".join(startup.boot_class_path_locations)
    command = [
        str(dalvikvm),
        "-Xbootclasspath:runtime/boot.jar",
        f"-Xbootclasspath-locations:{boot_locations}",
        f"-Ximage:{startup.image_location}",
        "-XjdwpProvider:none",
        "-Xms64m",
        "-Xmx512m",
    ]
    command.append("-Xint" if execution_mode == "interpreter" else "-Xusejit:false")
    if probe_name is not None:
        command.append("-Djava.library.path=.")
    command.extend(("-cp", "runtime/hello.jar", main_class))
    return command


def _validate_image_manifest(
    image_root: Path, boot_jar: Path, target_id: str
) -> dict[str, object]:
    manifest_path = _regular_file(image_root / "manifest.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise WindowsBootImageError(f"invalid boot image manifest: {exc}") from exc
    if not isinstance(manifest, dict):
        raise WindowsBootImageError("boot image manifest is not an object")
    expected_options = list(windows_aot_identity.generation_options())
    if (
        manifest.get("schema_version") != 1
        or manifest.get("target_id") != target_id
        or manifest.get("instruction_set") != windows_aot_identity.INSTRUCTION_SET
        or manifest.get("logical_boot_jar") != windows_aot_identity.LOGICAL_BOOT_JAR
        or manifest.get("image_format") != "lz4"
        or manifest.get("boot_jar_sha256") != _sha256(boot_jar)
        or manifest.get("generation_options") != expected_options
    ):
        raise WindowsBootImageError("boot image manifest does not match runtime inputs")
    windows_aot_identity.identity_from_contract_record(
        manifest.get("windows_aot_identity")
    )

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise WindowsBootImageError("boot image manifest has no artifact list")
    expected = {
        path.removeprefix("runtime/boot-image/")
        for path in windows_aot_identity.PACKAGE_IMAGE_FILES
    }
    seen: set[str] = set()
    for raw in artifacts:
        if not isinstance(raw, dict) or not isinstance(raw.get("path"), str):
            raise WindowsBootImageError("boot image artifact record is malformed")
        relative = raw["path"]
        if relative not in expected or relative in seen:
            raise WindowsBootImageError(f"unexpected boot image artifact: {relative!r}")
        source = _regular_file(image_root / Path(relative))
        if raw.get("size") != source.stat().st_size or raw.get("sha256") != _sha256(source):
            raise WindowsBootImageError(f"boot image artifact identity changed: {relative}")
        seen.add(relative)
    if seen != expected:
        raise WindowsBootImageError(
            f"boot image artifact set is incomplete: {sorted(expected - seen)}"
        )
    return manifest


def _prepare_output_root(path: Path) -> Path:
    path = _managed_path(path, allow_missing=True)
    if path == Path(path.anchor) or path == path.parent:
        raise WindowsBootImageError(f"unsafe work root: {path}")
    parent = _managed_path(path.parent, allow_missing=True)
    parent.mkdir(parents=True, exist_ok=True)
    parent = _directory(parent)
    if path.exists() or path.is_symlink():
        _directory(path)
        _reject_tree_links(path)
        shutil.rmtree(path)
    path.mkdir()
    return _directory(path)


def _managed_path(path: Path, *, allow_missing: bool = False) -> Path:
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
            raise WindowsBootImageError(
                f"existing path below a missing component: {current}"
            )
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & reparse:
            raise WindowsBootImageError(f"link/reparse path is forbidden: {current}")
    if not allow_missing and not path.exists():
        raise WindowsBootImageError(f"managed path does not exist: {path}")
    return path


def _regular_file(path: Path) -> Path:
    path = _managed_path(path)
    if not path.is_file():
        raise WindowsBootImageError(f"required regular file is missing: {path}")
    return path


def _directory(path: Path) -> Path:
    path = _managed_path(path)
    if not path.is_dir():
        raise WindowsBootImageError(f"required directory is missing: {path}")
    return path


def _reject_tree_links(root: Path) -> None:
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        for name in (*directories, *files):
            _managed_path(Path(current) / name)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
