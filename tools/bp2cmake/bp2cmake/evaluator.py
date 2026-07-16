"""Layer 1 evaluator: parsed Blueprint -> normalized, config-resolved graph.

Responsibilities:
  * Evaluate value expressions (variable refs, `+` concatenation) into plain
    Python values, using per-file variable scope.
  * Expand `defaults:` inheritance with Soong merge semantics (lists append,
    scalars overridden by the more-specific module; defaults applied first).
  * Collapse `target{}` / `arch{}` / `multilib{}` selects against the fixed
    Config, dropping inactive branches against Config (android/musl/other OS; windows active when Config.os=windows).
  * Map the surviving properties onto the `model.Module` dataclass, discarding
    Android-only metadata (apex, vndk, stubs, sanitize, min_sdk_version, ...).

It does NOT apply port-policy decisions — that is Layer 2 (the overlay).
"""

from __future__ import annotations

import os

from . import ast
from .config import Config
from .model import Module, ModuleGraph
from .parser import parse

# Soong target keys we recognise as *selects*; only those in the config's
# active set survive collapsing.
_SELECT_KEYS = ("target", "arch", "multilib", "soong_config_variables", "codegen", "avx2")

# Module property names we map onto model.Module (list-typed).
_LIST_PROPS = {
    "srcs", "exclude_srcs",
    "cflags", "cppflags", "conlyflags", "ldflags",
    "include_dirs", "local_include_dirs", "export_include_dirs",
    "shared_libs", "static_libs", "whole_static_libs", "header_libs",
    "export_header_lib_headers", "export_static_lib_headers",
    "generated_sources", "generated_headers",
}

# Of those, the ones whose entries are MODULE NAMES (dependency references).
# Their entries may carry a Soong dependency-tag suffix `name#tag` (e.g.
# `libdexfile#impl`, new in android-16.0.0_r4) selecting a build variant. For
# the non-APEX host build there is a single variant, so the tag is stripped:
# both so the name maps to the right CMake target and so a `#` (a CMake comment
# char) never leaks into target_link_libraries().
_DEP_LIST_PROPS = {
    "shared_libs", "static_libs", "whole_static_libs", "header_libs",
    "export_header_lib_headers", "export_static_lib_headers",
}


def _strip_dep_tag(name: str) -> str:
    """`libfoo#impl` / `libfoo#bootstrap` -> `libfoo`. Soong variant tag."""
    if isinstance(name, str) and "#" in name:
        return name.split("#", 1)[0]
    return name

# Properties we intentionally ignore (Android-only / not needed for CMake).
_IGNORED_PROPS = {
    "vndk", "apex_available", "min_sdk_version", "sanitize", "stubs",
    "vendor_available", "product_available", "ramdisk_available",
    "vendor_ramdisk_available", "recovery_available", "native_bridge_supported",
    "host_supported", "device_supported", "sdk_version", "stl",
    "double_loadable", "llndk", "version_script", "afdo", "compile_multilib",
    "visibility", "license_kinds", "license_text", "default_applicable_licenses",
    "lto", "tidy", "tidy_checks", "tidy_flags", "pack_relocations",
    "product_variables", "ndk_headers", "system_shared_libs", "required",
    "recovery", "native_coverage", "use_version_lib", "static",
    "shared", "header_abi_checker", "name", "defaults",
}


class EvalError(Exception):
    pass


# Module types that actually produce C/C++ build artifacts we care about. On a
# name collision (e.g. a cc_library and an ndk_library both named "liblog"), the
# cc-type declaration wins over stubs/bindings/prebuilts.
_CC_MODULE_TYPES = {
    "cc_library", "cc_library_shared", "cc_library_static", "cc_library_headers",
    "cc_binary", "cc_binary_host", "cc_object", "cc_defaults", "cc_test",
    "art_cc_library", "art_cc_library_static", "art_cc_binary", "art_cc_defaults",
    "art_cc_test", "art_cc_test_library", "libart_cc_defaults",
    "libart_static_cc_defaults", "art_debug_defaults", "filegroup", "genrule",
    "gensrcs", "cc_genrule", "python_binary_host",
}


class _FileScope:
    """Variable bindings for one .bp file."""

    def __init__(self) -> None:
        self.vars: dict[str, object] = {}


