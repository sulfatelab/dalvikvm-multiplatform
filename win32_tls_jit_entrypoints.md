# ART on Windows NT — TLS, Managed ABI, Quick Entrypoints, and JIT

**Status:** DRAFT (research + design only; no implementation commitment in this document)  
**Date:** 2026-07-17  
**Scope:** Design **all** ART-WinNT ISA targets in theory; implement later with **x86_64 first**.  
**Related:** [win32_port.md](win32_port.md) (product phases), [win32_open_items.md](win32_open_items.md) (open workarounds W-001+), Phase 3+ runtime hardening, Phase 5 JIT/oat.

### Suggested filename

| Name | Rationale |
|------|-----------|
| **`win32_tls_jit_entrypoints.md`** (this file) | Covers the inseparable triad: OS TLS, managed Thread base access, quick entrypoints that JIT/nterp call into |
| `win32_tls_and_jit.md` | Slightly narrower; understates entrypoint/ABI volume |
| `art_winnt_managed_abi.md` | Good long-term title if the doc grows beyond Windows-only notes |

---

## 0. Why this document exists

Today’s multiplatform Win64 product runs **imageless interpreter** (`-Xint`). That path deliberately avoids:

- `%gs`-based `Thread*` access in quick/nterp assembly,
- SysV-shaped `art_quick_invoke_*` stubs,
- JIT code-cache emission and managed↔native bridges.

Leaving pure `-Xint` (phase 3+ / phase 5) requires a **coherent design** of three layers that AOSP treats as one machine-specific package:

1. **How C++ finds `Thread*`** (`Thread::Current()`).
2. **How managed / quick / nterp code finds `Thread*` and `QuickEntryPoints`**.
3. **Calling conventions** between JIT/nterp frames, quick entrypoints, and C++ (Win64 / Arm64 / Arm64EC ABIs).

This draft designs those layers for:

| Target label | Machine | Product role |
|--------------|---------|--------------|
| **win-x86_64** | Windows AMD64 PE | **Primary implementation focus** |
| **win-x86** | Windows i386 PE | DRAFT only (not a near-term product) |
| **win-arm64** | Windows ARM64 native PE | DRAFT; future WoA native |
| **win-arm64ec** | Arm64EC PE (x64-convention interop on ARM64) | DRAFT; mixed x64/ARM64EC process story |

Linux **amd64** and **arm64** remain the correctness oracles.

---

## 1. Research method and sources

Primary evidence is **this tree’s ART** (`vendor/art`, android-16.0.0_r4 / artmp):

| Area | Key files |
|------|-----------|
| C++ TLS | `runtime/thread-current-inl.h`, `runtime/thread.cc` (`Init`, `self_tls_`, pthread key / Bionic slot) |
| CPU self setup | `runtime/arch/x86_64/thread_x86_64.cc`, `runtime/arch/x86/thread_x86.cc`, `runtime/arch/arm64/thread_arm64.cc` |
| Managed self + entrypoints asm | `runtime/arch/x86_64/asm_support_x86_64.S`, `quick_entrypoints_x86_64.S`, `arm64/asm_support_arm64.S`, `quick_entrypoints_arm64.S` |
| Quick entrypoint table | `runtime/entrypoints/quick/quick_entrypoints.h`, `quick_entrypoints_list.h` |
| Invoke routing | `runtime/art_method.cc` (`art_quick_invoke_*`, Win32 force-interpreter) |
| Offsets | `tools/cpp-define-generator/thread.def` → `THREAD_*_OFFSET` |
| Win stubs already present | `LOAD_RUNTIME_INSTANCE` PE helper; `_WIN32` `int3` in many SETUP macros |

Secondary: platform ABI documentation (System V AMD64 / AArch64, Microsoft x64 / ARM64 / Arm64EC), and TEB/TLS layout knowledge used by Windows PE runtimes.

---

## 2. Two different “TLS” problems (do not conflate)

ART uses the word “TLS” for **two distinct mechanisms**:

