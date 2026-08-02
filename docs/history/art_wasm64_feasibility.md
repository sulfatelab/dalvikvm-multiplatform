# Browser ART WebAssembly switch-interpreter, AOT, and POSIX feasibility analysis

Status: feasibility reassessment

Date: 2026-08-01

## Executive conclusion

A full ART port preserving the current OAT, physical-ISA quick-code, JIT,
JNI-loading, POSIX, threading, fault, and DSO contracts is not presently
feasible in browser wasm64.

A restricted ART-derived runtime with only the C++ switch interpreter and
build-time WebAssembly AOT is technically feasible, but it would be a
substantial fork with a new compiled-method contract:

- the portable C++ switch interpreter for fallback and dynamically loaded DEX;
- offline DEX-to-Wasm AOT for a packaging-time closed world;
- imageless DEX boot;
- ART, libcore JNI implementations, ICU/OpenJDK C/C++, libc compatibility, and
  POSIX simulation all cross-compiled into Wasm;
- explicit fault checks;
- custom linear-memory allocation; and
- initially single-threaded or tied to a specific browser/engine threading
  model.

The repository's existing classification of `wasi-wasm64` as
`impossible_under_current_art_contract` is accurate. The important
qualification is `current_art_contract`: an offline compiler that emits normal
Wasm functions, a function-table-based method entrypoint, and a new artifact
format avoids ART JIT memory, but it is not current `dex2oat` or OAT.
`wasi-wasm64` is not the proposed product target; the product is a browser
profile with JavaScript capability imports and a Wasm-resident POSIX
simulation.

The deployed runtime is Wasm-only: there is no physical-CPU `native` layer in
the deployed ART/application architecture. No ART, libcore, ICU/OpenJDK,
application JNI, or POSIX behavior has a physical-ISA executable or shared
library fallback. JavaScript is limited to browser capability imports, and any
machine code generated internally by the browser's Wasm engine is inaccessible
to ART. The offline packaging compiler is a build tool and is not part of the
deployed runtime.

The resulting feasibility judgment is:

| Goal | Judgment |
|---|---|
| Cross-compile current ART, OAT, and `dex2oat` unchanged | No-go |
| Convert DEX to class files and use an existing Java-to-Wasm runtime | Feasible for many applications, but this replaces ART semantics |
| Direct DEX/ART HGraph to portable Wasm with switch fallback | Conditional go for a research prototype |
| AOT-compile newly loaded DEX inside the Wasm guest | No-go while runtime code generation is disabled |
| Treat raw `&func` as both callable code and a linear-memory pointer | No-go; it is a function-table slot, not a code address |
| Use a bounded synthetic code-address view with explicit slot translation | Feasible as a compatibility layer, not as executable memory |
| Depend on a sparse or overcommitted 1-TiB browser Memory64 | No-go; browser Wasm exposes contiguous memory and currently limits runtime size to 16 GiB |
| Curated browser POSIX simulation for ART/libcore | Conditional go with an explicit supported API contract |
| Transparent Linux/POSIX process, raw-socket, signal, and VM compatibility | No-go in an ordinary browser |
| Preserve full Android runtime, JNI, threading, JVMTI, and GC behavior | Research-scale redesign |

## DEX, class files, and the stack/register distinction

DEX is register-based, while JVM bytecode and core WebAssembly use an operand
stack encoding. This is not a fundamental obstacle. Wasm also has typed locals,
and compiler engines normally lower its operand stack to SSA and machine
registers. A DEX compiler can map virtual registers to SSA values or Wasm
locals, then stackify expressions while emitting the final module.

Converting ordinary `.dex` back to semantically equivalent `.class` files is
possible; dex2jar and Enjarify demonstrate this. It is not a faithful or
universal reversal of D8/dx:

- the original JVM operand-stack layout, constant-pool organization, stack
  maps, and compiler structure no longer exist and must be reconstructed;
- optional debug/source metadata and annotations can be incomplete or lost;
- unusual type merges, exception control flow, oversized methods, optimized
  or quickened input, and class-file limits need special handling; and
- Android library, reflection, object-layout, GC, and JNI semantics do not
  become OpenJDK semantics merely because the instructions are in a class file.

An existing class-to-Wasm compiler typically brings its own class library,
object model, garbage collector, reflection policy, and JNI interface. That
is useful for a standalone experiment, but the result is Java-on-Wasm rather
than ART-on-Wasm.

For this project the preferred route is direct DEX to SSA to Wasm. ART already
constructs basic blocks and SSA from DEX virtual registers in
[`builder.cc`](../../vendor/art/compiler/optimizing/builder.cc). Reusing that
front end retains DEX verification, resolution, Android semantics, and a common
authoritative DEX representation for the switch interpreter.

## Why the current tree cannot simply be cross-compiled

| Area | Finding |
|---|---|
| Toolchain | LLVM recognizes `wasm64` and Emscripten exposes browser Memory64, but the usable combination of C/C++ ABI, browser engine, function tables, exceptions, Workers, shared memory, and required compatibility libraries must be validated. WASI SDK limitations are not the deployment contract because the target is the browser. |
| Build frontend | [`native/CMakeLists.txt`](../../native/CMakeLists.txt) rejects anything except Linux or Windows. The registered Wasm profiles deliberately fail before graph generation in [`target.py`](../../tools/bp2cmake/bp2cmake/target.py). |
| ART architecture | [`instruction_set.h`](../../vendor/art/libartbase/arch/instruction_set.h) knows only ARM, ARM64, RISC-V64, x86, and x86-64. Under wasm64, `kRuntimeISA` becomes `kNone`. The current tree contains 276 ISA switch cases across 23 runtime/compiler files. |
| Interpreter | The portable C++ switch interpreter exists, which is encouraging, but even it enters through an architecture-specific assembly/CFI wrapper in [`interpreter_switch_impl.h`](../../vendor/art/runtime/interpreter/interpreter_switch_impl.h). There is no Wasm quick-invoke, JNI, context, frame, TLS, or long-jump implementation. |
| Compiler | [`code_generator.cc`](../../vendor/art/compiler/optimizing/code_generator.cc) has no WebAssembly backend. HGraph construction is also currently entered only after creating a physical-ISA code generator. JNI calling conventions, trampolines, register allocation, unwind metadata, and runtime entrypoints are similarly ISA-specific. |
| Executable code | ART assumes generated code is byte-addressable executable memory. `OatQuickMethodHeader` physically precedes its machine-code bytes and is recovered by pointer subtraction in [`oat_quick_method_header.h`](../../vendor/art/runtime/oat/oat_quick_method_header.h). Wasm functions live in code sections/function tables, not linear memory. |
| Method entrypoints | `ArtMethod` stores a physical-ISA quick-code pointer. Wasm function references cannot be stored and recovered as linear-memory code pointers. The port needs an execution-kind/side-table entry and a function-table slot or a universal AOT dispatcher. |
| JIT memory | ART requires executable mappings, dual RW/RX views, `mprotect`, `memfd`, and fixed mappings; see [`jit_memory_region.cc`](../../vendor/art/runtime/jit/jit_memory_region.cc). WebAssembly linear memory has no executable pages or per-page protection. |
| Fault handling | ART relies on recoverable `SIGSEGV`/`SIGBUS` contexts, guard pages, and PC/SP rewriting. Browser Wasm has traps rather than resumable POSIX faults; Emscripten explicitly does not support POSIX signals. |
| OAT/AOT | Current OAT loading is ELF/physical-ISA-code-oriented. A WebAssembly module cannot be copied from an OAT mapping into linear memory and called like physical-ISA instructions. Some metadata concepts can be reused, but supporting AOT requires a new artifact, linker, metadata, entrypoint, and stack-walking model. |
| AOT GC roots | Managed references held only in Wasm locals are invisible to ART's collector. Every allocation, suspend point, monitor operation, or runtime call that can trigger GC must spill live references into an ART-visible shadow frame or explicit root stack. |
| JNI/DSOs | Startup dynamically loads `libicu_jni`, `libjavacore`, and `libopenjdk` in [`runtime.cc`](../../vendor/art/runtime/runtime.cc). In this design their C/C++ implementations are cross-compiled into Wasm and registered statically; no physical-CPU DSO or physical-ISA JNI fallback is permitted. |
| POSIX surface | ART, libcore, ICU, and OpenJDK expect files, descriptors, memory maps, threads, futexes, clocks, sockets, polling, signals, process identity, and dynamic loading. These APIs need a Wasm-resident compatibility layer over narrow browser capabilities, with explicit unsupported semantics where faithful simulation is impossible. |
| Heap references | Managed references remain raw 32-bit compressed pointers even in a 64-bit ART build; see [`object_reference.h`](../../vendor/art/runtime/mirror/object_reference.h). Therefore the managed heap still has to reside below 4 GiB. wasm64 does not automatically give ART a larger Java heap. |

