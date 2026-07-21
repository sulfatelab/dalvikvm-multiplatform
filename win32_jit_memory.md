# Win64 JIT memory & codepath — feasibility analysis

**Status:** FEASIBILITY DRAFT (active)  
**Date:** 2026-07-19  
**Repo root doc:** `./win32_jit_memory.md`  
**Related:** [win32_tls_jit_entrypoints.md](win32_tls_jit_entrypoints.md) (§15–§17.8 nterp/rSELF), [win32_open_items.md](win32_open_items.md), Phase 5 JIT  

## 0. Question

Is it feasible to run ART **JIT compilation** on Win64 PE (wine first, real Windows later) the way Linux ART does — i.e. `UseJitCompilation=true` actually creates a code cache, compiles hot methods, and executes that code safely under the locked managed ABI (**rSELF=r15**, no GS Thread\*)?

Short answer:

| Subproblem | Feasible? | Difficulty | Blocks “JIT works”? |
|------------|-----------|------------|---------------------|
| A. Map a usable code+data cache on Windows | **Yes** | Medium | Yes (today Create soft-fails) |
| B. RX↔RW(X) updates + icache flush | **Yes** | Low–medium | Yes after A |
| C. Contiguous vs dual-view layout | **Yes** (several designs) | Medium | Yes for correctness of offsets |
| D. **Compiler emits `%gs:` Thread access** | **Yes, but large** | **High** | **Yes — independent of A–C** |
| E. JIT helpers / entrypoints ABI (MS vs SysV, rSELF) | **Yes** | Medium–high | Yes once code runs |
| F. Product “defaults like Linux” without crashing | **Partial now** | — | Nterp/quick **ON**; JIT option true but cache absent |

**Conclusion:** Memory mapping is **solvable** with a deliberate Windows path. Enabling JIT end-to-end is **blocked harder by codegen TLS (GS)** than by `VirtualAlloc`. Treat as **two sequential workstreams**: (1) JitMemoryRegion on Win, (2) x86_64 backend Thread access via r15.

---

## 1. Current product baseline (measured 2026-07-19)

### 1.1 Defaults (Linux-like knobs)

| Knob | Product default | Opt-out |
|------|-----------------|---------|
| Quick invoke | **ON** | `ART_WIN64_QUICK_INVOKE=0` |
| Nterp (N-1 rSELF=r15, rREFS=rbp) | **ON** after `finished_starting_` | `ART_WIN64_NTERP=0` |
| `UseJitCompilation` | **true** (`runtime_options.def`) | `-Xusejit:false` / `-Xint` |

### 1.2 Wine imageless Hello (no `ART_WIN64_*` env)

```
nterp_supported=1
can_use_nterp=0   # during ClassLoader
finished_starting_=true → can_use_nterp=1
Failed to create JIT Code Cache: Failed to create read execute code cache:
  map(0x4a030000, 32MiB, PROT_RX, MAP_FIXED|…, -1, 0) failed: Invalid argument
  size=64MiB
Hello from dalvikvm!  exit 0
```

So: **nterp product path is green**; JIT Create **soft-fails**; runtime continues without `jit_`.

### 1.3 Capacities

From `JitCodeCache`:

- Initial: 64 KiB release / 8 KiB debug (min 2 pages)  
- Max: **64 MiB** (`kMaxCapacity`)  
- Region splits capacity 50/50 data vs code (`kCodeAndDataCapacityDivider = 2`)  
- Soft-fail log shows **64 MiB** total → 32 MiB data + 32 MiB exec at max map time (`Initialize` maps **max_capacity**, not only initial)

---

## 2. How Linux JIT memory works (contract)

### 2.1 Dual-view (preferred when `memfd_create` works)

- One memfd of size `capacity`  
- Views: RW non-exec code updater + RX exec; data R vs RW for zygote  
- `HasDualCodeMapping()==true` → `ScopedCodeCacheWrite` mostly no-ops protect (debug still toggles)  
- Commit writes to non-exec, flushes, exec view already RX  

**Win today:** `memfd_create` is non-functional (syscall stub / always fail) → dual path not taken.

### 2.2 Single-view (fallback when RWX allowed)

