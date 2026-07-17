# Win64 real ICU PE — RESULT

**Date:** 2026-07-17  
**Status:** **Phase A–B2 SUCCESS for product PE** — real ICU + hybrid javacore + AOSP openjdk NIO; **W-005 CLOSED** (no libcombined product aliases)

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

## Phase B1 — hybrid `openjdk.dll` (2026-07-17)

**Status:** **BUILT + wine smoke OK** (CoreProbe, IoProbe)

| Piece | Approach |
|-------|----------|
| Zip Inflater/Deflater/CRC/Adler | Real AOSP ojluni |
| Float/Double, Object streams, Character, jdk.internal.misc.VM | Real AOSP |
| System/Runtime/math/time | PE stubs (`libcore_hello3` + `win_runtime_natives`) |
| `JVM_*` memory helpers | Standalone `openjdkjvm.dll` (process memory heuristics; not full ART heap yet) |
| NIO/EPoll/Unix FS/process | **Not included** (classic Socket via javacore Win bridge) |

Artifact: `build/win64_libcore_icu/openjdk.dll` (~113K), `openjdkjvm.dll` (~13K)

### Smoke (with real ICU + hybrid javacore + hybrid openjdk)

```
showversion OK
CoreProbe.done=ok
IoProbe.done=ok
```


## Phase B2 — AOSP openjdk Unix/NIO surface (2026-07-17)

**Status:** **BUILT + wine smoke OK** (CoreProbe, IoProbe with `ICU_DATA=run/icu`)

| Piece | Approach |
|-------|----------|
| NIO channels (`Net`, `SocketChannel`, `ServerSocketChannel`, `Datagram*`, `FileChannel`/`FileDispatcher`, `IOUtil`, `EPoll`, `PollArrayWrapper`, streams) | Real AOSP ojluni sources |
| CRT fd ↔ Winsock + select-based epoll | `compat/src/win64_socket_posix.c` + improved `poll`/`ioctl`/`fcntl` |
| `linux_close` / async-close / NativeThread | Win bridges under `vendor/libcore/multiplatform/windows/native/` |
| `JVM_*` I/O + socket helpers | Expanded `openjdkjvm_memory_standalone.c` |
| NIO.2 `sun.nio.fs` / async ports / UNIXProcess / UnixFileSystem_md | **Excluded** (non-goal / WinNT FS via javacore) |
| System/Runtime | Still PE stubs (`hello3` / `win_runtime`) |

Artifacts: `openjdk.dll` (~208K), `openjdkjvm.dll` (~38K)

### Smoke

```
ICU_DATA=run/icu  # required: full icudt72l.dat under run/icu (stubdata alone → U_FILE_ACCESS_ERROR)
showversion OK
CoreProbe.done=ok
IoProbe.done=ok
NetProbe.done=ok (after W-018 linger get/set in win_net_natives)
```

### ICU note

`icu_jni` `Register.cpp` now calls `udata_setCommonData(&U_ICUDATA_ENTRY_POINT)` on Windows; product smoke still needs **`ICU_DATA=run/icu`** with real `icudt72l.dat` until full data is embedded or path is hard-wired.


## Linger + ICU_DATA follow-up (2026-07-17)

- **W-018 CLOSED:** `getsockoptLinger` / `setsockoptLinger` in `tools/win64/jni_stubs/win_net_natives.c` + register table; wine NetProbe PASS.
- **ICU_DATA defaults:** phase3/phase4 runners already export `ICU_DATA=run/icu`; `package_win64_phase3.sh` now **requires** `run/icu/icudt72l.dat` (copies from build or vendor stubdata path fallback) and stages `icuuc`/`icui18n`/`openjdkjvm` when present.


## Product ICU data shipping (2026-07-17, W-016 CLOSED)

`icudt72l.dat` is a **required product asset** staged like `boot.jar`:

```bash
tools/win64/stage_run_assets.sh <dest_root> [build_dir]
# -> <dest>/run/boot.jar
# -> <dest>/run/icu/icudt72l.dat
```

Used by `package_win64_phase3.sh` and `install_into_phase1.sh`.  
`libicu_jni` `Register.cpp` defaults `ICU_DATA` to `<cwd>/run/icu` when unset if `icudt72l.dat` is present.


## Packaging (W-005 CLOSED)

Product trees use:

```bash
tools/win64/stage_native_modules.sh <dest> [build/win64_libcore_icu] [build/win64_phase1]
```

Stages real `icuuc`/`icui18n`/`openjdkjvm` + `icu_jni`/`javacore`/`openjdk`, then ART sonames `libicu_jni`/`libjavacore`/`libopenjdk` as copies of those real modules.  
`tools/win64/jni_stubs/libcombined.dll` is **legacy / non-product**.