The repository already records essentially the same architectural boundary in
[`unified_art_build.md`](../../unified_art_build.md).

## Proposed execution architecture

The viable AOT design compiles DEX in an offline packaging environment, not
inside the Wasm guest. DEX remains present and authoritative for class
metadata, verification, reflection, debugging, and switch-interpreter fallback.

```text
                      offline packaging compiler
                         +---------------------------+
DEX -- verify/resolve --+--> retained DEX/metadata --+--> switch interpreter
                       |                             |
                       +--> HGraph/SSA --> Wasm IR --+--> classes-aot.wasm
                         +---------------------------+

deployment:

runtime.wasm
  owns and exports ART linear memory, method table, and runtime helpers

classes-aot.wasm
  imports the same memory and method table
  installs compiled methods into reserved table slots
  calls ART helpers through an explicit C ABI
```

The two modules can later be statically combined, but separate core modules are
useful for the prototype. Core Wasm permits an AOT module to import memory and a
function table, and active element segments can install its functions into that
imported table during instantiation. Browser JavaScript instantiates
`runtime.wasm` first and `classes-aot.wasm` second.

### Whole-runtime Wasm boundary

In this document, ART-on-Wasm means that the whole language runtime is inside
the Wasm guest:

- ART runtime, verifier, class linker, interpreter, GC, and AOT dispatch;
- libcore JNI-declared implementations;
- ICU and OpenJDK C/C++ support code;
- allocator and libc compatibility code;
- the virtual file-descriptor, filesystem, socket, polling, clock, entropy,
  Worker/thread, and other POSIX simulation state; and
- all application JNI implementations admitted by the product.

Every item above is compiled to Wasm and shares the same linear-memory object
model. There are no physical-CPU ART methods, physical-CPU shared libraries,
platform JNI plugins, or browser callbacks implementing Java/library behavior
as an escape hatch. If a Java method is declared `native`, that word describes
its JNI boundary; its implementation is still Wasm code.

The embedding supplies only narrow browser capability primitives that cannot be
implemented inside the guest, such as accessing an allowed browser-backed file,
obtaining time or entropy, sending network data, scheduling a Worker, or
waiting for an event. Browser JavaScript implements those primitives, but it
does not own ART objects, perform Java dispatch, run libcore algorithms, or
provide an alternate physical-CPU runtime.

A Wasm engine may internally translate validated Wasm to physical CPU
instructions. That is an engine implementation detail outside ART's
architecture. The guest cannot address that code, load it as OAT, call a
physical-CPU DSO, or use it as a second method implementation.

Direct browser imports are the simplest initial capability boundary. The
component model could describe a later external interface, but it is not
appropriate for per-method ART calls because canonical ABI lifting/copying does
not preserve raw managed pointers or the shared ART heap representation.

### Method entrypoint and call ABI

Current quick entrypoints cannot be reused. For the initial port, keep a
Wasm-specific side table keyed by `ArtMethod*` rather than forcing a Wasm
function reference into the existing physical-ISA quick-code pointer field:

```text
execution kind: switch | wasm-aot
AOT slot:       function-table index
metadata:       DEX identity, DEX-PC map, root/safepoint data
```

Every compiled method should initially have one uniform Wasm signature, for
example:

```text
(thread_ptr, art_method_ptr, shadow_frame_ptr, result_ptr) -> status
```

The uniform signature keeps all AOT methods in one table and makes transitions
between compiled and interpreted methods explicit. A later optimized ABI can
introduce signature buckets based on the DEX shorty.

Static and direct calls may be emitted as direct Wasm calls when the target is
fixed. Virtual and interface calls must resolve an `ArtMethod` through ART,
inspect its execution kind, and either use `call_indirect` on its AOT slot or
enter the switch interpreter.

### Code addresses, function pointers, and a synthetic address view

#### Current ART assumes addressable code

Current ART's quick/OAT contract effectively assumes that code participates in
the process virtual-address space:

- `ArtMethod::PtrSizedFields` stores both the overloaded `data_` value and
  `entry_point_from_quick_compiled_code_` as `void*` in
  [`art_method.h`](../../vendor/art/runtime/art_method.h). For JNI-declared
  methods `data_` can itself be a callable JNI entrypoint.
- physical-ISA backends load the quick entrypoint and branch to the loaded
  address; for example, ARM64 does this in
  [`code_generator_arm64.cc`](../../vendor/art/compiler/optimizing/code_generator_arm64.cc).
- `OatQuickMethodHeader::FromCodePointer()` subtracts from a code pointer,
  `NativeQuickPcOffset()` subtracts the entrypoint from a PC, and `Contains()`
  performs address-range tests in
  [`oat_quick_method_header.h`](../../vendor/art/runtime/oat/oat_quick_method_header.h).
- `OatFile::OatMethod` computes a code pointer as `begin_ + code_offset_` and
  dereferences the header immediately before it in
  [`oat_file-inl.h`](../../vendor/art/runtime/oat/oat_file-inl.h).
- the quick-frame walker reads a physical return PC from a fixed frame offset
  and uses it to locate frame metadata in
  [`stack.cc`](../../vendor/art/runtime/stack.cc).

This is a hard requirement of the current quick/OAT ABI, not a fundamental ART
language or GC requirement. A Wasm port can remove it, but only by replacing
quick invocation, header discovery, PC-to-stack-map lookup, exception transfer,
and compiled-frame walking together. Merely changing the value stored in
`ArtMethod` is insufficient.

#### What `(uint64_t)&func` means in Wasm

Core Wasm has separate index spaces and no byte address for a function:

| Value | Meaning |
|---|---|
| module function index | Module-local target for a direct `call`; includes imported and defined functions |
| function-table index | Slot consumed by `call_indirect`; this is the usual LLVM C function-pointer representation |
| linear-memory address | Byte offset consumed by loads and stores; it cannot name executable Wasm code |
| engine code location | Private browser-engine implementation detail, inaccessible to the guest |

The integer cast is toolchain ABI behavior rather than a portable C++ promise.
With Clang 21.1.8 and LLD checked on 2026-08-01, a small linked test produced:

```text
                                 wasm32                    wasm64
&target representation           i32 table slot            i64 table64 slot
(uint64_t)&target                zero-extended slot         i64 slot
target module function index     0                          0
target function-table slot       1                          1
```