```
MapAnonymous(data+exec, RW, low_4gb=true)
RemapAtEnd(divider) → exec tail MAP_FIXED as RX
ScopedCodeCacheWrite: mprotect(exec, RWX) … write … mprotect(exec, RX)
```

Code info pointer: `OatQuickMethodHeader` stores **uint32** `code_info_offset_` such that:

```text
stack_map = code_pointer - code_info_offset_
```

Constraints:

1. `stack_map` must be **at a lower address** than `code_` (unsigned subtraction).  
2. Distance must fit in **32 bits**.  
3. Linux single-view places **data below, exec above** in one contiguous VA → natural.

`JitCodeCache::Create` comment also notes maps should stay within ~1 GB span so 32-bit offsets between code and data remain safe.

### 2.3 `RemapAtEnd` semantics (Unix)

`mmap(MAP_FIXED)` over the tail **replaces** the mapping without needing to free the whole reservation. Atomic vs races; yields a second `MemMap` object for the tail.

---

## 3. Why Windows fails today (memory)

### 3.1 Root cause of soft-fail

`MemMap::RemapAtEnd` → `TargetMMap(..., MAP_FIXED | MAP_ANON, ...)` →  
`mem_map_windows.cc` `VirtualAlloc(preferred, len, MEM_RESERVE|MEM_COMMIT, PAGE_EXECUTE_READ)`.

Problems:

1. Tail address is **already inside** an existing `MEM_RESERVE|MEM_COMMIT` region from the first `MapAnonymous(data+exec)`.  
2. Windows does **not** allow a nested `MEM_RESERVE` on a subrange still owned by the parent allocation.  
3. `VirtualFree(addr, 0, MEM_RELEASE)` only works from the **allocation base**, not from an interior divider.  
4. `MEM_DECOMMIT` can decommit the tail but does not create an independent mapping with separate protect lifetime the way Linux remap does — and current `TargetMMap` does not implement “decommit + re-commit tail” as RemapAtEnd.

Observed errno path: **Invalid argument** on the fixed RX map of 32 MiB at `0x4a030000`.

### 3.2 What already works on Win MemMap

| Primitive | Status |
|-----------|--------|
| Anonymous `VirtualAlloc` low-4GB scan (`VirtualQuery`) | Working (heap/LOS/linear alloc) |
| `VirtualProtect` via `MemMap::Protect` and `compat mprotect` | Working for ordinary pages |
| File `CreateFileMapping` + `MapViewOfFile` | Implemented for fd-backed maps |
| `TakeReservedMemory` | Exists (splits **logical** ownership of a reservation on Unix; Win unmap rules need care) |
| `memfd_create` | Fail → no dual-view |
| `RemapAtEnd` anonymous MAP_FIXED | **Broken** (this bug) |

### 3.3 Failed experiment (2026-07-19) — separate non-contiguous maps

**Idea:** Map `data` and `exec` as two independent low-4GB anonymous regions (skip RemapAtEnd).

**Result:**

- JIT Create **no longer soft-failed** (region appeared at `~0x4a03…`).  
- Hello **AV 0xc0000005** during ClassLoader setup (`rip` in low-4G JIT range, `fault_addr=0x18`).  
- `-Xusejit:false` on same binary → Hello **PASS**.  
- **Reverted** from tree; not a product path.

**Likely causes (ordered hypotheses, not yet proven):**

1. **JIT code uses `%gs:Thread`** (see §5) → first compiled method immediately faults or corrupts.  
2. Non-contiguous layout + **uint32 code→data offset** if `exec.Begin() < data.Begin()` or span wrong.  
3. `FlushCpuCaches` = `__builtin___clear_cache` may be weak/no-op for wine i-cache (less likely sole cause of null deref).  
4. `ScopedCodeCacheWrite` / mprotect on full exec map OK, but early compile quality / missing rSELF publish.

Hypothesis **(1)** is sufficient alone to explain AV even with perfect mapping.

---

## 4. Feasibility of memory designs

### Option J-1 — Single reservation, split commit (contiguous) — **RECOMMENDED for memory**

**Mechanism:**

