# Win32 / multiplatform — open items & temporary workarounds

**Status:** living tracker  
**Created:** 2026-07-17  
**Rule:** Every **temporary workaround** that future work must remove belongs here as **OPEN**.  
When the proper fix lands, mark the item **CLOSED** (keep a one-line closure note; do not delete history).  
Do **not** list permanent non-goals as OPEN workarounds—list them under §Non-goals.

### Filename

| Name | Use |
|------|-----|
| **`win32_open_items.md`** (this file) | Preferred: leftovers **and** temporary workarounds |
| `win32_leftovers.md` | OK alias if you prefer |
| `win32_bug_tracker.md` | Prefer for defect IDs only; this file is broader |

### Related docs

| Doc | Role |
|-----|------|
| [win32_port.md](win32_port.md) | Product phases / feasibility |
| [filesystem_win32.md](filesystem_win32.md) | Option H path model |
| [win32_tls_jit_entrypoints.md](win32_tls_jit_entrypoints.md) | TLS / managed ABI / quick / JIT design (draft) |
| [win32_libcore_os_natives.md](win32_libcore_os_natives.md) | Os/`Linux` natives: Implemented / Needed / ENOSYS |
| `tools/verify/win64_phase*/RESULT.md` | Gate evidence |

---

## How to maintain

**Add** when you land a temporary path (compile stub, force-interpreter, fake DLL name, wine-only gate, etc.):

```markdown
### W-XXX — short title
- **State:** OPEN
- **Kind:** workaround | leftover | debt | host-gap
- **Area:** art | libcore-stub | icu | packaging | linux-host | docs | …
- **Symptom / why:** …
- **Current behavior:** …
- **Proper fix:** …
- **Code anchors:** `path:line` or symbol names
- **Blocked on / design doc:** …
- **Opened:** YYYY-MM-DD
```

**Close** when fixed:

```markdown
- **State:** CLOSED (YYYY-MM-DD) — one-line how
```

IDs: `W-` workaround, `L-` leftover/product gap, `H-` host/validation gap, `D-` docs/process. Numbers are stable; do not reuse.

---

## Snapshot (2026-07-17)

| Bucket | Summary |
|--------|---------|
| Phases 0–3 | **Gate-complete** (P3 G12 real Win10 + wine) |
| Phase 4 | **Wine complete**; host re-run still recommended |
| PE libcore/ICU/openjdk | **Product-default real PE** (icu/javacore/openjdk); NIO.2 non-goal; NetProbe OK |
| Quick/JIT/TLS | **Designed** in draft doc; **not implemented**; invoke forced to interpreter; **W-024** restore Critical/FastNative after |
| Linux multiplatform | Native `dalvikvm -showversion` OK; imageless Hello e2e not re-gated here |

---

## Temporary workarounds (must be removed later)

### W-001 — Force interpreter invoke (quick entrypoints effectively disabled)
- **State:** OPEN
- **Kind:** workaround
- **Area:** art / invoke
- **Symptom / why:** Win64 `art_quick_invoke_*` stubs assume SysV + managed `%gs:Thread*`; not ported.
- **Current behavior:** On `_WIN32`, `ArtMethod::Invoke` sets `use_interpreter_invoke = true` for invokable non-proxy methods → always `EnterInterpreterFromInvoke` (including natives via interpreter JNI).
- **Proper fix:** Win64 invoke stubs + managed self (see [win32_tls_jit_entrypoints.md](win32_tls_jit_entrypoints.md)); then remove the unconditional Win32 force (keep legitimate debugger/force-interpreter cases).
- **Code anchors:** `vendor/art/runtime/art_method.cc` (`#if defined(_WIN32)` force); comments on SysV + `%gs`
- **Blocked on:** TLS/entrypoint design lock-in + implementation
- **Opened:** 2026-07-16 (Phase 2)

### W-002 — No managed GS / Thread base on Windows (`InitCpu` no-op for GS)
- **State:** OPEN
- **Kind:** workaround
- **Area:** art / TLS
- **Symptom / why:** Linux x86_64 uses `ARCH_SET_GS` so quick/nterp use `%gs:OFFSET`. Windows GS is TEB.
- **Current behavior:** `thread_x86_64.cc::InitCpu` Win32 branch only documents TODO; relies on C++ `thread_local` / no GS verify. Quick asm that still uses `%gs` is unsafe/unused while W-001 holds.
- **Proper fix:** Explicit managed self register (draft: `r15`) + THREAD_LOAD/STORE macros; never set GS to Thread*.
- **Code anchors:** `vendor/art/runtime/arch/x86_64/thread_x86_64.cc`; design §6 in `win32_tls_jit_entrypoints.md`
- **Opened:** 2026-07-16

### W-003 — Quick entrypoint SETUP frames `int3` on Windows
- **State:** OPEN
- **Kind:** workaround (hard fail if reached)
- **Area:** art / quick asm
- **Symptom / why:** Many `SETUP_SAVE_*_FRAME` paths are stubbed for Apple/Win32.
- **Current behavior:** Hitting those macros traps (`int3`) rather than building callee-save frames.
- **Proper fix:** Port macros with Win self base + MS C++ edge ABI; remove `int3` guards.
- **Code anchors:** `vendor/art/runtime/arch/x86_64/asm_support_x86_64.S`, `quick_entrypoints_x86_64.S` (`#if defined(__APPLE__) \|\| defined(_WIN32)`)
- **Depends on:** W-001, W-002
- **Opened:** 2026-07-16


