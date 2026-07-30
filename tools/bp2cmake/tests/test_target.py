import pytest

from bp2cmake.config import Config
from bp2cmake.target import (
    TARGET_PROFILES,
    TargetUnavailableError,
    UnknownTargetError,
    resolve_target,
)


def test_registry_uses_canonical_ids():
    expected = {
        "linux-x86_64",
        "linux-aarch64",
        "linux-x86",
        "linux-armv7",
        "linux-riscv64",
        "windows-x86_64",
        "windows-aarch64",
        "windows-aarch64-arm64ec",
        "windows-x86",
        "wasi-wasm32",
        "wasi-wasm64",
    }
    assert set(TARGET_PROFILES) == expected


@pytest.mark.parametrize(
    ("bad", "replacement"),
    [
        ("linux-x64", "linux-x86_64"),
        ("linux-arm", "linux-armv7"),
        ("windows-arm64ec", "windows-aarch64-arm64ec"),
        ("wasm64-wasi", "wasi-wasm64"),
    ],
)
def test_noncanonical_ids_are_rejected_with_hint(bad, replacement):
    with pytest.raises(UnknownTargetError, match=replacement):
        resolve_target(bad)


def test_aosp_arch_is_distinct_from_canonical_cpu():
    target = resolve_target("linux-aarch64")
    assert target.cpu_arch == "aarch64"
    assert target.aosp_arch == "arm64"
    config = Config.from_target(target)
    assert config.arch == "arm64"
    assert config.bitness == 64


def test_planned_target_fails_before_generation():
    with pytest.raises(TargetUnavailableError, match="mterp"):
        resolve_target("linux-riscv64").require_generation()


def test_supported_and_experimental_targets_are_admitted():
    resolve_target("linux-x86_64").require_generation()
    resolve_target("windows-x86_64").require_generation()


def test_cmake_projection_is_data_only_and_path_free():
    text = resolve_target("windows-x86_64").to_cmake()
    assert 'set(ART_TARGET_ID "windows-x86_64")' in text
    assert 'set(ART_TARGET_CPU_ARCH "x86_64")' in text
    assert 'set(ART_TARGET_AOSP_ARCH "x86_64")' in text
    assert "add_library" not in text
    assert "include(" not in text
    assert "/home/" not in text
    assert ":\\" not in text