```text
┌──────────────────────────────────────────────────────────────────┐
│ A. C++ Thread::Current()                                         │
│    - Bionic: fixed TLS slot TLS_SLOT_ART_THREAD_SELF             │
│    - glibc / host: thread_local Thread* self_tls_ (+ pthread key)│
│    - Used by almost all runtime C++                              │
└──────────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────────┐
│ B. Managed / quick / nterp Thread base                           │
│    - x86_64 Linux: GS base = Thread*, then %gs:OFFSET            │
│    - x86 Linux:    FS base = Thread*, then %fs:OFFSET            │
│    - arm64:        callee-saved xSELF (x19) = Thread*            │
│    - Holds tlsPtr_, quick_entrypoints, exception, top frame, …   │
└──────────────────────────────────────────────────────────────────┘
```

**Invariant:** After `Thread::Init` / attach, A and B must name the **same** `Thread*`.  
**Non-invariant:** A and B need **not** use the same OS mechanism. AOSP already splits them (C++ TLS vs GS/x19).

WinNT design must preserve that split and make B correct for **JIT and quick stubs**, not only for C++.

---

## 3. How ART behaves on real Linux

### 3.1 x86_64 Linux (amd64 SysV) — oracle for win-x86_64

#### OS / ABI baseline (SysV AMD64)

| Item | SysV AMD64 / Linux |
|------|--------------------|
| Integer args | `rdi, rsi, rdx, rcx, r8, r9` then stack |
| FP args | `xmm0–xmm7` |
| Return | `rax` / `rdx:rax`, `xmm0` |
| Callee-saved | `rbx, rbp, r12–r15` |
| Caller-saved | `rax, rcx, rdx, rsi, rdi, r8–r11`, XMMs used as args/temps |
| Red zone | 128 bytes below `rsp` (leaf only; ART frames usually explicit) |
| Thread pointer (libc TLS) | **FS** segment base → `struct pthread` / TLS blocks |
| PLT / PIC | `@GOTPCREL`, `@PLT` |

Linux libc owns **FS**. ART **must not** steal FS for `Thread*`.

#### ART choice: steal **GS** for managed `Thread*`

In `thread_x86_64.cc::InitCpu()` (Linux):

```text
arch_prctl(ARCH_SET_GS, this);   // GS base := Thread*
tlsPtr_.self = this;
// verify: movq %%gs:(THREAD_SELF_OFFSET), %reg  == this
```

Quick assembly then treats **`%gs` as an implicit `Thread*` base**:

```text
movq %gs:THREAD_SELF_OFFSET, %rdi          # pass Thread::Current()
movq %rsp, %gs:THREAD_TOP_QUICK_FRAME_OFFSET
cmpl $0, %gs:THREAD_DEOPT_CHECK_REQUIRED_OFFSET
```

Callee-save macros load `Runtime::instance_` via GOT (`LOAD_RUNTIME_INSTANCE`) and stash `ArtMethod*` at `[rsp]`, matching `Runtime::CreateCalleeSaveMethod(...)` layouts in `callee_save_frame_x86_64.h`.

#### C++ `Thread::Current()` on glibc host

Not GS. From `thread-current-inl.h`:

```text
#ifndef __BIONIC__
  Thread* thread = Thread::self_tls_;   // C++ thread_local
#endif
```

Attach path also sets `pthread_setspecific(pthread_key_self_, this)` for cleanup / some paths.

So on Linux amd64:

| Consumer | Mechanism |
|----------|-----------|
| Runtime C++ | `thread_local` / pthread key |
| Quick / nterp / JIT-generated code | **`%gs:offset`** with GS base = `Thread*` |
| Entry into managed | stubs assume GS already set for that OS thread |

#### Quick entrypoint table

`Thread` embeds `QuickEntryPoints` (pointers filled by `InitTlsEntryPoints`). Compiled code and trampolines call helpers **relative to Thread** (e.g. `QUICK_ENTRYPOINT_OFFSET(ptr_size, pAllocObjectResolved)`), not via global PLT for every helper. That is why a correct managed self base is mandatory before any non-interpreter invoke.

#### Invoke path

`ArtMethod::Invoke` → `art_quick_invoke_stub` / `_static_stub` (assembly, SysV args: method, args*, size, Thread*, JValue*, shorty).  
Win32 currently **forces** `EnterInterpreterFromInvoke` because those stubs + GS are not ported (`art_method.cc` comment: SysV + `%gs:THREAD_SELF`).

