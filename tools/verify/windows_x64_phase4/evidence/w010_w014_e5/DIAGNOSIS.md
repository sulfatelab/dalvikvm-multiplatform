# W-010/W-014 E5 native diagnosis

**Host:** Windows Server 2025 Datacenter Evaluation, build 26100, x86_64  
**Run date:** 2026-07-28  
**Package SHA-256:** `231322dd1261bb7a592929005cef85079110466462cadfef8fc996fbfaae2a05`  
**Result bundle SHA-256:** `1a58bb0f318eae82882ea1bd0e5b0fa403202d02ae95a889b07a1e7b3524b3d9`  
**Root revision:** `177993020896f18c19ab6ac0f863104c640db6d2`  
**ART revision:** `b57890bd710687631f56387ab8073c11ce33bdc0`

The exact E5 package and its Python package checker passed on native Windows.
The complete diagnostic runner reports `DIAGNOSTICS COMPLETE`:

```text
JNI hardware: late UEF=0, ART UEF=0, dumps=0, trace frames=14
JNI raised:   late UEF=0, ART UEF=0, dumps=0, trace frames=15
Native worker: late UEF=1, ART UEF=1, dumps=1, trace frames=4
```

The repaired `ExecuteSwitchImplAsm` now has a runtime-function record in both
JNI traces. The live native lookup at its post-call PC succeeds:

```text
art.dll rva=0x9b608d
ExecuteSwitchImplAsm + 0xd
lookup=1
begin=0x009b6080 end=0x009b6093
```

This closes the E4 defect: the Windows-only RBX save, 32-byte MSVC outgoing
home area, canonical epilogue, and PE unwind description work on Windows, not
only in the structural and Wine probes.

Both JNI traces then traverse four more registered ART C++ frames. The first
new lookup miss is the return PC after `call artQuickToInterpreterBridge`:

```text
art.dll rva=0x9d3652
art_quick_to_interpreter_bridge + 0x82
lookup=0
```

It occurs at trace frame 11 for the hardware AV and frame 12 for the raised
AV. Leaf fallback then consumes ART frame data as return addresses, so neither
late nor ART UEF runs. The bridge has two distinct stack shapes: its primary
200-byte save-refs-and-args frame and a pending-exception tail entered after
that frame has been removed. Any repair must describe each live range with its
actual frame; one blanket unwind record is not correct.

The native worker again traverses four registered native/OS frames, reaches
zero PC, enters both UEFs, and creates one valid 747,073-byte minidump:

```text
sha256=99bff7ef07986eb4c2c15506056664f1a7d39db6fc6f685482e93fadbacc19f5
```

Current Windows also repeats the fixed-page stack-growth result. E5 therefore
closes the switch-wrapper repair but does not close fatal dispatch or W-014:
repair and probe the two interpreter-bridge ranges next, while the replacement
managed-SOE design remains independent work.
