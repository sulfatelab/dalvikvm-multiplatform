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


def test_stage_copies_only_regular_product_files(tmp_path):
    binary_dir = _configured_build(tmp_path)
    (binary_dir / "dalvikvm").write_bytes(b"vm")
    (binary_dir / "libart.so").write_bytes(b"art")
    (binary_dir / "libbase.so").write_bytes(b"base")

    build_art._stage(
        build_art.resolve_target("linux-x86_64-gnu"), binary_dir, LocalBuildConfig()
    )

    manifest = (binary_dir / "stage" / "stage_manifest.json").read_text(encoding="utf-8")
    assert (binary_dir / "stage" / "dalvikvm").read_bytes() == b"vm"
    assert (binary_dir / "stage" / "libart.so").read_bytes() == b"art"
    assert (binary_dir / "stage" / "libbase.so").read_bytes() == b"base"
    assert '"target_id": "linux-x86_64-gnu"' in manifest


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
    jdk = tmp_path / "jdk-21"
    (jdk / "bin").mkdir(parents=True)
    monkeypatch.setattr(build_art, "_resolve_jdk", lambda _local: jdk)
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
    assert f"-DART_JDK_ROOT={jdk}" in commands[0]
    assert any(arg.startswith("-DART_TARGET_BUNDLE_ROOT=") for arg in commands[0])
    assert "-DART_ENABLE_TARGET_RUNTIME_TESTS=OFF" in commands[0]


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
