# Windows x64 JIT memory and codepath — current design and status

**Status:** W-025 is closed. The pagefile-backed dual mapping is the only
Windows JIT memory path. JIT-5 removed the J-1 diagnostic opt-out and
single-view fallback, then passed post-removal Wine, Linux, and native Windows
regressions. Section construction now fails closed instead of downgrading W^X.
**Updated:** 2026-07-30
**Native gate:** Windows Server 2025 Datacenter Evaluation x64 build 26100;
the former Windows 10 lab host is unavailable for future gates. See
[native Windows gate policy](win32_host_gate_policy.md).
**Product API baseline:** Windows 10 version 1803 or later (NTDDI_WIN10_RS4)
**Related:** [win32_tls_jit_entrypoints.md](win32_tls_jit_entrypoints.md),
[win32_heap_memory.md](win32_heap_memory.md),
[win32_faults_and_stacks.md](win32_faults_and_stacks.md),
[win32_open_items.md](win32_open_items.md), Phase 5 JIT

## 0. Executive decision

The Windows x64 port shall keep ART's observable memory layout and shared JIT logic as
close to Linux as practical. Windows-specific allocation belongs in one small,
contained mapping helper rather than in the allocator, compiler, metadata
format, or code-cache growth logic.

The selected end state is:

1. Create one unnamed pagefile-backed section with
   `CreateFileMapping(INVALID_HANDLE_VALUE, PAGE_EXECUTE_READWRITE)`.
2. Map that section twice: one complete primary view below 4 GiB and one
   complete writable, non-executable alias at any address.
3. Give the primary view final `[data R][code RX]` protection and expose both
   complete views as ART's existing four logical `MemMap` ranges.
4. Keep the Windows-specific work in the mapping helpers, then use the common
   mspace, growth, translation, commit, collection, and cache-flush code.
5. Check every x86_64 JIT-root disp32 and CodeInfo uint32 encoding before
   patching or committing code. Reject an unrepresentable compilation without
   changing the encoded format.
6. Expose no Windows runtime opt-out to the executable single-view path.
   `ART_WINDOWS_X64_JIT_DUAL` is retired and ignored because the runtime no
   longer reads it.
7. If section creation or any view construction step fails, return the error
   and leave the JIT cache disabled. Never fall back to an RX/RWX-toggle
   mapping on Windows. The generic single-view fallback remains available to
   non-Windows platforms whose existing contract permits it.
8. Keep CET user shadow stacks outside W-025. Current Win32 ART does not
   support Hardware-enforced Stack Protection because its shared managed
   exception/deoptimization long jump does not maintain CET's protected return
   stack. All defined incompatible HSP/context-validation fields must be
   disabled under W-010's startup contract; `CetDynamicApisOutOfProcOnly` and
   reserved fields do not imply HSP. The accepted W-025 JIT-2 CFG gate and
   negative unsupported-policy rejection remain separate from CET/HSP support.
9. Treat executable-memory capability as an explicit ART product prerequisite.
   `ProhibitDynamicCode`/ACG is not a supported operating mode. The accepted
   rejection probe proves fail-closed behavior only; it does not create a
   product obligation to run JIT or future OAT under that policy, and ART must
   not use `AllowThreadOptOut` or another mitigation bypass.

The selected design creates no filesystem file. A Windows pagefile-backed
section can be paged by the operating system, just as anonymous Linux memory can
be swapped, but it has no pathname and no delete-on-close file lifecycle.

This replaces the temporary-file `memfd` compatibility plan. That plan reduced
the visible JIT branch but added filesystem semantics, a full-view placeholder
unmap/remap transaction, rollback requirements, and more `MemMap` ownership
risk. A pagefile section reproduces the required memory topology with fewer
failure states.

This supersedes the earlier recommendation to move stack maps into the code
arena. Moving stack maps alone cannot fix the observed J-2 crash because JIT
root-table references have a stricter signed 32-bit displacement requirement.

## 1. Current product baseline

Measured on agent01 under Wine:

| Item | Current state |
|------|---------------|
| Quick invoke | ON by default |
| Nterp | ON after runtime startup; rSELF=r15 and rREFS=rbp |
| Managed and native JIT | ON by default with the corrected section dual view |
| Default Hello | About 28–30 successful compilation records after native-JIT cleanup; PASS |
| Default JIT smoke | 14/14, including default-silent diagnostics and a retired-key negative test |
| Default probe matrix | 14/14 |
| Relative metadata encoding | Checked signed-int32 JIT-root and uint32 CodeInfo construction; deterministic boundary/overflow tests pass |
| Native JIT | Common ART default policy; direct CriticalNative and 7/7 mixed/high-FP normal/FastNative matrices pass through binding, method-tracing, and JVMTI forced-interpreter transitions; Math native surfaces and native Windows acceptance pass |
| Windows J-1 fallback | Removed in ART `389158d46f`; the retired key is ignored and J-2 remains active |
| Code cache | 64 KiB initial release capacity; 64 MiB maximum |

The 64 MiB cache is split equally into data and code. The maximum supported
cache remains at most 1 GiB, matching ART's relative-address assumptions.

## 2. Linux JIT memory contract

### 2.1 Normal dual-view path

Linux ART creates one memfd and maps its physical storage through several
virtual views:

```text
primary view:       [ data R  ][ code RX ]
writable aliases:   [ data RW ][ code RW, non-executable ]
```

Important properties:

- The primary data and executable code ranges are contiguous.
- Data addresses are below code addresses.
- Code is written through `non_exec_pages_`.
- Code executes through `exec_pages_`.
- The executable view never needs to become writable.
- `HasDualCodeMapping()` makes `ScopedCodeCacheWrite` avoid RWX protection
  toggles in release builds.

### 2.2 How ART obtains contiguous low-4-GiB memory on Linux

ART does not rely blindly on x86-64 `MAP_32BIT`. On LP64 platforms using
`USE_ART_LOW_4G_ALLOCATOR`, `MemMap::MapInternalArtLow4GBAllocator`:

1. starts from a low-address cursor; Android/Bionic randomizes the initial
   position, while the non-Bionic host path starts at 64 KiB;
2. holds the `MemMap` lock and uses `gMaps` to skip ranges already owned by ART;
3. tries one complete mapping at a candidate address without `MAP_FIXED`;
4. rejects and unmaps any result whose end is at or above 4 GiB;
5. probes pages when needed to detect mappings not represented in `gMaps`;
6. advances past occupied ranges, wraps once to 64 KiB, and finally fails with
   `ENOMEM` if no complete gap exists.

The important contract is one atomic, contiguous primary mapping wholly below
4 GiB. `MAP_32BIT` alone is not an equivalent algorithm: on Linux x86-64 it is
limited to the first 2 GiB and is only an address-placement hint outside fixed
mappings.

For the JIT, only the complete primary `[data][code]` view needs this constraint.
The writable aliases can be above 4 GiB because generated code and CodeInfo
metadata refer to the primary addresses, not the update aliases.

### 2.3 Non-Windows single-view fallback

When shared dual mapping is unavailable and RWX memory is permitted, ART maps
one anonymous data+code reservation and splits it:

```text
[ data RW ][ code RX ]
                  ↕
       RX -> RWX -> RX during updates
```

This remains common ART behavior for non-Windows platforms when shared dual
mapping is unavailable and their executable-memory policy permits it. JIT-5
places this branch behind the non-Windows platform arm. Windows never enters
it and never creates the RWX update window.

## 3. Address-layout invariants

The dual-view layout is required for correctness, not only security.

### 3.1 JIT root-table references: signed 32-bit

The x86_64 optimizing compiler patches JIT string, class, and MethodType roots
as RIP-relative loads:

```cpp
int32_t displacement = address_of_root - address_after_instruction;
```

The displacement must fit signed 32 bits, approximately ±2 GiB. The current
implementation uses `dchecked_integral_cast<int32_t>`; release-style builds can
truncate an invalid value instead of stopping.

### 3.2 CodeInfo pointer: unsigned 32-bit

`OatQuickMethodHeader` stores:

```text
stack_map = code_pointer - code_info_offset_
```

`code_info_offset_` is uint32. Therefore:

