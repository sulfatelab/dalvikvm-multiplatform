# Win64 JIT memory and codepath — current design and implementation plan

**Status:** P3+P4 complete under J-1; P5 design revised for Linux-parity dual mapping
**Updated:** 2026-07-23
**Target baseline:** Windows 10 version 1803 or later (NTDDI_WIN10_RS4)
**Related:** [win32_tls_jit_entrypoints.md](win32_tls_jit_entrypoints.md), [win32_open_items.md](win32_open_items.md), Phase 5 JIT

## 0. Executive decision

The Win64 port shall keep ART behavior and shared ART source as close to Linux as
practical. Windows-specific behavior belongs in the platform compatibility
layer, especially `memfd` and `MemMap`, rather than in the JIT allocator or
x86_64 compiler.

The selected end state is:

1. Implement Windows `art::memfd_create()` with delete-on-close temporary-file
   semantics.
2. Implement Windows 10 placeholder-backed shared mappings and fixed-address
   remapping in `MemMap`.
3. Make Windows follow ART's existing fd-backed dual-view path in
   `JitMemoryRegion::Initialize`.
4. Remove the experimental Win32 J-2 allocation branch after the common path is
   verified.
5. Keep ART's ordinary single-view RWX-toggle path only as the same fallback
   that Linux ART permits when RWX memory is allowed.

This supersedes the earlier recommendation to move stack maps into the code
arena. Moving stack maps alone cannot fix the observed J-2 crash because JIT
root-table references have a stricter signed 32-bit displacement requirement.

## 1. Current product baseline

Measured on agent01 under Wine:

| Item | Current state |
|------|---------------|
| Quick invoke | ON by default |
| Nterp | ON after runtime startup; rSELF=r15 and rREFS=rbp |
| Managed JIT | ON by default under J-1 |
| J-1 Hello | About 24 managed compilations; PASS |
| J-1 smoke | 10/10 |
| J-1 probe matrix | 14/14 |
| Native JIT | Gated off; `ART_WIN64_JIT_NATIVE=1` exposes the FastNative ABI defect |
| J-2 experiment | Opt-in with `ART_WIN64_JIT_DUAL=1`; Hello runs, full matrix is not green |
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

### 2.2 Single-view fallback

When shared dual mapping is unavailable and RWX memory is permitted, ART maps
one anonymous data+code reservation and splits it:

```text
[ data RW ][ code RX ]
                  ↕
       RX -> RWX -> RX during updates
```

This is the current working J-1 implementation on Windows. It is correct but
has an RWX update window, so it is not the preferred P5 end state.

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

## 4. Corrected J-2 FloatProbe diagnosis

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

### 5.1 J-1: working single-view fallback

J-1 maps one low-address anonymous reservation with `VirtualAlloc`.
`MemMap::RemapAtEnd` changes protection on the tail and represents it as a
reuse view.

Verified:

- managed JIT Hello;
- JIT smoke 10/10;
- probe matrix 14/14;
- code-cache collection paths used by the existing tests.

Temporary difference from the desired dual-view path:

- code updates use an RX-to-RWX-to-RX protection transition.

### 5.2 J-2: experimental pagefile-section branch

The current opt-in implementation creates separate section views:

- low-address primary data view;
- high-address executable view;
- high-address non-executable code updater;
- high-address writable data alias.

The views are coherent, and Hello can compile and run. However, the primary data
and executable views are not contiguous, violating §3.

J-2 remains diagnostic-only until replaced. `ART_WIN64_JIT_DUAL=1` is a
temporary workaround, not the selected product architecture.

## 6. Selected Windows 10 compatibility design

### 6.1 Effective minimum version

The port no longer targets Windows 7. The mapping design uses:

- `VirtualAlloc2`: Windows 10;
- `UnmapViewOfFile2`: Windows 10 version 1703;
- `MapViewOfFile3` placeholder replacement: Windows 10 version 1803.

