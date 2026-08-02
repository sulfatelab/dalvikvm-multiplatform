"""Portable ART graph/configure/build frontend for Linux and Windows hosts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import stat
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
BUILD_VARIANTS = (
    "product",
    "win32-frame-attribution",
    "win32-stack-high-water",
)
ROOT_MODULES = (
    "dalvikvm",
    "dex2oat",
    "libart-compiler",
    "libjavacrypto",
    "libjavacore",
    "libopenjdk",
    "libicu_jni",
    "libopenjdkjvmti",
)

_LINUX_SYSTEM_NEEDED = frozenset(
    {
        "libc.so.6",
        "libcap.so.2",
        "libexpat.so.1",
        "libgcc_s.so.1",
        "liblz4.so.1",
        "libm.so.6",
        "libstdc++.so.6",
        "libz.so.1",
    }
)
_WINDOWS_SYSTEM_NEEDED = frozenset(
    {
        "advapi32.dll",
        "bcrypt.dll",
        "cfgmgr32.dll",
        "crypt32.dll",
        "dbghelp.dll",
        "gdi32.dll",
        "iphlpapi.dll",
        "kernel32.dll",
        "msvcp140.dll",
        "ntdll.dll",
        "ole32.dll",
        "oleaut32.dll",
        "pdh.dll",
        "psapi.dll",
        "rpcrt4.dll",
        "secur32.dll",
        "shell32.dll",
        "shlwapi.dll",
        "user32.dll",
        "userenv.dll",
        "version.dll",
        "vcruntime140.dll",
        "vcruntime140_1.dll",
        "winmm.dll",
        "ws2_32.dll",
    }
)
_FORBIDDEN_COMMAND_TOOLS = frozenset(
    {
        "ash",
        "ash.exe",
        "awk",
        "awk.exe",
        "bash",
        "bash.exe",
        "clang-cl",
        "clang-cl.exe",
        "clang-mingw",
        "clang-mingw.exe",
        "cl",
        "cl.exe",
        "cp",
        "cp.exe",
        "cygwin",
        "cygwin.exe",
        "dash",
        "dash.exe",
        "find",
        "find.exe",
        "g++",
        "g++.exe",
        "gcc",
        "gcc.exe",
        "gmake",
        "gmake.exe",
        "grep",
        "grep.exe",
        "ld",
        "ld.exe",
        "ld.lld",
        "ld.lld.exe",
        "lld-link",
        "lld-link.exe",
        "make",
        "make.exe",
        "mingw32-make",
        "mingw32-make.exe",
        "msbuild",
        "msbuild.exe",
        "nmake",
        "nmake.exe",
        "powershell",
        "powershell.exe",
        "pwsh",
        "pwsh.exe",
        "readlink",
        "readlink.exe",
        "rm",
        "rm.exe",
        "sed",
        "sed.exe",
        "sh",
        "sh.exe",
        "stat",
        "stat.exe",
        "strings",
        "strings.exe",
        "timeout",
        "timeout.exe",
        "wsl",
        "wsl.exe",
        "zsh",
        "zsh.exe",
    }
)


def _host_can_run_target(target: TargetProfile) -> bool:
    """Conservatively admit runtime probes only on an exact native host."""
    host_os = platform.system().lower()
    if host_os != target.target_platform:
        return False
    host_arch = platform.machine().lower()
    normalized_arch = {
        "amd64": "x86_64",
        "x64": "x86_64",
        "arm64": "aarch64",
        "i386": "x86",
        "i686": "x86",
    }.get(host_arch, host_arch)
    if target.target_arch == "arm64ec":
        return target.target_platform == "windows" and normalized_arch == "aarch64"
    return normalized_arch == target.target_arch


def _boot_image_parallel_limit() -> int:
    """Keep native Windows within its 16 GiB VM limit."""
    return 16 if platform.system().lower() == "windows" else 32


class BuildFrontendError(RuntimeError):
    """Raised for a deterministic user-facing frontend failure."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="build_art.py")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-targets", help="list canonical target profiles")
    subparsers.add_parser(
        "init-local-config", help=f"create ignored {LOCAL_CONFIG_NAME} from discovered tools"
    )

    for command in (
        "generate",
        "check-generated",
        "configure",
        "audit",
        "build",
        "test",
        "stage",
    ):
        sub = subparsers.add_parser(command)
        sub.add_argument("--target-id", required=True)
        sub.add_argument("--build-type", choices=BUILD_TYPES, default=DEFAULT_BUILD_TYPE)
        sub.add_argument("--variant", choices=BUILD_VARIANTS, default="product")
        sub.add_argument("--output-root", type=Path)
        if command in ("build", "test"):
            sub.add_argument("--parallel", type=int)
        if command == "build":
            sub.add_argument("--cmake-target")
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
        _validate_build_variant(target, args.variant, args.command)
        local = load_local_config(REPO_ROOT)
        output_root = _resolve_output_root(args.output_root, local)
        binary_dir = _binary_dir(output_root, target, args.build_type, args.variant)
        validate_managed_path(binary_dir, allow_missing=True)

        if args.command in ("generate", "check-generated", "configure"):
            _generate(
                target,
                args.build_type,
                binary_dir,
                check=args.command == "check-generated",
            )
        if args.command == "configure":
            _configure(target, args.build_type, binary_dir, local, args.variant)
        elif args.command == "audit":
            _audit_generated_commands(target, binary_dir, local)
        elif args.command == "build":
            _build(target, binary_dir, local, args.cmake_target, args.parallel)
        elif args.command == "test":
            _test(binary_dir, local, args.label, args.stage, args.parallel)
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


def _binary_dir(
    output_root: Path,
    target: TargetProfile,
    build_type: str,
    variant: str,
) -> Path:
    configuration = build_type if variant == "product" else f"{build_type}-{variant}"
    return output_root / target.target_id / configuration