### W-024 — Restore original @CriticalNative / @FastNative surfaces after JIT/TLS/entrypoints
- **State:** OPEN
- **Kind:** workaround / debt (must revert multipath demotions)
- **Area:** art / libcore / JNI ABI
- **Symptom / why:** Official AOSP libcore marks many natives `@CriticalNative` or `@FastNative` (Math/StrictMath were **@FastNative → @CriticalNative** in AOSP; see libcore `d021f1d8475c`). Win64 multipath cannot yet honor those ABIs because:
  1. **W-001** forces interpreter invoke (no quick/managed entrypoints / TLS).
  2. Interpreter JNI historically lacked full CriticalNative shorty coverage (partially papered by **W-019** for Math `DD`/`DDD`/…).
  3. Product demotions for bring-up: **Math.ceil / Math.floor** are pure Java (`ART-WinNT` comments in `Math.java`; natives unregistered in `Math.c`) even though AOSP exposes them as `@CriticalNative` natives.
  4. Win `Math.c` uses a PE-specific registration table (`gMethodsWin` CriticalNative-shaped pointers) vs Linux `FAST_NATIVE_METHOD` macro table — temporary dual path until PE trampolines match AOSP.
- **Current behavior:**
  - Annotations remain on most Math/StrictMath/etc. methods, but **ceil/floor are non-native pure Java**.
  - Win64 relies on interpreter CriticalNative shorty dispatch + correct CriticalNative binding (no `JNIEnv*`) rather than real quick CriticalNative stubs.
  - FastNative methods stay Runnable on the interpreter bridge (W-019 supporting fix) instead of true FastNative entrypoints.
- **Proper fix (when JIT / TLS / quick entrypoints land — W-001–W-003 + [win32_tls_jit_entrypoints.md](win32_tls_jit_entrypoints.md)):**
  1. Restore **every** multipath demotion of methods that were originally `@CriticalNative` / `@FastNative` in AOSP (starting with **Math.ceil / Math.floor** → native + `@CriticalNative` again).
  2. Re-register matching natives in `Math.c` (and any other demoted tables) on **both** PE and ELF with AOSP-correct CriticalNative/FastNative ABIs.
  3. Prefer real ART CriticalNative/FastNative trampolines over InterpreterJni shorty expansion; then **trim** PE-only shorty explosion (**W-011**) and dual `gMethodsWin` paths where redundant.
  4. Audit libcore for other `ART-WinNT` pure-Java / ABI demotions of Critical/Fast natives (not just Math) and revert once entrypoints are product-default.
- **Exit criteria:**
  - No pure-Java stand-ins for AOSP `@CriticalNative`/`@FastNative` Math (ceil/floor native again).
  - Wine + Linux smokes for Math/HashMap/conscrypt without relying on pure-Java ceil or incomplete CriticalNative shorty lists.
  - Document that W-019 temporary ABI/shorty fixes are superseded (may remain as defensive fallback until deleted).
- **Code anchors:**
  - `vendor/libcore/ojluni/src/main/java/java/lang/Math.java` (`ART-WinNT` pure-Java ceil/floor)
  - `vendor/libcore/ojluni/src/main/native/Math.c` (`gMethodsWin` / no ceil|floor register; Linux `FAST_NATIVE_METHOD`)
  - `vendor/art/runtime/interpreter/interpreter.cc` (`InterpreterJniGeneric` CriticalNative shorties)
  - `vendor/art/runtime/art_method.cc` (Win32 force interpreter invoke)
  - AOSP history: `d021f1d8475c` FastNative→CriticalNative Math; multipath `f16cd44db5fe` pure-Java ceil/floor; `b9265e7b5da6` CriticalNative register fix; art `7ea144b073` / `4c17423714` interpreter Critical/FastNative bridge
- **Blocked on:** W-001–W-003 implementation (JIT/TLS/quick entrypoints)
- **Related:** W-019 (CLOSED temporary Math ABI fix), W-011 (InterpreterJni shorty expansion)
- **Opened:** 2026-07-17

### W-004 — `LOAD_RUNTIME_INSTANCE` PE helper call (vs GOT)
- **State:** OPEN (acceptable interim; still temporary vs ideal PE codegen)
- **Kind:** workaround
- **Area:** art / asm
- **Current behavior:** Win path calls `art_Runtime_instance_ptr` with shadow space instead of `@GOTPCREL`.
- **Proper fix:** Keep helper **or** RIP-relative import of `Runtime::instance_` consistently for JIT + hand asm (document single sequence).
- **Code anchors:** `LOAD_RUNTIME_INSTANCE` in `asm_support_x86_64.S`
- **Opened:** 2026-07-16

