# ART on Windows NT — TLS, Managed ABI, Quick Entrypoints, and JIT

**Status:** DRAFT + **implementation started** (Win64 x86_64 spine); **mterp design §15**  
**Date:** 2026-07-18  
**Scope:** Design **all** ART-WinNT ISA targets in theory; implement later with **x86_64 first**.  
**Related:** [win64_art_port.md](win64_art_port.md) (product phases), [win32_open_items.md](win32_open_items.md) (open workarounds W-001+), Phase 3+ runtime hardening, Phase 5 JIT/oat.

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
| **`FS.base = Thread*`** (`%fs:off`) | Would free r15 for nterp rREFS without moving rREFS→rbp | **Rejected (2026-07-18):** see **§16** — not a portable product self base |
| Load from TEB TLS every time | Simple | Too slow / clunky for every entrypoint |

**LOCKED (2026-07-18): `r15` = Thread\*** (`rSELF`) on win-x86_64 managed / quick / JIT / nterp.

Companion nterp lock: **`rREFS = %rbp`** when nterp is ported (**N-1**, §15 / §17). Do **not** put Thread\* in `rbp`.

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

For **win-x86_64**, **Managed X64** convention (**LOCKED** self / nterp bases / Linux-like args):

| Role | Register | Status |
|------|----------|--------|
| Thread\* (self) | **r15** (`rSELF`) | **LOCKED** |
| nterp ref-shadow base | **rbp** (`rREFS`) | **LOCKED** for nterp port (N-1) |
| nterp dex vregs / PC / ibase / inst | r13 / r12 / r14 / rbx | **LOCKED** (same as Linux nterp) |
| ArtMethod\* (current / invoke) | **rdi** | **LOCKED** Linux-like |
| Managed integer args | **rsi, rdx, rcx, r8, r9** | **LOCKED** Linux-like; MS only at C++ edges |
| Stack alignment | 16-byte at calls; **no red zone** | **LOCKED** |

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
Managed self: r15 (LOCKED); nterp rREFS: rbp (LOCKED)
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
| Win x86_64 | `thread_local` (+ optional TlsAlloc) | **r15 LOCKED**; nterp **rREFS=rbp** |
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
2. **Exact rSELF register:** **CLOSED — r15** (nterp **rREFS=rbp**). Spill-bitmap/JNI audit is implementation work, not an open design choice.  
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
- Win64 `FS.base = Thread*` as managed self (rejected §16).  
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


## 12b. Implementation progress (2026-07-18)

Locked for coding:

1. **Managed arg regs:** Linux-like SysV shape inside managed/quick asm; convert only at edges.  
2. **rSELF:** **r15** on win-x86_64 (quick / JIT / nterp).  
3. **nterp map (when ported):** **N-1** — `rSELF=r15`, **`rREFS=rbp`**; **not** N-2 (`rSELF=rbp`). See §15 / §17.  
4. **C++ quick helpers:** `ART_QUICK_ENTRYPOINT_ABI` = `sysv_abi` on Win64 so asm can keep SysV `call` sites.  
5. **Invoke stubs:** Microsoft x64 entry at `art_quick_invoke_*`, then map to SysV body + publish r15.  
6. **Force-interpreter (W-001):** still default ON; opt-in `ART_WIN64_QUICK_INVOKE=1`.

Landed in tree:

| Item | Location |
|------|----------|
| `THREAD_*` macros (GS vs r15) | `asm_support_x86_64.S` |
| `%gs:` sites → macros | x86_64 `*.S` |
| SETUP frames enabled on Win (no `int3`) | `asm_support_x86_64.S` |
| Win64 invoke prologues + rSELF publish | `quick_entrypoints_x86_64.S` |
| `ART_QUICK_ENTRYPOINT_ABI` | `libartbase/base/macros.h` + entrypoint defs |
| Invoke force gated by env | `art_method.cc` |
| `InitCpu` Win comments | `thread_x86_64.cc` |
| Nterp disabled on `_WIN32` | `interpreter/mterp/nterp.cc` |

Wine smoke (2026-07-18, `build/win64_phase1`):

| Gate | Result |
|------|--------|
| `dalvikvm.exe -showversion` | PASS (`ART version 2.1.0 x86_64`) |
| Hello default (force-interp) | PASS (`Hello from dalvikvm!`, `java.version=1.8.0`) |
| Hello `ART_WIN64_QUICK_INVOKE=1` + `-Xint` | **PASS** — no `ArtMethod::Invoke via interpreter` spam; invoke→quick stub→interpreter bridge works |

### Next-phase progress (2026-07-18, design §12 steps 4–5)

**Nterp disabled on Win32** (`IsNterpSupported() → false`): generated `mterp_x86_64` still uses `%gs` Thread TLS and occupies `r15` as `rREFS`, conflicting with managed rSELF. Switch interpreter is used instead until mterp is ported.

Wine matrix with `ART_WIN64_QUICK_INVOKE=1` (fresh PE, imageless):

| Gate | `-Xint` | no `-Xint` |
|------|---------|------------|
| Hello | PASS | **PASS** (was AV before nterp off) |
| MathProbe | PASS | **PASS** |
| IoProbe | PASS | **PASS** |
| NetProbe | PASS | **PASS** |
| CoreProbe | FAIL (NPE `toCopy==null`, both modes) | FAIL (same pre-existing) |

