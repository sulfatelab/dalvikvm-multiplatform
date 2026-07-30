# ART wasm64 feasibility analysis

Status: feasibility assessment

Date: 2026-07-31

## Conclusion

A full ART port preserving the current runtime, JIT/AOT, OAT, JNI-loading,
threading, and DSO contracts is not presently feasible on portable wasm64.

A restricted ART-derived runtime is technically feasible, but it would be a
substantial fork:

- interpreter-only;
- imageless DEX boot;
- statically linked native libraries;
- explicit fault checks;
- custom linear-memory allocation; and
- initially single-threaded or tied to a specific browser/engine threading
  model.

The repository's existing classification of `wasi-wasm64` as
`impossible_under_current_art_contract` is accurate.

## Why the current tree cannot simply be cross-compiled

| Area | Finding |
|---|---|
| Toolchain | LLVM 21 recognizes `wasm64`, but the official WASI SDK currently says 64-bit linear-memory targets are unsupported. It has no plans for `wasm64-wasi`/Preview1 variants; a future `wasm64-wasip2` depends on unresolved component-model work. |
| Build frontend | [`native/CMakeLists.txt`](../native/CMakeLists.txt) rejects anything except Linux or Windows. The registered Wasm profiles deliberately fail before graph generation in [`target.py`](../tools/bp2cmake/bp2cmake/target.py). |
| ART architecture | [`instruction_set.h`](../vendor/art/libartbase/arch/instruction_set.h) knows only ARM, ARM64, RISC-V64, x86, and x86-64. Under wasm64, `kRuntimeISA` becomes `kNone`. The current tree contains 276 ISA switch cases across 23 runtime/compiler files. |
| Interpreter | The portable C++ switch interpreter exists, which is encouraging, but even it enters through an architecture-specific assembly/CFI wrapper in [`interpreter_switch_impl.h`](../vendor/art/runtime/interpreter/interpreter_switch_impl.h). There is no Wasm quick-invoke, JNI, context, frame, TLS, or long-jump implementation. |
| Compiler | [`code_generator.cc`](../vendor/art/compiler/optimizing/code_generator.cc) has no WebAssembly backend. JNI calling conventions, trampolines, register allocation, unwind metadata, and runtime entrypoints are similarly ISA-specific. |
| Executable code | ART assumes generated code is byte-addressable executable memory. `OatQuickMethodHeader` physically precedes its machine-code bytes and is recovered by pointer subtraction in [`oat_quick_method_header.h`](../vendor/art/runtime/oat/oat_quick_method_header.h). Wasm functions live in code sections/function tables, not linear memory. |
| JIT memory | ART requires executable mappings, dual RW/RX views, `mprotect`, `memfd`, and fixed mappings; see [`jit_memory_region.cc`](../vendor/art/runtime/jit/jit_memory_region.cc). WebAssembly linear memory has no executable pages or per-page protection. |
| Fault handling | ART relies on recoverable `SIGSEGV`/`SIGBUS` contexts, guard pages, and PC/SP rewriting. Browser Wasm has traps rather than resumable POSIX faults; Emscripten explicitly does not support POSIX signals. |
| OAT/AOT | Current OAT loading is ELF/`dlopen`-oriented. A WebAssembly module cannot be copied from an OAT mapping into linear memory and called like native instructions. Supporting AOT would require a new artifact, linker, metadata, and entrypoint model. |
| JNI/DSOs | Startup dynamically loads `libicu_jni`, `libjavacore`, and `libopenjdk` in [`runtime.cc`](../vendor/art/runtime/runtime.cc). WebAssembly dynamic linking has no stable ABI, and official WASI support remains incomplete. |
| Heap references | Managed references remain raw 32-bit compressed pointers even in a 64-bit ART build; see [`object_reference.h`](../vendor/art/runtime/mirror/object_reference.h). Therefore the managed heap still has to reside below 4 GiB. wasm64 does not automatically give ART a larger Java heap. |

The repository already records essentially the same architectural boundary in
[`unified_art_build.md`](../unified_art_build.md).

## What is realistically feasible

The most credible first target is not `wasi-wasm64`, but something explicitly
different, such as `browser-wasm64-emscripten`.

That prototype would need to:

1. Use `-Xint` and the C++ switch interpreter; disable nterp, JIT, OSR,
   dex2oat, executable OAT, and JVMTI compiled-code features.
2. Replace the switch-interpreter assembly wrapper and quick invocation
   machinery with Wasm-specific C++ entrypoints.
3. Boot imageless from DEX/JAR. This repository's existing Linux/Windows
   imageless path provides useful precedent.
4. Link ART, libcore natives, ICU, and OpenJDK natives into one module and
   replace `dlopen`/`dlsym` with a generated native-method registry.
5. Implement `MemMap` as a linear-memory suballocator. Managed objects must
   stay in a reserved low-4-GiB arena.
6. Replace implicit null and stack-overflow faults with explicit checks.
   Protection-dependent GC/debug mechanisms must be disabled or redesigned.
7. Start with the simplest stop-the-world collector.
8. Run ART in a Web Worker. Add pthread support only after validating the exact
   engine's combined memory64, shared-memory, atomics, TLS, and function-table
   support.

For a standards-oriented experiment today, `wasm32-wasip1-threads` is more
mature than wasm64, although WASI threading is still marked experimental and
lightly tested. It would prove many ART platform abstractions but not the
requested pointer width.

## Expected scale

The following estimates are rough orders of magnitude:

- `libartbase` plus DEX parsing/verifying in wasm64: several engineer-weeks;
- imageless interpreter-only `HelloWorld` with prelinked core natives: roughly
  6-12 engineer-months;
- a useful Java runtime with threads, filesystem, networking, reflection, ICU,
  and broader JNI: likely 1-3 engineer-years; and
- current ART parity with JIT/AOT/OAT/dynamic JNI: a research-scale redesign,
  partly blocked on platform/engine contracts.

The decisive go/no-go milestone should be an imageless `-Xint` Hello running
from a single statically linked Wasm module. A Wasm JIT backend should not be
part of the initial port.

## Upstream references

- [WASI SDK notable limitations](https://github.com/WebAssembly/wasi-sdk#notable-limitations)
- [Memory64 proposal and implementation status](https://github.com/WebAssembly/memory64/blob/main/proposals/memory64/Overview.md)
- [Emscripten Memory64 setting](https://emscripten.org/docs/tools_reference/settings_reference.html#memory64)
- [Emscripten pthread and signal limitations](https://emscripten.org/docs/porting/pthreads.html)
- [WebAssembly dynamic-linking ABI status](https://github.com/WebAssembly/tool-conventions/blob/main/DynamicLinking.md)
