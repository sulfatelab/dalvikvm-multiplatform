"""CLI for the codegen driver: stage the gensrc/ tree.

Usage:
    python3 -m bp2cmake.codegen_main --root <native-root> --gensrc <out-dir> \
        [--arch x86_64] [--clang clang++] [--only operator_out|mterp|asm_defines]
"""

from __future__ import annotations

import argparse
import sys

from .codegen import CodegenConfig, CodegenError, run_all, gen_mterp, gen_asm_defines, gen_aconfig


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bp2cmake.codegen")
    ap.add_argument("--root", required=True, help="native source root")
    ap.add_argument("--art-root", default="", help="bumped art tree root (art/* inputs)")
    ap.add_argument("--libcore-root", default="", help="libcore tree root (libcore.aconfig)")
    ap.add_argument("--gensrc", required=True, help="output gensrc dir")
    ap.add_argument("--arch", default="x86_64")
    ap.add_argument("--clang", default="clang++")
    ap.add_argument("--only", choices=["operator_out", "mterp", "asm_defines", "aconfig"],
                    help="run only one generation kind")
    args = ap.parse_args(argv)

    cfg = CodegenConfig(native_root=args.root, gensrc_dir=args.gensrc,
                        arch=args.arch, clang=args.clang, art_root=args.art_root,
                        libcore_root=args.libcore_root)
    try:
        if args.only == "mterp":
            print("mterp:", gen_mterp(cfg))
        elif args.only == "asm_defines":
            print("asm_defines:", gen_asm_defines(cfg))
        elif args.only == "aconfig":
            print("aconfig:", ", ".join(gen_aconfig(cfg)) or "(none)")
        elif args.only == "operator_out":
            rep = run_all(cfg, do_mterp=False, do_asm_defines=False, do_aconfig=False)
            print(f"operator_out: {len(rep['operator_out'])} files")
        else:
            rep = run_all(cfg)
            print(f"aconfig: {len(rep['aconfig'])} files")
            print(f"operator_out: {len(rep['operator_out'])} files")
            print(f"mterp: {rep['mterp']}")
            print(f"asm_defines: {rep['asm_defines']}")
    except CodegenError as e:
        print(f"codegen failed: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
