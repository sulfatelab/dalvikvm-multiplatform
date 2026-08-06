# Windows x64 W-028 native result

**Date:** 2026-08-06
**Host:** Windows Server 2025 Datacenter Evaluation, x64, build 26100
**Status:** **PASS — Windows AOT/OAT implementation-sequence step 1 complete**

## Scope

W-028 is the native trivial no-image `dex2oat` operation gate. It compiles one
JAR with the `speed` filter, watchdog enabled, and forced swap, then validates
the resulting OAT/VDEX envelope. This result accepts generation-sequence step
1 only. It does not exercise `ImageWriter`, generate or stage a boot image,
load an executable OAT, register Windows unwind/CFG metadata, or prove that a
managed method executes from boot-OAT code.

## Source and toolchain identity

The fresh native workspace recorded these committed source identities:

```text
root ef507bb9b63f0184c0bf11a1d9d98c0ae8d819f8
ART  681f2f38a295602a1d04e21febb63b7e26e19103
```

The native toolchain was:

```text
CMake 3.31.8
Ninja 1.13.2
Clang/LLVM 21.1.8
Temurin JDK 21.0.12+8
Python 3.13.14
```

The configured target bundle contained 7,307 files in 149 directories,
totalling 695,394,928 bytes. Its tree SHA-256 was:

```text
e3537962cb3c8e6920da37795c66dab6092bb5fd1ed536be1899122673c1b3e8
```

The generated-build identities were:

```text
graph     82033ac261c507ec119098f587b073146fa641577376932fd767a53fa8151047
manifest  7862b4bfac76fec49eebafe17c73ee368e0a7e851fbb8076f45fd8de3b31ac33
profile   e8b03b9cf78f172f231fe498076fef88727eb96cb52ebc71687a3df29a3c3848
```

## Native build and gate

A fresh native `RelWithDebInfo` dependency closure built `dex2oat.exe`,
`boot.jar`, and `hello.jar`. The target-binding audit accepted 2,081 compile
commands, 2,126 Ninja commands, and 30 product links. An immediate repeat
build returned `ninja: no work to do.`

The authoritative command was:

```text
python.exe tools\build_art.py test \
  --target-id windows-x86_64-msvc \
  --build-type RelWithDebInfo \
  --output-root <native-output-root> \
  --parallel 2 \
  --stage w028
```

It passed twice from the coherent native build:

| Run | CTest | Runner manifest | Result |
|---:|---:|---:|---|
| 1 | 0.64 s | 0.501 s | 1/1 passed |
| 2 | 0.61 s | 0.483 s | 1/1 passed |

Both runs produced the same final artifacts:

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `probe.oat` | 66,888 | `fa03ad2f48f7a83bc8c6ddbf42620454f336d8c870e339771fc3edc88eb615f7` |
| `probe.vdex` | 1,000 | `cc1b8db5d41a00c51a380c27020e69e97cf987e0e0ee9b44a0b7995c703073c1` |

The accepted manifest reports:

```text
target                   windows-x86_64-msvc
instruction set          x86_64
image mode               none
compiler filter          speed
watchdog                 enabled
swap file                requested
logical boot JAR         /system/framework/boot.jar
logical input JAR        /data/local/tmp/win32-oat-probe.jar
logical OAT              probe.oat
ELF                      ELF64, little-endian, ET_DYN, x86-64
EI_OSABI/ABI/e_flags     3 / 0 / 0
PT_LOAD                  4, all aligned to 65,536, none W+X
OAT                      265
VDEX                     027, four sections, one embedded DEX
```

The relative logical OAT name is intentional. Passing `probe.oat` from the
managed output directory prevents ELF `DT_SONAME` from inheriting a
host-specific physical output path.

## Cross-environment diagnostic

A fresh post-correction Wine diagnostic generated artifacts with the same
sizes and SHA-256 identities as both native runs. That byte identity shows the
stable logical OAT name removed the previously observed physical-path input
from the ELF output. Wine remains diagnostic only; the two native Server 2025
runs are the authoritative acceptance.

## Disposition

W-028 and implementation-sequence step 1 are complete. Step 2 remains partial
until generation and startup identities for the selected boot-image/component
topology, including `-Ximage:`, are fixed and tested. Boot-set generation,
Windows private-copy `ElfOatFile` loading, VDEX/image ownership, unwind and CFG
transport, experimental fallback, and proof of real boot-OAT execution remain
pending.
