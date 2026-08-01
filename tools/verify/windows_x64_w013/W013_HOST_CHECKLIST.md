# Historical W-013 native Windows host acceptance

This checklist applies only to the already issued R2 package and its immutable
returned evidence. The repository package producer and packaged PowerShell
runner were retired after unified W-013 passed on Windows Server 2025 and Linux
x86-64, with Ninja no-op repeats. For a new run, use
`tools/build_art.py test --stage w013`; do not reconstruct this package.

**Authoritative lab gate:** Windows Server 2025 Datacenter Evaluation, x64,
build 26100. The accepted Windows 10 result below is historical; the former
Windows 10 host is no longer available for future reruns. See
`../windows_x64_phase4/HOST_GATE_POLICY.md`.

**Historical acceptance:** PASS on 2026-07-25 using Windows 10 build 19044. Returned R2
archive `w013-log-r2.7z` has SHA-256
`456e297d70c2f166308c869812ddec262fa38bc6dcd2852ea56edd5b2205078e`;
the reviewed result contains 56 PASS records, zero failures, complete metrics,
and `NO_DMP_FILES`. See `evidence/native_r2/ACCEPTANCE.md`.

**Purpose:** document the accepted historical native host matrix after W-013
Stages A–E, the reviewed failed R1 run, and the post-R1 Wine/Linux repair
gates. This is not a current repeat procedure. Do not reuse the R1 package
built from root `dbca77c`; it contains the defects recorded in `RESULT.md`.

## Run

Unpack the generated archive on the authoritative Windows Server 2025 x64
host. From PowerShell in the package root:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\RUN_W013_HOST.ps1
```

Do not run the package from WSL. The working directory may be anywhere; the
script resolves the package root from its own location.

## Required result

`logs\RESULT_W013.txt` must end in:

```text
OVERALL PASS
```

The matrix covers:

- native `VirtualAlloc2`, exact/low/anywhere placement, ownership, page-state,
  `VirtualQuery`, zero/overflow rejection, fragmented-low-VA,
  complete-low-VA-exhaustion, no-high-fallback, recovery, and repeated-owner-
  destruction checks through `windows_x64_w013_mem_map_probe.exe`;
- embedded dlmalloc create/grow/trim/regrow/failure behavior;
- actual ART mspace provider attachment and rebind;
- 75,497,472 bytes per run of sub-LOS non-moving allocation pressure at both
  128-MiB and 1-GiB `-Xmx`, with stable low addresses and post-GC regrowth;
- moving and large-object GC stress, ThreadHeavy, and HandleLeak;
- default dual-view JIT smoke, JIT disable/filter/exclude/quiet checks, the
  temporary J-1 diagnostic path, and the fourteen-case managed JIT matrix;
- 512-MiB and 1-GiB heap startup plus every process's peak paged, working-set,
  and virtual-byte metrics;
- twenty independent default-JIT imageless starts; and
- fatal/check/access-violation log scanning plus a recursive crash-dump scan.

`logs\HOST_MEMORY.txt` records physical-memory and pagefile data needed to
interpret large-heap commit failures. Every child process has a five-minute
timeout so a hung case becomes an explicit failure rather than blocking the
matrix indefinitely.

## Return evidence

Return the complete `logs` directory and these package metadata files:

- `BUILD_INFO.txt`
- `MANIFEST.json`
- `SHA256SUMS.txt`

Do not return only screenshots. Preserve the text logs so addresses, process
metrics, exit codes, OS build, and dump-scan results can be reviewed.

## Interpretation

`peak_paged_bytes` is a per-process pagefile-backed/private-memory proxy, not a
machine-wide commit-limit measurement. Record the host's installed RAM and
pagefile configuration alongside any 1-GiB failure. A failure caused by an
insufficient system commit limit is distinct from an ART address-placement,
protection, or allocator failure and must not be hidden by lowering `-Xmx` in
the returned evidence.
