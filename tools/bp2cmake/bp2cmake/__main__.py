"""CLI: bp2cmake — generate CMake for a set of modules.

Usage:
    python3 -m bp2cmake --root <native-src-root> --overlay <port_policy.py> \
        --module libbase [--module liblog ...] [--out <file>]

The converter loads the Android.bp for each requested module's directory (and,
lazily, any dependency dirs it can find), evaluates Layer 1, applies the Layer 2
overlay, and emits Layer 3 CMake.
"""

from __future__ import annotations

import argparse
import os
import sys

from .config import Config
from .emitter import Emitter
from .evaluator import Evaluator
from .overlay import load_overlay


def _find_bp_files(root: str, names=("Android.bp",)) -> list[str]:
    out = []
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if fn in names or (fn.endswith(".bp") and "blueprint-allbp" in names):
                out.append(os.path.join(dirpath, fn))
    return out


def _load_root(ev, root_dir, root_var, names, label="", exclude_top=()):
    """Load .bp files from a source tree. Returns count loaded.
    exclude_top: top-level subdir names (relative to root_dir) to skip entirely
    -- used to drop a tree (e.g. the archive's stale `art`) that an --extra-root
    supersedes with a coherent newer snapshot."""
    loaded = 0
    for bp in _find_bp_files(root_dir, names):
        rel = os.path.relpath(bp, root_dir)
        parts = rel.split(os.sep)
        if any(p in ("test", "tests", "fuzz", "benchmark", "sample") for p in parts):
            continue
        if parts and parts[0] in exclude_top:
            continue
        try:
            ev.add_path(bp, source_root=root_dir, root_var=root_var)
            loaded += 1
        except Exception as e:  # noqa: BLE001
            print(f"warn: failed to load {label}{rel}: {e}", file=sys.stderr)
    return loaded


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bp2cmake")
    ap.add_argument("--root", required=True, help="native source root")
    ap.add_argument("--overlay", required=True, help="path to port_policy.py")
    ap.add_argument("--module", action="append", default=[],
                    help="AOSP module name to emit (repeatable)")
    ap.add_argument("--root-module", action="append", default=[],
                    help="emit this module AND its full transitive dependency "
                         "closure, in dependency order (repeatable)")
    ap.add_argument("--out", help="output file (default: stdout)")
    ap.add_argument("--list-only", action="store_true",
                    help="print the resolved module list (closure) and exit")
    ap.add_argument("--load-dir", action="append", default=[],
                    help="extra dir (relative to root) whose Android.bp to load")
    ap.add_argument("--extra-root", action="append", default=[], metavar="DIR:CMAKEVAR",
                    help="load ALL *.bp blueprint files under DIR, recording their "
                         "paths relative to DIR against CMake variable CMAKEVAR "
                         "(repeatable). For trees outside native/ like libcore "
                         "(NativeCode.bp etc.) and ICU.")
    ap.add_argument("--exclude-top", action="append", default=[], metavar="NAME",
                    help="skip this top-level subdir of --root (e.g. drop the "
                         "archive's stale `art` when an --extra-root supersedes it)")
    ap.add_argument("--os", default="linux_glibc",
                    choices=["linux_glibc", "windows"],
                    help="target OS for Layer 1 select resolution "
                         "(default: linux_glibc; windows = Win64 PE)")
    ap.add_argument("--arch", default="x86_64",
                    help="target arch (default: x86_64)")
    args = ap.parse_args(argv)

    cfg = Config(os=args.os, arch=args.arch,
                 bitness=64 if "64" in args.arch else 32)
    ev = Evaluator(cfg)
    root_paths: dict[str, str] = {}

    # Load the native source root. Include boringssl's sources.bp (it holds the
    # libcrypto_sources/libssl_sources cc_defaults that the Android.bp modules
    # inherit) alongside Android.bp.
    root_paths["MDVM_NATIVE_SRC_ROOT_DIR"] = os.path.abspath(args.root)
    loaded = _load_root(ev, args.root, "MDVM_NATIVE_SRC_ROOT_DIR",
                        ("Android.bp", "sources.bp"), exclude_top=tuple(args.exclude_top))

    # Load extra roots: DIR:CMAKEVAR. These trees use blueprint files that may
    # not be named "Android.bp" (e.g. libcore's NativeCode.bp), so load every
    # *.bp. CMAKEVAR is the CMake path variable their sources resolve against.
    for spec in args.extra_root:
        dir_part, _, var = spec.rpartition(":")
        if not dir_part or not var:
            ap.error(f"--extra-root must be DIR:CMAKEVAR, got {spec!r}")
        root_paths[var] = os.path.abspath(dir_part)
        loaded += _load_root(ev, dir_part, var, ("blueprint-allbp",),
                             label=f"[{var}] ")

    overlay = load_overlay(args.overlay)
    emitter = Emitter(ev, overlay, root_paths)

    # Resolve the module list: explicit --module entries plus the transitive
    # closure of any --root-module entries (deps first).
    from .closure import dependency_closure
    modules: list[str] = list(args.module)
    if args.root_module:
        closure = dependency_closure(ev, overlay, args.root_module)
        for name in closure:
            if name not in modules:
                modules.append(name)
    if not modules:
        ap.error("nothing to emit: pass --module and/or --root-module")

    if args.list_only:
        for name in modules:
            print(name)
        return 0

    chunks = []
    for name in modules:
        m = ev.resolve(name)
        chunks.append(emitter.emit_module(m))

    output = "\n".join(chunks)
    if args.out:
        with open(args.out, "w") as f:
            f.write(output)
        print(f"wrote {args.out} ({len(modules)} modules, {loaded} .bp files loaded)",
              file=sys.stderr)
    else:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
