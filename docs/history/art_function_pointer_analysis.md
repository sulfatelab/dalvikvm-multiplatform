# ART executable-pointer, code-address, and function-pointer analysis

Status: source audit complete

Date: 2026-08-07

ART branch: `artmp_android-16.0.0_r4`

ART revision: `03d55ca0174dbf39b54444ce5fdf4a55e5dce331`

Companion feasibility analysis:
[`art_wasm_feasibility.md`](art_wasm_feasibility.md)

## How to read this consolidated audit

This document consolidates the two complementary source audits that previously
lived in `art_function_pointer_analysis_1.md` and
`art_function_pointer_analysis_2.md`. No substantive finding has been
discarded. Part I gives the broad inventory, provenance and lifetime analysis,
managed-heap and GC boundary, and required execution model. Part II provides a
focused subsystem-by-subsystem WebAssembly impact audit with more granular
source references, classifications, implementation constraints, and edge cases.

The two parts deliberately cross-check some of the same ART surfaces from
different angles. Repetition is retained where removing it would also remove a
distinct classification, source trail, ownership observation, or Wasm design
constraint.

## Part I — Expanded inventory, provenance, lifetime, and GC audit

### Executive conclusion

ART does not use a raw code pointer only as an opaque callable value. The same
native address is routinely treated as all of the following:

1. a call target;
2. a byte address in an executable mapping;
3. the base of a method code range;
4. an anchor from which a preceding `OatQuickMethodHeader` and other metadata
   are recovered;
5. an ordered-map or set key;
6. a physical program counter in the middle of a method;
7. a return address or exception/deoptimization continuation;
8. an input to OS signal, unwinding, debugging, profiling, and control-flow
   protection APIs; and
9. a lifetime token whose allocation must remain valid while any stack can
   still contain a PC into it.

This is the central wasm64 incompatibility. A WebAssembly function reference or
C/C++ function-table slot can support equality and an indirect call, subject to
signature rules. It is not a byte address in linear memory. Memory64 widens
linear-memory addresses; it does not merge the function-index, table-slot, and
linear-memory namespaces. Therefore a Wasm port cannot preserve ART's current
contract merely by putting a table index in
`ArtMethod::entry_point_from_quick_compiled_code_`.

The uses divide into two substantially different groups:

- **Callable-only pointers**: ordinary C/C++ callbacks, vtables, `std::function`,
  pthread callbacks, statically linked JNI functions, and runtime helper
  functions can generally be lowered to Wasm table slots if their types and
  lifetimes remain explicit and no code-address arithmetic is performed.
- **Physical-code-address pointers**: OAT and JIT entrypoints, nterp code ranges,
  return PCs, fault PCs, OSR targets, catch targets, header recovery, range maps,
  native unwind records, and native debugger records require a new logical code
  model. They cannot be represented by a raw Wasm function-table slot.

The managed heap normally does **not** contain direct executable pointers.
Managed `Class`, reflection, vtable, and interface structures contain native
`ArtMethod*` identities, and an `ArtMethod` then contains the executable
entrypoint. `ArtMethod` arrays are native `LinearAlloc` or packed image
metadata, not ordinary moving Java objects. Managed GC does not trace quick or
JNI entrypoint fields as object references. It does, however, depend on
physical PCs to find stack maps and roots. Separately, ART has a JIT **code
cache GC** that treats live executable PCs on thread stacks as marks; that is
not managed-heap GC.

For the restricted browser design in the companion feasibility analysis, the
practical boundary is:

- retain the C++ switch interpreter after removing its assembly/function-as-
  `void*` wrapper dependency;
- statically link admitted JNI and runtime helpers behind typed table slots or
  registries;
- use a new offline Wasm AOT artifact with explicit method-table slots and
  side-table metadata;
- represent execution locations as `(code_blob_id, logical_offset)` or a
  safepoint/continuation ID, never as a dereferenceable linear-memory code
  address; and
- keep current OAT, native JIT, OSR, nterp, recoverable signal faults, and
  runtime DSO loading disabled until each is deliberately redesigned.

### Scope and terminology

This audit covers both readings of "pointer in executable memory":

- a pointer **whose target lies in an executable mapping**, including an
  entrypoint, an interior PC, or a pointer to metadata immediately adjacent to
  code; and
- address-like values **encoded in executable bytes**, such as direct-call
  displacements, PC-relative references, literals, and linker patches.

It also covers raw C/C++ function pointers whose representation may not be a
physical code address on Wasm. Pure data pointers are included only when they
explain executable-code ownership, managed-heap reachability, GC root handling,
or a required replacement abstraction.

Terms used below:

- **AOT**: physical-ISA code and trampolines in OAT files, including boot/app
  image entrypoints.
- **JIT**: physical-ISA code generated into the JIT code cache, including JIT
  JNI stubs and OSR code.
- **nterp**: ART's native assembly interpreter. It interprets DEX, but it uses
  the quick native stack/code-PC contract.
- **switch**: the portable C++ switch interpreter.
- **RTLD/DSO/JNI**: `dlopen`/`dlsym`, Android native-loader/native-bridge
  equivalents, shared-library lifecycle, JNI function pointers, agents, and
  plugins.
- **managed heap**: Java objects managed by ART GC. This is distinct from
  native `malloc`, `LinearAlloc`, OAT mappings, JIT mappings, and image metadata.
- **managed GC**: tracing/moving/collecting Java objects.
- **JIT code GC**: reclaiming JIT code/data allocations after proving that no
  live stack still executes them.

The audit groups equivalent architecture backends rather than listing every
ARM, ARM64, RISC-V, x86, and x86-64 spelling. ARM64 source is used as a
representative generated-code consumer where appropriate. Ordinary C++
callback sites are grouped by ABI role; enumerating every virtual method or
lambda would add volume without exposing a new executable-pointer contract.

### Classification legend and summary

In the subsystem columns, **D** means the row directly stores or consumes a
callable/executable address for that subsystem, **I** means an important
indirect interaction, and `-` means no material relationship. `Heap` means the
managed Java heap. Native-heap storage is described in the detailed sections.

| Surface | Primary operations on executable value | AOT | JIT | nterp | RTLD/DSO/JNI | Heap | Managed GC | JIT code GC |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `ArtMethod` quick entrypoint | call, equality, atomic replacement, classification, header/range lookup | D | D | D | I | I | I | D |
| `ArtMethod::data_` as JNI entrypoint | typed call, resolver replacement, native-bridge wrapping | I | I through JIT JNI stub | I | D | I | I | I through JIT JNI stub |
| OAT method code and trampolines | base+offset, header subtraction, range tests, direct/indirect call | D | - | I | D for `dlopen` OAT path | I | I | - |
| Runtime quick/JNI TLS tables and stubs | fixed-offset load, indirect call, equality | D | D | D | D | I | D for GC helpers | I |
| Switch-interpreter implementation pointer | typed function selected then passed as `const void*` to assembly | - | I on transition | - | D for direct JNI calls | I | I | - |
| nterp implementation/handler ranges | function subtraction, synthetic header, range/PC tests | I | I | D | I through `libart` | I | I | - |
| JIT code-cache addresses | RX/RW alias translation, maps/sets, arithmetic, call, OSR interior jump | - | D | I | I for JIT JNI stubs | I | I | D |
| JNI libraries, agents, plugins, native bridge | load, symbol lookup, cast, call, unload | - | I | I | D | I | I via class unloading | I |
| Quick-frame return/fault/catch/deopt PCs | frame load/store, range lookup, metadata lookup, PC rewrite | D | D | D | I | I | D | D |
| Patches and target values encoded in code | branch displacement, PC-relative address, literal/reference load | D | D | I | I | I | D for barriers/root tables | I |
| Native unwind/debug/profiling records | publish ranges/PCs to OS and tooling | D | D | D | I | - | I | D |
| Managed class/vtable/reflection metadata | store `ArtMethod*`, then load entrypoint from method | I | I | I | I | D, but indirect | D | I |
| Ordinary C/C++ callbacks and vtables | callable identity and typed indirect call | I | I | I | I | - | I for GC callbacks | - |
| Perf executable marker page | map/unmap and retain address; never call it | - | D tooling | - | - | - | - | - |

Two negative findings are important:

- The switch interpreter does not require generated method code merely to
  interpret DEX, but it still uses ordinary C/C++ function pointers, a native
  assembly wrapper, and JNI function pointers.
- Managed GC does not treat executable pointers as roots. It traces explicit
  `GcRoot` tables and uses executable PCs only to locate the metadata that
  identifies actual roots.

### 1. `ArtMethod`: the central overloaded storage

**Classification:** AOT direct; JIT direct; nterp direct; switch bridge direct;
RTLD/JNI direct through `data_`; managed heap indirect; managed GC indirect;
JIT code GC direct.

[`ArtMethod::PtrSizedFields`](../../vendor/art/runtime/art_method.h) has two
untyped pointer-sized words:

```cpp
struct PtrSizedFields {
  void* data_;
  void* entry_point_from_quick_compiled_code_;
};
```

The quick entrypoint is not simply "compiled code." Depending on method state,
it can name:

- an AOT OAT method body;
- a JIT method body;
- a JIT-generated JNI stub;
- `ExecuteNterpImpl` or its class-initialization variant;
- the quick-to-switch-interpreter bridge;
- the resolution trampoline;
- a generic JNI trampoline;
- the proxy invoke handler;
- the obsolete-method stub;
- an IMT conflict stub; or
- a precompiled `libart` helper selected by the small-pattern matcher.

The `data_` word is even more heavily overloaded:

| Method kind | Meaning of `data_` |
|---|---|
| native method | registered/resolved JNI function or JNI resolver stub |
| resolution method | resolver/JNI critical-native stub |
| IMT conflict runtime method | `ImtConflictTable*` |
| abstract/interface method | single implementation `ArtMethod*`, if known |
| proxy method | original interface method or constructor |
| ordinary DEX method | code-item pointer at runtime; code-item offset during AOT |

`GetEntryPointFromJni()` is an alias for `data_`, guarded mainly by method-kind
checks. Consequently, a field-type search cannot distinguish callable values
from native metadata pointers or offsets.

#### Writers and state changes

The principal writers are:

- the class linker, which installs interpreter, resolution, JNI, proxy, and
  runtime stubs;
- the image writer, which writes OAT code/trampoline addresses into packed
  boot/app-image methods;
- the image loader, which relocates saved quick and JNI code addresses;
- instrumentation, which atomically exchanges the quick entrypoint among AOT,
  JIT, nterp, interpreter, resolution, JNI, proxy, and obsolete states;
- the JIT code cache, which publishes a committed JIT entrypoint only after
  code, roots, stack maps, unwind data, and debugger records are ready; and
- JNI resolution/`RegisterNatives`, which installs a DSO symbol, static
  function, or native-bridge trampoline in `data_`.

[`Instrumentation::UpdateEntryPoints()`](../../vendor/art/runtime/instrumentation.cc)
uses a pointer-sized compare/exchange. If the replaced address is in the JIT
cache, the old allocation becomes zombie code rather than being freed
immediately. This establishes that the field is only the **current** dispatch
target; older addresses remain authoritative for frames already on stack.

#### Readers and calls

[`ArtMethod::Invoke()`](../../vendor/art/runtime/art_method.cc) calls an
architecture invoke stub. Quick assembly obtains the method's quick entrypoint
and branches to it. Generated code does the same operation directly. For
example, the ARM64 optimizing backend in
[`code_generator_arm64.cc`](../../vendor/art/compiler/optimizing/code_generator_arm64.cc)
loads `EntryPointFromQuickCompiledCodeOffset()` and executes `blr`; critical
native calls load `EntryPointFromJniOffset()` and execute `blr`.

Virtual and interface dispatch first resolves an `ArtMethod*` through a vtable,
IMT, or conflict table, then loads the quick entrypoint. Slow resolution
trampolines in
[`quick_trampoline_entrypoints.cc`](../../vendor/art/runtime/entrypoints/quick/quick_trampoline_entrypoints.cc)
return the executable address and `ArtMethod*` as two integer words to assembly,
which then branches to the returned address.

The current quick entrypoint is also read for equality and provenance tests:

- is it the switch bridge, resolution stub, generic JNI stub, or proxy stub?
- is it exactly the nterp entrypoint?
- does it fall inside a JIT or OAT range?
- is it a hard-coded `libart` stub?
- does it support instrumentation entry/exit hooks?

These tests make a bare table slot insufficient even before considering code
arithmetic. The replacement needs an explicit execution kind and owner.

#### Method identity is not code identity

ART already contains evidence that these identities differ:

- one `ArtMethod` can move from interpreter to AOT or JIT code;
- a JIT recompile can produce multiple code allocations for one method;
- OSR code is a separate allocation and is not necessarily the normal method
  entrypoint;
- all eligible nterp methods share the same executable entrypoint;
- JNI stubs can be shared by multiple methods; and
- copied/obsolete methods can retain distinct metadata while dispatch changes.

A Wasm design must therefore keep at least method identity, current call target,
code-blob identity, and logical PC as separate values.

### 2. AOT/OAT and image executable addresses

**Classification:** AOT direct; JIT none; nterp indirect through OAT
trampolines; RTLD/DSO direct for the `dlopen` loading path; managed heap
indirect through image/class metadata; managed GC indirect through stack maps
and OAT root tables; JIT code GC none.

#### Code is laid out as addressable bytes

[`OatQuickMethodHeader`](../../vendor/art/runtime/oat/oat_quick_method_header.h)
physically precedes the generated instruction bytes:

```text
lower addresses                                       higher addresses
[ CodeInfo / stack-map data ] ... [ header ][ machine instructions ]
                                            ^ entrypoint/code pointer
```

ART depends on this layout in both directions:

- `FromCodePointer()` subtracts the header offset from a code pointer.
- `FromEntryPoint()` first removes the ARM Thumb tag, then subtracts.
- `GetOptimizedCodeInfoPtr()` subtracts a stored offset from the code address.
- `NativeQuickPcOffset(pc)` subtracts the method entrypoint from an interior PC.
- `Contains(pc)` compares numeric addresses against the code range.
- `GetEntryPoint()` can add the ARM Thumb bit back to the code address.

[`OatFile::OatMethod`](../../vendor/art/runtime/oat/oat_file-inl.h) constructs a
method pointer as `begin_ + code_offset_`, dereferences the header immediately
before it, and subtracts from the code address to find vmap/stack-map data.
[`OatHeader`](../../vendor/art/runtime/oat/oat.cc) constructs JNI, resolution,
generic-JNI, IMT, interpreter, and nterp trampoline pointers as
`&OatHeader + stored_offset`.

This is not representable by a Wasm table index. A side table can preserve the
same logical relationships, but `header = entrypoint - sizeof(header)` and
`metadata = code - offset` must disappear from the runtime contract.

#### OAT loading is also an executable-mapping and sometimes DSO contract

[`oat_file.cc`](../../vendor/art/runtime/oat/oat_file.cc) has two relevant
loading models:

- `DlOpenOatFile` loads an ELF OAT with `dlopen`/`android_dlopen_ext` and locates
  symbols such as `oatdata` with `dlsym`. This path is both **AOT** and
  **RTLD/DSO** related. The `oatdata` symbol itself is a data address, but code
  and trampoline addresses are derived from the loaded image.
