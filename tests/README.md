# ART test contributor guide

This directory owns maintained ART product tests. It keeps each logical test's
source, target applicability, runner, reviewer, accepted result, and small
diagnostic evidence together while all generated files remain under `out/`.

The test system is part of the unified build. It uses the same target profile,
plain Clang GNU-style driver, CMake, Ninja, SDK/sysroot, libc++, and generated
product graph as ART. A test must not create a second product build graph or
fall back to Make, NMake, MSBuild, GCC, MinGW, `cl.exe`, `clang-cl`, Bash,
PowerShell, WSL, Cygwin, or another POSIX environment on a Windows host.

The authoritative build-system design and migration tracker is
[`../unified_art_build.md`](../unified_art_build.md).

## Principles

1. Organize files by logical test, not by historical phase, host, or current
   target architecture.
2. Declare applicability per test. A virtual stage groups tests but does not
   make every member support the same platform or architecture.
3. Reuse one physical source file when its contract is shared. Do not copy it
   into architecture directories and do not use filesystem links.
4. Treat `applicable`, `build-verified`, and `runtime-verified` as separate
   states.
5. Keep accepted `RESULT.md` records near the source they describe.
6. Write every generated source, object, executable, DSO, package, log, and
   machine result below `out/<target-id>/<build-type>/`.
7. Never commit generated or returned binaries or archives. The pinned
   `vendor/r8/r8.jar` D8/R8 tool is the sole exact-path exception.
8. Do not record workstation absolute paths, secrets, full environment dumps,
   or build-host-specific output paths in tracked files.

## Target directory structure

```text
tests/
  README.md                    this guide
  CMakeLists.txt               transitional common target declaration API
  catalog.py                   final target-neutral test declarations

  cases/
    <logical-test-id>/
      <native and/or Java source>
      run.py                   optional target runner
      review.py                optional returned-result reviewer
      RESULT.md                maintained multi-target acceptance record
      evidence/
        <target-id>/
          manifest.json        optional small accepted text metadata
          <selected text log>  only when diagnostically valuable

  support/
    <shared Python helpers>

  stages/
    <wNNN>/
      RESULT.md                optional stage-wide roll-up only

  host/
    <repository/infrastructure tests that are not owned by one case>
```

`cases/` is the final home for active behavioral tests. A case may contain C,
C++, assembly, Java, and Python together when they implement one acceptance
contract. Avoid splitting one JNI test between unrelated language-first trees.

`support/` is for reusable test framework code. A helper used by only one case
stays in that case. A user-facing build, provisioning, or audit command belongs
under `tools/`, not `tests/support/`.

Target-specific shared artifact reviewers may use one additional directory,
such as `support/windows/`, when they validate a platform ABI across several
logical cases. They must consume the unified output directory and must not own
or configure a second product graph.

`stages/` contains no product source. Its optional `RESULT.md` summarizes a
cross-test milestone when a per-case result cannot express the complete stage
conclusion. Stage membership itself remains catalog metadata.

### Current migration state

The first complete case-first migration slice moved the common registry to
`tests/CMakeLists.txt` and established these canonical cases:

```text
tests/cases/jni-critical-native/
tests/cases/jni-native-abi/
tests/cases/w003-frame-probe/
tests/cases/w003-xmm-sentinel/
tests/stages/w003/ANALYSIS.md
```

