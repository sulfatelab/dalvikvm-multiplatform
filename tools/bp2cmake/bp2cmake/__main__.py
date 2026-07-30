"""Generate a target-resolved CMake graph from Android Blueprint modules."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

from .closure import dependency_closure
from .config import Config
from .emitter import Emitter
from .evaluator import Evaluator
from .overlay import load_overlay, load_overlay_factory
from .target import TargetError, TargetProfile, resolve_target


class StaleOutputError(RuntimeError):
    """Raised by --check when generated content differs from an output file."""


def _find_bp_files(root: str, names=("Android.bp",)) -> list[str]:
    out = []
    for dirpath, _dirs, files in os.walk(root):
        for filename in files:
            if filename in names or (
                filename.endswith(".bp") and "blueprint-allbp" in names
            ):
                out.append(os.path.join(dirpath, filename))
    return sorted(out)


def _load_root(
    evaluator: Evaluator,
    root_dir: str,
    root_var: str,
    names: tuple[str, ...],
    *,
    label: str = "",
    exclude_top: tuple[str, ...] = (),
    input_records: list[dict[str, str]],
) -> int:
    """Load Blueprint inputs and record only stable root-relative identities."""
    loaded = 0
    for blueprint in _find_bp_files(root_dir, names):
        rel = os.path.relpath(blueprint, root_dir)
        parts = rel.split(os.sep)
        if any(part in ("test", "tests", "fuzz", "benchmark", "sample") for part in parts):
            continue
        if parts and parts[0] in exclude_top:
            continue
        try:
            evaluator.add_path(blueprint, source_root=root_dir, root_var=root_var)
            input_records.append(
                {
                    "root_variable": root_var,
                    "path": Path(rel).as_posix(),
                    "sha256": _sha256_file(Path(blueprint)),
                }
            )
            loaded += 1
        except Exception as exc:  # noqa: BLE001
            print(f"warn: failed to load {label}{rel}: {exc}", file=sys.stderr)
    return loaded


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bp2cmake")
    parser.add_argument("--root", required=True, help="native source root")
    policy = parser.add_mutually_exclusive_group(required=True)
    policy.add_argument("--overlay", help="legacy path to one fixed overlay")
    policy.add_argument(
        "--overlay-factory", help="path to the target-aware make_overlay(target) file"
    )
    parser.add_argument("--target-id", help="canonical registered target ID")
    parser.add_argument("--module", action="append", default=[])
    parser.add_argument("--root-module", action="append", default=[])
    parser.add_argument("--out", help="generated CMake output (default: stdout)")
    parser.add_argument("--manifest-out", help="deterministic JSON graph manifest")
    parser.add_argument("--profile-out", help="path-free generated CMake target data")
    parser.add_argument(
        "--check", action="store_true", help="fail instead of changing stale outputs"
    )
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument("--load-dir", action="append", default=[])
    parser.add_argument(
        "--extra-root", action="append", default=[], metavar="DIR:CMAKEVAR"
    )
    parser.add_argument("--exclude-top", action="append", default=[], metavar="NAME")
    parser.add_argument(
        "--os", choices=["linux_glibc", "windows"], help="legacy target OS"
    )
    parser.add_argument("--arch", help="legacy AOSP architecture token")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        target, config = _resolve_config(args, parser)
        overlay = _resolve_overlay(args, target, parser)
        return _generate(args, parser, target, config, overlay)
    except (TargetError, StaleOutputError, ValueError) as exc:
        print(f"bp2cmake: error: {exc}", file=sys.stderr)
        return 2


def _resolve_config(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> tuple[TargetProfile | None, Config]:
    if args.target_id:
        if args.os or args.arch:
            parser.error("--target-id cannot be combined with legacy --os/--arch")
        target = resolve_target(args.target_id)
        target.require_generation()
        return target, Config.from_target(target)
    if args.overlay_factory:
        parser.error("--overlay-factory requires --target-id")
    return None, Config(
        os=args.os or "linux_glibc",
        arch=args.arch or "x86_64",
        bitness=64 if "64" in (args.arch or "x86_64") else 32,
    )


def _resolve_overlay(
    args: argparse.Namespace,
    target: TargetProfile | None,
    parser: argparse.ArgumentParser,
):
    if args.overlay_factory:
        assert target is not None
        return load_overlay_factory(args.overlay_factory, target)
    if not args.overlay:
        parser.error("legacy generation requires --overlay")
    return load_overlay(args.overlay)


def _generate(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    target: TargetProfile | None,
    config: Config,
    overlay,
) -> int:
    evaluator = Evaluator(config)
    root_paths: dict[str, str] = {}
    input_records: list[dict[str, str]] = []

    root_paths["MDVM_NATIVE_SRC_ROOT_DIR"] = os.path.abspath(args.root)
    loaded = _load_root(
        evaluator,
        args.root,
        "MDVM_NATIVE_SRC_ROOT_DIR",
        ("Android.bp", "sources.bp"),
        exclude_top=tuple(args.exclude_top),
        input_records=input_records,
    )

    for spec in args.extra_root:
        directory, _, variable = spec.rpartition(":")
        if not directory or not variable:
            parser.error(f"--extra-root must be DIR:CMAKEVAR, got {spec!r}")
        root_paths[variable] = os.path.abspath(directory)
        loaded += _load_root(
            evaluator,
            directory,
            variable,
            ("blueprint-allbp",),
            label=f"[{variable}] ",
            input_records=input_records,
        )

    emitter = Emitter(evaluator, overlay, root_paths)
    modules = list(args.module)
    if args.root_module:
        for name in dependency_closure(evaluator, overlay, args.root_module):
            if name not in modules:
                modules.append(name)
    if not modules:
        parser.error("nothing to emit: pass --module and/or --root-module")

    if args.list_only:
        for name in modules:
            print(name)
        return 0

    chunks: list[str] = []
    module_manifest: list[dict[str, object]] = []
    for name in modules:
        resolved = evaluator.resolve(name)
        module_manifest.append(emitter.module_manifest(resolved))
        chunks.append(emitter.emit_module(resolved))
    output = "\n".join(chunks)
    _reject_bound_paths(output, root_paths)

    graph_digest = hashlib.sha256(output.encode("utf-8")).hexdigest()
    manifest = {
        "schema_version": 1,
        "target": target.to_dict() if target else {
            "legacy_os": config.os,
            "legacy_arch": config.arch,
            "pointer_bits": config.bitness,
        },
        "root_variables": sorted(root_paths),
        "blueprint_inputs": sorted(
            input_records, key=lambda item: (item["root_variable"], item["path"])
        ),
        "root_modules": list(args.root_module),
        "modules": module_manifest,
        "graph_sha256": graph_digest,
    }
    manifest_text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"

    if args.out:
        _write_generated(Path(args.out), output, check=args.check)
    else:
        if args.check:
            parser.error("--check requires --out")
        sys.stdout.write(output)
    if args.manifest_out:
        _write_generated(Path(args.manifest_out), manifest_text, check=args.check)
    if args.profile_out:
        if target is None:
            parser.error("--profile-out requires --target-id")
        _write_generated(Path(args.profile_out), target.to_cmake(), check=args.check)

    if args.out:
        action = "checked" if args.check else "wrote"
        print(
            f"{action} {args.out} ({len(modules)} modules, {loaded} .bp files loaded)",
            file=sys.stderr,
        )
    return 0


def _write_generated(path: Path, content: str, *, check: bool) -> None:
    encoded = content.encode("utf-8")
    if path.is_symlink():
        raise ValueError(f"refusing generated symlink output: {path}")
    try:
        current = path.read_bytes()
    except FileNotFoundError:
        current = None
    if current == encoded:
        return
    if check:
        state = "missing" if current is None else "stale"
        raise StaleOutputError(f"generated output is {state}: {path}")

    path.parent.mkdir(parents=True, exist_ok=True)
    handle, staged_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staged_name, path)
    except BaseException:
        try:
            os.unlink(staged_name)
        except FileNotFoundError:
            pass
        raise


def _reject_bound_paths(output: str, root_paths: dict[str, str]) -> None:
    normalized = output.replace("\\", "/")
    for root in root_paths.values():
        spelling = os.path.abspath(root).replace("\\", "/").rstrip("/")
        if spelling and spelling in normalized:
            raise ValueError(f"generated graph contains bound source path for {root!r}")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