### 3.2 arm64 Linux (AArch64 Procedure Call Standard) — oracle for win-arm64

#### OS / ABI baseline

| Item | AAPCS64 (Linux) |
|------|-----------------|
| Integer args | `x0–x7` |
| FP args | `v0–v7` |
| Callee-saved | `x19–x28`, `d8–d15`, `x29/x30` frame |
| IP temps | `x16/x17` (IP0/IP1) |
| Platform / TLS | **TPIDR_EL0** for libc TLS; **x18** often platform reserved (Android treats carefully) |

#### ART choice: **register xSELF = x19**, not TPIDR

`asm_support_arm64.S`:

```text
#define xSELF x19
```

`thread_arm64.cc::InitCpu()` only **checks** offset constants; it does **not** program a system register with `Thread*`. Managed code assumes **x19 already holds `Thread*`** across quick frames (callee-saved). Entrypoints store top frame as:

```text
str xIP0, [xSELF, #THREAD_TOP_QUICK_FRAME_OFFSET]
```

This is the **cleanest multi-OS model**: managed self is an ordinary callee-saved pointer, independent of libc TLS.

### 3.3 x86 Linux (32-bit) — oracle for win-x86 (draft only)

Uses **`%fs`** as Thread base (`thread_x86.cc` / `quick_entrypoints_x86.S`: `pushl %fs:THREAD_SELF_OFFSET`). On Linux i386, FS is also entangled with historical libc TLS/LDT tricks; ART’s use is “base = Thread*” via LDT/`modify_ldt` style setup (see `thread_x86.cc`). Windows i386 instead uses **FS→TEB**; same conflict class as GS on x64.

### 3.4 Mental model summary (Linux)

```text
                    C++ world                    Managed/quick world
                 ──────────────                 ─────────────────────
  amd64 Linux    thread_local / pthread    GS.base = Thread* ; %gs:off
  arm64 Linux    thread_local / Bionic     x19 = Thread*     ; [x19,#off]
  x86 Linux      thread_local / pthread    FS.base = Thread* ; %fs:off

  QuickEntryPoints ⊂ Thread::tlsPtr_  (same object A and B both see)
```

---

## 4. Windows TLS and calling conventions

### 4.1 win-x86_64 (Microsoft x64)

| Item | Microsoft x64 |
|------|----------------|
| Integer args | **`rcx, rdx, r8, r9`** then stack |
| FP args | **`xmm0–xmm3`** for first four float/double slots (positional with integer) |
| Return | `rax`, `xmm0` |
| Callee-saved | `rbx, rbp, rdi, rsi, r12–r15`, `xmm6–xmm15` |
| Caller-saved | `rax, rcx, rdx, r8–r11`, `xmm0–xmm5` |
| **Shadow space** | **32 bytes** home area above return address on **every** call |
| Stack align | 16-byte before `call` |
| Red zone | **None** |
| TEB | **`GS` segment base → TEB** (not available for ART Thread*) |
| Dynamic TLS | `TlsAlloc` / `TlsGetValue` / `TlsSetValue` (slots in TEB TLS array / expansion) |
| Fiber TLS | `FlsAlloc` if fibers matter (ART: not required for v1) |

**Critical conflict with AOSP amd64 managed TLS:**  
Linux ART sets **GS = Thread\***. Windows **requires GS = TEB**. User code cannot adopt Linux’s `ARCH_SET_GS` strategy portably (CET, CFG, shared libraries, and the OS all assume TEB in GS).  

**Therefore win-x86_64 managed self must NOT use `%gs:offset` as Thread\*.**

C++ `Thread::Current()` can use:

- C++ `thread_local` (works with Clang/MSVC runtime), and/or  
- `TlsAlloc` once + `TlsSetValue` on attach (explicit, fiber-aware optional later).

### 4.2 win-x86 (Microsoft i386 cdecl/stdcall mix)

| Item | 32-bit Windows |
|------|----------------|
| Default C | `cdecl` (caller cleans) for CRT; many Win32 APIs `stdcall` |
| TEB | **`FS:[0]`** → TEB |
| Dynamic TLS | `TlsAlloc` family |
| ART Linux parallel | FS-as-Thread conflicts with FS-as-TEB |

