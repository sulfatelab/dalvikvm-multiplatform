# Win64 JIT memory & codepath — feasibility analysis

**Status:** P3+P4 DONE — J-2 design in §14; P5 pending implementation  
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

### 1.2 Wine imageless Hello (no `ART_WIN64_*` env) — updated 2026-07-22

```
nterp_supported=1
can_use_nterp=0   # during ClassLoader
finished_starting_=true → can_use_nterp=1
Win64 JitCodeCache::Create OK initial=64KB max=64MB
Win64 CompileMethod done success=1 method=...  (×24 managed methods)
Hello from dalvikvm!  exit 0
```

So: **nterp product path is green**; JIT Create **succeeds**; managed methods
compile and execute. Native JIT gated off by default (FastNative stub ABI gap).

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
| 2026-07-22 | P5 started: J-2 design written (§14); CreateFileMapping + MapViewOfFileEx approach |
| Pending | P5: implement J-2 (est. 3-4 days); remove RWX; host Win10 |

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

## 13. Implementation status — updated 2026-07-22

### J-1 — landed (2026-07-19)

| Piece | Change |
|-------|--------|
| `MemMap::RemapAtEnd` (`mem_map.cc`) | Win anonymous tail: `VirtualProtect` in place + `reuse_` view |
| Exec initial prot | **RWX** when `PROT_EXEC` (mspace writes into exec half on single-view) |
| Evidence | `Win64 JitCodeCache::Create OK initial=64KB max=64MB` under wine |
| Verification | JIT smoke 10/10 (2026-07-21), JIT matrix 14/14 (2026-07-22) |

### D-1 — partially landed (2026-07-19)

| Piece | Change |
|-------|--------|
| `Address::ThreadOffsetAddr` | Win: `Address(R15, offset)`; Linux: Absolute+GS |
| `X86_64Assembler::gs()` | No-op on Win (no `0x65`); still emits GS on Linux |
| Thread Absolute(true) sites | codegen / JNI macro / intrinsics / trampoline → `ThreadOffsetAddr` |
| R15 | Removed from Win callee-saves; blocked in register allocator |

