# Win64 JIT memory and codepath — current design and status

**Status:** P5 Wine implementation complete; pagefile-backed dual mapping is the default
**Updated:** 2026-07-23
**Target baseline:** Windows 10 version 1803 or later (NTDDI_WIN10_RS4)
**Related:** [win32_tls_jit_entrypoints.md](win32_tls_jit_entrypoints.md), [win32_open_items.md](win32_open_items.md), Phase 5 JIT

## 0. Executive decision

The Win64 port shall keep ART's observable memory layout and shared JIT logic as
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
5. Keep `ART_WIN64_JIT_DUAL=0` temporarily as a diagnostic J-1 opt-out until
   real-Windows acceptance is complete, then remove the gate.
6. Keep ART's ordinary single-view RWX-toggle path temporarily as a Windows
   diagnostic fallback; it is not the default product path.

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
| Managed JIT | ON by default with the corrected section dual view |
| Default Hello | About 21–24 managed compilations; PASS |
| Default JIT smoke | 10/10 |
| Default probe matrix | 14/14 |
| Native JIT | Gated off; `ART_WIN64_JIT_NATIVE=1` exposes the FastNative ABI defect |
| J-1 fallback | Diagnostic opt-out with `ART_WIN64_JIT_DUAL=0`; Hello passes |
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

### 2.3 Single-view fallback

When shared dual mapping is unavailable and RWX memory is permitted, ART maps
one anonymous data+code reservation and splits it:

```text
[ data RW ][ code RX ]
                  ↕
       RX -> RWX -> RX during updates
```

This remains the J-1 diagnostic/failure fallback on Windows. It is correct but
has an RWX update window, so it is no longer the product default.

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
- JIT smoke 10/10;
- probe matrix 14/14, including FloatProbe, ThrowProbe, and GcProbe;
- explicit Windows `FlushInstructionCache` for generated code;
- low-space fragmentation and non-64-KiB capacities in the permanent section
  probe.

### 5.2 J-1: single-view diagnostic fallback

J-1 maps one low-address anonymous reservation with `VirtualAlloc`.
`MemMap::RemapAtEnd` changes protection on the tail and represents it as a
reuse view.

Verified:

- managed JIT Hello;
- JIT smoke 10/10;
- probe matrix 14/14;
- code-cache collection paths used by the existing tests.

The fallback differs from the default dual-view path:

- code updates use an RX-to-RWX-to-RX protection transition.

Select this path only for comparison with `ART_WIN64_JIT_DUAL=0`.

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

### 6.7 Implemented safeguards and residual risks

- Windows `FlushCpuCaches` uses `FlushInstructionCache` for generated code.
- Runtime `VirtualQuery` checks verify R/RX and RW/RW roles; the updater alias
  never gains execute permission.
- Low-address allocation failure is a real dual-view failure and never permits
  a high primary view.
- The implementation uses no temporary file, pseudo-fd table, placeholder
  split/remap transaction, or Windows-only 64 KiB JIT-capacity rule.
- Remaining work is real-Windows repeated-start testing, dynamic-code/CFG
  policy testing, large `SEC_COMMIT` pressure measurement, and direct release
  checks at the JIT-root and CodeInfo encoding sites.
- Native JIT remains gated independently until the FastNative MS x64 ABI
  problem is fixed.

## 7. Implementation and commit status

### Stage 1 — declare the Windows 10 baseline

- Set `_WIN32_WINNT=0x0A00`.
- Set `NTDDI_VERSION=NTDDI_WIN10_RS4`.
- Link `onecore.lib` for `MapViewOfFile3`.
- Add a build-and-run API probe under Wine.

Completed:

```text
win64: require Windows 10 RS4 for constrained section views
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
win64: add constrained pagefile-section views
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
win64: build contiguous JIT dual views from one section
```

### Stage 4 — verify and make dual view the default

- Run the complete acceptance matrix in §12 under Wine.
- Include fragmented-low-space and non-64-KiB capacity cases.
- Add permanent mapping layout and protection checks.
- Make the corrected section path default; retain J-1 temporarily as a
  diagnostic opt-out.

Completed:

```text
win64: enable contiguous dual-view JIT memory by default
```

### Stage 5 — real-Windows acceptance and cleanup

- Validate on real Windows 10.
- Remove the temporary `ART_WIN64_JIT_DUAL=0` diagnostic gate.
- Confirm no temporary file is created and no view is RWX.
- Add direct signed-int32 JIT-root and uint32 CodeInfo construction checks.
- Update W-025 and test-result documents.

Planned commits:

```text
win64: remove the dual-view diagnostic opt-out
win64: document dual-view JIT verification
```

Each stage should be committed only after its focused tests pass cleanly.

## 8. Alternatives reconsidered

| Plan | Linux similarity | Risk | Verdict |
|------|------------------|------|---------|
| Pagefile section + two complete views | Same topology and JIT behavior; one mapping hook differs | Low-medium | **Selected** |
| Pagefile section + four placeholder views | Exact independent OS views | Medium; 64 KiB split rules and more cleanup | Rejected as unnecessary |
| Temporary-file memfd + placeholder remap | Reuses fd branch | High lifecycle and rollback complexity; creates a filesystem object | Rejected |
| Keep J-1 as permanent default | Common fallback behavior, weaker W^X | Low | Interim only |
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
the supplied memory. It does not independently allocate virtual memory.

The selected ART configuration is:

- `USE_LOCKS=0` for ART's embedded dlmalloc;
- JIT mspaces serialized by `Locks::jit_lock_`;
- heap mspaces protected by ART-level locks.

Internal dlmalloc locks are redundant here. A temporary
`USE_SPIN_LOCKS=1` experiment was reverted after Wine regressions.

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

