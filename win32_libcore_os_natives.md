# Win32 libcore Os / `Linux` natives map

**Status:** living design map for hybrid `libjavacore`  
**Preferred name:** `win32_libcore_os_natives.md` (clearer than `win32_libcore_syscalls.md`)  
**Related:** L-001, W-007, [filesystem_win32.md](filesystem_win32.md), `tools/win64/jni_stubs/win_{fs,net}_natives.c`  
**Scope:** `libcore.io.Linux` JNI used by `Os` / IoBridge — **not** NIO.2 `sun.nio.fs`.

## Rules

1. **Implemented** — real Win32/Winsock/CRT behavior registered in hybrid PE.
2. **Needed** — product paths (java.io, classic sockets, mmap, env) must not stay ENOSYS.
3. **ENOSYS** — may fail with `ErrnoException(ENOSYS)`; not required for Phase 3–4 goldens.
4. Full AOSP `libcore_io_Linux.cpp` remains **excluded** until compat covers its include set; grow Win bridges instead.
5. Update this file when natives change bucket.

## Summary

| Bucket | Count |
|--------|------:|
| implemented | 59 |
| registered_missing_impl | 0 |
| impl_unregistered | 0 |
| needed | 16 |
| enosys | 46 |
| **Total `Linux.java` natives** | **121** |

## Implemented

| Method | Source |
|--------|--------|
| `accept` | win_fs/win_net/hello3 |
| `access` | win_fs/win_net/hello3 |
| `android_fdsan_exchange_owner_tag` | win_fs/win_net/hello3 |
| `android_fdsan_get_owner_tag` | win_fs/win_net/hello3 |
| `android_fdsan_get_tag_type` | win_fs/win_net/hello3 |
| `android_fdsan_get_tag_value` | win_fs/win_net/hello3 |
| `android_getaddrinfo` | win_fs/win_net/hello3 |
| `bind` | win_fs/win_net/hello3 |
| `bind` | win_fs/win_net/hello3 |
| `close` | win_fs/win_net/hello3 |
| `connect` | win_fs/win_net/hello3 |
| `connect` | win_fs/win_net/hello3 |
| `dup` | win_fs/win_net/hello3 |
| `dup2` | win_fs/win_net/hello3 |
| `environ` | win_fs (+posix stubs) |
| `fcntlInt` | win_fs/win_net/hello3 |
| `fcntlVoid` | win_fs/win_net/hello3 |
| `fdatasync` | win_fs/win_net/hello3 |
| `fstat` | win_fs/win_net/hello3 |
| `fsync` | win_fs/win_net/hello3 |
| `ftruncate` | win_fs (+posix stubs) |
| `gai_strerror` | win_fs (+posix stubs) |
| `getenv` | win_fs/win_net/hello3 |
| `getpeername` | win_fs/win_net/hello3 |
| `getpwnam` | win_fs/win_net/hello3 |
| `getpwuid` | win_fs/win_net/hello3 |
| `getsockname` | win_fs/win_net/hello3 |
| `getsockoptInt` | win_fs/win_net/hello3 |
| `getsockoptLinger` | win_fs/win_net/hello3 |
| `ioctlInt` | win_fs/win_net/hello3 |
| `isatty` | win_fs (+posix stubs) |
| `listen` | win_fs/win_net/hello3 |
| `lseek` | win_fs/win_net/hello3 |
| `lstat` | win_fs/win_net/hello3 |
| `madvise` | win_fs (+posix stubs) |
| `mincore` | win_fs (+posix stubs) |
| `mkdir` | win_fs/win_net/hello3 |
| `mlock` | win_fs (+posix stubs) |
| `mmap` | win_fs (+posix stubs) |
| `msync` | win_fs (+posix stubs) |
| `munlock` | win_fs (+posix stubs) |
| `munmap` | win_fs (+posix stubs) |
| `open` | win_fs/win_net/hello3 |
| `poll` | win_fs/win_net/hello3 |
| `posix_fallocate` | win_fs (+posix stubs) |
| `readlink` | win_fs (+posix stubs) |
| `realpath` | win_fs/win_net/hello3 |
| `remove` | win_fs/win_net/hello3 |
| `rename` | win_fs/win_net/hello3 |
| `setsockoptInt` | win_fs/win_net/hello3 |
| `setsockoptLinger` | win_fs/win_net/hello3 |
| `shutdown` | win_fs/win_net/hello3 |
| `socket` | win_fs/win_net/hello3 |
| `socketpair` | win_fs/win_net/hello3 |
| `stat` | win_fs/win_net/hello3 |
| `strerror` | win_fs (+posix stubs) |
| `sysconf` | win_fs/win_net/hello3 |
| `uname` | win_fs/win_net/hello3 |
| `unlink` | win_fs/win_net/hello3 |

## Needed (product)

