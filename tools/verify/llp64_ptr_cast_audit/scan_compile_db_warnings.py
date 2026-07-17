#!/usr/bin/env python3
"""Full Windows-path LLP64 scan via compile_commands + clang frontend warnings.

This is the practical LibTooling-class approach without writing a custom binary:
for every TU in the Win64 compile DBs, re-run the same flags with
  -fsyntax-only
  -Wvoid-pointer-to-int-cast
  -Wint-to-void-pointer-cast
  -Wshorten-64-to-32 (optional noise)

Clang only emits void-pointer-to-int / int-to-void-pointer when the integer
type is *smaller* than a pointer — exactly the LLP64 long/unsigned long trap.

Usage:
  python3 tools/verify/llp64_ptr_cast_audit/scan_compile_db_warnings.py \
    build/win64_phase1 build/win64_libcore_icu --jobs 32 \
    --out tools/verify/llp64_ptr_cast_audit/FULL_AST_RESULT.md
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

WARN_RE = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+): warning: (?P<msg>.*) \[(?P<flag>[^\]]+)\]"
)
INTERESTING = {
    "-Wvoid-pointer-to-int-cast",
    "-Wint-to-void-pointer-cast",
    # optional:
    # "-Wshorten-64-to-32",
}


def load_db(path: Path) -> list[dict]:
    data = json.loads(path.read_text())
    out = []
    for e in data:
        f = e["file"]
        directory = Path(e.get("directory") or path.parent)
        if not Path(f).is_absolute():
            f = str((directory / f).resolve())
        if Path(f).suffix.lower() in {".s", ".S", ".asm"}:
            continue
        if "arguments" in e:
            args = list(e["arguments"])
        else:
            args = shlex.split(e["command"])
        out.append({"file": f, "directory": str(directory), "args": args})
    return out


def build_cmd(entry: dict, extra: list[str]) -> list[str]:
    args = entry["args"][:]
    # drop compiler is first
    # remove -c -S -o out
    new = []
    skip = False
    for a in args:
        if skip:
            skip = False
            continue
        if a in ("-c", "-S", "-emit-ast"):
            continue
        if a == "-o":
            skip = True
            continue
        if a.startswith("-o") and not a.startswith("-og") and not a.startswith("-object"):
            # -oFILE
            if len(a) > 2 and not a.startswith("-opt"):
                continue
        new.append(a)
    # strip trailing source path duplicates later
    # append warnings + fsyntax-only + file
    cmd = new + extra + ["-fsyntax-only", entry["file"]]
    return cmd


def run_one(entry: dict, repo: str) -> dict:
    extra = [
        "-Wno-everything",
        "-Wvoid-pointer-to-int-cast",
        "-Wint-to-void-pointer-cast",
    ]
    cmd = build_cmd(entry, extra)
    try:
        r = subprocess.run(
            cmd,
            cwd=entry["directory"],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception as e:
        return {"file": entry["file"], "ok": False, "err": str(e), "hits": []}

    hits = []
    text = (r.stderr or "") + "\n" + (r.stdout or "")
    for line in text.splitlines():
        m = WARN_RE.match(line.strip())
        if not m:
            continue
        flag = m.group("flag")
        if flag not in INTERESTING and not flag.endswith("void-pointer-to-int-cast") and not flag.endswith("int-to-void-pointer-cast"):
            continue
        f = m.group("file")
        # normalize
        if not Path(f).is_absolute():
            f = str((Path(entry["directory"]) / f).resolve())
        # only repo product paths
        fr = f.replace("\\", "/")
        if repo not in fr:
            continue
        if not any(x in fr for x in ("/vendor/", "/tools/", "/compat/", "/native/")):
            continue
        hits.append({
            "file": f,
            "line": int(m.group("line")),
            "col": int(m.group("col")),
            "flag": flag,
            "msg": m.group("msg"),
            "kind": "PTR->INT" if "void-pointer-to-int" in flag else "INT->PTR",
        })
    return {"file": entry["file"], "ok": True, "err": "", "hits": hits, "rc": r.returncode}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dbs", nargs="+")
    ap.add_argument("--jobs", type=int, default=max(4, (os.cpu_count() or 8)))
    ap.add_argument("--out", default="tools/verify/llp64_ptr_cast_audit/FULL_AST_RESULT.md")
    ap.add_argument("--json-out", default="tools/verify/llp64_ptr_cast_audit/FULL_AST_RESULT.json")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    repo = str(Path(".").resolve())
    by_file: dict[str, dict] = {}
    for db in args.dbs:
        p = Path(db)
        ccf = p / "compile_commands.json" if p.is_dir() else p
        for e in load_db(ccf):
            by_file[e["file"]] = e
    items = [by_file[k] for k in sorted(by_file)]
    if args.limit:
        items = items[: args.limit]

    print(f"LibTooling-class frontend scan: {len(items)} TUs, jobs={args.jobs}", flush=True)
    t0 = time.time()
    results = []
    hits_all = []
    fails = 0

    # Thread pool is fine: clang is the heavy process
    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        futs = {ex.submit(run_one, e, repo): e["file"] for e in items}
        done = 0
        for fut in as_completed(futs):
            done += 1
            r = fut.result()
            results.append(r)
            if not r["ok"]:
                fails += 1
            hits_all.extend(r["hits"])
            if done % 25 == 0 or done == len(items):
                print(f"  progress {done}/{len(items)} elapsed {time.time()-t0:.1f}s hits={len(hits_all)}", flush=True)

    # dedupe
    seen = set()
    uniq = []
    for h in hits_all:
        k = (h["file"], h["line"], h["col"], h["flag"], h["msg"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(h)
    uniq.sort(key=lambda h: (h["kind"], h["file"], h["line"]))

    high = [h for h in uniq if h["kind"] in ("PTR->INT", "INT->PTR")]
    Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.json_out).write_text(json.dumps({
        "method": "clang-frontend -Wvoid-pointer-to-int-cast / -Wint-to-void-pointer-cast",
        "tus": len(items),
        "elapsed_sec": time.time() - t0,
        "high": high,
        "med": [],
        "all_hits": uniq,
        "parse_fail_count": fails,
        "dbs": args.dbs,
    }, indent=2))

    lines = []
    lines.append("# Full Windows AST LLP64 cast audit (compile_commands + clang frontend)\n")
    lines.append(f"- Method: **LibTooling-class** re-run of each Win64 `compile_commands` TU with")
    lines.append(f"  `-fsyntax-only -Wvoid-pointer-to-int-cast -Wint-to-void-pointer-cast`")
    lines.append(f"  (Clang only warns when integer is smaller than pointer — LLP64 `long` trap).")
    lines.append(f"- TUs: **{len(items)}**")
    lines.append(f"- Elapsed: {time.time()-t0:.1f}s")
    lines.append(f"- Hits (repo vendor/tools/compat/native only): **{len(uniq)}**")
    lines.append(f"- Worker failures: {fails}")
    lines.append(f"- DBs: {', '.join(args.dbs)}")
    lines.append("")
    lines.append("## Findings\n")
    if not uniq:
        lines.append("_None. No void*/smaller-integer casts in product repo paths._\n")
    else:
        for h in uniq:
            rel = h["file"].replace(repo + "/", "")
            lines.append(
                f"- `{rel}:{h['line']}:{h['col']}` **{h['kind']}** `{h['flag']}` — {h['msg']}"
            )
    lines.append("\n## Notes\n")
    lines.append("- This is stronger than regex: uses Clang's type size model on the real Win triple.")
    lines.append("- System SDK hits (basetsd HandleToLong) are filtered by path.")
    lines.append("- Pair with `scan_text.py` for `(jlong)(unsigned long)` spelling patterns.")
    lines.append("- Optional custom LibTooling binary: see `llp64_cast_tool/` if libclang-*-dev is installed.\n")
    Path(args.out).write_text("\n".join(lines) + "\n")
    print(f"Wrote {args.out} hits={len(uniq)} fails={fails}")
    return 1 if uniq else 0


if __name__ == "__main__":
    sys.exit(main())