class Evaluator:
    def __init__(self, config: Config):
        self.config = config
        # name -> (ast.Module, bp_dir, _FileScope)
        self._decls: dict[str, tuple[ast.Module, str, _FileScope]] = {}
        self._source_root = ""

    # --- loading -------------------------------------------------------

    def add_file(self, text: str, bp_path: str, source_root: str = "",
                 root_var: str = "MDVM_NATIVE_SRC_ROOT_DIR") -> None:
        bp = parse(text, bp_path)
        bp_dir = ""
        if source_root:
            self._source_root = source_root
            bp_dir = os.path.relpath(os.path.dirname(bp_path), source_root)
            if bp_dir == ".":
                bp_dir = ""
        scope = self._build_scope(bp)
        for m in bp.modules:
            name = self._module_name(m, scope)
            if not name:
                continue
            if name in self._decls:
                # Name collision: prefer a cc-type module over a non-cc stub
                # (ndk_library, rust_*, prebuilt_*, ...). If the incumbent is
                # already cc-type and the newcomer is not, keep the incumbent.
                existing_type = self._decls[name][0].type
                incoming_is_cc = m.type in _CC_MODULE_TYPES
                existing_is_cc = existing_type in _CC_MODULE_TYPES
                if existing_is_cc and not incoming_is_cc:
                    continue
            self._decls[name] = (m, bp_dir, scope, root_var)

    def add_path(self, bp_path: str, source_root: str = "",
                 root_var: str = "MDVM_NATIVE_SRC_ROOT_DIR") -> None:
        with open(bp_path) as f:
            self.add_file(f.read(), bp_path, source_root, root_var)

    # --- variable scope ------------------------------------------------

    def _build_scope(self, bp: ast.BlueprintFile) -> _FileScope:
        scope = _FileScope()
        for assn in bp.assignments:
            value = self._eval(assn.value, scope)
            if assn.append and assn.name in scope.vars:
                scope.vars[assn.name] = _concat(scope.vars[assn.name], value)
            else:
                scope.vars[assn.name] = value
        return scope

    def _module_name(self, m: ast.Module, scope: _FileScope) -> str | None:
        n = m.properties.get("name")
        if n is None:
            return None
        return self._eval(n, scope)

    # --- expression evaluation ----------------------------------------

    def _eval(self, expr: ast.Expr, scope: _FileScope):
        if isinstance(expr, ast.StringLit):
            return expr.value
        if isinstance(expr, ast.BoolLit):
            return expr.value
        if isinstance(expr, ast.IntLit):
            return expr.value
        if isinstance(expr, ast.VarRef):
            if expr.name not in scope.vars:
                raise EvalError(f"undefined variable {expr.name!r}")
            return scope.vars[expr.name]
        if isinstance(expr, ast.ListExpr):
            return [self._eval(it, scope) for it in expr.items]
        if isinstance(expr, ast.MapExpr):
            return {k: self._eval(v, scope) for k, v in expr.entries}
        if isinstance(expr, ast.Concat):
            return _concat(self._eval(expr.left, scope), self._eval(expr.right, scope))
        if isinstance(expr, ast.Select):
            return self._eval_select(expr, scope)
        raise EvalError(f"cannot evaluate {type(expr).__name__}")

    def _eval_select(self, sel: ast.Select, scope: _FileScope):
        """Resolve a Soong select() against the fixed Config.

        Resolve each condition to a value, then choose a case. Matching, per
        Soong: a `default` pattern matches anything (incl. unset/None); an `any`
        pattern matches any *set* (non-None) value; a literal/bool pattern
        matches an equal condition value. We make TWO passes so a `default` arm
        never shadows a more specific arm listed before it: first try cases with
        no DEFAULT pattern (exact/any), then fall back to the first case that
        has a DEFAULT in every non-matched position. An `any @ name` / matched
        binding exposes the condition value as variable `name` in that case's
        expression. No match and no default -> None (Soong's zero value; callers
        concatenating treat it as empty).
        """
        cond_values = [self.config.select_condition_value(fn, args)
                       for (fn, args) in sel.conditions]

        def try_match(allow_default: bool):
            for case in sel.cases:
                pats = case.patterns
                if len(pats) != len(cond_values):
                    continue
                bound = None
                ok = True
                for pat, cv in zip(pats, cond_values):
                    if pat is ast.DEFAULT:
                        if not allow_default:
                            ok = False
                            break
                        bound = cv
                    elif pat is ast.ANY:
                        if cv is None:      # `any` requires a set value
                            ok = False
                            break
                        bound = cv
                    elif pat == cv:
                        bound = cv
                    else:
                        ok = False
                        break
                if ok:
                    return case, bound
            return None

        chosen = try_match(allow_default=False) or try_match(allow_default=True)
        if chosen is None:
            return None
        case, bound = chosen
        if case.binding is not None:
            child = _FileScope()
            child.vars = dict(scope.vars)
            child.vars[case.binding] = bound
            return self._eval(case.value, child)
        return self._eval(case.value, scope)

    # --- module resolution --------------------------------------------

    def resolve(self, name: str) -> Module:
        """Build a fully normalized Module for `name`."""
        if name not in self._decls:
            raise EvalError(f"unknown module {name!r}")
        m_ast, bp_dir, scope, root_var = self._decls[name]

        # 1. Evaluate this module's own properties to a raw dict.
        raw = {k: self._eval(v, scope) for k, v in m_ast.properties.entries}

        # 2. Expand defaults (recursively), merging defaults FIRST then own.
        merged: dict = {}
        for default_name in raw.get("defaults", []) or []:
            base = self._resolve_propmap(default_name)
            merged = _deep_merge(merged, base)
        merged = _deep_merge(merged, raw)

        # 3. Collapse target/arch/multilib selects against config.
        collapsed = self._collapse_selects(merged)

        # 4. Map onto Module.
        return self._to_module(name, m_ast.type, bp_dir, collapsed, root_var)

    def resolve_filegroup(self, name: str):
        """Resolve a `filegroup` module to (srcs, bp_dir, root_var). srcs are
        paths relative to the filegroup's own bp_dir. Returns None if the module
        is unknown OR is not a `filegroup` (e.g. a genrule/gensrcs, whose `srcs`
        are generator INPUTS, not sources to compile -- those are handled by the
        gensrcs path / codegen driver, not inlined here)."""
        if name not in self._decls:
            return None
        m_ast, bp_dir, scope, root_var = self._decls[name]
        if m_ast.type != "filegroup":
            return None
        raw = {k: self._eval(v, scope) for k, v in m_ast.properties.entries}
        srcs = [s for s in (raw.get("srcs", []) or []) if isinstance(s, str)]
        return (srcs, bp_dir, root_var)

    def resolve_gensrcs(self, name: str) -> "GenSrcs":
        """Resolve a `gensrcs` module into a GenSrcs descriptor."""
        from .model import GenSrcs
        if name not in self._decls:
            raise EvalError(f"unknown gensrcs module {name!r}")
        m_ast, bp_dir, scope, _root = self._decls[name]
        raw = {k: self._eval(v, scope) for k, v in m_ast.properties.entries}
        tools = raw.get("tools", []) or []
        return GenSrcs(
            name=name,
            bp_dir=bp_dir,
            tool=tools[0] if tools else "",
            cmd=raw.get("cmd", ""),
            srcs=list(raw.get("srcs", []) or []),
            output_extension=raw.get("output_extension", "out"),
            root_var=_root,
        )

    def tool_script(self, tool_name: str) -> tuple[str, str, str] | None:
        """For a python_binary_host tool, return (bp_dir, main_script_relpath,
        root_var). Returns None if not found / not a python tool."""
        if tool_name not in self._decls:
            return None
        m_ast, bp_dir, scope, root_var = self._decls[tool_name]
        raw = {k: self._eval(v, scope) for k, v in m_ast.properties.entries}
        srcs = raw.get("srcs", []) or []
        main = raw.get("main")
        script = main if isinstance(main, str) else (srcs[0] if srcs else None)
        if not script:
            return None
        return (bp_dir, script, root_var)

    def _resolve_propmap(self, name: str) -> dict:
        """Return a default module's merged (defaults-expanded) property map,
        WITHOUT collapsing selects yet (so a default's target blocks merge with
        the consumer's before collapsing)."""
        if name not in self._decls:
            raise EvalError(f"unknown defaults module {name!r}")
        m_ast, _bp_dir, scope, _root = self._decls[name]
        raw = {k: self._eval(v, scope) for k, v in m_ast.properties.entries}
        merged: dict = {}
        for default_name in raw.get("defaults", []) or []:
            merged = _deep_merge(merged, self._resolve_propmap(default_name))
        return _deep_merge(merged, raw)

    def _collapse_selects(self, propmap: dict) -> dict:
        out: dict = {}
        # First copy non-select keys.
        for k, v in propmap.items():
            if k in _SELECT_KEYS:
                continue
            out[k] = v
        # Then merge active select branches (append lists onto base).
        for select_key in _SELECT_KEYS:
            block = propmap.get(select_key)
            if not isinstance(block, dict):
                continue
            active = self._active_branches(select_key, block)
            for branch in active:
                if isinstance(branch, dict):
                    # branch may itself contain selects (nested); collapse it too
                    out = _deep_merge(out, self._collapse_selects(branch))
        return out

    def _active_branches(self, select_key: str, block: dict) -> list[dict]:
        cfg = self.config
        result: list[dict] = []
        if select_key == "target":
            active_keys = cfg.active_target_keys
            for key in active_keys:
                if key in block:
                    result.append(block[key])
        elif select_key == "arch":
            if cfg.arch in block:
                result.append(block[cfg.arch])
        elif select_key == "multilib":
            if cfg.multilib_key in block:
                result.append(block[cfg.multilib_key])
        elif select_key == "avx2":
            # arch.<a>.avx2.{cflags:...}: only active when avx2 is enabled.
            if cfg.avx2:
                result.append(block)
        elif select_key == "codegen":
            # codegen: { arm:{...}, x86_64:{...}, ... } -> merge the enabled
            # codegen arches' branches.
            for a in cfg.codegen_arches:
                if a in block:
                    result.append(block[a])
        elif select_key == "soong_config_variables":
            # { varname: { <when-true props> }, ... }: include a branch when its
            # config variable resolves true. (Soong also supports nested value
            # selects, but ART only uses the boolean enable form here.)
            for var, branch in block.items():
                if isinstance(branch, dict) and cfg.soong_config_value(var):
                    result.append(branch)
        return result

    # --- mapping -------------------------------------------------------

    def _to_module(self, name: str, type_: str, bp_dir: str, props: dict,
                   root_var: str = "MDVM_NATIVE_SRC_ROOT_DIR") -> Module:
        m = Module(name=name, type=type_, bp_dir=bp_dir, root_var=root_var)

        # enabled: false disables the module.
        if props.get("enabled") is False:
            m.enabled = False

        # export_*_lib_headers contribute their named libs as header sources;
        # fold them into header_libs for include propagation.
        extra_header_libs: list[str] = []

        for key, value in props.items():
            if key in ("enabled",):
                continue
            if key in _IGNORED_PROPS:
                continue
            if key in ("cpp_std", "c_std"):
                if isinstance(value, str):
                    setattr(m, key, value)
                continue
            if key in ("export_header_lib_headers", "export_static_lib_headers"):
                if isinstance(value, list):
                    extra_header_libs.extend(_strip_dep_tag(v) for v in value)
                continue
            if key in _LIST_PROPS and hasattr(m, key):
                vals = value if isinstance(value, list) else [value]
                if key in _DEP_LIST_PROPS:
                    vals = [_strip_dep_tag(v) for v in vals]
                getattr(m, key).extend(vals)
            elif key in _LIST_PROPS:
                # known list prop not on the dataclass (export_*): stash
                m.extra[key] = value
            else:
                m.extra[key] = value

        for hl in extra_header_libs:
            if hl not in m.header_libs:
                m.header_libs.append(hl)

        return m


def _concat(a, b):
    """Blueprint `+` : string+string or list+list. A None operand (e.g. a
    select() with no matching case) acts as the identity / empty value."""
    if a is None:
        return b
    if b is None:
        return a
    if isinstance(a, str) and isinstance(b, str):
        return a + b
    if isinstance(a, list) and isinstance(b, list):
        return a + b
    if isinstance(a, int) and isinstance(b, int):
        return a + b
    raise EvalError(f"cannot concatenate {type(a).__name__} + {type(b).__name__}")


def _deep_merge(a: dict, b: dict) -> dict:
    """Deep-merge b onto a. Lists concatenate (a then b); dicts merge
    recursively; scalars: b wins. Inputs are not mutated."""
    out = dict(a)
    for k, vb in b.items():
        if k in out:
            va = out[k]
            if isinstance(va, list) and isinstance(vb, list):
                out[k] = va + vb
            elif isinstance(va, dict) and isinstance(vb, dict):
                out[k] = _deep_merge(va, vb)
            else:
                out[k] = vb
        else:
            out[k] = vb
    return out


def build_graph(evaluator: Evaluator, names: list[str]) -> ModuleGraph:
    g = ModuleGraph()
    for n in names:
        g.add(evaluator.resolve(n))
    return g
