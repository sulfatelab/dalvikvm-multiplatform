# ART in WebAssembly: runtime design

Status: design; not yet implementation-ready

Date: 2026-08-07

Companion analyses:
- [`art_wasm_feasibility.md`](art_wasm_feasibility.md) — target feasibility
- [`art_function_pointer_analysis.md`](art_function_pointer_analysis.md) — executable-pointer audit

## Executive summary

How to run ART in a browser Wasm environment, for real: put the **entire
language runtime** — ART itself, the C++ switch interpreter, libcore JNI
implementations, ICU/OpenJDK C/C++, libc compatibility, and PosixShim virtual
state — inside the Wasm guest, compiled to Wasm, sharing one linear memory.
There is no physical-CPU DSO, no native JIT, no OAT executable, no signal
handler, and no JavaScript that implements Java behavior. The browser supplies
only narrow capability imports below PosixShim.

The two load-bearing constraints, restated from the feasibility analysis:

1. **A Wasm callable is not a byte address.** `ArtMethod` stores an entrypoint
   as a native code pointer and ART recovers `OatQuickMethodHeader`, stack maps,
   return PCs, catch targets, and OSR targets by subtracting from or testing
   against that pointer. None of that works on Wasm: a C/C++ function pointer is
   a function-table slot, and the engine's real return PCs are invisible to the
   guest. The port must replace the entrypoint representation with an explicit
   tagged execution descriptor and keep method identity, body identity, table
   slot, and logical PC as separate values.
2. **Compiled-code GC roots live in explicit linear-memory frames, not engine
   registers.** Wasm engine stack maps cannot see a Java reference held only in
   a Wasm local. Every method that can allocate, suspend, or enter runtime code
   must spill live references into an ART-visible managed frame before the
   call.

The delivery order is therefore: switch interpreter first, offline DEX-to-Wasm
AOT second, GC root correctness and exceptions third, threads last (mandatory
before target admission). wasm32 first; wasm64 later.

The sections below give the target classification, the complete runtime
architecture, the method dispatch and execution-descriptor design, the managed
frame and GC-root contract, the exception model, the offline AOT compiler
pipeline (ART HGraph through Waffle), the PosixShim boundary, the milestone
plan mapped onto this repository's conventions, and the precise code-level
first steps.

## Target classification and capability gate

The canonical profile is `wasm-wasm32-posixshim` (and later
`wasm-wasm64-posixshim`). The feasibility analysis concluded, and this design
accepts, that these profiles are **not admissible under the current ART
contract** — that classification stays until every milestone is proven. The
design below deliberately works under a **new, documented contract**: a
restricted ART-derived runtime with switch interpreter, offline Wasm AOT, no
runtime JIT, no nterp, no OSR, and no signal-based faults. Until the threading
milestone passes, the profile must not be reclassified, because current ART
cannot run without its thread contract.

Admission gates, all mandatory:

| Gate | Requirement | Current status |
|---|---|---|
| Compilation | clang/LLD target `wasm32-unknown-unknown` (or Emscripten), single linear memory, function table | available |
| Single-thread boot | imageless `-Xint` boot through the switch interpreter | design, not built |
| Shared memory and atomics | `SharedArrayBuffer`-backed `WebAssembly.Memory` with atomics | browser-dependent; cross-origin isolation required |
| Worker threads | `pthread_create` over Web Workers, per-thread TLS blocks in shared memory, futex-style waits | design |
| Table | shared function table with declared maximum; slot 0 reserved for null | available |
| Threading contract | `Runtime::Start` daemon threads, thread pool, GC coordination | **blocked** until shared-memory/Worker work passes |

The repo already has the structure for this: `tools/bp2cmake/bp2cmake/target.py`
registers both Wasm profiles with status `impossible_under_current_art_contract`,
and `native/CMakeLists.txt` admits only `linux|windows`. Both must be opened up
deliberately, profile by profile, as milestones pass — never silently.

## Architecture: whole runtime in the guest

```text
Java/DEX methods                     (interpreted or offline-AOT-compiled to Wasm)
   |
libcore JNI + ICU/OpenJDK C/C++      all compiled to Wasm, statically linked
   |
libc entrypoints + ART OS abstractions   (files, fds, mmap, pthreads, sockets, clocks)
   |
PosixShim virtual POSIX state         Wasm-owned descriptor tables, VFS, thread registry
   |
versioned host-capability imports     narrow browser primitives only
   |
Browser: Worker, SharedArrayBuffer, OPFS/IndexedDB, Fetch/WSS, crypto, clocks
```