- `ElfOatFile` uses ART's ELF loader and maps loadable executable segments with
  execute permission. This is AOT executable memory without using the process
  RTLD for dispatch.

The `OatFile`/module mapping owns all method, trampoline, and interior-PC
addresses derived from it. Unmapping invalidates them together. OAT executable
ranges are also registered with the fault manager so a signal PC can be
recognized as generated ART code.

Browser Wasm provides neither an ELF executable mapping nor a browser RTLD that
returns callable byte addresses. Offline AOT must instead instantiate validated
Wasm functions and publish explicit table slots plus metadata descriptors.

#### Image writing and relocation

[`ImageWriter::CopyAndFixupMethod()`](../../vendor/art/dex2oat/linker/image_writer.cc)
copies OAT method-body and trampoline addresses into packed `ArtMethod`
records. Native methods receive a JNI dlsym resolver address in `data_`; normal
methods receive AOT, resolution, nterp-trampoline, or switch-bridge addresses
according to availability and class-initialization state.

At load time,
[`image_space.cc`](../../vendor/art/runtime/gc/space/image_space.cc) visits
packed methods and relocates quick and native-code addresses with the OAT/image
mapping delta. That source is under `runtime/gc/space`, but this particular
operation is **image relocation**, not managed-GC tracing of a code pointer.
The same visitor separately patches `declaring_class_` as a real GC root.

This distinction matters for a new artifact: relocatable Wasm table slots,
metadata indices, and linear-memory roots need different relocation domains.
They must not be collapsed into one pointer-sized image word.

#### Values encoded in AOT instruction streams

[`LinkerPatch`](../../vendor/art/compiler/linker/linker_patch.h) describes
values that the architecture patcher writes into generated instruction bytes
or literal/reference sequences. The families include:

- relative calls to compiled methods;
- relative JNI entrypoint references;
- calls through runtime entrypoints;
- method references and method `.bss` entries;
- boot/app-image references;
- type, string, and method-type `.bss` entries; and
- Baker read-barrier branches.

Not every patch encodes an absolute pointer: many encode a branch displacement,
PC-relative address, or address of a writable indirection slot. They are still
part of the physical-code-address contract because their meaning depends on the
instruction PC and the native layout of code, image, and `.bss`.

For Wasm AOT these become module-level calls, table calls, imports, globals, or
linear-memory table indices produced by a new backend/linker. Copying the
physical-ISA patch taxonomy unchanged would preserve the wrong abstraction.

#### AOT roots are explicit data, not hidden movable pointers in text

OAT `.bss` can contain `GcRoot<mirror::Object>` entries. The class table visits
`OatFile::GetBssGcRoots()` in
[`class_table-inl.h`](../../vendor/art/runtime/class_table-inl.h). Generated
code reaches these entries through patched PC-relative sequences, while GC
updates the data entries themselves.

Boot-image object and native-metadata addresses can be embedded or referenced
more directly because boot-image placement is non-moving after loader
relocation. This is not a general license to embed movable managed-object
pointers in executable text.

#### Platform unwind and control-flow metadata

This fork also makes the physical-address dependency explicit on Windows x64:

- [`aot_unwind_windows.cc`](../../vendor/art/runtime/multiplatform/windows/aot_unwind_windows.cc)
  turns OAT-relative method ranges into `RUNTIME_FUNCTION` entries and
  registers them with `RtlAddFunctionTable` using the mapped OAT base.
- [`aot_cfg_windows.cc`](../../vendor/art/runtime/multiplatform/windows/aot_cfg_windows.cc)
  validates a serialized set of indirect-callable code offsets and classifies
  quick methods, JNI stubs, boot trampolines, and indirect-callable thunks.

These are **AOT/platform integration**, not RTLD symbol resolution. A browser
Wasm engine owns native unwinding and indirect-call validation internally; ART
cannot register engine PCs or use them as its method-PC namespace.

### 3. Runtime stubs and per-thread function-pointer tables

**Classification:** AOT direct; JIT direct; nterp direct; switch bridge direct;
RTLD/JNI direct; managed heap indirect; managed GC direct for allocation/read-
barrier helpers; JIT code GC indirect.

ART contains a process-lifetime layer of assembly and C/C++ entrypoints that is
neither an AOT Java method nor JIT-generated code. Representative stubs in
[`runtime_asm_entrypoints.h`](../../vendor/art/runtime/entrypoints/runtime_asm_entrypoints.h)
include:

- JNI dlsym lookup and critical-JNI lookup;
- generic JNI;
- method resolution;
- IMT conflict handling;
- quick-to-interpreter transition;
- proxy invocation;
- obsolete-method invocation; and
- deoptimization.

The inline getters cast each declared function to `const void*`. These pointers
can be installed in `ArtMethod`, compared for state classification, returned by
resolution trampolines, and branched to by quick assembly.

There are two physical implementations of several stubs:

- code linked into `libart`/the runtime module; and
- equivalent boot-OAT trampolines whose addresses are derived from OAT-header
  offsets.

`ClassLinker` helpers hide some of this distinction by recognizing either
address. ART nevertheless classifies hard-coded assembly by asking whether a PC
is in the executable range of `libart`; see
[`OatQuickMethodHeader::IsStub()`](../../vendor/art/runtime/oat/oat_quick_method_header.cc).
On ELF platforms this discovers module segments, and on Windows this fork uses
the PE module containing `Runtime::Current`. This is executable-module range
introspection, not just function-pointer equality.

#### `QuickEntryPoints` and `JniEntryPoints`

[`QuickEntryPoints`](../../vendor/art/runtime/entrypoints/quick/quick_entrypoints.h)
is a large struct of `void*` function addresses. Every
[`Thread`](../../vendor/art/runtime/thread.h) contains a copy in its pointer-
sized TLS block, next to the two JNI resolver addresses in
[`JniEntryPoints`](../../vendor/art/runtime/entrypoints/jni/jni_entrypoints.h).
Generated quick code uses compile-time field offsets to load one of these
addresses and call it indirectly.

The table spans many runtime domains:

- allocation and object/array initialization;
- field, array, type, string, method, and class resolution;
- exceptions, suspend checks, locks, and deoptimization;
- JNI transitions;
- math/memory helpers; and
- read-barrier and GC marking helpers, including register-specific marking
  entrypoints.

The executable pointer itself is not a GC root, but many targets implement GC
barriers or allocation slow paths and are therefore directly **managed-GC
related**. Instrumentation can replace/reset allocation helper entries for all
threads, making this table another mutable dispatch surface.

For Wasm, a typed helper table or a set of direct imports/internal calls is a
reasonable replacement. The generated-code ABI must load a function-table slot
or call a statically known function, not load a linear-memory `void*` and treat
it as byte-addressable code. Signature differences require typed tables,
signature adapters, or a deliberately uniform helper ABI.

### 4. Switch interpreter and nterp are different pointer models

#### Portable switch interpreter

**Classification:** AOT/JIT indirect only when transitioning to compiled code;
nterp none; RTLD/JNI direct for native method calls; managed heap indirect;
managed GC indirect through shadow frames and JNI handles; JIT code GC none
while it stays in switch mode.

The switch interpreter does not allocate or execute per-method native code.
That makes it the viable first execution engine for the restricted Wasm port,
but the current implementation is not free of function pointers.

[`interpreter.cc`](../../vendor/art/runtime/interpreter/interpreter.cc) chooses
one of two templated `ExecuteSwitchImplCpp` functions, casts it to
`const void*`, and passes it to
[`ExecuteSwitchImplAsm`](../../vendor/art/runtime/interpreter/interpreter_switch_impl.h).
The architecture assembly wrapper supplies unwind/CFI behavior and indirectly
branches or calls through that value. The function is used only as a callable
identity; ART does not subtract from it or inspect its code bytes.

This use is Wasm-convertible. Replace the assembly wrapper with a Wasm/C++
wrapper and select the transactional/non-transactional implementation by a
direct branch, enum, or typed function pointer. Do not preserve the
function-to-`void*` conversion as the portable ABI.

The switch interpreter also invokes a limited set of native methods directly.
`InterpreterJni()` reads `ArtMethod::GetEntryPointFromJni()`, casts it to a
signature-specific C function type, and calls it. This is a real JNI/DSO
function-pointer dependency even in an interpreter-only runtime. A Wasm build
can support a curated statically linked registry with signature adapters; it
cannot assume that browser `dlsym` supplies a native code address.

Finally, a switch frame may transition to quick compiled code through
`ArtInterpreterToCompiledCodeBridge()`, which calls `ArtMethod::Invoke()`. If
that transition is enabled, all AOT/JIT quick-entrypoint and physical-PC
requirements return. A genuinely switch-only profile must keep that transition
disabled or route it to the new Wasm AOT descriptor model.

#### nterp

**Classification:** nterp direct; AOT/JIT indirect through common quick-frame
infrastructure; RTLD/DSO indirect because code lives in the runtime module;
managed heap indirect; managed GC indirect through nterp frame maps; JIT code
GC none for nterp code itself.

nterp interprets DEX but is implemented as native assembly and deliberately
masquerades as quick code. In
[`nterp.cc`](../../vendor/art/runtime/interpreter/mterp/nterp.cc):

- `GetNterpEntryPoint()` casts `ExecuteNterpImpl` to `const void*`;
- `NterpImpl()` subtracts the address of `ExecuteNterpImpl` from
  `EndExecuteNterpImpl` to calculate an executable byte range;
- the class-initialization variant does the same;
- `CheckNterpAsmConstants()` subtracts
  `artNterpAsmInstructionStart` from `artNterpAsmInstructionEnd` to validate
  the fixed-width opcode-handler region; and
- all eligible methods can store the same nterp entrypoint in `ArtMethod`.

[`oat_quick_method_header.cc`](../../vendor/art/runtime/oat/oat_quick_method_header.cc)
creates `NterpMethodHeader` by subtracting `sizeof(OatQuickMethodHeader)` from
the nterp code pointer. Special cases then make this synthetic header act like
a quick-method header for frame sizing, stack walking, PC containment,
exceptions, and deoptimization.

The runtime registers the nterp implementation range with the fault manager.
Signal handlers and stack walkers recognize PCs in the shared range and use the
method stored in each frame to recover DEX-level state.

This model is not portable to browser Wasm. The browser does not expose the
engine's compiled bytes for `ExecuteNterpImpl`, labels cannot be subtracted to
obtain a stable engine code range, and an engine PC cannot be mapped back to an
ART-synthesized header. Porting nterp would mean designing a new Wasm
interpreter/frame/continuation ABI, not recompiling the current assembly.

### 5. JIT executable addresses and code-cache ownership

**Classification:** JIT direct; AOT none for private code but shared quick
metadata format; nterp indirect through transitions; RTLD/JNI direct for JIT
JNI stubs; managed heap indirect; managed GC direct through explicit root
tables and stack maps; JIT code GC direct.

#### Executable mappings and aliases

[`JitMemoryRegion`](../../vendor/art/runtime/jit/jit_memory_region.cc) creates
physical executable memory. Depending on platform and policy it uses anonymous
or file/section-backed mappings, a single mapping whose permissions change, or
dual views of the same pages:

```text
same physical code allocation
    writable/non-executable alias  <->  executable/read-only alias
```

`AllocateCode()` allocates through the writable-side allocator but returns the
translated executable address. `CommitCode()`:

1. translates the reserved RX address to its writable alias;
2. copies machine instructions through that alias;
3. writes an `OatQuickMethodHeader` immediately before the code;
4. encodes the address relationship from code to stack-map data;
5. flushes data and instruction caches; and
6. returns the RX code address.

[`ScopedCodeCacheWrite`](../../vendor/art/runtime/jit/jit_scoped_code_cache_write.h)
temporarily changes protections for single mappings or controls the appropriate
view for dual mappings. Freed allocations can be reused, so cache flushing is a
correctness requirement, not only a performance action.

WebAssembly linear memory has no executable pages, no RX/RW alias, no
instruction-cache flush contract, and no operation that makes newly written
bytes callable. This entire allocator is native-JIT infrastructure and must be
disabled in the browser profile. A hypothetical Wasm JIT would compile and
instantiate a new Wasm module through a host API and would need new ownership,
metadata, and continuation contracts.

#### Raw executable addresses in cache indexes

[`JitCodeCache`](../../vendor/art/runtime/jit/jit_code_cache.h) retains raw code
addresses in several native containers:

- `ZygoteMap::Entry::code_ptr`;
- `method_code_map_`, ordered by code address;
- `method_code_map_reversed_`, allowing multiple code allocations per method;
- `saved_compiled_methods_map_`;
- `osr_code_map_`;
- `zombie_code_` and `processed_zombie_code_`; and
- JNI-stub records and their zombie sets.

These are native-heap/container values, not managed Java references. Lookup is
address-based: `ContainsPc()` tests executable mappings;
`LookupMethodHeader()` uses ordered-map predecessor lookup and range
containment; `FreeCodeAndData()` converts code to allocation base and recovers
the header/root table through address arithmetic.

The cache registers whole executable regions with the fault manager and
publishes individual method ranges to native debugger/profiler support. Thus
the same address is simultaneously an allocator address, dispatch target,
range-map key, stack-walk key, fault classification key, and tooling symbol
address.

A replacement must use stable handles such as `CodeBlobId` as map keys. Numeric
ordering of function-table slots cannot stand in for address containment, and
table-slot reuse must be generation-checked if stale handles can survive.

#### Commit and publication ordering

[`JitCodeCache::Commit()`](../../vendor/art/runtime/jit/jit_code_cache.cc)
publishes in a deliberate order:

1. commit code and its header;
2. commit root table, stack maps, and unwind data;
3. register unwind/debug metadata;
4. validate class-hierarchy assumptions;
5. insert code/method and OSR/JNI side-map entries; and
6. update the method's executable entrypoint through instrumentation.

Readers may call the entrypoint as soon as step 6 is visible, so all metadata
needed for a GC, exception, deoptimization, stack walk, or debugger lookup must
already be valid. A Wasm AOT or future module-JIT publisher needs the same
semantic ordering even though the published values become table slots and blob
IDs rather than addresses.

#### OSR jumps into the middle of generated code

On-stack replacement is a stronger dependency than ordinary entry dispatch.
[`Jit::PrepareForOsr()`](../../vendor/art/runtime/jit/jit.cc) finds an OSR stack
map and calculates:

```text
native_pc = JIT method entrypoint + stack_map.native_pc_offset
```

Architecture `art_quick_osr_stub` assembly builds the compiled frame and jumps
to that interior `native_pc`. This target is neither the method entrypoint nor
an independent C function pointer.

A Wasm function table cannot name an arbitrary byte offset within a function.
Supporting OSR requires compiler-created Wasm entry functions/continuations for
specific OSR points and explicit reconstructed-frame state. Current OSR must
remain disabled in the restricted port.

#### JIT code GC is not managed-heap GC

When instrumentation or invalidation replaces a JIT entrypoint, ART retains
the old code in a zombie set. During `DoCollection()` it:

1. moves zombies and OSR allocations into a candidate set;
2. runs checkpoints on all threads;
3. stack-walks each thread and obtains each frame's current
   `OatQuickMethodHeader`;
4. marks JIT allocations whose executable code is still on a stack; and
5. removes debugger/unwind/map state and frees unmarked code/data.

