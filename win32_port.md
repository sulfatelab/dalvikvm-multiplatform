# Feasibility: Full Native Win64 ART (no Android platform API, no WSL)

> **Arch lock:** **64-bit only** (`x86_64-pc-windows-msvc`, PE32+). “Win32 API” below means the Windows platform API on x64, not a 32-bit product.

Status: Phase 0–2 implementation gated (A2+A3 passed under wine64)  
Date: 2026-07-16 (rev 37 — Phase 4 wine hardening COMPLETE: GC/thread/handle/crash-dump gates PASS)  
Product goal (owner requirement): **full native Windows NT support** for this repo’s ART runtime — a real `dalvikvm.exe` + DLLs + `boot.jar` that runs plain Java on Win32/Win64 **without** Android platform APIs and **without** WSL/VM indirection.

This document answers: *is that feasible, what does “full” mean, and what is the actual port plan?*

Grounding: current Linux port (`project_scope.md`, `overlay/port_policy.py`, `native/CMakeLists.txt`) and vendored AOSP ART/libcore (android-16 era art + libcore).

---

## 0. Mandate and non-goals

### In scope (required)

1. **Native PE process** on Windows 10/11 **x64 only** (Win64). 32-bit x86 Windows is **out of scope**.
2. Same product shape as Linux: hand the VM a dex/jar + main class; it executes bytecode.
3. **No Android platform API**: no framework, binder, Zygote, ashmem daemon, statsd, APEX linker namespaces, `libandroid`.
4. **No WSL2 / Hyper-V guest / Docker-on-WSL** as the delivery mechanism. Build and run are first-class Windows.

### Explicitly out of scope (unless later expanded)

- Android app model (Activities, PackageManager, etc.).
- Device ABI emulation for arbitrary APKs.
- Full Java SE / OpenJDK replacement semantics beyond what Android libcore already provides on Linux.
- Cygwin/MSYS2/MinGW as toolchains or runtime personalities (no `msys-2.0.dll` / `libgcc_s` / MinGW binutils dependency).
- MSVC **as the C/C++ compiler** (`cl`, `clang-cl`). **Using the MSVC/Windows SDK header set with Clang is required**, not forbidden.

### Word “Win32” vs Win64

In Windows APIs, “Win32” often means the classic Windows API surface (including on x64). **This port is Win64-only:**

- **Arch:** `x86_64` / PE32+ only. No 32-bit x86 / WOW64 product target.
- **Compiler stack:** LLVM **Clang** (`clang` / `clang++`) + **lld** + **libc++** / **compiler-rt**.
- **Platform headers/libs:** **Windows SDK / MSVC SDK headers and import libraries** (Win32 API + UCRT) for **x64**.
- **Not used:** MSVC **compiler** (`cl.exe`), `clang-cl`, MSVC STL as C++ library, **MinGW-w64**, Cygwin/MSYS2, **32-bit Windows**.

---

## 1. Executive verdict (revised)

| Question | Answer |
|----------|--------|
| Is full native Windows ART **possible** without Android platform APIs? | **Yes.** Platform APIs are already avoided on Linux; Windows does not require them either. |
| Is it a config/port_policy tweak? | **No.** Upstream disables the ART runtime on Windows; you must **write an OS port** of the runtime spine. |
| Is WSL an acceptable substitute for this goal? | **No** (owner mandate). Discarded as a product answer. |
| Overall feasibility | **Feasible as a dedicated multi-phase systems project.** Not “easy”; not “impossible.” Closer to porting a JVM than to finishing the Linux host overlay. |
| Relative cost vs current Linux port | Roughly **3–8×** for interpreter-quality product; **more** if JIT/AOT parity is required in v1. |
| Recommended stance | **Accept full Win64 as a first-class second OS target.** Sequence work so Linux remains the correctness oracle, but design the OS boundary so Windows is not a dead end. |

**Bottom line:** Full native **Win64** support is a **real OS port of ART + libcore natives**, not an extension of `ART_TARGET_LINUX`. It is worth doing only with that understanding. With that understanding, it is **doable** by isolating a Windows platform layer, reusing AOSP’s partial Windows leaf code, and phasing interpreter → libcore → JIT.

---

## 2. What “full” support must deliver (acceptance bar)

A release is not “full” until all of the following pass on native Windows:

| # | Acceptance criterion |
|---|----------------------|
| A1 | `cmake` + Ninja (or equivalent) builds `dalvikvm.exe` and required DLLs **on Windows or as a Windows-target cross-build from Linux CI**. |
| A2 | `dalvikvm.exe -showversion` prints ART version without Unix-only loader hacks. |
| A3 | Imageless boot with project `boot.jar`; **Hello.main** completes (interpreter). |
| A4 | Core libcore natives work for: files, streams, strings/charset, basic concurrency, `System.arraycopy` / `Class` / reflection used by normal apps. |
| A5 | GC survives smoke + simple allocation stress (CMS or chosen Windows-safe GC). |
| A6 | Multi-thread Java works (monitors, `Thread.start`, interruption basics). |
| A7 | Network + NIO sufficient for a small socket client/server (product-class apps). |
| A8 | Crash path does not silent-corrupt; controlled abort or dump is possible (need not match Linux signal catcher UX). |
| A9 | No dependency on WSL, Android device, or Android platform shared libraries at runtime. |

**JIT/dex2oat** can be a **v1.1** gate if v1 is explicitly “interpreter product.” Document that choice; do not claim JIT parity until entrypoints are Win64-correct.

---

## 3. Why this is a real port (evidence)

### 3.1 Upstream does not ship a Windows runtime

- `vendor/art/build/Android.bp`: ART defaults set **`windows: { enabled: false }`**.
- `vendor/art/libartbase/base/globals.h`: target flavors are only **ANDROID / LINUX / FUCHSIA** — no `ART_TARGET_WINDOWS`.
- `vendor/art/runtime/`: essentially **zero `_WIN32`** runtime implementation; host path is `thread_linux.cc` / `runtime_linux.cc` / `monitor_linux.cc` (signals, `sigaltstack`).
- Existing Windows code is **leaf-level**: `mem_map_windows.cc`, libbase/liblog windows sources, dex tools.

### 3.2 Linux port still assumes Unix

Current Layer 2 forces `ART_TARGET` + `ART_TARGET_LINUX`, CMS, glibc macros on javacore, Linux boringssl `.S` paths, `dlopen` of `libjavacore` / `libopenjdk` / `libicu_jni`, `-pie` / `--export-dynamic`. That product **cannot** be renamed to Windows.

### 3.3 Hard dependencies that must be reimplemented

| Subsystem | Linux mechanism | Windows replacement |
|-----------|-----------------|---------------------|
| Null checks / SO / some GC traps | SIGSEGV/SIGBUS + sigchain + ucontext | VEH (`AddVectoredExceptionHandler`) + `CONTEXT` / `EXCEPTION_POINTERS` |
| Alt signal stack | `sigaltstack` | Not applicable; careful stack guard + VEH stack discipline |
| Mutex fast path | futex (`ART_USE_FUTEXES` on `__linux__`) | `WaitOnAddress`/`WakeByAddress*` (Win8+) and/or SRWLOCK + condition vars; audit non-futex paths |
| Mapping | `mmap`/`mprotect`/`madvise` | `VirtualAlloc`/`VirtualProtect`/`PrefetchVirtualMemory`/`DiscardVirtualMemory`; extend `mem_map_windows.cc` |
| Thread identity | pthread TLS / ART TLS layout | `FlsAlloc`/`TlsAlloc` or TEB-based TLS; Win64 GS/FS conventions differ |
| Dynamic load | `dlopen` / `.so` | `LoadLibraryW` / DLLs; explicit exports |
| Entrypoints / mterp | GAS SysV ELF `.S` | **Win64 ABI** assembly (or C++ fallback where possible) |
| libcore I/O | POSIX / epoll / Linux natives | Win32 file/socket APIs or a thin project-owned POSIX subset used only inside JNI |
| Code cache exec | `mprotect` RW→RX | `VirtualProtect`; respect CFG if enabled |