1. `VirtualAlloc(low4g, capacity, MEM_RESERVE, PAGE_NOACCESS)`  
2. `VirtualAlloc(base, data_cap, MEM_COMMIT, PAGE_READWRITE)`  
3. `VirtualAlloc(base+data_cap, exec_cap, MEM_COMMIT, PAGE_EXECUTE_READ)`  
4. Represent as:
   - `data_pages_`: begin=base, size=data_cap (owns release of **entire** reservation), and  
   - `exec_pages_`: begin=base+data_cap, size=exec_cap, **`reuse_` or `already_unmapped_` so destructor does not `MEM_RELEASE` twice**

**Feasibility:** **High.** Matches Windows memory model; contiguous VA restores Linux offset assumptions; `ScopedCodeCacheWrite` → existing `mprotect`/`VirtualProtect` RX↔RWX.

**Risks / work:**

| Risk | Mitigation |
|------|------------|
| Double-free on destroy | Mark exec map `reuse_=true` or custom “subrange view” API |
| Low-4G fragmentation for 64 MiB | Reuse `VirtualQuery` scan from `mem_map_windows.cc` |
| Wine reserve quirks | Probe with tiny capacity first (2× page), then 64 MiB |
| `TakeReservedMemory` semantics on Win | Prefer explicit Win helper over overloading Unix remap |

**Effort:** ~1–3 days for Create green + unmap tests; not including codegen.

### Option J-2 — Pagefile section dual-view (Windows-native dual)

**Mechanism:**

1. `CreateFileMapping(INVALID_HANDLE_VALUE, PAGE_EXECUTE_READWRITE, capacity)`  
2. View RW (or RW code + R data) + view RX via `MapViewOfFile` / `MapViewOfFileEx` with low-4G hints  
3. Fill `non_exec_pages_` + `exec_pages_` → `HasDualCodeMapping()==true`

**Feasibility:** **Medium–high.** API exists; ART dual-view logic already written. Low-4G **two** views is harder; wine section protect matrix needs validation.

**Pros:** No permanent RWX; closer to Android security model.  
**Cons:** More moving parts; dual VA for same PA; offset between code exec view and data view still must satisfy uint32 header math (data often in same section at lower offset — OK if layout mirrors Linux).

**Effort:** ~3–7 days including wine matrix.

### Option J-3 — Always-RWX one map (bring-up only)

Map full capacity `PAGE_EXECUTE_READWRITE`, set `data_pages_` / `exec_pages_` as views with `reuse_`, never RemapAtEnd.

**Feasibility:** **High for Create**, **low as product**. Useful to isolate “does JIT code run at all?” after GS fix. Not end-state.

### Option J-4 — Soft-fail (current)

**Feasibility:** Already shipping. Nterp carries product. **Does not** meet “JIT like Linux.”

### Option J-5 — Separate non-contiguous maps (experiment)

**Feasibility for Create:** High.  
**Feasibility for correct JIT:** **Low until §5 solved**, and only if **exec VA > data VA** and delta ≤ 2³²−1.  
**Status:** Rejected for product until proven; kept as research note.

### Memory option scorecard

| Option | Create likely | Offset-safe | No RWX | Matches ART | Recommend |
|--------|---------------|-------------|--------|-------------|-----------|
| J-1 reserve/commit | High | High | No (toggles RWX) | High | **Primary** |
| J-2 section dual | Medium | High if laid out well | Yes | Highest | Secondary / hardening |
| J-3 always RWX | High | High if contiguous | No | Medium | Bring-up only |
| J-4 soft-fail | N/A | N/A | N/A | N/A | Interim product |
| J-5 separate | High | Conditional | No | Low | Research only |

---

## 5. Feasibility of *running* JIT code — GS / Thread TLS (critical)

### 5.1 Evidence

x86_64 optimizing compiler and JNI macro assembler **hardcode GS relative Thread TLS**:

- `vendor/art/compiler/optimizing/code_generator_x86_64.cc` — many `__ gs()->…` loads of entrypoints, card table, flags, exceptions  
- `vendor/art/compiler/utils/x86_64/jni_macro_assembler_x86_64.cc` — `GetCurrentThread` = `gs:Thread::SelfOffset`  
- Trampoline compiler: `gs()->jmp` to thread entrypoints  

Quick/nterp **runtime asm** on Win was ported to **rSELF=r15** + `THREAD_*` macros. **Compiler backend was not.**

Linux: `ARCH_SET_GS` → GS base = `Thread*`.  
Windows: GS = **TEB**, not ART Thread. JIT code that does `mov reg, gs:[offset]` reads TEB fields → garbage / null → **AV** (matches experiment `fault_addr=0x18` class of failures).

