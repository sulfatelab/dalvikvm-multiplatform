#include <jni.h>
#include <windows.h>

#include <cstdio>
#include <cstring>
#include <cwchar>

namespace {

using CreateJavaVmFn = jint(JNICALL*)(JavaVM**, JNIEnv**, void*);

volatile LONG g_foreign_veh_calls = 0;
volatile LONG g_predecessor_uef_calls = 0;
volatile LONG g_late_uef_calls = 0;
volatile LONG g_frame_seh_calls = 0;

void WriteMarker(const char* text) {
  DWORD length = 0u;
  while (text[length] != '\0') {
    ++length;
  }
  DWORD written = 0u;
  WriteFile(GetStdHandle(STD_ERROR_HANDLE), text, length, &written, nullptr);
}

bool IsAccessViolation(EXCEPTION_POINTERS* info) {
  return info != nullptr && info->ExceptionRecord != nullptr &&
      info->ExceptionRecord->ExceptionCode == EXCEPTION_ACCESS_VIOLATION;
}

LONG WINAPI ForeignVeh(EXCEPTION_POINTERS* info) {
  if (IsAccessViolation(info)) {
    InterlockedIncrement(&g_foreign_veh_calls);
    WriteMarker("WIN32_ART_EMBED foreign_veh search=1\n");
  }
  return EXCEPTION_CONTINUE_SEARCH;
}

LONG WINAPI PredecessorUef(EXCEPTION_POINTERS* info) {
  if (IsAccessViolation(info)) {
    InterlockedIncrement(&g_predecessor_uef_calls);
    WriteMarker("WIN32_ART_EMBED predecessor_uef continue=1\n");
    return EXCEPTION_CONTINUE_EXECUTION;
  }
  return EXCEPTION_CONTINUE_SEARCH;
}

LONG WINAPI LateUef(EXCEPTION_POINTERS* info) {
  if (IsAccessViolation(info)) {
    InterlockedIncrement(&g_late_uef_calls);
    WriteMarker("WIN32_ART_EMBED late_uef unexpected_call=1\n");
  }
  return EXCEPTION_CONTINUE_SEARCH;
}

LONG WINAPI QueryUef(EXCEPTION_POINTERS*) {
  return EXCEPTION_CONTINUE_SEARCH;
}

int FrameFilter(DWORD code) {
  if (code == EXCEPTION_ACCESS_VIOLATION) {
    InterlockedIncrement(&g_frame_seh_calls);
    return EXCEPTION_EXECUTE_HANDLER;
  }
  return EXCEPTION_CONTINUE_SEARCH;
}

void RaiseProbeAccessViolation() {
  ULONG_PTR arguments[2] = {1u, 0u};
  RaiseException(EXCEPTION_ACCESS_VIOLATION, 0u, 2u, arguments);
}

void RaiseForFrameSeh(const char* phase) {
  std::printf("WIN32_ART_EMBED frame_seh armed phase=%s\n", phase);
  std::fflush(stdout);
  __try {
    RaiseProbeAccessViolation();
  } __except (FrameFilter(GetExceptionCode())) {
    std::printf("WIN32_ART_EMBED frame_seh caught phase=%s\n", phase);
    std::fflush(stdout);
  }
}

bool PointerIsInModule(void* pointer, const wchar_t* expected_name) {
  MEMORY_BASIC_INFORMATION memory = {};
  wchar_t path[MAX_PATH] = {};
  if (pointer == nullptr || VirtualQuery(pointer, &memory, sizeof(memory)) == 0u ||
      GetModuleFileNameW(static_cast<HMODULE>(memory.AllocationBase), path, MAX_PATH) == 0u) {
    return false;
  }
  const wchar_t* base = std::wcsrchr(path, L'\\');
  base = base == nullptr ? std::wcsrchr(path, L'/') : base;
  base = base == nullptr ? path : base + 1;
  return _wcsicmp(base, expected_name) == 0 ||
      (std::wcscmp(expected_name, L"art.dll") == 0 && _wcsicmp(base, L"libart.dll") == 0);
}

}  // namespace