Managed self cannot be FS base. Prefer **callee-saved register** (e.g. `ebp`-relative is wrong; use something like `ebx`/`esi` carefully) or **explicit push of Thread*** into every helper — register model still preferred for nterp density.

### 4.3 win-arm64 (native Windows on ARM64)

| Item | Microsoft ARM64 |
|------|-----------------|
| Integer args | `x0–x7` (AAPCS-like) |
| Callee-saved | broadly AAPCS-like (`x19–x28`, …) |
| **Platform register** | **`x18` reserved — TEB / OS** |
| TLS | TEB via x18 + `TlsAlloc` slots |

Linux ART’s **xSELF=x19** is compatible **in spirit** with Windows ARM64: x19 is still callee-saved; **do not** pick x18 for Thread*. Prefer keeping **xSELF = x19** on win-arm64 for maximum assembler sharing with Linux arm64 (with Windows-specific prologues only at JNI/C++ edges).

### 4.4 win-arm64ec (Arm64EC)

Arm64EC is a **hybrid ABI** for Windows on ARM:

- **Arm64EC code** uses an ARM64 register file with a **calling convention designed to interoperate with x64** (parameter slots map to the Microsoft x64 mental model: first four integer-like args correspond to the x64 `rcx,rdx,r8,r9` roles via defined Arm64EC register mapping).
- Processes may load **x64 DLLs** and **Arm64EC DLLs** together; the OS/linker provide **thunking**.
- **TEB** remains the Windows TEB (accessed in a platform-defined way; x18 still special).

Implications for ART:

| Concern | Design stance (DRAFT) |
|---------|------------------------|
| JIT ISA | Emit **Arm64EC** (or pure ARM64 if process is pure ARM64 — separate SKU) |
| Managed self | Still a **callee-saved pointer** (likely x19), never TEB register |
| Quick entrypoints | Compiled as Arm64EC functions; C++ edges use Arm64EC/x64 thunk rules when calling MSVC/Clang CRT and OS |
| Mixed x64 `art.dll` | **Not** a goal: ship one ISA flavor of ART per package; avoid in-process dual JIT ISAs |
| x64 guest JIT inside Arm64EC process | Out of scope; if ever needed, separate code cache + exit thunks (research later) |

Arm64EC is drafted so WinNT ART’s **abstractions** (self register, entrypoint table, bridge stubs) do not hard-code “GS exists” or “only SysV”.

---

## 5. Target architecture matrix for ART-WinNT (DRAFT)

```text
                    Managed self base          C++ Current()        C++ ABI at bridges
                    ─────────────────          ─────────────        ───────────────────
Linux amd64         GS → Thread*               thread_local         SysV
Linux arm64         x19 = Thread*              thread_local/Bionic  AAPCS64
win-x86_64          rSELF (reg) → Thread*      thread_local/Tls*    Microsoft x64
win-x86             rSELF32 → Thread*          Tls*/thread_local    cdecl (+stdcall APIs)
win-arm64           x19 = Thread*              thread_local/Tls*    MS ARM64
win-arm64ec         x19 = Thread* (EC)         thread_local/Tls*    Arm64EC (+ x64 thunks)
```

**Unifying principle:** On **all Windows targets**, managed code uses an explicit **Thread\* self register** (arm64-style), not a segment register. Linux amd64 keeps GS for AOSP compatibility; Windows never inherits that choice.

---

## 6. Proposed WinNT design (all arches drafted)

### 6.1 Layer cake