The effective minimum is therefore Windows 10 version 1803
(`NTDDI_WIN10_RS4`). The build should define and document this baseline rather
than carrying runtime branches for older Windows releases.

Wine 10 on agent01 exports all three APIs. Their placeholder behavior still
requires focused tests before the common path is enabled.

### 6.2 Windows `art::memfd_create`

Implement the Windows branch of `art::memfd_create` as a private,
delete-on-close temporary file:

1. Generate a unique path in the Windows temporary directory.
2. Open with `CreateFileW(CREATE_NEW)`.
3. Request `GENERIC_READ | GENERIC_WRITE | GENERIC_EXECUTE` so the same backing
   file can create RW and RX mapping objects.
4. Use `FILE_ATTRIBUTE_TEMPORARY | FILE_FLAG_DELETE_ON_CLOSE`.
5. Convert the handle to a CRT fd with `_open_osfhandle`.
6. Map `MFD_CLOEXEC` to a non-inheritable handle.
7. Keep sealing unsupported; desktop Windows has no zygote requirement and
   `IsSealFutureWriteSupported()` remains false.

This is intentionally an fd-compatible implementation. It lets existing ART
code continue to use `ftruncate`, `MapFile`, `unique_fd`, and ordinary file
lifetime rules.

The file is a compatibility backing store rather than a persistent artifact:
`FILE_ATTRIBUTE_TEMPORARY` encourages cache-backed operation, and
`FILE_FLAG_DELETE_ON_CLOSE` removes it after the last handle closes, including
normal crash cleanup.

### 6.3 Placeholder-backed `MapFile`

For shared low-address file mappings:

1. Reserve the complete virtual range with:

   ```text
   VirtualAlloc2(
       MEM_RESERVE | MEM_RESERVE_PLACEHOLDER,
       PAGE_NOACCESS,
       address requirements below 4 GiB)
   ```

2. Replace the placeholder with the file mapping using `MapViewOfFile3` and
   `MEM_REPLACE_PLACEHOLDER`.
3. Treat failure to satisfy `low_4gb=true` as a mapping failure. Do not silently
   place the view at a high address.

The Windows allocation granularity is normally 64 KiB. File offsets and view
boundaries used by the JIT path must be checked or rounded consistently to that
granularity.

### 6.4 Placeholder-backed `RemapAtEnd`

To emulate Linux `mmap(MAP_FIXED)` over the tail:

1. Convert the complete mapped view back to a placeholder with:

   ```text
   UnmapViewOfFile2(..., MEM_PRESERVE_PLACEHOLDER)
   ```

2. Split the placeholder at the data/code divider using:

   ```text
   VirtualFree(..., MEM_RELEASE | MEM_PRESERVE_PLACEHOLDER)
   ```

3. Replace the prefix with the file's data range as read-only.
4. Replace the tail with the file's code range as read/execute.
5. Preserve one owner per real view and avoid double unmapping.
6. On partial failure, restore or release all placeholders before returning.

The placeholder keeps the address range reserved throughout the operation, so
another thread cannot claim the tail between unmap and replacement. This is the
Windows 10 equivalent of the atomic-address property ART expects from
`MAP_FIXED`.

### 6.5 Other platform semantics

- `MemMap::MadviseDontFork()` returns success on Windows because there is no
  `fork()` inheritance to suppress.
- `MadviseDontNeedAndZero` remains a best-effort Windows operation.
- `FlushInstructionCache` may be added as explicit hardening after code commit;
  x86 instruction/data caches are coherent, so it is not the current blocker.
- Windows desktop has no JIT zygote. Sealing remains out of scope.

### 6.6 Resulting common ART flow

After the platform layer is complete:

1. `art::memfd_create("jit-cache", 0)` succeeds.
2. `JitMemoryRegion::Initialize` enters the existing fd-backed branch.
3. ART creates the writable data and code aliases.
4. ART maps one primary data+code range below 4 GiB.
5. `RemapAtEnd` creates the contiguous RX code tail.
6. `HasDualCodeMapping()` becomes true.
7. JIT commits write through the non-executable alias and execute through RX.