The mark is derived from a physical executable PC/header, not from the current
`ArtMethod` entrypoint. Addresses can be reused only after no stack can retain
a return PC into the old allocation.

This is a distinct **JIT code GC**. Managed GC may run during the same process
and uses the same stack maps, but its liveness unit is a Java object, not a code
allocation. In a module/table design, code lifetime would need explicit active-
frame references or epoch/generation tracking; scanning an inaccessible Wasm
engine return PC is not available.

#### Managed roots associated with JIT code

ART avoids leaving arbitrary movable-object pointers hidden in machine code.
[`JitMemoryRegion::CommitData()`](../../vendor/art/runtime/jit/jit_memory_region.cc)
writes compiled constants into a separate `GcRoot<mirror::Object>` table in the
JIT data region. Generated code uses a stable displacement/reference to the
table. GC integration then operates on the data entries:

- [`ArtMethod::VisitRoots()`](../../vendor/art/runtime/art_method-inl.h) asks the
  code cache to visit strong JIT roots associated with the method;
- [`JitCodeCache::VisitRootTables()`](../../vendor/art/runtime/jit/jit_code_cache-inl.h)
  visits strong strings and `MethodType` objects; and
- `SweepRootTables()` updates moved objects and clears weak class/string
  entries as appropriate.

JIT stack-map inline metadata can also encode a raw `ArtMethod*`; see
[`StackMapStream::BeginInlineInfoEntry()`](../../vendor/art/compiler/optimizing/stack_map_stream.cc).
This metadata is JIT data, not a managed object and not a code pointer. Class
unloading must remove the associated maps/code before its class-loader
`LinearAlloc` releases those methods.

The explicit root-table idea ports well to Wasm linear memory. The
code-address-to-root-table recovery does not. A Wasm code descriptor should
carry a root-table index and metadata index directly.

#### Precompiled helpers selected by JIT policy

[`SmallPatternMatcher`](../../vendor/art/runtime/jit/small_pattern_matcher.cc)
recognizes trivial DEX bodies and returns addresses of static `libart` helper
functions such as empty, constant-return, and small field-access methods. Some
helpers access managed objects and perform object-field write barriers.

This surface is **JIT-triggered** but the target is not allocated in the JIT
cache; its lifetime is the runtime module's lifetime. It demonstrates why
provenance cannot be inferred from "the JIT installed this pointer." In Wasm,
these helpers can be statically assigned table slots and marked with an
explicit `precompiled_helper` execution kind.

#### JIT unwind, debugger, and profiler records

JIT code addresses are exported beyond dispatch:

- [`jit_unwind_windows.cc`](../../vendor/art/runtime/multiplatform/windows/jit_unwind_windows.cc)
  registers each code range and unwind-data address with Windows, keyed by the
  raw code pointer.
- [`debugger_interface.cc`](../../vendor/art/runtime/jit/debugger_interface.cc)
  publishes code addresses and in-memory ELF symbol files through the native
  GDB/JIT interface; it also exposes replaceable notification function
  pointers.
- [`jit_logger.cc`](../../vendor/art/compiler/jit/jit_logger.cc) records native
  code ranges for perf. It additionally maps one `PROT_READ|PROT_EXEC` marker
  page so perf records an executable mapping. `marker_address_` is never a call
  target; this is JIT tooling/profiling, not method dispatch.

Browser Wasm needs Wasm-aware source maps, names, engine profiling APIs, or a
project-owned logical-PC trace format. Native ELF/JIT registration and the
executable marker page have no browser equivalent.

### 6. JNI, RTLD/DSO, agents, plugins, and native bridge

**Classification:** RTLD/DSO/JNI direct; JIT direct for compiled JNI stubs;
AOT indirect through generic/resolver trampolines; nterp and switch direct when
invoking native methods; managed heap indirect through class-loader ownership;
managed GC indirect through weak roots/class unloading; JIT code GC direct for
JIT JNI stubs.

#### Symbol lookup and native method installation

[`java_vm_ext.cc`](../../vendor/art/runtime/jni/java_vm_ext.cc) owns loaded JNI
libraries in `SharedLibrary` objects. Each record retains:

- the native-loader/`dlopen` handle;
- whether native bridge is required;
- a weak global reference to the defining class loader; and
- a native class-loader allocator identity used to restrict symbol search.

For ordinary DSOs, `FindSymbolWithoutNativeBridge()` returns `dlsym(handle,
name)`. Native-bridge lookup returns a bridge-generated trampoline. Native
method resolution tries the short and long JNI names, returns the resulting
`void*`, and eventually installs it in `ArtMethod::data_`. Subsequent generic,
critical, or interpreter JNI paths cast/call that raw value.

The same file resolves `JNI_OnLoad` and `JNI_OnUnload` as `void*`, converts each
to its typed function-pointer signature, and calls it. The DSO handle must
remain live for every method pointer and lifecycle callback obtained from it.

#### Library lifetime and managed GC interaction

JNI-library lifetime is connected to managed class-loader lifetime, but the
code pointer is not a managed root. `SharedLibrary` keeps a `jweak` class-loader
reference. `UnloadNativeLibraries()` observes class loaders cleared by managed
GC, calls `JNI_OnUnload`, deletes the `SharedLibrary`, and closes the native
library. That unload invalidates all executable addresses from the DSO.

This is an **indirect managed-GC relationship**:

```text
managed ClassLoader dies
        -> weak JNI root is cleared
        -> library ownership record is removed
        -> JNI_OnUnload is called
        -> DSO is closed
        -> its function addresses cease to be valid
```

The collector never marks a JNI function because an `ArtMethod` contains its
address. Correctness instead requires class unloading, method metadata cleanup,
active native-frame rules, and DSO unloading to be ordered so no call can use a
stale address.

#### `RegisterNatives` and native bridge

[`JNIImpl::RegisterNatives()`](../../vendor/art/runtime/jni/jni_internal.cc)
accepts `JNINativeMethod::fnPtr`. It validates the method, optionally replaces
the pointer with a native-bridge trampoline, and asks the class linker to
register the final address. `UnregisterNatives` restores resolver behavior.

[`native_bridge_art_interface.cc`](../../vendor/art/runtime/native_bridge_art_interface.cc)
adds more function-pointer surfaces:

- [`libnativebridge/native_bridge.cc`](../../vendor/art/libnativebridge/native_bridge.cc)
  loads a bridge implementation, resolves its exported
  `NativeBridgeCallbacks` table, and calls through the retained table;
- a callback table through which the native bridge asks ART for method
  metadata and registered native pointers;
- generated trampolines representing foreign-ISA native functions; and
- per-signal native-bridge handler pointers installed in ART's signal chain.

These are callable-only at the ART C++ layer, but their producer owns hidden
native executable code and ABI adaptation. They cannot be treated as stable
linear-memory pointers.

#### JNI function tables

The global `JNINativeInterface` and `JNIInvokeInterface` objects are large
tables of C function pointers used through `JNIEnv*` and `JavaVM*`. They are not
OAT/JIT code addresses and ART does not perform header subtraction or method-PC
range tests on them. They are nevertheless raw executable targets stored in
native data.

When ART, libcore native implementations, and the admitted application-native
surface are all compiled into the same Wasm deployment, LLVM can lower such
typed indirect calls through Wasm tables. The port should still preserve the
JNI ABI intentionally: table entries need stable signatures, and any untyped
`void*` transport should be replaced by an explicit registry/adapter.

#### Agents and plugins

Additional DSO entrypoints include:

- [`Agent`](../../vendor/art/runtime/ti/agent.cc), which resolves and retains
  `Agent_OnLoad`, `Agent_OnAttach`, and `Agent_OnUnload` function pointers; and
- [`Plugin`](../../vendor/art/runtime/plugin.cc), which resolves and calls
  `ArtPlugin_Initialize` and `ArtPlugin_Deinitialize`.

Their address lifetime is the corresponding DSO-handle lifetime. These paths
are RTLD/JVMTI/plugin infrastructure rather than managed method dispatch, but a
browser port has the same fundamental problem: there is no native DSO namespace
from which to obtain physical executable addresses.

#### Peripheral RTLD function tables

ART-adjacent libraries also populate typed function-pointer tables with
`dlsym`. These values are executable targets in native DSOs, but they are not
method entrypoints and ART does not perform code-header or PC arithmetic on
them:

| Surface | Pointer use | Classification |
|---|---|---|
| [`libartpalette/apex/palette.cc`](../../vendor/art/libartpalette/apex/palette.cc) | loads `libartpalette-system.so`, stores each Palette API method pointer, and calls it through a typed wrapper | **RTLD direct**; **JIT indirect** because Palette provides ashmem creation/protection used by executable-memory policy; AOT/nterp/heap/managed-GC/JIT-code-GC none |
| [`libnativebridge/native_bridge_lazy.cc`](../../vendor/art/libnativebridge/native_bridge_lazy.cc) | lazily resolves the native-bridge API, including the operation that returns foreign-ISA trampolines | **RTLD and native-bridge direct**; **JNI direct** at the subsystem boundary; AOT/JIT/nterp indirect only when their native-call paths use the bridge; heap/managed-GC/JIT-code-GC none |
| [`libnativeloader/native_loader_lazy.cpp`](../../vendor/art/libnativeloader/native_loader_lazy.cpp) | lazily resolves namespace, open, and close operations from `libnativeloader.so` | **RTLD/JNI direct**; managed heap and managed GC indirect only through the class-loader arguments and ownership described above; AOT/JIT/nterp/JIT-code-GC none |
| [`libdexfile/external/dex_file_supp.cc`](../../vendor/art/libdexfile/external/dex_file_supp.cc) | loads `libdexfile.so` with `RTLD_NODELETE` and publishes a table of dex API pointers | **RTLD/tooling direct**; not method execution, heap, managed GC, or JIT code GC |
| [`sigchainlib/sigchain.cc`](../../vendor/art/sigchainlib/sigchain.cc) | resolves the real libc signal-mask/action functions around ART's interposed wrappers | **RTLD/signal infrastructure direct**; AOT/JIT/nterp and managed-GC indirect because their fault/suspend paths depend on signal chaining; heap/JIT-code-GC none |
| [`openjdkjvm/OpenjdkJvm.cc`](../../vendor/art/openjdkjvm/OpenjdkJvm.cc) | exposes `JVM_FindLibraryEntry()` as a raw `dlsym` result for OpenJDK native-library integration | **RTLD/JNI direct**; AOT/JIT/nterp/heap/managed-GC/JIT-code-GC none at this API |
| [`adbconnection/adbconnection.cc`](../../vendor/art/adbconnection/adbconnection.cc) | resolves optional debugger-service callbacks from `RTLD_DEFAULT`, with static no-op function fallbacks | **RTLD/debugger direct**; execution engines, heap, managed GC, and JIT code GC none |
| [`compiler/optimizing/graph_visualizer.cc`](../../vendor/art/compiler/optimizing/graph_visualizer.cc) | resolves a factory from an optional disassembler DSO, calls it, and keeps the DSO live until the returned C++ object is destroyed | **RTLD/compiler-tooling direct**; it can inspect AOT/JIT-target machine bytes but is not execution, heap, managed GC, or JIT code GC |
| [`simulator/code_simulator_container.cc`](../../vendor/art/simulator/code_simulator_container.cc) | resolves a simulator factory and retains the DSO until the returned simulator object is destroyed | **RTLD/compiler/testing direct**; AOT/JIT/nterp/heap/managed-GC/JIT-code-GC none |

The external JVMTI utilities under
[`tools/jvmti-agents`](../../vendor/art/tools/jvmti-agents) repeat the agent
model by loading chained agents and retaining typed `Agent_OnLoad`,
`Agent_OnAttach`, and `Agent_OnUnload` pointers. They are **RTLD/JVMTI tool
direct**, not ART execution-engine, managed-heap, managed-GC, or JIT-code-GC
surfaces.

These tables have module/static lifetime rather than method or class-loader
lifetime, except where the underlying API explicitly manages a returned DSO
handle. For Wasm they should be statically linked/imported service tables or
omitted with the corresponding platform feature; they do not need the logical
PC and code-metadata model required by OAT, JIT, and nterp.

#### Wasm disposition

For the restricted browser runtime:

- replace dynamic JNI lookup with a build-time registry keyed by method/signature
  and backed by statically linked Wasm functions;
- use typed adapters or a uniform JNI bridge ABI for indirect calls;
- make unsupported `System.loadLibrary`, agents, plugins, and native bridge
  fail explicitly;
- do not fabricate `dlopen` handles or linear-memory function addresses; and
- model module/registry ownership separately if dynamic Wasm modules are added
  later.

Wasm dynamic-linking conventions can help a controlled application packaging
system, but they do not recreate the Android/Linux RTLD, native-loader
namespaces, ELF code addresses, arbitrary JNI ABI, or signal-handler contract.

### 7. Return PCs, stack maps, exceptions, deoptimization, and faults

**Classification:** AOT direct; JIT direct; nterp direct; RTLD/JNI indirect for
native frames/stubs; managed heap indirect; managed GC direct; JIT code GC
direct.

#### Quick frames retain physical return PCs

[`StackVisitor`](../../vendor/art/runtime/stack.cc) obtains a quick frame's
return-PC address from the architecture frame layout, reads the raw
`uintptr_t`, and can overwrite it. During a stack walk it treats the current
quick-frame PC as an interior executable address and asks the method for the
corresponding `OatQuickMethodHeader`.

[`ArtMethod::GetOatQuickMethodHeader(pc)`](../../vendor/art/runtime/art_method.cc)
illustrates why the method's current entrypoint is insufficient:

1. test whether the current non-stub entrypoint's header contains `pc`;
2. test the shared nterp range;
3. ask the JIT code cache to find a header containing `pc` for the method; and
4. fall back to the method's OAT code and test its range.

These fallbacks are necessary because instrumentation, JIT recompilation,
deoptimization, or class state may have changed the current entrypoint after
the frame was entered. The physical PC on the stack identifies the actual code
version and metadata.

#### Managed GC uses PCs to find roots

For an optimized quick frame, the chain is:

```text
physical frame PC
  -> containing OatQuickMethodHeader
  -> native PC offset within that code body
  -> CodeInfo stack-map row
  -> register mask, stack mask, and vreg locations
  -> actual managed references to visit/update
```

This makes executable PCs essential to managed GC without making them GC
roots. The collector marks or updates Java references described by the stack
map; it does not mark the PC itself.

The browser engine's native return PC is not exposed to guest Wasm and is not a
stable ART-visible identifier. A Wasm backend needs explicit managed frames or
shadow frames carrying a metadata/safepoint ID at every GC-capable call. The GC
must walk those records rather than inspect the engine's native call stack.

#### Catch and deoptimization targets are interior PCs

[`QuickExceptionHandler`](../../vendor/art/runtime/quick_exception_handler.cc)
maps a DEX catch location through `CodeInfo` to a native code offset, produces
an interior handler PC, and writes it to an architecture `Context` with
`SetPC()` before a long jump. Deoptimization similarly rebuilds interpreter
frames and redirects execution through quick/interpreter stubs.

OSR, catch delivery, and deoptimization therefore require **continuations**,
not merely callable method entrypoints. In a Wasm backend each permitted
continuation must be represented explicitly, for example by returning a tagged
result to a dispatcher or by calling a compiler-generated continuation
function. An arbitrary `entrypoint + byte_offset` jump is unavailable.