```text
┌─────────────────────────────────────────────────────────────────┐
│ JIT / nterp / oat quick code                                    │
│  - ISA-specific machine code                                    │
│  - Assumes rSELF/xSELF holds Thread*                            │
│  - Calls QuickEntryPoints via [self + OFFSETOF pName]           │
└────────────────────────────▲────────────────────────────────────┘
                             │ managed ABI (per ISA)
┌────────────────────────────┴────────────────────────────────────┐
│ Quick entrypoint stubs (.S / thin C++)                          │
│  - Prolog: ensure self reg; spill per managed callee-save set   │
│  - Marshal args to C++ ABI (SysV vs MS x64 vs AAPCS vs Arm64EC) │
│  - Call Runtime helpers; handle exception delivery              │
└────────────────────────────▲────────────────────────────────────┘
                             │ C++ ABI
┌────────────────────────────┴────────────────────────────────────┐
│ Runtime C++ (Thread, Runtime, JNI, GC, …)                       │
│  - Thread::Current() via C++ TLS / TlsGetValue                  │
│  - InitCpu() publishes managed self (reg contract / verify)     │
└────────────────────────────▲────────────────────────────────────┘
                             │ Win32 API
┌────────────────────────────┴────────────────────────────────────┐
│ OS: TEB, TlsAlloc, VirtualProtect, VEH, CreateThread, …         │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 C++ `Thread::Current()` on Windows (all arches)

**Recommendation:** keep **`thread_local Thread* self_tls_`** as primary (already used for non-Bionic), set in `Thread::Init` / reattach / clear on detach.

Optional hardening:

- Mirror into a process-global `TlsAlloc` index for tools that do not see C++ TLS (debuggers, some FFI).
- Do **not** require `pthread_key` on pure Win32 builds long-term (pthread is a portability shim today).

**Fibers:** default **unsupported** for v1 (document: ART threads ≡ OS threads). If fibers appear later, switch publishing path to FLS or reject attach on fiber mismatch.

### 6.3 Managed self on win-x86_64 (PRIMARY)

#### Choice: dedicated callee-saved **rSELF**

| Candidate | Pros | Cons |
|-----------|------|------|
| **`r15` as rSELF** | Callee-saved in MS x64 **and** SysV; free of TEB | AOSP quick code uses r15 in some spill sets; need bitmap/frame audit |
| `r14` / `r13` | Same class | Same audit |
| Keep `%gs` via custom GS base | Matches Linux asm literally | **Rejected:** fights TEB/GS, non-portable, CET risk |
| Load from TEB TLS every time | Simple | Too slow / clunky for every entrypoint |

**Draft default: `r15` = Thread\*** on win-x86_64 managed code.

Consequences:

1. **All** `movq %gs:OFF, …` become `movq OFF(%r15), …` under `#if defined(_WIN32)`.
2. **All** managed prologues / transitions from C++ must **materialize r15** (from `Thread*` argument or `Thread::Current()`).
3. Callee-save frame bitmaps for Windows must treat r15 as **reserved self**, not general spill (or always restore self after spills that included it — prefer reserved).
4. Linux builds remain GS-based; use assembler macros:

```text
// conceptual
#if defined(_WIN32)
  #define THREAD_LOAD(dst, off)  movq off(rSELF), dst
  #define THREAD_STORE(src, off) movq src, off(rSELF)
#else
  #define THREAD_LOAD(dst, off)  movq %gs:off, dst
  #define THREAD_STORE(src, off) movq src, %gs:off
#endif
```

#### Entry bridges (C++ → managed)

`art_quick_invoke_stub` (Win64) must:

1. Use **Microsoft x64** C++ entry (shadow space, `rcx=method, rdx=args, r8=size, r9=self`, rest spilled).
2. Move `self` into **r15**.
3. Build managed frame; jump to quick code / interpreter bridge with **managed** arg regs (define managed arg map — §6.5).

#### Exit bridges (managed → C++)

Quick entrypoints called from JIT:

1. Assume r15 = self.
2. Spill managed caller-saves as today.
3. Place C++ args in **rcx, rdx, r8, r9** + shadow space (not rdi/rsi SysV).
4. `call` helper; on return, restore and check `THREAD_EXCEPTION_OFFSET(r15)`.

This is the bulk of “port quick_entrypoints_x86_64.S to Windows”.

### 6.4 Managed self on other Windows arches (DRAFT)

| Target | Managed self | Notes |
|--------|--------------|-------|
| win-x86 | `rSELF32` e.g. `%esi` or `%ebx` (callee-saved; audit vs frame pointers) | No FS base |
| win-arm64 | **x19** (= Linux xSELF) | Do not use x18 |
| win-arm64ec | **x19** | Emit EC; C++ edges follow Arm64EC; no x64 JIT in-process |

### 6.5 Managed calling convention vs OS C++ ABI

