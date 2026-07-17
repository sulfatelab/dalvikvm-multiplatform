# Win32 libcore Os / `Linux` natives map

**Status:** living design map for hybrid `libjavacore`  
**Preferred name:** `win32_libcore_os_natives.md` (vs `win32_libcore_syscalls.md`)  
**Related:** L-001, W-007, [filesystem_win32.md](filesystem_win32.md)  
**Scope:** `libcore.io.Linux` / private helper natives used by Os & IoBridge (not NIO.2).

## Rules

1. **Implemented** — registered + Win bridge/AOSP Memory behavior in product PE.
2. **Needed** — product paths must get a real backend (not permanent ENOSYS).
3. **ENOSYS** — Linux-only / rare; fail cleanly.
4. Full AOSP `libcore_io_Linux.cpp` remains excluded; grow Win bridges.
5. Update when natives move buckets.

## Summary

| Bucket | Count |
|--------|------:|
| implemented | 80 |
| registered_missing_impl | 0 |
| impl_unregistered | 0 |
| needed | 0 |
| enosys | 46 |
| **Total tracked natives** | **126** |

## Implemented

| Method |
|--------|
| `accept` |
| `access` |
| `android_fdsan_exchange_owner_tag` |
| `android_fdsan_get_owner_tag` |
| `android_fdsan_get_tag_type` |
| `android_fdsan_get_tag_value` |
| `android_getaddrinfo` |
| `bind` |
| `chmod` |
| `close` |
| `connect` |
| `dup` |
| `dup2` |
| `environ` |
| `fchmod` |
| `fcntlInt` |
| `fcntlVoid` |
| `fdatasync` |
| `fstat` |
| `fsync` |
| `ftruncate` |
| `gai_strerror` |
| `getenv` |
| `getnameinfo` |
| `getpeername` |
| `getpwnam` |
| `getpwuid` |
| `getsockname` |
| `getsockoptByte` |
| `getsockoptInt` |
| `getsockoptLinger` |
| `getsockoptTimeval` |
| `if_indextoname` |
| `if_nametoindex` |
| `inet_pton` |
| `ioctlInt` |
| `isatty` |
| `listen` |
| `lseek` |
| `lstat` |
| `madvise` |
| `mincore` |
| `mkdir` |
| `mlock` |
| `mmap` |
| `msync` |
| `munlock` |
| `munmap` |
| `open` |
| `pipe2` |
| `poll` |
| `posix_fallocate` |
| `preadBytes` |
| `pwriteBytes` |
| `readBytes` |
| `readlink` |
| `readv` |
| `realpath` |
| `recvfromBytes` |
| `recvmsg` |
| `remove` |
| `rename` |
| `sendfile` |
| `sendmsg` |
| `sendtoBytes` |
| `setsockoptByte` |
| `setsockoptInt` |
| `setsockoptLinger` |
| `setsockoptTimeval` |
| `shutdown` |
| `socket` |
| `socketpair` |
| `stat` |
| `strerror` |
| `sysconf` |
| `umaskImpl` |
| `uname` |
| `unlink` |
| `writeBytes` |
| `writev` |

## ENOSYS / unsupported for now

| Method |
|--------|
| `capget` |
| `capset` |
| `chown` |
| `dladdr` |
| `execv` |
| `execve` |
| `fchown` |
| `fstatvfs` |
| `getifaddrs` |
| `getpgid` |
| `getrlimit` |
| `getsockoptInAddr` |
| `getsockoptUcred` |
| `getxattr` |
| `ioctlFlags` |
| `ioctlInetAddress` |
| `ioctlMTU` |
| `kill` |
| `lchown` |
| `link` |
| `listxattr` |
| `memfd_create` |
| `mkfifo` |
| `prctl` |
| `removexattr` |
| `setegid` |
| `setenv` |
| `seteuid` |
| `setgid` |
| `setpgid` |
| `setregid` |
| `setreuid` |
| `setsid` |
| `setsockoptGroupReq` |
| `setsockoptIfreq` |
| `setsockoptIpMreqn` |
| `setuid` |
| `setxattr` |
| `splice` |
| `statvfs` |
| `strsignal` |
| `symlink` |
| `tcdrain` |
| `tcsendbreak` |
| `unsetenv` |
| `waitpid` |

## Memory

| Piece | Status |
|-------|--------|
| AOSP `libcore_io_Memory.cpp` | In hybrid javacore |
| ART peek*Array Memory | ART runtime |

## Linux.cpp strategy

Keep AOSP `libcore_io_Linux.cpp` **out** on Win. Implement semantics via `win_fs_natives.c` / `win_net_natives.c` + register table.

*Updated after L-001 deepen pass: implemented=80, needed=0, enosys=46.*
