#!/usr/bin/env python3
"""LLP64 pointer/jlong truncation audit (text heuristics).

Windows x64 is LLP64: sizeof(long)==4, sizeof(void*)==8. Casting a pointer or
jlong through long/unsigned long truncates the high 32 bits (W-020 FileChannel
map0). This scanner finds explicit/implicit *looking* conversion sites in
.c/.cc/.cpp/.h/.hpp via regex heuristics.

For AST precision, use scan_ast.sh with compile_commands.json + clang-query.

Usage:
  python3 tools/verify/llp64_ptr_cast_audit/scan_text.py [root ...]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

DEFAULT_ROOTS = [
    "vendor/libcore",
    "vendor/art",
    "tools/win64",
    "tools/verify/win64_libcore_icu",
    "compat",
]
EXTS = {".c", ".cc", ".cpp", ".h", ".hpp"}
SKIP_RE = re.compile(r"/(test|tests|googletest|third_party|\.git|build)/")

# High-precision W-020-class patterns
HIGH = [
    (re.compile(r"\(\s*jlong\s*\)\s*\(\s*unsigned\s+long\s*\)"),
     "HIGH jlong <- (unsigned long)  [W-020 class]"),
    (re.compile(r"\(\s*jlong\s*\)\s*\(\s*long\s*\)"),
     "HIGH jlong <- (long)"),
    (re.compile(r"\(\s*void\s*\*\s*\)\s*\(\s*(?:unsigned\s+)?long\s*\)"),
     "HIGH void* <- (long)"),
    (re.compile(r"\(\s*(?:unsigned\s+)?long\s*\)\s*\(\s*void\s*\*\s*\)"),
     "HIGH (long) <- void*"),
    (re.compile(r"static_cast\s*<\s*jlong\s*>\s*\(\s*\(?\s*(?:unsigned\s+)?long\b"),
     "HIGH static_cast<jlong>(long)"),
    (re.compile(r"reinterpret_cast\s*<\s*jlong\s*>\s*\(\s*\(?\s*(?:unsigned\s+)?long\b"),
     "HIGH reinterpret_cast<jlong>(long)"),
    (re.compile(r"reinterpret_cast\s*<\s*(?:unsigned\s+)?long\s*>\s*\(\s*.*\*"),
     "HIGH reinterpret_cast<long>(pointer-ish)"),
    (re.compile(r"static_cast\s*<\s*(?:unsigned\s+)?long\s*>\s*\(\s*.*\*"),
     "HIGH static_cast<long>(pointer-ish)"),
    (re.compile(r"#\s*define\s+ptr_to_jlong\s*\([^)]*\)\s*\(\s*\(\s*jlong\s*\)\s*\(\s*int\s*\)"),
     "HIGH BAD ptr_to_jlong via int"),
    (re.compile(r"#\s*define\s+jlong_to_ptr\s*\([^)]*\)\s*\(\s*\(\s*void\s*\*\s*\)\s*\(\s*int\s*\)"),
     "HIGH BAD jlong_to_ptr via int"),
]

# Medium: cast to long near pointer/jlong vocabulary
MED_CAST = re.compile(r"\(\s*(?:unsigned\s+)?long\s*\)\s*[A-Za-z_&*][\w\-><\.\(\)]*")
PTRISH = re.compile(
    r"\b(ptr|addr|address|map|handle|base|buf|pointer|Native|mmap|MapView|"
    r"GetDirect|capacity|jlong_to_ptr|ptr_to_jlong|p[A-Z]\w*)\b",
    re.I,
)
NOISE = re.compile(
    r"printf|snprintf|StringPrintf|fprintf|LOG\(|PLOG|tv_sec|tv_usec|tv_nsec|"
    r"version|Version|pid\b|errno|i2d_|d2i_|fread|fileCount|hash|BYTEORDER|"
    r"sizeof\s*\(|IOC_|\bULONG\b|dwMajor|dwMinor|dwBuild",
    re.I,
)

# Good helpers (informational)
GOOD = re.compile(r"\b(ptr_to_jlong|jlong_to_ptr)\s*\(")


def scan_file(path: Path) -> list[tuple[str, int, str, str]]:
    try:
        lines = path.read_text(errors="ignore").splitlines()
    except OSError:
        return []
    out: list[tuple[str, int, str, str]] = []
    for i, line in enumerate(lines, 1):
        code = line.split("//")[0]
        for cre, label in HIGH:
            if cre.search(code):
                out.append((label, i, line.strip()[:240], str(path)))
        if GOOD.search(code):
            out.append(("INFO safe helper", i, line.strip()[:240], str(path)))
        if MED_CAST.search(code) and PTRISH.search(code) and not NOISE.search(code):
            # skip pure (long)0 / (long)literal
            if re.search(r"\(\s*(?:unsigned\s+)?long\s*\)\s*-?\d", code):
                continue
            out.append(("MED cast-to-long near ptrish", i, line.strip()[:240], str(path)))
    return out


def main(argv: list[str]) -> int:
    roots = [Path(a) for a in argv[1:]] or [Path(r) for r in DEFAULT_ROOTS]
    hits: list[tuple[str, int, str, str]] = []
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if p.suffix not in EXTS:
                continue
            s = str(p).replace("\\", "/")
            if SKIP_RE.search("/" + s + "/"):
                continue
            hits.extend(scan_file(p))

    # Dedup, sort HIGH first
    def rank(label: str) -> int:
        if label.startswith("HIGH"):
            return 0
        if label.startswith("MED"):
            return 1
        return 2

    seen = set()
    uniq = []
    for h in hits:
        k = (h[0], h[3], h[1])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(h)
    uniq.sort(key=lambda h: (rank(h[0]), h[3], h[1]))

    high = [h for h in uniq if h[0].startswith("HIGH")]
    med = [h for h in uniq if h[0].startswith("MED")]
    info = [h for h in uniq if h[0].startswith("INFO")]

    print(f"LLP64 text audit: roots={[str(r) for r in roots]}")
    print(f"  HIGH={len(high)}  MED={len(med)}  INFO safe-helper sites={len(info)}")
    print()
    for label, ln, text, path in high + med:
        print(f"{label}")
        print(f"  {path}:{ln}: {text}")
        print()
    if not high and not med:
        print("No HIGH/MED hits in scoped trees.")
    return 1 if high else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
