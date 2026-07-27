# ART on Windows NT — TLS, Managed ABI, Quick Entrypoints, and JIT

**Status:** Win64 x86_64 quick invoke, nterp, managed JIT, and native JIT
implemented and product-default; other Windows ISAs remain design-only
**Updated:** 2026-07-27
**Scope:** Record the cross-ISA design and the implemented x86_64 contracts.
**Related:** [win64_art_port.md](win64_art_port.md) (product phases),
[win32_jit_memory.md](win32_jit_memory.md) (implemented code-cache design), and
[win32_open_items.md](win32_open_items.md) (W-002/W-003 closure plus remaining
W-008/W-010/W-014/W-017 and W-025 work).

---

## 0. Why this document exists

The current multiplatform Win64 product remains imageless but no longer
depends on `-Xint`. Quick invoke, nterp N-1, managed JIT, and native JIT are
default-on. Win64 uses `r15` as rSELF and `rbp` as nterp rREFS; Linux keeps
its GS-relative x86_64 Thread model. The default JIT cache is one unnamed
pagefile-backed section with a contiguous low R/RX primary view and a complete
RW updater alias. Native ABI, tracing, JVMTI forced-interpreter, and native
Windows W-002/W-003/W-004/W-013/W-024 acceptance subsets pass.

The port required a **coherent design** of three layers that AOSP treats as one
machine-specific package:

1. **How C++ finds `Thread*`** (`Thread::Current()`).
2. **How managed / quick / nterp code finds `Thread*` and `QuickEntryPoints`**.
3. **Calling conventions** between JIT/nterp frames, quick entrypoints, and C++ (Win64 / Arm64 / Arm64EC ABIs).

Sections 3 through 17.7 preserve the staged research and implementation
history. Any historical “current” or “next” statement there is superseded by
§17.8, [win32_jit_memory.md](win32_jit_memory.md), and the current tracker.

This document covers those layers for:

| Target label | Machine | Product role |
|--------------|---------|--------------|
| **win-x86_64** | Windows AMD64 PE | **Implemented product target** |
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
| Invoke routing | `runtime/art_method.cc` (`art_quick_invoke_*`, default quick policy + diagnostic opt-out) |
| Offsets | `tools/cpp-define-generator/thread.def` → `THREAD_*_OFFSET` |
| Win asm/platform anchors | W-004 direct same-image `LOAD_RUNTIME_INSTANCE`; ported SETUP frames and rSELF macros |

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
At the initial design checkpoint Win32 **forced**
`EnterInterpreterFromInvoke` because those stubs and the GS replacement were
not ported. That historical restriction is removed: quick invoke is now the
default, with `ART_WIN64_QUICK_INVOKE=0` retained only as a diagnostic opt-out.

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
│ OS: TEB, TlsAlloc, VirtualProtect, VEH, OS thread creation, …   │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 C++ `Thread::Current()` on Windows (all arches)

**Recommendation:** keep **`thread_local Thread* self_tls_`** as primary (already used for non-Bionic), set in `Thread::Init` / reattach / clear on detach.

Optional hardening:

- Mirror into a process-global `TlsAlloc` index for tools that do not see C++ TLS (debuggers, some FFI).
- Do **not** require `pthread_key` on pure Win32 builds long-term (pthread is a portability shim today).

**Fibers:** default **unsupported** for v1 (ART threads are OS threads). W-014
rejects `IsThreadAFiber() == TRUE` explicitly; stack-bound coincidence alone is
not sufficient. If fibers are supported later, self publication must move to
FLS and the complete stack/lifetime contract must be redesigned together.

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
3. Optimizing Win64 code treats r15 as **reserved self**, not a general allocated callee-save. Canonical runtime callee-save frames still spill and restore r15 in the shared x86-64 slot so ART stack visitors and long-jump contexts keep the Linux layout.
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
3. Call ART quick helpers through `ART_QUICK_ENTRYPOINT_ABI`, which is
   `sysv_abi` on Win64, so the shared Linux-shaped register body and frame
   layout remain intact.
4. Use Microsoft registers and shadow space only in an explicit adapter that
   calls an ordinary platform-ABI function, such as a JNI/native boundary.
5. On return, restore the managed frame and check
   `THREAD_EXCEPTION_OFFSET(r15)`.

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
| quick entrypoint asm ↔ ART quick helper C++ | Managed helper ABI; `ART_QUICK_ENTRYPOINT_ABI=sysv_abi` on Win64 x86-64 |
| explicit asm ↔ ordinary OS/library C++ | OS C++ ABI through a local adapter, including Microsoft shadow space/nonvolatiles |
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

### 6.7 Runtime instance load — W-004 implementation record (2026-07-25)

**Status:** direct same-image PE/COFF load implemented; structural, Wine,
Linux, and native Windows acceptance pass. W-004 is closed.

#### 6.7.1 Scope correction

`LOAD_RUNTIME_INSTANCE` is a build-time assembly macro. In the current Win64
build it is expanded into `art.dll` by the x86_64 quick, JNI, and generated
nterp assembly objects. The optimizing JIT does **not** emit this macro and does
not reference `Runtime::instance_` directly.

Therefore W-004 must not require one address sequence for both `art.dll` and
dynamically generated JIT code. A RIP-relative reference inside `art.dll` is
same-image and comfortably in range. Code in the low-4-GiB JIT cache may be
more than signed 32-bit displacement range from a normally loaded `art.dll`;
future JIT code must continue to use `Thread`/quick entrypoints or an explicit
patched literal when it needs runtime services. That separate rule belongs to
W-025, not W-004.

In older wording, “generated paths” meant assembly generated at **build time**
(notably nterp), not runtime JIT machine code.

#### 6.7.2 Current Linux and Windows sequences

Linux x86_64 follows upstream ART and loads the singleton through its GOT entry:

```asm
movq _ZN3art7Runtime9instance_E@GOTPCREL(%rip), reg
movq (reg), reg
```

Other upstream ART ISAs also load the singleton data directly: arm64 uses
`adrp` + `ldr`, RISC-V uses `la` + `ld`, and x86 uses its PC-relative base
sequence. A helper call is not part of the conceptual ART contract.

Windows now loads the existing MSVC-ABI data definition directly from the same
PE image:

```asm
movq "?instance_@Runtime@art@@0PEAV12@EA"(%rip), reg
```

The current RelWithDebInfo objects contain the following direct
`IMAGE_REL_AMD64_REL32` relocations:

| Object/path | Direct `Runtime::instance_` relocations |
|-------------|----------------------------------------:|
| x86_64 quick entrypoints | 563 |
| generated x86_64 nterp | 10 |
| x86_64 JNI entrypoints | 1 |
| **Total** | **574** |

Before W-004, each site expanded to a 23-byte Microsoft-x64 helper call with
shadow space, saved registers, an `r11` scratch, and a returned `Runtime**`
dereference. The implemented 7-byte load removes about 9,184 bytes of repeated
call-site code at this build shape, before alignment and deletion of the helper
itself. The count is evidence, not a fixed test expectation; allocator and
entrypoint generation can change it.

