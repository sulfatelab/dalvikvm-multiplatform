# W-003 quick callee-save frame analysis

**Status:** ANALYSIS COMPLETE; W-003 remains open

**Date:** 2026-07-26

**Host:** agent01

## Outcome

W-003 is no longer an implementation task to remove known Windows `int3`
instructions from ART's runtime callee-save frame macros. That historical
source defect is already fixed. All four x86-64 frame families execute the
shared non-Apple frame body on Windows:

- `kSaveRefsOnly`;
- `kSaveRefsAndArgs`;
- `kSaveAllCalleeSaves`; and
- `kSaveEverything`, including its r14/r15-already-saved variants.

Only two macros ever trapped Windows: `SETUP_SAVE_REFS_ONLY_FRAME` and
`SETUP_SAVE_ALL_CALLEE_SAVES_FRAME`. The refs-and-args and save-everything
families were already shared with Linux. Commit `ace4da84b1` removed `_WIN32`
from the first two guards, changed top-quick-frame publication to
`THREAD_STORE_Q`, and retained Apple traps.

W-003 remains open for two reasons:

1. the ordinary Microsoft-x64 C++ boundaries into quick invoke and quick OSR
   do not preserve XMM6-XMM11 before crossing into ART managed code; and
2. existing broad tests do not attribute execution to every frame family or
   permanently reject a future Windows-only SETUP trap.

## Current frame contract

The selected design deliberately keeps the managed body Linux-like:

| Contract | Linux x86-64 | Windows x86-64 |
|----------|--------------|----------------|
| Managed method/argument registers | ART/SysV-shaped | same |
| Managed Thread base | GS | r15 |
| Runtime singleton load | GOT load | same-image PE RIP-relative load |
| C++ helpers called by quick assembly | native SysV | `ART_QUICK_ENTRYPOINT_ABI` (`sysv_abi`) |
| Runtime callee-save frame sizes/masks | canonical x86-64 | same |
| Top quick frame publication | GS store | `THREAD_STORE_Q` through r15 |

The canonical sizes are still 96 bytes for refs-only and all-callee-saves,
208 bytes for refs-and-args, and 272 bytes for save-everything. Assembly
compile-time checks continue to compare the concrete push/save layout against
those constants.

r15 has two related but distinct roles. Win64 optimizing code reserves it as
rSELF and does not allocate it as a general compiled callee-save. Runtime
callee-save frames still spill and restore r15 in the canonical shared slot so
ART stack visitors and long-jump contexts retain the upstream x86-64 layout.
The frame must publish `top_quick_frame` while the live r15 still contains the
current `Thread*`.

## Trap audit

Source inspection finds no `_WIN32` guard selecting an `int3` body for any
SETUP family. All SETUP-family trap branches are Apple-only.

The current matched Win64 and Linux quick-entrypoint objects both contain:

```text
functions containing int3: 212
int3 instructions:         401
```

The symbol-by-symbol distribution is identical. These remaining instructions
come from shared `UNIMPLEMENTED` entrypoints, `UNREACHABLE` tails after ART
long jumps, and read-barrier assertions. They are not Windows-only SETUP
stubs. The numeric counts depend on the configured entrypoint set and must not
be hard-coded as permanent acceptance constants. A durable check should build
matched configurations and compare the complete function/count multiset.

## Confirmed ABI conflict

Microsoft x64 requires a callee to preserve rbx, rbp, rdi, rsi, r12-r15 and
the lower 128 bits of XMM6-XMM15. ART's managed x86-64 convention instead
treats only XMM12-XMM15 as floating-point callee-saves; XMM6-XMM11 may be
clobbered by managed code.

Three current functions are ordinary Microsoft-ABI C++ entries that cross
into managed code:

- `art_quick_invoke_stub`;
- `art_quick_invoke_static_stub`; and
- `art_quick_osr_stub`.

Their Windows prologues correctly convert arguments, preserve rdi/rsi, save
the native caller's r15, and publish managed rSELF. They do not preserve
XMM6-XMM11. The invoke stubs directly load managed floating arguments into
XMM6 and XMM7 before saving any FP state, and the invoked/OSR-compiled method
may freely use XMM6-XMM11. Returning to a Microsoft-ABI C++ caller can
therefore corrupt live nonvolatile registers.

Existing Java/JNI checksums do not disprove this defect: a caller only exposes
it when the compiler keeps values live in those registers across the boundary.
The fix belongs at the explicit default-C++-to-managed adapters. It must not
change the shared SETUP layouts or switch assembly-called ART helpers to the
Microsoft ABI.

XMM12-XMM15 do not need an additional boundary save for this purpose because
the ART managed convention already preserves them. Saving XMM6-XMM11 is the
minimal Windows-only delta.

## Other conflicts and ownership

### Helper ABI and shadow space

Quick assembly calls ART C++ helpers through `ART_QUICK_ENTRYPOINT_ABI`, which
is `sysv_abi` on Win64. The existing shared frames are aligned for those calls
and intentionally do not provide Microsoft shadow space. Adding shadow space
to every SETUP macro would change frame sizes, spill offsets, stack visitors,
and long-jump contexts and would create unnecessary Windows divergence.

