# Feasibility: Full Native Win32 ART (no Android platform API, no WSL)

Product tree: **dalvikvm-multiplatform** (nested vendor + artmp_*).

> **Arch lock:** **64-bit only** (`x86_64-pc-windows-msvc`, PE32+). “Win32 API” below means the Windows platform API on x64, not a 32-bit product.

Status: historical feasibility and phased-port record; Phases 0–3 gate-complete,
Phase 4 Wine-complete with the authoritative Windows Server 2025 build-26100
native gate accepted, x86_64 quick/nterp/managed/native JIT enabled by default,
and W-010/W-014 Stage E accepted on that host. The former Windows 10 lab host
is no longer available for future gates.
Updated: 2026-08-06

Future native-gate policy: use only Windows Server 2025 Datacenter Evaluation
x64 build 26100. See
[native Windows gate policy](win32_host_gate_policy.md).

**Living tracker (leftovers + temporary workarounds):** [win32_open_items.md](win32_open_items.md)
Product goal (owner requirement): **full native Windows NT support** for this repo’s ART runtime — a real `dalvikvm.exe` + DLLs + `boot.jar` that runs plain Java on Win32 x64 **without** Android platform APIs and **without** WSL/VM indirection.

This document answers: *is that feasible, what does “full” mean, and what is the actual port plan?*

Grounding: current Linux port (`bp2cmake_linux_scope.md`, `overlay/art_port_policy.py`, `native/CMakeLists.txt`) and vendored AOSP ART/libcore (android-16 era art + libcore).

---

## 0. Mandate and non-goals

### In scope (required)

1. **Native PE process** on Windows 10/11 **x64 only** (Windows x64). 32-bit x86 Windows is **out of scope**.
2. Same product shape as Linux: hand the VM a dex/jar + main class; it executes bytecode.
3. **No Android platform API**: no framework, binder, Zygote, ashmem daemon, statsd, APEX linker namespaces, `libandroid`.
4. **No WSL2 / Hyper-V guest / Docker-on-WSL** as the delivery mechanism. Build and run are first-class Windows.

### Explicitly out of scope (unless later expanded)

- Android app model (Activities, PackageManager, etc.).
- Device ABI emulation for arbitrary APKs.
- Full Java SE / OpenJDK replacement semantics beyond what Android libcore already provides on Linux.
- Cygwin/MSYS2/MinGW as toolchains or runtime personalities (no `msys-2.0.dll` / `libgcc_s` / MinGW binutils dependency).
- MSVC **as the C/C++ compiler** (`cl`, `clang-cl`). **Using the MSVC/Windows SDK header set with Clang is required**, not forbidden.
- An alternate PE-form OAT container. Windows boot AOT keeps the current Linux
  ART ELF64 header identity, uses a page-size-agnostic 64-KiB artifact layout,
  and uses an ART-owned private-copy mapping path. PE remains the process/DLL
  format, not the OAT container.
- `ProhibitDynamicCode`/ACG compatibility. ART-created executable memory is an
  explicit product prerequisite for JIT and OAT; policy rejection must be
  clean but is not a supported operating mode.

### Word “Win32” vs Windows x64

In Windows APIs, “Win32” often means the classic Windows API surface (including on x64). **This port is Windows x64-only:**

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
| Recommended stance | **Accept full Windows x64 as a first-class second OS target.** Sequence work so Linux remains the correctness oracle, but design the OS boundary so Windows is not a dead end. |

**Bottom line:** Full native **Windows x64** support is a **real OS port of ART + libcore natives**, not an extension of `ART_TARGET_LINUX`. It is worth doing only with that understanding. With that understanding, it is **doable** by isolating a Windows platform layer, reusing AOSP’s partial Windows leaf code, and phasing interpreter → libcore → JIT.

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

The current x86_64 product additionally requires Windows CET user shadow
stacks (Hardware-enforced Stack Protection) and context-IP validation to be
disabled for the ART process. The startup guard rejects the defined
shadow-stack, audit, strict, context-validation, and non-CET-binary fields,
but permits `CetDynamicApisOutOfProcOnly` and ignores `ReservedFlags` because
neither is evidence that HSP is enabled. Explicit PE marking and the early
fail-closed query guard are implemented; forced incompatible-policy rejection
remains pending native acceptance. This is a platform prerequisite, not an
unmet W-025 feature; CFG remains separate.

The original plan allowed JIT/dex2oat to be a v1.1 gate. Current x86_64 quick,
nterp, managed-JIT, and native-JIT entrypoints are correct and default-on;
Windows `dex2oat` trivial no-image generation passes the W-028 native operation
gate twice with structurally valid artifacts. W-030 now generates and stages an
LZ4 boot set and passes validation-only plus executable private-copy ELF/VDEX
loading under an experimental `-Xint` startup. W-031 implements the core
`.oat_unwind.windows` writer/parser/registration path, locates underlying
managed/JNI AOT bodies, and passes corresponding JIT-disabled runtime calls,
but ordinary dispatch
inside boot-OAT RX ranges remains unproven because startup upgrades many
current entrypoints to nterp. Deeper unwind, CFG, and product integration remain
pending. Step 8 is complete because
one manifest binds and validates each matching path-sensitive cache set;
cross-generation byte identity is not required.

---

## 3. Why this is a real port (evidence)

### 3.1 Upstream baseline did not ship a Windows runtime

At the Android base tag, ART defaults disabled Windows, `globals.h` had no
`ART_TARGET_WINDOWS`, and runtime support stopped at leaf-level Windows files
such as `mem_map_windows.cc`. The current `artmp_*` branch has since added the
target identity, build policy, and the project-owned runtime spine under
`vendor/art/runtime/multiplatform/windows/`. This section records why the port
was necessary; it is not a description of the current branch.

### 3.2 Linux port still assumes Unix