- the stack map must be below the code pointer;
- the distance must be no more than `UINT32_MAX`.

### 3.3 Layout consequence

Keeping `[data][code]` in one contiguous primary view of at most 1 GiB satisfies
both constraints:

- every root-table reference fits signed int32;
- every CodeInfo offset fits uint32 and has the correct direction.

Arbitrary high-address executable views paired with low-address data views do
not satisfy either contract.

## 4. Historical separated-J-2 FloatProbe diagnosis

### 4.1 Recorded failure

With J-2 and `-Xjitthreshold:0`:

```text
exception  = 0xc0000005
RIP        = 0x7abe53ab03e0
fault_addr = 0x7abe480303c0
```

The fault is approximately 195 MiB below the instruction while the real root
table is in the low-address data mapping.

### 4.2 Immediate cause: truncated JIT-root displacement

The addresses satisfy the x86_64 RIP-patch failure exactly:

```text
code              = 0x7abe53ab03e0
intended root     = 0x0000480303c0
true displacement= -0x7abe0ba80020
low signed int32  = -0x0ba80020
code + int32      = 0x7abe480303c0  <- recorded fault_addr
```

The immediate crash is therefore a JIT root-table load whose true displacement
was truncated to 32 bits. It is not float-specific code generation and it is
not a remaining D-1 GS/TLS defect.

### 4.3 Second defect: CodeInfo overflow

The same separated layout also makes:

```text
high code pointer - low stack-map pointer
```

far larger than uint32. Even after fixing the generated root load, runtime stack
walking, exceptions, deoptimization, or GC metadata decoding would eventually
recover an invalid CodeInfo pointer.

Both defects must be fixed together by restoring the expected layout or by
changing both encodings. Restoring the layout is the selected solution.

## 5. Current Windows memory paths

### 5.1 Default: contiguous pagefile-section dual view

The default Windows path creates one unnamed pagefile-backed section and maps
it twice at offset zero:

```text
primary: [ data R  ][ code RX ]   entirely below 4 GiB
alias:   [ data RW ][ code RW ]   address unrestricted
```

The primary and alias mappings are split logically in place. The common ART
mspace initialization, address translation, commit, collection, and metadata
paths run unchanged after mapping construction. Runtime checks use
`VirtualQuery` to verify the primary R/RX and alias RW/RW roles and check both
logical pairs are contiguous.

Verified under Wine:

- Hello with the default environment;
- post-removal JIT smoke 14/14;
- probe matrix 14/14, including FloatProbe, ThrowProbe, and GcProbe;
- explicit Windows `FlushInstructionCache` for generated code;
- low-space fragmentation and non-64-KiB capacities in the permanent section
  probe.

### 5.2 Removed J-1 diagnostic path

Before JIT-5, `ART_WINDOWS_X64_JIT_DUAL=0` selected a low-address
`VirtualAlloc` reservation whose code tail moved RX-to-RWX-to-RX during
updates. That path served bring-up and comparison testing through JIT-4.

ART `389158d46f` removes the environment read and prevents Windows from
entering the common single-view branch. The active smoke gate deliberately
sets the retired key to zero and still requires J-2 creation plus compiled
Hello. Historical J-1 result documents remain valid records of pre-removal
testing, not statements of current availability.

## 6. Implemented Windows 10 pagefile-section design

### 6.1 Effective minimum version and linkage

The port no longer targets Windows 7. The selected allocator uses
`MapViewOfFile3` with `MEM_ADDRESS_REQUIREMENTS`, whose documented desktop
minimum is Windows 10 version 1803. The build shall define:

```text
_WIN32_WINNT=0x0A00
NTDDI_VERSION=NTDDI_WIN10_RS4
```

The direct import also requires the Windows SDK `onecore.lib`. Wine 10 on
agent01 exports the API, and a PE probe linked through `onecore.lib` passed.
There is no older-Windows runtime branch.

The selected path does not need placeholder replacement, `VirtualAlloc2`, or
`UnmapViewOfFile2`. Removing those operations eliminates the most difficult
rollback and ownership problem from the previous design.

### 6.2 Anonymous shared backing

Create one unnamed section:

```text
CreateFileMappingW(
    INVALID_HANDLE_VALUE,
    nullptr,
    PAGE_EXECUTE_READWRITE,
    capacity_high,
    capacity_low,
    nullptr)
```

Properties:

- `INVALID_HANDLE_VALUE` makes the object pagefile-backed rather than backed by
  a filesystem file;
- a null name avoids global namespace and collision concerns;
- null security attributes make the handle non-inheritable;
- `PAGE_EXECUTE_READWRITE` is the section's maximum permission, allowing
  separate R, RX, and RW views; no mapped view is itself RWX;
- closing the section handle after mapping is safe because mapped views retain
  references to the section.

The default `SEC_COMMIT` behavior reserves commit charge for the full maximum
cache. This is acceptable for the 64 MiB default but must be tested at large
configured capacities up to ART's 1 GiB limit. `SEC_RESERVE` is not selected
initially because it would require Windows-only commit-on-growth logic in
`MoreCore`, increasing divergence.

### 6.3 One contiguous low-4-GiB primary view

Map the entire section in one `MapViewOfFile3` call with
`PAGE_EXECUTE_READ`. Supply one address-requirements extended parameter:

```text
LowestStartingAddress = allocation_granularity
HighestEndingAddress  = 0xffffffff
Alignment             = 0
```

`Alignment=0` requests normal system-allocation-granularity alignment. Mapping
the full capacity in one call gives the same essential guarantee as Linux: the
primary data and code address range is contiguous, and allocation either
succeeds as a whole or fails.

After mapping:

1. reject and unmap the result if `base + capacity >= 4 GiB`, matching ART's
   current Linux boundary check;
2. change only the data prefix from RX to R with `VirtualProtect`;
3. do this before creating the writable alias, so there is never a writable
   alias while the data prefix is executable;
4. never retry without the low-address constraint.

The primary mapping is therefore:

```text
[ data R ][ code RX ]
```

Only page alignment is required at the data/code divider. No 64 KiB divider
rule is introduced.

### 6.4 One complete writable alias

Map the same complete section a second time with `PAGE_READWRITE` and no
low-address requirement:

```text
[ data RW ][ code RW, non-executable ]
```

Using a complete offset-zero view is deliberate. Ordinary Windows file-view
offsets are normally allocation-granularity aligned, but ART permits JIT cache
sizes aligned only to `2 * gPageSize`. Mapping the whole section twice avoids a
Windows-only capacity rounding rule and preserves Linux command-line behavior
for non-64-KiB-aligned `-Xjitmaxsize` values.

Expose the two real views as four logical ART ranges:

| ART range | Real view | Protection |
|-----------|-----------|------------|
| `data_pages_` | primary prefix | R |
| `exec_pages_` | primary tail | RX |
| `writable_data_pages_` | writable prefix | RW |
| `non_exec_pages_` | writable tail | RW, non-executable |

The prefix `MemMap` owns each complete Windows view; the tail is a non-owning
reuse view, following the ownership model already used by Windows J-1. A narrow
Windows in-place split helper updates protections and `MemMap` metadata
without pretending to remap a different fd or section offset.

### 6.5 Failure and lifetime rules

- Build all four logical ranges before publishing them to the mspaces.
- Close the section handle only after both complete views are mapped.
- On any construction failure, unmap every complete view already created and
  close the section handle; the mappings are not yet visible to generated code.
- Report `CreateFileMapping` and partial-view failures through `error_msg` and
  return `false`. Do not continue into Windows single-view allocation.
- Destroy or reset non-owning tail views before their owning prefix view.
- Never call `UnmapViewOfFile` on an interior tail pointer.
- Keep the owner at the actual base returned by `MapViewOfFile3`; Windows
  `TargetMUnmap` may ignore the shortened logical size but must unmap by the
  original view base.

Unlike the placeholder transaction, this design never temporarily removes a
published primary prefix and has no coalesce/remap rollback state.

### 6.6 Divergence boundary

Windows requires one platform mapping helper because a pagefile section handle
cannot honestly masquerade as a POSIX fd. The helper only creates and splits
the four mappings. After that point, Windows uses the existing common
code for:

