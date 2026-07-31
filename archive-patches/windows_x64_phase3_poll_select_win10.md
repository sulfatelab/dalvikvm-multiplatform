# Windows x64 Phase 3 — poll EINVAL on real Windows 10

Status: applied in `tools/windows_x64/jni_stubs/win_net_natives.c`. The rule is
Windows-platform behavior and is not specific to x86_64.

**Evidence:** host logs 2026-07-16 (`logs-win10-20260716T195646.zip`).

**Symptom:** `ServerSocket.accept` → `libcore.io.Linux.poll` → `ErrnoException: poll failed: EINVAL`.
Fails NetProbe/DnsProbe/GoldenApp on real Win10; wine64 suite still green with WSAPoll.

**Cause:** `WSAPoll` on sockets obtained via `_open_osfhandle(SOCKET)` returned `WSAEINVAL`
on the host. Bind/listen/accept themselves worked; only poll failed.

**Fix:** implement `Java_libcore_io_Linux_poll` with Winsock `select()`, and use the same
helper for SocketInputStream timeout wait / SocketOutputStream writable wait.

**Also:** host `.cmd` must capture `%ERRORLEVEL%` into `RC` before `type` (which zeros ERRORLEVEL).

**Verify:** wine net/dns/golden PASS; re-run G12 on Windows with rebuilt package.