| Method | Priority | Backend sketch |
|--------|----------|----------------|
| `chmod` | medium | Winsock/CRT or Win32 |
| `fchmod` | medium | Winsock/CRT or Win32 |
| `getnameinfo` | medium | Winsock/CRT or Win32 |
| `getsockoptByte` | medium | Winsock/CRT or Win32 |
| `getsockoptTimeval` | high | Winsock/CRT or Win32 |
| `if_indextoname` | medium | Winsock/CRT or Win32 |
| `if_nametoindex` | medium | Winsock/CRT or Win32 |
| `inet_pton` | medium | Winsock/CRT or Win32 |
| `pipe2` | high | Winsock/CRT or Win32 |
| `readv` | high | Winsock/CRT or Win32 |
| `recvmsg` | high | Winsock/CRT or Win32 |
| `sendfile` | high | Winsock/CRT or Win32 |
| `sendmsg` | high | Winsock/CRT or Win32 |
| `setsockoptByte` | medium | Winsock/CRT or Win32 |
| `setsockoptTimeval` | high | Winsock/CRT or Win32 |
| `writev` | high | Winsock/CRT or Win32 |

## ENOSYS / unsupported for now

| Method | Rationale |
|--------|-----------|
| `capget` | Linux-specific / rare / non-goal for classic ART PE |
| `capset` | Linux-specific / rare / non-goal for classic ART PE |
| `chown` | Linux-specific / rare / non-goal for classic ART PE |
| `dladdr` | Linux-specific / rare / non-goal for classic ART PE |
| `execv` | Linux-specific / rare / non-goal for classic ART PE |
| `execve` | Linux-specific / rare / non-goal for classic ART PE |
| `fchown` | Linux-specific / rare / non-goal for classic ART PE |
| `fstatvfs` | Linux-specific / rare / non-goal for classic ART PE |
| `getifaddrs` | Linux-specific / rare / non-goal for classic ART PE |
| `getpgid` | Linux-specific / rare / non-goal for classic ART PE |
| `getrlimit` | Linux-specific / rare / non-goal for classic ART PE |
| `getsockoptInAddr` | Linux-specific / rare / non-goal for classic ART PE |
| `getsockoptUcred` | Linux-specific / rare / non-goal for classic ART PE |
| `getxattr` | Linux-specific / rare / non-goal for classic ART PE |
| `ioctlFlags` | Linux-specific / rare / non-goal for classic ART PE |
| `ioctlInetAddress` | Linux-specific / rare / non-goal for classic ART PE |
| `ioctlMTU` | Linux-specific / rare / non-goal for classic ART PE |
| `kill` | Linux-specific / rare / non-goal for classic ART PE |
| `lchown` | Linux-specific / rare / non-goal for classic ART PE |
| `link` | Linux-specific / rare / non-goal for classic ART PE |
| `listxattr` | Linux-specific / rare / non-goal for classic ART PE |
| `memfd_create` | Linux-specific / rare / non-goal for classic ART PE |
| `mkfifo` | Linux-specific / rare / non-goal for classic ART PE |
| `prctl` | Linux-specific / rare / non-goal for classic ART PE |
| `removexattr` | Linux-specific / rare / non-goal for classic ART PE |
| `setegid` | Linux-specific / rare / non-goal for classic ART PE |
| `setenv` | Linux-specific / rare / non-goal for classic ART PE |
| `seteuid` | Linux-specific / rare / non-goal for classic ART PE |
| `setgid` | Linux-specific / rare / non-goal for classic ART PE |
| `setpgid` | Linux-specific / rare / non-goal for classic ART PE |
| `setregid` | Linux-specific / rare / non-goal for classic ART PE |
| `setreuid` | Linux-specific / rare / non-goal for classic ART PE |
| `setsid` | Linux-specific / rare / non-goal for classic ART PE |
| `setsockoptGroupReq` | Linux-specific / rare / non-goal for classic ART PE |
| `setsockoptIfreq` | Linux-specific / rare / non-goal for classic ART PE |
| `setsockoptIpMreqn` | Linux-specific / rare / non-goal for classic ART PE |
| `setuid` | Linux-specific / rare / non-goal for classic ART PE |
| `setxattr` | Linux-specific / rare / non-goal for classic ART PE |
| `splice` | Linux-specific / rare / non-goal for classic ART PE |
| `statvfs` | Linux-specific / rare / non-goal for classic ART PE |
| `strsignal` | Linux-specific / rare / non-goal for classic ART PE |
| `symlink` | Linux-specific / rare / non-goal for classic ART PE |
| `tcdrain` | Linux-specific / rare / non-goal for classic ART PE |
| `tcsendbreak` | Linux-specific / rare / non-goal for classic ART PE |
| `unsetenv` | Linux-specific / rare / non-goal for classic ART PE |
| `waitpid` | Linux-specific / rare / non-goal for classic ART PE |

## AOSP Memory (`libcore.io.Memory`)

| Piece | Status |
|-------|--------|
| `luni/.../libcore_io_Memory.cpp` | **In hybrid javacore** (2026-07-17) |
| ART `runtime/native/libcore_io_Memory.cc` peek*Array | ART runtime registration |

## `libcore_io_Linux.cpp` strategy

Do **not** compile full AOSP `libcore_io_Linux.cpp` on Win yet (Bionic headers: xattr, capability, rtnetlink, ifaddrs, fdsan, …).
Product path: **Win bridges** + this map. Revisit filtered AOSP compile only after compat covers includes.

## Related open items

| ID | Relation |
|----|----------|
| L-001 | Overall PE libcore surface |
| W-007 | sockets/poll via select |
| W-009 | compat POSIX stub quality |
| W-017 | openjdk NIO exclusions |

*Inventory derived from `Linux.java` + `register_libcore_io_Linux_win.cpp` + win_fs/win_net/hello3.*
