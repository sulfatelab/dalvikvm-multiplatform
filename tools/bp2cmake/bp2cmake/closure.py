"""Dependency-closure resolution: given root module(s), find every buildable
module that must be emitted, in dependency order (deps before dependents).

This lets the top-level build name ONE root (e.g. `dalvikvm`) instead of a
hand-maintained list of ~20 modules. The walk follows the same link edges the
emitter does, with the same overlay edits applied, so the closure matches what
actually gets linked:

  * link deps = shared_libs + static_libs (+ whole_static_libs unless the module
    absorbs them), AFTER the overlay's add_/remove_ edits.
  * absorbed whole_static_libs are NOT emitted standalone (their sources are
    inlined into the consumer), but their own transitive link deps still are.
  * host/system libs (overlay.global_policy.host_libs, e.g. libz/libcap/liblz4)
    are skipped -- the build provides them as imported targets.
  * names that don't resolve to a buildable module (header_libs, missing libs)
    are skipped.
"""

from __future__ import annotations

from .evaluator import EvalError, Evaluator
from .model import Module
from .overlay import Overlay


def _effective_link_deps(m: Module, ov: Overlay) -> tuple[list[str], list[str]]:
    """Return (linked_dep_names, absorbed_dep_names) for a module after applying
    the overlay's dependency edits. `linked` are emitted+linked; `absorbed` are
    inlined (not emitted) but their transitive deps still count."""
    pol = ov.policy_for(m.name)

    shared = [d for d in m.shared_libs if d not in pol.remove_shared_libs]
    shared += [d for d in pol.add_shared_libs if d not in shared]
    static = [d for d in m.static_libs if d not in pol.remove_static_libs]
    static += [d for d in pol.add_static_libs if d not in static]
    whole = list(m.whole_static_libs)

    if pol.absorb_whole_static:
        absorbed = whole
        linked = shared + static
    else:
        absorbed = []
        linked = shared + static + whole
    return linked, absorbed


def _is_buildable(m: Module, ov: Overlay) -> bool:
    """A module is emitted if it has sources, or absorbs sources, or has
    overlay-added sources. Header-only libs (no sources) are skipped."""
    pol = ov.policy_for(m.name)
    if m.effective_srcs():
        return True
    if pol.add_srcs:
        return True
    if pol.absorb_whole_static and m.whole_static_libs:
        return True
    return False


def dependency_closure(ev: Evaluator, ov: Overlay, roots: list[str]) -> list[str]:
    """Return module names to emit, deps-before-dependents, starting from roots."""
    host = set(ov.global_policy.host_libs)
    order: list[str] = []
    state: dict[str, str] = {}  # name -> "visiting" | "done"

    def visit(name: str) -> None:
        if name in host or state.get(name) == "done":
            return
        if state.get(name) == "visiting":
            return  # cycle guard (ART has shared-lib cycles; tolerate them)
        try:
            m = ev.resolve(name)
        except EvalError:
            return  # header lib / system lib / unknown -> not emitted
        if not _is_buildable(m, ov):
            return
        state[name] = "visiting"

        linked, absorbed = _effective_link_deps(m, ov)
        # Recurse into linked deps (these get emitted too).
        for d in linked:
            visit(d)
        # Absorbed deps are inlined, not emitted, but pull THEIR link deps.
        for a in absorbed:
            if a in host:
                continue
            try:
                am = ev.resolve(a)
            except EvalError:
                continue
            a_linked, _ = _effective_link_deps(am, ov)
            for d in a_linked:
                visit(d)

        state[name] = "done"
        order.append(name)

    for r in roots:
        visit(r)
    return order
