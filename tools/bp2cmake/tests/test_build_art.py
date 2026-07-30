from pathlib import Path
import subprocess

import pytest

from bp2cmake.local_config import LocalBuildConfig
from tools import build_art


def _configured_build(tmp_path: Path) -> Path:
    binary_dir = tmp_path / "out" / "windows-x86_64" / "RelWithDebInfo"
    binary_dir.mkdir(parents=True)
    (binary_dir / "CMakeCache.txt").write_text("cache\n", encoding="utf-8")
    (binary_dir / "build_manifest.json").write_text("{}\n", encoding="utf-8")
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
        build_art.resolve_target("linux-x86_64"), binary_dir, LocalBuildConfig()
    )

    manifest = (binary_dir / "stage" / "stage_manifest.json").read_text(encoding="utf-8")
    assert (binary_dir / "stage" / "dalvikvm").read_bytes() == b"vm"
    assert (binary_dir / "stage" / "libart.so").read_bytes() == b"art"
    assert (binary_dir / "stage" / "libbase.so").read_bytes() == b"base"
    assert '"target_id": "linux-x86_64"' in manifest


def test_windows_configure_uses_target_bundle_and_clang_target(tmp_path, monkeypatch):
    binary_dir = tmp_path / "out" / "windows-x86_64" / "RelWithDebInfo"
    bundle = tmp_path / "bundle"
    bundle.mkdir(parents=True)
    tools = {name: tmp_path / name for name in ("cmake", "ninja", "clang", "clang++")}
    for path in tools.values():
        path.write_bytes(b"")
    local = LocalBuildConfig(
        tools={"cmake": tools["cmake"], "ninja": tools["ninja"],
               "llvm_root": tmp_path},
        targets={"windows-x86_64": {"bundle_root": bundle}},
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
    commands = []
    monkeypatch.setattr(build_art, "_run_checked", lambda command: commands.append(command))

    build_art._configure(
        build_art.resolve_target("windows-x86_64"),
        "RelWithDebInfo",
        binary_dir,
        local,
    )

    assert "-G" in commands[0] and "Ninja" in commands[0]
    assert "-DCMAKE_SYSTEM_NAME=Windows" in commands[0]
    assert "-DCMAKE_CXX_COMPILER_TARGET=x86_64-pc-windows-msvc" in commands[0]
    assert f"-DCMAKE_RC_COMPILER={llvm_rc.as_posix()}" in commands[0]
    assert any(arg.startswith("-DART_TARGET_BUNDLE_ROOT=") for arg in commands[0])
    assert "-DART_ENABLE_TARGET_RUNTIME_TESTS=OFF" in commands[0]


@pytest.mark.parametrize(
    ("system", "machine", "target_id", "expected"),
    [
        ("Windows", "AMD64", "windows-x86_64", True),
        ("Windows", "ARM64", "windows-x86_64", False),
        ("Linux", "x86_64", "windows-x86_64", False),
        ("Linux", "x86_64", "linux-x86_64", True),
    ],
)
def test_runtime_tests_require_exact_native_host(
    monkeypatch, system, machine, target_id, expected
):
    monkeypatch.setattr(build_art.platform, "system", lambda: system)
    monkeypatch.setattr(build_art.platform, "machine", lambda: machine)
    assert build_art._host_can_run_target(build_art.resolve_target(target_id)) is expected
