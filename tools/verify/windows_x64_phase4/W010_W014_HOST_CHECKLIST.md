# Historical W-010/W-014 native Windows Stage E acceptance

This checklist applies only to the already issued package and its immutable
returned evidence. The repository package producer and packaged-runner sources
were retired after unified `stage:w010` and `stage:w014` passed on Windows
Server 2025 and repeated as Ninja no-ops. For a new W-010 run, use
`tools/build_art.py test --stage w010 --parallel 16`; do not reconstruct this
package.

**Authoritative lab gate:** Windows Server 2025 Datacenter Evaluation, x64,
build 26100. The former Windows 10 host is no longer available. The Windows
10 RS4 requirement below is only the product API compatibility baseline.
See the [native Windows gate policy](../../../win32_host_gate_policy.md).

**State:** HISTORICAL PACKAGE PROCEDURE; E9 configured-guarantee explicit-stack-check, FS-1 stack high-water,
and FS-2 debugger/CET/embedding/exception-XMM native acceptance accepted on
Windows Server 2025 build 26100

## Purpose

This package exercises the automatable native subset of the coupled W-010
managed-fault and W-014 thread-stack design. Wine and Linux are already green;
the native run must establish that the real Windows loader, exception
dispatcher, moving stack guard, static boundaries, dynamic JIT tables, and
minidump path preserve the same contracts.

The package intentionally does not claim to close every Stage E item. All
future native reruns use the Server 2025 lab gate; no second Windows host is
required under the current policy. FS-1
supplies the Release/Debug stack high-water evidence and FS-2 supplies the
debugger first-chance, forced-policy, exception-XMM, and embedding/UEF teardown
evidence. Conditional pending-range, reservation-correlation, negative-
exception, and debugger-quality dump-stack work remains separate.

E9 replaces the rejected Windows x64 fixed-page recursive-SOE mechanism with narrow
explicit `RSP < Thread::stack_end_` checks in optimizing code and nterp. An
equal stack pointer is allowed. Overflow tail-jumps through
`Thread::pThrowStackOverflow`; Windows owns stack growth and mapping state, and
ART raises each attached thread's stack guarantee to at least four system
pages, preserves any larger host value, and queries the configured value back.
Its excluded low interval is the sum of the inaccessible memory prefix, the
page-rounded guarantee, and one moving-guard page. ART then adds its unchanged
8192-byte managed-overflow recovery reserve. This keeps that entire reserve
above Windows' native recovery boundary. Linux retains its original implicit
`RSP - 8192` probes. The issued structural report records this accounting
contract and a disassembly-backed cross-target check of both object files.

If the acceptance runner fails in managed SOE or fatal UEF/minidump cases, run
the separate diagnostic matrix before changing product code:

```powershell
.\scripts\RUN_W010_W014_DIAGNOSTICS.ps1
```

It writes `diagnostic_logs` and does not change the required 30 acceptance
records. Interpretation is documented in `W010_W014_DIAGNOSTICS.md`.

## Host prerequisites

- Use the authoritative native Windows Server 2025 x64 host, not Wine, WSL, or
  a compatibility VM layer.
- The acceptance host must report build 26100. Windows 10 build 17134 remains
  the product API compatibility baseline only.
- Hardware-enforced Stack Protection must be disabled for the ART process.
  On build 19041 or later, the runner requires the process policy probe to
  report `actual=disabled` and `known_incompatible=0x00000000`. The raw flags
  may still contain `CetDynamicApisOutOfProcOnly` or reserved bits; neither is
  HSP enablement. Older supported builds may report that the policy query is
  unavailable.
- Do not enable compatibility, audit, strict, or context-IP-validation shadow-
  stack policies for the ordinary acceptance run.
- Allow each fatal native AV case to terminate and write a minidump under
  `run\crash`. If Windows Error Reporting asks to debug the process, decline
  debugging and allow the process to terminate.

## Run