### W-005 — Combined PE JNI stub DLL aliased as libjavacore/libopenjdk/libicu_jni
- **State:** CLOSED (2026-07-17) — product packaging uses stage_native_modules.sh (real PE only); libcombined is legacy non-product
- **Kind:** workaround
- **Area:** libcore-stub / packaging
- **Symptom / why:** Full ojluni + ICU4C PE ports not built; ART `InitNativeMethods` still dlopens those sonames.
- **Current behavior:** `tools/win64/jni_stubs/libcombined.dll` copied to six names (`libjavacore.dll`, `libopenjdk.dll`, `libicu_jni.dll`, and short names). ~160 `Java_*` exports, hand-written (~2.3k LOC).
- **Proper fix:** Real PE modules (or fewer real DLLs) from Soong/bp2cmake Win64 graph: javacore, openjdk, icu_jni + icuuc/i18n, etc.; stop multi-name aliasing of one stub.
- **Code anchors:** `tools/win64/jni_stubs/build_combined.sh`, `tools/win64/host_package/package_win64_phase3.sh`, stage scripts in phase2 RESULT
- **Opened:** 2026-07-16 (Phase 2; expanded Phase 3)

### W-006 — Minimal NativeConverter / ICU version shims (not full ICU4C)
- **State:** CLOSED (2026-07-17) — product uses real icu_jni NativeConverter + icuuc/icui18n + icudt; native_converter.c obsolete and removed from libcombined; charset stub no longer product path
- **Kind:** workaround
- **Area:** icu
- **Current behavior:** Phase-3 package historically used `native_converter.c` stubs. **Phase A progress:** real PE `icuuc.dll` / `icui18n.dll` / `icu_jni.dll` now build from AOSP sources (`tools/verify/win64_libcore_icu/`) and can replace stub `libicu_jni` in `build/win64_phase1`. `libjavacore`/`libopenjdk` still combined stubs (may still register overlapping charset helpers until removed).
- **Proper fix:** Default package/install to real ICU PE only; remove charset exports from `libcombined`; verify full data (`ICU_DATA` / icudt) vs stubdata; complete L-001 for javacore/openjdk.
- **Code anchors:** `tools/verify/win64_libcore_icu/`, `tools/win64/jni_stubs/native_converter.c`
- **Opened:** 2026-07-16
- **Progress:** 2026-07-17 — real ICU PE + CoreProbe wine OK with hybrid package

### W-007 — Classic sockets / poll via Winsock `select` (not full Os/NIO)
- **State:** OPEN (functional for GoldenApp; incomplete API surface)
- **Kind:** workaround / incomplete port
- **Area:** libcore-stub / net
- **Symptom / why:** Full `libcore.io.Linux` PE not ported; Win10 rejected CRT-fd `WSAPoll` patterns.
- **Current behavior:** Hand-written socket/bind/connect/accept/read/write + poll via `select()`; enough for A7/GoldenApp; overloads/options incomplete (notes in source).
- **Proper fix:** Systematic Os natives PE port (or generate from AOSP with Win backends); keep select-based poll if correct.
- **Code anchors:** `tools/win64/jni_stubs/win_net_natives.c`; host analysis under `tools/verify/win64_phase3/evidence/host/`
- **Opened:** 2026-07-16

### W-008 — Product smoke always passes `-Xint` / imageless / `-Xno-sig-chain`
- **State:** OPEN
- **Kind:** workaround (policy flags)
- **Area:** packaging / product CLI
- **Current behavior:** Host package scripts and wine runners force interpreter + no boot image + no sigchain.
- **Proper fix:** After W-001–W-003, drop forced `-Xint` for default product scripts (keep as opt-in debug). Imageless may remain until boot image (separate track).
- **Code anchors:** `tools/win64/host_package/package_win64_phase3.sh`, `tools/verify/win64_phase*/run_*.sh`
- **Opened:** 2026-07-16

### W-009 — Phase-1 grade `compat` POSIX/pthread stubs
- **State:** OPEN
- **Kind:** workaround
- **Area:** compat
- **Current behavior:** `compat/src/win64_posix_stubs.c` + headers provide enough symbols to link ART; rwlock/poll/uname/etc. are simplified.
- **Proper fix:** Replace hot paths with real Win32 implementations or ART-native Windows backends; shrink stub surface over time.
- **Code anchors:** `compat/src/win64_posix_stubs.c`, `compat/include/**`
- **Opened:** 2026-07-16 (Phase 0/1)

### W-010 — Sigchain is a Windows stub; VEH owns faults
- **State:** OPEN (may become permanent architecture — reclassify if so)
- **Kind:** workaround → candidate permanent design
- **Area:** art / exceptions
- **Current behavior:** `sigchain_windows.cc` stub; crash/null/SO paths use VEH + minidump in `runtime_windows.cc`.
- **Proper fix:** Document as permanent WinNT model **or** deepen VEH/sigchain integration tests; remove any code that still assumes Linux sigchain interposition.
- **Code anchors:** `vendor/art/runtime/multiplatform/windows/sigchain_windows.cc`, `runtime_windows.cc`
- **Opened:** 2026-07-16

