# Debugger fault result

The probe covers Windows debugger interaction with managed fault and overflow
paths. Its current selector is `windows` / `x86_64` / `msvc`.

| Build | Runtime | Last checked |
|---|---|---|
| verified | verified on Windows Server 2025 build 26100 | 2026-08-01 12:35:42 |

The shell-free unified gate passed NPE and SOE modes twice in native
`stage:w010`. The debugger observed and continued the first-chance managed NPE
AV, observed no hardware fault for the explicit SOE path, received no
second-chance exception, and both children exited zero without a minidump. The
final stage build was a Ninja no-op.

The runner launches the frontend-provided absolute `dalvikvm.exe` while keeping
its working data isolated below the target output. Copying only the EXE into
the work directory was rejected: it changed Windows DLL search order and bound
`icu_jni.dll` to the incompatible system `icuuc.dll`, causing
`STATUS_ENTRYPOINT_NOT_FOUND`. The absolute product EXE keeps the matching
product DLL directory first without recording that machine path in result
JSON.

The unified Windows cross stage also rebuilt this source. No other target is
currently applicable. `CreateProcessA` remains tracked for the later W-027
repository-wide A-to-W Win32 API audit; it is not treated as a portability
claim.
