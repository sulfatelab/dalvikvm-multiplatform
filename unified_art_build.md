# Unified ART build refactor tracker and design

Status: live refactor tracker; the x86-64 product build is unified, while test,
packaging, topology-parity, and legacy-removal work remains active

Last updated: 2026-08-01

This document is the authoritative live tracker and design record for replacing
the repository's split Linux and Windows ART build paths. Keep the tracker near
the top current whenever build ownership, target admission, phase-gate
migration, validation evidence, or the remaining work queue changes. The
deeper design and acceptance sections remain the contract against which tracker
items are closed.

## Live refactor tracker

### Tracker rules

- Use `COMPLETE`, `PARTIAL`, `BLOCKED`, and `NOT STARTED` for area status.
- Mark an item complete only after its command path and required native or
  cross-target gate pass from a fresh frontend-owned build directory.
- Distinguish a compile-only probe group from a runnable behavioral gate.
- Preserve useful probe sources and result evidence while removing alternative
  product graphs and host-specific orchestration around them.
- Do not commit generated or returned binary artifacts, executable images,
  libraries, crash dumps, or package archives. `vendor/r8/r8.jar` is the one
  explicit retained exception because it is the pinned D8/R8 build tool, not a
  product or test artifact, and replacing it with a reproducible source build
  is not presently practical.
- Record machine paths only in ignored local configuration. Tracker evidence
  uses canonical target IDs and stable repository-relative names.
- Use `--parallel 32` for Linux and Windows-cross work on agent01, and
  `--parallel 16` for native builds on the 16 GiB Windows Server 2025 VM.
- Update the dated evidence below after any change to the frontend, generated
  graph, target bundle contract, test registry, staging rules, or topology.

### Current status snapshot

| Area | Status | Current position | Exit condition |
|---|---|---|---|
| Python frontend | COMPLETE for the initial slice | `generate`, `check-generated`, `configure`, `build`, `test`, and `stage` exist; subprocesses are shell-free; configured JDK 21 is validated and passed to CMake | keep regression coverage current |
| Linux x86-64 product | COMPLETE for the current W-004/W-013 runtime slice | a fresh target-local boot/runtime closure passes all five W-004 gates plus the shared W-013 128 MiB non-moving-heap gate; identical stage rebuilds are Ninja no-ops | add boot-image/security packaging and migrate the remaining behavioral stages |
| Windows x86-64 product | PARTIAL / experimental | Linux-hosted cross and native Windows Server 2025 product builds pass; fresh native W-002 passes 4/4, W-003 product passes 4/4, W-003 frame variant passes 5/5, expanded W-004 passes 26/26, W-010 passes 8/8, W-013 passes 7/7, and expanded W-025 passes 9/9; every identical stage repeat is a Ninja no-op | run the remaining multi-stage catalog and migrate its behavioral tests |
| Compiler DSO parity | COMPLETE for `art-compiler` | both targets emit a shared compiler DSO; Windows imports `art.dll` and exports `art_compiler_jit_create` | retain exact ABI and no-cycle gates |
| Windows runtime DSO exports | COMPLETE for current x86-64 closure | `art.dll` combines explicit source annotations with a reviewed 187-entry runtime-consumer DEF, never CMake auto-export; Debug has 2,065 exports and RelWithDebInfo has 2,066 | keep the consumer allowlist and actual PE boundary under regression review |
| Full DSO topology parity | PARTIAL | five module kinds and two target-specific module pairs still differ | convert each difference or record a reviewed target exception |
| Unified phase catalog | PARTIAL | seven virtual stages declare 32 native probes, 47 managed JARs, and twelve command gates; Windows has 89 applicable items (59 target-runnable, six host-review, and 24 compile-only in the product variant), while Linux x86-64 has seven applicable items (six runnable and one compile-only artifact) | migrate the remaining behavioral runners, portable JNI expansion, and result checks |
| Boot/runtime packaging | PARTIAL | the base boot JAR and probe JARs are Python/CMake/Ninja-owned, deterministic, target-local, and fail-fast; managed gates isolate a runtime root and stage pinned ICU data plus the mandatory native boot DSO closure | add boot images, security providers/resources, cacerts, and complete runtime packages |
| POSIX-free Windows build host | COMPLETE for the current native/managed W-002, W-003, W-004, W-010, W-013, and W-025 graphs; PARTIAL end to end | Server 2025 uses configured official JDK 21, Python, CMake, Ninja, and plain Clang drivers; native managed build/runtime and no-op gates pass without POSIX tooling | migrate every retained behavioral gate and run the complete current catalog |
| Legacy build removal | PARTIAL | active product ownership was demoted, project-owned symlink overlays were removed, and the superseded Linux miniature, Windows Phase-0/Phase-1, and libcore/ICU product graphs were deleted; the checked-in Linux graph and split overlay datasets remain | remove or demote every alternative product path after gate migration |
| CI/acceptance automation | NOT STARTED | no in-repository CI workflow owns the acceptance matrix | fresh-build, no-op, graph, command, artifact, and native-host gates run automatically |
| Additional architectures | BLOCKED by capability gates | all 17 canonical identities are registered; only `linux-x86_64-gnu` and experimental `windows-x86_64-msvc` generate | admit each profile only after its architecture and runtime gates pass |
| Windows AOT/OAT | BLOCKED / separate track | compiler DSO parity does not provide Windows OAT production or loading | satisfy `win32_aot_oat.md`; do not imply capability from `art-compiler.dll` |

### Latest verification baseline (2026-08-01)

- [x] `PYTHONPATH=tools/bp2cmake python3 -m pytest tools/bp2cmake/tests tests/host -q`:
  186 passed, including generated PE-header, Linux/Windows test-catalog,
  shell-free runtime/managed-artifact gates, parallel-frontend, JDK validation,
  deterministic JAR, Windows-path/DSO-name, reviewer ownership, W-010
  nonzero/fault/debugger/fatal-dump orchestration, W-013 source-policy,
  W-025 JIT lifecycle/mapping/process-policy/reviewer orchestration, fatal
  contracts, the shell-free Math CriticalNative matrix, W-024 cleanup, the
  reviewed PE runtime-consumer export boundary, retired libcore-product-path
  absence, VCS binary/source-ownership coverage, and schema-2 build-fingerprint
  graph/tool/target-binding identity coverage.
- [x] Fresh generation loads the same 260 Blueprint files for both targets and
  emits 34 generated modules for `linux-x86_64-gnu` and 33 for
  `windows-x86_64-msvc`. Both graphs emit the separate `openjdkjvmti` DSO;
  Linux additionally emits `sigchain`, while Windows supplies the reviewed
  platform-source `sigchain` target from the common native entry point.
- [x] Blueprint discovery no longer has hard-coded global path filtering or an
  `--exclude-top` product argument. The unified overlay carries one typed,
  path-free scan policy keyed by stable logical root variables. Graph-manifest
  schema 2 records the resolved component/top-level exclusions; regenerating
  both targets preserved the 260-input and 34/33-module graphs.
- [x] The first maintained-CMake decomposition slice moved platform SDK/host
  imports plus handwritten Windows `sigchain` and POSIX compatibility targets
  into common `native/cmake/ArtPlatform.cmake`. Linux and Windows-cross CMake
  regeneration produced no compile/link work, and immediate repeats were
  Ninja no-ops at `--parallel 32`.
- [x] Configure-time aconfig, mterp, asm-defines, and Windows PE-header
  generation moved unchanged into common `native/cmake/ArtCodegen.cmake`.
  Linux and Windows-cross reconfiguration again produced no compile/link work,
  followed by immediate Ninja no-ops at `--parallel 32`. VCS regression
  coverage rejects either focused module becoming an independent CMake entry
  point.
- [x] Generated-graph loading, the shared `art-compiler` DSO assertion, and
  reviewed Windows target/source augmentation moved unchanged into common
  `native/cmake/ArtTargetGraph.cmake`. The sole `native/CMakeLists.txt` remains
  the entry point; the focused module cannot declare its own CMake project.
  Linux, Windows-cross, and native Windows Server 2025 reconfiguration produced
  no compile/link work, immediate repeats were Ninja no-ops, and the native
  58-file CET contract passed. Linux/cross used 32 jobs and native Windows used
  16 jobs.
- [x] Source/toolchain drift shims, test-variant instrumentation, generated
  target compile/link policy, and Windows PE-header overlays moved unchanged
  into common `native/cmake/ArtCompatibility.cmake`. Linux, Windows-cross, and
  native Windows Server 2025 reconfiguration produced no compile/link work;
  immediate repeats were Ninja no-ops, all 170 host regressions passed, and
  both cross and native 58-file CET contracts passed. Linux/cross used 32 jobs
  and native Windows used 16 jobs.
- [x] Unified target-aware catalog registration moved unchanged into common
  `native/cmake/ArtTests.cmake`; `native/CMakeLists.txt` remains the sole CMake
  entry point. Linux, Windows-cross, and native Windows Server 2025
  reconfiguration produced no compile/link work, immediate repeats were Ninja
  no-ops, all 177 host regressions passed, and both cross and native 58-file
  CET contracts passed. Linux/cross used 32 jobs and native Windows used 16.
- [x] Build-manifest schema 2 records the full serialized target profile;
  SHA-256 identities for the generated graph, graph manifest, and generated
  CMake profile; each tool's resolved path, shell-free version command, and
  complete version output; and deterministic layout/content identities for
  configured bundle, sysroot, and runtime roots. Target-binding traversal
  rejects links, reparse points, and non-regular entries instead of following
  them. The regular-file Windows bundle contains 6,618 files in 144
  directories, totals 718,271,618 bytes, and has tree identity
  `c3892764c8a4b7d386437e896ea2905aee722617c18a6bc8db62ff14aa44083c`.
  In a fresh ignored output root, Linux and Windows-cross configuration replay
  accepted identical fingerprints; both product builds passed at
  `--parallel 32` and repeated as Ninja no-ops. The cross `art-tests` graph
  also built and repeated as a no-op, and its CET contract passed 58/58 with
  no raw links or legacy packagers. A fresh native Windows Server 2025 product
  completed all 1,857 steps at `--parallel 16` on the 16 GiB VM; `art-tests`
  completed 123 steps; product, tests, and the post-reconfiguration test repeat
  were Ninja no-ops; and the native CET contract passed all 58 PE files.
- [x] The redundant product-wide `-Wno-error` compatibility demotion was
  removed. Layer 2 already drops upstream `-Werror`, neither admitted product
  compile database retained a global warning-as-error flag, and a host
  regression prevents the blanket demotion from returning. The stricter
  policy rebuilt all 1,771 affected Linux edges and all 1,806 affected
  Windows-cross edges at `--parallel 32`; native Windows rebuilt the same
  1,806-edge Windows graph at `--parallel 16` on the 16 GiB VM. All three
  products passed and immediately repeated as Ninja no-ops, and both cross and
  native CET contracts remained 58/58.
- [x] The target-wide `-Wno-strict-primary-template-shadow` suppression was
  removed while the reviewed exceptions for `file_utils.cc`, `utils.cc`, and
  libdexfile sources remain source-scoped. A host regression rejects the
  blanket generator expression without rejecting those explicit exceptions.
  The resulting policy rebuilt all 1,771 Linux edges and 1,806 Windows-cross
  edges at `--parallel 32`, then rebuilt all 1,806 native Windows edges at
  `--parallel 16`. All three products passed and immediately repeated as Ninja
  no-ops; cross and native CET contracts remained 58/58.
- [x] The target-wide Linux `mdvm_toolchain_prelude.h` force-include was
  removed. Linux toolchain drift is now confined to the reviewed libbase,
  libdexfile, runtime, and `openjdkjvmti` source/module shims; direct standard
  headers for `file_utils.cc`, `time_utils.cc`, `runtime_common.cc`, and the
  generated `invoke_type` source are guarded explicitly as Linux-only policy.
  Windows retains its required graph-wide platform prelude. The full Linux
  product rebuilt successfully and immediately repeated as a Ninja no-op at
  `--parallel 32`; the final Windows-cross policy passed and repeated as a
  Ninja no-op at `--parallel 32`. Host regressions prove the platform boundary
  and all 179 host tests pass.
- [x] The Windows platform prelude was removed from seven reviewed
  dependency-owning targets. `art-dex2oat` now applies it only to its 19 ART
  sources and one generated ART source; its 224 embedded BoringSSL sources,
  standalone BoringSSL, Expat, fdlibm, and ICU compile with only explicit
  Windows SDK hygiene definitions. A configure-time count guard makes ART-side
  dex2oat source drift fail closed. Forced-prelude compile commands fell from
  1,795 to 821. The Windows-cross affected rebuild passed and repeated as a
  Ninja no-op at `--parallel 32`; native Windows rebuilt 1,009 affected edges
  and repeated as a no-op at `--parallel 16`. Native and cross compile
  databases agree on the 224/20 dex2oat split, the native CET contract passed
  58/58, and all 179 host tests pass.
- [x] The standalone LZMA target now owns its Windows portability without the
  ART prelude. Its existing target definitions are sufficient for all 44 C
  sources on both build hosts, reducing forced-prelude compile commands from
  821 to 777. Fresh Linux and Windows-cross product graphs rebuilt all 1,773
  and 1,808 edges respectively at `--parallel 32` and repeated as Ninja
  no-ops. Native Windows rebuilt the 44 LZMA sources and `lzma.dll` at
  `--parallel 16` and also repeated as a no-op. Cross and native compile
  databases agree, both CET contracts pass 58/58, and all 179 host tests pass.
- [x] `unwindstack` now owns its Windows portability through project POSIX
  compatibility headers instead of the ART prelude. The project `sys/types.h`
  wrapper supplies guarded Windows `pid_t` and `ssize_t`, while `unistd.h`
  owns `getpagesize()` through `sysconf(_SC_PAGESIZE)`. All 34 `unwindstack`
  compile commands are prelude-free on both Windows build hosts, reducing the
  forced-prelude total from 777 to 743. Linux, Windows-cross, and native
  Windows products rebuilt successfully at their required 32/32/16 job
  limits and immediately repeated as Ninja no-ops. Cross and native CET
  contracts pass 58/58, and all 180 host tests pass.
- [x] The one-source `artpalette`, `nativebridge`, and Windows `procinfo`
  platform-library targets now compile without the ART prelude on both Windows
  build hosts. The project `sys/stat.h` wrapper owns POSIX `mkdir(path, mode)`
  adaptation and the group/other aggregate mode bits used by `nativebridge`;
  the duplicate `mkdir` macro was removed from the prelude. This reduces the
  forced-prelude total from 743 to 740. Linux, Windows-cross, and native
  Windows products passed at their required 32/32/16 job limits and repeated
  as Ninja no-ops. Cross and native CET contracts pass 58/58, and all 181 host
  tests pass.
- [x] The five-source `log` and five-source `ziparchive` dependencies now
  compile without the ART prelude on both Windows build hosts. Project
  `sys/types.h` owns the Windows `mode_t` spelling, `unistd.h` maps `lseek64`
  directly to the UCRT 64-bit API, and the redundant compatibility-stub
  implementation was removed. `ziparchive` owns its four 64-bit stdio
  spellings as explicit target definitions. This reduces forced-prelude
  compile commands from 740 to 730. Linux, Windows-cross, and native Windows
  products passed at their required 32/32/16 job limits and repeated as Ninja
  no-ops. Cross and native CET contracts pass 58/58, and all 182 host tests
  pass.
- [x] The seven-source `nativehelper` dependency now compiles without the ART
  prelude on both Windows build hosts. Its C sources and owned headers already
  expose the complete Windows contract, so this stage needs no new platform
  shim or target definition. Forced-prelude compile commands fell from 730 to
  723, and the cross and native compile databases agree on zero `nativehelper`
  consumers. Linux and both Windows products passed at their required 32/32/16
  job limits and repeated as Ninja no-ops. Cross and native CET contracts pass
  58/58, and all 182 host tests pass.
- [x] The five-source `elffile` static library now compiles without the ART
  prelude on both Windows build hosts. Its ART headers and the Windows UCRT
  surface already provide the required stream and file-descriptor contracts,
  so the target needs no compatibility shim. Forced-prelude compile commands
  fell from 723 to 718, and the cross and native compile databases agree on
  zero `elffile` consumers. Linux and both Windows products passed at their
  required 32/32/16 job limits and repeated as Ninja no-ops; cross and native
  CET contracts pass 58/58, and all 182 host tests pass.
- [x] Windows SDK macro hygiene now belongs to a project `windows.h` wrapper
  instead of the forced ART prelude. The wrapper supplies the common lean SDK
  definitions, delegates to the real SDK with `include_next`, and removes the
  `CONST`, `ERROR`, and reserved-identifier macros plus the opt-in `CALLBACK`
  collision at the Windows-header boundary. This fixes the SDK `CONST` versus
  DEX-opcode collision for the two-source `profile` library and makes both of
  its compile commands prelude-free. Forced-prelude commands fell from 718 to
  716. The complete Windows-cross and native graphs rebuilt 640 and 726
  affected actions at 32 and 16 jobs, then repeated as Ninja no-ops; Linux
  remained a no-op at 32 jobs. Cross and native compile databases agree, both
  CET contracts pass 58/58, and all 183 host tests pass.
- [x] Five small leaf targets now use only their owned Windows contracts:
  one-source `androidio`, two-source `art-disassembler`, one-source `icu`,
  one-source `nativeloader`, and one-source `odrstatslog`. All six compile
  commands are prelude-free on both Windows build hosts without adding a shim
  or target definition, reducing the forced-prelude total from 716 to 710.
  Linux and both Windows products passed at the required 32/32/16 job limits
  and repeated as Ninja no-ops. Cross and native compile databases agree, both
  CET contracts pass 58/58, and all 183 host tests pass.
- [x] The three-source `openjdkjvm` DSO now compiles without the ART prelude on
  both Windows build hosts. `OpenjdkJvm.cc` directly includes `sched.h`,
  `atomic_pair.h` uses fixed-width `uint32_t` counters from `cstdint`, and the
  project `stdlib.h` wrapper owns the Windows `posix_memalign` declaration that
  is implemented by `windows_x64_posix_stubs`; the duplicate declaration was
  removed from the broad prelude. Forced-prelude compile commands fell from
  710 to 707. The affected Linux, Windows-cross, and native Windows graphs
  completed with their required 32/32/16 job limits and repeated as Ninja
  no-ops. Cross and native compile databases agree at 1,816 commands with all
  three `openjdkjvm` commands prelude-free, both CET contracts pass 58/58, and
  all 184 host tests pass.
- [x] The one-source `dalvikvm` launcher now compiles without the ART prelude
  on both Windows build hosts. Its source and included project headers already
  expose the complete launcher contract, so this stage needs no compatibility
  shim or target definition. Forced-prelude compile commands fell from 707 to
  706. Linux and both Windows products passed at their required 32/32/16 job
  limits and repeated as Ninja no-ops. Cross and native compile databases
  agree at 1,816 commands with the `dalvikvm` command prelude-free, both CET
  contracts pass 58/58, and all 184 host tests pass.
- [x] The one-source Windows `sigchain` DSO now compiles without the ART
  prelude on both build hosts. Its platform source, `sigchain.h`, project
  `signal.h`, fault-record header, and direct Windows SDK include already own
  the complete contract, so no source shim was added. Forced-prelude compile
  commands fell from 706 to 705. Linux and both Windows products passed at the
  required 32/32/16 job limits and repeated as Ninja no-ops. Cross and native
  compile databases agree at 1,816 commands with the `sigchain` command
  prelude-free, both CET contracts pass 58/58, and all 184 host tests pass.
- [x] The one-source `windows_x64_posix_stubs` compatibility library now
  compiles without the ART prelude on both build hosts. Its implementation
  directly includes the Windows SDK, CRT, and project POSIX wrapper headers it
  consumes; no compatibility declaration had to be widened. Forced-prelude
  compile commands fell from 705 to 704. The full static-library consumer
  closure linked on both Windows hosts, while Linux and both Windows products
  passed at the required 32/32/16 job limits and repeated as Ninja no-ops.
  Cross and native compile databases agree at 1,816 commands with the stubs
  command prelude-free, both CET contracts pass 58/58, and all 184 host tests
  pass.
- [x] The two-source `dex2oat` executable now compiles without the ART prelude
  on both Windows build hosts. The project `sys/stat.h` wrapper now owns the
  `fchmod` declaration, and a project `stdio.h` wrapper owns `getline`; both
  implementations already reside in `windows_x64_posix_stubs`, and their
  duplicate prelude declarations were removed. Forced-prelude compile commands
  fell from 704 to 702. The header migration received broad clean-equivalent
  coverage, including 1,193 affected native Windows actions at 16 jobs. Linux
  and both Windows products passed at their required 32/32/16 job limits and
  repeated as Ninja no-ops. Cross and native compile databases agree at 1,816
  commands with both `dex2oat` commands prelude-free, both CET contracts pass
  58/58, and all 185 host tests pass.
- [x] The 13-source `icu_jni` DSO now compiles without the ART prelude on both
  Windows build hosts. Its ICU bridge sources and existing target definitions
  already expose the complete Windows contract, so this stage needs no new
  compatibility shim. Forced-prelude compile commands fell from 702 to 689.
  Linux and both Windows products passed at their required 32/32/16 job limits
  and repeated as Ninja no-ops. Cross and native compile databases agree at
  1,816 commands with all 13 `icu_jni` commands prelude-free, both CET
  contracts pass 58/58, and all 185 host tests pass.