---

## 4. Target architecture for *this* repo

Keep the three-layer model; make OS a first-class axis.

```text
Android.bp
    │
    ▼
Layer 1  bp2cmake Config: os ∈ {linux, windows}, arch, libc/crt
    │
    ▼
Layer 2  port_policy:
           port_policy_linux.py   (existing OVERLAY)
           port_policy_windows.py (new)
    │
    ▼
Layer 3  CMake emission + native/CMakeLists.txt OS branches
    │
    ▼
compat/windows/   project-owned ART OS spine (new sources)
vendor/…          AOSP with minimal patches; prefer overlay src injection
```

### 4.1 Target identity choice (locked recommendation)

Introduce project-owned:

```text
-DART_TARGET -DART_TARGET_WINDOWS
```

and extend `globals.h` via a **compat patch or prelude** (same pattern as other host shims):

- `kIsTargetBuild = true`
- `kIsTargetWindows = true`
- `kIsTargetLinux = false`, `kIsTargetAndroid = false`

Do **not** define `ART_TARGET_LINUX` on Windows. That macro documents ashmem/mem_map expectations and misleads future readers.

Host-only (`!ART_TARGET`) is a weaker alternative: it matches some AOSP host tests but diverges from the Linux product’s “target-flavored” semantics (boot paths, base addresses, etc.). Prefer **symmetric target-flavored ports**: Linux target vs Windows target.

### 4.2 Toolchain choice (locked recommendation)

**Canonical env root (agent01):** `/home/agent/Projects/win64-dev-env` — see **§4.2.4**.  
**Locked:**

1. **Compiler/linker/C++ runtime = LLVM only** (`clang` / `clang++`, `lld`, `libc++`, `compiler-rt`).
2. **Platform headers & import libs = MSVC/Windows SDK** (required).
3. **No MinGW.** No MSVC **`cl` / `clang-cl`** as the build driver.

The Windows port uses the same *kind* of **compiler** as Linux (LLVM Clang), plus the **official Microsoft Windows SDK header/import-lib surface** as the platform sysroot — the same role glibc headers play on Linux.

| Component | Choice |
|-----------|--------|
| C/C++ compiler | LLVM **`clang` / `clang++`** on the Windows host (**not** `cl`, **not** `clang-cl`) |
| Assembler | Clang integrated assembler (GAS-syntax `.S` sources) |
| Linker | LLVM **`lld`** / **`lld-link`** |
| C++ standard library | LLVM **`libc++`** (not MSVC STL) |
| Compiler runtime | LLVM **`compiler-rt`** (+ **libunwind** as needed) |
| **Win32 / CRT headers** | **Windows SDK** — `windows.h`, `winbase.h`, … under SDK `Include/*/um|shared|winrt` |
| **C library headers / import libs** | **UCRT** from the Windows SDK / MSVC redistributable layout (`Include/*/ucrt`, `Lib/*/ucrt`, `um`) |
| Target triple | `x86_64-pc-windows-msvc` (COFF + Windows ABI). This names the **object/platform ABI**, not the MSVC compiler. |
| Build | **CMake + Ninja**, `CMAKE_CXX_COMPILER=clang++` |

| Rejected | Why |
|----------|-----|
| MSVC `cl.exe` | Not Clang; poor GNU/Clang extension and `.S` story |
| `clang-cl` | MSVC-compatible *driver*; owner wants plain `clang++` + SDK includes |
| MSVC STL (`msvcp*`) as ART’s C++ library | Use **libc++** instead |
| **MinGW-w64** headers/libs/binutils / `windows-gnu` triple | Owner rejected MinGW; SDK headers are the chosen Win32 surface |
| Cygwin / MSYS2 toolchains | Wrong product shape |

**Required: MSVC/Windows SDK headers**

These **must** be on the include and library paths:

- Windows SDK API headers (`um`, `shared`, …) for `windows.h`, VEH, threads, virtual memory, etc.
- UCRT headers and `.lib` import libraries used by the `windows-msvc` ABI.
- Matching architecture lib directories (`x64`) for `kernel32.lib`, `ucrt.lib`, `uuid.lib`, …

Installing the SDK (standalone Windows SDK and/or VS Build Tools **SDK components**) is expected. That is **not** permission to invoke `cl.exe`. Clang consumes the same header tree Microsoft ships for the platform.

**Forbidden:**

- Using `cl` / `clang-cl` / VS `link.exe` as the ART build tools.
- Using MinGW’s `windows.h` / CRT instead of the Windows SDK.
- Claiming a build with *no* SDK and *no* MinGW (impossible for real Win32 APIs).

Prefer an **official or self-built LLVM Windows release** (clang, lld, libc++, compiler-rt) side-by-side with a **Windows SDK** install.

**Concrete expectations:**

- Compiler identity: `CMAKE_CXX_COMPILER_ID=Clang`; driver `clang++`.
- Language: C++20 / C11 as on Linux.
- Includes: SDK `um`/`shared`/`ucrt` before any accidental third-party Win32 headers.
- Linker: `lld-link` (or `clang++ -fuse-ld=lld`) against SDK import libs.
- C++ library: `libc++` (not MSVC STL, not MinGW libstdc++).
- Assembler: Clang IA for `.S`; Win64 calling-convention ports still required in ART sources.
- Harness: `FATAL_ERROR` if compiler is MSVC or clang-cl; `FATAL_ERROR` if Windows SDK paths are missing on a Windows build.

CMake configure sketch (native Windows; adjust SDK paths to the installed version):

```bat
cmake -S native -B build/native -G Ninja ^
  -DCMAKE_C_COMPILER=clang ^
  -DCMAKE_CXX_COMPILER=clang++ ^
  -DCMAKE_ASM_COMPILER=clang ^
  -DCMAKE_CXX_FLAGS="-stdlib=libc++ --target=x86_64-pc-windows-msvc" ^
  -DCMAKE_C_FLAGS="--target=x86_64-pc-windows-msvc" ^
  -DCMAKE_EXE_LINKER_FLAGS="-fuse-ld=lld -stdlib=libc++" ^
  -DCMAKE_SHARED_LINKER_FLAGS="-fuse-ld=lld -stdlib=libc++" ^
  -DMDVM_WINDOWS_SDK_ROOT="C:/Program Files (x86)/Windows Kits/10" ^
  -DCMAKE_BUILD_TYPE=RelWithDebInfo
```

Harness (or a small CMake module) should wire `MDVM_WINDOWS_SDK_ROOT` / auto-detected kit version into `include_directories` + `link_directories` for `um`/`ucrt`/`shared` and `Lib/10.x/um/x64` etc.

Cross-compile from Linux is optional for compile-only CI **if** a Windows SDK sysroot is available to Clang; **runtime validation stays on real Windows**. No MinGW triple.

#### 4.2.1 Quick compiler-tool feasibility check (2026-07-16)

**Question:** Can this project actually build with **LLVM Clang only** on Windows, given the locks “no MSVC toolset” and “no MinGW”?

**Short answer:** **Yes for the compiler/linker stack; conditional on a platform sysroot for headers and import libs.** The frontend is not the risk. The sysroot policy is.

