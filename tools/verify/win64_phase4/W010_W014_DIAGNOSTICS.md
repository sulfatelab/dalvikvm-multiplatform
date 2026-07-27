# W-010/W-014 native Windows diagnostics

These probes distinguish the two failure classes first observed in the
Windows 10 build-19044 Stage E run. They are evidence tools, not acceptance
tests, and do not change the 30-record `RUN_W010_W014_HOST.ps1` contract.

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
- `fixed_at_terminal` or `fixed_before_reset` with `protect=0x104` shows
  `PAGE_READWRITE | PAGE_GUARD` on the temporarily writable ART page.
- `protect_before_reset_error=13` with the failure text about private
  read/write protection reproduces ART's current re-protection rejection.
- A successful retry only after `_resetstkoflw()` is diagnostic evidence; it
  is not directly usable by ART because managed SOE translation is entered
  from an AV and ART does not own Windows' native stack-overflow reset policy.

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

`CrashNativeProbe uef` installs a diagnostic UEF immediately before the
existing native AV. `SetUnhandledExceptionFilter()` returns the filter that
was current at that instant. The probe resolves that predecessor through
`VirtualQuery()` and `GetModuleFileNameA()`, reports whether it belongs to
`art.dll`, and directly chains to it if dispatch reaches the diagnostic UEF.

Use this matrix:

| Observation | Meaning |
|---|---|
| predecessor is `art.dll`; late UEF and ART UEF both run | ART still owned the early UEF slot; late registration makes the fatal chain reachable, so do not blame JIT unwind first |
| predecessor is null or outside `art.dll` | another component replaced ART's process-wide UEF after runtime initialization |
| standalone UEF runs, but the late ART UEF never enters | the dalvikvm fatal path does not reach top-level dispatch; inspect native exception boundaries and any enclosing SEH |
| late UEF enters, predecessor is ART, but ART UEF does not log | failure occurs while invoking or inside ART's UEF |
| ART UEF logs but no dump appears | diagnose dump path, file creation, or `MiniDumpWriteDump`, separately from dispatch |

Static, JIT J-2/J-1, and OSR J-2/J-1 cases failed identically in the returned
run. No JIT unwind change is justified until these probes distinguish UEF
ownership and top-level dispatch.
