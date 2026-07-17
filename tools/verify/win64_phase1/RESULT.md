# Win64 Phase 1 — Skeleton VM — RESULT

Date: 2026-07-16  
Gate (win64_art_port.md Phase 1 / acceptance **A2**):  
`dalvikvm.exe -showversion` prints ART version on PE32+ (verified under wine64).

## Status: **PASSED**

Cross-built on Linux (`agent01`) with:

- LLVM clang/clang++ + lld 21 (triple `x86_64-pc-windows-msvc`)
- `/home/agent/Projects/win64-dev-env` (Windows SDK via xwin, libc++, compiler-rt)
- Harness: `tools/verify/win64_phase1/` + `overlay/port_policy_windows.py`
- No MSVC `cl`/`clang-cl`, no MinGW, no WSL product path

### Gate command / output

```bash
source /home/agent/Projects/win64-dev-env/env.sh
# after build + stage c++.dll next to PE
cd build/win64_phase1
cp -f $WIN64_DEV_ENV/lib/libcxx/lib/c++.dll .
WINEDEBUG=-all wine64 ./dalvikvm.exe -showversion
# ART version 2.1.0 x86_64
```

Recorded log: [`showversion.log`](showversion.log)

### Artifacts (`build/win64_phase1/`)

| Binary | Size (approx) | Notes |
|--------|----------------|--------|
| `dalvikvm.exe` | 22K | PE32+ console; loads `art.dll` via JNI invocation |
| `art.dll` | 17M | Full ART runtime + compiler objects linked |
| `nativehelper.dll` | 33K | Defaults to `art.dll` on `_WIN32` |
| `sigchain.dll` | 12K | Windows stub |
| `base.dll` / `log.dll` / `ziparchive.dll` / … | various | Phase 0 deps |
| `c++.dll` | 1.2M | Deploy next to exe (from win64-dev-env) |

`file(1)`: PE32+ x86-64 for `dalvikvm.exe` and `art.dll`.

### What Phase 1 delivered

- Nearly all ART C++/asm objects compile for Win64.
- PE asm: ELF-only directives treated like Apple; no bare `ASM_HIDDEN` on Windows.
- `ART_USE_FUTEXES` + `WaitOnAddress` backend.
- POSIX stubs (`compat/src/win64_posix_stubs.c`) + force-included `mdvm_win64_prelude.h`.
- Static intermediate libs for artbase/dexfile/profile/unwindstack (DLL data-export issues avoided).
- Windows cpu_features (`impl_x86_windows.c`).
- Runtime instance load for asm via `art_Runtime_instance_ptr` / `LOAD_RUNTIME_INSTANCE` PE path.

### Critical fixes for A2

| Issue | Fix |
|-------|-----|
| `unistd.h` `#define write _write` poisoned `std::ostream::write` → link error `_write` | Removed CRT name macros; rely on UCRT non-STDC declarations |
| `JniInvocation` defaulted to `libart.so` | `_WIN32` defaults: `art.dll` / `artd.dll` in archive `libnativehelper/JniInvocation.c` |
| `DlHelp` Windows path | `LoadLibraryA` / includes hardened in `DlHelp.c` |
| Linux ldflags (`-z max-page-size`) | Stripped in port policy + harness |
| Missing POSIX symbols | Stubs for mremap/msync/fcntl/realpath/pthread_getname_np, etc. |

### Reproduce

```bash
source /home/agent/Projects/win64-dev-env/env.sh
cd /home/agent/Projects/dalvikvm-multiplatform

cmake -S tools/verify/win64_phase1 -B build/win64_phase1 -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE=$WIN64_CMAKE_TOOLCHAIN \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo

cmake --build build/win64_phase1 --target art dalvikvm -j"$(nproc)"

cd build/win64_phase1
cp -f "$WIN64_DEV_ENV/lib/libcxx/lib/c++.dll" .
WINEDEBUG=-all wine64 ./dalvikvm.exe -showversion
```

### Not in Phase 1 (next)

- Imageless boot + Hello.main (Phase 2 / A3)
- Real fault handling (VEH) beyond stubs
- Full interpreter correctness, GC/heap bring-up on Windows
- libcore natives matrix (Phase 3)
- JIT productization (Phase 5)

### Source / tree touch points

| Path | Role |
|------|------|
| `tools/verify/win64_phase1/` | CMake harness |
| `overlay/port_policy_windows.py` | Windows Layer 2 |
| `compat/include/*`, `compat/src/win64_posix_stubs.c` | POSIX/CRT bridge |
| `vendor/art/runtime/multiplatform/windows/*` | thread/runtime/monitor/sigchain stubs |
| Archive `libnativehelper/JniInvocation.c`, `DlHelp.c` | PE library load name + LoadLibraryA |
| `vendor/art/runtime/base/mutex-inl.h` | WaitOnAddress futex path |
| `vendor/art/runtime/arch/x86_64/asm_support_x86_64.S` | PE `LOAD_RUNTIME_INSTANCE` |