def _validate_build_variant(
    target: TargetProfile, variant: str, command: str
) -> None:
    if variant == "product":
        return
    if variant in ("win32-frame-attribution", "win32-stack-high-water") and (
        target.target_id != "windows-x86_64-msvc"
    ):
        raise BuildFrontendError(
            f"{variant} is an exact windows-x86_64-msvc test variant"
        )
    if command == "stage":
        raise BuildFrontendError(
            f"test-only build variant {variant} cannot be staged as a product"
        )


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
    variant: str = "product",
) -> None:
    tools = _resolve_tools(local, need_compiler=True)
    tools.update(_resolve_llvm_inspection_tools(local))
    jdk = _resolve_jdk(local)
    tools["java"] = jdk / "bin" / ("java.exe" if os.name == "nt" else "java")
    tools["javac"] = jdk / "bin" / ("javac.exe" if os.name == "nt" else "javac")
    if target.target_platform == "windows":
        tools["llvm-rc"] = _resolve_llvm_resource_compiler(local)
        tools["llvm-pdbutil"] = _resolve_llvm_pdbutil(local)
    bindings = _target_bindings(target, local)
    generated = binary_dir / "generated"
    fingerprint = _build_fingerprint(
        target,
        build_type,
        variant,
        tools,
        generated,
        bindings,
    )
    manifest_path = binary_dir / "build_manifest.json"
    command = [
        str(tools["cmake"]),
        "-S",
        str(REPO_ROOT / "native"),
        "-B",
        str(binary_dir),
        "-G",
        "Ninja",
        f"-DCMAKE_BUILD_TYPE={build_type}",
        "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
        f"-DCMAKE_MAKE_PROGRAM={tools['ninja']}",
        f"-DCMAKE_C_COMPILER={tools['clang']}",
        f"-DCMAKE_CXX_COMPILER={tools['clang++']}",
        f"-DCMAKE_C_COMPILER_TARGET={target.target_triple}",
        f"-DCMAKE_CXX_COMPILER_TARGET={target.target_triple}",
        f"-DCMAKE_ASM_COMPILER_TARGET={target.target_triple}",
        f"-DCMAKE_SYSTEM_NAME={target.cmake_system_name}",
        f"-DPython3_EXECUTABLE={_python_executable()}",
        f"-DART_JDK_ROOT={jdk}",
        f"-DART_PROFILE_FILE={generated / 'target_profile.cmake'}",
        f"-DART_GRAPH_FILE={generated / 'art_graph.cmake'}",
        f"-DART_LLVM_READOBJ={tools['llvm-readobj']}",
        f"-DART_LLVM_OBJDUMP={tools['llvm-objdump']}",
        "-DART_ENABLE_TARGET_RUNTIME_TESTS="
        + ("ON" if _host_can_run_target(target) else "OFF"),
        f"-DART_BOOT_IMAGE_PARALLEL={_boot_image_parallel_limit()}",
        f"-DART_TEST_VARIANT={variant}",
    ]
    if target.target_platform == "windows":
        bundle = bindings.get("bundle_root")
        if bundle is None:
            raise BuildFrontendError(
                f"target {target.target_id} requires targets.{target.target_id}.bundle_root "
                "in .art-build.local.toml"
            )
        command.extend((
            f"-DART_TARGET_BUNDLE_ROOT={bundle}",
            f"-DART_LLVM_PDBUTIL={tools['llvm-pdbutil']}",
            f"-DCMAKE_RC_COMPILER={tools['llvm-rc'].as_posix()}",
        ))
        if target.target_abi == "msvc":
            command.append("-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreadedDLL")
        command.append("-DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY")
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
    _audit_generated_commands(target, binary_dir, local)
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
    _audit_generated_commands(target, binary_dir, local)
    if target.target_platform == "windows" and (
        cmake_target is None or cmake_target in ("all", "art-compiler")
    ):
        _validate_windows_art_compiler(binary_dir, target, local)


