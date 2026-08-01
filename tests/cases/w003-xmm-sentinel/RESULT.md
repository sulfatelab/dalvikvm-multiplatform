# W-003 Microsoft XMM nonvolatile sentinel

**Status:** W-003 six-register checkpoint and W-010 full-width XMM6-XMM15
follow-up accepted on native Windows

**Date:** 2026-07-26

**Updated:** 2026-08-01

**Host:** agent01

## Target status

| Target ID | Applicable | Build | Runtime | Last accepted |
|---|---:|---:|---:|---|
| `windows-x86_64-msvc` | yes | verified | verified | 2026-08-01 |
| `windows-aarch64-msvc` | no | not applicable | not applicable | — |
| `windows-arm64ec-msvc` | no | not applicable | not applicable | — |

This test is intrinsically Microsoft x86-64-specific: its contract names
XMM6-XMM15, uses PE x86-64 unwind directives, and validates AMD64 relocations.
An AArch64 SIMD preservation test requires a separate logical ID and source.

## Contract tested

`art_quick_invoke_stub`, `art_quick_invoke_static_stub`, and
`art_quick_osr_stub` are ordinary Microsoft-x64 entries into ART managed code.
The Microsoft ABI requires the lower 128 bits of XMM6-XMM15 to survive, while
ART managed x86-64 preserves only 64-bit scalar XMM12-XMM15 state. W-003
originally added an explicit boundary save for XMM6-XMM11. W-010 now expands
that Windows-only adapter to the complete XMM6-XMM15 set without changing ART
managed frames or the Linux path.

The focused probe does not depend only on C compiler register allocation. Its
PE assembly wrapper:

1. emits `.pdata`/`.xdata` for its own 200-byte Microsoft-ABI frame;
2. saves the native caller's XMM6-XMM15 values;
3. seeds ten distinct 128-bit patterns;
4. calls a twelve-double, high-FP-pressure Java method through
   `CallStaticIntMethod` and the normal JNI quick-invoke path;
5. compares every byte of every register and returns a ten-bit mismatch mask;
   and
6. restores the original native caller state before returning.

The Java probe also requests one intentional post-callback clobber. The
checker must return `0x3ff` for that self-test while returning zero for all
normal calls. Java retains `selfTestMask=63` as the historical W-003
compatibility field and reports `fullSelfTestMask=1023` as the authoritative
full-width result. This rejects a probe whose comparison path was optimized
away or wired to only a subset of the registers.

## Structural checks

The unified `windows_w003_quick_boundary_structure` reviewer verifies:

- the JNI symbol is exported from `libw003xmmsentinel.dll`;
- the PE object reserves/releases exactly 200 bytes;
- XMM6 and XMM15 endpoint saves/restores surround the callback;
- the callback relocation targets `W003InvokeManagedCallback`; and
- PE unwind information names both sentinel functions and records exactly
  twenty `SAVE_XMM128` operations.

It consumes explicit frontend-resolved host LLVM tools, so a Linux-hosted
Windows cross build does not append the target `.exe` suffix. The following
retired-runner description is retained as historical context; the standalone
shell path is no longer maintained. It verified:

- the JNI symbol is exported from `libw003xmmsentinel.dll`;
- the PE object reserves/releases exactly 200 bytes;
- XMM6 and XMM15 endpoint saves/restores are present around the callback;
- the callback relocation targets `W003InvokeManagedCallback`; and
- PE unwind information names `W003XmmSentinelAssembly` and records all ten
  `SAVE_XMM128` operations.

The compiled C callback object uses XMM3 for the first floating argument and
does not add its own XMM6-XMM15 spill around `CallStaticIntMethod`, so the
sentinel observes the ART boundary rather than a compiler-generated local
repair.

## Historical Wine matrix

The retired compatibility runner executed two repetitions in each mode. Its
accepted result was:

```text
W-003 XMM sentinel nterp run=1 PASS
W-003 XMM sentinel nterp run=2 PASS
W-003 XMM sentinel switch run=1 PASS
W-003 XMM sentinel switch run=2 PASS
W-003 XMM sentinel jit run=1 PASS
W-003 XMM sentinel jit run=2 PASS
W-003 XMM sentinel acceptance: nterp/switch/JIT, 2 repeat(s): PASS
```

Each process reports:

```text
mask=0 selfTestMask=63 iterations=128
fullSelfTestMask=1023
main end exception=0
```

The JIT pair additionally records successful baseline compilation of
`W003XmmSentinelProbe.managedCallback(double, ... double)`.

## Native Windows acceptance

The unified product `stage:w003` and exact frame-attribution variant each ran
the nterp, switch, and threshold-zero JIT modes twice on Windows Server 2025
x86-64. All six processes in each tree reported `mask=0`,
`selfTestMask=63`, `fullSelfTestMask=1023`, `exceptionMask=0`, and
`exceptionSelfTestMask=1023`; both JIT processes emitted the required normal
and exception-callback compile records. Product passed 4/4 CTest gates and the
variant passed 5/5, then both repeated as Ninja no-ops. Each XMM aggregate
contains six successful runs, no dumps, and no machine absolute paths.

The records below remain historical native-package and E9 acceptance context.

The accepted Windows 10 build 19044 evidence predates the W-010 expansion and
passes the original XMM6-XMM11 sentinel 2/2 in nterp, switch, and threshold-zero
JIT modes. All six runs report a zero normal mismatch mask, the exact six-bit
intentional-clobber mask, zero pending exception, and exit zero. Both JIT runs
compile the twelve-double managed callback through the corrected Windows
pagefile-section dual view.

The separate four-family managed-frame probe also passes 8/8 on the same
native host; see the adjacent
[frame-family result](../w003-frame-probe/RESULT.md).
Fatal-marker and recursive dump scans are clean. The complete accepted return
and its immutable identities are documented in the
[W-003 analysis](../../stages/w003/ANALYSIS.md), and W-003 is closed. The
historical accepted logs are intentionally not rewritten.

E9 subsequently performs the strengthened ten-register repetition on Windows
Server 2025 build 26100. Nterp, switch, and threshold-zero JIT each pass two
runs with `mask=0`, the retained `selfTestMask=63`, and authoritative
`fullSelfTestMask=1023`. These six cases are part of the accepted 30/30
W-010/W-014 package described in
[E9 acceptance](../../../docs/history/windows_x64_w010_w014_e9_result.md).

## Related files

- `probe.c`
- `sentinel_x86_64.S`
- `W003XmmSentinelProbe.java`
- `../../../tests/support/windows/w003_managed_gate.py`
- `../../stages/w003/ANALYSIS.md`
