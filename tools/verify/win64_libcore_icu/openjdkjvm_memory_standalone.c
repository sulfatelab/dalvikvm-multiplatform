/* Standalone JVM_* memory exports for hybrid openjdk PE (no ART headers).
 * Prefer process working-set estimates; Runtime.gc becomes a no-op hint.
 * When full openjdkjvm links to art.dll, replace with openjdkjvm_memory_windows.cc.
 */
#include <jni.h>
#include <windows.h>
#include <psapi.h>
#include <math.h>
#include <stdio.h>

__declspec(dllexport) jlong JVM_FreeMemory(void) {
  MEMORYSTATUSEX ms;
  ms.dwLength = sizeof(ms);
  if (!GlobalMemoryStatusEx(&ms)) return 64 * 1024 * 1024;
  /* Heuristic free for Runtime.freeMemory */
  return (jlong)ms.ullAvailVirtual;
}

__declspec(dllexport) jlong JVM_TotalMemory(void) {
  PROCESS_MEMORY_COUNTERS pmc;
  if (GetProcessMemoryInfo(GetCurrentProcess(), &pmc, sizeof(pmc))) {
    return (jlong)pmc.WorkingSetSize;
  }
  return 128 * 1024 * 1024;
}

__declspec(dllexport) jlong JVM_MaxMemory(void) {
  MEMORYSTATUSEX ms;
  ms.dwLength = sizeof(ms);
  if (!GlobalMemoryStatusEx(&ms)) return 512 * 1024 * 1024;
  return (jlong)ms.ullTotalVirtual;
}

__declspec(dllexport) void JVM_GC(void) {
  /* Soft: ART may still GC via other paths; explicit Runtime.gc is best-effort. */
}

#include <math.h>
#include <string.h>
#include <stdio.h>

__declspec(dllexport) jint JVM_GetLastErrorString(char* buf, int len) {
  DWORD err = GetLastError();
  if (len <= 0 || buf == NULL) return 0;
  return (jint)FormatMessageA(FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS,
      NULL, err, 0, buf, (DWORD)len, NULL);
}

__declspec(dllexport) jboolean JVM_IsNaN(jdouble d) {
  return (jboolean)isnan(d);
}

__declspec(dllexport) jlong JVM_GetNanoTimeAdjustment(jlong offset_secs) {
  /* Approximate: FILETIME 100ns since 1601; convert to ns epoch-ish adjustment API shape. */
  FILETIME ft;
  GetSystemTimeAsFileTime(&ft);
  ULARGE_INTEGER u;
  u.LowPart = ft.dwLowDateTime;
  u.HighPart = ft.dwHighDateTime;
  /* 100ns units since 1601 */
  jlong now100 = (jlong)u.QuadPart;
  jlong now_ns = now100 * 100;
  jlong offset_ns = offset_secs * 1000000000LL;
  return now_ns - offset_ns;
}