### W-011 — Expanded InterpreterJni shorty coverage for PE (bypass missing quick/JNI stubs)
- **State:** OPEN
- **Kind:** workaround
- **Area:** art / jni
- **Current behavior:** Extra shorty paths in interpreter JNI so Phase-2/3 natives work without full quick/JNI trampoline matrix.
- **Proper fix:** After real PE libcore + entrypoints, audit whether generic path suffices; trim PE-only shorty explosion if redundant.
- **Code anchors:** interpreter JNI / generic paths (Phase-2 RESULT notes: FJ/IJ/VLJ/…)
- **Opened:** 2026-07-16

### W-012 — `ResolveJniEntryPoint` without `art_jni_dlsym_lookup_stub` (`%gs`)
- **State:** OPEN
- **Kind:** workaround
- **Area:** art / jni
- **Current behavior:** Windows avoids GS-based JNI lookup stub.
- **Proper fix:** Fold into final managed-self / JNI trampoline design (W-002).
- **Code anchors:** Phase-2 RESULT; JNI resolution paths under `_WIN32`
- **Opened:** 2026-07-16

### W-013 — dlmalloc WIN32 / low-4GB / MORECORE choices for imageless ART
- **State:** OPEN (may stay as permanent Win allocator policy)
- **Kind:** workaround / platform policy
- **Area:** art / heap
- **Current behavior:** WIN32 mmap/MORECORE path + low-4g constraints for compressed refs / imageless bring-up (see Phase-2 root-cause notes).
- **Proper fix:** Re-validate against real Win10 under load; document as permanent if correct; remove any Linux-only assumptions left in comments.
- **Code anchors:** dlmalloc Win path / Phase-2 docs in `win32_port.md` §9c
- **Opened:** 2026-07-16

### W-014 — Stack bounds via VirtualQuery + clamp (Wine-safe estimates)
- **State:** OPEN
- **Kind:** workaround
- **Area:** art / threads
- **Current behavior:** Win `GetThreadStack` uses VirtualQuery + clamps; ProtectStack skipped/no-op on `_WIN32` in places to avoid mprotect of wrong regions.
- **Proper fix:** TEB-accurate stack bounds + optional guard pages when trusted; re-enable protection carefully.
- **Code anchors:** `vendor/art/runtime/thread.cc` Win branch; `ProtectStack` `#ifdef _WIN32`
- **Opened:** 2026-07-16

### W-015 — openjdkjvm memory exports minimal PE surface
- **State:** OPEN
- **Kind:** workaround
- **Area:** art / openjdkjvm
- **Current behavior:** `openjdkjvm_memory_windows.cc` supplies Runtime free/total/max/GC-related exports expected by stubs.
- **Proper fix:** Full `libopenjdkjvm` PE or merge into openjdk module with complete JVM_* set used by libcore.
- **Code anchors:** `vendor/art/openjdkjvm/openjdkjvm_memory_windows.cc`
- **Opened:** 2026-07-16

---


### W-016 — ICU needs external `ICU_DATA` / `icudt72l.dat` for wine smoke
- **State:** CLOSED (2026-07-17) — product always stages run/icu/icudt72l.dat via tools/win64/stage_run_assets.sh (same class as boot.jar); libicu_jni defaults ICU_DATA to run/icu when unset
- **Kind:** workaround
- **Area:** icu / packaging
- **Symptom / why:** Linked stubdata alone yields `u_init` `U_FILE_ACCESS_ERROR` under wine; full data file works.
- **Current behavior:** Stage `run/icu/icudt72l.dat` and set `ICU_DATA=run/icu` (or absolute path). `Register.cpp` also calls `udata_setCommonData(&U_ICUDATA_ENTRY_POINT)` on Win.
- **Proper fix:** Package full ICU data by default in host package scripts; verify embedded data path or always set ICU_DATA in runners.
- **Code anchors:** `vendor/icu/android_icu4j/libcore_bridge/src/native/Register.cpp`; `build/win64_phase1/run/icu/`
- **Opened:** 2026-07-17
- **Progress:** 2026-07-17 — `package_win64_phase3.sh` fails if `icudt72l.dat` missing; phase3/4 runners and install_into_phase1 default/export `ICU_DATA=run/icu`

### W-017 — openjdk hybrid excludes NIO.2 / async / UNIXProcess; epoll via select
- **State:** OPEN
- **Kind:** workaround / incomplete port
- **Area:** openjdk / nio
- **Current behavior:** Phase B2 builds AOSP NIO channel natives with Winsock CRT-fd shims; `epoll_*` emulated with `select`; NIO.2 UnixNativeDispatcher/WatchService/async EPollPort not registered.
- **Proper fix:** Keep NIO.2 non-goal; deepen channel/options matrix; optional IOCP epoll later if needed.
- **Code anchors:** `tools/verify/win64_libcore_icu/CMakeLists.txt` (`_OJ_SRCS` filters); `compat/src/win64_socket_posix.c`
- **Opened:** 2026-07-17

### W-018 — NetProbe StructLinger NPE (getsockopt SO_LINGER incomplete in javacore Win bridge)
- **State:** CLOSED (2026-07-17) — implemented getsockoptLinger/setsockoptLinger in win_net_natives; NetProbe wine PASS
- **Kind:** leftover / bug
- **Area:** libcore-stub / net
- **Symptom / why:** `NetProbe` fails: `StructLinger.isOn()` on null from linger get.
- **Proper fix:** Implement linger get/set in `win_net_natives` / Linux Os bridge returning real `StructLinger`.
- **Code anchors:** `tools/win64/jni_stubs/win_net_natives.c`; NetProbe client path
- **Opened:** 2026-07-17