Current Layer 2 forces `ART_TARGET` + `ART_TARGET_LINUX`, CMS, glibc macros on javacore, Linux boringssl `.S` paths, `dlopen` of `libjavacore` / `libopenjdk` / `libicu_jni`, `-pie` / `--export-dynamic`. That product **cannot** be renamed to Windows.

### 3.3 Hard dependencies that must be reimplemented

| Subsystem | Linux mechanism | Windows replacement |
|-----------|-----------------|---------------------|
| Null checks / SO / some GC traps | SIGSEGV/SIGBUS + sigchain + ucontext | VEH (`AddVectoredExceptionHandler`) + `CONTEXT` / `EXCEPTION_POINTERS` |
| Alt signal stack | `sigaltstack` | Not applicable; careful stack guard + VEH stack discipline |
| Mutex fast path | futex (`ART_USE_FUTEXES` on `__linux__`) | `WaitOnAddress`/`WakeByAddress*` (Win8+) and/or SRWLOCK + condition vars; audit non-futex paths |
| Mapping | `mmap`/`mprotect`/`madvise` | `VirtualAlloc`/`VirtualProtect`/`PrefetchVirtualMemory`/`DiscardVirtualMemory`; extend `mem_map_windows.cc` |
| Thread identity | pthread TLS / ART TLS layout | `FlsAlloc`/`TlsAlloc` or TEB-based TLS; Windows x64 GS/FS conventions differ |
| Dynamic load | `dlopen` / `.so` | `LoadLibraryW` / DLLs; explicit exports |
| Entrypoints / mterp | GAS SysV ELF `.S` | **Windows x64 ABI** assembly (or C++ fallback where possible) |
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
Layer 2  art_port_policy.py:
           common product policy
           + explicit target delta selected by make_overlay(profile)
    │
    ▼
Layer 3  CMake emission + native/CMakeLists.txt OS branches
    │
    ▼
vendor/art/.../multiplatform/windows/   ART OS spine (folded into nested artmp_*)
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

**Canonical env root (agent01):** `/home/agent/Projects/windows_x64-dev-env` — see **§4.2.4**.  
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
- Assembler: Clang IA for `.S`; the required Windows x64 calling-convention ports
  are now implemented in the x86_64 ART sources.
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
| Integrated assembler (`.S` → COFF) | **Yes** | Same driver; the Windows x64 calling-convention work was ABI work and is now implemented for x86_64. |
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
Win32 OS DLLs on x64 at runtime (kernel32, ntdll, ucrtbase, …)
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

**Short answer:** **Yes for build/CI artifacts; no as a substitute for Windows
runtime validation.** Cross-compile is the first-class compile/link path.
Native G12 and focused W-024/W-013 host evidence now exist, while Wine remains
a development gate only.

| Stage | On Linux host? | Notes |
|-------|----------------|--------|
| Compile C/C++/ASM → COFF | **Yes** | Spot-check: agent01 Ubuntu clang 21 already produces `x86-64 COFF` with `-target x86_64-pc-windows-msvc`. |
| Assemble ART `.S` to COFF | **Yes** | Integrated assembler; the product x86_64 sources now contain the required Windows x64 ABI bridges. |
| Preprocess/include `windows.h` / UCRT | **Yes, iff sysroot** | Linux Clang does **not** ship these. Need a Windows Kits tree on the Linux machine (see below). |
| Link `dalvikvm.exe` / DLLs | **Yes** | agent01 has Clang 21.1.8, `lld-link`/`ld.lld`, xwin SDK libraries, Windows-target compiler-rt, and cross-built libc++. |
| Build libc++ for Windows target | **Yes / bring-your-own** | Either use a prebuilt Windows libc++ in the sysroot or build libc++ once for `x86_64-pc-windows-msvc` and cache it. |
| Run `dalvikvm.exe` | **Wine gate only** | PE does not run natively on Linux; Wine executes development gates but is not the product acceptance bar. |
| Full e2e (A3–A8) | **No on Linux alone** | Requires Windows test machine/CI runner; native G12 has passed. |

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

