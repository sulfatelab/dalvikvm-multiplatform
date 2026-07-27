# W-010/W-014 native Windows Stage E acceptance

**Target:** Windows 10 version 1803 (RS4, build 17134) or later, x64

**State:** native acceptance candidate; not yet accepted

## Purpose

This package exercises the automatable native subset of the coupled W-010
managed-fault and W-014 thread-stack design. Wine and Linux are already green;
the native run must establish that the real Windows loader, exception
dispatcher, moving stack guard, static boundaries, dynamic JIT tables, and
minidump path preserve the same contracts.

The package intentionally does not claim to close every Stage E item. Debugger
first-chance behavior, forced Hardware-enforced Stack Protection policies,
handler stack high-water measurement, and predecessor-UEF embedding remain
separate manual or launcher-assisted evidence after this automated run passes.
These items are tracked as the remaining forced-policy and embedding matrix.

## Host prerequisites

- Use native Windows 10/11 x64, not Wine, WSL, or a compatibility VM layer.
- Windows build must be at least 17134.
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
- two full XMM6-XMM15 preservation runs at each nterp, switch-interpreter, and
  threshold-zero JIT native-to-managed boundary;
- actual user shadow-stack policy observation;
- main/default, 64 KiB, 256 KiB, 1 MiB, 2 MiB, and 9 MiB requested pthread
  reservations. A nonzero `_beginthreadex` request uses
  `STACK_SIZE_PARAM_IS_A_RESERVATION` and is checked against that request after
  allocation-granularity rounding; it is not clamped to the executable
  default;
- join/detach handle stress, raw `CreateThread`, and fiber rejection;
- deterministic protected-page selection plus committed/reserved restoration;
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
large-table sampling; those remain separate Stage E evidence.
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
  `xmm_count=10`, two invoke records, and the `OK` marker;
- six `logs\xmm_full_*_run*.log` files with `mask=0`,
  `fullSelfTestMask=1023`, and `W003XmmSentinelProbe OK`. The retained
  `selfTestMask=63` field is the historical XMM6-XMM11 compatibility marker;
  `fullSelfTestMask=1023` is the authoritative XMM6-XMM15 self-test;
- `logs\W010_W014_STRUCTURAL_REPORT.txt` with
  `boundary_unwind=win32_boundary_unwind OK ...`;
- `logs\thread_stack.log` with exact
  `requested=65536 actual=65536`,
  `requested=262144 actual=262144`, all five nonzero requested sizes, zero
  failures, and
  `runtime=native reservation_rounding=request wine_default_clamps=0`;
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
python3 tools/verify/win64_phase4/review_w010_w014_host_result.py \
  /path/to/returned.zip --issued dist/win64_w010_w014_host
```

## Remaining Stage E evidence after an automated PASS

The following are still required before W-010/W-014 close:

- repeat the package on Windows 10 build 17134+ and a current Windows release;
- debugger first-chance stop followed by continue for managed NPE/SOE;
- forced compatibility, audit, strict, context-IP-validation, and other named
  incompatible policy rejection before Java/JIT, with no control-protection
  dump; `CetDynamicApisOutOfProcOnly` must remain accepted and reserved fields
  must not be assigned policy meaning;
- exact handler/pre-unprotect stack high-water measurements in release and
  debug builds;
- wrong-address and unsupported exception-kind native negatives; and
- predecessor UEF invocation and runtime unload behavior in an embedding host;
  and
- successful review of the automated native J-2/J-1 JIT-origin and OSR-origin
  fatal evidence included in this package.