Design step 5 (**compiled Hello without forced `-Xint`**, still imageless) is **met** under opt-in quick invoke + switch interpreter.

Still open (toward product default + Phase 5 JIT):

- Flip product default: `ART_WIN64_QUICK_INVOKE` on by default / drop W-001 force (after broader green + host).  
- Port **mterp** per **§15 N-1 LOCKED** (rSELF=r15, rREFS=rbp) or keep N-0 switch-interp.  
- JNI quick stubs (`art_jni_dlsym_lookup_*`) under rSELF when leaving InterpreterJni (W-012).  
- CoreProbe NPE (libcore/reflect path; not specific to quick invoke).  
- W-024 Critical/FastNative restore.  
- Phase 5: JIT code cache + emitter on same self/ABI contracts.  
- Host (real Win10) re-run.

## 15. Nterp / mterp on WinNT x86_64 — analysis and design

**Status:** DESIGN (research complete; implementation not started)  
**Current product:** `IsNterpSupported()` returns **false** on `_WIN32` (§12b); switch interpreter only.  
**Goal:** specify a correct, implementable port that fits the locked rSELF model without reintroducing GS Thread\*.

### 15.1 What nterp is (in this tree)

ART’s fast interpreter is **nterp** (templates under `vendor/art/runtime/interpreter/mterp/`, generators `gen_mterp.py`). For x86_64 the arch pack is **`x86_64ng/`**; codegen emits `mterp_x86_64.S` (in-tree gensrc: `build/*/gensrc/art/asm/mterp/mterp_x86_64.S`).

Control model (README):

- Handler table: entry ≈ `handler_base + opcode * NTERP_HANDLER_SIZE` (computed goto).  
- **`rIBASE`** holds the active handler table base; refreshed on backward branches / throws / returns.  
- Frame layout matches optimizing ABI (see `nterp_helpers.cc`): callee saves, dex regs, **reference regs**, caller fp, dex_pc_ptr, outs, `ArtMethod*`.  
- No ManagedStack transitions between nterp and compiled frames.  
- Entry points: `ExecuteNterpImpl` / `ExecuteNterpWithClinitImpl` (OAT-prefixed headers for stack walk).

Gate today (`nterp.cc`):

```text
IsNterpSupported():
  ART_USE_RESTRICTED_MODE → false
  _WIN32                  → false   // multipath (2026-07-18)
  else x86_64             → !kUseTableLookupReadBarrier

CanRuntimeUseNterp():
  IsNterpSupported()
  && !InterpretOnly()     // -Xint forces switch
  && !debuggable / stubs / async exception / jit-at-first-use …
```

That is why **`-Xint` Hello worked** with quick invoke, while **no-`-Xint` crashed** until nterp was disabled: without `-Xint`, methods get nterp entry points that still assume Linux GS Thread TLS.

### 15.2 Linux x86_64 register map (oracle)

From `x86_64ng/main.S` header (and generated `mterp_x86_64.S`):

| Symbolic | Register / mechanism | Role |
|----------|----------------------|------|
| **rSELF** | **`%gs` (segment)** | Thread\* base: `rSELF:THREAD_*_OFFSET` → `%gs:offset` |
| **rPC** | `%r12` | Dex PC pointer |
| **rFP** | `%r13` | Dex register array base |
| **rIBASE** | `%r14` | Handler table base |
| **rREFS** | **`%r15`** | Reference-only reg array base (GC roots) |
| **rINST** | `%rbx` / `%ebx` | Current instruction / temps |
| **rNEW_FP / rNEW_REFS** | `%r8` / `%r9` | Frame setup temps (nterp→nterp) |
| shorty / misc | **`%rbp`** | Entry shorty pointer; also arg-count temps in invoke paths |

Callee-save spill (`SPILL_ALL_CALLEE_SAVES`): `r15,r14,r13,r12,rbp,rbx` + FP callee saves — aligned with “save all callee saves” thinking.

**Thread field traffic in generated mterp** (counts from current gensrc, approximate):

| Access | ~count | Notes |
|--------|-------:|-------|
| `THREAD_SELF_OFFSET` | 57 | Often materialize `Thread*` into `%rdi`/`%rax` for C++ helpers |
| `THREAD_READ_BARRIER_MARK_REG00_OFFSET` | 15 | Marking check |
| `THREAD_CARD_TABLE_OFFSET` | 4 | Write barrier |
| exception / flags / tid / hotness / alloc entrypoints | few | trampolines + suspend |

Plus **one bare** `cmpq …, %gs:THREAD_EXCEPTION_OFFSET` in `NTERP_TRAMPOLINE` (not via `rSELF` symbol).

**Entry ABI (managed / ART, SysV-shaped):**

```text
ExecuteNterpImpl:
  rdi = ArtMethod*
  remaining args = method parameters (GPRs/XMMs / stack)
  // Thread* is NOT an argument — Linux relies on GS already = Thread* (InitCpu)
```

`ExecuteNterpWithClinitImpl` reads **`rSELF:THREAD_TID_OFFSET` before spilling** — assumes GS is live on entry.

**CFA / unwind:** after frame setup, CFA is often **based on rREFS** (`CFI_DEF_CFA_BREG_PLUS_UCONST CFI_REFS, -8, …`). `EXPORT_PC` stores dex PC at **`-16(rREFS)`**. Changing rREFS is a CFI + exception-landing change, not a local rewrite.

