# W-010/W-014 native Windows diagnostics

These probes distinguish the two failure classes first observed in the
Windows 10 build-19044 Stage E run. They are evidence tools, not acceptance
tests, and do not change the 30-record `RUN_W010_W014_HOST.ps1` contract.

The returned run-3 diagnostics already establish two facts:

- recursive protected growth commits/reprotects ART's selected page as
  ordinary `PAGE_READWRITE` before `STATUS_STACK_OVERFLOW`; and
- standalone UEF dispatch works and ART still owns the process UEF slot
  immediately before the JNI crash, but neither the late filter nor ART's UEF
  is dispatched after ART's VEH marker.

The current package retains those probes for repetition and adds a repaired,
realistic GenericJNI virtual-unwind gate plus three exception-shape cases.

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
exception-shape results are still required to determine whether it also
repairs top-level fatal dispatch.