The wasm64 object used an `R_WASM_TABLE_INDEX_SLEB64` relocation, and the linked
table had the table64 flag. Thus `&target == 1` in the example even though the
function index was `0`. A cast to `void*` preserves that numeric table-slot
representation under this ABI; dereferencing the result makes a linear-memory
access at that number, not a read from the function's code.

Memory64 and table64 are distinct features in core Wasm even though the default
LLVM wasm64 C ABI currently uses both. The project-owned ART AOT table can keep
slots as `uint32_t` while the admitted browser table is smaller than 2^32 and
can be a separate table32 import. This does not by itself remove table64 from a
whole C++ wasm64 runtime: ordinary C/C++ function pointers and virtual calls
compiled by the tested LLVM ABI use table64. Browser table64 support is
therefore a separate wasm64 platform gate unless the toolchain ABI is changed.

#### Index zero, null, and the usable range

Function index `0` is valid: index spaces are zero-based. Table slot `0` is also
valid in core Wasm and could contain a function, but LLVM/LLD's C ABI reserves
it for the null-function-pointer convention. LLD's default `--table-base` is
`1`; Clang lowers a null C function pointer to integer zero. Calling an empty or
type-mismatched table slot through `call_indirect` traps.

For the LLVM C ABI the useful value range is therefore:

```text
0                           null function pointer
1 .. table.size - 1         currently installed callable slots
table.size .. table.max - 1 slots that may be installed after table growth
```

The WebAssembly JavaScript API caps a browser table at 10,000,000 entries, so
the browser-wide maximum slot is currently 9,999,999. An ART package should not
reserve against that maximum. It should declare a smaller explicit table
maximum, reserve nonzero slot ranges in the AOT manifest, and reject overlapping
or out-of-range element segments. The function-table number is not stable
across independent modules unless they import the same table and share one slot
allocation contract.

#### Why one fake 64-KiB page does not unify the spaces

Giving a table slot and a linear-memory offset the same integer does not join
their namespaces:

```text
call_indirect N    selects table[N]
load from N        reads linear_memory[N]
```

One 64-KiB linear-memory page can give a one-byte alias only to slots 0 through
65,535. Covering the browser table limit at one byte per slot would require 153
pages, approximately 9.56 MiB. That still does not provide code bytes or room
for a distinct `OatQuickMethodHeader` before every adjacent slot. Spacing table
slots far enough apart for headers and virtual PC ranges creates a large,
sparse, but physically dense function table and quickly reaches browser table
limits.

The scheme also cannot create engine return PCs. Wasm calls keep their actual
return locations on an opaque engine stack. ART cannot derive a method header,
stack map, or catch target by subtracting from that location, even if the
method's entrypoint has a matching fake linear-memory number.

#### Feasible compatibility form

If incremental porting benefits from address-like identities, use a bounded
synthetic code-address view whose values are never called directly:

```text
WasmMethodEntry
  execution_kind: switch | wasm-aot | jni-wasm
  abi_type:       uniform managed ABI or signature bucket
  table_slot:     actual shared-table index
  metadata_index: DEX-PC, root, exception, and debug metadata
  virtual_entry:  optional pointer into a linear-memory descriptor arena
```

For example:

```text
virtual_entry = code_view_base + method_id * descriptor_stride

linear memory:
[Wasm method descriptor / compatibility header][virtual entry marker]
                                                  ^
                                                  address-like ART identity
```

Invocation must resolve the descriptor and execute `call_indirect table_slot`;
it must never cast `virtual_entry` to a C function pointer. Conversely, raw
`&func` must never be passed to `OatQuickMethodHeader::FromEntryPoint()` or
otherwise dereferenced as code data.

A synthetic virtual PC may be `virtual_entry + safepoint_offset`, but the AOT
compiler must explicitly publish it, or preferably publish a safepoint ID, in a
linear-memory managed frame. Such a virtual PC is useful only for compatibility
lookups; it is not the browser engine's PC. Size the descriptor arena from a
declared method-capacity and descriptor stride:

```text
code-view pages = ceil(method_capacity * descriptor_stride / 65,536)
```

This approach can preserve selected pointer identity, range, and header APIs
while they are migrated. It does not preserve executable OAT, physical quick
frames, signal contexts, or code-byte inspection.

#### Mixed AOT and switch-interpreter dispatch

The deployed runtime remains mixed AOT/interpreter even though nterp, mterp,
JIT, OSR, and deoptimization are disabled:

| Transition | Wasm behavior |
|---|---|
| switch interpreter to AOT | Resolve `ArtMethod`, construct/publish the AOT root frame, then `call_indirect` its table slot |
| AOT to switch interpreter | Resolve `ArtMethod`, create/link an interpreter `ShadowFrame`, and enter `ExecuteSwitch` |
| AOT to AOT, virtual/interface | Resolve the target method, validate its execution kind and ABI type, then `call_indirect` |
| AOT to AOT, fixed target | A direct Wasm call is optional when class initialization, instrumentation, and artifact linking make the target invariant |
| Java JNI declaration to C/C++ Wasm | Use a generated registry and a typed thunk/table slot; there is no physical-CPU JNI address |

Current ART already chooses interpreter-to-interpreter or
interpreter-to-compiled bridging in
[`common_dex_operations.h`](../../vendor/art/runtime/common_dex_operations.h),
but its compiled bridge eventually enters the physical quick ABI. The Wasm
port should retain the decision and argument-marshalling logic while replacing
that final invocation.

The existing `ManagedStack` supports either shadow frames or physical quick
frame pointers in each fragment; see
[`managed_stack.h`](../../vendor/art/runtime/managed_stack.h). Wasm AOT frames
need an explicit linear-memory representation containing `ArtMethod*`, current
DEX PC or safepoint ID, reference roots, and metadata index. A synthetic code
address does not make the opaque Wasm engine stack walkable.

#### Memory64 is not sparse virtual memory

Memory64 widens linear-memory addresses. It does not expose `mmap`-style holes
or guest-controlled virtual-memory overcommit. The current memory is logically
the contiguous range from zero through `memory.size * 65,536 - 1`, and
`memory.grow` extends only its end. An engine may reserve address space and
physically commit zero-filled pages lazily, but this is an engine optimization
on which ART cannot rely.

The WebAssembly JavaScript API currently limits the runtime size of a 64-bit
memory to 262,144 pages, or 16 GiB. A 1-TiB memory would require 16,777,216
pages and is therefore not a browser deployment option. Placing a synthetic
code view at a 1-TiB offset would first require growing through the entire
logical gap; there is no sparse reservation operation. Multiple memories do
not make an ordinary C/C++ pointer carry a memory number and therefore do not
restore a unified C address space.

#### C/C++ data-object addresses are linear-memory offsets

For the tested LLVM wasm64 C/C++ ABI, every addressable data object is in
linear memory and an ordinary pointer is an `i64` byte offset into that memory:

| Object | Address form | Lifetime and initialization |
|---|---|---|
| addressable automatic local | `__stack_pointer + frame_offset` | Valid until the C/C++ frame returns |
| pthread TLS object | `__tls_base + TLS-relative offset` | Per Worker/thread TLS-block lifetime; `.tdata` copied and `.tbss` zero-filled |
| `malloc()` allocation | Allocator-selected offset, normally in the arena beginning at or after `__heap_base` | Valid until `free()` or a moving `realloc()`; reused addresses are permitted |
| `.data` object | Linker-assigned static offset | Initialized from a Wasm data segment |
| `.bss` object | Linker-assigned static offset | Initially zero; may require no payload or an explicit fill |

This is the data-side unified address space that ART can use. An `ArtMethod*`,
`Thread*`, heap metadata pointer, addressable `ShadowFrame`, C++ object, TLS
object, and allocator result can all be regular pointers into the same imported
memory. It does not include Wasm functions or the browser engine's stacks.