Each case owns its native and managed source plus an adjacent `RESULT.md`. The
stage analysis links the case-specific results without physically grouping the
source by stage. The XMM sentinel remains explicitly x86-64-only; moving it did
not broaden its selector to AArch64 or ARM64EC.
The source-ownership slices moved all 32 catalog-owned native probe declarations
into logical cases. The registry now has zero
source references into `tools/verify`; every case containing catalog native
source has an adjacent target-status result. Shared stack-fault assembly has
one physical owner under `stack-page-growth/` and is consumed by related
targets without copying or filesystem links.
Two Linux x86-64 command gates in `w004` now exercise `dalvikvm -showversion`
and the runtime/compiler ELF load topology through
`support/runtime_gate.py`. A command gate owns no dummy target binary; its
virtual target depends on the exact product artifacts that must exist before
CTest runs it.
The managed-source slice moved all 48 retained Java probe sources into logical
cases. The catalog now declares 47 managed JAR artifacts (the paired
CriticalNative sources intentionally share one JAR), built by
`support/managed_artifact.py` through CMake/Ninja. The same helper builds the
target-local boot JAR first, so Android/libcore APIs and ART annotations are
resolved from the same AOSP boot classes on Linux and Windows build hosts.
Three W-004 managed declarations are `target-runnable` on the exact current
Linux and Windows x86-64 identities. `support/runtime_gate.py` runs imageless
Hello and allocation/collection stress; the case-local `math-critical/run.py`
runs Math CriticalNative in `-Xint` and threshold-zero JIT twice each. All
three use a declared native DSO closure, isolated target-local runtime
directories, pinned ICU data, strict exit/marker checks, timeouts, and
sanitized JSON results. The Math aggregate additionally rejects filesystem
links/reparse points, and Windows JIT requires a matching compiler record.
Linux also registers its show-version and compiler-DSO topology gates, for five W-004
CTest gates. Windows adds its BoringSSL SHA executable plus the exact
`windows-x86_64-msvc` JVMTI managed gate and runtime-load/assembly-dependency
reviewer. Fifteen more accepted Phase-3 libcore behaviors use one checked-in
JSON contract matrix and one case-local, shell-free Python runner. The expanded
native W-004 stage has 26 gates: core/charset/monitor, DNS, ordinary and forced
GC, GoldenApp, interruption, file I/O, TCP loopback, errno/UTF-8 paths,
properties/clocks, runtime memory, thread stress, and expected-nonzero uncaught
exception behavior join the earlier six. Exec validates `Runtime.exec` and
`ProcessBuilder`; IPv6 validates AF_INET6 bind and `getsockname`. PathProbe and
AbsPathProbe add a
standalone Hello regression, multi-JAR `;` classpath, structured
drive/mixed/UNC checks, three absolute path forms, and two required `:`
negative cases. The retained Phase-4 HandleLeak, PerfSmoke, and ThreadHeavy
cases now run through the same shell-free gate in interpreter mode with exact
marker contracts. Windows Server 2025 passed 26/26
twice with `--parallel 16`, including a true Ninja no-op repeat. Its first DNS
run exposed recursive `getnameinfo` JNI behavior; the maintained bridge now
uses `GetNameInfoW` with explicit bionic-to-Winsock flag mapping. The remaining
L-003 Locale and Zip probes timed out after 120 seconds natively, and UDP failed
at `DatagramSocket` construction with `setsockopt EINVAL`; all three stay
compile-only until their exact native contracts pass. Historical Wine results
do not promote them. The JVMTI runner, native agent, managed
source, and result live together under `cases/jvmti-force/`; its current
selector is deliberately not generalized to another Windows architecture or
ABI.
The W-013 non-moving-heap artifact and 128 MiB runtime gate use the same exact
Linux and Windows x86-64 identities. Its heavier 1024 MiB gate is separately
Windows-specific. This is intentional per-test applicability: sharing one Java
source and Python runner does not imply that every resource profile or future
architecture is supported.
W-010's four native EXEs and three managed declarations are now all
`target-runnable` for `windows-x86_64-msvc`. Case-local Python runners own the
four-mode UEF contract, two debugger modes, managed abort, three fatal
static/JIT/OSR origins with exact minidump validation, and six managed-fault
recovery modes. Direct native fault-record and sigchain probes remain separate
CTest processes. A host reviewer resolves six private transition stubs from
`art.pdb` and audits their linked unwind records without exporting them.
Windows Server 2025 passed the eight-gate stage twice with a Ninja no-op
repeat; the Linux-hosted cross stage built the same artifacts, passed the
reviewer, and also repeated as a no-op. The debugger launches the
frontend-resolved product EXE rather than copying it away from its matching DLL
directory, while all writable runtime state remains isolated below the output
tree.
W-025 keeps its three JNI DSOs as compile-only dependencies and makes eight
behavioral declarations target-runnable. The managed runners cover unwind
lifecycle, stress, and 64 MiB/1 GiB mapping audits; the native runners cover
unwind encoding/registry, section policy, CFG execution, and fail-closed
dynamic-code policy. A unified twelve-process gate covers default/disabled/
filtered/excluded/quiet JIT controls plus Math, IO, Net, GC, and throw
workloads. One shared reviewer audits source, CFG/import/export PE policy,
XMM0 floating-point returns, and absence of the retired J-1 path. Windows
Server 2025 passed the nine-gate stage twice, and the Linux-hosted
Windows cross stage passed its reviewer; both stage builds repeated as Ninja
no-ops. Test assets are copied as regular files into output-owned work roots,
while the original absolute `dalvikvm.exe` is launched to preserve its product
DLL lookup order. No machine path is serialized in result JSON.
W-027 is a typed Windows x86-64/MSVC `host-review` gate over the active
translation-unit graph. Its scanner reads `compile_commands.json`, de-duplicates
sources, strips comments and literals, distinguishes JNI `Call*MethodA` from
Win32 suffix-`A` APIs, and fails on either a known ANSI call or an unclassified
suffix-`A` family. The active 1,441-source graph has zero ANSI calls, source
files, or API families. The Linux-hosted Windows-cross stage passes. Native
Windows Server 2025 now passes W-027 as part of the complete 66/66 catalog;
the first run completed in 12.38 seconds and the no-op repeat in 12.33 seconds.
The complete catalog contains 59 target-runnable gates and seven host reviewers,
and its repeated `art-tests` build reports `ninja: no work to do`.
Remaining legacy shell runners and retained per-probe CMake entry points use
canonical files as temporary compatibility shims; they must be replaced by the
unified Python/CMake/Ninja path before `tools/verify` can be removed. W-003 has
removed its four standalone CMake graphs, shell runners, and package producer;
W-004 has likewise removed the standalone JVMTI CMake/Bash orchestration after
unified native acceptance. Its accepted Phase-3 libcore slices removed all 26
superseded Bash build/run wrappers; native-open cases remain compile-only in
the same catalog instead of retaining an alternative product or runtime graph.
The remaining Phase-3 libcore/ICU CMake graph, checked source snapshot, shell
host packager/stager, raw-link combined-stub builder, and minimal
`NativeConverter` stub were then removed after the unified product built the
same DLL closure and native W-004 passed. The stable bring-up result is history
beside the canonical `cases/windows-libcore-smoke/` sources, not a second
reproduction path. Its durable G12 result, corrected acceptance analysis, and
preceding false-pass diagnosis are under the exact
`evidence/windows-x86_64-msvc/` identity. Raw Wine transcripts, duplicate host
results, and package-integrity logs were removed because they contained machine
paths or repeated the retained contract. The maintained Phase-3 reproduction
is the unified W-004 stage only.
The accepted Phase-4 managed stress slice also removed its generic builder,
generic Wine runner, aggregate Wine runner, and four per-case wrappers. W-010's
redundant Phase-4 managed-abort Wine wrapper is also retired; the native-crash
wrapper followed after its additional PE unwind audit migrated into W-010.
The final Phase-4 shell wrapper, for Math CriticalNative, was retired after its
two-mode matrix moved beside the case and passed twice on native Windows plus
the fresh Linux W-004 build. The W-024 source cleanup is now enforced by the
live W-004 reviewer on native and cross hosts.
The composite W-004 host package producer and repository-side PowerShell
runner were then retired: W-003 owns its native-ABI matrices, W-004 owns its
runtime/JVMTI/stress contracts, and W-025 owns its supported JIT controls and
workloads. Its source-less FloatProbe JAR remains historical evidence rather
than a reason to keep an alternative package build.
W-025 has removed its four package producers,
package-only PowerShell/Bash/Wine orchestration, and superseded Phase-4 JIT
wrappers after unified native acceptance. Its four durable JIT-2 through JIT-5
acceptance summaries now live under `docs/history`; obsolete package checklists,
checkers/reviewers, and per-process log bundles were removed. Retained aggregate
package flows acquire required DLL/JAR inputs from an explicitly configured
unified build.
Nine shared Windows x86-64 source/object/PE/API reviewers now live under
`support/windows/`: six moved from the retired Phase-1 product graph, and the
W-013, W-025, and W-027 policy reviewers were added directly to the unified
system.
Their defaults or explicit arguments consume canonical
`out/<target-id>/<build-type>` artifacts.
The last W-013 host package producer and repository-side PowerShell runner were
retired after native Windows 7/7 and Linux 1/1 acceptance plus no-op repeats.
W-013 owns allocator/mapping/source-policy and 128/1024 MiB pressure; W-004
owns the package's generic managed stress; W-025 owns its supported JIT
controls and lifecycle behavior. Historical peak-memory/pagefile measurements
remain evidence, not portable pass criteria. The single durable R1/R2 summary
now lives under `docs/history`; its obsolete host checklist and duplicate
compact acceptance file were removed.
The unreferenced Phase-4 `JitSectionProbe.c` predecessor was removed after the
canonical W-025 section-policy case subsumed its low-view, R/RX/RW, execution,
low-VA failure/recovery, and commit-pressure contracts with stronger native and
cross-host acceptance.
Four unreferenced Wine-only package smoke scripts were also removed after their
W-002/W-003/W-004/W-010 package producers and repository-side runners had been
retired. Accepted Wine text remains evidence; new behavioral acceptance uses
the unified native stages.
W-002's remaining package checker, returned-ZIP reviewer and its unit tests,
host checklist, and duplicate checksum/acceptance files were retired after
the unified stage passed twice. Its durable rSELF/OSR/attach design, R1 timing
diagnosis, R2 correction, and native acceptance are one stage-owned
`stages/w002/ANALYSIS.md`; its two maintained runtime results remain adjacent
to the canonical `osr-unwind` and `attached-thread-entry` sources.
W-003's package checker, host checklist, and duplicate compact acceptance were
likewise removed. Its existing stage analysis now retains the unique issued
and returned archive identities, source commits, metadata-integrity result,
and native 19/19 acceptance alongside the cross-case frame/XMM design; current
results remain adjacent to both canonical cases.
W-004's remaining composite package checker, returned-ZIP reviewer, host
checklist, and duplicate checksum/acceptance files were removed after unified
W-003/W-004/W-025 native acceptance superseded that bundle. The direct runtime
singleton design, structural contract, incremental dependency fix, immutable
archive identities, and historical 28/28 acceptance now form one
`stages/w004/ANALYSIS.md`; current behavior is the unified W-004 stage.
The old Phase-4 pthread-once note was folded into its canonical case result:
the diagnosis, three-state publication fix, historical controls, and current
native `--parallel 16` reproduction now live beside the probe source.
The retired JIT-1 encoding summary now precedes the existing JIT-2 through
JIT-5 series under `docs/history`; it also retains the durable 12-control and
14-workload Wine conclusions. Duplicate smoke/matrix notes and raw host,
build-path, checksum, dump-scan, and aggregate files were removed after their
identities and acceptance contract were consolidated into that summary.
The H-001 scoped Phase-4 native rerun is likewise one sanitized history
summary. Its exact five-case markers, native-fatal exit, authoritative host,
and out-of-scope DNS note are retained; duplicate host/result records and
verbose process logs were removed because unified W-004/W-010 now maintain
the same GC/thread/handle and abort/fatal contracts.
FS-1 stack-high-water history is now adjacent to its canonical source. The
case result retains the old native/Wine margins, allocation-free sample
contract, Debug failure diagnosis, 40 KiB reserve rationale, and archive
identity; duplicate aggregate, host, dump-scan, and checksum files were
removed after current unified W-014 acceptance superseded the package.
FS-5's pending interpreter-tail disposition was merged into the canonical
managed-fault result. Its exact structural boundary and the reason a real
native fault would require product-altering or fabricated injection remain
source-adjacent; the standalone legacy result path was removed.
The W-010/W-014 E4–E6 diagnosis fragments were deduplicated into the existing
consolidated diagnostics analysis. All package/source/result/dump identities,
live lookup boundaries, and the rejected fixed-page SOE outcome remain there;
four compact fragments and one raw aggregate record were removed.
The unreferenced W-025 JIT-2/JIT-3 source preflights and the broken JIT-4
preflight were removed as well. The unified W-025 reviewer owns their current
mapping, lifecycle, nterp floating-point, JIT-control, PE-import/export, and
fail-closed binary contracts.
The W-014 FS-1 stack-high-water case now uses the exact test-only build variant
`win32-stack-high-water`. That variant has its own fingerprinted output
directory, cannot be staged as a product, and changes the managed case from
compile-only to target-runnable. Its shell-free runtime gate runs switch,
nterp, and JIT modes, while a `host-review` gate inspects the generated offsets
and target objects for allocation-free direct stack sampling. Product builds
keep both FS-1 declarations compile-only and receive no instrumentation macro.
W-003 uses the same variant discipline for frame-family attribution. Product
`stage:w003` runs the structural reviewer plus CriticalNative,
normal/FastNative, and XMM matrices; the exact `win32-frame-attribution`
variant adds the frame matrix and defines `ART_W003_FRAME_PROBE` only for
`art`. Its fingerprinted tree cannot be staged. The four counters have object
linkage only because generated nterp assembly consumes the common frame
macros; only reset and snapshot are variant DLL exports, and product `art.dll`
has no W-003 hook. Native Windows passed product 4/4 and variant 5/5, with
Ninja no-op repeats, sanitized aggregate JSON, no dumps, and no source/output
reparse points. A Linux-hosted Windows cross build also passed the structural
gate through the same CTest declaration using explicit host LLVM reviewer
tools.