AOSP managed code on amd64 is **not** “pure SysV C” either: it is an ART convention (ArtMethod* in a fixed reg, shorty-driven args, callee-save method frames). When porting:

| Edge | Rule |
|------|------|
| JIT ↔ JIT | ART managed convention (per ISA), OS-independent except stack alignment / W^X |
| JIT ↔ quick entrypoint asm | ART managed convention |
| quick entrypoint asm ↔ C++ | **OS C++ ABI** (MS x64 / MS ARM64 / Arm64EC) |
| JNI | JNIEnv* + Java args per JNI; underlying C++ is OS ABI |

For **win-x86_64**, explicitly document a **Managed X64** convention (draft):

| Role | Register (draft) |
|------|------------------|
| Thread\* (self) | **r15** |
| ArtMethod\* (current / invoke) | **rdi** kept as managed method reg *or* remapped to **rax/rcx** — **open decision** (§9) |
| Managed integer args | Prefer **mirroring Linux ART** where possible to maximize assembler sharing **inside** managed code; only **bridges** convert to MS x64 |
| Stack alignment | 16-byte at call boundaries; **no red zone** (Windows-safe, also fine on Linux) |

**Design preference:** maximize **shared managed-body** with Linux; isolate OS ABI differences in **macros + trampoline prologues/epilogues**. If that proves too fragile for arg regs (SysV rdi vs MS rcx), accept Windows-specific managed arg regs and dual JIT backends — costlier.

### 6.6 `QuickEntryPoints` lifetime and TLS layout

Unchanged conceptually:

- Stored in `Thread::tlsPtr_.quick_entrypoints`.
- Initialized by existing `InitTlsEntryPoints()` once self exists.
- Instrumentation may patch pointers under locks.

Windows only changes **how offsets are addressed** (reg base vs GS), not the C++ layout of `Thread`.

### 6.7 Runtime instance load

Linux: GOT load of `art::Runtime::instance_`.  
Windows PE (already): `LOAD_RUNTIME_INSTANCE` calls `art_Runtime_instance_ptr` with shadow space.  

JIT should either:

- emit the same helper call, or  
- load from a **hidden global** via RIP-relative LEA of an `__declspec(dllimport)`-safe indirection exported from `art.dll`.

Prefer **one** PE-safe sequence used by both hand asm and JIT emitter.

### 6.8 JIT design (phase 5, all arches drafted)

#### Code cache

| Topic | WinNT design |
|-------|----------------|
| Allocation | `VirtualAlloc` RW → later RX (or RWX only if policy allows; prefer W^X) |
| Publish | `VirtualProtect` RW→RX; flush I-cache (`FlushInstructionCache`) on non-x86 |
| Free / collect | existing ART JIT GC hooks + `VirtualFree` |
| CFG / CET | Prefer **not** dynamic CFG calls into JIT until researched; use regular `call rel32` within cache; document CET shadow-stack interactions as open |
| Antivirus | Expect false positives; keep cache private, avoid RWX long windows |

#### Compiler backend

| Target | Backend |
|--------|---------|
| win-x86_64 | Optimizing/Quick backend with **Windows self addressing** + bridge ABI |
| win-x86 | DRAFT; likely defer forever unless product asks |
| win-arm64 | Reuse arm64 backend + MS edge stubs |
| win-arm64ec | arm64 backend + **Arm64EC relocation / thunk** constraints |

#### Entry points into JIT code

Same as Linux conceptually:

```text
ArtMethod::entry_point_from_quick_compiled_code_ → JIT / oat / bridge
```

Windows must stop forcing interpreter in `ArtMethod::Invoke` once:

1. rSELF published,  
2. `art_quick_invoke_*` Win stubs exist,  
3. bridge to interpreter remains available for uncompiled methods.

#### Nterp / mterp

If nterp asm uses `%gs`, it needs the same THREAD_LOAD macros. Until then, stay on Switch interpreter (`-Xint`) even if JIT is partially enabled for select methods (possible but not recommended).

### 6.9 Thread attach / detach publish protocol