### 15.3 Conflicts with locked WinNT design

| Locked multipath choice (§6 / §12b) | Nterp Linux reality | Conflict |
|-------------------------------------|---------------------|----------|
| Never set GS = Thread\* (TEB owns GS) | rSELF = `%gs` | **Hard fail** if nterp enabled |
| Managed self = **r15** | rREFS = **r15** | **Same physical register, two roles** |
| Quick helpers SysV via `ART_QUICK_ENTRYPOINT_ABI` | Nterp calls C++ helpers with SysV ARG macros | Compatible **if** helpers stay sysv_abi |
| Invoke stubs publish r15 at C++→managed edge | Nterp entry does not take Thread\*; expects GS | **Must materialize Thread\* on entry** |

Empirical: wine AV without `-Xint` (pre-disable); fault pattern consistent with bad Thread-relative access. Disabling nterp restored Hello/Math/Io/Net without `-Xint`.

**Register pressure (why this is hard):** SysV callee-saved cores are only `rbx,rbp,r12–r15`. Nterp already assigns **all six**:

```text
rbx=rINST  rbp=temps/shorty  r12=rPC  r13=rFP  r14=rIBASE  r15=rREFS
```

Making rSELF a **GPR** requires either:

1. **Repurposing** one of those roles (almost certainly **rbp** or a redesign of rREFS), or  
2. **Not** holding Thread\* in a dedicated reg (reload from C++ TLS / TEB slot — fights nterp’s density).

Arm64 nterp is the cleaner oracle: **xSELF=x19** is a normal callee-saved pointer (same idea as quick), not a segment.

### 15.4 Design options (Win x86_64)

#### Option N-0 — Switch interpreter only (current product)

- Keep `IsNterpSupported()==false` on `_WIN32`.  
- Non-`-Xint` uses switch interpreter + existing quick invoke / entrypoints.  
- **Pros:** already green for Hello/Math/Io/Net; no huge asm churn.  
- **Cons:** slower than nterp; delays “interpreter quality” vs Linux; still need JIT for speed.  
- **Verdict:** acceptable **v1 product** if Phase 5 JIT is the speed path; document as temporary or permanent.

#### Option N-1 — rSELF=r15, move rREFS → rbp  **(LOCKED for Win nterp port)**

**Selected 2026-07-18** (also the greenfield winner — §17). Align nterp with quick/managed self:

```text
Win-x86_64 nterp:
  rSELF  = %r15          // Thread*  (same as quick managed self)
  rREFS  = %rbp          // reference array base
  rPC/rFP/rIBASE/rINST unchanged (r12/r13/r14/rbx)
```

Work items:

1. **Template header** (`x86_64ng/main.S`): `#if defined(_WIN32)` redefine rSELF/rREFS/CFI_REFS.  
2. **Syntax:** keep `rSELF:OFF` only if rSELF is a segment; for GPR base switch to **`OFF(rSELF)`** (or introduce `THREAD_LOAD` style macros shared with `asm_support_x86_64.S`). Prefer **one** addressing style used by both quick and nterp.  
3. **Audit every `%rbp`/`%ebp` temp** (shorty save, invoke arg counts, stack indices) → use `r10`/`r11`/`eax` instead so rREFS=rbp is never clobbered mid-handler.  
4. **CFI:** rewrite CFA expressions that use CFI_REFS (was 15 → rbp’s DWARF number 6).  
5. **`EXPORT_PC`:** `-16(rREFS)` becomes `-16(%rbp)` automatically if rREFS redefined — verify exception landing (`artNterpAsmInstructionEnd`).  
6. **`NTERP_TRAMPOLINE`:** replace bare `%gs:THREAD_EXCEPTION_OFFSET` with Thread field via rSELF.  
7. **Entry materialization** (mandatory on Win — no GS):

```text
ExecuteNterpImpl (Win):
  SPILL_ALL_CALLEE_SAVES     // includes old r15/rbp
  call art_nterp_current_thread  // ART_QUICK_ENTRYPOINT_ABI Thread* ()
  movq %rax, rSELF           // r15
  // then SETUP_STACK_FRAME (defines rREFS=rbp, rFP, …)
```

   `ExecuteNterpWithClinitImpl` must **not** read TID via rSELF **before** that materialization (today it does). Order becomes: spill → load Thread → tid check → body, **or** call a tiny C++ helper that does the clinit gate.

8. **nterp→nterp:** same OS thread → rSELF already valid; do not clobber r15.  
9. **nterp→compiled / compiled→nterp:** compiled code must honor r15 as self when quick is enabled; invoke stubs already set r15 from C++.  
10. **Regenerate** `mterp_x86_64.S` via existing bp2cmake/codegen path; PE + Linux smoke.

**Pros:** one self story across quick + nterp + future JIT.  
**Cons:** largest careful asm audit (rbp is busy); CFI risk.

#### Option N-2 — rSELF=rbp, keep rREFS=r15  **(REJECTED)**

```text
rSELF = %rbp   // Thread*
rREFS = %r15   // unchanged
```

