#!/usr/bin/env python3
"""Compare fresh Linux/Windows ART graphs against the reviewed topology contract."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_FRONTEND = REPO_ROOT / "tools" / "build_art.py"
DEFAULT_CONTRACT = REPO_ROOT / "overlay" / "art_topology_contract.json"
PLATFORM_CMAKE = REPO_ROOT / "native" / "cmake" / "ArtPlatform.cmake"


class TopologyError(RuntimeError):
    """Raised when generated topology differs from reviewed policy."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="check_art_topology.py")
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--linux-manifest", type=Path)
    parser.add_argument("--windows-manifest", type=Path)
    return parser


def _read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TopologyError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise TopologyError(f"top-level JSON value must be an object: {path}")
    return value


def _module_map(manifest: dict[str, object], target_id: str) -> dict[str, dict[str, object]]:
    target = manifest.get("target")
    if not isinstance(target, dict) or target.get("target_id") != target_id:
        raise TopologyError(f"manifest does not describe {target_id}")
    raw_modules = manifest.get("modules")
    if not isinstance(raw_modules, list):
        raise TopologyError(f"{target_id} manifest has no module list")
    modules: dict[str, dict[str, object]] = {}
    for index, raw in enumerate(raw_modules):
        if not isinstance(raw, dict):
            raise TopologyError(f"{target_id} module {index} is not an object")
        name = raw.get("aosp_name")
        kind = raw.get("kind")
        cmake_target = raw.get("cmake_target")
        if not all(isinstance(value, str) and value for value in (name, kind, cmake_target)):
            raise TopologyError(f"{target_id} module {index} is incomplete")
        if name in modules:
            raise TopologyError(f"{target_id} repeats module {name}")
        modules[name] = raw
    return modules


def _contract_targets(contract: dict[str, object]) -> tuple[str, str]:
    if contract.get("schema_version") != 1:
        raise TopologyError("topology contract schema_version must be 1")
    targets = contract.get("targets")
    if not isinstance(targets, dict):
        raise TopologyError("topology contract has no targets object")
    linux = targets.get("linux")
    windows = targets.get("windows")
    if not isinstance(linux, str) or not isinstance(windows, str):
        raise TopologyError("topology contract target IDs must be strings")
    return linux, windows


def _expected_set_differences(
    contract: dict[str, object], side: str
) -> dict[str, dict[str, object]]:
    differences = contract.get("module_set_differences")
    if not isinstance(differences, dict):
        raise TopologyError("topology contract has no module_set_differences")
    raw = differences.get(side)
    if not isinstance(raw, dict):
        raise TopologyError(f"topology contract has no {side} object")
    if not all(isinstance(name, str) and isinstance(value, dict) for name, value in raw.items()):
        raise TopologyError(f"topology contract {side} entries are malformed")
    return raw