## Product leftovers (not single-line workarounds)

### L-001 — Real PE libcore / openjdk / ICU module build
- **State:** OPEN (ICU+javacore+openjdk PE staged; hybrid surface deepened)
- **Kind:** leftover
- **Area:** build / libcore / icu
- **Gap:** Linux has full `.so` graph from bp2cmake; Win64 has **real ICU** + **hybrid javacore** + **AOSP openjdk NIO PE** (product-default via `stage_native_modules.sh`, W-005 closed). **Expat + NativeBN + NetworkUtilities + AsynchronousCloseMonitor + OsConstantsHolder** now in product PE (2026-07-17). Still missing full AOSP `libcore_io_Linux` compile; NIO.2 excluded; crypto PE under L-002.
- **Exit criteria:** PE DLLs built from AOSP sources without `libcombined` aliasing; GoldenApp + charset/locale smoke still pass. (product PE criterion already met; residual is remaining hybrid exclusions.)
- **Opened:** 2026-07-17
- **Progress:** see `tools/verify/win64_libcore_icu/RESULT.md`; Os map [win32_libcore_os_natives.md](win32_libcore_os_natives.md)
- **Progress:** 2026-07-17 — AOSP `Memory` in javacore; Linux bridge mmap/… + Needed pipe/pread/readv/timeval/sendto/…; see win32_libcore_os_natives.md (Needed residual small)
- **Progress:** 2026-07-17 — **Expat** (static `vendor/external/expat` 2.6.4), **NativeBN** (link `libcrypto`), **NetworkUtilities** (POSIX msghdr CMSG shims) in product `libjavacore.dll`; wine `BnProbe`/`XmlProbe`/`CoreProbe`/`NetProbe` PASS
- **Progress:** 2026-07-17 — **AsynchronousCloseMonitor** JNI + Win monitor + `win_close` NET_* wrappers; wine `AsyncCloseProbe` PASS (accept SocketException / read EOF)
- **Progress:** 2026-07-17 — **OsConstantsHolder** multipath `initConstants` (bionic AI/EAI/_SC ABI); wine `OsConstantsProbe`/`DnsProbe` PASS

### L-002 — boringssl / conscrypt / SSL PE
- **State:** OPEN (partial — C0–C3 smoke OK under wine; HTTPS golden suite / non-ASCII IDNA / win ASM still open)
- **Kind:** leftover (priority only if apps need TLS)
- **Area:** crypto
- **Gap:** ~~libcrypto/ssl/javacrypto PE~~ **C0+C1 done.** ~~conscrypt Java absent from boot.jar~~ **C2 packaged**. ~~OpenSSLProvider construct / Security.getProviders~~ **done (2026-07-17)**. Still missing: win-x86_64 ASM; BC optional (BKS); broader ICU4J resources for non-ASCII IDNA/normalization; HTTPS golden beyond smoke.
- **Exit criteria:** HTTPS/crypto golden **or** explicit non-goal. Crypto digests/providers met; SSLContext.init/HTTPS still open.
- **Code anchors:** hybrid CMake SSL/javacrypto; `tools/bootjar/build_conscrypt_win64.sh`; `libcore_hello3.c` mapLibraryName; boot.jar `com.android.org.conscrypt`
- **Opened:** 2026-07-17
- **Progress:** 2026-07-17 — W-019 Math.ceil fixed; Runtime.nativeLoad+JNI_OnLoad; jarjar prefix fix; LoadCryptoProbe OpenSSLProvider OK; **Security.getProviders PASS** (SecStep3) after Win64 FastNative interpreter routing + `FileChannelImpl.map0` LLP64 pointer fix (W-020); digests/SecureRandom/AES-GCM/SSLContext.getInstance OK; **SSLContext.init fails: `jks KeyStore not available`** (next)
- **Workaround note:** Do not claim HTTPS until SSLContext.init + connect golden green.

### L-003 — Process/exec, rich locale, zip edge, UDP/IPv6 matrix
- **State:** CLOSED (2026-07-17)
- **Kind:** leftover
- **Area:** libcore / openjdk hybrid
- **Gap:** Phase-3 product matrix for process/exec, locale (without full ICU4J bundles), zip edges, UDP IPv4, dual-stack IPv6 Os.socket bind.
- **Fix:**
  - `win_process_natives.c` CreateProcess `UNIXProcess` + openjdk OnLoad register
  - InterpreterJni 12-slot path for multi-arg natives (`forkAndExec`, `sendtoBytes`)
  - UDP `recvfrom` InetSocketAddress holder fill; multicast GroupReq/IpMreqn
  - ZipFile CEN: Windows heap-read + DirectByteBuffer mirror (mmap CEN invalid under wine)
  - LocaleProbe uses Calendar/String case without ICU DecimalFormatSymbols bundles
  - Ipv6Probe: Os.socket AF_INET6 bind on raw `::` (avoid reverse-DNS hang)
  - Gate: `tools/verify/win64_phase3/run_l003_wine.sh` — OVERALL PASS