| Layer | Feasible? | Notes |
|-------|-----------|--------|
| `clang` / `clang++` codegen for Windows | **Yes** | LLVM targets both `x86_64-pc-windows-msvc` (MSVC *object* ABI) and `x86_64-pc-windows-gnu`. Spot-check on agent01: Ubuntu clang 21 emits **x86-64 COFF** for both triples (`clang -target … -c` → COFF object). |
| Integrated assembler (`.S` → COFF) | **Yes** | Same driver; Win64 **calling convention** still must be ported in ART sources — that is ABI work, not missing compiler support. |
| `lld` / `lld-link` | **Yes** | LLVM ships a COFF linker. **Rechecked agent01:** `/usr/bin/lld`, `ld.lld`, `lld-link` → Ubuntu LLD **21.1.8**. |
| `compiler-rt` builtins | **Yes** | Standard LLVM component; needed for some runtime helpers. |
| `libc++` on Windows | **Yes, with care** | libc++ supports Windows configurations; must be built/installed as part of the LLVM Windows toolchain. Do **not** fall back to MSVC STL or MinGW libstdc++. |
| “Headers only from clang resource dir” | **No** | Spot-check: `clang++ -target x86_64-pc-windows-msvc -E` only sees `…/lib/clang/21/include` — **no `windows.h` / UCRT**. Clang alone does not ship the Win32 API surface. |
| Link final `dalvikvm.exe` with zero platform import libs | **No** | Need `kernel32`, UCRT, etc. Those come from a **sysroot**, not from the ART tree. |

**Critical distinction (easy to confuse with “no MSVC”):**

| Thing | Is it the MSVC *compiler toolset*? | Allowed under this port? |
|-------|------------------------------------|---------------------------|
| `cl.exe`, VS `link.exe`, MSVC STL (`msvcp*`), VS Build Tools as the C++ driver | **Yes** | **No** |
| **Windows SDK / MSVC SDK headers** (`windows.h`, `um`/`shared`/`ucrt`, `kernel32.lib`, UCRT import libs) | **No** — platform SDK headers/libs, not the compiler | **Yes — required** (owner lock: use this header surface with Clang) |
| MinGW-w64 headers/libs/binutils | N/A | **No** |
| Official/self-built **LLVM** clang+lld+libc+++compiler-rt on Windows | N/A | **Yes — required** |

So the locked stack is:

```text
LLVM clang/clang++  +  lld/lld-link  +  libc++  +  compiler-rt
        +
MSVC / Windows SDK headers & import libs   ← REQUIRED (not the MSVC compiler)
  (Include/.../um|shared|ucrt , Lib/.../um|ucrt)
        +
Win32/Win64 OS DLLs at runtime (kernel32, ntdll, ucrtbase, …)
```

That is **“Clang compiler + MSVC/Windows SDK headers.”** It is **not** “building with the MSVC compiler.” It is analogous to clang + glibc headers on Linux. MinGW headers are not an alternative under this lock.

**Implications for ART / this repo:**

1. **Harness:** require `CMAKE_CXX_COMPILER_ID=Clang` (plain `clang++`); reject `MSVC` / `clang-cl` / MinGW-GCC; **require** resolvable Windows SDK paths (`MDVM_WINDOWS_SDK_ROOT` or auto-detect under `Windows Kits/10`).
2. **Triple:** `x86_64-pc-windows-msvc` (COFF + Windows ABI for those SDK headers). **Not** `windows-gnu`.
3. **CI:** Windows runner installs **LLVM + Windows SDK** (VS C++ compiler workload optional/unnecessary). Cross builds need the same SDK header tree as a sysroot.
4. **Risk remaining (toolchain-only):** medium-low — standard layout; ART OS port remains the large cost. Compiler-tool feasibility is **Go** with this SDK-header policy.

**Feasibility rating (compiler tools only):** **Go** — LLVM Clang/LLD/libc++ **plus required MSVC/Windows SDK headers**.

#### 4.2.2 Linux → Windows cross-compile feasibility

**Question:** Can the Windows ART tree be **cross-compiled on Linux** (this project’s current home), under the locks: LLVM `clang++` (not `cl`/`clang-cl`), **MSVC/Windows SDK headers**, no MinGW, no WSL-as-product?

**Short answer:** **Yes for build/CI artifacts; no as a substitute for Windows runtime validation.** Cross-compile is a first-class *compile/link* path; Hello.main and libcore still need a real Windows host (or hardware) to gate.

| Stage | On Linux host? | Notes |
|-------|----------------|--------|
| Compile C/C++/ASM → COFF | **Yes** | Spot-check: agent01 Ubuntu clang 21 already produces `x86-64 COFF` with `-target x86_64-pc-windows-msvc`. |
| Assemble ART `.S` to COFF | **Yes** | Integrated assembler; content must still be **Win64 ABI**-correct. |
| Preprocess/include `windows.h` / UCRT | **Yes, iff sysroot** | Linux Clang does **not** ship these. Need a Windows Kits tree on the Linux machine (see below). |
| Link `dalvikvm.exe` / DLLs | **Yes, iff lld + SDK libs** | Need `lld-link` (or `clang -fuse-ld=lld` in link mode) and SDK `Lib/*/um/x64`, `ucrt`, etc. agent01 currently has `clang` but **no** `lld-link`/`ld.lld` installed — fixable package gap. |
| Build libc++ for Windows target | **Yes / bring-your-own** | Either use a prebuilt Windows libc++ in the sysroot or build libc++ once for `x86_64-pc-windows-msvc` and cache it. |
| Run `dalvikvm.exe` | **No** | PE won’t run natively on Linux. Wine is **not** the acceptance bar for this port (and is unreliable for ART VEH/GC). |
| Full e2e (A3–A8) | **No on Linux alone** | Requires Windows test machine/CI runner. |

**What you must put on the Linux builder**

```text
Linux
  ├── LLVM: clang, clang++, lld (with COFF/lld-link support)
  ├── libc++ + compiler-rt for the Windows target (or build them)
  └── Windows sysroot (MSVC/Windows SDK layout), e.g.:
        Include/<ver>/um|shared|ucrt|cppwinrt
        Lib/<ver>/um/x64
        Lib/<ver>/ucrt/x64
```

How the SDK tree gets onto Linux (all compatible with “use MSVC SDK headers, not MinGW”):

