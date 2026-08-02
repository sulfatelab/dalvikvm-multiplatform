"""Canonical ART target profiles shared by generation and build orchestration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Mapping


class TargetError(ValueError):
    """Base class for invalid or unavailable target profiles."""


class UnknownTargetError(TargetError):
    """Raised when a target ID is not present in the canonical registry."""


class TargetUnavailableError(TargetError):
    """Raised when a known target is not admitted to graph generation."""


# Closed identity enums. Adding a value requires an explicit design and registry
# change; callers must never infer or accept aliases for these fields.
TARGET_PLATFORMS = ("linux", "windows", "wasi")
TARGET_ARCHES = (
    "x86",
    "x86_64",
    "armv7",
    "aarch64",
    "riscv64",
    "arm64ec",
    "wasm32",
    "wasm64",
)
TARGET_ABIS = ("gnu", "msvc", "wasi")


@dataclass(frozen=True)
class TargetProfile:
    target_id: str
    target_platform: str
    target_arch: str
    base_isa: str
    aosp_arch: str
    target_abi: str
    object_format: str
    pointer_bits: int
    endianness: str
    target_triple: str
    cmake_system_name: str
    cmake_system_processor: str
    capabilities: tuple[str, ...]
    support_status: str
    unavailable_reason: str = ""

    @property
    def aosp_os(self) -> str:
        if self.target_platform == "linux":
            return "linux_glibc"
        if self.target_platform == "windows":
            return "windows"
        return self.target_platform

    @property
    def is_buildable(self) -> bool:
        return self.support_status in ("supported", "experimental")

    def require_generation(self) -> None:
        if self.is_buildable:
            return
        detail = self.unavailable_reason or "the target has not passed its capability gates"
        raise TargetUnavailableError(
            f"target {self.target_id!r} is {self.support_status}: {detail}"
        )

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["capabilities"] = list(self.capabilities)
        return data

    def to_cmake(self) -> str:
        """Return a path-free, data-only CMake target-profile projection."""
        values: tuple[tuple[str, str], ...] = (
            ("ART_TARGET_ID", self.target_id),
            ("ART_TARGET_PLATFORM", self.target_platform),
            ("ART_TARGET_ARCH", self.target_arch),
            ("ART_TARGET_BASE_ISA", self.base_isa),
            ("ART_TARGET_AOSP_ARCH", self.aosp_arch),
            ("ART_TARGET_ABI", self.target_abi),
            ("ART_TARGET_OBJECT_FORMAT", self.object_format),
            ("ART_TARGET_POINTER_BITS", str(self.pointer_bits)),
            ("ART_TARGET_ENDIANNESS", self.endianness),
            ("ART_TARGET_TRIPLE", self.target_triple),
            ("ART_TARGET_CMAKE_SYSTEM_NAME", self.cmake_system_name),
            ("ART_TARGET_CMAKE_SYSTEM_PROCESSOR", self.cmake_system_processor),
            ("ART_TARGET_CAPABILITIES", ";".join(self.capabilities)),
            ("ART_TARGET_SUPPORT_STATUS", self.support_status),
            ("ART_TARGET_ID_ENUM", ";".join(TARGET_PROFILES)),
            ("ART_TARGET_PLATFORM_ENUM", ";".join(TARGET_PLATFORMS)),
            ("ART_TARGET_ARCH_ENUM", ";".join(TARGET_ARCHES)),
            ("ART_TARGET_ABI_ENUM", ";".join(TARGET_ABIS)),
        )
        lines = ["# Generated target data. Do not edit."]
        lines.extend(f'set({key} "{_cmake_escape(value)}")' for key, value in values)
        return "\n".join(lines) + "\n"


_NATIVE_CAPABILITIES = (
    "native",
    "dso",
    "threads",
    "virtual_memory",
    "executable_memory",
    "dynamic_loading",
    "target_assembly",
)

_WINDOWS_PLACEHOLDER_REASON = (
    "recognized registry placeholder; implementation is not expected on the "
    "near or far roadmap"
)
_WINDOWS_GNU_REASON = (
    "the current product contract forbids MinGW and clang-mingw; no official "
    "regular-file GNU-ABI target bundle is defined"
)


def _profile(
    target_id: str,
    target_platform: str,
    target_arch: str,
    base_isa: str,
    aosp_arch: str,
    target_abi: str,
    object_format: str,
    pointer_bits: int,
    triple: str,
    cmake_system_name: str,
    *,
    status: str,
    capabilities: tuple[str, ...] = (),
    reason: str = "",
) -> TargetProfile:
    if target_platform not in TARGET_PLATFORMS:
        raise AssertionError(f"unregistered target platform: {target_platform}")
    if target_arch not in TARGET_ARCHES:
        raise AssertionError(f"unregistered target architecture: {target_arch}")
    if target_abi not in TARGET_ABIS:
        raise AssertionError(f"unregistered target ABI: {target_abi}")
    expected_id = f"{target_platform}-{target_arch}-{target_abi}"
    if target_id != expected_id:
        raise AssertionError(f"target ID {target_id!r} must be {expected_id!r}")
    return TargetProfile(
        target_id=target_id,
        target_platform=target_platform,
        target_arch=target_arch,
        base_isa=base_isa,
        aosp_arch=aosp_arch,
        target_abi=target_abi,
        object_format=object_format,
        pointer_bits=pointer_bits,
        endianness="little",
        target_triple=triple,
        cmake_system_name=cmake_system_name,
        cmake_system_processor=target_arch,
        capabilities=tuple(sorted(capabilities)),
        support_status=status,
        unavailable_reason=reason,
    )


_PROFILES = {
    "linux-x86-gnu": _profile(
        "linux-x86-gnu", "linux", "x86", "x86", "x86", "gnu",
        "elf32", 32, "i686-unknown-linux-gnu", "Linux",
        status="planned", reason="32-bit dependency and runtime gates are not validated",
    ),
    "linux-x86_64-gnu": _profile(
        "linux-x86_64-gnu", "linux", "x86_64", "x86_64", "x86_64", "gnu",
        "elf64", 64, "x86_64-unknown-linux-gnu", "Linux",
        status="supported",
        capabilities=_NATIVE_CAPABILITIES + ("boot_image", "signals", "jit"),
    ),
    "linux-armv7-gnu": _profile(
        "linux-armv7-gnu", "linux", "armv7", "armv7", "arm", "gnu",
        "elf32", 32, "armv7-unknown-linux-gnueabihf", "Linux",
        status="planned", reason="ARMv7 hard-float dependency and runtime gates are not validated",
    ),
    "linux-aarch64-gnu": _profile(
        "linux-aarch64-gnu", "linux", "aarch64", "aarch64", "arm64", "gnu",
        "elf64", 64, "aarch64-unknown-linux-gnu", "Linux",
        status="planned", reason="architecture-specific graph/codegen is not validated",
    ),
    "linux-riscv64-gnu": _profile(
        "linux-riscv64-gnu", "linux", "riscv64", "riscv64", "riscv64", "gnu",
        "elf64", 64, "riscv64-unknown-linux-gnu", "Linux",
        status="planned", reason="RISC-V mterp and dependency policy are not validated",
    ),
    "windows-x86-gnu": _profile(
        "windows-x86-gnu", "windows", "x86", "x86", "x86", "gnu",
        "pe32", 32, "i686-w64-windows-gnu", "Windows",
        status="planned", reason=f"{_WINDOWS_PLACEHOLDER_REASON}; {_WINDOWS_GNU_REASON}",
    ),
    "windows-x86-msvc": _profile(
        "windows-x86-msvc", "windows", "x86", "x86", "x86", "msvc",
        "pe32", 32, "i686-pc-windows-msvc", "Windows",
        status="planned", reason=_WINDOWS_PLACEHOLDER_REASON,
    ),
    "windows-x86_64-gnu": _profile(
        "windows-x86_64-gnu", "windows", "x86_64", "x86_64", "x86_64", "gnu",
        "pe32+", 64, "x86_64-w64-windows-gnu", "Windows",
        status="planned", reason=_WINDOWS_GNU_REASON,
    ),
    "windows-x86_64-msvc": _profile(
        "windows-x86_64-msvc", "windows", "x86_64", "x86_64", "x86_64", "msvc",
        "pe32+", 64, "x86_64-pc-windows-msvc", "Windows",
        status="experimental",
        capabilities=_NATIVE_CAPABILITIES + ("seh", "jit", "windows_contracts"),
    ),
    "windows-armv7-gnu": _profile(
        "windows-armv7-gnu", "windows", "armv7", "armv7", "arm", "gnu",
        "pe32", 32, "armv7-w64-windows-gnu", "Windows",
        status="planned", reason=f"{_WINDOWS_PLACEHOLDER_REASON}; {_WINDOWS_GNU_REASON}",
    ),
    "windows-armv7-msvc": _profile(
        "windows-armv7-msvc", "windows", "armv7", "armv7", "arm", "msvc",
        "pe32", 32, "armv7-pc-windows-msvc", "Windows",
        status="planned", reason=_WINDOWS_PLACEHOLDER_REASON,
    ),
    "windows-aarch64-gnu": _profile(
        "windows-aarch64-gnu", "windows", "aarch64", "aarch64", "arm64", "gnu",
        "pe32+", 64, "aarch64-w64-windows-gnu", "Windows",
        status="planned", reason=_WINDOWS_GNU_REASON,
    ),
    "windows-aarch64-msvc": _profile(
        "windows-aarch64-msvc", "windows", "aarch64", "aarch64", "arm64", "msvc",
        "pe32+", 64, "aarch64-pc-windows-msvc", "Windows",
        status="planned", reason="Windows AArch64 sources and ABI gates are not implemented",
    ),
    "windows-arm64ec-gnu": _profile(
        "windows-arm64ec-gnu", "windows", "arm64ec", "aarch64", "arm64", "gnu",
        "pe32+", 64, "arm64ec-w64-windows-gnu", "Windows",
        status="planned", reason=_WINDOWS_GNU_REASON,
    ),
    "windows-arm64ec-msvc": _profile(
        "windows-arm64ec-msvc", "windows", "arm64ec", "aarch64", "arm64", "msvc",
        "pe32+", 64, "arm64ec-pc-windows-msvc", "Windows",
        status="planned", reason="ARM64EC source, macro, import/export, and runtime gates are not implemented",
    ),
    "wasi-wasm32-wasi": _profile(
        "wasi-wasm32-wasi", "wasi", "wasm32", "wasm32", "wasm32", "wasi",
        "wasm", 32, "wasm32-wasi", "WASI",
        status="impossible_under_current_art_contract",
        reason="ART requires native DSO, executable-memory, signal/fault, and JIT contracts",
    ),
    "wasi-wasm64-wasi": _profile(
        "wasi-wasm64-wasi", "wasi", "wasm64", "wasm64", "wasm64", "wasi",
        "wasm", 64, "wasm64-wasi", "WASI",
        status="impossible_under_current_art_contract",
        reason="ART requires native DSO, executable-memory, signal/fault, and JIT contracts",
    ),
}

TARGET_PROFILES: Mapping[str, TargetProfile] = MappingProxyType(_PROFILES)

_NON_CANONICAL_HINTS: Mapping[str, tuple[str, ...]] = MappingProxyType({
    "linux-x64": ("linux-x86_64-gnu",),
    "linux_x86_64": ("linux-x86_64-gnu",),
    "linux-x86_64": ("linux-x86_64-gnu",),
    "linux-x86": ("linux-x86-gnu",),
    "linux-arm": ("linux-armv7-gnu",),
    "linux-armv7": ("linux-armv7-gnu",),
    "linux-arm64": ("linux-aarch64-gnu",),
    "linux-aarch64": ("linux-aarch64-gnu",),
    "linux-riscv64": ("linux-riscv64-gnu",),
    "windows-x64": ("windows-x86_64-msvc",),
    "windows_x86_64": ("windows-x86_64-msvc",),
    "windows-x86_64": ("windows-x86_64-msvc",),
    "windows-x86": ("windows-x86-msvc",),
    "windows-arm": ("windows-armv7-msvc",),
    "windows-armv7": ("windows-armv7-msvc",),
    "windows-arm64": ("windows-aarch64-msvc",),
    "windows-aarch64": ("windows-aarch64-msvc",),
    "windows-aarch64-arm64ec": ("windows-arm64ec-msvc",),
    "windows-arm64ec": ("windows-arm64ec-gnu", "windows-arm64ec-msvc"),
    "wasi-wasm32": ("wasi-wasm32-wasi",),
    "wasi-wasm64": ("wasi-wasm64-wasi",),
    "wasm32-wasi": ("wasi-wasm32-wasi",),
    "wasm64-wasi": ("wasi-wasm64-wasi",),
})


def resolve_target(target_id: str) -> TargetProfile:
    try:
        return TARGET_PROFILES[target_id]
    except KeyError:
        hints = _NON_CANONICAL_HINTS.get(target_id)
        if hints:
            if len(hints) == 1:
                detail = f"use {hints[0]!r}"
            else:
                detail = "use one of " + ", ".join(repr(hint) for hint in hints)
            raise UnknownTargetError(
                f"non-canonical target ID {target_id!r}; {detail}"
            ) from None
        known = ", ".join(TARGET_PROFILES)
        raise UnknownTargetError(
            f"unknown target ID {target_id!r}; registered targets: {known}"
        ) from None


def _cmake_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