- Slightly less churn on ref-array addressing and some CFI; closer to Linux `rREFS=r15`.  
- Puts **Thread\*** in the traditional FP register for **all** managed code, or forces a dual-self split with quick.  
- Still needs the full rbp-temp audit (cannot clobber self).  
- Quick stubs that use `rbp` as a temporary CFA/SP anchor (invoke / OSR) fight immortal self-in-rbp.  
- **Verdict: REJECTED** even from a greenfield analysis (§17). Not an alternative while self stays r15.

#### Option N-3 — Thread\* via TEB TLS every access

- Map ART Thread\* into a PE TLS slot; expand `rSELF:OFF` to load base from TEB then field.  
- **Pros:** no extra dedicated GPR.  
- **Cons:** code size / latency destroy nterp’s reason to exist; ugly macros; still need TEB layout constants.  
- **Verdict:** research-only / reject for product nterp.

#### Option N-4 — Dual generated files

- `mterp_x86_64.S` (Linux GS) vs `mterp_x86_64_win.S` (GPR self).  
- Build system selects by target.  
- **Pros:** no `#ifdef` spaghetti inside every line.  
- **Cons:** two artifacts to regen; still implement N-1 body once.  
- **Verdict:** good **packaging** on top of N-1, not a separate ISA design.

### 15.5 Recommended strategy (phased)

```text
Now (product):     N-0  switch only on Win
LOCKED nterp port: N-1  rSELF=r15, rREFS=rbp  (+ optional N-4 dual gensrc)
REJECTED:          N-2 (rSELF=rbp) / N-3 (TLS every access)
JIT (Phase 5):     independent of nterp, but same r15 self contract
```

**Ordering relative to §12:**

| Step | Work | Depends on |
|------|------|------------|
| 0 | Keep N-0; document | done |
| 1 | Spec lock: N-1 register map + entry helper `art_nterp_current_thread` | this section |
| 2 | Template + trampoline + CFI edits; regen mterp | 1 |
| 3 | Wine: enable `IsNterpSupported` on Win under flag e.g. `ART_WIN64_NTERP=1` | 2 |
| 4 | Hello/Math/Io/Net **no `-Xint`** with nterp on; compare to switch | 3 |
| 5 | Default nterp on Win if green; else leave N-0 | 4 |
| 6 | Only then treat nterp as prerequisite for “fast interpreter product”; JIT still separate | 5 |

Do **not** re-enable nterp by default without step 3–4.

### 15.6 Entry / exit protocol (N-1 detail)

```text
                    Linux nterp              Win nterp (N-1)
                    ------------             ----------------
Thread base         GS (InitCpu)             r15, set each ExecuteNterp* entry
Refs base           r15                      rbp
C++ Thread::Current thread_local             thread_local (unchanged)
Quick managed self  GS                       r15 (already)
Invoke stub         SysV + GS live           MS→SysV + r15 publish
Nterp trampoline    %gs:exception            THREAD_* via r15
Exception EXPORT_PC -16(r15)                 -16(rbp)
```

Helper sketch (C++):

```cpp
extern "C" ART_QUICK_ENTRYPOINT_ABI Thread* art_nterp_current_thread() {
  return Thread::Current();  // self_tls_ on non-Bionic
}
```

Must be safe when called with partial nterp frame (after callee spill, before SETUP_STACK_FRAME). Prefer no lock / no suspend.

### 15.7 Interaction with `-Xint`, quick invoke, JIT

| Mode | Nterp? | Path |
|------|--------|------|
| `-Xint` | never (`InterpretOnly`) | switch + (opt) quick invoke stubs |
| no `-Xint`, N-0 Win | never | switch; methods may still point at switch entry |
| no `-Xint`, N-1 Win | yes if `CanRuntimeUseNterp` | nterp hot loops; runtime via trampolines |
| JIT on | nterp until compiled | same self contract; code cache W^X |

Enabling nterp does **not** replace the need for correct **quick entrypoint** exception/alloc/JNI paths; nterp *calls* those (alloc entrypoint offsets on Thread, card table, etc.).

### 15.8 Testing plan (when implementing)

1. Unit: assemble `mterp_x86_64` for PE and Linux; size check `handler_size`.  
2. Wine `ART_WIN64_NTERP=1 ART_WIN64_QUICK_INVOKE=1` Hello **without** `-Xint`.  
3. Same matrix as §12b: Math / Io / Net; CoreProbe if fixed.  
4. Exception path: throw/catch across nterp frames (ThrowProbe).  
5. GC: allocation stress with nterp on (ref array walk via rREFS=rbp).  
6. Differential: Linux nterp remains GS; no Linux reg map change.  
7. Host Win10 smoke before default-on.

### 15.9 Explicit non-goals for mterp port

- Emulating Linux GS Thread\* on Windows.  
- Keeping rSELF=%gs with a custom GS base.  
- Using **FS.base = Thread\*** to free r15 (rejected — §16); nterp still follows **N-1**.  
- Porting x86 (32-bit) nterp.  
- Arm64EC nterp before win-x86_64 nterp is done.  
- Claiming Phase 5 JIT complete by finishing nterp.

### 15.10 Decision summary