| Method | Feasible? | Comment |
|--------|-----------|---------|
| Copy/rsync a Windows Kits install from a Windows box | **Yes** | Simplest legally if you already own the SDK install; scripts pin version. |
| [xwin](https://github.com/Jake-Shadle/xwin) / similar splatters of CRT+SDK | **Yes (common)** | Downloads MS CRT/SDK components into a Linux-friendly layout for clang/lld. Still **Microsoft headers/libs**, not MinGW. **On agent01:** already splatted at `~/xwin` (see recheck). |
| Mount/CI cache of SDK from Windows runner | **Yes** | Hybrid CI: Windows job publishes SDK tarball; Linux job compiles. |
| Hope apt `mingw-w64` packages | **No** under current lock | That’s MinGW headers — rejected. |
| Empty sysroot (clang resource dir only) | **No** | Cannot include `windows.h` (already verified locally). |

**CMake sketch (Linux host → Windows PE)**

```bash
# Assume: $WINSDK is a Windows Kits-style root (Include/, Lib/)
#          $WINLIBCXX is a Windows-target libc++ install (optional if in sysroot)

cmake -S native -B build/win64 -G Ninja   -DCMAKE_SYSTEM_NAME=Windows   -DCMAKE_SYSTEM_PROCESSOR=AMD64   -DCMAKE_C_COMPILER=clang   -DCMAKE_CXX_COMPILER=clang++   -DCMAKE_ASM_COMPILER=clang   -DCMAKE_C_COMPILER_TARGET=x86_64-pc-windows-msvc   -DCMAKE_CXX_COMPILER_TARGET=x86_64-pc-windows-msvc   -DCMAKE_ASM_COMPILER_TARGET=x86_64-pc-windows-msvc   -DCMAKE_CXX_FLAGS="-stdlib=libc++ -isystem $WINSDK/Include/<ver>/ucrt -isystem $WINSDK/Include/<ver>/um -isystem $WINSDK/Include/<ver>/shared"   -DCMAKE_C_FLAGS="-isystem $WINSDK/Include/<ver>/ucrt -isystem $WINSDK/Include/<ver>/um -isystem $WINSDK/Include/<ver>/shared"   -DCMAKE_EXE_LINKER_FLAGS="-fuse-ld=lld -stdlib=libc++ -L$WINSDK/Lib/<ver>/ucrt/x64 -L$WINSDK/Lib/<ver>/um/x64"   -DCMAKE_SHARED_LINKER_FLAGS="-fuse-ld=lld -stdlib=libc++ -L$WINSDK/Lib/<ver>/ucrt/x64 -L$WINSDK/Lib/<ver>/um/x64"   -DMDVM_WINDOWS_SDK_ROOT="$WINSDK"   -DCMAKE_BUILD_TYPE=RelWithDebInfo
```

(Exact `-isystem` / version dir names should be centralized in a `cmake/WindowsLLVM.cmake` module; the sketch is the shape, not the final path discovery.)

**Hard corners (still feasible, not free)**

1. **codegen driver / host tools:** `operator_out`, mterp generation, `asm_defines` currently run at configure time with the **build** clang. For cross builds, run those tools as **Linux host executables** (build them for the builder, not for Windows), then compile their outputs with the Windows target — classic host vs target split. ART already thinks this way in Soong; the Linux port must not assume “configure-time clang == target clang.”
2. **Trying to *run* Windows codegen binaries on Linux** during the build: avoid; keep Python + host ELF tools.
3. **lld vs MSVC `.lib`:** works for normal import libs; exotic MSVC whole-archive / PDB workflows need care — prefer LLVM-side debug (`-g` + lld) for CI.
4. **License/redistribution:** shipping the SDK *in the git repo* is wrong; CI should fetch or cache a kit the same way other projects cache Windows Kits. Document the pin (e.g. SDK 10.0.22621.0).
5. **agent01 recheck (2026-07-16):** cross-build tooling is **already present enough for a PE smoke**:
   - **lld:** `/usr/bin/lld`, `ld.lld`, `lld-link` → Ubuntu LLD **21.1.8** (package `lld-21`).
   - **`~/xwin`:** `/home/agent/xwin` (~630M splat) + `/home/agent/.xwin-cache` (~1.1G); tool at `/home/agent/.cargo/bin/xwin`.
   - Layout: `xwin/sdk/include/{um,shared,ucrt,winrt,cppwinrt}`, `xwin/sdk/lib/{um,ucrt}/x86_64`, `xwin/crt/{include,lib/x86_64}` (MSVC CRT headers/libs from VS 17.x / VC 14.44 tree in cache).
   - SDK provenance in cache: **Win11 SDK 10.0.26100** MSIs (`Win11SDK_10.0.26100_*.msi`, `ucrt.msi`).
   - **Compile smoke:** `clang -target x86_64-pc-windows-msvc` + `-isystem` to `~/xwin/sdk/include/{ucrt,shared,um}` (+ crt include) successfully compiled `#include <windows.h>` → COFF.
   - **Link smoke:** `lld-link` with `msvcrt.lib vcruntime.lib ucrt.lib kernel32.lib` produced **`PE32+` console x86-64** (`/tmp/winhello_md.exe`). Mixing static `libcmt`/`libucrt` incorrectly duplicated UCRT symbols — use a consistent CRT flavor (DLL UCRT worked).
   - **libc++ / compiler-rt (resolved on agent01):**
     - **compiler-rt:** **prebuilt available** in official `clang+llvm-21.1.8-x86_64-pc-windows-msvc` release (`lib/clang/21/lib/windows/clang_rt.builtins-x86_64.lib`, asan/ubsan/…). Extracted to `/home/agent/Projects/llvm-windows-msvc/prefix/`.
     - **libc++:** **not** shipped in that official Windows tarball (headers/libs absent). **Cross-built** from `llvmorg-21.1.8` on Linux → `/home/agent/Projects/llvm-runtimes-win64/install/` (`c++.dll`, `c++.lib`, `libc++.lib`, `include/c++/v1`). ABI=`vcruntime`; link with `msvcprt`. Smoke under wine64: `libc++-win64-ok`.
     - Host Ubuntu LLVM still only has `lib/clang/21/lib/linux` — use the two `~/Projects/...` trees as the Windows-target runtimes, not the host package.
   - Bottom line: **Linux cross-compile path is ready for C++ Win64** (clang + lld + `~/xwin` + prebuilt compiler-rt + cross-built libc++).

   - **wine64 recheck (2026-07-16):** package `wine64` **10.0** (`wine-10.0`, Ubuntu). Prefix `~/.wine` initializes. Cross-linked PE from clang+lld+`~/xwin` runs under `WINEDEBUG=-all wine64`:
     - trivial EXE exit 0;
     - `printf` + `GetCurrentProcessId()` printed `wine64-ok pid=…` and exited 0.
     - `wine32` **not** installed (64-bit PE only — matches Win64 primary target).
     - **Use:** optional Linux-side **PE load/CRT smoke** after cross-link.
     - **Do not use as** product acceptance (A3–A8). Wine is not a substitute for real Windows for ART VEH/GC/threads; §0 still rejects WSL/VM *as the product*, and Wine is even weaker as an ART runtime oracle.

**Recommended CI shape for this repo**

```text
Linux job (cheap, every commit):
  host tools + cross-compile Windows objects/DLLs/EXE with clang+lld+WinSDK sysroot
  artifact: dalvikvm.exe + DLLs

Windows job (required for green product gates):
  download artifact (or native rebuild)
  run -showversion, Hello.main, smoke tests
```

Do **not** declare the Windows port “done” on Linux-only CI green.

#### 4.2.3 libc++ / compiler-rt inventory (agent01)

| Component | Prebuilt binary available? | Action taken |
|-----------|----------------------------|--------------|
| **compiler-rt** for `x86_64-pc-windows-msvc` | **Yes** — official LLVM GitHub release `clang+llvm-21.1.8-x86_64-pc-windows-msvc.tar.xz` | Downloaded to `/home/agent/Projects/llvm-windows-msvc/`; extracted `lib/clang/21/lib/windows/*` |
| **libc++** for same triple | **No** in that official package (no `include/c++`, no `c++.dll`/`libc++.lib`) | Cross-built under `/home/agent/Projects/llvm-runtimes-win64/` from `llvmorg-21.1.8`; installed to `…/install/` |
| Host apt `libclang-rt-21-dev` | Linux only | Not usable as Windows target libs |

See `/home/agent/Projects/llvm-runtimes-win64/README.md` for rebuild flags (clang resource includes before UCRT; `-lmsvcprt` for shared libc++).

**Feasibility rating (Linux cross-compile):**

| Scope | Rating |
|-------|--------|
| Compile + link Windows PE/DLL from Linux with LLVM + MSVC/Windows SDK sysroot | **Go** (standard; needs sysroot + lld + host/target tool split) |
| Replace Windows test machines entirely | **No** |
| Cross-compile using MinGW packages on Linux | **Rejected** by toolchain lock |

#### 4.2.4 Development environment (locked setup on agent01)

**Canonical root:** [`/home/agent/Projects/win64-dev-env`](/home/agent/Projects/win64-dev-env)

This is the assembled **Linux → Win64** toolchain for this project. It does **not** replace the ART OS port work; it only makes compile/link of Windows PE/DLL (and later ART) reproducible.

##### What is installed / required

| Layer | Component | Location / version | Notes |
|-------|-----------|--------------------|--------|
| Host compiler | LLVM **clang / clang++** | system 21.1.8 | Driver must be `clang++`, not `cl` / `clang-cl` |
| Host linker | LLVM **lld** (`lld-link`) | system 21.1.8 | COFF/PE linker |
| Build | CMake ≥ 3.20, Ninja, Python3 | system | |
| Platform SDK | Windows SDK + UCRT + MSVC CRT import libs | `win64-dev-env/xwin` → `~/xwin` | Win11 SDK **10.0.26100** via **xwin** |
| C++ stdlib | **libc++** (shared + static) | `win64-dev-env/lib/libcxx/` | Cross-built from `llvmorg-21.1.8`, ABI=`vcruntime` |
| compiler-rt | builtins (+ sanitizer libs) | `win64-dev-env/lib/clang/21/lib/windows/` | From official `clang+llvm-21.1.8-x86_64-pc-windows-msvc` release |
| CMake integration | `cmake/Win64LLVM.cmake` + `Win64LLVMTargets.cmake` | under env root | Cross toolchain file |
| Optional PE runner | wine64 10.0 | system | Smoke only — **not** product acceptance |

**Not** part of the env: MinGW, MSVC `cl`, MSVC STL as ART’s C++ library, 32-bit targets.

##### Activate

```bash
source /home/agent/Projects/win64-dev-env/env.sh
win64-info
win64-smoke    # full host+sysroot+C+C+++wine+cmake smoke
```

`env.sh` exports `WIN64_DEV_ENV`, `WIN64_CMAKE_TOOLCHAIN`, SDK/libcxx/compiler-rt paths, and helpers `win64-clang` / `win64-clangxx` / `win64-lld-link`.

##### CMake cross-build pattern

```bash
source /home/agent/Projects/win64-dev-env/env.sh
cmake -S <src> -B <build> -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$WIN64_CMAKE_TOOLCHAIN" \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build <build>
# Deploy c++.dll next to EXEs when using shared libc++:
#   cp "$WIN64_LIBCXX_LIB/c++.dll" <build>/
```

In a `CMakeLists.txt` after `project(...)`:

```cmake
include(${WIN64_LLVM_TARGETS_FILE})   # or $ENV{WIN64_DEV_ENV}/cmake/Win64LLVMTargets.cmake
target_link_libraries(my_target PRIVATE win64::libcxx)  # or win64::libcxx_static
```

Hand link libraries (shared libc++): `c++.lib msvcprt.lib msvcrt.lib vcruntime.lib ucrt.lib kernel32.lib`.

##### Include / link path rules (load-bearing)

1. **Clang resource dir before UCRT** (`-isystem $(clang -print-resource-dir)/include` then ucrt/shared/um/crt). UCRT `stddef.h` does not define `max_align_t` the way libc++’s `using_if_exists` needs.
2. **libc++ headers** with `-nostdinc++ -isystem …/include/c++/v1` (do not use MSVC STL headers from `xwin/crt/include` for ART C++).
3. **CRT flavor:** MultiThreaded DLL (`msvcrt` / UCRT DLL) — matches how libc++ was built. Do not mix `libcmt` + `ucrt` DLL carelessly.
4. Shared libc++ needs **`msvcprt.lib`** for `__ExceptionPtr*` (vcruntime ABI).
5. Target triple is always **`x86_64-pc-windows-msvc`** (object/platform ABI name; still compiled with clang, not `cl`).

##### Provenance & rebuild trees

| Artifact | How obtained | Source tree / cache |
|----------|--------------|---------------------|
| compiler-rt Windows libs | **Prebuilt** download | `/home/agent/Projects/llvm-windows-msvc/` (`clang+llvm-21.1.8-…tar.xz`) |
| libc++ | **Cross-built** on Linux | `/home/agent/Projects/llvm-runtimes-win64/` (see its `README.md`) |
| SDK headers/libs | **xwin** splat | `/home/agent/xwin` (+ `~/.xwin-cache`) |
| Unified consumer view | assembled | `/home/agent/Projects/win64-dev-env` |

Host package helper (idempotent):  
`win64-dev-env/scripts/ensure-host-packages.sh` (clang, lld, cmake, ninja-build, python3).

##### Verification status (2026-07-16)

`scripts/smoke-test.sh` **ALL SMOKES PASSED** on agent01:

- host tools present  
- SDK + libc++ + compiler-rt paths valid  
- C PE (kernel32) + C++ PE (libc++) link  
- wine64 runs both  
- CMake toolchain configures and builds `hi.exe`

##### What this does *not* finish

The env does **not** implement ART’s Windows runtime spine (VEH, threads, entrypoints, libcore natives). It only removes the “can we even compile C++ for Win64?” blocker for the port described in the rest of this document.

---

### 4.3 Packaging model

```text
dalvikvm.exe
art.dll              (or libart.dll — pick one naming scheme and stick to it)
artbase.dll, dexfile.dll, …   // or fewer amalgamated DLLs on Windows
javacore.dll, openjdk.dll, icu*.dll, …
boot.jar
```

Windows-specific policies:

- Prefer **fewer shared DLLs** than Linux if export/import churn hurts (Layer 2 may amalgamate more on Windows).
- Export JNI_OnLoad and ART symbols via generated `.def` or explicit visibility macros in compat headers.
- App-local DLL directory next to `dalvikvm.exe` (no `LD_LIBRARY_PATH`).

### 4.4 Project-owned Windows runtime spine (must write)

New files under e.g. `compat/windows/art/` or injected via overlay `add_srcs`:

| File | Role |
|------|------|
| `thread_windows.cc` | TLS attach, stack bounds, no sigaltstack |
| `runtime_windows.cc` | Init VEH, crash path, env |
| `monitor_windows.cc` | Contention logging no-op / ETW later |
| `fault_handler_windows.cc` | Map `EXCEPTION_ACCESS_VIOLATION` etc. → ART fault manager |
| `os_windows.cc` | Replace `os_linux.cc` file ops with Win32/`_wsopen_s` UTF-8 bridge |
| `sigchain_windows.cc` or stub | Sigchain cannot interpose CRT the Linux way; fold into VEH chain |
| `win64/*.S` or `.asm` | Entrypoints / mterp as needed |

Upstream `mem_map_windows.cc` is **necessary but not sufficient** — extend for `MAP_FIXED`-like placement used by ART heaps/code cache, or change ART heap placement policy on Windows via flags.

### 4.5 Synchronization strategy

1. Prefer **`WaitOnAddress` / `WakeByAddressSingle`** (Windows 8+) to mirror futex closely so less of `mutex.cc` must die.
2. Keep `ART_USE_FUTEXES` conceptually as `ART_USE_WAIT_ON_ADDRESS` under a project define on Windows, **or** implement a futex-like wrapper in compat and leave ART sources less patched.
3. Fallback: force non-futex mutex path and fix every `LOG(FATAL)` / incomplete branch — higher patch surface.

Recommended: **compat futex emulation** over `WaitOnAddress` to minimize vendor diffs.

### 4.6 Assembly / interpreter strategy (phased)

**Phase I (required for A3):** maximize **C++ interpreter / nterp C paths** where AOSP allows; only port mandatory stubs.

**Phase II:** port **Win64** quick entrypoints + interpreter assembly:

- Different arg registers (RCX, RDX, R8, R9 vs SysV).
- 32-byte shadow space; different caller-saved sets.
- PECOFF vs ELF directives; clang can still assemble Intel/AT&T with care.

**Phase III:** JIT + oatload — either emit PE sections or keep JIT code purely as RWX/RX anonymous memory (no ELF `libelffile` load of oat on Windows until ported). Imageless + JIT-in-memory is enough for many apps; dex2oat can wait.

### 4.7 libcore natives strategy (this is half the work)

“No Android platform API” does **not** remove libcore JNI.

Plan:

1. **Inventory** every `native` method registered at boot (Class, Object, Throwable, System, File, …).
2. Split into:
   - **Pure / already portable** (boringssl bignums, much of ICU, charset).
   - **OS I/O / path** → Win32 in `compat/windows/libcore/` (see §4.7.1 path model).
   - **Linux-only** (`epoll`, `sendfile`, vsock, …) → Win32 IOCP/select equivalents or stub with checked exceptions.
3. Replace forced `__GLIBC__` / `LINUX` defines in Windows overlay with a **Windows SDK / UCRT** policy (include paths from the kit; never glibc macros).
4. `Portability.h`: Windows edition (no `byteswap.h` / `sys/sendfile.h` as mandatory).

Product-class apps (network bots, CLI) need A4+A7; pure compute may pass earlier.

#### 4.7.1 Win64 path model (mandatory mixed/hybrid paths)

> Detailed layer analysis (libcore vs libart): **[filesystem_win32.md](filesystem_win32.md)**.

**Product requirement:** ART on Win64 must accept **Windows-native and mixed separators** in filesystem paths, and **resolve absolutes to normal Win32 form** (`C:\path\to\file`, not `/…` and not `\\?\` by default). See [filesystem_win32.md](filesystem_win32.md) §1.5. Examples:

- `C:\Users\example\file.txt`
- `C:/Users/example/file.txt`
- **`C:\Users\example/some/file`** (mixed `\` and `/`)
- UNC forms (`\\server\share\…` / `//server/share/…`) where Win32 allows
- Relative paths used by this port today (`run/hello.jar`, `run/boot.jar`)

**Why this is mandatory for ART (not cosmetic):**

1. **Native Windows hosts** hand apps and shells drive-letter paths; users will pass them on `-cp` / properties / `File` APIs.
2. **Win32 file APIs** (`CreateFileW`, `GetFileAttributesW`, …) generally accept `/` as well as `\`; mixed strings are common when Android/libcore code joins with `/` onto a Windows root.
3. **Phase-2 “keep UnixFileSystem forever” is insufficient** for this requirement:
   - `UnixFileSystem.prefixLength` / `isAbsolute` only treat a leading `/` as absolute → **`C:\…` is not absolute**.
   - `normalize` only collapses `/`, leaves `\` as ordinary characters → wrong parent/name/resolve semantics.
   - `file.separator=/` alone does not make drive letters or UNC work in `java.io.File`.
4. OpenJDK already solved this in **`java.io.WinNTFileSystem`** (+ `WinNTFileSystem_md.c`); Android ojluni in this tree **does not ship** those sources — reuse = **port from OpenJDK windows/** + refit Android hooks.

**Classpath list separator is a separate axis** (do not conflate with file separators):

| Axis | Android/Linux today | Win64 ART requirement |
|------|---------------------|------------------------|
| File path chars inside one path | `/` | **`\` and `/` both valid; mixed OK**; prefer normalize-to-Win32 for kernel calls |
| Multi-path list (`-cp`, `-Xbootclasspath`, `java.class.path`, `DexPathList`) | `:` | **Keep `:` as primary** for ART/Android compatibility (`parsed_options` help text, `Split(..., ':')`, bootclasspath). Optionally **also accept `;`** later if dual-split is implemented carefully (`;` must not break drive letters — `C:\a.jar;D:\b.jar`). |

**Architecture (revised hybrid):**

1. **`java.io` path facade:** adopt a **Windows-capable `FileSystem`** (OpenJDK `WinNTFileSystem` lineage or equivalent project class), not bare `UnixFileSystem`, for Win64 product builds.
2. **Byte I/O:** still mostly `IoBridge` → `Libcore.os` → implement PE natives for open/read/write/close/stat (the bulk of A4); path facade and Os layer both must open mixed paths.
3. **NIO.2 (`sun.nio.fs`):** **non-goal for now** (no Windows provider port). Leave Linux-shaped stubs / fail clearly; **`java.io.File` must not lag**.
4. **Normalize at the Win32 boundary:** before `CreateFileW` / `GetFileAttributesW`, normalize mixed paths to a consistent wide path (OpenJDK WinNT does this; do not rely on accidental CRT tolerance alone).
5. **`path.separator=;`** on Win64; ART `-cp` / `-Xbootclasspath` parsing must use `;` (not hardcoded `:`).
6. **Phase-2 stubs** (`UnixFileSystem.getBooleanAttributes0`, relative `run/…`) remain a **bootstrap**, not the product path model.

**Decision:** **Option H (Hybrid)** locked — [filesystem_win32.md](filesystem_win32.md). WinNT-class `java.io` + Os/IoBridge + ART open; **`;` lists**; normal `C:\…` absolutes. **Windows NIO.2 is a non-goal for now.** Still smaller than “replace all of libcore.”

### 4.8 GC choice on Windows

Keep **CMS** (already forced on Linux to avoid userfaultfd). Do not enable CMC/userfaultfd paths. Validate:

- Card table / heap `mprotect` equivalents via `VirtualProtect`.
- Stack load/store barriers independent of Linux signals where possible.
- Growth and trimming via `VirtualAlloc`/`VirtualFree` or decommit.

---

## 5. Converter / build changes (concrete)

### Layer 1

- Config fields: `os=windows`, `target_os_windows=True`, arch `x86_64`.
- Evaluate `target.windows` / `not_windows` / `windows:` bp branches (already present for many leaves).
- For modules with `windows: { enabled: false }` in ART defaults, **overlay re-enables** runtime modules explicitly (Layer 2), rather than fighting every bp.

### Layer 2 (`port_policy_windows.py`)

Mirror Linux decisions where semantics match; replace OS-specific ones:

| Linux policy | Windows policy |
|--------------|----------------|
| `ART_TARGET` + `ART_TARGET_LINUX` | `ART_TARGET` + `ART_TARGET_WINDOWS` |
| `ART_DEFAULT_GC_TYPE_IS_CMS` | same |
| `palette_fake` | same (already host/windows friendly) |
| `monitor_linux` / `runtime_linux` / `thread_linux` | **compat windows sources** |
| drop `libdl_android`, statsd, … | same drops |
| host `libcap` | **drop / stub** (no capabilities) |
| boringssl `linux-x86_64/*.S` | `win-x86_64` perlasm outputs or safe C paths |
| `-pie`, `--export-dynamic` | DLL export defs / `/SUBSYSTEM:CONSOLE` |
| `__GLIBC__` forced on javacore | Windows SDK / UCRT defines; never `__GLIBC__` |

### Layer 3 / harness

- `native/CMakeLists.txt`: branch on `WIN32` for imported zlib/lz4/expat, no `libcap`, codegen driver with `--os windows`.
- Compiler gate: require LLVM `Clang` (not `clang-cl`); reject `cl` and MinGW-GCC.
- Sysroot gate: require **Windows SDK / MSVC SDK headers** + import libs (`um`/`ucrt`).
- CI: **native Windows** runner with LLVM (clang, lld, libc++, compiler-rt) **and** Windows SDK; optional cross compile only with the same SDK header tree — **no MinGW**.
- Tests: smoke scripts in PowerShell and/or Python, run on real Windows.

### Submodule / patch discipline

- Prefer **compat injection** over editing `vendor/art`.
- When vendor edit is unavoidable (e.g. `globals.h` target enum), keep a **tiny** `vendor-patches/` entry with clear Windows rationale (same discipline as Linux `FillVRegs`/prelude patches).
- Goal remains: Layer 1 absorbs AOSP churn; Windows OS spine stays project-owned.

---

## 6. Phased delivery plan (full support)

Each phase has a kill-or-continue gate. This is the execution roadmap when implementation starts.

### Phase 0 — Foundations (2–4 weeks) — **DONE (2026-07-16)**

- Toolchain bootstrap: **LLVM clang/lld + Win SDK (xwin) + libc++ + compiler-rt** via `/home/agent/Projects/win64-dev-env` (Linux cross → PE). No `cl`, no MinGW.
- Layer 1: `Config(os="windows")` + `bp2cmake --os windows` selects `target.windows` (e.g. `errors_windows.cpp`, `mem_map_windows.cc`).
- Layer 2: `overlay/port_policy_windows.py`.
- Built PE32+ DLLs: `log`, `base`, `nativehelper`, `ziparchive`, `artpalette`, **`artbase`**.
- **Gate:** `libartbase` links — **PASSED** (`build/win64_phase0/artbase.dll`). See `tools/verify/win64_phase0/RESULT.md`.

### Phase 1 — Skeleton VM (1–2 months) — **DONE (2026-07-16)**

- Port policy + harness for full ART graph on `x86_64-pc-windows-msvc`.
- `thread_windows` / `runtime_windows` / `monitor_windows` / `sigchain` stubs; PE asm + WaitOnAddress futex path.
- Linked `dalvikvm.exe` + `art.dll` (+ deps); JNI default library is `art.dll` on Windows.
- **Gate:** `dalvikvm -showversion` (A2) — **PASSED** under `wine64` → `ART version 2.1.0 x86_64`.
- Details: `tools/verify/win64_phase1/RESULT.md`.

### Phase 2 — Interpreter Hello (2–4 months) — **DONE (2026-07-16, wine64 A3)**

- Fault handler MVP for null + stack overflow (enough for Hello).
- MemMap extensions for heap + boot image optional (imageless OK).
- Minimal JNI registration; **reduced boot.jar** if needed to reach Hello, then grow.
- Win64: only required assembly stubs; expanded C++ `InterpreterJni` for PE shorties.
- Phase-2 PE JNI stubs: `tools/win64/jni_stubs/` (stand-in for real libcore natives).
- **Gate:** A3 Hello.main imageless interpreter — **PASSED under wine64** (`-cp run/hello.jar Hello`).
  Native Windows host re-check remains product/Phase-3 follow-on; wine is the agent01 cross-build gate.

### Phase 3 — libcore bring-up (3–6 months, overlaps Phase 2) — **COMPLETE**

- Foundations (2026-07-16): Option H path/FS + `;` classpath; A4–A7 + GoldenApp under wine64.
- A5 forced GC: `System.gc()` hang fixed (`GetThreadTimes` ThreadCpuNanoTime + WaitOnAddress ETIMEDOUT); gate `run_gcforced.sh`.
- See `tools/verify/win64_phase3/RESULT.md` and `archive-patches/win64_phase3_system_gc_hang_fix.md`.
- Path gates (same day): `File.isAbsolute("C:\\…")` **PASS**, mixed/UNC **PASS**, multi-jar `-cp a;b` **PASS** under wine64 (`tools/verify/win64_phase3/run_probe.sh`).
- **Pitfall:** imageless ART has `Character.isLetter('C')==false` (no ICU props). `WinNTFileSystem` must use ASCII `isDriveLetter`, not `Character.isLetter`.
- **Shell pitfall:** bash splits on `;` — multi-jar `-cp` must be passed via argv list (Python subprocess), not a shell string.
- File I/O (P7): `FileInputStream`/`FileOutputStream` round-trip **PASS** (`run_ioprobe.sh`); PE FD must run `<init>` for `releaseLock`.
- A4 core: arraycopy/UTF-8/reflect/threads monitors **PASS** (`run_coreprobe.sh`).
- A7 classic loopback `ServerSocket`/`Socket` payload echo **PASS** (`run_netprobe.sh`); NIO.2 still non-goal.
- A5/A6/GoldenApp + forced System.gc **PASS** under wine64 (`run_gcprobe.sh`, `run_gcforced.sh`, `run_interruptprobe.sh`, `run_goldenapp.sh`).
- Absolute C: jar load P2–P4/P8 + P5 parent/name + P9c colon **PASS** (`run_abspathprobe.sh`).
- Runtime free/total/maxMemory **PASS** (`run_rtmem.sh`) via art `JVM_*` exports + PE Runtime natives.
- Props/time/`java.version=1.8.0` **PASS** (`run_propsprobe.sh`); Os errno + UTF-8 paths **PASS** (`run_oserrnoprobe.sh`).
- Host smoke package staged: `dist/win64_phase3_host` via `tools/win64/host_package/package_win64_phase3.sh`.
- Full wine suite `run_all_wine_gates.sh` **PASS** (includes throw path + thread stress).
- Host package integrity under wine `smoke_package_wine64.sh` **PASS** (not a substitute for host).
- Host transfer: `dist/win64_phase3_host.zip`; checklist `tools/win64/host_package/G12_HOST_CHECKLIST.md`.
- First Win10 G12 evidence analyzed: paths/props/GC PASS; **net poll EINVAL FAIL**; false OVERALL PASS from cmd ERRORLEVEL clobber.
- G12 real Win10 host goldens **PASS** (`evidence/host/RESULT_HOST.txt`, 2026-07-16T205926): net/dns/golden/abspath/props/GC all markers green.
- Phase 3 acceptance (A4–A7 + Option H + golden app on native Windows) **met**.

- Systematic native registration matrix; file/path UTF-8; network.
- **Path model (Option H / filesystem_win32.md):** WinNT-class `java.io` + Os/ART open; mixed paths; normal `C:\…` absolutes; **`path.separator=;`**. Drive math uses ASCII letters (not ICU `Character.isLetter`). **Windows NIO non-goal for now.**
- ICU data loading on Windows paths (including mixed/drive-letter locations).
- boringssl Windows ASM or C.
- **Gate:** A4–A7 for target app class (define one golden app early), including golden paths:
  - relative `run/hello.jar`
  - `C:/…` and `C:\\…` and **mixed** `C:\\Users\\x/y/z.jar` open/load

### Phase 4 — Hardening (2–4 months) — **WINE COMPLETE**

- GC stress, multi-thread stress, crash dumps, resource leaks handles — **PASS** under wine64 (`tools/verify/win64_phase4/`).
- Crash path: VEH diagnostics + unhandled filter + **MiniDumpWriteDump** to `run/crash/*.dmp` (`runtime_windows.cc`).
- Performance smoke (arraycopy/string churn) **PASS**.
- **Gate:** A5–A8 stable under wine; host Phase-4 re-run recommended via updated host package.
- See `tools/verify/win64_phase4/RESULT.md`.

### Phase 5 — JIT / oat (optional v1.1+)

- Win64 quick entrypoints complete.
- JIT code cache W^X.
- dex2oat either ported or deferred (interpreter+JIT may suffice).
- **Gate:** optional; declare v1 without it if needed.

**Calendar (one strong engineer, part-time Linux still maintained):** ~12–24 months to solid interpreter product; faster with 2–3 people if split (build system / runtime OS / libcore).

---

## 7. Risk register (full-port oriented)

| Risk | Severity | Mitigation |
|------|----------|------------|
| VEH ≠ Linux signals subtlety | Critical | Early Phase 2 spike; differential tests vs Linux oracle |
| Win64 ABI assembly volume | Critical | Defer JIT; minimize asm in v1; shared C++ entrypoints where AOSP allows |
| libcore native breadth | High | Golden-app-driven bring-up; stub with clear `UnsatisfiedLinkError` / exceptions |
| Vendor submodule churn vs Windows patches | High | Compat-first; tiny vendor-patches; CI on both OSes |
| Handle vs fd impedance in ART `unix_file` | High | UTF-8 path bridge; extend `fd_file` Windows ifdefs already partially present |
| CFG / W^X / antivirus on JIT later | Medium | Start interpreter; document JIT policy |
| Effort starves Linux product | High | Shared tests; Linux remains reference; Windows phases gated |
| Underestimating “full” | High | Use acceptance bar §2; do not call tools-only “full” |

---

## 8. Relationship to the Linux port

| Aspect | Guidance |
|--------|----------|
| Finish Linux e2e? | **Still valuable** as the oracle and boot.jar producer; not a substitute for Windows. |
| Shared code | bp2cmake, most of ART C++, dex format, Java boot content. |
| Divergent code | OS spine, assembly, libcore natives, CMake link model, crypto ASM flavor. |
| Dual maintenance cost | Expect ongoing ~20–40% tax after both work, unless Windows is frozen. |

Do **not** block all Windows design work on perfect Linux polish — but **do** keep one OS green. Dual red trees will not converge.

---

## 9. What we will not do (under this mandate)

- Recommend WSL2 as the product.
- Claim AOSP already supports full Windows ART.
- Ship with `ART_TARGET_LINUX` macros and call it Windows support.
- Use MSVC `cl` / `clang-cl` as the ART **compiler**.
- Use MinGW-w64 headers or the `windows-gnu` triple instead of **Windows SDK / MSVC SDK headers**.
- Omit the Windows SDK and hope Clang’s resource directory is enough for Win32 APIs.
- Require Android framework libraries on Windows.
- Promise month-scale full parity including JIT without the phase gates above.

---

## 9b. Phase 2 status (imageless Hello / A3) — **DONE**

**2026-07-16 rev19:** A3 **PASSED** under wine64 (imageless `-Xint`, `-cp run/hello.jar Hello`).

```text
Hello from dalvikvm!
java.version=0
exit 0
```

See `tools/verify/win64_phase2/RESULT.md` and `tools/verify/win64_phase1/hello_attempt54.log`.

### Landed (runtime)
- dlmalloc WIN32 mmap override fixed (MORECORE, low-4g non-moving).
- MemMap `mprotect`/`msync`/`madvise` Win64 behavior.
- LinearAlloc / arena pools forced **low 4GB** on Win64.
- VEH register + stack dump; SignalCatcher skipped; `-Xno-sig-chain` allowed.
- **SysV vs MSVC ABI:**
  - Win64 `ArtMethod::Invoke` → `EnterInterpreterFromInvoke` (skip quick invoke stubs).
  - `ExecuteSwitchImplAsm`: `sysv_abi` call from C++; `RDI→RCX` before calling C++ impl.
  - Expanded `InterpreterJni` / `InterpreterJniGeneric` for Phase-2 shorties (FJ, encode/decode, VLJ, …).
  - `ResolveJniEntryPoint` without `art_jni_dlsym_lookup_stub` (`%gs`).
- `InitNativeMethods` loads `libicu_jni.dll` / `libjavacore.dll` / `libopenjdk.dll` on Win64.
- Phase-2 PE JNI stubs: `tools/win64/jni_stubs/` (`libcombined.dll` stand-in) — **not** full libcore.

### Follow-on (Phase 3+)
- Real PE libcore / ICU natives (replace stubs).
- Complete property table (`java.version` currently stub `0`).
- Native Windows host validation (wine is gate-only).
- JIT / quick entrypoints / GS TLS when leaving pure `-Xint`.


## 9c. Phase 2 root cause — dlmalloc WIN32 mmap (2026-07-16)

`dlmalloc.c` `#ifdef WIN32` forces `HAVE_MMAP=1` / `HAVE_MORECORE=0`, so non-moving mspaces grow via `VirtualAlloc` **outside** ART's low-4g `MemMap`. Objects at `0x7ffffe9c…` cannot live in compressed refs / card table.

**Fix:** suppress that configure block in `art-dlmalloc.cc` and keep ART MORECORE; register non-moving as `dlmalloc_space_`. Rebuild + Hello re-run pending.

## 10. Final answer

**Full native Win64 support for ART without Android platform APIs is feasible** as a deliberate second OS port of this project. It is **not** blocked by the “no platform API” rule. It **is** blocked today by missing runtime OS backends, exception model, Win64 ABI entrypoints, DLL productization, and libcore native Windows implementations.

With WSL and MinGW ruled out, and MSVC **compiler** ruled out, the only honest path is:

1. Add `ART_TARGET_WINDOWS` + project-owned Windows runtime spine.  
2. Lock **compiler** to **LLVM Clang** (`clang`/`clang++`, `lld`, `libc++`, `compiler-rt`) via `/home/agent/Projects/win64-dev-env`.  
3. Lock **platform headers** to the **MSVC/Windows SDK** (um/shared/ucrt + import libs; `~/xwin` / env `xwin`).  
4. Extend bp2cmake + a Windows port_policy.  
5. Deliver by phases against the acceptance bar in §2.  
6. Treat Linux as the reference implementation, not the only ship vehicle.

**Feasibility rating:** **Go, with eyes open** — high engineering cost, clear architecture, no fundamental impossibility.

---

## 11. References (in-tree)

- [filesystem_win32.md](filesystem_win32.md) — Win64 path/filesystem feasibility (layers A/B/C, mixed paths)

- [project_scope.md](project_scope.md) — Linux product + three-layer converter  
- [overlay/port_policy.py](overlay/port_policy.py) — current Linux-only Layer 2  
- [native/CMakeLists.txt](native/CMakeLists.txt) — Unix/clang harness  
- `vendor/art/libartbase/base/globals.h` — target identity (extend for Windows)  
- `vendor/art/libartbase/base/mem_map_windows.cc` — partial MemMap (extend)  
- `vendor/art/runtime/{fault_handler,signal_catcher,thread_linux,runtime_linux}.cc` — must be Windows-paralleled  
- `vendor/art/runtime/base/mutex.h` — futex gated on `__linux__`  
- `vendor/art/build/Android.bp` — runtime disabled on Windows upstream  
- `vendor/libcore/luni/src/main/native/Portability.h` — needs Windows counterpart  
- `tools/verify/e2e/RESULT.md` — Linux e2e baseline for oracle tests
- `/home/agent/Projects/win64-dev-env/README.md` — Win64 cross-dev environment (clang/lld, xwin SDK, libc++, compiler-rt)
- `/home/agent/Projects/llvm-runtimes-win64/README.md` — libc++ cross-build notes
- `/home/agent/Projects/llvm-windows-msvc/` — official LLVM Windows package cache (compiler-rt source)  

---

*Phase 0–3 gated; Phase 4 wine hardening complete (GC/thread/handle/crash-dump). Host Phase-4 re-run recommended.*
