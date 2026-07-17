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
| Quick/JIT/TLS | **Designed** in draft doc; **not implemented**; invoke forced to interpreter |
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
- **State:** OPEN (ICU+javacore+openjdk PE staged for product; surface still hybrid)
- **Kind:** leftover
- **Area:** build / libcore / icu
- **Gap:** Linux has full `.so` graph from bp2cmake; Win64 has **real ICU** + **hybrid javacore** (`tools/verify/win64_libcore_icu`). ICU + hybrid javacore + **AOSP openjdk NIO PE** landed and are **product-default** via `stage_native_modules.sh` (W-005 closed). Still missing full AOSP `libcore_io_Linux`, Memory, Expat, NativeBN, NetworkUtilities, crypto PE; NIO.2 excluded by design.
- **Exit criteria:** PE DLLs built from AOSP sources without `libcombined` aliasing; GoldenApp + charset/locale smoke still pass.
- **Opened:** 2026-07-17
- **Progress:** see `tools/verify/win64_libcore_icu/RESULT.md`

### L-002 — boringssl / conscrypt / SSL PE
- **State:** OPEN
- **Kind:** leftover (priority only if apps need TLS)
- **Area:** crypto
- **Gap:** No `libcrypto` PE; win32_port notes win-x86_64 perlasm or C paths.
- **Exit criteria:** HTTPS/crypto golden or explicit non-goal product statement.
- **Opened:** 2026-07-17

### L-003 — Process/exec, rich locale, zip edge, UDP/IPv6 matrix
- **State:** OPEN
- **Kind:** leftover
- **Area:** libcore-stub
- **Gap:** Not covered by Phase 3 gates; behavior unknown or partial under stub.
- **Exit criteria:** Gate list + implementations or documented unsupported.
- **Opened:** 2026-07-17

### L-004 — Shrink or replace multi-name DLL staging
- **State:** OPEN (reduced)
- **Kind:** leftover / packaging debt
- **Depends on:** L-001, W-005
- **Note:** W-005 closed — no more one-stub-six-names. Remaining dual names are intentional ART sonames (`libicu_jni`/`libjavacore`/`libopenjdk`) plus short build names; optional cleanup only.
- **Opened:** 2026-07-17

### L-005 — Linux multiplatform imageless Hello / boot.jar CI gate
- **State:** OPEN
- **Kind:** leftover
- **Area:** linux-host
- **Gap:** After repo migration, host Linux verified `dalvikvm -showversion` only; bootjar+Hello not re-scripted as a required gate in this tree.
- **Exit criteria:** One scripted imageless Hello (or RESULT) on multiplatform `main`.
- **Opened:** 2026-07-17

### L-006 — phase1.cmake / generated Win graph pure-vendor consistency
- **State:** OPEN
- **Kind:** leftover
- **Area:** build
- **Gap:** Ensure no residual archive path assumptions inside generated Win/Linux cmake.
- **Opened:** 2026-07-17

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

## Closed items

_(None yet in this tracker. When closing a W-/L-/H- item, move a one-line summary here.)_

<!--
### W-000 — example
- **State:** CLOSED (YYYY-MM-DD) — fixed by …
-->

---

## Suggested next closures (priority)

1. **W-001–W-003** — after TLS/entrypoint implementation (design draft ready).  
2. **L-001** — deepen hybrid libcore surface (Memory/Expat/NativeBN/…); W-005/W-006 closed for ICU product PE.  
3. **H-001** — host Phase-4 with multiplatform package.  
4. **L-005** — Linux Hello gate so host oracle stays green.

---

## Maintenance checklist for future PRs

- [ ] New `#ifdef _WIN32` temporary behavior → new **W-** row  
- [ ] New stub JNI → update **W-005** export scope or split **W-**  
- [ ] Gate newly green on host → close matching **H-**  
- [ ] Permanent design choice (e.g. VEH forever) → move from W- to documented architecture; close workaround  
- [ ] CLOSED items: one line in §Closed, leave detail above with State CLOSED  

*Last snapshot: 2026-07-17 — W-005/W-006/W-016 CLOSED (real ICU PE + product packaging; no charset stubs); NetProbe OK.*
