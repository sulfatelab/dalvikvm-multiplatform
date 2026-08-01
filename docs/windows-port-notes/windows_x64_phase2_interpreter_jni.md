# Windows x64 Phase 2 — retired InterpreterJni workaround

Status: retired; do not reapply

The Phase 2 bring-up temporarily routed runtime-started Windows native methods
through a C++ `InterpreterJni` fallback. It directly resolved JNI entrypoints and
manually dispatched a growing table of shorties because the PE quick-JNI and
generic-JNI paths were not yet usable.

That workaround was an x86_64 bring-up bridge, not a valid Windows ABI design:

- signature-specific C++ function casts duplicate the platform calling
  convention and are easy to get wrong for floating-point, aggregate, and wide
  arguments;
- a manual shorty table cannot cover arbitrary application JNI methods;
- it made Windows `-Xint` behavior diverge from Linux even though `-Xint`
  interprets Java methods, not JNI ABI transitions; and
- it would be especially unsafe to copy to `aarch64` or `arm64ec`.

The real quick/JNI entrypoints, compiled JNI, CriticalNative calls, method
tracing, and JVMTI forced interpretation now work. Nested ART commit
`42a03f2ea0` restored `runtime/interpreter/interpreter.cc` byte-for-byte to the
Android 16 upstream policy and removed the native-method JIT exclusion.

The accepted Wine and native-Windows reachability audit is recorded in
`docs/history/windows_x64_w024_interpreter_jni_result.md`. The
original source excerpt remains recoverable from top-level Git history if an
old Phase 2 binary must be investigated, but it must not be used as source for a
future Windows port.
