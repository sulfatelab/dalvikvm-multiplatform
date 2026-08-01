# Windows x64 Phase 3 — Runtime free/total/maxMemory

Status: applied in nested ART and the project-owned Runtime JNI bridge. This
module boundary is reusable for every Windows architecture until the complete
upstream OpenJDK JVM layer is portable.

**Symptom:** `Runtime.freeMemory()/totalMemory()/maxMemory()` returned `0` under wine64 while GC/alloc worked.

**Cause:** PE `libopenjdk.dll` (libcombined stand-in) did not export `Java_java_lang_Runtime_{free,total,max}Memory` / `nativeGc`, and `art.dll` did not export `JVM_FreeMemory` / `JVM_TotalMemory` / `JVM_MaxMemory` / `JVM_GC` (full `OpenjdkJvm.cc` is POSIX-heavy and not linked on Windows x64).

**Fix:**

1. `vendor/art/openjdkjvm/openjdkjvm_memory_windows.cc` — export
   `JVM_FreeMemory/TotalMemory/MaxMemory/GC` using ART heap APIs.
2. `tools/windows_x64/jni_stubs/win_runtime_natives.c` — PE JNI for Runtime natives via `GetProcAddress(art.dll, "JVM_*")`.
3. Link memory object into `art.dll`; rebuild libcombined and copy to `libopenjdk.dll` et al.

**Verify:** `python tools/build_art.py test --target-id windows-x86_64-msvc --stage w004 --parallel 16`; gate `art.w004.managed_rtmem` reports `mem.ok=true` with `-Xmx512m`.
