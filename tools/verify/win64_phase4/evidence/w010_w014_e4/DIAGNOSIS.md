# W-010/W-014 E4 native diagnosis

**Host:** Windows Server 2025 Datacenter Evaluation, build 26100, x86_64  
**Run date:** 2026-07-28  
**Package SHA-256:** `391547a4fe0f76193af2f3767123b9c054ec0461d7cd589ed405cdc9f6ace1b5`  
**Result bundle SHA-256:** `4616e8622dba2977b5472264f099de9449aa5c8b0a4bc1d1d568f9af8c6987b8`  
**Root revision:** `22cad3ad23cb94be76a46e7b8fd67748d6162994`  
**ART revision:** `69999bce0bd494c616bf8344baeddc7f69f7c702`

The complete diagnostic runner reports `DIAGNOSTICS COMPLETE`. Stack-growth
and standalone UEF results repeat native runs 3-4 on current Windows.

JNI hardware AV and JNI `RaiseException` both reach the repaired GenericJNI
and static-invoke records, ordinary ART C++ frames, and
`ExecuteSwitchImplCpp`. The next recovered PC is `art.dll` RVA `0x009b6089`,
`ExecuteSwitchImplAsm + 0x9`, where `RtlLookupFunctionEntry()` returns null.
That instruction is the post-call `pop %rbx` in the issued binary. Because the
wrapper pushed RBX but has no PE runtime-function record, leaf fallback reads
the saved RBX stack value as its next PC and leaves the real return address
behind. Neither late nor ART UEF is subsequently dispatched.

The JNI-created native worker has no ART frames on its crashing thread. All
four frames have runtime-function entries, unwind reaches zero PC, both UEFs
run, and ART writes one valid 747,491-byte minidump:

```text
sha256=8d854b1e25d561dd8515e6ceb17c9e58574c9e766e3a0e6a1a82091fb7815bf6
```

This native run confirms the local Wine candidate. The product repair belongs
in the Win64 `ExecuteSwitchImplAsm` wrapper: add PE unwind metadata for its RBX
save and stack allocation, and reserve the mandatory 32-byte MSVC outgoing
home area for the call to `ExecuteSwitchImplCpp`. Keep the Linux/SysV body
unchanged. Structural lookup plus body/epilogue `RtlVirtualUnwind()` tests must
land with the repair before fatal dispatch is repeated.