- [x] The 18-source `base` DSO now owns its Windows portability without the ART
  prelude. The project `string.h` wrapper owns the UCRT `strcasecmp` and
  `strncasecmp` spellings, and `hex.cpp` receives only its exact `stdint.h`
  toolchain-drift include instead of the broad platform prelude. Forced-prelude
  compile commands fell from 689 to 671. The shared-header migration exercised
  1,395 Linux, 1,487 Windows-cross, and 1,516 native-Windows affected actions at
  the required 32/32/16 job limits; all three products then repeated as Ninja
  no-ops. Cross and native compile databases agree at 1,816 commands with all
  18 `base` commands prelude-free, both CET contracts pass 58/58, and all 185
  host tests pass.
- [x] The 20 ART-side `art-dex2oat` sources now compile without the broad ART
  prelude, matching the 224 embedded BoringSSL sources that were already
  independent. The project `malloc.h` wrapper owns the Windows `mallinfo`
  fallback, while only `oat_writer.cc` receives a narrow namespace-lookup shim
  for the pinned source's MS-compatible friend declaration. Forced-prelude
  compile commands fell from 671 to 651. Clean-equivalent validation rebuilt
  706 Linux closure actions plus ten downstream links, 534 Windows-cross
  closure actions plus 108 downstream product actions, and 659 native-Windows
  actions at the required 32/32/16 job limits; all three products then repeated
  as Ninja no-ops. Cross and native compile databases agree at 1,816 commands:
  all 244 `art-dex2oat` commands are broad-prelude-free and exactly one carries
  the narrow OatWriter shim. Both CET contracts pass 58/58, and all 186 host
  tests pass.
- [x] The 21-source Windows `javacore` DSO now compiles without the ART prelude
  on both build hosts. Its libcore JNI sources, Windows platform sources, and
  project-owned JNI stubs already expose the complete contract, so no new shim
  or target definition was needed. Forced-prelude compile commands fell from
  651 to 630. Linux and both Windows products passed at their required 32/32/16
  job limits and repeated as Ninja no-ops. Cross and native compile databases
  agree at 1,816 commands with all 21 `javacore` commands prelude-free, both
  CET contracts pass 58/58, and all 186 host tests pass.
- [x] The 22-command Windows `dexfile` static library now compiles without the
  ART prelude on both build hosts. Its existing headers expose the complete
  Windows contract; the 15 direct `libdexfile/dex/*.cc` commands retain only
  their source-scoped `-Wno-strict-primary-template-shadow` suppression. The
  Linux-only toolchain prelude remains unchanged. Forced-prelude compile
  commands fell from 630 to 608. Linux and both Windows products passed at
  their required 32/32/16 job limits and repeated as Ninja no-ops. Cross and
  native compile databases agree at 1,816 commands with all 22 `dexfile`
  commands prelude-free, both CET contracts pass 58/58, and all 186 host tests
  pass.
- [x] The 29-source Windows `openjdkjvmti` DSO now compiles without the ART
  prelude on both build hosts. `deopt_manager.cc` directly includes the
  project-owned portable `sched.h` for its `sched_yield` call; the other 28
  sources needed no new shim. The Linux-only JVMTI toolchain prelude remains
  unchanged. Forced-prelude compile commands fell from 608 to 579. Linux and
  both Windows products passed at their required 32/32/16 job limits and
  repeated as Ninja no-ops. Cross and native compile databases agree at 1,816
  commands with all 29 `openjdkjvmti` commands prelude-free, both CET contracts
  pass 58/58, and all 187 host tests pass.
- [x] `check-generated` passes for both frontend-owned canonical graphs.
- [x] Fresh Linux configuration with Clang 21, CMake, Ninja, and configured
  JDK 21 emits a 91-declaration catalog. Seven declarations apply to
  `linux-x86_64-gnu`: the five runnable W-004 gates, the W-013 non-moving
  managed artifact, and its runnable 128 MiB gate. Six register with CTest;
  the managed artifact is compile-only and built as the W-013 gate dependency.
- [x] Windows-target configuration emits the same 91 declarations and keeps
  89 items applicable. Fifty-nine product-variant items are
  `target-runnable`, and the W-002 managed-entry, W-003 quick-boundary, W-004
  runtime-load, W-010 boundary-unwind, W-013 source-policy, and W-025
  JIT-contract reviewers are
  separately registered `host-review` declarations. Twenty-four applicable
  declarations remain compile-only. The complete W-002, W-003, W-004, W-010,
  W-013, and W-025 runnable/reviewer slices are accepted on the authoritative
  native host.
- [x] FS-1 is now an exact `windows-x86_64-msvc` test-only build variant with a
  fingerprinted output directory. Product staging rejects the variant and the
  product graph receives no instrumentation macro. The variant applies the
  macro consistently to C, C++, and generated assembly, runs the managed
  switch/nterp/JIT matrix through Python without a shell, and registers the
  migrated allocation-free/direct-store object reviewer as a W-014
  `host-review` gate. Debug and RelWithDebInfo each passed 9/9 on Windows
  Server 2025; both immediate repeats were Ninja no-ops and passed 9/9 again.
  Each mode produced four complete records, zero exit, positive native margin,
  sanitized aggregate JSON, and no dump. The source and both output trees had
  zero reparse points.
- [x] After that native acceptance, the redundant FS-1 standalone CMake graph,
  Bash build/runtime runner, Bash host packager, and package-only PowerShell
  runner were removed. Maintained reproduction is the unified frontend plus
  the W-014 virtual stage; immutable archive hashes and returned text remain as
  historical evidence only.
- [x] W-002 now owns shell-free managed attach and OSR runtime matrices plus
  its source/object reviewer in the unified catalog. Native Windows Server
  2025 accepted all four CTest gates; the identical repeat was a Ninja no-op
  and passed 4/4 again. Attach and OSR each completed nterp and switch twice,
  their aggregate JSON records contain no absolute host paths or dumps, and
  both the source and product-output trees contain zero reparse points. The
  synthetic unwind probe resolves private ART stubs from the adjacent PDB with
  DbgHelp `*W` APIs, so it does not widen the explicit `art.dll` export ABI.
- [x] After unified native W-002 acceptance, its standalone attach CMake graph,
  two Bash/Wine runtime runners, Bash host packager, and package-only
  PowerShell runner were removed. The broader legacy Phase-4/W-025 scripts no
  longer invoke those runners; current W-002 reproduction is only the unified
  frontend and virtual stage. Historical checklists, returned evidence, and
  archive hashes remain readable.
- [x] The remaining Phase-4 OSR leaf wrapper was retired after its complete
  R12/RBP, GPR/XMM, invoke, GenericJNI, switch, interpreter-bridge, and
  epilogue matrix passed as `art.w002.win32_osr_unwind_probe` on native
  Windows. Its source and adjacent result remain under `tests/cases/osr-unwind/`.
- [x] W-003 now owns shell-free CriticalNative, normal/FastNative, XMM, and
  frame-family matrices plus one source/object/PE-unwind reviewer. Product
  `stage:w003` passed 4/4 on Windows Server 2025 and its exact
  `win32-frame-attribution` variant passed 5/5; both identical repeats were
  Ninja no-ops. The variant alone defines `ART_W003_FRAME_PROBE` for `art`,
  exposes only the reset/snapshot test API, and stores output in its own
  fingerprinted directory that cannot be staged. Product `art.dll` has zero
  W-003 exports. Both trees have zero dumps and reparse points, and all seven
  aggregate JSON results contain no machine absolute paths.
- [x] A final-source Linux-hosted Windows cross build completed all 1,492
  `stage:w003` edges and passed the same structural reviewer through CTest; its
  identical repeat was a Ninja no-op. The reviewer tools are explicit
  frontend-resolved fingerprint inputs, so Linux-hosted cross configuration
  uses host `llvm-readobj`/`llvm-objdump` without a target `.exe` suffix.
- [x] After unified native W-003 acceptance, its four standalone probe CMake
  graphs, four Bash/Wine runners, Bash host packager, and repository-side
  PowerShell runner were removed. The broader Phase-4 aggregate now consumes
  only the unified structural reviewer. Later W-004 and W-010 historical
  package flows acquire W-003 DLL/JAR inputs from an explicitly configured
  unified Windows target tree and retain their own package-level Wine/native
  behavioral matrices. Historical checklists, accepted hashes, and returned
  evidence remain readable.
- [x] `art.dll` no longer uses `WINDOWS_EXPORT_ALL_SYMBOLS`. Before the change,
  a Debug scan found 80,318 candidate exports and exceeded PE's 65,535-entry
  limit, while RelWithDebInfo exposed 17,112. ART's existing `EXPORT` boundary
  now maps to producer `dllexport`; namespace/enum visibility uses the PE-safe
  `ART_VISIBILITY_EXPORT`, `Thread` keeps `self_tls_` private and exports only
  its required callable/data boundary, and three optimized inline template
  specializations have one Windows-only producer translation unit. The later
  full-product linkability pass added the checked
  `compat/art_runtime_consumer_exports.def` for direct PE imports that cannot
  be expressed by the existing source-level producer/consumer annotations.
  Its 187 unique entries cover the complete RelWithDebInfo and Debug compiler,
  dex2oat, executable, and JVMTI consumer closure; CMake tracks the DEF through
  `LINK_DEPENDS`, so changing it relinks `art.dll` and its import library.
  Native inspection reports 2,065 Debug and 2,066 RelWithDebInfo `art.dll`
  exports. `art-compiler.dll` separately retains its one-entry reviewed DEF
  allowlist; other generated DSOs retain auto-export until their own explicit
  ABI is reviewed.
- [x] A clean full native Windows product build exposed runtime imports that
  stage-specific compiler builds had not exercised. The repaired
  RelWithDebInfo graph links `art.dll`, `dalvikvm.exe`, `art-compiler.dll`,
  `art-dex2oat.dll`, `dex2oat.exe`, `openjdkjvmti.dll`, and the remaining
  product DSOs; its identical repeat is a Ninja no-op. Staging hashes 28
  regular-file artifacts plus the manifest, contains the complete DSO closure,
  and has zero reparse points. The final W-004 rerun passes 26/26.
- [x] A fresh native Windows Debug output tree generated the same 33-module,
  260-Blueprint graph with plain Clang 21 GNU-style drivers and Ninja, then
  completed the full 1,857-edge product graph at `--parallel 16`. The immediate
  repeat is a Ninja no-op. In both supported build types,
  `art-compiler.dll` has exactly the single `art_compiler_jit_create` export
  and imports `art.dll`; no static compiler fallback was introduced.
- [x] Every MSVC-ABI build type now selects the release dynamic CRT
  (`MultiThreadedDLL`). This preserves Debug optimization/assertion behavior
  without depending on Visual Studio's private `msvcrtd.lib`; the native CMake
  entry point rejects a mismatched CRT cache.
- [x] All 32 catalog-owned native/assembly probe declarations have logical
  `tests/cases` ownership across 29 source-owning cases with adjacent results.
  The latest clean `windows-x86_64-msvc` cross graph compiled and linked both
  newly migrated libcore probes and the unified dlmalloc-configuration probe
  from their regular-file paths with `--parallel 32`.
- [x] The historical W-013 memory-map closure includes complete low-VA
  fragmentation and exhaustion. Even after reducing the fragmented cadence
  from roughly 3,800 reservations to 64, the fresh native Server 2025 gate
  timed out after 300.01 seconds and twice left the VM requiring a reboot;
  Wine completed that path in 0.76 seconds. Routine unified CTest now keeps
  the disruptive path behind explicit `--exhaustive-low-va` opt-in and runs
  the bounded placement/ownership/page-state contract. The safe native probe
  passes in 0.08 seconds within the complete accepted W-013 stage.
- [x] The fresh native Stage-8 W-013 build completed 1,488 Ninja actions. Its
  first CTest run proved the other five gates before the exhaustive memory-map
  timeout. After the safe-default correction, the exact memory-map CTest
  passed in 1.14 seconds; the canonical stage rerun was a Ninja no-op and
  passed 6/6 in 4.94 seconds. All seven W-013 declarations are build-verified,
  all six runnable declarations are runtime-verified, both managed result JSON
  files are sanitized, and the source/output trees have zero reparse points.
- [x] The W-013 `MemMap`, page-transition, mspace-lock, metadata-placement,
  write-barrier, and exact required-low caller source audits now run through a
  dependency-free Python `host-review` gate. Native Stage-8 was a Ninja no-op
  and passed the expanded W-013 stage 7/7 in 6.89 seconds, including the source
  review in 3.69 seconds. The two superseded mixed Bash audit/build/Wine entry
  points were removed.
- [x] The W-013 mspace-owner executable now runs through a shell-free Python
  fatal-contract gate. It accepts the normal attach/rebind path and requires
  four subprocesses to terminate with the expected missing-provider,
  use-after-detach, wrong-owner-detach, and double-attach diagnostics. The
  rebooted authoritative Server 2025 Stage-8 tree remained a Ninja no-op and
  passed W-013 7/7 in 5.31 seconds; the mspace gate took 0.50 seconds, its
  sanitized JSON records one success and four nonzero death cases with no
  timeout, and the host remained responsive afterward. The superseded Bash/Wine
  mspace runner was removed.
- [x] The remaining dlmalloc Bash runner was retired after its source-only
  contracts moved into the W-013 Python reviewer. That reviewer now enforces
  active Windows macros, six provider-attachment tokens, exactly one authorized
  raw-mspace creation file, and absence of global owner discovery in addition
  to the existing memory policies. The native Stage-8 tree remained a Ninja
  no-op and passed 7/7 in 25.16 seconds on a cold source scan; the reviewer
  completed an immediate repeat in 2.01 seconds.
- [x] The historical dual-target non-moving runner was retired without losing
  Linux coverage. The managed artifact and 128 MiB command gate now select the
  exact `linux-x86_64-gnu` and `windows-x86_64-msvc` identities; the 1024 MiB
  resource gate remains Windows-only. A fresh 1,485-action Linux build passed
  W-013 1/1 in 0.27 seconds and repeated as a Ninja no-op in 0.28 seconds. The
  reconfigured Server 2025 Stage-8 tree was also a Ninja no-op and passed W-013
  7/7 in 5.14 seconds. All managed results are sanitized, both Windows trees
  contain zero reparse points, and the host remained responsive.
- [x] The last W-013 host-package path was retired after a final native/Linux
  audit. Windows Server 2025 rebuilt eleven previously absent test edges at
  `--parallel 16`, passed 7/7 in 14.93 seconds, then repeated as a Ninja no-op
  in 5.05 seconds. Linux passed 1/1 and repeated as a no-op at `--parallel 32`
  in 0.31 seconds. The deleted Bash producer was already broken by its
  references to removed runners and the deleted Phase-1 tree; its PowerShell
  matrix is superseded by W-013 allocator/pressure gates, W-004 managed stress,
  and W-025 JIT controls/lifecycle. Historical per-process memory and pagefile
  measurements remain evidence, not portable pass criteria.
- [x] The unreferenced Phase-4 `JitSectionProbe.c` was removed. The canonical
  W-025 section-policy case is its stronger regular-file successor: it owns
  R/RX/RW pagefile views, generated execution, complete low-VA rejection and
  recovery, 1 GiB commit pressure, CFG, and fail-closed process policy in the
  unified native/cross stage.
- [x] Four unreferenced package-only Wine smoke scripts for historical W-002,
  W-003, W-004, and W-010/W-014 bundles were removed after their producers and
  repository-side runners were retired. Their accepted text evidence remains;
  current behavioral acceptance is owned by unified native stages.
- [x] The unreferenced W-025 JIT-2/JIT-3 source preflights and already-broken
  JIT-4 preflight were removed. Their mapping/CFG, lifecycle/unwind, nterp
  floating-point, supported-control, PE, and fail-closed contracts are all
  enforced by the live unified W-025 reviewer. Accepted historical source
  reports remain beside the native evidence.
- [x] The shared shell-free runtime gate now owns native executable repetition,
  marker, timeout, DSO-path, log, and sanitized-result orchestration. W-014
  pthread-once passed 10/10, thread-stack preserved all five reservation sizes
  and its 512/128 join/detach counters, and stack-page preserved all selection,
  restoration, and 258-fault checks. The authoritative Server 2025 stage built
  in 24 Ninja actions and passed 3/3 in 1.95 seconds. All records contain zero
  failed iterations or host paths; both Windows trees have zero reparse points
  and the VM remained responsive. The two superseded Bash/Wine runners were
  removed.
- [x] W-014 recursive growth, executable-stack/RX, and CET policy are now
  shell-free native gates. A source-adjacent JSON matrix owns the four growth
  modes and their exact per-mode marker contracts; the generic Python runner
  executed all 16/16 repetitions. RX preserved all 64 marker bytes through a
  `PAGE_EXECUTE_READ` stack-page transition and recovery, while CET reported
  zero known incompatible fields. The authoritative Server 2025 Stage-8 tree
  passed all six current W-014 gates in 2.47 seconds with a Ninja no-op, zero
  result path leaks, and zero source/output reparse points.
- [x] The exact x86-64 W-014 pre-growth diagnostic is now a unified native
  matrix: implicit E9 passed 30/30, native collision produced the expected
  `0xc0000005` child exit, attach/detach passed 5/5, and the 1/10/100-thread
  commit-scale cases preserved the exact 2,093,056-byte per-worker cost. All
  39/39 process runs passed. The complete current W-014 stage passed 7/7 in
  3.81 seconds with a Ninja no-op, sanitized records, zero reparse points, and
  responsive `lsass` and `sshd`.
- [x] All 48 retained Java probe sources now have logical `tests/cases`
  ownership and adjacent results. The registry emits 47 managed artifacts;
  the old verification tree owns no Java source.
- [x] The shell-free managed builder compiled 2,919 boot sources into 5,849
  classes and a DEX boot JAR using official JDK 21 plus the pinned in-tree D8.
  A clean Linux-hosted Windows target build produced all 46 then-declared
  applicable managed JARs, and its second identical `art-managed-tests` build
  was a Ninja no-op. The later native W-004 acceptance produced all 33 managed
  artifacts in that stage, including the newly declared Hello JAR.
- [x] The same CMake path built the target-local boot JAR and common managed
  Hello, GC, and Math probes for `linux-x86_64-gnu`; all generated classes,
  DEX/JAR files, manifests, argument files, and logs remained below the exact
  target output.
- [x] Linux `art-compiler` completed a fresh 701-action build after the
  identity migration and emits `libart-compiler.so` with dynamic ART
  dependencies.
- [x] The complete Linux product completed a fresh 1850-action build; after the
  latest Windows-scoped CMake changes, a 264-action affected rebuild also
  passed with `--parallel 32`, and `dalvikvm -showversion` reported
  `ART version 2.1.0 x86_64`.
- [x] A second identical Linux `art-compiler` build reports
  `ninja: no work to do.`
- [x] At main-repository commit `22026b9`, native Windows Server 2025 x86-64
  freshly configures and builds all 1825 actions in the canonical
  `windows-x86_64-msvc` product graph with `--parallel 32`, LLVM 21.1.8,
  CMake 3.31.8, Ninja 1.13.2, and Python 3.13.14. The source projection and
  installed tools use space-free regular paths; archive timestamps ahead of
  the VM clock were normalized before the clean acceptance run.
- [x] The native no-stage Windows `test` command builds every applicable
  catalog target and passes all three registered runnable gates: W-002
  OSR/unwind plus the W-014 pthread-once and thread-stack probes.
- [x] Before managed-artifact expansion, that native Windows acceptance
  recorded 29 applicable/build-verified probes, three runtime-verified probes,
  and 26 compile-only probes with `runtime_status=not-required`. At that point,
  native revalidation of the then-81-item applicable catalog remained pending;
  the later accepted W-004, W-013, and other stage slices are recorded below.
- [x] The authoritative Server 2025 host installed the official Eclipse
  Temurin 21.0.12 x64 JDK from Adoptium's published asset, verified its
  published SHA-256 before and after transfer, and configured its space-free
  regular path only in ignored `.art-build.local.toml`. No GUI, shell build
  layer, or tracked machine path was required.
- [x] A fresh native Windows W-004 build completed 1,515 Ninja actions with
  `--parallel 32`, including 2,919 boot sources, 5,849 boot classes, 33 managed
  W-004 artifacts, `icu_jni.dll`, `javacore.dll`, and `openjdk.dll`. Imageless
  Hello, GC stress, and Math CriticalNative then passed as three CTest gates;
  an identical rerun reported `ninja: no work to do.` and passed again.
- [x] A subsequent fresh native Windows Server 2025 projection accepted the
  unified libcore probe ownership: W-004 passed 4/4 after adding the BoringSSL
  fixed-message SHA-256 executable, and W-013 passed 1/1 for the process-wide
  CRT-fd/Winsock registry linked through `openjdkjvm.dll`. The same source and
  output trees contained zero reparse points; all generated artifacts stayed
  outside VCS.
- [x] The managed gate caught Windows bootstrap names that still requested
  Linux-style `lib*.dll` basenames. ART now requests the generated no-prefix
  DLL names, and the compatibility `dlopen` boundary strictly converts UTF-8
  to UTF-16 before `LoadLibraryW`. W-027 tracks the broader remaining `*A` API
  inventory without expanding this runtime-gate slice.
- [x] A non-following native scan found zero symlinks or reparse points in the
  fresh source projection and complete W-004 build tree. The three result JSON
  files record exit zero, no missing/forbidden markers, target ID and JAR
  hashes, while containing no build-host absolute paths.
