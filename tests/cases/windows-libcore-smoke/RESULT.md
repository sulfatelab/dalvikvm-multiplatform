# Libcore smoke — result

**Status:** **COMPLETE for the promoted native Windows matrix and the exact
Linux CoreProbe/InterruptProbe slice** — 25 unified libcore behaviors pass on
the authoritative Windows Server 2025 host; CoreProbe and InterruptProbe
additionally pass on Linux x86-64 and AArch64; no named L-003 case remains
native-open

**Latest acceptance:** 2026-08-02

**Original Phase-3 acceptance:** 2026-07-16
**Plan:** [win32_filesystem.md](../../../win32_filesystem.md) (Option H locked; Windows NIO non-goal)

## Scope delivered

Phase 3 libcore bring-up for Windows x86-64 imageless ART:

- Option H filesystem + `;` classpath + absolute/mixed `C:\` paths
- Classic `java.io` + Os PE natives (errno + UTF-8)
- A4 core (charset/reflect/arraycopy/monitors, Runtime memory, clocks, `java.version=1.8.0`)
- A5 LOS + forced `System.gc`
- A6 interrupt + thread stress
- A7 classic sockets + DNS/localhost resolve
- A8-lite uncaught exception path
- Product **GoldenApp**
- Historical host package + **G12 real Windows goldens**

## Gates

| Gate | Status | Evidence |
|------|--------|----------|
| G0–G11 wine suite | **HISTORICAL PASS** | summary retained below; raw machine-path log removed |
| G12 host package | **HISTORICAL PASS** | issued archive hash recorded below; producer retired |
| G12 real Windows host | **PASS** | compact result and two analyses under `evidence/windows-x86_64-msvc/` |

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

Twenty-five accepted Phase-3 behaviors are now target-runnable through the common
W-004 catalog and one case-local Python runner with a checked-in JSON contract
matrix. Core/charset/monitor, DNS, ordinary and forced GC, GoldenApp,
interruption, file I/O, TCP loopback, errno/UTF-8 paths, properties/clocks,
runtime memory, thread stress, and the expected-nonzero uncaught-exception path
all run without Bash, Wine, PowerShell, or a package handoff. UDP now validates
an IPv4 loopback datagram payload and peer address. PathProbe and
AbsPathProbe add eight shell-free subcases covering multi-JAR semicolon
classpath, structured drive/mixed/UNC paths, three absolute JAR path forms,
and two required colon-separator failures. ExecProbe adds `Runtime.exec` and
`ProcessBuilder` marker/exit validation; Ipv6Probe adds AF_INET6 bind and
`getsockname` validation without reverse-DNS side effects. LocaleProbe now
requires US locale identity/case conversion, UTC epoch/calendar arithmetic,
and a `zh-Hans-CN` language-tag round trip. It deliberately does not claim
resource-backed display names or collation: the current runtime reports a null
display language and catches a missing-resource exception for its soft
collator check. ZipProbe now requires the exact CRC32 marker, a raw
DEFLATE/INFLATE round trip, three matching entries through both stream and
`ZipFile` readers, successful lookup, and deletion of its temporary ZIP.
BnProbe requires deterministic BigInteger addition, multiplication, remainder,
modular exponentiation, and byte-array round-trip behavior through NativeBN.
OsConstantsProbe requires all 18 exact Android/bionic AF/SOCK, errno,
address-info, file, signal, sysconf, and name-info constants consumed by the
Windows bridge.
XmlProbe requires namespace-aware SAX parsing through the Harmony Expat path,
with exactly three elements and `helloworld` character content.
SocketAddressProbe requires `android.system.Os` bind/connect/accept and address
conversion to return positive-port loopback local and peer addresses.
AsyncCloseProbe requires a closed server to unblock its blocked accept with a
socket error and a closed peer to unblock the client read with EOF or an I/O
error; both worker threads must terminate and no unexpected peer may appear.
Historical Wine success is evidence only and does not broaden this result.

Applicability remains per probe. CoreProbe and InterruptProbe are each accepted
on exactly `linux-x86_64-gnu`, `linux-aarch64-gnu`, and
`windows-x86_64-msvc`. Every other declaration in this case keeps its existing
Windows x86-64/MSVC selector until independently reviewed, built, and
runtime-tested on another exact target.

### Latest Linux CoreProbe acceptance

Fresh Linux graphs generated from the same 262 Blueprint files retained their
audited 2,089 x86-64 and 2,113 AArch64 compile commands, 2,172/2,196 Ninja
commands, and 32 product links. The fresh 1,863-edge x86-64 W-004 build passed
10/10 in 3.69 seconds, including CoreProbe in 0.23 seconds; its true Ninja
no-op repeat passed 10/10 in 3.68 seconds, including CoreProbe in 0.22 seconds.
The fresh 1,628-edge AArch64 build passed 9/9 in 92.17 seconds, including
CoreProbe in 1.55 seconds under the explicit target runner; its true Ninja
no-op repeat passed 9/9 in 92.92 seconds, including CoreProbe in 1.52 seconds.

Both CoreProbe records require exact-zero exit, successful array copy, the
UTF-8 `hello-χ` round trip, reflective `String` construction, the exact
2,000-update monitor result, `CoreProbe.done=ok`, and
`main end exception=0`. They use app JAR SHA-256
`063225c8763992495aa29267c07b479f86811905799fcba67de2d3d3e14128c1`
and boot JAR SHA-256
`45e19b8cc4a4161d7b7b011e268bf262069d9a7b70c9cfd9c37e324feb249eae`.
The manifests contain only normalized native/QEMU runner identity and no
absolute machine path; neither result tree contains a filesystem link.

### Latest Linux InterruptProbe acceptance

Fresh Linux graphs retained the same 262-Blueprint, 2,089/2,113-compile-command,
2,172/2,196-Ninja-command, and 32-product-link audits. The fresh 1,864-edge
x86-64 W-004 build passed 11/11 in 3.82 seconds; its true Ninja no-op repeat
passed 11/11 in 3.88 seconds, including InterruptProbe in 0.22 seconds. The
fresh 1,629-edge AArch64 build passed 10/10 in 93.88 seconds, including
InterruptProbe in 1.52 seconds; its true Ninja no-op repeat passed 10/10 in
93.98 seconds, including InterruptProbe in 1.51 seconds.

Both InterruptProbe records require exact-zero exit, a terminated sleeper
after interruption, `interrupt.ok=true`, `InterruptProbe.done=ok`, and
`main end exception=0`. They use app JAR SHA-256
`62f39baec03d56d02e2077b6e564e9fb9179486dc69277173c8bfdbc9cd84ea8`
and the same boot JAR hash recorded above. The manifests contain normalized
native/QEMU runner identity and no absolute machine path; neither result tree
contains a filesystem link.

```text
python tools/build_art.py test --target-id windows-x86_64-msvc --stage w004 --parallel 16

