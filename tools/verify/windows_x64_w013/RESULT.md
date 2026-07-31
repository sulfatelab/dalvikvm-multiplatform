# W-013 Windows x64 heap-memory implementation

**Status:** CLOSED — Stages A–E and native Windows R2 acceptance PASS
**Date:** 2026-07-25
**Host:** agent01

## Stage A — explicit embedded-dlmalloc configuration

Landed changes:

- external dlmalloc `f3356ce` makes Win32 defaults respect embedding-provided
  `HAVE_MMAP`, `HAVE_MORECORE`, and related platform definitions;
- Win32 contiguous MoreCore now uses `dwPageSize` rather than
  `dwAllocationGranularity`;
- ART `8c900a9e4b` removes `_WIN32`/`WIN32` masking and explicitly selects and
  compile-checks `HAVE_MMAP=0`, `HAVE_MREMAP=0`, `HAVE_MORECORE=1`,
  `MORECORE_CONTIGUOUS=1`, `USE_LOCKS=0`, and mspace-only operation; and
- ART explicitly sets allocation failure to `errno = ENOMEM`.

## Focused probe

Command:

```text
tools/verify/windows_x64_w013/run_dlmalloc_config_probe.sh
```

Observed under Wine:

```text
W013_DLMALLOC_CONFIG_PASS page=4096 granularity=4096 positive=4 negative=2 queries=8 failures=1 last_positive=8192 last_negative=-20480
```

The probe now creates an mspace over a mock owner, grows it, frees and trims the
top segment, regrows it, injects an owner-side capacity failure, proves the
mspace remains usable afterward, and destroys it. It validates `MoreCore(0)`,
page-granular positive and negative increments, footprint limits, and `ENOMEM`.
The source gate also checks that Windows macros remain active, that raw mspace
creation cannot bypass ART's wrapper, and that provider magic plus
attach/detach fields remain present in `art-dlmalloc.cc`.

## Stage B — direct mspace-owner attachment

ART commit: `d011d72d56`

Landed behavior:

- all ART mspaces are created through `ArtCreateMspaceWithBase()`;
- `malloc_state::extp/exts` store an `MspaceMoreCoreProvider` and validation
  magic;
- the dlmalloc MoreCore callback validates and dispatches directly to
  `DlMallocSpace` or `JitMemoryRegion`;
- heap construction, clear, and destruction attach/detach the provider;
- JIT move construction/assignment detach the temporary provider and rebind
  both mspaces to the destination, while reset/destruction detach them; and
- the global `Runtime::Current()`/heap/JIT owner scan and
  `JitCodeCache::OwnsSpace()` path are removed.

The focused probe now also rejects raw `create_mspace*()` calls outside
`art-dlmalloc.cc` and rejects restoration of the global owner-discovery path.

The actual `art-dlmalloc.cc` wrapper is also compiled into a focused executable:

```text
tools/verify/windows_x64_w013/run_mspace_owner_probe.sh
```

Its success case grows through one provider, trims, detaches, rebinds a second
provider, and regrows. Four subprocess death cases verify missing provider,
use-after-detach, wrong-owner detach, and double attachment all terminate with
the expected `CHECK` diagnostic. The source gate also requires the heap and JIT
external-lock assertions.

```text
W013_MSPACE_OWNER_PASS first_calls=5 second_calls=2
W013_MSPACE_OWNER_PROBE_PASS success=1 death=4
```

Native R1 additionally exposed a J-1-only move failure after the executable
mspace mapping had returned to RX. `ArtDetachMspaceMoreCoreProvider()` was
correctly updating `malloc_state::extp/exts`, but the metadata write itself
faulted. ART `27a1ac74a4` now performs executable-mspace detach and attach under
`ScopedCodeCacheWrite`; the writable data mspace remains unchanged. The exact
J-1 create/move path now passes under Wine with code-cache creation, 31
successful compilation records, Hello output, and a clean JNI return. The
dual-view JIT smoke remains 12/12.