- [x] W-004 now also owns the separately loaded `openjdkjvmti.dll`, its native
  agent, managed force-interpreter runner, and a structural runtime-load and
  assembly-dependency reviewer. The final native Server 2025 build used
  `--parallel 16` for the 16 GiB VM and passed the complete stage 6/6; its
  identical repeat was a true Ninja no-op and passed 6/6 again. Three JVMTI
  processes compiled exactly the two permitted methods, compiled no
  CriticalNative method, and produced no dumps. All 24 JSON records were free
  of absolute host paths, and both source and output trees had zero reparse
  points. The Linux-hosted Windows cross graph also built all 33 modules and
  passed the structural reviewer, followed by an identical Ninja no-op.
- [x] The JVMTI import boundary adds 24 bounded C++ exports plus explicit
  `mspace_malloc` and `mspace_usable_size` exports to `art.dll`; it does not
  restore `WINDOWS_EXPORT_ALL_SYMBOLS`. The accepted native DLL has 1,964
  exports. The reviewer verifies 563 quick, ten nterp, and one JNI direct
  `Runtime::instance_` relocations and the explicit Ninja dependency from each
  x86-64 assembly consumer to the shared assembly support inputs.
- [x] W-004 now runs 13 accepted Phase-3 libcore behaviors through one
  data-driven, shell-free Python runner: core reflection/charset/monitor,
  DNS, ordinary and forced GC, GoldenApp, interruption, file I/O, TCP loopback,
  errno/UTF-8 paths, properties/clocks, runtime memory, thread stress, and the
  expected-nonzero uncaught-exception path. Windows Server 2025 passed the
  expanded stage 19/19 in 25.15 seconds and repeated from a true Ninja no-op
  in 21.44 seconds with `--parallel 16`; the Linux-hosted Windows cross tree
  rebuilt the affected `javacore.dll` edge with `--parallel 32` and passed its
  structural reviewer. The migration exposed a recursive Win32
  `getnameinfo` bridge; the bridge now converts Java addresses to `sockaddr`,
  maps bionic flags explicitly, and calls Unicode `GetNameInfoW`. The 20
  superseded Phase-3 Bash producers/runners were removed; Path/AbsPath and the
  separate L-003 matrix were the next semantic slices recorded below.
- [x] W-004 PathProbe and AbsPathProbe now use the same shell-free case runner
  with regular-file staging. Native Windows validates the standalone Hello
  regression, multi-JAR semicolon classpath, drive/mixed/UNC path blocks,
  forward/backslash/mixed absolute JAR paths, parent/name and absolute-file
  behavior, and two negative colon-separated classpaths. Their portable result
  records pass 2/2 and 6/6 subcases with zero reparse paths and no serialized
  host paths. Windows Server 2025 passed the expanded W-004 stage 21/21 in
  27.79 seconds and repeated from `ninja: no work to do.` at 21/21 in 27.97
  seconds with `--parallel 16`; the cross tree built both changed JARs with
  `--parallel 32` and passed its reviewer. Three path-specific Bash scripts
  were removed; at that checkpoint only the generic Phase-3 builder/runner and
  L-003 matrix remained.
- [x] The L-003 migration promotes ExecProbe and Ipv6Probe on exactly Windows +
  x86-64 + MSVC ABI. Native Exec validates both `Runtime.exec` and
  `ProcessBuilder`; native IPv6 validates AF_INET6 bind to `::` and
  `getsockname` without reverse-DNS side effects. LocaleProbe and ZipProbe each
  timed out after 120 seconds on native Windows, and UdpProbe failed
  `DatagramSocket` construction with `setsockopt failed: EINVAL`; those three
  therefore remain compile-only. The historical all-pass Wine result remains
  evidence, not native acceptance.
- [x] Windows Server 2025 passed the expanded W-004 stage 23/23 in 30.70 seconds
  with `--parallel 16`; its immediate repeat was a Ninja no-op and passed 23/23
  in 32.58 seconds. A fresh Linux-hosted Windows cross build with
  `--parallel 32` passed the structural reviewer, and its repeat was a Ninja
  no-op. That fresh cross build exposed host-dependent quoted-include lookup in
  the generated PE header projection: `runtime_options.h` reached projected
  `jit_code_cache.h`, whose unchanged sibling headers were not explicitly
  anchored. The common CMake entry point now supplies the source JIT include
  directory to all three affected translation units; native Windows rebuilt
  the same objects and retained 23/23 acceptance plus a no-op repeat.
- [x] The last generic Phase-3 builder, runner, and L-003 Wine orchestration
  were removed. All 26 superseded Phase-3 shell wrappers are now retired;
  native-open managed cases remain in the common compile-only catalog rather
  than preserving an alternative graph.
- [x] W-004 now runs HandleLeakProbe, PerfSmokeProbe, and ThreadHeavyProbe on
  exactly Windows + x86-64 + MSVC ABI through the shared shell-free managed
  runtime gate. Each uses interpreter mode, a 180-second child timeout, an
  output-owned work root, and its complete success-marker contract. Windows
  Server 2025 passed the expanded stage 26/26 in 35.93 seconds with
  `--parallel 16`; its immediate Ninja no-op repeat passed 26/26 in 34.21
  seconds. The Linux-hosted Windows cross stage passed its sole structural
  reviewer with `--parallel 32`, and its immediate repeat was a Ninja no-op.
- [x] The obsolete Phase-4 aggregate Wine runner, generic managed builder and
  runner, and four GC/runtime-stress wrappers were removed after native
  acceptance. Historical text evidence remains readable; crash, JIT, and OSR
  leaf diagnostics are retained until their own remaining ownership is
  resolved.
- [x] W-010 now owns seven shell-free target-runnable gates in the unified
  catalog: the four-mode UEF matrix, eight-case fault-record adapter, live
  sigchain ordering/frame-SEH probe, two-mode managed-fault debugger, managed
  abort, static/JIT/OSR fatal dispatch, and six-case switch/nterp/JIT managed
  recovery matrix. Windows Server 2025 passed all 7/7 twice with
  `--parallel 16`; handled paths produced no dumps, while the three fatal
  origins produced exactly three validated `MDMP` files. The final stage build
  was a true Ninja no-op. The Linux-hosted Windows cross stage built the same
  four EXEs and three JARs with `--parallel 32`, then repeated as a Ninja
  no-op. All 39 native result JSON files are free of machine absolute paths,
  and non-following scans found zero reparse points in both the source
  projection and complete output tree.
- [x] The debugger gate exposed a Windows loader isolation hazard: copying only
  `dalvikvm.exe` into a work directory allowed the system `icuuc.dll` to outrank
  the matching product DLL and failed with `STATUS_ENTRYPOINT_NOT_FOUND`.
  Passing the frontend-resolved absolute product EXE to the debugger preserves
  its product DLL directory while the jars, data, logs, and dumps remain in an
  isolated output-owned working tree. No machine path is serialized.
- [x] W-010 now also owns a shell-free host reviewer for the linked PE unwind
  records of ExecuteSwitchImplAsm, invoke/static-invoke, OSR, GenericJNI, and
  interpreter-bridge boundaries. It resolves their private RVAs from
  `art.pdb` with the frontend-resolved official `llvm-pdbutil`, then audits
  `art.dll` with `llvm-readobj`; the product export boundary stays unchanged.
  A fresh Linux-hosted Windows cross build completed 1,491 edges, passed this
  reviewer in 2.93 seconds, and repeated as a Ninja no-op in 2.97 seconds.
- [x] A fresh native Server 2025 Stage-10 tree passed expanded W-010 8/8 in
  19.27 seconds at `--parallel 16`; its immediate Ninja no-op repeat passed
  8/8 in 17.26 seconds. The superseded Phase-4 managed-abort and native-crash
  Wine wrappers were then removed; their retained logs are historical only.
- [x] W-025 now owns eight shell-free target-runnable gates plus one
  `host-review` gate. Windows Server 2025 passed the expanded stage 9/9 twice
  in 20.95 and 20.68 seconds. The stage covers six unwind-info encodings,
  runtime-function
  registration, managed invalidation/collection/exact reuse, the eight-cycle
  216-compilation/192-reuse stress contract, 64 MiB and 1 GiB JIT mappings,
  low-VA and `SEC_COMMIT` section policy, CFG execution, fail-closed
  `ProhibitDynamicCode`, and twelve isolated JIT control/workload processes:
  default, environment-disabled, `-Xusejit:false`, filter, exclude, quiet,
  retired-key, Math, IO, Net, GC, and throw. The native
  build used `--parallel 16` on the 16 GiB VM and its repeat was a Ninja no-op.
  All 41 result JSON files in the current native result tree contain zero
  absolute paths; non-following scans of source and output found zero reparse
  points.
- [x] The Linux-hosted Windows cross W-025 stage builds with `--parallel 32`,
  passes the same source/PE reviewer, and repeats as a Ninja no-op. A generated
  PE header overlay exports only `JitCodeCache::GetGarbageCollectCode()` and
  `GetCurrentRegion()` for the ordinary JNI test DSOs; it is source-scoped to
  the defining translation unit and does not restore unbounded
  `WINDOWS_EXPORT_ALL_SYMBOLS` on `art.dll`.
- [x] The final Phase-4 JIT smoke and workload-matrix Bash wrappers were
  retired after their supported control semantics and canonical Math/IO/Net/
  GC/throw workloads passed in unified W-025. The ten old managed jars without
  repository source remain historical evidence only. The unreferenced,
  already-broken JIT-5 source preflight checker was removed after its retired
  key and fail-closed source/binary contracts migrated to the live reviewer.
- [x] After native W-025 acceptance, its four host-package producers, four
  package-only PowerShell runners, five W-025 Bash build/preflight runners,
  two package-only Wine smoke wrappers, and six superseded Phase-4 JIT
  section/unwind/fatal runners were removed. Historical accepted results,
  checklists, package checkers/reviewers, and compact text evidence remain
  readable; maintained reproduction is only the unified W-010/W-025 stages.
- [x] The eight early Linux converter bring-up harnesses under `tools/verify`
  were removed after the unified graph, show-version gate, and maintained
  historical scope document subsumed their product and evidence roles. Their
  checked-in generated CMake snapshots and isolation stubs are no longer
  alternative build entry points.
- [x] The Windows Phase-0 CMake entry point, Bash generator, generated graph,
  and checked-in generated aconfig headers were removed after the unified
  Windows product graph subsumed that foundational link gate. Its historical
  result remains evidence, not a supported reproduction command.
- [x] The Windows Phase-1 CMake entry point, generated 17-module graph, and
  closure snapshot were removed after the unified product and probe graph
  subsumed them. Its six reusable Python PE/source auditors moved to
  `tests/support/windows` with canonical unified-output defaults. The W-024
  source audit is now Python-owned under `tests/support` and covered by the
  host suite. It checks the actual retired-workaround contract instead of the
  obsolete whole-file equality rule that rejected accepted guarded FS-1
  stack-high-water instrumentation.
- [x] The unproducible 641-line libcore/ICU source snapshot, its standalone
  CMake graph, and its duplicate `openjdkjvm` memory source were removed after
  the unified graph built the full ICU/libcore/openjdk DLL closure. The final
  Phase-3 shell package/staging flow, the one-DLL `libcombined` raw linker, and
  the obsolete minimal `NativeConverter` stub were retired after native W-004
  acceptance. Their stable 2026-07-17 result moved to `docs/history`; current
  builds and stages use only `tools/build_art.py` and generated Ninja edges.
- [x] Retiring the raw linker made the CET reviewer fail closed on the unified
  graph itself. It exposed the handwritten product `sigchain.dll` and thirteen
  test probes without explicit `/CETCOMPAT:NO`. `sigchain` now declares the
  option directly and the shared Windows test-target policy propagates it to
  every probe. The reviewer ignores Ninja `phony` aliases, rejects any new raw
  PE linker or legacy shell packager, and passes all 58 real cross-built PE
  link commands and files. A fresh native Windows Server 2025 RelWithDebInfo
  product build completed 1,857 edges at `--parallel 16`; its repeat was a
  Ninja no-op. The native `art-tests` build completed 123 edges, the reviewer
  then reported `raw_links=0 legacy_packagers=0 link_targets=58 pe_files=58`,
  and the final `art-tests` repeat was also a Ninja no-op. The Linux-hosted
  Windows product and test graphs retain the same no-op baseline.
- [x] Layer-2 policy now has one target-aware
  `overlay/art_port_policy.py`. Exact common fields are declared once and
  whole-field Linux/Windows deltas remain explicit behind
  `make_overlay(profile)`. Before deleting the fixed policy files, serialized
  equality held for all 38 Linux and 31 Windows module policies plus their
  global policy. Both 260-Blueprint generated graphs passed `check-generated`,
  both local products remained Ninja no-ops at `--parallel 32`, and native
  Windows repeated the 33-module graph check and product no-op at
  `--parallel 16`; the native CET review remained 58/58.
- [x] The final `install_into_phase1.sh` compatibility installer was removed.
  The unified graph builds ICU, libcore, OpenJDK, ART, and their managed assets
  into one target tree, so no maintained workflow copies a second product into
  the deleted Phase-1 tree. The historical Phase-3 package staging flow was
  subsequently retired with the alternative libcore/ICU graph.
- [x] The six documentation-only Linux E2E bring-up records moved from
  `tools/verify/e2e` to flat, clearly historical names under `docs/history`;
  their obsolete harness commands are not test entry points.
- [x] The maintained LLP64 audit moved to `tools/llp64_audit`, now consumes the
  unified compile database and writes regenerated reports below `out/`. The
  redundant Bash/clang-query path, experimental libclang scanner, and generated
  report copies were removed; the accepted summary remains beside the scanner.
  Its fast source scan reports zero high/medium findings and 119 safe-helper
  sites on the current tree. A fresh frontend-owned Linux configure emitted a
  1,771-entry unified `compile_commands.json`, proving the database is available
  without a legacy verification graph.
- [x] Native Windows `check-generated` passes for the 32-module, 260-Blueprint
  graph, and a second identical full product build reports
  `ninja: no work to do.`
- [x] A clean Linux-hosted `windows-x86_64-msvc` cross build completed all
  1825 Ninja actions with `--parallel 32`. It links `art.dll`,
  `art-compiler.dll`, `art-dex2oat.dll`, `dex2oat.exe`, `javacore.dll`,
  `openjdk.dll`, and `openjdkjvm.dll`; this is a build/link result and does not
  claim Windows AOT/OAT runtime capability.
- [x] Native Windows staging records 28 hashed regular-file artifacts plus its
  JSON manifest. A non-following scan finds zero reparse points in the complete
  build tree, and Python `ctypes` loads both staged `art.dll` and
  `art-compiler.dll` from the staged dependency closure.
- [x] Native LLVM object inspection reports COFF x86-64, dynamic-base,
  high-entropy-VA, and NX-compatible `art-compiler.dll`; it imports `art.dll`,
  exports `art_compiler_jit_create`, and `art.dll` has no reverse import of the
  compiler DLL.
- [x] The current cross-built Windows stage records 27 regular-file artifacts
  and the Linux stage records 28; non-following scans find no symlinks in
  either build or stage tree.
- [x] Generated graph/profile files contain no filesystem absolute paths.
- [x] The main-repository VCS audit permits only the exact pinned
  `vendor/r8/r8.jar` binary-tool exception; the former tracked Phase 3 evidence
  ZIP now lives under ignored `out/` storage and its accepted SHA-256 remains in
  the text record.
- [x] All 1825 native Windows Ninja commands were audited. Their outer
  executables are 1099 plain `clang++.exe` commands, 645 plain `clang.exe`
  commands, and 81 CMake-generated native `cmd.exe` wrappers for archive,
  export-table, link, or Python-codegen sequences. No POSIX shell, Make,
  NMake, GCC, G++, MinGW, `cl.exe`, `clang-cl`, direct `ld.lld`, or direct
  `lld-link` invocation occurs; links inside the native wrappers still invoke
  the configured plain Clang driver with `-shared` and `-fuse-ld=lld`.
- [x] The documented Linux W-004 `test` command builds its declared product and
  managed-runtime dependencies and passes five CTest gates: imageless Hello,
  GC stress, Math CriticalNative, exact `dalvikvm -showversion`, and
  Python-owned ELF DSO topology requiring `libart-compiler.so -> libart.so`
  while forbidding the reverse edge. Its identical rerun is a Ninja no-op.
- [x] After adding `openjdkjvmti` to the common root closure, a new target-local
  Linux W-004 tree generated 34 modules from 260 Blueprint files and completed
  a fresh 1,586-action stage build with `--parallel 32`. All five gates passed;
  the immediate repeat was a true Ninja no-op and passed 5/5 again.
- [x] Building the newly rooted Linux `openjdkjvmti` target exposed two pinned
  source assumptions hidden by the earlier closure: bionic's global
  `nullptr_t` and ART's pre-glibc-2.38 `strlcpy` fallback. A module-scoped,
  Linux-only compatibility prelude now resolves those host-toolchain drifts
  without editing vendor source or changing other targets. The corrected
  31-edge build links `libopenjdkjvmti.so`; its immediate repeat is a Ninja
  no-op. The Windows cross W-004 graph remained a no-op and passed its reviewer
  after the same common-CMake change.
- [x] Math CriticalNative now has one case-local Python matrix for the exact
  Linux and Windows x86-64 targets. It runs `-Xint` and threshold-zero JIT twice
  each, requires an explicit Windows compile record, writes portable aggregate
  JSON, and rejects dumps and filesystem links/reparse points. Its W-024 source
  cleanup audit is part of the live W-004 reviewer instead of a legacy shell
  preflight. Native Windows no-op runs passed 26/26 twice at `--parallel 16`
  (Math 5.59/5.64 seconds); the fresh Linux W-004 build and repeat passed 5/5
  at `--parallel 32` (Math 1.31 seconds). The Linux-hosted Windows cross graph
  rebuilt 66 affected edges, passed the reviewer, and immediately repeated as
  a Ninja no-op in 0.64 seconds.
- [x] The final W-004 host package was an obsolete composite: W-003 now owns
  its CriticalNative and normal/FastNative matrices, W-004 owns its
  interpreter/JVMTI/runtime-load and managed stress behavior, and W-025 owns
  the supported JIT controls, workloads, and lifecycle stress. After native
  acceptance and no-op repeats for all three stages, the Bash package producer
  and repository-side PowerShell runner were removed. The source-less legacy
  FloatProbe JAR remains historical evidence; maintained FP/native-ABI
  coverage is deeper in W-003. Package checkers/reviewers and returned text
  remain available only for immutable historical evidence.

### Unified stage migration coverage

One historical work stage maps to exactly one virtual target named
`art-test-stage-wNNN`. Building a stage is not by itself a runtime pass.

| Stage | Current build catalog | Exact-ID / typed selectors | Execution modes | Remaining semantic coverage |
|---|---:|---|---|---|
| `w002` | 1 EXE, 1 DLL, 2 managed, 1 gate | 3 exact / 2 typed | 3 runnable, 1 host-review, 1 compile-only | registered Windows x86-64 coverage is complete |
| `w003` | 4 DLLs, 4 managed, 1 gate | 3 exact / 6 typed | product: 3 runnable, 1 host-review, 5 compile-only; frame variant: 4 runnable, 1 host-review, 4 compile-only | registered Windows x86-64 coverage is complete |
| `w004` | 2 EXEs, 1 DLL, 33 managed, 3 gates | 6 exact / 33 typed | product: 27 target-runnable, 1 host-review, 11 compile-only; Windows applicable subset: 25 target-runnable, 1 host-review, 11 compile-only | Windows embedding, native-open Locale/UDP/Zip, and remaining unregistered libcore behavior |
| `w010` | 4 EXEs, 3 managed, 1 gate | 2 exact / 6 typed | 7 target-runnable, 1 host-review | registered Windows x86-64 coverage is complete |
| `w013` | 4 EXEs, 1 managed, 3 gates | 3 exact / 5 typed | 6 runnable, 1 host-review, 1 compile-only | registered x86-64 native, managed, and source-policy coverage is complete |
| `w014` | 7 EXEs, 1 DLL, 1 managed, 1 gate | 3 exact / 7 typed | product: 7 runnable, 3 compile-only; FS-1 variant: 8 runnable, 1 host-review, 1 compile-only | registered FS-1 coverage is complete for Windows x86-64 |
| `w025` | 4 EXEs, 3 DLLs, 3 managed, 2 gates | 7 exact / 5 typed | 8 target-runnable, 1 host-review, 3 compile-only | registered Windows x86-64 coverage is complete |
| Total | 22 EXEs, 10 DLLs, 47 managed, 12 gates | 27 exact / 64 typed | product: 61 target-runnable, 6 host-review, 24 compile-only | Windows applies 89 declarations; Linux x86-64 applies seven |

The shared registry now references zero source files from historical
verification directories. All 91 declarations own canonical source under
`tests/cases/` or a shell-free runner under `tests/support/`; all 29 native
source cases and all 48 Java sources have adjacent results, and shared stage
analysis remains under `tests/stages/`. The old verification tree now contains
zero Java or native source files, zero shell scripts, zero PowerShell scripts,
and 17 Python scripts. Python checkers
and reviewers may remain, but the unified frontend must invoke them through a
declared stage instead of a phase-local product build.

### Test applicability and target-architecture coverage

Test applicability belongs to each probe or behavioral test, not to its stage.
A stage is only a virtual grouping. Tests in one stage may have different
platform, target-architecture, capability, and execution requirements.

