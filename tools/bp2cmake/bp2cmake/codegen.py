"""Python codegen driver — replaces historical AOSP Gradle generation tasks.

AOSP ART historically generated headers/sources from Gradle
(generateArtOpCxxSrc, generateArtMterpAsmSrc, generateArtAsmHeader,
generateArtAsmDefinitions). This multipath tree drops Gradle; this module
reproduces those steps in Python, staging a `gensrc/` tree the generated CMake
consumes. Three kinds of generation:

  1. operator_out  -- run art/tools/generate_operator_out.py over a set of
     headers, one .operator_out.cc per (module, header). (Also emitted as
     gensrcs custom-commands by the emitter; this driver can pre-stage them
     too, which is handy for standalone runs / debugging.)

  2. mterp asm     -- run art/runtime/interpreter/mterp/gen_mterp.py over the
     per-arch *.S inputs to produce mterp_<arch>.S.

  3. asm_defines   -- TWO-STAGE: compile art/tools/cpp-define-generator/
     asm_defines.cc to assembly text (clang -S) with the runtime's include +
     define context, then run make_header.py over the .s to emit asm_defines.h.

This driver is deliberately separate from the .bp->CMake converter: it is build
orchestration, not description. It is invoked once before/at configure time to
populate gensrc/, OR wired as CMake custom commands. The asm_defines step needs
the same include/define context as libart, supplied here explicitly (mirroring
historical $<TARGET_PROPERTY:art,...> wiring).
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field


@dataclass
class CodegenConfig:
    native_root: str               # multipath vendor/ (foundational libs, ICU, …)
    gensrc_dir: str                # output tree, e.g. build/gensrc
    arch: str = "x86_64"
    clang: str = "clang++"
    # Root of the art tree. art/* inputs (mterp, asm_defines, operator_out
    # headers) come from here (nested vendor/art). Defaults to native_root for
    # standalone runs where art lives under the same root.
    art_root: str = ""
    # aconfig flag declaration files to generate C++ headers for (android-16+
    # feature flags; no aconfig tool on host). art-tree files are relative to
    # art_root; the libcore file lives under libcore_root (com_android_libcore.h,
    # included by art e.g. scoped_thread_priority_change.cc).
    aconfig_files: list[str] = field(default_factory=lambda: [
        "art/build/flags/art-flags.aconfig",
        "art/build/flags/art-rw-flags.aconfig",
    ])
    # libcore tree root (for libcore.aconfig). Empty -> skip libcore flags.
    libcore_root: str = ""
    libcore_aconfig_files: list[str] = field(default_factory=lambda: [
        "libcore.aconfig",
    ])
    # Project-owned compat include root (//compat/include): provides shim headers
    # the bumped art needs but the archive-pinned libbase lacks (android-base/
    # stringify.h). Empty -> derived from this file's location.
    compat_include: str = ""
    # Include dirs (relative to native_root) for the asm_defines compile.
    asm_includes: list[str] = field(default_factory=lambda: [
        "art/libartbase", "art/runtime", "art/libdexfile",
        "libnativehelper/include_jni", "libbase/include",
        "logging/liblog/include", "fmtlib/include", "external/tinyxml2",
        "libziparchive/include", "art/tools/cpp-define-generator",
    ])
    # Target OS for asm_defines layout: linux (host) or windows (PE).
    # Windows Runtime* has different sizeof/layout (e.g. unique_ptr padding),
    # so ART_TARGET_WINDOWS must be used when generating PE asm_defines.h.
    # Default remains Linux for host/native builds.
    asm_target_os: str = "linux"
    # Defines for the asm_defines compile: the art.go-injected knobs (absent
    # from any .bp) plus the runtime behavioral overlay. Mirrors runtime.cmake.
    # For windows, ART_TARGET_LINUX is replaced by ART_TARGET_WINDOWS (+ _WIN32).
    asm_defines_macros: list[str] = field(default_factory=lambda: [
        "ART_STACK_OVERFLOW_GAP_arm=8192", "ART_STACK_OVERFLOW_GAP_arm64=8192",
        "ART_STACK_OVERFLOW_GAP_riscv64=8192", "ART_STACK_OVERFLOW_GAP_x86=8192",
        "ART_STACK_OVERFLOW_GAP_x86_64=8192", "ART_FRAME_SIZE_LIMIT=1744",
        "ART_PAGE_SIZE_AGNOSTIC=1",
        "ART_DEFAULT_GC_TYPE_IS_CMS", "ART_BASE_ADDRESS=0x60000000",
        "ART_BASE_ADDRESS_MIN_DELTA=(-0x1000000)",
        "ART_BASE_ADDRESS_MAX_DELTA=0x1000000",
        "ART_TARGET", "ART_TARGET_LINUX", "USE_D8_DESUGAR=1",
    ])
    # Toolchain-drift force-includes for the asm_defines compile (see
    # toolchain-drift notes): clang-21 vs 2023 sources.
    asm_force_includes: list[str] = field(default_factory=lambda: [
        "cstdint", "algorithm",
    ])

    def p(self, *parts: str) -> str:
        return os.path.join(self.native_root, *parts)

    def _art_base(self) -> str:
        return self.art_root or self.native_root

    def pa(self, *parts: str) -> str:
        """Resolve an art/* path against the bumped art tree (art_root)."""
        return os.path.join(self._art_base(), *parts)

    def inc(self, rel: str) -> str:
        """Resolve an include dir: art/* against art_root, the rest against
        native_root (foundational libs / ICU stay archive-pinned)."""
        if rel == "art" or rel.startswith("art/"):
            return os.path.join(self._art_base(), rel)
        return os.path.join(self.native_root, rel)

    def out(self, *parts: str) -> str:
        return os.path.join(self.gensrc_dir, *parts)

    def compat_inc(self) -> str:
        """Project-owned //compat/include root (stringify.h shim, etc.)."""
        if self.compat_include:
            return self.compat_include
        # tools/bp2cmake/bp2cmake/codegen.py -> repo root is 3 levels up.
        here = os.path.dirname(os.path.abspath(__file__))
        return os.path.abspath(os.path.join(here, "..", "..", "..", "compat", "include"))


class CodegenError(Exception):
    pass


def _run(cmd: list[str], cwd: str | None = None, capture_stdout_to: str | None = None) -> None:
    """Run a command; on failure raise with captured stderr. If
    capture_stdout_to is given, write stdout to that file."""
    out_f = open(capture_stdout_to, "w") if capture_stdout_to else None
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, stdout=(out_f or subprocess.PIPE),
            stderr=subprocess.PIPE, text=True,
        )
    finally:
        if out_f:
            out_f.close()
    if proc.returncode != 0:
        # Clean up a partial output file so a failed step doesn't look done.
        if capture_stdout_to and os.path.exists(capture_stdout_to):
            os.remove(capture_stdout_to)
        raise CodegenError(
            f"command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stderr}"
        )


def gen_operator_out(cfg: CodegenConfig, module_reldir: str, headers: list[str]) -> list[str]:
    """Run generate_operator_out.py for each header. Returns output paths.
    Mirrors the archive's generateArtOpCxxSrc task."""
    tool = cfg.pa("art/tools/generate_operator_out.py")
    outputs = []
    for h in headers:
        out_path = cfg.out(module_reldir, h + ".operator_out.cc")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        # Tool reads <reldir> <header-relative-to-root>; run from the art root.
        in_rel = os.path.join(module_reldir, h)
        _run([sys.executable, tool, module_reldir, in_rel],
             cwd=cfg._art_base(), capture_stdout_to=out_path)
        outputs.append(out_path)
    return outputs


def gen_mterp(cfg: CodegenConfig, arch: str | None = None) -> str:
    """Run gen_mterp.py over the per-arch *.S inputs -> mterp_<arch>.S.
    Mirrors generateArtMterpAsmSrc."""
    arch = arch or cfg.arch
    tool = cfg.pa("art/runtime/interpreter/mterp/gen_mterp.py")
    src_dir = cfg.pa("art/runtime/interpreter/mterp", arch + "ng")
    if not os.path.isdir(src_dir):
        raise CodegenError(f"mterp source dir not found: {src_dir}")
    asm_inputs = sorted(
        os.path.join(src_dir, f) for f in os.listdir(src_dir) if f.endswith(".S")
    )
    if not asm_inputs:
        raise CodegenError(f"no .S inputs in {src_dir}")
    out_path = cfg.out("art/asm/mterp", f"mterp_{arch}.S")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    # gen_mterp.py writes the output file itself (arg1 = output, rest = inputs).
    _run([sys.executable, tool, out_path] + asm_inputs, cwd=cfg._art_base())
    return out_path


def _asm_defines_macros_for(cfg: CodegenConfig) -> list[str]:
    """Return asm_defines macros adjusted for cfg.asm_target_os."""
    macros = list(cfg.asm_defines_macros)
    os_name = (cfg.asm_target_os or "linux").lower()
    if os_name in ("windows", "win32", "win64", "pe"):
        # PE layout: drop ART_TARGET_LINUX, force ART_TARGET_WINDOWS/_WIN32.
        macros = [m for m in macros if m != "ART_TARGET_LINUX" and not m.startswith("ART_TARGET_LINUX=")]
        for extra in ("ART_TARGET_WINDOWS", "_WIN32", "WIN32", "WIN32_LEAN_AND_MEAN", "NOMINMAX", "NOGDI"):
            if extra not in macros and not any(m == extra or m.startswith(extra + "=") for m in macros):
                macros.append(extra)
    return macros


def gen_asm_defines(cfg: CodegenConfig) -> str:
    """TWO-STAGE: compile asm_defines.cc to assembly text, then make_header.py
    over it -> asm_defines.h. Mirrors generateArtAsmDefinitions +
    generateArtAsmHeader (which the archive split between CMake and Gradle).

    For PE (asm_target_os=windows), uses ART_TARGET_WINDOWS so offsets match
    the MSVC/PE Runtime layout (notably RUNTIME_INSTRUMENTATION_OFFSET)."""
    asm_cc = cfg.pa("art/tools/cpp-define-generator/asm_defines.cc")
    s_path = cfg.out("art/asm_defines.s")
    h_path = cfg.out("art/asm/include/asm_defines.h")
    os.makedirs(os.path.dirname(s_path), exist_ok=True)
    os.makedirs(os.path.dirname(h_path), exist_ok=True)

    # Stage 1: clang -S to human-readable assembly carrying the >>NAME val neg<<
    # markers. Needs the runtime include + define context.
    cmd = [cfg.clang, "-std=gnu++20", "-S", "-o", s_path]
    for inc in cfg.asm_includes:
        cmd += ["-I", cfg.inc(inc)]
    # aconfig-generated headers (com_android_art_flags.h etc.) staged in gensrc.
    cmd += ["-I", cfg.out("art/aconfig/include")]
    # project-owned compat shims (android-base/stringify.h) the archive lacks.
    cmd += ["-I", cfg.compat_inc()]
    for m in _asm_defines_macros_for(cfg):
        cmd += ["-D" + m]
    for fi in cfg.asm_force_includes:
        cmd += ["-include", fi]
    cmd += ["-Wno-strict-primary-template-shadow", "-Wno-invalid-offsetof",
            "-Wno-attribute", "-Wno-deprecated-declarations", "-UDEBUG"]
    # PE target: prefer windows-msvc triple when generating PE offsets so
    # ABI/layout matches art.dll. Host linux builds keep default host triple.
    os_name = (cfg.asm_target_os or "linux").lower()
    if os_name in ("windows", "win32", "win64", "pe"):
        cmd += ["--target=x86_64-pc-windows-msvc"]
    cmd += [asm_cc]
    _run(cmd, cwd=cfg._art_base())

    # Stage 2: make_header.py reads the .s and prints the #defines to stdout.
    make_header = cfg.pa("art/tools/cpp-define-generator/make_header.py")
    _run([sys.executable, make_header, s_path],
         cwd=cfg._art_base(), capture_stdout_to=h_path)
    return h_path


# The operator_out generation set, mirroring the archive's generateArtOpCxxSrc
# genInfoList. Keyed by module source dir (relative to native_root).
OPERATOR_OUT_SETS: dict[str, list[str]] = {
    "art/libartbase": [
        "arch/instruction_set.h", "base/allocator.h", "base/unix_file/fd_file.h",
    ],
    "art/libdexfile": [
        "dex/dex_file.h", "dex/dex_file_layout.h", "dex/dex_instruction.h",
        "dex/dex_instruction_utils.h", "dex/invoke_type.h",
    ],
    "art/runtime": [
        "base/callee_save_type.h", "base/locks.h", "class_status.h",
        "compilation_kind.h", "gc_root.h", "gc/allocator_type.h",
        "gc/allocator/rosalloc.h", "gc/collector_type.h", "gc/collector/gc_type.h",
        "gc/collector/mark_compact.h", "gc/space/region_space.h",
        "gc/space/space.h", "gc/weak_root_state.h", "image.h", "instrumentation.h",
        "indirect_reference_table.h", "jdwp_provider.h", "jni_id_type.h",
        "linear_alloc.h", "lock_word.h", "oat.h", "oat_file.h", "process_state.h",
        "reflective_value_visitor.h", "stack.h", "suspend_reason.h", "thread.h",
        "thread_state.h", "trace.h", "verifier/verifier_enums.h",
    ],
}


def gen_aconfig(cfg: CodegenConfig) -> list[str]:
    """Generate the aconfig C++ headers (com_android_art_flags.h,
    com_android_art_rw_flags.h) from the .aconfig declarations under art_root.
    android-16+ ART includes these generated headers; we have no aconfig tool,
    so reproduce its C++ output (all flags at their default == disabled)."""
    from . import aconfig
    files = [cfg.pa(f) for f in cfg.aconfig_files]
    if cfg.libcore_root:
        files += [os.path.join(cfg.libcore_root, f) for f in cfg.libcore_aconfig_files]
    files = [f for f in files if os.path.isfile(f)]
    if not files:
        return []
    out_dir = cfg.out("art/aconfig/include")
    return aconfig.generate(files, out_dir)


def run_all(cfg: CodegenConfig, operator_sets: dict[str, list[str]] | None = None,
            do_mterp: bool = True, do_asm_defines: bool = True,
            do_aconfig: bool = True) -> dict[str, list[str]]:
    """Stage the whole gensrc tree. Returns a report of produced files."""
    report: dict[str, list[str]] = {"operator_out": [], "mterp": [],
                                     "asm_defines": [], "aconfig": []}
    sets = operator_sets if operator_sets is not None else OPERATOR_OUT_SETS
    # aconfig headers first: asm_defines and other TUs may include them.
    if do_aconfig:
        report["aconfig"].extend(gen_aconfig(cfg))
    for reldir, headers in sets.items():
        report["operator_out"].extend(gen_operator_out(cfg, reldir, headers))
    if do_mterp:
        report["mterp"].append(gen_mterp(cfg))
    if do_asm_defines:
        report["asm_defines"].append(gen_asm_defines(cfg))
    return report
