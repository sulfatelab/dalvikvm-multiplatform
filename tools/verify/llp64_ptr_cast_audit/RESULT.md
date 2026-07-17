# LLP64 pointer/jlong cast audit — RESULT

**Date:** 2026-07-17  
**Scope:** product-critical C/C++ (`vendor/libcore`, `vendor/art`, `tools/win64`, `tools/verify/win64_libcore_icu`, `compat`)  
**Compile DB:** `build/win64_libcore_icu/compile_commands.json`, `build/win64_phase1/compile_commands.json`  
**Motivation:** Win64 LLP64 `long` is 32-bit; W-020 was `(jlong)(unsigned long)mapAddress`.

## Method

1. **Text scanner** `scan_text.py` — high-precision patterns for pointer/`jlong` ↔ `long`/`unsigned long`.
2. **clang-query** `scan_ast.sh` — `cStyleCastExpr(hasType(asString("long"|"unsigned long")))` against compile_commands (noisy: SDK `HandleToLong`, ioctl macros).
3. **Manual review** of `jlong_md.h` / multipath include order / FileChannelImpl_map0.
4. Confirmed product openjdk flags: multipath include **first**, `-D_LP64=1`.

## Findings

### Closed / fixed (this audit)

| Item | Status |
|------|--------|
| W-020 `FileChannelImpl_map0` | Already fixed: `return ptr_to_jlong(mapAddress)` |
| Stock `ojluni/jlong_md.h` non-`_LP64` branch used `(int)` for ptr | **Hardened** to `_WIN64`/`x86_64`/… + `uintptr_t` |
| Multipath `jlong_md.h` | Confirmed `uintptr_t`; documentation comment refreshed |

### Text scan (post-fix)

```
HIGH=0  MED=0  INFO safe-helper sites≈119 (ptr_to_jlong/jlong_to_ptr usage)
```

No remaining `(jlong)(unsigned long)` / `(jlong)(long)` / `void*`↔`long` patterns in scoped trees.

### Not bugs (reviewed noise)

| Site | Why OK |
|------|--------|
| `Float.c` / `ObjectInputStream.c` `(long)v` | Float bit pattern / IEEE bits, not pointers |
| SDK `basetsd.h` `HandleToLong` | Windows HANDLE truncation APIs (not our code) |
| boringssl/icu `static_cast<long>(len)` for ASN.1 | Lengths in API, not pointers |
| printf `%lu` with `(unsigned long)version` | Integers only |

### Residual risk (monitor)

1. **New code** that copies AOSP `(jlong)(unsigned long)` idioms without multipath `ptr_to_jlong`.
2. **Implicit** conversions hard to regex; prefer compile with `-Wpointer-to-int-cast` / review any new mmap/JNI address returns.
3. **ART** heap pointers already use 64-bit types extensively; scanner found no HIGH hits under `vendor/art` product paths.

## How to re-run

```bash
python3 tools/verify/llp64_ptr_cast_audit/scan_text.py
# optional AST:
source $WIN64_DEV_ENV/env.sh
cmake -S tools/verify/win64_libcore_icu -B build/win64_libcore_icu -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE=$WIN64_CMAKE_TOOLCHAIN -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
tools/verify/llp64_ptr_cast_audit/scan_ast.sh build/win64_libcore_icu
```

## clang-query recipes

```text
# Casts whose result type is long (filter to repo paths)
m cStyleCastExpr(hasType(asString("long"))).bind("c")
m cStyleCastExpr(hasType(asString("unsigned long"))).bind("c")
```

Pair with text scan; AST alone is not sufficient (SDK false positives; implicit casts).

## Recommended project rule

**Never** convert pointer/`jlong` addresses through `long`/`unsigned long` on Win64.  
Always use `uintptr_t` / `ptr_to_jlong` / `jlong_to_ptr` / `LONG_PTR`/`UINT_PTR` as appropriate.