For this build, ARM64EC is modeled as the distinct target-architecture token
`arm64ec`, not as ordinary `aarch64` plus a GNU/MSVC-level switch. This is a
deliberate build-system distinction: ARM64EC changes compiler predefined
macros, source and assembly eligibility, calling conventions, PE imports and
exports, unwind data, and the tests that are meaningful. A separate derived
`base_isa=aarch64` may be used only by code generation proven to be shared with
ordinary AArch64. It must not drive general source or test selection.

The three identity fields are closed enums. The following values are all
possible choices; adding another value requires an explicit design and registry
change:

| Field | Complete enum |
|---|---|
| `target_platform` | `linux`, `windows`, `wasi` |
| `target_arch` | `x86`, `x86_64`, `armv7`, `aarch64`, `riscv64`, `arm64ec`, `wasm32`, `wasm64` |
| `target_abi` | `gnu`, `msvc`, `wasi` |

`base_isa` is derived metadata, not a fourth user-selectable identity enum. It
equals `target_arch` except that `arm64ec` derives `aarch64`; consumers must
still opt in before using that relationship. Aliases such as `x64`, `amd64`,
`arm64`, `arm`, `win32`, `unix`, `posix`, `mingw`, and every MIPS spelling are
not enum values.

The theoretical target platform/architecture/ABI sets are:

| Target platform | Target architectures | Target ABIs | Explicitly absent |
|---|---|---|---|
| `windows` | `x86`, `x86_64`, `armv7`, `aarch64`, `arm64ec` | `gnu`, `msvc` | RISC-V64 is not currently planned for Windows |
| `linux` | `x86`, `x86_64`, `armv7`, `aarch64`, `riscv64` | `gnu` | ARM64EC is Windows-only |
| `wasi` | `wasm32`, `wasm64` | `wasi` | native ART contracts are capability-blocked |
| All | no additional architecture values | no additional ABI values | no MIPS platform/architecture/ABI profile exists |

This yields exactly 17 theoretical identity triples: five Linux GNU, ten
Windows GNU/MSVC, and two WASI. These are all possible target choices in this
design. A known identity may remain planned or capability-blocked; identity
enumeration is not a support claim. Every other Cartesian-product combination
is invalid and must be rejected before graph generation.

`target_abi` is the canonical name for the `gnu`, `msvc`, or `wasi` contract.
The platform, `target_arch`, and `target_abi` triple identifies the exact
profile relevant to source and test selection. Details such as the compiler
target triple, object format, calling convention, and C runtime remain
immutable profile facts. `target_abi` does not replace `target_arch`:
`windows-arm64ec-gnu` and `windows-arm64ec-msvc` both remain ARM64EC builds,
distinct from `windows-aarch64-gnu` and `windows-aarch64-msvc`.

The theoretical Windows GNU profiles are representable but capability-blocked
under the current product contract, which forbids MinGW and clang-mingw
toolchains. A future decision to admit such a profile must define its official
headers, CRT/import libraries, Clang target triple, and runtime gates without
making MSYS2, Cygwin, or any POSIX environment a build-host prerequisite.

#### Current probe-by-probe selector audit

`tests/CMakeLists.txt` now declares every probe through the common
`art_add_target_probe` API. There is no platform-level early return and no
`ARCH any` spelling. Eleven Microsoft x86-64-specific probes use the exact
`windows-x86_64-msvc` target ID. The other twenty-one use the explicit typed
intersection `PLATFORMS windows`, `TARGET_ARCHES x86_64`, and
`TARGET_ABIS msvc`. Both forms currently select the same one verified target;
the distinction preserves which probes are intrinsically exact-ABI tests and
which are candidates for reviewed expansion.

| Stage | Typed `windows`/`x86_64`/`msvc` probes | Exact `windows-x86_64-msvc` probes | Portable-source candidates |
|---|---|---|---|
| `w002` | `w002attachprobe` | `win32_osr_unwind_probe` | none |
| `w003` | `criticalnativeprobe`, `nativeabiprobe`, `w003frameprobe` | `w003xmmsentinel` | `criticalnativeprobe`, `nativeabiprobe` |
| `w004` | `win32_art_embedding_probe`, `jvmtiforceprobe`, `windows_crypto_sha_probe` | none | none |
| `w010` | `win32_uef_probe`, `win32_fault_record_probe`, `win32_debugger_probe` | `win32_sigchain_probe` | none |
| `w013` | `windows_socket_fd_registry_probe`, `windows_x64_w013_mem_map_probe`, `windows_x64_w013_mspace_owner_probe` | `windows_x64_w013_dlmalloc_config_probe` | none |
| `w014` | `windows_x64_pthread_once_probe`, `win32_thread_stack_probe`, `win32_stack_growth_rx_probe`, `win32_cet_policy_probe`, `fs1stackhighwater` | `win32_stack_page_probe`, `win32_stack_growth_probe`, `win32_stack_pregrow_probe` | none |
| `w025` | `w025jitmappingprobe`, `windows_x64_w025_section_policy_probe`, `windows_x64_w025_policy_launcher` | `win32_jit_unwind_info_probe`, `win32_jit_unwind_registry_probe`, `jitunwindlifecycleprobe`, `w025jitlifecyclestressprobe` | none |

The eleven exact-ID entries inspect or depend on Microsoft x86-64 calling,
register, stack, PE unwind, or handwritten assembly behavior. They are not
applicable to `arm64ec` or a Windows GNU profile. The ability of a Windows
ARM64 or ARM64EC machine to execute an x86-64 program through emulation would
not turn that program into an ARM64EC ABI test.

The other twenty-one typed entries use Windows APIs or Windows ART contracts but
are not proven for another Windows architecture or ABI. They remain unreviewed
port candidates for Windows AArch64 and ARM64EC. Each must compile and pass its
own native runtime or result-review gate before another exact selector value is
added. Windows x86 and ARMv7 remain valid registry identities but are explicitly
outside the implementation roadmap. Names containing `windows_x64` must be
renamed if their audited contract proves architecture-independent.

Only `criticalnativeprobe` and `nativeabiprobe` currently use
platform-neutral JNI/C scalar sources and are credible common Linux/Windows
candidates. They are especially useful as per-target calling-convention
tests, but source portability is not a support claim. Their CMake ownership,
library naming/options, managed runners, 32-bit expectations, and result
expectations must become target-resolved and pass separately for every exact
platform/target-architecture combination declared.

Current evidence remains much narrower than theoretical applicability:

- all 32 native probes have compile evidence for the
  `windows-x86_64-msvc` target, including native Stage-8 evidence for the
  newest dlmalloc probe;
- all 17 native executables declared as runnable CTest gates have native
  `windows-x86_64-msvc` runtime evidence across the accepted W-002, W-004,
  W-010, W-013, and W-014 slices;
- the Linux x86-64 W-004 slice has five runnable managed/command gates, but no
  native-probe portability claim; and
- no probe has build or runtime evidence for Windows x86, ARMv7, AArch64, or
  ARM64EC.

#### Required registry semantics

The implemented common declaration states `PLATFORMS`, `TARGET_ARCHES`,
`TARGET_ABIS`, `TARGET_IDS`, `CAPABILITIES`, and `EXECUTION`. A target is
applicable only when all specified selectors match its serialized profile.
`TARGET_IDS` is the narrow override for tests such as the Windows x86-64 MSVC
unwind probes; applicability is never inferred from the build-host
architecture.

The registry and generated test manifest must record three separate states for
every exact target:

1. `applicable`: the declared selectors match;
2. `build-verified`: the probe and all managed assets compiled for that target;
3. `runtime-verified`: the behavioral command and required reviewer passed on
   an authoritative runner.

An applicable test is not automatically verified. A non-applicable test is an
explicit skip with its failed selector recorded, not a silent disappearance.
A requested stage with zero applicable tests must report that fact distinctly
from a stage whose applicable tests were expected but not built or run.

The profile registry now uses the closed `target_platform`, `target_arch`, and
`target_abi` enums and contains all 17 canonical identities. The ARM64EC family
uses
`target_platform=windows, target_arch=arm64ec, base_isa=aarch64` plus an
independent `target_abi`, yielding exact `windows-arm64ec-gnu` and
`windows-arm64ec-msvc` profiles. The registry also contains capability-blocked
Windows ARMv7 GNU/MSVC identities. Transitional unsuffixed target IDs are
rejected with migration diagnostics and do not enter generated profiles or
output paths.

### Test source, artifact, and result ownership

`tools/verify` combines five different roles: reusable test source, alternate
product build graphs, host runners/reviewers, generated artifacts, and
historical evidence. It must not be renamed wholesale. The useful pieces move
by role into a top-level `tests/` tree; obsolete product graphs and shell-only
orchestration are removed only after their behavior is owned by the unified
frontend.

The target layout is:

```text
tests/
  README.md
  CMakeLists.txt
  catalog.py
  native/
    <logical-test-id>/
      probe.c or probe.cc
      <architecture-specific source when required>
  java/
    <logical-test-id>/
  host/
    <Python runner or result reviewer>
  fixtures/
    <logical-test-id>/
  records/
    <target-id>/
      <record-id>/
        RESULT.md
        manifest.json
```

Physical source directories describe the stable behavior being tested, not the
historical phase, current target architecture, or temporary bring-up status.
Do not create `tests/windows_arm64_phaseX`, `tests/windows_x64_phaseX`, or
`tests/quick`. Stage membership remains virtual metadata such as `w014`, and
one stage remains one CMake group such as `art-test-stage-w014`.

#### Native probe reuse and linkage

A Windows AArch64 bring-up probe initially uses the exact canonical selector
`windows-aarch64-msvc`. Source portability does not automatically broaden test
applicability. The selector may expand only after the source, build result,
runtime behavior, and reviewer have been validated for each added target.
Windows ARM64EC remains the separate `arm64ec` target architecture and never
inherits AArch64 applicability implicitly.

Reuse one physical source file without copying or linking it when the same
C/C++ code and acceptance rule apply to x86-64 and AArch64. When the assertion
is common but the implementation is architecture-specific, keep one logical
test and select adjacent variants such as `fault_x86_64.S` and
`fault_aarch64.S`. When the ABI assertion itself differs, use separate logical
test IDs. No test source, fixture, build tree, result, or package may depend on
a filesystem symlink or reparse point.

Linkage is explicit registry metadata rather than a directory convention:

| Linkage | Contract |
|---|---|
| `standalone` | link only the exact target SDK/system dependencies; do not acquire ART transitively |
| `art-dso` | link through the generated CMake target/import library for `art.dll` or `libart.so`, never a filesystem path |
| `jni-dso` | build a target DSO loaded by managed/JNI test code; direct ART linkage is not implied |

All three use the product's plain Clang GNU-style driver, target bundle, CMake,
Ninja, and target policy. An `art-dso` runtime probe executes against a staged
regular-file DSO closure, not against a build-host DLL search path.

#### Test catalog generation

The final target-neutral declaration belongs in `tests/catalog.py`. It records
the logical ID, virtual stage, output kind, linkage, common and per-architecture
sources, platform/architecture/ABI or exact-ID selectors, required
capabilities, and execution mode. The target-aware Python overlay resolves that
catalog and emits a small target-specific `generated/Tests.cmake`; the emitted
file refers to repository-root variables plus relative paths and contains no
machine absolute paths. A generated JSON manifest retains every declared test,
including non-applicable tests and the selector that excluded each one.

During migration, a thin checked-in `tests/CMakeLists.txt` may continue to own
the common target declaration API while declarations are transferred out of
the historical directories. It is migration scaffolding, not permission for a
second product graph.

#### Generated outputs and cross-run results

All ordinary build and execution state belongs below the canonical target and
build-type directory:

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

The path never contains `<host>-to-`; build-host identity is manifest metadata.
An ordinary configure, build, test, import, or review command must not modify a
tracked file. A cross-runner package is created under `out/.../packages`,
contains no links/reparse points, is returned into `out/.../results`, and stays
outside VCS.

Generated and returned files with binary or archive types such as `.zip`,
`.exe`, `.dll`, `.lib`, `.pdb`, `.dmp`, `.jar`, `.dex`, and native object or
library formats must not be added to the product repository. Small accepted
text logs may be retained only when they add diagnostic value; otherwise the
tracked record stores hashes and the accepted conclusion. The pinned
`vendor/r8/r8.jar` D8/R8 tool is the sole named exception and must not become a
general `vendor/` or `*.jar` exemption.

#### Tracked acceptance records

`RESULT.md` does not live beside reusable source because one source may have
different results for several exact targets. An accepted stage or milestone is
recorded at:

```text
tests/records/<target-id>/<record-id>/RESULT.md
```

For example, x86-64 and AArch64 results for the same virtual stage are separate
records:

```text
tests/records/windows-x86_64-msvc/w014/RESULT.md
tests/records/windows-aarch64-msvc/w014/RESULT.md
```

The record states the target ID, product commit, toolchain identity, portable
build/run commands, applicable tests and explicit skips, separate build/run/
review status, authoritative runner, stable artifact/result hashes, known
limitations, and an acceptance time in `yyyy-MM-dd HH:mm:ss` form. It contains
no workstation absolute path, environment dump, executable, DLL, archive, or
crash dump. Promotion from `out/.../results` to a tracked record is explicit
and reviewed; normal test execution never performs it.

#### Migration classification

| Current `tools/verify` content | Destination or disposition |
|---|---|
| reusable C/C++/assembly source | owning `tests/cases/<logical-test-id>/` |
| managed Java source | same logical case as its native/behavioral contract |
| maintained test-specific Python runner/reviewer | same logical case |
| shared Python test framework | `tests/support/` |
| intentional static input | `tests/fixtures/<logical-test-id>/` |
| accepted target-specific summary | `tests/records/<target-id>/<record-id>/` |
| shell/PowerShell runner | replace with Python, then remove |
| Phase-0/Phase-1 or per-probe product CMake graph | remove after unified ownership; do not relocate |
| generated source, binary, log bundle, dump, or package | regenerate below `out/`; never track |
| obsolete progress narrative | move selectively to `docs/history/` or remove |

### Fresh Linux/Windows topology comparison

`libart-compiler` is shared on both targets, but full module-kind equality is
not yet achieved:

| Module | Linux | Windows | Required disposition |
|---|---|---|---|
| `libartbase` | shared | static | convert or document exception |
| `libdexfile` | shared | static | convert or document exception |
| `libprofile` | shared | static | convert or document exception |
| `libunwindstack` | shared | static | convert or document exception |
| `libicuuc_stubdata` | static | shared | convert or document exception |
| compiler tool component | `libart-dex2oat` | `libdex2oat_static` | reconcile capability/topology |
| signal-chain component | generated `libsigchain` | handwritten Windows `sigchain` | record the platform mapping and validate ABI |
| native-helper compatibility | none | `libnativehelper_compat_libc++` | record or remove compatibility exception |

The next topology gate must compare fresh manifests mechanically and fail on
an unreviewed module-set or kind change.

### Prioritized work queue

#### P0: make `test` and runtime packaging truthful

- [x] Replace the Windows-only `ARCH any` probe API with typed `PLATFORMS`,
  `TARGET_ARCHES`, `TARGET_ABIS`, `TARGET_IDS`, `CAPABILITIES`, and `EXECUTION`
  selectors plus an applicability/build/runtime-status manifest.
- [x] Move the `criticalnativeprobe` and `nativeabiprobe` native/managed source,
  result, and CMake ownership into adjacent `tests/cases/` directories without
  copying or linking the sources.
- [ ] Make those two probes fully platform-resolved, then validate rather than
  assume their exact Linux and Windows target-architecture sets.
- [x] Add Linux CTest registrations for show-version, imageless Hello, GC
  stress, DSO loading, and compiler-DSO topology.
- [x] Replace shell-only base boot-JAR construction with a fail-fast Python stage
  using configured JDK/R8 paths and binary-directory-local outputs.
- [x] Stage pinned ICU data and the mandatory native bootstrap DSO closure in
  isolated managed-gate runtime roots without `/tmp` or shared cross-target
  state.
- [ ] Add boot images, security assets/cacerts, and complete runtime package
  staging to the frontend.
- [x] Convert Phase-3 Java and Phase-4 managed probe compilation/D8 packaging
  into declared CMake/Ninja custom commands implemented by Python helpers.
- [ ] Register behavioral commands and expected-result reviewers for every
  current stage; do not mark a compile-only DLL as a passed runtime gate.
- [ ] Run the newly unified stage set on the authoritative Windows Server 2025
  host and preserve sanitized evidence. W-004 and the complete runnable W-013
  stage are accepted; the remaining stage coverage is still pending as a
  complete-catalog run.

#### P1: complete parity and mechanical acceptance

- [ ] Resolve or explicitly approve every topology difference in the table
  above.
- [ ] Enforce the exact `art-compiler.dll` export allowlist, target
  architecture/object format, ASLR flags, imports, and absence of an
  `art.dll` -> `art-compiler.dll` reverse dependency.
- [ ] Validate the Linux compiler DSO and the complete staged import closure,
  not only the Windows compiler DLL.
- [ ] Make staging start from an empty frontend-owned directory or reject every
  stale entry, then scan the complete result for links/reparse points.
- [ ] Add generated-command audits for compiler drivers, link drivers, shell
  operators, POSIX utilities, host include/library leakage, and forbidden
  generators.
- [ ] Add in-repository CI for fresh Linux generation/build/test/stage and the
  provisioned Windows cross/native cells.

#### P2: remove migration scaffolding and harden orchestration

- [x] Remove `native/generate.sh` and its ignored
  `native/generated/dalvikvm.cmake` snapshot; no focused harness consumed them, the
  frontend-owned target-local graph is the only maintained product input, and
  VCS regression coverage prevents either compatibility path from returning.
- [x] Remove the Phase-0 product CMake graph, Bash generator, and generated
  source snapshots; retain its historical result record.
- [x] Remove the Phase-1 product CMake graph, move its historical result out of
  `tools/verify`, and relocate its reusable PE/source auditors to
  `tests/support/windows`.
- [x] Remove the unproducible libcore/ICU `sources.cmake`, alternative CMake
  graph, duplicate runtime source, raw-link stub builder, and shell package
  flow after the unified product and W-004 gates own their behavior.
- [x] Consolidate `overlay/port_policy.py` and
  `overlay/port_policy_windows.py` into common policy plus explicit target
  deltas behind `make_overlay(profile)`; both resolved policies remained
  exactly equal to their reviewed predecessors before the fixed files were
  deleted.
- [x] Move converter scan exclusions from global CLI behavior into typed
  target/product policy and serialize the resolved policy in each graph
  manifest.
- [x] Split the maintained product CMake into focused codegen, platform import,
  target-graph, compatibility, and test modules without creating
  target-specific product entry points. Artifact staging deliberately remains
  shell-free Python frontend policy in `tools/build_art.py`; it is not a CMake
  target-graph responsibility.
- [x] Strengthen the build fingerprint with the full serialized profile,
  generated graph digest, tool versions, and target-bundle identity rather
  than only paths and the target triple. Schema 2 also fingerprints the graph
  manifest and generated CMake profile, captures complete shell-free tool
  version output, hashes every regular target-binding file, and rejects
  link/reparse and non-regular binding entries.
- [x] Remove the redundant product-wide `-Wno-error` demotion after proving
  Layer 2 already strips upstream `-Werror` and complete Linux, Windows-cross,
  and native Windows rebuilds pass without it.
- [x] Remove the target-wide strict-primary-template-shadow demotion while
  retaining only the reviewed source-specific exceptions.
- [ ] Retire forced toolchain-drift preludes as vendored dependencies are
  updated or required compatibility becomes explicit per module/source.
- [ ] Prove a second identical build is a true Ninja no-op and that Blueprint,
  overlay, and codegen input changes rebuild only affected outputs.

#### P3: admit additional targets one at a time

- [ ] Remove the `<arch>ng` mterp assumption and select generated assembly from
  explicit profile metadata, including RISC-V's different naming.
- [ ] Remove fixed x86-64 triples, preludes, stack-gap definitions, CPU-feature
  sources, BoringSSL assembly, probe names, and object-inspection assumptions.
- [ ] Validate and admit Linux AArch64, x86, ARMv7, and RISC-V64 separately.
- [x] Migrate the ARM64EC identity from transitional
  `windows-aarch64-arm64ec/cpu_arch=aarch64` to
  distinct `windows-arm64ec-gnu` and `windows-arm64ec-msvc` profiles with
  `target_arch=arm64ec/base_isa=aarch64`; rename the profile fields from
  `os_or_runtime`/`cpu_arch`/`abi` to
  `target_platform`/`target_arch`/`target_abi`; and add the valid but deliberately
  unavailable Windows ARMv7 GNU/MSVC placeholders.
- [ ] Keep Windows x86 and ARMv7 GNU/MSVC identities as recognized placeholders
  that fail capability admission; do not place them on the implementation or
  CI roadmap without an explicit future decision.
- [ ] Validate the Windows x86-64, AArch64, and ARM64EC MSVC profiles as
  distinct targets; an `arch:any` test annotation alone is not port completion.
- [ ] Keep every Windows GNU profile capability-blocked under the current
  no-MinGW/clang-mingw contract unless a future decision explicitly replaces
  that constraint and supplies an official regular-file target bundle.
- [ ] Run native Windows ARM64 host tools for the Windows x86-64 cross cell and
  the Windows-to-Linux sysroot cell without x86-64 host-tool emulation.