int main() {
  std::puts("WIN32_ART_EMBED start");
  PVOID foreign = AddVectoredExceptionHandler(0u, ForeignVeh);
  if (foreign == nullptr) {
    std::fprintf(stderr, "WIN32_ART_EMBED FAIL foreign VEH error=%lu\n", GetLastError());
    return 1;
  }
  LPTOP_LEVEL_EXCEPTION_FILTER original_uef =
      SetUnhandledExceptionFilter(PredecessorUef);

  HMODULE art = LoadLibraryW(L"art.dll");
  if (art == nullptr) {
    std::fprintf(stderr, "WIN32_ART_EMBED FAIL LoadLibrary art error=%lu\n", GetLastError());
    return 1;
  }
  auto create_java_vm = reinterpret_cast<CreateJavaVmFn>(
      GetProcAddress(art, "JNI_CreateJavaVM"));
  if (create_java_vm == nullptr) {
    std::fputs("WIN32_ART_EMBED FAIL JNI_CreateJavaVM export missing\n", stderr);
    return 1;
  }

  JavaVMOption options[] = {
      {const_cast<char*>("-Xbootclasspath:run\\boot.jar"), nullptr},
      {const_cast<char*>("-Xbootclasspath-locations:run\\boot.jar"), nullptr},
      {const_cast<char*>("-Ximage:/nonexistent-no-boot-image"), nullptr},
      {const_cast<char*>("-XjdwpProvider:none"), nullptr},
      {const_cast<char*>("-Xms64m"), nullptr},
      {const_cast<char*>("-Xmx512m"), nullptr},
      {const_cast<char*>("-Xusejit:false"), nullptr},
  };
  JavaVMInitArgs args = {};
  args.version = JNI_VERSION_1_6;
  args.nOptions = static_cast<jint>(sizeof(options) / sizeof(options[0]));
  args.options = options;
  args.ignoreUnrecognized = JNI_FALSE;
  JavaVM* vm = nullptr;
  JNIEnv* env = nullptr;
  const jint create_result = create_java_vm(&vm, &env, &args);
  std::printf("WIN32_ART_EMBED runtime_create result=%d vm=%p env=%p\n",
              create_result,
              static_cast<void*>(vm),
              static_cast<void*>(env));
  std::fflush(stdout);
  if (create_result != JNI_OK || vm == nullptr || env == nullptr) {
    return 1;
  }

  std::puts("WIN32_ART_EMBED predecessor_uef armed=1");
  std::fflush(stdout);
  RaiseProbeAccessViolation();
  std::printf("WIN32_ART_EMBED predecessor_uef resumed calls=%ld\n",
              g_predecessor_uef_calls);
  RaiseForFrameSeh("runtime-active");

  LPTOP_LEVEL_EXCEPTION_FILTER late_predecessor =
      SetUnhandledExceptionFilter(LateUef);
  const bool late_predecessor_is_art =
      PointerIsInModule(reinterpret_cast<void*>(late_predecessor), L"art.dll");
  std::printf("WIN32_ART_EMBED late_uef installed predecessor_is_art=%d\n",
              late_predecessor_is_art ? 1 : 0);

  const jint detach_result = vm->DetachCurrentThread();
  const jint destroy_result = vm->DestroyJavaVM();
  std::printf("WIN32_ART_EMBED runtime_destroy detach=%d destroy=%d\n",
              detach_result,
              destroy_result);

  LPTOP_LEVEL_EXCEPTION_FILTER after_destroy =
      SetUnhandledExceptionFilter(QueryUef);
  const bool late_preserved = after_destroy == LateUef;
  SetUnhandledExceptionFilter(after_destroy);
  std::printf("WIN32_ART_EMBED teardown late_uef_preserved=%d\n",
              late_preserved ? 1 : 0);

  FreeLibrary(art);
  RaiseForFrameSeh("runtime-unloaded");

  RemoveVectoredExceptionHandler(foreign);
  SetUnhandledExceptionFilter(original_uef);
  std::printf(
      "WIN32_ART_EMBED result foreign_veh_calls=%ld predecessor_uef_calls=%ld "
      "late_uef_calls=%ld frame_seh_calls=%ld\n",
      g_foreign_veh_calls,
      g_predecessor_uef_calls,
      g_late_uef_calls,
      g_frame_seh_calls);
  if (g_foreign_veh_calls != 3 || g_predecessor_uef_calls != 1 ||
      g_late_uef_calls != 0 || g_frame_seh_calls != 2 ||
      !late_predecessor_is_art || detach_result != JNI_OK ||
      destroy_result != JNI_OK || !late_preserved) {
    std::puts("WIN32_ART_EMBED FAIL");
    return 1;
  }
  std::puts("WIN32_ART_EMBED PASS");
  return 0;
}
