# LLP64 pointer/jlong cast audit — RESULT

**Date:** 2026-07-17 22:56:00  
**Scope:** **full Windows build path** (all TUs in Win64 compile DBs), not only libcore  
**Compile DBs:**
- `build/win64_phase1/compile_commands.json` (ART / phase1)
- `build/win64_libcore_icu/compile_commands.json` (libcore / ICU / openjdk natives)
**Union TUs scanned:** **1426**  
**Motivation:** Win64 LLP64 `long` is 32-bit; W-020 was `(jlong)(unsigned long)mapAddress`.

## Method

1. **Text scanner** `scan_text.py` — high-precision patterns for pointer/`jlong` ↔ `long`/`unsigned long` under product trees.
2. **Full frontend scan** `scan_compile_db_warnings.py` — LibTooling-class re-run of every Win64 `compile_commands` TU with:
   - triple/flags from the real compile DB (`x86_64-pc-windows-msvc`)
   - `-fsyntax-only -Wvoid-pointer-to-int-cast -Wint-to-void-pointer-cast`
   - Clang only warns when the integer type is **smaller than a pointer** → catches LLP64 `long`/`unsigned long` traps.
   - jobs=16 (jobs=32 previously OOM'd; confirmed via `dmesg`)
3. **clang-query** `scan_ast.sh` / experimental `scan_ast_full.py` — noisier AST matchers (SDK `HandleToLong`, ioctl macros); not primary evidence.
4. **Manual review** of `jlong_md.h` / multipath include order / FileChannelImpl_map0.
5. Confirmed product openjdk flags: multipath include **first**, `-D_LP64=1`.

## Full Windows frontend scan (authoritative)

```
Method: clang frontend -Wvoid-pointer-to-int-cast / -Wint-to-void-pointer-cast
TUs: 1426
Elapsed: ~560.8s (jobs=16)
Hits (repo vendor/tools/compat/native only): 0
Worker failures: 0
```

Artifacts:
- `tools/verify/llp64_ptr_cast_audit/FULL_AST_RESULT.md`
- `tools/verify/llp64_ptr_cast_audit/FULL_AST_RESULT.json`

**Conclusion:** No product-path `void*` ↔ smaller-integer casts remain on the full Win64 compile graph.

## Findings

### Closed / fixed (this audit)

| Item | Status |
|------|--------|
| W-020 `FileChannelImpl_map0` | Already fixed: `return ptr_to_jlong(mapAddress)` |
| Stock `ojluni/jlong_md.h` non-`_LP64` branch used `(int)` for ptr | **Hardened** to `_WIN64`/`x86_64`/… + `uintptr_t` |
| Multipath `jlong_md.h` | Confirmed `uintptr_t`; documentation comment refreshed |

### Text scan (post-fix)

```
HIGH=0  MED=0  INFO safe-helper sites=119 (ptr_to_jlong/jlong_to_ptr usage)
```

No remaining `(jlong)(unsigned long)` / `(jlong)(long)` / `void*`↔`long` spelling patterns in scoped trees.

### Not bugs (reviewed noise from earlier text/AST)

| Site | Why OK |
|------|--------|
| `Float.c` / `ObjectInputStream.c` `(long)v` | Float bit pattern / IEEE bits, not pointers |
| SDK `basetsd.h` `HandleToLong` | Windows HANDLE truncation APIs (not our code; path-filtered) |
| boringssl/icu `static_cast<long>(len)` for ASN.1 | Lengths in API, not pointers |
| printf `%lu` with `(unsigned long)version` | Integers only |
| conscrypt time `static_cast<long>(milliseconds*1000)` | Duration, not pointer |

### Residual risk (monitor)

1. **New code** that copies AOSP `(jlong)(unsigned long)` idioms without multipath `ptr_to_jlong`.
2. **Non-void pointer** casts to `long` (e.g. `char*` → `long`) may not always trip `-Wvoid-pointer-to-int-cast`; keep text scanner + code review for address returns.
3. **Host tools** under third_party (not product DLL path) may still use `long` for lengths — out of product scope unless linked into Win ART.

## How to re-run

```bash
# Fast text heuristics
python3 tools/verify/llp64_ptr_cast_audit/scan_text.py

# Full Windows compile-graph frontend scan (recommended)
# Prefer jobs=16 on this host; jobs=32 OOM'd previously.
python3 -u tools/verify/llp64_ptr_cast_audit/scan_compile_db_warnings.py \
  build/win64_phase1 build/win64_libcore_icu \
  --jobs 16 \
  --out tools/verify/llp64_ptr_cast_audit/FULL_AST_RESULT.md \
  --json-out tools/verify/llp64_ptr_cast_audit/FULL_AST_RESULT.json

# Optional clang-query (noisy):
source $WIN64_DEV_ENV/env.sh
cmake -S tools/verify/win64_libcore_icu -B build/win64_libcore_icu -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE=$WIN64_CMAKE_TOOLCHAIN -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
tools/verify/llp64_ptr_cast_audit/scan_ast.sh build/win64_libcore_icu
```

## Recommended project rule

**Never** convert pointer/`jlong` addresses through `long`/`unsigned long` on Win64.  
Always use `uintptr_t` / `ptr_to_jlong` / `jlong_to_ptr` / `LONG_PTR`/`UINT_PTR` as appropriate.