Unpack the issued archive. From PowerShell in the package root:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\RUN_W010_W014_HOST.ps1
```

The path may contain spaces. The script resolves the package root from its own
location, validates all issued hashes before execution, removes old test dumps,
and writes its evidence under `logs` plus the expected fatal dumps under
`run\crash`. Each valid new dump is immediately renamed with its fatal case
name so ART's one-second timestamp filenames cannot collide across cases.

## Automated matrix

The runner verifies:

- package identity and the Linux-generated CET/link structural report;
- emitted PE unwind records for the static invoke, generic-JNI, and split OSR
  entry/return boundaries;
- live split OSR lookup and virtual unwind from a variable copied-stack RSP,
  an RSP-based return with managed RBP clobbered, and the canonical epilogue;
- realistic GenericJNI virtual unwind from the captured native-call return at
  trampoline `+0xc5`, with variable native RSP and caller RIP/RSP plus all
  nonvolatile GPR restoration;
- two full XMM6-XMM15 preservation runs at each nterp, switch-interpreter, and
  threshold-zero JIT native-to-managed boundary;
- actual user shadow-stack policy observation;
- main/default, 64 KiB, 256 KiB, 1 MiB, 2 MiB, and 9 MiB requested pthread
  reservations. A nonzero `_beginthreadex` request uses
  `STACK_SIZE_PARAM_IS_A_RESERVATION` and is checked against that request after
  allocation-granularity rounding; it is not clamped to the executable
  default;
- join/detach handle stress, raw `CreateThread`, and fiber rejection;
- read-only Windows stack-layout inspection and usable-bound selection;
- deterministic protected-page selection plus committed/reserved restoration
  as test-only page-state diagnostics; these probes do not describe the E9
  product SOE mechanism;
- exact exception-record filtering;
- two handled page faults, one unrecognized fault forwarded through foreign
  VEH registered before and after ART to frame-based SEH, promotion, and
  handler removal;
- started-runtime `-Xno-sig-chain` rejection;
- switch-interpreter SOE reference behavior;
- repeated nterp and threshold-zero JIT read/write NPE and main/child SOE;
- post-fault stack-trace construction, `System.nanoTime()` JNI, object
  allocation/identity, and `System.gc()` recovery;
- no diagnostic VEH/UEF marker and `NO_HANDLED_DMP_FILES` for every handled
  path; and
- one static `-Xint` fatal JNI native AV reaching diagnostic VEH, UEF, nonzero
  termination, and a new real `MDMP` file;
- one threshold-zero JIT-origin fatal AV in each J-2 and J-1 memory mode,
  including the optimizing caller and JIT JNI stub; and
- one switch-interpreter OSR-origin fatal AV in each J-2 and J-1 memory mode,
  including Baseline/Osr compilation, the real OSR jump, the copied-stack RBP
  handoff, and a new `MDMP` file.
The package still does not claim debugger-quality stack reconstruction or
large-table sampling; those remain separate Stage E evidence. FS-2's debugger
assertion is limited to first-chance delivery and continuation, not dump-stack
quality.
The automated fatal subset explicitly covers JIT-origin and OSR-origin fatal
dispatch in both J-2 and J-1 memory modes.

## Required result

`logs\RESULT_W010_W014.txt` must end with:

```text
OVERALL PASS
```

It must contain 30 PASS records and no FAIL record. Key evidence includes:

- `logs\cet_policy.log` with `WIN32_CET_POLICY_PROBE PASS`,
  `actual=disabled`, and `known_incompatible=0x00000000`; a nonzero raw
  `flags=` value is allowed when it contains no named incompatible field;
- `logs\osr_unwind.log` with `win32_osr_unwind_probe failures=0`,
  `entry_frame_register=R12 compiled_frame_register=RBP`, the zero-offset
  entry frame, zero-prologue return range, `fixed_frame=248`,
  `xmm_count=10`, two invoke records, `generic_jni_records=1`,
  `generic_jni_native_return=0xc5`, `switch_impl_records=1`,
  `switch_impl_call_return=0xd`, `interpreter_bridge_records=2`,
  `interpreter_bridge_call_return=0x82`,
  `interpreter_bridge_pending=0x140`, `interpreter_bridge_frame=200`,
  `interpreter_bridge_pending_frame=88`, and the `OK` marker;
- six `logs\xmm_full_*_run*.log` files with `mask=0`,
  `fullSelfTestMask=1023`, and `W003XmmSentinelProbe OK`. The retained
  `selfTestMask=63` field is the historical XMM6-XMM11 compatibility marker;
  `fullSelfTestMask=1023` is the authoritative XMM6-XMM15 self-test;
- `logs\W010_W014_STRUCTURAL_REPORT.txt` with
  `boundary_unwind=win32_boundary_unwind OK ...`, the cross-target
  `explicit_stack_checks=... PASS (Windows x64 object, Linux object)` marker,
  `stack_overflow_delivery=explicit-rsp-below-guarantee-aware-thread-stack-end`,
  `windows_stack_guarantee=minimum-four-pages-preserve-larger-query-actual`,
  `windows_excluded_low=sum-memory-prefix-guarantee-moving-guard`,
  `art_stack_overflow_reserve=8192`, and
  `windows_stack_mapping_ownership=os`;
- `logs\thread_stack.log` with exact
  `requested=65536 actual=65536`,
  `requested=262144 actual=262144`, all five nonzero requested sizes, zero
  failures, and
  `runtime=native reservation_rounding=request wine_default_clamps=0`;
- `logs\stack_page.log` with one main and one pthread guarantee record,
  `minimum=16384`, a configured value at least that minimum, preservation of
  any larger `before` value, and the zero-failure marker;
- `logs\sigchain.log` with
  `action_calls=3 foreign_before=2 foreign_after=2` and
  `sequence=1,2,1,2`;
- managed NPE records with `read=64 write=64 recovery=128 gc=16`;
- managed SOE records with `main=2 child=2 recovery=4 gc=4`;
- `logs\HANDLED_DMP_SCAN.txt` containing `NO_HANDLED_DMP_FILES`;
- `logs\crashnative.log` containing the native AV VEH, UEF, minidump, and
  `new_minidump=` markers;
- `logs\jit_fatal_j2.log` and `logs\jit_fatal_j1.log` containing the
  optimizing caller/JNI compile records, VEH, UEF, J-2/J-1 selection, and
  `new_minidump=`;
- `logs\osr_fatal_j2.log` and `logs\osr_fatal_j1.log` containing Baseline/Osr
  records, the real OSR jump, VEH, UEF, J-2/J-1 selection, and
  `new_minidump=`; and
- `logs\FATAL_DMP_SCAN.txt` listing at least five dumps with byte count and
  SHA-256.

## Return evidence

Return either the complete package directory or a ZIP preserving:

- the complete `logs` directory;
- every `run\crash\*.dmp` produced by the fatal case;
- `BUILD_INFO.txt`;
- `MANIFEST.json`;
- `SHA256SUMS.txt`; and
- `W010_W014_STRUCTURAL_REPORT.txt`.

Do not return screenshots alone. After the runner finishes, do not delete or
rename its case-prefixed dump files. The reviewer checks the `MDMP` signature,
dump size, returned metadata identity, exact managed/native markers, and
Windows build.

Linux-side review command:

```bash
python3 tools/verify/windows_x64_phase4/review_w010_w014_host_result.py \
  /path/to/returned.zip --issued dist/windows_x64_w010_w014_host
```

## Remaining Stage E evidence after the E9/FS-1/FS-2 automated PASS

FS-1 is accepted separately on Windows Server 2025 build 26100. Its Release
and Debug switch/nterp/JIT runner records four complete allocation-free
high-water records per mode, positive native margins, no fatal marker, and
`NO_DMP_FILES`. Native minimum margins are 6784/7536/7616 bytes in Release and
69744/37168/37232 bytes in Debug. The 40-KiB Debug-only reserve leaves more
than 37 KiB on both quick paths; product and non-Windows remain at 8192 bytes.
See `evidence/fs1_stack_high_water/ACCEPTANCE.md`.

The following are still optional or conditional before W-010/W-014 close:

- reservation-correlation and pending-range probes only if deterministic;
- wrong-address and unsupported exception-kind native negatives; and
- debugger-quality dump-stack reconstruction.

FS-2 has closed the previously open debugger first-chance/continue,
named-incompatible CET, safe dynamic/reserved policy, predecessor-UEF/frame-SEH
teardown, and exception-unwind XMM requirements. Its compact native evidence is
under `evidence/fs2_w010_w014_native/`.