R15 is pinned as rSELF and removed from the Win64 allocatable callee-saves.
`X86_64Assembler::gs()` emits no GS prefix on Windows.

The historical separated-J-2 failure was not evidence of incomplete D-1 work.

### 11.2 Native JIT remains separate

JIT compilation of native methods is gated off by default. The compiled
FastNative path still mixes ART's managed convention with MS x64 native
argument placement and produces invalid multi-argument calls.

The memory plan does not change this blocker. Enablement requires a separate
FastNative ABI design and test stage.

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
- Full `run_jit_smoke.sh`.
- Full `run_jit_matrix.sh`.
- ThrowProbe to exercise CodeInfo decoding.
- GcProbe to exercise JIT root updates.
- Small-cache collection and code-reuse stress.
- Repeated cold starts to vary ASLR placement.
- Custom page-aligned JIT maximum sizes that are not 64 KiB aligned.
- J-1 regression run while the fallback remains.
- `ART_WIN64_JIT=0` interpreter/nterp regression.

### 12.4 Host acceptance

Wine success is necessary but insufficient. Before removing the diagnostic
gate and declaring P5 complete:

- validate on real Windows 10 version 1803 or later;
- repeat mapping protection inspection;
- run the smoke and probe matrices;
- exercise code-cache collection under load.

Native-JIT tests remain excluded until the FastNative ABI item closes.

### 12.5 Threshold-zero stress finding

`FloatProbe -Xjitthreshold:0` currently fails in both J-1 and the corrected
dual-view path at `ArtMethod::GetOatQuickMethodHeader()` with an invalid
`ArtMethod*`. The dual-view run faults with `fault_addr=0x100000009`; the J-1
control faults at the same instruction with `fault_addr=0x9`. This is a shared
aggressive-compilation/runtime issue, not the old separated-view displacement
or CodeInfo-layout defect. Standard FloatProbe and the full 14-probe matrix are
green on both memory paths.

The threshold-zero stress case remains open, but it does not justify retaining
the RWX J-1 path as the product default.

## 13. Current status — 2026-07-23

### Done

| Item | Evidence |
|------|----------|
| J-1 single-view memory | JIT smoke 10/10; matrix 14/14 |
| D-1 r15 compiler TLS | 37/37 GS sites audited |
| Managed JIT default | Corrected pagefile-section dual view; Hello about 21–24 compilations |
| Corrected dual-view integration | JIT smoke 10/10; matrix 14/14; protections checked with `VirtualQuery` |
| Section-layout probe | 64 MiB and non-64-KiB capacity cases pass under Wine; low primary remains contiguous under forced low-space fragmentation |
| dlmalloc configuration | `USE_LOCKS=0`; spin-lock experiment reverted |
| Root-cause correction | JIT-root signed displacement plus latent CodeInfo overflow |
| PE asm definitions | Windows-target generator test enforces `RUNTIME_INSTRUMENTATION_OFFSET=0x328` |

### Open

| Item | Blocker |
|------|---------|
| Real Windows acceptance | Host access; Wine implementation and matrix are complete |
| Threshold-zero stress | Invalid `ArtMethod*` in both J-1 and dual view |
| Direct encoding checks | Add checks at JIT-root patch and CodeInfo construction sites |
| Native JIT | FastNative MS x64 ABI |

### Current test summary

| Test | J-1 opt-out | Default corrected dual view |
|------|------------|-----------------------------|
| Hello | PASS | PASS |
| JIT smoke | 10/10 | 10/10 |
| JIT matrix | 14/14 | 14/14 |
| FloatProbe normal threshold | PASS | PASS |
| FloatProbe `-Xjitthreshold:0` | Shared `GetOatQuickMethodHeader` failure | Shared `GetOatQuickMethodHeader` failure |

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

## 15. Code anchors

| Topic | Path |
|-------|------|
| JIT region initialization | `vendor/art/runtime/jit/jit_memory_region.cc` |
| JIT cache capacities and layout comment | `vendor/art/runtime/jit/jit_code_cache.{h,cc}` |
| Code write protection | `vendor/art/runtime/jit/jit_scoped_code_cache_write.h` |
| Windows mapping implementation | `vendor/art/libartbase/base/mem_map_windows.cc` |
| Generic `RemapAtEnd` | `vendor/art/libartbase/base/mem_map.cc` |
| Windows CPU-cache flush | `vendor/art/libartbase/base/utils.cc` |
| JIT root patching | `vendor/art/compiler/optimizing/code_generator_x86_64.cc` |
| CodeInfo offset | `vendor/art/runtime/oat/oat_quick_method_header.h` |
| D-1 Thread-address helper | `vendor/art/compiler/utils/x86_64/assembler_x86_64.*` |
| Native JIT gate | `vendor/art/runtime/jit/jit.cc` |
| dlmalloc configuration | `vendor/art/runtime/gc/allocator/art-dlmalloc.cc` |
| PE asm-defines generation | `tools/bp2cmake/bp2cmake/codegen.py`; `tools/verify/win64_phase1/CMakeLists.txt` |

## 16. External API references

- [CreateFileMappingW](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-createfilemappingw): pagefile-backed sections, compatible view permissions, commit behavior, and coherent views.
- [MapViewOfFile3](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-mapviewoffile3): address requirements, page-size view sizing, and the Windows 10 version 1803 minimum.
- [MEM_ADDRESS_REQUIREMENTS](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-mem_address_requirements): inclusive high address and allocation-granularity rules.
- [VirtualProtect](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualprotect): mapped-view protection compatibility and the requirement to flush the instruction cache for generated code.