No Win32-specific JIT allocation algorithm is required.

## 7. Implementation and commit plan

### Stage 1 — declare the Windows 10 baseline

- Set `_WIN32_WINNT=0x0A00`.
- Set `NTDDI_VERSION=NTDDI_WIN10_RS4`.
- Document Windows 10 version 1803 as the minimum.
- Add a small API-availability build test.

Planned commit:

```text
win64: require Windows 10 RS4 for virtual-memory placeholders
```

### Stage 2 — implement Windows memfd semantics

- Implement `art::memfd_create`.
- Add create, truncate, read/write, mapping, close, and delete-on-close tests.
- Verify executable mapping creation from the returned fd.

Planned commit:

```text
win64: implement delete-on-close memfd backing
```

### Stage 3 — implement placeholder-backed mappings

- Implement low-address placeholder reservation.
- Implement `MapViewOfFile3` replacement.
- Implement file-backed `RemapAtEnd` split and cleanup.
- Make `MadviseDontFork` a successful no-op.
- Add ownership, failure-injection, and repeated map/unmap tests.

Planned commit:

```text
win64: emulate MAP_FIXED file remaps with placeholders
```

### Stage 4 — route JIT through the common path

- Remove or bypass the current J-2 initialization branch.
- Verify Windows takes the same fd-backed `JitMemoryRegion` branch as Linux.
- Add permanent address-range checks.
- Keep J-1 as the normal ART fallback while validation is incomplete.

Planned commit:

```text
win64: use the common ART dual-view JIT memory path
```

### Stage 5 — verification and cleanup

- Run the full acceptance matrix in §12.
- Validate on real Windows 10.
- Remove unused `CreatePageFileSection`/`MapFileSection` helpers and the
  `ART_WIN64_JIT_DUAL` gate.
- Make dual view the default; retain only the common ART single-view fallback.
- Update W-025 and test-result documents.

Planned commits:

```text
win64: remove the experimental J-2 section branch
win64: document dual-view JIT verification
```

Each stage should be committed only after its focused tests pass cleanly.

## 8. Alternatives reconsidered

| Plan | Linux similarity | Risk | Verdict |
|------|------------------|------|---------|
| Common memfd + `MemMap` placeholders | Highest | Medium platform work | **Selected** |
| Pagefile section + placeholders in a Win32 JIT branch | Same layout, different JIT source | Medium | Fallback prototype |
| Keep J-1 as permanent default | Common fallback behavior, weaker W^X | Low | Interim only |
| Far-address JIT roots + extended CodeInfo header | Low; Win-only compiler/runtime format | High | Rejected |
| Move roots and stack maps into code arena | Low; allocator/GC divergence | High | Rejected |
| Move stack maps only | Does not fix JIT-root displacement | Incorrect | Rejected |
| Force every section view below 4 GiB | Wastes scarce low VA and still duplicates JIT logic | High fragmentation | Rejected |

If the delete-on-close memfd backing proves unreliable, the fallback design is
a pagefile-backed section using the same placeholder-created
`[data R][code RX]` primary layout. That fallback must preserve the layout
invariants; it must not return to arbitrary separated primary views.

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

These bugs are specific to the experimental branch and disappear when Windows
uses the common fd-backed initialization flow.

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

The J-2 failure is not evidence of incomplete D-1 work.

### 11.2 Native JIT remains separate

JIT compilation of native methods is gated off by default. The compiled
FastNative path still mixes ART's managed convention with MS x64 native
argument placement and produces invalid multi-argument calls.

The memory plan does not change this blocker. Enablement requires a separate
FastNative ABI design and test stage.

## 12. Verification and acceptance

### 12.1 Platform-memory tests

