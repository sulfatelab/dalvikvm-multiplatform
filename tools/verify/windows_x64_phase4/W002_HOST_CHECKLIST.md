# W-002 native Windows host acceptance

**Target:** Windows 10 version 1803 (RS4, build 17134) or later, x64

**State:** ACCEPTED on Windows 10 build 19044; W-002 closed

The accepted `2026-07-26 14:37:55` R2 run produced 21 PASS records, zero
failures, `OVERALL PASS`, and `NO_DMP_FILES`. All OSR and attached-thread mode
pairs passed twice. See
[`evidence/w002_host/ACCEPTANCE.md`](evidence/w002_host/ACCEPTANCE.md).

## Purpose

This focused package is the remaining close gate for W-002. Wine and Linux
already pass the structural, OSR, native-thread attach, and broader regression
controls. The native run confirms that the Windows x64 rSELF and OSR transitions also
behave correctly on the supported Windows kernel and loader.

The matrix covers:

- corrected dual-view and J-1 diagnostic JIT memory modes;
- product-default nterp and the switch interpreter;
- baseline-to-OSR compilation and transition with exact checksum;
- `AttachCurrentThread` and `AttachCurrentThreadAsDaemon`;
- invocation of a pre-JITed Java callback from 16 newly attached native
  threads per attach process;
- daemon state, allocation, exact return values, detach, and
  `JNI_EDETACHED` checks; and
- two complete repetitions of every mode pair.

The package embeds a Linux-generated structural report for the quick and nterp
OSR assembly. The Windows host does not need LLVM tools. R2 explicitly sets
both JIT warmup and optimize thresholds to 100 and uses a 2,000,000-iteration
loop so a fast native host repeatedly checks for asynchronously installed OSR
code instead of completing before the transition.

## Run

Unpack the archive on a native Windows 10/11 x64 host. Do not use WSL or Wine.
From PowerShell in the package root:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\RUN_W002_HOST.ps1
```

The script resolves the package root from its own location, so the unpack path
may contain spaces.

## Required result

`logs\RESULT_W002.txt` must end with:

```text
OVERALL PASS
```

The result must contain 21 PASS records:

- host OS, package integrity, and structural report: 3;
- OSR and attach processes: 16;
- fatal-log scan and recursive dump scan: 2.

Every child process must exit zero without timing out. The eight OSR processes
must report `warmup_threshold=100, optimize_threshold=100`, show baseline and
OSR compilation, the jump marker, exact checksum `65553463744`, and no pending
exception. Switch-interpreter OSR must also show the switch return-completion
marker; nterp OSR must not use that return path.

Every attach process must report `W002AttachProbe OK completed=16`, compile
`W002AttachProbe.attachedCallback`, and finish without an exception.

`logs\DMP_SCAN.txt` must contain:

```text
NO_DMP_FILES
```

## Return evidence

Return either the complete package directory or an evidence-only ZIP. Do not
return only screenshots. An evidence-only return must preserve:

- the complete `logs` directory;
- `BUILD_INFO.txt`;
- `MANIFEST.json`;
- `SHA256SUMS.txt`; and
- `W002_STRUCTURAL_REPORT.txt`.

The reviewer requires those four root metadata files to match the issued
package byte for byte. A complete returned payload is also accepted and is
fully re-hashed; a partial payload is rejected. In both forms, preserve the
complete `logs` directory.

Linux-side review command:

```bash
python3 tools/verify/windows_x64_phase4/review_w002_host_result.py \
  /path/to/returned.zip --issued dist/windows_x64_w002_host
```

The originally returned evidence ZIP omitted the unchanged root
`MANIFEST.json`. The acceptance record documents the omission and the strict
review of a normalized archive containing only the retained byte-identical
issued manifest plus the original evidence. W-002 is closed.