cmake -S native -B build/windows_x64 -G Ninja   -DCMAKE_SYSTEM_NAME=Windows   -DCMAKE_SYSTEM_PROCESSOR=AMD64   -DCMAKE_C_COMPILER=clang   -DCMAKE_CXX_COMPILER=clang++   -DCMAKE_ASM_COMPILER=clang   -DCMAKE_C_COMPILER_TARGET=x86_64-pc-windows-msvc   -DCMAKE_CXX_COMPILER_TARGET=x86_64-pc-windows-msvc   -DCMAKE_ASM_COMPILER_TARGET=x86_64-pc-windows-msvc   -DCMAKE_CXX_FLAGS="-stdlib=libc++ -isystem $WINSDK/Include/<ver>/ucrt -isystem $WINSDK/Include/<ver>/um -isystem $WINSDK/Include/<ver>/shared"   -DCMAKE_C_FLAGS="-isystem $WINSDK/Include/<ver>/ucrt -isystem $WINSDK/Include/<ver>/um -isystem $WINSDK/Include/<ver>/shared"   -DCMAKE_EXE_LINKER_FLAGS="-fuse-ld=lld -stdlib=libc++ -L$WINSDK/Lib/<ver>/ucrt/x64 -L$WINSDK/Lib/<ver>/um/x64"   -DCMAKE_SHARED_LINKER_FLAGS="-fuse-ld=lld -stdlib=libc++ -L$WINSDK/Lib/<ver>/ucrt/x64 -L$WINSDK/Lib/<ver>/um/x64"   -DMDVM_WINDOWS_SDK_ROOT="$WINSDK"   -DCMAKE_BUILD_TYPE=RelWithDebInfo
```

(Exact `-isystem` / version dir names should be centralized in a `cmake/WindowsLLVM.cmake` module; the sketch is the shape, not the final path discovery.)

**Historical hard corners and their current resolution**

1. **codegen driver / host tools:** the build keeps Python and generated-source
   tooling on the Linux host, then compiles generated output for the Windows
   target. Host and target roles are no longer conflated.
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
     - **libc++:** **not** shipped in that official Windows tarball (headers/libs absent). **Cross-built** from `llvmorg-21.1.8` on Linux → `/home/agent/Projects/llvm-runtimes-windows_x64/install/` (`c++.dll`, `c++.lib`, `libc++.lib`, `include/c++/v1`). ABI=`vcruntime`; link with `msvcprt`. Smoke under wine64: `libc++-windows_x64-ok`.
     - Host Ubuntu LLVM still only has `lib/clang/21/lib/linux` — use the two `~/Projects/...` trees as the Windows-target runtimes, not the host package.
   - Bottom line: **Linux cross-compile path is ready for C++ Windows x64** (clang + lld + `~/xwin` + prebuilt compiler-rt + cross-built libc++).

   - **wine64 recheck (2026-07-16):** package `wine64` **10.0** (`wine-10.0`, Ubuntu). Prefix `~/.wine` initializes. Cross-linked PE from clang+lld+`~/xwin` runs under `WINEDEBUG=-all wine64`:
     - trivial EXE exit 0;
     - `printf` + `GetCurrentProcessId()` printed `wine64-ok pid=…` and exited 0.
     - `wine32` **not** installed (64-bit PE only — matches Windows x64 primary target).
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
| **libc++** for same triple | **No** in that official package (no `include/c++`, no `c++.dll`/`libc++.lib`) | Cross-built under `/home/agent/Projects/llvm-runtimes-windows_x64/` from `llvmorg-21.1.8`; installed to `…/install/` |
| Host apt `libclang-rt-21-dev` | Linux only | Not usable as Windows target libs |

See `/home/agent/Projects/llvm-runtimes-windows_x64/README.md` for rebuild flags (clang resource includes before UCRT; `-lmsvcprt` for shared libc++).

**Feasibility rating (Linux cross-compile):**

| Scope | Rating |
|-------|--------|
| Compile + link Windows PE/DLL from Linux with LLVM + MSVC/Windows SDK sysroot | **Go** (standard; needs sysroot + lld + host/target tool split) |
| Replace Windows test machines entirely | **No** |
| Cross-compile using MinGW packages on Linux | **Rejected** by toolchain lock |

#### 4.2.4 Development environment (locked setup on agent01)

**Canonical root:** [`/home/agent/Projects/windows_x64-dev-env`](/home/agent/Projects/windows_x64-dev-env)

This is the assembled **Linux → Windows x64** toolchain for this project. It does **not** replace the ART OS port work; it only makes compile/link of Windows PE/DLL (and later ART) reproducible.

##### What is installed / required

| Layer | Component | Location / version | Notes |
|-------|-----------|--------------------|--------|
| Host compiler | LLVM **clang / clang++** | system 21.1.8 | Driver must be `clang++`, not `cl` / `clang-cl` |
| Host linker | LLVM **lld** (`lld-link`) | system 21.1.8 | COFF/PE linker |
| Build | CMake ≥ 3.20, Ninja, Python3 | system | |
| Platform SDK | Windows SDK + UCRT + MSVC CRT import libs | `windows_x64-dev-env/xwin` → `~/xwin` | Win11 SDK **10.0.26100** via **xwin** |
| C++ stdlib | **libc++** (shared + static) | `windows_x64-dev-env/lib/libcxx/` | Cross-built from `llvmorg-21.1.8`, ABI=`vcruntime` |
| compiler-rt | builtins (+ sanitizer libs) | `windows_x64-dev-env/lib/clang/21/lib/windows/` | From official `clang+llvm-21.1.8-x86_64-pc-windows-msvc` release |
| CMake integration | `cmake/WindowsX64LLVM.cmake` + `WindowsX64LLVMTargets.cmake` | under env root | Cross toolchain file |
| Optional PE runner | wine64 10.0 | system | Smoke only — **not** product acceptance |

**Not** part of the env: MinGW, MSVC `cl`, MSVC STL as ART’s C++ library, 32-bit targets.

##### Activate

```bash
source /home/agent/Projects/windows_x64-dev-env/env.sh
windows_x64-info
windows_x64-smoke    # full host+sysroot+C+C+++wine+cmake smoke
```

`env.sh` exports `WINDOWS_X64_DEV_ENV`, `WINDOWS_X64_CMAKE_TOOLCHAIN`, SDK/libcxx/compiler-rt paths, and helpers `windows_x64-clang` / `windows_x64-clangxx` / `windows_x64-lld-link`.

##### CMake cross-build pattern

```bash
source /home/agent/Projects/windows_x64-dev-env/env.sh
cmake -S <src> -B <build> -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$WINDOWS_X64_CMAKE_TOOLCHAIN" \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build <build>
# Deploy c++.dll next to EXEs when using shared libc++:
#   cp "$WINDOWS_X64_LIBCXX_LIB/c++.dll" <build>/
```

In a `CMakeLists.txt` after `project(...)`:

```cmake
include(${WINDOWS_X64_LLVM_TARGETS_FILE})   # or $ENV{WINDOWS_X64_DEV_ENV}/cmake/WindowsX64LLVMTargets.cmake
target_link_libraries(my_target PRIVATE windows_x64::libcxx)  # or windows_x64::libcxx_static
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
| libc++ | **Cross-built** on Linux | `/home/agent/Projects/llvm-runtimes-windows_x64/` (see its `README.md`) |
| SDK headers/libs | **xwin** splat | `/home/agent/xwin` (+ `~/.xwin-cache`) |
| Unified consumer view | assembled | `/home/agent/Projects/windows_x64-dev-env` |

Host package helper (idempotent):  
`windows_x64-dev-env/scripts/ensure-host-packages.sh` (clang, lld, cmake, ninja-build, python3).

##### Verification status (2026-07-16)

`scripts/smoke-test.sh` **ALL SMOKES PASSED** on agent01:

