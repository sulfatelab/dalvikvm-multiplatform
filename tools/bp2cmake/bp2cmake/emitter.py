"""Layer 3 — emit CMake from a Layer-1 module + the Layer-2 overlay.

The emitter is intentionally "dumb": all judgment lives in Layer 2. It:
  * resolves the CMake library kind (shared/static/executable),
  * collects sources (prefixed with the module's bp_dir, plus absorbed
    whole_static_libs sources),
  * resolves include directories by walking exported includes of header_libs
    and link deps,
  * maps AOSP dep names to CMake target names via the overlay,
  * writes add_library/add_executable + target_* commands.

Paths are emitted relative to a `${MDVM_NATIVE_SRC_ROOT_DIR}` CMake variable so
the generated file is location-independent.
"""

from __future__ import annotations

import os
import posixpath

from .evaluator import EvalError, Evaluator
from .model import Module
from .overlay import Overlay, apply_module_policy

_SRC = "${MDVM_NATIVE_SRC_ROOT_DIR}"
_COMPAT = "${MDVM_COMPAT_INCLUDE_DIR}"
_GENSRC = "${MDVM_GENSRC_DIR}"


class Emitter:
    def __init__(self, evaluator: Evaluator, overlay: Overlay,
                 root_paths: dict[str, str] | None = None):
        self.ev = evaluator
        self.ov = overlay
        # Map of root_var -> real filesystem path, for glob expansion.
        self.root_paths = root_paths or {}
        self._exported_cache: dict[str, list[str]] = {}

    def _expand_globs(self, srcs: list[str], bp_dir: str, root_var: str) -> list[str]:
        """Expand Soong glob srcs (containing '*') against the real filesystem.
        Soong expands these at build time; we do it at convert time. Falls back
        to keeping the literal if the root path is unknown."""
        import glob as _glob
        root = self.root_paths.get(root_var)
        out: list[str] = []
        for s in srcs:
            if "*" not in s:
                out.append(s)
                continue
            if not root:
                out.append(s)  # can't expand; keep literal
                continue
            base = os.path.join(root, bp_dir) if bp_dir else root
            matches = sorted(_glob.glob(os.path.join(base, s), recursive=True))
            for mpath in matches:
                rel = os.path.relpath(mpath, base)
                out.append(rel)
        return out

    # --- helpers -------------------------------------------------------

    def _kind(self, m: Module) -> str:
        pol = self.ov.policy_for(m.name)
        if pol.kind:
            return pol.kind
        t = m.type
        if t in ("cc_binary", "cc_binary_host", "art_cc_binary"):
            return "executable"
        if t in ("cc_library_static", "art_cc_library_static"):
            return "static"
        if t in ("cc_library_shared",):
            return "shared"
        # cc_library / art_cc_library are ambiguous -> default shared.
        return "shared"

    def _join(self, bp_dir: str, rel: str, root_var: str = "MDVM_NATIVE_SRC_ROOT_DIR") -> str:
        p = posixpath.normpath(posixpath.join(bp_dir, rel)) if bp_dir else rel
        return f"${{{root_var}}}/{p}"

    def _exported_includes(self, name: str, _seen: set[str] | None = None) -> list[str]:
        """Include dirs a dependency contributes to its consumers, transitively
        through its header libs. Unresolvable deps are skipped (the converter
        only loads the allowlisted reachable modules)."""
        if name in self._exported_cache:
            return self._exported_cache[name]
        _seen = _seen or set()
        if name in _seen:
            return []
        _seen.add(name)
        out: list[str] = []
        try:
            dep = self.ev.resolve(name)
        except EvalError:
            return []
        for d in dep.export_include_dirs:
            out.append(self._join(dep.bp_dir, d, dep.root_var))
        for hl in dep.header_libs:
            out.extend(self._exported_includes(hl, _seen))
        self._exported_cache[name] = _dedupe(out)
        return self._exported_cache[name]

    def _absorbed_modules(self, m: Module) -> list[Module]:
        """All modules whose sources should be inlined into `m` via
        whole_static_libs, transitively (whole_static is recursive in Soong)."""
        out: list[Module] = []
        seen: set[str] = set()
        stack = list(m.whole_static_libs)
        while stack:
            name = stack.pop(0)
            if name in seen:
                continue
            seen.add(name)
            try:
                dep = self.ev.resolve(name)
            except EvalError:
                continue
            out.append(dep)
            stack.extend(dep.whole_static_libs)
        return out

    def _module_files(self, m: Module) -> list[str]:
        """Final list of (root_var, relpath) source files for a module: expand
        filegroup refs and globs, then apply exclude_srcs. Returns joined paths."""
        raw: list[tuple[str, str, str]] = []  # (bp_dir, rel, root_var)
        for s in m.srcs:
            if s.startswith(":"):
                fg = self.ev.resolve_filegroup(s[1:])
                if fg is not None:
                    fg_srcs, fg_dir, fg_root = fg
                    expanded = self._expand_globs(fg_srcs, fg_dir, fg_root)
                    raw.extend((fg_dir, fs, fg_root) for fs in expanded)
                continue
            raw.append((m.bp_dir, s, m.root_var))
        # expand globs for the module's own (non-filegroup) srcs
        expanded: list[tuple[str, str, str]] = []
        for bp_dir, s, rv in raw:
            if "*" in s:
                for e in self._expand_globs([s], bp_dir, rv):
                    expanded.append((bp_dir, e, rv))
            else:
                expanded.append((bp_dir, s, rv))
        # apply exclude_srcs (match on basename rel)
        excluded = set(m.exclude_srcs)
        out: list[str] = []
        seen: set[tuple[str, str]] = set()
        for bp_dir, s, rv in expanded:
            if s in excluded:
                continue
            key = (rv, posixpath.join(bp_dir, s))
            if key in seen:
                continue
            seen.add(key)
            out.append(self._join(bp_dir, s, rv))
        return out

    def _sources(self, m: Module) -> list[str]:
        pol = self.ov.policy_for(m.name)
        srcs = self._module_files(m)
        if pol.absorb_whole_static:
            # whole_static_libs are inlined transitively. Apply each absorbed
            # module's overlay source edits so e.g. Win64 can drop
            # monitor_linux.cc from libart-runtime when folding into libart.
            for dep in self._absorbed_modules(m):
                from .overlay import apply_module_policy
                dep_pol = self.ov.policy_for(dep.name)
                dep2 = apply_module_policy(dep, dep_pol, self.ov.global_policy)
                srcs.extend(self._module_files(dep2))
        # Top-level remove_srcs also filters absorbed paths by basename.
        if pol.remove_srcs:
            ban = set(pol.remove_srcs)
            srcs = [s for s in srcs if posixpath.basename(s) not in ban
                    and not any(s.endswith("/" + b) or s.endswith(b) for b in ban)]
        # add_gensrc_sources already handled elsewhere; pol.add_srcs joined below
        for s in pol.add_srcs:
            # relative to module bp_dir
            srcs.append(self._join(m.bp_dir, s, m.root_var))
        return _dedupe(srcs)

    def _absorbed_source_props(self, m: Module) -> list[str]:
        """When we absorb a whole_static_lib's sources into this target, those
        sources still need the absorbed module's own cflags/defines (Soong
        compiled them in the dep's context). Emit per-source COMPILE_OPTIONS so
        e.g. cpu_features' -DSTACK_LINE_READER_BUFFER_SIZE reaches its .c files
        even though they now build inside libart."""
        pol = self.ov.policy_for(m.name)
        if not pol.absorb_whole_static:
            return []
        gp = self.ov.global_policy
        blocks: list[str] = []
        for dep in self._absorbed_modules(m):
            # Apply the SAME global flag-drop policy as the main target options
            # (drop_cflags): these per-file COMPILE_OPTIONS otherwise bypass it
            # and can re-arm e.g. -Werror on host (C++20's
            # -Wdeprecated-literal-operator fires in fmtlib via art_defaults).
            opts = [c for c in dep.cflags if c not in gp.drop_cflags]
            if not opts:
                continue
            files = [self._join(dep.bp_dir, s, dep.root_var) for s in dep.effective_srcs()
                     if not s.startswith(":")]
            if not files:
                continue
            opt_str = ";".join(opts)
            block = ["set_source_files_properties("]
            for f in files:
                block.append(f"        {f}")
            block.append(f'        PROPERTIES COMPILE_OPTIONS "{opt_str}")')
            blocks.append("\n".join(block))
        return blocks

    def _include_dirs(self, m: Module) -> list[str]:
        dirs: list[str] = []
        # own includes
        for d in m.export_include_dirs:
            dirs.append(self._join(m.bp_dir, d, m.root_var))
        for d in m.local_include_dirs:
            dirs.append(self._join(m.bp_dir, d, m.root_var))
        for d in m.include_dirs:
            dirs.append(f"${{{m.root_var}}}/{d}")
        # from header libs
        for hl in m.header_libs:
            dirs.extend(self._exported_includes(hl))
        # from link deps (so we can see their public headers)
        for dep in m.shared_libs + m.static_libs + m.whole_static_libs:
            dirs.extend(self._exported_includes(dep))
        # overlay-added include dirs (e.g. non-AOSP glue)
        pol = self.ov.policy_for(m.name)
        for d in pol.add_include_dirs:
            dirs.append(f"{_SRC}/{d}")
        for d in pol.add_compat_include_dirs:
            dirs.append(_COMPAT if d in (".", "") else f"{_COMPAT}/{d}")
        for d in pol.add_gensrc_includes:
            dirs.append(_GENSRC if d in (".", "") else f"{_GENSRC}/{d}")
        return _dedupe(dirs)

    def _link_libs(self, m: Module) -> list[str]:
        pol = self.ov.policy_for(m.name)
        libs: list[str] = []
        # whole_static absorbed (transitively) -> not linked as separate targets
        skip = {d.name for d in self._absorbed_modules(m)} if pol.absorb_whole_static else set()
        skip |= set(m.whole_static_libs) if pol.absorb_whole_static else set()
        for lib in m.shared_libs + m.static_libs:
            if lib in skip:
                continue
            libs.append(self.ov.target_name(lib))
        return _dedupe(libs)

    # --- emission ------------------------------------------------------

    def _generated_sources(self, m: Module) -> tuple[list[str], list[str]]:
        """Return (generated_cc_paths, custom_command_blocks) for the module's
        generated_sources (gensrcs modules). Outputs are staged under
        ${MDVM_GENSRC_DIR}/<bp_dir>/<src>.<ext>.

        When the module absorbs whole_static_libs (absorb_whole_static), those
        absorbed modules' sources are inlined here, so their generated_sources
        (e.g. libart-runtime's art_operator_srcs operator_out) must be generated
        and compiled into THIS target too -- otherwise the operator<< definitions
        are missing and the final link fails with undefined references."""
        gen_paths: list[str] = []
        blocks: list[str] = []
        pol = self.ov.policy_for(m.name)
        modules = [m]
        if pol.absorb_whole_static:
            modules += self._absorbed_modules(m)
        seen_gensrcs: set[str] = set()
        for mod in modules:
            for gname in mod.generated_sources:
                if gname in seen_gensrcs:
                    continue
                seen_gensrcs.add(gname)
                self._emit_one_gensrcs(gname, gen_paths, blocks)
        return gen_paths, blocks

    def _emit_one_gensrcs(self, gname: str, gen_paths: list[str],
                          blocks: list[str]) -> None:
        try:
            gs = self.ev.resolve_gensrcs(gname)
        except EvalError:
            return
        if gs is None:
            return
        tool = self.ev.tool_script(gs.tool)
        if tool is None:
            blocks.append(f"# WARNING: gensrcs {gname}: tool {gs.tool!r} not resolved")
            return
        tool_dir, tool_script, tool_root = tool
        tool_path = self._join(tool_dir, tool_script, tool_root)
        src_root = f"${{{gs.root_var}}}"
        for src in gs.srcs:
            in_rel = f"{gs.bp_dir}/{src}" if gs.bp_dir else src
            out_rel = f"{gs.bp_dir}/{src}.{gs.output_extension}" if gs.bp_dir else f"{src}.{gs.output_extension}"
            out_path = f"{_GENSRC}/{out_rel}"
            gen_paths.append(out_path)
            reldir = gs.bp_dir
            blocks.append(
                f"add_custom_command(\n"
                f"    OUTPUT {out_path}\n"
                f"    COMMAND ${{CMAKE_COMMAND}} -E make_directory {_GENSRC}/{gs.bp_dir}\n"
                f"    COMMAND ${{Python3_EXECUTABLE}} {tool_path} {reldir} {in_rel} > {out_path}\n"
                f"    DEPENDS {tool_path} {src_root}/{in_rel}\n"
                f"    WORKING_DIRECTORY {src_root}\n"
                f"    COMMENT \"gensrcs {gname}: {src}\"\n"
                f"    VERBATIM)"
            )

    def emit_module(self, m: Module) -> str:
        pol = self.ov.policy_for(m.name)
        # Apply list/flag policy edits in place.
        apply_module_policy(m, pol, self.ov.global_policy)

        target = self.ov.target_name(m.name)
        kind = self._kind(m)
        srcs = self._sources(m)
        gen_paths, gen_blocks = self._generated_sources(m)
        srcs = srcs + gen_paths
        # Sources produced by the codegen driver (mterp .S, etc.).
        for gp in pol.add_gensrc_sources:
            srcs.append(f"{_GENSRC}/{gp}")
        includes = self._include_dirs(m)
        cflags = list(m.cflags)
        cppflags = list(m.cppflags)
        conlyflags = list(m.conlyflags)
        # Language standard overrides (Soong cpp_std/c_std) -> -std= flags,
        # scoped to the right language so a mixed C/C++ target stays correct.
        if m.cpp_std:
            cppflags.insert(0, "-std=" + _std_flag(m.cpp_std, cpp=True))
        if m.c_std:
            conlyflags.insert(0, "-std=" + _std_flag(m.c_std, cpp=False))
        defines = list(pol.add_defines)
        public_defines = list(pol.add_public_defines)
        # art.go-injected defines for every ART-tree module (bp_dir under art/).
        gp = self.ov.global_policy
        if gp.art_defines and (m.bp_dir == "art" or m.bp_dir.startswith("art/")):
            for d in gp.art_defines:
                if d not in defines:
                    defines.append(d)
        link = self._link_libs(m)

        lines: list[str] = []
        lines.append(f"# Generated by bp2cmake from {m.type} \"{m.name}\". Do not edit by hand.")
        lines.append(f"# Port-policy decisions for this module live in //overlay/port_policy.py.")
        lines.append("")

        # Generated-source custom commands (run before the target compiles).
        if gen_blocks:
            lines.extend(gen_blocks)
            lines.append("")

        # target declaration
        if kind == "executable":
            lines.append(f"add_executable({target}")
        else:
            ck = "SHARED" if kind == "shared" else "STATIC"
            lines.append(f"add_library({target} {ck}")
        for s in srcs:
            lines.append(f"        {s}")
        lines.append(")")
        lines.append("")

        if includes:
            lines.append(f"target_include_directories({target}")
            for d in includes:
                lines.append(f"        PUBLIC {d}")
            lines.append(")")
            lines.append("")

        # compile options, split by language where the .bp distinguished them.
        opt_lines: list[str] = []
        if cflags:
            opt_lines.append("        PRIVATE " + " ".join(cflags))
        if cppflags:
            opt_lines.append(
                "        PRIVATE $<$<COMPILE_LANGUAGE:CXX>:" + " ".join(cppflags) + ">"
            )
        if conlyflags:
            opt_lines.append(
                "        PRIVATE $<$<COMPILE_LANGUAGE:C>:" + " ".join(conlyflags) + ">"
            )
        if opt_lines:
            lines.append(f"target_compile_options({target}")
            lines.extend(opt_lines)
            lines.append(")")
            lines.append("")

        # Function-like macro defines (name has parens, e.g. __INTRODUCED_IN(x)=)
        # cannot round-trip through CMake's COMPILE_DEFINITIONS (it mangles the
        # '()' and '='). Emit those as raw compile OPTIONS with SHELL: quoting so
        # they reach clang as a literal -D token.
        def _is_funcmacro(d: str) -> bool:
            name = d.split("=", 1)[0]
            return "(" in name
        fn_defines = [d for d in defines if _is_funcmacro(d)]
        defines = [d for d in defines if not _is_funcmacro(d)]
        fn_public = [d for d in public_defines if _is_funcmacro(d)]
        public_defines = [d for d in public_defines if not _is_funcmacro(d)]

        if defines or public_defines:
            lines.append(f"target_compile_definitions({target}")
            if public_defines:
                lines.append("        PUBLIC " + " ".join(_quote_define(d) for d in public_defines))
            if defines:
                lines.append("        PRIVATE " + " ".join(_quote_define(d) for d in defines))
            lines.append(")")
            lines.append("")
        if fn_defines or fn_public:
            lines.append(f"target_compile_options({target}")
            for d in fn_public:
                lines.append(f'        PUBLIC "SHELL:-D{d}"')
            for d in fn_defines:
                lines.append(f'        PRIVATE "SHELL:-D{d}"')
            lines.append(")")
            lines.append("")

        if m.ldflags:
            lines.append(f"target_link_options({target} PRIVATE " + " ".join(m.ldflags) + ")")
            lines.append("")

        if link:
            lines.append(f"target_link_libraries({target} " + " ".join(link) + ")")
            lines.append("")

        # Per-source flags for absorbed whole_static sources (they need the
        # absorbed module's own cflags/defines, e.g. cpu_features' buffer-size).
        for block in self._absorbed_source_props(m):
            lines.append(block)
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"


def _quote_define(d: str) -> str:
    """Quote a compile definition whose name OR value contains characters the
    shell or CMake list-splitting would mangle (parens, spaces). Examples:
    ART_BASE_ADDRESS_MIN_DELTA=(-0x1000000) (value), __INTRODUCED_IN(x)= (name --
    a function-like macro neutralizer). The whole token must reach clang intact."""
    if any(c in d for c in "() \t"):
        esc = d.replace('"', '\\"')
        return f'"{esc}"'
    return d


def _std_flag(value: str, cpp: bool) -> str:
    """Map a Soong cpp_std/c_std value to a clang -std= argument value.

    Soong accepts e.g. "c++17", "c++2a", "gnu++17", "c99", "c11", and the
    special "experimental" (latest draft). We pass through concrete values and
    map "experimental" to a sane recent default."""
    if value == "experimental":
        return "gnu++2a" if cpp else "gnu11"
    return value


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out
