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
Legacy shell runners and per-probe CMake entry points still reference these
canonical files as temporary compatibility shims; they must be replaced by the
unified Python/CMake/Ninja path before `tools/verify` can be removed.

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
| output kind | executable or shared library |
| linkage | `standalone`, `art-dso`, or `jni-dso` |
| sources | common sources plus any exact architecture variants |
| selectors | platform/architecture/ABI intersection or exact target IDs |
| capabilities | target features required before the test is meaningful |
| execution | `compile-only`, `target-runnable`, `cross-runner`, or `host-review` |
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

`cross-runner`

: Build and package locally, execute on an authoritative target machine, then
  import and review the returned result.

`host-review`

: A Python reviewer validates manifests, hashes, text results, object metadata,
  or another result that does not require executing the target program in the
  current process.

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
python tools/build_art.py test --target-id windows-x86_64-msvc
```

Select one virtual stage:

```text
python tools/build_art.py test --target-id windows-x86_64-msvc --stage w014
```

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
  test-work/
    <logical-test-id>/
  results/
    <logical-test-id>/
      <run-id>/
        result.json
        stdout.txt
        stderr.txt
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