Until `catalog.py` generation replaces the declarations, add or migrate test
targets through the common API in `tests/CMakeLists.txt`. Do not add another
standalone `CMakeLists.txt` product graph inside a case.

## Canonical target identity

Test selectors use the same closed identity enums as the product:

| Field | Allowed values |
|---|---|
| `target_platform` | `linux`, `windows`, `wasi` |
| `target_arch` | `x86`, `x86_64`, `armv7`, `aarch64`, `riscv64`, `arm64ec`, `wasm32`, `wasm64` |
| `target_abi` | `gnu`, `msvc`, `wasi` |

Use canonical target IDs such as:

```text
linux-x86_64-gnu
linux-aarch64-gnu
windows-x86_64-msvc
windows-aarch64-msvc
windows-arm64ec-msvc
wasi-wasm32-wasi
```

Aliases such as `x64`, `amd64`, `arm64`, bare `arm`, `win32`, and underscore
whole-target spellings are invalid. ARM64EC is the distinct target architecture
`arm64ec`, not ordinary AArch64 plus an ABI option. Linux never has an ARM64EC
target.

Declaring an identity is not a support claim. Planned and capability-blocked
profiles remain valid registry identities but cannot build until their profile
gates are satisfied.

## Test declaration

Every logical test declaration records:

| Field | Meaning |
|---|---|
| logical ID | stable lowercase hyphenated test name |
| stage | one virtual group in canonical `wNNN` form |
| output kind | executable, shared library, managed JAR, or command gate |
| linkage | `standalone`, `art-dso`, or `jni-dso` |
| sources | common sources plus any exact architecture variants |
| selectors | platform/architecture/ABI intersection or exact target IDs |
| capabilities | target features required before the test is meaningful |
| execution | `compile-only`, `target-runnable`, `cross-runner`, or `host-review` |
| timeout | optional positive whole seconds for a `target-runnable` declaration |
| contracts | searchable behavior labels such as `jni`, `stack`, `unwind`, or `jit` |

Use exact `TARGET_IDS` for a test tied to one complete target ABI. Use the typed
platform, architecture, and ABI intersection only when each combination in the
intersection is intentionally applicable. Do not combine exact IDs with broad
selectors in one declaration.

The generated test manifest records all declarations, including tests excluded
from the current target and the selector or capability that excluded each one.
An excluded test must not silently disappear.

### Linkage

`standalone`

: A target executable that does not link the ART runtime DSO. It may link
  explicitly declared platform or product-component dependencies required by
  the contract, but it must not acquire `art.dll` or `libart.so` accidentally.

`art-dso`