- [ ] Keep WASI profiles as explicit capability failures until ART's DSO,
  executable-memory, fault, threading, and JIT contracts are redesigned.

### Legacy inventory blocking Phase 5 removal

The retained alternative build descriptions are concentrated in the checked-in
Linux graph and split overlay datasets. The eight early Linux
isolation/miniature graphs, both Windows Phase-0/Phase-1 graphs, and the
libcore/ICU alternative graph have been removed. The remaining descriptions
are not invoked by `tools/build_art.py`, but remain runnable and can drift.
Removal is blocked only by missing unified gate ownership, not by product graph
generation.

The repository also has no checked-in CI workflow. External or manual evidence
does not replace a repeatable in-repository acceptance entry point.

## Decision

ART should have one product build pipeline:

1. one `bp2cmake` graph evaluator and emitter;
2. one target-aware Python overlay factory;
3. one maintained CMake product entry point and one shared set of CMake
   modules;
4. one Python command-line frontend for generation, configuration, build,
   test, staging, and reproducibility checks;
5. CMake's single-configuration `Ninja` generator on Linux and Windows build
   hosts, for native and cross targets; and
6. the LLVM Clang GNU-style driver plus LLD for every compile and link.

The pipeline also has no project-authored shell logic or POSIX-environment
prerequisite. Source-control aliases are normalized to regular files, and all
compiler/tool inputs and product outputs are symlink-free on both build hosts.
Python, CMake, Ninja, and native host LLVM/JDK executables are the complete
host-tool contract. Linux is not allowed to hide a dependency that a stock
Windows 10 ARM64 host cannot satisfy.

The same logical CMake targets must be produced for Linux and Windows. Platform
differences are limited to source selection, ABI definitions, system libraries,
exports, target SDK/sysroot, and the platform-correct implementation of a
common security/property requirement.

```text
Android.bp + target profile + one Python overlay
                        |
                        v
                    bp2cmake
                        |
                        v
             out/<target-id>/<build-type>/generated/art_graph.cmake
                        |
                        v
              CMake -G Ninja -> build.ninja
                        |
                        v
         clang/clang++ -fuse-ld=lld -> target artifacts
```

### Implemented migration slice (2026-07-30)

The target registry, relocatable graph/profile generation, ignored local TOML
bindings, shell-free generated commands, and the Python `generate`,
`check-generated`, `configure`, `build`, `test`, and `stage` frontend commands
are now implemented. Linux x86-64 and Windows x86-64 use the same
`native/CMakeLists.txt` entry point with `-G Ninja`; Windows requires an
explicit regular-file target bundle and never searches host libraries. The
frontend rejects symlink/reparse-point configured paths and records a build-host
fingerprint before reusing a binary directory.

Target verification probes now have one shared registry at
[`tests/CMakeLists.txt`](tests/CMakeLists.txt). A historical
stage is exactly one virtual CMake target such as `art-test-stage-w002`; probe
targets declare typed platform, target-architecture, target-ABI, capability,
exact-ID, and execution selectors. The stage target is a build group, not a
second product graph. CMake writes `tests/art_test_catalog.json` with every
declaration, failed-selector reason, applicability, CTest registration, and
separate build/runtime verification status. All 32 compiled probes remain
truthfully limited to `windows-x86_64-msvc`; 24 are compile-only and eight are
target-runnable. Twelve `GATE` declarations avoid dummy binaries: two exact
`linux-x86_64-gnu` declarations check the runtime version marker and the
runtime/compiler ELF DSO topology; the Windows W-002, W-003, and W-004 host
reviews check source, target objects, PE imports/relocations, and incremental
assembly dependencies; one shared exact-ID W-013 declaration runs the managed
non-moving-heap artifact at 128 MiB on Linux and Windows; one Windows W-013
declaration runs it at 1024 MiB; one Windows W-013 host review checks source
policy; W-010 owns the private-boundary unwind review; W-025 owns its source/
PE review and twelve-process JIT control/workload matrix; and the FS-1 variant
owns its stack-sampling host review. Managed W-002
attach/OSR, W-003 CriticalNative/FastNative/XMM/frame, and W-004 JVMTI
declarations own their shell-free Python runtime commands without dummy gate
targets. The old phase directories remain temporary evidence locations while
their product graph ownership and shell runners are removed.

The Windows overlay now emits `art-compiler` as `SHARED` and links it to
`art` and `art-disassembler`, matching the Linux topology. The native entry
point injects the Windows runtime sources, sets the stable `art-compiler.dll`
name, passes bundle SDK/libc++ paths to Clang, and supplies a reviewed DEF
allowlist for its narrow public entry point. ART runtime globals used by the
compiler use `LIBART_PE_DATA` producer/consumer annotations, including regular
header overlays generated under the target's `gensrc` tree for declarations
that must remain out of the nested vendor checkout. PE data imports therefore
have the required indirection while `Thread::Current()` keeps TLS inside
`art.dll`. Direct runtime imports not covered by those source annotations use
the checked 187-entry `compat/art_runtime_consumer_exports.def`; it is a link
dependency of `art.dll`, so Ninja cannot leave a stale import library after an
allowlist change. A Linux-hosted `windows-x86_64-msvc` cross build now links the full
1825-action product graph, including `art.dll`, `art-compiler.dll`,
`art-dex2oat.dll`, both command-line executables, and the libcore DSOs. A
native Windows Server
2025 x86-64 build using LLVM 21.1.8, CMake 3.31.8, and Ninja 1.13.2 also
configures and links the same graph without a POSIX environment. The native
`w002` unwind test runs through the unified virtual stage, and the complete
catalog builds 22 executable probes and 10 probe DLLs. Loading staged
`art.dll` and `art-compiler.dll` and resolving `art_compiler_jit_create` pass
from a directory containing only the staged closure. A frontend-owned
`linux-x86_64-gnu` build produces `libart-compiler.so` with dynamic dependencies
on `libart.so` and `libart-disassembler.so`. Fresh Linux and Windows generation
loads the same Blueprint input set and uses the same converter. The resolved
Linux graph contains 34 generated modules and the Windows graph contains 33:
both emit `openjdkjvmti` as a separate DSO, while Linux emits `sigchain` and
Windows owns its platform `sigchain` target in the common native entry point.
`build_art.py stage` validates the Windows
DLL/import-library pair, copies the complete top-level DSO closure (including
the pinned Windows `c++.dll`), rejects links/reparse points, and records
regular-file hashes.

Windows source selection replaces Linux-only libcore backends with the
maintained Windows bridge sources for `javacore` and `openjdk`; the pinned
static Expat target propagates `XML_STATIC` to consumers. The generated PE
header overlays are force-included only into the defining and consuming
translation units. This keeps `vendor/art` clean, requires no source-tree
symlink, and avoids committing generated or absolute-path-bearing headers.

The test-ownership migration moves the registry from `native/` to the top-level
`tests/` tree and places all 91 declarations under stable logical ownership.
All 32 native probes and 47 managed artifacts consume canonical source under
`tests/cases/`; the common W-004 managed gates, Windows W-002/W-003 managed
commands, Linux command gates, and target-object reviewers use shell-free
Python under `tests/support/`. Each source case has an adjacent result, while the
W-003 cross-case analysis remains stage-owned without relocating source by
stage. The base boot JAR and probe JARs are ordinary target-local Ninja outputs
from configured JDK 21 and pinned D8. Remaining legacy per-probe CMake entry
points and shell runners temporarily reference canonical source; W-003, the
W-004 JVMTI case, and all Phase-3 libcore probes have retired these
compatibility paths. A portable VCS
audit rejects tracked product/test binaries and archives
while retaining the one named `vendor/r8/r8.jar` D8/R8 exception. The old Phase
3 returned ZIP is retained under ignored `out/` storage, and its tracked result
now records the package hash instead of committing the archive.

In particular, `art-compiler` is a shared library on both targets:

| Target | Required runtime artifact | Link-time artifact |
|---|---|---|
| Linux x86-64 | `libart-compiler.so` | the DSO itself |
| Windows x86-64 | `art-compiler.dll` | `art-compiler.lib` import library |

Windows must not silently substitute a static `art-compiler` when DLL exports
are incomplete. Missing exports are a port defect and must fail the build or an
ABI validation gate.

The following are deliberately unsupported:

- GCC or G++ as a compiler driver;
- MinGW, including `clang-mingw` toolchains and MinGW target triples/runtimes;
- `cl.exe`;
- `clang-cl.exe` and Clang's CL-style frontend;
- Makefile, NMake, Visual Studio, and Ninja Multi-Config CMake generators;
- Bash, `sh`, `ash`, WSL, MSYS2, Cygwin, or a POSIX utility layer as a build
  prerequisite;
- project build logic in `.sh`, `.bat`, `.cmd`, or PowerShell scripts;
- operating-system-resolved symbolic links, junctions, or other path aliases
  as compiler/tool inputs or product outputs; and
- invoking `ld.lld` or `lld-link` directly as a separate product link path.

LLD remains the linker. On a Windows target, plain `clang`/`clang++` may select
`lld-link` internally for PE/COFF, but CMake link rules must invoke the Clang
driver with GNU-style options and `-fuse-ld=lld`.

## Goals and non-goals

### Goals

- Make a build mean the same thing regardless of whether CMake and Clang run
  on Linux or Windows.
- Make the target platform/ABI explicit and independent of the build-host
  platform.
- Derive source/dependency graphs from `Android.bp`, then apply all intentional
  port policy through one reviewed Python overlay.
- Generate build-tree CMake deterministically; do not maintain generated
  product CMake snapshots by hand.
- Use CMake target properties rather than global flag strings wherever CMake
  has a semantic representation.
- Build the same DSO topology on Linux and Windows, including
  `art-compiler.dll`.
- Keep target code generation ABI-correct during cross compilation.
- Reject stale toolchain caches and accidental host-library discovery.
- Run directly on Windows 10 ARM64 with native Windows host tools and no WSL,
  Cygwin, POSIX shell, or Make installation.
- Use no symlink or Windows junction/reparse-point dependency on Linux or
  Windows.
- Make the product graph smaller and easier to audit without deleting useful
  Windows verification probes.

### Non-goals

- Translating every Soong feature or every module in the AOSP tree.
- Supporting Android/bionic as a target in this pipeline.
- Validating 32-bit or non-x86-64 targets in the initial migration. The design
  is multi-target from the start, but the first migration gates remain Linux
  x86-64 and Windows x86-64.
- Making Linux and PE/COFF command lines byte-for-byte identical.
- Replacing libc, the platform SDK, or all platform compatibility code.
- Completing Windows AOT/OAT generation or loading merely by producing
  `art-compiler.dll`.
- Redesigning ART's runtime/compiler ownership during the first unification
  pass.

## Build host and target are separate dimensions

The current tree sometimes uses "host" to mean both the machine running the
tools and an AOSP `host_supported` target. The new system must use unambiguous
terms:

- **build host**: the OS on which Python, CMake, Ninja, and Clang execute;
- **target**: the OS, architecture, ABI, SDK/sysroot, and runtime for the
  produced ART binaries; and
- **AOSP build kind**: this project selects ART's AOSP host variant even when
  it is cross-compiled. This is not the build-host OS.

The build-host OS must never choose `target.linux` or `target.windows` branches
from `Android.bp`. Only the target profile may do that.

### Required host/target matrix

| Build host | Target | Mode | Required target environment |
|---|---|---|---|
| Linux x86-64 | Linux x86-64 | native | explicit or validated native Linux SDK/sysroot |
| Linux x86-64 | Windows x86-64 | OS/ABI cross | Windows SDK/UCRT, MSVC-ABI libraries, libc++/compiler-rt as selected by the profile |
| Windows 10 ARM64 | Windows x86-64 | architecture cross | the same target ABI contract and an explicit Windows SDK |
| Windows 10 ARM64 | Linux x86-64 | OS/architecture cross | an explicit Linux sysroot; never libraries found from the Windows host |

All four cells use the same Python frontend, `bp2cmake`, overlay factory,
CMake source tree, target names, and Ninja build flow. A cell may be enabled in
CI only when its target SDK/sysroot is provisioned. In particular,
Windows-to-Linux must fail at configuration if no Linux sysroot was supplied;
falling back to host headers or libraries is forbidden.

Windows x86-64 can remain a compatible build-host variant, but it must not be
the only Windows CI coverage. Windows 10 ARM64 is the portability baseline:
Python, CMake, Ninja, Clang/LLVM, and the JDK run as native Windows ARM64 host
programs while Clang and javac produce the requested target artifacts. The
build never executes x86-64 target binaries during configure or generation.

## One maintained CMake implementation, one configured instance per target

All target families use the same maintained [`native/CMakeLists.txt`](native/CMakeLists.txt),
the same CMake modules, the same `bp2cmake` implementation, and the same Python
overlay factory. They do **not** share one configured CMake cache or one
universal generated module graph.

For each exact target, the frontend creates a separate:

- resolved target profile;
- target-selected `art_graph.cmake`;
- CMake binary directory and `CMakeCache.txt`;
- `build.ninja` graph; and
- generated-source, artifact, and staging tree.

Conceptually:

```text
one maintained CMake implementation
              |
              +-- linux-x86_64-gnu profile
              |     -> out/linux-x86_64-gnu/<type>/...
              +-- linux-aarch64-gnu profile
              |     -> out/linux-aarch64-gnu/<type>/...
              +-- windows-x86_64-msvc profile
              |     -> out/windows-x86_64-msvc/<type>/...
              +-- future profiles
                    -> one isolated configured instance each
```

The compiler target triple, pointer size, ABI, object format, SDK/sysroot,
selected assembly, and many compiler checks are fixed when CMake enables a
language. Reusing a binary directory for another target is therefore invalid,
even when only the CPU changes. A build directory has exactly one target
identity for its entire lifetime.

### What `bp2cmake` generates

`bp2cmake` plus the Python overlay should generate one **target-resolved**
`art_graph.cmake` per exact target. It should not generate one giant file that
contains the source lists for every target behind CMake `if()` branches.

Uniformity means that all graphs are produced by one evaluator, policy schema,
overlay composition model, and emitter, with the same logical CMake target
names and validated topology. It does not mean that Linux ARM64 and Windows
x86-64 graphs must be byte-for-byte identical. Their selected source files,
defines, system imports, assembly, exports, and security mappings necessarily
differ. Conversely, generation of the **same** target profile on different
build hosts must yield equivalent graph manifests.

The frontend should not expose a bag of independently editable `-D` switches
such as OS, CPU, bitness, ABI, triple, and object format. Those switches can
contradict one another. It accepts one canonical target ID, resolves and
validates the complete profile in Python, then gives CMake only the resolved
inputs, for example:

```text
cmake -S native -B out/linux-riscv64-gnu/RelWithDebInfo \
  -G Ninja \
  --toolchain native/cmake/toolchains/LLVM.cmake \
  -DART_PROFILE_FILE:FILEPATH=<absolute-path>/target_profile.cmake \
  -DART_GRAPH_FILE:FILEPATH=<absolute-path>/art_graph.cmake
```

The public frontend, rather than a user assembling that command, owns these
arguments. The same resolved profile is serialized as JSON for `bp2cmake` and
as a generated CMake data projection for the common LLVM toolchain and product
entry point. The CMake projection contains portable target semantics only; it
does not contain machine installation paths.

Generated `.cmake` files must remain simple and relocatable. In particular,
`art_graph.cmake` contains resolved target declarations, stable CMake root
variables, logical target names, and their relationships. It does not contain:

- absolute source, output, LLVM, JDK, SDK, sysroot, or dependency paths;
- build-host conditionals;
- target branches that Python has already resolved;
- shell commands or platform-specific path spelling; or
- repeated policy that belongs in a maintained CMake interface target.

The generated-file surface should be deliberately narrow:

- `target_profile.cmake` consists only of validated `set(ART_TARGET_... ...)`
  data with no filesystem bindings;
- `art_graph.cmake` uses declarative target/source/include/definition/option
  and logical dependency commands, plus calls to a small reviewed set of
  project codegen helpers; and
- generated files do not call `project()`, discover a toolchain or package,
  run `find_package()`, `execute_process()`, or `file(GLOB)`, define new
  functions/macros, perform staging/install work, or implement control-flow
  trees.

A representative emitted fragment is:

```cmake
add_library(art-compiler SHARED
  "${MDVM_SOURCE_ROOT}/art/compiler/driver/compiler_driver.cc"
  "${MDVM_GENSRC_ROOT}/art/asm/mterp/mterp_x86_64.S"
)
target_link_libraries(art-compiler PRIVATE art art-disassembler)
```

Machine-specific absolute roots are unavoidable when tools actually open an
SDK or source tree, but they are runtime bindings, not graph content. The
Python frontend passes them to CMake through a small internal cache interface;
they may appear in `CMakeCache.txt` and the build manifest, but never in an
emitted `.cmake` file. The generated files are therefore relocatable and the
same-target graph can be compared across build hosts.

### How CMake distinguishes targets

CMake has `if()`, `elseif()`, `else()`, functions, generator expressions, and
conditional `include()` support. The unified build uses them for small,
declared policy composition, not for target detection or duplicate module
graphs. A simplified shape is:

```cmake
include("${ART_PROFILE_FILE}")

if(ART_TARGET_PLATFORM STREQUAL "linux")
  include(PlatformLinux)
elseif(ART_TARGET_PLATFORM STREQUAL "windows")
  include(PlatformWindows)
elseif(ART_TARGET_PLATFORM STREQUAL "wasi")
  include(PlatformWasi)
else()
  message(FATAL_ERROR "Unsupported ART target: ${ART_TARGET_ID}")
endif()

include("${ART_GRAPH_FILE}")
```

The generated profile defines immutable, mutually validated values such as
`ART_TARGET_ID`, `ART_TARGET_PLATFORM`, `ART_TARGET_ARCH`,
`ART_TARGET_BASE_ISA`, `ART_TARGET_ABI`, and `ART_TARGET_OBJECT_FORMAT`.
`CMAKE_SYSTEM_NAME` and
`CMAKE_SYSTEM_PROCESSOR` must agree with them, but are not sufficiently precise
to be the registry key. `CMAKE_HOST_SYSTEM_NAME` describes the build host;
`CMAKE_SYSTEM_NAME` describes the target. Similarly, CMake's `WIN32` condition
describes a Windows **target**, while `CMAKE_HOST_WIN32` describes a Windows
build host. Product source selection must never use the latter.

Architecture-specific inputs should normally be selected by the Python
overlay before graph emission. CMake conditions remain appropriate for
platform linker-property mapping, artifact suffix behavior, imported target
SDK libraries, and a small number of CMake-native platform semantics. This
keeps `native/CMakeLists.txt` from becoming a nested OS-by-architecture-by-ABI
decision tree.

## Target identity and registry

A target cannot be represented safely by one architecture string. The
resolved target schema should include at least:

```text
target_id
target_platform
target_arch
base_isa
aosp_arch
target_abi
object_format
pointer_bits
endianness
target_triple
cmake_system_name
cmake_system_processor
capabilities
support_status
```

`target_platform` is the canonical target-system name for `linux`, `windows`,
and `wasi`. It is not named `target_os` because WASI is a system-interface and
runtime contract rather than a conventional operating system. It replaces the
former implementation's awkward `os_or_runtime` field.

`target_arch` is the canonical build-selection name for `x86`, `x86_64`,
`armv7`, `aarch64`, `riscv64`, `arm64ec`, `wasm32`, and `wasm64`. This field is
not named `cpu` because WebAssembly is not a physical CPU; it is not named
`isa` because ARM64EC changes contracts beyond the instruction set; and it is
not named `abi` because the other tokens describe more than calling convention
and object ABI. The `target_` prefix prevents confusion with the build-host
architecture.

`target_abi` is the canonical ABI-environment name. Its complete enum is
`gnu`, `msvc`, and `wasi`. It is separate from `target_arch`: selecting
`arm64ec` still controls ARM64EC macros and sources, while selecting `gnu` or
`msvc` chooses the ABI/CRT/import-library environment for that architecture.

For build selection, ARM64EC is the distinct `arm64ec` target-architecture
token because it materially changes compiler macros, sources, assembly
eligibility, calling conventions, PE metadata, and test applicability. Its
derived `base_isa=aarch64` records only the instruction-family relationship that
explicitly reviewed code generators may share. Generic source selection must
not collapse it into `aarch64` or treat it as merely a GNU/MSVC-level ABI
switch. Likewise, `wasm32` only describes a WebAssembly address width; it does
not say whether the runtime contract is WASI, a browser, or a custom embedding.
A WebAssembly target ID must include that runtime ABI.

Canonical target IDs use the grammar
`<target-platform>-<target-arch>-<target-abi>`. They are lowercase ASCII;
hyphens separate identity dimensions, while an underscore remains part of the
standard `x86_64` architecture token. The target platform comes first, so
WASI follows the same ordering as Linux and Windows.

The product frontend accepts registered canonical IDs, not informal
architecture aliases. In particular, use `x86_64`, not `x64`; `aarch64`, not
`arm64`; and `armv7`, not bare `arm`. This avoids one spelling acquiring
different meanings on different operating systems. The 17 canonical IDs below
are the complete theoretical registry; no other platform/architecture/ABI
combination is implicitly available:

| Canonical target ID | Target arch | Target ABI | Object format | Initial status |
|---|---|---|---|---|
| `linux-x86-gnu` | `x86` | GNU | ELF32 | `planned` |
| `linux-x86_64-gnu` | `x86_64` | GNU | ELF64 | `supported` after ID migration |
| `linux-armv7-gnu` | `armv7` | GNU EABI hard-float fixed by this profile | ELF32 | `planned` |
| `linux-aarch64-gnu` | `aarch64` | GNU | ELF64 | `planned` |
| `linux-riscv64-gnu` | `riscv64` | GNU | ELF64 | `planned` |
| `windows-x86-gnu` | `x86` | GNU | PE32 | valid `planned` placeholder; no near/far implementation commitment; also blocked by the no-MinGW contract |
| `windows-x86-msvc` | `x86` | MSVC | PE32 | valid `planned` placeholder; no near/far implementation commitment |
| `windows-x86_64-gnu` | `x86_64` | GNU | PE32+ | capability-blocked by the current no-MinGW contract |
| `windows-x86_64-msvc` | `x86_64` | MSVC | PE32+ | `experimental` after ID migration |
| `windows-armv7-gnu` | `armv7` | GNU | PE32 | valid `planned` placeholder; no near/far implementation commitment; also blocked by the no-MinGW contract |
| `windows-armv7-msvc` | `armv7` | MSVC | PE32 | valid `planned` placeholder; no near/far implementation commitment |
| `windows-aarch64-gnu` | `aarch64` | GNU | PE32+ | capability-blocked by the current no-MinGW contract |
| `windows-aarch64-msvc` | `aarch64` | MSVC | PE32+ | `planned` |
| `windows-arm64ec-gnu` | `arm64ec` (`base_isa=aarch64`) | GNU | PE32+ | capability-blocked by the current no-MinGW contract |
| `windows-arm64ec-msvc` | `arm64ec` (`base_isa=aarch64`) | MSVC | PE32+ | `planned` |
| `wasi-wasm32-wasi` | `wasm32` | WASI | WebAssembly | `impossible_under_current_art_contract` |
| `wasi-wasm64-wasi` | `wasm64` | WASI/Memory64 | WebAssembly | `impossible_under_current_art_contract` |

Windows x86-64 MSVC is the first parity target and is promoted to `supported`
only after the unified graph, DLL topology, and runtime acceptance gates pass.

Both Windows x86 profiles and both Windows ARMv7 profiles are valid canonical
registry choices, not spelling errors or aliases. They deliberately fail
generation through capability admission and carry no implementation expectation
for either the near or far roadmap. Their purpose is to keep target identity,
test applicability, and unsupported-target diagnostics complete. They must not
appear in build/CI matrices unless a future roadmap decision changes their
status.

Inputs such as `linux-x64`, `linux-arm`, `windows-aarch64-arm64ec`, bare
`windows-arm64ec`, `wasm64-wasi`, and underscore-separated whole IDs are
rejected with the canonical replacement in the diagnostic. The former
`linux-x86_64`, `windows-x86_64`, and `windows-aarch64-arm64ec` IDs now produce
migration diagnostics to `linux-x86_64-gnu`, `windows-x86_64-msvc`, and the
explicit `windows-arm64ec-{gnu,msvc}` profiles. Aliases do not enter the profile
registry, manifests, cache keys, or output paths. If a Linux ARM soft-float ABI
is ever required, it receives a distinct canonical profile rather than
changing the meaning of `linux-armv7-gnu`.

`target_arch` uses the canonical external tokens, including distinct `arm64ec`.
`base_isa` maps `arm64ec` to `aarch64` and otherwise normally equals
`target_arch`. A separate derived `aosp_arch` field translates to
Blueprint/Soong vocabulary: `aarch64` and explicitly compatible ARM64EC
selections map to `arm64`, while `armv7` maps to `arm`. The user-facing ID,
source/test selector, output directory, cache key, and manifest never collapse
back to the ambiguous AOSP or base-ISA token.

The supported native architecture universe is deliberately closed: Linux has
`x86`, `x86_64`, `armv7`, `aarch64`, and `riscv64`; Windows has `x86`,
`x86_64`, `armv7`, `aarch64`, and `arm64ec`. MIPS is not supported and must not
appear as a placeholder profile, fallback branch, or test selector.

Support state is machine-readable:

- `supported`: CI must configure, compile, link, inspect, and run the
  applicable product gates;
- `experimental`: generation/configuration may work, but it is not yet a
  product contract;
- `planned`: the schema entry exists, but configuration fails with a clear
  missing capability/toolchain/port reason; and
- `impossible_under_current_art_contract`: retained for architectural
  planning, but rejected before graph generation until ART's required runtime
  contracts are redesigned.

WASM profiles initially belong to the last category. Current ART assumes
threads, native virtual memory and executable mappings/JIT, signal/fault
handling, target assembly, dynamic loading, and native DSO semantics. The
overlay must not quietly turn `SHARED` targets into static libraries or disable
these contracts until something compiles. It should fail capability validation
and list the unresolved runtime contracts. A future WASI port can change the
status only after those semantics and the intended AOT/interpreter/JIT model
are explicitly designed.

## Current-state analysis

### Linux product path

The Linux path is the closest existing model for the desired architecture:

- [`tools/build_art.py`](tools/build_art.py) runs `bp2cmake` over the seven
  product roots and writes the resolved graph/profile only below the ignored,
  fingerprinted target output directory.
- [`native/CMakeLists.txt`](native/CMakeLists.txt) is the handwritten product
  shell. It supplies code generation, imported libraries, compatibility flags,
  staging, and the generated graph.
- The current Linux generated closure contains 34 modules and already emits
  `art-compiler` as `SHARED`.
- A fresh Linux conversion is checked against its target-local generated file
  and deterministic graph manifest.

The legacy Bash generator and ignored 3,672-line graph snapshot were removed
after all focused product harnesses stopped consuming them. The Python frontend owns
graph generation and passes a target-specific graph/profile to CMake. Linux
imports validated host libraries; Windows imports zlib, lz4, and expat only
from the explicit target bundle. Configure-time code generation is still
intentionally performed by Python before CMake emits the Ninja graph.

### Windows product and verification paths

The historical Windows phase files are no longer a product entry point:

- The retired Phase-0 Bash generator, product CMake entry point, generated
  foundational graph, and generated aconfig headers proved the first Windows
  `libartbase` link. They were deleted after the unified frontend subsumed the
  same graph; the adjacent historical result is retained as evidence only.
- The retired Phase-1 snapshot contained 17 generated modules but had no
  reproducing generator. Its CMake entry point mixed the product graph, target
  environment, compatibility injections, staging, and 23 probes. Both were
  deleted after the unified graph took ownership; reusable Python artifact
  auditors remain temporarily while packaging migration continues.
- The historical Phase-1 snapshot made `artbase`, `dexfile`, `profile`,
  `elffile`, and the compiler component static, folded compiler objects into
  `art.dll`, and did not emit a standalone `art-compiler.dll`. The active
  target-aware graph now emits `art-compiler` as a shared target.
- The retired `tools/verify/windows_x64_libcore_icu/sources.cmake` claimed to
  be automatically extracted, but the repository contained no matching
  extractor. Its CMake file imported Phase-1 artifacts rather than consuming
  targets from one graph. The stable bring-up evidence now lives in
  [`docs/history/windows_x64_libcore_icu_result.md`](docs/history/windows_x64_libcore_icu_result.md).

The present Windows linker command is nevertheless useful evidence: plain
`clang++ --target=x86_64-pc-windows-msvc ... -shared -fuse-ld=lld` already
links PE DLLs. The unified design should preserve this GNU-driver shape and
remove the surrounding special build path. The currently used external
`windows_x64-dev-env` toolchain already combines plain Clang, an explicit MSVC
ABI target, LLD, xwin-provisioned SDK files, libc++, and compiler-rt; the design
should make that contract reproducible rather than relying on one workstation
path.

The checked Windows build cache also demonstrates why build directories need
fingerprints. It records `Release`/`-O3`, while current reproduction text asks
for `RelWithDebInfo`/`-O2`, and contains paths from both the older
`win64-dev-env` and newer `windows_x64-dev-env`. A successful incremental link
from such a directory is not evidence of a reproducible configuration.

### Converter and overlay split

The converter has the intended three conceptual layers: parse/evaluate, apply
port policy, then emit CMake. [`overlay/art_port_policy.py`](overlay/art_port_policy.py)
is the single Layer-2 entry and composes exact common module/global policy with
an explicit Linux or Windows target delta behind `make_overlay(profile)`.
Linux and Windows still resolve to 38 and 31 reviewed module policies; their
serialized policy objects remained byte-for-byte equal across this migration.
The Windows delta keeps `libart-compiler` shared for `dex2oat`, like Linux,
while `libart` still absorbs the compiler sources needed by the runtime. The
converter's test/fuzz/benchmark/sample and duplicate top-level ART exclusions
now live in the typed, path-free product scan policy. The generic CLI defaults
to scanning everything and no longer accepts the old global `--exclude-top`
escape hatch.

### Current architecture assumptions

The vendored ART source has architecture implementations under
`runtime/arch`, compiler quick-JNI/utilities, and related compiler trees for
`arm`, `arm64`, `riscv64`, `x86`, and `x86_64`. Its mterp inputs use
`armng`, `arm64ng`, `x86ng`, and `x86_64ng`, but RISC-V uses `riscv64`
without the `ng` suffix. That source availability is evidence for the target
registry, not proof that this repository can build all five architectures.

The current conversion path remains materially x86-64-specific:

- [`tools/bp2cmake/bp2cmake/config.py`](tools/bp2cmake/bp2cmake/config.py)
  explicitly models x86-64, x86, ARM64, and ARM codegen sibling selection;
  other architecture values only fall through generic paths and are not a
  validated profile;
- [`tools/bp2cmake/bp2cmake/codegen.py`](tools/bp2cmake/bp2cmake/codegen.py)
  constructs the mterp directory as `<arch>ng`, which is wrong for RISC-V;
- the same code generator hard-codes `x86_64-pc-windows-msvc` and
  `mdvm_windows_x64_prelude.h` for target-layout assembly generation;
- both current overlays inject `mterp_x86_64.S` rather than a target-selected
  generated source;
- Linux BoringSSL policy injects a fixed set of x86-64 assembly files; and
- the Windows policy, compatibility prelude, verification graphs, and ABI
  checks are Windows x86-64-specific.

These are migration work items. A planned target must not be labeled
`supported` merely because `Config(arch=...)` accepts its spelling or an ART
source directory exists. Profile admission should check all required source,
codegen, dependency, ABI, linker, and runtime capabilities before CMake graph
generation.

### Code generation and Java staging

Python generation for aconfig, `operator_out`, mterp, and `asm_defines` is
already shared. It correctly recognizes that `asm_defines` is target-layout
sensitive: Windows and Linux produce different `Runtime` offsets. The Windows
entry point, however, reconstructs target include paths and definitions
manually.

The boot-jar scripts are not yet suitable as a common product stage:

- `tools/bootjar/build_windows_x64.sh` ignores `build.sh` failure with
  `|| true`;
- `build.sh` and `dex.sh` do not use fail-fast shell behavior; and
- every invocation reuses `/tmp/bootbuild`, allowing cross-build contamination.

Boot-jar work does not need to be folded into `bp2cmake`, but it should be an
ordinary, fail-fast stage owned by the same frontend and build directory.
Likewise, the Bash-only Linux generator and boot-jar entry points cannot be the
portable frontend for a native Windows build host.

### Symlink audit

The current checkout still contains upstream filesystem symlinks:

- 279 under `vendor/art`, including 277 test aliases;
- 14 under `vendor/logging`;
- four under other `vendor/external` trees;
- one each under `vendor/libbase`, `vendor/libprocinfo`, and
  `vendor/unwinding`;
The project-owned `vendor/fmtlib` and fdlibm aliases have been removed. Their
logical paths now use `vendor/external/fmtlib`, while one tracked regular
forwarding header provides the required fdlibm relative-include projection.

Some are broken because formatting metadata points at the absent AOSP
`build/soong` tree. None of the repository links is absolute or escapes the
repository. The current `build/` and staging trees contain no symlinks.

Most vendored links are outside the product closure. The maintained and legacy
CMake snapshots now address the canonical `vendor/external/fmtlib` path, and
`native/CMakeLists.txt` consumes the tracked regular-file projection under
`compat/openjdk_fdlibm`; it does not replace a Git symlink with an untracked
directory at the same path.

The current external `windows_x64-dev-env` path is also unsuitable: it contains
11 absolute symlinks back to the older `win64-dev-env`, including its SDK,
libraries, CRT, scripts, and CMake toolchain. The normal Linux
`/usr/bin/clang`, `/usr/bin/clang++`, and `/usr/bin/python3` names are symlink
aliases as well. A unified build must use real, canonical files/directories and
cannot rely on any of these aliases after tool discovery.

### POSIX-host assumptions

Residual repository utilities and historical instructions still assume a Unix
userland in several places, but the product path does not:

- source provisioning is launched by `tools/vendor-sync.sh`;
- boot-jar and staging flows use Bash arrays, `source`, pipelines, shell
  redirection, `/tmp`, `rm`, `cp`, `find`, `grep`, `stat`, `strings`, and
  `timeout`;
- documentation uses `$(nproc)` and environment-activation scripts; and
- generated `operator_out` CMake commands use shell `>` redirection instead of
  passing an output path to a process: 52 commands in the current Linux graph,
  45 in Windows Phase 1, and three in Windows Phase 0.

These are hard Windows 10 ARM64 blockers without WSL. Cygwin is not a fallback;
besides being outside the desired toolchain, an adequate Cygwin environment is
not available for this ARM64 baseline.

The reusable Python codegen layer is already mostly suitable: its `_run()`
helper uses an argument vector with `subprocess.run`, captures stdout itself,
and the mterp/header generators are Python. The unified emitter should route
all generation through that layer instead of reproducing shell syntax in
CMake.

## Required invariants

The unified implementation should enforce these conditions rather than merely
document them:

1. `CMAKE_GENERATOR` is exactly `Ninja`.
2. `CMAKE_C_COMPILER_ID` and `CMAKE_CXX_COMPILER_ID` are Clang, and the
   frontend variant is GNU-style rather than MSVC-style.
3. compiler executable basenames are `clang`/`clang++` or
   `clang.exe`/`clang++.exe`; aliases resolving to GCC, Clang-CL, or MinGW are
   rejected after canonical-path and `--version` inspection.
4. every C, C++, assembly, executable-link, and DSO-link rule is launched
   through the configured Clang driver.
5. every link selects LLD with `-fuse-ld=lld`; an internal `lld-link` process
   for PE is acceptable, but a direct `lld-link` CMake rule is not.
6. target triple, target platform, CMake system name, sysroot/SDK, runtime libraries,
   and `bp2cmake` target profile agree.
7. CMake never searches build-host include or library paths for a cross target.
8. generated CMake and generated sources live under the configured target's
   binary tree.
9. `RelWithDebInfo` with `-O2` is the default product configuration. Other
   product build types are rejected unless the frontend explicitly enables a
   developer configuration such as `Debug`.
10. no configure-time or generation-time check executes a target binary while
    cross-compiling.
11. the logical shared/static target topology is identical between Linux and
    Windows unless a reviewed manifest records a platform exception.
12. `art-compiler` is always a CMake `SHARED` target for every admitted native
    target with DSO capability. A target without that contract is rejected,
    not converted to a static compiler library.
13. no project-authored build step invokes or requires Bash, `sh`, `ash`, WSL,
    MSYS2, Cygwin, Make, or a POSIX command-line utility.
14. every project-owned Python subprocess is started with an argument vector
    and shell execution disabled; no emitted CMake command payload contains
    shell redirection, a pipe, command substitution, or command chaining.
15. Git symlink entries may exist in a source checkout as real links or
    `core.symlinks=false` plain files, but a manifest-driven source normalizer
    materializes any required alias as regular files before graph emission. No
    compiler/tool input, SDK/sysroot, binary-directory, generated, staging, or
    packaged-artifact path depends on an OS-resolved symlink, junction, or
    project-controlled reparse point.
16. Windows 10 ARM64 uses native ARM64 host Python, CMake, Ninja, LLVM, and JDK
    executables. Cross-target binaries are never host tools.
17. one CMake binary directory is permanently bound to one canonical target
    ID, target triple, ABI, object format, SDK/sysroot identity, and build type.
18. Python emits a separate, fully target-resolved `art_graph.cmake` for each
    exact target; a generated graph contains no unselected target branches.
19. generated `.cmake` files contain no machine-specific absolute paths. They
    address source/generated roots through stable CMake variables and
    dependencies through logical CMake target names.
20. generating the same target from different supported build hosts produces
    equivalent graph manifests; generating different targets is allowed to
    produce different source/options/import selections.
21. a `planned` or `impossible_under_current_art_contract` profile fails
    capability validation before CMake rather than degrading DSO topology,
    disabling runtime contracts silently, or compiling host fallbacks.
22. canonical target IDs follow
    `<target-platform>-<target-arch>-<target-abi>`;
    informal aliases such as `x64`, `arm`, and suffix-first WASI IDs are not
    accepted as profile identities.
23. the default binary directory is `out/<target-id>/<build-type>`. Build-host
    identity is a required manifest/cache fingerprint, not a path component;
    a host mismatch rejects cache reuse.
24. machine-local roots exist only in ignored `.art-build.local.toml`, explicit
    frontend/CI bindings, CMake cache state, and ignored manifests. They never
    enter Git or generated `.cmake` content.
25. project-created source aliases such as `vendor/fmtlib` are removed after
    canonical logical source mappings are live; the normalizer is not used to
    preserve avoidable project-owned symlinks.

## Proposed repository layout

The names are illustrative, but ownership boundaries are mandatory:

```text
CMakePresets.json                 optional common/CI convenience presets
native/
  CMakeLists.txt                 one product entry point
  cmake/
    Common.cmake                validation and common target policy
    Codegen.cmake               generated-source targets
    Dependencies.cmake          target dependency imports
    PlatformLinux.cmake         Linux semantic mappings
    PlatformWindows.cmake       Windows semantic mappings
    PlatformWasi.cmake          future WASI semantic mappings; gated
    Packaging.cmake             target-tree staging
    toolchains/
      LLVM.cmake                one target-profile-driven toolchain
overlay/
  art_port_policy.py            one target-aware overlay factory
tools/
  build_art.py                  one user/CI frontend
  target_profiles.py            canonical target registry and ID validation
  provision_target_bundle.py    regular SDK/runtime bundle provisioner
  path_audit.py                 symlink/reparse and Windows-name validation
  command_audit.py              shell/tool invocation validation
  bp2cmake/                     one evaluator and emitter
out/
  <target-id>/
    <build-type>/
      source_projection/
      generated/
        art_graph.cmake
        target_profile.cmake
        graph_manifest.json
        inputs.sha256
      gensrc/
      stage/
      CMakeCache.txt
      build.ninja
      build_manifest.json
```

Target SDK locations belong in frontend configuration, internal CMake cache
arguments, or machine-local configuration; they must not be embedded in
checked-in files or generated `.cmake` files.

## Machine-local configuration and absolute paths

Use one repository-root `.art-build.local.toml` for developer-machine path
bindings. It is ignored by Git and is never read by `bp2cmake`; only
`tools/build_art.py` reads it. TOML is preferable to `.env` because it has no
shell expansion/quoting contract, and preferable to `local.properties`
because Windows backslashes, types, and nested per-target values have
unambiguous standard parsing. The portable frontend may parse it with Python's
standard TOML parser.

The local schema may bind only machine facts such as:

- CMake, Ninja, LLVM, and JDK roots;
- an optional output root;
- SDK/sysroot or target-bundle roots keyed by canonical target ID; and
- optional target dependency package roots.

It cannot define target identity fields, module policy, compiler/linker flags,
source lists, or topology exceptions. Those remain reviewed repository data.
`tools/build_art.py init-local-config` should discover candidate tools, validate
them, and create the ignored file without overwriting an existing one. The
checked-in documentation describes keys but never contains a real developer
path or a filled machine-local example.

Binding precedence is explicit frontend argument, then a narrowly defined CI
process-environment variable, then local TOML. Process environment works on a
native Windows process; there is no `.env` loader or environment activation
script. Every resolved path is canonicalized, checked for symlink/reparse
components, and recorded in the ignored build manifest. The frontend then
passes required roots to CMake as cache bindings. It never copies their
absolute values into `target_profile.cmake` or `art_graph.cmake`.

`CMakeUserPresets.json` is also ignored to prevent an expert/debug CMake flow
from committing local paths, but it is not a second supported product
configuration source. Product builds use `.art-build.local.toml` plus the
Python frontend.

For a target environment such as the legacy environment named
`windows_x64-dev-env`, prefer one regular-file target bundle over an activation
environment or a collection of independent paths. The local TOML binds the
canonical `windows-x86_64-msvc` profile to that bundle root. A bundle-local manifest
uses only relative paths to its SDK, UCRT, import libraries, libc++, and
compiler-rt components and records their versions and hashes. The checked-in
target profile records the required bundle schema and component constraints,
but no installation location.

The provisioner must create a fresh ordinary directory tree and validate its
manifest. It must not turn the current symlink-based environment into a
supported bundle by silently following or copying its aliases. Host-native
LLVM executables remain a separate build-host binding when they are not part
of the bundle. This replaces environment activation with explicit structured
data and works identically from a native Windows process.

### Existing absolute-path migration

The current tracked tree contains 77 occurrences of one developer's absolute
agent-home prefix across 35 non-vendor files. Twelve are executable script or
CMake defaults; the remainder are mostly historical documentation and captured
evidence. This is migration debt, not an acceptable precedent for the unified
build.