- `create_mspace_with_base` and footprint growth;
- address translation between primary and writable views;
- code and metadata commit;
- code-cache collection and reuse;
- JIT-root and CodeInfo encoding;
- debug/release write-protection policy.

Linux's memfd path remains unchanged. Windows `art::memfd_create` remains
`ENOSYS`; no temporary file, pseudo-fd table, or fd-specific `RemapAtEnd`
emulation is added.

### 6.7 Implemented safeguards and closure state

- Windows `FlushCpuCaches` uses `FlushInstructionCache` for generated code.
- Runtime `VirtualQuery` checks verify R/RX and RW/RW roles; the updater alias
  never gains execute permission.
- Low-address allocation failure is a real dual-view failure and never permits
  a high primary view.
- The implementation uses no temporary file, pseudo-fd table, placeholder
  split/remap transaction, or Windows-only 64 KiB JIT-capacity rule.
- Real-Windows repeated starts, dynamic-code/CFG policy, 1 GiB `SEC_COMMIT`
  pressure, direct JIT-root/CodeInfo encoding checks, and native
  compilation/collection churn with concurrent `RtlLookupFunctionEntry()`
  sampling are accepted through JIT-1 to JIT-4.
- JIT-5 accepts the final fail-closed source/binary contract, the inert retired
  environment key, post-removal default regressions, and three fatal origins.
  W-025 has no residual proof point.
- CET user shadow-stack support is outside W-025: all named incompatible HSP
  fields must be disabled for the ART process, and marking dynamic JIT ranges
  CET-compatible is forbidden as a workaround. The unrelated
  `CetDynamicApisOutOfProcOnly` field and reserved bits are classified under
  W-010, not as JIT-memory failures.
- Native JIT follows the common ART policy by default after W-024 cleanup.
  Native Windows 10 acceptance, Math.ceil/floor, and the common ELF/PE
  registration table are complete. Mixed/high-FP, unresolved app-JNI,
  unregister/re-register binding, method-tracing, and JVMTI forced-interpreter
  transitions pass for normal, FastNative, and CriticalNative calls in both
  memory modes.

## 7. Implementation and commit status

### Stage 1 — declare the Windows 10 baseline

- Set `_WIN32_WINNT=0x0A00`.
- Set `NTDDI_VERSION=NTDDI_WIN10_RS4`.
- Link `onecore.lib` for `MapViewOfFile3`.
- Add a build-and-run API probe under Wine.

Completed:

```text
windows_x64: require Windows 10 RS4 for constrained section views
```

### Stage 2 — harden section-view primitives

- Replace the former manual low-address `VirtualQuery` scan in the J-2 helper
  with `MapViewOfFile3` plus `MEM_ADDRESS_REQUIREMENTS`.
- Add a narrow Windows helper that logically splits one complete mapped view
  into an owning prefix and non-owning tail with explicit protections.
- Reject high results and remove the current high-address fallback.
- Add cleanup, repeated split/unmap, and partial-failure tests.

Completed:

```text
windows_x64: add constrained pagefile-section views
```

### Stage 3 — replace the separated J-2 topology

- Create one pagefile section and two complete offset-zero views.
- Split them logically into primary R/RX and alias RW/RW ranges.
- Keep all mspace initialization and later JIT logic on the common path.
- Add `FlushInstructionCache` to the Windows cache-flush implementation.
- Keep the corrected path opt-in during this stage until the full Wine matrix
  passes.

Completed:

```text
windows_x64: build contiguous JIT dual views from one section
```

### Stage 4 — verify and make dual view the default

- Run the complete acceptance matrix in §12 under Wine.
- Include fragmented-low-space and non-64-KiB capacity cases.
- Add permanent mapping layout and protection checks.
- Make the corrected section path default; retain J-1 temporarily as a
  diagnostic opt-out.

Completed:

```text
windows_x64: enable contiguous dual-view JIT memory by default
```

### Stage 5 — real-Windows acceptance and cleanup

- JIT-1 added direct signed-int32 JIT-root and uint32 CodeInfo construction
  checks with deterministic rejection tests at the construction sites.
- JIT-2 accepted mapping roles, CFG/dynamic-code policy, low-VA rejection and
  recovery, and 1 GiB `SEC_COMMIT` pressure on native Windows build 26100.
- JIT-2 confirmed that no temporary file is created and no view is RWX.
- JIT-3 accepted collection/reuse and concurrent dynamic-unwind lookup on
  native Windows build 26100, including exact reuse and live/dead sampling.
- JIT-4 accepted the complete default-J-2 native regression on build 26100:
  28 cases and 34/34 aggregate records pass, including three valid fatal
  dumps, with no J-1 arm, JIT temporary file, or trace.
- JIT-5 removed `ART_WINDOWS_X64_JIT_DUAL` and the Windows single-view branch,
  made section-construction errors fail closed, and accepted 29 native cases
  with 36/36 aggregate records on build 26100. The retired-key negative test
  still used J-2; three fatal dumps were valid; lifecycle lookup/unwind had no
  missing, stale, or failed record.
- JIT-1 through JIT-5 have immutable host evidence linked from their result
  docs. W-025 is closed.

Completed closure commits:

```text
windows_x64: remove the dual-view diagnostic opt-out
windows_x64: document dual-view JIT verification
```

Each stage should be committed only after its focused tests pass cleanly.
The dependency-ordered Stage 5 schedule is recorded in §13.

## 8. Alternatives reconsidered

| Plan | Linux similarity | Risk | Verdict |
|------|------------------|------|---------|
| Pagefile section + two complete views | Same topology and JIT behavior; one mapping hook differs | Low-medium | **Selected** |
| Pagefile section + four placeholder views | Exact independent OS views | Medium; 64 KiB split rules and more cleanup | Rejected as unnecessary |
| Temporary-file memfd + placeholder remap | Reuses fd branch | High lifecycle and rollback complexity; creates a filesystem object | Rejected |
| Keep J-1 as permanent default | Common fallback behavior, weaker W^X | Low | Rejected and removed in JIT-5 |
| Far-address JIT roots + extended CodeInfo header | Low; Win-only compiler/runtime format | High | Rejected |
| Move roots and stack maps into code arena | Low; allocator/GC divergence | High | Rejected |
| Move stack maps only | Does not fix JIT-root displacement | Incorrect | Rejected |
| Force every section view below 4 GiB | Wastes scarce low VA and still duplicates JIT logic | High fragmentation | Rejected |

If direct constrained mapping proves unreliable on real Windows, the fallback
design is a pagefile section plus a low-address placeholder for the one complete
primary view, followed by the same in-place protection split. It must not return
to separate low-data/high-code primary mappings.

## 9. Permanent safety checks

The corrected layout should be defended in release builds.

### 9.1 Region initialization

Verify:

- primary data begins below executable code;
- data and code are contiguous;
- the entire span is no more than `INT32_MAX`;
- the mappings use the expected protection and alias roles.

### 9.2 JIT-root patching

Before storing the displacement:

```cpp
intptr_t delta = root_address - rip_base;
CHECK(IsInt<32>(delta));
```

Do not rely only on `dchecked_integral_cast`.

### 9.3 CodeInfo header

Use integer address arithmetic:

```cpp
uintptr_t code_address = reinterpret_cast<uintptr_t>(code);
uintptr_t info_address = reinterpret_cast<uintptr_t>(stack_map);
CHECK_GE(code_address, info_address);
CHECK_LE(code_address - info_address, UINT32_MAX);
```

This also avoids depending on pointer subtraction across separate allocations.

## 10. dlmalloc and mspace findings

`create_mspace_with_base` performs allocator initialization by writing inside
the supplied memory. It initializes `malloc_state`, bins, and the top chunk,
marks the supplied segment external, and does not independently allocate
virtual memory or call MoreCore during successful creation.

The permanent ART configuration remains:

- `HAVE_MMAP=0`, `HAVE_MORECORE=1`, and mspace-only operation;
- `USE_LOCKS=0` for ART's embedded dlmalloc;
- JIT mspaces serialized by `Locks::jit_lock_`;
- heap mspaces protected by ART-level locks.