: A target executable linked through the generated CMake ART target and the
  corresponding DSO/import library. Never use a hard-coded path to `art.dll`,
  `art.lib`, or `libart.so`. Runtime execution uses the staged regular-file DSO
  closure.

`jni-dso`

: A target shared library loaded by managed/JNI test code. Direct ART linkage
  is not implied; any ART dependency must still be declared explicitly.

### Command gates

A command gate validates existing product outputs without compiling a dummy
probe. It declares `TYPE GATE`, a shell-free argument-list `COMMAND`, and
explicit product `DEPENDS`. It participates in `art-tests`, its one virtual
stage target, the applicability catalog, labels, and separate build/runtime
status exactly like a compiled probe. Shared runner logic belongs under
`tests/support/`; maintained acceptance records remain in the corresponding
`tests/cases/<logical-id>/` directories.

Use command gates only for artifact, loader, topology, package, or reviewer
contracts that genuinely need no target source. A C/C++ behavior probe remains
an executable or shared library. Every native command gate must use
`target-runnable` and is registered only when the frontend proves that the
build host can execute the exact target identity.

### Managed JARs

A managed declaration uses `TYPE MANAGED`, lists regular Java `SOURCES`, and
selects targets exactly like a native probe. It is compile-only by default. A
managed declaration becomes `target-runnable` only when it also declares a
shell-free `COMMAND`, exact product/runtime `DEPENDS`, deterministic success
markers, forbidden markers, timeout, and result location. CTest registers that
command only when the build host can execute the exact target identity. One
virtual stage may therefore contain native DSOs, managed JARs, and command
gates with different applicability and execution status.

