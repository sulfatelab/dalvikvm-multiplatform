"""Build configuration that Layer 1 resolves `arch{}`/`target{}` selects against.

Default remains a glibc Linux host build. Windows is a first-class second OS
(`os="windows"`) used by the Win64 port (win32_port.md Phase 0+).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    # linux_glibc (default) | windows
    # musl deferred on Unix; windows is the Win64 PE target (x86_64-pc-windows-msvc).
    os: str = "linux_glibc"
    arch: str = "x86_64"       # x86_64 | x86 | arm64 | arm  (Win64 port: x86_64 only)
    bitness: int = 64           # 64 | 32
    host: bool = True

    # Whether to enable the AVX2 codegen/cflag sub-select. The archive's host
    # build assumed only sse4.2 (NOT avx2), so default off (audit 5.2 / art
    # CMakeLists notes).
    avx2: bool = False

    def soong_config_value(self, name: str) -> bool:
        # Soong config variables resolved to fixed values. ART gates its modules
        # behind `source_build` (art_defaults sets enabled:false unless this is
        # true); we always build ART from source. Everything else defaults off.
        return {"source_build": True}.get(name, False)

    def select_condition_value(self, func: str, args: list[str]):
        """Resolve a Soong select() condition to a concrete value.

          * os()                              -> host OS string for this Config
          * arch()                            -> the build arch
          * soong_config_variable(ns, var)    -> bool via soong_config_value(var)
                                                 (None when unset so it matches
                                                 only `default`, not `false`)
          * release_flag(name)                -> None (unset -> matches default)
          * boolean_var_for_testing() / other -> None (unset -> default)
        """
        if func == "os":
            # Soong uses "windows" / "linux_glibc" / "darwin" as os() values.
            return self.os
        if func == "arch":
            return self.arch
        if func == "soong_config_variable":
            var = args[-1] if args else ""
            if var in _SET_SOONG_CONFIG_VARS:
                return self.soong_config_value(var)
            return None
        return None

    @property
    def is_windows(self) -> bool:
        return self.os == "windows"

    @property
    def is_linux(self) -> bool:
        return self.os in ("linux_glibc", "linux_musl", "linux")

    @property
    def codegen_arches(self) -> list[str]:
        # Which ART code generators to compile in. art.go's default device
        # codegen enables both the 64-bit arch and its 32-bit sibling.
        return {
            "x86_64": ["x86_64", "x86"],
            "x86": ["x86"],
            "arm64": ["arm64", "arm"],
            "arm": ["arm"],
        }.get(self.arch, [self.arch])

    @property
    def active_target_keys(self) -> list[str]:
        """Soong `target:` keys that apply to this config.

        Anything NOT in this set is dropped during evaluation.
        """
        if self.is_windows:
            keys = [
                "host",
                "windows",
                "not_darwin",
                "not_fuchsia",
                # Windows builds are host_supported modules without not_windows.
            ]
            # Some modules use arch-combined windows keys rarely; include arch.
            keys.append(f"windows_{self.arch}")
            return keys

        keys = [
            "host",
            "host_linux",
            "linux",
            "linux_glibc",
            "glibc",
            "not_windows",
            "not_darwin",
            "not_fuchsia",
        ]
        keys.append(f"linux_{self.arch}")
        keys.append(f"linux_glibc_{self.arch}")
        keys.append(f"glibc_{self.arch}")
        return keys

    @property
    def multilib_key(self) -> str:
        return "lib64" if self.bitness == 64 else "lib32"


# Soong config variables we treat as explicitly SET.
_SET_SOONG_CONFIG_VARS: frozenset = frozenset()
