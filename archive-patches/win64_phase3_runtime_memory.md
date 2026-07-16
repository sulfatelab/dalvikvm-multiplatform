# Win64 Phase 3 — Runtime free/total/maxMemory

**Symptom:** `Runtime.freeMemory()/totalMemory()/maxMemory()` returned `0` under wine64 while GC/alloc worked.

**Cause:** PE `libopenjdk.dll` (libcombined stand-in) did not export `Java_java_lang_Runtime_{free,total,max}Memory` / `nativeGc`, and `art.dll` did not export `JVM_FreeMemory` / `JVM_TotalMemory` / `JVM_MaxMemory` / `JVM_GC` (full `OpenjdkJvm.cc` is POSIX-heavy and not linked on Win64).

**Fix:**

1. `compat/windows/art/openjdkjvm_memory_windows.cc` — export `JVM_FreeMemory/TotalMemory/MaxMemory/GC` using ART heap APIs.
2. `tools/win64/jni_stubs/win_runtime_natives.c` — PE JNI for Runtime natives via `GetProcAddress(art.dll, "JVM_*")`.
3. Link memory object into `art.dll`; rebuild libcombined and copy to `libopenjdk.dll` et al.

**Verify:** `bash tools/verify/win64_phase3/run_rtmem.sh` → `max=536870912` with `-Xmx512m`.