Rules that are not optional:

- Every C/C++ source in the deployment — ART runtime, switch interpreter,
  libcore JNI, ICU, OpenJDK support, allocator, libc compat, admitted app JNI —
  compiles to Wasm. There is no physical-ISA fallback.
- `System.loadLibrary`, `dlopen`, `dlsym`, agents, plugins, native bridge:
  unsupported, replaced by a generated static JNI registry. JavaScript never
  implements a Java method.
- The managed heap is a dedicated arena below 4 GiB because managed references
  are compressed 32-bit offsets even in a 64-bit build
  (`object_reference.h`). wasm64 does not grow the Java heap.
- Linear memory, function table, module-local function index, and engine stack
  are four different namespaces and are never conflated in the C++ type model.

## Method dispatch: the execution descriptor

`ArtMethod::PtrSizedFields` (`art_method.h`) has two overloaded `void*` words:
`data_` and `entry_point_from_quick_compiled_code_`. The audit's central
finding: these words are simultaneously call targets, byte addresses,
metadata anchors, and keys. The port replaces the entrypoint word with an
explicit, tagged value. The cleanest form for a fork is a side table keyed by
`ArtMethod*`, because it does not change `ArtMethod`'s layout (which is also
image-packed and heap-visible) — but a Wasm-specific fork can also carve a
real field. The design:

```cpp
// Execution descriptor: what the current dispatch target is.
enum class ExecutionKind : uint8_t {
  kSwitch,        // enter the C++ switch interpreter with a ShadowFrame
  kWasmAot,       // call a table slot in classes-aot.wasm
  kStaticJni,     // typed static-registry slot for a JNI-declared method
  kRuntimeStub,   // resolution, proxy, obsolete, IMT-conflict "stubs"
  kPrecompiled,   // statically linked helper (small-pattern-matcher analogues)
  kUnsupported,   // explicit failure for disabled native paths
};

struct WasmMethodEntry {
  ExecutionKind kind;
  uint32_t table_slot;    // shared-table index for kWasmAot / kStaticJni
  uint32_t type_id;       // exact Wasm function type (signature bucket)
  uint32_t body_id;       // stable body identity for metadata lookup
  uint32_t generation;    // stale-reference guard for table-slot reuse
};
```

`data_` keeps its legitimate data meanings (JNI resolver identity, `ImtConflictTable*`,
single-implementation method, code-item pointer). The two words must never be
confused; the audit's invariant 1 (separate namespaces in the type and data
model) is enforced in code with distinct C++ types, not comments.

All AOT methods initially share one uniform Wasm signature so every AOT call
can go through one table:

```text
(thread_ptr, art_method_ptr, shadow_frame_ptr, result_ptr) -> status
```

`status` carries `kNormal`, `kException`, `kDeoptimize`, `kSuspended`. A later
optimization can bucket by shorty with typed tables and adapters; the uniform
signature first.

Dispatch transitions:

| Transition | Mechanism |
|---|---|
| switch -> switch | existing `ExecuteSwitch` / ShadowFrame machinery |
| switch -> AOT | resolve `ArtMethod`, read descriptor, publish managed frame, `call_indirect` |
| AOT -> AOT (fixed target) | direct Wasm call when class init/instrumentation/artifact linking make it invariant |
| AOT -> AOT (virtual/interface) | resolve `ArtMethod`, validate kind+type, `call_indirect` |
| AOT -> switch | create/link `ShadowFrame`, `ExecuteSwitch` |
| Java `native` -> C/C++ | generated registry entry, typed thunk |

`ArtMethod::Invoke()` currently enters an ISA-specific invoke stub; the Wasm
port routes it through the descriptor instead. Instrumentation switches
descriptors and requests explicit safepoints; it never infers execution kind
from numeric table-slot ranges (the audit's instrumentation section and
invariant 2).

## Managed frames and GC roots

Wasm engine stack maps do not describe ART managed references stored as
integer linear-memory offsets. A moving or collecting ART GC cannot discover a
reference that exists only in a Wasm local. This is the correctness crux of
the whole port, not an optimization.

