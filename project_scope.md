# MinDalvikVM (Linux) — Project Scope

Status: draft 2 — step two underway (2026-06-20)
Author: initial survey pass + bp/cmake comparison audit
Scope of this document: orientation + locked decisions. Step one (survey) and
the cmake/bp audit are done. Step two (build the converter, prototype on
`libbase`) is now in progress.

## 0. Locked decisions (step 2)

- **Converter language: Python.** (`python3` already required; AOSP codegen is
  already Python; no JVM/Gradle in the codegen path.)
- **Blueprint parsing: hand-written parser.** Small grammar, no external
  dependency, exactly the features we need. (Section 6.1.)
- **First target snapshot: the archive's 2023 submodule pins.** Keeps the
  hand-written `.cmake` as a validation baseline while we build the converter;
  submodule updates are a separate later step.
- **libc: glibc only for now; musl deferred.** (Section 5.2 item 5, Section 7.)
- Verified host toolchain: python 3.14, cmake 4.2, ninja 1.13, clang 21, gcc 15.

## 0b. Progress (step 2+)

- **Converter built** (`tools/bp2cmake/`): Layer 1 (lexer/parser/evaluator),
  Layer 2 (`overlay/port_policy.py`), Layer 3 (emitter). 16 unit tests pass.
- **Foundational layer DONE and validated**: all 8 libs the archive builds
  before `art/` — `libbase`, `liblog`, `libnativehelper`, `libprocinfo`,
  `libziparchive`, `libtinyxml2`, `liblzma`, `libcpu_features` — are converted
  from `.bp`, compile, and link together (real liblog, no stub). See
  `tools/verify/foundational/RESULT.md`. Generated CMake already fixes two
  archive bugs (dropped `errors_unix.cpp`; warning flags only on C TUs).
- **Project-owned `//compat`** include root established for vendored shim
  headers replacing absent Android deps (first: `gtest/gtest_prod.h`). Distinct
  from the read-only AOSP tree and from `native/jdwpheader`-style glue.
- **Next milestone: the ART core** (`libartbase`, `libdexfile`, `runtime`,
  `dalvikvm`, ...). Substantially larger: requires modelling `art.go` flag
  injection (Section 5.1), the generated-source pipeline (operator_out, mterp
  asm, asm_defines), and the bigger overlay surface from the audit (palette
  fake, CMS GC, ART_TARGET_LINUX, dropped statsd/libdl_android, etc.).

### ART core progress (2026-06-20)

- **Layer 1 extended** for ART: `soong_config_variables` (resolve
  `source_build=true` → ART modules enabled), `codegen` select (x86_64 →
  x86_64+x86), `avx2` sub-select (off). `art_defaults` itself is a normal
  `cc_defaults`, so its cflags inherit automatically.
- **Generated-source pipeline DONE**: emitter models `gensrcs` →
  `add_custom_command` running the Python codegen tool, outputs staged under
  `${MDVM_GENSRC_DIR}` and compiled into the consumer.
- **art.go-injected defines** handled via a PUBLIC overlay channel
  (`add_public_defines`), so knobs absent from any `.bp` (stack gaps, frame
  limit) propagate to consumers.
- **Validated**: `libartpalette.so` (no codegen) and `libartbase.so` (2.9 MB,
  3 generated `operator_out.cc`, full dep chain incl. host libcap) both build
  and link. See `tools/verify/{artpalette,artbase}/RESULT.md`.
