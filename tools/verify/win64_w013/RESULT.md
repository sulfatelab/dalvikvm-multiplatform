# W-013 Win64 heap-memory implementation

**Status:** Stage A PASS; Stages B–E remain OPEN
**Date:** 2026-07-25
**Host:** agent01

## Stage A — explicit embedded-dlmalloc configuration

Landed changes:

- external dlmalloc `f3356ce` makes Win32 defaults respect embedding-provided
  `HAVE_MMAP`, `HAVE_MORECORE`, and related platform definitions;
- Win32 contiguous MoreCore now uses `dwPageSize` rather than
  `dwAllocationGranularity`;
- ART `8c900a9e4b` removes `_WIN32`/`WIN32` masking and explicitly selects and
  compile-checks `HAVE_MMAP=0`, `HAVE_MREMAP=0`, `HAVE_MORECORE=1`,
  `MORECORE_CONTIGUOUS=1`, `USE_LOCKS=0`, and mspace-only operation; and
- ART explicitly sets allocation failure to `errno = ENOMEM`.

## Focused probe

Command:

```text
tools/verify/win64_w013/run_dlmalloc_config_probe.sh
```

Observed under Wine:

```text
W013_DLMALLOC_CONFIG_PASS page=4096 granularity=4096 increment=20480
```

The probe also checks that Windows macros remain active, a maximal allocation
fails with `ENOMEM`, and `art-dlmalloc.cc` contains no `_WIN32`/`WIN32` undef.

## Integration verification

```text
cmake --build build/win64_phase1 --target art dalvikvm -j8
tools/verify/win64_phase4/run_jit_smoke.sh
cmake --build build/native --target art dalvikvm -j8
tools/verify/linux_hello/run_imageless_hello.sh
```

Results:

- Win64 `art.dll` and `dalvikvm.exe`: build PASS;
- Win64 JIT smoke under Wine: 12/12 PASS;
- Linux `libart.so` and `dalvikvm`: full rebuild PASS; and
- Linux L-005 imageless Hello: PASS, exit 0.

Stage A does not close W-013. Direct mspace-owner attachment, Windows address
policy/ownership, explicit page-state operations, low-VA reduction, native
Windows stress, and the complete closure matrix remain.