| Question | Answer |
|----------|--------|
| Can we enable stock Linux nterp on Win? | **No** (GS + r15 dual use). |
| Is switch-only viable? | **Yes** for current product (N-0). |
| **LOCKED** nterp port map? | **N-1:** rSELF=r15, rREFS=rbp + entry Thread materialization. |
| First code touch? | `x86_64ng/main.S` map + `NTERP_TRAMPOLINE` + clinit entry order + regen. |
| Gate to re-enable `IsNterpSupported` on Win? | Feature flag + wine matrix green, not compile success alone. |


## 16. Feasibility: Win64 amd64 `FS.base = Thread*` to free a register (2026-07-18)

**Question:** On win-x86_64, can we set **FS.base = `Thread*`** and address managed TLS as `%fs:OFFSET`, so **r15 is free** (especially to keep nterp’s Linux `rREFS=r15` without N-1’s rREFS→rbp move)?

**Short verdict: REJECT for product.** Keep locked **rSELF = r15**; nterp remains **N-1** if/when ported. FS-as-self is not a reliable free-register win.

### 16.1 Why the idea is tempting

| Fact | Implication |
|------|-------------|
| On **native** Windows x64, **TEB is GS**, not FS | Unlike win-x86 (FS→TEB) or Linux amd64 (FS→libc TLS), FS looks “unused” for TEB |
| Linux ART already uses a **segment base** for Thread\* (GS) | `%fs:OFF` would let Windows share more of the segment addressing shape |
| Nterp register pressure | SysV callee-saves are only `rbx,rbp,r12–r15`; nterp uses all six. If rSELF is **not** a GPR, **r15 stays rREFS** and N-1’s rbp audit shrinks |
| Intel **FSGSBASE** (`RDFSBASE`/`WRFSBASE`/`RDGSBASE`/`WRGSBASE`) | Usermode can read/write bases **only if** the OS enables CR4.FSGSBASE and advertises it |

So: **if** Windows guaranteed a sticky, context-switched, app-owned FS base for every ART thread, FS-self would be an elegant way to free r15.

### 16.2 OS / CPU / ABI constraints

1. **GS is off-limits** (already locked): TEB lives in GS. Wine actively **fixes GS back to TEB** when user code corrupts it (`check_invalid_gsbase` in wine `ntdll` signal path). Product must never `WRGSBASE`/custom GS.

2. **FSGSBASE is OS-gated, not “CPUID implies free use”.**  
   - CPUID leaf 7 EBX.0 = FSGSBASE hardware.  
   - Windows exposes usermode enablement via **`IsProcessorFeaturePresent(PF_RDWRFSGSBASE_AVAILABLE)`** (feature index **22**).  
   - Intel’s enabling guidance: only use `RD/WR*FS/GSBASE` when the OS has turned the feature on for usermode; otherwise instructions **#UD/#GP**.  
   - Wine (10.x on agent01) sets the feature bit from CPUID **and** requires Linux **`AT_HWCAP2` bit for FSGSBASE** (`ntdll/unix/system.c`). On this VM: **CPU has fsgsbase, but wine reports `PF_RDWRFSGSBASE_AVAILABLE = 0`**.

3. **Public Win64 `CONTEXT` has no `FsBase`/`GsBase` fields** (SDK `winnt.h` AMD64 `CONTEXT`: segment **selectors** `SegFs`/`SegGs` only). VEH/exception restore paths do **not** give applications a documented way to save/restore a custom FS base the way integer regs are restored. Any self base that is not a callee-saved GPR is therefore outside the normal exception/unwind contract ART already depends on.

4. **Wine’s use of FS is the opposite of “free for apps”.** On Linux hosts, wine keeps **host pthread TLS in FS** and TEB in GS. Entering wine’s “kernel” / syscall paths rewrites FS with `wrfsbase`/`ARCH_SET_FS` back to `pthread_teb`. An ART policy of “FS always = Thread\*” would **fight wine’s host ABI** even if a bare `WRFSBASE` appeared to work in a toy probe.

5. **Real Windows is not “FS is always free.”** Even when FS is not TEB, the OS owns segment base lifetime across attach, `CreateThread`, APC/callback edges, and any future FSGSBASE policy. There is **no** documented ART-grade API of the form “pin FS.base = this pointer for this thread for the process lifetime” analogous to Linux `arch_prctl(ARCH_SET_GS)` used by AOSP. Depending on `WRFSBASE` when feature bit 22 is set would also **hard-require** new enough CPU+OS combinations and exclude older product SKUs.

6. **CET / CFG / shared code.** Segment-self is a global thread state. Third-party native code, sanitizers, or runtime helpers that assume default FS (or zero base) become latent AVs. Callee-saved **r15** is local to the managed ABI and already the arm64-style model we chose for all Windows targets.

### 16.3 Empirical probes (agent01, 2026-07-18)

Environment: `agent01`, wine-10.0, CPU flags include `fsgsbase`, PE built with project clang / xwin.

| Probe | Result |
|-------|--------|
| Linux host `rdfsbase` / `rdgsbase` | FS = pthread TLS; GS = 0 (Linux ART would use GS via arch_prctl, not shown here) |
| Wine PE: `IsProcessorFeaturePresent(22)` | **0** (feature not advertised to apps) |
| Wine PE: `NtCurrentTeb()` | non-null TEB |
| Wine PE: forced `rdgsbase` (ignore feature bit) | equals TEB (GS base = TEB) |
| Wine PE: forced `rdfsbase` | non-null host pthread-ish base (**not** TEB) — FS is **in use by wine**, not free |
| Wine PE: `WRFSBASE` experiment | process-level fault / unstable under wine (not productizable) |