- **13-module combined graph builds** (`tools/verify/artcore/`): 8 foundational
  + `libartpalette`, `libartbase`, `libdexfile`, `libelffile`, `libprofile`.
  `libprofile.so` links the full converted closure. PUBLIC-define propagation
  confirmed (dexfile gets artbase's art.go defines via the link, unrestated).

### Runtime — COMPLETE: runnable dalvikvm built from Android.bp (2026-06-20)

`libart` (the runtime) AND the `dalvikvm` executable now build end-to-end from
the converter + codegen driver, and the VM RUNS:

    $ LD_LIBRARY_PATH=. ./dalvikvm -showversion
    ART version 2.1.0 x86_64

- `dalvikvm` (PIE, 136 KB) links the full 19-module graph; `libart.so` builds
  with 237 srcs + 30 operator_out + mterp_x86_64.S + asm_defines.h + 5 .S
  entrypoint objects. See `tools/verify/runtime/RESULT.md`.
- The Python codegen driver (operator_out via emitter custom-commands;
  mterp + asm_defines via the driver at configure time) all works in the real
  build.

**One authorized source change** to the read-only archive made this possible:
`art_method-inl.h` `FillVRegs` terminal overload lost its value parameters to
resolve a clang≥17 variadic-overload ambiguity (behavior-preserving; recorded in
`archive-patches/README.md`). This is the source rot the submodule-update goal
will eliminate upstream.

Final converter mechanisms added: recursive `whole_static_libs` absorption,
`:name` source skipping, shell-quoted defines, absorbed-source cflags, ldflags +
global ldflag drops, executable kind, `absorb_whole_static=False` option, and
libdexfile absorbing `dex_file_supp.cc`. Build needs `ASM` language enabled and
`-DCMAKE_BUILD_TYPE=Release` (Debug expects `d`-suffixed libs).

### Status: the native side is functionally complete

The original goal — "something converting Android.bp to CMakeLists.txt so we
don't hand-write CMake" — is achieved for the whole `dalvikvm` native graph,
with a clean single-entry build:

```sh
native/generate.sh                       # Android.bp -> generated/dalvikvm.cmake
cmake -S native -B build/native -G Ninja -DCMAKE_C_COMPILER=clang \
    -DCMAKE_CXX_COMPILER=clang++ -DCMAKE_BUILD_TYPE=Release
cmake --build build/native               # -> dalvikvm + 17 libs
LD_LIBRARY_PATH=build/native build/native/dalvikvm -showversion
# ART version 2.1.0 x86_64
```

- **Dependency closure**: `bp2cmake --root-module dalvikvm` walks the link graph
  and emits all 18 buildable targets deps-first — no hand-maintained module list
  (`tools/bp2cmake/bp2cmake/closure.py`).
- **One hand-written CMake file** (`native/CMakeLists.txt`): only project-owned
  glue the converter can't derive — host imported libs (z/cap/lz4), the codegen
  driver invocation, and the clang-21 toolchain-drift shims. Everything else is
  generated.

Remaining project work is breadth/polish:
- Bump submodules to current AOSP (drops the one `FillVRegs` patch and the
  toolchain-drift shims).
- The Java side (`boot.jar`, already close in the archive) for a full
  end-to-end `command-example.txt`-style run.

### End-to-end run — the VM executes bytecode (2026-06-20)

Validated the converter-built `dalvikvm` (built **RelWithDebInfo**) against the
archive's prebuilt boot.jar (`javalib/build/merged/output.jar`) + ICU data + a
`d8`-compiled HelloWorld. The VM boots, brings up the CMS GC, falls back to
imageless running, links the core libcore classes, and **executes Java bytecode
in the interpreter (nterp)** — exercising the entire generated runtime (dex
loading, class linker, GC, interpreter, JNI).

**Build type matters: use RelWithDebInfo (-O2), not Release.** Release compiles
ART at `-O3`, which miscompiles it (an earlier `-O3` run faked a "LinkMethods
hang"; that diagnosis was wrong). Debug's GC is unusably slow. RelWithDebInfo
(`-O2 -DNDEBUG -g`) is correct and keeps symbols.

Current blocker to `main()`: the **libcore JNI natives aren't loaded**.
`libart`'s `runtime_libs: ["libjavacore"]` (runtime/Android.bp:533) is a
dlopen-at-runtime dependency (correctly not a link edge), and the
**javacorenatives** group (`libjavacore`, `libopenjdk`, + ICU/crypto/expat JNI)
isn't converted yet. Without it, libcore `native` methods (e.g.
`Class.getNameNative`) are unregistered, so the first exception's `toString`
recurses to a StackOverflow → SIGSEGV. See `tools/verify/e2e/RESULT.md`.

Next milestone: convert the javacorenatives group (the audit already analyzed
its port decisions) and load it, so `Hello.main()` runs to completion.

## 1. What this project is

The goal is a **minimal ART runtime** (the `dalvikvm` / `dalvikvm64` executable
plus its supporting libraries and a `boot.jar` core library) that runs on a
normal **GNU/Linux desktop or server** — glibc only for now (musl is explicitly
deferred, see Section 6/7) — no Android device, no Android platform services, no
`libandroid`, no framework. You hand it a dex
(or a jar of dex) and a main class and it executes Java bytecode.

Concretely, the end product is the kind of invocation already captured in the
archive's `command-example.txt`: an LD_PRELOAD/LD_LIBRARY_PATH wrapper around
`dalvikvm64 -Xbootclasspath:0:boot.jar -cp app.jar <MainClass>`, used to run a
plain-Java application (a Telegram bot, in that example) on top of ART instead
of OpenJDK.

The sources are **AOSP components vendored as git submodules**, pinned to a
2023-era snapshot (see Section 3). We are starting a fresh repository
(`dalvikvm-multiplatform` / historical `dalvikvm-linux` fallback) rather than continuing inside the archive.

## 2. What the archive (`../MinDalvikVM-Archive`) actually contains

Read-only reference. AOSP-derived, last touched early 2023. Layout:

```
MinDalvikVM-Archive/
  settings.gradle.kts        Gradle root: include(":native", ":javalib")
  build.gradle.kts           just a clean task
  buildSrc/                  Kotlin/Java build helpers (see below)
  gradle/ gradlew            Gradle wrapper (mixed 7.5 / 8.0.1 state)
  local.properties           points at an Android SDK (sdk.dir=...Android/Sdk)
  command-example.txt        sample real-world invocation of the built VM

  javalib/                   the Java side -> produces boot.jar (dex)
    build.gradle.kts         compiles libcore + icu + okhttp + conscrypt + bouncycastle,
                             then d8 -> dex -> merged output.jar
    android-annotation-stub/ hand-written stubs for @annotations libcore needs
    external/                submodules: okhttp, conscrypt, fdlibm, bouncycastle, icu

  libcore/                   AOSP libcore submodule (the Java core library source)

  native/                    the C/C++ side -> produces dalvikvm + .so libraries
    build.gradle.kts         orchestrates python codegen + drives CMake
    cmake/                   ~40 HAND-WRITTEN .cmake/CMakeLists.txt files (the mess)
    art/                     AOSP art submodule (runtime, compiler, dex2oat, dalvikvm...)
    libbase libnativehelper logging libziparchive libprocinfo
    fmtlib unwinding         AOSP system libs (submodules)
    external/                boringssl, cpu_features, dlmalloc, lzma,
                             oj-libjdwp, tinyxml2 (submodules)
```

### 2.1 The Java build (`javalib`) — "maybe somewhat fine"

`javalib/build.gradle.kts` is a single, fairly linear Gradle script. It:
- pulls Java source from many `srcDirs` across `libcore/` and the `external/`
  submodules (ojluni, libart, dalvik, luni, xml, json, dom, icu4j, okhttp,
  conscrypt, bouncycastle) plus local annotation stubs;
- compiles with `--system=none` and `--patch-module java.base=.../ojluni`;
- depends on `:native:generateConscryptNativeConstants` (one generated
  `NativeConstants.java` comes out of the native build);
- runs `d8` from the Android SDK build-tools to dex, then zips a merged
  `output.jar`.

This part is comparatively healthy: it is declarative-ish, one file, and the
only real external coupling is (a) the Android SDK `d8` tool and (b) one
generated source file from the native side. Main concerns going forward are the
Android SDK dependency and keeping the long `srcDirs` list in sync after
submodule updates.

### 2.2 The native build (`native`) — "a complete mess"

Two layers:

1. `native/build.gradle.kts` — a Gradle script that does **code generation and
   CMake orchestration**, not compilation itself. It:
   - runs AOSP python generators: `generate_operator_out.py` (enum `operator<<`
     `.cc` files for a long hand-maintained list of headers), `gen_mterp.py`
     (interpreter assembly for arm/arm64/x86/x86_64), `make_header.py`
     (`asm_defines.h` from a compiled `asm_defines.s`);
   - builds a couple of intermediate CMake targets to *generate more source*
     (`asm_defines_s`, `conscrypt_generate_constants`);
   - then invokes CMake (Ninja, clang/clang++) via the `CMakeProject` helper.

2. `native/cmake/**` — ~40 **hand-written** CMake files, one per library, e.g.
   `libbase.cmake`, `runtime.cmake` (346 lines), `compiler.cmake`,
   `dex2oat.cmake`, `dalvikvm.cmake`. Each one re-lists every source file,
   include dir, compile flag and link dependency **by hand**, transcribed from
   the corresponding AOSP `Android.bp`.

This is the pain point. Every one of those source lists, include dirs and flag
sets already exists, authoritatively, in an `Android.bp` next to the sources.
The hand-written `.cmake` files are a manual, lossy, drift-prone copy. When a
submodule is updated, someone has to diff the `Android.bp` by eye and patch the
`.cmake`. That is what makes updates miserable.

### 2.3 `buildSrc` helpers (reusable)

- `CMakeProject.kt` — thin wrapper: run `cmake -G Ninja ... -S -B` then
  `cmake --build --target`. Reusable.
- `Common.kt` — git version code via jgit, `findInPath`, read `local.properties`.
- `AbiUtils.java` — host arch -> Android ABI name mapping.

## 3. Submodules and their state (why "update" is a goal)

The archive uses git submodules pinned to ~2023:

- `art` HEAD: `f76ca8c3cb`, 2023-04-06
- `libcore` HEAD: `399a1e7563`, 2023-02-23 (udc-preview2 era)
- plus `libbase`, `libnativehelper`, `logging`, `libprocinfo`, `libziparchive`,
  `fmtlib`, and `external/{boringssl,cpu_features,dlmalloc,lzma,oj-libjdwp,
  tinyxml2}`, and the java `external/{okhttp,conscrypt,fdlibm,bouncycastle}`.

`git status` in the archive shows many submodules dirty / modified, and the
gradle wrapper itself is in a half-migrated state. So the archive is not a clean
baseline — it is a working tree someone left mid-change.

All submodule URLs point at `android.googlesource.com/platform/...`. Updating
means moving these pins forward to a coherent newer AOSP snapshot, which will
change source lists, flags, and dependencies — exactly the churn the
hand-written CMake can't absorb cheaply.

## 4. The core problem to solve

> Android builds these components with **Soong**, which reads `Android.bp`
> (Blueprint) files. We are not on Android and don't want Soong. Today we
> bridge that gap by hand-writing CMake. That hand-translation is the mess and
> the maintenance tax.

Scale of the `Android.bp` surface (counts across the subset we actually use —
`libbase`, `libnativehelper`, `art`, `logging`, `libziparchive`, `libprocinfo`,
`fmtlib`):

- 810 `Android.bp` files total under `native/` (most are tests/tools we ignore).
- The module types we care about are mainly: `cc_library`, `cc_library_shared`,
  `cc_library_static`, `cc_library_headers`, `cc_binary`, `cc_defaults`,
  `cc_object`, `filegroup`, `genrule`/`gensrcs`, and ART's custom
  `art_cc_library` / `art_cc_binary` / `art_cc_defaults` family.
- Important: `art_cc_*` are **not** built-in Soong types. They are defined in Go
  (`native/art/build/art.go`, `codegen.go`, `makevars.go`) and via
  `soong_config_module_type_import` from `art/build/SoongConfig.bp`. A converter
  must treat these as "cc_* plus extra ART defaults/codegen flags", not parse
  the Go. We hardcode/approximate their behavior.
- Features that appear and must be handled: `defaults` inheritance, `srcs` /
  `exclude_srcs`, `shared_libs` / `static_libs` / `header_libs`,
  `include_dirs` / `export_include_dirs`, `cflags` / `cppflags`,
  `generated_sources` / `generated_headers`, and `arch: {}` / `target: {}`
  conditioning (we only need the linux + host + arm/arm64/x86/x86_64 branches).
- `soong_config` variables appear (~34 references) but for our minimal Linux
  target most can be resolved to fixed values.

## 5. What the comparison revealed (the hand-written CMake is NOT a faithful translation)

We audited the ~40 hand-written `.cmake` files against their source `Android.bp`
files, module by module. **Critical finding: the existing CMake is not a
mechanical translation of the `.bp`. It is a translation plus a thick layer of
deliberate Android-to-Linux engineering decisions, plus a number of outright
bugs.** This reshapes the converter design (Section 6/7) and is the single most
important thing to internalize before writing any code.

Two consequences up front:

- A naive "parse `.bp` -> emit CMake" converter produces a **wrong** build. It
  would faithfully reproduce Android behavior we explicitly do not want, and it
  cannot invent the fakes/substitutions the port depends on.
- The old `.cmake` files are a **quarry to mine the port decisions from, not a
  golden reference to reproduce** — they contain real defects (listed in 5.8).

### 5.1 The `.bp` are written for Android, and encode Android assumptions invisibly

The `.bp` describe how to build ART **for an Android device on bionic**, inside
the APEX/Soong world. Much of what we must change is not even visible in the
`.bp` text:

- **ART's build flags are injected by Go, not declared in `.bp`.** `ART_TARGET`,
  `ART_TARGET_ANDROID`/`ART_TARGET_LINUX`, the default GC type,
  `ART_FRAME_SIZE_LIMIT`, `ART_STACK_OVERFLOW_GAP_*`, the per-arch
  `ART_ENABLE_CODEGEN_*`, and the whole base cflag list come from
  `native/art/build/art.go` / `codegen.go` load hooks. They appear **nowhere**
  in the module `.bp`. The hand-written CMake reconstructs them by hand in
  `native/cmake/art/CMakeLists.txt` (`ART_COMPILE_C_FLAGS`) and `runtime.cmake`.
  A `.bp`-only parser is blind to all of it.
- AOSP `art.go` defines `-DART_TARGET`/`-DART_TARGET_ANDROID` vs `_LINUX` based
  on an `ART_TARGET_LINUX` env var, and ONLY for the android target. A real host
  build defines neither. The port instead **force-defines `ART_TARGET` +
  `ART_TARGET_LINUX`** on the runtime — compiling ART in a "Linux-flavored
  target" mode that is its own third thing, not host and not device.

### 5.2 Recurring workaround patterns (these are the rules the converter must encode)

1. **Linkage swaps (static<->shared).** Almost every `cc_library` /
   `cc_library_static` is forced to `add_library(... SHARED)`, with a few forced
   STATIC (`elffile`, `cpu_features`, `fdlibm`, `icuuc_stubdata`,
   `androidicuinit`). Concrete inversions: `libicu_static` -> shared `icu`;
   shared `libicuuc_stubdata` -> STATIC; AOSP's `whole_static_libs` (fmtlib into
   libbase, cpu_features/tinyxml2 into their consumers) become either inlined
   sources or plain shared links. This is a global policy, tied to the next item.
