# Win64 real ICU PE — RESULT

**Date:** 2026-07-17  
**Status:** **Phase A PARTIAL SUCCESS** — real `icuuc.dll` + `icui18n.dll` + `icu_jni.dll` cross-built

## What built

| DLL | Approx size | Notes |
|-----|-------------|--------|
| `icuuc.dll` | ~2.0M | ICU4C common; stubdata object linked into DLL; no `libandroidicuinit` |
| `icui18n.dll` | ~3.4M | ICU4C i18n |
| `icu_jni.dll` | (built) | Real `android_icu4j` libcore_bridge natives (NativeConverter, ICU4CMetadata, …) |

Harness: `tools/verify/win64_libcore_icu/`  
Configure/build:

```bash
source $WIN64_DEV_ENV/env.sh
cmake -S tools/verify/win64_libcore_icu -B build/win64_libcore_icu -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE=$WIN64_CMAKE_TOOLCHAIN -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build build/win64_libcore_icu -j$(nproc)
```

## Staging into ART package

```bash
cp build/win64_libcore_icu/{icuuc,icui18n,icu_jni}.dll build/win64_phase1/
cp build/win64_libcore_icu/icu_jni.dll build/win64_phase1/libicu_jni.dll
# javacore/openjdk still from jni_stubs/libcombined until Phase B
```

## Not done (Phase B+)

- Real `libjavacore.dll` / `libopenjdk.dll` (still `libcombined` stubs) — L-001 / W-005
- Full ICU data load path vs stubdata (file `ICU_DATA` / `icudt*.dat` packaging verification)
- Drop dual-name staging once ART load names settle
- Wire install into `package_win64_phase3.sh`

## Compat fixes landed for this work

- `compat/include/unistd.h` — `typedef int pid_t` on Win32
- `compat/include/byteswap.h` — new shim for ICU bridge sources

## Phase B0 — hybrid `javacore.dll` (2026-07-17)

**Status:** **BUILT + wine smoke OK** (CoreProbe, IoProbe)

| Piece | Approach |
|-------|----------|
| AOSP `Register.cpp`, ICU helpers, MethodHandle/VarHandle, NativeAllocationRegistry | Real sources |
| `libcore.io.Linux` | **Excluded** AOSP `libcore_io_Linux.cpp`; Win bridge registers ~50 methods from `win_fs`/`win_net` stubs |
| WinNT FS / sockets / OsConstants init | Same PE stub C sources linked into `javacore.dll` |
| Expat, NativeBN, Memory, NetworkUtilities, AsyncClose, full OsConstantsHolder | **Not yet** (empty register stubs / deferred) |
| `libopenjdk.dll` | Still pure `libcombined` alias |

Artifact: `build/win64_libcore_icu/javacore.dll` (~92K)

### Smoke

```
showversion → ART version 2.1.0 x86_64
CoreProbe.done=ok
IoProbe.done=ok
```
