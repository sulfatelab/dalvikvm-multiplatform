# W-004 direct Runtime singleton load

**Status:** PASS; W-004 CLOSED

**Date:** 2026-07-25

**Host:** agent01

## Outcome

Windows x64 `LOAD_RUNTIME_INSTANCE` now matches the upstream ART model more closely:
it reads `Runtime::instance_` directly instead of crossing the Microsoft x64 C
ABI through a Windows-only helper.

```asm
movq "?instance_@Runtime@art@@0PEAV12@EA"(%rip), REG_VAR(reg)
```

The Linux x86-64 macro remains byte-for-byte unchanged:

```asm
movq _ZN3art7Runtime9instance_E@GOTPCREL(%rip), REG_VAR(reg)
movq (REG_VAR(reg)), REG_VAR(reg)
```

The Windows expansion is one 7-byte same-image RIP-relative load. It does not
call through an ABI, touch `rsp`, change flags, or require a scratch register.
The old `art_Runtime_instance_ptr()` helper, helper-only
`Runtime::InstanceLocation()`, CriticalNative `r11` reload, and immediate
generic-JNI `xmm0` repair were removed. The later `xmm0` repair after a real
instrumentation hook remains.

This sequence applies only to assembly linked into `art.dll`. It must not be
copied into low-address dynamic JIT code, whose address may be outside signed
32-bit reach of `art.dll`; that contract remains under W-025.

## Structural gate

`tools/verify/windows_x64_phase1/check_w004_runtime_load.py` checks the source,
objects, final PE artifacts, and Ninja dependency graph. The current result is:

```text
W-004 runtime load structural check: PASS (quick=563 jni=1 nterp=10 total=574)
```

The gate verifies:

- the exact direct Windows macro and unchanged Linux macro;
- no retired helper or helper-only accessor remains in ART source;
- quick, JNI, and generated nterp objects use direct
  `IMAGE_REL_AMD64_REL32` relocations to `Runtime::instance_`;
- every relocation is attached to a RIP-relative `movq`;
- `art.dll` exports exactly one existing `Runtime::instance_` data symbol;
- `openjdkjvmti.dll` imports that symbol exactly once through the IAT;
- no object or checked DLL references or exports the retired helper;
- all five x86-64 assembly objects explicitly depend on the shared macro
  source; and
- a missing required artifact causes the check to fail.

The relocation count is recorded evidence, not a fixed acceptance constant.
Each required object must have at least one direct reference and no helper
reference.

## Incremental-build correction

The first full link after changing the shared macro found ten stale helper
relocations in generated nterp assembly. CMake's clang ASM rule declared a
depfile but did not pass flags that produced one, so changing
`asm_support_x86_64.S` did not reliably rebuild all consumers.

The unified `native/CMakeLists.txt` gives these five objects explicit
dependencies on the shared x86-64 assembly support sources:

- `memcmp16_x86_64.S`;
- `native_entrypoints_x86_64.S`;
- `jni_entrypoints_x86_64.S`;
- `quick_entrypoints_x86_64.S`; and
- generated `mterp_x86_64.S`.

Clean and incremental builds now produce the same direct-load objects.

## Build verification

Both focused and complete Windows x64 builds passed with parallelism 32:

```bash
cmake --build build/windows_x64_phase1 --target art -j32
cmake --build build/windows_x64_phase1 -j32
```

## Runtime verification

The rebuilt artifacts passed the following local acceptance on Wine:

| Gate | Result |
|------|--------|
| W-004 structural/source/dependency check | PASS, 574 direct / 0 helper |
| JIT smoke | PASS, 12/12 |
| Phase 3 aggregate | PASS all gates |
| JIT matrix | PASS, 14/14 |
| CriticalNative, corrected dual view | PASS, 6/6 float/signature + 3/3 tracing |
| CriticalNative, J-1 diagnostic | PASS, 6/6 float/signature + 3/3 tracing |
| Normal/FastNative ABI | PASS, 7/7 default + 7/7 tracing |
| JVMTI forced interpreter, corrected dual view | PASS, 3/3 |
| JVMTI forced interpreter, J-1 diagnostic | PASS, 3/3 |
| Phase 4 aggregate | PASS all gates |

The Phase 4 aggregate includes W-004 structural inspection, W-024 cleanup,
GC stress, thread-heavy, handle-leak, performance, controlled-crash, and Phase
3 golden-regression gates.

Linux controls also passed:

- imageless Hello using the shared boot class path; and
- GC stress.

## Native Windows closure

Native Windows acceptance passed on Windows 10 Enterprise LTSC x64 build
19044. W-004 is closed.

The focused native package is implemented by
`tools/windows_x64/host_package/package_windows_x64_w004.sh`. Its source and artifact
contract are checked by `check_w004_host_package.py`, and the staged package is
exercised under Wine by `smoke_w004_host_package_wine.py` before the final
manifest and archive are written.

The package contains the shipped product artifacts, focused
quick/nterp/JIT/native-ABI/GC/thread probes, and a structural report generated
on Linux. LLVM inspection tools are not required on the Windows host. The
embedded PowerShell runner requires Windows 10 RS4 build 17134 or later,
verifies all packaged SHA-256 values and report/artifact hash agreement, then
runs the complete host matrix and recursive dump scan. See
[`W004_HOST_CHECKLIST.md`](W004_HOST_CHECKLIST.md).

Local package verification passes:

- package checker before and after Wine execution;
- ZIP integrity check;
- nterp `-Xint`, dual-view JIT, and threshold-zero FloatProbe;
- CriticalNative, normal/FastNative, and JVMTI forced-interpreter probes;
- GC stress and thread-heavy probes; and
- three independent default-JIT package starts.

The returned archive passes integrity testing and its `BUILD_INFO.txt`,
`MANIFEST.json`, `SHA256SUMS.txt`, and structural report match the issued
package byte for byte. The host result contains 28 PASS records, zero failures,
and `OVERALL PASS` across 22 child processes. Every child exits zero without a
timeout, launch error, missing marker, or forbidden marker.

The native matrix covers nterp `-Xint`, corrected dual-view JIT,
threshold-zero FloatProbe, dual/J-1 CriticalNative, normal/FastNative, and
JVMTI transitions, GC/thread/handle stress, and ten repeated default-JIT
starts. Independent review confirmed exact ABI values and compilation counts.
Fatal/access-violation and trace-cleanup scans pass; the recursive dump scan
reports `NO_DMP_FILES`.

Full accepted evidence:
[`evidence/w004_host/ACCEPTANCE.md`](evidence/w004_host/ACCEPTANCE.md).