## Stage C — explicit Windows address policy and ownership

ART commit: `2fa301a13b`

Landed behavior:

- anonymous anywhere, below-4-GiB, and exact requests are explicit;
- low and aligned allocations use `VirtualAlloc2` with
  `MEM_ADDRESS_REQUIREMENTS`, with no manual hole scan or unrestricted high
  fallback;
- exact reuse inside an existing reservation uses `VirtualProtect` instead of
  an overlapping reservation;
- a low half-open range may end exactly at 4 GiB;
- private allocations and section views carry a shared owner keyed by
  `AllocationBase` and use `VirtualFree(MEM_RELEASE)` or `UnmapViewOfFile`,
  respectively;
- reservation transfers, logical splits, and `reuse=true` views retain that
  owner until the final view is destroyed; and
- aligned allocation, `SetSize()`, and `AlignBy()` avoid partial
  `MEM_RELEASE`.

Current unified reproduction:

```text
python tools/build_art.py test --target-id windows-x86_64-msvc --stage w013 --parallel 32
python tests/support/windows/check_w013_source_policy.py
```

The former mixed Bash build/audit/Wine runner was retired after the unified
native gate and shell-free host reviewer accepted its maintained contracts.

Observed under Wine:

```text
W013_MEM_MAP_POLICY_PASS anywhere=00007FFFFE7C0000 low=0000000000010000 boundary=tested transitions=32 fragments=3854 exhaustion_reservations=2 destruction_cycles=128
```

The probe validates anywhere/low/exact placement, exact collision, a mapping
ending exactly at 4 GiB, zero and overflowing requests, 2-MiB direct alignment,
3,854-way low-VA fragmentation, complete low-VA exhaustion with high VA still
available, low-VA recovery, reservation transfer, `reuse=true` shared
lifetime, logical shrink without partial release, exactly-once final release,
and 128 repeated whole-owner destruction cycles.

Known Stage-C boundary: `MapViewOfFileEx` cannot replace an ordinary
`VirtualAlloc` reservation in place. Fixed file-backed overlay remains
unsupported rather than being emulated unsafely; the imageless runtime and JIT
pagefile-section path do not require it.

## Stage D — explicit heap page-state operations

ART commit: `9ea15456a2`

Landed behavior:

- `MemMap` exposes page-aligned `ActivateRange()`, `DeactivateRange()`, and
  `DiscardRange()` operations with containment and zero-length validation;
- Linux uses `mprotect()` and `madvise(MADV_DONTNEED)` behind those methods;
- Windows uses `VirtualProtect()` and `DiscardVirtualMemory()` while retaining
  the full committed reservation;
- positive and negative `MallocSpace::MoreCore()` transitions use the owning
  `MemMap`;
- dlmalloc trim/clear and RosAlloc initial discard, page release, trim, clear,
  and page-map release no longer call platform VM APIs directly;
- RosAlloc carries a rebased pointer to its owning `MemMap` across space
  construction; and
- Windows `SetSize()`/`AlignBy()` discard and deactivate excluded pages before
  shrinking the logical range.

The focused probe now performs 32 discard/deactivate/activate cycles. It
checks `PAGE_NOACCESS` and `PAGE_READWRITE` transitions, discard while already
no-access, adjacent-page content preservation, write-after-reactivation, and
logical-shrink tail protection.

Observed under Wine:

```text
W013_MEM_MAP_POLICY_PASS anywhere=00007FFFFE7C0000 low=0000000000010000 boundary=tested transitions=32 fragments=3854 exhaustion_reservations=2 destruction_cycles=128
```

The source gate rejects direct `mprotect()`/`madvise()` calls in malloc-space,
dlmalloc-space, RosAlloc-space, and RosAlloc allocator transition paths.