#### 6.7.3 Why the helper was removed

The macro is intended to behave like a data load: write the requested register
without otherwise disturbing managed state. The retired helper could not
express that contract safely through the ordinary Microsoft x64 ABI:

- Microsoft x64 permits a call to clobber `rax`, `rcx`, `rdx`, `r8`–`r11`, and
  `xmm0`–`xmm5`. The macro saves only `rax` and `rcx`, writes `r11` as an
  undocumented scratch, and relies on the helper's current compiler output not
  to use the other volatile registers.
- The call sequence changes flags through `subq`/`addq`; the Linux data-load
  sequence does not. It also mutates the managed stack and pushes a return
  address merely to read a process-global pointer.
- The `reg == rcx` case caused a generic-JNI instrumentation fault and required
  the `r11` scratch workaround.
- Threshold-zero CriticalNative debugging later found the inverse collision:
  the unresolved dlsym stub kept its caller PC in `r11`, and the macro replaced
  it with `Runtime*`. Before W-004, that path reloaded the caller PC after the
  helper.
- Generic JNI also re-materialized an FP return value immediately after the
  helper because an ordinary call is permitted to clobber `xmm0`.

Correctness no longer depends on one C++ leaf function continuing to use a
convenient subset of volatile registers. The direct load does not call through
an ABI, touch `rsp`, change flags, or use an extra scratch register. The local
CriticalNative `r11` reload and immediate generic-JNI `xmm0` re-materialization
were removed with the helper.

#### 6.7.4 PE/COFF feasibility findings

The existing data symbol is already suitable for a direct in-DLL load:

- `Runtime::instance_` is declared `LIBART_PROTECTED`. For the Windows
  `BUILDING_LIBART` build this is `__declspec(dllexport)`; for
  `ART_CONSUMING_LIBART` it is `__declspec(dllimport)`.
- The current DLL exports the Microsoft-ABI data name
  `?instance_@Runtime@art@@0PEAV12@EA`. `openjdkjvmti.dll` imports that same data
  symbol through its IAT, proving that the consumer-side annotation is already
  active.
- A probe using the selected clang GNU driver with target
  `x86_64-pc-windows-msvc` and the `lld-link` linker assembled
  `movq "?instance_@Runtime@art@@0PEAV12@EA"(%rip), %r10` as
  `IMAGE_REL_AMD64_REL32`. Linking the data definition into the same DLL
  resolved it to one 7-byte RIP-relative load.
- Text and data are in the same PE image, so ASLR moves both together and does
  not change the relative displacement. The current DLL is only about 18 MiB;
  the signed 32-bit same-image reach is not a practical constraint.
- Assembly inside `art.dll` should reference the definition directly. It does
  not need an IAT load and must not try to import the DLL currently being linked.
  External consumers continue to get the normal `__imp_...` indirection from
  `dllimport`.

Relevant platform references:

- [Microsoft x64 calling convention](https://learn.microsoft.com/en-us/cpp/build/x64-calling-convention?view=msvc-170)
- [`dllexport` and `dllimport`](https://learn.microsoft.com/en-us/cpp/cpp/dllexport-dllimport?view=msvc-170)
- [PE/COFF AMD64 relocation types](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format#amd64-processors)

#### 6.7.5 Design options

| Option | Shape | Advantages | Costs / risks | Outcome |
|--------|-------|------------|---------------|---------|
| **A. Direct current MS-mangled data symbol** | One same-image RIP-relative `movq` | Smallest source and runtime divergence; preserves the existing export/import ABI; no call, stack, flags, or scratch clobber | Assembly quotes one Microsoft C++ mangled name; a class/member ABI change requires updating it | **Implemented** |
| **B. Stable C assembly label on `Runtime::instance_`** | Give the Windows member `__asm__("art_Runtime_instance")`, then direct-load it | Stable readable symbol; clang correctly emits direct definition references and `__imp_art_Runtime_instance` for consumers | Changes the currently exported ART data ABI and adds a Windows-only declaration attribute in common `runtime.h`; requires rebuilding every consumer | Viable fallback, not preferred while the current ABI works |
| **C. Exported C `Runtime**` address cell** | RIP-load the cell, then dereference it | Stable C name and Linux-like two-load shape without a call | Adds a second global/relocation and potential initialization/ownership questions; still more Windows-only machinery | Fallback only |
| **D. Harden or hand-write the helper** | Custom leaf helper with a documented private clobber set | Avoids exposing a C++ spelling at every assembly relocation | Retains hundreds of calls and the extra symbol; easier to regress than a data load | Reject as permanent design |
| **E. Self-IAT import or cache `Runtime*` in `Thread`** | Import `art.dll` from itself, or add per-thread runtime state | Avoids spelling the current data definition at the use site | Cyclic/self-import is the wrong PE model; a Thread field changes common layout and lifecycle for no benefit | Reject |

Option A best matches the user's Linux-parity rule and is now the product path.
Upstream Linux assembly already names the C++ singleton explicitly; the Windows
branch names the same singleton using the selected MSVC ABI spelling. If the
spelling becomes a real maintenance burden, Option B remains cleaner than
restoring a call helper.

#### 6.7.6 Implementation and verification stages

**Stage W004-A — source conversion and cleanup: COMPLETE**

1. Replaced only the `_WIN32` body of `LOAD_RUNTIME_INSTANCE` with a quoted
   same-image RIP-relative load of the existing MSVC data symbol. Kept the Linux
   two-instruction GOT body byte-for-byte unchanged.
2. Deleted `art_Runtime_instance_ptr()` from `runtime_windows.cc` and deleted
   `Runtime::InstanceLocation()`, which existed only for that helper.
3. Removed the helper-specific comment in `base/macros.h`.
4. Removed only compensations made obsolete by the direct load: the Windows
   caller-PC reload after `LOAD_RUNTIME_INSTANCE` in the critical dlsym stub and
   the immediate generic-JNI `xmm0` re-materialization attributed to the helper.
   Kept the later re-materialization required after an actual instrumentation
   exit-hook call.
5. Did not alter JIT code generation, JIT memory layout, managed argument
   registers, `rSELF`, callee-save frame layouts, or the external
   `Runtime::instance_` export/import contract.
6. Added explicit CMake object dependencies for all five x86_64 assembly
   consumers because the clang ASM rule declared a depfile without emitting
   one. Incremental and clean builds now rebuild the same macro users.

**Stage W004-B — structural artifact gate: COMPLETE**

`tools/verify/win64_phase1/check_w004_runtime_load.py` is integrated into the
Phase 4 aggregate and fails unless all of these hold:

1. `art.dll` exports the existing `Runtime::instance_` data symbol and
   `openjdkjvmti.dll` still imports it through the IAT.
2. No affected object or checked DLL references or exports
   `art_Runtime_instance_ptr`.
3. The quick, JNI, and generated-nterp objects contain direct
   `IMAGE_REL_AMD64_REL32` relocations to `Runtime::instance_`.
4. Every direct relocation in the three affected objects is attached to a
   RIP-relative `movq`, with no helper relocation.
5. All five assembly consumers list the shared macro source as an explicit
   incremental-build dependency.
6. The source cleanup and Linux macro body remain intact. The test does not
   hard-code 574 as a pass condition; each required object must have a nonzero
   direct-reference count and zero helper calls.

Current gate result:

```text
W-004 runtime load structural check: PASS (quick=563 jni=1 nterp=10 total=574)
```

**Stage W004-C — build, Wine, and Linux regression: COMPLETE**

The Win64 graph rebuilt successfully with `-j32`. Acceptance on agent01 passed:

| Gate | Result |
|------|--------|
| PE structural/source/dependency check | PASS, 574 direct / 0 helper |
| JIT smoke | 12/12 |
| Phase 3 aggregate | PASS all gates |
| JIT matrix | 14/14 |
| CriticalNative dual view | 6/6 float+signature + 3/3 tracing |
| CriticalNative J-1 | 6/6 float+signature + 3/3 tracing |
| Normal/FastNative ABI | 7/7 default and 7/7 under tracing |
| JVMTI forced interpreter | dual 3/3; J-1 3/3 |
| Phase 4 aggregate | PASS all gates, including GC/thread/handle/crash paths |
| Linux imageless shared-boot Hello | PASS |
| Linux GC stress | PASS |

Full details are in
`tools/verify/win64_phase4/RESULT-w004-runtime-load.md`.

**Stage W004-D — native Windows closure: COMPLETE**

`tools/win64/host_package/package_win64_w004.sh` builds and locally verifies a
focused native-host bundle containing the Linux-generated structural report
plus quick/nterp/JIT/native-ABI/GC/thread probes. The package checker validates
the inspected DLL hashes, manifest, PE export/import contract, and absence of
the helper. Its staged Wine smoke passes before the final archive is written.

The Windows 10+ PowerShell runner verifies package hashes, runs both dual and
J-1 native paths, performs ten repeated starts, scans all logs for fatal/access-
violation markers, and recursively scans for crash dumps. On Windows 10 build
19044 the returned result contains 28 PASS records, zero failures, and
`OVERALL PASS`; all 22 children exit zero without timeouts, and the dump scan
reports `NO_DMP_FILES`. Returned package metadata and the structural report
match the issued package byte for byte. Procedure and evidence:
`tools/verify/win64_phase4/W004_HOST_CHECKLIST.md` and
`tools/verify/win64_phase4/evidence/w004_host/ACCEPTANCE.md`.

#### 6.7.7 Rollback and review rules

- If direct linking fails, first inspect the actual data-symbol spelling and
  `BUILDING_LIBART` definition. Do not restore the C++ call before testing Option
  B's stable assembly label.
- If a test fails, compare the direct-load object relocation and final linked
  target before changing register or frame logic. The direct `movq` has no ABI
  clobber contract and should make those paths simpler, not require new saves.
- Do not replace the direct load with an absolute address embedded in assembly;
  PE ASLR and image rebasing must remain supported.
- Do not reuse this same-image RIP-relative sequence in low-address JIT code.
  Keep the W-004 and W-025 address-range contracts separate.

### 6.8 JIT design (x86_64 implemented; other arches drafted)

#### Code cache

| Topic | WinNT design |
|-------|----------------|
| Allocation | One unnamed pagefile-backed section mapped twice: contiguous low R/RX primary plus full RW alias |
| Publish | Write through the RW alias; execute through RX; call `FlushInstructionCache` explicitly |
| Free / collect | Existing ART JIT GC hooks; mapped views use `UnmapViewOfFile` and the section handle is closed |
| CFG | Basic real-host execution passes; broader dynamic-code/direct-encoding hardening remains W-025 |
| CET user shadow stack | **Unsupported.** Hardware-enforced Stack Protection must be completely disabled for the ART process; compatibility, audit, and strict modes are rejected under W-010's activation contract |
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

Windows stopped forcing interpreter in `ArtMethod::Invoke` after:

1. rSELF published,  
2. `art_quick_invoke_*` Win stubs exist,  
3. bridge to interpreter remains available for uncompiled methods.

#### Nterp / mterp

Nterp now uses the same Windows rSELF contract: `r15` is Thread and `rbp` is
rREFS. Linux continues to use GS/r15. `ART_WIN64_NTERP=0` is a diagnostic
opt-out; normal Win64 execution does not require `-Xint`.

### 6.9 Thread attach / detach publish protocol

```text
Thread::Init (on the native thread):
  1. discover and validate the current system stack interval
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

The publish order and W-014 Stages A-B of step 1 are implemented. The Win branch now
accepts only the current non-fiber system stack, uses
`GetCurrentThreadStackLimits()`, validates current-SP containment and the
committed-private allocation base, and walks the complete reservation before
publishing the bounds. Failure rejects attachment; there is no clamp or
fabricated-size fallback. The one-page pthread `guardsize` result remains a
facade compatibility value; the Stage B platform helper replaces it with the
measured excluded-low prefix, installs the fixed ART page, and publishes the
adjusted bounds before managed execution. W-010 Stage D now activates common
implicit null/SO translation after those page prerequisites are installed;
native Windows Stage E acceptance remains incomplete.

#### 6.9.1 W-014 bounds and thread-creation contract

The authoritative contract is now
[win32_faults_and_stacks.md](win32_faults_and_stacks.md) §8. In summary:

- `IsThreadAFiber()` rejects fibers before bounds are accepted;
- `GetCurrentThreadStackLimits()` supplies the current system allocation;
- current SP containment, `VirtualQuery(SP)`, and a complete `[low, high)`
  allocation walk must all agree before `Thread` publishes stack fields;
- TEB `StackBase`/changing `StackLimit` are diagnostics only;
- fiber/manual-stack attachment is rejected instead of clamped or guessed;
- ART-created C/C++ threads use `_beginthreadex`, with non-zero stack sizes
  passed as reservations;
- Windows `pthread_t` retains a real joinable handle rather than closing it and
  later reopening by reusable thread ID;
- thread pools pass a requested reservation and do not allocate ignored custom
  `MemMap` stacks;
- non-null `pthread_attr_setstack()` addresses are unsupported and rejected.

The implemented opaque identity also accounts for the compat archive being
copied into several DLLs. Facade-created threads retain a control object and
temporarily publish it in module-local TLS. Externally created threads use an
allocation-free tagged live thread-ID token; `pthread_equal()` compares the
immutable Windows IDs across facade copies and `pthread_gettid_np()` is the
numeric boundary. An FLS-destructor draft was rejected because Wine showed a
loader-teardown callback entering an already non-executable `art.dll`.

These choices do not alter the rSELF publication order above. They ensure that
the `Thread` being published describes the stack on which it is actually
running.

#### 6.9.2 W-014 fixed protected-page contract

ART keeps the Linux conceptual layout while using Windows virtual-memory
primitives:

```text
high address / StackBase
  normal native and managed frames
stack_end
  ART reserved overflow gap (x86_64: 8 KiB)
stack_begin
  ART fixed page: committed, PAGE_NOACCESS
  measured excluded-low prefix:
    lowest page plus adjacent bottom PAGE_NOACCESS/PAGE_GUARD regions
low address / GetCurrentThreadStackLimits.LowLimit
```

The implemented W-014 path never assumes `low + one page` is available. It
preserves the measured bottom prefix, rejects a candidate that is already
`PAGE_GUARD` or `PAGE_NOACCESS`, then records the first suitable reserved or
ordinary committed-private read/write page and its original state in `Thread`.
It commits a reserved candidate read/write, leaves an already committed
candidate and its contents intact, then changes the selected page to
`PAGE_NOACCESS`.
The Windows path does not reuse Linux's recursive `VM_GROWSDOWN` touching or
`madvise()`. Protect/unprotect and direct detach restoration verify the exact
allocation, type, state, and protection. An externally created thread returns
to its original reserved/committed state before detach completes. Windows
`PAGE_GUARD` remains the OS's moving one-shot stack-growth mechanism and is
never ART's repeatable fixed page.

The local permanent probe now covers eight deterministic layouts, actual Wine
main/pthread stack pages, 64 committed restore cycles, 64 real reserved
commit/decommit cycles, and exact direct fault delivery. The W-002 raw-thread
matrix additionally detaches, consumes native stack, reattaches, and detaches
again on the same thread. Native Windows bottom-layout and guard-growth
acceptance remains open.

### 6.10 Exception delivery interaction

Win64 now has two deliberately separate exception paths. The runtime-owned
diagnostic VEH logs selected unhandled first-chance exceptions and returns
`EXCEPTION_CONTINUE_SEARCH`. The active W-010 special-`SIGSEGV` facade owns
a second, first-position managed VEH that filters exact continuable access
violations and adapts the live `CONTEXT` into common `FaultManager`.
Managed soft throws still use ART's `Thread::exception_` and delivery
entrypoints.

Stage D closes the former stack-overflow policy mismatch. Runtime
initialization enables Windows implicit null/SO checks, keeps x86_64 implicit
suspend checks off, and registers stack before null. The x86_64 optimizing
backend and nterp retain their normal unconditional
`RSP - ART_STACK_OVERFLOW_GAP_x86_64` probe; W-014's fixed page makes the
low-stack fault deterministic and common ART redirects it to
`art_quick_throw_stack_overflow`. The switch interpreter continues to use
explicit `Thread::stack_end_` comparisons.

The selected W-010 design is a narrow ART `SIGSEGV` facade over a first
process-wide VEH. It filters only continuable access violations, passes a
minimal `siginfo_t` plus a stack-local non-owning view of the real Win64
`CONTEXT` and AV access kind into common `FaultManager`, and modifies
`CONTEXT.Rip`/`Rsp` in place in the x86_64 handlers. Stack handling requires a
read operation, `fault == Rsp - reserved_bytes`, and containment in W-014's
recorded fixed page; null handling reuses ART's existing method/instruction
validation and signal quick entrypoint. R15/rSELF and all untouched registers
remain in the real OS context.

Native `EXCEPTION_STACK_OVERFLOW`, `EXCEPTION_GUARD_PAGE`, execute AV, and
native/unregistered faults continue through Windows debugger/VEH/SEH policy.
Expected implicit faults do not run first-chance logging or minidump code. The
selected fatal UEF design is separate and chains the previous process filter.
Stage A removes the current diagnostic VEH before `art.dll` unload and restores
ART's predecessor without clobbering a later host UEF; the UEF now calls its
predecessor after the best-effort dump, or returns search when none exists.

W-010 and W-014 now activate atomically for the normal nterp/JIT product. The
main-thread page is installed before runtime architecture flags are selected;
the VEH, stack/null handlers, and nterp generated-code range are registered
before startup publishes nterp entrypoints; later attachments install their
page under the enabled flag. Focused Wine passes repeated nterp/JIT NPE/SOE
and clean handled-fault diagnostics. Native handler-stack and chain evidence
remains Stage E. See the authoritative design and full matrix in
[win32_faults_and_stacks.md](win32_faults_and_stacks.md), with state tracked in
[win32_open_items.md](win32_open_items.md).

This exception design does not support CET user shadow stacks. The decisive
conflict is the shared x86_64 `art_quick_do_long_jump`: it restores an older
regular `RSP` and returns to a managed catch/deoptimization PC without
restoring CET's protected return stack. Ordinary explicit exceptions,
deoptimization, pending JNI exceptions, and W-010's implicit NPE/SOE path all
use this mechanism. W-010 additionally modifies `CONTEXT.Rip` and, for null
delivery, `CONTEXT.Rsp`, which conflicts with CET context-IP validation without
a complete EH-continuation contract. Therefore every ART process must have
Hardware-enforced Stack Protection completely disabled, every project PE link
must explicitly use `/CETCOMPAT:NO`, and startup must reject every nonzero
`ProcessUserShadowStackPolicy` before managed threads or JIT. CFG remains a
separate W-025 mitigation; `/guard:ehcont`, dynamic JIT CET-range registration,
IBT, and `-fcf-protection` do not repair ART's shadow-stack mismatch.

The Stage 0 enforcement is implemented: all generated and handwritten project
PE links use explicit `/CETCOMPAT:NO`, the selected package/LLVM libc++ scan
finds no CET-compatible marker, and `Runtime::Init()` fails closed on every
nonzero or unexpectedly unavailable policy before memory/thread/JIT startup.
Stage C focused Wine evidence also passes: the deterministic record probe
passes all eight cases, and the live VEH/context probe forwards two real page
faults, redirects `Rip`, returns `Rax == 0`, survives promotion, and removes
the action cleanly. Stage D now also gates generated nterp/JIT implicit NPE
and SOE paths under Wine, including repeated caught faults and clean handled-
fault diagnostics. Wine exercises the disabled-policy allow path; native
Stage E compatibility, chain/debugger behavior, stack-budget evidence, and
strict shadow-stack-policy rejection remain pending acceptance.

JIT deopt flags (`THREAD_DEOPT_CHECK_REQUIRED_OFFSET`) stay Thread fields accessed via self base.

---

## 7. Per-architecture draft sketches

### 7.1 win-x86_64 (implemented)

```text
C++ ABI:     rcx, rdx, r8, r9 + 32B shadow
Managed self: r15 (LOCKED); nterp rREFS: rbp (LOCKED)
Thread base:  [r15 + THREAD_*_OFFSET]
Entrypoint:   call [r15 + QUICK_ENTRYPOINT_OFFSET(pX)]  or load ptr then call
Invoke stub:  MS x64 entry → set r15 → managed
Reject:       ARCH_SET_GS, %gs:THREAD_*, SysV-only invoke stubs
```

**Implemented slices:**

1. Assembler macros for THREAD_LOAD/STORE + DEFINE_FUNCTION (PE symbols, no `@PLT`).  
2. `art_quick_invoke_{,static_}stub` Win64.  
3. Port `SETUP_*_FRAME` macros off `int3`.  
4. Port high-traffic quick entrypoints (alloc, invoke trampolines, exception deliver, JNI).  
5. Use quick invoke by default with a diagnostic force-interpreter opt-out.
6. JIT emitter: self via r15; pagefile-backed dual-view W^X cache.
7. Wine64 gates plus focused real-Windows W-024 and W-013 acceptance.

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

## 9. Decision status

1. **Managed method/arg registers on win-x86_64:** **CLOSED** — keep the
   Linux-like managed convention and convert only at Microsoft x64 native/C++
   boundaries.
2. **Exact rSELF register:** **CLOSED — r15** (nterp **rREFS=rbp**). Spill-bitmap/JNI audit is implementation work, not an open design choice.  
3. **Nterp priority vs optimizing JIT:** **CLOSED for x86_64** — both are
   implemented and default-on.
4. **CET / shadow stack / CFG policy:** **CLOSED as a product contract.** CET
   user shadow stacks are unsupported and Hardware-enforced Stack Protection
   must be completely disabled for the ART process; compatibility, audit, and
   strict modes are rejected. Build and startup enforcement is implemented;
   native forced-policy acceptance remains pending. CFG and dynamic-code
   hardening remain separate W-025 work.
5. **Wine sufficiency:** **CLOSED as policy** — Wine is a development gate, not
   final product acceptance. Focused native W-024/W-013 matrices pass; broader
   host acceptance remains tracked separately.
6. **Arm64EC product:** design-only; no product SKU is scheduled.
7. **Single art.dll multi-ISA:** rejected for now.

---

## 10. Historical design-phase non-goals

The first two bullets describe the scope of the original design-only change;
the x86_64 implementation subsequently landed.

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
| Phase 2–3 (`-Xint`) | Historical bootstrap: C++ TLS only |
| Entrypoint/nterp port | **Complete:** Win invoke stubs, quick entrypoints, rSELF macros, N-1 |
| **Phase 5 JIT** | **Implemented/default:** managed/native codegen plus corrected dual view |
| oat/dex2oat | Optional; imageless JIT can precede oat PE |

---

## 12. Historical implementation order (completed for x86_64)

1. Document lock-in: **no GS Thread\* on Windows**; **rSELF register model**.  
2. Introduce THREAD_LOAD/STORE macros; keep Linux GS path intact.  
3. Implement Win64 `art_quick_invoke_*` + remove unconditional interpreter force under a flag.  
4. Port entrypoints in dependency order (exception, alloc, invoke trampolines, JNI).  
5. Wine gates: compiled Hello without `-Xint` (still imageless).  
6. JIT cache + smoke; then stress (phase 4-style) under wine/host.  
7. Revisit arm64 / Arm64EC only after x86_64 contracts stabilize.

---


## 12b. Historical implementation checkpoint (2026-07-18)

Locked for coding:

1. **Managed arg regs:** Linux-like SysV shape inside managed/quick asm; convert only at edges.  
2. **rSELF:** **r15** on win-x86_64 (quick / JIT / nterp).  
3. **nterp map (when ported):** **N-1** — `rSELF=r15`, **`rREFS=rbp`**; **not** N-2 (`rSELF=rbp`). See §15 / §17.  
4. **C++ quick helpers:** `ART_QUICK_ENTRYPOINT_ABI` = `sysv_abi` on Win64 so asm can keep SysV `call` sites.  
5. **Invoke stubs:** Microsoft x64 entry at `art_quick_invoke_*`, then map to SysV body + publish r15.  
6. **Force-interpreter (W-001):** **CLOSED** — quick invoke default ON; opt-out `ART_WIN64_QUICK_INVOKE=0`.

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
| Nterp initially disabled on `_WIN32`; later ported/default-on | `interpreter/mterp/nterp.cc` |

Wine smoke (2026-07-18, `build/win64_phase1`):

| Gate | Result |
|------|--------|
| `dalvikvm.exe -showversion` | PASS (`ART version 2.1.0 x86_64`) |
| Hello default (force-interp) | PASS (`Hello from dalvikvm!`, `java.version=1.8.0`) |
| Hello `ART_WIN64_QUICK_INVOKE=1` + `-Xint` | **PASS** — no `ArtMethod::Invoke via interpreter` spam; invoke→quick stub→interpreter bridge works |

### Next-phase progress (2026-07-18, design §12 steps 4–5)

**Nterp (historical 2026-07-18):** was disabled on Win32 until N-1 port. **Superseded by §17.8** — product default nterp ON.

Wine matrix with `ART_WIN64_QUICK_INVOKE=1` (fresh PE, imageless):

| Gate | `-Xint` | no `-Xint` |
|------|---------|------------|
| Hello | PASS | **PASS** (was AV before nterp off) |
| MathProbe | PASS | **PASS** |
| IoProbe | PASS | **PASS** |
| NetProbe | PASS | **PASS** |
| CoreProbe | FAIL (NPE `toCopy==null`, both modes) | FAIL (same pre-existing) |

Design step 5 (**compiled Hello without forced `-Xint`**, still imageless) is **met** under opt-in quick invoke + switch interpreter.

The checkpoint's quick-invoke, nterp, CoreProbe, W-012, W-024, and Phase-5 JIT
items are complete. W-002's managed-entry implementation and Wine/Linux/native
Windows verification are complete; deterministic R2 passes every OSR and
attached-thread mode pair and closes W-002. W-003's frame-family and native
XMM boundary matrices also pass on Windows build 19044. Current residual work
is W-008, native W-010/W-014 acceptance, W-017, broader W-025 hardening, and the other
host-validation gaps in [win32_open_items.md](win32_open_items.md).

## 15. Nterp / mterp on WinNT x86_64 — analysis and design

**Status:** IMPLEMENTED for Win64 x86_64; the detailed subsections preserve the
pre-implementation option analysis
**Current product (updated §17.8):** `IsNterpSupported()` **true** on `_WIN32` by default (opt-out `ART_WIN64_NTERP=0`).  
**Goal (historical design):** specify a correct port that fits the locked rSELF model without reintroducing GS Thread\* — **met**.

### 15.1 What nterp is (in this tree)

ART’s fast interpreter is **nterp** (templates under `vendor/art/runtime/interpreter/mterp/`, generators `gen_mterp.py`). For x86_64 the arch pack is **`x86_64ng/`**; codegen emits `mterp_x86_64.S` (in-tree gensrc: `build/*/gensrc/art/asm/mterp/mterp_x86_64.S`).

Control model (README):

- Handler table: entry ≈ `handler_base + opcode * NTERP_HANDLER_SIZE` (computed goto).  
- **`rIBASE`** holds the active handler table base; refreshed on backward branches / throws / returns.  
- Frame layout matches optimizing ABI (see `nterp_helpers.cc`): callee saves, dex regs, **reference regs**, caller fp, dex_pc_ptr, outs, `ArtMethod*`.  
- No ManagedStack transitions between nterp and compiled frames.  
- Entry points: `ExecuteNterpImpl` / `ExecuteNterpWithClinitImpl` (OAT-prefixed headers for stack walk).

Historical gate at the design checkpoint (`nterp.cc`):

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

#### Option N-0 — Switch interpreter only (historical fallback)

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

   `ExecuteNterpWithClinitImpl` could not read TID via rSELF **before** that
   materialization (the design-checkpoint source did). The required order was:
   spill → load Thread → tid check → body, or call a tiny C++ helper that does
   the clinit gate.

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
Historical start: N-0  switch only on Win
LOCKED nterp port: N-1  rSELF=r15, rREFS=rbp  (+ optional N-4 dual gensrc)
REJECTED:          N-2 (rSELF=rbp) / N-3 (TLS every access)
Current product:   N-1 plus JIT, both using the same r15 self contract
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

### 15.8 Testing plan used for implementation

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
| Is switch-only viable? | **Yes only as a diagnostic fallback;** N-1 is the product default. |
| **LOCKED** nterp port map? | **N-1:** rSELF=r15, rREFS=rbp + entry Thread materialization; implemented. |
| First code touch? | Historical: `x86_64ng/main.S` map + `NTERP_TRAMPOLINE` + clinit entry order + regen. |
| Gate to re-enable `IsNterpSupported` on Win? | Met; Wine matrices are green and the product default is on. |


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
| rSELF=r15 | **LOCKED** + **implemented**; quick invoke **default ON** |
| rREFS=rbp | **LOCKED** + **templates/entry implemented** (2026-07-18); regen mterp_x86_64.S |
| N-2 rSELF=rbp | **REJECTED** |
| Product nterp default | **ON** (2026-07-19); opt-out `ART_WIN64_NTERP=0` — N-1 map + MS generic-JNI + PE `asm_defines` + boot gate + CE packing fix landed |
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
2. **`CanMethodUseNterp()` F/D exclude removed** (goal). Residual CharsetEncoder path
   under full nterp still IAE — see §17.7.2 (**FIXED**). Product default is nterp **ON** as of §17.8.

### 17.7.1 Float packing progress (2026-07-18)

| Item | Status |
|------|--------|
| Nterp entry `NTERP_MATERIALIZE_RSELF_WIN` spills **xmm0–7** + GPs; spill base in **rbx** (not r11) | Done |
| MS x64 **generic-JNI** reserved-area packing: unified slots — integer/pointer args also advance FPR packing cursor (`PushFpr8(0)` skip) and float args advance GPR (`PushGpr(0)` skip) so xmmN matches parameter index N | Done — fixes `Float.intBitsToFloat` / `floatToRawIntBits` under nterp→generic JNI |
| Managed nterp float arg store (`LOOP_OVER_SHORTY_STORING_XMMS`) / VLFFL(Z/J) ctors | OK in dedicated probes (`I2`, `RFloat`, `JLFloat`) |
| ICU `getAveBytesPerChar`/`getMaxBytesPerChar` native values under nterp | Correct (2 and 3 for UTF-8) when logged |
| **Residual:** CharsetEncoderICU under full nterp | **FIXED** 2026-07-19 — see §17.7.2 (static-flag ZF clobber) |
| Residual empty stdout with exclude | Open (exit 0, no exception; switch prints Hello) |

### 17.7.2 CharsetEncoder under nterp — FIXED (2026-07-19 02:56)

**Root cause:** In `ExecuteNterpImpl` slow-path arg setup (`x86_64ng/main.S`), the sequence was:

```
testl  IS_STATIC, flags(%rdi)
movq   shorty+1, %r10
addq   $1, %r10          # clobbers ZF
leaq   ...               # also clobbers flags
jne    .Lhandle_static   # branch used *stale/wrong* ZF
```

`addq $1, %r10` (shorty always non-null) left ZF clear, so **every method took the static store path**. Instance methods then:

1. Stored `rsi` as first shorty arg (should skip `this` already in place),  
2. Skipped float slots against a shifted shorty,  
3. Left `L F F L …` ctor args misaligned.

Observed symptom: `CharsetEncoderICU` / `super(cs, avg, max, repl, true)` IAE  
`aBits=40400000` (3.0f as average) / `mBits=40e3xxxx` (object bits as max).  
Native `getAve`/`getMax` were correct; app VLFF probes that stayed nterp→nterp often hid the bug.

**Fix:** Branch on static immediately after `testl` (`jnz .Lsetup_static_bases`), then set shorty/base pointers on each side. Instance path skips `this` before `LOOP_OVER_SHORTY_STORING_GPRS`.

**Also kept (supporting):** post-Start UpgradeToNterp + force when imageless `!verified`; Win `CanUseNterp` clinit fallback; generic-JNI / nterp F-return xmm0 re-materialize after PE helper clobber; **no F/D exclude**.

**Verification (wine, imageless, `ART_WIN64_QUICK_INVOKE=1 ART_WIN64_NTERP=1`):**

| Probe | Result |
|-------|--------|
| CEnc | PASS (exception=0) |
| switch CEnc | PASS |
| NFlow / VLj / I2F / FRet / CEBoot / CELike | PASS |




## 17.8 Product defaults ON (2026-07-19) — Linux-like nterp + quick invoke

**Status:** IMPLEMENTED

Win64 product now matches Linux ART for the normal execution path:

| Knob | Previous | Now |
|------|----------|-----|
| Quick invoke (`ArtMethod::Invoke`) | Force interpreter unless `ART_WIN64_QUICK_INVOKE=1` (W-001) | **Default ON**; opt-out `ART_WIN64_QUICK_INVOKE=0` |
| Nterp (`IsNterpSupported`) | Off unless `ART_WIN64_NTERP=1` | **Default ON** (N-1 rSELF=r15 / rREFS=rbp); opt-out `ART_WIN64_NTERP=0` |
| JIT (`UseJitCompilation`) | Already default **true** in `runtime_options.def` | Unchanged (still disabled by `-Xint` / AOT compiler / debuggable paths) |
| Boot gate | `CanRuntimeUseNterp()` false until `Runtime::IsFinishedStarting()` | Unchanged (switch for early ClassLoader) |

Code:

- `vendor/art/runtime/art_method.cc` — `kWin64QuickInvoke` default true unless env `=0`
- `vendor/art/runtime/interpreter/mterp/nterp.cc` — `IsNterpSupported` default true unless env `=0`
- Post-Start `UpgradeToNterpVisitor` still re-points imageless boot methods

Smoke (wine, imageless, **no** `ART_WIN64_*` env):

| Probe | Expectation |
|-------|-------------|
| Hello / CEnc / float probes | PASS without env opt-in |
| `ART_WIN64_NTERP=0` | falls back to switch interpreter |
| `ART_WIN64_QUICK_INVOKE=0` | force interpreter invoke (legacy W-001) |
| `-Xint` | still interpret-only (no nterp/JIT compile path) |

W-001 marked CLOSED in [win32_open_items.md](win32_open_items.md).

**JIT memory / codegen:** see [win32_jit_memory.md](win32_jit_memory.md) §13 — managed and native JIT use the corrected dual view by default; D-1 r15 TLS audit is complete; the compiled-JNI managed/native split plus XMM-to-XMM moves pass a 7/7 registered/unresolved normal/FastNative mixed/high-FP matrix across rebinding and method tracing without extra target compilation; and registered/unresolved CriticalNative unified ordinals, shadow/stack layout, dlsym lookup, and method tracing pass in both memory modes through the ART-owned native-load bridge. A separate Win64 `openjdkjvmti.dll` passes the real forced-interpreter transition 3/3 in each memory mode over all three native kinds. Math.ceil/floor are native CriticalNative methods again and use the same registration table on ELF and PE. Per-method compile records are opt-in through `ART_WIN64_JIT_LOG_COMPILES=1`. W-024 native-host acceptance, upstream interpreter cleanup, and default native-JIT restoration are complete.

## 17.9 W-002 managed OSR and attached-thread entries (2026-07-25)

**Status:** ACCEPTED on native Windows 10 build 19044; W-002 closed

The rSELF design did not need to change. The remaining failures were two local
OSR transitions that bypassed the already-correct quick-invoke boundary.

### Quick/switch OSR

`jit.cc` calls `art_quick_osr_stub` as an ordinary platform C++ function.
Changing that declaration to a SysV ABI would increase divergence and push a
Windows-only convention into C++ callers. The stub therefore retains the
Microsoft x64 entry and converts only inside its Windows prologue:

| Microsoft x64 input | Shared assembly body |
|---------------------|----------------------|
| rcx: copied stack | rdi |
| rdx: stack size | rsi |
| r8: native PC | rdx |
| r9: result pointer | rcx |
| stack argument 5: shorty | r8 |
| stack argument 6: `Thread*` | r9, then managed r15 |

The prologue preserves rdi and rsi because they are Microsoft nonvolatile
registers, and the common save block preserves the native caller's r15 before
publishing managed rSELF. W-003 initially added a 96-byte boundary area for
XMM6-XMM11. The W-010 full-width follow-up expands only that Windows adapter
to 160 bytes for XMM6-XMM15, so the Windows conceptual CFA is now 256 bytes;
Linux retains its original 80-byte CFA and instruction path. W-010 also added
two contiguous PE unwind ranges: an R12-anchored entry/variable-copy range and
an RSP-based inherited-frame return range. Immediately before the JIT handoff,
the entry path sets RBP to the copied RSP, reproducing the dynamic Win64 JIT
frame anchor that OSR skips. The return record does not trust R12 or RBP because
OSR code reconstructs managed state before returning. The emitted XMM unwind
offsets are 64 through 208 relative to the completed 248-byte fixed frame, not
0 through 144 relative to the temporary store RSP. The accepted W-002
rSELF/OSR transition, W-003 Microsoft-XMM normal-return repair, and W-010
exception-unwind records are separate contracts.

### Nterp OSR

The first defect was a raw `free` call shaped for SysV. Windows now calls
`NterpFree`, whose assembly-facing SysV ABI bridges to UCRT's Microsoft ABI
with the required shadow space.

That correction exposed the deeper frame defect. Linux reuses nterp's
callee-save block as the compiled OSR frame because their layouts match.
Windows pins r15 as rSELF and excludes it from the compiled spill set, so the
nterp and compiled layouts are intentionally different. Reusing the block let
compiled OSR return with the wrong stack restoration state.

The Windows transition now:

1. keeps nterp's original save block as a return adapter;
2. saves the compiled native PC away from `NterpFree`;
3. copies the complete compiled OSR frame below the adapter;
4. frees the temporary OSR data through `NterpFree`;
5. jumps to compiled code;
6. receives the compiled return in the adapter; and
7. restores XMM12–XMM15 and rbx/rbp/r12–r15 before returning to the original
   managed caller.

The compiled result remains in rax/xmm0 throughout the adapter. Linux keeps its
original direct transition and raw libc `free`.

### Native attach contract

`AttachCurrentThread` and `AttachCurrentThreadAsDaemon` establish ART's
C++ TLS state; they do not own the native caller's r15. A later JNI
`CallStaticLongMethod` crosses `ArtMethod::Invoke`, which preserves native
r15 and publishes managed rSELF at the quick boundary. The focused probe
pre-JITs the callback, creates regular and daemon Win32 threads, checks daemon
state and `Thread.currentThread()`, allocates objects, validates exact
64-bit results, detaches, and requires `GetEnv == JNI_EDETACHED`.

### Verification

| Control | Result |
|---------|--------|
| Source and PE object structure | PASS |
| OSR, dual/default nterp | 2/2 |
| OSR, dual/switch | 2/2 |
| OSR, J-1/default nterp | 2/2 |
| OSR, J-1/switch | 2/2 |
| Attached-thread JNI, same four mode pairs | 2/2 each; 16 threads per process |
| Full Phase 3 Wine aggregate | PASS |
| Full Phase 4 Wine aggregate | PASS |
| Linux full build and shared-boot Hello/GC | PASS |
| Linux nterp OSR baseline/OSR/jump/checksum | PASS |
| Native Windows R1 | PASS identity/structure, 8/8 attach, and 4/4 switch OSR; default-nterp 0/4 jumps with clean checksums/exits |
| Deterministic R2 Wine OSR | PASS 2/2 per mode pair with warmup/optimize 100 and checksum `65553463744` |
| Staged R2 package Wine smoke | 8/8 processes |
| Native Windows R2 | PASS 21/21 records: OSR 8/8, attach 8/8, no fatal marker or dump |

R1 left the nterp warmup threshold at 65535, allowing the short loop to finish
before asynchronous OSR installation was followed by another hotness check.
R2 pins warmup and optimize thresholds to 100 and lengthens the loop to
2,000,000 iterations. Native Windows R2 passes every required transition on
build 19044. The accepted result and the evidence-transport normalization are
documented in
`tools/verify/win64_phase4/evidence/w002_host/ACCEPTANCE.md`.


## 17.10 W-003 quick callee-save frames and native-boundary gap (2026-07-26)

**Status:** CLOSED — SETUP, Microsoft-XMM boundary repair, focused Wine gates,
and native Windows acceptance complete

All four x86-64 runtime callee-save frame families execute their shared
non-Apple bodies on Windows. Only refs-only and all-callee-saves ever had a
Windows trap; refs-and-args and save-everything were already shared. Matched
current PE and ELF objects have an identical `int3` symbol/count distribution,
so no Windows-only SETUP trap remains.

The managed frame design should stay unchanged: Linux-shaped ART argument
registers, canonical x86-64 frame sizes/spill masks, r15 Thread addressing on
Windows, and `sysv_abi` ART quick helpers. Microsoft ABI conversion belongs
only at explicit platform boundaries.

The confirmed defect was at three such boundaries:
`art_quick_invoke_stub`, `art_quick_invoke_static_stub`, and
`art_quick_osr_stub`. They are ordinary Microsoft-x64 C++ entries and preserve
the additional nonvolatile GPRs. W-003 initially reserved a Windows-only
96-byte area for XMM6-XMM11. The W-010 exception-unwind follow-up now reserves
160 bytes and saves the lower 128 bits of XMM6-XMM15 before argument setup or
the managed OSR jump. Restoration occurs before the Microsoft-ABI return. The
area stays outside canonical ART frames and preserves alignment; the Win64
OSR conceptual CFA is 256 while Linux remains 80.

`check_w003_quick_boundaries.py` permanently checks all four SETUP source
contracts, each PE boundary sequence, absence of the save area in Linux
objects, and the complete matched PE/ELF `int3` function/count multiset. The
current rebuilt pair passes with 212 trap-bearing functions and 401 shared
traps. The checker compares distributions rather than fixing those snapshot
counts as constants.

The opt-in attributed frame probe now counts the four SETUP families while
preserving EFLAGS and emits no product symbols when disabled. It passes 8/8
Wine processes across `-Xint`, switch, nterp, and threshold-zero JIT. Nterp
and JIT each independently report positive refs-only, refs-and-args,
all-callee-saves, and save-everything counts. The dedicated native sentinel
saves and seeds XMM6-XMM11, invokes a twelve-double Java callback through JNI
quick invoke, compares all 96 bytes, and restores the native caller. It passes
6/6 nterp/switch/JIT Wine processes; an intentional-clobber self-test returns
the exact six-bit mask `0x3f`.

The initial frame workload also isolated the independent W-010 defect:
nterp's implicit null load faulted at `nterp_op_invoke_virtual+0x3a` because
the old Win64 VEH only logged generated-code faults. W-003 continues to exclude
that one subtest so its frame attribution remains stable, but Stage D now
translates the product fault and the dedicated W-010 gate covers repeated
nterp/JIT read/write NPEs without adding a compiler or interpreter fallback.
Explicit class-cast, array-store, and bounds paths remain covered by W-003.

The focused native-host package validates its PE/hash contract, smokes all
seven modes under Wine, restores product `art.dll`, and ships without runtime
logs, dumps, or traces. Windows 10 build 19044 returns exactly 19 PASS records
and `OVERALL PASS` over 8 frame runs and 6 XMM runs. All children exit zero
without timeout; nterp and JIT each attribute all four frame families; every
XMM run reports `mask=0 selfTestMask=63`; and fatal/dump scans are clean. This
accepted W-003 evidence remains the historical six-register checkpoint. The
same sentinel has since been extended to XMM6-XMM15 for W-010 while retaining
`selfTestMask=63` as a compatibility field and adding the authoritative
`fullSelfTestMask=1023`; focused Wine passes 2/2 in nterp, switch, and
threshold-zero JIT. Native repetition is part of W-010 Stage E. The JIT logs
explicitly confirm creation of the Windows pagefile-section J-2
dual view before successful compilation.

Targeted PE assembly unwind metadata is now present for the static invoke,
generic-JNI, and split OSR boundaries even though the generic CFI macros remain
disabled on Windows. ART managed unwinding is separate. W-010 owns both the
exact VEH/non-owning-`CONTEXT` managed-fault adapter and the Windows unwind
records required for exception dispatch across exercised native/managed
boundaries; a missing record on another fatal-crossable frame is a correctness
gap, not merely dump hardening. This remains under the required
CET-shadow-stack-disabled process contract; unwind/EH-continuation metadata
cannot be interpreted as latent CET support.

See
[RESULT-w003-quick-frames-analysis.md](tools/verify/win64_phase4/RESULT-w003-quick-frames-analysis.md)
and
[RESULT-w003-frame-probe.md](tools/verify/win64_phase4/RESULT-w003-frame-probe.md)
and
[RESULT-w003-xmm-sentinel.md](tools/verify/win64_phase4/RESULT-w003-xmm-sentinel.md)
and
[W003_HOST_CHECKLIST.md](tools/verify/win64_phase4/W003_HOST_CHECKLIST.md)
and
[native acceptance](tools/verify/win64_phase4/evidence/w003_host/ACCEPTANCE.md)
for the design, staged implementation, and accepted evidence.


## 13. Appendix — evidence anchors in tree

| Claim | Anchor |
|-------|--------|
| GS = Thread\* on Linux x64 | `vendor/art/runtime/arch/x86_64/thread_x86_64.cc` (`ARCH_SET_GS`) |
| `%gs:THREAD_*` in quick code | `vendor/art/runtime/arch/x86_64/quick_entrypoints_x86_64.S` |
| xSELF = x19 | `vendor/art/runtime/arch/arm64/asm_support_arm64.S` |
| C++ Current = thread_local non-Bionic | `vendor/art/runtime/thread-current-inl.h` |
| QuickEntryPoints in Thread | `quick_entrypoints.h`, `Thread::QuickEntryPointOffset` |
| Win quick-invoke policy | `vendor/art/runtime/art_method.cc` (default quick invoke with diagnostic opt-out) |
| Win SETUP frames (was int3) | Ported off Win `int3`; Apple still traps |
| W-003 frame/ABI analysis | §17.10; `tools/verify/win64_phase4/RESULT-w003-quick-frames-analysis.md` |
| Direct PE Runtime singleton load | `LOAD_RUNTIME_INSTANCE` in `asm_support_x86_64.S`; §6.7 |
| Nterp Win conflicts (GS + r15=rREFS) | `mterp/x86_64ng/main.S`; generated `mterp_x86_64.S`; §15 |
| Nterp Win policy | `interpreter/mterp/nterp.cc` `IsNterpSupported` (default on; diagnostic opt-out) |
| Win quick and nterp OSR entries | `quick_entrypoints_x86_64.S` `art_quick_osr_stub`; `mterp/x86_64ng/main.S` `NterpHotnessCheck`; §17.9 |
| FS.base=Thread* rejected | §16; wine `PF_RDWRFSGSBASE_AVAILABLE`; public `CONTEXT` has no FsBase |
| rSELF=r15, rREFS=rbp locked | §17; §15 N-1; asm_support `rSELF r15` |

---

## 14. One-paragraph executive summary

On Linux amd64, ART’s managed world is **GS-relative Thread TLS** layered on top of normal C++ `thread_local`, with quick entrypoints and JIT assuming SysV bridges; on Linux arm64, managed world is **x19 = Thread\***. Windows **cannot** reuse GS for Thread\* (TEB owns GS); **FS.base=Thread\*** is also **rejected** (§16: FSGSBASE/wine/CONTEXT portability), so managed self is a GPR. The WinNT design therefore adopts the **arm64-style explicit self register** on all Windows ISAs (**LOCKED and implemented: r15** on x86_64 with nterp **rREFS=rbp**; **x19** remains a design for ARM64/Arm64EC), keeps C++ `Thread::Current()` on `thread_local`/`TlsAlloc`, and isolates Microsoft C++ calling conventions at explicit quick-invoke and OSR bridges. The Windows nterp OSR adapter preserves the deliberately different nterp and compiled save layouts. JIT code obeys the same self and entrypoint contracts and uses one unnamed pagefile-backed section with a low contiguous R/RX primary view plus an RW updater alias. **W-002's rSELF/OSR contract and W-003's quick-frame/XMM boundary contract are both accepted and closed after native Windows repetition.** x86, arm64, and Arm64EC remain design-only so future work is not forced into a GS-shaped abstraction.
