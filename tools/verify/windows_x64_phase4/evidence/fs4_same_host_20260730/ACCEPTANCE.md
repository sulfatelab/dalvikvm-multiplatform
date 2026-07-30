# FS-4 same-host repeat

**Date:** 2026-07-30
**Host:** Windows Server 2025 Datacenter Evaluation, x64, build 26100
**Host address:** `administrator@10.127.137.62`
**Status:** Same-host repeat PASS; FS-4 remains open for the required second supported Windows host

## Repeated gates

The accepted native host was rebooted before this run. The refreshed E9/FS-2
package, FS-1 package, and JIT-3/FS-3 package were extracted into a fresh
working area on the host and executed with their native PowerShell runners.
The source archives and hashes were:

```text
dist/windows_x64_w010_w014_host_fs2.zip
935ab419124782bf8ac98546f38c352d4a32223466f3fe962f3c64dd3afd21bd

dist/windows_x64_fs1_stack_high_water.zip
22195128d460eef6fe260b79f25e792a2af5303546fadacc7ad188038c09bfbe

dist/windows_x64_w025_jit3_20260729_candidate1.zip
8446a41d72aba32e19ce53cba8ac4b518b182bdebcd68c8023ce6e2ac6d0759f
```

The combined E9/FS-2 runner returned `OVERALL PASS`:

- all structural, CET/HSP, debugger, managed NPE/SOE, embedding, and XMM
  records passed;
- the parameterized thread-stack and page-state probes passed;
- handled-dump scanning returned `NO_HANDLED_DMP_FILES`; and
- six intentional fatal/embedding dumps passed the fatal dump scan.

FS-1 returned `OVERALL PASS` for all six native modes:

| Build | switch | nterp | JIT |
|---|---:|---:|---:|
| Release | 6528 | 7552 | 7632 |
| Debug | 69568 | 37216 | 37232 |

Every mode produced four high-water records and the dump scan returned
`NO_DMP_FILES`.

FS-3/JIT-3 returned `OVERALL PASS` for J-2 stress, J-1 comparison, and two
J-2 repeats. JIT temporary-file and dump scans were empty/clean.

## Additional FS-4 checks

`STACK_GROWTH_PARAMETERIZED.txt` records all 16 combinations of
`baseline`, `protected`, `writable`, and `direct` diagnostic modes with
requested guarantees `0`, `8192`, `16384`, and `65536`. Every combination
reports successful before/after guarantee queries and
`win32_stack_growth_probe OK`.

The native thread-stack probe reports:

```text
requested=65536,262144,1048576,2097152,9437184 -> accepted exactly
join_stress count=512 handles_before=73 handles_after=73
detach_stress count=128
fiber_case rejected=1
win32_thread_stack_probe failures=0 join_stress=512 detach_stress=128
```

The page-state probe reports eight selection cases, five layout cases, a
16-KiB configured guarantee, 64 committed-page restorations, 64 reserved-page
restorations, 258 direct faults, and `win32_stack_page_probe OK`.

Compact raw results are retained beside this file:

- `fs2/RESULT_W010_W014.txt`
- `fs2/W010_W014_STRUCTURAL_REPORT.txt`
- `fs2/thread_stack.log` and `fs2/stack_page.log`
- `fs1/RESULT_FS1.txt`
- `fs3/RESULT_W025_JIT3.txt`
- `STACK_GROWTH_PARAMETERIZED.txt`

## Second-host gate

The local `10.127.137.32/27` network was checked for SSH listeners. The only
other listener was `10.127.137.60`, which identifies as Ubuntu OpenSSH and
rejects the available Windows `administrator` credentials. No second supported
Windows 10 or later host is currently available. Therefore this evidence
refreshes the accepted-host portion of FS-4 but does not close H-002/FS-4.
