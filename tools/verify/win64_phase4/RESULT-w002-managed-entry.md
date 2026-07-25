# W-002 managed-entry repair

**Status:** IMPLEMENTATION PASS; WINE AND LINUX PASS; NATIVE WINDOWS
ACCEPTANCE PENDING

**Date:** 2026-07-25

**Host:** agent01

## Outcome

The Win64 rSELF design remains `r15`; Windows GS remains the TEB and
`InitCpu` correctly does not replace it. The residual failures were local ABI
and frame-layout defects in switch and nterp OSR transitions, not a reason to
change the managed Thread model.

The repaired paths now preserve the normal ART/Linux structure:

- platform C++ calls keep their platform ABI;
- Windows-only conversion stays at the assembly boundary;
- managed code observes rSELF in r15;
- Linux assembly remains on its original instruction path; and
- native attached threads publish rSELF only when they cross the existing
  quick-invoke boundary.

W-002 remains open only for the issued native Windows 10 acceptance run.

## Quick/switch OSR root cause and fix

`jit.cc` declares and calls `art_quick_osr_stub` as an ordinary C++
function. On Windows this supplies:

- rcx: copied stack;
- rdx: copied-stack size;
- r8: compiled native PC;
- r9: result pointer;
- stack argument 5: shorty; and
- stack argument 6: `Thread*`.

The assembly body previously consumed the SysV register layout directly and
never published the explicit `Thread*` into r15.

The Windows prologue now:

1. saves rdi and rsi, which are Microsoft nonvolatile;
2. reads the two stack arguments after accounting for those saves;
3. converts the six arguments into the shared SysV-shaped body;
4. saves the native caller's r15 in the common callee-save block;
5. publishes `Thread*` into r15 before the OSR jump; and
6. restores r15/rsi/rdi before returning through the native C++ caller.

The Win64 CFA is 96 bytes. Linux retains the original 80-byte CFA and does not
execute the Windows conversion.

## Nterp OSR root causes and fix

The first nterp defect was an assembly call to `free` with its pointer in rdi
and without Microsoft x64 shadow space. Windows now calls `NterpFree`, the
existing assembly-facing SysV-to-Microsoft bridge.

Using only that bridge removed the UCRT ABI violation but exposed a second
failure. Compiled OSR returned with an invalid restoration stack because the
Linux transition treats nterp's save block as the compiled OSR callee-save
frame. That assumption is valid when the layouts match. It is invalid on
Windows because:

- nterp saves r15 as part of its native/nonvolatile state;
- managed r15 is pinned as rSELF; and
- the Win64 optimizing compiler excludes r15 from its compiled spill set.

The Windows nterp transition now keeps the original nterp save block as a
return adapter and copies the full compiled OSR frame below it. Compiled code
returns to the adapter, which removes alignment padding, restores
XMM12–XMM15 and rbx/rbp/r12–r15, and returns to the original managed caller.
The compiled result stays in rax/xmm0.

Linux retains its original direct frame reuse and libc `free`.

## Attached-thread contract

`AttachCurrentThread` and `AttachCurrentThreadAsDaemon` establish
`Thread::Current()` in ART's C++ TLS. They must not reserve or overwrite a
native caller's r15. JNI `CallStaticLongMethod` enters through
`ArtMethod::Invoke`, whose Win64 quick boundary preserves native r15 and
publishes the attached `Thread*` for managed code.

Each attach process:

- warms and JIT-compiles `W002AttachProbe.attachedCallback`;
- creates eight regular and eight daemon Win32 threads;
- attaches each thread through the matching JNI API;
- enters the pre-JITed Java callback;
- verifies `Thread.currentThread()` and daemon state;
- allocates Java objects;
- validates an exact 64-bit return value;
- detaches; and
- requires `GetEnv == JNI_EDETACHED`.

## Permanent gates

| Gate | Purpose |
|------|---------|
| `check_w002_managed_entries.py` | Source, Win64 object, relocation, r15 compiler, CFA, `NterpFree`, and Linux-path invariants |
| `run_w002_osr_probe.sh` | Baseline compile, OSR compile, jump, exact checksum, switch/nterp return-path distinction |
| `run_w002_attach_probe.sh` | Regular/daemon native attach into a pre-JITed Java callback |
| `run_all_wine_gates.sh` | Runs all three W-002 gates before the broader Phase 4 suite |