Migrate it by ownership rather than blind text replacement:

1. active CMake and script defaults become required named frontend bindings;
   absence produces a configuration error instead of falling back to one
   developer's directory;
2. source/build/output paths become repository-relative paths or stable tokens
   such as `<repo-root>`, `<output-root>`, and `<windows-sdk-root>` in
   documentation;
3. evidence capture sanitizes machine roots to stable tokens before writing a
   tracked result, while manifests store relative artifact paths and content
   hashes;
4. existing tracked results are rewritten by the same deterministic sanitizer
   and reviewed so evidentiary meaning is retained; and
5. a presubmit path audit rejects newly staged machine-specific POSIX home,
   Windows user/profile, drive-root toolchain, and UNC-share configuration
   paths in build files, generated files, documentation, and evidence.

The audit must distinguish machine-local configuration from intentional
portable content. HTTPS URLs, linker options such as `/DYNAMICBASE`, and
runtime filesystem test cases such as a synthetic Windows drive path are not
toolchain bindings and must not be rewritten. Tests should generate temporary
absolute locations at runtime when the exact literal is not itself the
behavior under test.

## One profile, one graph generator, one overlay

### Profile model

`tools/build_art.py` should resolve a typed profile and pass the same profile to
both `bp2cmake` and CMake. At minimum it contains:

```text
build:
  build_host_os
  build_host_arch
  host_python
  host_cmake
  host_ninja
  host_llvm_root
  host_jdk
  sysroot_or_sdk
  build_type

target:
  target_id
  target_platform
  target_arch
  base_isa
  aosp_arch
  target_abi
  object_format
  pointer_bits
  endianness
  target_triple
  cmake_system_name
  cmake_system_processor
  aosp_build_kind = host
  cxx_runtime
  compiler_runtime
  capabilities
  support_status

product:
  root_modules
  source_roots
  source_alias_policy = materialize_regular_files
  managed_path_policy = reject_symlinks_and_reparse_aliases
  shell_policy = no_shell
```

The build-host fields control only executable suffixes, path handling, and
host-native tool discovery/validation. `target_platform`, `target_arch`,
`base_isa`, `target_abi`, and capabilities control Blueprint selects and target
policy. `target_arch`, not `base_isa`, is the default source, macro, and test
selector. The target graph for `windows-x86_64-msvc` must therefore be the
same whether generation runs on Linux x86-64 or Windows 10 ARM64.

The serialized profile should have separate `build_host` and `target`
sections. `bp2cmake` consumes only the target, AOSP-build-kind, source, and
policy projection. The graph digest excludes build-host paths and uses
normalized relative paths with `/` separators, while the outer build manifest
records the complete build-host/tool environment. This keeps a target graph
host-independent without losing provenance.

The generated `target_profile.cmake` is a portable projection of the `target`
section only. Host tool, source root, SDK, sysroot, and output locations are
bound by the frontend through CMake cache variables and recorded in the build
manifest; their absolute values are not emitted into either generated CMake
file.

The profile should replace independent `--os`, overlay filename, hand-entered
root-module lists, and CMake cache fragments. Command-line overrides may bind
machine paths or build type, but may not mutate individual target identity
fields. A different ABI/triple requires a different named target profile. The
fully resolved result is serialized into the build manifest.

### Overlay factory

Replace two top-level policy objects with one factory, conceptually:

```python
def make_overlay(target: TargetProfile) -> Overlay:
    policy = common_art_policy(target)
    policy.merge(target_platform_policy(target.target_platform, target))
    policy.merge(object_format_policy(target.object_format, target))
    policy.merge(abi_policy(target.target_abi, target))
    policy.merge(architecture_policy(target.target_arch, target))
    policy.merge(capability_policy(target.capabilities, target))
    return policy.validate()
```

This is one Python overlay module and one schema, composed as common policy,
target-platform policy, object-format/ABI policy, architecture policy, and
capability policy. It may contain clearly named policy sections, but modules
are declared once and refined by target. A module cannot have unrelated
definitions in separate files, and a new architecture must not require a copy
of the whole overlay.

The common portion owns:

- name mapping;
- root modules and closure policy;
- common module kinds;
- whole-static absorption rules;
- common warnings and ART behavioral definitions;
- generated-source declarations; and
- the expected DSO/static topology.

Target portions own only actual target differences:

- Blueprint target branch;
- OS source replacement;
- architecture-specific sources and generated assembly;
- target ABI definitions;
- pointer-width and object-format behavior;
- target system libraries;
- platform compatibility sources;
- linker security mappings; and
- DSO export policy.

The overlay validator should reject conflicting keys, duplicate target names,
an unknown module exception, or a platform override that changes a common
module kind without an explicit `topology_exception` reason. The hard-coded
test/fuzz/benchmark/sample exclusions should move from `bp2cmake.__main__` into
the product profile.

### Deterministic output

`bp2cmake` should write atomically and deterministically to
`out/<target-id>/<build-type>/generated/art_graph.cmake`. It
should also write a machine-readable graph manifest containing, for each
module:

- Blueprint name and CMake target name;
- module kind;
- normalized, sorted source list;
- public/private includes and definitions;
- generated sources;
- link dependencies; and
- each overlay rule that changed the normalized Blueprint module.

Paths in generated CMake use project CMake variables and normalized relative
suffixes rather than machine-specific absolute prefixes. The emitter rejects
an absolute path in every emitted source, include, library, tool, output, and
custom-command field. The input digest should cover all loaded
`Android.bp`/`sources.bp` files, source-root identities, generator source,
target profile, and overlay source without hashing build-host path spellings
into the target graph identity.

Generation needs two explicit modes:

- `--write`: atomically replace outputs whose content changed; and
- `--check`: generate in memory and fail if an output or manifest differs.

No generated product CMake snapshot should be committed after migration. CI's
`--check` gate proves that a configured build tree is current instead.

## One CMake entry point

`native/CMakeLists.txt` should be target-neutral. Its order should be:

1. load and validate the portable target profile already consumed by the
   common toolchain, plus the target dependency manifest;
2. validate the generator, single-config build type, compiler frontend, target
   triple, SDK/sysroot bindings, and LLD selection;
3. define common policy interface targets;
4. define generated-source commands/targets;
5. include the generated module graph;
6. attach the small number of compatibility sources or options that cannot be
   represented in the overlay;
7. validate the final target topology; and
8. define install/staging and tests.

CMake should not contain module source lists copied from Blueprint. Probe
programs should live under a test subtree and link the product targets. A probe
must not redefine or import a second copy of the product graph.

Avoid mutable global strings such as `CMAKE_CXX_FLAGS`. Toolchain files may set
the compiler target/sysroot initialization necessary for compiler discovery;
ordinary warnings, features, definitions, security options, and platform
libraries belong on CMake targets. Recommended common interface targets are:

```text
mdvm::compile_policy
mdvm::link_policy
mdvm::platform
mdvm::sanitizer_policy
```

Generated targets link the appropriate interfaces privately or publicly.
Source-specific workarounds remain source properties only when a target-level
policy is provably too broad.

## CMake frontend, optional presets, and Ninja

Do not check in a manually duplicated build-host-by-target preset Cartesian
product. With Linux x86, ARM, ARM64, RISC-V, several Windows ABIs, and possible
WASM profiles, that list would become configuration code by repetition.

`CMakePresets.json` may provide a hidden common Ninja/Clang base and a small
number of supported CI convenience presets. The authoritative matrix comes
from the Python target registry. `tools/build_art.py` detects the build-host ID,
resolves the requested target ID, and deterministically assigns:

```text
out/<target-id>/<build-type>/
```

The build host does not need to appear in this ignored path. Its OS,
architecture, executable formats, and tool fingerprints are recorded in the
build manifest and checked against `CMakeCache.txt` before reuse. Reopening a
binary directory from a different build host fails with a cache-recreation
diagnostic. Users who intentionally share one source checkout between hosts or
need simultaneous independently provisioned builds select another untracked
`--output-root`; the default target ID remains unchanged.

It then invokes the same maintained CMake entry point with `-G Ninja`, the
common LLVM toolchain, the generated target profile/graph paths, and the
machine-specific root bindings. It must not synthesize a Make, NMake, Visual
Studio, or Multi-Config fallback. The exact configure argument vector is
recorded in the build manifest so the dynamic frontend is no less auditable
than a static preset.

After the identity-field migration, the public command shape is identical on
both hosts:

```text
python tools/build_art.py configure --target-id windows-x86_64-msvc
python tools/build_art.py build --target-id windows-x86_64-msvc --cmake-target art-compiler
python tools/build_art.py test --target-id windows-x86_64-msvc
python tools/build_art.py stage --target-id windows-x86_64-msvc
python tools/build_art.py check-generated --target-id windows-x86_64-msvc
```

Only the operating system's Python executable spelling may differ. There
should be no `.sh` versus `.bat` product logic split.

The `configure` operation has one fixed sequence: resolve and validate the
profile, bind and audit machine-specific roots, run `bp2cmake --write`, invoke
CMake with the generated graph/profile paths, then write the build manifest.
Calling CMake directly is an expert/debug flow and requires an already checked
generated graph; it must not trigger a second, subtly different generator
implementation.

## POSIX-environment-free Windows 10 ARM64 host contract

The Windows host is a normal Win32 environment, not a Unix compatibility
environment. The required host executables are native Windows ARM64 builds of:

- Python 3.11 or newer, including the standard TOML parser;
- CMake;
- Ninja;
- Clang/LLVM, including the LLVM inspection/archive tools; and
- a JDK when the boot jar is requested.

The Clang host executable architecture and its output target are independent.
For example, ARM64 `clang++.exe` runs on Windows 10 ARM64 with
`--target=x86_64-pc-windows-msvc` to produce `art-compiler.dll`. The matching
target SDK contains headers and libraries, not helper executables that the
build tries to run. The same separation applies to Windows-to-Linux builds.

All orchestration belongs in Python using `pathlib`, `shutil`, hashing/archive
libraries, and `subprocess.run(argv, shell=False, check=True)`. Resolve and
validate `sys.executable` once, then use the recorded final regular executable
for child Python processes rather than a symlink spelling. Timeouts use the
subprocess API; file copies, removals, scans, and byte searches use Python or
CMake built-ins. No project logic may depend on command parsing by `cmd.exe` or
PowerShell either.

CMake custom commands must pass one executable and an argument list with
`VERBATIM`. They may invoke portable `cmake -E` operations or Python helpers.
They must not contain:

- `>`, `<`, `|`, `&&`, `||`, backticks, or command substitution;
- Unix tools such as `cp`, `rm`, `mkdir`, `find`, `grep`, `sed`, `awk`,
  `stat`, `file`, `strings`, `readlink`, or `timeout`;
- environment activation through `source` or an `.sh` file;
- `/tmp`, `~`, `$HOME`, or POSIX-only path construction; or
- executable-bit or shebang assumptions for Python scripts.

`operator_out` is a concrete required fix: the emitter must call the existing
Python codegen wrapper with an explicit output argument. The wrapper captures
the upstream script's stdout and atomically writes the file; generated CMake
must not emit `python ... > output.cc`.

Use response files for long compiler, linker, javac, and D8 argument lists.
The frontend should choose a short per-build output root and validate Windows
path legality, case-fold collisions, reserved device names, trailing spaces or
dots, and configured long-path support before CMake runs. These checks apply on
Linux too so a Linux-generated graph cannot contain names that fail only on
Windows.

CI must configure and build from a stock Windows process environment with
WSL, Cygwin, MSYS2, Bash, Make, and Unix utilities absent from `PATH`. Merely
running a Python wrapper from Git Bash does not satisfy this gate. CMake may
use a native `cmd.exe /C` wrapper internally when implementing a Ninja custom
command or working directory; that implementation detail is allowed, but the
project command payload contains no batch logic or shell operators.

## LLVM toolchain contract

### Common contract

The one maintained LLVM toolchain module must configure from the resolved
target profile:

- a host-native Clang/LLVM installation, including Windows ARM64 executables
  on the Windows 10 ARM64 build host;
- `clang` for C and assembly-with-cpp;
- `clang++` for C++ and final C++ links;
- LLVM binutils (`llvm-ar`, `llvm-ranlib`, `llvm-nm`, `llvm-strip`, and related
  tools appropriate to the target);
- a target triple for every cross build and preferably every reproducible
  native build;
- the selected SDK/sysroot and only its include/library search roots; and
- LLD through the driver with `-fuse-ld=lld`.

The compiler ban applies to the driver and toolchain path, not to the target's
ABI name. `x86_64-pc-windows-msvc` is the required non-MinGW Windows ABI triple
even though neither MSVC's compiler nor Clang-CL is used.

C++ runtime selection must be explicit in the target profile. Windows can use
the already provisioned libc++/compiler-rt combination. Linux may retain a
validated target runtime initially or move to libc++ as a separately tested ABI
decision; it must not depend on whichever C++ runtime happens to be found on
the build host.

Toolchain configuration is data, not an activation script. The frontend or an
optional user preset passes regular-file roots for host LLVM and the target
SDK/sysroot.
`env.sh`, `source`, `cygpath`, registry-dependent `cl.exe` discovery, and
inherited Unix environment variables are not part of the contract.

### Representative driver commands

CMake remains responsible for the exact rule, but the audit-visible shape
should resemble:

```text
# Linux shared library
clang++ --target=x86_64-unknown-linux-gnu ... -fPIC -c compiler.cc
clang++ --target=x86_64-unknown-linux-gnu ... -shared -fuse-ld=lld \
  -o libart-compiler.so ...

# Windows shared library, from either build host
clang++.exe --target=x86_64-pc-windows-msvc ... -c compiler.cc
clang++.exe --target=x86_64-pc-windows-msvc ... -shared -fuse-ld=lld \
  -Wl,/implib:art-compiler.lib -o art-compiler.dll ...
```

On a Linux build host the Windows compiler executable normally has no `.exe`
suffix. That host spelling is not a separate toolchain design.

Assembly must also go through Clang. MASM, `ml.exe`, and `ml64.exe` are not
fallbacks. Target assembly syntax/source selection is an overlay concern.

## PIC, PIE, shared libraries, and command-line parity

The user's required command style is best expressed as equal CMake semantics
and equal Clang-driver usage. Literal ELF options are not all meaningful to a
PE linker.

| Intent | Common CMake representation | Linux/ELF result | Windows/PE result |
|---|---|---|---|
| Shared library | `add_library(name SHARED ...)` | Clang link with `-shared`, PIC objects | Clang link with `-shared`, PE DLL and import library |
| Relocatable DSO code | `POSITION_INDEPENDENT_CODE ON` | normally `-fPIC` | no literal ELF PIC flag is required; PE relocation rules apply |
| Relocatable executable | `POSITION_INDEPENDENT_CODE ON` plus `CheckPIESupported` where supported | normally `-fPIE` compile and `-pie` link | PE image with ASLR-compatible relocation data |
| ASLR/security | platform link-policy target | ELF PIE and project hardening | `/DYNAMICBASE` and `/HIGHENTROPYVA` through Clang's linker-option forwarding |

Thus `-shared` should visibly occur for both `libart-compiler.so` and
`art-compiler.dll`. Linux executables should visibly use `-fPIE` and `-pie`.
Windows executables must not be fed a meaningless ELF `-pie` merely to make logs
look alike; they must receive PE's equivalent dynamic-base/high-entropy policy
through the same GNU-style Clang driver. CMake's `LINKER:` option form should be
used so it chooses correct driver forwarding instead of a direct linker call.

This distinction is semantic parity, not an exception to unification.

## Target dependency resolution

Native `find_library()` calls are not sufficient for the matrix. Every target
profile should expose imported CMake targets for zlib, lz4, expat, libc++ or
other runtime libraries, and platform libraries. Imported targets carry target
include directories and target library files.

For cross profiles:

- set CMake root-path modes so programs are found on the build host while
  headers/packages/libraries are found only in the target sysroot;
- set `CMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY` where compiler checks
  would otherwise try to link or run an executable;
- prohibit unresolved absolute paths outside the repository, Clang root, and
  declared target SDK/sysroot; and
- never make a missing target dependency an empty interface library unless it
  is a reviewed, capability-gated absence with no referenced symbols.

The profile's dependency manifest, rather than build-host discovery, should
decide whether a library is built from AOSP source or imported from the target
SDK.

## Symlink-normalized path contract

Git symlink entries are allowed to exist in the source checkout. On Linux they
may be filesystem symlinks; with Git for Windows and `core.symlinks=false`, the
same entry may be an ordinary file whose content is only the relative target
name. The build must accept both representations and produce the same graph.
It must never pass either the link or the placeholder file to a compiler.

Before `bp2cmake` scans paths, the Python frontend loads a source-alias map from
the source manifest. The evaluator resolves logical paths through that map,
without asking the OS to follow a link. After dependency closure is known and
before CMake is emitted, the frontend normalizes every required source and
declared include tree. For each Git mode `120000` entry it:

1. reads the link target from version-control metadata rather than relying on
   host filesystem resolution;
2. rejects an absolute target, repository escape, cycle, type mismatch, or
   target missing from the pinned source manifest;
3. resolves chained aliases entirely within the manifest;
4. copies the required target file or the relevant declared include/source
   tree into the target binary directory's `source_projection` as ordinary
   files/directories,
   preserving the logical relative layout; and
5. records alias, target, file modes, and content hashes in the graph inputs.

The emitter references only the regular source projection or a canonical
source path whose components and reachable declared include tree passed the
non-link scan. Code generation, CMake, Ninja, Clang, javac, and packaging never
call `readlink`, follow a junction, or compile the small text placeholder
created by Git for Windows.

The source checkout may therefore retain upstream symlinks that are not in the
product closure. Broken formatting/test links outside the closure do not fail a
product build. If a required alias cannot be normalized, the frontend fails
during source validation with the owning module, alias, and expected target;
the failure cannot surface later as a compiler syntax/file-not-found error.

The maintained product uses canonical source locations and regular include
projections. Vendored ART test aliases outside the product closure remain
legacy evidence inputs and must be normalized before they become product
sources.

The product must not create, stage, or package a symlink. The same rule applies
to Windows directory junctions and other project-controlled name-surrogate
reparse points. Linux CI enforces the output/tool rule too; Linux's permissive
symlink behavior must not conceal a Windows failure.

The strict no-link scope includes every component of:

- the normalized source projection and generated include paths;
- Python, CMake, Ninja, Clang/LLVM, JDK, SDK, sysroot, and dependency paths;
- binary and generated-source directories;
- imported libraries and runtime staging inputs; and
- staged directories and archive entries.

The frontend inspects these managed path components without following them. On
POSIX it uses `lstat` semantics. On Windows it also checks reparse
attributes/tags so a junction is not mistaken for an ordinary directory.
Discovery may report a canonical real tool path, but the resolved profile and
all Ninja rules use the final regular file path. A user-supplied managed path
that still contains an alias fails before generation.

Git mode `120000` must be recorded for the root repository and every
participating submodule because `core.symlinks=false` can turn a symlink blob
into a regular text file containing only the target name. Filesystem inspection
alone would then miss the semantic link and a compiler could consume the
placeholder.

Source provisioning should move to a shell-free `tools/vendor_sync.py` that
writes a platform-neutral source manifest containing repository identities,
paths, modes, link payloads, and hashes. The build host reads that manifest
with Python and does not require a Git executable. The manifest is pinned and
checked in alongside the submodule/source lock. When a developer builds from a
live Git checkout and Git is available, an optional cross-check may
refresh/verify the manifest, but it is not part of the Windows host contract.
`bp2cmake` validates every source/include in the emitted closure against the
normalized projection, source manifest, and filesystem metadata.

The SDK/toolchain provisioner must unpack a real directory tree. The current
`windows_x64-dev-env` alias tree is rejected rather than dereferenced. Host
compiler discovery similarly records and invokes the actual LLVM executable,
not `/usr/bin/clang`-style symlink names.

Packaging performs a final non-following traversal. ZIP/JAR/TAR metadata that
encodes a symlink is rejected even if extraction on the current host would
materialize it. The build manifest records
`source_alias_policy: materialize_regular_files`,
`output_symlink_policy: reject`, and the path-audit digest.

## Host tools versus target generation

Every generator must be classified explicitly:

| Generator | Runs on build host | Uses target ABI | May execute target output |
|---|---:|---:|---:|
| aconfig Python stand-in | yes | no, except profile data | no |
| `operator_out` Python | yes | no | no |
| mterp Python | yes | target architecture selects inputs | no |
| `asm_defines` stage 1 | target Clang runs on host | yes | no; emits assembly with `-S` |
| `asm_defines` stage 2 | host Python | reads target assembly text | no |

`asm_defines` must use `CMAKE_CXX_COMPILER`, the same target triple, sysroot,
headers, definitions, language standard, and ABI-affecting options as ART. Its
output manifest should record those inputs. The Windows `0x328` versus Linux
`0x340` instrumentation-offset check is a useful target-specific assertion,
but it should be generated from/validated against the profile rather than
embedded in a Windows-only product harness.

Generated-source steps should be Ninja dependencies with declared `OUTPUT`,
`BYPRODUCTS`, `DEPENDS`, and `VERBATIM` behavior. The Python generator should
continue replacing files only when content changes. Configuration may generate
the CMake graph needed to create targets, but compilation-derived artifacts
such as `asm_defines.h` should be ordinary build graph outputs, not hidden
configure side effects.