Internal dlmalloc locks are redundant under that single-owner lock contract. A
temporary `USE_SPIN_LOCKS=1` experiment was reverted after Wine regressions.
W-013 Stages A through E removed the historical `_WIN32`/`WIN32` masking, the
global MoreCore owner lookup, and the implicit Windows anonymous low-address
policy. dlmalloc now has embedding-safe Win32 defaults;
ART explicitly compile-checks its MoreCore-only, page-granular, unlocked
mspace policy; and each JIT mspace stores its `JitMemoryRegion` provider in
`malloc_state::extp/exts`. JIT-region move operations detach the temporary
provider and rebind both mspaces to the destination before the temporary can be
destroyed. Windows `MemMap` views now share whole-allocation ownership keyed by
`AllocationBase`, so the logical R/RX and R/RW splits keep their complete
section view alive and release it exactly once with `UnmapViewOfFile`. Heap
page-state changes now use the same `MemMap` abstraction, without changing the
JIT dual-view topology. Stage E also restores Linux-like anywhere placement
for compiler/JIT metadata arenas and ordinary LinearAlloc; the complete JIT
primary view remains low because generated code relies on that encoding
contract. See [win32_heap_memory.md](win32_heap_memory.md) §§4–7.

The JIT pagefile-section topology does not give dlmalloc ownership of the
section or its views. `JitMemoryRegion` owns those `MemMap` objects, and each
mspace only manages chunks in its writable ART-provided range. The landed
owner-attached MoreCore callback changes only dispatch ownership; it does not
change the dual-view layout, address translation, or protection roles
described in this document.

Two historical J-2 wiring bugs are recorded so they are not repeated:

1. The first J-2 implementation returned before mspace initialization.
2. A later version failed to move the primary mapping into `data_pages_`,
   causing `TranslateAddress` checks to fail.

These bugs were specific to the experimental branch. The replacement helper
returns all four mappings and falls through to the unchanged common mspace
initialization; it does not initialize or publish mspaces inside the Windows
mapping branch.

Verified section-view properties under Wine:

- RW and RX views are coherent;
- writes across the complete 32 MiB test view succeed;
- mspace initialization and page readback succeed with `USE_LOCKS=0`.

## 11. Compiler TLS and native JIT

### 11.1 D-1 is complete

All 37 audited compiler-backend Thread accesses route through
`Address::ThreadOffsetAddr`:

- Windows: `Address(R15, offset)`;
- Linux: GS-relative addressing.

R15 is pinned as rSELF and removed from the Windows x64 allocatable callee-saves.
`X86_64Assembler::gs()` emits no GS prefix on Windows.

The historical separated-J-2 failure was not evidence of incomplete D-1 work.

### 11.2 Native JIT ABI repair is complete

Historically, JIT compilation of native methods was gated off. The compiled
FastNative path requires two conventions at the stub boundary: Linux-like ART
managed inputs and Microsoft x64 native outputs. The current Windows x64 patch
correctly defines the outgoing unified four-slot register layout, 32-byte
shadow area, and stack arguments. The incoming/outgoing register tables and
limits are now separate in `X86_64JniCallingConvention`, so
`X86_64ManagedRuntimeCallingConvention` retains the Linux-like managed input
layout.

Before the split, the concrete failures matched the register shift exactly.
For static
`StringFactory.newStringFromBytes`, managed `RSI` contains `byte[] data` and
`RDX` contains `high == 0`; the stub reads `RDX` as the first Java argument and
throws `data == null`. For `System.arraycopy`, managed `RSI` contains `src`
and `RDX` contains `srcPos == 0`; the old compiled stub read a null `src`.

The landed split makes both workloads pass. The expanded acceptance matrix
then exposed a missing XMM-to-XMM operation in
`X86_64JNIMacroAssembler::Move()`: managed `XMM0` needed to become native
unified-slot `XMM3`. The assembler now emits `movss`/`movsd` for those moves.

The final default matrix compiles 7/7 distinct native targets and covers registered
and unresolved normal/FastNative methods, static and instance calls,
references, five managed core ordinals, six managed FP ordinals, Windows x64 home
space and deep stack spills, boolean input, and double returns. Before gate
removal, a 0/7 gate-closed control and repeated 7/7 gate-open runs qualified the
transition. Unresolved CriticalNative mixed signatures are covered separately.

The same default probe exercises native data-entrypoint changes after compilation.
It unregisters the probe class, verifies dlsym re-resolution with `+10000`
values, installs a second `RegisterNatives` table, and verifies `+20000`
alternate values. The verifier allows exactly seven target compile records for
all three phases, so the transition cannot pass by recompiling the methods.

A second default process starts non-sampling method tracing, verifies tracing
mode `0 -> 1 -> 0`, executes all alternate normal/FastNative bindings during
and after tracing, and requires the same seven target compilation records.
ART's tracing path changes runtime debug state, invalidates pre-tracing JIT
code, and installs entry/exit instrumentation support. The trace output is
deleted by Java and defensively removed by the harness, so the test leaves no
filesystem artifact.

The separate optimizing-compiler direct CriticalNative convention is also
fixed. Windows x64 direct calls now use unified Microsoft x64 argument ordinals,
reserve the 32-byte home area, and spill after it. W-024 originally made the
unresolved critical dlsym stub reload its caller PC after the helper-based PE
runtime-instance macro used `r11` as scratch. W-004 later replaced that helper
with a direct load that does not clobber `r11` and removed the reload. The
focused direct-signature probe covers zero, mixed integer/floating, FP-only,
stack-spilled arguments, and scalar returns.

Unresolved mixed-signature app JNI is now covered as well. The initial probe
returned zeros because the previous Windows x64 `Runtime.nativeLoad` shortcut called
`LoadLibraryA` and `JNI_OnLoad` without adding the DLL to
`JavaVMExt::libraries_`. Product `JVM_NativeLoad` now delegates to
`art.dll!ART_LoadNativeLibrary`, which follows AOSP ownership through
`JavaVMExt::LoadNativeLibrary`. The host loader's only Windows path divergence
is recognizing drive, root, and UNC absolute paths; Linux behavior is unchanged.

The memory plan did not own that ABI repair. The compiled-JNI split, XMM moves,
and mixed/high-FP matrix are landed; the acceptance probe is
unified `managed_native_abi` gate.

Windows x64 now also builds ART's upstream `openjdkjvmti` sources as a separate
`openjdkjvmti.dll`, matching Linux topology. A focused agent enables
thread-scoped `JVMTI_EVENT_SINGLE_STEP`, exercising the real
force-interpreter/deoptimization path. Registered and unresolved normal,
FastNative, and CriticalNative calls retain exact results before, during, and
after the transition in three dual-view and three J-1 runs.

The former Windows-only `ShouldStayInSwitchInterpreter()` branch that forced
native methods into `InterpreterJni` was removed. Linux ART forces the Java
caller into the interpreter while native methods continue through JNI
compiler/generated entrypoints. Keeping that common behavior both reduces
divergence and avoids the old signature-specific interpreter abort on mixed
shorty `DJDIF`.

Because JVMTI makes the runtime debuggable, AOSP intentionally rejects JIT
compilation of CriticalNative methods. The verifier therefore requires exactly
two compiled registered normal/FastNative targets and zero successful
CriticalNative compilations while still checking all six native calls across
the forced-interpreter transition.

The `ART_WINDOWS_X64_JIT_NATIVE` exclusion and override are removed. Native methods
now follow the common ART JIT policy by default; the focused default matrix
compiles 7/7 normal/FastNative targets with exact values. Math.ceil/floor are
native CriticalNative methods again and Math.c uses one common ELF/PE
registration table.

Per-method `Windows x64 CompileMethod done` logging is no longer a product default.
It is enabled only by `ART_WINDOWS_X64_JIT_LOG_COMPILES=1`; the ABI/JVMTI acceptance
harnesses set that flag when they need exact compilation records. JIT smoke
verifies both the opt-in records and a normal quiet run.