The structural gate requires:

- the normal platform ABI on the C++ declaration;
- ordered Microsoft-to-SysV conversion and r15 publication in source and PE
  object code;
- preservation of Win64 rdi/rsi and the Linux 80-byte CFA;
- the Windows 96-byte CFA;
- exactly one nterp relocation to `NterpFree` and no raw `free` relocation;
- the Windows nterp return-adapter sequence;
- Win64 compiler Thread accesses through r15; and
- r15 excluded from the Win64 compiled callee-save set.

## Focused Wine results

### OSR

| JIT memory | Interpreter | Result |
|------------|-------------|--------|
| Corrected dual view | Default nterp | 2/2 |
| Corrected dual view | Switch | 2/2 |
| J-1 diagnostic | Default nterp | 2/2 |
| J-1 diagnostic | Switch | 2/2 |

All eight processes report:

- baseline compilation;
- OSR compilation;
- `Jumping to long W002OsrProbe.osrLoop(int)`;
- `W002OsrProbe OK checksum=9835131152`; and
- `main end exception=0`.

Switch runs additionally report the switch OSR completion marker. Nterp runs
must not use that return path.

### Attached threads

| JIT memory | Interpreter | Result |
|------------|-------------|--------|
| Corrected dual view | Default nterp | 2/2 |
| Corrected dual view | Switch | 2/2 |
| J-1 diagnostic | Default nterp | 2/2 |
| J-1 diagnostic | Switch | 2/2 |

All eight processes compile the callback, report
`W002AttachProbe OK completed=16`, and finish with no exception. This is 128
successful native-thread attach/callback/detach lifecycles across the focused
matrix: 64 regular and 64 daemon.

## Broader regression results

| Control | Result |
|---------|--------|
| Complete Win64 build, `-j32` | PASS |
| Full Phase 3 Wine aggregate | PASS all gates |
| Full Phase 4 Wine aggregate | PASS all gates |
| JIT smoke | 12/12 |
| JIT matrix | 14/14 |
| Normal/FastNative default and tracing | 7/7 + 7/7 |
| CriticalNative dual and J-1 | 4/4 signature + 2/2 instrumentation per mode |
| JVMTI forced interpreter dual and J-1 | 2/2 per mode |
| Complete Linux build, `-j32` | PASS |
| Linux shared-boot imageless Hello | PASS |
| Linux GC stress | PASS |
| Linux nterp baseline-to-OSR transition | PASS with exact checksum |

The clean Linux rebuild exposed an unrelated compatibility-header issue:
`compat/include/sys/sendfile.h` was overriding glibc's `sendfile64`
prototype. The header is now Windows-only and uses the system header on Linux.
Both Linux and Windows hybrid libcore builds pass after that correction.

## Native Windows package

Generate the issued package with:

```bash
JOBS=32 WINEDEBUG=-all \
  bash tools/win64/host_package/package_win64_w002.sh
```

Package generation:

- rebuilds ART;
- reruns the structural and 16-process focused Wine matrix;
- stages product PE artifacts and both W-002 jars/DLL;
- embeds an artifact-bound structural report;
- validates the manifest and required PE exports;
- runs all eight mode pairs once from the staged package under Wine;
- cleans runtime outputs;
- regenerates and rechecks the final manifest; and
- creates `dist/win64_w002_host.zip`.

The staged package smoke passes 8/8 processes, and ZIP integrity passes.
The native runner repeats every pair twice, enforces Windows build 17134 or
later, validates package hashes and structural-report artifact identities,
scans fatal markers, and recursively rejects any `*.dmp`.

See [W002_HOST_CHECKLIST.md](W002_HOST_CHECKLIST.md). Accept returned evidence
with:

```bash
python3 tools/verify/win64_phase4/review_w002_host_result.py \
  /path/to/returned.zip --issued dist/win64_w002_host
```

The expected native result has 21 PASS records over 16 child processes and
ends in `OVERALL PASS`. Until that evidence returns, W-002 remains open.
