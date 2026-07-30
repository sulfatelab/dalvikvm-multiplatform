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
