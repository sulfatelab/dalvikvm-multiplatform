import pytest

from bp2cmake.config import Config
from bp2cmake.target import (
    TARGET_ABIS,
    TARGET_ARCHES,
    TARGET_PLATFORMS,
    TARGET_PROFILES,
    TargetUnavailableError,
    UnknownTargetError,
    resolve_target,
)


def test_identity_enums_are_closed_and_complete():
    assert TARGET_PLATFORMS == ("linux", "windows", "wasm", "uefi")
    assert TARGET_ARCHES == (
        "x86",
        "x86_64",
        "armv7",
        "aarch64",
        "riscv64",
        "arm64ec",
        "wasm32",
        "wasm64",
    )
    assert TARGET_ABIS == ("gnu", "msvc", "posixshim")


def test_registry_contains_all_fifteen_canonical_ids():
    expected = {
        "linux-x86-gnu",
        "linux-x86_64-gnu",
        "linux-armv7-gnu",
        "linux-aarch64-gnu",
        "linux-riscv64-gnu",
        "windows-x86-msvc",
        "windows-x86_64-msvc",
        "windows-armv7-msvc",
        "windows-aarch64-msvc",
        "windows-arm64ec-msvc",
        "wasm-wasm32-posixshim",
        "wasm-wasm64-posixshim",
        "uefi-x86_64-posixshim",
        "uefi-aarch64-posixshim",
        "uefi-riscv64-posixshim",
    }
    assert set(TARGET_PROFILES) == expected
    assert len(TARGET_PROFILES) == 15


def test_registry_owns_exact_llvm_file_identities():
    expected = {
        "linux-x86-gnu": ("elf32-i386", "i386", 32),
        "linux-x86_64-gnu": ("elf64-x86-64", "x86_64", 64),
        "linux-armv7-gnu": ("elf32-littlearm", "arm", 32),
        "linux-aarch64-gnu": ("elf64-littleaarch64", "aarch64", 64),
        "linux-riscv64-gnu": ("elf64-littleriscv", "riscv64", 64),
        "windows-x86-msvc": ("COFF-i386", "i386", 32),
        "windows-x86_64-msvc": ("COFF-x86-64", "x86_64", 64),
        "windows-armv7-msvc": ("COFF-ARM", "thumb", 32),
        "windows-aarch64-msvc": ("COFF-ARM64", "aarch64", 64),
        "windows-arm64ec-msvc": ("COFF-ARM64EC", "aarch64", 64),
        "wasm-wasm32-posixshim": ("WASM", "wasm32", 32),
        "wasm-wasm64-posixshim": ("WASM", "wasm64", 64),
        "uefi-x86_64-posixshim": ("COFF-x86-64", "x86_64", 64),
        "uefi-aarch64-posixshim": ("COFF-ARM64", "aarch64", 64),
        "uefi-riscv64-posixshim": ("elf64-littleriscv", "riscv64", 64),
    }
    assert {
        target_id: (
            profile.llvm_file_format,
            profile.llvm_arch,
            profile.pointer_bits,
        )
        for target_id, profile in TARGET_PROFILES.items()
    } == expected


@pytest.mark.parametrize(
    ("bad", "replacement"),
    [
        ("linux-x64", "linux-x86_64-gnu"),
        ("linux-x86_64", "linux-x86_64-gnu"),
        ("linux-arm", "linux-armv7-gnu"),
        ("windows-x86_64", "windows-x86_64-msvc"),
        ("windows-aarch64-arm64ec", "windows-arm64ec-msvc"),
        ("wasm64-posixshim", "wasm-wasm64-posixshim"),
        ("uefi-riscv64", "uefi-riscv64-posixshim"),
    ],
)
def test_noncanonical_ids_are_rejected_with_hint(bad, replacement):
    with pytest.raises(UnknownTargetError, match=replacement):
        resolve_target(bad)


def test_suffixless_windows_arm64ec_has_only_msvc_replacement():
    with pytest.raises(UnknownTargetError, match="windows-arm64ec-msvc"):
        resolve_target("windows-arm64ec")


def test_aosp_arch_is_distinct_from_canonical_target_arch():
    target = resolve_target("linux-aarch64-gnu")
    assert target.target_platform == "linux"
    assert target.target_arch == "aarch64"
    assert target.base_isa == "aarch64"
    assert target.aosp_arch == "arm64"
    assert target.mterp_source_dir == "arm64ng"
    assert target.mterp_output == "mterp_arm64.S"
    assert target.target_abi == "gnu"
    config = Config.from_target(target)
    assert config.arch == "arm64"
    assert config.bitness == 64


