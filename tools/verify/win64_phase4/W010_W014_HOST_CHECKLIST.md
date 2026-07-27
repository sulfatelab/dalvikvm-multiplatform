# W-010/W-014 native Windows Stage E acceptance

**Target:** Windows 10 version 1803 (RS4, build 17134) or later, x64

**State:** native acceptance candidate; not yet accepted

## Purpose

This package exercises the automatable native subset of the coupled W-010
managed-fault and W-014 thread-stack design. Wine and Linux are already green;
the native run must establish that the real Windows loader, exception
dispatcher, moving stack guard, and minidump path preserve the same contracts.

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
  report `actual=disabled`. Older supported builds may report that the policy
  query is unavailable.
- Do not enable compatibility, audit, strict, or context-IP-validation shadow-
  stack policies for the ordinary acceptance run.
- Allow the fatal native AV case to terminate and write one minidump under
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
and writes its evidence under `logs` plus the expected fatal dump under
`run\crash`.

## Automated matrix

The runner verifies:

- package identity and the Linux-generated CET/link structural report;
- emitted PE unwind records for the static invoke and generic-JNI boundaries;
- actual user shadow-stack policy observation;
- main/default, 64 KiB, 256 KiB, 1 MiB, 2 MiB, and 9 MiB requested pthread
  reservations, including the Windows rule that sub-default requests retain
  the executable default reservation;
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
  termination, and a real `MDMP` file.

The package does not claim fatal dispatch from dynamically emitted JIT code.
That path still requires registered JIT PE runtime-function data and explicit
code-cache registration/removal ownership.

## Required result

`logs\RESULT_W010_W014.txt` must end with:

```text
OVERALL PASS
```

It must contain 19 PASS records and no FAIL record. Key evidence includes:

- `logs\cet_policy.log` with `WIN32_CET_POLICY_PROBE PASS`;
- `logs\W010_W014_STRUCTURAL_REPORT.txt` with
  `boundary_unwind=win32_boundary_unwind OK ...`;
- `logs\thread_stack.log` with all five nonzero requested sizes and zero
  failures;
- `logs\sigchain.log` with
  `action_calls=3 foreign_before=2 foreign_after=2` and
  `sequence=1,2,1,2`;
- managed NPE records with `read=64 write=64 recovery=128 gc=16`;
- managed SOE records with `main=2 child=2 recovery=4 gc=4`;
- `logs\HANDLED_DMP_SCAN.txt` containing `NO_HANDLED_DMP_FILES`;
- `logs\crashnative.log` containing the native AV VEH, UEF, and minidump
  markers; and
- `logs\FATAL_DMP_SCAN.txt` listing at least one dump with byte count and
  SHA-256.

## Return evidence

Return either the complete package directory or a ZIP preserving:

- the complete `logs` directory;
- every `run\crash\*.dmp` produced by the fatal case;
- `BUILD_INFO.txt`;
- `MANIFEST.json`;
- `SHA256SUMS.txt`; and
- `W010_W014_STRUCTURAL_REPORT.txt`.

Do not return screenshots alone. Do not delete or rename the dump. The reviewer
checks the `MDMP` signature, dump size, returned metadata identity, exact
managed/native markers, and Windows build.

Linux-side review command:

```bash
python3 tools/verify/win64_phase4/review_w010_w014_host_result.py \
  /path/to/returned.zip --issued dist/win64_w010_w014_host
```

## Remaining Stage E evidence after an automated PASS

The following are still required before W-010/W-014 close:

- repeat the package on Windows 10 build 17134+ and a current Windows release;
- debugger first-chance stop followed by continue for managed NPE/SOE;
- forced compatibility, audit, strict, and context-IP-validation policy
  rejection before Java/JIT, with no control-protection dump;
- exact handler/pre-unprotect stack high-water measurements in release and
  debug builds;
- wrong-address and unsupported exception-kind native negatives; and
- predecessor UEF invocation and runtime unload behavior in an embedding host.
- threshold-zero JIT-origin fatal dispatch after dynamic runtime-function
  registration is implemented.
