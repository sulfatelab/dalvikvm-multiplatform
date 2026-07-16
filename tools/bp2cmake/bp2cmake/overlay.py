"""Layer 2 — the port-policy overlay.

This module defines the *schema* for the overlay and the logic that applies it
to a Layer 1 module. The actual policy DATA (the decisions, with their rationale
in comments) lives outside the package, under //overlay, and is loaded at
runtime. Keeping schema and data apart means the data file reads as a reviewable
list of "here is what we deliberately changed vs AOSP, and why".

A faithful `.bp`->CMake translation is wrong for Linux (see project_scope.md
section 5). The overlay is where every deliberate Android->Linux deviation is
recorded:

  * library kind (cc_library is ambiguous; we pick shared/static here)
  * source substitutions / additions / removals
  * dependency rewrites (drop libdl_android, map libz->host zlib, ...)
  * compile-flag policy (drop -Werror, add -D_FILE_OFFSET_BITS=64, ...)
  * define overrides (force __GLIBC__, CMS GC, ...)
  * "do not build this" exclusions
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .model import Module


@dataclass
class ModulePolicy:
    """Per-module deliberate decisions. Every field should be justified by a
    comment in the overlay data file citing the Android-vs-Linux reason."""

    # Force the CMake library kind. None = let the module type decide.
    # "shared" | "static" | "executable"
    kind: str | None = None

    # Inline the sources + include dirs of whole_static_libs directly into this
    # target instead of building them as separate libraries. Matches what the
    # archive did for fmtlib-in-libbase.
    absorb_whole_static: bool = True

    # Source list edits (applied after Layer 1).
    add_srcs: list[str] = field(default_factory=list)
    remove_srcs: list[str] = field(default_factory=list)

    # Dependency edits, by AOSP module name (mapping to short names happens
    # later, in the emitter, via the global name map).
    add_shared_libs: list[str] = field(default_factory=list)
    remove_shared_libs: list[str] = field(default_factory=list)
    add_static_libs: list[str] = field(default_factory=list)
    remove_static_libs: list[str] = field(default_factory=list)

    # Flag / define edits.
    add_cflags: list[str] = field(default_factory=list)
    add_cppflags: list[str] = field(default_factory=list)
    add_conlyflags: list[str] = field(default_factory=list)
    add_ldflags: list[str] = field(default_factory=list)
    add_defines: list[str] = field(default_factory=list)        # all languages, PRIVATE
    add_public_defines: list[str] = field(default_factory=list)  # exported to consumers
    remove_cflags: list[str] = field(default_factory=list)

    # Language standard overrides. None = keep whatever Layer 1 resolved from
    # the .bp (cpp_std/c_std). Set to force a different standard on Linux.
    set_c_std: str | None = None
    set_cpp_std: str | None = None

    # Extra include dirs (rooted at the native source root), e.g. for non-AOSP
    # glue like native/jdwpheader.
    add_include_dirs: list[str] = field(default_factory=list)

    # Extra include dirs rooted at the PROJECT-OWNED compat root
    # (${MDVM_COMPAT_INCLUDE_DIR}), for vendored shim headers that replace
    # Android-only deps we don't have (e.g. gtest_prod.h's FRIEND_TEST). Kept
    # separate from the read-only AOSP source tree.
    add_compat_include_dirs: list[str] = field(default_factory=list)

    # Sources/includes produced by the Python codegen driver (bp2cmake/codegen.py),
    # staged under ${MDVM_GENSRC_DIR}. Used for generated outputs the emitter
    # cannot express as gensrcs custom-commands (mterp .S, asm_defines.h). Paths
    # are relative to ${MDVM_GENSRC_DIR}.
    add_gensrc_sources: list[str] = field(default_factory=list)
    add_gensrc_includes: list[str] = field(default_factory=list)

    # Do not emit this module at all.
    skip: bool = False

    # Override Layer 1 enabled=False (art_defaults target.windows).
    force_enabled: bool = False


@dataclass
class GlobalPolicy:
    """Cross-cutting decisions applied to every module."""

    # AOSP module name -> CMake target name. Anything not listed falls back to
    # strip_lib_prefix (libbase -> base, liblog -> log).
    name_map: dict[str, str] = field(default_factory=dict)

    # Modules that are NOT built from the AOSP tree but provided as host/system
    # libraries (imported targets in the build): the dependency-closure walk
    # skips them and the build supplies them. e.g. libz/libcap/liblz4.
    host_libs: list[str] = field(default_factory=list)

    # cflags removed from every target (host clang/glibc warns where the Android
    # toolchain does not -- see audit).
    drop_cflags: list[str] = field(default_factory=list)
    drop_cppflags: list[str] = field(default_factory=list)
    # Defines injected into EVERY ART module (bp_dir under art/). Models the
    # art.go load-hook cflags that aren't in any .bp: the stack-overflow gaps,
    # frame-size limit, compact-dex level, ART_TARGET[_LINUX], etc. -- needed by
    # the many art headers (instruction_set.h, compact_dex_level.h) that any art
    # TU may include, not just runtime.
    art_defines: list[str] = field(default_factory=list)
    # ldflags dropped from every target. Used for Android/APEX/host-test layout
    # flags that are wrong or pointless on our Linux install (audit 5.2).
    drop_ldflags: list[str] = field(default_factory=list)
    # Substring-matched ldflag drops (for flags with embedded paths like rpath).
    drop_ldflags_containing: list[str] = field(default_factory=list)

    strip_lib_prefix: bool = True


@dataclass
class Overlay:
    global_policy: GlobalPolicy = field(default_factory=GlobalPolicy)
    modules: dict[str, ModulePolicy] = field(default_factory=dict)

    def policy_for(self, name: str) -> ModulePolicy:
        return self.modules.get(name, ModulePolicy())

    def target_name(self, aosp_name: str) -> str:
        if aosp_name in self.global_policy.name_map:
            return self.global_policy.name_map[aosp_name]
        n = aosp_name
        if self.global_policy.strip_lib_prefix and n.startswith("lib") and len(n) > 3:
            n = n[3:]
        return n


def apply_module_policy(m: Module, pol: ModulePolicy, glob: GlobalPolicy) -> Module:
    """Return a copy-ish of `m` with the per-module + global policy applied.

    Mutates and returns `m` (callers pass freshly-resolved modules)."""
    if pol.force_enabled:
        m.enabled = True
    # source edits
    for s in pol.remove_srcs:
        while s in m.srcs:
            m.srcs.remove(s)
    m.srcs.extend(s for s in pol.add_srcs if s not in m.srcs)

    # dependency edits
    for lib in pol.remove_shared_libs:
        while lib in m.shared_libs:
            m.shared_libs.remove(lib)
    m.shared_libs.extend(l for l in pol.add_shared_libs if l not in m.shared_libs)
    for lib in pol.remove_static_libs:
        while lib in m.static_libs:
            m.static_libs.remove(lib)
    m.static_libs.extend(l for l in pol.add_static_libs if l not in m.static_libs)

    # flag edits (per-module adds, then global drops)
    m.cflags.extend(pol.add_cflags)
    m.cppflags.extend(pol.add_cppflags)
    m.conlyflags.extend(pol.add_conlyflags)
    m.ldflags.extend(pol.add_ldflags)
    if pol.set_c_std is not None:
        m.c_std = pol.set_c_std
    if pol.set_cpp_std is not None:
        m.cpp_std = pol.set_cpp_std
    for f in glob.drop_cflags:
        while f in m.cflags:
            m.cflags.remove(f)
    for f in glob.drop_cppflags:
        while f in m.cppflags:
            m.cppflags.remove(f)
    # ldflag drops (exact + substring), then de-dup preserving order.
    for f in glob.drop_ldflags:
        while f in m.ldflags:
            m.ldflags.remove(f)
    if glob.drop_ldflags_containing:
        m.ldflags = [f for f in m.ldflags
                     if not any(sub in f for sub in glob.drop_ldflags_containing)]
    seen: set[str] = set()
    deduped: list[str] = []
    for f in m.ldflags:
        if f not in seen:
            seen.add(f)
            deduped.append(f)
    m.ldflags = deduped

    return m


def load_overlay(path: str) -> Overlay:
    """Load an overlay data file. The file is executed as Python and must define
    a module-level `OVERLAY` of type Overlay."""
    namespace: dict = {
        "Overlay": Overlay,
        "GlobalPolicy": GlobalPolicy,
        "ModulePolicy": ModulePolicy,
    }
    with open(path) as f:
        code = compile(f.read(), path, "exec")
    exec(code, namespace)
    ov = namespace.get("OVERLAY")
    if not isinstance(ov, Overlay):
        raise ValueError(f"{path}: must define OVERLAY: Overlay")
    return ov
