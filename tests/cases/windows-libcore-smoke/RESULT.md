# Windows libcore smoke — result

**Status:** **COMPLETE** — unified native probes pass on the authoritative
Windows Server 2025 host; A4–A7 + Option H + product golden app also pass on
the historical Windows 10 host and Wine oracle

**Latest acceptance:** 2026-08-01

**Original Phase-3 acceptance:** 2026-07-16
**Plan:** [win32_filesystem.md](../../../win32_filesystem.md) (Option H locked; Windows NIO non-goal)

## Scope delivered

Phase 3 libcore bring-up for Windows x64 imageless ART:

- Option H filesystem + `;` classpath + absolute/mixed `C:\` paths
- Classic `java.io` + Os PE natives (errno + UTF-8)
- A4 core (charset/reflect/arraycopy/monitors, Runtime memory, clocks, `java.version=1.8.0`)
- A5 LOS + forced `System.gc`
- A6 interrupt + thread stress
- A7 classic sockets + DNS/localhost resolve
- A8-lite uncaught exception path
- Product **GoldenApp**
- Host smoke package + **G12 real Windows goldens**

## Gates

| Gate | Status | Evidence |
|------|--------|----------|
| G0–G11 wine suite | **PASS** | `evidence/all_wine_gates.txt` |
| G12 host package | **PASS** | `dist/windows_x64_phase3_host` / packager |
| G12 real Windows host | **PASS** | `evidence/host/RESULT_HOST.txt`, `logs_20260716T205926/` |

## Unified native probe ownership

The fixed-message BoringSSL SHA-256 probe and the process-wide CRT
file-descriptor/Winsock registry probe now live beside this result and are
declared by the common test catalog. Both remain typed for the currently
verified Windows x86-64 MSVC profile and are `target-runnable`; that selector
may expand to Windows AArch64 or ARM64EC only after each native runtime gate
passes there. Their build and execution use the unified product targets
`crypto_static` and `openjdkjvm`, not the retired libcore/ICU product graph.

### Latest unified native acceptance

The authoritative Windows Server 2025 x86-64 host configured a fresh regular-
file source projection and output tree with Python 3.13.14, CMake 3.31.8,
Ninja 1.13.2, LLVM 21.1.8 GNU-style Clang drivers, and the official configured
JDK 21.0.12. No POSIX shell, Make, NMake, PowerShell, WSL, Cygwin, MSVC
compiler driver, or `clang-cl` participated.

Thirteen accepted Phase-3 behaviors are now target-runnable through the common
W-004 catalog and one case-local Python runner with a checked-in JSON contract
matrix. Core/charset/monitor, DNS, ordinary and forced GC, GoldenApp,
interruption, file I/O, TCP loopback, errno/UTF-8 paths, properties/clocks,
runtime memory, thread stress, and the expected-nonzero uncaught-exception path
all run without Bash, Wine, PowerShell, or a package handoff. Path/AbsPath and
the separate L-003 matrix remain compile-only pending their next migration
slice.

```text
python tools/build_art.py test --target-id windows-x86_64-msvc --stage w004 --parallel 16

W-004: 19/19 PASS in 25.15 seconds
repeat: ninja: no work to do; 19/19 PASS in 21.44 seconds
Linux-hosted Windows cross reviewer: PASS with --parallel 32
```

The first native DNS run exposed that the Win32 `getnameinfo` JNI bridge called
Java `InetAddress.getHostAddress()`, which calls the same native bridge and
recursed. The maintained bridge now converts the Java address to `sockaddr`,
maps bionic name-info flag values to Winsock values, and calls Unicode
`GetNameInfoW`; the rebuilt `javacore.dll` passes DNS resolution and loopback
payload acceptance. The superseded Phase-3 Bash producers and runners for
these 13 cases were removed after native acceptance.

The generated binaries, managed artifacts, routine logs, and build trees
remain outside VCS. W-027 tracks the probe's current `GetTempPathA`,
`GetTempFileNameA`, and `DeleteFileA` calls together with the broader Win32
encoding audit; they did not block this ownership/runtime migration.

### Real Windows host (authoritative G12)

Original returned-package SHA-256:
`4f15b7808a7ff6039663d9931523a82b33c429d00a6a7b068eecb36feac58e3b`.
The ZIP is retained outside VCS; the accepted text result and analysis remain
under `evidence/host/`. The runner working directory is normalized as
`<host-workdir>\windows_x64_phase3_host`.

```text
OVERALL PASS
Hello java.version=1.8.0
props.ok=true user.dir=C:\Users\sulfate\Desktop\windows_x64_phase3_host
NetProbe.done=ok match=true
dns.ok=true payload=dns-ok
golden.ok=true served=32
AbsPathProbe.fails=0 (C:\art_phase3\...)
gc.forced.ok=true threadstress.ok=true
throw: phase3-throw-ok
```

Analysis: `evidence/host/ANALYSIS_20260716T205926.md`

### Wine oracle

```text
PASS all wine Phase 3 gates
package smoke_package_wine64.sh OVERALL PASS
```

## Critical fixes landed during Phase 3

- Option H WinNT FS, `;` classpath, ASCII drive letters
- PE file/socket natives; Runtime `JVM_*` memory exports
- LOS MemMap VirtualQuery; System.gc hang (ThreadCpuNanoTime + WaitOnAddress)
- `java.version` via recompiled `sun.misc.Version`
- Real System clocks / user props
- Win10 `poll EINVAL` → `select()`-based poll
- Host cmd `ERRORLEVEL` clobber after `type`
- DnsProbe hang: `localhost`/`::1` vs `127.0.0.1` + missing `SO_TIMEOUT`

## Non-goals (unchanged)

- Windows NIO.2 provider
- WSL2 as product runtime
- Full JIT/dex2oat (Phase 5 optional)

## Current reproduction

```text
python tools/build_art.py test --target-id windows-x86_64-msvc --stage w004 --parallel 16
python tools/build_art.py test --target-id windows-x86_64-msvc --stage w013 --parallel 16
```

## Historical Phase-3 evidence

The old Wine and returned-host-package results remain evidence, not maintained
reproduction paths. Current reproduction uses only the unified frontend and
the `w004` virtual stage above.
