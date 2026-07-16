"""Normalized module graph — the output of Layer 1, input to Layers 2 and 3.

A `Module` here is fully config-resolved: defaults expanded, variables
substituted, and `arch`/`target` selects collapsed into flat property lists for
the active glibc host config. It deliberately keeps only the properties the
CMake emitter cares about; Android-only metadata (apex, vndk, stubs, sanitize,
min_sdk_version, ...) is dropped during evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GenSrcs:
    """A resolved Soong `gensrcs` module: run `tool` over each input file to
    produce one output per input. Maps to CMake add_custom_command."""

    name: str
    bp_dir: str = ""
    tool: str = ""                 # referenced tool module name
    cmd: str = ""                  # Soong cmd template ($(location)/$(in)/$(out))
    srcs: list[str] = field(default_factory=list)
    output_extension: str = "out"
    root_var: str = "MDVM_NATIVE_SRC_ROOT_DIR"  # source-tree root for inputs


@dataclass
class Module:
    name: str
    type: str  # cc_library, cc_library_static, cc_binary, cc_defaults, ...
    # Source-relative directory the .bp lived in (for resolving src paths).
    bp_dir: str = ""
    # CMake variable naming the source tree this module's paths are relative to.
    # Defaults to the native source root; extra roots (libcore, ICU, ...) set
    # their own so the emitter prefixes paths correctly.
    root_var: str = "MDVM_NATIVE_SRC_ROOT_DIR"

    srcs: list[str] = field(default_factory=list)
    exclude_srcs: list[str] = field(default_factory=list)

    cflags: list[str] = field(default_factory=list)
    cppflags: list[str] = field(default_factory=list)
    conlyflags: list[str] = field(default_factory=list)
    ldflags: list[str] = field(default_factory=list)

    include_dirs: list[str] = field(default_factory=list)       # global (rooted)
    local_include_dirs: list[str] = field(default_factory=list)  # relative to bp_dir
    export_include_dirs: list[str] = field(default_factory=list)

    shared_libs: list[str] = field(default_factory=list)
    static_libs: list[str] = field(default_factory=list)
    whole_static_libs: list[str] = field(default_factory=list)
    header_libs: list[str] = field(default_factory=list)

    generated_sources: list[str] = field(default_factory=list)
    generated_headers: list[str] = field(default_factory=list)

    # Language standard overrides (Soong cpp_std / c_std), e.g. "c++2a", "c99".
    cpp_std: str | None = None
    c_std: str | None = None

    # Whether this module type produces a shared or static library by default.
    # cc_library is ambiguous (both); the overlay/emitter decides.
    enabled: bool = True

    # Raw leftover properties we did not model, kept for debugging/overlay use.
    extra: dict = field(default_factory=dict)

    def effective_srcs(self) -> list[str]:
        excluded = set(self.exclude_srcs)
        seen: set[str] = set()
        out: list[str] = []
        for s in self.srcs:
            if s in excluded or s in seen:
                continue
            seen.add(s)
            out.append(s)
        return out


@dataclass
class ModuleGraph:
    modules: dict[str, Module] = field(default_factory=dict)

    def add(self, m: Module) -> None:
        self.modules[m.name] = m

    def get(self, name: str) -> Module | None:
        return self.modules.get(name)