2. **Global "self-contained .so" link policy.** Top-level CMake forces
   `-Wl,--no-undefined,--no-allow-shlib-undefined -static-libgcc
   -static-libstdc++` on every target. That is *why* every dropped source or dep
   matters: there is no lazy Android runtime symbol resolution to paper over gaps.
3. **dlopen/linker-namespace model replaced by direct linking.**
   `libart-disassembler` flips from `runtime_libs` (Android lazy dlopen) to a
   hard link in the compiler. `libnativeloader` drops its entire namespace engine
   (`library_namespaces.cpp`, `native_loader_namespace.cpp`,
   `public_libraries.cpp`, `libdl_android`, `libPlatformProperties`) down to bare
   `dlopen` on `native_loader.cpp`. `libnativebridge` strips `libdl_android` +
   `dlext_namespaces.h`.
4. **Android platform services replaced by fakes / Linux source variants.**
   `libartpalette` builds ONLY `system/palette_fake.cc` (no-op thread
   priority/ashmem/tracing) instead of the Android `dlopen(libartpalette-system)`
   loader. ART picks `os_linux.cc`, `monitor_linux.cc`, `runtime_linux.cc`,
   `thread_linux.cc`, `unix_file/*` and DROPS the `*_android.cc` trio +
   `metrics/statsd.cc`. liblog is reduced to a minimal write-only stub (logd/pmsg
   transport sources dropped).
