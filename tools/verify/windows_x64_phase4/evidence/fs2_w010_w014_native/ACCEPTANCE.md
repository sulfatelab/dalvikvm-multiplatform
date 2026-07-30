# FS-2 native W-010/W-014 acceptance

**State:** ACCEPTED
**Date:** 2026-07-30
**Host:** Microsoft Windows Server 2025 Datacenter Evaluation, x64, build 26100

## Issued package and result

The rebuilt package passed the Linux-side structural checker and complete Wine
host smoke before transfer:

```text
package=dist/windows_x64_w010_w014_host_fs2.zip
sha256=935ab419124782bf8ac98546f38c352d4a32223466f3fe962f3c64dd3afd21bd
```

The native runner was executed from the extracted package with
`RUN_W010_W014_HOST.ps1`. Its retained `logs/RESULT_W010_W014.txt` contains
the ordinary 30-record E9 matrix plus the FS-2 records and ends with:

```text
PASS fatal_dump_scan count=6
OVERALL PASS
```

The six dumps are the embedding diagnostic dump and the five intentional
static/JIT/OSR fatal cases. `HANDLED_DMP_SCAN.txt` contains
`NO_HANDLED_DMP_FILES`; all fatal dumps have the `MDMP` signature and are
listed with size and SHA-256 in `FATAL_DMP_SCAN.txt`.

## FS-2 gates

- The real process policy probe reports `actual=disabled`,
  `flags=0x00000100`, and `known_incompatible=0x00000000`.
- All nine named incompatible CET/HSP policy overrides reject startup before
  Java/JIT and produce no dump. `dynamic-apis-out-of-proc-only` and
  `reserved-all` both remain accepted and complete the managed NPE probe.
- The native debug loop observes a first-chance AV for threshold-zero JIT NPE,
  continues it with `DBG_EXCEPTION_NOT_HANDLED`, and the child reports
  `first_av=128`, `second_chance=0`, and a clean exit. Explicit SOE reports
  `first_av=0`, `first_stack_overflow=0`, `second_chance=0`, and a clean exit.
- The managed callback exception sentinel passes in nterp, switch, and JIT,
  including two repeats per mode. It reports
  `exceptionMask=0 exceptionCaught=32 exceptionIterations=32
  exceptionSelfTestMask=1023`, proving full-width XMM6-XMM15 state survives
  the exception/unwind path.
- The JNI embedding probe installs a predecessor UEF and foreign VEH, checks
  predecessor chaining and frame SEH while ART is active, installs a later UEF,
  destroys/unloads ART, and verifies the later UEF remains installed while no
  stale ART callback runs.

Selected native logs and the complete result record are retained beside this
file. The package archive and host location are recorded in `ARCHIVE_SHA256SUMS.txt`
and `HOST_INFO.txt`; minidump binaries remain in the returned Windows package
rather than in the source tree.

## Remaining work

FS-2 closes its four requested native proof points. Remaining W-010/W-014 work
is limited to second-host repetition, reservation-correlation/pending-range
conditional probes, wrong-address and unsupported-exception negatives, and
debugger-quality dump-stack reconstruction. None reopens the accepted managed
fault, CET classifier, UEF teardown, or exception-XMM behavior.