#### Fault handling reads and rewrites execution state

[`FaultManager`](../../vendor/art/runtime/fault_handler.cc) maintains raw
`{start, size}` executable ranges for:

- OAT code, registered as executable OAT files become reachable;
- JIT executable regions; and
- the nterp implementation.

In a signal handler it reads the architecture context PC, tests range
membership, validates the current `ArtMethod`, and delegates to architecture
handlers. Those handlers can inspect instruction bytes around the PC,
calculate the next/return PC, modify registers and stack words, and redirect
the context to ART exception, suspend, or stack-overflow stubs.

This is simultaneously AOT/JIT/nterp, exception, synchronization, and managed-
GC infrastructure. For example, implicit null/suspend checks can avoid an
explicit branch in generated code, and read-barrier/suspend machinery depends
on recognizing the faulting instruction sequence.

Browser Wasm traps are not resumable POSIX signals with writable `ucontext_t`.
The guest cannot inspect engine machine instructions or set the engine PC.
Therefore the Wasm compiler/interpreter must emit explicit null, bounds,
stack-overflow, suspend, and read-barrier checks and route failure through
ordinary Wasm control flow.

#### Executable-range removal is synchronized

Removing a generated-code range is not a simple container erase. The fault
manager preserves list-node visibility for concurrent signal readers and may
run a thread checkpoint before freeing a removed range. JIT code GC separately
proves that no quick frame points into a code allocation.

This lifetime protocol must be carried into any logical-code registry. Even if
there are no executable byte pointers, a `(blob_id, generation)` cannot be
reused while a managed frame, exception continuation, profiler sample, or
debugger record can still name the old generation.

### 8. Instrumentation is a cross-cutting executable-pointer consumer

**Classification:** AOT direct; JIT direct; nterp direct; switch direct;
RTLD/JNI direct for JNI/generic stubs; managed heap indirect; managed GC
indirect through deoptimization/stack walking; JIT code GC direct.

[`instrumentation.cc`](../../vendor/art/runtime/instrumentation.cc) treats raw
addresses as a method execution-state machine. `EntryPointString()` classifies
an address by pointer equality or OAT/JIT range membership as interpreter,
resolution, JIT, obsolete, nterp, generic JNI, OAT, hard-coded stub, or unknown.

Instrumentation can atomically replace a method's quick entrypoint to:

- force the switch interpreter;
- install or remove entry/exit support;
- select nterp or nterp-with-class-initialization;
- restore AOT/JIT optimized code;
- route through resolution; or
- reject invocation of obsolete methods.

It also walks already-active stacks. Entry/exit instrumentation can replace
physical return PCs and retain side records so the original continuation can
be restored. Deoptimization uses the frame PC/header/stack-map chain described
above. Replacing the current method entrypoint does not rewrite the identity of
code already executing.

The explicit Wasm replacement should be a tagged execution descriptor, for
example:

```text
ExecutionTarget {
  kind: switch | wasm_aot | runtime_stub | static_jni | ...,
  call_slot: typed table slot,
  code_blob_id: optional stable metadata owner,
  generation: stale-reference guard,
  flags: clinit/instrumentation/deopt policy
}
```

Instrumentation should switch descriptors and request explicit safepoint/
deoptimization actions. It should not infer execution kind from the numeric
range of a table slot or synthetic address.

### 9. Managed heap and GC boundary

#### Where method metadata lives

**Classification:** managed heap indirect; managed GC direct for method roots
and frame maps; AOT/JIT/nterp/RTLD indirect through `ArtMethod`; executable
pointers themselves are not managed objects or roots.

[`ClassLinker::AllocArtMethodArray()`](../../vendor/art/runtime/class_linker.cc)
allocates method arrays from a class-loader `LinearAlloc` with kind
`kArtMethodArray`. Boot/app images can instead contain packed method metadata.
Neither is an ordinary moving managed-heap object.

Managed objects point into that native metadata:

- [`mirror::Class::methods_`](../../vendor/art/runtime/mirror/class.h) is a
  native pointer to a `LengthPrefixedArray<ArtMethod>` stored in a 64-bit field;
- managed vtable and interface method arrays contain `ArtMethod*` values;
- embedded vtables contain `ArtMethod*` values; and
- reflection objects resolve to an `ArtMethod*` identity.

The normal dispatch chain is therefore:

```text
managed receiver/Class/vtable
        -> native ArtMethod*
        -> quick-entrypoint execution descriptor/address
        -> code or bridge
```

The managed heap side stores method identity, not a direct OAT/JIT/nterp code
pointer. This indirection is useful for Wasm: `ArtMethod*` can remain a linear-
memory metadata pointer while the entrypoint word is replaced with a tagged
descriptor/table index.

#### What `ArtMethod::VisitRoots()` does and does not visit

[`ArtMethod::VisitRoots()`](../../vendor/art/runtime/art_method-inl.h) visits:

- `declaring_class_`, which is a real `GcRoot<mirror::Class>`;
- the proxied interface method's roots when needed; and
- JIT root tables associated with reachable JIT code for the method.

It does **not** visit either `entry_point_from_quick_compiled_code_` or a JNI
function stored in `data_`. Those fields are not managed references. The
mark-compact collector's `LinearAlloc` visitor similarly knows where
`ArtMethod` declaring-class roots occur; it does not reinterpret pointer-sized
entrypoint fields as heap objects.

Image-space fixup can relocate method entrypoint fields because it knows the
saved OAT/image address domains. That is loader relocation. It must not be
confused with tracing or forwarding a Java object during an ordinary GC.

#### Four different GC relationships

The phrase "GC-related code pointer" covers four separate mechanisms:

| Mechanism | Executable pointer's role | What GC actually traces or updates |
|---|---|---|
| quick-frame root discovery | return/interior PC locates header and stack map | references in registers, stack slots, and vregs |
| AOT `.bss` roots | compiled code addresses an indirection table | `GcRoot` entries visited by `ClassTable` |
| JIT constant roots | JIT code/metadata identifies a separate root table | `GcRoot` entries visited/swept by `JitCodeCache` |
| JIT code GC | stack PCs mark live code allocations | code/data allocation lifetime, not Java objects |

There is also a fifth, callable-only surface: quick entrypoint tables contain
allocation, marking, and read-barrier function addresses. These functions
participate in GC, but their addresses are not roots.

#### Raw `ArtMethod*` values and class unloading

JIT maps, profiling structures, inline metadata, native stacks, JNI IDs, and
tooling can retain `ArtMethod*`. An `ArtMethod*` is a native metadata pointer,
not an executable pointer, but it often leads to one. Its lifetime is tied to
the defining class loader's `LinearAlloc` unless it belongs to a boot image or
other non-unloadable owner.

JIT inline info deliberately stores raw `ArtMethod*` values for JIT compilation
while AOT inline info uses reconstructible method indices. When a class loader
becomes unreachable, ART must invalidate/remove associated JIT code and maps
before releasing its method metadata. A Wasm design should prefer stable method
IDs with owner generations in long-lived code metadata rather than embed
unloadable `ArtMethod*` values.

#### Managed-heap verdict

The audited core paths show no general design in which a direct executable
address is a managed Java reference that the collector follows. Direct code
addresses live in native metadata, TLS, native containers, stack return slots,
image metadata, OS records, or code/data mappings.

That negative finding does not make GC easy on Wasm. Current compiled-frame GC
is still built around physical return PCs. The managed object layout can mostly
retain `ArtMethod*` indirection, but compiled Wasm frames need explicit root and
safepoint records visible in linear memory.

### 10. Ordinary C/C++ function pointers

**Classification:** callable-only; cross-cutting runtime infrastructure; stored
in native static/native-heap objects rather than managed heap; generally not
subject to code-address arithmetic.

ART also uses normal C/C++ callback machinery extensively. Representative
families include:

- `Runtime` hooks for `vfprintf`, `exit`, `abort`, and out-of-memory handling in
  [`runtime.h`](../../vendor/art/runtime/runtime.h);
- the sensitive-thread hook and pthread start/TLS-destructor callbacks in
  [`thread.cc`](../../vendor/art/runtime/thread.cc);
- `std::function<void(Thread*)>` closures and tasks in
  [`thread_pool.h`](../../vendor/art/runtime/thread_pool.h);
- C++ virtual callback interfaces in
  [`runtime_callbacks.h`](../../vendor/art/runtime/runtime_callbacks.h);
- signal-chain handlers and native-bridge signal callbacks;
- the JNI/JavaVM function tables discussed above;
- ordinary C++ vtables throughout ART; and
- replaceable native-debugger notification pointers such as
  `__jit_debug_register_code_ptr`.

These pointers target executable code, but they are normally used only through
a typed indirect call plus null/equality checks. ART does not recover an
`OatQuickMethodHeader`, calculate a method PC offset, or use range containment
for an ordinary `std::function` or virtual call.

This is the portion of the audit most naturally handled by an existing C++ to
Wasm toolchain. The toolchain can lower function pointers and vtables to table
slots. Constraints remain:

- function signature/type compatibility must match Wasm indirect-call rules;
- function pointers must not be assumed to equal linear-memory data pointers;
- a table slot must not be dereferenced or used as a code-byte address;
- dynamically supplied native callback addresses need a registry/import
  boundary; and
- owner lifetime must outlive every stored callback.

ART frequently transports function addresses as `void*` because native
platform ABIs support it, and POSIX specifically defines the intended `dlsym`
usage. That source pattern should not be treated as a portable Wasm contract.
Where a callable-only use is retained, prefer an actual typed function pointer,
typed table slot, or explicit callback ID.

### 11. Address provenance and lifetime inventory

The owner is as important as the numeric value. The following table summarizes
the principal provenance classes.

| Address/value provenance | Typical storage/consumer | Owner and valid lifetime | Invalidated by |
|---|---|---|---|
| `libart` quick/runtime/helper function | `ArtMethod`, TLS entrypoint table, callback table | runtime module/process | runtime/module unload |
| boot/app OAT method or trampoline | image `ArtMethod`, OAT maps, return PCs | mapped `OatFile`/image | OAT unmap or image teardown |
| private JIT method/JNI stub | method entrypoint, code maps, OS/debug records, return PCs | JIT code/data allocation | code GC after stack liveness proof |
| zygote/shared JIT code | zygote map and shared region | shared code region policy | shared-region teardown |
| nterp function/handler range | many method entrypoints, synthetic header, fault ranges | runtime module | runtime/module teardown |
| JNI DSO symbol | `ArtMethod::data_`, lifecycle callback | `SharedLibrary`/native-loader handle | class-loader-driven or runtime unload |
| native-bridge trampoline | `ArtMethod::data_`, signal chain | native-bridge implementation/DSO | trampoline destruction or bridge unload |
| agent/plugin function | `Agent`/`Plugin` record | corresponding DSO handle | agent/plugin shutdown/unload |
| ordinary static callback | hook/table/vtable/TLS | defining Wasm/native module | module or owner teardown |
| interior quick return/catch/OSR PC | quick frame, context, profiler sample | exact code generation/allocation | frame/record retirement, then owner teardown |
| branch/reference encoded in instructions | executable bytes | exact linked code layout plus target owner | code unmap/relink or target invalidation |
| perf executable marker address | `JitLogger` | marker mapping | logger shutdown/unmap |

Several non-obvious consequences follow:

- Pointer equality is meaningful only within a provenance domain and owner
  generation.
- The current `ArtMethod` entrypoint is not a lifetime reference for old code.
- An interior PC must retain exact code-version identity, not just method
  identity.
- OAT/JIT/native-DSO addresses require different teardown protocols.
- A table slot without a generation can reproduce native address-reuse bugs if
  it is recycled while stale logical PCs or callbacks remain.

### 12. Required Wasm execution model

The following is the minimum abstraction split implied by the audit. Names are
illustrative, not a mandate for a particular C++ layout.

| Current native value/operation | Required Wasm-side concept |
|---|---|
| `void*` quick entrypoint | tagged `ExecutionTarget` with kind and typed call slot |
| executable code base | stable `CodeBlobId`/artifact method ID |
| interior native PC | `LogicalPc { blob_id, offset_or_safepoint, generation }` |
| header before code | side-table `CodeDescriptor` indexed by blob ID |
| code-to-`CodeInfo` subtraction | explicit metadata index in `CodeDescriptor` |
| address range containment | blob/generation equality plus validated logical offset |
| return PC read from engine stack | explicit managed frame/continuation record |
| catch/OSR `entry + offset` | compiler-created continuation/OSR entry or dispatcher state |
| quick TLS `void*` helper | typed helper-table slot or direct/imported function |
| JNI `void*` | signature-aware static registry slot/adapter |
| DSO handle and `dlsym` result | packaged module/registry ownership, or unsupported |
| JIT address-keyed map | handle-keyed code registry |
| JIT stack-PC marking | active-frame references/epochs to blob generations |
| native fault PC rewrite | explicit check and ordinary Wasm exception/result flow |
| native debugger code address | logical-PC trace/source map/engine tooling API |

#### Hard invariants

A correct design should enforce these invariants rather than rely on convention:

1. A linear-memory pointer, `ArtMethod*`, function-table slot, code-blob ID,
   logical PC, and managed-object reference are different types/domains.
2. No table slot is passed to code that subtracts, dereferences, range-checks,
   or registers it as a linear-memory executable address.
3. Every compiled frame exposes an ART-visible method/code-generation identity
   and safepoint/continuation state without reading the browser engine's stack.
4. Every managed reference live across a GC-capable call is in an explicit
   root location visible to ART.
5. Metadata and root tables are committed before a call target becomes
   reachable.
6. A code/table generation is not recycled while a frame, continuation,
   profiler/debug record, or callback can name it.
7. Dynamic JNI/module loading never fabricates a native address; unsupported
   cases fail deterministically.

#### Per-subsystem disposition

| Subsystem | Current contract on browser wasm64 | Recommended restricted-port disposition |
|---|---|---|
| physical OAT AOT | not portable | replace with new offline Wasm AOT artifact and method table |
| native JIT code cache | not portable | disable; future module JIT requires a new host/code model |
| OSR | not portable | disable until explicit Wasm OSR entry functions exist |
| nterp | not portable | disable; use switch interpreter |
| switch interpreter | conditionally portable | remove architecture assembly wrapper and compiled transition assumptions |
| quick runtime helpers | conditionally portable | typed slots/direct Wasm calls with a defined ABI |
| JNI | conditionally portable when closed-world | static registry and Wasm-compiled implementations only |
| RTLD/agents/plugins/native bridge | not portable as current contract | unsupported or replace with controlled packaged Wasm modules |
| managed heap metadata | mostly reusable | keep `ArtMethod*` identity, replace executable entrypoint representation |
| managed GC root tables | reusable as data model | retain explicit roots; add Wasm-visible frame/safepoint records |
| quick stack walking/faults | not portable | explicit shadow frames, logical PCs, and explicit checks |
| ordinary C++ callbacks/vtables | toolchain-portable with constraints | retain typed uses; remove function/data-pointer assumptions |

#### Suggested bring-up order

1. Introduce distinct C++ types for call slots, blob IDs, metadata IDs, and
   logical PCs before adding Wasm code generation.
2. Convert `ArtMethod` dispatch to an explicit tagged descriptor while keeping
   native adapters for existing targets.
