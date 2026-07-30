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


def _host_can_run_target(target: TargetProfile) -> bool:
    """Conservatively admit runtime probes only on an exact native host."""
    host_os = platform.system().lower()
    if host_os != target.os_or_runtime:
        return False
    host_arch = platform.machine().lower()
    normalized_arch = {
        "amd64": "x86_64",
        "x64": "x86_64",
        "arm64": "aarch64",
        "i386": "x86",
        "i686": "x86",
    }.get(host_arch, host_arch)
    return normalized_arch == target.cpu_arch


class BuildFrontendError(RuntimeError):
    """Raised for a deterministic user-facing frontend failure."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="build_art.py")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-targets", help="list canonical target profiles")
    subparsers.add_parser(
        "init-local-config", help=f"create ignored {LOCAL_CONFIG_NAME} from discovered tools"
    )

    for command in ("generate", "check-generated", "configure", "build", "test", "stage"):
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
        validate_managed_path(binary_dir, allow_missing=True)

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
            _build(target, binary_dir, local, args.cmake_target, args.parallel)
        elif args.command == "test":
            _test(binary_dir, local, args.label, args.stage)
        elif args.command == "stage":
            _stage(target, binary_dir, local)
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
    tools = _resolve_tools(local, need_compiler=True)
    if target.os_or_runtime == "windows":
        tools["llvm-rc"] = _resolve_llvm_resource_compiler(local)
    bindings = _target_bindings(target, local)
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
        f"-DCMAKE_C_COMPILER_TARGET={target.target_triple}",
        f"-DCMAKE_CXX_COMPILER_TARGET={target.target_triple}",
        f"-DCMAKE_ASM_COMPILER_TARGET={target.target_triple}",
        f"-DCMAKE_SYSTEM_NAME={target.os_or_runtime.capitalize()}",
        f"-DPython3_EXECUTABLE={_python_executable()}",
        f"-DART_PROFILE_FILE={generated / 'target_profile.cmake'}",
        f"-DART_GRAPH_FILE={generated / 'art_graph.cmake'}",
        "-DART_ENABLE_TARGET_RUNTIME_TESTS="
        + ("ON" if _host_can_run_target(target) else "OFF"),
    ]
    if target.os_or_runtime == "windows":
        bundle = bindings.get("bundle_root")
        if bundle is None:
            raise BuildFrontendError(
                f"target {target.target_id} requires targets.{target.target_id}.bundle_root "
                "in .art-build.local.toml"
            )
        command.extend((
            f"-DART_TARGET_BUNDLE_ROOT={bundle}",
            f"-DCMAKE_RC_COMPILER={tools['llvm-rc'].as_posix()}",
            "-DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY",
        ))
    elif platform.system().lower() == "windows" and "sysroot" not in bindings:
        raise BuildFrontendError(
            "Windows-hosted Linux targets require targets."
            f"{target.target_id}.sysroot in .art-build.local.toml"
        )
    for key, cmake_key in (("sdk_root", "ART_TARGET_SDK_ROOT"),
                           ("sysroot", "ART_TARGET_SYSROOT"),
                           ("runtime_root", "ART_TARGET_RUNTIME_ROOT")):
        if key in bindings:
            command.append(f"-D{cmake_key}={bindings[key]}")
    if "sysroot" in bindings:
        command.append(f"-DCMAKE_SYSROOT={bindings['sysroot']}")
    fingerprint["configure_command"] = command
    _guard_binary_directory(binary_dir, manifest_path, fingerprint)
    _run_checked(command)
    _write_json_atomic(manifest_path, fingerprint)
    print(f"configured {target.target_id} in {binary_dir}")


def _build(
    target: TargetProfile,
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
    if target.os_or_runtime == "windows" and (
        cmake_target is None or cmake_target in ("all", "art-compiler")
    ):
        _validate_windows_art_compiler(binary_dir, target, local)


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
    command = [
        str(ctest),
        "--test-dir",
        str(binary_dir),
        "--output-on-failure",
        "--no-tests=error",
    ]
    selected_labels = list(dict.fromkeys([*labels, *stage_labels]))
    if selected_labels:
        label_regex = "^(" + "|".join(re.escape(label) for label in selected_labels) + ")$"
        command.extend(("--label-regex", label_regex))
    _run_checked(command)


def _stage(target: TargetProfile, binary_dir: Path, local: LocalBuildConfig) -> None:
    """Copy product outputs into a regular-file staging tree and record them."""
    _require_configured(binary_dir)
    if target.os_or_runtime == "windows":
        _validate_windows_art_compiler(binary_dir, target, local)

    stage_dir = binary_dir / "stage"
    validate_managed_path(stage_dir, allow_missing=True)
    stage_dir.mkdir(parents=True, exist_ok=True)
    product_names = (
        "dalvikvm", "dex2oat", "art", "art-compiler", "art-disassembler",
        "javacore", "openjdk", "icu_jni",
    )
    sources: list[Path] = []
    for name in product_names:
        source = next(
            (candidate for candidate in _artifact_candidates(binary_dir, target, name)
             if candidate.is_file()),
            None,
        )
        if source is None:
            continue
        sources.append(source)

        if target.os_or_runtime == "windows" and name == "art-compiler":
            import_lib = next(
                (candidate for candidate in _artifact_candidates(binary_dir, target, name)
                 if candidate.suffix.lower() == ".lib" and candidate.is_file()),
                None,
            )
            if import_lib is None:
                raise BuildFrontendError(
                    f"Windows art-compiler import library is missing in {binary_dir}"
                )
            sources.append(import_lib)

    # The product is a DSO closure, not only its public entry points. Generated
    # CMake DSOs are emitted in the top-level binary directory; test-only DSOs
    # remain below tests/ and are deliberately excluded.
    if target.os_or_runtime == "windows":
        sources.extend(sorted(binary_dir.glob("*.dll")))
        bundle_root = _target_bindings(target, local).get("bundle_root")
        if bundle_root is None:
            raise BuildFrontendError(
                f"target {target.target_id} has no configured target bundle"
            )
        libcxx_runtime = bundle_root / "lib" / "libcxx" / "bin" / "c++.dll"
        if not libcxx_runtime.is_file():
            raise BuildFrontendError(
                f"Windows target bundle is missing libc++ runtime: {libcxx_runtime}"
            )
        sources.append(libcxx_runtime)
    else:
        sources.extend(sorted(binary_dir.glob("*.so")))

    copied: list[dict[str, object]] = []
    destinations: dict[str, Path] = {}
    for source in sources:
        if source.is_symlink():
            raise BuildFrontendError(f"refusing to stage a symlink: {source}")
        validate_managed_path(source)
        previous = destinations.get(source.name)
        if previous is not None:
            if previous != source:
                raise BuildFrontendError(
                    f"staged artifact name collision: {previous} and {source}"
                )
            continue
        destinations[source.name] = source
        destination = stage_dir / source.name
        if destination.is_symlink():
            raise BuildFrontendError(f"refusing to replace staged symlink: {destination}")
        shutil.copy2(source, destination)
        copied.append({"path": destination.name, "sha256": _sha256(destination)})

    if not copied:
        raise BuildFrontendError(f"no product artifacts found in {binary_dir}; build first")
    _write_json_atomic(stage_dir / "stage_manifest.json", {
        "schema_version": 1,
        "target_id": target.target_id,
        "artifacts": copied,
    })
    print(f"staged {len(copied)} artifacts in {stage_dir}")


def _artifact_candidates(binary_dir: Path, target: TargetProfile, name: str) -> list[Path]:
    if target.os_or_runtime == "windows":
        suffixes = (".exe",) if name in ("dalvikvm", "dex2oat") else (".dll", ".lib")
        prefixes = ("", "lib")
    else:
        suffixes = ("",) if name in ("dalvikvm", "dex2oat") else (".so",)
        prefixes = ("", "lib") if name in ("dalvikvm", "dex2oat") else ("lib", "")
    return [binary_dir / f"{prefix}{name}{suffix}" for prefix in prefixes for suffix in suffixes]


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_windows_art_compiler(
    binary_dir: Path, target: TargetProfile, local: LocalBuildConfig
) -> None:
    dll = next((path for path in _artifact_candidates(binary_dir, target, "art-compiler")
                if path.suffix.lower() == ".dll" and path.is_file()), None)
    if dll is None:
        raise BuildFrontendError(f"Windows art-compiler.dll is missing in {binary_dir}")
    import_lib = next((path for path in _artifact_candidates(binary_dir, target, "art-compiler")
                       if path.suffix.lower() == ".lib" and path.is_file()), None)
    if import_lib is None:
        raise BuildFrontendError(f"Windows art-compiler.lib is missing in {binary_dir}")
    for artifact in (dll, import_lib):
        if artifact.is_symlink():
            raise BuildFrontendError(
                f"Windows art-compiler artifact must be a regular file: {artifact}"
            )
        validate_managed_path(artifact)

    llvm_root = local.tools.get("llvm_root")
    readobj = (
        llvm_root / "bin" / ("llvm-readobj.exe" if os.name == "nt" else "llvm-readobj")
        if llvm_root is not None else None
    )
    if readobj is None or not readobj.exists():
        discovered = shutil.which("llvm-readobj.exe" if os.name == "nt" else "llvm-readobj")
        readobj = Path(discovered) if discovered else None
    if readobj is None or not readobj.exists():
        raise BuildFrontendError(
            "llvm-readobj is required to validate art-compiler.dll exports/imports"
        )
    result = subprocess.run(
        [str(readobj), "--coff-exports", "--coff-imports", str(dll)],
        cwd=REPO_ROOT,
        shell=False,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise BuildFrontendError(f"llvm-readobj failed with exit code {result.returncode}")
    if "art_compiler_jit_create" not in result.stdout:
        raise BuildFrontendError(
            "art-compiler.dll export allowlist is missing art_compiler_jit_create"
        )
    if "Name: art.dll" not in result.stdout:
        raise BuildFrontendError("art-compiler.dll must import its runtime from art.dll")


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


def _resolve_llvm_resource_compiler(local: LocalBuildConfig) -> Path:
    """Resolve LLVM's native resource compiler for Windows target graphs."""
    executable = "llvm-rc.exe" if os.name == "nt" else "llvm-rc"
    llvm_root = local.tools.get("llvm_root")
    path = llvm_root / "bin" / executable if llvm_root is not None else _discover(executable)
    resolved = validate_managed_path(path.resolve())
    if resolved.name not in ("llvm-rc", "llvm-rc.exe"):
        raise BuildFrontendError(
            f"LLVM resource compiler required; got {resolved.name!r}"
        )
    return resolved


def _target_bindings(target: TargetProfile, local: LocalBuildConfig) -> dict[str, Path]:
    bindings = local.target_bindings(target.target_id)
    for path in bindings.values():
        validate_managed_path(path)
    return bindings


def _configured_or_discovered(
    local: LocalBuildConfig, key: str, executable: str
) -> Path:
    configured = local.tools.get(key)
    path = configured if configured is not None else _discover(executable)
    if configured is not None:
        validate_managed_path(path)
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
    cmake_path = _discover("cmake")
    ninja_path = _discover("ninja")
    clang_path = _discover("clang")
    cmake = validate_managed_path(cmake_path.resolve())
    ninja = validate_managed_path(ninja_path.resolve())
    clang = validate_managed_path(clang_path.resolve())
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
