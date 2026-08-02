#!/usr/bin/env python3
"""Build ART boot and test DEX JARs without a shell or source-tree output."""

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
import zipfile


REPO_ROOT = Path(__file__).resolve().parents[2]
BP2CMAKE_ROOT = REPO_ROOT / "tools" / "bp2cmake"
if str(BP2CMAKE_ROOT) not in sys.path:
    sys.path.insert(0, str(BP2CMAKE_ROOT))

from bp2cmake import aconfig  # noqa: E402


class ManagedArtifactError(RuntimeError):
    """Raised for deterministic managed-artifact build failures."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jdk-root", type=Path, required=True)
    parser.add_argument("--r8-jar", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--source", type=Path, action="append", default=[])
    parser.add_argument("--source-tree", type=Path, action="append", default=[])
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--aconfig", type=Path, action="append", default=[])
    parser.add_argument(
        "--resource",
        nargs=2,
        action="append",
        default=[],
        metavar=("SOURCE", "JAR_PATH"),
    )
    parser.add_argument("--boot-classpath", type=Path)
    parser.add_argument("--patch-module", type=Path)
    parser.add_argument("--javac-option", action="append", default=[])
    parser.add_argument("--android-platform-build", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        build_managed_artifact(args)
        return 0
    except (ManagedArtifactError, OSError, subprocess.SubprocessError) as exc:
        print(f"managed_artifact.py: error: {exc}", file=sys.stderr)
        return 2


def build_managed_artifact(args: argparse.Namespace) -> tuple[Path, Path]:
    if re.fullmatch(r"[a-z0-9][a-z0-9._-]*", args.name) is None:
        raise ManagedArtifactError(f"non-canonical artifact name: {args.name!r}")

    source_root = _validate_path(args.source_root)
    output_root = _validate_path(args.output_root, allow_missing=True)

    jdk_root, java, javac = _validate_jdk(args.jdk_root)
    r8_jar = _validate_regular_file(args.r8_jar)
    if r8_jar != source_root / "vendor" / "r8" / "r8.jar":
        raise ManagedArtifactError(
            "the managed build must use the pinned vendor/r8/r8.jar"
        )

    output_root.mkdir(parents=True, exist_ok=True)
    _validate_path(output_root)
    classes = output_root / "classes" / args.name
    dex = output_root / "dex" / args.name
    generated = output_root / "generated" / args.name
    logs = output_root / "logs"
    arguments = output_root / "arguments"
    inputs = output_root / "inputs"
    for directory in (classes, dex, generated):
        _replace_directory(directory, output_root)
    logs.mkdir(parents=True, exist_ok=True)
    arguments.mkdir(parents=True, exist_ok=True)
    inputs.mkdir(parents=True, exist_ok=True)

    sources = [_validate_regular_file(path) for path in args.source]
    resources = _validate_resources(args.resource, source_root, output_root)
    for tree in args.source_tree:
        sources.extend(_collect_java_sources(tree, args.exclude, source_root=source_root))
    if args.aconfig:
        declarations = [_validate_regular_file(path) for path in args.aconfig]
        written = aconfig.generate_java(
            [str(path) for path in declarations], str(generated)
        )
        sources.extend(_validate_regular_file(Path(path)) for path in written)
    sources = sorted(set(sources), key=lambda path: path.as_posix())
    if not sources:
        raise ManagedArtifactError(f"{args.name}: no Java sources were declared")

    javac_command = [str(javac), "-d", str(classes)]
    if args.boot_classpath is not None:
        boot_classpath = _validate_path(args.boot_classpath)
        javac_command.extend(
            (
                "-source",
                "8",
                "-target",
                "8",
                "-bootclasspath",
                str(boot_classpath),
                "-classpath",
                str(boot_classpath),
                "-Xlint:-options",
            )
        )
    if args.patch_module is not None:
        patch_module = _validate_path(args.patch_module)
        javac_command.extend(("--system=none", "--patch-module", f"java.base={patch_module}"))
    javac_command.extend(args.javac_option)
    source_args = arguments / f"{args.name}.sources.args"
    _write_java_argfile(source_args, sources)
    javac_command.append(f"@{source_args}")
    _run_logged(javac_command, logs / f"{args.name}.javac.log", timeout=900)

    class_files = sorted(classes.rglob("*.class"), key=lambda path: path.as_posix())
    if not class_files:
        raise ManagedArtifactError(f"{args.name}: javac produced no class files")
    for class_file in class_files:
        _validate_regular_file(class_file)
    class_input = inputs / f"{args.name}.classes.jar"
    _write_class_jar(class_input, classes, class_files)

    d8_command = [
        str(java),
        "-Dcom.android.tools.r8.emitRecordAnnotationsInDex=1",
        "-cp",
        str(r8_jar),
        "com.android.tools.r8.D8",
        "--release",
        "--min-api",
        "31",
    ]
    if args.android_platform_build:
        d8_command.append("--android-platform-build")
    d8_command.extend(("--output", str(dex), str(class_input)))
    _run_logged(d8_command, logs / f"{args.name}.d8.log", timeout=900)

    dex_files = sorted(dex.glob("classes*.dex"), key=lambda path: path.name)
    if not dex_files or dex_files[0].name != "classes.dex":
        raise ManagedArtifactError(f"{args.name}: D8 did not produce classes.dex")
    for dex_file in dex_files:
        _validate_regular_file(dex_file)

    jar = output_root / f"{args.name}.jar"
    _write_deterministic_jar(jar, dex_files, resources)
    manifest = output_root / f"{args.name}.manifest.json"
    manifest_value = {
        "schema_version": 1,
        "name": args.name,
        "jdk_major": 21,
        "class_count": len(class_files),
        "dex_entries": [path.name for path in dex_files],
        "jar_sha256": _sha256(jar),
        "resources": [
            {
                "jar_path": archive_name,
                "sha256": _sha256(path),
                "source": _portable_source_name(path, source_root, output_root),
            }
            for path, archive_name in resources
        ],
        "sources": [_portable_source_name(path, source_root, output_root) for path in sources],
        "tool": "vendor/r8/r8.jar",
    }
    _write_text_atomic(
        manifest, json.dumps(manifest_value, indent=2, sort_keys=True) + "\n"
    )
    print(
        f"built {args.name}: sources={len(sources)} classes={len(class_files)} "
        f"dex={len(dex_files)}"
    )
    return jar, manifest


def _validate_jdk(root: Path) -> tuple[Path, Path, Path]:
    root = _validate_path(root)
    suffix = ".exe" if os.name == "nt" else ""
    java = _validate_regular_file(root / "bin" / f"java{suffix}")
    javac = _validate_regular_file(root / "bin" / f"javac{suffix}")
    versions = {}
    for name, executable in (("java", java), ("javac", javac)):
        result = subprocess.run(
            [str(executable), "-version"],
            text=True,
            capture_output=True,
            check=False,
            shell=False,
        )
        versions[name] = (result.stdout + result.stderr).strip()
        if result.returncode:
            raise ManagedArtifactError(
                f"JDK 21 {name} failed at {executable} with exit code {result.returncode}"
            )
    if re.search(r"\b(?:openjdk|java) version \"21(?:\.|\")", versions["java"]) is None:
        raise ManagedArtifactError(
            f"JDK 21 java required at {root}; got {versions['java'] or 'no version output'}"
        )
    if re.search(r"\bjavac 21(?:\.|\s|$)", versions["javac"]) is None:
        raise ManagedArtifactError(
            f"JDK 21 javac required at {root}; got {versions['javac'] or 'no version output'}"
        )
    return root, java, javac


def _collect_java_sources(
    root: Path, exclusions: list[str], *, source_root: Path | None = None
) -> list[Path]:
    root = _validate_path(root)
    normalized_exclusions = {value.replace("\\", "/") for value in exclusions}
    result: list[Path] = []
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in sorted(directories):
            _reject_link_or_reparse(current_path / name)
        directories.sort()
        for name in sorted(files):
            path = current_path / name
            _reject_link_or_reparse(path)
            if path.suffix != ".java":
                continue
            relative = path.relative_to(root).as_posix()
            source_relative = None
            if source_root is not None:
                try:
                    source_relative = path.relative_to(source_root).as_posix()
                except ValueError:
                    pass
            if relative in normalized_exclusions or source_relative in normalized_exclusions:
                continue
            result.append(_validate_regular_file(path))
    return result


def _validate_path(path: Path, *, allow_missing: bool = False) -> Path:
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
            raise ManagedArtifactError(
                f"existing path below a missing managed component: {current}"
            )
        if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
            raise ManagedArtifactError(f"link/reparse path is forbidden: {current}")
    if not allow_missing and not path.exists():
        raise ManagedArtifactError(f"managed path does not exist: {path}")
    return path


def _validate_regular_file(path: Path) -> Path:
    path = _validate_path(path)
    if not path.is_file():
        raise ManagedArtifactError(f"managed input is not a regular file: {path}")
    return path


def _reject_link_or_reparse(path: Path) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
        raise ManagedArtifactError(f"link/reparse input is forbidden: {path}")


def _is_reparse(info: os.stat_result) -> bool:
    attributes = getattr(info, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse)


def _replace_directory(path: Path, output_root: Path) -> None:
    path = Path(os.path.abspath(path))
    output_root = Path(os.path.abspath(output_root))
    try:
        relative = path.relative_to(output_root)
    except ValueError as exc:
        raise ManagedArtifactError(f"work directory escapes output root: {path}") from exc
    if not relative.parts:
        raise ManagedArtifactError("refusing to replace the managed output root")
    if path.exists() or path.is_symlink():
        _reject_link_or_reparse(path)
        _reject_tree_links(path)
        shutil.rmtree(path)
    path.mkdir(parents=True)
    _validate_path(path)


def _reject_tree_links(root: Path) -> None:
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in (*directories, *files):
            _reject_link_or_reparse(current_path / name)


def _write_java_argfile(path: Path, values: list[Path]) -> None:
    # Java argument files accept a quoted token per line. Backslashes and quotes
    # are escaped so native Windows paths remain one literal argument.
    lines = []
    for value in values:
        token = str(value).replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'"{token}"')
    _write_text_atomic(path, "\n".join(lines) + "\n")


def _run_logged(command: list[str], log: Path, *, timeout: int) -> None:
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
        shell=False,
        timeout=timeout,
    )
    _write_text_atomic(
        log,
        "stdout:\n" + result.stdout + "\nstderr:\n" + result.stderr,
    )
    if result.returncode:
        raise ManagedArtifactError(
            f"{Path(command[0]).name} failed with exit code {result.returncode}; see {log}"
        )


def _write_deterministic_jar(
    path: Path,
    dex_files: list[Path],
    resources: list[tuple[Path, str]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, staged_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    os.close(handle)
    try:
        with zipfile.ZipFile(staged_name, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for dex_file in dex_files:
                info = zipfile.ZipInfo(dex_file.name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, dex_file.read_bytes())
            for source, archive_name in resources:
                info = zipfile.ZipInfo(
                    archive_name, date_time=(1980, 1, 1, 0, 0, 0)
                )
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, source.read_bytes())
        os.replace(staged_name, path)
    except BaseException:
        try:
            os.unlink(staged_name)
        except FileNotFoundError:
            pass
        raise


def _validate_resources(
    values: list[list[str]], source_root: Path, output_root: Path
) -> list[tuple[Path, str]]:
    result: list[tuple[Path, str]] = []
    names: set[str] = set()
    for raw_source, raw_name in values:
        source = _validate_regular_file(Path(raw_source))
        archive_name = raw_name.replace("\\", "/")
        parts = archive_name.split("/")
        if (
            not archive_name
            or archive_name.startswith("/")
            or any(part in ("", ".", "..") for part in parts)
            or re.match(r"^[A-Za-z]:", archive_name)
        ):
            raise ManagedArtifactError(
                f"non-canonical managed resource path: {raw_name!r}"
            )
        if archive_name.startswith("classes") and archive_name.endswith(".dex"):
            raise ManagedArtifactError(
                f"managed resource collides with D8 output: {archive_name}"
            )
        if archive_name in names:
            raise ManagedArtifactError(
                f"managed resource path is duplicated: {archive_name}"
            )
        _portable_source_name(source, source_root, output_root)
        names.add(archive_name)
        result.append((source, archive_name))
    return sorted(result, key=lambda item: item[1])


def _write_class_jar(path: Path, root: Path, class_files: list[Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, staged_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    os.close(handle)
    try:
        with zipfile.ZipFile(staged_name, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for class_file in class_files:
                relative = class_file.relative_to(root).as_posix()
                info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, class_file.read_bytes())
        os.replace(staged_name, path)
    except BaseException:
        try:
            os.unlink(staged_name)
        except FileNotFoundError:
            pass
        raise


def _portable_source_name(path: Path, source_root: Path, output_root: Path) -> str:
    for prefix, label in ((output_root, "generated"), (source_root, "source")):
        try:
            relative = path.relative_to(prefix)
        except ValueError:
            continue
        return f"{label}/{relative.as_posix()}"
    raise ManagedArtifactError(f"source is outside declared roots: {path}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, staged_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staged_name, path)
    except BaseException:
        try:
            os.unlink(staged_name)
        except FileNotFoundError:
            pass
        raise


if __name__ == "__main__":
    raise SystemExit(main())