5. **libc identity forced; musl path collapsed.** `libjavacore` / `libopenjdk`
   hand-define `__GLIBC__`, `_GNU_SOURCE`, `_LARGEFILE64_SOURCE`, `LINUX`
   (literally commented `# Sigh.`); `cpu_features` force-defines
   `-DHAVE_STRONG_GETAUXVAL`. The `.bp` keep a real `target.musl` branch; the
   CMake collapses to glibc-only. We are keeping glibc-only by choice (musl
   deferred, Section 6/7), so this collapse is acceptable for now — but it is a
   *decision to record in Layer 2*, not an accident, so musl can be restored
   later without rediscovering why `__GLIBC__` was forced.
6. **Dependency rewiring / renaming.** AOSP names map to short targets
   (`libbase`->`base`, `liblog`->`log`, `libz`->`z` = host system zlib,
   `liblzma`->`lzma`); Android-only deps are dropped from `art`
   (`libdl_android`, `libstatssocket`, `heapprofd_client_api`,
   `libstatslog_art`, `libodrstatslog`); boringssl `libcrypto` is built SHARED +
   **non-FIPS** (the entire `bcm_object`/FIPS hashing machinery dropped), which
   then forces conscrypt's `libjavacrypto` to link crypto **shared** (AOSP links
   it static on host).
