# FS-5 pending interpreter-bridge range disposition

**Date:** 2026-07-30
**Scope:** W-010/W-014 conditional pending-range coverage
**Host evidence:** Windows Server 2025 build 26100, plus the final-source Wine gate

## Result

FS-5 is **conditionally closed as impractical coverage**. The 88-byte
`art_quick_to_interpreter_pending_exception` range is structurally valid and
synthetically unwound, but no deterministic real native exception can enter it
without changing ART's product control flow or injecting a fault into the
probe-only assembly.

The existing structural/live probe remains green:

```text
win32_osr_unwind_probe failures=0 prologue=136 entry_frame_register=R12
compiled_frame_register=RBP entry_frame_offset=0 return_prologue=0 fixed_frame=248
xmm_count=10 invoke_records=2 generic_jni_records=1
generic_jni_native_return=0xc5 switch_impl_records=1 switch_impl_call_return=0xd
interpreter_bridge_records=2 interpreter_bridge_call_return=0x82
interpreter_bridge_pending=0x140 interpreter_bridge_frame=200
interpreter_bridge_pending_frame=88 variable_rsp_delta=256
win32_osr_unwind_probe OK
```

The same two-range structural record is retained in the native FS-2 package
(`tools/verify/windows_x64_phase4/evidence/fs2_w010_w014_native/`). The native
E6/E9 fatal matrix exercises `art_quick_to_interpreter_bridge + 0x82` and all
five static/JIT/OSR origins; those faults enter the primary range and then the
ART VEH/UEF path. No returned fatal/JNI trace has a pending-tail instruction
pointer.

## Why a real pending-tail fault is not a product test

On Windows x64 the bridge performs the following sequence after
`artQuickToInterpreterBridge` returns:

1. restore the 200-byte save-refs-and-args frame;
2. test `Thread::exception`;
3. return through the normal epilogue when it is null; or
4. jump to `.Lquick_to_interpreter_pending_exception` when it is non-null.

The pending range is therefore entered by an ART-managed pending-exception
state transition, not by a Windows native exception. Its 88-byte prologue only
saves callee-saved registers and XMM12-XMM15 before
`DELIVER_PENDING_EXCEPTION_FRAME_READY`, which transfers exception delivery to
the interpreter and is not a returning native call site. The native fatal cases
used for acceptance fault before this state transition and are already covered
by the primary bridge record and the complete fatal-origin matrix.

Forcing a native exception at a pending-tail instruction would require one of
the following non-acceptance interventions:

* patching or branching the product tail to execute an invalid access;
* changing the pending-frame helper to raise an exception; or
* jumping directly into the internal tail from a probe with fabricated ART
  registers and thread state.

The first two change product semantics. The last is a synthetic unwind test,
not evidence that a real ART pending transition is native-safe. The existing
`RtlVirtualUnwind` synthetic body/epilogue checks already cover that metadata
question, so no such probe is added.

The lab policy makes Windows Server 2025 build 26100 the sole authoritative
native gate; the former Windows 10 host is unavailable and a second-host
repeat is not an acceptance requirement. If a future product requirement needs
debugger quality for this non-returning tail, add a dedicated probe with an
explicit synthetic/non-product label and a separately reviewed fault-injection
contract.
