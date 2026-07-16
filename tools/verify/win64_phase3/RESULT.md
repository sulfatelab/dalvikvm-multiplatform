# Win64 Phase 3 — RESULT

**Status:** **COMPLETE** — A4–A7 + Option H + product golden app **PASS on real Windows 10 host** (and wine oracle)  
**Date:** 2026-07-16  
**Plan:** [filesystem_win32.md](../../../filesystem_win32.md) (Option H locked; Windows NIO non-goal)

## Scope delivered

Phase 3 libcore bring-up for Win64 imageless ART:

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
| G12 host package | **PASS** | `dist/win64_phase3_host` / packager |
| G12 real Windows host | **PASS** | `evidence/host/RESULT_HOST.txt`, `logs_20260716T205926/` |

### Real Windows host (authoritative G12)

Zip: `evidence/host/logs-20260716T205926.zip`  
Host dir: `C:\Users\sulfate\Desktop\win64_phase3_host`

```text
OVERALL PASS
Hello java.version=1.8.0
props.ok=true user.dir=C:\Users\sulfate\Desktop\win64_phase3_host
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

## Repro

```bash
# Wine
bash tools/verify/win64_phase3/run_all_wine_gates.sh
# Host package
bash tools/win64/host_package/package_win64_phase3.sh
# On Windows: scripts\run_all_host.cmd
```