7. **Behavioral pins.** GC default swapped from CMC (mark-compact, needs
   userfaultfd) back to **CMS** (`ART_DEFAULT_GC_TYPE_IS_CMS`) in `runtime.cmake`.
8. **Metadata dropped wholesale.** All `version_script:` / `stubs:` (APEX symbol
   ABI), `apex_available`, `min_sdk_version`, `vndk`, `sanitize`, `tidy` blocks
   are dropped. `-Werror` and `-Wthread-safety` are removed globally (host
   clang+glibc warns where the Android toolchain does not), with assorted
   `-Wno-*` added.
9. **Module merges with no `.bp` equivalent.** `libandroidio` is collapsed into
   `libjavacore` (its `.map.txt` symbol-versioned stub has no CMake analogue);
   `libdexfile` absorbs `dex_file_supp.cc` from AOSP's separate
   `libdexfile_support`; the standalone `dexlayout` binary and `libbacktrace` are
   simply not built.
10. **Generated code pre-baked.** `:libart_mterp.*ng`, `operator_out`,
    `asm_defines` genrules are replaced by pre-generated files staged under
    `build/gensrc/` and consumed directly.

### 5.3 The one local non-AOSP file

`native/jdwpheader/jdwpTransport.h` is an **OpenJDK** header (not from any
`.bp`) hand-placed to satisfy ART's JVMTI/JDWP debug transport ABI. A converter
could never derive this from the `.bp`; it must be carried as project-owned glue.