Configure JDK 21 only in ignored `.art-build.local.toml`:

```toml
[tools]
jdk_root = "<absolute regular path to an official JDK 21>"
```

The frontend validates regular `java` and `javac` executables and the exact
major version, then passes `ART_JDK_ROOT` to CMake. Do not add that absolute
path to CMake source, a tracked preset, a result, or a manifest.

`art-managed-boot-jar` compiles the selected libcore/ICU source closure,
generates aconfig Java sources, and invokes the pinned `vendor/r8/r8.jar`.
Each applicable managed probe depends on those boot classes. The aggregate
`art-managed-tests` target builds only applicable managed artifacts:

```text
python tools/build_art.py build --target-id windows-x86_64-msvc --cmake-target art-managed-tests --parallel 16
```

All classes, DEX files, deterministic JARs, argument files, manifests, and
logs stay below `out/<target-id>/<build-type>/tests/managed/`. Manifests use
repository-relative source names and contain no machine absolute paths. The
builder invokes no shell, rejects symlink/reparse inputs, propagates javac/D8
failures, and replaces only its named work directories under that output root.

Managed runtime gates must use `support/runtime_gate.py` unless a case has a
genuinely unique runner. The shared runner invokes `dalvikvm` with `shell=False`,
creates its runtime root below the exact build output, stages `icudt72l.dat` as
a regular file, supplies only declared DSO directories, rejects link/reparse
components, and fails closed on a non-zero exit, timeout, missing marker, or
forbidden marker. Its `result.json` records target identity, class, exit status,
marker status, and JAR hashes without recording machine paths or environment
dumps.

Linkage describes the binary boundary under test. It is independent of whether
the test is compile-only, run locally, transferred to another machine, or
reviewed from returned evidence.

### Execution modes

`compile-only`

: Building the exact target artifact is the acceptance action. This does not
  claim runtime behavior.

`target-runnable`

: The configured build host can natively execute the exact target and CTest may
  register the command.

  A declaration-level `TIMEOUT` is a positive whole number of seconds. CMake
  records it as `timeout_seconds` in `art_test_catalog.json` and applies it to
  the registered CTest command. When the Python runner also has an internal
  timeout, keep that timeout shorter so it can terminate the child, sanitize
  its result, and return before CTest enforces the outer limit.

`cross-runner`

: Build and package locally, execute on an authoritative target machine, then
  import and review the returned result.

`host-review`

: A Python reviewer validates manifests, hashes, text results, object metadata,
  or another result that does not require executing the target program in the
  current process.

### Host-disruptive stress

A routine `target-runnable` gate must not deliberately exhaust a process-wide
or host-wide resource when failure can leave the build host unhealthy after
CTest terminates the child. Preserve such a closure test behind an explicit
opt-in argument, keep its accepted historical evidence adjacent to the source,
and run it only through a separately reviewed isolated-host procedure. The
default catalog command must exercise a bounded behavioral contract and finish
within its declared timeout.

Do not report a compile-only DLL as runtime-verified. Do not infer target
applicability from the architecture of the build host or from an emulation layer
available on the runner.

## Creating a test

### 1. Choose one logical contract

Select a stable ID that describes behavior rather than a work phase or current
machine. Prefer:

```text
jni-critical-native
win32-thread-stack
win32-stack-growth
art-runtime-load
```

Avoid:

```text
quick-test
windows-arm64-phase1
windows-x64-new-probe
attempt-42
```

Create `tests/cases/<logical-test-id>/` and place all case-owned source and
Python code there.

### 2. Decide source reuse explicitly

If the same C/C++ implementation and expected result apply to x86-64 and
AArch64, reference the same file for both targets:

```text
tests/cases/win32-thread-stack/probe.c
```

Do not copy it into `x86_64/` and `aarch64/` directories.

If the behavior is shared but architecture code differs, keep adjacent
variants:

```text
tests/cases/win32-stack-growth/probe.cc
tests/cases/win32-stack-growth/fault_x86_64.S
tests/cases/win32-stack-growth/fault_aarch64.S
```

The target-aware Python overlay selects one variant. If the ABI assertion or
expected result differs materially, create separate logical test IDs instead.

Do not use a symlink, junction, reparse point, generated source alias, or copied
vendor source to share test code.

### 3. Start with truthful applicability

A new Windows AArch64 bring-up probe normally starts with:

```text
TARGET_IDS windows-aarch64-msvc
```

