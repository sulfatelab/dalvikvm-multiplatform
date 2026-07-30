"""Portable ART graph/configure/build frontend for Linux and Windows hosts."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BP2CMAKE_ROOT = REPO_ROOT / "tools" / "bp2cmake"
if str(BP2CMAKE_ROOT) not in sys.path:
    sys.path.insert(0, str(BP2CMAKE_ROOT))

from bp2cmake.local_config import (  # noqa: E402
    LOCAL_CONFIG_NAME,
    LocalBuildConfig,
    LocalConfigError,
    load_local_config,
    validate_managed_path,
)
from bp2cmake.target import TARGET_PROFILES, TargetError, TargetProfile, resolve_target  # noqa: E402


DEFAULT_BUILD_TYPE = "RelWithDebInfo"
BUILD_TYPES = ("RelWithDebInfo", "Debug")
ROOT_MODULES = (
    "dalvikvm",
    "dex2oat",
    "libart-compiler",
    "libjavacore",
    "libopenjdk",
    "libicu_jni",
)


class BuildFrontendError(RuntimeError):
    """Raised for a deterministic user-facing frontend failure."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="build_art.py")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-targets", help="list canonical target profiles")
    subparsers.add_parser(
        "init-local-config", help=f"create ignored {LOCAL_CONFIG_NAME} from discovered tools"
    )

    for command in ("generate", "check-generated", "configure", "build", "test"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--target-id", required=True)
        sub.add_argument("--build-type", choices=BUILD_TYPES, default=DEFAULT_BUILD_TYPE)
        sub.add_argument("--output-root", type=Path)
        if command == "build":
            sub.add_argument("--cmake-target")
            sub.add_argument("--parallel", type=int)
        if command == "test":
            sub.add_argument("--label", action="append", default=[])
            sub.add_argument(
                "--stage",
                action="append",
                default=[],
                help="build and run one virtual test stage (canonical form: wNNN)",
            )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "list-targets":
            return _list_targets()
        if args.command == "init-local-config":
            return _init_local_config()

        target = resolve_target(args.target_id)
        target.require_generation()
        local = load_local_config(REPO_ROOT)
        output_root = _resolve_output_root(args.output_root, local)
        binary_dir = output_root / target.target_id / args.build_type

        if args.command in ("generate", "check-generated", "configure"):
            _generate(
                target,
                args.build_type,
                binary_dir,
                check=args.command == "check-generated",
            )
        if args.command == "configure":
            _configure(target, args.build_type, binary_dir, local)
        elif args.command == "build":
            _build(binary_dir, local, args.cmake_target, args.parallel)
        elif args.command == "test":
            _test(binary_dir, local, args.label, args.stage)
        return 0
    except (BuildFrontendError, LocalConfigError, TargetError, OSError) as exc:
        print(f"build_art.py: error: {exc}", file=sys.stderr)
        return 2


def _list_targets() -> int:
    for target in TARGET_PROFILES.values():
        print(f"{target.target_id}\t{target.support_status}\t{target.target_triple}")
    return 0


def _resolve_output_root(explicit: Path | None, local: LocalBuildConfig) -> Path:
    if explicit is not None:
        if not explicit.is_absolute():
            raise BuildFrontendError("--output-root must be an absolute path")
        output_root = explicit
    elif local.output_root is not None:
        output_root = local.output_root
    else:
        output_root = REPO_ROOT / "out"
    validate_managed_path(output_root, allow_missing=True)
    return output_root


def _generate(
    target: TargetProfile,
    build_type: str,
    binary_dir: Path,
    *,
    check: bool,
) -> None:
    generated_dir = binary_dir / "generated"
    graph = generated_dir / "art_graph.cmake"
    graph_manifest = generated_dir / "graph_manifest.json"
    target_profile = generated_dir / "target_profile.cmake"
    python = _python_executable()

    command = [
        str(python),
        "-m",
        "bp2cmake",
        "--root",
        str(REPO_ROOT / "vendor"),
        "--exclude-top",
        "art",
        "--overlay-factory",
        str(REPO_ROOT / "overlay" / "art_port_policy.py"),
        "--target-id",
        target.target_id,
        "--extra-root",
        f"{REPO_ROOT / 'vendor'}:MDVM_ART_ROOT_DIR",
        "--extra-root",
        f"{REPO_ROOT / 'vendor' / 'libcore'}:MDVM_LIBCORE_DIR",
        "--extra-root",
        f"{REPO_ROOT / 'vendor' / 'icu'}:MDVM_ICU_DIR",
        "--extra-root",
        f"{REPO_ROOT / 'vendor' / 'java-external' / 'fdlibm'}:MDVM_FDLIBM_DIR",
    ]
    for root_module in ROOT_MODULES:
        command.extend(("--root-module", root_module))
    command.extend(
        (
            "--out",
            str(graph),
            "--manifest-out",
            str(graph_manifest),
            "--profile-out",
            str(target_profile),
        )
    )
    if check:
        command.append("--check")
    env = dict(os.environ)
    previous_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(BP2CMAKE_ROOT) + (
        os.pathsep + previous_pythonpath if previous_pythonpath else ""
    )
    result = subprocess.run(command, cwd=REPO_ROOT, env=env, shell=False, check=False)
    if result.returncode:
        action = "check" if check else "generation"
        raise BuildFrontendError(f"target graph {action} failed ({result.returncode})")
    _validate_graph_manifest(graph_manifest, target)
    if not check:
        print(f"generated {target.target_id} graph in {generated_dir}")


def _validate_graph_manifest(path: Path, target: TargetProfile) -> None:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildFrontendError(f"cannot read generated graph manifest: {path}: {exc}") from exc
    compiler = next(
        (module for module in manifest.get("modules", [])
         if module.get("aosp_name") == "libart-compiler"),
        None,
    )
    if compiler is None:
        raise BuildFrontendError(
            f"generated graph for {target.target_id} omits the required libart-compiler module"
        )
    if compiler.get("kind") != "shared":
        raise BuildFrontendError(
            f"generated graph for {target.target_id} has non-shared libart-compiler "
            f"kind {compiler.get('kind')!r}"
        )


def _configure(
    target: TargetProfile,
    build_type: str,
    binary_dir: Path,
    local: LocalBuildConfig,
) -> None:
    if target.target_id != "linux-x86_64":
        raise BuildFrontendError(
            f"unified CMake configure is not admitted for {target.target_id}; "
            "target graph generation is available, but product CMake migration remains"
        )

    tools = _resolve_tools(local, need_compiler=True)
    fingerprint = _build_fingerprint(target, build_type, tools)
    manifest_path = binary_dir / "build_manifest.json"
    generated = binary_dir / "generated"
    command = [
        str(tools["cmake"]),
        "-S",
        str(REPO_ROOT / "native"),
        "-B",
        str(binary_dir),
        "-G",
        "Ninja",
        f"-DCMAKE_BUILD_TYPE={build_type}",
        f"-DCMAKE_MAKE_PROGRAM={tools['ninja']}",
        f"-DCMAKE_C_COMPILER={tools['clang']}",
        f"-DCMAKE_CXX_COMPILER={tools['clang++']}",
        f"-DPython3_EXECUTABLE={_python_executable()}",
        f"-DART_PROFILE_FILE={generated / 'target_profile.cmake'}",
        f"-DART_GRAPH_FILE={generated / 'art_graph.cmake'}",
    ]
    fingerprint["configure_command"] = command
    _guard_binary_directory(binary_dir, manifest_path, fingerprint)
    _run_checked(command)
    _write_json_atomic(manifest_path, fingerprint)
    print(f"configured {target.target_id} in {binary_dir}")


def _build(
    binary_dir: Path,
    local: LocalBuildConfig,
    cmake_target: str | None,
    parallel: int | None,
) -> None:
    _require_configured(binary_dir)
    cmake = _resolve_tools(local, need_compiler=False)["cmake"]
    command = [str(cmake), "--build", str(binary_dir)]
    if cmake_target:
        command.extend(("--target", cmake_target))
    if parallel is not None:
        if parallel < 1:
            raise BuildFrontendError("--parallel must be positive")
        command.extend(("--parallel", str(parallel)))
    _run_checked(command)


def _test(
    binary_dir: Path,
    local: LocalBuildConfig,
    labels: list[str],
    stages: list[str] | None = None,
) -> None:
    _require_configured(binary_dir)
    cmake = _resolve_tools(local, need_compiler=False)["cmake"]
    stages = stages or []
    stage_labels = [_stage_label(stage) for stage in stages]
    for stage in dict.fromkeys(stages):
        _run_checked(
            [
                str(cmake),
                "--build",
                str(binary_dir),
                "--target",
                f"art-test-stage-{stage}",
            ]
        )

    ctest_name = "ctest.exe" if os.name == "nt" else "ctest"
    ctest = validate_managed_path((cmake.parent / ctest_name).resolve())
    command = [str(ctest), "--test-dir", str(binary_dir), "--output-on-failure"]
    selected_labels = list(dict.fromkeys([*labels, *stage_labels]))
    if selected_labels:
        label_regex = "^(" + "|".join(re.escape(label) for label in selected_labels) + ")$"
        command.extend(("--label-regex", label_regex))
    _run_checked(command)


def _stage_label(stage: str) -> str:
    if re.fullmatch(r"w[0-9]{3}", stage) is None:
        raise BuildFrontendError(
            f"invalid test stage {stage!r}; expected canonical lower-case form wNNN"
        )
    return f"stage:{stage}"


def _run_checked(command: list[str]) -> None:
    try:
        subprocess.run(command, cwd=REPO_ROOT, shell=False, check=True)
    except subprocess.CalledProcessError as exc:
        executable = Path(command[0]).name
        raise BuildFrontendError(
            f"{executable} failed with exit code {exc.returncode}"
        ) from exc


def _resolve_tools(local: LocalBuildConfig, *, need_compiler: bool) -> dict[str, Path]:
    tools = {
        "cmake": _configured_or_discovered(local, "cmake", "cmake"),
        "ninja": _configured_or_discovered(local, "ninja", "ninja"),
    }
    if not need_compiler:
        return tools

    llvm_root = local.tools.get("llvm_root")
    suffix = ".exe" if os.name == "nt" else ""
    if llvm_root is not None:
        clang = llvm_root / "bin" / f"clang{suffix}"
        clangxx = llvm_root / "bin" / f"clang++{suffix}"
    else:
        clang = _discover("clang")
        clangxx = _discover("clang++")
    tools["clang"] = validate_managed_path(clang.resolve())
    tools["clang++"] = validate_managed_path(clangxx.resolve())
    if tools["clang"].name not in ("clang", "clang.exe"):
        raise BuildFrontendError(f"plain Clang driver required: {tools['clang']}")
    if tools["clang++"].name not in ("clang++", "clang++.exe", "clang"):
        raise BuildFrontendError(f"plain Clang++ driver required: {tools['clang++']}")
    return tools


def _configured_or_discovered(
    local: LocalBuildConfig, key: str, executable: str
) -> Path:
    configured = local.tools.get(key)
    path = configured if configured is not None else _discover(executable)
    resolved = validate_managed_path(path.resolve())
    allowed = {
        "cmake": ("cmake", "cmake.exe"),
        "ninja": ("ninja", "ninja.exe"),
    }.get(key)
    if allowed is not None and resolved.name not in allowed:
        raise BuildFrontendError(
            f"plain {key} executable required; got {resolved.name!r}"
        )
    return resolved


def _discover(executable: str) -> Path:
    found = shutil.which(executable)
    if not found:
        raise BuildFrontendError(
            f"required host tool {executable!r} was not configured or found"
        )
    return Path(found)


def _python_executable() -> Path:
    path = validate_managed_path(Path(sys.executable).resolve())
    if sys.version_info < (3, 11):
        raise BuildFrontendError("Python 3.11 or newer is required")
    return path


def _build_fingerprint(
    target: TargetProfile, build_type: str, tools: dict[str, Path]
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "build_host": {
            "os": platform.system().lower(),
            "arch": _canonical_host_arch(platform.machine()),
            "python_version": platform.python_version(),
        },
        "target_id": target.target_id,
        "target_triple": target.target_triple,
        "build_type": build_type,
        "tools": {name: str(path) for name, path in sorted(tools.items())},
    }


def _guard_binary_directory(
    binary_dir: Path, manifest_path: Path, expected: dict[str, object]
) -> None:
    if manifest_path.exists():
        try:
            current = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BuildFrontendError(f"cannot read build manifest: {exc}") from exc
        if current != expected:
            raise BuildFrontendError(
                f"build fingerprint changed for {binary_dir}; use a fresh output root "
                "or remove this ignored binary directory explicitly"
            )
    elif (binary_dir / "CMakeCache.txt").exists():
        raise BuildFrontendError(
            f"refusing unowned existing CMake cache without build manifest: {binary_dir}"
        )


def _require_configured(binary_dir: Path) -> None:
    if not (binary_dir / "CMakeCache.txt").is_file() or not (
        binary_dir / "build_manifest.json"
    ).is_file():
        raise BuildFrontendError(f"build is not configured by build_art.py: {binary_dir}")


def _canonical_host_arch(machine: str) -> str:
    normalized = machine.lower()
    return {
        "amd64": "x86_64",
        "x64": "x86_64",
        "arm64": "aarch64",
    }.get(normalized, normalized)


def _init_local_config() -> int:
    path = REPO_ROOT / LOCAL_CONFIG_NAME
    if path.exists() or path.is_symlink():
        raise BuildFrontendError(f"refusing to overwrite existing {path}")
    cmake = validate_managed_path(_discover("cmake").resolve())
    ninja = validate_managed_path(_discover("ninja").resolve())
    clang = validate_managed_path(_discover("clang").resolve())
    content = (
        "# Machine-local paths only. This file is ignored by Git.\n"
        "[tools]\n"
        f"cmake = {json.dumps(str(cmake))}\n"
        f"ninja = {json.dumps(str(ninja))}\n"
        f"llvm_root = {json.dumps(str(clang.parent.parent))}\n"
    )
    _write_text_atomic(path, content)
    print(f"created {path}")
    return 0


def _write_json_atomic(path: Path, value: dict[str, object]) -> None:
    _write_text_atomic(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = content.encode("utf-8")
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


if __name__ == "__main__":
    raise SystemExit(main())