### 5.4 Bugs found in the existing CMake (do NOT reproduce; fix when porting)

The audit surfaced real defects in the hand-written files, which is further
proof they cannot be a golden reference:

- `libbase` **drops `errors_unix.cpp`** entirely (picked no OS `target` branch),
  so the host build is missing `SystemErrorCodeToString`.
- `libssl` accidentally compiles the `bssl` **command-line tool** sources
  (`src/tool/*.cc`) into the shared SSL library.
- The FIPS `fips_shared.lds` version script + `-Bsymbolic` are applied to a
  **non-FIPS** crypto build (wrong context).
- `disassembler` compiles BOTH `disassembler_arm64.cc` and `disassembler_arm.cc`
  for arm64; never links `libvixl`.
- `asm_defines` passes `-UDEBUG` where AOSP undefines `-UNDEBUG`.
- `libtinyxml2` force-enables Android logcat macros (`-DDEBUG -DANDROID_NDK`) on
  Linux while NOT linking `liblog`.
- `liblzma` sets `CXX_STANDARD 20` on a pure-C target; `libbase` applies
  `-Werror`-class flags only to C TUs though it is all C++.
- `libunwindstack` ships `DexFile.cpp` but never defines `DEXFILE_SUPPORT`, so
  dex-frame symbolization is compiled in its disabled form.
- Duplicate entries: `dex_file_verifier.cc` (libdexfile), ziparchive include
  (libartbase).
- ICU `.dat` data file is never wired in by any CMake; the build leans on an
  empty stubdata + external `ICU_DATA`.

### 5.5 Design conclusion the comparison forces

The converter cannot be a single pass. It must be **three layers**, separating
"what AOSP says" from "what we decided" from "how CMake spells it":

- **Layer 1 — Blueprint evaluator.** Parse `.bp`; resolve `defaults`, variables,
  `+` concatenation; evaluate `arch{}`/`target{}` selects against a FIXED config
  (host, `linux_glibc`, chosen arch — `linux_musl` is a future config value, not
  wired now). Include a hardcoded model
  of `art.go`/`codegen.go` so `art_cc_*` modules receive their real injected
  flags. Output: a normalized, config-resolved module graph.
- **Layer 2 — port-policy overlay (WE own this file; it is the valuable part).**
  The small, relatively stable set of deliberate decisions from 5.2: per-module
  kind overrides, source substitutions (`palette_fake.cc`, `os_linux.cc`, drop
  `*_android.cc`), dependency rewrites (drop `libdl_android`, map `libz`->host
  zlib, drop FIPS), define overrides (CMS GC, force `__GLIBC__`, force
  `ART_TARGET_LINUX`), flag policy (drop `-Werror`), and "don't build this"
  exclusions. Mined from the existing `.cmake` (minus its bugs).
