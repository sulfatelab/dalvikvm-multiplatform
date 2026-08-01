# L-003 runtime matrix

**Status:** PARTIAL — Exec and IPv6 are accepted natively; Locale, UDP, and
Zip remain native-open and compile-only

**Latest acceptance:** 2026-08-01

## Current unified result

All five managed artifacts are built by the common CMake/Ninja graph from the
canonical sources under `tests/cases/windows-libcore-smoke/`. Runtime status is
deliberately narrower than build status:

| Probe | Current `windows-x86_64-msvc` status | Native Windows Server 2025 result |
|---|---|---|
| `ExecProbe` | `target-runnable` | PASS: `Runtime.exec` and `ProcessBuilder` each returned exit 0 and the expected output |
| `Ipv6Probe` | `target-runnable` | PASS: AF_INET6 socket, bind to `::`, and `getsockname` contract completed |
| `LocaleProbe` | `compile-only` | OPEN: timed out after 120 seconds |
| `UdpProbe` | `compile-only` | OPEN: `DatagramSocket` construction failed with `setsockopt failed: EINVAL` |
| `ZipProbe` | `compile-only` | OPEN: timed out after 120 seconds |

The authoritative native reproduction is:

```text
python tools/build_art.py test --target-id windows-x86_64-msvc --stage w004 --parallel 16
```

The resulting W-004 stage passed 23/23, including Exec and IPv6. Its immediate
repeat reported `ninja: no work to do.` and passed 23/23 again. The fresh
Linux-hosted Windows cross graph used `--parallel 32`, passed its structural
reviewer, and repeated as a Ninja no-op. Neither host used a Phase-3 shell
builder or Wine runner.

Applicability remains exactly Windows + x86-64 + MSVC ABI. This result does not
claim support for another Windows architecture or ABI; each future target must
be promoted independently after its native behavior passes.

## Historical Wine evidence

On 2026-07-17 the retired `run_l003_wine.sh` flow reported all five probes as
passing under Wine, including Locale, Zip, and UDP. That result remains useful
porting evidence in this directory, but it is not native Windows acceptance
and does not override the three failures above. The generic builder, runner,
and L-003 orchestration were removed after the supported subset moved to the
unified shell-free catalog.

Historical implementation notes still apply: the Windows ZipFile CEN path uses
heap read plus a DirectByteBuffer mirror, and IPv6 avoids reverse-DNS side
effects. TCP IPv4-mapped dual-stack is outside the accepted IPv6 bind contract.