##### Addressable C/C++ stack versus engine stack

When the address of an automatic `int32_t` observably escapes, Clang creates a
linear-memory C stack slot. A wasm64 test lowered `&local` approximately as:

```text
frame = __stack_pointer - 16
linear_memory[frame + 12] = local
&local = frame + 12
```

`__stack_pointer` is a mutable Wasm global containing a linear-memory offset;
the global itself is not stored in linear memory. If the address does not
escape, the optimizer may keep the value in a Wasm local and eliminate the
memory slot under the as-if rule. Wasm locals, the operand stack, and the
engine call stack have no C address. Taking a source-language address
materializes the object in the linear-memory C stack; it does not expose an
engine frame or return PC.

Consequently, the switch interpreter's addressable C++ frames can reside in
linear memory, but AOT references held only in Wasm locals remain invisible to
ART GC. AOT methods still need explicit root spills and published managed
frames.

##### TLS is a per-thread linear-memory block

With `-pthread` or the equivalent POSIX thread model, Clang generated an
`R_WASM_MEMORY_ADDR_TLS_SLEB64` relocation and calculated:

```text
&tls_object = __tls_base + tls_relative_offset
```

The linker groups initialized TLS into a `.tdata` template and zero TLS into
`.tbss`. Each Worker/thread receives a separate suitably aligned block in the
shared linear memory, initializes it from that template, and sets its own
`__tls_base`. Browser Workers instantiate their own module globals while
sharing the `WebAssembly.Memory`, so equal TLS-relative offsets yield distinct
addresses when the TLS bases differ. The blocks are not protected from other
threads; isolation is an ABI and language rule.

Without the pthread thread model, the tested compiler lowered `_Thread_local`
objects as ordinary single-thread static storage with absolute linear-memory
addresses. That is adequate only for the single-managed-thread bring-up and
must not silently persist when Workers are introduced.

On the non-Bionic ART path, `Thread::Current()` reads the C++ `thread_local`
`Thread::self_tls_`; see
[`thread-current-inl.h`](../../vendor/art/runtime/thread-current-inl.h) and
[`thread.h`](../../vendor/art/runtime/thread.h). Under the pthread wasm64 ABI,
this becomes an entry in the per-Worker linear-memory TLS block. ART's pthread
key, direct `thread_local`, Worker lifecycle, and `__tls_base` initialization
must agree on attachment and detachment.

##### Static storage and allocator storage

C/C++ `.data` and `.bss` section names exist in relocatable Wasm objects for
the linker. In the final module they denote reserved ranges of linear memory,
not ELF mappings or protected OS pages. In a shared-memory link, LLD may emit an
atomic start routine so one Worker initializes `.data` and zeros `.bss` exactly
once.

`malloc(size_t)` takes an `i64` size and returns an `i64` linear-memory pointer
under wasm64. A null result is zero. Existing allocations retain their numeric
offsets across `memory.grow`; growth extends the memory rather than relocating
objects. `free()` invalidates the object and permits address reuse, while
`realloc()` may return a different offset. JavaScript receives an exported
`i64` pointer as a `BigInt` and must use it only as an offset into the matching
exported `WebAssembly.Memory`, never as a browser process address.

The exact layout is linker- and allocator-specific. One checked two-page test
placed the initial TLS base at 1,024, initialized TLS at offsets 1,024 and
1,028, ordinary `.data` at 1,032, `.bss` at 1,036, and the initial C stack
pointer at 66,592. These numbers are evidence of one layout, not an ABI to
hardcode.

##### Shared-memory and multi-module rules

Every Worker needs a non-overlapping C stack and TLS block. Threads may share
ordinary globals and a malloc heap, but the allocator must be thread-safe. Two
independent allocators must never manage overlapping regions of the same
memory.

Likewise, `runtime.wasm` and `classes-aot.wasm` can exchange ordinary pointers
only when they import the same memory and follow one static-region, stack, TLS,
and allocator layout. Independently linked data segments need explicit,
non-overlapping bases. Prefer one allocator exported by `runtime.wasm`; the AOT
module should call it or use manifest-reserved arenas rather than creating a
second unconstrained heap.

`memory.grow` preserves guest numeric offsets, although JavaScript typed-array
views over the old buffer may need to be recreated. Multiple memories do not
change the default C pointer representation: a plain `i64` pointer does not
carry a memory index.

##### ART managed-heap constraint

General ART C++ allocations, runtime metadata, stacks, TLS, and synthetic code
descriptors may use wasm64 linear-memory pointers. Managed Java references are
still compressed 32-bit offsets, so Java objects must use a dedicated arena
entirely below 4 GiB. An arbitrary `malloc()` result cannot be converted to a
managed reference unless the allocator guarantees that range and all ART heap
alignment and GC contracts.

The resulting address model is:

```text
linear memory, i64 byte offsets:
  addressable C/C++ stack, TLS, malloc heap, .data, .bss,
  ART objects and metadata, explicit AOT/shadow frames

function table:
  C/C++ function pointers and Wasm AOT callable slots

engine-private state:
  operand stack, call stack, return PCs, compiled machine code
```

### AOT artifact model

Do not treat a Wasm module as executable bytes inside a conventional OAT file.
Define a versioned Wasm AOT artifact instead:

| Artifact | Purpose |
|---|---|
| Original DEX/JAR | Authoritative bytecode and metadata; interpreter fallback |
| `classes-aot.wasm` | Portable build-time-compiled method functions |
| Manifest/custom sections | Runtime ABI version, pointer width, required Wasm features, DEX and boot-class-path hashes, method-to-table-slot map, DEX-PC maps |

The loader must reject a module if its runtime ABI, DEX checksums, boot class
path, pointer width, feature set, or compiler metadata do not match. Existing
OAT concepts such as class compilation status, method indexes, stack maps, and
profile-guided selection can inform the format, but the OAT binary layout and
quick-code loader should not be reused.

A browser engine may internally cache compiled Wasm, but that cache is never
loaded, inspected, or invoked by ART and cannot replace `classes-aot.wasm`.
Wasmtime `.cwasm` is not a product artifact; it is relevant only to offline
validation experiments.

## Compiler backend

### Reuse ART HGraph, not class files

The preferred compiler pipeline is:

```text
DEX verifier/resolution
  -> ART HGraph SSA
  -> backend-independent optimization subset
  -> explicit lowering of ART operations to runtime-helper calls
  -> Wasm-oriented SSA/CFG
  -> structured core Wasm
```

HGraph preserves DEX semantics and already models control flow, values, invokes,
checks, and environments. However,
[`optimizing_compiler.cc`](../../vendor/art/compiler/optimizing/optimizing_compiler.cc)
currently creates a physical-ISA `CodeGenerator` before building HGraph, and several
builder paths consult it for compiler options and target capabilities. The Wasm
compiler must either:

1. decouple HGraph construction from physical-ISA code generation and pass compiler
   capabilities directly; or
2. provide a minimal Wasm IR code-generator adapter used only to make the
   frontend and selected optimization passes available.

Only clearly backend-independent optimization passes should run initially.
Allocations, class/string resolution, monitors, read barriers, suspend checks,
type checks, and unresolved or polymorphic invokes should lower to explicit ART
runtime helper imports.

### Waffle removes most CFG-to-Wasm mechanics