- **Layer 3 — CMake emission.** Deterministic, dumb. Graph + overlay -> CMake.

This split is exactly what makes updates cheap (the project's core goal): a
submodule bump re-runs Layer 1, refreshing the tedious, drift-prone source lists
and dependency edges automatically, while Layer 2 — the human judgment — rarely
changes. The hand-written CMake conflated all three layers into one, which is
precisely why it rots on every update.

## 6. The goal (what "good" looks like)

The `dalvikvm-multiplatform` project (historically started as `dalvikvm-linux`) where:

1. **Native build is generated, not hand-written.** A tool reads the AOSP
   `Android.bp` files and emits `CMakeLists.txt`. When we bump a submodule, we
   re-run the generator instead of diffing source lists by hand.
2. **Updates are cheap.** Submodule bump -> regenerate -> build. Drift between
   the AOSP source and our build description is structurally impossible because
   the build description is derived.
3. **Linux-first, no Android platform API.** Target **glibc only for now** (musl
   deferred — see Section 7), host clang, `arm/arm64/x86/x86_64`. Resolve Soong's
   Android-only branches away.
4. **The Java side keeps working** (it is already close), fed by the one
   generated source the native side produces.
5. **Reproducible end artifact**: `dalvikvm` + the needed `.so`s + `boot.jar`,
   runnable like `command-example.txt`.

### 6.1 The Android.bp -> CMakeLists.txt converter

The centerpiece, structured as the three layers established in Section 5.5
(Blueprint evaluator -> port-policy overlay -> CMake emission). Decisions to
lock in next phase, current leaning:

- **Language: Python.** Rationale: the existing codegen the build already shells
  out to is Python (`generate_operator_out.py`, `gen_mterp.py`,
  `make_header.py`); `python3` is already a required tool; Blueprint is close to
  JSON and easy to parse in Python; no JVM/Gradle needed just to generate a
  build. (Kotlin is the alternative — it matches `buildSrc` and is type-safe,
  but drags Gradle into the codegen step. We will confirm the choice in step 2.)
- **Reuse Soong's own parser if practical.** Blueprint's grammar is small but
  real (`defaults`, variables, `+` concat, `arch`/`target` selects). AOSP ships a
  Go Blueprint parser; there are also third-party Python `.bp` parsers. To
  confirm in step 2 whether to reuse one vs. write a small one.
- **Layer 1 must model `art.go`.** Because ART's real flags live in Go, not
  `.bp` (Section 5.1), the evaluator needs a hardcoded table reproducing the
  `art_cc_*` defaults and `ART_ENABLE_CODEGEN_*` logic. This is unavoidable and
  is the part most coupled to the AOSP snapshot.
- **Layer 2 is a checked-in, human-authored policy file** (format TBD — likely
  declarative: per-module overrides keyed by module name). It is the durable
  asset; treat it as code, with comments citing *why* (Android vs Linux) for
  each override, since the audit showed those reasons are easy to lose.
- **What Layer 3 emits:** per-module CMake targets (`add_library`/
  `add_executable`, `target_sources`, `target_include_directories`,
  `target_compile_options`, `target_link_libraries`) wired by module name —
  structurally like today's files, minus the bugs.
- **Allowlist, not whole-tree:** only convert modules reachable from the
  `dalvikvm` target (and the boot-jar codegen). Not all 810 blueprints.
- **Validation strategy:** diff generated output against the existing
  hand-written `.cmake` for each module, using the audit notes to distinguish
  "intended port decision" (must match, encode in Layer 2) from "old bug"
  (generated output should differ and be correct).

## 7. Risks and open questions

- **Blueprint is not trivial — and the `.bp` is not even the whole truth.**
  `defaults` inheritance, `arch/target` selects, `soong_config`, the Go-defined
  `art_cc_*` types, AND the `art.go` flag injection (Section 5.1) mean a naive
  parser is not just incomplete but actively misleading. Mitigation: the
  three-layer design (Section 5.5), scope to the reachable module set, hardcode
  the ART/`art.go` expansion, resolve config to fixed Linux values.
- **The port-policy overlay (Layer 2) is the hard, valuable part.** It captures
  the Section 5.2 decisions and is mined from the buggy hand-written CMake. Risk:
  getting it wrong silently reintroduces Android behavior or an old bug. It needs
  per-entry rationale and per-module validation against the audit notes.
- **musl is explicitly deferred (decided).** glibc is the only step-one target.
  The hand-written CMake force-defines `__GLIBC__` and collapses Soong's
  `target.musl` branch (Section 5.2 item 5); we keep that collapse for now, but
  record it as a deliberate Layer 2 entry rather than leaving it implicit. Real
  musl support later means *restoring* that branch in Layer 1 and parameterizing
  the libc in Layer 2 — a future milestone, not a freebie, and not blocking
  anything now.
- **Generated sources are load-bearing.** `operator_out`, mterp asm,
  `asm_defines.h`, `conscrypt_generate_constants` must run in the right order.
  The converter must emit these as CMake custom commands / targets, or we keep
  driving them from a thin outer script. Decide which.
- **Non-AOSP glue must be carried.** `native/jdwpheader/jdwpTransport.h`
  (Section 5.3) and any future shim are project-owned; the converter must know
  they exist and where they plug in.
- **Submodule bump = source churn — but that is the point.** Newer AOSP may add
  files, flags, deps, or new Android-only branches the converter doesn't model.
  The win is that breakage shows up at regeneration/compile time in a known
  place (Layer 1 output or build error), not as silent drift. New Android-only
  behavior may require new Layer 2 overrides.
- **The existing `.cmake` has bugs (Section 5.4).** Validation must not blindly
  match it; the audit notes are the arbiter of correct-vs-bug.
- **Android SDK dependency (`d8`).** The Java side needs `d8`. Acceptable for
  now; note it as an external prerequisite.
- **No build attempted yet.** Everything above is from reading and comparing the
  archive, not from a successful build of either tree. First real build is a
  future step.

## 8. Next steps (immediate)

This document is step one and the only deliverable for now. The proposed
sequence after sign-off:

1. **Lock the converter decision** — Python vs Kotlin; reuse a Blueprint parser
   vs write one; confirm the three-layer structure. (Section 6.1.)
2. **Initialize the new repo** — `git init`, decide submodule set + URLs, pin to
   a chosen AOSP snapshot (start from the archive's pins, plan an update path).
   Port the reusable `buildSrc` helpers (`CMakeProject`, `AbiUtils`) if we keep
   any Gradle orchestration. Carry over `native/jdwpheader/`.
3. **Seed the port-policy overlay from the audit.** Capture the Section 5.2
   decisions and Section 5.4 bug-fixes as the first Layer 2 entries, each with a
   why. This is the durable artifact and should exist before broad conversion.
4. **Prototype the converter on one leaf module** — `libbase` is ideal: small,
   self-contained, and we have a known-good (but buggy — missing
   `errors_unix.cpp`) hand-written `libbase.cmake` to diff against. Success =
   generated CMake builds `libbase`, matches the *intended* result, and FIXES the
   `errors_unix.cpp` bug via Layer 1's `target.linux` resolution.
5. **Expand outward along the dependency graph** — liblog, libnativehelper,
   fmtlib, libziparchive, ... up to `runtime` and finally the `dalvikvm`
   executable, validating each against the archive's `.cmake` and the audit
   notes (intended decision vs old bug).
6. **Re-wire codegen + the Java side**, then attempt a full `dalvikvm` + boot.jar
   build and run the `command-example.txt`-style smoke test.

## 9. Reference: pointers into the archive

- Sample real invocation: `../MinDalvikVM-Archive/command-example.txt`
- Native orchestration: `../MinDalvikVM-Archive/native/build.gradle.kts`
- Hand-written CMake (the mess, also the policy quarry): `native/cmake/**`
- ART flag injection (NOT in `.bp`): `native/art/build/{art,codegen,makevars}.go`
- A clean small example to mirror (and a bug to fix): `native/cmake/libbase.cmake`
  <-> `native/libbase/Android.bp` (note the missing `errors_unix.cpp`)
- The platform-fake pattern: `native/cmake/art/libartpalette.cmake` <->
  `native/art/libartpalette/Android.bp` (`palette_fake.cc`)
- Final exe: `native/cmake/art/dalvikvm.cmake` <-> `native/art/dalvikvm/`
- Project-owned non-AOSP glue: `native/jdwpheader/jdwpTransport.h`
- Java build: `../MinDalvikVM-Archive/javalib/build.gradle.kts`
- Reusable helpers: `../MinDalvikVM-Archive/buildSrc/src/main/`
- Submodule list + URLs: `../MinDalvikVM-Archive/.gitmodules`