def compare_topologies(
    linux_manifest: dict[str, object],
    windows_manifest: dict[str, object],
    contract: dict[str, object],
) -> dict[str, int]:
    linux_id, windows_id = _contract_targets(contract)
    linux = _module_map(linux_manifest, linux_id)
    windows = _module_map(windows_manifest, windows_id)
    expected_linux_only = _expected_set_differences(contract, "linux_only")
    expected_windows_only = _expected_set_differences(contract, "windows_only")
    actual_linux_only = set(linux) - set(windows)
    actual_windows_only = set(windows) - set(linux)
    if actual_linux_only != set(expected_linux_only):
        raise TopologyError(
            "Linux-only module set differs: expected "
            f"{sorted(expected_linux_only)}, got {sorted(actual_linux_only)}"
        )
    if actual_windows_only != set(expected_windows_only):
        raise TopologyError(
            "Windows-only module set differs: expected "
            f"{sorted(expected_windows_only)}, got {sorted(actual_windows_only)}"
        )

    for name, expected in expected_linux_only.items():
        for field in ("kind", "cmake_target", "reason"):
            if not isinstance(expected.get(field), str) or not expected[field]:
                raise TopologyError(f"Linux-only contract for {name} omits {field}")
        if linux[name]["kind"] != expected["kind"]:
            raise TopologyError(f"Linux-only module {name} changed kind")
        if linux[name]["cmake_target"] != expected["cmake_target"]:
            raise TopologyError(f"Linux-only module {name} changed CMake target")

    for name, expected in expected_windows_only.items():
        for field in ("kind", "cmake_target", "reason"):
            if not isinstance(expected.get(field), str) or not expected[field]:
                raise TopologyError(f"Windows-only contract for {name} omits {field}")
        if windows[name]["kind"] != expected["kind"]:
            raise TopologyError(f"Windows-only module {name} changed kind")
        if windows[name]["cmake_target"] != expected["cmake_target"]:
            raise TopologyError(f"Windows-only module {name} changed CMake target")

    common = set(linux) & set(windows)
    renamed = sorted(
        name for name in common
        if linux[name]["cmake_target"] != windows[name]["cmake_target"]
    )
    if renamed:
        raise TopologyError(f"common modules changed CMake target names: {renamed}")
    actual_kind_differences = {
        name: (linux[name]["kind"], windows[name]["kind"])
        for name in common
        if linux[name]["kind"] != windows[name]["kind"]
    }
    raw_kind_contract = contract.get("kind_differences")
    if not isinstance(raw_kind_contract, dict):
        raise TopologyError("topology contract has no kind_differences object")
    if set(actual_kind_differences) != set(raw_kind_contract):
        raise TopologyError(
            "module kind differences changed: expected "
            f"{sorted(raw_kind_contract)}, got {sorted(actual_kind_differences)}"
        )
    for name, (linux_kind, windows_kind) in actual_kind_differences.items():
        expected = raw_kind_contract[name]
        if not isinstance(expected, dict):
            raise TopologyError(f"kind contract for {name} is malformed")
        if expected.get("linux") != linux_kind or expected.get("windows") != windows_kind:
            raise TopologyError(f"kind contract for {name} does not match generated graphs")
        if not isinstance(expected.get("reason"), str) or not expected["reason"]:
            raise TopologyError(f"kind contract for {name} omits its disposition")
        direct_consumers = expected.get("direct_consumers")
        if not isinstance(direct_consumers, list) or not all(
            isinstance(consumer, str) and consumer for consumer in direct_consumers
        ):
            raise TopologyError(
                f"kind contract for {name} has malformed direct_consumers"
            )
        for side, modules in (("Linux", linux), ("Windows", windows)):
            dependency = modules[name]["cmake_target"]
            actual_consumers = {
                consumer_name
                for consumer_name, consumer in modules.items()
                if dependency in consumer.get("link_dependencies", [])
            }
            if actual_consumers != set(direct_consumers):
                raise TopologyError(
                    f"{side} direct consumers for kind difference {name} changed: "
                    f"expected {sorted(direct_consumers)}, got {sorted(actual_consumers)}"
                )

    if "libsigchain" in expected_linux_only:
        mapping = expected_linux_only["libsigchain"]
        target = mapping.get("windows_cmake_target")
        kind = mapping.get("windows_kind")
        platform_text = PLATFORM_CMAKE.read_text(encoding="utf-8")
        declaration = f"add_library({target} {str(kind).upper()}"
        if target != "sigchain" or kind != "shared" or declaration not in platform_text:
            raise TopologyError("Windows sigchain platform mapping changed")

    return {
        "linux_modules": len(linux),
        "windows_modules": len(windows),
        "set_differences": len(actual_linux_only) + len(actual_windows_only),
        "kind_differences": len(actual_kind_differences),
    }


def _generate_manifests(linux_id: str, windows_id: str) -> tuple[Path, Path, Path]:
    ignored_out = REPO_ROOT / "out"
    ignored_out.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="topology-check-", dir=ignored_out))
    for target_id in (linux_id, windows_id):
        result = subprocess.run(
            [
                sys.executable,
                str(BUILD_FRONTEND),
                "generate",
                "--target-id",
                target_id,
                "--output-root",
                str(scratch),
            ],
            cwd=REPO_ROOT,
            shell=False,
            check=False,
        )
        if result.returncode:
            shutil.rmtree(scratch)
            raise TopologyError(f"fresh graph generation failed for {target_id}")
    suffix = Path("RelWithDebInfo") / "generated" / "graph_manifest.json"
    return scratch / linux_id / suffix, scratch / windows_id / suffix, scratch


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    scratch = None
    try:
        contract = _read_json(args.contract)
        linux_id, windows_id = _contract_targets(contract)
        if (args.linux_manifest is None) != (args.windows_manifest is None):
            raise TopologyError("pass both manifest paths or neither")
        if args.linux_manifest is None:
            linux_path, windows_path, scratch = _generate_manifests(linux_id, windows_id)
        else:
            linux_path = args.linux_manifest
            windows_path = args.windows_manifest
        result = compare_topologies(
            _read_json(linux_path),
            _read_json(windows_path),
            contract,
        )
        print(
            "ART topology accepted: "
            f"Linux modules={result['linux_modules']}, "
            f"Windows modules={result['windows_modules']}, "
            f"approved set differences={result['set_differences']}, "
            f"approved kind differences={result['kind_differences']}"
        )
        return 0
    except (OSError, TopologyError) as exc:
        print(f"check_art_topology.py: error: {exc}", file=sys.stderr)
        return 2
    finally:
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