The expanded `InterpreterJni` shorties were not observed product paths. An
opt-in fatal-tripwire build disabled both runtime-started fallback
calls and still passed Windows x64 `-Xint`, direct/unresolved CriticalNative,
normal/FastNative, method tracing, and JVMTI forced interpretation under Wine
and native Windows 10. With both calls disabled, Clang reported
`InterpreterJni` unused. The build was restored to the product-default
tripwire-OFF mode and the final binaries rebuilt. Linux and Windows x64 use identical
boot.jar dex and annotation bytes, so there is no Windows-only boot shorty set.
ART commit `42a03f2ea0` restored exact upstream interpreter scope and removed
the native-JIT gate; see
`docs/history/windows_x64_w024_interpreter_jni_result.md`.

## 12. Verification and acceptance

### 12.1 Platform-memory tests

- Unnamed pagefile section creation with no filesystem artifact.
- One complete primary view below 4 GiB.
- One complete writable alias at an unconstrained address.
- Coherent RW/R/RX access across the two views.
- Page-aligned but non-64-KiB-aligned capacity and divider.
- Fragmented low-address space with the complete primary still placed in one
  suitable gap.
- Low-address exhaustion fails rather than falling back high.
- Repeated map/split/unmap without leaks or double unmaps.
- Failure injection after each section, view, and protection operation.
- RW alias writes visible through the RX view.
- Execute a small function written through the RW alias.
- Explicit `FlushInstructionCache` succeeds for committed code.
- Large maximum-capacity tests observe and document `SEC_COMMIT` pressure.

### 12.2 Protection checks

Use `VirtualQuery` to verify:

| View | Required protection |
|------|---------------------|
| Primary data | R |
| Primary code | RX |
| Writable data alias | RW, non-executable |
| Code updater alias | RW, non-executable |

No primary mapping may be RWX.

### 12.3 ART integration

- JIT code cache creation through the contained Windows section helper.
- Hello under default managed JIT.
- FloatProbe under the normal product threshold.
- Unified `art.w025.windows_w025_jit_runtime_controls` control matrix.
- Unified threshold-zero Math/IO/Net/GC/throw workload matrix.
- ThrowProbe to exercise CodeInfo decoding.
- GcProbe to exercise JIT root updates.
- Small-cache collection and code-reuse stress.
- Repeated cold starts to vary ASLR placement.
- Custom page-aligned JIT maximum sizes that are not 64 KiB aligned.
- Retired-key negative run proving `ART_WINDOWS_X64_JIT_DUAL=0` is inert and
  still creates J-2.
- `ART_WINDOWS_X64_JIT=0` interpreter/nterp regression.

### 12.4 Host acceptance

Wine success is necessary but insufficient. JIT-2 through JIT-5 therefore
validated the closure on Windows 10 version 1803 or later:

- validate on real Windows 10 version 1803 or later;
- repeat mapping protection inspection;
- run the smoke and probe matrices;
- exercise code-cache collection and exact-address reuse under load;
- sample generated PCs concurrently with collection and require lookup/unwind
  to observe only registered live allocations; and
- record CFG, low-address exhaustion, and large-cache `SEC_COMMIT` behavior;
  retain one `ProhibitDynamicCode` child only as a clean unsupported-policy
  rejection proof.

The focused W-024 native-host matrix passed on Windows 10 Enterprise LTSC 2021
build 19044: both normal/FastNative modes compile the required 7/7 targets,
both JVMTI modes compile the two allowed targets and no CriticalNative target,
all transition values pass, and no tripwire or crash dump appears. The W-024
native-method gate and interpreter fallback expansion were removed after
acceptance and post-change regressions. W-025 JIT-2 now also accepts native
mapping protection, CFG and dynamic-code mitigation, low-VA failure/recovery,
and 1 GiB code-cache pressure. W-025 JIT-3 accepts 52 native collection cycles,
1,344 optimizing/JNI compilations, 1,248 exact address reuses, and concurrent
live/dead lookup plus virtual unwind with no missing, stale, or failed record.
W-025 JIT-4 accepted the final pre-removal default-J-2 regression. JIT-5 then
removed the opt-out and Windows single-view branch and accepted 29 native
cases with 36/36 aggregate PASS records. Its 14-record smoke includes the
inert retired-key proof; source and `art.dll` lack both retired strings; the
eight-cycle lifecycle and three fatal origins pass with empty `jit-temp` and
no trace. Post-removal Wine gates, the full Linux rebuild, imageless Hello, and
Linux GC stress also pass. P5 and W-025 are complete.

Native W-025 mitigation runs must record that Hardware-enforced Stack
Protection is disabled. CFG may be enabled and tested independently. An
HSP-enabled process is rejected by W-010's implemented early startup guard,
not treated as a JIT mapping failure and not allowed to reach generated code.

### 12.5 Threshold-zero stress resolution

`FloatProbe -Xjitthreshold:0` now passes in both J-1 and the corrected dual-view
path. The failure was in the Windows x64 direct `@CriticalNative` first-use path, not
JIT memory topology.

The historical controls and current result are:

| Configuration | Historical baseline | Current result |
|---------------|---------------------|----------------|
| Windows x64 dual view, threshold 0 | FAIL | PASS, 5/5 in the combined acceptance harness |
| Windows x64 J-1, threshold 0 | FAIL at the same path | PASS, 5/5 in the combined acceptance harness |
| Windows x64 JIT disabled, threshold 0 | PASS | Not rerun in this stage; unaffected control |
| Windows x64 dual view, threshold 1 | PASS | Superseded by the stricter threshold-zero pass |
| Linux ART, threshold 0 | PASS | Linux control build and shared-boot L-005 Hello pass; runtime behavior unchanged |

The first real fault is a stack walk from the unresolved direct
`System.currentTimeMillis()` call in
`Daemons$FinalizerWatchdogDaemon.waitForProgress()`. The runtime save frame is
the normal 208-byte x86_64 SaveRefsAndArgs frame. The apparent invalid
`ArtMethod*` (`0x0000000100000001`) is caller spill data reached because the
frame was positioned 32 bytes too high.

The exact mismatch is:

1. The Windows x64 JNI-frame helper correctly reports a 32-byte Microsoft x64 shadow
   area for direct `@CriticalNative` shorty `J` (`()J`).
2. `CriticalNativeCallingConventionVisitorX86_64` had the upstream SysV
   direct-call behavior: it reported zero outgoing bytes for `()J`, so the JIT
   emitted no `sub rsp, 32` before `call *ArtMethod::jni_entrypoint`.
3. `art_jni_dlsym_lookup_critical_stub` asks
   `artCriticalNativeFrameSize()` for the expected direct-call frame size and
   receives 32. It therefore positions its managed SaveRefsAndArgs frame as if
   the caller had reserved that area. The stack walker advances 208 bytes and
   lands at caller SP + 32 instead of the caller's method slot.

Adding the missing 32-byte area corrected the stack walk and exposed a second
independent Windows x64 stub defect: the then-current `LOAD_RUNTIME_INSTANCE r10`
used `r11` as its PE scratch register, overwriting the caller PC that the dlsym
stub kept live in `r11`. The stub then installed `Runtime*` as the native return
address.

The landed fix covers both defects:

1. `CriticalNativeCallingConventionVisitorX86_64` has a Windows branch using
   the Microsoft x64 contract: RCX/RDX/R8/R9 or XMM0-XMM3 selected by unified
   argument ordinal, followed by stack arguments.
2. Windows x64 direct-call stack offsets start after the 32-byte shadow area, so
   argument moves and `GetCriticalNativeDirectCallFrameSize()` agree for zero,
   mixed, and spilled arguments.
3. The original W-024 fix made the dlsym stub reload its caller PC from the
   existing saved frame slot after `LOAD_RUNTIME_INSTANCE`; the common macro
   and Linux assembly were unchanged in that stage. W-004 later replaced the
   Windows helper with a direct same-image data load, which does not clobber
   `r11`, and removed the now-unnecessary local reload. Linux remains unchanged.
4. Unified `managed_critical_native` covers unresolved `()J`, registered zero,
   FP-only, mixed integer/FP, stack-spilled signatures, scalar returns, and the
   corresponding unresolved exported app-JNI dlsym shapes. JIT dump inspection
   confirmed `rsp+0x20`/`rsp+0x28` stack slots.
5. The harness alternates `System.loadLibrary` and absolute `System.load`.
   Windows drive/root/UNC absolute paths bypass host library-path prefixing;
   the internal `BaseDexClassLoader.getLdLibraryPath()` contract remains
   colon-separated after it parses the public semicolon-separated property.

