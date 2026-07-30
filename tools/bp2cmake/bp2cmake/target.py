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


@dataclass(frozen=True)
class TargetProfile:
    target_id: str
    os_or_runtime: str
    cpu_arch: str
    aosp_arch: str
    abi: str
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
        if self.os_or_runtime == "linux":
            return "linux_glibc"
        if self.os_or_runtime == "windows":
            return "windows"
        return self.os_or_runtime

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
            ("ART_TARGET_OS_OR_RUNTIME", self.os_or_runtime),
            ("ART_TARGET_CPU_ARCH", self.cpu_arch),
            ("ART_TARGET_AOSP_ARCH", self.aosp_arch),
            ("ART_TARGET_ABI", self.abi),
            ("ART_TARGET_OBJECT_FORMAT", self.object_format),
            ("ART_TARGET_POINTER_BITS", str(self.pointer_bits)),
            ("ART_TARGET_ENDIANNESS", self.endianness),
            ("ART_TARGET_TRIPLE", self.target_triple),
            ("ART_TARGET_CMAKE_SYSTEM_NAME", self.cmake_system_name),
            ("ART_TARGET_CMAKE_SYSTEM_PROCESSOR", self.cmake_system_processor),
            ("ART_TARGET_CAPABILITIES", ";".join(self.capabilities)),
            ("ART_TARGET_SUPPORT_STATUS", self.support_status),
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


def _profile(
    target_id: str,
    os_or_runtime: str,
    cpu_arch: str,
    aosp_arch: str,
    abi: str,
    object_format: str,
    pointer_bits: int,
    triple: str,
    cmake_system_name: str,
    *,
    status: str,
    capabilities: tuple[str, ...] = (),
    reason: str = "",
) -> TargetProfile:
    return TargetProfile(
        target_id=target_id,
        os_or_runtime=os_or_runtime,
        cpu_arch=cpu_arch,
        aosp_arch=aosp_arch,
        abi=abi,
        object_format=object_format,
        pointer_bits=pointer_bits,
        endianness="little",
        target_triple=triple,
        cmake_system_name=cmake_system_name,
        cmake_system_processor=cpu_arch,
        capabilities=tuple(sorted(capabilities)),
        support_status=status,
        unavailable_reason=reason,
    )


_PROFILES = {
    "linux-x86_64": _profile(
        "linux-x86_64", "linux", "x86_64", "x86_64", "gnu",
        "elf64", 64, "x86_64-unknown-linux-gnu", "Linux",
        status="supported", capabilities=_NATIVE_CAPABILITIES + ("signals", "jit"),
    ),
    "linux-aarch64": _profile(
        "linux-aarch64", "linux", "aarch64", "arm64", "gnu",
        "elf64", 64, "aarch64-unknown-linux-gnu", "Linux",
        status="planned", reason="architecture-specific graph/codegen is not validated",
    ),
    "linux-x86": _profile(
        "linux-x86", "linux", "x86", "x86", "gnu",
        "elf32", 32, "i686-unknown-linux-gnu", "Linux",
        status="planned", reason="32-bit dependency and runtime gates are not validated",
    ),
    "linux-armv7": _profile(
        "linux-armv7", "linux", "armv7", "arm", "gnueabihf",
        "elf32", 32, "armv7-unknown-linux-gnueabihf", "Linux",
        status="planned", reason="ARMv7 hard-float dependency and runtime gates are not validated",
    ),
    "linux-riscv64": _profile(
        "linux-riscv64", "linux", "riscv64", "riscv64", "gnu",
        "elf64", 64, "riscv64-unknown-linux-gnu", "Linux",
        status="planned", reason="RISC-V mterp and dependency policy are not validated",
    ),
    "windows-x86_64": _profile(
        "windows-x86_64", "windows", "x86_64", "x86_64", "msvc",
        "pe32+", 64, "x86_64-pc-windows-msvc", "Windows",
        status="experimental",
        capabilities=_NATIVE_CAPABILITIES + ("seh", "jit", "windows_contracts"),
    ),
    "windows-aarch64": _profile(
        "windows-aarch64", "windows", "aarch64", "arm64", "msvc-arm64",
        "pe32+", 64, "aarch64-pc-windows-msvc", "Windows",
        status="planned", reason="Windows AArch64 sources and ABI gates are not implemented",
    ),
    "windows-aarch64-arm64ec": _profile(
        "windows-aarch64-arm64ec", "windows", "aarch64", "arm64", "arm64ec",
        "pe32+", 64, "arm64ec-pc-windows-msvc", "Windows",
        status="planned", reason="ARM64EC ABI and hybrid import/export gates are not implemented",
    ),
    "windows-x86": _profile(
        "windows-x86", "windows", "x86", "x86", "msvc",
        "pe32", 32, "i686-pc-windows-msvc", "Windows",
        status="planned", reason="Windows x86 is a registry placeholder",
    ),
    "wasi-wasm32": _profile(
        "wasi-wasm32", "wasi", "wasm32", "wasm32", "wasi",
        "wasm", 32, "wasm32-wasi", "WASI",
        status="impossible_under_current_art_contract",
        reason="ART requires native DSO, executable-memory, signal/fault, and JIT contracts",
    ),
    "wasi-wasm64": _profile(
        "wasi-wasm64", "wasi", "wasm64", "wasm64", "wasi-memory64",
        "wasm", 64, "wasm64-wasi", "WASI",
        status="impossible_under_current_art_contract",
        reason="ART requires native DSO, executable-memory, signal/fault, and JIT contracts",
    ),
}

TARGET_PROFILES: Mapping[str, TargetProfile] = MappingProxyType(_PROFILES)

_NON_CANONICAL_HINTS = {
    "linux-x64": "linux-x86_64",
    "linux_x86_64": "linux-x86_64",
    "linux-arm64": "linux-aarch64",
    "linux-arm": "linux-armv7",
    "windows-x64": "windows-x86_64",
    "windows_x86_64": "windows-x86_64",
    "windows-arm64": "windows-aarch64",
    "windows-arm64ec": "windows-aarch64-arm64ec",
    "wasm32-wasi": "wasi-wasm32",
    "wasm64-wasi": "wasi-wasm64",
}


def resolve_target(target_id: str) -> TargetProfile:
    try:
        return TARGET_PROFILES[target_id]
    except KeyError:
        hint = _NON_CANONICAL_HINTS.get(target_id)
        if hint:
            raise UnknownTargetError(
                f"non-canonical target ID {target_id!r}; use {hint!r}"
            ) from None
        known = ", ".join(TARGET_PROFILES)
        raise UnknownTargetError(
            f"unknown target ID {target_id!r}; registered targets: {known}"
        ) from None


def _cmake_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
