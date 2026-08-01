# Attached-thread entry result

The `w002attachprobe` JNI DSO exercises native-thread attach and managed-entry
transitions. It is currently applicable only to `windows-x86_64-msvc`.

| Build | Runtime | Last checked |
|---|---|---|
| verified | verified | 2026-08-01 |

The unified `stage:w002` gate passed natively on Windows Server 2025 x86-64 in
both nterp and switch modes, twice per mode. Every run completed 16 native
thread attach/callback/detach cycles and observed JIT compilation of the Java
callback. The identical stage repeat reported `ninja: no work to do` and
passed 4/4 CTest gates again. The aggregate JSON contains four successful
records, stable input hashes, no host absolute paths, and no dump files.

This declaration uses the typed `windows`/`x86_64`/`msvc` intersection.
Windows AArch64 and ARM64EC remain non-applicable until separately compiled,
reviewed for their calling conventions, and run.
