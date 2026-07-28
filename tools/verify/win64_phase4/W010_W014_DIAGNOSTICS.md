# W-010/W-014 native Windows diagnostics

These probes distinguish the two failure classes first observed in the
Windows 10 build-19044 Stage E run. They are evidence tools, not acceptance
tests, and do not change the 30-record `RUN_W010_W014_HOST.ps1` contract.

The returned run-3 and run-4 diagnostics establish three facts:

- recursive protected growth commits/reprotects ART's selected page as
  ordinary `PAGE_READWRITE` before `STATUS_STACK_OVERFLOW`; and
- standalone UEF dispatch works and ART still owns the process UEF slot
  immediately before the JNI crash, but neither the late filter nor ART's UEF
  is dispatched after ART's VEH marker on a JNI/managed caller chain; and
- the same initialized ART process reaches the late UEF, ART UEF, and
  minidump path when a JNI-created native worker faults without ART frames on
  the crashing thread.

The current package retains those probes for repetition and includes the
repaired, realistic GenericJNI virtual-unwind gate plus three exception-shape
cases.

Run from the unpacked package root in PowerShell 5.1 or later:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\RUN_W010_W014_DIAGNOSTICS.ps1
```

Return the complete `diagnostic_logs` directory and any new `run\crash\*.dmp`
files. The script does not delete existing acceptance dumps.

## Stack-growth probe

`win32_stack_growth_probe.exe` creates a separate 2 MiB `_beginthreadex`
reservation for each mode. A first VEH records the terminal exception, RSP,
fault address, fixed-page state, and guard observations without formatting or
heap allocation. Frame SEH catches the terminal AV or
`STATUS_STACK_OVERFLOW`; `_resetstkoflw()` runs only after leaving that
handler. The writable mode tests `ProtectWin32StackPage()` before reset and,
if that fails, retries after reset.

The four modes are:

- `baseline`: ordinary Windows recursive stack exhaustion;
- `protected`: recursive exhaustion while ART's fixed page is
  `PAGE_NOACCESS`;
- `writable`: recursive exhaustion after the fixed page is temporarily made
  writable, matching the recovery interval in `ThrowStackOverflowError()`;
- `direct`: one direct read from the protected page, without recursive stack
  growth.

Interpret the records as follows:

- `direct` AV success proves only that the selected fixed page can generate a
  catchable access violation. It does not prove recursive managed SOE.
- A recursive `caught=0xc00000fd` before the fixed page is accessed proves the
  moving Windows guard owns the terminal event instead of ART's fixed page.
- Run 3 reports the protected page inside a 2,093,056-byte committed
  `PAGE_READWRITE` region at termination. Do not describe that result as
  `PAGE_GUARD` moving onto the fixed page.
- `protect_before_reset_ok=1` proves ART can re-protect the page before
  `_resetstkoflw()`. The earlier error 13 was secondary state-check/recovery
  fallout, not the cause of overflow delivery failure.
- The fixed-page selector and restoration remain useful infrastructure, but a
  page inside a Windows-owned stack reservation cannot remain ART's recursive
  SOE tripwire unchanged.

Wine 10.0 can run `baseline`, `writable`, and `direct`, but its host process
segfaults in `protected`. The protected recursion result therefore must come
from real Windows and is intentionally excluded from Wine smoke.

## Standalone UEF probe

`win32_uef_probe.exe` has four isolated modes:

- `seh`: VEH runs, frame SEH handles the AV, and no UEF runs;
- `unhandled`: the installed UEF must run for a main-thread AV;
- `chain`: the second UEF must call the predecessor, producing both markers;
- `thread`: an unhandled worker-thread AV must reach the process UEF.

Each mode reports `IsDebuggerPresent()` and
`CheckRemoteDebuggerPresent()`. If these standalone cases reach their UEF on
the target host, `Start-Process -PassThru -NoNewWindow` and ordinary Windows
dispatch are not the cause of ART's missing UEF.

## Late ART UEF ownership probe

Every late mode installs a diagnostic UEF immediately before its exception.
`SetUnhandledExceptionFilter()` returns the filter that was current at that
instant. The probe resolves that predecessor through `VirtualQuery()` and
`GetModuleFileNameA()`, reports whether it belongs to `art.dll`, and directly
chains to it if dispatch reaches the diagnostic UEF.

The modes are:

- `CrashNativeProbe uef-av`: the existing hardware null-write AV on the JNI
  thread;
- `CrashNativeProbe uef-raise`: continuable
  `RaiseException(EXCEPTION_ACCESS_VIOLATION)` with write/null parameters on
  the JNI thread; and
- `CrashNativeProbe uef-thread`: a hardware null-write AV on a
  `_beginthreadex` worker created from JNI. The crashing worker has no ART
  managed frames, while the Java thread waits inside the JNI call.

The software-raised case is intentionally allowed to return under Wine after
all filters run; the result records its exit shape rather than treating that
Wine behavior as infrastructure failure.

Use this matrix:

| Observation | Meaning |
|---|---|
| predecessor is `art.dll`; late UEF and ART UEF both run | ART still owned the early UEF slot; late registration makes the fatal chain reachable, so do not blame JIT unwind first |
| predecessor is null or outside `art.dll` | another component replaced ART's process-wide UEF after runtime initialization |
| standalone UEF runs, but the late ART UEF never enters | the dalvikvm fatal path does not reach top-level dispatch; inspect native exception boundaries and any enclosing SEH |
| late UEF enters, predecessor is ART, but ART UEF does not log | failure occurs while invoking or inside ART's UEF |
| ART UEF logs but no dump appears | diagnose dump path, file creation, or `MiniDumpWriteDump`, separately from dispatch |

Use the three-mode comparison as follows:

| Observation | Meaning |
|---|---|
| JNI raised AV and JNI hardware AV both miss UEF, native worker reaches it | traversal across GenericJNI/managed frames remains the leading obstruction |
| JNI raised AV reaches UEF but JNI hardware AV misses it | inspect hardware/software exception shape, flags, and first-chance handler interaction |
| native worker also misses UEF | a process-level interaction after ART startup remains; GenericJNI alone is insufficient |
| all three reach UEF after the metadata repair | the GenericJNI RDI unwind defect was material; repeat the full static/JIT/OSR native fatal matrix |

Static, JIT J-2/J-1, and OSR J-2/J-1 cases failed identically in the returned
run. The three new cases distinguish the next boundary before any broader JIT
unwind change.

## GenericJNI virtual-unwind gate

`win32_osr_unwind_probe.exe` now also constructs the completed 200-byte
GenericJNI canonical frame, the 5120-byte R12-anchored reserved area, and a
realistic variable native-call RSP. It calls `RtlVirtualUnwind()` from the
indirect native-call return at `art_quick_generic_jni_trampoline + 0xc5` and
requires restoration of caller RIP/RSP plus RBP, RDI, RSI, RBX, and R12-R15.

The first version of this test found that RDI was physically saved at
`R12 + 5120` while `.xdata` described offset zero. The assembly metadata now
uses `SAVE_NONVOL RDI, offset=0x1400`; structural inspection and the realistic
virtual unwind both pass. This is a concrete correctness repair. Native
run 4 proves it does not by itself repair top-level fatal dispatch.

## Native run-4 result

`/tmp/diag_w010_w014_host-run4.zip` matches the issued E3 GenericJNI package
identity. Its archive SHA-256 is
`9f9a4cbaea3cb7cc030b44db47a4275f97b8d39026fa2fb1cb59b7a8ac405aa7`.
The returned worker dump is a valid 648,619-byte minidump with SHA-256
`b14377fc0670a496d11960d818c387e243f500588033fd6d7238b1655f703086`.

The stack-growth and standalone UEF rows repeat run 3. The three ART rows are
decisive:

| Mode | ART VEH | late UEF | ART UEF | new dump |
|---|---:|---:|---:|---:|
| JNI hardware AV | 1 | 0 | 0 | 0 |
| JNI raised AV | 1 | 0 | 0 | 0 |
| JNI-created native-worker hardware AV | 1 | 1 | 1 | 1 |

ART is the predecessor UEF in all three modes. Both JNI-thread cases exit with
`STATUS_ACCESS_VIOLATION` after ART's VEH and before either UEF. Hardware and
software-raised AVs therefore have the same failed dispatch shape. The native
worker, created by the same JNI library after ART startup, reaches both UEFs
and writes the valid dump.

This rules out exception hardware/software shape, process-wide ART startup
state, UEF ownership, debugger/PowerShell dispatch, and dump API/path as the
remaining distinction. The failure is specific to Windows exception traversal
through the ART managed/GenericJNI caller chain. The repaired GenericJNI
record passes isolated `RtlVirtualUnwind()`, so it is not the complete boundary.
The next diagnostic must capture a bounded recursive `RtlVirtualUnwind()` trace
from the live VEH `CONTEXT` and identify the first frame after GenericJNI that
does not make valid progress. Do not add metadata to
`art_jni_dlsym_lookup_stub` merely because its address appears in raw stack
memory: it restores its temporary frame and tail-jumps to the resolved native
method, so that value is not yet a proven active frame.

## Live VEH unwind trace

The E4 package sets `ART_WIN64_FATAL_UNWIND_TRACE=1` only for the three late-
UEF cases. ART's diagnostic VEH copies the live `CONTEXT` and walks at most 32
frames without modifying the exception record, live context, or handler return
value. Every frame reports PC/RSP, module base/path and RVA, the
`RtlLookupFunctionEntry()` result, and runtime-function begin/end/unwind RVAs.
Registered frames use `RtlVirtualUnwind(UNW_FLAG_NHANDLER)`; leaf frames pop one
validated return slot. The walk stops on zero PC, unaligned/out-of-stack RSP,
unreadable leaf return, non-increasing/no progress, or the fixed limit. A
thread-local recursion guard prevents an instrumentation fault from recursively
starting another trace.

The diagnostic result rows require a begin marker, at least one frame, and an
end marker. Use the module-relative RVA rather than the process-specific PC
when comparing Wine and native Windows.

Before the native run, a local Wine smoke found a concrete candidate. The walk
crosses the crashing `libopenjdk.dll` native method,
the repaired `art_quick_generic_jni_trampoline + 0xc5`,
`art_quick_invoke_static_stub`, ordinary ART C++ frames, and
`ExecuteSwitchImplCpp`. That last registered frame unwinds to
`ExecuteSwitchImplAsm + 0x9`, the `pop %rbx` after its indirect call.
`RtlLookupFunctionEntry()` returns null there even though the assembly wrapper
has pushed RBX. Leaf fallback consequently reads the saved RBX as a return PC
and leaves the real return address behind. This is the first proven live
lookup gap in the local trace; `art_jni_dlsym_lookup_stub` is not the missing
active frame in that walk.

The product repair was deliberately held until native evidence repeated this
boundary. Native E4 did so, therefore repair `ExecuteSwitchImplAsm` as one
Win64 ABI change:
describe its prologue/epilogue with PE unwind directives and provide the
mandatory 32-byte MSVC outgoing home area for its call to
`ExecuteSwitchImplCpp`. Keep the Linux/SysV body unchanged, then add structural
lookup and realistic virtual-unwind coverage before repeating fatal dispatch.

The complete E4 `-j32` package preflight passed under Wine. It requires begin,
frame, and end trace markers in JNI hardware, JNI raised, and native-worker
cases; preserved 14-15 valid fatal minidumps across two complete smokes; then
removed all runtime dumps and regenerated the clean package manifests. This
preflight preceded the native E4 result below.

## Native E4 result

The exact package was run automatically on Windows Server 2025 build 26100.
The archive, manifest, structural report, and package checker passed before
execution. The returned result bundle has SHA-256
`4616e8622dba2977b5472264f099de9449aa5c8b0a4bc1d1d568f9af8c6987b8`.

Both JNI-thread traces confirm Wine's candidate:

- hardware AV reaches `ExecuteSwitchImplAsm + 0x9` at trace frame 7;
- raised AV reaches the same PC at trace frame 8; and
- both report `module=art.dll rva=0x9b6089 lookup=0`, then leaf fallback
  produces a stack address as PC and UEF dispatch is lost.

The native worker trace has four registered native/OS frames, reaches zero PC,
enters both UEFs, and creates one valid 747,491-byte minidump. Its SHA-256 is
`8d854b1e25d561dd8515e6ceb17c9e58574c9e766e3a0e6a1a82091fb7815bf6`.
Stack and standalone UEF rows repeat the prior native result on current
Windows. See `evidence/w010_w014_e4/DIAGNOSIS.md`.

The diagnosis is closed: `ExecuteSwitchImplAsm` is the first missing live
runtime-function record. Repair its Win64 RBX/home-area frame, add structural
and body/epilogue virtual-unwind gates, then repeat the three exception shapes.
