# W-010/W-014 native Windows diagnostics

This is the interpretation guide for the already issued historical package.
Its repository-side package producer and PowerShell diagnostic runner are
retired; the immutable returned evidence remains useful for explaining the
rejected fixed-page design. Current W-010 reproduction uses unified
`stage:w010`.

**Current state:** E9 is accepted 30/30 on Windows Server 2025 build 26100.
These probes preserve the historical diagnosis that led from the rejected
fixed-page design through the accepted explicit-check and configured-guarantee
design. They are evidence tools, not product mechanisms, and do not change the
30-record `RUN_W010_W014_HOST.ps1` contract.

The returned run-3 and run-4 diagnostics establish three facts:

- recursive protected growth commits/reprotects ART's selected page as
  ordinary `PAGE_READWRITE` before `STATUS_STACK_OVERFLOW`; and
- standalone UEF dispatch works and ART still owns the process UEF slot
  immediately before the JNI crash, but neither the late filter nor ART's UEF
  is dispatched after ART's VEH marker on a JNI/managed caller chain; and
- the same initialized ART process reaches the late UEF, ART UEF, and
  minidump path when a JNI-created native worker faults without ART frames on
  the crashing thread.

The issued package retained those probes and included the
repaired, realistic GenericJNI virtual-unwind gate plus three exception-shape
cases. Their fixed-page modes test direct page state only; E9 product SOE does
not install or depend on a fixed page.

