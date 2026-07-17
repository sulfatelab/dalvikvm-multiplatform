# LLP64 pointer / jlong cast audit (Win64)

## Why

Windows x64 uses **LLP64**:

| type | size |
|------|-----:|
| `long` / `unsigned long` | 4 |
| `void*` / `uintptr_t` / `jlong` | 8 |

Any conversion of a **pointer** (or full `jlong` address) through `long` /
`unsigned long` drops the high half. That was **W-020**:

```c
// BAD (truncated on Win64)
return (jlong)(unsigned long)mapAddress;

// GOOD
return ptr_to_jlong(mapAddress);  // via uintptr_t
```

## Product safeguards already in tree

1. **`FileChannelImpl_map0`** returns `ptr_to_jlong(mapAddress)` (W-020 closed).
2. Hybrid openjdk CMake puts **`vendor/libcore/multiplatform/windows/native`**
   first on the include path (`jlong_md.h` with `uintptr_t`).
3. Openjdk C flags include **`-D_LP64=1`** even on Win64 so AOSP `#ifdef _LP64`
   branches take the wide-pointer path if multipath headers are missed.
4. Stock `ojluni/.../jlong_md.h` is hardened to treat `_WIN64` / x86_64 / arm64
   as wide-pointer ABIs (not only `_LP64`).

## How to search

### 1) Text heuristics (fast, whole tree)

```bash
python3 tools/verify/llp64_ptr_cast_audit/scan_text.py
# exit 1 if any HIGH hit remains
```

Looks for:

- `(jlong)(unsigned long)` / `(jlong)(long)`
- `void*` ↔ `(unsigned) long`
- `static_cast` / `reinterpret_cast` of pointer to `long`
- bad `#define ptr_to_jlong ... (int)`

### 2) AST via compile_commands + clang-query

Generate compile DB:

```bash
source $WIN64_DEV_ENV/env.sh
cmake -S tools/verify/win64_libcore_icu -B build/win64_libcore_icu -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE=$WIN64_CMAKE_TOOLCHAIN \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
# optional ART DB:
cmake -S tools/verify/win64_phase1 -B build/win64_phase1 -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE=$WIN64_CMAKE_TOOLCHAIN \
  -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
```

Run:

```bash
tools/verify/llp64_ptr_cast_audit/scan_ast.sh build/win64_libcore_icu
```

Matchers (clang-query):

```
cStyleCastExpr(hasType(asString("long")))
cStyleCastExpr(hasType(asString("unsigned long")))
```

**Caveats:**

- Matches **any** cast to `long` (sizes, ioctl macros, SDK `HandleToLong`).
- Filter matches to `vendor/`, `tools/`, `compat/` paths.
- Implicit conversions are harder; pair with `-Wpointer-to-int-cast`
  / `-Wshorten-64-to-32` on a file’s compile command (replace `-c -o` with
  `-fsyntax-only -Wpointer-to-int-cast`).

### 3) Manual AST dump for one TU

From an entry in `compile_commands.json`, drop `-c -o out` and add:

```bash
...flags... -fsyntax-only -Xclang -ast-dump -fno-color-diagnostics path/to/file.c \
  | rg 'CastExpr|CStyleCastExpr' | rg "long|jlong|void \*"
```

## What “good” looks like

| Operation | Preferred |
|-----------|-----------|
| pointer → `jlong` | `ptr_to_jlong(p)` or `(jlong)(uintptr_t)(p)` |
| `jlong` → pointer | `jlong_to_ptr(j)` or `(T*)(uintptr_t)(j)` |
| size/length → `jlong` | `(jlong)(size_t)n` (not via `long`) |
| Win HANDLE ↔ integer | `UINT_PTR` / `LONG_PTR` / `intptr_t` (not `long`) |

## Related

- W-020 closed: `win32_open_items.md`
- Multipath: `vendor/libcore/multiplatform/windows/native/jlong_md.h`