The baseline AOT ABI therefore keeps an ART `ShadowFrame` (or a Wasm-specific
managed frame with the same contract) for every compiled method. The compiler
generates, at every safepoint (allocation, suspend poll, monitor op, runtime
call, class resolution, JNI call):

1. spill all live managed references into the frame's root slots;
2. update the published current DEX PC / safepoint ID;
3. publish precise reference-kind information (which slots hold references);
4. after the runtime call, restore possibly-moved references.

The frame in linear memory carries, at minimum: caller link, `ArtMethod*`,
current safepoint ID / DEX PC, root slots, and deoptimization state. GC walks
these explicit frame chains; it does not read an engine PC. The offline
artifact maps `(body_id, safepoint_id)` to root slots and reference kinds,
mirroring how `CodeInfo` + stack maps work today but keyed explicitly.

The JIT code GC (reclaiming code allocations by scanning stack PCs) is
disabled. Code lifetime uses explicit active-frame references or
epoch/generation tracking on `body_id`/`table_slot` instead.

## Exceptions

Wasm traps are terminal; they cannot stand in for recoverable `SIGSEGV`
contexts. The compiler emits explicit checks:

- null checks before dereference;
- array bounds checks;
- divide-by-zero and cast checks;
- stack-limit / managed-call-depth checks in method prologues (no guard-page
  stack overflow recovery);

The AOT body sets a pending exception on `Thread` and returns `kException`
status to its caller, or transfers to the DEX catch handler. Exception delivery
is a dispatcher-driven state transfer, not a PC write. Wasm exception-handling
proposal (exception tags / `try`-`catch`) can be revisited later; the initial
ABI does not depend on it.

## Offline AOT: DEX -> HGraph -> Waffle -> Wasm

The compiler runs at packaging time, on the build host. It never runs inside
the guest. The deployed runtime is mixed AOT/interpreter; DEX remains
authoritative for metadata, verification, reflection, debugging, and fallback.

```text
DEX -- verify/resolve (ART front end)
  --> HGraph/SSA (builder.cc)
  --> backend-independent optimization subset
  --> explicit lowering to runtime-helper calls
  --> Waffle FunctionBody IR
  --> Waffle backend (block/SSA to structured core Wasm)
  --> classes-aot.wasm
```

Why ART's own front end instead of dex2jar/Enjarify (class-file round-trip):
reusing `builder.cc` retains DEX verification, resolution, Android semantics,
and one authoritative DEX representation shared with the switch interpreter.
A class-to-Wasm pipeline would deliver Java-on-Wasm, not ART-on-Wasm.

Why Waffle (Bytecode Alliance, pinned revision; currently hardcodes
`memory64=false`, `shared=false`, `table64=false` — a good match for the
wasm32 first prototype): it already implements reducification of irreducible
loops, recovery of structured `block`/`loop`/`if`, treeification of SSA
values, and linear-scan allocation to Wasm locals. It emits imports and active
element segments, so `classes-aot.wasm` can populate an imported method table.
The `optimizing_compiler.cc` currently constructs a physical-ISA
`CodeGenerator` before building HGraph; the Wasm compiler must decouple HGraph
construction from code generation and pass compiler capabilities directly, or
provide a minimal Wasm-IR code-generator adapter used only to make the frontend
and selected passes available.

Two modules at deploy time, sharing one memory and one table:

- `runtime.wasm` — owns and exports linear memory, method table, allocator, GC,
  interpreter, registry;
- `classes-aot.wasm` — imports the same memory and table, installs compiled
  methods into reserved slots via active element segments, calls ART helpers
  through the explicit C ABI.

(Statically combinable later.) The AOT artifact is a versioned Wasm format,
**not** an OAT: manifest with runtime ABI version, pointer width, required Wasm
features, DEX checksums, boot-class-path hashes, method-to-table-slot map,
DEX-PC maps. The loader rejects mismatched manifests deterministically. OAT
loading (`DlOpenOatFile`, `ElfOatFile`), OAT header arithmetic, and image
code-pointer relocation are all disabled in this profile.

## PosixShim and the browser boundary

PosixShim is the project-owned, Wasm-resident POSIX surface below ART and
libcore. `open`, `read`, `mmap`, `pthread_mutex_lock`, `poll`,
`clock_gettime` are Wasm functions over virtual state plus narrow imports.
Three behavior classes, all explicit and versioned:

| Class | Meaning |
|---|---|
| Implemented | sufficiently equivalent for ART/libcore, with conformance tests |
| Virtualized | deterministic, documented, differs from a real process/kernel |
| Unsupported | documented error (`ENOSYS`, `EOPNOTSUPP`, `EPERM`) or disabled feature |

Never a silent success no-op: pretending `mprotect` installed read-only
protection when it cannot would corrupt any GC relying on a later fault.

Key decisions, from the feasibility analysis:

- **Memory**: `MemMap` becomes a Wasm region allocator over one linear memory;
  logical 4-KiB ART pages (16 per 64-KiB Wasm page) for bookkeeping; no real
  protection semantics; `PROT_EXEC` always fails; `MAP_FIXED` only inside
  reserved compatible arenas; `memory.grow` preserves offsets.
- **Files**: preload boot JAR/DEX into linear memory synchronously before
  `Runtime::Start`; packaged read-only assets plus in-memory files; later
  OPFS-backed persistence with a capability-Worker bridge.
- **Clocks**: monotonic from `performance.now`, wall from `Date.now`.
- **Entropy**: `crypto.getRandomValues`.
- **Networking**: standard Trojan-over-WSS outbound contract (Trojan `CONNECT`
  for TCP, `UDP ASSOCIATE` with per-datagram SOCKS address for UDP), one WSS
  connection per fd, Wasm-owned socket state and framing; `listen`/`accept`/
  raw sockets etc. return documented errors.
- **Threads**: shared memory + atomics + Workers; `Atomics.wait`/`notify` for
  futexes; per-Worker TLS blocks in the shared linear memory
  (`__tls_base` + offset). Threads are mandatory before target admission;
  Shared-Everything Threads is preferred long-term but is Phase 1 and not
  implemented in browsers (verified 2026-08-07), so the shared-memory baseline
  must work.
- **Sync over async**: ART runs in a dedicated Worker; boot-critical reads come
  from preloaded memory; blocking waits cross to a capability Worker and wait on
  a `SharedArrayBuffer` word with `Atomics.wait`. Asyncify/JSPI are not the
  initial foundation.
- **Emscripten** may supply libc/filesystem/pthread components beneath the
  PosixShim boundary; it is never the ABI axis. Start with Emscripten for
  bring-up speed, then move correctness-sensitive state into Wasm.

## The full source change set

Everything below is "eventually"; the milestone plan says what comes first.

| Area | Today | Change |
|---|---|---|
| `tools/bp2cmake/bp2cmake/target.py` | Wasm profiles `impossible_under_current_art_contract` | keep status; add milestone gate so status flips only with evidence |
| `native/CMakeLists.txt` | admits `linux\|windows` only | admit `wasm` behind a new profile gate + bundle/runner policy |
| `vendor/art/libartbase/arch/instruction_set.h` | 4 physical ISAs + `kNone` | add `kWebAssembly`; 276 ISA switch cases across 23 files need audit and routing |
| `vendor/art/compiler/optimizing/` | physical-ISA code generators; HGraph construction coupled to them | decouple HGraph from codegen; new Wasm backend (lowering + Waffle) |
| `vendor/art/runtime/interpreter/interpreter_switch_impl.h` | assembly/CFI wrapper; function-to-`void*` | Wasm C++ entry path; direct call |
| `vendor/art/runtime/art_method.h` + entrypoints | `void*` quick entrypoint | execution descriptor; typed dispatch; no header/PC arithmetic |
| `vendor/art/runtime/oat/*`, `oat_quick_method_header*`, `image_space.cc` | native OAT/ELF/image code-pointer contract | disabled; replaced by Wasm AOT artifact and side-table metadata |
| `vendor/art/runtime/jit/*` | executable mappings, code cache, OSR, JIT code GC | disabled |
| `vendor/art/runtime/interpreter/mterp/nterp.*` | assembly interpreter impersonating quick code | disabled; switch interpreter only |
| `vendor/art/runtime/fault_handler.cc` | signal context, PC rewriting | disabled; explicit checks in generated code |
| `vendor/art/runtime/stack.cc`, `quick_exception_handler.cc` | native PC walking, catch via native PC | explicit managed frame chain, safepoint IDs, dispatcher |
| `vendor/art/runtime/jni/*`, `java_vm_ext.cc` | `dlopen`/`dlsym` JNI | generated static registry, typed thunks |
| `vendor/art/runtime/gc/` | PC-derived stack maps | explicit root slots + safepoint tables (algorithm shapes reusable) |
| `vendor/art/compiler/optimizing/stack_map_stream.cc` etc. | native stack maps | explicit `(body_id, safepoint_id)` maps |
| `vendor/libcore`, `vendor/icu`, `vendor/external/*` | native C/C++ | cross-compile to Wasm; JNI registry |
| new: PosixShim | — | Wasm-resident libc/POSIX surface + capability imports |
| `tests/`, `overlay/` | Linux/Windows gates | wasm32 probe and gate registry entries |