Bytecode Alliance's
[Waffle](https://github.com/bytecodealliance/waffle) 0.3.1 is a strong
prototype backend. It can construct a module from scratch using a block/SSA IR
and compile that IR back to Wasm. Its backend already implements:

- reducification of irreducible loops through context-sensitive block
  duplication;
- recovery of structured Wasm `block`, `loop`, and `if` control flow;
- treeification of single-use SSA values onto the Wasm operand stack; and
- linear-scan allocation of remaining SSA values to Wasm locals.

This directly addresses the register-based DEX to stack-encoded Wasm
translation. The proposed prototype backend is therefore:

```text
ART HGraph -> lowered Waffle FunctionBody -> Waffle backend -> core Wasm
```

Waffle also emits imports and active function element segments, so an AOT
module can populate an imported method table. It is experimental infrastructure
and should be pinned to an exact revision behind a project-owned abstraction.

The current Waffle backend hardcodes `memory64 = false`, `shared = false`, and
`table64 = false` for imported and defined memories/tables. It is therefore
well matched to a wasm32, non-threaded first prototype, but it is not presently
a wasm64/shared-memory production backend. Reaching wasm64 requires extending
Waffle's IR and backend or replacing its module emitter with a lower-level path.

### Other Bytecode Alliance components

| Project | Useful role | Does not provide |
|---|---|---|
| [`wasm-tools`](https://github.com/bytecodealliance/wasm-tools) and `wasm-encoder` | Low-level module emission, memory64/shared/table encoding, validation, printing, custom sections, and `addr2line` | A DEX frontend, ART ABI, or managed runtime |
| [Wasmtime](https://github.com/bytecodealliance/wasmtime) | Offline validation, differential testing, and module-linking experiments | The browser deployment engine, a portable Wasm code-generation backend, or any part of ART |
| [Cranelift](https://github.com/bytecodealliance/wasmtime/tree/main/cranelift) | Wasm/CLIF to physical-CPU code inside a Wasm engine | Portable Wasm output; direct DEX-to-CLIF would leave the all-ART-in-Wasm architecture |
| [Wizer](https://github.com/bytecodealliance/wasmtime/tree/main/crates/wizer) | Possible later pre-initialization of a self-contained module | Imported-memory/table snapshots, mutable reference-table snapshots, or an ART boot image |
| WIT/component tooling | External typed embedding-service boundary | Internal ART quick ABI or shared managed-pointer calls |

The only product AOT layer is DEX to regular `classes-aot.wasm`. Wasmtime AOT,
Cranelift output, and `.cwasm` are not product artifacts. They are relevant only
to offline tool evaluation and must not enter the browser runtime architecture.

## Runtime correctness requirements

Disabling nterp, mterp, JIT, OSR, and deoptimization removes runtime code
generation, executable JIT mappings, tier transitions, and much physical-ISA
unwind complexity. It does not make compiled Wasm methods ordinary ART quick
frames.

### Switch interpreter baseline

The first milestone remains imageless `-Xint` boot through the C++ switch
interpreter. The architecture-specific assembly/CFI wrapper must be replaced
with a Wasm C++ entry path. AOT should not be started until a self-contained
Wasm runtime can execute a small DEX program and JNI-declared core methods,
whose C/C++ implementations are also Wasm, through the switch interpreter.

The switch interpreter remains required after AOT exists:

- methods omitted by the offline compiler;
- methods using unsupported instructions or runtime features;
- dynamically loaded DEX unknown at packaging time;
- debugging/instrumentation cases that explicitly force interpretation; and
- safe fallback when AOT metadata validation fails for a method.

### GC roots and safepoints

Wasm engine stack maps do not describe ART managed references stored as integer
linear-memory offsets. A moving or collecting ART GC cannot discover a
reference that exists only in a Wasm local.

The baseline AOT ABI should therefore retain an ART `ShadowFrame` for every
compiled method. Scalar values may remain in Wasm locals between safepoints,
but before any operation that can allocate, suspend, block, or enter runtime
code, the compiler must:

1. spill all live managed references into the shadow frame or a dedicated
   linear-memory root stack;
2. update the current DEX PC;
3. publish precise reference-kind information; and
4. restore potentially moved references after the runtime call.

Starting single-threaded with the simplest stop-the-world collector reduces
suspension races but does not remove the need to make live roots visible.

### Java exceptions and Wasm traps

Wasm traps are terminal control transfers to the embedding boundary and are not
recoverable ART `SIGSEGV` contexts. Do not use traps to implement Java null,
array-bounds, divide-by-zero, cast, or stack-overflow exceptions.

The AOT compiler should emit explicit checks. Runtime helpers set the pending
`Thread` exception; the compiled method then transfers to the appropriate DEX
catch handler or returns an exception status to its caller. Wasm exception
handling can be investigated later, but the initial ABI should not depend on
proposal- or engine-specific unwinding behavior.

Use an explicit managed-call-depth or stack-limit check in method prologues.
Physical-ISA guard-page stack overflow recovery is not portable into the Wasm
guest.

### Stack walking, debugging, and instrumentation

Even without deoptimization, ART needs DEX-PC information for exceptions,
stack traces, GC, reflection, and interpreter transitions. Each AOT function
must preserve a mapping from Wasm code positions or explicit safepoints to DEX
PCs and materialized vregs.

Compiled-code JVMTI events, physical-PC instrumentation, OSR, and arbitrary forced
deoptimization should remain disabled in the first product. Interpreter-only
debugging can be supported through the retained DEX and shadow frames.

### JNI-declared methods and browser capabilities

ART, libcore JNI implementations, ICU, OpenJDK support code, and admitted
application JNI implementations must all be cross-compiled into the Wasm
runtime. Replace `dlopen`/`dlsym` and unrestricted `System.loadLibrary` with a
generated registry that maps Java JNI declarations to Wasm functions.

The Java `native` keyword does not authorize a physical-CPU implementation.
There is no browser path for loading a platform DSO, calling arbitrary
physical-CPU addresses, or substituting a Java method with JavaScript.
JavaScript imports
provide only narrow browser capabilities beneath the Wasm-resident libc/POSIX
simulation.

### Threads

Core Wasm threads provide shared memory and atomics, not thread creation or a
complete TLS contract. Browser threads additionally depend on Web Workers,
`SharedArrayBuffer`, and cross-origin isolation.

Start with one managed thread. Add threads only after the same engine supports
the required combination of shared memory, atomics, pointer width, TLS,
function tables, `Atomics.wait`/`notify` behavior, and Worker creation.

## Browser POSIX API simulation

The browser has no POSIX kernel. The product therefore needs a Wasm-resident
compatibility contract, not a set of physical-CPU POSIX libraries. ART and
libcore call libc/JNI code compiled into `runtime.wasm`. Calls such as `open`,
`read`, `mmap`, `pthread_mutex_lock`, `poll`, and `clock_gettime` are then
implemented by Wasm code, Emscripten JavaScript syscall shims, or a combination
of both over browser APIs. None resolves to a physical-CPU library.

```text
Java and DEX methods
        |
libcore JNI + ICU/OpenJDK C/C++            all compiled to Wasm
        |
libc entrypoints + ART OS abstractions    compiled to Wasm
        |
virtual POSIX state                        Wasm-owned where correctness needs it
        |
browser syscall/capability imports         JavaScript/Web APIs only
        |
Browser: Workers, OPFS/IndexedDB, Fetch/WebSocket, clocks, crypto
```

The JavaScript boundary is below ART and libcore. In the project-owned form,
`read(fd, ...)` is a Wasm function that validates a virtual descriptor,
enforces offsets and permissions, copies data, and returns POSIX errors. Only
when the descriptor represents a browser-backed resource does it invoke a
narrow JavaScript capability using an opaque handle. An Emscripten-first
implementation may keep more descriptor/syscall state in JavaScript, but
JavaScript still does not implement `java.io`, ART, or JNI dispatch.

### Simulation contract

The compatibility layer needs a versioned browser POSIX ABI with three explicit
classes of behavior:

| Class | Meaning |
|---|---|
| Implemented | Behavior is sufficiently equivalent for ART/libcore and has conformance tests |
| Virtualized | Behavior is deterministic and documented but differs from a real process/kernel |
| Unsupported | Returns a documented error such as `ENOSYS`, `EOPNOTSUPP`, or `EPERM`, or disables the dependent ART feature |

Correctness-sensitive calls must never be silent success no-ops. For example,
pretending that `mprotect` installed a read-only page would corrupt any GC
algorithm that relies on a later protection fault. Such an ART feature must be
rewritten with explicit metadata/checks or disabled.

### Relationship to Emscripten

Emscripten is a useful browser toolchain and provides musl-derived libc,
filesystem adapters, pthread support, and JavaScript syscall libraries. Those
are simulations over browser APIs, not physical-CPU libraries, so using them
does not violate the all-ART-in-Wasm boundary.

However, Emscripten compatibility is not automatically Linux compatibility.
Its filesystem may live partly in JavaScript, blocking operations may be
proxied to Workers, socket APIs map to browser transports, and many process,
signal, mapping, or dynamic-loader operations are absent or approximate.

Two implementation shapes are possible:

1. Link ART and the libcore/ICU/OpenJDK C/C++ code against Emscripten libc and
   adapt the existing Emscripten syscall/filesystem layer.
2. Keep a project-owned descriptor and POSIX state machine in Wasm and use
   narrow JavaScript imports only for browser resources.

The second gives ART more deterministic ownership and testing. The first is
faster for bring-up. A practical progression is to start with Emscripten, place
all calls behind a versioned `BrowserPosixAbi`, then move correctness-sensitive
state into Wasm as required. Do not mix independent Emscripten and project
descriptor namespaces without one explicit ownership/translation layer.

### API-area feasibility

| Area | Representative APIs | Browser/Wasm implementation | Judgment |
|---|---|---|---|
| Heap and anonymous mappings | `malloc`, `calloc`, `mmap(MAP_ANONYMOUS)`, `munmap` | Wasm allocator and reserved-region manager over `memory.grow`; suballocate ART heap, metadata, stacks, and virtual mappings | Feasible |
| Page protection and executable mappings | `mprotect`, `PROT_NONE`, `PROT_EXEC`, guard pages | Track virtual permissions for diagnostics and explicit checks; no executable pages and no recoverable protection faults | Semantics requiring kernel enforcement are unavailable |
| File-backed mappings | `mmap`, `msync`, `madvise` | Copy browser-backed file ranges into linear memory and flush explicitly; no true kernel page cache or arbitrary `MAP_FIXED` aliasing | Partially virtualizable |
| Descriptors and byte I/O | `open`, `close`, `read`, `write`, `pread`, `pwrite`, `lseek`, `fcntl` | Wasm descriptor table mapping integers to in-memory files, packaged assets, pipes/event objects, and opaque browser resource handles | Feasible for a defined subset |
| Filesystem metadata | `stat`, `fstat`, `lstat`, `mkdir`, `rename`, directory iteration | Virtual filesystem with packaged read-only assets plus optional OPFS/IndexedDB persistence; synthesize ownership/mode fields | Feasible with documented differences |
| Clocks and sleeping | `clock_gettime`, `gettimeofday`, `nanosleep`, timers | `performance.now` for monotonic time, `Date.now` for wall time, Worker timers and wait queues | Feasible; resolution and scheduling differ |
| Entropy | `getrandom`, `/dev/urandom` | Fill guest buffers through `crypto.getRandomValues` | Feasible |
| Mutexes, condition variables, futexes | `pthread_mutex_*`, `pthread_cond_*`, futex wait/wake | Wasm atomics and linear-memory synchronization; `Atomics.wait`/`notify` in Workers when shared memory is enabled | Conditional on browser threads; single-thread subset first |
| TLS and thread lifecycle | `pthread_create`, `pthread_join`, `pthread_key_*` | Web Workers, shared memory, Wasm TLS/runtime records, and a Wasm-owned thread registry | High complexity and requires cross-origin isolation |
| Signals and fault contexts | `sigaction`, `pthread_kill`, `SIGSEGV`/`SIGBUS` recovery | Internal cooperative events may simulate cancellation/interrupt flags; browser traps cannot provide resumable POSIX signal contexts | Fault-based ART mechanisms are unavailable |
| Polling and readiness | `poll`, `select`, `epoll`, pipes/eventfd-like waits | Wasm readiness table plus browser event delivery from another Worker; wake waiters with shared-memory atomics | Feasible for virtual handles, not arbitrary OS descriptors |
| DNS and networking | `getaddrinfo`, `socket`, `connect`, `accept`, `send`, `recv` | Curated adapters over Fetch, WebSocket, or WebTransport; Wasm socket objects hold state and buffers | Raw TCP/UDP and full POSIX socket semantics are unavailable in ordinary browsers |
| Process model | `fork`, `execve`, `waitpid`, `kill`, process groups | One virtual process; optionally synthesize PID/UID/GID. No address-space clone or arbitrary executable launch | `fork`/`exec` are unsupported |
| System identity/configuration | `uname`, `sysconf`, `getpid`, `getuid`, passwd/group lookup, environment | Deterministic browser-runtime values stored by the Wasm compatibility layer | Feasible as synthetic data |
| Dynamic loading | `dlopen`, `dlsym`, JNI library loading | Generated link-time registry of Wasm functions and data; fixed module set at packaging time | Arbitrary dynamic loading is unsupported |

The first runtime does not need every row. It needs the transitive subset used
by imageless ART boot, DEX/JAR access, the selected collector, libcore startup,
console output, clocks, entropy, and the initial test program.

### Virtual filesystem and descriptors

Use a single Wasm-owned descriptor namespace for ART and all libcore/OpenJDK
code. Each entry records a resource kind, access mode, current offset,
readiness, reference count, and either Wasm state or an opaque browser
capability handle. Candidate resource kinds include:

- packaged read-only boot JAR/DEX assets loaded before ART starts;
- in-memory files and temporary files;
- OPFS-backed persistent files;
- console streams;
- pipes/event objects used only inside the Wasm runtime;
- WebSocket/WebTransport-backed virtual sockets; and
- directory iterators and timer/event handles.

Browser objects and JavaScript references must not be embedded as ART pointers.
The browser boundary exposes integer capability handles, while ownership and
lifetime are controlled by the Wasm descriptor table.

Packaged boot assets should be available synchronously from linear memory before
`Runtime::Start`. This avoids making class loading depend on an asynchronous
browser operation. Persistent application files and networking need a separate
blocking bridge or explicitly asynchronous Java-facing design.

### Synchronous POSIX calls over asynchronous browser APIs

ART and much of libcore/OpenJDK assume synchronous C calls, while Fetch,
IndexedDB, most OPFS operations, and browser networking are asynchronous.
Calling an async JavaScript function from a normal synchronous Wasm import
cannot suspend and later resume the ART C++ stack by itself.

The credible browser strategies are:

1. Run ART in a dedicated Worker. Preload all boot-critical assets, and satisfy
   boot/runtime reads from Wasm memory.
2. For operations that must block, send a request to a separate capability
   Worker and wait on a `SharedArrayBuffer` word with `Atomics.wait`. The
   capability Worker performs the async browser operation, writes the result,
   and wakes ART.
3. Use OPFS synchronous access handles where available in dedicated Workers.
4. Keep naturally asynchronous facilities behind Java asynchronous APIs rather
   than forcing complete POSIX socket/filesystem behavior.

Asyncify, JSPI, or future stack-switching could suspend Wasm through async
imports, but this interacts with ART shadow frames, GC roots, exception state,
locks, and stack walking. It should not be the initial POSIX foundation.

The Worker/SAB bridge requires cross-origin isolation. Without it, the product
must stay single-threaded and restrict itself to preloaded/in-memory synchronous
resources plus nonblocking browser-facing APIs.

### Memory API rules

ART `MemMap` must become a Wasm region allocator. It should reserve logical
regions inside linear memory and implement anonymous mapping, alignment,
splitting, merging, and unmapping as metadata operations.

The following contracts need explicit treatment:

- `PROT_EXEC` always fails because no guest data page can become code.
- `mprotect` cannot create a recoverable fault boundary. Permission changes can
  be recorded and checked by instrumented access paths only.
- `MAP_FIXED` is allowed only within an already reserved compatible arena and
  must never overwrite unrelated Wasm runtime state.
- file mappings are copied buffers with explicit writeback, not OS page-cache
  aliases;
- `MAP_SHARED` means sharing inside the one Wasm memory, not between POSIX
  processes; and
- `madvise`, page residency, locking, and discard hints are advisory metadata or
  documented unsupported operations.

This is sufficient for heap arenas and runtime metadata only after all ART
features that require real page protection, alias mappings, fork inheritance,
or executable mappings are disabled or redesigned.

### POSIX inventory and acceptance

Before implementation, generate a symbol and source-call inventory across the
exact ART, libcore, ICU, OpenJDK, libc, and application-JNI graph. Classify each
API by caller, startup criticality, required semantics, blocking behavior, and
browser backend.

Acceptance requires:

- no unresolved POSIX symbols in the final Wasm module;
- no physical-CPU DSO imports or physical-CPU function-address escape;
- conformance tests for values, side effects, `errno`, blocking, interruption,
  and descriptor lifetime;
- explicit negative tests for `fork`, `exec`, signals, executable mappings,
  dynamic loading, and raw sockets;
- identical behavior when called from the switch interpreter or an AOT method;
  and
- startup failure when a required browser capability is absent, rather than a
  misleading partial boot.

The feasibility boundary is therefore a curated browser POSIX personality,
which is achievable, not transparent Linux compatibility, which is not.

## wasm32 before wasm64

Although this file evaluates the requested wasm64 destination, the lowest-risk
proof target is wasm32:

- ART managed heap references are already compressed to 32 bits;
- wasm64 guest C/C++ pointers do not increase the Java heap beyond 4 GiB under the
  current object-reference representation;
- Waffle currently emits only memory32, non-shared modules;
- the tested LLVM wasm64 C/C++ ABI also emits table64 for address-taken
  functions, so browser Memory64 support alone is insufficient;
- wasm32 C/C++ and engine paths are more mature; and
- a wasm32 prototype validates the switch interpreter, linear-memory allocator,
  static JNI registry, AOT ABI, table dispatch, explicit faults, and GC roots
  without coupling all failures to memory64.

The recommended progression is:

1. `browser-wasm32-emscripten`, single-threaded, imageless, and running in a
   dedicated Worker;
2. wasm32 switch interpreter plus selective Waffle-based AOT;
3. precise root spilling, exceptions, virtual dispatch, and JNI implementations
   compiled to Wasm;
4. extend or replace the Waffle emitter for memory64 and decide whether the ART
   method table remains a separate table32 table;
5. validate the complete LLVM C++ table64 ABI, including virtual calls, against
   one explicitly named browser engine/configuration; and
6. consider shared memory and threads last.

For wasm64, managed objects must still remain in a reserved low-4-GiB arena
unless ART's compressed-reference representation is separately redesigned.
Guest C/C++ runtime pointers can be 64-bit while method-table slots remain
compact integer indexes.

## Staged validation plan

### Stage 0: switch-only runtime

- Build `libartbase` and DEX parsing/verifying for the selected Wasm target.
- Freeze a non-overlapping linear-memory layout for static data, the initial C
  stack, single-thread TLS, the general C/C++ allocator, the low-4-GiB managed
  heap arena, and any synthetic code descriptors. Export or record the relevant
  bounds and fail startup on overlap.
- Verify that addresses of stack, TLS, `.data`, `.bss`, and `malloc()` objects
  are valid offsets into the one imported memory and remain valid across
  permitted `memory.grow` operations.
- Inventory the exact POSIX symbols and source calls in the selected ART,
  libcore, ICU/OpenJDK, libc, and application-JNI closure; freeze the initial
  versioned `BrowserPosixAbi` and its implemented/virtualized/unsupported
  classifications.
- Preload the boot JAR/DEX set into a synchronous packaged-asset VFS, and
  implement the descriptor operations needed to read it.
- Implement the boot-critical browser personality for console I/O, monotonic
  and wall clocks, entropy, environment/system identity, and anonymous memory;
  fail explicitly for unsupported process, signal, executable-mapping, and
  dynamic-loader operations.
- Boot imageless without OAT or an ART image.
- Run `HelloWorld` through the C++ switch interpreter.
- Cross-compile and statically register the minimum libcore JNI C/C++ surface
  inside `runtime.wasm`.
- Prove explicit null and stack-depth exceptions.

This remains the decisive initial go/no-go gate.

### Stage 1: compiler mechanics

- Refactor HGraph construction so it does not require a physical-ISA backend.
- Translate arithmetic, comparisons, branches, loops, and returns into Waffle
  SSA.
- Validate generated modules with `wasm-tools validate`.
- Differentially execute each method through switch and AOT paths.
- Support irreducible DEX control flow through Waffle's reducifier.

No allocation, GC, virtual dispatch, monitors, JNI, or threads are required at
this stage.

### Stage 2: module and invocation ABI

- Instantiate `runtime.wasm` and `classes-aot.wasm` with the same memory and
  method table.
- Reserve table slot zero for the null-function-pointer convention, declare an
  explicit table maximum, and reject duplicate, zero, or out-of-range AOT slot
  assignments.
- Install AOT methods through active element segments.
- Implement the uniform shadow-frame invocation ABI and a typed
  `WasmMethodEntry` that keeps execution kind, table slot, metadata index, and
  any synthetic address identity distinct.
- Exercise switch-to-AOT, AOT-to-switch, direct AOT-to-AOT, and exception
  returns.
- If a synthetic code-address view is retained for compatibility, prove that
  every call translates its descriptor to a table slot and that no raw table
  slot is dereferenced as linear-memory code.
- Reject mismatched artifact manifests deterministically.

### Stage 3: managed runtime semantics

- Add allocation and class/string resolution helpers.
- Spill precise roots at every possible GC/suspend point.
- Stress GC while alternating switch and AOT frames.
- Walk explicit AOT and interpreter frames without using an engine return PC;
  resolve AOT metadata through safepoint IDs or synthetic PCs published by the
  compiler.
- Add DEX catch handlers, virtual/interface dispatch, monitors, and class
  initialization.
- Verify stack traces and reflection across mixed execution modes.

### Stage 4: useful runtime and platform expansion

- Selectively AOT-compile boot and application methods using an offline profile
  or compiler filter; interpret everything else.
- Expand the static JNI registry and browser capability layer without adding a
  physical-ISA fallback.
- Add persistent OPFS storage in a dedicated Worker. Where a synchronous ART or
  libcore call must wait for an asynchronous browser operation, validate the
  capability-Worker/`SharedArrayBuffer` bridge and its cancellation and error
  semantics.
- Give every Worker a disjoint linear-memory C stack and initialized TLS block,
  and use one thread-safe allocator and one shared static-data initialization
  protocol across all module instances.
- Add the Wasm-owned readiness table and only the polling and Fetch,
  WebSocket, or WebTransport adapters required by supported Java APIs; do not
  claim raw-socket compatibility.
- Measure code size, startup, execution time, and browser download cost.
- Extend to memory64 only after the wasm32 correctness gates pass. Add
  pthreads, TLS, futex-like waits, and multiple managed threads last, after
  shared-memory operation and the required cross-origin isolation are proven
  for the selected browsers.

Acceptance must prove that ART itself never creates executable memory or
compiles code at runtime. Browser-engine compilation of the already validated
`.wasm` module is an engine implementation detail, not ART JIT.

## Expected scale

The following remain rough orders of magnitude:

- `libartbase` plus DEX parsing/verifying for a Wasm target: several
  engineer-weeks;
- imageless switch-interpreter `HelloWorld` with core JNI implementations
  cross-compiled into Wasm: roughly 6-12 engineer-months;
- the Stage 0 POSIX inventory, packaged read-only VFS, descriptors, clocks,
  entropy, console, and explicit unsupported-call behavior: roughly 2-6
  engineer-months, partly overlapping switch-runtime bring-up;
- HGraph-to-Waffle arithmetic/control-flow proof after HGraph extraction:
  roughly 1-3 engineer-months;
- baseline mixed switch/AOT invocation, artifact validation, exceptions, and
  precise root spilling after the switch runtime works: another 6-12
  engineer-months;
- persistent OPFS, a tested synchronous Worker bridge, virtual polling, and a
  curated browser-networking subset: another 6-18 engineer-months;
- pthread/TLS/futex integration and multiple ART threads: another 6-18
  engineer-months plus browser deployment work for cross-origin isolation;
- a useful browser runtime with GC, persistent files, curated networking,
  reflection, ICU, broader JNI, selective AOT, and threads: likely 2-4
  engineer-years in total; and
- current ART parity with OAT compatibility, dynamic JNI, full JVMTI, and
  runtime AOT: a research-scale redesign, partly blocked on platform contracts.

The ranges overlap and are not a staffing schedule. Waffle removes much of the
generic CFG structuring and stackification work, but it does not reduce the ART
runtime, GC, exception, ABI, POSIX-simulation, or browser-integration effort.

## Final recommendation

Proceed only under a deliberately new contract:

- make the browser the only deployment target; use Wasmtime only for offline
  validation and differential tests;
- compile the whole deployed ART, switch interpreter, libcore JNI
  implementations, ICU/OpenJDK C/C++, libc/POSIX layer, and admitted
  application JNI implementations to Wasm, with no physical-ISA method, DSO,
  or JavaScript method-implementation fallback;
- expose only narrow JavaScript browser capabilities beneath the Wasm-owned
  runtime and virtual POSIX state;
- use one coordinated linear-memory layout for C/C++ stacks, TLS, static data,
  allocator storage, managed heap, and explicit managed frames; keep Java
  objects in a dedicated low-4-GiB arena;
- keep module function indices, shared-table slots, linear-memory metadata
  pointers, and optional synthetic PCs as separate values; never call a fake
  linear-memory code address or dereference a raw `&func` table slot as code;
- keep DEX as the authoritative executable and metadata input;
- establish the imageless C++ switch interpreter first;
- add offline, selective DEX/HGraph-to-Wasm AOT with switch fallback;
- use Waffle for the initial wasm32 SSA/CFG-to-Wasm backend;
- use a new Wasm AOT artifact and function-table method model rather than OAT;
- keep nterp, mterp, JIT, OSR, deoptimization, executable OAT, and compiled-code
  JVMTI features disabled;
- implement a curated, versioned browser POSIX personality rather than claim
  transparent Linux compatibility; and
- treat wasm64 and threads as later platform expansions.

DEX-to-class-to-Wasm is a valid standalone experiment, but it is not the
recommended ART implementation path. Current OAT and `dex2oat` should not be
retrofitted to pretend that Wasm functions are physical instruction pointers.

## Upstream references

Bytecode Alliance source was checked on 2026-08-01 at Wasmtime commit
`e8ac8c27f19939bfb1d26d920368d8b6028a67a9`, wasm-tools commit
`606b4cc5503015ce539e6d6a7ec39a774710e114`, and Waffle commit
`c0ce14354e1b86f53fcca4d90e3c80507f23df7f`.
LLVM/LLD and V8 sources were checked at LLVM commit
`c27bee245fc0cbc1881632c1546a946fd96d305e` and V8 commit
`1d17afafffbb434e04b2ee4bec7ca09989626341`.

- [Waffle architecture and status](https://github.com/bytecodealliance/waffle/blob/c0ce14354e1b86f53fcca4d90e3c80507f23df7f/README.md)
- [Waffle wasm32/non-shared emitter settings](https://github.com/bytecodealliance/waffle/blob/c0ce14354e1b86f53fcca4d90e3c80507f23df7f/src/backend/mod.rs)
- [wasm-tools and wasm-encoder](https://github.com/bytecodealliance/wasm-tools/tree/606b4cc5503015ce539e6d6a7ec39a774710e114)
- [Wasmtime pre-compilation](https://github.com/bytecodealliance/wasmtime/blob/e8ac8c27f19939bfb1d26d920368d8b6028a67a9/docs/examples-pre-compiling-wasm.md)
- [Wasmtime platform/compiler support](https://github.com/bytecodealliance/wasmtime/blob/e8ac8c27f19939bfb1d26d920368d8b6028a67a9/docs/stability-platform-support.md)
- [Wasmtime serialized module safety and compatibility](https://github.com/bytecodealliance/wasmtime/blob/e8ac8c27f19939bfb1d26d920368d8b6028a67a9/crates/wasmtime/src/runtime/module.rs)
- [Wizer caveats](https://github.com/bytecodealliance/wasmtime/blob/e8ac8c27f19939bfb1d26d920368d8b6028a67a9/crates/wizer/README.md#caveats)
- [dex2jar](https://github.com/pxb1988/dex2jar)
- [Enjarify](https://github.com/google/enjarify)
- [WASI SDK notable limitations](https://github.com/WebAssembly/wasi-sdk#notable-limitations)
- [Memory64 and table64 proposal](https://github.com/WebAssembly/spec/blob/main/proposals/memory64/Overview.md)
- [WebAssembly JavaScript API implementation-defined limits](https://webassembly.github.io/spec/js-api/index.html#limits)
- [LLD Wasm `--table-base` definition](https://github.com/llvm/llvm-project/blob/c27bee245fc0cbc1881632c1546a946fd96d305e/lld/wasm/Options.td)
- [V8 Wasm memory and table limits](https://github.com/v8/v8/blob/1d17afafffbb434e04b2ee4bec7ca09989626341/src/wasm/wasm-limits.h)
- [WebAssembly linking convention for TLS and memory relocations](https://github.com/WebAssembly/tool-conventions/blob/main/Linking.md)
- [Emscripten Memory64 setting](https://emscripten.org/docs/tools_reference/settings_reference.html#memory64)
- [Emscripten filesystem API](https://emscripten.org/docs/api_reference/Filesystem-API.html)
- [Emscripten browser networking limitations](https://emscripten.org/docs/porting/networking.html)
- [Emscripten pthread and signal limitations](https://emscripten.org/docs/porting/pthreads.html)
- [OPFS synchronous access handles in Workers](https://developer.mozilla.org/en-US/docs/Web/API/FileSystemFileHandle/createSyncAccessHandle)
- [`SharedArrayBuffer` security and cross-origin-isolation requirements](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/SharedArrayBuffer#security_requirements)
- [WebAssembly dynamic-linking ABI status](https://github.com/WebAssembly/tool-conventions/blob/main/DynamicLinking.md)