```text
Thread::Init (on the native thread):
  1. stack bounds (existing Win VirtualQuery path)
  2. self_tls_ = this            # C++ Current()
  3. InitTlsEntryPoints()
  4. InitCpu()                   # verify policy; no GS write on Windows
  5. (optional) TlsSetValue(kArtTls, this)

Transition C++ → managed (invoke stub / JNI return to managed):
  rSELF/xSELF := Thread::Current()  # or use explicit Thread* arg

Detach:
  clear self_tls_ / TLS slot
  rSELF must not be used after
```

**CreateThread / pthread shim:** any OS thread that runs managed code must go through ART attach (existing model).

### 6.10 Exception delivery interaction

VEH already used for Win64 crash paths. Managed exception delivery still uses ART’s `Thread::exception_` and delivery entrypoints. Bridges must:

- not clobber rSELF across VEH-unrelated calls,  
- use OS CONTEXT only for **native** faults; managed throws stay soft.

JIT deopt flags (`THREAD_DEOPT_CHECK_REQUIRED_OFFSET`) stay Thread fields accessed via self base.

---

## 7. Per-architecture draft sketches

### 7.1 win-x86_64 (implement first)

```text
C++ ABI:     rcx, rdx, r8, r9 + 32B shadow
Managed self: r15
Thread base:  [r15 + THREAD_*_OFFSET]
Entrypoint:   call [r15 + QUICK_ENTRYPOINT_OFFSET(pX)]  or load ptr then call
Invoke stub:  MS x64 entry → set r15 → managed
Reject:       ARCH_SET_GS, %gs:THREAD_*, SysV-only invoke stubs
```

**Implementation slices (when coding starts):**

1. Assembler macros for THREAD_LOAD/STORE + DEFINE_FUNCTION (PE symbols, no `@PLT`).  
2. `art_quick_invoke_{,static_}stub` Win64.  
3. Port `SETUP_*_FRAME` macros off `int3`.  
4. Port high-traffic quick entrypoints (alloc, invoke trampolines, exception deliver, JNI).  
5. Remove Win force-interpreter gate behind a runtime flag.  
6. JIT emitter: self via r15; cache W^X.  
7. Wine64 + real Win10 gates beyond `-Xint`.

### 7.2 win-x86 (draft only)

```text
C++ ABI:     cdecl (runtime) / stdcall (Win32 APIs)
Managed self: callee-saved reg (TBD; not FS)
TEB:         FS → TEB remains OS
Product:     non-goal unless explicitly revived
```

### 7.3 win-arm64 (draft)

```text
C++ ABI:     Microsoft ARM64
Managed self: x19 (share Linux asm bodies)
Forbidden:    x18 as Thread*
JIT:          arm64 emitter + FlushInstructionCache + VirtualProtect
```

### 7.4 win-arm64ec (draft)

```text
Emit:        Arm64EC code for ART + JIT
Managed self: x19
Interop:     OS thunks to x64 DLLs outside ART
Package:     separate artifact from win-x86_64; do not mix JIT ISAs in one art.dll
```

---

## 8. Comparison tables

### 8.1 Thread::Current vs managed self

| Platform | C++ Current | Managed Thread base |
|----------|-------------|---------------------|
| Linux x86_64 | `thread_local` | **GS base = Thread\*** |
| Linux arm64 | TLS / Bionic slot | **x19** |
| Linux x86 | `thread_local` | **FS base = Thread\*** |
| Win x86_64 | `thread_local` (+ optional TlsAlloc) | **r15 (draft)** |
| Win x86 | Tls / thread_local | **rSELF32 (draft)** |
| Win arm64 | thread_local / Tls | **x19** |
| Win Arm64EC | thread_local / Tls | **x19** |

### 8.2 First four integer arguments (C++ edges only)

| ABI | arg0 | arg1 | arg2 | arg3 |
|-----|------|------|------|------|
| SysV AMD64 | rdi | rsi | rdx | rcx |
| MS x64 | rcx | rdx | r8 | r9 |
| AAPCS64 / MS ARM64 | x0 | x1 | x2 | x3 |
| Arm64EC | mapped ARM64 regs corresponding to MS x64 slots | | | |

Quick entrypoint **asm prologues** are where these differences are centralized.

---

## 9. Open decisions (must resolve before coding JIT)

1. **Managed method/arg registers on win-x86_64:** keep Linux-like `rdi/rsi/...` inside managed and only convert at C++ boundary, **or** redefine managed to MS-like `rcx/rdx/...`?  
   - *Lean toward:* Linux-like managed + convert at boundary (less dual backend).  