Reusing source previously tested on x86-64 does not prove AArch64 support. Add
another target only after its build, runtime behavior when required, and result
review pass independently. A Windows AArch64 result never proves ARM64EC.

### 4. Select a virtual stage

Use an existing `wNNN` stage when the probe is part of that milestone's
contract. Define a new stage only for a genuinely new work group. Physical
source location does not change when stage membership changes.

Building `art-test-stage-w014`, for example, builds every applicable member of
that stage. It does not mean every `w014` test supports the same target and does
not by itself prove runtime success.

### 5. Define the runner and reviewer

Use Python `subprocess` with an argument list. Do not construct a shell command.
The runner must:

- fail on a nonzero exit or missing acceptance marker;
- use only frontend-provided paths and target metadata;
- place its working state under the current binary directory;
- avoid shared `/tmp`, repository-source output, and ambient DLL discovery;
- record separate build and runtime status;
- avoid locale-dependent parsing where a machine-readable result is possible;
- work on Windows without Bash, PowerShell, WSL, Cygwin, or Unix utilities; and
- reject symlink/reparse entries in transferred packages and results.

The reviewer must treat the returned package as untrusted input: validate paths
before extraction, reject links and traversal, check required files and hashes,
and fail closed on malformed or incomplete results.

### 6. Add or update `RESULT.md`

Create one maintained `RESULT.md` beside the case source. It is a reviewed
acceptance ledger, not output written by the runner.

A useful initial structure is:

```markdown
# <logical test name> result

## Contract

<What the test proves and what it does not prove.>

## Target status

| Target ID | Applicable | Build | Runtime | Last accepted |
|---|---:|---:|---:|---|
| windows-x86_64-msvc | yes | verified | verified | yyyy-MM-dd HH:mm:ss |
| windows-aarch64-msvc | yes | pending | pending | — |
| windows-arm64ec-msvc | no | not applicable | not applicable | — |

## Latest accepted run

- Product commit: `<commit>`
- Toolchain: `<portable identity/version>`
- Commands: `<repository-relative frontend commands>`
- Runner: `<normalized authoritative-runner description>`
- Result/artifact hashes: `<hashes>`
- Known limitations: `<limitations>`
```

The result may link to small curated files under
`evidence/<target-id>/`. It must not embed a workstation path, complete
environment dump, executable, DSO, archive, crash dump, or routine full log.

If one historical phase result covers several independent tests, split its
acceptance claims into the corresponding case `RESULT.md` files. Keep a short
`tests/stages/<wNNN>/RESULT.md` only when a stage-wide conclusion remains useful.

## Building and running tests

Configure through the portable frontend:

```text
python tools/build_art.py configure --target-id windows-x86_64-msvc
```

Build and run the applicable catalog scope:

```text
python tools/build_art.py test --target-id windows-x86_64-msvc --parallel 16
```

Select one virtual stage:

```text
python tools/build_art.py test --target-id windows-x86_64-msvc --stage w014 --parallel 16
```

Use 16 jobs on the current 16 GiB native Windows VM. Linux-hosted cross builds
on agent01 may use 32 jobs.

Use `--build-type Debug` or `--build-type RelWithDebInfo` when the non-default
configuration is required. The frontend uses the corresponding canonical
binary directory and must reject reuse with a different target profile or
build-host fingerprint.

A test request fails when the selected scope has no applicable tests or when it
has applicable tests but no runnable CTest gate. This is intentional: zero
tests must not look like a successful verification run.

### Cross-target execution

For a target that the build host cannot execute, the workflow is:

1. Configure and build the exact target under its canonical output directory.
2. Create a regular-file-only test package below `out/.../packages/`.
3. Transfer it to the authoritative target runner.
4. Execute it with the case's Python runner.
5. Return a machine-readable result package.
6. Import and review it below `out/.../results/`.
7. Explicitly update the case `RESULT.md` only after acceptance.

The host platform and architecture are manifest fields; they are never encoded
as `<host>-to-` in an output path. Running an x86-64 executable through Windows
ARM emulation remains an x86-64 test, not an AArch64 or ARM64EC test.

## Generated output structure

All build and run outputs belong under:

```text
out/<target-id>/<build-type>/
  generated/
    Tests.cmake
    test_catalog.json
  tests/
    bin/
    lib/
    managed/
    results/
      <logical-test-id>/
        runtime/
        result.json
        stdout.txt
        stderr.txt
  results/
    <imported-cross-target-result>/
      <run-id>/
        result.json
  stage/
    tests/
  packages/
    <stage-or-test-bundle>.zip
```