Callee-saves on x86_64 codegen include **R15** (`kCoreCalleeSaves[] = { RBX, RBP, R12, R13, R14, R15 }`). On Win nterp/quick, **r15 is rSELF** and must remain live across managed calls — same register pressure story as Linux mark-reg / nterp refs conflict, but inverted: Linux keeps Thread in GS and can use r15 as callee-save temp; Win needs r15 = Thread and must **not** treat it as a free callee-save for JIT.

### 5.2 What “feasible” means for codegen

| Approach | Feasible? | Notes |
|----------|-----------|-------|
| D-1 Emit `Thread*` from **r15** (base+offset) instead of `gs:offset` when `ART_TARGET_WINDOWS` / `_WIN32` | **Yes** | Mirrors quick asm macros; large mechanical patch across codegen + JNI macro assembler + trampolines |
| D-2 Set GS base to Thread\* on Win | **No** (locked reject in §16 tls doc) | TEB / SEH / wine; not viable |
| D-3 FS.base = Thread\* | **No** (rejected §16) | FS used by CRT/TEB on x64 Win in practice; earlier analysis rejected |
| D-4 Interpreter-only forever | Yes | Not product goal for Phase 5 |

**Effort estimate for D-1:** multi-day to multi-week depending on how many call sites; needs assembler helpers like `ThreadAddress(offset)` → `Address(r15, offset)` under Win, and **exclude R15 from allocatable callee-saves** on Win (or pin rSELF like ARM marks).

### 5.3 Interaction with memory work

Even perfect J-1 Create will **still AV** on first JIT-compiled method until D-1 lands.  
Order should be:

1. **Optional:** J-1 Create success (observable in log) while compile threshold maxed / JIT disabled for execution tests, **or**  
2. **Preferred parallel:** D-1 on a branch with J-3 RWX map for fastest “first compiled Hello”, then harden memory to J-1/J-2.

Separate-map AV is **not** proof that separate maps are wrong; it is weak evidence that **any** successful Create surfaces GS bugs immediately.

---

## 6. Secondary feasibility items

### 6.1 `FlushCpuCaches` on Win/x86_64

Uses `__builtin___clear_cache`. On x86 usually a compiler barrier; hardware coherent I/D. Wine: generally OK. Optional hardening: `FlushInstructionCache(GetCurrentProcess(), …)`.

**Feasibility:** High; low priority.

### 6.2 `ScopedCodeCacheWrite` → `mprotect`

Compat stub implements `VirtualProtect` including RWX. Wine allows RWX for anonymous allocations in practice (PE product already runs RX nterp code from `art.dll`).

**Feasibility:** High for J-1/J-3. J-2 avoids RWX.

### 6.3 Calling convention of JIT → runtime

Compiled code calls quick entrypoints via Thread* table (today via GS). After D-1, calls go through r15-relative entrypoints — same stubs as nterp/quick. MS vs SysV: managed stubs already SysV-bodied with MS prologues where needed; JIT should target **same** quick ABI as Linux x86_64 managed (SysV-like ART convention), not MS x64 for managed↔managed.

**Feasibility:** Medium; mostly already done for interpreter/quick; verify JIT call sites.

### 6.4 Boot / imageless

Imageless boot relies on nterp/switch heavily. JIT of boot classpath methods may stress ClassLinker + resolution. Keep `CanRuntimeUseNterp` boot gate; allow JIT only after Start (already true for nterp).

### 6.5 Zygote / dual zygote maps

**Out of scope** for desktop PE (no zygote). Hosted `ProtectZygoteMemory` stubs can stay no-ops.

---

## 7. Recommended plan (phased)

| Phase | Goal | Success metric | Depends |
|-------|------|----------------|---------|
| **P0** | Product defaults | nterp+quick ON; JIT option true; soft-fail OK | **Done** 2026-07-19 |
| **P1** | Design lock | This doc reviewed; choose J-1 (+ D-1) | **Done** 2026-07-19 |
| **P2a** | MemMap J-1 | Log: JIT code cache created; no VEH at Create | **Done** 2026-07-19 |
| **P2b** | Codegen D-1 | No `gs` Thread access in JIT for Win; R15 = rSELF | **Done** 2026-07-19 |
| **P3** | First compiled method | Hello prints with managed JIT; no AV | **Done** 2026-07-21 |
| **P4** | Matrix | CEnc, float, Math, Io, Net, GC under JIT | **Done** 2026-07-22 |
| **P5** | Harden | J-2 optional; drop RWX; host Win10 | P4 |