- **Exit criteria:** Process/UDP/locale/zip/IPv6 gates documented + wine green **met**.
- **Non-goals / host residual:** TCP IPv4-mapped dual-stack under wine; full ICU Collator resources; zip STORED empty-dir edges beyond DEFLATED multi-entry.
- **Code anchors:** `win_process_natives.c`, `win_net_natives.c`, `ZipFile.java` (Win CEN), `FileInputStream.c` available0, `interpreter.cc` 12-slot, probes under `tools/verify/win64_phase3/src/`
- **Opened:** 2026-07-17
- **Closed:** 2026-07-17

### L-004 — Shrink or replace multi-name DLL staging
- **State:** CLOSED (2026-07-17) — product ships one PE soname each: `libicu_jni`/`libjavacore`/`libopenjdk`/`libopenjdkjvm`/`libcrypto`/`libssl`/`libjavacrypto` (+ `icuuc`/`icui18n`); short-name twins removed from packaging
- **Kind:** leftover / packaging debt
- **Depends on:** L-001, W-005
- **Fix:** CMake `OUTPUT_NAME` for hybrid targets; `stage_native_modules.sh` stages only product names and deletes short twins; install rejects short-name reappearance
- **Opened:** 2026-07-17

### L-005 — Linux multiplatform imageless Hello / boot.jar CI gate
- **State:** CLOSED (2026-07-17)
- **Kind:** leftover
- **Area:** linux-host
- **Gap:** ~~After repo migration, host Linux verified `dalvikvm -showversion` only~~ **scripted gate landed**.
- **Exit criteria:** One scripted imageless Hello (or RESULT) on multiplatform `main`.
- **Fix:** `tools/verify/linux_hello/run_imageless_hello.sh` + `RESULT.md` PASS on `build/native/dalvikvm` imageless `-Xint` Hello. Requires **UnixFileSystem** boot.jar (rejects Win64 WinNT product boot).
- **Opened:** 2026-07-17
- **Closed:** 2026-07-17

### L-006 — phase1.cmake / generated Win graph pure-vendor consistency
- **State:** CLOSED (2026-07-17)
- **Kind:** leftover / build
- **Area:** build
- **Gap:** ~~Residual MinDalvikVM-Archive path assumptions in product scripts~~ **pure-vendor**.
- **Fix / evidence:**
  - Product CMake (`tools/verify/win64_phase1`, `win64_libcore_icu`, `native/`, Linux verify) already resolved via `${MDVM_NATIVE_SRC_ROOT_DIR}` → **`vendor/`**; `phase1.cmake` has no hard-coded archive absolutes.
  - `tools/bootjar/build.sh` no longer auto-discovers sibling `MinDalvikVM-Archive(_)` for ICU/annotation stubs; requires nested `vendor/icu` + in-tree `compat/java-stubs` (expanded minimal android.annotation / android.compat.annotation set).
  - `MDVM_ARCHIVE` remains an optional non-default escape hatch only.
  - Docs/tests scrubbed: `README.md`, `native/{CMakeLists,generate}.sh`, `tools/bp2cmake` CODEGEN/codegen + unit tests point at multipath `vendor/`.
  - Historical `tools/verify/*/RESULT.md` absolute archive paths left as past evidence only (not product inputs).
- **Opened:** 2026-07-17
- **Closed:** 2026-07-17

---

## Host / validation gaps

### H-001 — Phase 4 re-run on real Windows host
- **State:** OPEN
- **Kind:** host-gap
- **Gap:** Wine Phase 4 PASS (incl. multiplatform rebuild 2026-07-17). Real Win10 Phase-4 subset (gcstress, threadheavy, handleleak, crash native/abort) not re-proven with multiplatform PE.
- **Exit criteria:** Host logs under `tools/verify/win64_phase4/evidence/host/` (or successor) OVERALL PASS.
- **Opened:** 2026-07-16

### H-002 — Phase 3 G12 with multiplatform-built PE (not only pre-migration tree)
- **State:** OPEN
- **Kind:** host-gap
- **Gap:** Authoritative G12 used earlier host package; multiplatform in-tree PE rebuild should re-package and smoke on Win10 when convenient.
- **Opened:** 2026-07-17

### H-003 — Wine is not product acceptance
- **State:** OPEN (policy reminder, not a code fix)
- **Kind:** host-gap / process
- **Note:** Keep wine as agent01 oracle; product claims need real Windows for VEH/TEB/network.
- **Opened:** 2026-07-16

---

## Non-goals (do not track as OPEN workarounds)

| Item | Decision |
|------|----------|
| Windows NIO.2 (`sun.nio.fs`) | Non-goal for now ([filesystem_win32.md](filesystem_win32.md)) |
| WSL2 / Wine as product runtime | Rejected |
| Win32 x86 product SKU | Out of scope (x64 first) |
| Full Android framework / zygote / binder | Out of scope |
| In-process dual JIT ISA (x64+Arm64EC) | Rejected in TLS/JIT draft |

If product reopens a non-goal, add an **L-** item and link the decision.