Native Windows 10 direct-call and fallback-reachability acceptance is complete.
W-024 cleanup is also complete: native methods compile by default,
`interpreter.cc` matches upstream, and the post-change Linux/Windows x64 regression
matrix passes. Math.ceil/floor and the common registration table are restored.
None of this justifies retaining the RWX J-1 path as the product default.

## 13. Current status — 2026-07-29

### Done

| Item | Evidence |
|------|----------|
| J-1 single-view memory | ART `27a1ac74a4` rebinding uses `ScopedCodeCacheWrite`; native R2 passes with 26 successful compilations, Hello, clean return, and no dump |
| D-1 r15 compiler TLS | 37/37 GS sites audited |
| Managed/native JIT default | Corrected pagefile-section dual view; Hello about 28–30 successful records after native-gate removal |
| Corrected dual-view integration | Post-removal JIT smoke 14/14; matrix 14/14; protections checked with `VirtualQuery` |
| Section-layout probe | 64 MiB and non-64-KiB capacity cases pass under Wine; low primary remains contiguous under forced low-space fragmentation |
| dlmalloc and `MemMap` ownership | W-013 CLOSED: Stages A–E plus native R2 mapping, ownership, discard, pressure, metrics, and repeated-start acceptance pass |
| Root-cause correction | JIT-root signed displacement plus latent CodeInfo overflow |
| Direct encoding checks | ART `146016f83e` validates every x86_64 JIT-root disp32 before patching and CodeInfo placement before code/header writes; deterministic bounds pass, both native builds pass, and Windows Server 2025 W-004 regression returns 28/28 with no dump |
| W-025 JIT-2 mapping/policy | Native build 26100 accepts 64 MiB and 1 GiB unnamed R/RX+RW mappings, complete low-VA rejection/recovery, 1 GiB `SEC_COMMIT`, CFG execution and ART compilation, graceful error-1655 dynamic-code rejection, 14/14 aggregate checks, empty JIT temp, and no dump |
| W-025 JIT-3 lifecycle/unwind | Native build 26100 accepts four J-2/J-1 cases, 52 collections, 1,344 compilations, 1,248 exact reuses, 696,929 live lookups, 5,909,811 dead lookups, and 696,969 virtual unwinds with zero missing/stale/failed records, empty JIT temp, and no dump |
| W-025 JIT-4 final regression | Native build 26100 accepts 28 default-J-2 cases and 34/34 aggregate records across exact smoke/matrix, two JIT-disabled controls, default native ABIs, nterp/switch OSR, eight lifecycle cycles, and three valid static/JIT/OSR fatal dumps; no J-1 arm runs, JIT temp is empty, and no trace remains |
| W-025 JIT-5 removal | ART `389158d46f` removes the Windows opt-out and single-view fallback; source/binary absence and fail-closed policy pass; native build 26100 accepts 29 cases and 36/36 records, including the inert retired-key test, lifecycle, and three fatal dumps; Wine/Linux regressions pass |
| nterp hard-float return | ART `43f866830e` keeps compiled quick/normal-JNI float and double results in XMM0 instead of replacing them with the Native-to-Runnable RAX state value; all eight JIT-3 JNI targets pass every lifecycle cycle |
| PE asm definitions | Windows-target generator test enforces `RUNTIME_INSTRUMENTATION_OFFSET=0x328` |
| W-002 managed OSR entries | W-002 CLOSED: quick and nterp OSR adapters pass structural, Wine, Linux, and native R2 controls; native R2 returns 8/8 OSR with deterministic thresholds/checksum |
| W-002 native attach entries | Regular and daemon native threads call a pre-JITed Java callback, allocate, validate daemon state and exact values, detach, and verify `JNI_EDETACHED` in both memory and interpreter modes |
| W-003 quick-frame/XMM boundary | CLOSED: opt-in counters compile out of product artifacts; nterp and threshold-zero JIT each reach all four frame families; native Windows build 19044 passes 8/8 frame runs and 6/6 XMM runs with 19/19 records, J-2 creation, and clean fatal/dump scans |
| Dynamic JIT PE unwind | W-010 E9 accepts static, J-2/J-1 JIT, and J-2/J-1 OSR fatal origins on build 26100; registration precedes publication, exact deletion precedes reuse, and focused lifecycle/re-registration gates pass |
| FS-2 native exception-unwind/JIT boundary | Windows Server 2025 build 26100 accepts threshold-zero JIT debugger continuation and full-width XMM6-XMM15 preservation through managed exception unwind; safe CET dynamic/reserved policy fields remain accepted |
| Threshold-zero CriticalNative | Direct visitor uses Windows x64 unified ordinals/home area; dlsym caller PC preserved; repeated J-1 and dual-view probes pass |
| Unresolved CriticalNative dlsym | ART-owned `JVM_NativeLoad` bridge; mixed/spilled/scalar exported calls pass through both load APIs |
| CriticalNative method tracing | Registered and unresolved suites pass during/after tracing in J-1 and dual-view modes; mode restores to zero and trace output is deleted |
| Compiled normal/FastNative | Default 7/7 distinct targets; registered/unresolved, static/instance, mixed/high-FP, references, deep spills, returns, rebinding, and method tracing pass with exactly seven target compile records |
| JVMTI forced interpreter | Separate `openjdkjvmti.dll`; thread-scoped single-step; registered/unresolved normal, FastNative, and CriticalNative exact values pass 3/3 in each memory mode |
| Math CriticalNative surface | ceil/floor native again; one ELF/PE table; dual/J-1/-Xint 3/3 plus Linux JIT/-Xint pass on identical boot.jar bytes |
| W-024 native host | Windows 10 build 19044 tripwire matrix passes 9/9 with exact required native compilation records and no crash dump |

### Open

No W-025 items remain. The Windows JIT memory closure is complete.

CET user shadow stacks are intentionally absent from this open table. They are
unsupported for current Win32 ART rather than a pending W-025 feature; see
[win32_faults_and_stacks.md](win32_faults_and_stacks.md).

### Current test summary

The J-1 column below is historical pre-removal evidence. The current runtime
has only the corrected dual view; the JIT-5 row records the closure state.

| Test | J-1 opt-out | Default corrected dual view |
|------|------------|-----------------------------|
| Hello | PASS | PASS |
| JIT smoke | 12/12 | 12/12 |
| JIT matrix | 14/14 | 14/14 |
| FloatProbe normal threshold | PASS | PASS |
| FloatProbe `-Xjitthreshold:0` | PASS, 3/3 current harness | PASS, 3/3 current harness |
| Direct registered CriticalNative signatures | PASS, 3/3 current harness | PASS, 3/3 current harness |
| Direct unresolved CriticalNative signatures | PASS, 3/3 current harness | PASS, 3/3 current harness |
| CriticalNative method tracing | PASS, 3/3 current harness | PASS, 3/3 current harness |
| FastNative ABI probe, default native JIT | PASS, three binding phases, 7/7 compiled once | PASS, three binding phases, 7/7 compiled once |
| FastNative method tracing | PASS, mode `0 -> 1 -> 0`, no trace file | PASS, mode `0 -> 1 -> 0`, no trace file |
| JVMTI forced interpreter | PASS, 3/3; all six calls exact; two normal/FastNative compile records | PASS, 3/3; all six calls exact; two normal/FastNative compile records |
| Managed OSR, default nterp | PASS, 2/2 Wine + 2/2 native R2 | PASS, 2/2 Wine + 2/2 native R2 |
| Managed OSR, switch interpreter | PASS, 2/2 Wine + 2/2 native R2 | PASS, 2/2 Wine + 2/2 native R2 |
| Attached-thread JNI, default nterp | PASS, 2/2 Wine + 2/2 native R2; 16 threads/run | PASS, 2/2 Wine + 2/2 native R2; 16 threads/run |
| Attached-thread JNI, switch interpreter | PASS, 2/2 Wine + 2/2 native R2; 16 threads/run | PASS, 2/2 Wine + 2/2 native R2; 16 threads/run |
| Restored Math ceil/floor | PASS, 3/3 threshold-zero and 3/3 `-Xint` | PASS, 3/3 threshold-zero and 3/3 `-Xint` |
| Direct encoder boundary/overflow | PASS | PASS |
| Post-guard native W-004 regression | PASS: CriticalNative, normal/FastNative, and JVMTI J-1 arms | PASS: dual-view JIT, threshold-zero, native/JVMTI, stress, and ten repeated starts; 28/28 aggregate |
| W-025 JIT-2 native mapping/policy | Dynamic-policy J-1 executable fallback is rejected with error 1655 | PASS: 64 MiB/1 GiB mappings, low-VA recovery, pressure, CFG compile/execute, policy rejection, and 14/14 aggregate checks |
| W-025 JIT-3 native lifecycle/unwind | PASS comparison: 12 cycles, 312 compilations, 288 exact reuses, zero missing/stale/failed records | PASS: 40 cycles across three runs, 1,032 compilations, 960 exact reuses, zero missing/stale/failed records; combined four-case review passes 9/9 |
| W-025 JIT-4 final native regression | Not executed; JIT-4 intentionally has no J-1 arm | PASS: 28 cases, 34/34 aggregate records, eight lifecycle cycles, three valid fatal dumps, empty JIT temp, and no trace |
| W-025 JIT-5 removal | Removed; the retired key is only an inert negative-test input | PASS: 29 cases, 36/36 aggregate records, source/binary removal proof, eight lifecycle cycles, three valid fatal dumps, empty JIT temp, and no trace |