**Do not** claim “JIT enabled by default” as complete until **P3**.  
**Do** claim “JIT **option** default true; execution via nterp until cache+codegen land” (honest Linux-like config, partial runtime).

---

## 8. Work estimates (order-of-magnitude)

| Workstream | Size | Confidence |
|------------|------|------------|
| J-1 reserve/commit + MemMap views | S–M | High it unblocks Create |
| J-2 dual section | M | Medium |
| D-1 compiler GS→r15 | **L** | High it is required |
| P3 debug (ABI/edge) | M | Medium |
| Host validation | S | Medium (wine≠host) |

---

## 9. Risks & open questions

1. **R15 callee-save conflict:** Codegen lists R15 as callee-save; Win managed needs rSELF pinned. Must change register allocator / ABI for Win x86_64.  
2. **How many GS sites:** Dozens across optimizing + JNI macro + trampolines; need systematic `ThreadMemOperand` helper, not one-off ifdefs.  
3. **Wine low-4G 64 MiB reserve:** May need capacity clamp for wine only (e.g. max 16 MiB) if fragmentation hurts — product knob.  
4. **Is AOT/JIT compiler built into `art.dll`?** Yes (phase1 cmake includes jit compiler objects) — emit path is present; not a link gap.  
5. **Separate maps AV:** Re-test only **after** D-1; until then do not burn time on J-5.  
6. **uint32 offset direction:** Any layout must keep **data addresses below code addresses** (or change header encoding — out of scope).

---

## 10. Decision log

| When | Decision |
|------|----------|
| 2026-07-19 | Nterp + quick product default ON; JIT option remains true |
| 2026-07-19 | Soft-fail Create acceptable interim (J-4) |
| 2026-07-19 | Separate-map experiment **reverted**; AV not chased as memory-only bug |
| 2026-07-19 | **Feasibility:** memory **yes (J-1)**; end-to-end JIT **yes only with codegen D-1** |
| 2026-07-21 | P3 gate: JIT smoke test passes (24 compiles, Hello OK) |
| 2026-07-22 | P4 gate: full probe matrix passes (14 probes, 0 failures) |
| Pending | P5: J-2 pagefile section dual-view; drop RWX; host Win10 |

---

## 11. Code anchors

| Topic | Path |
|-------|------|
| Region init / RemapAtEnd | `vendor/art/runtime/jit/jit_memory_region.cc` |
| Create / capacities | `vendor/art/runtime/jit/jit_code_cache.{h,cc}` |
| RX↔RWX | `vendor/art/runtime/jit/jit_scoped_code_cache_write.h` |
| Win mmap | `vendor/art/libartbase/base/mem_map_windows.cc` |
| mprotect stub | `compat/src/win64_posix_stubs.c` |
| CreateJit soft-fail | `vendor/art/runtime/runtime.cc` |
| UseJit default | `vendor/art/runtime/runtime_options.def` |
| GS codegen | `vendor/art/compiler/optimizing/code_generator_x86_64.cc` |
| GS JNI macro | `vendor/art/compiler/utils/x86_64/jni_macro_assembler_x86_64.cc` |
| rSELF lock | `win32_tls_jit_entrypoints.md` §15–§17.8 |
| Header offsets | `vendor/art/runtime/oat/oat_quick_method_header.h` |

---

## 12. Next actions (when implementation resumes)

1. Implement **J-1** in `mem_map_windows` / `JitMemoryRegion::Initialize` with tests for destroy/protect.  
2. Add Win **Thread operand** helper in x86_64 assembler; gate GS vs r15.  
3. Pin **R15** as non-allocatable on Win managed ABI.  
4. Smoke: Create success log + `-Xusejit:true -Xjitthreshold:0` Hello.  
5. Only then expand matrix and consider J-2.

Until then: keep **J-4 soft-fail**, ship **nterp** as the default execution engine (already green).