- host tools present  
- SDK + libc++ + compiler-rt paths valid  
- C PE (kernel32) + C++ PE (libc++) link  
- wine64 runs both  
- CMake toolchain configures and builds `hi.exe`

##### What this environment did *not* finish by itself

The environment only removed the “can we compile C++ for Windows x64?” blocker. The
runtime spine, VEH, threads, entrypoints, and libcore natives were later
implemented in this repository and are described by the phase records below.

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

New files under nested ART multipath paths (or injected via overlay `add_srcs`):

| File | Role |
|------|------|
| `stack_windows.{h,cc}` / `thread_windows.cc` | Implemented W-014 fixed-page selection/state/restoration plus bounded `Thread` integration; no `sigaltstack` |
| `runtime_windows.cc` | Runtime platform initialization plus fatal UEF/minidump policy; expected managed faults must not use the diagnostic path |
| `monitor_windows.cc` | Contention logging no-op / ETW later |
| `fault_handler_windows.cc` | Optional split for the selected W-010 exact access-violation/non-owning-`CONTEXT` adapter if it is not kept with the Windows sigchain facade |
| `os_windows.cc` | Replace `os_linux.cc` file ops with Win32/`_wsopen_s` UTF-8 bridge |
| `sigchain_windows.cc` | Narrow ART special-`SIGSEGV` facade over one first VEH; no general POSIX signal emulation |
| `windows_x64/*.S` or `.asm` | Entrypoints / mterp as needed |

Upstream `mem_map_windows.cc` is **necessary but not sufficient** — extend for `MAP_FIXED`-like placement used by ART heaps/code cache, or change ART heap placement policy on Windows via flags.

### 4.5 Synchronization strategy

1. Prefer **`WaitOnAddress` / `WakeByAddressSingle`** (Windows 8+) to mirror futex closely so less of `mutex.cc` must die.
2. Keep `ART_USE_FUTEXES` conceptually as `ART_USE_WAIT_ON_ADDRESS` under a project define on Windows, **or** implement a futex-like wrapper in compat and leave ART sources less patched.
3. Fallback: force non-futex mutex path and fix every `LOG(FATAL)` / incomplete branch — higher patch surface.

Recommended: **compat futex emulation** over `WaitOnAddress` to minimize vendor diffs.

### 4.6 Assembly / interpreter strategy (phased)

**Phase I (required for A3):** maximize **C++ interpreter / nterp C paths** where AOSP allows; only port mandatory stubs.

**Phase II:** port **Windows x64** quick entrypoints + interpreter assembly:

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
   - **OS I/O / path** → Win32 in nested `vendor/libcore` (ojluni + multiplatform/windows; see §4.7.1 / win32_filesystem.md).
   - **Linux-only** (`epoll`, `sendfile`, vsock, …) → Win32 IOCP/select equivalents or stub with checked exceptions.
3. Replace forced `__GLIBC__` / `LINUX` defines in Windows overlay with a **Windows SDK / UCRT** policy (include paths from the kit; never glibc macros).
4. `Portability.h`: Windows edition (no `byteswap.h` / `sys/sendfile.h` as mandatory).

Product-class apps (network bots, CLI) need A4+A7; pure compute may pass earlier.

#### 4.7.1 Win32 path model (mandatory mixed/hybrid paths)

> Detailed layer analysis (libcore vs libart): **[win32_filesystem.md](win32_filesystem.md)**.