## Milestone plan (mapped to this repo)

The milestones mirror the feasibility analysis's stages, phrased for this
repository so each one is a shippable commit sequence with evidence.

### M0 — Profile groundwork (repo mechanics)

- Add `wasm32`/`wasm64` admission plumbing to `target.py` and
  `native/CMakeLists.txt` without flipping support status: a wasm profile can
  be generated and fail at the graph stage by design, but the frontend records
  exactly where it fails and why.
- Pin the Wasm toolchain: LLVM/Clang/LLD version and flags for
  `wasm32-unknown-unknown`; decide Emscripten vs. raw wasm target (start
  Emscripten for libc); record the chosen `--table-base`, memory layout, and
  TLS ABI.
- Freeze the non-overlapping linear-memory layout: static `.data`/`.bss`,
  initial C stack, single-thread TLS block, general allocator arena, low-4-GiB
  managed heap arena. Export bounds; fail startup on overlap.
- Gate: `tools/build_art.py` runs end to end for a wasm32 profile and stops at
  the documented point.

### M1 — Switch interpreter boot (the decisive go/no-go)

- `libartbase` + DEX parsing/verifying for Wasm.
- Replace `ExecuteSwitchImplAsm` with a Wasm C++ wrapper; call
  `ExecuteSwitchImplCpp` directly; keep the `ShadowFrame`; disable
  switch-to-native-quick transitions.
- PosixShim boot-critical slice: console, clocks, entropy, environment,
  anonymous memory; explicit failures for process/signal/executable-mapping/
  dynamic-loader calls.
- Preload boot JAR/DEX into a synchronous packaged-asset VFS.
- Imageless boot (`-Xint`, no OAT/image); `HelloWorld` through the switch
  interpreter.
- Statically register the minimum libcore JNI surface in `runtime.wasm`;
  `InterpreterJni` calls through a typed registry (no raw `dlsym`-style casts).
- Explicit null and stack-depth exceptions.
- Gate: imageless HelloWorld in a browser Worker, all ART-in-Wasm.

### M2 — Offline AOT mechanics

- Decouple HGraph construction from physical-ISA codegen; pass compiler
  capabilities directly.
- Translate arithmetic, comparisons, branches, loops, returns to Waffle SSA;
  `wasm-tools validate`; differential switch-vs-AOT execution per method;
  irreducible DEX control flow through Waffle's reducifier.
- No allocation/GC/virtual dispatch/monitors/JNI/threads required at this
  stage.
- Gate: each compiled method produces identical results via switch and AOT.

### M3 — Module and invocation ABI

- Instantiate `runtime.wasm` + `classes-aot.wasm` with one memory and one
  table; slot 0 reserved for null; declared table maximum; reject duplicate/
  zero/out-of-range AOT slot assignments; install methods via active element
  segments.
- `WasmMethodEntry` descriptor (execution kind, table slot, metadata index,
  body ID) wired into dispatch; switch-to-AOT, AOT-to-switch, direct
  AOT-to-AOT, exception returns all exercised.
- Deterministic rejection of mismatched artifact manifests.
- Gate: mixed execution end to end on a small DEX program.

### M4 — Managed semantics (GC correctness)

- Allocation and class/string resolution helpers.
- Precise root spilling at every GC/suspend point; stress GC while alternating
  switch and AOT frames.
- Walk explicit AOT and interpreter frames without an engine return PC;
  resolve AOT metadata via safepoint IDs.
- DEX catch handlers, virtual/interface dispatch, monitors, class
  initialization.
- Stack traces and reflection across mixed execution modes.
- Gate: GC stress + mixed-mode stack traces pass.

### M5 — Useful runtime expansion

