# FS-4 same-host repeat

**Date:** 2026-07-30
**Host:** Windows Server 2025 Datacenter Evaluation, x64, build 26100
**Status:** **FS-4 CLOSED by acceptance-policy decision**; Windows Server 2025 build 26100 is the authoritative native gate

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

The six repeat dumps had the following byte/SHA-256 identities:

```text
embedding 740381 cc9ef7fee49a33183e5759a0fb37a6f443ad9ce8e43f83519e6834e9ded8126b
static    745547 823f84e4982c4848a40a9b01b47c65b2727fdd442a936dfcf6977ad1e9c0b0ce
jit-j1    750777 e10f53f9a82b394368e263f9b681b8813372223123600deacc1e73cee2c0ca7e
jit-j2    747545 9ceb678309d1360eaa23fd294f351a3b3799035ca3d3f0e08f1b650846616020
osr-j1    748255 5c46f117febe4996b0a43f554af6593276e44f053a2ec3e101e69d3a8d4655d5
osr-j2    751919 21a817f8c2305d4d5b381e62c49ede54388d98fbb2279a004f6ddfaa3e412f6c
```

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

The copied FS-1/FS-2/FS-3 result/scan records and parameterized raw transcript
were removed after the exact repeat contract and immutable identities were
consolidated here.

## Acceptance-policy disposition

The local lab network was checked for another Windows SSH endpoint; the only
other listener identified as Ubuntu. Per the explicit
[native Windows gate policy](../../win32_host_gate_policy.md), Windows Server
2025 build 26100 is authoritative for this gate and the separate Windows
10/second-host repetition is skipped. The same-host results above therefore
close FS-4 and H-002 within that declared scope; they do not claim
cross-version coverage.