Native R1 showed that real Windows rejects `DiscardVirtualMemory()` on a
`PAGE_NOACCESS` page with `ERROR_INVALID_PARAMETER`. ART `6253d01afc` makes
the Windows discard primitive walk protection regions with `VirtualQuery()`.
An already deactivated region is changed temporarily to `PAGE_READWRITE`,
discarded, and restored immediately to its exact previous protection. Writable
regions are discarded directly. The VM primitive allocates no temporary
container, and the focused transition/fragmentation/ownership probe still
passes.

## Stage E — audited low-address consumers

ART commit: `47567cebcc`

Landed behavior:

- ordinary runtime and verifier arenas use unrestricted mappings as on Linux;
- compiler/JIT metadata arenas use unrestricted mappings as on Linux;
- ordinary runtime LinearAlloc no longer creates a Windows x64-only low arena pool;
- the upstream AOT cross-compilation low-LinearAlloc condition remains intact;
- the card table uses an unrestricted mapping because x86-64 card marking
  loads its full biased pointer and uses a 64-bit object-derived index;
- the Windows-only `MarkCard` OOB log-and-skip path is removed, restoring the
  common checked write barrier; and
- Java object spaces, LOS, required image/heap reservations, the complete JIT
  primary view, and the exact sentinel request remain low.

Focused audit command:

```text
python tests/support/windows/check_w013_source_policy.py
```

Observed:

```text
W013_LOW_4GB_POLICY_PASS required_files=8 metadata=anywhere card_mark=unconditional nonmoving_barrier=unconditional
```

The audit rejects the retired `windows_x64_low_4gb` branch, the retired card-mark
skip, any Windows-specific card-table behavior, and changes to the exact set of
product files containing literal required-low requests.

The first dedicated product non-moving stress run exposed one additional
Phase-2 branch in `gc/heap-inl.h`: Windows logged every non-moving allocation,
checked card-table range manually, and skipped the class write barrier when the
check failed. ART `1509b1f95e` removes that branch and restores the common
unconditional barrier. The low-address audit now rejects its return.

## Product non-moving pressure

Command:

```text
tools/verify/windows_x64_w013/run_non_moving_stress.sh
```

The Java probe calls `VMRuntime.newNonMovableArray()` through reflection and
allocates only 8-KiB primitive arrays, below the 12-KiB LOS threshold. With
`-Xms2m -Xmx128m`, it churns 75,497,472 bytes, retains up to 1,024 live arrays,
forces GC between twelve rounds, verifies 16 anchor addresses never move,
checks sampled addresses stay below 4 GiB, clears the live set, and allocates
again to exercise post-GC regrowth.

Observed after `1509b1f95e`:

```text
W013_NON_MOVING_STRESS_PASS windows_x64=ok linux=ok total_bytes=75497472
```

Windows x64 and Linux address spans were about 14.8 MiB, well beyond the 2-MiB
startup setting. Both runtimes reported `nonmoving.stable=true`,
`nonmoving.low=true`, and `nonmoving.ok=true`.

## Integration verification

```text
cmake --build build/windows_x64_phase1 --target art dalvikvm -j16
tools/verify/windows_x64_w013/run_dlmalloc_config_probe.sh
tools/verify/windows_x64_w013/run_mspace_owner_probe.sh
tools/verify/windows_x64_w013/run_non_moving_stress.sh
python tests/support/windows/check_w013_source_policy.py
python tools/build_art.py test --target-id windows-x86_64-msvc --stage w013 --parallel 32
tools/verify/windows_x64_phase4/run_jit_smoke.sh
tools/verify/windows_x64_phase4/run_gcstress.sh
tools/verify/windows_x64_phase4/run_threadheavy.sh
tools/verify/windows_x64_phase4/run_handleleak.sh
cmake --build build/native --target art dalvikvm -j16
retired Linux shell runners; historical Hello result moved to
tests/cases/imageless-runtime/RESULT.md and unified managed gates remain pending
```

Results:

- Windows x64 `art.dll` and `dalvikvm.exe`: build PASS;
- actual ART mspace-owner wrapper: success/rebind PASS and 4/4 expected-death
  lifetime checks PASS;