2. **Exact rSELF register (r15 vs other):** needs full spill-bitmap / JNI macro assembler audit.  
3. **Nterp priority vs optimizing JIT first.**  
4. **CET / shadow stack / CFG policy** for JIT call sites.  
5. **Whether wine64 is sufficient** to validate GS-free entrypoints (likely yes for ABI; host still required for TEB edge cases).  
6. **Arm64EC product:** separate SKU or never?  
7. **Single art.dll multi-ISA:** rejected for now.

---

## 10. Non-goals (this design phase)

- Implementing stubs or JIT in this change.  
- Claiming phase 5 complete.  
- Supporting fibers, APC-heavy hosts, or non-ART thread attachment.  
- Emulating Linux GS on Windows.  
- In-process concurrent x64 + Arm64EC JIT.

---

## 11. Mapping to product phases

| Phase | TLS / entry / JIT relevance |
|-------|-----------------------------|
| Phase 2–3 (`-Xint`) | C++ TLS only; managed self unused for invoke |
| Phase 3+ hardening | Still interpreter; optional early rSELF plumbing tests |
| **Entrypoint port (pre-JIT)** | Win invoke stubs + quick entrypoints + rSELF macros |
| **Phase 5 JIT** | Code cache + emitter using same self/ABI contracts |
| oat/dex2oat | Optional; imageless JIT can precede oat PE |

---

## 12. Recommended implementation order (when approved)

1. Document lock-in: **no GS Thread\* on Windows**; **rSELF register model**.  
2. Introduce THREAD_LOAD/STORE macros; keep Linux GS path intact.  
3. Implement Win64 `art_quick_invoke_*` + remove unconditional interpreter force under a flag.  
4. Port entrypoints in dependency order (exception, alloc, invoke trampolines, JNI).  
5. Wine gates: compiled Hello without `-Xint` (still imageless).  
6. JIT cache + smoke; then stress (phase 4-style) under wine/host.  
7. Revisit arm64 / Arm64EC only after x86_64 contracts stabilize.

---

## 13. Appendix — evidence anchors in tree

| Claim | Anchor |
|-------|--------|
| GS = Thread\* on Linux x64 | `vendor/art/runtime/arch/x86_64/thread_x86_64.cc` (`ARCH_SET_GS`) |
| `%gs:THREAD_*` in quick code | `vendor/art/runtime/arch/x86_64/quick_entrypoints_x86_64.S` |
| xSELF = x19 | `vendor/art/runtime/arch/arm64/asm_support_arm64.S` |
| C++ Current = thread_local non-Bionic | `vendor/art/runtime/thread-current-inl.h` |
| QuickEntryPoints in Thread | `quick_entrypoints.h`, `Thread::QuickEntryPointOffset` |
| Win forces interpreter invoke | `vendor/art/runtime/art_method.cc` (`#if defined(_WIN32)`) |
| Win SETUP frames still trap | `asm_support_x86_64.S` (`#if defined(__APPLE__) \|\| defined(_WIN32) int3`) |
| PE Runtime load helper | `LOAD_RUNTIME_INSTANCE` in `asm_support_x86_64.S` |

---

## 14. One-paragraph executive summary

On Linux amd64, ART’s managed world is **GS-relative Thread TLS** layered on top of normal C++ `thread_local`, with quick entrypoints and JIT assuming SysV bridges; on Linux arm64, managed world is **x19 = Thread\***. Windows **cannot** reuse GS/FS for Thread\* because those segments point at the **TEB**. The WinNT design therefore adopts the **arm64-style explicit self register** on all Windows ISAs (draft: **r15** on x86_64, **x19** on ARM64/Arm64EC), keeps C++ `Thread::Current()` on `thread_local`/`TlsAlloc`, and isolates **Microsoft / Arm64EC C++ calling conventions** at quick-entrypoint and invoke bridges. JIT is “just” machine code that obeys the same self + entrypoint contracts with a W^X `VirtualAlloc` cache. **x86_64 is the first implementation target**; x86, arm64, and Arm64EC are specified so the abstractions do not paint us into a GS-shaped corner.