---

## Closed

- **D-001** — shared boot.jar runtime OS selection (**single jar** goal; not dual-host FS proof)
- **L-003** — Process/exec, locale, zip edge, UDP/IPv6 matrix (wine gate PASS)
- **L-005** — Linux imageless Hello / boot.jar CI gate
- **W-019..W-023** and other closed W- items: detail rows remain below / above with State CLOSED

<!--
### W-000 — example
- **State:** CLOSED (YYYY-MM-DD) — fixed by …
-->

---





### W-023 — OkHttp Http(s)Handler on bootclasspath + ASCII IDN/Normalizer multipath
- **State:** CLOSED (2026-07-17)
- **Kind:** packaging / compatibility
- **Area:** java.net URL / HTTPS
- **Root cause:** Android resolves `http/https` via `com.android.okhttp.HttpHandler`/`HttpsHandler`, not packaged in multipath boot.jar. After packaging, pure-ASCII OkHttp/TLS paths still required ICU4J StringPrep/Normalizer tables not present in boot.jar.
- **Fix:** `tools/bootjar/build_okhttp_win64.sh` merges repackaged OkHttp+okio into boot; `IDN.toASCII` and `java.text.Normalizer` short-circuit pure-ASCII; product ICU data preferred over stub in `libicu_jni` Register.cpp; cacerts already staged.
- **Exit criteria:** HttpsProbe handler resolution + `https://example.com/` status 200 under wine.
- **Opened/Closed:** 2026-07-17

### W-022 — Product default CA bundle (AndroidCAStore cacerts)
- **State:** CLOSED (2026-07-17)
- **Kind:** packaging / product asset
- **Area:** TLS trust / AndroidCAStore
- **Root cause:** Android `TrustedCertificateStore` reads `$ANDROID_ROOT/etc/security/cacerts/<subject_hash_old>.N`. Product previously shipped empty dirs, so SSLContext.init worked but trust set was empty.
- **Fix:** generate Mozilla/system PEM bundle into OpenSSL hash_old layout (`tools/win64/generate_cacerts.sh`), hermetic assets under `tools/win64/assets/cacerts`, stage via `stage_run_assets.sh` as required asset (with `boot.jar` / `icudt72l.dat`). LocaleData hard-coded fallback so OpenSSLX509Certificate date parsing works without full ICU4J resource bundles in boot.jar.
- **Exit criteria:** TrustStoreProbe AndroidCAStore.size>=50 and acceptedIssuers>=50 under wine with ANDROID_ROOT=run.
- **Opened/Closed:** 2026-07-17

### W-021 — Default KeyStore type Android-compatible (AndroidCAStore)
- **State:** CLOSED (2026-07-17)
- **Kind:** config / compatibility
- **Area:** JCA / conscrypt SSL defaults
- **Root cause:** Win64 multipath deferred BouncyCastle, so `keystore.type=BKS` could not resolve. `Security.initializeStatic()` also omitted `keystore.type`, so `KeyStore.getDefaultType()` fell back to desktop `jks`, which is not registered. `KeyManagerFactory.init(null,null)` → `KeyStore.getInstance("jks")` failed and `SSLContext.init` aborted.
- **Fix:** default `keystore.type=AndroidCAStore` (HarmonyJSSE/`TrustedCertificateKeyStoreSpi`, empty-loadable); restore loading `security.properties` on Windows after W-020; mirror in `build_conscrypt_win64.sh` and boot.jar resource.
- **Exit criteria:** KeyStoreProbe + SslProviderProbe `sslcontext.init=ok` under wine.
- **Opened/Closed:** 2026-07-17

### W-020 — FileChannelImpl.map0 pointer truncation on Win64 (LLP64)
- **State:** CLOSED (2026-07-17) — `ptr_to_jlong(mapAddress)` instead of `(jlong)(unsigned long)`
- **Kind:** bug / ABI
- **Area:** openjdk NIO / boot classpath ZIP mmap
- **Root cause:** AOSP `FileChannelImpl_map0` returned `(jlong)(unsigned long)mapAddress`. On Win64 LLP64 `unsigned long` is 32-bit, so mapped addresses like `0x6ffff…` were truncated (high bits zeroed). `Memory.peekByteArray` then crashed in CRT (`fault_addr=0xff0e0eec` pattern) while `VMClassLoader` clinit mapped `boot.jar` for `ClassPathURLStreamHandler`.
- **Symptom chain:** `Security.getProviders` → provider class load → `BootClassLoader.loadClass` → `findLoadedClass` path / resource handlers → ZIP mmap via NIO → AV. Earlier W-019-style AV signature was coincidental.
- **Also fixed nearby (supporting):** Win64 `-Xint` keeps natives on interpreter bridge (`ShouldStayInSwitchInterpreter` + `ArtInterpreterToInterpreterBridge` → `InterpreterJni`); FastNative stays Runnable; specialized static `LLL` shorty.
- **Exit criteria:** SecStep17 `BootClassLoader.loadClass` + SecStep3 `Security.getProviders` wine PASS.
- **Code anchors:** `vendor/libcore/ojluni/src/main/native/FileChannelImpl.c`; `vendor/art/runtime/interpreter/interpreter.cc`; `interpreter_common.cc`
- **Opened:** 2026-07-17
- **Closed:** 2026-07-17