3. Bring up the C++ switch interpreter without `ExecuteSwitchImplAsm` and
   without switch-to-native-quick transitions.
4. Establish explicit managed shadow frames/root maps at all GC-capable calls.
5. Add the static JNI/runtime-helper registry.
6. Add offline Wasm AOT functions with a uniform invocation ABI and explicit
   code descriptors.
7. Add exceptions, stack traces, instrumentation, and deoptimization using
   logical continuations.
8. Treat JIT, nterp, OSR, and dynamic module loading as separate later research
   projects, not compatibility toggles.

### 13. Audit limitations

This is a source-family audit, not a proof that every syntactic function-pointer
declaration in ART has been enumerated. It deliberately groups:

- equivalent architecture backends;
- ordinary virtual dispatch and callback templates;
- tests that repeat production pointer operations; and
- native debugger/profiler consumers with the same ownership model.

The audit focused on runtime/compiler paths that introduce a distinct
representation, arithmetic, provenance, lifetime, GC, or Wasm requirement.
New platform ports and downstream changes should be checked against the hard
invariants above. In particular, any new cast between function pointer,
`void*`, `uintptr_t`, and byte pointer deserves review even if a native compiler
accepts it.

The exact Wasm C/C++ function-pointer representation is toolchain ABI specific.
Nothing here assumes that a particular compiler uses a 32-bit or 64-bit table
index. The portable conclusion is narrower and stronger: whatever its concrete
representation, a Wasm callable reference is not an ART-visible byte address
for engine-generated executable code.

### 14. Source index

Central method and dispatch:

- [`art_method.h`](../../vendor/art/runtime/art_method.h)
- [`art_method.cc`](../../vendor/art/runtime/art_method.cc)
- [`instrumentation.cc`](../../vendor/art/runtime/instrumentation.cc)
- [`quick_trampoline_entrypoints.cc`](../../vendor/art/runtime/entrypoints/quick/quick_trampoline_entrypoints.cc)
- [`runtime_asm_entrypoints.h`](../../vendor/art/runtime/entrypoints/runtime_asm_entrypoints.h)
- [`code_generator_arm64.cc`](../../vendor/art/compiler/optimizing/code_generator_arm64.cc)
- [`fast_compiler_arm64.cc`](../../vendor/art/compiler/optimizing/fast_compiler_arm64.cc)

AOT/OAT/image:

- [`oat_quick_method_header.h`](../../vendor/art/runtime/oat/oat_quick_method_header.h)
- [`oat_quick_method_header.cc`](../../vendor/art/runtime/oat/oat_quick_method_header.cc)
- [`oat_file-inl.h`](../../vendor/art/runtime/oat/oat_file-inl.h)
- [`oat_file.cc`](../../vendor/art/runtime/oat/oat_file.cc)
- [`oat.cc`](../../vendor/art/runtime/oat/oat.cc)
- [`image_writer.cc`](../../vendor/art/dex2oat/linker/image_writer.cc)
- [`image_space.cc`](../../vendor/art/runtime/gc/space/image_space.cc)
- [`linker_patch.h`](../../vendor/art/compiler/linker/linker_patch.h)
- [`aot_unwind_windows.cc`](../../vendor/art/runtime/multiplatform/windows/aot_unwind_windows.cc)
- [`aot_cfg_windows.cc`](../../vendor/art/runtime/multiplatform/windows/aot_cfg_windows.cc)

Interpreters and entrypoint tables:

- [`interpreter.cc`](../../vendor/art/runtime/interpreter/interpreter.cc)
- [`interpreter_common.cc`](../../vendor/art/runtime/interpreter/interpreter_common.cc)
- [`interpreter_switch_impl.h`](../../vendor/art/runtime/interpreter/interpreter_switch_impl.h)
- [`nterp.cc`](../../vendor/art/runtime/interpreter/mterp/nterp.cc)
- [`quick_entrypoints.h`](../../vendor/art/runtime/entrypoints/quick/quick_entrypoints.h)
- [`jni_entrypoints.h`](../../vendor/art/runtime/entrypoints/jni/jni_entrypoints.h)
- [`thread.h`](../../vendor/art/runtime/thread.h)

JIT:

- [`jit_memory_region.h`](../../vendor/art/runtime/jit/jit_memory_region.h)
- [`jit_memory_region.cc`](../../vendor/art/runtime/jit/jit_memory_region.cc)
- [`jit_scoped_code_cache_write.h`](../../vendor/art/runtime/jit/jit_scoped_code_cache_write.h)
- [`jit_code_cache.h`](../../vendor/art/runtime/jit/jit_code_cache.h)
- [`jit_code_cache.cc`](../../vendor/art/runtime/jit/jit_code_cache.cc)
- [`jit_code_cache-inl.h`](../../vendor/art/runtime/jit/jit_code_cache-inl.h)
- [`jit.cc`](../../vendor/art/runtime/jit/jit.cc)
- [`small_pattern_matcher.cc`](../../vendor/art/runtime/jit/small_pattern_matcher.cc)
- [`stack_map_stream.cc`](../../vendor/art/compiler/optimizing/stack_map_stream.cc)
- [`jit_unwind_windows.cc`](../../vendor/art/runtime/multiplatform/windows/jit_unwind_windows.cc)
- [`debugger_interface.cc`](../../vendor/art/runtime/jit/debugger_interface.cc)
- [`jit_logger.cc`](../../vendor/art/compiler/jit/jit_logger.cc)

JNI/DSO/native bridge:

- [`java_vm_ext.cc`](../../vendor/art/runtime/jni/java_vm_ext.cc)
- [`jni_internal.cc`](../../vendor/art/runtime/jni/jni_internal.cc)
- [`native_bridge_art_interface.cc`](../../vendor/art/runtime/native_bridge_art_interface.cc)
- [`libnativebridge/native_bridge.cc`](../../vendor/art/libnativebridge/native_bridge.cc)
- [`agent.cc`](../../vendor/art/runtime/ti/agent.cc)
- [`plugin.cc`](../../vendor/art/runtime/plugin.cc)
- [`libartpalette/apex/palette.cc`](../../vendor/art/libartpalette/apex/palette.cc)
- [`libnativebridge/native_bridge_lazy.cc`](../../vendor/art/libnativebridge/native_bridge_lazy.cc)
- [`libnativeloader/native_loader_lazy.cpp`](../../vendor/art/libnativeloader/native_loader_lazy.cpp)
- [`libdexfile/external/dex_file_supp.cc`](../../vendor/art/libdexfile/external/dex_file_supp.cc)
- [`sigchainlib/sigchain.cc`](../../vendor/art/sigchainlib/sigchain.cc)
- [`openjdkjvm/OpenjdkJvm.cc`](../../vendor/art/openjdkjvm/OpenjdkJvm.cc)
- [`adbconnection/adbconnection.cc`](../../vendor/art/adbconnection/adbconnection.cc)
- [`compiler/optimizing/graph_visualizer.cc`](../../vendor/art/compiler/optimizing/graph_visualizer.cc)
- [`simulator/code_simulator_container.cc`](../../vendor/art/simulator/code_simulator_container.cc)
- [`tools/jvmti-agents`](../../vendor/art/tools/jvmti-agents)

PCs, stack walking, faults, heap, and GC:

- [`stack.cc`](../../vendor/art/runtime/stack.cc)
- [`quick_exception_handler.cc`](../../vendor/art/runtime/quick_exception_handler.cc)
- [`fault_handler.cc`](../../vendor/art/runtime/fault_handler.cc)
- [`class_linker.cc`](../../vendor/art/runtime/class_linker.cc)
- [`class_table-inl.h`](../../vendor/art/runtime/class_table-inl.h)
- [`class.h`](../../vendor/art/runtime/mirror/class.h)
- [`class-inl.h`](../../vendor/art/runtime/mirror/class-inl.h)
- [`mark_compact.cc`](../../vendor/art/runtime/gc/collector/mark_compact.cc)

Ordinary callback examples:

- [`runtime.h`](../../vendor/art/runtime/runtime.h)
- [`thread.cc`](../../vendor/art/runtime/thread.cc)
- [`thread_pool.h`](../../vendor/art/runtime/thread_pool.h)
- [`runtime_callbacks.h`](../../vendor/art/runtime/runtime_callbacks.h)

## Part II — Focused executable-pointer and Wasm-impact audit

### Audit question and source baseline

This document audits ART uses of values that are callable function pointers,
addresses in executable mappings, physical program counters (PCs), or identities
derived from any of those values. The question is not merely whether C++ can call
an ordinary function pointer after compilation to WebAssembly. The question is
whether a use assumes that callable code also has a byte address in the data
address space. That assumption fails when a Wasm C/C++ function pointer is a
function-table slot rather than a linear-memory code address.

The audit was performed against this repository's ART checkout at
`vendor/art`, branch `artmp_android-16.0.0_r4`, commit
`03d55ca0174dbf39b54444ce5fdf4a55e5dce331`. File and line references describe
that source baseline. Tests are used as corroboration, but the classifications
are based on production paths unless explicitly labeled otherwise.

The requested filename is retained because it is concise, but the scope is
intentionally wider than ISO C++ function pointers. "Executable pointer" below
includes all of the following:

| Value kind | Native ART meaning | Wasm representation or replacement |
|---|---|---|
| C/C++ function pointer | Callable address, commonly also cast to `void*` or `uintptr_t` | Toolchain-managed function-table reference/index; callable only through the matching Wasm type/table contract |
| Quick/JNI method entrypoint | Physical quick-code, assembly-stub, nterp, or JNI address stored in `ArtMethod` | Typed execution kind plus table slot/thunk; it cannot remain a generic linear-memory `void*` |
| Quick runtime entrypoint | Physical helper address stored in per-thread TLS and loaded by generated code | Typed import/direct call or table slot; a data load cannot be followed by a native branch |
| Code pointer | Address of physical instruction bytes, sometimes ISA-tagged | No equivalent for a Wasm function; an optional synthetic descriptor address is data only |
| Return PC/current PC | Physical location inside a compiled method or assembly stub | Engine-private and unavailable; publish a safepoint/DEX-PC identity in an explicit managed frame |
| OAT/JIT metadata pointer | Header or stack-map data discovered by subtraction/range lookup from a code address | Linear-memory metadata indexed explicitly by method and safepoint ID |
| DSO symbol pointer | `dlsym()` result naming callable code or data | Closed-world registry must distinguish typed function slots from linear-memory data addresses |

Four different Wasm namespaces must never be conflated: a module-local function
index, a shared function-table slot, a linear-memory byte offset, and an
engine-private instruction/return location. The first two are not necessarily
equal, neither is a byte address, and the fourth is not exposed to ART.

### Classification labels

Each audited use is marked with the execution or runtime areas that own it:

- **AOT/OAT**: `dex2oat`, OAT/ELF loading, boot/app images, or offline compiled
  quick code.
- **JIT**: JIT compilation, JIT code cache, OSR, debug registration, or code
  reclamation.
- **nterp/mterp**: assembly interpreters and their PC/entrypoint contracts.
- **switch**: the portable C++ switch interpreter.
- **JNI/native**: Java native methods, JNI stubs, `RegisterNatives`, or critical
  native calls.
- **RTLD/DSO**: ELF/shared-library loading and symbol resolution.
- **stack/exception**: frame walking, unwinding, catch lookup, deoptimization,
  or stack traces.
- **instrumentation/JVMTI**: entry/exit hooks, tracing, debugger, profiling,
  obsolete methods, or method redefinition.
- **GC/heap**: root discovery, stack maps, read barriers, allocation entrypoints,
  code roots, or collector interaction.
- **fault**: signal context, implicit checks, guard pages, or PC rewriting.

The Wasm effect uses these verdicts:

| Verdict | Meaning |
|---|---|
| **Representation-only** | A typed indirect call can work as a table call, but storage, signatures, table ownership, or null handling must be made explicit. No byte-address semantics are required. |
| **Synthetic-compatible** | The consumer can use a bounded synthetic code identity only after every lookup is redirected to explicit metadata. The value must never be called or treated as real code. |
| **Redesign** | The path depends on byte-addressable instructions, real PCs, executable mappings, native frames, or signal contexts and cannot be preserved by substituting a table index. |
| **Disable** | The proposed switch plus offline-Wasm-AOT profile should omit the feature rather than emulate its current contract. |
| **Unaffected data pointer** | The value is an ordinary object/metadata pointer in linear memory and is not an executable pointer despite nearby overloaded storage. |

### Initial representation inventory

#### `ArtMethod` overloads callable code and ordinary data

[`art_method.h`](../../vendor/art/runtime/art_method.h) defines two pointer-sized
fields at the end of every method. Semantically,
`entry_point_from_quick_compiled_code_` names an execution entrypoint, although
image construction temporarily stores target-relative encodings in it. `data_`
is a tagged-by-method-kind union in practice: for native methods it is a JNI
function or resolver; for runtime resolution methods it can also be callable;
for other method kinds it can be an `ImtConflictTable*`, another `ArtMethod*`, or
a DEX code-item pointer/offset. Consequently, globally converting both fields to
Wasm table slots would corrupt valid linear-memory data pointers, while leaving
both as `void*` would retain an ambiguous namespace.

The accessors make the overloading explicit:

- `Get/SetEntryPointFromQuickCompiledCode[PtrSize]()` read and write the quick
  entrypoint as a native pointer-sized `const void*` (`art_method.h:800-819`).
- `Get/SetEntryPointFromJni[PtrSize]()` alias the JNI entrypoint onto `data_`
  (`art_method.h:890-911`).
- `Get/SetDataPtrSize()`, `SetImtConflictTable()`, and
  `SetSingleImplementation()` use the same bits as ordinary data or method
  pointers (`art_method.h:837-911`).
- `PtrSizedFields` documents the complete union and says quick dispatch invokes
  the second pointer (`art_method.h:1168-1185`).

This is **AOT/OAT + JIT + nterp + switch bridge + JNI/native +
instrumentation**. Direct or virtual compiled calls eventually load the quick
field and branch using the physical quick ABI. `ArtMethod::Invoke()` enters an
ISA-specific quick invoke stub, which in turn performs that dispatch
(`art_method.cc:404-479`). A Wasm port therefore needs an execution-kind and
typed-slot side table (or a changed `ArtMethod` layout), not a numeric table
index disguised as the existing code `void*`.

Pure equality against well-known stubs is not itself byte-address arithmetic,
but it still compares identities from a function namespace after erasing their
type. It is **representation-only** if every well-known stub has a stable typed
registry identity. Header discovery and PC containment performed after those
comparisons are separately classified as **redesign** below.

#### Per-thread quick and JNI helper tables erase 176 callable values

[`quick_entrypoints_list.h`](../../vendor/art/runtime/entrypoints/quick/quick_entrypoints_list.h)
declares 174 typed quick helpers. The macro in
[`quick_entrypoints.h`](../../vendor/art/runtime/entrypoints/quick/quick_entrypoints.h)
stores every helper as `void*`, despite accepting typed setters. Together with
the two raw JNI resolver cells in
[`jni_entrypoints.h`](../../vendor/art/runtime/entrypoints/jni/jni_entrypoints.h),
these tables are embedded in each `Thread` (`thread.h:2630-2633`). Compiled
quick/JNI code loads a cell at a fixed TLS offset and branches to the resulting
physical address.

