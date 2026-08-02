# ART compiler DSO topology result

## Contract

Both the runtime and compiler shared objects must load from the target build
closure. `libart-compiler.so` must contain a direct `DT_NEEDED` entry for
`libart.so`, while `libart.so` must not contain a reverse dependency on
`libart-compiler.so`. The shell-free Python wrapper parses ELF program and
dynamic tables without `readelf` or another POSIX utility, then runs one
plain-Clang target executable that loads both DSOs with immediate symbol
resolution. Native and cross-runner execution use the same executable and
result schema.

## Target status

| Target ID | Applicable | Build | Runtime | Last accepted |
|---|---:|---:|---:|---|
| `linux-x86_64-gnu` | yes | verified | verified | 2026-08-02 |
| `linux-aarch64-gnu` | yes | verified | verified | 2026-08-02 |
| `windows-x86_64-msvc` | no | not applicable | not applicable | — |

## Linux AArch64 acceptance

A fresh 38-module configuration audited 2,113 compile commands, 2,196 Ninja
commands, and 32 product links. Its 1,624-edge W-004 build used explicit
`-fPIC -fPIE` and `-pie` for the loader, linked `libart-compiler.so`, and passed
W-004 5/5 in 85.13 seconds. The topology gate passed in 0.71 seconds. The
identical repeat began with `ninja: no work to do`, passed 5/5 in 86.33
seconds, and passed topology in 0.68 seconds.

Both runs observed the direct `libart-compiler.so -> libart.so` edge, absence
of the reverse edge, an exact-zero target exit, and the target load marker.
The accepted AArch64 loader SHA-256 is
`9e37a643d5a758d7003ec6f170a6ad8ab6522f6145e7e442f2a0f5f468283d5c`;
the compiler DSO SHA-256 is
`a3888572127e886320dc8ca53bbed89ca271dc09e50769d555f3f84c0e8186f8`.
The sanitized result records the normalized QEMU fingerprint and contains no
machine path. Source and result scans found no filesystem links.

## Native Linux x86-64 regression

A fresh 37-module configuration audited 2,089 compile commands, 2,172 Ninja
commands, and 32 product links. The 1,859-edge W-004 graph also rebuilt its
native boot image and passed 6/6 in 2.47 seconds. Its repeat began with
`ninja: no work to do` and passed 6/6 in 2.47 seconds. The unified target-side
topology executable passed in 0.37 seconds in both runs, replacing the former
host-architecture `ctypes` load without weakening the dependency-edge checks.
The accepted x86-64 loader SHA-256 is
`9c6e9a7d85f5cb93f588b2d74644d892627e8400a4c7ce8e6b77e15ed5577303`.

Windows PE load, import, export, and no-cycle acceptance remains separately
recorded by the native Windows baseline; this ELF gate does not claim Windows
applicability.