### Next execution schedule — dependency order

This is an evidence-gated order, not a calendar estimate. A later row starts
only after the preceding exit gate is archived or is explicitly split into an
independent package.

| Order | Work | Exit gate |
|------:|------|-----------|
| JIT-1 (done) | Direct range checks at every signed-int32 JIT-root patch and uint32 CodeInfo construction site, with positive boundary and deterministic overflow tests | Accepted 2026-07-29: focused checks, Windows x64/Linux builds, Wine JIT/unwind gates, and native Windows Server 2025 W-004 regression pass without changing the encoded format; see `docs/history/windows_x64_w025_jit1_result.md` |
| JIT-2 (done) | Build one W-025 native closure package for mapping protections, no-filesystem/no-RWX assertions, CFG, unsupported-policy rejection, low-VA failure, and large `SEC_COMMIT` pressure | Accepted 2026-07-29 on Windows Server 2025 build 26100: nine cases and 14 aggregate checks pass; the `ProhibitDynamicCode` child cleanly rejects J-2/J-1 operations with error 1655 as a negative boundary, no dump or JIT temp remains, and the returned archive passes independent review; see `docs/history/windows_x64_w025_jit2_result.md` |
| JIT-3 (done) | Run default J-2 allocation/compile/invalidate/collect/reuse stress with concurrent `RtlLookupFunctionEntry()` and virtual-unwind sampling; retain J-1 only as a comparison arm | Accepted 2026-07-29 on Windows Server 2025 build 26100: four cases complete 52 collections, 1,344 compilations, 1,248 exact reuses, and 696,969 virtual unwinds with no missing live record, stale dead record, unwind failure, dump, or JIT temp; see `docs/history/windows_x64_w025_jit3_result.md` |
| JIT-4 (done) | Repeat smoke, matrix, JIT-disabled, and representative managed/native/OSR/fatal gates on the accepted default build | Accepted 2026-07-29 on Windows Server 2025 build 26100: 28 default-J-2 cases and 34/34 aggregate records pass with eight lifecycle cycles, three valid fatal dumps, empty JIT temp, no trace, and no J-1 arm; see `docs/history/windows_x64_w025_jit4_result.md` |
| JIT-5 (done) | Remove `ART_WINDOWS_X64_JIT_DUAL=0` and its single-view Windows diagnostic branch | Accepted 2026-07-29 on Windows Server 2025 build 26100: 29 cases and 36/36 records pass; source and `art.dll` lack the opt-out/fallback; the retired key remains inert; Wine and Linux regressions pass; see `docs/history/windows_x64_w025_jit5_result.md` |

The shared FS-3 dynamic-table churn requirement is complete through JIT-3.
FS-2 now closes the native debugger continuation, CET policy classification,
exception-unwind XMM, and embedding gates that exercise the JIT/managed
boundary. Conditional pending-range, reservation-correlation,
negative-exception, and debugger-quality dump-stack work remains scheduled in
[win32_faults_and_stacks.md](win32_faults_and_stacks.md), independent of the
completed JIT-1 through JIT-5 gates.

## 14. Decision log

