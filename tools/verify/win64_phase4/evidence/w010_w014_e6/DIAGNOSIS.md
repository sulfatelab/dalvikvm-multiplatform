# W-010/W-014 E6 native diagnosis

**Host:** Windows Server 2025 Datacenter Evaluation, build 26100, x86_64  
**Run date:** 2026-07-28  
**Package SHA-256:** `9ab66c9a7b2e8e40210f9c47971cbf5ac9f86c0ca729c25a05448f12346499bc`  
**Result bundle SHA-256:** `a1c6af0ceff198f6b4543aa832dbf40ced81dcf72800b77c55dd5f2959302736`  
**Root revision:** `6cce29d7b5f1647b90c56ad02de747fdebcdca99`  
**ART revision:** `bbb397f2deff19b80588716ee53b0eaf1ab9db88`

The uploaded archive matched its Linux SHA-256, the Python package checker
passed on Windows, and the complete diagnostic runner reported
`DIAGNOSTICS COMPLETE`:

```text
JNI hardware: late UEF=1, ART UEF=1, dumps=1, trace frames=23
JNI raised:   late UEF=1, ART UEF=1, dumps=1, trace frames=24
Native worker: late UEF=1, ART UEF=1, dumps=1, trace frames=4
```

The repaired primary interpreter-bridge range is live in both JNI traces. The
native E5 miss now resolves:

```text
art.dll rva=0x9d3652
art_quick_to_interpreter_bridge + 0x82
lookup=1
begin=0x009d35d0 end=0x009d3710 unwind=0x0100df80
```

It appears at hardware frame 11 and raised frame 12. Both walks then cross the
static invoke record and all remaining ART, executable, and OS frames with
`lookup=1`. The hardware walk ends after 23 frames and the raised walk after
24, both with `reason=zero_pc`. Windows subsequently enters the late filter,
chains to ART's UEF, and writes a minidump. There is no later missing runtime-
function record in either exercised chain.

The three dumps are valid 14-stream `MDMP` files:

```text
748487  8cb6b7d8eb382e6ec86272ecb283936b35b44ed350825db85c4b462c37c44a1e
744355  4d164e01bb6a34596cf2d1c1df77420cc3bb592010ae5d9a3f38b1ec4a78d727
748587  f9caf7f54ae3cf578bce852c17f479d80eb19b5eb945faf8b176b9417cb0b7cc
```

This closes the diagnosed fatal-dispatch lookup chain and natively accepts the
primary interpreter-bridge record. The separate 88-byte pending range remains
structurally and synthetically verified but was not entered by these fatal JNI
cases. W-010/W-014 are not complete: run the full native host matrix to verify
static/JIT/OSR fatal origins, while the Windows managed-SOE redesign remains
independent open work.
