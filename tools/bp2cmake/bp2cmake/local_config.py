"""Machine-local ART build bindings from the ignored TOML configuration."""

from __future__ import annotations

import os
import stat
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .target import resolve_target


LOCAL_CONFIG_NAME = ".art-build.local.toml"
CI_CONFIG_ENV = "ART_BUILD_CI_CONFIG"

_TOOL_KEYS = frozenset({"cmake", "ninja", "llvm_root", "jdk_root"})
_BUILD_KEYS = frozenset({"output_root"})
_TARGET_KEYS = frozenset({"bundle_root", "sdk_root", "sysroot", "runtime_root"})


class LocalConfigError(ValueError):
    """Raised when machine-local build configuration is invalid."""


@dataclass(frozen=True)
class LocalBuildConfig:
    source_file: Path | None = None
    tools: dict[str, Path] = field(default_factory=dict)
    output_root: Path | None = None
    targets: dict[str, dict[str, Path]] = field(default_factory=dict)
    target_runners: dict[str, Path] = field(default_factory=dict)

    def target_bindings(self, target_id: str) -> dict[str, Path]:
        return dict(self.targets.get(target_id, {}))


def load_local_config(repo_root: Path) -> LocalBuildConfig:
    local = _load_config_file(repo_root / LOCAL_CONFIG_NAME, required=False)
    ci_value = os.environ.get(CI_CONFIG_ENV)
    if not ci_value:
        return local
    if ci_value.startswith("~") or "${" in ci_value or "%" in ci_value:
        raise LocalConfigError(
            f"{CI_CONFIG_ENV} must not use path expansion syntax"
        )
    ci_path = Path(ci_value)
    if not ci_path.is_absolute():
        raise LocalConfigError(f"{CI_CONFIG_ENV} must name an absolute path")
    ci = _load_config_file(ci_path, required=True)
    targets = {
        target_id: dict(bindings)
        for target_id, bindings in local.targets.items()
    }
    for target_id, bindings in ci.targets.items():
        targets.setdefault(target_id, {}).update(bindings)
    return LocalBuildConfig(
        source_file=ci.source_file,
        tools={**local.tools, **ci.tools},
        output_root=ci.output_root if ci.output_root is not None else local.output_root,
        targets=targets,
        target_runners={**local.target_runners, **ci.target_runners},
    )


def _load_config_file(path: Path, *, required: bool) -> LocalBuildConfig:
    if not path.exists():
        if required:
            raise LocalConfigError(f"CI configuration does not exist: {path}")
        return LocalBuildConfig()
    if path.is_symlink():
        raise LocalConfigError(f"local configuration must be a regular file: {path}")
    validate_managed_path(path)
    if not path.is_file():
        raise LocalConfigError(f"local configuration must be a regular file: {path}")
    try:
        with path.open("rb") as stream:
            data = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise LocalConfigError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise LocalConfigError(f"{path}: top-level TOML value must be a table")
    _reject_unknown(
        data, {"tools", "build", "targets", "target_runners"}, "top level"
    )

    tools_table = _table(data, "tools")
    _reject_unknown(tools_table, _TOOL_KEYS, "[tools]")
    tools = {
        key: _local_path(value, path, f"tools.{key}")
        for key, value in tools_table.items()
    }

    build_table = _table(data, "build")
    _reject_unknown(build_table, _BUILD_KEYS, "[build]")
    output_root = None
    if "output_root" in build_table:
        output_root = _local_path(
            build_table["output_root"], path, "build.output_root", allow_missing=True
        )

    targets_table = _table(data, "targets")
    targets: dict[str, dict[str, Path]] = {}
    for target_id, raw_bindings in targets_table.items():
        try:
            resolve_target(target_id)
        except ValueError as exc:
            raise LocalConfigError(f"{path}: targets.{target_id}: {exc}") from exc
        if not isinstance(raw_bindings, dict):
            raise LocalConfigError(f"{path}: targets.{target_id} must be a table")
        _reject_unknown(raw_bindings, _TARGET_KEYS, f"[targets.{target_id!r}]")
        targets[target_id] = {
            key: _local_path(value, path, f"targets.{target_id}.{key}")
            for key, value in raw_bindings.items()
        }

    runners_table = _table(data, "target_runners")
    target_runners: dict[str, Path] = {}
    for target_id, raw_runner in runners_table.items():
        try:
            resolve_target(target_id)
        except ValueError as exc:
            raise LocalConfigError(
                f"{path}: target_runners.{target_id}: {exc}"
            ) from exc
        runner = _local_path(
            raw_runner, path, f"target_runners.{target_id}"
        )
        if not runner.is_file():
            raise LocalConfigError(
                f"{path}: target_runners.{target_id} must name a regular executable"
            )
        target_runners[target_id] = runner

    return LocalBuildConfig(
        source_file=path,
        tools=tools,
        output_root=output_root,
        targets=targets,
        target_runners=target_runners,
    )


def validate_managed_path(path: Path, *, allow_missing: bool = False) -> Path:
    """Validate an absolute path without following symlink/reparse components."""
    if not path.is_absolute():
        raise LocalConfigError(f"machine-local path must be absolute: {path}")

    missing_seen = False
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            missing_seen = True
            continue
        except OSError as exc:
            raise LocalConfigError(f"cannot inspect managed path {current}: {exc}") from exc
        if missing_seen:
            raise LocalConfigError(
                f"managed path has an existing child below a missing component: {current}"
            )
        if stat.S_ISLNK(info.st_mode) or _is_windows_reparse(info):
            raise LocalConfigError(f"managed path contains a link/reparse component: {current}")

    if not allow_missing and not path.exists():
        raise LocalConfigError(f"managed path does not exist: {path}")
    return path


def _local_path(value: object, source: Path, key: str, *, allow_missing: bool = False) -> Path:
    if not isinstance(value, str) or not value:
        raise LocalConfigError(f"{source}: {key} must be a non-empty string")
    if value.startswith("~") or "${" in value or "%" in value:
        raise LocalConfigError(f"{source}: {key} must not use path expansion syntax")
    return validate_managed_path(Path(value), allow_missing=allow_missing)


def _table(data: dict[str, object], key: str) -> dict[str, object]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise LocalConfigError(f"[{key}] must be a TOML table")
    return value


def _reject_unknown(data: dict[str, object], allowed: set[str] | frozenset[str], where: str) -> None:
    unknown = sorted(set(data) - set(allowed))
    if unknown:
        raise LocalConfigError(f"{where}: unsupported keys: {', '.join(unknown)}")


def _is_windows_reparse(info: os.stat_result) -> bool:
    attributes = getattr(info, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse)