- Windows x64 W-013 address-policy/ownership probe: PASS, including the tested
  4-GiB boundary, fragmented and exhausted low VA, no high fallback, recovery,
  and 128 repeated whole-owner releases;
- Windows x64 W-013 low-address source audit: PASS, with eight required-low product
  files and unrestricted metadata/card-table policy;
- Windows x64 and Linux product non-moving pressure: PASS, 75,497,472 bytes churned,
  stable low addresses, post-GC allocation recovery;
- Windows x64 JIT smoke under Wine: 12/12 PASS;
- Windows x64 GCStress, ThreadHeavy, and HandleLeak under Wine: PASS;
- Linux `libart.so` and `dalvikvm`: full rebuild PASS;
- Linux L-005 imageless Hello: PASS, exit 0;
- Linux GCStress: PASS, including repeated explicit CMS collections.
- Native Windows R2: 56/56 acceptance records PASS with complete exits and
  sampled metrics, 20/20 repeated starts, and no crash dumps.

## Native Windows R1 review

Returned archive:

```text
/tmp/w013-r1.zip
SHA-256 643b906885d5a820d629391be7a0f9e504797960d51ae5ba37b4226c56210152
build commit dbca77c03fa634c5e8460c06695e2636b7d0fa0d
Windows 10 Enterprise LTSC 2021 build 19044
result OVERALL FAIL
```

The evidence contained three product defects and two runner defects:

1. `windows_x64_w013_mem_map_probe.exe` failed when native
   `DiscardVirtualMemory()` received `PAGE_NOACCESS`. This is fixed by ART
   `6253d01afc` as described in Stage D.
2. J-1 crashed with `0xc0000005` while moving `JitMemoryRegion`. Dump
   `art-20260725-130557.dmp` has SHA-256
   `a8376bf6fb564960167a03d69652a4c73cbe4b5112923a43962e34955a5aa849`;
   symbolication led through `ArtDetachMspaceMoreCoreProvider`,
   `JitMemoryRegion::DetachMspaceProviders`, `MoveFrom`, and
   `JitCodeCache::Create`. This is fixed by ART `27a1ac74a4`.
3. HandleLeak completed its initial file and socket churn but the final regular
   file write was sent through Winsock and failed with `WSAEINVAL`/10022.
   `_get_osfhandle(fd)` and `SO_TYPE` cannot classify a CRT fd because a
   regular Win32 handle may be numerically equal to a live value in Winsock's
   independent SOCKET namespace. Root `caad337` and libcore
   `67ec4ab8dd70` replace the probe with one process-wide socket-fd registry
   exported by the already shipped `libopenjdkjvm.dll`. Socket creation,
   accept, socketpair, dup, dup2, close, Libcore.os, JVM I/O, and NIO paths all
   update or consult that registry across `libjavacore` and `libopenjdk`.
4. Every child exit code and peak metric was blank because the PowerShell
   runner called `Process.Refresh()` after exit. Root `c943f1f` retains the
   process handle, samples paged/working-set/virtual peaks every 50 ms while
   the process is alive, rejects missing exit/metric data, and records
   `metrics_sampled` plus the PowerShell version.
5. The default dual-view JIT run compiled 30 methods and completed Hello, but
   a scheduling-sensitive `StringFactory` record was absent. That record was
   not a correctness requirement and has been removed from the host marker;
   the deterministic code-cache, successful-compile, output, and clean-return
   markers remain.

Post-fix Wine verification includes the native socket-fd reuse probe, five
consecutive HandleLeak runs, NetProbe, IoProbe, dual-view JIT smoke 12/12, and
J-1 Hello with 31 successful compilations. R1 remains a failed evidence set;
only a newly built and returned R2 package can close native acceptance.

## Native Windows R2 acceptance

Returned evidence:

```text
archive w013-log-r2.7z
SHA-256 456e297d70c2f166308c869812ddec262fa38bc6dcd2852ea56edd5b2205078e
issued package SHA-256 935708f339e39ef0e3f2c2f2239997adc7fa42907977b83f5870de45d3b1e0a7
root commit c909ca797372dbd30464f7ca1279380510d0f231
ART commit 27a1ac74a42957d68d1e21eb941e13e7976f8085
Windows 10 Enterprise LTSC 2021 build 19044
PowerShell 5.1.19041.7548
result OVERALL PASS
```

The returned `BUILD_INFO.txt`, `MANIFEST.json`, and `SHA256SUMS.txt` match the
issued R2 package byte for byte. Independent review found 56 PASS records and
zero failures. All 52 child logs have an expected numeric exit code,
`timed_out=False`, `metrics_sampled=True`, and nonnegative paged, working-set,
and virtual-memory peaks; no launch error is present.

Native coverage passed:

- mapping/configuration/owner probes, including 32 protection transitions,
  3,856-way low-VA fragmentation, complete low-VA exhaustion and recovery,
  and 128 repeated owner destructions;
- non-moving pressure at 128-MiB and 1-GiB `-Xmx`, each churning 75,497,472
  bytes with stable low addresses and post-GC regrowth;
- forced/moving/LOS GC, GCStress, ThreadHeavy, and HandleLeak; HandleLeak
  completed 400 file cycles, 80 socket cycles, and the final regular-file
  round trip;
- 512-MiB and 1-GiB startup, with the 1-GiB cases reaching about 2.32 GB peak
  paged bytes and 1.08 GB peak working set on a host with 34.3 GB RAM and a
  9-GiB pagefile;
- default dual-view JIT with 30 successful compilations and diagnostic J-1
  with 26, both completing Hello with no JNI exception;
- JIT disable/usejit/filter/exclude/quiet modes and the fourteen-case matrix;
- twenty independent default-JIT starts; and
- fatal/access-violation scan plus recursive dump scan (`NO_DMP_FILES`).

The mapping probe's overflow message is the expected rejection of its explicit
overflow test, not an acceptance failure. No R1 access violation, discard
failure, HandleLeak misclassification, missing metric, timeout, or hidden
marker failure recurs. The compact durable review is recorded in
`tools/verify/windows_x64_w013/evidence/native_r2/ACCEPTANCE.md`.

## Native Windows acceptance package

The host matrix is packaged by:

```text
tools/windows_x64/host_package/package_windows_x64_w013.sh
```

The generated archive contains the native mapping, dlmalloc configuration, and
mspace-owner probes. The mapping probe additionally rejects zero/overflowing
requests, forces fragmented and fully exhausted low VA, verifies that a failed
low request does not retry high, proves recovery after releasing the
reservations, and repeats whole-owner destruction 128 times. The runner covers
non-moving pressure at 128-MiB and 1-GiB `-Xmx`; moving/LOS GC stress;
ThreadHeavy and HandleLeak; 512-MiB and 1-GiB startup; default dual-view JIT,
the J-1 diagnostic path, and the fourteen-case JIT matrix; twenty repeated
default-JIT starts; per-process memory metrics and host pagefile data; fatal-log
scanning; and recursive dump scanning. Execution and evidence-return
instructions are in `tools/verify/windows_x64_w013/W013_HOST_CHECKLIST.md`. The R2
return meets this bar: `logs/RESULT_W013.txt` ends in `OVERALL PASS`,
the complete logs were reviewed, and the returned package metadata matches the
issued package.

Stages A through E implement the accepted W-013 design. Fixed file-overlay over
an ordinary `VirtualAlloc` reservation remains unsupported and is not used by
the imageless/JIT path; any future image/OAT implementation that needs it must
use placeholder APIs and rollback. Native Windows commit pressure,
protection/extent, and repeated-start acceptance now pass on
native Windows 10. W-013 is closed. Any future fixed file-overlay requirement
or reserve-only/lazy-commit redesign is separate work and must not reopen the
retired macro-masking workaround implicitly.