**Product requirement:** ART on Win32 must accept **Windows-native and mixed separators** in filesystem paths, and **resolve absolutes to normal Win32 form** (`C:\path\to\file`, not `/…` and not `\\?\` by default). See [win32_filesystem.md](win32_filesystem.md) §1.5. Examples:

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
4. OpenJDK already solved this in **`java.io.WinNTFileSystem`** (+ `WinNTFileSystem_md.c`). The Android base tag did not ship those sources; the
   current project has ported/refitted them under `vendor/libcore/ojluni` and
   `vendor/libcore/multiplatform/windows`.

**Classpath list separator is a separate axis** (do not conflate with file separators):

| Axis | Android/Linux today | Win32 ART requirement |
|------|---------------------|------------------------|
| File path chars inside one path | `/` | **`\` and `/` both valid; mixed OK**; prefer normalize-to-Win32 for kernel calls |
| Multi-path list (`-cp`, `-Xbootclasspath`, `java.class.path`, `DexPathList`) | `:` | **`;` implemented and required**; Linux keeps `:`. This avoids splitting drive-letter paths. |

**Architecture (revised hybrid):**

1. **`java.io` path facade:** adopt a **Windows-capable `FileSystem`** (OpenJDK `WinNTFileSystem` lineage or equivalent project class), not bare `UnixFileSystem`, for Win32 product builds.
2. **Byte I/O:** `IoBridge` → `Libcore.os` uses the implemented PE
   open/read/write/close/stat bridge; the path facade and Os layer both accept
   mixed paths.
3. **NIO.2 (`sun.nio.fs`):** **non-goal for now** (no Windows provider port). Leave Linux-shaped stubs / fail clearly; **`java.io.File` must not lag**.
4. **Normalize at the Win32 boundary:** before `CreateFileW` / `GetFileAttributesW`, normalize mixed paths to a consistent wide path (OpenJDK WinNT does this; do not rely on accidental CRT tolerance alone).
5. **`path.separator=;`** on Win32; ART `-cp` / `-Xbootclasspath` parsing must use `;` (not hardcoded `:`).
6. **Phase-2 stubs** (`UnixFileSystem.getBooleanAttributes0`, relative `run/…`) remain a **bootstrap**, not the product path model.

**Decision:** **Option H (Hybrid)** locked — [win32_filesystem.md](win32_filesystem.md). WinNT-class `java.io` + Os/IoBridge + ART open; **`;` lists**; normal `C:\…` absolutes. **Windows NIO.2 is a non-goal for now.** Still smaller than “replace all of libcore.”

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

### Layer 2 (`art_port_policy.py`, Windows target delta)

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
- When a vendor edit is unavoidable (for example a `globals.h` target enum),
  commit it on the pinned nested `artmp_*` branch with clear Windows rationale.
  The top-level repository records the gitlink; it does not maintain a second
  patch queue.
- Goal remains: Layer 1 absorbs AOSP churn; Windows OS spine stays project-owned.

---

## 6. Phased delivery plan (full support)

Each phase has a kill-or-continue gate. This is the execution roadmap when implementation starts.

### Phase 0 — Foundations (2–4 weeks) — **DONE (2026-07-16)**

- Toolchain bootstrap: **LLVM clang/lld + Win SDK (xwin) + libc++ + compiler-rt** via `/home/agent/Projects/windows_x64-dev-env` (Linux cross → PE). No `cl`, no MinGW.
- Layer 1: `Config(os="windows")` + `bp2cmake --os windows` selects `target.windows` (e.g. `errors_windows.cpp`, `mem_map_windows.cc`).
- Layer 2: the Windows delta in `overlay/art_port_policy.py`.
- Built PE32+ DLLs: `log`, `base`, `nativehelper`, `ziparchive`, `artpalette`, **`artbase`**.
- **Gate:** `libartbase` links — **PASSED** (`build/windows_x64_phase0/artbase.dll`). See `docs/history/windows_x64_phase0_result.md`.

### Phase 1 — Skeleton VM (1–2 months) — **DONE (2026-07-16)**

- Port policy + harness for full ART graph on `x86_64-pc-windows-msvc`.
- `thread_windows` / `runtime_windows` / `monitor_windows` / `sigchain` stubs; PE asm + WaitOnAddress futex path.
- Linked `dalvikvm.exe` + `art.dll` (+ deps); JNI default library is `art.dll` on Windows.
- **Gate:** `dalvikvm -showversion` (A2) — **PASSED** under `wine64` → `ART version 2.1.0 x86_64`.
- Historical details: `docs/history/windows_x64_phase1_result.md`.

### Phase 2 — Interpreter Hello (2–4 months) — **DONE (2026-07-16, wine64 A3)**

- Crash-diagnostic VEH was sufficient for the Phase-2 Hello path; managed
  implicit-null and stack-overflow fault translation did not exist at that
  checkpoint and was tracked as W-010. W-014 Stages A-B have since implemented
  accurate Windows stack
  bounds, requested reservation sizing, pthread lifetime, measured excluded-low
  accounting, the fixed ART protected page, and detach restoration. The
  W-010 Stage C exact-record/live-`CONTEXT` adapter and Stage D atomic
  null/SO activation are also implemented. Native A-B/E and handler-policy
  acceptance remain.
  Their selected coupled design is
  [win32_faults_and_stacks.md](win32_faults_and_stacks.md).
- MemMap extensions for heap + boot image optional (imageless OK).
- Minimal JNI registration; **reduced boot.jar** if needed to reach Hello, then grow.
- Windows x64: only required assembly stubs; expanded C++ `InterpreterJni` for PE shorties.
- Phase-2 PE JNI stubs: `tools/windows_x64/jni_stubs/` (stand-in for real libcore natives).
- **Gate:** A3 Hello.main imageless interpreter — **PASSED under wine64** (`-cp run/hello.jar Hello`).
  Native Windows host re-check remains product/Phase-3 follow-on; wine is the agent01 cross-build gate.

### Phase 3 — libcore bring-up (3–6 months, overlaps Phase 2) — **COMPLETE**

- Foundations (2026-07-16): Option H path/FS + `;` classpath; A4–A7 + GoldenApp under wine64.
- A5 forced GC: `System.gc()` hang fixed (`GetThreadTimes` ThreadCpuNanoTime + WaitOnAddress ETIMEDOUT); current gate `art.w004.managed_gcforced`.
- See `tests/cases/windows-libcore-smoke/RESULT.md` and
  `docs/windows-port-notes/windows_x64_phase3_system_gc_hang_fix.md`.
- Path gates: `File.isAbsolute("C:\\…")`, mixed/UNC, and multi-JAR `-cp a;b` **PASS** natively as `art.w004.managed_pathprobe`.
- **Pitfall:** imageless ART has `Character.isLetter('C')==false` (no ICU props). `WinNTFileSystem` must use ASCII `isDriveLetter`, not `Character.isLetter`.
- **Shell pitfall:** bash splits on `;` — multi-jar `-cp` must be passed via argv list (Python subprocess), not a shell string.
- File I/O (P7): `FileInputStream`/`FileOutputStream` round-trip **PASS** (`art.w004.managed_ioprobe`); PE FD must run `<init>` for `releaseLock`.
- A4 core: arraycopy/UTF-8/reflect/threads monitors **PASS** (`art.w004.managed_coreprobe`).
- A7 classic loopback `ServerSocket`/`Socket` payload echo **PASS** (`art.w004.managed_netprobe`); NIO.2 still non-goal.
- A5/A6/GoldenApp + forced System.gc **PASS** on native Windows through the unified W-004 stage.
- Absolute C: JAR load P2–P4/P8, P5 parent/name, and P9c colon rejection **PASS** natively as `art.w004.managed_abspathprobe`.
- Runtime free/total/maxMemory **PASS** (`art.w004.managed_rtmem`) via art `JVM_*` exports + PE Runtime natives.
- Props/time/`java.version=1.8.0` and Os errno + UTF-8 paths **PASS** through the unified W-004 stage.
- The historical Phase-3 host package was staged and accepted before its shell
  producer was retired; its text evidence remains with the libcore case.
- The historical full Wine suite **PASS** remains evidence; its migrated behavioral subset now passes through 26/26 shell-free native W-004 CTest gates.
- Historical host-package integrity under Wine was **PASS** (not a substitute
  for the accepted native-host result). The archive remains outside VCS and
  the producer/checklist are no longer maintained entry points.
- First Win10 G12 evidence analyzed: paths/props/GC PASS; **net poll EINVAL FAIL**; false OVERALL PASS from cmd ERRORLEVEL clobber.
- G12 real Win10 host goldens **PASS** ([retained result](tests/cases/windows-libcore-smoke/evidence/windows-x86_64-msvc/g12_result.txt), 2026-07-16T205926): net/dns/golden/abspath/props/GC all markers green.
- Phase 3 acceptance (A4–A7 + Option H + golden app on native Windows) **met**.

The original Phase-3 implementation list is complete: systematic native
registration, UTF-8 file/path handling, classic networking, Option H
`WinNTFileSystem` semantics, ICU data loading, and the PE crypto/TLS stack are
all product paths. Windows NIO.2 remains a non-goal.

### Phase 4 — Hardening (2–4 months) — **WINE COMPLETE; FOCUSED NATIVE SUBSETS PASS**

- GC stress, multi-thread stress, crash dumps, and resource-leak handles — **PASS** under wine64; see `docs/history/windows_x64_phase4_result.md`.
- Crash path: separate diagnostic VEH plus predecessor-preserving unhandled filter and **MiniDumpWriteDump** to `run/crash/*.dmp` (`runtime_windows.cc`); the W-010 managed VEH/context adapter is product-enabled for exact Windows x64 nterp/JIT implicit null and stack-overflow faults and has focused Wine stress.
- Performance smoke (arraycopy/string churn) **PASS**.
- **Gate:** A5–A8 stable under Wine. Focused native Windows W-024 JNI/JVMTI and
  W-013 heap/JIT/handle/repeated-start matrices pass; the broader general
  Phase-4 host rerun remains H-001.
- See `docs/history/windows_x64_phase4_result.md`.

### Phase 5 — JIT / oat — **JIT COMPLETE FOR X86_64; AOT STEP 1 COMPLETE**

> **Implemented x86_64 design and cross-ISA record:** TLS / managed ABI / quick
> entrypoints / nterp / JIT:
> [win32_tls_jit_entrypoints.md](win32_tls_jit_entrypoints.md).

- Windows x64 quick entrypoints, nterp, managed JIT, and native JIT are default-on.
- The JIT code cache uses the corrected unnamed pagefile-section dual view with
  a low contiguous R/RX primary and a full RW updater alias.
- W-025's final dual-view path, CFG execution, direct-encoding guards, and
  unsupported-policy rejection are accepted. `ProhibitDynamicCode` rejection
  is a negative boundary, not a supported runtime profile. CET user
  shadow stacks are explicitly unsupported and must be disabled for the ART
  process under W-010's activation contract.
- Boot-only AOT implementation has started. W-028 now builds the Windows x64
  `dex2oat.exe` and its trivial no-image operation gate; the target alignment
  and process-wide `artbase.dll` prerequisite are implemented. The enabled
  watchdog, VDEX finalization, mapped-file flushing, and binary-descriptor
  prerequisites now complete under a repeated Wine diagnostic. W-028 passes
  twice on native Server 2025 and produces validator-clean OAT/VDEX files; the
  recorded outputs happened to match, but byte identity is not required. This
  completes generation step 1. W-030 now supplies the boot-set generation and
  private-copy loading slices described below. The imageless interpreter+JIT
  product does not require them.
- W-029 starts sequence step 2 by pinning one `boot` component, logical
  `/system/framework/boot.jar`, package `runtime/boot.jar`, and explicit
  package-relative `-Ximage:runtime/boot-image/boot.art`. Its native preflight
  passes and diagnoses seven deliberate spelling/path/topology mismatches.
  W-030 makes Windows `ImageWriter`, the manifest, staging, and native ART
  startup consume that contract. Step 2 remains partial because the seven
  negative cases are launcher-level pre-spawn checks rather than ART-level
  mismatch diagnostics.
- Windows boot AOT keeps the current Linux ART ELF64 header identity:
  `ART_PAGE_SIZE_AGNOSTIC=1` remains enabled and Linux `EI_OSABI`/ABI
  version/e_flags behavior is retained. Linux stays at 16-KiB `PT_LOAD`
  alignment; Windows uses 64 KiB to match its allocation granularity. There is
  no separate Windows ELF coat identity.
- The first implementation is boot-only and reuses
  `ElfOatFile`/`ElfFile`/`OatFileBase` where practical. A narrow private-copy
  helper serves validation-only opens at an arbitrary private address and
  executable opens in the exact already committed ART reservation, preserves
  the `oatdex`/VDEX contract, applies final protections, flushes code, and
  registers checked Windows x64 AOT unwind data after `Setup()`. Whole-span commit
  is selected for the initial OAT-1 path to match current Windows `MemMap`
  semantics. The private-copy ELF/VDEX part is implemented and W-030 proves
  validation-only and executable opens, R/RX/RW protections, no-access gaps,
  zero fill, owner sharing, cache flush, and `oatdex` reuse. The initial
  Windows `boot.art` is LZ4 so ART uses anonymous decompression instead of an
  unrepresentable exact file view in the committed reservation; Linux remains
  uncompressed. W-031 proves the core unwind transport, managed/JNI and seven
  trampoline lookups, synthetic virtual unwind, and JIT-disabled managed/JNI
  runtime calls. Corruption/fallback injection, exception/fatal stack walking, stronger
  XMM-bearing AOT-frame execution, and normal RX dispatch proof remain.
- An alternate PE-form OAT, `LoadLibraryExW`, `SEC_IMAGE`, a general
  Bionic-linker port, application OAT, unloading, and shared-view/OAT-2 work
  are outside the initial milestone. Security hardening is deferred. CFG uses one
  architecture-neutral `.oat_cfg.windows` section with target ABI in its
  independently versioned header. Observation mode is the early default and
  characterizes guarded incoming OAT calls without target API changes. W-032
  is bounded to that metadata/observation path and does not instrument outgoing
  indirect branches in generated quick code. Explicit-target mode is
  separately gated on establishing invalid-by-default CFG state without W+X;
  the documented OAT-1 RW/NX-to-RX transition is default-valid, so a
  dual-view/OAT-2 allocation may be required.
- The remaining functional work is ART-level negative identity diagnostics,
  unwind completion and CFG transport, normal product selection with
  successful whole-transaction imageless fallback, OAT-1 measurements, and
  proof that real boot methods execute from the OAT RX range rather than
  JIT/nterp. The compiler-to-OAT unwind and CFG transports are no longer open
  format design: their layouts, writer integration, runtime validation, and
  mode boundaries are specified and now await implementation and native gates.
- The format analysis, Bionic reuse boundary, mapping design, risk register,
  correctness invariants, and Server 2025 proof gates are in
  [win32_aot_oat.md](win32_aot_oat.md); live progress is in
  [win32_aot_oat_tracker.md](win32_aot_oat_tracker.md).

**Historical planning estimate:** the original estimate was 12–24 months for a
solid interpreter product with one part-time engineer. It is retained only as
the feasibility record, not as a current schedule.

---

## 7. Risk register (full-port oriented)

| Risk | Severity | Mitigation |
|------|----------|------------|
| VEH ≠ Linux signals subtlety | Critical | Diagnostic VEH/minidump support and the active W-010 exact-record/non-owning-`CONTEXT` adapter are landed and Wine-verified. Common `FaultManager` now translates repeated nterp/JIT NPE/SOE while validating R15 and the W-014 page; every unrecognized exception still continues search. Native Windows debugger/foreign-VEH/SEH ordering, negative AVs, stack budget, fatal predecessor-UEF behavior, and repeated NPE/SOE remain required. |
| CET user shadow-stack mismatch | Critical | Current x86_64 `art_quick_do_long_jump` restores the regular stack and returns without synchronizing CET's protected return stack; W-010 also redirects `CONTEXT.Rip`/`Rsp`. Stage 0 marks every project PE `/CETCOMPAT:NO`, audits packaged DLLs, and rejects every defined incompatible `ProcessUserShadowStackPolicy` field before memory/thread/JIT startup. `CetDynamicApisOutOfProcOnly` is compatible and reserved fields are not interpreted. Native forced-policy acceptance remains; CFG is separate. |
| Windows stack discovery / growth differs from pthread stacks | Critical | W-014 Stages A-B reject fibers, use `GetCurrentThreadStackLimits()` plus a complete `VirtualQuery()` allocation walk, apply `_beginthreadex` reservation semantics with retained join handles/tagged external identities, pass thread-pool reservation sizes, measure the bottom exclusion, and install/restore a verified fixed `PAGE_NOACCESS` page without adopting Windows' moving one-shot `PAGE_GUARD`. Native small/default/large reservation, guard-growth, and detach/reattach acceptance remains. |
| Windows x64 ABI assembly volume | Critical | x86_64 quick/nterp/JIT bridges are implemented; retain Linux/Windows x64 ABI matrices |
| libcore native breadth | High | Product hybrid map tracks 82 implemented and 44 intentional ENOSYS methods |
| Vendor submodule churn vs Windows patches | High | Nested `artmp_*` branches, small OS boundaries, and cross-host gates |
| HANDLE vs socket/fd impedance | High | Explicit process-wide socket-fd registry plus UTF-8/wide path bridges |
| CFG / W^X / antivirus on JIT | Medium | Corrected dual view is default; broader mitigation/direct-encoding work remains W-025 |
| Effort starves Linux product | High | Shared boot.jar and Linux imageless gates keep Linux as the reference |
| Underestimating “full” | High | Use acceptance bar §2 and the living tracker; do not call Wine-only evidence full acceptance |

---

## 8. Relationship to the Linux port

| Aspect | Guidance |
|--------|----------|
| Linux e2e status | **Complete and still valuable** as the oracle and shared boot.jar producer; not a substitute for Windows. |
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
- Support or run under CET user shadow stacks/Hardware-enforced Stack
  Protection in the current Win32 ART ABI. All defined incompatible HSP and
  context-IP-validation fields must be disabled; compatibility, audit, and
  strict modes are not supported. `CetDynamicApisOutOfProcOnly` is not HSP
  enablement, and reserved policy fields are not classified as features.
- Promise month-scale full parity including JIT without the phase gates above.

---

## 9b. Phase 2 status (imageless Hello / A3) — **DONE**

**2026-07-16 rev19:** A3 **PASSED** under wine64 (imageless `-Xint`, `-cp run/hello.jar Hello`).

```text
Hello from dalvikvm!
java.version=0
exit 0
```

See `docs/history/windows_x64_phase2_result.md`; the transient Phase-1 attempt log is not retained.

### Landed (runtime)
- dlmalloc WIN32 mmap override fixed (MORECORE, low-4g non-moving).
- MemMap `mprotect`/`msync`/`madvise` Windows x64 behavior.
- LinearAlloc / arena pools were forced **low 4GB** on Windows x64 as a Phase-2
  stabilization measure. W-013 Stage E removed that policy after the encoding
  audit; runtime/compiler/JIT metadata and the card table now follow Linux-like
  anywhere placement.
- VEH register + stack dump; SignalCatcher skipped; `-Xno-sig-chain` was
  allowed for the historical Phase-2 interpreter path. Stage D removes that
  Windows exception: normal started runtimes reject it exactly as Linux does;
  only genuine non-started compiler/tool runtimes retain the option.
- W-014 Stages A-B exact current-stack validation, `_beginthreadex` reservation
  semantics, opaque join/detach/result lifetime, tagged external thread
  identity, Windows thread-pool sizing, measured excluded-low accounting,
  fixed-page state/restoration, and diagnostic VEH/UEF teardown are locally
  implemented. Focused Wine page/reattach and product gates pass; native A-B
  acceptance remains.
- **SysV vs MSVC ABI:**
  - Windows x64 `ArtMethod::Invoke` → `EnterInterpreterFromInvoke` (skip quick invoke stubs).
  - `ExecuteSwitchImplAsm`: `sysv_abi` call from C++; `RDI→RCX` before calling C++ impl.
  - Expanded `InterpreterJni` / `InterpreterJniGeneric` for Phase-2 shorties (FJ, encode/decode, VLJ, …).
  - `ResolveJniEntryPoint` without `art_jni_dlsym_lookup_stub` (`%gs`).
- `InitNativeMethods` loads `libicu_jni.dll` / `libjavacore.dll` / `libopenjdk.dll` on Windows x64.
- Phase-2 PE JNI stubs: `tools/windows_x64/jni_stubs/` (`libcombined.dll` stand-in) — **not** full libcore.

### Historical follow-on (Phase 3+; completed)

- Real PE libcore / ICU natives replaced the bootstrap stubs.
- The property table reports `java.version=1.8.0`.
- Native Windows G12 plus focused W-024/W-013 acceptance are recorded.
- Quick invoke, rSELF TLS replacement, nterp, and JIT are product-default.


## 9c. Historical Phase-2 root cause — dlmalloc WIN32 mmap (2026-07-16)

`dlmalloc.c`'s standalone `#ifdef WIN32` defaults force `HAVE_MMAP=1` and
`HAVE_MORECORE=0`. The non-moving mspace therefore grew through dlmalloc-owned
`VirtualAlloc` mappings outside ART's low-4-GiB `MemMap`. Objects observed near
`0x7ffffe9c...` could not satisfy compressed-reference and heap-addressing
contracts.

The Phase-2 recovery fix hid `_WIN32`/`WIN32` while including `dlmalloc.c`, kept
ART MoreCore, and registered the non-moving space as `dlmalloc_space_`. The
rebuild and imageless Hello rerun completed successfully; the old "pending"
wording was historical and is removed here.

That recovery fix was not the final allocator architecture. W-013 Stages A–E
landed on 2026-07-25: Windows macros remain visible; dlmalloc respects
embedding-provided configuration; ART compile-checks its MoreCore-only policy;
Win32 MoreCore uses page-size growth granularity; each mspace dispatches to its
attached owner; anywhere/low/exact address policy is explicit; `VirtualAlloc2`
enforces constrained placement; `MemMap` owns page-state transitions and whole
Windows mappings; and the Phase-2 blanket low placement for LinearAlloc,
metadata arenas, and the card table is removed. The Windows x64-only card-marking
skip and the equivalent non-moving allocation barrier skip are also gone.
Native Windows R2 closure stress passes 56/56 records, including pressure,
large heaps, both JIT memory modes, 20 repeated starts, handle churn, complete
metrics, and no dumps. W-013 is CLOSED; see
[win32_heap_memory.md](win32_heap_memory.md) and the accepted evidence under
`docs/history/windows_x64_w013_result.md`.

## 10. Conclusion and current position

**Full native Windows x64 support for ART without Android platform APIs is feasible**
as a deliberate second OS port. That conclusion is now backed by a real PE
runtime, libcore/ICU/OpenJDK product DLLs, imageless execution, GC/thread/handle
gates, and managed/native JIT operation with the corrected dual-view code
cache. The remaining work is tracked as focused platform debt rather than the
original missing runtime spine.

The lasting architecture is still:

1. use a project-owned Windows runtime/platform layer;
2. use LLVM Clang, lld, libc++, and compiler-rt with Windows SDK/MSVC SDK
   headers and import libraries;
3. keep Linux as the behavioral reference while isolating unavoidable Windows
   VM, exception, ABI, loader, and filesystem operations;
4. close remaining items against native Windows evidence, not Wine alone; and
5. keep platform differences at the OS boundary instead of forking ART's heap,
   JIT, metadata formats, or managed runtime semantics.

Current status and temporary workarounds live in
[win32_open_items.md](win32_open_items.md). Heap/dlmalloc W-013 is closed;
broader JIT-memory hardening remains W-025 and is maintained in
[win32_jit_memory.md](win32_jit_memory.md).

---

## 11. References (in-tree)

- [win32_filesystem.md](win32_filesystem.md) — Win32 path/filesystem feasibility (layers A/B/C, mixed paths)

- [bp2cmake_linux_scope.md](bp2cmake_linux_scope.md) — Linux product + three-layer converter  
- [overlay/art_port_policy.py](overlay/art_port_policy.py) — common policy and
  explicit target deltas selected by `make_overlay(profile)`
- [native/CMakeLists.txt](native/CMakeLists.txt) — Unix/clang harness  
- `vendor/art/libartbase/base/globals.h` — implemented `ART_TARGET_WINDOWS` identity
- `vendor/art/libartbase/base/mem_map_windows.cc` — Windows mapping and constrained dual-view implementation
- `vendor/art/runtime/multiplatform/windows/` — project Windows runtime spine
- `vendor/art/runtime/base/mutex.h` — futex gated on `__linux__`  
- `vendor/art/build/Android.bp` — runtime disabled on Windows upstream  
- `vendor/libcore/multiplatform/windows/` — Windows libcore Java/native implementation
- `docs/history/linux_e2e_initial_result.md` — historical Linux E2E baseline
  for oracle tests
- `/home/agent/Projects/windows_x64-dev-env/README.md` — Windows x64 cross-dev environment (clang/lld, xwin SDK, libc++, compiler-rt)
- `/home/agent/Projects/llvm-runtimes-windows_x64/README.md` — libc++ cross-build notes
- `/home/agent/Projects/llvm-windows-msvc/` — official LLVM Windows package cache (compiler-rt source)  

---

*Updated 2026-07-27: Phases 0–3 gated; Phase 4 Wine hardening complete;
focused native W-024 and W-013 matrices pass; W-010 Stages C-D exact-record,
live-context, and repeated nterp/JIT NPE/SOE probes pass under Wine with
product implicit null/SO translation active; native Stage E and broader
H-001/W-025 host work remain.*