### W-019 — Math @CriticalNative / FastNative double ABI on Win64
- **State:** CLOSED (2026-07-17) — Math.ceil/floor/sqrt + HashSet wine PASS after interpreter CriticalNative DD/DDD
- **See also:** **W-024** — full restore of AOSP Critical/FastNative after JIT/TLS/entrypoints (ceil/floor pure-Java demotion still OPEN debt)
- **Kind:** workaround / runtime ABI
- **Area:** libcore Math / ART interpreter JNI (Win64 -Xint)
- **Root cause:** Official AOSP CriticalNative is fine on Linux quick/generic-JNI. Win64 multipath forces `ArtMethod::Invoke` through the interpreter; `InterpreterJniGeneric` only handled CriticalNative shorties `II`/`I`/`Z`/`ZI`. `Math.ceil` is shorty `DD` (`(D)D`), so dispatch fell through and crashed. Secondary: registering `Math_*_jni(JNIEnv*,jclass,jdouble)` under CriticalNative is the wrong ABI.
- **Fix (landed source):** interpreter CriticalNative `DD`/`DDD`/`FF`/`J`; Math.c gMethodsWin → `Math_ceil(jdouble)` etc.; posix stubs `localtime_r`/`mingw_gettimeofday` for art rebuild.
- **Exit criteria:** `MathProbe` + `SslProviderProbe` wine PASS with rebuilt `art.dll`.
- **Code anchors:** `vendor/art/runtime/interpreter/interpreter.cc`, `vendor/libcore/ojluni/src/main/native/Math.c`, `compat/src/win64_posix_stubs.c`
- **Opened:** 2026-07-17
- **Progress:** 2026-07-17 — root cause + source fix; full art PE rebuild running

## Design notes

### D-001 — Shared boot.jar via runtime OS selection
- **State:** CLOSED (2026-07-17)
- **Goal (actual):** **one** multipath `boot.jar` (not dual packaged jars / not “prove WinFS-on-Win and UnixFS-on-Unix” as close criteria)
- **Doc:** `shared_bootjar_runtime_os_detection.md`
- **Canonical property:** `dalvik.vm.multiplatform.internal.os` = `windows` | `unix`
  - Long + `internal` intentional (not a public app API; not expected for external use)
  - Reject short `dalvik.vm.mp.os` (`mp` ambiguous)
  - Values: `windows`|`unix` (not `posix`, not `linux`) — aligns with `WinNTFileSystem` / `UnixFileSystem`
- **Injection:** `vendor/art/runtime/runtime.cc` after `PropertiesList` release (PE=`windows`, ELF=`unix` if unset)
- **Detection ladder:** `VMRuntime.properties()` → System props / `os.name` → default `unix` (`VMRuntime.isWindowsOs`)
- **Separators:** removed from `AndroidHardcodedSystemProperties`; set in `System.initUnchangeableSystemProperties`
- **Boot:** `tools/bootjar/build_win64.sh` stages shared jar (no WinNT-only overlay); jar embeds both FS + `isWindowsOs`
- **Exit criteria (met):** single shared boot pipeline produces one jar used for Linux imageless Hello (L-005 PASS on shared multipath bytes)
- **Non-goals for this close:** dual-host acceptance that Windows always selects `WinNTFileSystem` and Unix always selects `UnixFileSystem` under product PE/wine — those are ordinary product smoke, not D-001 scope
- **Follow-up (orthogonal):** wine/host Hello on same bytes; PE `art.dll` inject path when PE product is rebuilt
- **Code anchors:** `dalvik/system/VMRuntime.java` (`isWindowsOs*`), `DefaultFileSystem.java`, `System.java`, `runtime.cc`, `build_win64.sh`
- **Opened:** 2026-07-17
- **Closed:** 2026-07-17

## Suggested next closures (priority)

1. ~~**D-001**~~ **CLOSED** — single shared boot.jar (runtime OS selection); dual-host FS smoke is not the close bar.  
2. **W-001–W-003** — TLS/entrypoint implementation (design draft ready); then **W-024** restore Critical/FastNative surfaces.  
3. **L-001** — deepen hybrid libcore surface (Memory/Expat/NativeBN/…); W-005/W-006 closed for ICU product PE.  
4. **H-001** — host Phase-4 with multiplatform package.  
5. ~~**L-005** — Linux Hello gate~~ **CLOSED**.

---

## Maintenance checklist for future PRs

- [ ] New `#ifdef _WIN32` temporary behavior → new **W-** row  
- [ ] New stub JNI → update **W-005** export scope or split **W-**  
- [ ] Gate newly green on host → close matching **H-**  
- [ ] Permanent design choice (e.g. VEH forever) → move from W- to documented architecture; close workaround  
- [ ] CLOSED items: one line in §Closed, leave detail above with State CLOSED  

*Last snapshot: 2026-07-17 — L-003 CLOSED (run_l003_wine OVERALL PASS: exec/locale/zip/udp/ipv6); W-024 OPEN; D-001 CLOSED.*