The historical run command inside that already issued package was:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\RUN_W010_W014_DIAGNOSTICS.ps1
```

Return the complete `diagnostic_logs` directory and any new `run\crash\*.dmp`
files. The script does not delete existing acceptance dumps.

## Stack-growth probe

`win32_stack_growth_probe.exe` creates a separate 2 MiB `_beginthreadex`
reservation for each mode. An optional second argument sets the requested
stack-guarantee bytes. The probe queries the value before the call, records the
previous value returned by a nonzero `SetThreadStackGuarantee` call, and
queries the configured value afterward. A first VEH records the terminal
exception, RSP, fault address, fixed-page state, and guard observations without
formatting or heap allocation. Frame SEH catches the terminal AV or
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

Controlled build-26100 runs with guarantee requests 0, 8192, 12288, 16384,
32768, and 65536 place the terminal fault at `low + 0x3000`, `low + 0x3000`,
`low + 0x4000`, `low + 0x5000`, `low + 0x9000`, and `low + 0x11000`
respectively. This disproves E8's `max(prefix, guarantee)` accounting: the
guarantee is above a separate inaccessible terminal prefix, and one moving
guard page lies above the guarantee.

Wine 10.0 can run `baseline`, `writable`, and `direct`, but its host process
segfaults in `protected`. The protected recursion result therefore must come
from real Windows and is intentionally excluded from Wine smoke.

### Dirty RX stack-page experiment

`win32_stack_growth_rx_probe.exe` is a standalone Win32/CRT probe with no ART
headers or libraries. It repeats the recursive-growth experiment after
selecting the same first page above the terminal low prefix, committing it
read/write, filling the complete page with a deterministic pattern, flushing
the instruction cache, and changing it to `PAGE_EXECUTE_READ`. A first VEH
captures the exception access type, terminal page protection, and marker bytes
before frame SEH handles the exception. The worker then calls
`_resetstkoflw()` when required and restores the page to its original state.

Ten fresh processes on Windows build `10.0.26100.32230` produced the same
result. Immediately before recursion the page was a standalone 4096-byte
`PAGE_EXECUTE_READ` region and the marker matched 64/64 bytes. At first
terminal dispatch:

- Windows reported `STATUS_STACK_OVERFLOW` with write access at `low + 0x3000`;
- the selected page at `low + 0x1000` belonged to one 2,093,056-byte committed
  `PAGE_READWRITE` region extending through the rest of the stack allocation;
- the selected page was RW, never RWX, in every run; and
- its marker still matched 64/64 bytes, proving Windows removed RX before a
  recursive frame overwrote that page.

This rules out dirty executable protection as a fixed tripwire inside a
Windows-owned stack reservation. Native stack growth is willing to replace RX
with ordinary non-executable RW stack backing. It also would not directly fit
ART's Linux implicit SOE instruction: that instruction reads its probe address,
and an RX page is readable.

### Windows prior art and available designs

No public report of the exact dirty-RX-to-RW transition was found. The closest
published reproductions establish the broader rule behind it: protection in the
current native stack reservation participates in Windows stack management and
must not be treated as a persistent application-owned tripwire.

- Microsoft's [Creating Guard
  Pages](https://learn.microsoft.com/en-us/windows/win32/memory/creating-guard-pages)
  documentation defines `PAGE_GUARD` as a one-shot alarm whose first access
  clears the guard bit. [Thread Stack
  Size](https://learn.microsoft.com/en-us/windows/win32/procthread/thread-stack-size)
  says Windows commits reserved stack pages as they are needed. Microsoft's
  supported native recovery sequence is to unwind out of the overflow handler
  and then call
  [`_resetstkoflw()`](https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/resetstkoflw)
  to restore a guard page; this does not by itself preserve a managed catch at
  the faulting JIT frame.
- Raymond Chen's [A closer look at the stack guard
  page](https://devblogs.microsoft.com/oldnewthing/20220203-00/?p=106215)
  explains that the default stack-growth handler turns the accessed guard into
  ordinary committed memory, moves the guard, and resumes the instruction.
- The Stack Overflow reproducer [PAGE_GUARD protection on stack pages but
  exception handler is not
  executed](https://stackoverflow.com/questions/75175712/) observes that
  neither VEH nor SEH receives ordinary guard accesses in the current stack.
  Its answer demonstrates Windows removing the guard, installing lower guards,
  and changing `NT_TIB.StackLimit`. An older local-variable reproducer reports
  the same special behavior in [VirtualProtect With PAGE_GUARD Not Working With
  Local Variables](https://stackoverflow.com/questions/37148399/).

Existing runtimes use one of these designs instead of a fixed Linux-style
`PROT_NONE` page in the Windows-owned native stack:

- HotSpot uses compiler stack banging, handles `EXCEPTION_STACK_OVERFLOW`, and
  manages yellow/red/reserved zones. Its Windows handler explicitly notes that
  the OS has already unprotected the first yellow-zone page, reconstructs the
  Java frame at the stack-banging point, redirects to the shared stack-overflow
  continuation, and later reguards the zones. See
  [`os_windows.cpp`](https://github.com/openjdk/jdk/blob/master/src/hotspot/os/windows/os_windows.cpp),
  [`os_windows_x86.cpp`](https://github.com/openjdk/jdk/blob/master/src/hotspot/os_cpu/windows_x86/os_windows_x86.cpp),
  and
  [`stackOverflow.cpp`](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/stackOverflow.cpp).
- CoreCLR calls `SetThreadStackGuarantee`, translates `STATUS_STACK_OVERFLOW`
  using a preallocated managed exception, physically checks for a missing guard
  with `VirtualQuery`, and restores `PAGE_READWRITE | PAGE_GUARD` only after
  sufficient unwind. It verifies the protection because setting a guard too
  close to the current SP can race or fail, and terminates if it cannot restore
  one above its hard guard region. See
  [`threads.cpp`](https://github.com/dotnet/runtime/blob/main/src/coreclr/vm/threads.cpp)
  and
  [`excep.cpp`](https://github.com/dotnet/runtime/blob/main/src/coreclr/vm/excep.cpp).
- Rust's standard library takes the smaller diagnostic-only route on Windows:
  reserve emergency exception stack with `SetThreadStackGuarantee`, report
  `EXCEPTION_STACK_OVERFLOW` from a VEH, and continue searching rather than try
  to recover. See
  [`stack_overflow.rs`](https://github.com/rust-lang/rust/blob/master/library/std/src/sys/pal/windows/stack_overflow.rs).
- A recent WasmEdge proposal uses the same class of workaround selected here:
  a soft per-thread stack limit checked at compiled-function entry with a 64 KiB
  safety margin, producing a deterministic runtime trap before the native guard
  is reached. The proposal is
  [WasmEdge PR 4649](https://github.com/WasmEdge/WasmEdge/pull/4649); it was
  closed without merge, so it is supporting prior art rather than a shipped
  dependency.

For this port, the existing Windows x64 pre-prologue `RSP < Thread::stack_end_`
check remains the least invasive reliable design. A HotSpot/CoreCLR-style
native-SOE subsystem is possible, but would require stack banging, reserved
recovery budget, preallocated failure paths, frame reconstruction, and guard
restoration. Application-owned stacks could regain mapping control only through
a larger fiber/manual-stack ABI, unwind, GC, and native-transition redesign.

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

The E4 package sets `ART_WINDOWS_X64_FATAL_UNWIND_TRACE=1` only for the three late-
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
Windows x64 ABI change:
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
runtime-function record. Repair its Windows x64 RBX/home-area frame, add structural
and body/epilogue virtual-unwind gates, then repeat the three exception shapes.

## Native E5 result

The E5 switch-wrapper package was run automatically on Windows Server 2025
build 26100. Its archive SHA-256 is
`231322dd1261bb7a592929005cef85079110466462cadfef8fc996fbfaae2a05`, and
the returned result bundle SHA-256 is
`1a58bb0f318eae82882ea1bd0e5b0fa403202d02ae95a889b07a1e7b3524b3d9`.
The package checker and complete diagnostic runner pass.

The Windows x64-only RBX save, 32-byte MSVC home area, canonical epilogue, and PE
unwind metadata work natively. Both JNI traces report `lookup=1` at
`ExecuteSwitchImplAsm + 0xd` (`rva=0x9b608d`, runtime-function range
`0x009b6080..0x009b6093`) and unwind past it.

The new first miss is `art_quick_to_interpreter_bridge + 0x82`
(`rva=0x9d3652`), the return PC after `call artQuickToInterpreterBridge`.
It appears at hardware trace frame 11 and raised trace frame 12. Both JNI cases
still miss late and ART UEF. The bridge's primary 200-byte frame and its
post-frame pending-exception tail have different stack shapes and must receive
range-accurate descriptions; do not cover both with one blanket unwind record.

The native-worker control again reaches both UEFs and writes one valid
747,073-byte dump with SHA-256
`99bff7ef07986eb4c2c15506056664f1a7d39db6fc6f685482e93fadbacc19f5`.
See `evidence/w010_w014_e5/DIAGNOSIS.md`.

## Local E6 interpreter-bridge repair

The E6 candidate preserves ART's existing 200-byte save-refs-and-args frame
and gives its Windows x64 primary range a complete stack/GPR unwind description.
Windows-only fixed-offset restores keep the frame intact through the captured
`+0x82` return and end in recognized normal and pending tail-jump epilogues.
The pending target begins a second contiguous runtime-function range for its
separate 88-byte save-all frame. A single record never spans both shapes.

The static audit requires both records. The live probe exercises entry,
`+0x82`, the fixed restore sequence, both epilogues, and the pending body, and
reports:

```text
interpreter_bridge_records=2
interpreter_bridge_call_return=0x82
interpreter_bridge_pending=0x140
interpreter_bridge_frame=200
interpreter_bridge_pending_frame=88
failures=0
```

The complete Phase-4 Wine aggregate passes, including static/JIT/OSR fatal
dispatch. W-003 frame and XMM matrices pass, and Linux rebuild, showversion,
imageless Hello, and emitted bridge-disassembly parity pass. The package and
native reviewers are labeled E6. Run the three diagnostic exception shapes on
native Windows next; require live lookup at `+0x82` and use any later first
miss as the only basis for another unwind repair.

## Native E6 result

The archive SHA-256 is
`9ab66c9a7b2e8e40210f9c47971cbf5ac9f86c0ca729c25a05448f12346499bc`.
The transferred bytes and Python package checker pass on Windows Server 2025
build 26100. The returned result bundle SHA-256 is
`a1c6af0ceff198f6b4543aa832dbf40ced81dcf72800b77c55dd5f2959302736`.

Both JNI cases now resolve the native E5 miss:

```text
art_quick_to_interpreter_bridge + 0x82
rva=0x9d3652 lookup=1
begin=0x009d35d0 end=0x009d3710 unwind=0x0100df80
```

Hardware frame 11 and raised frame 12 cross the primary bridge record. Every
later frame has `lookup=1`; the walks end at zero PC after 23 and 24 frames.
Both cases enter the late UEF, chain into ART's UEF, and create valid dumps.
The native-worker control also reaches both UEFs and creates a dump. The three
valid 14-stream `MDMP` files are 748,487, 744,355, and 748,587 bytes.

This closes the diagnosed fatal-dispatch lookup chain. It natively validates
the primary record; the separate pending record is still structural/synthetic
coverage because these cases do not enter that path. The subsequent complete
host matrix repeats all five static/JIT/OSR fatal origins as described below.
See `evidence/w010_w014_e6/DIAGNOSIS.md`.

## Complete native E6 host matrix

The exact package then ran from a fresh directory on Windows Server 2025 build
26100. It produced 25 of the required 30 PASS records and `OVERALL FAIL`.
Package identity, structural/CET policy, static/live unwind, all six full-width
XMM runs, thread/page/fault/sigchain probes, no-chain rejection, nterp/JIT NPE,
and every fatal origin pass.

The five fatal cases are static `-Xint`, threshold-zero JIT J-2/J-1, and
switch-OSR J-2/J-1. Each reports the required VEH and UEF markers, exits with
`0xC0000005`, and creates a new valid named 14-stream minidump. This accepts
the complete native fatal-origin subset after the E5/E6 unwind repairs.

The remaining failures are all consequences of the rejected fixed-page SOE
design:

- switch mode cannot re-protect the selected page from the observed state,
  logs `error=13`, and exits with `0xC0000005` before managed recovery;
- nterp reaches `0xC00000FD`, logs VEH, and terminates without managed SOE;
- threshold-zero JIT reaches `0xC00000FD`, logs VEH and UEF, and writes an
  unwanted 1,768,325-byte dump; and
- handled-log and handled-dump aggregate checks consequently fail.

The full returned payload matches the issued identity. The reviewer reaches
and correctly rejects `RESULT_W010_W014.txt` because it ends in `OVERALL FAIL`.
The raw returned archive SHA-256 is
`d6bb85c1529496cb384bebcc1495378ade0e253041e01a9605f3f6c90b8538e5`.
See `evidence/w010_w014_e6_full/DIAGNOSIS.md`.

## Native E8 rejection and E9 acceptance

E7 made the deliberate product change from implicit Windows x64 probes to explicit
pre-prologue `RSP < Thread::stack_end_` checks while leaving Linux's implicit
`RSP - 8192` path unchanged. E8 then accounted for the native stack guarantee
as `max(inaccessible prefix, guarantee)`. All three native managed-SOE modes
still failed, proving those values are not overlapping descriptions of the
same bytes. The E8 result bundle SHA-256 is
`3c5fb26da6882e4fb3643a4575fef03b5cf4569ebe45a51e16086658aefd587b`.

E9 queries each thread's existing guarantee, raises it to at least four system
pages while preserving a larger value, queries it again, and debits:

```text
inaccessible memory prefix
+ page-rounded configured guarantee
+ one moving PAGE_GUARD page
```

Common ART then retains its separate 8192-byte recovery reserve. The immutable
E9 archive SHA-256 is
`2b84c911dfbe23dd5dd13917a0fb4a63bdbf90901172f74dfe642ed1fd20f16f`.
On Windows Server 2025 build 26100, the native runner records 30/30 PASS,
`NO_HANDLED_DMP_FILES`, and exactly five valid fatal dumps. The independent
reviewer accepts the returned full package. See
`evidence/w010_w014_e9/ACCEPTANCE.md`.

### Pregrown PAGE_NOACCESS implicit probe at the E9 low boundary

`win32_stack_pregrow_probe` extends the earlier conservative pre-growth experiment
to the product E9 low neighborhood and measures commit cost, attach/detach
irreversibility, and multi-thread scale.

Installation sequence on a fresh 2 MiB Windows thread stack:

1. Raise `SetThreadStackGuarantee` to four system pages and re-query it.
2. Measure the terminal inaccessible prefix with `VirtualQuery`.
3. Compute
   `pregrow_target = low + memory_prefix + rounded_guarantee + page_size`.
   On the acceptance host this is `low + 0x6000`.
4. Touch every page down to that target with a leaf `_chkstk`-style walk while
   leaving `RSP` high (`Win32PregrowStack`).
5. Change the first committed private RW page immediately above the moved
   Windows guard/guarantee region to `PAGE_NOACCESS`.
6. Execute the exact ART Linux probe shape `testq %rax, -8192(%rsp)`.

Artifact SHA-256 used for the E9 matrix:

```text
bdfec88fa7dc5cbcdd9e6e556ecbd7738a2b8822662bbafc15027ca3f320f7c5
```

Host: Windows `10.0.26100`.

Results:

- Implicit E9 mode: **30/30** fresh processes succeeded.
  - `selected_offset` was always `0x6000`.
  - Guard moved from near the high end (`low + 0x1F8000`, size 20 KiB) to
    `low + 0x1000`, size 20 KiB.
  - Every terminal fault was a read AV (`access_type=0`) with
    `fault_address == RSP - 8192` inside the selected page.
  - The selected page remained `PAGE_NOACCESS` in VEH and frame SEH.
  - The Windows guard did not move during the implicit fault.
  - No `STATUS_GUARD_PAGE_VIOLATION` reached user handlers.
  - Stack commit grew from about 32 KiB to **2,093,056** bytes
    (`2 MiB - 4 KiB` terminal prefix) and stayed there after restore.
- Native E9 collision: child exit **`0xC0000005`**, as expected. Frame SEH does
  not recover once ordinary recursion drives `RSP` into the ART page.
- Attach/detach E9: **5/5**. Restoring the ART page to RW succeeds, but the
  lowered guard and nearly-full stack commit remain. Pregrowth is irreversible
  with supported APIs.
- Commit-scale with workers held alive after install:

  | threads | private_peak_delta | stack_commit_sum | elapsed_ms |
  |--------:|--------------------:|-----------------:|-----------:|
  | 1 | 2,211,840 (~2.11 MiB) | 2,093,056 | 16 |
  | 10 | 21,164,032 (~20.2 MiB) | 20,930,560 | 31 |
  | 100 | 211,009,536 (~201.2 MiB) | 209,305,600 | 235 |

  Cost is essentially linear at about **2.0-2.1 MiB commit charge per thread**
  for a 2 MiB stack reservation. Average install latency at 100 threads was a
  few milliseconds of page-walk work plus thread creation.

Interpretation:

- A Linux-like implicit probe is technically implementable on Windows after
  deliberate pre-growth to the E9 low boundary.
- The mechanism is still a poor default product choice versus E9 explicit
  checks because it forces nearly full stack commit on every attached thread,
  permanently changes external-thread stack high water, and turns deep native
  recursion into an unhandled AV at the ART page.
- Logs:
  - `tools/verify/windows_x64_phase1/logs/pregrow_e9_matrix_2026-07-29.log`
  - `tools/verify/windows_x64_phase1/logs/pregrow_e9_commit_scale_hold_2026-07-29.log`