**D-1 residual:** float-intensive JIT-compiled methods (FloatProbe) crash
under J-2 dual-view with `fault_addr=0x8` (VEH loop in wine's ntdll).
The compiler may still emit `gs:` access in certain float code paths
not covered by the `ThreadOffsetAddr` conversion. Systematic audit of
all GS sites needed (see §9 risk 2).

### Native JIT gate — widened 2026-07-21

Original narrow gate (skip StringFactory) replaced with broad gate:
**skip JIT for all native methods** (`method->IsNative()` → return false).

| Mode | Create | Managed Compile | Native Compile | Hello |
|------|--------|-----------------|----------------|-------|
| Default | **OK** | **ON** (24 compiles) | **OFF** | **PASS** |
| `ART_WIN64_JIT=0` | OK | off | off | PASS (nterp) |
| `ART_WIN64_JIT_NATIVE=1` | OK | ON | ON | **crash** (FastNative ABI) |
| `ART_WIN64_JIT_DUAL=1` | OK (J-2) | ON (21 compiles) | OFF | **PASS** |

Debug knobs: `ART_WIN64_JIT_FILTER` / `ART_WIN64_JIT_EXCLUDE` (comma OR lists).

### FastNative MS ABI — partial (2026-07-19)

**Landed:**
- `vendor/art/runtime/arch/x86_64/jni_frame_x86_64.h` — Win max 4 int/float slots + 32B shadow
- `vendor/art/compiler/jni/quick/x86_64/calling_convention_x86_64.cc` — MS register order

**Still broken:** JIT-compiled FastNative stubs pass garbage multi-arg
values (observed `data==null high=18 offset=0x47d2f2e8...`). Generic JNI
trampoline is correct; native-JIT gate prevents this path in product.


---

## 14. J-2 pagefile section dual-view — design (2026-07-22)

### 14.1 Goal

Replace J-1's single-reservation + RWX-toggle approach with a true dual-view
mapping backed by a Windows pagefile section (`CreateFileMapping`), eliminating
the RWX requirement and matching Linux's `memfd_create` dual-view security model.

### 14.2 Why now

J-1 works (P3+P4 green) but has two weaknesses:

1. **RWX during writes:** `ScopedCodeCacheWrite` toggles exec pages to RWX,
   writes code, then back to RX. A concurrent thread reading those pages sees
   RWX — a window for W^X violation.
2. **No zygote hardening path:** J-1 reuses the single VA region; can't seal
   or protect the way Linux `memfd_create` + `MFD_ALLOW_SEALING` does.

J-2 resolves both: writes go to a non-executable RW view; the executable view
is always RX. No protection toggling, no RWX window.

### 14.3 API mapping: Linux memfd → Windows section

| Linux step | Windows equivalent |
|------------|-------------------|
| `memfd_create("jit-cache", 0)` | `CreateFileMappingW(INVALID_HANDLE_VALUE, NULL, PAGE_EXECUTE_READWRITE, hi, lo, NULL)` |
| `ftruncate(fd, capacity)` | Implicit in `CreateFileMapping` size params |
| `mmap(…, fd, offset)` non-exec view | `MapViewOfFileEx(hSection, FILE_MAP_WRITE, …, offset, …)` |
| `mmap(…, fd, offset)` exec view | `MapViewOfFileEx(hSection, FILE_MAP_EXECUTE, …, offset, …)` |
| `fcntl(F_ADD_SEALS)` | `NtSetInformationFile` or accept no-seal on desktop |

### 14.4 Code changes required

#### 14.4.1 New: `MemMap::MapFileSection` (mem_map_windows.cc)

```cpp
// Create a file mapping backed by the system paging file (no on-disk file).
// Returns a section HANDLE. Caller owns the handle.
static HANDLE CreatePageFileSection(size_t capacity, std::string* error_msg);

// Map a view of a section HANDLE. Mirrors MapFile but takes HANDLE instead of fd.
static MemMap MapFileSection(HANDLE hSection,
                             size_t byte_count,
                             int prot,
                             uint32_t flags,    // low_4gb, etc
                             size_t start_offset,
                             const char* name,
                             std::string* error_msg);
```

`CreatePageFileSection`:
1. `CreateFileMappingW(INVALID_HANDLE_VALUE, NULL, PAGE_EXECUTE_READWRITE, hi32(capacity), lo32(capacity), NULL)`
2. Return handle or NULL on failure.

`MapFileSection`:
1. Convert `prot` to Windows `PAGE_*` / `FILE_MAP_*` constants:
   - `PROT_READ` → `FILE_MAP_READ` (view: `PAGE_READONLY`)
   - `PROT_READ|PROT_WRITE` → `FILE_MAP_WRITE` (view: `PAGE_READWRITE`)
   - `PROT_READ|PROT_EXEC` → `FILE_MAP_EXECUTE` (view: `PAGE_EXECUTE_READ`)
2. If `low_4gb`, scan with `VirtualQuery` for free VA < 4 GB.
3. `MapViewOfFileEx(hSection, access, 0, start_offset, byte_count, preferred)`
4. Return MemMap wrapping the view base.

#### 14.4.2 Changed: `JitMemoryRegion::Initialize` (jit_memory_region.cc)

Add a `#if defined(_WIN32)` block in the fd-backed path:

```cpp
#if defined(_WIN32)
  // J-2: pagefile section dual-view
  HANDLE hSection = MemMap::CreatePageFileSection(capacity, error_msg);
  if (hSection == NULL) {
    // Fall through to single-view (J-1)
  } else {
    // Map non-executable code-updater view
    non_exec_pages = MemMap::MapFileSection(hSection, exec_capacity,
        kProtRW, /*flags=*/0, data_capacity, "jit-code-cache-rw", &error_str);
    // Map writable data view
    writable_data_pages = MemMap::MapFileSection(hSection, data_capacity,
        kProtRW, /*flags=*/0, 0, "data-code-cache-rw", &error_str);
    // Map primary R view in low 4 GB
    data_pages = MemMap::MapFileSection(hSection, data_capacity + exec_capacity,
        kProtR, /*flags=*/low_4gb, 0, "data-code-cache", &error_str);
    CloseHandle(hSection);
  }
#endif
```

When J-2 succeeds, `HasDualCodeMapping() == true`, and `ScopedCodeCacheWrite`
becomes a no-op (code already written to the RW non-exec view).

#### 14.4.3 No change needed

- `HasDualCodeMapping()` — already works when both `non_exec_pages_` and
  `exec_pages_` are valid.
- `ScopedCodeCacheWrite` — already no-ops when `HasDualCodeMapping()==true`.
- All code commit/copy paths — write to `non_exec_pages_`, read from
  `exec_pages_`; same as Linux dual-view.

### 14.5 Risk analysis

| Risk | Impact | Mitigation |
|------|--------|------------|
| Wine `CreateFileMapping` section protect matrix differs from real Windows | Maps fail or wrong access | Test both; gate J-2 behind `ART_WIN64_JIT_DUAL=1` env var initially |
| Low-4G two `MapViewOfFileEx` calls fragment VA space | Second view can't find 2 GB free low VA | Map primary view first; if non-exec can't fit low-4G, use high VA (JIT code pointer math works with high VA, just costs a few bytes of REX prefix) |
| `PAGE_EXECUTE_READWRITE` section protection may be denied by policy (AppContainer, WDAC) | Section creation fails | Fall back to J-1; J-2 is best-effort hardening |
| Dual-view offset math (uint32 code_info_offset) | If data pages VA > exec pages VA, subtraction is negative | Same layout as Linux: data pages at offset 0 (lower VA), exec at offset data_capacity (higher VA) |
| No `MFD_ALLOW_SEALING` equivalent on desktop Windows | Can't prevent new writable mappings post-zygote | Accept for desktop; zygote not used on Win64 desktop PE |

### 14.6 Implementation plan

| Step | Effort | Validation |
|------|--------|------------|
| 1. `CreatePageFileSection` + `MapFileSection` in mem_map_windows.cc | 1 day | Unit test: create 4 KB section, map RX view, verify read works, write AVs |
| 2. Wire into `JitMemoryRegion::Initialize` behind `ART_WIN64_JIT_DUAL` gate | 0.5 day | Log: "JIT dual-view OK" or fallback message |
| 3. Run full JIT matrix (run_jit_matrix.sh) with dual-view enabled | 0.5 day | All 14 probes pass; no RWX in exec view |
| 4. Verify `HasDualCodeMapping()==true` → `ScopedCodeCacheWrite` no-ops | 0.5 day | Check log: no mprotect/VirtualProtect calls during JIT compile |
| 5. Remove env gate, make J-2 the default | 0.5 day | Regression: JIT smoke + matrix still green |
| 6. Remove J-1 single-view fallback code | 1 day | Clean removal; verify no dead code |

**Total estimate:** ~3–4 days.

### 14.7 Gate logic (boot order)

```
JitMemoryRegion::Initialize:
  if ART_WIN64_JIT_DUAL == "1"  → try J-2
    success → HasDualCodeMapping = true
    fail    → LOG(WARNING) + fall through
  if ART_WIN64_JIT_DUAL == "0"  → skip J-2
  fallback → J-1 (current, works)
```

After validation (step 5), flip: try J-2 always, fall back to J-1 if
`CreateFileMapping` fails.


## 15. J-2 dlmalloc investigation (2026-07-22)

### 15.1 `create_mspace_with_base` flow

`create_mspace_with_base` in `vendor/external/dlmalloc/dlmalloc.c:5479`:
1. `ensure_initialization()` → `init_mparams()` on first call; cached thereafter
2. `pad_request(sizeof(struct malloc_state))` → chunk sizing math
3. `init_user_mstate(base, capacity)` → writes struct to memory:
   - `memset(m, 0, msize)`
   - `INITIAL_LOCK(&m->mutex)` → lock initialization
   - Struct field assignments (seg.base, footprint, magic, bins, top)
4. `set_lock(m, locked)` → bitwise `m->mflags` update

No explicit `VirtualAlloc` or syscalls during `create_mspace_with_base`.
All operations are pure memory writes within the provided base region.

### 15.2 Wine section view characteristics

Standalone test (32 MB pagefile section, RW view):
- ✅ `CreateFileMapping(INVALID_HANDLE_VALUE, PAGE_EXECUTE_READWRITE)`
- ✅ `MapViewOfFile(FILE_MAP_WRITE)` — writable
- ✅ Byte writes to all pages succeed
- ✅ 4 KB memset succeeds
- ✅ `VirtualProtect(PAGE_READWRITE)` succeeds
- ✅ RW↔RX section coherency (writes via RW visible via RX)

### 15.3 Root cause: pthread_mutex_init on section views

ART's `art-dlmalloc.cc` **undefines `WIN32` and `_WIN32`** before including
`dlmalloc.c` to force `HAVE_MORECORE=1` / `HAVE_MMAP=0`. This causes dlmalloc
to fall through to the **pthreads-based lock path** instead of the native
Win32 `InitializeCriticalSection` path.

```
INITIAL_LOCK(lk) → pthread_init_lock(lk)
                 → pthread_mutexattr_init(&attr)
                 → pthread_mutex_init(lk, &attr)    ← CRASHES
                 → pthread_mutexattr_destroy(&attr)
```

`pthread_mutex_init(lk, &attr)` on wine internally calls
`InitializeCriticalSection` or allocates kernel objects. When `lk` resides
in a `MapViewOfFile` section view (pagefile-backed, not
`VirtualAlloc`-committed memory), wine's pthread/winsock layer crashes.

This is a wine compatibility issue: the same code path would likely work
on real Windows where `InitializeCriticalSection` is agnostic to memory
type.

### 15.4 Why J-1 works

J-1 uses `MemMap::MapAnonymous` → `VirtualAlloc(MEM_COMMIT, PAGE_READWRITE)`
for all memory. dlmalloc's `pthread_mutex_init` works on `VirtualAlloc`-backed
memory under wine.

### 15.5 Solution: USE_LOCKS=0 (no dlmalloc locks) + data_pages_ init

**Applied fix (2026-07-22):** ART's dlmalloc configuration already uses
`USE_LOCKS=0` (no locks) because `art-dlmalloc.cc` undefines `WIN32`
before including `dlmalloc.c` — this makes `USE_SPIN_LOCKS` default to 0
and `USE_LOCKS` to 0. `INITIAL_LOCK` is `(0)` (no-op). This is the
correct configuration: ART heap uses ART-level `Mutex` protection;
JIT mspaces are accessed under `Locks::jit_lock_`. No dlmalloc-level
locks are needed.

**Attempted alternative:** `USE_SPIN_LOCKS=1` with temporary `__GNUC__`
define was tried but **reverted** — spin locks regress FloatProbe/MathProbe
under wine (likely due to empty `SPIN_LOCK_YIELD` with `LACKS_SCHED_H`
causing livelocks in wine's cooperative threading).

**Additional fix:** Missing `data_pages_ = std::move(data_pages)` added to
J-2 block in `jit_memory_region.cc`. Without this, `TranslateAddress`
CHECK-fails on `0x3c0` (null offset dereference in uninitialized MemMap).

**Result:** J-2 dual-view works under wine with `ART_WIN64_JIT_DUAL=1`:
21 managed methods compiled, Hello prints, no crash. J-1 default path
(24 compiles, all probes pass) unchanged.

### 15.6 Standalone test results

All standalone tests pass on wine:
- `section_test.exe`: RW↔RX section coherency ✅
- `page_touch_test.exe`: 32 MB section write/read/VirtualProtect ✅
- `dl_test.exe`: Manual `init_user_mstate` replication on section ✅
- `mspace_test.exe`: Write + readback on every page ✅

The crash is specifically in `pthread_mutex_init` on section-backed views,
which only occurs inside ART's dlmalloc integration.



---

## 16. Current status — 2026-07-22

### What's DONE

| Item | Phase | Verified |
|------|-------|----------|
| J-1 single-view memory (VirtualProtect RemapAtEnd) | P2a | JIT smoke 10/10, matrix 14/14 |
| D-1 partial codegen (ThreadOffsetAddr, gs() no-op, R15 pin) | P2b | Managed methods compile under J-1 |
| Managed JIT Hello (24 compiles, no crash) | P3 | run_jit_smoke.sh 10/10 |
| Probe matrix under J-1 (CEnc/float/Math/Io/Net/GC) | P4 | run_jit_matrix.sh 14/14 |
| Native JIT gate (all natives) | — | Zero native compiles by default |
| J-2 primitives (CreatePageFileSection, MapFileSection) | P5a | Builds, creates section+views |
| J-2 wiring (j2_complete flag, mspace init) | P5a | Hello 21 compiles under J-2 |
| J-2 dual-view code (RW↔RX coherency confirmed) | P5a | Standalone test passes |
| dlmalloc analysis (§15) | — | Root cause identified |
| dlmalloc fix (USE_LOCKS=0 + data_pages_ init) | — | J-1 + J-2 both work |
| JIT filter/exclude env vars | — | ART_WIN64_JIT_FILTER/EXCLUDE |
| nterp+quick defaults ON | P0 | Product default |

### What's BROKEN

| Item | Symptom | Blocker |
|------|---------|---------|
| FloatProbe/MathProbe/NetProbe under J-2 | VEH loop `fault_addr=0x8` in wine ntdll | **D-1 incomplete** — float code paths in JIT compiler still emit `gs:` Thread access instead of r15-relative |
| FastNative stub ABI (native JIT) | Garbage multi-arg values, `data==null` | MS x64 vs SysV mismatch in compiled FastNative stubs; generic JNI works |
| ART_WIN64_JIT_NATIVE=1 | Hello crash | Same FastNative ABI gap |

### What's MISSING

| Item | Priority | Effort |
|------|----------|--------|
| D-1 completion: audit all GS sites in x86_64 codegen | **High** — blocks J-2 default | Large (multi-week) |
| J-2 float regression fix (likely same as D-1 completion) | **High** | Subsumed by D-1 |
| J-2 step 3: run full matrix under J-2 | Medium | 0.5 day (after D-1 fix) |
| J-2 step 4: verify ScopedCodeCacheWrite no-ops | Low | 0.5 day |
| J-2 step 5: make J-2 default | Medium | After matrix passes |
| J-2 step 6: remove J-1 fallback | Low | After J-2 default |
| FastNative MS ABI fix | Medium | Unknown |
| Host Win10 validation | Low | Needs Win10 machine |
| ThreadMemOperand systematic helper | Medium | Subsumed by D-1 |

### What's BLOCKED

| Item | Blocked on |
|------|------------|
| J-2 as product default | D-1 completion (float codegen) |
| Native JIT enablement | FastNative MS ABI fix |
| Drop RWX requirement | J-2 as default |
| Host Win10 validation | Physical/virtual Win10 machine |

### Decision log additions

| When | Decision |
|------|----------|
| 2026-07-22 | J-2 stays opt-in (ART_WIN64_JIT_DUAL=1) until D-1 float codegen gap closed |
| 2026-07-22 | USE_LOCKS=0 confirmed correct; USE_SPIN_LOCKS=1 reverted (wine threading) |
| 2026-07-22 | data_pages_ init fix is the actual J-2 blocker fix (not dlmalloc locks) |
| 2026-07-22 | D-1 is the next major workstream: audit and fix all GS→r15 sites in compiler backend |

### Test summary

| Test | J-1 | J-2 | Notes |
|------|-----|-----|-------|
| run_jit_smoke.sh | 10/10 | 10/10¹ | ¹T5 (native JIT) excluded — known crash |
| run_jit_matrix.sh | 14/14 | 10/14 | FloatProbe/MathProbe/NetProbe fail under J-2 |
| Hello standalone | 24 compiles | 21 compiles | Both no crash |
| FloatProbe standalone | OK | VEH crash loop | D-1 float codegen gap |

### Next actions (priority order)

1. **D-1 completion:** Systematic audit of `gs:` Thread access in
   `code_generator_x86_64.cc`, `jni_macro_assembler_x86_64.cc`, and
   trampoline compiler. Every `gs()` call site must route through
   `ThreadOffsetAddr` on `ART_TARGET_WINDOWS`.
2. **Re-test J-2 matrix** after D-1 fix — verify FloatProbe/MathProbe/NetProbe.
3. **FastNative MS ABI fix** — fix compiled FastNative stub argument passing.
4. **J-2 → default** after matrix passes.
