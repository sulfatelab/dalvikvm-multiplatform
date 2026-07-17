#!/usr/bin/env python3
"""Full AST LLP64 pointer/jlong cast scan for Windows compile_commands.

Uses libclang to walk every TU in one or more compile_commands.json databases
and report conversions that are unsafe on Win64 LLP64 (long is 32-bit):

  pointer <-> long / unsigned long
  jlong/long long <-> long / unsigned long  (address-width related)
  nested C-style (jlong)(unsigned long)ptr patterns via cast of cast

Usage:
  /tmp/llp64_ast_venv/bin/python tools/verify/llp64_ptr_cast_audit/scan_ast_full.py \
      build/win64_phase1 build/win64_libcore_icu \
      --jobs 32 --out tools/verify/llp64_ptr_cast_audit/FULL_AST_RESULT.md
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from pathlib import Path

# libclang setup done in worker

SKIP_SUFFIX = {".S", ".s", ".asm"}
REPO_HINTS = ("/vendor/", "/tools/", "/compat/", "/native/")


def is_repo_path(path: str, repo: str) -> bool:
    p = path.replace("\\", "/")
    r = repo.replace("\\", "/")
    return p.startswith(r) and any(h in p for h in REPO_HINTS)


def parse_args_from_entry(entry: dict, db_dir: Path) -> list[str] | None:
    if "arguments" in entry:
        args = list(entry["arguments"])
    elif "command" in entry:
        args = shlex.split(entry["command"])
    else:
        return None
    # drop compiler binary
    if args:
        args = args[1:]
    # remove -c / -S / -o <file>
    out: list[str] = []
    skip_next = False
    for a in args:
        if skip_next:
            skip_next = False
            continue
        if a in ("-c", "-S", "-emit-ast"):
            continue
        if a == "-o":
            skip_next = True
            continue
        if a.startswith("-o") and a != "-og":  # -oFILE
            continue
        out.append(a)
    # ensure file path absolute relative to directory if needed
    directory = Path(entry.get("directory") or db_dir)
    f = entry["file"]
    if not Path(f).is_absolute():
        f = str((directory / f).resolve())
    # libclang wants compile args without the source file sometimes; keep file at end
    # Remove trailing source file from args if present
    out2 = []
    for a in out:
        if Path(a).name == Path(f).name and (a.endswith(Path(f).suffix)):
            # likely the source path in argv
            if os.path.basename(a) == os.path.basename(f):
                continue
        out2.append(a)
    return out2


@dataclass
class Hit:
    file: str
    line: int
    col: int
    kind: str
    detail: str
    spelling: str


def type_str(t) -> str:
    try:
        return t.spelling or t.get_canonical().spelling or ""
    except Exception:
        return ""


def is_pointer_type(t) -> bool:
    try:
        k = t.get_canonical().kind
        # TypeKind.POINTER = 101 historically; use name
        name = str(k)
        return "Pointer" in name or "ObjCObjectPointer" in name or "BlockPointer" in name or "MemberPointer" in name
    except Exception:
        s = type_str(t)
        return "*" in s and "long" not in s.split("*")[0]


def is_long_type(t) -> bool:
    s = type_str(t)
    # strip qualifiers/noise
    s2 = " ".join(s.replace("const", " ").replace("volatile", " ").split())
    return s2 in ("long", "unsigned long")


def is_jlongish_type(t) -> bool:
    s = type_str(t)
    s2 = " ".join(s.replace("const", " ").replace("volatile", " ").split())
    return s2 in ("long long", "unsigned long long", "jlong") or s2.endswith(" jlong")


def is_integer_type(t) -> bool:
    try:
        return t.get_canonical().kind.name.startswith("UInt") or t.get_canonical().kind.name.startswith("Int") or "Long" in t.get_canonical().kind.name
    except Exception:
        return False


def location_ok(loc, repo: str) -> bool:
    try:
        if not loc or not loc.file:
            return False
        return is_repo_path(str(loc.file.name), repo)
    except Exception:
        return False



def walk(cursor, repo: str, hits: list[Hit], visited=None, depth: int = 0):
    if visited is None:
        visited = set()
    if depth > 4000:
        return
    try:
        key = cursor.hash
    except Exception:
        key = id(cursor)
    if key in visited:
        return
    visited.add(key)

    try:
        kind = cursor.kind
    except Exception:
        return
    kn = kind.name if hasattr(kind, "name") else str(kind)

    if kn in (
        "CSTYLE_CAST_EXPR",
        "CXX_STATIC_CAST_EXPR",
        "CXX_REINTERPRET_CAST_EXPR",
        "CXX_CONST_CAST_EXPR",
        "CXX_FUNCTIONAL_CAST_EXPR",
        "CXX_DYNAMIC_CAST_EXPR",
        "IMPLICIT_CAST_EXPR",
    ):
        try:
            loc = cursor.location
            if location_ok(loc, repo):
                children = list(cursor.get_children())
                src_t = children[0].type if children else None
                dst_t = cursor.type
                if src_t is not None and dst_t is not None:
                    extent = ""
                    try:
                        extent = (cursor.displayname or cursor.spelling or "")[:160]
                    except Exception:
                        extent = ""
                    if is_pointer_type(src_t) and is_long_type(dst_t):
                        hits.append(Hit(str(loc.file.name), loc.line, loc.column,
                                        "PTR->LONG", f"{type_str(src_t)} -> {type_str(dst_t)}", extent))
                    elif is_long_type(src_t) and is_pointer_type(dst_t):
                        hits.append(Hit(str(loc.file.name), loc.line, loc.column,
                                        "LONG->PTR", f"{type_str(src_t)} -> {type_str(dst_t)}", extent))
                    elif is_jlongish_type(src_t) and is_long_type(dst_t):
                        hits.append(Hit(str(loc.file.name), loc.line, loc.column,
                                        "JLONG->LONG", f"{type_str(src_t)} -> {type_str(dst_t)}", extent))
                    elif is_long_type(src_t) and is_jlongish_type(dst_t):
                        hits.append(Hit(str(loc.file.name), loc.line, loc.column,
                                        "LONG->JLONG", f"{type_str(src_t)} -> {type_str(dst_t)}", extent))
                    if kn != "IMPLICIT_CAST_EXPR" and is_jlongish_type(dst_t):
                        for ch in children:
                            ckn = ch.kind.name if hasattr(ch.kind, "name") else ""
                            if "CAST" in ckn:
                                for g in ch.get_children():
                                    if is_pointer_type(g.type) and is_long_type(ch.type):
                                        hits.append(Hit(str(loc.file.name), loc.line, loc.column,
                                                        "NESTED (jlong)(long)ptr",
                                                        f"{type_str(g.type)} -> {type_str(ch.type)} -> {type_str(dst_t)}",
                                                        extent))
                                        break
        except Exception:
            pass

    try:
        for ch in cursor.get_children():
            walk(ch, repo, hits, visited, depth + 1)
    except Exception:
        pass


def _worker_init(libclang_path: str) -> None:
    import clang.cindex as ci
    if not getattr(ci.Config, "loaded", False):
        try:
            ci.Config.set_library_file(libclang_path)
        except Exception:
            # already configured in this process
            pass


def scan_one(payload: tuple) -> dict:
    file, args, repo, libclang_path = payload
    try:
        import clang.cindex as ci
        try:
            ci.Config.set_library_file(libclang_path)
        except Exception:
            pass
        idx = ci.Index.create()
        # parse
        tu = idx.parse(file, args=args, options=0)
        diags = [d for d in tu.diagnostics if d.severity >= ci.Diagnostic.Error]
        hits: list[Hit] = []
        walk(tu.cursor, repo, hits)
        # dedupe
        seen = set()
        uniq = []
        for h in hits:
            k = (h.file, h.line, h.col, h.kind, h.detail)
            if k in seen:
                continue
            seen.add(k)
            uniq.append(h)
        return {
            "file": file,
            "ok": True,
            "errors": len(diags),
            "hits": [asdict(h) for h in uniq],
            "err": "",
        }
    except Exception as e:
        return {"file": file, "ok": False, "errors": -1, "hits": [], "err": f"{e}\n{traceback.format_exc()[-400:]}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dbs", nargs="+", help="dirs containing compile_commands.json")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 4) // 1))
    ap.add_argument("--out", default="tools/verify/llp64_ptr_cast_audit/FULL_AST_RESULT.md")
    ap.add_argument("--json-out", default="tools/verify/llp64_ptr_cast_audit/FULL_AST_RESULT.json")
    ap.add_argument("--libclang", default="/usr/lib/llvm-21/lib/libclang-21.so.1")
    ap.add_argument("--limit", type=int, default=0, help="debug: max TUs")
    args = ap.parse_args()

    repo = str(Path(".").resolve())
    # merge compile DBs; prefer later entry for same file
    by_file: dict[str, tuple[list[str], str]] = {}
    for db in args.dbs:
        dbp = Path(db)
        ccf = dbp / "compile_commands.json" if dbp.is_dir() else dbp
        data = json.loads(ccf.read_text())
        directory = ccf.parent
        for e in data:
            f = e["file"]
            if not Path(f).is_absolute():
                f = str((Path(e.get("directory") or directory) / f).resolve())
            if Path(f).suffix in SKIP_SUFFIX:
                continue
            a = parse_args_from_entry(e, directory)
            if a is None:
                continue
            by_file[f] = (a, str(ccf))

    items = [(f, a, repo, args.libclang) for f, (a, _) in sorted(by_file.items())]
    if args.limit:
        items = items[: args.limit]
    print(f"Scanning {len(items)} Windows TUs with {args.jobs} jobs...", flush=True)
    t0 = time.time()

    results = []
    # ProcessPool needs picklable; use executor
    import multiprocessing as mp
    ctx = mp.get_context("spawn")
    with ProcessPoolExecutor(max_workers=args.jobs, mp_context=ctx,
                             initializer=_worker_init, initargs=(args.libclang,)) as ex:
        futs = {ex.submit(scan_one, it): it[0] for it in items}
        done = 0
        for fut in as_completed(futs):
            done += 1
            r = fut.result()
            results.append(r)
            if done % 50 == 0 or done == len(items):
                print(f"  progress {done}/{len(items)} elapsed {time.time()-t0:.1f}s", flush=True)

    all_hits = []
    parse_fail = []
    for r in results:
        if not r["ok"]:
            parse_fail.append(r)
        for h in r["hits"]:
            all_hits.append(h)

    # classify severity
    high_kinds = {"PTR->LONG", "LONG->PTR", "NESTED (jlong)(long)ptr"}
    med_kinds = {"JLONG->LONG", "LONG->JLONG"}
    high = [h for h in all_hits if h["kind"] in high_kinds]
    med = [h for h in all_hits if h["kind"] in med_kinds]

    # sort
    def key(h):
        return (0 if h["kind"] in high_kinds else 1, h["file"], h["line"], h["kind"])

    all_hits.sort(key=key)

    # write JSON
    Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.json_out).write_text(json.dumps({
        "tus": len(items),
        "elapsed_sec": time.time() - t0,
        "high": high,
        "med": med,
        "all_hits": all_hits,
        "parse_fail_count": len(parse_fail),
        "parse_fail_sample": parse_fail[:20],
    }, indent=2))

    # markdown
    lines = []
    lines.append("# Full Windows AST LLP64 cast audit\n")
    lines.append(f"- Date: {time.strftime('%Y-%m-%d %H:%M:%S %z')}")
    lines.append(f"- TUs scanned: **{len(items)}**")
    lines.append(f"- Jobs: {args.jobs}")
    lines.append(f"- Elapsed: {time.time()-t0:.1f}s")
    lines.append(f"- HIGH (ptr↔long / nested): **{len(high)}**")
    lines.append(f"- MED (jlong↔long): **{len(med)}**")
    lines.append(f"- Parse failures: {len(parse_fail)}")
    lines.append(f"- DBs: {', '.join(args.dbs)}")
    lines.append("")
    lines.append("## HIGH\n")
    if not high:
        lines.append("_None._\n")
    for h in high:
        rel = h["file"].replace(repo + "/", "")
        lines.append(f"- `{rel}:{h['line']}:{h['col']}` **{h['kind']}** — `{h['detail']}`")
        if h.get("spelling"):
            lines.append(f"  - `{h['spelling'][:200]}`")
    lines.append("\n## MED\n")
    if not med:
        lines.append("_None._\n")
    for h in med:
        rel = h["file"].replace(repo + "/", "")
        lines.append(f"- `{rel}:{h['line']}:{h['col']}` **{h['kind']}** — `{h['detail']}`")
        if h.get("spelling"):
            lines.append(f"  - `{h['spelling'][:200]}`")
    lines.append("\n## Notes\n")
    lines.append("- Only locations under repo `vendor/`, `tools/`, `compat/`, `native/` are reported.")
    lines.append("- SDK/header casts (e.g. basetsd HandleToLong) are excluded by path filter.")
    lines.append("- `LONG->JLONG` may be benign integer widen; review if operand is a pointer bits.")
    lines.append("- Prefer `ptr_to_jlong` / `jlong_to_ptr` / `uintptr_t`.\n")
    Path(args.out).write_text("\n".join(lines) + "\n")
    print(f"Wrote {args.out} and {args.json_out}")
    print(f"HIGH={len(high)} MED={len(med)} fail={len(parse_fail)}")
    return 1 if high else 0


if __name__ == "__main__":
    sys.exit(main())
