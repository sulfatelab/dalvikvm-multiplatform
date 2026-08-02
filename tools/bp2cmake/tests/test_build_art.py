import json
from pathlib import Path
import subprocess

import pytest

from bp2cmake.local_config import LocalBuildConfig, LocalConfigError
from tools import build_art


def _configured_build(tmp_path: Path) -> Path:
    binary_dir = tmp_path / "out" / "windows-x86_64-msvc" / "RelWithDebInfo"
    binary_dir.mkdir(parents=True)
    (binary_dir / "CMakeCache.txt").write_text("cache\n", encoding="utf-8")
    (binary_dir / "build_manifest.json").write_text("{}\n", encoding="utf-8")
    tests_dir = binary_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "art_test_catalog.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "target_id": "windows-x86_64-msvc",
                "probes": [
                    {
                        "name": "win32_osr_unwind_probe",
                        "stage": "w002",
                        "execution": "target-runnable",
                        "applicable": True,
                        "ctest_registered": True,
                        "build_verified": False,
                        "runtime_verified": False,
                        "build_status": "pending",
                        "runtime_status": "pending",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return binary_dir


def test_stage_selector_builds_one_virtual_group_and_filters_ctest(
    tmp_path, monkeypatch
):
    binary_dir = _configured_build(tmp_path)
    tool_dir = tmp_path / "tools"
    tool_dir.mkdir()
    cmake = tool_dir / "cmake"
    ctest = tool_dir / "ctest"
    cmake.write_text("", encoding="utf-8")
    ctest.write_text("", encoding="utf-8")
    commands = []

    monkeypatch.setattr(
        build_art,
        "_resolve_tools",
        lambda _local, *, need_compiler: {"cmake": cmake, "ninja": tool_dir / "ninja"},
    )
    monkeypatch.setattr(
        build_art.subprocess,
        "run",
        lambda command, **_kwargs: commands.append(command),
    )

    build_art._test(
        binary_dir,
        LocalBuildConfig(),
        ["contract:jni"],
        ["w002", "w002"],
    )

    assert commands[0][-2:] == ["--target", "art-test-stage-w002"]
    assert commands[1][-2:] == [
        "--label-regex",
        "^(contract:jni|stage:w002)$",
    ]
    assert "--no-tests=error" in commands[1]
    assert len(commands) == 2
    catalog = json.loads(
        (binary_dir / "tests" / "art_test_catalog.json").read_text(encoding="utf-8")
    )
    assert catalog["probes"][0]["build_verified"] is True
    assert catalog["probes"][0]["runtime_verified"] is False


def test_stage_reload_preserves_catalog_regenerated_during_ninja_build(
    tmp_path, monkeypatch
):
    binary_dir = _configured_build(tmp_path)
    catalog_path = binary_dir / "tests" / "art_test_catalog.json"
    stale = json.loads(catalog_path.read_text(encoding="utf-8"))
    stale["probes"][0]["execution"] = "compile-only"
    stale["probes"][0]["ctest_registered"] = False
    catalog_path.write_text(json.dumps(stale) + "\n", encoding="utf-8")
    tool_dir = tmp_path / "tools"
    tool_dir.mkdir()
    cmake = tool_dir / "cmake"
    ctest = tool_dir / "ctest"
    cmake.write_text("", encoding="utf-8")
    ctest.write_text("", encoding="utf-8")
    commands = []

    monkeypatch.setattr(
        build_art,
        "_resolve_tools",
        lambda _local, *, need_compiler: {"cmake": cmake, "ninja": tool_dir / "ninja"},
    )

    def run(command):
        commands.append(command)
        if command[-2:] == ["--target", "art-test-stage-w002"]:
            refreshed = json.loads(catalog_path.read_text(encoding="utf-8"))
            refreshed["probes"][0]["execution"] = "target-runnable"
            refreshed["probes"][0]["ctest_registered"] = True
            catalog_path.write_text(json.dumps(refreshed) + "\n", encoding="utf-8")

    monkeypatch.setattr(build_art, "_run_checked", run)
    build_art._test(binary_dir, LocalBuildConfig(), [], ["w002"])

    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert catalog["probes"][0]["execution"] == "target-runnable"
    assert catalog["probes"][0]["ctest_registered"] is True
    assert catalog["probes"][0]["build_verified"] is True
    assert len(commands) == 2


def test_without_stage_builds_all_probes_and_records_runtime_status(
    tmp_path, monkeypatch
):
    binary_dir = _configured_build(tmp_path)
    tool_dir = tmp_path / "tools"
    tool_dir.mkdir()
    cmake = tool_dir / "cmake"
    ctest = tool_dir / "ctest"
    cmake.write_text("", encoding="utf-8")
    ctest.write_text("", encoding="utf-8")
    commands = []

    monkeypatch.setattr(
        build_art,
        "_resolve_tools",
        lambda _local, *, need_compiler: {"cmake": cmake, "ninja": tool_dir / "ninja"},
    )
    monkeypatch.setattr(build_art, "_run_checked", lambda command: commands.append(command))

    build_art._test(binary_dir, LocalBuildConfig(), [], [])

    assert commands[0][-2:] == ["--target", "art-tests"]
    assert commands[1][0] == str(ctest)
    assert "--label-regex" not in commands[1]
    catalog = json.loads(
        (binary_dir / "tests" / "art_test_catalog.json").read_text(encoding="utf-8")
    )
    assert catalog["probes"][0]["build_verified"] is True
    assert catalog["probes"][0]["runtime_verified"] is True
    assert catalog["probes"][0]["build_status"] == "verified"
    assert catalog["probes"][0]["runtime_status"] == "verified"


def test_test_command_forwards_parallel_limit(tmp_path, monkeypatch):
    binary_dir = _configured_build(tmp_path)
    tool_dir = tmp_path / "tools"
    tool_dir.mkdir()
    cmake = tool_dir / "cmake"
    ctest = tool_dir / "ctest"
    cmake.write_text("", encoding="utf-8")
    ctest.write_text("", encoding="utf-8")
    commands = []

    monkeypatch.setattr(
        build_art,
        "_resolve_tools",
        lambda _local, *, need_compiler: {"cmake": cmake, "ninja": tool_dir / "ninja"},
    )
    monkeypatch.setattr(build_art, "_run_checked", lambda command: commands.append(command))

    build_art._test(binary_dir, LocalBuildConfig(), [], [], 32)

    assert commands[0][-5:] == [
        str(binary_dir),
        "--parallel",
        "32",
        "--target",
        "art-tests",
    ]


def test_stage_selector_reports_zero_applicable_probes(tmp_path, monkeypatch):
    binary_dir = _configured_build(tmp_path)
    catalog_path = binary_dir / "tests" / "art_test_catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["target_id"] = "linux-x86_64-gnu"
    catalog["probes"][0]["applicable"] = False
    catalog["probes"][0]["ctest_registered"] = False
    catalog_path.write_text(json.dumps(catalog) + "\n", encoding="utf-8")
    commands = []
    monkeypatch.setattr(
        build_art,
        "_resolve_tools",
        lambda _local, *, need_compiler: commands.append("resolve")
        or {"cmake": tmp_path / "cmake"},
    )

    with pytest.raises(build_art.BuildFrontendError, match="zero applicable probes"):
        build_art._test(binary_dir, LocalBuildConfig(), [], ["w002"])
    assert commands == ["resolve"]


def test_stage_selector_distinguishes_compile_only_from_runnable(tmp_path, monkeypatch):
    binary_dir = _configured_build(tmp_path)
    catalog_path = binary_dir / "tests" / "art_test_catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["probes"][0]["execution"] = "compile-only"
    catalog["probes"][0]["ctest_registered"] = False
    catalog_path.write_text(json.dumps(catalog) + "\n", encoding="utf-8")
    tool_dir = tmp_path / "tools"
    tool_dir.mkdir()
    cmake = tool_dir / "cmake"
    cmake.write_text("", encoding="utf-8")
    commands = []
    monkeypatch.setattr(
        build_art,
        "_resolve_tools",
        lambda _local, *, need_compiler: {"cmake": cmake},
    )
    monkeypatch.setattr(build_art, "_run_checked", lambda command: commands.append(command))

    with pytest.raises(build_art.BuildFrontendError, match="zero registered runnable"):
        build_art._test(binary_dir, LocalBuildConfig(), [], ["w002"])
    assert commands[0][-2:] == ["--target", "art-test-stage-w002"]
    assert len(commands) == 1


@pytest.mark.parametrize("stage", ["W002", "w02", "phase1", "w002-extra"])
def test_stage_selector_rejects_noncanonical_names(stage):
    with pytest.raises(build_art.BuildFrontendError, match="canonical"):
        build_art._stage_label(stage)


def test_checked_subprocess_failure_is_frontend_error(monkeypatch):
    def fail(command, **_kwargs):
        raise subprocess.CalledProcessError(7, command)

    monkeypatch.setattr(build_art.subprocess, "run", fail)
    with pytest.raises(build_art.BuildFrontendError, match="cmake failed with exit code 7"):
        build_art._run_checked(["cmake", "--build", "out"])


def test_stage_copies_only_regular_product_files(tmp_path, monkeypatch):
    binary_dir = _configured_build(tmp_path)
    (binary_dir / "dalvikvm").write_bytes(b"vm")
    (binary_dir / "libart.so").write_bytes(b"art")
    (binary_dir / "libbase.so").write_bytes(b"base")
    boot = binary_dir / "tests" / "managed" / "boot.jar"
    boot.parent.mkdir(parents=True)
    boot.write_bytes(b"boot")
    monkeypatch.setattr(
        build_art,
        "_ninja_product_outputs",
        lambda *_args: [
            (binary_dir / "dalvikvm", "executable"),
            (binary_dir / "libart.so", "shared-library"),
            (binary_dir / "libbase.so", "shared-library"),
        ],
    )
    monkeypatch.setattr(
        build_art,
        "_validate_staged_topology",
        lambda *_args, **_kwargs: {
            "dependencies": {},
            "runtime_paths": {},
            "system_dependencies": [],
        },
    )

    build_art._stage(
        build_art.resolve_target("linux-x86_64-gnu"), binary_dir, LocalBuildConfig()
    )

    manifest = (binary_dir / "stage" / "stage_manifest.json").read_text(encoding="utf-8")
    assert (binary_dir / "stage" / "dalvikvm").read_bytes() == b"vm"
    assert (binary_dir / "stage" / "libart.so").read_bytes() == b"art"
    assert (binary_dir / "stage" / "libbase.so").read_bytes() == b"base"
    assert (binary_dir / "stage" / "runtime" / "boot.jar").read_bytes() == b"boot"
    assert (
        binary_dir
        / "stage"
        / "runtime"
        / "etc"
        / "security"
        / "security.properties"
    ).is_file()
    assert len(list((
        binary_dir / "stage" / "runtime" / "etc" / "security" / "cacerts"
    ).glob("*.*"))) >= 121
    assert '"schema_version": 2' in manifest
    assert '"target_id": "linux-x86_64-gnu"' in manifest


def test_ninja_product_inventory_ignores_stale_and_nested_outputs():
    target = build_art.resolve_target("windows-x86_64-msvc")
    output = """
art.dll: CXX_SHARED_LIBRARY_LINKER__art_RelWithDebInfo
art.lib: CXX_SHARED_LIBRARY_LINKER__art_RelWithDebInfo
libcrypto.dll: C_SHARED_LIBRARY_LINKER__crypto_RelWithDebInfo
dalvikvm.exe: CXX_EXECUTABLE_LINKER__dalvikvm_RelWithDebInfo
tests/probe.dll: CXX_SHARED_LIBRARY_LINKER__probe_RelWithDebInfo
crypto.dll: phony
"""
    assert build_art._parse_ninja_product_outputs(output, target) == [
        ("art.dll", "shared-library"),
        ("dalvikvm.exe", "executable"),
        ("libcrypto.dll", "shared-library"),
    ]


def test_object_inspection_parsers_keep_relative_origin_and_needed_libraries():
    output = """
NeededLibraries [
  libart.so
  libc.so.6
]
DynamicSection [
  0x1D RUNPATH Library runpath: [$ORIGIN:$ORIGIN/providers]
]
"""
    assert build_art._parse_needed_libraries(output) == ["libart.so", "libc.so.6"]
    assert build_art._parse_elf_runtime_paths(output) == [
        "$ORIGIN",
        "$ORIGIN/providers",
    ]


def test_staged_topology_rejects_absolute_linux_runpath(tmp_path, monkeypatch):
    stage = tmp_path / "stage"
    stage.mkdir()
    for name in ("libart-compiler.so", "libart.so"):
        (stage / name).write_bytes(b"ELF")
    tool = tmp_path / "llvm-readobj"
    tool.write_bytes(b"tool")
    monkeypatch.setattr(
        build_art,
        "_resolve_llvm_inspection_tools",
        lambda _local: {"llvm-readobj": tool},
    )

    def run(command, **_kwargs):
        name = Path(command[-1]).name
        needed = "  libart.so\n" if name == "libart-compiler.so" else ""
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=(
                f"NeededLibraries [\n{needed}]\n"
                "DynamicSection [\n"
                "  0x1D RUNPATH Library runpath: [/machine/build]\n"
                "]\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(build_art.subprocess, "run", run)
    with pytest.raises(build_art.BuildFrontendError, match="non-relocatable"):
        build_art._validate_staged_topology(
            stage,
            build_art.resolve_target("linux-x86_64-gnu"),
            LocalBuildConfig(),
            executable_names=set(),
        )


def test_windows_configure_uses_target_bundle_and_clang_target(tmp_path, monkeypatch):
    binary_dir = tmp_path / "out" / "windows-x86_64-msvc" / "RelWithDebInfo"
    bundle = tmp_path / "bundle"
    bundle.mkdir(parents=True)
    tools = {name: tmp_path / name for name in ("cmake", "ninja", "clang", "clang++")}
    for path in tools.values():
        path.write_bytes(b"")
    local = LocalBuildConfig(
        tools={"cmake": tools["cmake"], "ninja": tools["ninja"],
               "llvm_root": tmp_path},
        targets={"windows-x86_64-msvc": {"bundle_root": bundle}},
    )
    monkeypatch.setattr(
        build_art,
        "_resolve_tools",
        lambda _local, *, need_compiler: {
            "cmake": tools["cmake"], "ninja": tools["ninja"],
            "clang": tools["clang"], "clang++": tools["clang++"],
        },
    )
    llvm_rc = tmp_path / "llvm-rc"
    llvm_rc.write_bytes(b"")
    monkeypatch.setattr(
        build_art,
        "_resolve_llvm_resource_compiler",
        lambda _local: llvm_rc,
    )
    llvm_readobj = tmp_path / "llvm-readobj"
    llvm_objdump = tmp_path / "llvm-objdump"
    llvm_pdbutil = tmp_path / "llvm-pdbutil"
    llvm_readobj.write_bytes(b"")
    llvm_objdump.write_bytes(b"")
    llvm_pdbutil.write_bytes(b"")
    monkeypatch.setattr(
        build_art,
        "_resolve_llvm_inspection_tools",
        lambda _local: {
            "llvm-readobj": llvm_readobj,
            "llvm-objdump": llvm_objdump,
        },
    )
    monkeypatch.setattr(
        build_art,
        "_resolve_llvm_pdbutil",
        lambda _local: llvm_pdbutil,
    )
    jdk = tmp_path / "jdk-21"
    (jdk / "bin").mkdir(parents=True)
    monkeypatch.setattr(build_art, "_resolve_jdk", lambda _local: jdk)
    monkeypatch.setattr(
        build_art,
        "_build_fingerprint",
        lambda *_args: {"schema_version": 2},
    )
    commands = []
    monkeypatch.setattr(build_art, "_run_checked", lambda command: commands.append(command))

    build_art._configure(
        build_art.resolve_target("windows-x86_64-msvc"),
        "RelWithDebInfo",
        binary_dir,
        local,
    )

    assert "-G" in commands[0] and "Ninja" in commands[0]
    assert "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON" in commands[0]
    assert "-DCMAKE_SYSTEM_NAME=Windows" in commands[0]
    assert "-DCMAKE_CXX_COMPILER_TARGET=x86_64-pc-windows-msvc" in commands[0]
    assert f"-DCMAKE_RC_COMPILER={llvm_rc.as_posix()}" in commands[0]
    assert f"-DART_LLVM_READOBJ={llvm_readobj}" in commands[0]
    assert f"-DART_LLVM_OBJDUMP={llvm_objdump}" in commands[0]
    assert f"-DART_LLVM_PDBUTIL={llvm_pdbutil}" in commands[0]
    assert f"-DART_JDK_ROOT={jdk}" in commands[0]
    assert any(arg.startswith("-DART_TARGET_BUNDLE_ROOT=") for arg in commands[0])
    assert "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreadedDLL" in commands[0]
    assert "-DART_ENABLE_TARGET_RUNTIME_TESTS=OFF" in commands[0]
    assert "-DART_TEST_VARIANT=product" in commands[0]


def test_test_variant_has_distinct_output_and_cannot_be_staged(tmp_path):
    target = build_art.resolve_target("windows-x86_64-msvc")
    binary = build_art._binary_dir(
        tmp_path, target, "RelWithDebInfo", "win32-stack-high-water"
    )
    assert binary == (
        tmp_path
        / "windows-x86_64-msvc"
        / "RelWithDebInfo-win32-stack-high-water"
    )
    build_art._validate_build_variant(
        target, "win32-stack-high-water", "configure"
    )
    with pytest.raises(build_art.BuildFrontendError, match="cannot be staged"):
        build_art._validate_build_variant(
            target, "win32-stack-high-water", "stage"
        )
    with pytest.raises(build_art.BuildFrontendError, match="exact"):
        build_art._validate_build_variant(
            build_art.resolve_target("linux-x86_64-gnu"),
            "win32-stack-high-water",
            "configure",
        )

    frame_binary = build_art._binary_dir(
        tmp_path, target, "RelWithDebInfo", "win32-frame-attribution"
    )
    assert frame_binary == (
        tmp_path
        / "windows-x86_64-msvc"
        / "RelWithDebInfo-win32-frame-attribution"
    )
    build_art._validate_build_variant(
        target, "win32-frame-attribution", "configure"
    )
    with pytest.raises(build_art.BuildFrontendError, match="cannot be staged"):
        build_art._validate_build_variant(
            target, "win32-frame-attribution", "stage"
        )


def test_resolve_tools_rejects_clangxx_symlink(tmp_path):
    tool_dir = tmp_path / "llvm" / "bin"
    tool_dir.mkdir(parents=True)
    clang = tool_dir / "clang"
    clang.write_bytes(b"")
    try:
        (tool_dir / "clang++").symlink_to(clang.name)
    except OSError:
        pytest.skip("host cannot create a compiler symlink")
    cmake = tmp_path / "cmake"
    ninja = tmp_path / "ninja"
    cmake.write_bytes(b"")
    ninja.write_bytes(b"")
    local = LocalBuildConfig(
        tools={"cmake": cmake, "ninja": ninja, "llvm_root": tool_dir.parent}
    )

    with pytest.raises(LocalConfigError, match="link/reparse component"):
        build_art._resolve_tools(local, need_compiler=True)


def test_resolve_jdk_requires_regular_jdk21_tools(tmp_path, monkeypatch):
    jdk = tmp_path / "jdk-21"
    binary = jdk / "bin"
    binary.mkdir(parents=True)
    (binary / "java").write_bytes(b"")
    (binary / "javac").write_bytes(b"")
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        version = (
            'openjdk version "21.0.11"\n'
            if Path(command[0]).name == "java"
            else "javac 21.0.11\n"
        )
        return subprocess.CompletedProcess(command, 0, stdout=version, stderr="")

    monkeypatch.setattr(build_art.subprocess, "run", run)
    resolved = build_art._resolve_jdk(LocalBuildConfig(tools={"jdk_root": jdk}))

    assert resolved == jdk
    assert calls[0][0] == [str(binary / "java"), "-version"]
    assert calls[1][0] == [str(binary / "javac"), "-version"]
    assert calls[0][1]["shell"] is False


def test_resolve_jdk_rejects_wrong_major(tmp_path, monkeypatch):
    jdk = tmp_path / "jdk-25"
    binary = jdk / "bin"
    binary.mkdir(parents=True)
    (binary / "java").write_bytes(b"")
    (binary / "javac").write_bytes(b"")
    monkeypatch.setattr(
        build_art.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout=(
                'openjdk version "25.0.3"\n'
                if Path(command[0]).name == "java"
                else "javac 25.0.3\n"
            ),
            stderr="",
        ),
    )

    with pytest.raises(build_art.BuildFrontendError, match="JDK 21"):
        build_art._resolve_jdk(LocalBuildConfig(tools={"jdk_root": jdk}))


@pytest.mark.parametrize(
    ("system", "machine", "target_id", "expected"),
    [
        ("Windows", "AMD64", "windows-x86_64-msvc", True),
        ("Windows", "ARM64", "windows-x86_64-msvc", False),
        ("Windows", "ARM64", "windows-arm64ec-msvc", True),
        ("Linux", "x86_64", "windows-x86_64-msvc", False),
        ("Linux", "x86_64", "linux-x86_64-gnu", True),
    ],
)
def test_runtime_tests_require_exact_native_host(
    monkeypatch, system, machine, target_id, expected
):
    monkeypatch.setattr(build_art.platform, "system", lambda: system)
    monkeypatch.setattr(build_art.platform, "machine", lambda: machine)
    assert build_art._host_can_run_target(build_art.resolve_target(target_id)) is expected


def test_build_fingerprint_records_resolved_profile_graph_tools_and_bindings(
    tmp_path, monkeypatch
):
    target = build_art.resolve_target("windows-x86_64-msvc")
    graph_identity = {
        "graph_sha256": "1" * 64,
        "manifest_sha256": "2" * 64,
        "profile_sha256": "3" * 64,
    }
    tool_identities = {
        "clang": {
            "path": str(tmp_path / "clang"),
            "version_command": ["--version"],
            "version_output": "clang version 21.1.8",
        }
    }
    binding_identities = {
        "bundle_root": {
            "path": str(tmp_path / "bundle"),
            "tree_sha256": "4" * 64,
            "file_count": 1,
            "directory_count": 0,
            "total_bytes": 4,
        }
    }
    monkeypatch.setattr(
        build_art, "_generated_graph_identity", lambda *_args: graph_identity
    )
    monkeypatch.setattr(build_art, "_tool_identities", lambda _tools: tool_identities)
    monkeypatch.setattr(
        build_art,
        "_target_binding_identities",
        lambda _bindings: binding_identities,
    )
    monkeypatch.setattr(build_art.platform, "system", lambda: "Windows")
    monkeypatch.setattr(build_art.platform, "machine", lambda: "AMD64")

    fingerprint = build_art._build_fingerprint(
        target,
        "RelWithDebInfo",
        "product",
        {"clang": tmp_path / "clang"},
        tmp_path / "generated",
        {"bundle_root": tmp_path / "bundle"},
    )

    assert fingerprint["schema_version"] == 2
    assert fingerprint["target"] == target.to_dict()
    assert fingerprint["generated_graph"] == graph_identity
    assert fingerprint["tools"] == tool_identities
    assert fingerprint["target_bindings"] == binding_identities
    assert fingerprint["build_host"]["os"] == "windows"
    assert fingerprint["build_host"]["arch"] == "x86_64"


def test_generated_graph_identity_checks_manifest_and_file_digest(tmp_path):
    target = build_art.resolve_target("linux-x86_64-gnu")
    generated = tmp_path / "generated"
    generated.mkdir()
    graph = generated / "art_graph.cmake"
    graph.write_text("add_library(art SHARED art.cc)\n", encoding="utf-8")
    profile = generated / "target_profile.cmake"
    profile.write_text(target.to_cmake(), encoding="utf-8")
    graph_sha256 = build_art._sha256_file(graph)
    manifest = {
        "schema_version": 2,
        "target": target.to_dict(),
        "graph_sha256": graph_sha256,
    }
    (generated / "graph_manifest.json").write_text(
        json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
    )

    identity = build_art._generated_graph_identity(generated, target)

    assert identity["graph_sha256"] == graph_sha256
    assert len(identity["manifest_sha256"]) == 64
    assert identity["profile_sha256"] == build_art._sha256_file(profile)
    graph.write_text("add_library(art STATIC art.cc)\n", encoding="utf-8")
    with pytest.raises(build_art.BuildFrontendError, match="digest mismatch"):
        build_art._generated_graph_identity(generated, target)


def test_tool_identities_capture_shell_free_version_output(tmp_path, monkeypatch):
    commands = []

    def run(command, **kwargs):
        commands.append((command, kwargs))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=("cmake version 4.2.3\r\n" if command[-1] == "--version" else ""),
            stderr=("openjdk version 21.0.11\r\n" if command[-1] == "-version" else ""),
        )

    monkeypatch.setattr(build_art.subprocess, "run", run)
    tools = {
        "cmake": tmp_path / "cmake",
        "java": tmp_path / "java",
    }

    identities = build_art._tool_identities(tools)

    assert identities["cmake"]["version_output"] == "cmake version 4.2.3"
    assert identities["java"]["version_output"] == "openjdk version 21.0.11"
    assert commands[0][1]["shell"] is False
    assert commands[0][1]["capture_output"] is True
    assert commands[1][0][-1] == "-version"


def test_regular_tree_identity_is_layout_and_content_sensitive(tmp_path):
    bundle = tmp_path / "bundle"
    include = bundle / "include"
    include.mkdir(parents=True)
    header = include / "runtime.h"
    header.write_bytes(b"ART1")
    (bundle / "empty").mkdir()

    first = build_art._regular_tree_identity(bundle)
    header.write_bytes(b"ART2")
    second = build_art._regular_tree_identity(bundle)

    assert first["file_count"] == 1
    assert first["directory_count"] == 2
    assert first["total_bytes"] == 4
    assert first["tree_sha256"] != second["tree_sha256"]


def test_regular_tree_identity_rejects_links(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    target = bundle / "target.h"
    target.write_bytes(b"header")
    link = bundle / "alias.h"
    try:
        link.symlink_to(target.name)
    except OSError:
        pytest.skip("host cannot create a test symlink")

    with pytest.raises(build_art.BuildFrontendError, match="link/reparse"):
        build_art._regular_tree_identity(bundle)