Conclusion from probes: **on the product’s wine oracle, FS is neither free nor OS-advertised for app base writes.** Host Win10/11 may differ on feature bit 22, but that does not remove CONTEXT/exception and portability problems.

### 16.4 Free-register math (nterp / quick)

| Self model | r15 role | Nterp path | Free-reg gain vs locked design |
|------------|----------|------------|--------------------------------|
| **rSELF = r15** (locked) | Thread\* | **N-1:** rREFS→rbp; audit `%rbp` temps | Baseline |
| FS.base = Thread\* | free for rREFS | Could keep Linux rREFS=r15 map | **+1 GPR** in theory |
| GS.base = Thread\* | free | Linux-like | **Rejected** (TEB) |
| TEB TLS reload every access | free | Possible | **−density** (reject for nterp) |

Even the theoretical +1 GPR is **not free**:

- Every managed entry / attach / `CreateThread` must program FS (vs publishing r15 once in existing invoke stubs).  
- Every exception / suspend / JIT deopt path must ensure FS still points at the right `Thread*` without CONTEXT support.  
- Dual addressing modes (`%fs:OFF` vs `OFF(%r15)`) **or** a full Windows-only segment flavor of quick+nterp+JIT — more code than N-1’s register rename.  
- Wine validation of the product path becomes invalid or requires wine-specific FS hacks.

**Net:** free-reg benefit is real only on paper; engineering + portability cost exceeds N-1.

### 16.5 Decision matrix

| Criterion | FS.base = Thread\* | rSELF = r15 (current) |
|-----------|--------------------|------------------------|
| Possible on some CPUs? | Conditionally (FSGSBASE + OS enable) | **Yes** |
| Portable Win10/11 product SKU? | **No** (feature + policy skew) | **Yes** |
| Safe vs TEB? | FS yes / GS no | Yes |
| Works under wine-10 agent01 oracle? | **No** (PF bit 0; wine owns FS) | **Yes** (already smoking) |
| CONTEXT / VEH friendly? | **No** (no FsBase in public CONTEXT) | **Yes** (callee-saved) |
| Frees r15 for nterp rREFS? | Theoretically yes | No — use N-1 |
| Aligns with win-arm64 x19 model? | No (x86-only trick) | **Yes** |
| **Product recommendation** | **Reject** | **Keep** |

### 16.6 Locked outcome

- **Do not** implement `WRFSBASE` / `%fs:THREAD_*` as managed self on win-x86_64.  
- **Do not** re-open GS-as-Thread on Windows.  
- **Keep** rSELF=r15 for quick / invoke / future JIT.  
- **Keep** nterp design **N-1** (rSELF=r15, rREFS=rbp) when that work starts; FS-self is **not** an alternative to N-1.  
- Optional research-only: if Microsoft later documents a stable process-wide FSGSBASE policy + CONTEXT base fields, re-evaluate — not scheduled.


## 17. Register-map lock: `rSELF=r15`, `rREFS=rbp` (2026-07-18)

**Decision:** On win-x86_64, managed Thread\* is **`r15`**. When nterp is ported, the reference-shadow base is **`rbp`**. **`rSELF=rbp` (N-2) is rejected.**

### 17.1 Locked map

```text
Win managed / quick / JIT / nterp:

  rSELF  = r15     // Thread*  (cross-layer)
  method = rdi
  args   = rsi, rdx, rcx, r8, r9

nterp-only (N-1):
  rPC    = r12
  rFP    = r13     // dex vregs
  rIBASE = r14
  rREFS  = rbp     // ref shadow array base (stack)
  rINST  = rbx

Linux unchanged:
  rSELF  = %gs
  rREFS  = r15
```

### 17.2 Why this pair (including greenfield)

| Concern | Why r15 for self | Why rbp for rREFS |
|---------|------------------|-------------------|
| Cross-layer pin | Self is used by quick + nterp + JIT | Refs base is nterp-only |
| Stack shape | Thread\* is not a frame cookie | rREFS points into the nterp stack frame (FP-ish) |
| JIT allocatable pool | Burning r15 is the usual “last CS” pin; leave rbp free for compiled code | nterp reinterprets rbp only while running |
| Quick stubs | Invoke/OSR often use rbp as temporary CFA/SP | Must not place immortal Thread\* there |
| Linux sharing | Win self is always a new GPR vs Linux GS | rREFS physical reg may differ; share via macros |
| Arm64 analogy | xSELF is a normal callee-save, not FP | — |

Rejected alternatives (summary):

- **N-2 rSELF=rbp:** worse global self home; same rbp-temp audit; dual-self risk.  
- **FS.base=Thread\\*:** rejected §16.  
- **Non-persistent rREFS:** density loss; not a substitute for N-1.  
- **rSELF=r14 / steal rIBASE:** extra nterp churn for no gain over rbp-as-refs.

### 17.3 Implementation implications (nterp)

Before enabling nterp on Win:

1. Evict Linux nterp **rbp temps** (range stack index, entry shorty\*, arg-count `%ebp`, opcode scratches, OSR CFA) to `r10`/`r11`/stack/`rINST` windows.  
2. `#if defined(_WIN32)`: `rSELF=r15`, `rREFS=%rbp`, `CFI_REFS=6`.  
3. GPR Thread addressing (`OFF(rSELF)` / shared `THREAD_*` macros); fix bare `%gs` in trampolines.  
4. Materialize Thread\* at `ExecuteNterp*` entry after callee spill.  
5. Feature-flag (`ART_WIN64_NTERP=1`) until wine matrix green.

Quick path already implements rSELF=r15; no ABI change required for this lock.

### 17.4 Status

| Item | State |
|------|--------|
| rSELF=r15 | **LOCKED** + **implemented** for quick invoke (opt-in env) |
| rREFS=rbp | **LOCKED** + **templates/entry implemented** (2026-07-18); regen mterp_x86_64.S |
| N-2 rSELF=rbp | **REJECTED** |
| Product nterp default | still **N-0**; opt-in `ART_WIN64_NTERP=1` — MS generic-JNI ABI + PE FindLibartCode + **PE `asm_defines`** (`RUNTIME_INSTRUMENTATION_OFFSET=0x328`) landed; residual: system ClassLoader / app dex open under nterp (`Unable to locate class Hello`; switch/`-Xint` OK) |
| Helper | `art_nterp_current_thread` in `nterp.cc` |

### 17.5 PE asm_defines / instrumentation offset (2026-07-18)

Host/Linux codegen for `asm_defines.h` used `ART_TARGET_LINUX`, which mis-laid out
`Runtime` for PE. Observed skew:

| Symbol | Linux host header | PE-correct (`ART_TARGET_WINDOWS`) |
|--------|-------------------|-----------------------------------|
| `RUNTIME_INSTRUMENTATION_OFFSET` | **0x340** | **0x328** (−0x18) |
| other `RUNTIME_*` / `THREAD_*` | same | same (in this tree) |

Effect of wrong 0x340 under nterp: AV on exit-hook path
(`mov 0x340(%rcx),%rcx` → non-pointer, then `cmpb $0,(%rcx)` with `rcx≈0x766`).

Fix:

1. Regenerate PE header with product defines (`ART_TARGET` + `ART_TARGET_WINDOWS`,
   full art includes / compat shims), install into
   `build/win64_phase1/gensrc/art/asm/include/asm_defines.h`.
2. Codegen: `CodegenConfig.asm_target_os` + CLI `--os windows` swap
   `ART_TARGET_LINUX`→`ART_TARGET_WINDOWS` and prefer
   `--target=x86_64-pc-windows-msvc` for the `clang -S` stage
   (`tools/bp2cmake/bp2cmake/codegen.py`).

After PE offset install: switch Hello still green; nterp no longer storms AVs at
instrumentation load — fails later with **`Unable to locate class 'Hello'`**.

### 17.6 Residual ClassNotFound under nterp (2026-07-18 debug)

Evidence (wine, imageless Hello, `ART_WIN64_QUICK_INVOKE=1 ART_WIN64_NTERP=1`):

| Step | Switch / `-Xint` | Nterp |
|------|------------------|-------|
| `Runtime.class_path_string_` | `run/hello.jar` | `run/hello.jar` |
| `VMRuntime.classPath()` (System props init) | `run/hello.jar` | `run/hello.jar` |
| `CreateSystemClassLoader` entry | to-interp bridge | **nterp** (`can_use_nterp=1`) |
| `WinNTFileSystem.getBooleanAttributes0` | `path='run\hello.jar' rv=BA_EXISTS|REGULAR` | **`path=''` (empty)** ×2 |
| `DexFile_openDexFileNative` | opens absolute `…\run\hello.jar` | **never called** |
| `PathClassLoader.toString` | (dex elements present) | `DexPathList[[],nativeLibraryDirectories=[., .]]` |

Conclusion: under nterp, `ClassLoader.createSystemClassLoader` builds a PathClassLoader
with an **empty dex path** (as if `java.class.path` / constructor String were empty),
so no app dex is opened → FindClass(Hello) fails. Native C++ classpath is correct;
the bug is on the **nterp managed path** that materializes/uses that String (property
read, `split`, `File` path, or generic-JNI string arg for `getBooleanAttributes0`).

Controls: nterp env + **`-Xint`** → Hello green; switch (nterp off) → green.

Next debug targets (ordered):

1. String/object correctness across nterp → generic-JNI (MS packing already in place;
   verify jobject arg for instance natives that take `String`).
2. `iget-object` / `move-result-object` / ref-shadow (`rREFS=rbp`) around
   `System.getProperty` and `File.<init>` under N-1.
3. Temporary isolation: force switch interpreter only for
   `ClassLoader.createSystemClassLoader` / PathClassLoader ctor while nterp flag on.

Temporary diagnostics (to remove later): INFO logs in `runtime.cc`
(`CreateSystemClassLoader`, loader.toString), `VMRuntime_classPath`,
`DexFile_openDexFileNative`; stderr logs in `win_fs_natives.c`
`getBooleanAttributes0`.


### 17.7 Boot gate + float exclusion (2026-07-18; packing notes 2026-07-18 21:25)

Workarounds while nterp remains incomplete on Win:

1. **`CanRuntimeUseNterp()`** returns false until `Runtime::IsFinishedStarting()` so
   `ClassLoader.createSystemClassLoader` / PathClassLoader construction use the
   switch interpreter (fixes empty `DexPathList[[]]` / empty File path under nterp).