CMake/Ninja object files and internal directories also remain below this binary
tree. Test code must not write generated state into `tests/`, `tools/`,
`vendor/`, root `build/`, root `run/`, or root `dist/`.

## VCS policy

### Add to VCS

- maintained C, C++, assembly, Java, and Python source;
- target-neutral catalog declarations and common CMake integration;
- deterministic, hand-reviewed text fixtures that cannot be generated from a
  canonical source;
- case `RESULT.md` files and optional stage summaries;
- small sanitized JSON manifests and selected text evidence with continuing
  diagnostic value;
- documentation describing the contract and expected behavior.

### Do not add to VCS

- `.zip`, `.7z`, tar archives, or returned test packages;
- `.exe`, `.dll`, `.lib`, `.pdb`, `.ilk`, `.exp`, `.dmp`, `.wasm`, or platform
  equivalents;
- `.o`, `.obj`, `.a`, `.so`, generated JNI libraries, or import libraries;
- generated `.class`, `.dex`, or `.jar` files;
- generated CMake, Ninja, object, staging, or package trees;
- routine stdout/stderr logs, complete trace collections, or crash dumps;
- `__pycache__`, `.pyc`, editor state, or test caches;
- machine-local SDK/tool paths, absolute source/build paths, secrets, tokens,
  usernames, or full environment dumps;
- symlinks, junctions, reparse points, link-text aliases, or archive link
  entries; or
- copied vendor/product source used only to avoid declaring the real dependency.

`vendor/r8/r8.jar` is the only named binary exception. It supplies the pinned
D8/R8 tool and must remain tracked until an equally reproducible replacement
exists. Do not use that exception to admit any other JAR or any wildcard path.

Run the main-index audit before requesting a commit:

```text
python tools/check_vcs_files.py
```

The root `.gitignore` is a convenience, not the enforcement boundary. The VCS
audit and review must still reject a force-added artifact.

## Migrating `tools/verify`

`tools/verify` is a temporary mixed historical tree and should disappear after
its useful content has canonical ownership. Do not move it wholesale to
`tests/archive` or `tests/archived`.

| Existing content | Action |
|---|---|
| reusable native/assembly source | move into the owning `tests/cases/<id>/` |
| managed source for the same contract | move into the same case |
| test-specific Python runner/reviewer | move into the same case |
| shared Python framework | move to `tests/support/` |
| accepted test result | merge into the case's adjacent `RESULT.md` |
| useful stage-wide conclusion | reduce to `tests/stages/<wNNN>/RESULT.md` |
| small durable text evidence | move under the case's `evidence/<target-id>/` |
| generated/returned binary or archive | move below `out/` and remove from VCS |
| shell or PowerShell orchestration | replace with Python, then remove |
| Phase-0/Phase-1/per-probe product CMake | remove after unified coverage; do not relocate |
| obsolete progress narrative | move selectively to `docs/history/` or remove |

Use `git mv` for maintained sources and records so their history remains easy
to follow. Update all consumers in the same change and verify that no active
reference still points at the old path. Do not delete an old graph until the
unified target builds the applicable probes and the required behavioral or
review gate owns its former acceptance claim.

## Review checklist

Before a new or migrated test is ready:

- [ ] The logical ID describes behavior, not a phase or machine.
- [ ] Platform, target architecture, ABI, capabilities, and execution mode are
  explicit.
- [ ] ARM64EC is not inferred from AArch64 and target support is not inferred
  from build-host emulation.
- [ ] Shared source has one physical regular-file copy; architecture variants
  are selected explicitly.
- [ ] Linkage is `standalone`, `art-dso`, or `jni-dso` and dependencies use
  generated CMake targets rather than artifact paths.
- [ ] The test uses the unified target toolchain and does not create a second
  product graph.
- [ ] Runner/reviewer code is Python and does not invoke a POSIX or platform
  shell.
- [ ] All generated files go below the canonical `out/` directory.
- [ ] `RESULT.md` is adjacent to the logical source and records separate build
  and runtime truth for each target.
- [ ] Tracked evidence is small, sanitized, textual, and useful.
- [ ] No binary, archive, absolute path, symlink, junction, reparse point, or
  generated cache is staged.
- [ ] `python tools/check_vcs_files.py` passes.
- [ ] The focused catalog test and relevant target build/test stage pass.