## 13. Implementation status (2026-07-19 J-1 + D-1)

### J-1 — landed

| Piece | Change |
|-------|--------|
| `MemMap::RemapAtEnd` (`mem_map.cc`) | Win anonymous tail: `VirtualProtect` in place + `reuse_` view (no MAP_FIXED `VirtualAlloc`) |
| Exec initial prot | **RWX** when `PROT_EXEC` (mspace writes into exec half on single-view; pure RX AV'd) |
| Evidence | `Win64 JitCodeCache::Create OK initial=64KB max=64MB` under wine |

### D-1 — partially landed

| Piece | Change |
|-------|--------|
| `Address::ThreadOffsetAddr` | Win: `Address(R15, offset)`; Linux: Absolute+GS |
| `X86_64Assembler::gs()` | No-op on Win (no `0x65`); still emits GS on Linux |
| Thread Absolute(true) sites | codegen / JNI macro / intrinsics / trampoline → `ThreadOffsetAddr` |
| R15 | Removed from Win callee-saves; blocked in register allocator |

### Residual (narrow) + product compile default

Background JIT **compile is ON by default** after J-1/D-1, with one residual exclude:

**Bug:** compiling **both** `StringBuilder.toString` and `StringFactory.newStringFromBytes` breaks Hello's second `println` (`NPE data == null`). Each alone is fine; other hot methods (String.equals/length/indexOf, StringBuilder.append, Math, Unsafe, …) are fine together.

| Mode | Create | Compile | Hello |
|------|--------|---------|-------|
| Default | **OK** | ON, **skip StringFactory** | **PASS** (ncomp≈19) |
| `ART_WIN64_JIT=0` | OK | off | PASS (nterp only) |
| `ART_WIN64_JIT_ALLOW_STRINGFACTORY=1` | OK | + StringFactory | **FAIL** residual pair |
| `-Xusejit:false` | no | no | PASS |

Debug knobs: `ART_WIN64_JIT_FILTER` / `ART_WIN64_JIT_EXCLUDE` (comma OR lists).

Next: fix StringFactory↔toString interaction (likely optimized/baseline string data path / arraycopy `data==null`), then drop exclude.

### Residual analysis notes (2026-07-19)

`data == null` is thrown by `StringFactory_newStringFromBytes` when the `byte[]`
argument is null (`java_lang_StringFactory.cc`). Isolation:

- JIT **only** `StringFactory.newStringFromBytes` → Hello PASS
- JIT **only** `StringBuilder.toString` → Hello PASS  
- JIT **both** → FAIL after first `println` (second string path)
- Other hot methods together without that pair → PASS

Tried / rejected for now:

1. Disable `StringNewStringFromBytes` intrinsic on Win — pair still fails (compiled FastNative path still broken).
2. Mark StringFactory natives `sysv_abi` directly — breaks JNI signature metafunctions.
3. SysV thin wrappers registered for StringFactory — early boot AV under wine (regressed); reverted.

Hypothesis still open: MS x64 vs SysV mismatch on **compiled FastNative** stubs for multi-arg natives, or `toString` returning a value that the factory call site mis-marshals when both are JIT. Product keeps **default compile ON, exclude StringFactory** until a safe ABI-wide fix lands.

### Win FastNative MS ABI (2026-07-19)

Compiled FastNative stubs previously used **SysV** argument registers (`RDI/RSI/...`)
while Win C++ natives use **MS x64** (`RCX/RDX/R8/R9` + 32B shadow). Generic JNI already
used MS packing; compiled stubs did not.

**Landed:**

- `vendor/art/runtime/arch/x86_64/jni_frame_x86_64.h` — Win max 4 int/float slots + 32B shadow
- `vendor/art/compiler/jni/quick/x86_64/calling_convention_x86_64.cc` — MS register order for JNI params

**Still residual:** JIT-compiled FastNative stubs still pass garbage multi-arg
values into natives (observed `data==null high=18 offset=0x47d2f2e8...`) even with
MS register layout (`OutFrameSize=48`, 4 regs + 2 stack for `LLIII`).

**Product gate:** do not JIT **native** methods on Win (`CompileMethodInternal`
returns false unless `ART_WIN64_JIT_NATIVE=1`). Managed JIT (including
`StringBuilder.toString`) stays on; natives use generic JNI.