Every generator accepts explicit input and output arguments. A generator that
only writes stdout upstream is called through the shared Python capture helper;
the CMake emitter never implements output capture with shell redirection.

If a future generator must compile and execute a helper, it needs a distinct
native host-tool target/build. It may not execute a cross-target program through
an implicit emulator during configuration.

## Shared/static topology

The graph manifest should carry the expected common topology. A practical
initial rule is:

| Logical role | Linux | Windows | Policy |
|---|---|---|---|
| Product/runtime components (`art`, `artbase`, `dexfile`, `profile`, `art-disassembler`) | shared where the Linux product graph exposes a DSO | same logical DSO | no Windows static fallback |
| Compiler (`art-compiler`) | `SHARED` | `SHARED` | mandatory parity |
| Dex2oat support (`art-dex2oat`) when enabled | `SHARED` | `SHARED` | availability may be capability-gated, kind may not drift |
| Final tools (`dalvikvm`, optional `dex2oat`) | executable | executable | same target names |
| Internal leaf aggregation with no ABI surface | static/object/interface | same logical role | platform exception requires manifest reason |
| Target SDK libraries | imported target | imported target | never copied into generated module source lists |

The migration should compare manifests rather than assume every current Linux
choice is ideal. The key rule is that a platform cannot change a logical DSO to
static just to bypass DLL export or dependency work.

## `art-compiler.dll` design

### Initial parity with the Linux graph

The current AOSP module is declared static because upstream aggregates compiler
and runtime pieces into `libart`. The Linux overlay already does two things:

1. absorbs compiler objects into `art`; and
2. emits a standalone shared `art-compiler` for compiler tools, linking it to
   `art` and `art-disassembler`.

The first Windows parity milestone should reproduce that same topology:

```text
art.dll
  contains the compiler objects required by the current libart aggregation

art-compiler.dll
  is a separate SHARED target built from the compiler module
  imports runtime symbols from art.dll
  exports the compiler API required by compiler tools
```

This compiles approximately 95 compiler translation units twice, as Linux
currently does. That cost is preferable to accidentally introducing a DSO
cycle during the unification migration. In particular, do not make `art.dll` import
`art-compiler.dll` while `art-compiler.dll` imports `art.dll`.

An object-library optimization is not automatically safe on Windows. The copy
inside `art.dll` and the copy inside `art-compiler.dll` can require different
`dllimport`/`dllexport` compilation contexts. Reusing one object set before the
symbol ownership model is proven can create invalid imports back into the DLL
being linked. Compile deduplication should therefore be a later, measured
refactor with an explicit no-cycle/ABI design.

### Export contract

`CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS` is useful for exploration but is not a
durable ABI contract. It can miss or mishandle data symbols and it exports
implementation details unpredictably as source lists change.

The preferred order is:

1. define narrow compiler API annotations that expand to default visibility on
   ELF and `__declspec(dllexport)`/`__declspec(dllimport)` on Windows;
2. set the building/importing definition per CMake target;
3. use reviewed `.def` files only for required symbols that cannot reasonably
   be annotated; and
4. have CI compare actual exports with a checked ABI allowlist.

The DLL target must have stable output properties so all hosts produce
`art-compiler.dll` plus `art-compiler.lib`. Compiler tools link the CMake target,
not a hard-coded file path. Runtime staging must place the DLL beside dependent
executables or in the declared product DLL directory.

The Windows ABI gate should use LLVM inspection tools to verify:

- the file is PE32+ x86-64;
- the import library exists and resolves a small link probe;
- required code and data exports are present;
- dependencies resolve from the staged product tree;
- no static `art-compiler` archive is used by `dex2oat` or another consumer;
  and
- loading/unloading the DLL does not rely on unresolved symbols supplied by a
  probe executable.

### Explicit `art.dll` PE export contract

`art.dll` itself must not use `WINDOWS_EXPORT_ALL_SYMBOLS`. PE permits at most
65,535 exported entries, and an unoptimized ART build exposes tens of thousands
of inline/template COMDAT implementation symbols when CMake scans every object.
The measured pre-refactor candidates were 80,318 in Debug and 17,112 in
RelWithDebInfo, so optimization level changed the accidental ABI and Debug did
not link.

The maintained boundary uses ART's source annotations plus one bounded
runtime-consumer DEF:

- while building `art.dll`, `EXPORT` is `__declspec(dllexport)`;
- consumers select `dllimport` through the existing `LIBART_PE_*` boundary;
- namespaces and enums use `ART_VISIBILITY_EXPORT`, which remains ELF
  visibility on non-Windows and is deliberately empty on PE;
- `Thread` is not a whole-class PE export because its `thread_local self_tls_`
  must remain DLL-private; only the required methods and static data are
  annotated; and
- optimized inline specializations that become DLL-owned have one explicit
  Windows translation-unit owner so Debug and RelWithDebInfo link identically;
  and
- `compat/art_runtime_consumer_exports.def` names the 187 decorated direct
  imports required by the current compiler, dex2oat, executable, and JVMTI
  consumers across both supported build types. It is explicitly tracked with
  CMake `LINK_DEPENDS`; it is not a generated whole-object export scan.

The current accepted counts are 2,065 Debug exports and 2,066 RelWithDebInfo
exports. The one-entry difference is reviewed optimization/configuration
surface, not a return to whole-object auto-export. Regression tests keep both
`art` and `art-compiler` outside the generic CMake auto-export loop, exercise
operator-out parsing of `ART_VISIBILITY_EXPORT`, enforce the unique 187-entry
runtime-consumer boundary and its incremental link dependency, and ensure
`Thread::self_tls_` remains unannotated.

### Longer-term topology optimization

After parity, measure the duplicate compiler compile/link cost and map symbol
ownership. A cleaner runtime-only `art` plus `art-compiler -> art` topology may
be possible, but only if all runtime-to-compiler edges are removed or inverted
without a cycle and both JIT and compiler entry points retain their required
ownership. That is a separate ART architecture change, not a build-script
cleanup.

## Build and source manifests

Each binary directory should contain a build manifest with at least:

- source revision and submodule revisions;
- resolved profile and graph/input digest;
- build host OS/architecture;
- canonical target ID, target platform, target architecture, base ISA, ABI,
  object format,
  pointer width, and triple;
- canonical Clang paths and `--version` output;
- host executable formats/architectures for Python, CMake, Ninja, LLVM, and the
  JDK;
- CMake and Ninja versions;
- LLD selection;
- SDK/sysroot identity and version/digest;
- C/C++ runtime selection;
- build type and effective optimization/debug policy;
- generated module topology digest;
- shell-free command-audit digest; and
- symlink/reparse-point audit policy and digest.

The frontend compares the manifest before every configure/build. A mismatch
must require a new binary directory or explicit cache recreation; it must not
quietly continue with stale values. Separate binary directories for every
matrix cell and build type prevent the mixed Windows environment observed in
the current cache.

For reproducibility, two clean generations from identical inputs must produce
byte-identical CMake and graph manifests. Two clean builds should compare
artifacts after accounting for explicitly documented non-deterministic fields
such as platform debug-path metadata; the first gate is deterministic graph and
command generation.

## Boot jar and staging

Replace the product role of the current shell chain with a host Python stage,
for example `tools/build_bootjar.py`, invoked by `build_art.py` and represented
as a Ninja custom target when part of the full product.

It should:

- use the target binary directory's `bootjar`, never shared `/tmp/bootbuild`
  state;
- treat javac and D8 failures as fatal;
- launch `javac`/`java` with argument vectors and response files, never a shell
  command string;
- use Python timeouts, file/archive APIs, and byte inspection instead of Unix
  utilities;
- declare the selected JDK, R8/D8, Java sources, aconfig inputs, and target
  profile in a manifest;
- write atomically; and
- stage into the target binary directory's `stage` without also copying to
  unrelated Linux and Windows directories.

The boot jar can remain logically shared when its bytecode is deliberately
multi-platform. Its producer and outputs still belong to one configured build
so a failed or partial invocation cannot contaminate another target build.

## Migration plan

### Phase 1: freeze and compare current graphs

- Add manifest output and `--check` mode to `bp2cmake`.
- Add Git-mode/filesystem symlink and Windows reparse-point audits.
- Add a tracked machine-path audit that distinguishes local configuration from
  URLs, linker syntax, and intentional runtime path tests.
- Add a generated-command scanner for shells, shell operators, POSIX utilities,
  and Make-family tools.
- Capture current Linux and Windows normalized module graphs.
- Classify every kind/source/dependency difference as common policy, a genuine
  target difference, a missing Windows port, or stale handwritten state.
- Add command audits for Ninja and the Clang GNU driver before changing target
  topology.

### Phase 2: introduce the unified profile and overlay factory

- Replace the two overlay entry points with `make_overlay(profile)`.
- Add the strict canonical target registry and the ignored
  `.art-build.local.toml` loader/generator.
- Move scan exclusions into typed product policy and record them in the graph
  manifest; moving the root-module set out of frontend constants remains.
- Make build-host and target fields distinct throughout evaluator, codegen, and
  emitter APIs.
- Generate both target graphs into isolated build directories and compare their
  topology manifests.
- Split build-host tool architecture from target architecture and provision a
  regular-file Windows ARM64 host-tool bundle.

### Phase 3: introduce one product CMake entry point

- Extract common policy, codegen, dependency imports, platform mappings, and
  staging into focused CMake modules.
- Configure all supported matrix cells through `tools/build_art.py`; optional
  CI presets may call the same frontend contract.
- Move Phase-1 probe executables to a test subtree that links the product graph.
- Remove product target/source duplication from verification CMake files.
- Replace shell redirection in emitted codegen rules with explicit Python
  output arguments.
- Replace fdlibm and fmtlib compatibility aliases with canonical paths and
  regular-file generation.
- Remove machine-specific defaults from active CMake/scripts and sanitize
  historical documentation/evidence to stable path tokens.
- Run the first POSIX-environment-free, symlink-normalized Windows 10 ARM64
  configure/build gate.

### Phase 4: finish Windows DSO topology parity

- [x] Change the Windows compiler policy from static to shared.
- [x] Implement the reviewed compiler DLL export entry point and DEF allowlist.
- [x] Produce and stage `art-compiler.dll` and its import library through the
  Python frontend.
- [x] Pass the native Windows x86-64 compiler DSO load/export smoke and unified
  `w002` runtime stage without Bash, Make, NMake, MSVC, GCC, or MinGW drivers.
- Convert other current Windows static substitutions to the common topology or
  record a temporary, owner/date-tagged exception.
- Prove that neither the runtime nor a tool introduces an `art`/`art-compiler`
  DLL dependency cycle.

### Phase 5: remove legacy product paths

After all acceptance gates pass, remove or demote the following as product
inputs:

- the now-retired `native/generate.sh` and ignored
  `native/generated/dalvikvm.cmake` compatibility path;
- the now-retired unproducible `windows_x64_libcore_icu/sources.cmake`
  snapshot and its standalone product/package flow;
- the now-merged `overlay/port_policy.py` and
  `overlay/port_policy_windows.py` fixed-policy datasets;
- build instructions or scripts that select Make, NMake, Visual Studio, or
  Ninja Multi-Config;
- shell-only boot-jar staging with ignored failures and shared `/tmp` output;
- all project-owned Git mode `120000` entries after canonical fmtlib/fdlibm
  paths are in service;
- environment-activation scripts and `.sh` product entry points; and
- the symlink-based `windows_x64-dev-env` alias tree from supported toolchain
  instructions.

Useful probes and result documents should remain. They become tests of the
unified product targets instead of alternative ways to build those targets.

### Phase 6: admit additional targets one at a time

- Keep registry entries for all planned targets, but enable each only after its
  profile capability gate is complete.
- Replace the `<arch>ng` mterp assumption with explicit architecture metadata
  and make generated assembly selection profile-driven.
- Remove the x86-64 triple, prelude, mterp, BoringSSL assembly, and verification
  assumptions identified in the current-state audit.
- Validate Linux AArch64, x86, ARMv7, and RISC-V64 independently; source-tree
  presence alone is not an admission gate.
- Treat Windows x86, x86-64, ARMv7, AArch64, and ARM64EC as separate
  target-architecture profiles with their own SDK, triple, source/macro
  selection, exports, object inspection, and runtime gates. ARM64EC uses
  `target_arch=arm64ec` and
  only derives `base_isa=aarch64` for explicitly shared code generation.
- Retain WASM profiles as explicit capability failures until a runtime/DSO/JIT
  contract is designed; do not introduce a static-library compatibility mode.

### Phase 7: optimize after parity

- Profile graph generation, configure time, duplicate compilation, link time,
  and incremental rebuilds.
- Remove duplicate compiler compilation only after DLL symbol ownership and
  no-cycle constraints are proven.
- Consolidate compatibility shims when Linux/Windows source differences can be
  expressed in upstream-shaped source selection.
- Consider a common LLVM C++ runtime only as an explicit ABI migration, not as
  an accidental side effect of host tool discovery.

## Acceptance gates

### Generation and configuration

- `bp2cmake` unit tests pass for every registry profile, including explicit
  expected capability rejection for planned/blocked profiles.
- Generating twice produces no diff and identical digests.
- Linux-host and Windows-host generation of the same target profile produces
  equivalent graph manifests.
- canonical ID tests recognize all 17 exact IDs enumerated above, including
  the deliberately unavailable Windows x86/ARMv7 placeholders; capability
  admission then rejects unavailable profiles with their recorded reason;
- canonical ID tests reject transitional suffix-less IDs,
  `windows-aarch64-arm64ec`, `x64`, bare `arm`, whole-ID underscore variants,
  suffix-first WASI names, unregistered cross-products, and every MIPS target;
- default outputs use `out/<target-id>/<build-type>` with no build-host path
  component, and opening that directory from a mismatched build host rejects
  the existing cache;
- every generated `.cmake` file is target-resolved, contains no unselected
  target branches, and passes an absolute-path rejection scan;
- each binary directory records exactly one canonical target identity and is
  rejected if target, ABI, triple, object format, SDK/sysroot, or build type is
  changed in place;
- every planned or contract-blocked profile fails before CMake with a
  capability-specific diagnostic rather than a substituted source or library
  kind;
- checkouts with real Git symlinks and with `core.symlinks=false` link-text
  files produce identical normalized source and graph digests for the product
  closure;
- every configured build reports exactly `Ninja`, one build type, Clang GNU
  frontend, the intended target triple, and LLD;
- forbidden tool/generator names do not occur in CMake caches or Ninja command
  rules;
- cross builds contain no undeclared build-host include or library path;
- `.art-build.local.toml` and `CMakeUserPresets.json` are ignored, no
  machine-specific absolute path appears in a tracked build/configuration
  input, and sanitized evidence contains only stable path tokens;
- neither the Git index, source manifest, generated graph, nor normalized
  closure contains the project-owned `vendor/fmtlib` alias after its canonical
  mapping migration;
- Windows 10 ARM64 configures using native ARM64 host tools from a stock Windows
  environment with no POSIX layer; and
- Git-mode and filesystem audits report no unnormalized symlink/reparse-point
  path in the emitted closure, toolchain, binary tree, or stage tree.

### Command-line audit

Audit `compile_commands.json` and `ninja -t commands` for every matrix cell:

- compile rules start with the configured plain Clang driver;
- C++ and final C++ links use `clang++`;
- shared-library links contain driver-level `-shared` and `-fuse-ld=lld`;
- Linux executable compile/link rules show the expected `-fPIE`/`-pie` result;
- Windows image rules show the required PE ASLR flags through the driver;
- no rule invokes GCC, G++, MinGW, Clang-CL, CL, Make, NMake, a Visual Studio
  tool, `ld.lld`, or `lld-link` directly;
- no rule invokes a POSIX shell or Unix utility; and
- no project-authored command payload contains redirection, pipes, chaining,
  or command substitution.

### Artifact and topology validation

- the common module-kind manifest matches across Linux and Windows except for
  reviewed exceptions;
- Linux produces and loads `libart-compiler.so`;
- Windows produces `art-compiler.dll` and `art-compiler.lib`, and a consumer
  links and loads through the import library;
- LLVM object inspection confirms the target file format, architecture,
  imports/exports, and PIE/ASLR properties;
- staged executables resolve only staged target DSOs plus approved platform
  libraries;
- the Windows product has no static compiler fallback or cyclic DLL imports;
- non-following scans find no symlink, junction/name-surrogate reparse point,
  or archive symlink entry in build and staged artifacts.
- the main Git index contains no generated binary or package/archive extension;
  `vendor/r8/r8.jar` is the sole exact-path exception and no wildcard binary
  exception is accepted by the VCS audit.

### Build and runtime validation

- clean `RelWithDebInfo` builds pass for each provisioned matrix cell;
- native Linux smoke tests pass;
- Windows x86-64 and other cross-built artifacts pass smoke tests only under an
  explicit target runner or emulation environment where provisioned; the
  Windows 10 ARM64 build gate does not depend on x86-64 emulation and no runner
  is used during configure;
- incremental no-op builds execute no compile/link/generation commands;
- changing an `Android.bp`, overlay rule, codegen input, or target ABI setting
  rebuilds exactly the affected graph/output;
- boot-jar failure stops the product build and cannot leave a successful-looking
  staged artifact;
- a Linux build with shell/POSIX tools deliberately removed from the frontend's
  `PATH` still generates and builds, proving both hosts use the same contract.

## Risks and controls

| Risk | Effect | Control |
|---|---|---|
| Build host leaks into target selection | wrong sources and ABI | one serialized profile; graph equivalence across hosts |
| One CMake cache is reused for another target | stale compiler checks, pointer size, ABI, or assembly | one immutable target identity and binary directory per target/build type |
| The same target cache is reopened on another build host | incompatible host tools/cache state despite a simple output path | build-host manifest fingerprint rejects reuse; optional separate output root |
| Informal target aliases drift | duplicate cache keys or ambiguous ABI | one strict canonical ID grammar and diagnostic-only migration suggestions |
| Local tool/SDK path is committed | workstation-specific build and information leak | ignored local TOML, staged-path audit, no local defaults in scripts/CMake |
| Generated graph embeds machine paths | graph differs by host and cannot relocate | stable root variables plus absolute-path rejection in the emitter |
| Giant generated graph retains inactive target branches | wrong source or policy leaks into the closure | Python emits one fully resolved graph per exact target |
| Project-owned fmtlib alias survives | Git-for-Windows link text reaches legacy graph | canonical `external/fmtlib` mapping, graph assertion, then delete mode `120000` entry |
| Cross build finds host headers/libs | links successfully but is invalid | sysroot-only root modes and path audit |
| Literal Linux flag reuse on Windows | ignored options or broken PE link | common semantic properties with platform mapping |
| Export-all hides an incomplete DLL ABI | unstable or missing imports/data | annotations/`.def` allowlist and ABI probe |
| Static fallback masks DLL defects | unequal products | topology validator makes `art-compiler SHARED` mandatory |
| Compiler DSO creates a cycle with `art` | loader/link failure | preserve current aggregate topology first; import graph gate |
| Object-library dedup uses wrong import/export context | invalid Windows objects | defer until symbol ownership is designed and tested |
| Configure executes target helper | cross build fails or uses emulator accidentally | classify host tools; compile target layout with `-S` only |
| Stale generated snapshot | unreviewed source/dependency drift | build-tree generation, digest, and `--check` |
| Stale CMake cache | wrong SDK, flags, or optimization | per-target binary directory and build fingerprint |
| Shared `/tmp` boot state | cross-target contamination | binary-directory-local atomic output |
| Linux follows a symlink while Windows stores its link text | compiler sees different or invalid input | manifest-driven alias resolution and identical regular-file projection |
| Toolchain/SDK path contains a junction or symlink | non-reproducible host-dependent toolchain | regular-file toolchain package and component-wise path validation |
| Ninja rule contains `>` or a Unix utility | Windows 10 ARM64 build failure | explicit Python output APIs and shell-free command scanner |
| x86-64 helper is run on Windows ARM64 | emulation dependency or configure failure | host-tool architecture validation; never execute target outputs |
| Case/path-length difference appears only on Windows | generation or compile failure | Windows legality/case-fold checks on every host and response files |

## Relationship to Windows AOT/OAT

[`win32_aot_oat.md`](win32_aot_oat.md) explicitly states that Windows OAT
generation and executable loading are not implemented. This build design does
not change that status.

`art-compiler.dll` is necessary DSO parity and may be a prerequisite for future
compiler tools. It does not by itself provide:

- a working Windows `dex2oat.exe`;
- the selected restricted Windows OAT-ELF writer profile;
- OAT/VDEX/image transaction and relocation behavior;
- the dedicated Windows OAT loader;
- Windows quick-code unwind/CFG publication; or
- the acceptance gates in `win32_aot_oat.md`.

Until those gates pass, Windows product capability should continue to be
described as interpreter/JIT work only. The build manifest may expose
`windows_aot=false`; generating a compiler DLL must not flip it.

## Final recommendation

Proceed with unification as a graph/orchestration refactor first, then achieve
Windows DSO parity, then optimize duplicate compiler work. The success measure
is not one giant platform-conditional CMake file. It is one deterministic
target graph, one reviewed target-aware overlay, one target-neutral CMake entry
point, and one Clang/Ninja command contract whose small platform mappings are
explicit and mechanically validated. That command contract uses only native
Python/CMake/Ninja/LLVM/JDK host executables, consumes only regular canonical
paths, and works unchanged on Linux and a stock Windows 10 ARM64 host without
WSL, Cygwin, a POSIX shell, Make, or reliance on symlink resolution.