- Selective offline AOT (profile or filter); interpret everything else.
- Expand the static JNI registry and browser capability layer.
- OPFS persistence and the capability-Worker/`SharedArrayBuffer` bridge with
  cancellation/error semantics.
- Outbound Trojan-over-WSS TCP/UDP, Wasm-owned framing, DNS over the relay,
  readiness table.
- Gate: a useful single-threaded browser runtime with GC, reflection, ICU,
  selective AOT, curated networking.

### M6 — Threads (mandatory admission gate)

- Shared linear memory, atomics, per-Worker C stacks and TLS blocks, one
  thread-safe allocator, one shared static-data init protocol.
- pthread/TLS/futex integration; `Runtime::Start` daemon threads, thread pool,
  GC coordination all working.
- Cross-origin isolation deployment (COOP/COEP) for `SharedArrayBuffer`.
- wasm64 expansion after wasm32 correctness gates pass.
- Gate: full thread contract proven; only then may the profile's support status
  leave `impossible_under_current_art_contract`.

## Code-level first steps (where to start editing)

1. **`tools/bp2cmake/bp2cmake/target.py`** — the Wasm profiles already exist.
   Add an evidence-gated status transition: a `wasm32` profile becomes
   `experimental` only when M1's imageless boot gate passes. Record the gate
   in the profile reason field. This is the smallest, safest first change.
2. **`native/CMakeLists.txt`** — add a `wasm` branch to the platform
   admission gate, wired to a new `ART_TARGET_BUNDLE_ROOT`-style policy for
   the wasm toolchain and a runner policy for browser gates. Keep it failing
   closed until the target graph actually builds.
3. **`vendor/art/runtime/interpreter/interpreter_switch_impl.h`** — the
   switch interpreter is the first executable milestone. Replace the
   assembly wrapper with a direct C++ call path (Wasm), keep `ShadowFrame`,
   disable quick transitions. This is the single most important early diff
   because it unblocks M1's HelloWorld.
4. **`vendor/art/runtime/art_method.h`** — introduce the execution
   descriptor side table (or, for the fork, a Wasm-specific field) and route
   `Invoke()` through it. Do this alongside M1 so the interpreter never
   installs native-code pointers.
5. **`vendor/art/compiler/optimizing/optimizing_compiler.cc`** — decouple
   HGraph construction from physical-ISA code generation (M2 prerequisite).
6. New: **`compat/` and `overlay/` PosixShim skeletons** — the versioned
   `PosixShimAbi` with implemented/virtualized/unsupported classification,
   and the capability-import surface, started in M0/M1.

## Risks and open decisions

| Risk/decision | Stance |
|---|---|
| Engine table64 ABI for wasm64 C++ function pointers | wasm32 first; browser table64 is a separate wasm64 platform gate |
| Waffle maturity (experimental, pinned revision) | pin exact revision behind a project-owned abstraction; it removes only CFG/stackification work, not ART runtime effort |
| Cross-origin isolation availability | hard capability requirement for threads; a research runtime may stay single-threaded and preloaded-only, but that never admits the target |
| Compiled-method performance | uniform-signature ABI first; shorty buckets later; selective AOT means most code is interpreted initially |
| JVMTI/debugging | switch-only debugging initially; compiled-code JVMTI stays disabled |
| Emscripten vs. raw toolchain | Emscripten for bring-up libc; all calls behind `PosixShimAbi`; move correctness-sensitive state into Wasm |

## Scale

The feasibility analysis's rough numbers stand: several engineer-weeks for
`libartbase`+DEX on Wasm; 6-12 engineer-months to imageless switch-interpreter
HelloWorld with core JNI cross-compiled; 6-12 more for mixed switch/AOT
invocation, exceptions, and precise root spilling; 6-18 for POSIX/sockets/OPFS;
6-18 for threads; 2-4 engineer-years total to a useful browser runtime; parity
with current ART is a research-scale redesign. Waffle shortens the generic
CFG-to-Wasm work only.

## Bottom line

Run ART in Wasm by changing the contract, not by pretending Wasm functions are
instruction pointers. Switch interpreter first, offline Wasm AOT second, GC
roots and exceptions third, threads last. Build everything into one Wasm
guest; keep the browser at arm's length behind a curated PosixShim. The first
commit is a hello-world through the C++ switch interpreter inside a Worker;
everything else is engineered in service of making that prove out.