`Thread::InitTlsEntryPoints()` additionally treats both structures as one
contiguous array of `uintptr_t` and initializes every cell by converting
`UnimplementedEntryPoint` to an integer (`thread.cc:184-198`). This is direct
evidence that current ART expects a function address, object pointer, and
integer of the target pointer width to be interchangeable for storage.

This is **AOT/OAT + JIT + JNI/native + GC/heap + instrumentation**. The GC tie
is direct: allocation and read-barrier helpers are members of the same table,
and collector state dynamically replaces read-barrier entries. Ordinary typed
Wasm indirect calls can implement the semantic operation, so the table is
mostly **representation-only** rather than intrinsically dependent on code
bytes. However, it requires generated Wasm calls/imports or explicitly typed
table slots. Preserving the current erased `void*` TLS blob and native
load-and-branch sequences is a **redesign**.

#### Assembly stub identities are intentionally converted to data pointers

[`runtime_asm_entrypoints.h`](../../vendor/art/runtime/entrypoints/runtime_asm_entrypoints.h)
returns the addresses of JNI lookup, IMT conflict, quick-to-interpreter,
obsolete-method, generic-JNI, proxy, resolution, and deoptimization assembly
stubs as `const void*`. These identities are installed in `ArtMethod`, compared
to classify current dispatch state, and sometimes used as replacement
entrypoints.

This is **AOT/OAT + JIT + nterp/switch bridge + JNI/native +
instrumentation/JVMTI + stack/exception**. Equality/classification can become
an execution-kind enum and is **representation-only**. Calling through the
current quick ABI, using a stub as a physical PC, or redirecting a saved native
PC to one of these addresses is **redesign**.

### Detailed subsystem audit

#### OAT/AOT is a physical code-layout format, not just a method table

An OAT method does not name an abstract callable. `OatMethodOffsets::code_offset_`
is added to the mapped OAT base to form the quick-code address
(`oat_file-inl.h:94-99`). The runtime then treats the bytes immediately before
that address as an `OatQuickMethodHeader` and subtracts a second encoded offset
from the code address to find `CodeInfo` (`oat_file-inl.h:74-92`). The header API
itself exposes all of the relevant native-address assumptions
(`oat_quick_method_header.h:51-203`):

- `FromCodePointer()` subtracts the header size from code;
- `NativeQuickPcOffset()` subtracts the entrypoint from a physical PC;
- `GetOptimizedCodeInfoPtr()` subtracts `code_info_offset_` from code;
- `Contains()` compares a PC with an instruction-byte interval and accounts for
  ARM/Thumb entrypoint tagging;
- `GetCodeSize()` decodes metadata associated with those instruction bytes;
- `ToDexPc()` selects a stack map by native PC offset, while
  `ToNativeQuickPc[ForCatchHandlers]()` reverses that mapping by adding a native
  offset to the entrypoint (`oat_quick_method_header.cc:35-126`).

The same assumption is serialized by dex2oat. `OatWriter` aligns an executable
section, places a header immediately before each instruction array, makes the
stack-map offset code-relative, writes physical trampoline offsets, and records
native debug code ranges (`oat_writer.cc:1260-1410,2461-2510`). `OatHeader`
turns each serialized trampoline offset back into `&header + offset`
(`oat.cc:240-365`). During image creation, `ImageWriter` also uses a quick
entrypoint as an OAT-relative value in the special low-32-bit image-writing
representation (`image_writer.cc:3478-3530`). These are not valid operations on
a Wasm function-table slot, even if that slot happens to be integer-sized.

Call-site linking adds an **AOT/compiler + JNI/native** dependency distinct from
header lookup. `LinkerPatch` has physical instruction-patch kinds for a JNI
entrypoint field, relative call, runtime-entrypoint call, and Baker branch
(`compiler/linker/linker_patch.h:49-66,117-132,215-230`). On ARM64, an AOT slow
path emits a placeholder `BL` for later redirection to an entrypoint thunk; a
critical-native invoke either uses PC-relative patches to load
`ArtMethod::EntryPointFromJni` or loads that field and executes `BLR`
(`compiler/optimizing/code_generator_arm64.cc:5075-5153,5385-5399`). The emitted
patch list includes the JNI-field references and runtime-entrypoint calls, and
the generated thunks load a quick TLS cell before jumping
(`code_generator_arm64.cc:5609-5650`). `OatWriter` and the ISA patcher then
rewrite actual instruction displacements (`oat_writer.cc:1870-1889`;
`dex2oat/linker/arm64/relative_patcher_arm64.cc:314-337,374-386`). The generic
`kCallRelative` method-call path still exists, including thunk machinery, but
this baseline explicitly says that patch kind is currently unused
(`oat_writer.cc:1768-1775,1956-1973`).

Critical-native frame sizing has a related **JNI/native + stack metadata**
dependency: when invoked from compiled managed code, the runtime helper receives
the caller PC, resolves the caller's method header and native-PC stack map, and
uses inline information to recover the actual invoke and its shorty
(`entrypoints/jni/jni_entrypoints.cc:135-190`). A Wasm call site must carry this
signature/frame information explicitly; a whole-function table slot cannot
identify the inline call site.

This physical patch/thunk machinery is **redesign** for a Wasm backend. A known
callee should be a Wasm direct-call relocation; a dynamic method, JNI target,
or runtime helper should use an exact-signature shared-table/import relocation.
Data references such as an `ArtMethod*` or `.bss` entry remain linear-memory
relocations. There is no native instruction displacement to patch and no valid
operation in which an AOT linker computes a table slot's byte distance from a
call instruction.

Boot and app images preserve the same native-address contract after creation.
The runtime-image writer installs OAT trampoline or method addresses into the
quick and JNI fields (`runtime_image.cc:944-980`). At load time, `ImageSpace`
constructs a code-address forwarder from the old and new OAT mappings, applies
it to both method entrypoint fields, and elsewhere relocates the packed quick
field with the same generic native-pointer delta machinery
(`gc/space/image_space.cc:1296-1303,1395-1428,2609-2630`). This is **AOT/OAT +
heap/image loading** and is another **redesign**, not an integer-width fix:
shared-table slots must be linked by function-symbol relocation, while genuine
image and metadata pointers continue to use linear-memory relocation.

This is **AOT/OAT + stack/exception + GC/heap + JNI/native + native debug** and
is **redesign**. The offline compiler can retain DEX-PC maps, frame/root maps,
inline information, and method metadata, but the Wasm artifact must index them
explicitly by method and safepoint/call-site identity. It cannot reuse the
native OAT convention of discovering data by subtracting from a callable.
Native OAT instruction blobs, quick trampolines, unwind data, and native debug
address ranges should be **disabled** for the proposed Wasm target.

Assigning each Wasm method a synthetic linear-memory "code descriptor" can
help existing maps preserve stable identity, but only as **synthetic-compatible
data**. Every consumer must first resolve the descriptor through a registry.
There must be no header subtraction, byte-range test, function call, or attempt
to derive an engine PC from it.

#### Quick stack walking makes return PCs part of the managed-runtime ABI

`StackVisitor` does substantially more than produce diagnostic traces. For a
quick frame it reads the saved return PC from an ISA-defined frame offset
(`stack.cc:583-595`), resolves an `OatQuickMethodHeader`, subtracts the method
entrypoint to obtain a native PC offset, selects a stack map, and advances the
stack pointer using `QuickMethodFrameInfo` (`stack.cc:95-169,221-239,816-970`).
Optimized vreg reconstruction and inlined-frame expansion use the same selected
`CodeInfo` (`stack.cc:308-495`). Thus all of these operations depend on a native
quick frame and on a return address that lies inside byte-addressable code.

Exception delivery closes the loop in the other direction. Catch search obtains
the DEX PC from the current native PC, looks up a catch stack map, converts the
handler DEX PC back into a physical code address, and stores that address and
the native SP into an ISA `Context` for a long jump
(`quick_exception_handler.cc:125-145,795-830`). Deoptimization likewise rebuilds
shadow frames from native quick frames before jumping to an invoke/interpreter
bridge. A Wasm engine's return address and native stack are not exposed in a
portable form, and a function-table index identifies a whole function rather
than an interior call site.

This is **AOT/OAT + JIT + nterp + stack/exception + instrumentation/JVMTI** and
is **redesign**. In the switch plus offline-Wasm-AOT profile, generated Wasm
must maintain an explicit managed frame chain in linear memory. At each point
where collection, exception delivery, deoptimization, suspension, or inspection
can occur, the frame must publish at least method identity, a safepoint/DEX-PC
identity, caller link, logical vregs/spills required by the selected metadata,
and root locations. Exception dispatch must resume through structured Wasm
control flow or a dispatcher state, not by writing an engine PC.

#### GC root correctness depends on native PCs, not merely method identity

The most consequential consumer is `ReferenceMapVisitor`. For an optimized
quick frame it takes the current saved PC, calls
`OatQuickMethodHeader::NativeQuickPcOffset()`, finds the exact `StackMap`, and
uses its stack and register masks to visit and update moving-GC roots
(`thread.cc:4487-4534`). Precise visiting further maps those physical locations
back to DEX registers (`thread.cc:4589-4648`). Native and proxy frames use
separate ABI-specific argument layouts. One native-intrinsic carve-out even
classifies the current PC by testing whether it lies in a boot-image OAT mapping
(`thread.cc:4433-4447`).

This is **GC/heap + AOT/OAT + JIT + stack** and is **redesign**, with correctness
rather than observability at stake. A fake entry address plus `pc - entry` cannot
select the right root map because the engine-internal return location is absent.
The replacement managed frame must publish a safepoint ID before a GC-visible
call or poll, and the offline artifact must map `(method ID, safepoint ID)` to
root slots. Roots need to live in known linear-memory frame slots or another
collector-visible handle structure; relying on engine registers is not viable.

Some nearby GC data remains ordinary data. OAT `.bss` roots, class tables,
DexCache objects, and object/metadata pointers are **unaffected data pointers**
as long as their lookup is not derived from a code address. Allocation and read
barrier *helper callables* in the thread entrypoint table are the separate
representation issue described above.

#### nterp intentionally impersonates compiled native code

nterp is not simply a faster spelling of the switch loop. ART obtains its
executable extent by subtracting the symbols `ExecuteNterpImpl` and
`EndExecuteNterpImpl`, converts those function addresses to byte arrays, and
does the same for its clinit variant (`interpreter/mterp/nterp.cc:108-135`). It
also verifies a fixed-width assembly handler region by subtracting handler
symbols (`nterp.cc:138-155`).

To integrate with the quick walker, ART fabricates a shared
`OatQuickMethodHeader` immediately before the nterp entrypoint
(`oat_quick_method_header.cc:129-147`). `IsNterpPc()` is a physical range test.
An nterp frame follows optimizing-compiler ABI conventions, records a native
return PC, and is walked as compiled code; its helper documentation explicitly
describes the prefixed header and its separate DEX-register/reference arrays
(`nterp_helpers.cc:29-101`). Catch delivery returns the single physical address
`artNterpAsmInstructionEnd` as a landing pad (`nterp_helpers.cc:223-227`).

This is **nterp/mterp + AOT/OAT + stack/exception + GC/heap** and should be
**disabled** for the Wasm profile. Replacing just the nterp entrypoint with a
table slot leaves its range, frame, landing-pad, and PC contracts broken. Its
parallel reference-array design is nevertheless useful precedent for explicit
roots in the new Wasm managed-frame layout.

#### The native JIT requires executable memory and address-derived ownership

`JitMemoryRegion` creates executable and writable/non-executable views (using
`memfd` or platform equivalents), reserves and commits instruction storage,
copies generated code, performs instruction-cache maintenance, and issues a
sync-core `membarrier` (`jit_memory_region.cc:127-274,549-632`). This is the
opposite of the Wasm security and compilation model: a Wasm module cannot write
new engine instructions into linear memory and branch to them.

The JIT cache also makes code addresses its primary keys:

- committed code has an `OatQuickMethodHeader` immediately before the
  instruction bytes, while `CodeInfo` is found through a backwards 32-bit delta
  (`jit_code_cache.cc:667-675,700-905`);
- `ContainsPc()` classifies raw addresses by executable mappings, and
  `LookupMethodHeader()` performs ordered pointer lookup plus code-range tests
  to recover a method version (`jit_code_cache.cc:304-310,1450-1530`);
- maps and sets associate raw entrypoints with methods, OSR versions, JNI stubs,
  saved entrypoints, zygote code, and zombie allocations
  (`jit_code_cache.h:239-590`);
- code-cache GC walks thread stacks, marks executable allocations reached by
  saved PCs/entrypoints, subtracts the header size to find allocation starts,
  and frees unmarked code (`jit_code_cache.cc:1120-1325`);
- `GetRootTable()` discovers the stack-map data from a code header and then
  subtracts the root-table size. `VisitRootTables()` and `SweepRootTables()`
  use it to mark, update, and clear embedded class, string, method-type, and
  call-site roots (`jit_code_cache-inl.h:30-75`,
  `jit_code_cache.cc:427-523,667-675`).

This is **JIT + stack/exception + GC/heap + JNI/native + instrumentation/native
debug**. Runtime method compilation, OSR, JIT JNI-stub compilation, executable
code-cache collection, zygote JIT sharing, and native JIT debug registration are
all **disabled** in the proposed offline-Wasm-AOT profile. Merely storing a Wasm
table index in `ArtMethod` would not provide code bytes, interior PCs, range
ownership, patchable call sites, or reclaimable executable allocations. The
JIT's logical metadata formats can inform the offline artifact, but all lookup
must be keyed explicitly and its managed roots must be normal GC-visible data.

Several smaller JIT paths reinforce that verdict:

- OSR builds an ABI-shaped native stack frame, computes an interior native PC as
  `entrypoint + stack-map offset`, and passes it to an assembly stub that jumps
  into the middle of compiled code (`jit.cc:405-568`, `jit.h:92-114`). This is
  **JIT + stack** and **disabled**. A future Wasm tier would need an explicit
  state-transfer entry function, not an interior PC.
- `SmallPatternMatcher` returns addresses of templated C++ functions and installs
  them directly as quick entrypoints because ARM's C++ and managed ABIs happen
  to be compatible (`small_pattern_matcher.cc:58-154,195-295`,
  `jit.cc:138-154`). Typed Wasm thunks could express the small operations, but
  the current erased-address/quick-ABI shortcut is **JIT** and **disabled** with
  the JIT; offline AOT should just emit the equivalent Wasm body.
- CHA records an `OatQuickMethodHeader*` as the identity of each dependent JIT
  version, walks native frames to set a version-specific deopt flag, and removes
  dependencies before freeing those headers (`cha.h:89-112`,
  `cha.cc:178-258,620-692`). This is **JIT + deoptimization** and **disabled**.
  Closed-world offline CHA can instead attach assumptions to stable method/body
  IDs or decline the optimization.
- the debugger interface publishes mini-ELF entries keyed by physical JIT code
  address and later parses symbol address ranges to match cache contents
  (`jit/debugger_interface.cc:587-687`, `jit_code_cache.cc:525-570`). This is
  **JIT + native debug** and **disabled**; Wasm-native source maps or engine debug
  APIs are a separate integration.

#### Instrumentation mixes portable events with native code-version tests

