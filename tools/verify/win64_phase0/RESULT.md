# Win64 Phase 0 — Foundations — RESULT

Date: 2026-07-16  
Gate (win32_port.md Phase 0): **libartbase links** as a Win64 PE DLL.

## Status: **PASSED**

Cross-built on Linux (agent01) with:

- LLVM clang/clang++ + lld 21.1.8  
- `/home/agent/Projects/win64-dev-env` (SDK via xwin, libc++, compiler-rt)  
- `bp2cmake --os windows` + `overlay/port_policy_windows.py`

### Artifacts (`build/win64_phase0/`)

| DLL | Size (approx) | Notes |
|-----|----------------|--------|
| `log.dll` | 28K | write-path liblog |
| `base.dll` | 397K | libbase + fmtlib; `errors_windows.cpp` |
| `nativehelper.dll` | 27K | |
| `ziparchive.dll` | 162K | links static Win64 zlib |
| `artpalette.dll` | 22K | `palette_fake.cc` |
| `artbase.dll` | 373K | `mem_map_windows.cc` + gensrcs operator_out |

All are **PE32+ x86-64** DLLs (`file(1)`).

### Converter / Layer 1

- `Config(os="windows")` activates `target.windows` / drops `not_windows`.
- CLI: `python3 -m bp2cmake --os windows --arch x86_64 ...`
- Unit tests: `test_evaluator.py` **19 passed** (includes windows branch selects).

### Layer 2

- New: [`overlay/port_policy_windows.py`](../../overlay/port_policy_windows.py)

### Compat (Win64)

Under `compat/include/` + `compat/src/win64_posix_stubs.c`:

- `unistd.h`, `dirent.h`, `pthread.h`, `sys/cdefs.h`, `sys/file.h`, `sys/time.h`, `sys/param.h`, `ftw.h`, `sched.h`, `mdvm_win64_prelude.h`
- Stubs: pthread, dirent, flock, pread/pwrite, nftw

### Source patches (Phase 0)

| Location | Change |
|----------|--------|
| Archive `libziparchive/zip_cd_entry_map.h` | bitfields both `uint32_t` for 4-byte pack |
| Archive `liblog/include/android/log.h` | `enum log_id : uint32_t` |
| Archive `liblog/logger.h` | C++ `std::atomic_int` |
| vendor `art/libartbase/base/mem_map.{h,cc}` | `#undef ZeroMemory` on Windows |
| vendor `art/libartbase/base/unix_file/fd_file.cc` | `FdReadOffset=off64_t` on Windows |

Record durable patches under `vendor-patches/` / `archive-patches` as follow-up.

### Reproduce

```bash
source /home/agent/Projects/win64-dev-env/env.sh

# regenerate cmake
cd /home/agent/Projects/dalvikvm-linux
PYTHONPATH=tools/bp2cmake python3 -m bp2cmake \
  --root /home/agent/Projects/MinDalvikVM-Archive/native \
  --overlay overlay/port_policy_windows.py \
  --os windows --arch x86_64 \
  --extra-root vendor:MDVM_ART_ROOT_DIR --exclude-top art \
  --module liblog --module libbase --module libnativehelper \
  --module libziparchive --module libartpalette --module libartbase \
  --out tools/verify/win64_phase0/phase0.cmake

cmake -S tools/verify/win64_phase0 -B build/win64_phase0 -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE=$WIN64_CMAKE_TOOLCHAIN \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build build/win64_phase0
# expect artbase.dll
```

### Not in Phase 0

- Runtime spine (`thread_windows`, VEH, `dalvikvm.exe`) — Phase 1  
- Full libcore / JIT — later phases  
- Native Windows machine e2e (this gate is **link** of libartbase)