def _test(
    binary_dir: Path,
    local: LocalBuildConfig,
    labels: list[str],
    stages: list[str] | None = None,
    parallel: int | None = None,
) -> None:
    _require_configured(binary_dir)
    cmake = _resolve_tools(local, need_compiler=False)["cmake"]
    catalog_path, catalog, probes = _load_test_catalog(binary_dir)
    target_id = str(catalog["target_id"])
    stages = list(dict.fromkeys(stages or []))
    stage_labels = [_stage_label(stage) for stage in stages]
    if parallel is not None and parallel < 1:
        raise BuildFrontendError("--parallel must be positive")

    def build_test_target(name: str) -> None:
        command = [str(cmake), "--build", str(binary_dir)]
        if parallel is not None:
            command.extend(("--parallel", str(parallel)))
        command.extend(("--target", name))
        _run_checked(command)

    for stage in stages:
        declared = [probe for probe in probes if probe["stage"] == stage]
        if not declared:
            raise BuildFrontendError(
                f"test stage {stage} has no declared probes for target {target_id}"
            )
        applicable = [probe for probe in declared if probe["applicable"]]
        if not applicable:
            raise BuildFrontendError(
                f"test stage {stage} has zero applicable probes for target {target_id}; "
                f"all {len(declared)} declarations were excluded by their selectors"
            )
        build_test_target(f"art-test-stage-{stage}")
        # Ninja may have re-run CMake because the catalog declaration changed.
        # Reload before recording status so an old in-memory catalog cannot
        # overwrite the freshly configured execution/CTest metadata.
        catalog_path, catalog, probes = _load_test_catalog(binary_dir)
        target_id = str(catalog["target_id"])
        declared = [probe for probe in probes if probe["stage"] == stage]
        applicable = [probe for probe in declared if probe["applicable"]]
        if not declared or not applicable:
            raise BuildFrontendError(
                f"test stage {stage} changed applicability during CMake regeneration"
            )
        for probe in applicable:
            probe["build_verified"] = True
            probe["build_status"] = "verified"
        _write_json_atomic(catalog_path, catalog)

    selected = probes if not stages else [
        probe for probe in probes if probe["stage"] in stages
    ]
    applicable_selected = [probe for probe in selected if probe["applicable"]]
    if not stages:
        if not applicable_selected:
            raise BuildFrontendError(
                f"target {target_id} has zero applicable probes in the selected test scope"
            )
        build_test_target("art-tests")
        catalog_path, catalog, probes = _load_test_catalog(binary_dir)
        target_id = str(catalog["target_id"])
        selected = probes
        applicable_selected = [probe for probe in probes if probe["applicable"]]
        if not applicable_selected:
            raise BuildFrontendError(
                f"target {target_id} changed to zero applicable probes during CMake regeneration"
            )
        for probe in applicable_selected:
            probe["build_verified"] = True
            probe["build_status"] = "verified"
        _write_json_atomic(catalog_path, catalog)

    registered = [
        probe for probe in selected
        if probe["applicable"] and probe["ctest_registered"]
    ]
    if not registered:
        applicable_count = len(applicable_selected)
        if applicable_count:
            raise BuildFrontendError(
                f"target {target_id} has {applicable_count} applicable probes in the "
                "selected scope but zero registered runnable CTest gates"
            )
        raise BuildFrontendError(
            f"target {target_id} has zero applicable probes in the selected test scope"
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
    if not labels:
        for probe in registered:
            probe["runtime_verified"] = True
            probe["runtime_status"] = "verified"
        _write_json_atomic(catalog_path, catalog)


def _load_test_catalog(
    binary_dir: Path,
) -> tuple[Path, dict[str, object], list[dict[str, object]]]:
    path = binary_dir / "tests" / "art_test_catalog.json"
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BuildFrontendError(
            f"test catalog is missing; reconfigure the build directory: {path}"
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildFrontendError(f"cannot read test catalog {path}: {exc}") from exc
    if not isinstance(catalog, dict) or catalog.get("schema_version") != 1:
        raise BuildFrontendError(f"unsupported test catalog schema in {path}")
    target_id = catalog.get("target_id")
    raw_probes = catalog.get("probes")
    if not isinstance(target_id, str) or not isinstance(raw_probes, list):
        raise BuildFrontendError(f"malformed test catalog in {path}")
    probes: list[dict[str, object]] = []
    required = {
        "name": str,
        "stage": str,
        "execution": str,
        "applicable": bool,
        "ctest_registered": bool,
        "build_verified": bool,
        "runtime_verified": bool,
    }
    for index, raw_probe in enumerate(raw_probes):
        if not isinstance(raw_probe, dict):
            raise BuildFrontendError(
                f"malformed test catalog probe {index} in {path}"
            )
        for key, expected_type in required.items():
            if not isinstance(raw_probe.get(key), expected_type):
                raise BuildFrontendError(
                    f"malformed test catalog probe {index} field {key!r} in {path}"
                )
        probes.append(raw_probe)
    return path, catalog, probes


def _stage(target: TargetProfile, binary_dir: Path, local: LocalBuildConfig) -> None:
    """Copy product outputs into a regular-file staging tree and record them."""
    _require_configured(binary_dir)
    _audit_generated_commands(target, binary_dir, local)
    if target.target_platform == "windows":
        _validate_windows_art_compiler(binary_dir, target, local)

    stage_dir = binary_dir / "stage"
    validate_managed_path(stage_dir, allow_missing=True)
    if stage_dir.exists() or stage_dir.is_symlink():
        _reject_managed_tree(stage_dir)
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)
    product_outputs = _ninja_product_outputs(binary_dir, target, local)
    sources = [path for path, _kind in product_outputs]
    if target.target_platform == "windows":
        import_lib = next(
            (
                candidate
                for candidate in _artifact_candidates(
                    binary_dir, target, "art-compiler"
                )
                if candidate.suffix.lower() == ".lib" and candidate.is_file()
            ),
            None,
        )
        if import_lib is None:
            raise BuildFrontendError(
                f"Windows art-compiler import library is missing in {binary_dir}"
            )
        sources.append(import_lib)
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

    runtime_sources = (
        (
            binary_dir / "tests" / "managed" / "boot.jar",
            stage_dir / "runtime" / "boot.jar",
        ),
        (
            REPO_ROOT / "vendor" / "icu" / "icu4c" / "source" / "stubdata"
            / "icudt72l.dat",
            stage_dir / "runtime" / "icu" / "icudt72l.dat",
        ),
        (
            REPO_ROOT / "compat" / "java-resources" / "java" / "security"
            / "security.properties",
            stage_dir / "runtime" / "etc" / "security" / "security.properties",
        ),
    )
    for source, destination in runtime_sources:
        copied.append(_copy_staged_file(source, destination, stage_dir))
    boot_image_status, boot_image_files = _stage_boot_image(
        binary_dir,
        stage_dir,
        target,
        boot_jar=runtime_sources[0][0],
    )
    copied.extend(boot_image_files)

    cacerts_root = REPO_ROOT / "native" / "runtime-assets" / "etc" / "security" / "cacerts"
    validate_managed_path(cacerts_root)
    certificate_count = 0
    for source in sorted(cacerts_root.iterdir(), key=lambda path: path.name):
        if not source.is_file():
            raise BuildFrontendError(f"non-file entry in product cacerts: {source}")
        validate_managed_path(source)
        destination = stage_dir / "runtime" / "etc" / "security" / "cacerts" / source.name
        copied.append(_copy_staged_file(source, destination, stage_dir))
        if re.fullmatch(r"[0-9a-f]{8}\.[0-9]+", source.name):
            certificate_count += 1
    if certificate_count < 1:
        raise BuildFrontendError("product runtime has zero AndroidCAStore certificates")
    for keychain_directory in ("cacerts-added", "cacerts-removed"):
        (stage_dir / "runtime" / "data" / "misc" / "keychain"
         / keychain_directory).mkdir(parents=True, exist_ok=True)

    if not copied:
        raise BuildFrontendError(f"no product artifacts found in {binary_dir}; build first")
    topology = _validate_staged_topology(
        stage_dir,
        target,
        local,
        executable_names={
            path.name for path, kind in product_outputs if kind == "executable"
        },
    )
    _write_json_atomic(stage_dir / "stage_manifest.json", {
        "schema_version": 2,
        "target_id": target.target_id,
        "artifacts": copied,
        "runtime_package": {"boot_image": boot_image_status},
        "topology": topology,
    })
    _reject_managed_tree(stage_dir)
    print(
        f"staged {len(copied)} regular files in {stage_dir} "
        f"(AndroidCAStore certificates={certificate_count})"
    )


def _stage_boot_image(
    binary_dir: Path,
    stage_dir: Path,
    target: TargetProfile,
    *,
    boot_jar: Path,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    if "boot_image" not in target.capabilities:
        return {"status": "unsupported"}, []
    source_root = binary_dir / "runtime" / "boot-image"
    if not source_root.is_dir():
        if _host_can_run_target(target):
            raise BuildFrontendError(
                "native runtime package is missing its declared boot image; "
                "build the complete product first"
            )
        return {"status": "not-built-cross-host"}, []
    validate_managed_path(source_root)
    _reject_managed_tree(source_root)
    manifest_path = source_root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildFrontendError(f"cannot read boot image manifest: {exc}") from exc
    if (
        manifest.get("schema_version") != 1
        or manifest.get("target_id") != target.target_id
        or manifest.get("instruction_set") != target.aosp_arch
        or manifest.get("logical_boot_jar") != "/system/framework/boot.jar"
        or manifest.get("boot_jar_sha256") != _sha256(boot_jar)
    ):
        raise BuildFrontendError("boot image manifest does not match the product")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise BuildFrontendError("boot image manifest has no artifact list")
    expected = {
        f"{target.aosp_arch}/boot.art",
        f"{target.aosp_arch}/boot.oat",
        f"{target.aosp_arch}/boot.vdex",
    }
    copied: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw in artifacts:
        if not isinstance(raw, dict) or not isinstance(raw.get("path"), str):
            raise BuildFrontendError("boot image artifact record is malformed")
        relative = raw["path"].replace("\\", "/")
        if relative not in expected or relative in seen:
            raise BuildFrontendError(f"unexpected boot image artifact: {relative}")
        source = source_root / Path(relative)
        validate_managed_path(source)
        if not source.is_file() or source.is_symlink():
            raise BuildFrontendError(f"boot image artifact is not regular: {source}")
        if raw.get("sha256") != _sha256(source) or raw.get("size") != source.stat().st_size:
            raise BuildFrontendError(f"boot image artifact identity changed: {relative}")
        destination = stage_dir / "runtime" / "boot-image" / Path(relative)
        copied.append(_copy_staged_file(source, destination, stage_dir))
        seen.add(relative)
    if seen != expected:
        raise BuildFrontendError(
            f"boot image artifact set is incomplete: {sorted(expected - seen)}"
        )
    copied.append(
        _copy_staged_file(
            manifest_path,
            stage_dir / "runtime" / "boot-image" / "manifest.json",
            stage_dir,
        )
    )
    return {
        "status": "included",
        "instruction_set": target.aosp_arch,
        "artifacts": sorted(expected),
    }, copied


def _copy_staged_file(source: Path, destination: Path, stage_dir: Path) -> dict[str, object]:
    validate_managed_path(source)
    if not source.is_file() or source.is_symlink():
        raise BuildFrontendError(f"staged input must be a regular file: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    validate_managed_path(destination.parent)
    shutil.copy2(source, destination)
    relative = destination.relative_to(stage_dir).as_posix()
    return {"path": relative, "sha256": _sha256(destination)}


def _reject_managed_tree(root: Path) -> None:
    validate_managed_path(root)
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        for name in (*directories, *files):
            validate_managed_path(Path(current) / name)


def _audit_generated_commands(
    target: TargetProfile,
    binary_dir: Path,
    local: LocalBuildConfig,
) -> dict[str, object]:
    """Mechanically enforce the generated Ninja/plain-Clang command contract."""
    tools = _resolve_tools(local, need_compiler=True)
    cache = _read_cmake_cache(binary_dir / "CMakeCache.txt")
    expected_cache = {
        "CMAKE_GENERATOR": "Ninja",
        "CMAKE_SYSTEM_NAME": target.cmake_system_name,
        "CMAKE_C_COMPILER_TARGET": target.target_triple,
        "CMAKE_CXX_COMPILER_TARGET": target.target_triple,
        "CMAKE_ASM_COMPILER_TARGET": target.target_triple,
    }
    for key, expected in expected_cache.items():
        if cache.get(key) != expected:
            raise BuildFrontendError(
                f"generated-command audit: {key} must be {expected!r}, "
                f"got {cache.get(key)!r}"
            )
    if _tool_basename(cache.get("CMAKE_MAKE_PROGRAM", "")) not in (
        "ninja",
        "ninja.exe",
    ):
        raise BuildFrontendError(
            "generated-command audit: CMAKE_MAKE_PROGRAM is not Ninja"
        )
    for key, tool_key in (
        ("CMAKE_C_COMPILER", "clang"),
        ("CMAKE_CXX_COMPILER", "clang++"),
    ):
        if not _same_host_path(cache.get(key, ""), tools[tool_key]):
            raise BuildFrontendError(
                f"generated-command audit: {key} differs from configured {tool_key}"
            )

    forbidden_generator_artifacts = [
        path.name
        for path in binary_dir.iterdir()
        if path.name == "Makefile"
        or path.suffix.lower() in (".sln", ".vcxproj", ".filters")
        or path.name.startswith("build-") and path.suffix == ".ninja"
    ]
    if forbidden_generator_artifacts:
        raise BuildFrontendError(
            "generated-command audit: forbidden generator artifacts: "
            + ", ".join(sorted(forbidden_generator_artifacts))
        )

    compile_path = binary_dir / "compile_commands.json"
    try:
        compile_records = json.loads(compile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildFrontendError(
            f"generated-command audit: cannot read {compile_path}: {exc}"
        ) from exc
    if not isinstance(compile_records, list) or not compile_records:
        raise BuildFrontendError(
            "generated-command audit: compile_commands.json is empty or malformed"
        )

    ninja = tools["ninja"]
    inventory_text = _run_ninja_tool(binary_dir, ninja, "targets", "all")
    link_outputs = _parse_ninja_link_outputs(inventory_text, target)
    product_executables = {
        _product_target_name(name, target)
        for name, kind, _language in link_outputs
        if kind == "executable"
    }
    cross_target = not _host_can_run_target(target)
    allowed_search_roots = _command_search_roots(
        target, binary_dir, local, tools
    )
    compiler_counts = {"clang": 0, "clang++": 0}
    for index, raw_record in enumerate(compile_records):
        if not isinstance(raw_record, dict):
            raise BuildFrontendError(
                f"generated-command audit: compile record {index} is not an object"
            )
        command = raw_record.get("command")
        source = raw_record.get("file")
        output = raw_record.get("output", "")
        if not isinstance(command, str) or not isinstance(source, str):
            raise BuildFrontendError(
                f"generated-command audit: compile record {index} is malformed"
            )
        tokens = _command_tokens(command)
        if not tokens:
            raise BuildFrontendError(
                f"generated-command audit: compile record {index} has no command"
            )
        suffix = Path(source).suffix.lower()
        expected_driver = "clang" if suffix in (".c", ".s") else "clang++"
        actual_driver = _tool_basename(tokens[0])
        expected_names = {
            expected_driver,
            f"{expected_driver}.exe",
        }
        if actual_driver not in expected_names or not _same_host_path(
            tokens[0], tools[expected_driver]
        ):
            raise BuildFrontendError(
                f"generated-command audit: compile record {index} does not start "
                f"with configured {expected_driver}"
            )
        compiler_counts[expected_driver] += 1
        if not _command_has_target(tokens, target.target_triple) or "-c" not in tokens:
            raise BuildFrontendError(
                f"generated-command audit: compile record {index} omits target or -c"
            )
        if target.target_platform == "linux" and "-fPIC" not in tokens:
            raise BuildFrontendError(
                f"generated-command audit: Linux compile record {index} omits -fPIC"
            )
        normalized_output = str(output).replace("\\", "/")
        if (
            target.target_platform == "linux"
            and any(
                f"CMakeFiles/{name}.dir/" in normalized_output
                for name in product_executables
            )
            and "-fPIE" not in tokens
        ):
            raise BuildFrontendError(
                f"generated-command audit: product executable compile record {index} "
                "omits -fPIE"
            )
        _audit_command_invocations(command)
        if not _path_below_any(source, (REPO_ROOT, binary_dir)):
            raise BuildFrontendError(
                f"generated-command audit: compile source is outside source/output roots: "
                f"{source}"
            )
        if cross_target:
            _audit_search_paths(
                command,
                allowed_search_roots,
                binary_dir,
                context=f"compile record {index}",
            )

    all_commands_text = _run_ninja_tool(binary_dir, ninja, "commands")
    all_commands = [line for line in all_commands_text.splitlines() if line.strip()]
    if not all_commands:
        raise BuildFrontendError("generated-command audit: Ninja command graph is empty")
    for index, command in enumerate(all_commands):
        _audit_command_invocations(command)
        _audit_shell_operators(command, index)

    link_counts = {"executable": 0, "shared-library": 0}
    for name, kind, language in link_outputs:
        target_commands = _run_ninja_tool(binary_dir, ninja, "commands", name)
        command_lines = [
            line for line in target_commands.splitlines() if line.strip()
        ]
        if not command_lines:
            raise BuildFrontendError(
                f"generated-command audit: Ninja emits no command for {name}"
            )
        link_command = command_lines[-1]
        _audit_link_command(
            link_command,
            name=name,
            kind=kind,
            language=language,
            target=target,
            tools=tools,
        )
        if cross_target:
            _audit_search_paths(
                link_command,
                allowed_search_roots,
                binary_dir,
                context=f"link output {name}",
                include_absolute_libraries=True,
            )
        link_counts[kind] += 1

    if cross_target:
        _audit_cmake_implicit_search_paths(
            binary_dir, allowed_search_roots
        )

    result: dict[str, object] = {
        "schema_version": 1,
        "target_id": target.target_id,
        "generator": "Ninja",
        "compile_commands": len(compile_records),
        "ninja_commands": len(all_commands),
        "compiler_commands": compiler_counts,
        "product_links": link_counts,
        "cross_search_isolation": cross_target,
    }
    _write_json_atomic(binary_dir / "command_audit.json", result)
    print(
        f"audited {len(compile_records)} compile commands, "
        f"{len(all_commands)} Ninja commands, and {sum(link_counts.values())} "
        f"product links for {target.target_id}"
    )
    return result


def _read_cmake_cache(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        raise BuildFrontendError(
            f"generated-command audit: cannot read {path}: {exc}"
        ) from exc
    values: dict[str, str] = {}
    for line in lines:
        if not line or line.startswith(("#", "//")) or "=" not in line:
            continue
        field, value = line.split("=", 1)
        name, separator, _kind = field.partition(":")
        if separator:
            values[name] = value
    return values


def _run_ninja_tool(binary_dir: Path, ninja: Path, *arguments: str) -> str:
    result = subprocess.run(
        [str(ninja), "-C", str(binary_dir), "-t", *arguments],
        cwd=REPO_ROOT,
        shell=False,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise BuildFrontendError(
            "generated-command audit: Ninja tool failed for "
            + " ".join(arguments)
            + f" (exit {result.returncode})"
        )
    return result.stdout


def _command_tokens(command: str) -> list[str]:
    return [
        quoted if quoted else bare
        for quoted, bare in re.findall(r'"([^"\r\n]*)"|(\S+)', command)
    ]


def _tool_basename(token: str) -> str:
    return token.strip('"').replace("\\", "/").rsplit("/", 1)[-1].lower()


def _command_has_target(tokens: list[str], target_triple: str) -> bool:
    if f"--target={target_triple}" in tokens:
        return True
    return any(
        token in ("-target", "--target")
        and index + 1 < len(tokens)
        and tokens[index + 1] == target_triple
        for index, token in enumerate(tokens)
    )


def _same_host_path(left: str | Path, right: str | Path) -> bool:
    return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(
        os.path.abspath(str(right))
    )


def _path_below_any(path: str | Path, roots: tuple[Path, ...]) -> bool:
    candidate = os.path.normcase(os.path.abspath(str(path)))
    for root in roots:
        normalized_root = os.path.normcase(os.path.abspath(str(root)))
        try:
            if os.path.commonpath((candidate, normalized_root)) == normalized_root:
                return True
        except ValueError:
            continue
    return False


def _command_search_roots(
    target: TargetProfile,
    binary_dir: Path,
    local: LocalBuildConfig,
    tools: dict[str, Path],
) -> tuple[Path, ...]:
    roots = [REPO_ROOT, binary_dir]
    roots.extend(_target_bindings(target, local).values())
    llvm_root = local.tools.get("llvm_root")
    if llvm_root is not None:
        roots.append(llvm_root)
    else:
        roots.append(tools["clang"].parent.parent)
    return tuple(dict.fromkeys(path.resolve() for path in roots))


def _extract_search_paths(
    command: str,
    *,
    include_absolute_libraries: bool,
) -> list[str]:
    tokens = _command_tokens(command)
    paths: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        lowered = token.lower()
        if token in ("-I", "-L", "-isystem", "--sysroot"):
            if index + 1 < len(tokens):
                paths.append(tokens[index + 1])
                index += 2
                continue
        elif token.startswith(("-I", "-L")) and len(token) > 2:
            paths.append(token[2:])
        elif lowered.startswith("-isystem=") or lowered.startswith("--sysroot="):
            paths.append(token.split("=", 1)[1])
        elif lowered.startswith("/libpath:"):
            paths.append(token.split(":", 1)[1])
        elif include_absolute_libraries and lowered.endswith(
            (".a", ".so", ".lib", ".dll.a")
        ) and re.match(r"^/[a-z][a-z0-9_-]*:", lowered) is None:
            paths.append(token)
        index += 1
    return paths


def _audit_search_paths(
    command: str,
    allowed_roots: tuple[Path, ...],
    binary_dir: Path,
    *,
    context: str,
    include_absolute_libraries: bool = False,
) -> None:
    for spelling in _extract_search_paths(
        command,
        include_absolute_libraries=include_absolute_libraries,
    ):
        candidate = Path(spelling)
        if not candidate.is_absolute():
            candidate = binary_dir / candidate
        if not _path_below_any(candidate, allowed_roots):
            raise BuildFrontendError(
                f"generated-command audit: undeclared host search path in "
                f"{context}: {spelling}"
            )


def _audit_cmake_implicit_search_paths(
    binary_dir: Path,
    allowed_roots: tuple[Path, ...],
) -> None:
    pattern = re.compile(
        r'^set\(CMAKE_(?:C|CXX)_IMPLICIT_(?:INCLUDE|LINK)_DIRECTORIES "([^"]*)"\)$',
        re.MULTILINE,
    )
    compiler_metadata = sorted(
        (binary_dir / "CMakeFiles").glob("*/CMake*CCompiler.cmake")
    ) + sorted((binary_dir / "CMakeFiles").glob("*/CMakeCXXCompiler.cmake"))
    if not compiler_metadata:
        raise BuildFrontendError(
            "generated-command audit: CMake compiler metadata is missing"
        )
    for path in compiler_metadata:
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in pattern.finditer(text):
            for spelling in match.group(1).split(";"):
                if spelling and not _path_below_any(spelling, allowed_roots):
                    raise BuildFrontendError(
                        "generated-command audit: undeclared implicit host search "
                        f"path in {path.name}: {spelling}"
                    )


def _audit_command_invocations(command: str) -> None:
    for tokens in _command_invocations(command):
        if not tokens:
            continue
        executable = _tool_basename(tokens[0])
        if executable == "cd":
            continue
        if executable in _FORBIDDEN_COMMAND_TOOLS:
            raise BuildFrontendError(
                f"generated-command audit: forbidden command tool {executable}"
            )
        if executable in ("cmake", "cmake.exe") and len(tokens) > 3:
            try:
                env_index = tokens.index("env", 1)
            except ValueError:
                continue
            nested = env_index + 1
            while nested < len(tokens) and "=" in tokens[nested]:
                nested += 1
            if nested < len(tokens):
                nested_name = _tool_basename(tokens[nested])
                if nested_name in _FORBIDDEN_COMMAND_TOOLS:
                    raise BuildFrontendError(
                        "generated-command audit: forbidden command tool "
                        f"{nested_name} through cmake -E env"
                    )


def _command_invocations(command: str) -> list[list[str]]:
    """Tokenize each payload in CMake's platform shell wrappers.

    Native Windows Ninja link rules commonly use
    ``cmd.exe /C "cd . && clang++.exe ... && cd ."``.  Splitting the command
    first exposes the compiler payload without mistaking the quoted wrapper
    body for one executable token.  This also matches the ``: && ... && :``
    wrapper emitted on POSIX hosts.
    """
    invocations: list[list[str]] = []
    for raw_segment in re.split(r"\s+&&\s+|\s+\|\|\s+", command):
        segment = raw_segment.strip().lstrip(":").strip().lstrip('"')
        tokens = _command_tokens(segment)
        if tokens:
            invocations.append(tokens)
    return invocations


def _audit_shell_operators(command: str, index: int) -> None:
    if "$(" in command or "`" in command:
        raise BuildFrontendError(
            f"generated-command audit: command {index} contains command substitution"
        )
    if "||" in command:
        raise BuildFrontendError(
            f"generated-command audit: command {index} contains conditional chaining"
        )
    if re.search(r"(?:^|\s)[<>](?:\s|[^=])", command):
        raise BuildFrontendError(
            f"generated-command audit: command {index} contains redirection"
        )
    if re.search(r"(?:^|\s)\|(?:\s|$)", command):
        raise BuildFrontendError(
            f"generated-command audit: command {index} contains a pipe"
        )
    if re.search(r"(?:^|\s);(?:\s|$)", command):
        raise BuildFrontendError(
            f"generated-command audit: command {index} contains statement chaining"
        )
    lowered = command.lower()
    working_directory_wrapper = command.startswith("cd ") or (
        "cmd.exe /c \"cd /d " in lowered
    )
    if working_directory_wrapper and command.count(" && ") != 1:
        raise BuildFrontendError(
            f"generated-command audit: command {index} has multiple project payloads"
        )


def _parse_ninja_link_outputs(
    output: str,
    target: TargetProfile,
) -> list[tuple[str, str, str]]:
    declared: dict[str, tuple[str, str]] = {}
    for line in output.splitlines():
        name, separator, rule = line.rpartition(": ")
        if not separator or "/" in name or "\\" in name:
            continue
        if "SHARED_LIBRARY_LINKER__" in rule:
            kind = "shared-library"
        elif "EXECUTABLE_LINKER__" in rule:
            kind = "executable"
        else:
            continue
        lowered = name.lower()
        if target.target_platform == "windows":
            expected = (
                lowered.endswith(".dll")
                if kind == "shared-library"
                else lowered.endswith(".exe")
            )
        else:
            expected = (
                lowered.endswith(".so")
                if kind == "shared-library"
                else "." not in name
            )
        if not expected or name in declared:
            continue
        if "CXX_" in rule:
            language = "c++"
        elif re.search(r"(?:^|_)C_(?:SHARED|EXECUTABLE)", rule):
            language = "c"
        else:
            raise BuildFrontendError(
                f"generated-command audit: unknown link language for {name}: {rule}"
            )
        declared[name] = (kind, language)
    return [
        (name, kind, language)
        for name, (kind, language) in sorted(declared.items())
    ]


def _product_target_name(name: str, target: TargetProfile) -> str:
    if target.target_platform == "windows":
        return name.rsplit(".", 1)[0]
    if name.startswith("lib") and name.endswith(".so"):
        return name[3:-3]
    return name.rsplit(".", 1)[0]


def _audit_link_command(
    command: str,
    *,
    name: str,
    kind: str,
    language: str,
    target: TargetProfile,
    tools: dict[str, Path],
) -> None:
    invocations = _command_invocations(command)
    tokens = [token for invocation in invocations for token in invocation]
    driver = "clang++" if language == "c++" else "clang"
    driver_tokens = [
        invocation[0]
        for invocation in invocations
        if _tool_basename(invocation[0]) in (driver, f"{driver}.exe")
    ]
    if not driver_tokens or not any(
        _same_host_path(token, tools[driver]) for token in driver_tokens
    ):
        raise BuildFrontendError(
            f"generated-command audit: {name} does not link through configured {driver}"
        )
    if not _command_has_target(tokens, target.target_triple):
        raise BuildFrontendError(
            f"generated-command audit: {name} link omits target triple"
        )
    if "-fuse-ld=lld" not in tokens:
        raise BuildFrontendError(
            f"generated-command audit: {name} link omits driver-level LLD selection"
        )
    if kind == "shared-library" and "-shared" not in tokens:
        raise BuildFrontendError(
            f"generated-command audit: {name} shared-library link omits -shared"
        )
    if (
        kind == "executable"
        and target.target_platform == "linux"
        and "-pie" not in tokens
    ):
        raise BuildFrontendError(
            f"generated-command audit: {name} executable link omits -pie"
        )
    if target.target_platform == "windows":
        upper = command.upper()
        required = ["/DYNAMICBASE", "/NXCOMPAT"]
        if target.target_arch in ("x86_64", "aarch64", "arm64ec"):
            required.append("/HIGHENTROPYVA")
        missing = [flag for flag in required if flag not in upper]
        if missing:
            raise BuildFrontendError(
                f"generated-command audit: {name} omits PE image flags: "
                + ", ".join(missing)
            )


def _ninja_product_outputs(
    binary_dir: Path, target: TargetProfile, local: LocalBuildConfig
) -> list[tuple[Path, str]]:
    """Return current top-level CMake link outputs, excluding stale files."""
    ninja = _configured_or_discovered(local, "ninja", "ninja")
    result = subprocess.run(
        [str(ninja), "-C", str(binary_dir), "-t", "targets", "all"],
        cwd=REPO_ROOT,
        shell=False,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise BuildFrontendError(
            f"Ninja target inventory failed with exit code {result.returncode}"
        )
    declared = _parse_ninja_product_outputs(result.stdout, target)
    if not declared:
        raise BuildFrontendError(
            f"Ninja declares no top-level product link outputs in {binary_dir}"
        )
    missing = [name for name, _kind in declared if not (binary_dir / name).is_file()]
    if missing:
        raise BuildFrontendError(
            "product outputs are missing; run the full build before staging: "
            + ", ".join(missing)
        )
    outputs = [(binary_dir / name, kind) for name, kind in declared]
    for path, _kind in outputs:
        validate_managed_path(path)
        if path.is_symlink():
            raise BuildFrontendError(f"product output must be a regular file: {path}")
    return outputs


def _parse_ninja_product_outputs(
    output: str, target: TargetProfile
) -> list[tuple[str, str]]:
    declared: dict[str, str] = {}
    for line in output.splitlines():
        name, separator, rule = line.rpartition(": ")
        if not separator or "/" in name or "\\" in name:
            continue
        if "SHARED_LIBRARY_LINKER__" in rule:
            kind = "shared-library"
        elif "EXECUTABLE_LINKER__" in rule:
            kind = "executable"
        else:
            continue
        lowered = name.lower()
        if target.target_platform == "windows":
            expected = (
                lowered.endswith(".dll")
                if kind == "shared-library"
                else lowered.endswith(".exe")
            )
        else:
            expected = lowered.endswith(".so") if kind == "shared-library" else "." not in name
        if not expected or name in declared:
            continue
        declared[name] = kind
    return sorted(declared.items())


def _validate_staged_topology(
    stage_dir: Path,
    target: TargetProfile,
    local: LocalBuildConfig,
    *,
    executable_names: set[str],
) -> dict[str, object]:
    readobj = _resolve_llvm_inspection_tools(local)["llvm-readobj"]
    if target.target_platform == "windows":
        inspect = sorted((*stage_dir.glob("*.dll"), *stage_dir.glob("*.exe")))
        normalize = str.lower
    else:
        inspect = sorted(
            [*stage_dir.glob("*.so"), *(stage_dir / name for name in executable_names)]
        )
        normalize = lambda value: value
    stage_names = {
        normalize(path.name)
        for path in stage_dir.iterdir()
        if path.is_file() and not path.is_symlink()
    }
    dependencies: dict[str, list[str]] = {}
    system_dependencies: set[str] = set()
    runtime_paths: dict[str, list[str]] = {}
    for artifact in inspect:
        validate_managed_path(artifact)
        result = subprocess.run(
            [str(readobj), "--needed-libs", "--dynamic-table", str(artifact)],
            cwd=REPO_ROOT,
            shell=False,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise BuildFrontendError(
                f"llvm-readobj failed for staged {artifact.name} "
                f"with exit code {result.returncode}"
            )
        needed = _parse_needed_libraries(result.stdout)
        dependencies[artifact.name] = needed
        for name in needed:
            if normalize(name) in stage_names:
                continue
            if not _approved_system_dependency(target, name):
                raise BuildFrontendError(
                    f"staged {artifact.name} has unresolved dependency {name}"
                )
            system_dependencies.add(name)
        if target.target_platform == "linux":
            paths = _parse_elf_runtime_paths(result.stdout)
            forbidden = [
                path
                for path in paths
                if not (path == "$ORIGIN" or path.startswith("$ORIGIN/"))
            ]
            if forbidden:
                raise BuildFrontendError(
                    f"staged {artifact.name} has non-relocatable RUNPATH/RPATH: "
                    + ", ".join(forbidden)
                )
            runtime_paths[artifact.name] = paths

    compiler_name = (
        "art-compiler.dll"
        if target.target_platform == "windows"
        else "libart-compiler.so"
    )
    runtime_name = "art.dll" if target.target_platform == "windows" else "libart.so"
    compiler_needed = {normalize(name) for name in dependencies.get(compiler_name, [])}
    runtime_needed = {normalize(name) for name in dependencies.get(runtime_name, [])}
    if normalize(runtime_name) not in compiler_needed:
        raise BuildFrontendError(
            f"staged {compiler_name} must depend on {runtime_name}"
        )
    if normalize(compiler_name) in runtime_needed:
        raise BuildFrontendError(
            f"staged {runtime_name} must not depend on {compiler_name}"
        )
    return {
        "dependencies": dependencies,
        "runtime_paths": runtime_paths,
        "system_dependencies": sorted(system_dependencies, key=str.lower),
    }


def _parse_needed_libraries(output: str) -> list[str]:
    match = re.search(r"^NeededLibraries \[\r?\n(.*?)^\]$", output, re.MULTILINE | re.DOTALL)
    if match is None:
        raise BuildFrontendError("llvm-readobj output has no NeededLibraries block")
    return [line.strip() for line in match.group(1).splitlines() if line.strip()]


def _parse_elf_runtime_paths(output: str) -> list[str]:
    values: list[str] = []
    for match in re.finditer(
        r"\b(?:RUNPATH|RPATH)\s+Library r(?:un)?path:\s*\[([^]]*)\]",
        output,
    ):
        values.extend(part for part in match.group(1).split(":") if part)
    return values


def _approved_system_dependency(target: TargetProfile, name: str) -> bool:
    lowered = name.lower()
    if target.target_platform == "windows":
        return lowered in _WINDOWS_SYSTEM_NEEDED or re.fullmatch(
            r"api-ms-win-[a-z0-9-]+\.dll", lowered
        ) is not None
    return name in _LINUX_SYSTEM_NEEDED or re.fullmatch(
        r"ld-linux(?:-[a-z0-9_-]+)?\.so\.[0-9]+", name
    ) is not None


def _artifact_candidates(binary_dir: Path, target: TargetProfile, name: str) -> list[Path]:
    if target.target_platform == "windows":
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
    exports = set(
        re.findall(
            r"Export \{.*?^\s*Name:\s*(\S+)",
            result.stdout,
            re.MULTILINE | re.DOTALL,
        )
    )
    if exports != {"art_compiler_jit_create"}:
        raise BuildFrontendError(
            "art-compiler.dll exports differ from the exact allowlist: "
            + ", ".join(sorted(exports))
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
    tools["clang"] = validate_managed_path(clang)
    tools["clang++"] = validate_managed_path(clangxx)
    if tools["clang"].name not in ("clang", "clang.exe"):
        raise BuildFrontendError(f"plain Clang driver required: {tools['clang']}")
    if tools["clang++"].name not in ("clang++", "clang++.exe"):
        raise BuildFrontendError(f"plain Clang++ driver required: {tools['clang++']}")
    return tools


def _resolve_llvm_resource_compiler(local: LocalBuildConfig) -> Path:
    """Resolve LLVM's native resource compiler for Windows target graphs."""
    executable = "llvm-rc.exe" if os.name == "nt" else "llvm-rc"
    llvm_root = local.tools.get("llvm_root")
    path = llvm_root / "bin" / executable if llvm_root is not None else _discover(executable)
    resolved = validate_managed_path(path)
    if resolved.name not in ("llvm-rc", "llvm-rc.exe"):
        raise BuildFrontendError(
            f"LLVM resource compiler required; got {resolved.name!r}"
        )
    return resolved


def _resolve_llvm_inspection_tools(local: LocalBuildConfig) -> dict[str, Path]:
    """Resolve regular canonical LLVM object-inspection executables."""
    suffix = ".exe" if os.name == "nt" else ""
    llvm_root = local.tools.get("llvm_root")
    tools: dict[str, Path] = {}
    for name in ("llvm-readobj", "llvm-objdump"):
        executable = f"{name}{suffix}"
        candidate = llvm_root / "bin" / executable if llvm_root is not None else None
        if candidate is None or not candidate.is_file():
            candidate = _discover(executable).resolve()
        resolved = validate_managed_path(candidate)
        if resolved.name not in (name, f"{name}.exe"):
            raise BuildFrontendError(
                f"LLVM inspection tool {name} required; got {resolved.name!r}"
            )
        tools[name] = resolved
    return tools


def _resolve_llvm_pdbutil(local: LocalBuildConfig) -> Path:
    """Resolve LLVM's PDB reader for Windows private-symbol reviewers."""
    executable = "llvm-pdbutil.exe" if os.name == "nt" else "llvm-pdbutil"
    llvm_root = local.tools.get("llvm_root")
    path = llvm_root / "bin" / executable if llvm_root is not None else _discover(executable)
    resolved = validate_managed_path(path)
    if resolved.name not in ("llvm-pdbutil", "llvm-pdbutil.exe"):
        raise BuildFrontendError(
            f"LLVM PDB inspection tool required; got {resolved.name!r}"
        )
    return resolved


def _resolve_jdk(local: LocalBuildConfig) -> Path:
    root = local.tools.get("jdk_root")
    if root is None:
        raise BuildFrontendError(
            "JDK 21 is required; set tools.jdk_root in .art-build.local.toml"
        )
    root = validate_managed_path(root)
    suffix = ".exe" if os.name == "nt" else ""
    java = validate_managed_path(root / "bin" / f"java{suffix}")
    javac = validate_managed_path(root / "bin" / f"javac{suffix}")
    if java.name not in ("java", "java.exe") or javac.name not in ("javac", "javac.exe"):
        raise BuildFrontendError(f"plain JDK java/javac executables required below {root}")
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
            raise BuildFrontendError(
                f"JDK 21 {name} failed at {executable} with exit code {result.returncode}"
            )
    if re.search(r"\b(?:openjdk|java) version \"21(?:\.|\")", versions["java"]) is None:
        raise BuildFrontendError(
            f"JDK 21 java required at {root}; got {versions['java'] or 'no version output'}"
        )
    if re.search(r"\bjavac 21(?:\.|\s|$)", versions["javac"]) is None:
        raise BuildFrontendError(
            f"JDK 21 javac required at {root}; got {versions['javac'] or 'no version output'}"
        )
    return root


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
    target: TargetProfile,
    build_type: str,
    variant: str,
    tools: dict[str, Path],
    generated_dir: Path,
    bindings: dict[str, Path],
) -> dict[str, object]:
    return {
        "schema_version": 2,
        "build_host": {
            "os": platform.system().lower(),
            "arch": _canonical_host_arch(platform.machine()),
            "python_version": platform.python_version(),
        },
        "target": target.to_dict(),
        "build_type": build_type,
        "build_variant": variant,
        "generated_graph": _generated_graph_identity(generated_dir, target),
        "tools": _tool_identities(tools),
        "target_bindings": _target_binding_identities(bindings),
    }


def _generated_graph_identity(
    generated_dir: Path, target: TargetProfile
) -> dict[str, object]:
    graph = generated_dir / "art_graph.cmake"
    manifest_path = generated_dir / "graph_manifest.json"
    profile_path = generated_dir / "target_profile.cmake"
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BuildFrontendError(
            f"cannot fingerprint generated graph manifest {manifest_path}: {exc}"
        ) from exc
    if manifest.get("target") != target.to_dict():
        raise BuildFrontendError(
            f"generated graph target does not match profile {target.target_id}"
        )
    graph_sha256 = manifest.get("graph_sha256")
    if not isinstance(graph_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", graph_sha256) is None:
        raise BuildFrontendError("generated graph manifest has no valid graph_sha256")
    actual_graph_sha256 = _sha256_file(graph)
    if actual_graph_sha256 != graph_sha256:
        raise BuildFrontendError(
            f"generated graph digest mismatch: manifest has {graph_sha256}, "
            f"file has {actual_graph_sha256}"
        )
    return {
        "graph_sha256": graph_sha256,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "profile_sha256": _sha256_file(profile_path),
    }


_TOOL_VERSION_ARGUMENTS = {
    "java": ("-version",),
    "javac": ("-version",),
    # llvm-rc deliberately has no version flag. Its official help banner plus
    # the sibling LLVM tool versions still make this executable identity
    # reviewable without invoking a shell or compiling a probe resource.
    "llvm-rc": ("/?",),
}


def _tool_identities(tools: dict[str, Path]) -> dict[str, object]:
    identities: dict[str, object] = {}
    for name, path in sorted(tools.items()):
        arguments = _TOOL_VERSION_ARGUMENTS.get(name, ("--version",))
        command = [str(path), *arguments]
        try:
            result = subprocess.run(
                command,
                cwd=REPO_ROOT,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            raise BuildFrontendError(
                f"cannot query {name} version at {path}: {exc}"
            ) from exc
        output = (result.stdout + result.stderr).replace("\r\n", "\n").strip()
        if result.returncode or not output:
            raise BuildFrontendError(
                f"{name} version query failed at {path} with exit code "
                f"{result.returncode}: {output or 'no output'}"
            )
        identities[name] = {
            "path": str(path),
            "version_command": list(arguments),
            "version_output": output,
        }
    return identities


def _target_binding_identities(
    bindings: dict[str, Path],
) -> dict[str, object]:
    identities: dict[str, object] = {}
    for name, path in sorted(bindings.items()):
        print(f"fingerprinting target binding {name}: {path}")
        identities[name] = {
            "path": str(path),
            **_regular_tree_identity(path),
        }
    return identities


def _regular_tree_identity(root: Path) -> dict[str, object]:
    root = validate_managed_path(root)
    if not root.is_dir():
        raise BuildFrontendError(f"target binding must be a directory: {root}")
    digest = hashlib.sha256()
    file_count = 0
    directory_count = 0
    total_bytes = 0

    def visit(directory: Path, relative: Path) -> None:
        nonlocal file_count, directory_count, total_bytes
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as exc:
            raise BuildFrontendError(
                f"cannot scan target binding directory {directory}: {exc}"
            ) from exc
        for entry in entries:
            entry_path = Path(entry.path)
            entry_relative = relative / entry.name
            normalized = entry_relative.as_posix().encode("utf-8")
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise BuildFrontendError(
                    f"cannot stat target binding entry {entry_path}: {exc}"
                ) from exc
            file_attributes = getattr(metadata, "st_file_attributes", 0)
            if entry.is_symlink() or file_attributes & 0x400:
                raise BuildFrontendError(
                    f"target binding contains a link/reparse entry: {entry_path}"
                )
            if stat.S_ISDIR(metadata.st_mode):
                directory_count += 1
                digest.update(b"D\0" + normalized + b"\0")
                visit(entry_path, entry_relative)
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise BuildFrontendError(
                    f"target binding contains a non-regular entry: {entry_path}"
                )
            file_count += 1
            total_bytes += metadata.st_size
            digest.update(
                b"F\0"
                + normalized
                + b"\0"
                + str(metadata.st_size).encode("ascii")
                + b"\0"
            )
            try:
                with entry_path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
            except OSError as exc:
                raise BuildFrontendError(
                    f"cannot hash target binding file {entry_path}: {exc}"
                ) from exc
            digest.update(b"\0")

    visit(root, Path())
    return {
        "tree_sha256": digest.hexdigest(),
        "file_count": file_count,
        "directory_count": directory_count,
        "total_bytes": total_bytes,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise BuildFrontendError(f"cannot hash {path}: {exc}") from exc
    return digest.hexdigest()


def _guard_binary_directory(
    binary_dir: Path, manifest_path: Path, expected: dict[str, object]
) -> None:
    if manifest_path.exists():
        try:
            current = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BuildFrontendError(f"cannot read build manifest: {exc}") from exc
        if _immutable_build_fingerprint(current) != _immutable_build_fingerprint(
            expected
        ):
            raise BuildFrontendError(
                f"build fingerprint changed for {binary_dir}; use a fresh output root "
                "or remove this ignored binary directory explicitly"
            )
    elif (binary_dir / "CMakeCache.txt").exists():
        raise BuildFrontendError(
            f"refusing unowned existing CMake cache without build manifest: {binary_dir}"
        )


def _immutable_build_fingerprint(
    fingerprint: dict[str, object],
) -> dict[str, object]:
    """Return the cache identity while excluding regenerated graph content.

    Blueprint and overlay changes are expected to regenerate the target graph
    and reconfigure the existing Ninja tree.  Build-host, target, build-type,
    tool, target-binding, and configure-command changes still require a fresh
    binary directory.
    """
    return {
        key: value
        for key, value in fingerprint.items()
        if key != "generated_graph"
    }


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
    llvm_root = clang.parent.parent
    validate_managed_path(llvm_root / "bin" / ("clang.exe" if os.name == "nt" else "clang"))
    validate_managed_path(
        llvm_root / "bin" / ("clang++.exe" if os.name == "nt" else "clang++")
    )
    jdk_root = _discover_jdk21_root()
    content = (
        "# Machine-local paths only. This file is ignored by Git.\n"
        "[tools]\n"
        f"cmake = {json.dumps(str(cmake))}\n"
        f"ninja = {json.dumps(str(ninja))}\n"
        f"llvm_root = {json.dumps(str(llvm_root))}\n"
        f"jdk_root = {json.dumps(str(jdk_root))}\n"
    )
    _write_text_atomic(path, content)
    print(f"created {path}")
    return 0


def _discover_jdk21_root() -> Path:
    candidates: list[Path] = []
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidates.append(Path(java_home))
    javac_name = "javac.exe" if os.name == "nt" else "javac"
    discovered = shutil.which(javac_name)
    if discovered:
        candidates.append(Path(discovered).resolve().parent.parent)
    if os.name == "nt":
        for variable in ("ProgramW6432", "ProgramFiles"):
            program_files = os.environ.get(variable)
            if program_files:
                candidates.extend(sorted((Path(program_files) / "Java").glob("jdk-21*")))
        candidates.extend((Path("C:/Java/jdk-21"), Path("C:/JDK/jdk-21")))
    else:
        candidates.extend(sorted(Path("/usr/lib/jvm").glob("*21*")))

    seen: set[str] = set()
    for candidate in candidates:
        key = os.path.normcase(str(candidate))
        if key in seen:
            continue
        seen.add(key)
        try:
            local = LocalBuildConfig(tools={"jdk_root": candidate})
            return _resolve_jdk(local)
        except (BuildFrontendError, LocalConfigError, OSError):
            continue
    raise BuildFrontendError(
        "cannot discover a regular-file JDK 21; install an official JDK in a "
        "space-free path or create .art-build.local.toml manually"
    )


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
