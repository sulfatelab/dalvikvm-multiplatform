# W-003 Microsoft XMM nonvolatile sentinel

**Status:** NATIVE WINDOWS ACCEPTED — W-003 closed

**Date:** 2026-07-26

**Host:** agent01

## Contract tested

`art_quick_invoke_stub`, `art_quick_invoke_static_stub`, and
`art_quick_osr_stub` are ordinary Microsoft-x64 entries into ART managed code.
The Microsoft ABI requires the lower 128 bits of XMM6-XMM15 to survive, while
ART managed x86-64 preserves only XMM12-XMM15. W-003 therefore added an
explicit boundary save for XMM6-XMM11.

The focused probe does not depend only on C compiler register allocation. Its
PE assembly wrapper:

1. emits `.pdata`/`.xdata` for its own 136-byte Microsoft-ABI frame;
2. saves the native caller's XMM6-XMM11 values;
3. seeds six distinct 128-bit patterns;
4. calls a twelve-double, high-FP-pressure Java method through
   `CallStaticIntMethod` and the normal JNI quick-invoke path;
5. compares every byte of every register and returns a six-bit mismatch mask;
   and
6. restores the original native caller state before returning.

The Java probe also requests one intentional post-callback clobber. The
checker must return `0x3f` for that self-test while returning zero for all
normal calls. This rejects a probe whose comparison path was optimized away
or wired to only a subset of the registers.

## Structural checks

`run_w003_xmm_sentinel.sh` verifies:

- the JNI symbol is exported from `libw003xmmsentinel.dll`;
- the PE object reserves/releases exactly 136 bytes;
- XMM6 and XMM11 endpoint saves/restores are present around the callback;
- the callback relocation targets `W003InvokeManagedCallback`; and
- PE unwind information names `W003XmmSentinelAssembly` and records all six
  `SAVE_XMM128` operations.

The compiled C callback object uses XMM3 for the first floating argument and
does not add its own XMM6-XMM11 spill around `CallStaticIntMethod`, so the
sentinel observes the ART boundary rather than a compiler-generated local
repair.

## Wine matrix

Command:

```bash
REPEATS=2 bash tools/verify/win64_phase4/run_w003_xmm_sentinel.sh
```

Result:

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
main end exception=0
```

The JIT pair additionally records successful baseline compilation of
`W003XmmSentinelProbe.managedCallback(double, ... double)`.

## Native Windows acceptance

Windows 10 build 19044 passes the sentinel 2/2 in nterp, switch, and
threshold-zero JIT modes. All six runs report a zero normal mismatch mask, the
exact six-bit intentional-clobber mask, zero pending exception, and exit zero.
Both JIT runs compile the twelve-double managed callback through the corrected
Windows pagefile-section dual view.

The separate four-family managed-frame probe also passes 8/8 on the same
native host; see [RESULT-w003-frame-probe.md](RESULT-w003-frame-probe.md).
Fatal-marker and recursive dump scans are clean. The complete accepted return
is documented in
[evidence/w003_host/ACCEPTANCE.md](evidence/w003_host/ACCEPTANCE.md), and W-003
is closed.