ART's listener semantics are not inherently tied to executable addresses. A
switch-interpreted or newly generated Wasm method can call method-entry, exit,
DEX-PC, field, allocation, and unwind listeners using normal typed calls. The
current mechanism for deciding *how* to deliver those events, however, examines
quick-code identities and layouts:

- `CodeSupportsEntryExitHooks()` compares known bridge/stub entrypoints, tests
  whether the address lies in the JIT cache, performs header subtraction, and
  decodes a debuggable bit from code-relative metadata
  (`instrumentation.cc:183-249`).
- `UpdateEntryPoints()` erases both old and new callables to `uintptr_t`, updates
  the pointer-sized field with an integer CAS, validates the ARM Thumb bit, and
  classifies an old value by executable JIT range so it can become zombie code
  (`instrumentation.cc:251-305`).
- `InstrumentationInstallStack()` walks physical quick frames and writes a
  per-frame deoptimization flag found through the current method header
  (`instrumentation.cc:495-578`). `ShouldDeoptimizeCaller()` reads the caller's
  ArtMethod and saved PC from native ABI offsets, resolves the header, inspects
  that frame flag, and asks whether the precise native PC is asynchronously
  deoptimizable (`instrumentation.cc:1684-1803`).
- compiled and JNI method-entry/exit hooks are quick TLS entrypoints with ISA
  stubs and native result-register/frame conventions
  (`quick_trampoline_entrypoints.cc:2778-2835`,
  `quick_default_init_entrypoints.h:138-149`).

This is **instrumentation/JVMTI + AOT/OAT + JIT + stack/exception**. Listener
registration and event dispatch are **representation-only**. The quick-code
classifier, native hook ABI, on-stack frame inspection, and current
deoptimization transfer are **redesign**. The replacement execution descriptor
should state whether a body has hooks, and the explicit Wasm managed frame must
carry its deoptimization/event state. The switch interpreter already owns a
`ShadowFrame` and can deliver DEX-PC events without native PCs.

There are stale-looking comments/declarations in this baseline about an
"instrumentation stack" and replacing return PCs (`instrumentation.cc:90-93`,
`instrumentation.h:638-641`), but the production `InstrumentationInstallStack()`
shown above does not rewrite return PCs, and there is no production definition
or use of `InstrumentationStackFrame` in this checkout. The audit therefore
does not attribute the older return-PC interception design to this source
baseline. Physical saved-PC use still exists in caller deoptimization and the
general quick stack walker.

Obsolete/redefined method handling uses a well-known obsolete-method stub as an
entrypoint identity, forces execution through the interpreter, and deoptimizes
already-active compiled frames. The identity part can become an execution-kind
enum; the compiled-frame conversion is covered by the managed-frame redesign.
For the initial Wasm profile, retaining redefinition/JVMTI semantics is feasible
only on switch frames unless and until Wasm AOT bodies emit complete
deoptimization state.

#### JVMTI, tracing, and ordinary callbacks split along the same boundary

JVMTI event tables and the JNI function tables are large structs of typed C
function pointers. ART copies the agent-supplied prefix of `jvmtiEventCallbacks`
as bytes and rounds the size down using `sizeof(void*)`
(`openjdkjvmti/OpenjdkJvmTi.cc:988-1019`); `JNINativeInterface` and
`JNIInvokeInterface` similarly contain hundreds of typed callable cells
(`jni_internal.cc:3160-3406`, `java_vm_ext.cc:591-625`). These callbacks do not
require code-byte arithmetic and are **representation-only**, but a Wasm ABI
must use the toolchain's actual function-pointer size/layout and exact indirect
call types. Code must not assume an object pointer, function reference, and
Wasm64 linear address have the same representation. Copying or overriding a
table supplied by another module additionally requires all parties to share a
table and canonical type/thunk policy.

That table replacement is a live cross-module operation, not just a layout
possibility. JVMTI `GetJNIFunctionTable` allocates and byte-copies the complete
current `JNINativeInterface`, while `SetJNIFunctionTable` installs an
agent-supplied table (`openjdkjvmti/ti_jni.cc:45-86`). `JNIEnvExt` keeps the
override globally, resets every thread's `JNIEnv::functions` pointer under the
JNI table lock, and gives the override precedence over both normal and CheckJNI
tables (`runtime/jni/jni_env_ext.cc:70-89,115-123,289-319`). This is
**instrumentation/JVMTI + JNI/native** and **representation-only** only if the
agent and runtime use the same Wasm C ABI, shared function table, canonical
indirect-call types, and table-object lifetime rules. The initial closed profile
disables native agents; a future Wasm-native agent cannot submit a native DSO
table, module-local indices, or linear-memory integers as callable cells.

There is an important JNI exception to that typed-table description. During VM
shutdown, `gJniSleepForeverStub` casts one `SleepForever` implementation to
every distinct `JNINativeInterface` signature (`jni_internal.cc:3409-3647`). A
native ABI tolerates the mismatched arguments and return type because the target
never returns. Wasm `call_indirect` still checks the target's function type
before entering it, so this can trap instead of sleeping. This is **JNI/native
+ runtime lifecycle** and the sentinel table is **redesign**: generate one
non-returning wrapper per canonical JNI signature, or redirect all JNI calls
through a separately typed shutdown check.

JVMTI extensions contain two similar type-erasure cases. ART publishes concrete
extension implementations by casting each to the variadic
`jvmtiExtensionFunction` type (`openjdkjvmti/ti_extension.cc:71-105,152-220,240-519`).
The extended heap iterator goes further: it deliberately reinterprets the
standard `heap_iteration_callback` cell as a different six-argument callback,
under a suppressed `-Wcast-function-type-mismatch` diagnostic
(`openjdkjvmti/ti_heap.cc:1585-1616`). These are **instrumentation/JVMTI +
GC/heap**. Native agents are already disabled by the closed profile; a future
Wasm-native JVMTI surface needs per-extension, exact-signature adapter slots.
Copying the same table index through both C types is not
**representation-only** and may fail Wasm's runtime type check.

ART-internal `InstrumentationListener` and `RuntimeCallbacks` objects use normal
C++ virtual dispatch (`instrumentation.h:67-156`,
`runtime_callbacks.h:49-115,286-307`). Likewise, STL `std::function`, pthread
start routines, GC bitmap visitors, root visitors, class visitors, and similar
typed callbacks are generally **representation-only**: the Wasm C++ toolchain
can lower their vtables/function pointers to table calls. They become a porting
issue only when ART erases them to object pointers/integers, serializes them,
obtains them from a DSO, relies on one native ABI for different signatures, or
does code-address arithmetic. This document calls out those escalations rather
than listing every ordinary virtual call.

The JNI invocation option path is one such escalation. `sensitiveThread`,
`vfprintf`, `exit`, and `abort` hooks arrive in a generic `const void*` option
payload and are cast back to four unrelated function-pointer types
(`parsed_options.cc:545-627`). This is **JNI/native + host embedding** and is
**representation-only** only after the embedding API carries typed table/import
references. A Wasm64 linear-memory `extraInfo` value cannot directly encode
these hooks.

Tracing illustrates the semantic/layout distinction. Method-event tracing can
consume explicit switch/AOT events and method IDs. Its sampling mode suspends
threads and uses `StackVisitor` to reconstruct native/inlined frames
(`trace.cc:316-405`), so sampling of current quick frames is **stack + profiling
redesign**. `pthread_create()` receiving `Trace::RunSamplingThread` is merely a
typed callback and **representation-only**. Native perf maps, mini-ELF, physical
code ranges, and native CFI are **disabled**; a Wasm engine-specific profiler is
not interchangeable with them.

#### The switch interpreter is viable after removing its native wrapper ABI

The portable switch implementation executes through `ShadowFrame` state and
does not need an interior machine PC for ordinary interpretation. The current
outer wrapper nevertheless passes `ExecuteSwitchImplCpp` as `const void*` to
ISA assembly, which makes a native indirect call and publishes the DEX PC
through native CFI (`interpreter_switch_impl.h:46-81`; representative x86-64
wrapper in `arch/x86_64/native_entrypoints_x86_64.S:32-69`). This is **switch +
stack**: call the C++ implementation directly in Wasm and retain the
`ShadowFrame`; the wrapper contract is **redesign/disabled**.

The switch interpreter's local JNI fallback recovers the native implementation
from `ArtMethod::data_`, casts it to shorty-specific C function types, and calls
it (`interpreter/interpreter.cc:43-229`). This is **switch + JNI/native** and can
be **representation-only** only for functions present in a typed Wasm registry.
Each signature bucket needs a canonical thunk and shared table; arbitrary
integer or DSO addresses cannot enter this path.

#### JNI registration is representable; arbitrary native discovery is not

`RegisterNatives` accepts the raw `JNINativeMethod::fnPtr`, may ask NativeBridge
to manufacture a replacement trampoline, and publishes the result through
`ClassLinker::RegisterNative()` into `ArtMethod::data_`
(`jni_internal.cc:2638-2795,3014-3040`; `class_linker.cc:470-525`). Lazy JNI
resolution searches loaded libraries for the short or long mangled name with
`dlsym()` (or asks NativeBridge for a trampoline) and returns that erased address
to a quick assembly stub (`jni/java_vm_ext.cc:156-189,276-426`;
`entrypoints/jni/jni_entrypoints.cc:50-132`). Resolution and interface quick
trampolines use the same general convention: return `{code address,
ArtMethod*}` as two integer words and let assembly branch to the first word
(`quick_trampoline_entrypoints.cc:2280-2490`).

Before storing a registered target, `ClassLinker::RegisterNative()` sends the
erased address through `RuntimeCallbacks` and accepts a replacement `void*`
(`class_linker.cc:470-500`). The JVMTI `NativeMethodBind` implementation exposes
that address and a `void**` replacement to agents, applying enabled callbacks in
sequence (`openjdkjvmti/ti_method.cc:86-106`;
`openjdkjvmti/events-inl.h:510-540`). This is **JNI/native +
instrumentation/JVMTI** and is **representation-only** only if the event carries
a registry-issued callable handle whose signature is derived from the method.
An agent-provided linear-memory integer or module-local table index cannot be
accepted as a replacement target.

This is **JNI/native + RTLD/DSO + switch/quick bridge**. A statically known JNI
method or host import can be **representation-only** if registration carries a
typed registry handle rather than a `void*`, and if the generated adapter obeys
the exact JNI/critical-native signature. Dynamic `RegisterNatives` can remain an
API only for values already issued by that registry. Treating an arbitrary
linear-memory integer, `dlsym()` result, or module-local index as globally
callable is invalid. Generic JNI/native quick assembly stubs and critical-native
direct calls are **redesign**; for an initial profile, route supported JNI
through generated Wasm thunks and the switch/AOT managed-frame convention.

#### ELF/DSO loading conflates data symbols, callable symbols, and return PCs

Native ART relies on the OS dynamic linker in several distinct ways:

- executable OAT files are loaded by `dlopen()` or ART's own ELF loader;
  `dlsym()` locates `oatdata`, `.bss`, VDEX, unwind, CFG, and other mostly-data
  symbols, while mapped ranges may receive `PROT_EXEC`
  (`oat_file.cc:1285-1750`, `oat/elf_file.cc:644-730`);
- JNI libraries are opened in class-loader namespaces, `JNI_OnLoad` is resolved
  and cast to a function, and per-method symbols are resolved as described
  above (`jni/java_vm_ext.cc:1030-1283`);
- plugins cast `dlsym()` results to `ArtPlugin_Initialize`/`Deinitialize`
  callbacks (`plugin.cc:30-79`), and JVMTI agents do the same for
  `Agent_OnLoad`, `Agent_OnAttach`, and `Agent_OnUnload`
  (`ti/agent.cc:49-162,209-221`);
- NativeBridge can return generated callable trampolines for a name or an
  already-supplied function pointer and can install its own signal-handler
  callbacks (`libnativebridge/native_bridge.cc:472-510,527-535`;
  `native_bridge_art_interface.cc:82-140`).
- runtime-adjacent ART libraries repeat the same dynamic binding pattern:
  Palette binds a system implementation and casts one no-argument fallback to
  every Palette signature (`libartpalette/apex/palette.cc:33-105`), sigchain
  resolves libc signal functions (`sigchainlib/sigchain.cc:139-176`), the JDWP
  connection layer probes debug-service functions
  (`adbconnection/adbconnection.cc:108-170`), the external dex-file API binds a
  complete support surface (`libdexfile/external/dex_file_supp.cc:52-79`), and
  OpenJDK exposes a generic `JVM_FindLibraryEntry()` returning `void*`
  (`openjdkjvm/OpenjdkJvm.cc:204-206`). Host/compiler-only simulator and
  disassembler factories also use `dlopen()`/`dlsym()`
  (`simulator/code_simulator_container.cc:24-48`,
  `compiler/optimizing/graph_visualizer.cc:124-145`).

One `void*` namespace is acceptable to native `dlsym()` but cannot distinguish a
Wasm linear-memory data address from a table slot. OAT data-symbol lookup would
be **unaffected data pointer** work in isolation, yet executable OAT loading is
already **disabled/redesign**. Arbitrary DSO loading, JNI symbol discovery,
NativeBridge, ART plugins, and native JVMTI agent loading are **RTLD/DSO +
JNI/native/instrumentation** and **disabled** for a closed offline-Wasm profile.
If dynamic Wasm modules are added later, the loader must explicitly relocate
data and register typed functions into a shared table; it cannot expose a
generic `dlsym` integer.

The auxiliary loaders have the same rule but different feature ownership.
Palette is **RTLD/DSO + platform runtime**, sigchain is **RTLD/DSO + fault**,
adbconnection is **RTLD/DSO + debugger**, and the dex-file, simulator, and
disassembler loaders are **RTLD/DSO + native API/host tooling**. Link required
pieces statically or expose exact typed host imports; otherwise disable those
integrations. Palette's cross-signature fallback needs typed wrappers even if
its real methods are statically linked. The Windows compatibility path has the
same namespace issue when it obtains `RtlGetVersion` through `GetProcAddress`
and casts the result to a typed function (`multiplatform/windows/cet_compat.cc:12-31`).
That particular call is **representation-only** as a declared typed host import;
a numeric linear-memory address is not a substitute.

ART also uses a native return address for policy rather than calling it. Four
JNI member-lookup entrypoints capture `__builtin_return_address(0)` and hidden-API
enforcement passes it to `dladdr()` to identify the caller DSO
(`jni_internal.cc:1014-1030,1556-1572`; `runtime/hidden_api.cc:110-115,241-258`).
CheckJNI
does the same (`check_jni.cc:2281-2299`). This is **JNI/native + RTLD/DSO +
security policy** and **redesign**: a Wasm JNI boundary must pass an explicit,
unforgeable caller-module/capability identity. A function index or synthetic PC
does not prove DSO provenance.

#### Signal-based implicit checks require instruction PCs and PC rewriting