def test_arm64ec_is_a_distinct_target_arch_with_aarch64_base_isa():
    target = resolve_target("windows-arm64ec-msvc")
    assert target.target_arch == "arm64ec"
    assert target.base_isa == "aarch64"
    assert target.aosp_arch == "arm64"
    assert target.mterp_source_dir == "arm64ng"
    assert target.mterp_output == "mterp_arm64.S"


def test_riscv_mterp_layout_is_explicit_and_has_no_ng_suffix():
    target = resolve_target("linux-riscv64-gnu")
    assert target.mterp_source_dir == "riscv64"
    assert target.mterp_output == "mterp_riscv64.S"


def test_planned_target_fails_before_generation():
    with pytest.raises(TargetUnavailableError, match="dependency"):
        resolve_target("linux-riscv64-gnu").require_generation()


@pytest.mark.parametrize(
    "target_id",
    [
        "windows-x86-msvc",
        "windows-armv7-msvc",
    ],
)
def test_windows_x86_and_armv7_are_valid_but_unavailable_placeholders(target_id):
    target = resolve_target(target_id)
    assert target.support_status == "planned"
    with pytest.raises(TargetUnavailableError, match="near or far roadmap"):
        target.require_generation()


@pytest.mark.parametrize(
    "target_id",
    [
        "windows-x86-gnu",
        "windows-x86_64-gnu",
        "windows-armv7-gnu",
        "windows-aarch64-gnu",
        "windows-arm64ec-gnu",
    ],
)
def test_windows_gnu_targets_are_not_registered(target_id):
    with pytest.raises(UnknownTargetError):
        resolve_target(target_id)


@pytest.mark.parametrize(
    "target_id",
    [
        "wasm-wasm32-posixshim",
        "wasm-wasm64-posixshim",
        "uefi-x86_64-posixshim",
        "uefi-aarch64-posixshim",
        "uefi-riscv64-posixshim",
    ],
)
def test_posixshim_targets_remain_impossible_under_current_art_contract(
    target_id,
):
    target = resolve_target(target_id)
    assert target.target_abi == "posixshim"
    assert target.support_status == "impossible_under_current_art_contract"
    with pytest.raises(TargetUnavailableError):
        target.require_generation()


def test_uefi_riscv64_records_independent_coff_blocker():
    target = resolve_target("uefi-riscv64-posixshim")
    assert target.object_format == "pe32+"
    assert target.llvm_file_format == "elf64-littleriscv"
    assert "cannot currently emit RISC-V64 COFF" in target.unavailable_reason


def test_supported_and_experimental_targets_are_admitted():
    linux = resolve_target("linux-x86_64-gnu")
    linux.require_generation()
    assert "boot_image" in linux.capabilities
    linux_aarch64 = resolve_target("linux-aarch64-gnu")
    linux_aarch64.require_generation()
    assert linux_aarch64.support_status == "experimental"
    assert "boot_image" not in linux_aarch64.capabilities
    assert "boot_image" not in resolve_target("windows-x86_64-msvc").capabilities
    resolve_target("windows-x86_64-msvc").require_generation()


def test_cmake_projection_is_data_only_and_path_free():
    text = resolve_target("windows-x86_64-msvc").to_cmake()
    assert 'set(ART_TARGET_ID "windows-x86_64-msvc")' in text
    assert 'set(ART_TARGET_PLATFORM "windows")' in text
    assert 'set(ART_TARGET_ARCH "x86_64")' in text
    assert 'set(ART_TARGET_BASE_ISA "x86_64")' in text
    assert 'set(ART_TARGET_ABI "msvc")' in text
    assert 'set(ART_TARGET_AOSP_ARCH "x86_64")' in text
    assert 'set(ART_TARGET_MTERP_SOURCE_DIR "x86_64ng")' in text
    assert 'set(ART_TARGET_MTERP_OUTPUT "mterp_x86_64.S")' in text
    assert 'set(ART_TARGET_LLVM_FILE_FORMAT "COFF-x86-64")' in text
    assert 'set(ART_TARGET_LLVM_ARCH "x86_64")' in text
    assert "ART_TARGET_CPU_ARCH" not in text
    assert "ART_TARGET_OS_OR_RUNTIME" not in text
    assert "add_library" not in text
    assert "include(" not in text
    assert "/home/" not in text
    assert ":\\" not in text