Microsoft shadow space is required only when an explicit adapter calls an
ordinary Microsoft-ABI function, as in the existing JNI/native and nterp
bridges.

### Runtime singleton load

W-004 removed the former C-ABI helper from `LOAD_RUNTIME_INSTANCE`. SETUP
macros now read `Runtime::instance_` with one same-image RIP-relative PE load.
It does not mutate the stack, consume shadow space, or clobber r11/r15. This
dependency is closed.

### OS unwind metadata

The Win64 quick-entrypoint object contains only `.text`, `.data`, and `.bss`.
Assembly CFI macros are disabled under `_WIN32`, and the object contributes no
`.pdata`/`.xdata`. ART managed exception delivery does not depend on Windows
SEH unwinding through these frames: it publishes runtime methods, uses ART
stack visitors, and restores long-jump contexts. Native debuggers, crash
walkers, or SEH unwinding through quick assembly nevertheless lack the PE
metadata available for compiler-generated C++ functions.

This must be an explicit policy decision. W-003 can close for managed-frame
correctness if W-010 clearly owns the VEH/SEH/native-unwind limitation. It
must not be described as full Windows unwind parity until PE unwind metadata
exists and is validated.

## Existing coverage

Current evidence is broad but not frame-attributed:

- W-001 established product-default quick invoke and historical quick-invoke
  to interpreter Wine smoke.
- Accepted W-002 native R2 covers quick/switch OSR, default nterp OSR, and
  native attached threads entering pre-JITed managed callbacks.
- Native ABI, CriticalNative, Math CriticalNative, and JVMTI suites exercise
  generic JNI, tracing, deoptimization, and managed/native transitions.
- JIT, GC, thread, allocation, monitor, and exception probes exercise many
  refs-only, save-everything, and all-callee-saves consumers indirectly.

The logs do not prove which SETUP family ran, do not deliberately cover every
throw/resolution/suspend/deopt shape, and do not seed Microsoft XMM
nonvolatiles around the native-to-managed boundary.

## Required implementation plan

### Stage A: boundary preservation

1. Add Windows-only save/restore helpers for XMM6-XMM11 using 16-byte slots.
2. In both quick-invoke stubs, save before `LOOP_OVER_SHORTY_LOADING_XMMS`
   can overwrite XMM6/XMM7 and restore after managed return but before the
   native `ret`.
3. In quick OSR, save before the managed jump and restore after the OSR return.
4. Keep Linux assembly byte-for-byte on its existing path.
5. Recompute Windows-only stack/CFA constants and preserve 16-byte call
   alignment. Do not change canonical runtime frame sizes or spill masks.

### Stage B: permanent structural gate

Add a W-003 checker that verifies:

- every SETUP trap guard is Apple-only;
- top-quick-frame stores use `THREAD_STORE_Q`;
- matched PE/ELF objects have identical `int3` function/count multisets;
- invoke and OSR PE prologues save XMM6-XMM11 before managed clobber points
  and restore them on every normal return;
- expected r15 publication and Runtime singleton relocations remain; and
- Linux invoke, OSR, and SETUP instruction paths are unchanged.

### Stage C: focused runtime probes

Create a managed probe with separate, named subtests for:

- refs-only: allocation slow paths and contended monitor lock/unlock;
- refs-and-args: quick-to-interpreter, resolution/proxy, and generic JNI;
- all-callee-saves: caught class-cast, array-store, null, and bounds throws;
- save-everything: suspend checks, deoptimization, and instrumentation hooks.

Run it under `-Xint`, product-default nterp, forced switch interpreter, and
threshold-zero JIT. Use deterministic outputs and require zero pending
exception at process end.

Add a native register-sentinel probe that places distinct values in
XMM6-XMM11, invokes Java through JNI/quick invoke, and verifies every lane on
return. Add a focused OSR boundary test or structural plus compiler-assisted
sentinel test so OSR preservation is not inferred only from checksums.

### Stage D: acceptance

Run:

- clean Win64 and Linux builds with `-j32`;
- the structural gate;
- focused Wine mode matrices;
- existing Phase 3 and Phase 4 regression aggregates;
- Linux shared-boot Hello, GC, and OSR controls; and
- a Windows 10 version 1803-or-later native package with repeated mode pairs,
  fatal-marker scan, and recursive dump scan.

Close W-003 only after all four frame families have attributed coverage and
the Microsoft XMM nonvolatile sentinel passes.

## Rejected directions

- Do not make all quick C++ helpers Microsoft ABI; that would duplicate most
  x86-64 quick assembly and increase Linux/Windows divergence.
- Do not add Microsoft shadow space to canonical SETUP frames.
- Do not create Windows-specific runtime frame sizes or spill masks merely to
  preserve native-boundary XMM registers.
- Do not treat the equal current `int3` totals as a fixed magic number.
- Do not close W-003 solely from broad application smoke without a register
  sentinel and frame-family attribution.