- Windows memfd create and automatic deletion.
- `ftruncate` to 64 MiB.
- Multiple coherent RW/R/RX mappings of one fd.
- Placeholder reservation below 4 GiB.
- Placeholder split and exact replacement.
- Repeated map/remap/unmap without leaks or double unmaps.
- Failure injection after each placeholder operation.
- RW alias writes visible through the RX view.
- Execute a small function written through the RW alias.

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

- JIT code cache creation through the fd-backed path.
- Hello under default managed JIT.
- FloatProbe with `-Xjitthreshold:0`.
- Full `run_jit_smoke.sh`.
- Full `run_jit_matrix.sh`.
- ThrowProbe to exercise CodeInfo decoding.
- GcProbe to exercise JIT root updates.
- Small-cache collection and code-reuse stress.
- Repeated cold starts to vary ASLR placement.
- J-1 regression run while the fallback remains.
- `ART_WIN64_JIT=0` interpreter/nterp regression.

### 12.4 Host acceptance

Wine success is necessary but insufficient. Before removing the experimental
gate and declaring P5 complete:

- validate on real Windows 10 version 1803 or later;
- repeat mapping protection inspection;
- run the smoke and probe matrices;
- exercise code-cache collection under load.

Native-JIT tests remain excluded until the FastNative ABI item closes.

## 13. Current status — 2026-07-23

### Done

| Item | Evidence |
|------|----------|
| J-1 single-view memory | JIT smoke 10/10; matrix 14/14 |
| D-1 r15 compiler TLS | 37/37 GS sites audited |
| Managed JIT default | Hello about 24 compilations |
| J-2 section primitives | RW/RX coherence and Hello about 21 compilations |
| dlmalloc configuration | `USE_LOCKS=0`; spin-lock experiment reverted |
| Root-cause correction | JIT-root signed displacement plus latent CodeInfo overflow |
| P5 architecture | Windows memfd + placeholder `MemMap` common path selected |

### Open

| Item | Blocker |
|------|---------|
| Common dual-view path | Windows memfd and placeholder remap implementation |
| J-2/default W^X-safe JIT | Common path plus full matrix |
| Real Windows acceptance | Host access and completed implementation |
| Native JIT | FastNative MS x64 ABI |

### Current test summary

| Test | J-1 | Experimental J-2 |
|------|-----|------------------|
| Hello | PASS | PASS |
| JIT smoke | 10/10 | Basic smoke passes with native JIT excluded |
| JIT matrix | 14/14 | Not green; FloatProbe/MathProbe/NetProbe expose layout failure |
| FloatProbe forced compile | PASS | VEH access violation |

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
| 2026-07-23 | Drop Windows 7 support; select Windows 10 RS4 placeholder APIs |
| 2026-07-23 | Select Windows memfd + `MemMap` compatibility work so JIT uses the common Linux fd-backed path |

## 15. Code anchors

| Topic | Path |
|-------|------|
| JIT region initialization | `vendor/art/runtime/jit/jit_memory_region.cc` |
| JIT cache capacities and layout comment | `vendor/art/runtime/jit/jit_code_cache.{h,cc}` |
| Code write protection | `vendor/art/runtime/jit/jit_scoped_code_cache_write.h` |
| Windows mapping implementation | `vendor/art/libartbase/base/mem_map_windows.cc` |
| Generic `RemapAtEnd` | `vendor/art/libartbase/base/mem_map.cc` |
| Windows memfd implementation point | `vendor/art/libartbase/base/memfd.cc` |
| Win POSIX `ftruncate` bridge | `compat/src/win64_posix_stubs.c` |
| JIT root patching | `vendor/art/compiler/optimizing/code_generator_x86_64.cc` |
| CodeInfo offset | `vendor/art/runtime/oat/oat_quick_method_header.h` |
| D-1 Thread-address helper | `vendor/art/compiler/utils/x86_64/assembler_x86_64.*` |
| Native JIT gate | `vendor/art/runtime/jit/jit.cc` |
| dlmalloc configuration | `vendor/art/runtime/gc/allocator/art-dlmalloc.cc` |