2. **`CanMethodUseNterp()`** still rejects methods whose shorty contains `F`/`D` (Win only).
   Product symptom without this: `IllegalArgumentException: averageBytesPerChar exceeds
   maxBytesPerChar` on Hello `System.out` under nterp.

### 17.7.1 Float packing progress (2026-07-18)

| Item | Status |
|------|--------|
| Nterp entry `NTERP_MATERIALIZE_RSELF_WIN` spills **xmm0–7** + GPs; spill base in **rbx** (not r11) | Done |
| MS x64 **generic-JNI** reserved-area packing: unified slots — integer/pointer args also advance FPR packing cursor (`PushFpr8(0)` skip) and float args advance GPR (`PushGpr(0)` skip) so xmmN matches parameter index N | Done — fixes `Float.intBitsToFloat` / `floatToRawIntBits` under nterp→generic JNI |
| Managed nterp float arg store (`LOOP_OVER_SHORTY_STORING_XMMS`) / VLFFL(Z/J) ctors | OK in dedicated probes (`I2`, `RFloat`, `JLFloat`) |
| ICU `getAveBytesPerChar`/`getMaxBytesPerChar` native values under nterp | Correct (2 and 3 for UTF-8) when logged |
| **Residual:** `CharsetEncoderICU.newInstance` / Hello println under full nterp (no F/D exclude) still IAE in super ctor | Open — see §17.7.2 |
| Residual empty stdout with exclude | Open (exit 0, no exception; switch prints Hello) |

### 17.7.2 Residual CharsetEncoder under nterp (2026-07-18 22:55)

Evidence that this is **not** simple float packing:

- Generic JNI returns correct `getAveBytesPerChar` (`result_f` low = `0x40000000` = 2.0f) and `getMaxBytesPerChar` (= 3).
- Dedicated probes: `Float.intBitsToFloat` (FI/IF), VLFFL/Z/J managed packing (`I2`/`RFloat`/`JLFloat`), and **NFlow** (same rearrange as `CharsetEncoderICU` + `intBitsToFloat`/`i2f`/range ctor) **PASS** under nterp.
- Full `CEnc` / Hello still IAE without F/D exclude.

Likely remaining area: interaction unique to boot/`CharsetEncoderICU` path (not pure VLFF), possibly after `makeReplacement` / trusted super, or a nterp path that NFlow does not exercise (e.g. class init / clinit / different invoke edge). Keep **F/D exclude** for product `ART_WIN64_NTERP=1` Hello exit 0.

`HasSystemClassLoader()` is a non-CHECK accessor for early startup.


## 13. Appendix — evidence anchors in tree

| Claim | Anchor |
|-------|--------|
| GS = Thread\* on Linux x64 | `vendor/art/runtime/arch/x86_64/thread_x86_64.cc` (`ARCH_SET_GS`) |
| `%gs:THREAD_*` in quick code | `vendor/art/runtime/arch/x86_64/quick_entrypoints_x86_64.S` |
| xSELF = x19 | `vendor/art/runtime/arch/arm64/asm_support_arm64.S` |
| C++ Current = thread_local non-Bionic | `vendor/art/runtime/thread-current-inl.h` |
| QuickEntryPoints in Thread | `quick_entrypoints.h`, `Thread::QuickEntryPointOffset` |
| Win forces interpreter invoke | `vendor/art/runtime/art_method.cc` (`#if defined(_WIN32)`) |
| Win SETUP frames (was int3) | Ported off Win `int3`; Apple still traps |
| PE Runtime load helper | `LOAD_RUNTIME_INSTANCE` in `asm_support_x86_64.S` |
| Nterp Win conflicts (GS + r15=rREFS) | `mterp/x86_64ng/main.S`; generated `mterp_x86_64.S`; §15 |
| Nterp disabled on Win | `interpreter/mterp/nterp.cc` `IsNterpSupported` |
| FS.base=Thread* rejected | §16; wine `PF_RDWRFSGSBASE_AVAILABLE`; public `CONTEXT` has no FsBase |
| rSELF=r15, rREFS=rbp locked | §17; §15 N-1; asm_support `rSELF r15` |

---

## 14. One-paragraph executive summary

On Linux amd64, ART’s managed world is **GS-relative Thread TLS** layered on top of normal C++ `thread_local`, with quick entrypoints and JIT assuming SysV bridges; on Linux arm64, managed world is **x19 = Thread\***. Windows **cannot** reuse GS for Thread\* (TEB owns GS); **FS.base=Thread\*** is also **rejected** (§16: FSGSBASE/wine/CONTEXT portability), so managed self is a GPR. The WinNT design therefore adopts the **arm64-style explicit self register** on all Windows ISAs (**LOCKED: r15** on x86_64 with nterp **rREFS=rbp**; **x19** on ARM64/Arm64EC), keeps C++ `Thread::Current()` on `thread_local`/`TlsAlloc`, and isolates **Microsoft / Arm64EC C++ calling conventions** at quick-entrypoint and invoke bridges. JIT is “just” machine code that obeys the same self + entrypoint contracts with a W^X `VirtualAlloc` cache. **x86_64 is the first implementation target**; x86, arm64, and Arm64EC are specified so the abstractions do not paint us into a GS-shaped corner.