| Date | Decision |
|------|----------|
| 2026-07-19 | J-1 selected for initial managed-JIT bring-up |
| 2026-07-21 | P3 complete: managed JIT Hello |
| 2026-07-22 | P4 complete: J-1 probe matrix 14/14 |
| 2026-07-22 | D-1 compiler audit complete: 37/37 Thread accesses use r15 on Windows |
| 2026-07-22 | Experimental J-2 stays opt-in after probe failures |
| 2026-07-23 | Correct immediate J-2 cause to signed 32-bit JIT-root displacement; CodeInfo overflow remains a second defect |
| 2026-07-23 | Reject stack-map-only relocation and far-address Win-only codegen as preferred fixes |
| 2026-07-23 | Drop Windows 7 support; require Windows 10 RS4 mapping APIs |
| 2026-07-23 | Temporary-file memfd plus placeholder remap considered, then superseded after lifecycle and rollback review |
| 2026-07-23 | Reconsider backing store: reject temporary-file memfd and placeholder remap in favor of an unnamed pagefile section mapped twice |
| 2026-07-23 | Wine probes verify constrained low mapping, R/RX plus RW coherence, execution, fragmented-low-space placement, and non-64-KiB capacity support |
| 2026-07-23 | Corrected contiguous dual view passes Wine smoke 10/10 and matrix 14/14 and becomes the Windows default |
| 2026-07-23 | Full rebuild exposed Linux-layout `asm_defines` regeneration; Windows-target codegen and a permanent 0x328 offset assertion fixed it |
| 2026-07-23 | Threshold-zero FloatProbe fails identically in J-1 and dual view, separating it from the historical J-2 layout defect |
| 2026-07-24 | Threshold-zero root cause isolated to missing Windows x64 direct-CriticalNative shadow space plus dlsym-stub `r11` caller-PC clobber; a reverted research prototype passes 20/20 and is later superseded by the complete landed fix |
| 2026-07-24 | Compiled-JNI/FastNative failure isolated to MS native register definitions leaking into the incoming ART managed convention; managed/native convention split landed and targeted System.arraycopy/StringFactory runs pass |
| 2026-07-24 | Direct CriticalNative Windows x64 visitor and dlsym caller-PC fixes landed; threshold-zero and mixed registered signature probes pass in both J-1 and dual-view modes |
| 2026-07-24 | Replaced direct `LoadLibraryA` native-load shortcut with an ART-owned `JavaVMExt::LoadNativeLibrary` bridge; unresolved mixed-signature dlsym and both Java load APIs pass |
| 2026-07-24 | Mixed/high-FP normal/FastNative matrix passes 7/7 after adding XMM-to-XMM JNI argument moves |
| 2026-07-24 | The same seven compiled JNI thunks pass unregister/dlsym/re-register binding transitions without recompilation |
| 2026-07-24 | Normal/FastNative bindings pass during and after method tracing with mode restoration and trace cleanup |
| 2026-07-24 | Registered and unresolved CriticalNative suites pass during and after method tracing in both memory modes |
| 2026-07-24 | Separate Windows x64 `openjdkjvmti.dll` and thread-scoped single-step probe pass 3/3 in both memory modes; the divergent native-interpreter branch is removed |
| 2026-07-24 | Restore Math.ceil/floor as CriticalNative and remove `gMethodsWin`; Windows x64 and Linux use one source table and identical boot.jar bytes |
| 2026-07-24 | Make per-method Windows x64 JIT compile records opt-in; smoke expands to 12/12 and verifies product-default silence |
| 2026-07-24 | Wine fatal-tripwire audit shows legacy runtime-started InterpreterJni fallback is unreachable across `-Xint`, native ABI, tracing, and JVMTI suites, establishing the native-host test candidate |
| 2026-07-25 | W-013 native R1 J-1 dump resolves to `ArtDetachMspaceMoreCoreProvider` writing executable-mspace metadata after the mapping returned to RX; attach/detach now run inside the existing `ScopedCodeCacheWrite` transition, with dual-view behavior unchanged |
| 2026-07-25 | W-013 native R2 passes 56/56 records: corrected dual view compiles 30 methods, J-1 compiles 26, 20/20 repeated starts and complete metrics pass, and no dump is present; W-013 closes while broader W-025 work remains separate |
| 2026-07-25 | W-002 quick OSR keeps the platform C++ ABI and performs a local Microsoft-to-SysV argument conversion with r15 publication; nterp OSR gains a Windows return adapter because its save layout intentionally differs from compiled code |
| 2026-07-25 | W-002 OSR and attached-thread JNI pass 2/2 in all dual/J-1 and default-nterp/switch combinations; Linux OSR and full builds pass; native Windows acceptance is packaged |
| 2026-07-26 | W-002 native R1 passes package identity, structure, 8/8 attach, and 4/4 switch OSR with no fatal marker or dump; all four clean default-nterp runs finish before the required OSR jump because warmup remained 65535 |
| 2026-07-26 | W-002 R2 pins warmup and optimize thresholds to 100, increases the exact-checksum loop to 2,000,000 iterations, accepts strict evidence-only returns, and passes unit, focused Wine, aggregate Wine, and Linux controls |
| 2026-07-26 | W-002 native R2 passes 21/21 records on Windows 10 build 19044: 8/8 OSR, 8/8 attach, exact thresholds/checksum, clean fatal scan, and no dump; W-002 closes |
| 2026-07-26 | W-003 opt-in frame attribution passes 8/8 under Wine; nterp and threshold-zero JIT each prove all four quick-frame families, while an independent implicit-null AV is assigned to W-010 |
| 2026-07-26 | W-003 native R1 passes 19/19 records on Windows build 19044: 8/8 frame attribution, 6/6 XMM6-XMM11 sentinel, explicit pagefile-section J-2 creation, successful JIT compilation, and no fatal marker or dump; W-003 closes while implicit-fault translation remains W-010 at this checkpoint (later activated by Stage D) |
| 2026-07-24 | Native Windows 10 build 19044 tripwire matrix passes all nine cases with exact required native compile records and no crash dump; W-024 cleanup is authorized |
| 2026-07-24 | ART `42a03f2ea0` restores exact upstream interpreter scope and common default native-JIT policy; final Windows x64 and Linux regressions pass and W-011/W-012/W-024 close |
| 2026-07-29 | Treat direct encoding guards as the first W-025 closure change, then run one combined native mapping/pressure/collection/dynamic-unwind gate before removing the J-1 diagnostic opt-out |
| 2026-07-29 | Complete JIT-1 in ART `146016f83e`: reject unrepresentable JIT-root and CodeInfo encodings before mutation; Windows Server 2025 build 26100 independently accepts the returned 28/28 W-004 regression archive with no dump |
| 2026-07-29 | Complete JIT-2 in root `b2ea7e89ff`: Windows Server 2025 build 26100 accepts nine native mapping/policy cases and 14 aggregate checks, including 1 GiB pressure, CFG, low-VA recovery, and graceful `ERROR_DYNAMIC_CODE_BLOCKED`; independent returned-archive review passes with no dump or JIT temp |
| 2026-07-29 | Fix the JIT-3 preflight's nterp JNI FP regression in ART `43f866830e`: quick and normal-JNI hard-float results remain in XMM0; RAX's Native-to-Runnable state value no longer becomes the Java float/double result |
| 2026-07-29 | Complete JIT-3/FS-3 in root `a741cfa8ab`: Windows Server 2025 build 26100 accepts four native lifecycle/unwind cases and independent returned-archive review with 52 collections, 1,344 compilations, 1,248 exact reuses, zero missing/stale/failed records, no dump, and no JIT temp; retain J-1 only through JIT-4 and remove it in JIT-5 |
| 2026-07-29 | Complete JIT-4 in root `a095f93d68`: Windows Server 2025 build 26100 accepts 28 default-J-2 cases and independent returned-archive review with 34/34 aggregate PASS records, eight lifecycle cycles, three valid static/JIT/OSR dumps, empty JIT temp, no trace, and no J-1 arm; authorize JIT-5 removal without claiming J-1 is already removed |
| 2026-07-29 | Complete JIT-5 with ART `389158d46f`: remove the Windows opt-out and single-view fallback, fail closed on section-construction errors, pass post-removal Wine/Linux gates, and independently accept 29 native cases plus 36/36 aggregate records on build 26100; close W-025 |

## 15. Code anchors

| Topic | Path |
|-------|------|
| JIT region initialization | `vendor/art/runtime/jit/jit_memory_region.cc` |
| JIT cache capacities and layout comment | `vendor/art/runtime/jit/jit_code_cache.{h,cc}` |
| Code write protection | `vendor/art/runtime/jit/jit_scoped_code_cache_write.h` |
| Windows mapping implementation | `vendor/art/libartbase/base/mem_map_windows.cc` |
| Generic `RemapAtEnd` | `vendor/art/libartbase/base/mem_map.cc` |
| Windows CPU-cache flush | `vendor/art/libartbase/base/utils.cc` |
| JIT root patching | `vendor/art/compiler/optimizing/code_generator_x86_64.cc`; `vendor/art/runtime/jit/jit_encoding.h` |
| CodeInfo offset | `vendor/art/runtime/jit/jit_encoding.h`; `vendor/art/runtime/jit/jit_memory_region.cc`; `vendor/art/runtime/oat/oat_quick_method_header.h` |
| Dynamic PE unwind metadata | `vendor/art/compiler/utils/x86_64/windows_x64_unwind_info.h`; `vendor/art/runtime/multiplatform/windows/jit_unwind_windows.*`; `vendor/art/runtime/jit/{jit_code_cache,jit_memory_region}.*` |
| D-1 Thread-address helper | `vendor/art/compiler/utils/x86_64/assembler_x86_64.*` |
| W-002 OSR entry adapters | `vendor/art/runtime/arch/x86_64/quick_entrypoints_x86_64.S`; `vendor/art/runtime/interpreter/mterp/x86_64ng/main.S` |
| W-003 frame-family/XMM acceptance | unified `managed_w003_frame` and `managed_w003_xmm_sentinel`; `tests/cases/w003-frame-probe/RESULT.md`; `tests/cases/w003-xmm-sentinel/RESULT.md`; `tests/stages/w003/ANALYSIS.md` |
| W-025 JIT-2 mapping/policy acceptance | `docs/history/windows_x64_w025_jit2_result.md` |
| W-025 JIT-3/FS-3 lifecycle/unwind acceptance | `docs/history/windows_x64_w025_jit3_result.md` |
| W-025 JIT-4 final native regression | `docs/history/windows_x64_w025_jit4_result.md` |
| W-025 JIT-5 removal and closure | `docs/history/windows_x64_w025_jit5_result.md` |
| nterp hard-float result adapter | `vendor/art/runtime/interpreter/mterp/x86_64ng/main.S` |
| JNI XMM argument moves | `vendor/art/compiler/utils/x86_64/jni_macro_assembler_x86_64.cc`; `assembler_x86_64_test.cc` |
| Native JIT gate | `vendor/art/runtime/jit/jit.cc` |
| dlmalloc configuration | `vendor/art/runtime/gc/allocator/art-dlmalloc.cc` |
| PE asm-defines generation | `tools/bp2cmake/bp2cmake/codegen.py`; `native/CMakeLists.txt` |

## 16. External API references

- [CreateFileMappingW](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-createfilemappingw): pagefile-backed sections, compatible view permissions, commit behavior, and coherent views.
- [MapViewOfFile3](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-mapviewoffile3): address requirements, page-size view sizing, and the Windows 10 version 1803 minimum.
- [MEM_ADDRESS_REQUIREMENTS](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-mem_address_requirements): inclusive high address and allocation-granularity rules.
- [VirtualProtect](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualprotect): mapped-view protection compatibility and the requirement to flush the instruction cache for generated code.