W-004: ninja: no work to do; 35/35 PASS in 49.03 seconds
repeat: ninja: no work to do; 35/35 PASS in 49.23 seconds
complete catalog: ninja: no work to do; 75/75 PASS in 132.83 seconds
Linux-hosted Windows cross reviewer: PASS; repeat Ninja no-op with --parallel 32
```

The first native DNS run exposed that the Win32 `getnameinfo` JNI bridge called
Java `InetAddress.getHostAddress()`, which calls the same native bridge and
recursed. The maintained bridge now converts the Java address to `sockaddr`,
maps bionic name-info flag values to Winsock values, and calls Unicode
`GetNameInfoW`; the rebuilt `javacore.dll` passes DNS resolution and loopback
payload acceptance. Native UDP then exposed that Android's bionic
`SO_BROADCAST = 6` crossed the JNI boundary unchanged. The maintained bridge
now maps that option to Winsock `SO_BROADCAST`; UdpProbe passes in 0.93/0.93
seconds across the stage and no-op repeat, then in 0.94 seconds after its peer
address marker was made mandatory. Its sanitized result contains no machine
path. All superseded Phase-3 Bash producers and runners were removed after the
supported behavior moved into the native catalog. LocaleProbe's old 120-second
timeout no longer reproduces in the current integrated runtime; it passes its
exact scoped contract in 0.95/0.96 seconds. Its sanitized result contains no
machine path. ZipProbe's historical timeout likewise does not reproduce: it
passed in 1.03/0.97 seconds across the stage and no-op repeat. Its strengthened
contract verifies temporary-ZIP deletion, and its sanitized result records exit
zero with no missing/forbidden markers or machine path. No named L-003 case now
requires a second runner; other W-004 compile-only declarations retain their
separate applicability. BnProbe passed its exact sum/remainder/modPow contract
in 0.93/0.96 seconds across the stage and no-op repeat. Its result records exit
zero with no missing/forbidden markers or machine path. OsConstantsProbe passed
all 18 exact-value markers in 0.94/0.94 seconds; its result is likewise clean.
XmlProbe passed its exact element/text contract in 0.93/0.98 seconds and wrote
the same sanitized result shape.
SocketAddressProbe passed its strengthened local/peer loopback contract in
0.94/0.94 seconds; its result is likewise clean.
AsyncCloseProbe passed both unblock contracts in 1.44/1.48 seconds, with no
forbidden unexpected-peer or explicit-failure marker and a clean result.

The generated binaries, managed artifacts, routine logs, and build trees
remain outside VCS. W-027 now rejects known or unclassified Win32 suffix-`A`
calls in the active Windows translation-unit graph; the accepted 1,441-source
graph contains zero ANSI calls, source files, or API families.

### Real Windows host (authoritative G12)

Original returned-package SHA-256:
`4f15b7808a7ff6039663d9931523a82b33c429d00a6a7b068eecb36feac58e3b`.
The ZIP is retained outside VCS; the accepted text result and analysis remain
under `evidence/windows-x86_64-msvc/`. The runner working directory is normalized as
`<host-workdir>\windows_x64_phase3_host`.

```text
OVERALL PASS
Hello java.version=1.8.0
props.ok=true user.dir=<host-workdir>\windows_x64_phase3_host
NetProbe.done=ok match=true
dns.ok=true payload=dns-ok
golden.ok=true served=32
AbsPathProbe.fails=0 (<absolute-test-root>\...)
gc.forced.ok=true threadstress.ok=true
throw: phase3-throw-ok
```

Analysis: `evidence/windows-x86_64-msvc/g12_acceptance_analysis.md`. The
preceding false-pass diagnosis is
`evidence/windows-x86_64-msvc/g12_failure_analysis.md`.

### Wine oracle

```text
PASS all wine Phase 3 gates
historical package smoke OVERALL PASS
```

The raw Wine transcript and duplicate returned-package logs were removed: they
contained machine paths but added no durable contract beyond this result and
the retained G12 analyses.

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
```

## Historical Phase-3 evidence

The old Wine and returned-host-package results remain evidence, not maintained
reproduction paths. Current reproduction uses only the unified frontend and
the `w004` virtual stage above. The shell package producer and Wine package
smoke were removed with the obsolete standalone libcore/ICU graph.