`FaultManager` registers OAT, JIT, nterp, and other executable intervals and,
inside SIGSEGV handling, classifies the fault PC by subtractive range tests
(`runtime/fault_handler.cc:452-602`; OAT registration in
`class_linker.cc:4791-4814`). The architecture handlers then rely on instruction
bytes and a writable native signal context. For example, the x86 null handler
locates the method header, decodes the faulting instruction length, validates
the post-instruction return PC against a stack map, and redirects execution to
`art_quick_throw_null_pointer_exception_from_signal`
(`arch/x86/fault_handler_x86.cc:94-270,305-365`). ARM/ARM64 handlers match fixed
instruction encodings and replace the saved PC/LR with quick exception,
implicit-suspend, or stack-overflow stubs (for example
`arch/arm64/fault_handler_arm64.cc:47-182`). Even the crash-only Java stack
handler treats the signal SP as a quick frame (`runtime/fault_handler.cc:649-688`).

This is **fault + AOT/OAT + JIT + nterp + stack/exception** and is **redesign**;
the native signal handlers and registered executable ranges are **disabled** for
Wasm. Wasm AOT must emit explicit null checks, suspend/safepoint polls, and stack
limit/accounting checks that call or branch to typed runtime helpers. Exceptions
must be propagated through the Wasm control/state-transfer design. A Wasm trap,
engine PC, or table index is not a POSIX `ucontext` and cannot be patched to a
runtime stub.

#### Baker read-barrier introspection performs arithmetic inside assembly code

The concurrent-copying read barrier is a second GC dependency distinct from
stack maps. Per-thread `ReadBarrierMarkReg00..29` cells are dynamically switched
between null and assembly helpers as marking starts or stops
(`quick_entrypoints_list.h:179-208`, `thread.cc:175-198`). That null/non-null
state and the semantic call to mark a reference can become an explicit boolean
plus typed/direct Wasm helper.

ARM's optimized Baker path, however, deliberately treats an entrypoint as the
base of a byte-addressed jump table. Initialization subtracts assembly symbols
to verify fixed offsets and alignment, then stores the introspection base in a
reserved register's TLS cell (`arch/arm/entrypoints_init_arm.cc:78-123`,
`arch/arm64/entrypoints_init_arm64.cc:100-150`). Generated thunks inspect the
caller's load instruction through LR, add fixed offsets to the base, splice a
register number into address bits for array cases, and branch to an interior
assembly label (`compiler/optimizing/code_generator_arm64.cc:7507-7628`;
`code_generator_arm_vixl.cc:10301-10443`).

This is **GC/heap + AOT/OAT/JIT code generation** and is **redesign**. A Wasm
function-table index has no instruction bytes, alignment, interior labels, or
meaningful byte offsets. The Wasm backend must emit the reference load and
barrier logic normally, then make a typed helper call when required. It must not
port the introspection-address trick. Other GC object/space/card-table pointer
arithmetic remains ordinary linear-memory arithmetic and is outside the
executable-pointer problem.

#### Runtime-stub and module-range classification should become explicit state

ART locates the native module containing `Runtime::Current`, records the module's
load interval, and implements `OatQuickMethodHeader::IsStub()` as a PC range
test (`oat_quick_method_header.cc:150-200`). `ArtMethod::GetOatQuickMethodHeader()`
uses this together with well-known stub equality, nterp containment, JIT range
lookup, OAT lookup, and header subtraction to decide how a saved PC should be
decoded (`art_method.cc:625-748`). `OatFileManager::ContainsPc()`,
`Heap::IsInBootImageOatFile()`, and instrumentation use analogous mapping tests
(`oat_file_manager.cc:936-945`, `heap.cc:4725-4731`,
`instrumentation.cc:1166-1187`).

These are **AOT/OAT + JIT + nterp + instrumentation + heap classification**.
They are **representation-only** only when answering a logical question such as
"is this the resolution stub?" or "is this body from the boot artifact?"; use
an execution-kind/body-origin enum. They are **redesign** when the result feeds
header subtraction, PC decoding, unwinding, or executable ownership. A numeric
table slot cannot safely answer either question by range: table allocation is
not a code layout, and slots from multiple modules need not be contiguous.

Native stack dumping and unwind registration are downstream consumers of the
same physical ranges. Linux `DumpNativeStack()` asks libunwindstack for physical
frames, prints map-relative PCs, and, when symbolization fails, obtains the
current method header and prints `frame.pc - header->GetCode()`
(`native_stack_dump.cc:318-425`). The GC-stress helper likewise unwinds native
frames, stores every absolute PC as `uintptr_t`, hashes the sequence, and uses a
previously unseen hash to trigger a collection (`backtrace_helper.cc:43-149`;
`backtrace_helper.h:55-76`; `gc/heap.cc:4677-4701`). This latter path is
**GC/heap stress + native unwind**, not production root lookup, but it still
breaks if a table index is mistaken for a PC. It should be disabled or hash the
explicit managed `(body ID, safepoint/frame ID)` chain.

The Windows paths make the native contract especially explicit. AOT loading
validates serialized code intervals, creates `RUNTIME_FUNCTION` records from
code-relative offsets, and registers them with `RtlAddFunctionTable`
(`multiplatform/windows/aot_unwind_windows.cc:200-240,243-392`;
`oat/oat_file.cc:1882-1955`). JIT registration computes offsets by subtracting
code and unwind pointers from an allocation base, registers each physical range,
and keys removal by the raw code pointer
(`multiplatform/windows/jit_unwind_windows.cc:31-135`). The fatal diagnostic
unwinder reads `CONTEXT.Rip`, looks up a native runtime-function entry, and uses
`RtlVirtualUnwind` to replace the context PC/SP
(`multiplatform/windows/runtime_windows.cc:104-220`). The Windows AOT CFG table
also validates serialized, aligned physical call-target offsets against the OAT
code interval (`multiplatform/windows/aot_cfg_windows.cc:82-186`); in this
baseline it records policy/metadata but does not activate CFG targets.

These facilities are **AOT/OAT + JIT + stack/native debug + platform unwind and
hardening** and are **disabled** as native-code mechanisms for Wasm. Managed Java
stack traces should walk the explicit Wasm frame chain; engine-level Wasm
backtraces and source maps are optional host integrations. A Wasm table slot is
neither an RVA accepted by an OS unwinder nor an aligned address in an RX image.
The public
`VMDebug.getExecutableMethodFileOffsets` native also subtracts an ELF mapping
base from an OAT method code pointer and reports the file/code offsets
(`native/dalvik_system_VMDebug.cc:319-381`). This is **AOT/OAT + native debug**
and must be disabled or redefined to return Wasm-artifact body/source-map
identity rather than a fabricated byte offset.

### Subsystem disposition matrix

The table states the disposition for the proposed **switch + offline Wasm AOT,
no runtime JIT** profile. "Slot" always means a linker-assigned shared-table
slot with an exact Wasm call type, never a module-local function index copied
verbatim into a data field.

| Subsystem | Executable-pointer dependency in current ART | Wasm effect | Profile disposition |
|---|---|---|---|
| `ArtMethod` dispatch | Quick/JNI/stub address in overloaded pointer fields | **Representation-only** for calling; **redesign** for field layout and code-address consumers | Store execution kind plus typed registry/body ID; keep real data pointers distinct |
| Quick/TLS helpers | 176 erased callable cells; native load-and-branch ABI | **Representation-only** semantically; current blob/ABI is **redesign** | Generate direct/import/table calls with typed cells |
| AOT/OAT | Base+offset code address, header/code adjacency, patched call displacements/thunks, executable ELF, image code-pointer relocation | **Redesign** | New Wasm artifact with direct calls and typed table relocations; do not load native OAT code |
| JIT/code cache | Writable/RX mappings, emitted bytes, raw-PC maps, code GC, OSR | **Disable** | No runtime JIT, OSR, JIT JNI stubs, or JIT code GC |
| nterp/mterp | Assembly interval, fabricated header, native frames/landing pad | **Disable** | Use switch interpreter |
| Switch interpreter | `ShadowFrame` is portable; ISA wrapper and local raw JNI call are not | **Representation-only** core plus wrapper **redesign** | Direct C++/Wasm call and typed JNI registry |
| JNI tables | Typed C function-pointer tables; JVMTI can copy/replace the whole table; shutdown table casts one target to every signature | Mostly **representation-only**; shutdown sentinel is **redesign** | Shared-ABI table refs, validated ownership/lifetime, and exact-signature shutdown wrappers |
| Native method registration | Erased `fnPtr` stored in `ArtMethod::data_`; JVMTI can replace it through `void**` | **Representation-only** only for registry-issued typed slots | Closed generated/host registry and signature thunks; validate JVMTI replacements |
| JNI lazy lookup / DSOs | `dlopen`/`dlsym`, `JNI_OnLoad`, raw symbol address | **Disable** in closed profile | Static imports/registry; future dynamic loader must relocate data and table slots separately |
| NativeBridge | Runtime-generated ABI trampolines and signal callbacks | **Disable** | No native-ISA bridge in initial Wasm profile |
| Plugins / JVMTI agents | DSO handles and `dlsym` callback casts | **Disable** dynamically | Statically linked/Wasm-native instrumentation may use typed callbacks |
| Managed stack walk | Saved native PCs, quick-frame offsets, header and stack-map lookup | **Redesign** | Explicit linear-memory managed frames and safepoint IDs |
| Exceptions/deoptimization | DEX-PC↔native-PC conversion and ISA context long jump | **Redesign** | Structured state transfer/dispatcher; explicit deopt metadata |
| GC stack roots | Native PC selects register/stack root mask | **Redesign** | `(body ID, safepoint ID)` root map and linear-memory root slots |
| JIT embedded roots | Root table found by subtraction from JIT code metadata | **Disable/redesign** | No JIT roots; offline artifact uses explicit root-table keys |
| Read barriers | Dynamic helper pointers; ARM interior-stub arithmetic/introspection | Helper call **representation-only**; optimized trick **redesign** | Explicit marking state and normal typed barrier helper |
| Allocation helpers/instrumentation | Dynamically replaced quick helper cells | **Representation-only** | Typed helper selection, not erased addresses |
| Heap/OAT range tests | PC determines boot-code origin or native special case | **Redesign** as a range test | Body-origin metadata; ordinary heap pointers remain unaffected |
| Instrumentation/tracing | Stub equality, JIT ranges, native hook frames; portable listeners | Mixed **representation-only/redesign** | Emit explicit AOT/switch events; no native sampling/unwind |
| JVMTI callback/extensions | Typed tables plus variadic/cross-signature extension casts | Tables are **representation-only**; extension erasure needs adapters | Shared typed table and exact-signature wrappers; switch-only debugging initially |
| Fault handling | Executable intervals, instruction decode, `ucontext` PC rewrite | **Disable/redesign** | Explicit null/suspend/stack checks |
| Native debug/profilers | Physical PCs and code offsets, native unwind/CFG tables, GC-stress PC hashes, ELF symbols, CFI/perf/JIT descriptors | **Disable/redesign** | Managed frame IDs plus Wasm source maps/engine tooling and artifact IDs as separate features |
| Runtime option hooks | Invocation callbacks transported as `const void*` | **Representation-only** only after API typing | Typed imports/table references, never linear-memory `extraInfo` |
| Auxiliary dynamic binders | Palette, sigchain, adbconnection, dex support, simulator/disassembler symbols | **Disable or redesign** | Static links or exact typed host imports; typed fallback wrappers |
| C++ callbacks/vtables | Ordinary compiler-managed typed indirect calls | **Representation-only** | Let the Wasm C++ ABI lower them; audit cross-module table ownership |
| OAT `.bss`, DexCache, heap metadata | Linear-memory data pointers, not callables | **Unaffected data pointer** | Preserve as data; remove only code-derived lookup paths |

### Required invariants for a Wasm port

The audit rules out a global mechanical substitution of native addresses with
Wasm function indices. A safe design needs all of the following invariants:

1. **Separate namespaces in the type and data model.** A linear-memory address,
   shared-table slot, module-local function index, body ID, safepoint ID, and
   engine PC must be different types. Do not serialize or compare one as another.
2. **Replace `ArtMethod`'s executable meaning explicitly.** Use an execution
   descriptor such as `{kind, body_or_registry_id, type_id}` in a side table or
   a Wasm-specific layout. `data_` must retain its non-callable alternatives.
   Resolution, proxy, obsolete, JNI, switch, and AOT are logical kinds rather
   than distinguished stub addresses.
3. **Link callables, do not guess indices.** Direct calls are preferable when
   the target is statically known. Indirect calls require a shared table,
   relocation from artifact-local symbol to table slot, exact Wasm type, a null
   representation, and adapters for every erased/native ABI boundary.
4. **Make metadata lookup one-way and explicit.** A body ID indexes frame size,
   DEX-PC/inlining information, exception tables, and a safepoint table. A
   safepoint ID indexes roots and live values. No metadata pointer may be
   recovered by subtracting from a callable or testing an alleged code range.
5. **Publish managed frames before runtime-visible operations.** A frame in
   linear memory must contain its caller link, method/body ID, current
   safepoint/DEX-PC state, roots, and deoptimization state before it can suspend,
   allocate, throw, call an unknown helper, or invoke host/native code. The
   compiler must update the safepoint ID in an order visible to the collector.
6. **Use explicit control transfers.** Exceptions, deoptimization, suspension,
   and stack overflow return through Wasm structured control/EH or a dispatcher.
   They never write a native/engine PC or synthesize a return address.
7. **Use explicit checks.** Null, suspend, and stack checks must be generated
   operations. Do not depend on POSIX signals, guard-page fault PCs, or decoding
   the faulting Wasm instruction.
8. **Close or redesign dynamic native boundaries.** The initial profile admits
   only generated JNI thunks and declared host imports/registry entries. Dynamic
   modules, if later supported, need separate data relocation and typed table
   registration plus an explicit caller-origin capability.
9. **Keep GC code and GC data separate.** Read/allocation barrier selection can
   use state flags and typed helpers. Stack roots, JIT roots, and Baker
   introspection must not be discovered from executable addresses. Ordinary
   object, card-table, space, and metadata pointers stay linear-memory pointers.

A synthetic code descriptor is optional and should be introduced only for a
consumer that truly needs stable body identity. It may be logged, hashed, or
used as a key after validation, but it is never callable and has no header,
size-based containment, interior PCs, ISA tag bit, or arithmetic relationship
to metadata. Calling it an "address" in APIs would invite the same bug class.

### Audit coverage and conclusion

The source pass searched production C++, headers, assembly, compiler backends,
dex2oat, runtime-support libraries, and relevant host tooling for entrypoint
accessors, function-to-`void*`/integer casts, cross-signature casts, PC and
return-PC consumers, executable mappings, code/header conversion, symbol
loading, range tests, unwind/debug registration, and dynamic callback tables.
It then followed representative producer-to-consumer chains rather than
treating search matches as independent facts. Architecture-specific
implementations are grouped where they implement the same quick/fault contract;
the unusually layout-dependent ARM read-barrier path is called out separately.
Test-only fake code mappings were not classified as runtime requirements.

The result is decisive: a Wasm function index can replace only the **callable
identity** portion of some typed callbacks and dispatch cells, and even then it
must be relocated into a shared table with the correct type. It cannot replace
ART's broader use of executable pointers as byte addresses, range members,
metadata anchors, return/interior PCs, DSO provenance, native unwind identities,
or GC safepoint selectors. The proposed port is therefore viable only with a
new execution descriptor, explicit managed-frame/safepoint metadata, typed
registry dispatch, and the stated disabling of JIT, nterp, native OAT/ELF code,
arbitrary DSO/native bridge paths, signal-based implicit checks, and native
debug/unwind facilities.
