#include <process.h>
#include <windows.h>

#include <cstdio>
#include <cstring>

namespace {

enum class ProbeMode {
  kSeh,
  kUnhandled,
  kChain,
  kThread,
};

volatile LONG g_veh_calls = 0;
volatile LONG g_first_uef_calls = 0;
volatile LONG g_second_uef_calls = 0;
volatile LONG g_seh_caught_code = 0;
LPTOP_LEVEL_EXCEPTION_FILTER g_second_predecessor = nullptr;

void WriteMarker(const char *text) {
  DWORD length = 0u;
  while (text[length] != '\0') {
    ++length;
  }
  DWORD written = 0u;
  HANDLE error = GetStdHandle(STD_ERROR_HANDLE);
  if (error != nullptr && error != INVALID_HANDLE_VALUE) {
    WriteFile(error, text, length, &written, nullptr);
  }
}

LONG WINAPI ObserveException(EXCEPTION_POINTERS *exception) {
  if (exception != nullptr && exception->ExceptionRecord != nullptr &&
      exception->ExceptionRecord->ExceptionCode == EXCEPTION_ACCESS_VIOLATION) {
    InterlockedIncrement(&g_veh_calls);
    WriteMarker("WIN32_UEF_PROBE VEH enter code=0xc0000005\n");
  }
  return EXCEPTION_CONTINUE_SEARCH;
}

LONG WINAPI FirstUef(EXCEPTION_POINTERS *exception) {
  InterlockedIncrement(&g_first_uef_calls);
  if (exception != nullptr && exception->ExceptionRecord != nullptr &&
      exception->ExceptionRecord->ExceptionCode == EXCEPTION_ACCESS_VIOLATION) {
    WriteMarker("WIN32_UEF_PROBE UEF first code=0xc0000005\n");
  } else {
    WriteMarker("WIN32_UEF_PROBE UEF first code=unexpected\n");
  }
  return EXCEPTION_EXECUTE_HANDLER;
}

LONG WINAPI SecondUef(EXCEPTION_POINTERS *exception) {
  InterlockedIncrement(&g_second_uef_calls);
  WriteMarker("WIN32_UEF_PROBE UEF second chaining=1\n");
  LPTOP_LEVEL_EXCEPTION_FILTER predecessor = g_second_predecessor;
  if (predecessor != nullptr && predecessor != SecondUef) {
    return predecessor(exception);
  }
  return EXCEPTION_EXECUTE_HANDLER;
}

__declspec(noinline) void RaiseAccessViolation() {
  ULONG_PTR arguments[2] = {1u, 0u};
  RaiseException(EXCEPTION_ACCESS_VIOLATION, EXCEPTION_NONCONTINUABLE, 2u,
                 arguments);
}

unsigned __stdcall FaultingWorker(void *) {
  WriteMarker("WIN32_UEF_PROBE worker armed=1\n");
  RaiseAccessViolation();
  WriteMarker("WIN32_UEF_PROBE worker unexpected_return=1\n");
  return 3u;
}

bool ParseMode(const char *value, ProbeMode *mode) {
  if (std::strcmp(value, "seh") == 0) {
    *mode = ProbeMode::kSeh;
  } else if (std::strcmp(value, "unhandled") == 0) {
    *mode = ProbeMode::kUnhandled;
  } else if (std::strcmp(value, "chain") == 0) {
    *mode = ProbeMode::kChain;
  } else if (std::strcmp(value, "thread") == 0) {
    *mode = ProbeMode::kThread;
  } else {
    return false;
  }
  return true;
}

const char *ModeName(ProbeMode mode) {
  switch (mode) {
  case ProbeMode::kSeh:
    return "seh";
  case ProbeMode::kUnhandled:
    return "unhandled";
  case ProbeMode::kChain:
    return "chain";
  case ProbeMode::kThread:
    return "thread";
  }
  return "unknown";
}

int CatchAccessViolation(DWORD code) {
  return code == EXCEPTION_ACCESS_VIOLATION ? EXCEPTION_EXECUTE_HANDLER
                                            : EXCEPTION_CONTINUE_SEARCH;
}

} // namespace

int main(int argc, char **argv) {
  if (argc != 2) {
    std::fprintf(stderr,
                 "usage: win32_uef_probe.exe <seh|unhandled|chain|thread>\n");
    return 2;
  }
  ProbeMode mode;
  if (!ParseMode(argv[1], &mode)) {
    std::fprintf(stderr, "unknown UEF mode: %s\n", argv[1]);
    return 2;
  }

  BOOL remote_debugger = FALSE;
  const BOOL remote_query_ok =
      CheckRemoteDebuggerPresent(GetCurrentProcess(), &remote_debugger);
  std::printf("WIN32_UEF_PROBE start mode=%s debugger=%d remote_query_ok=%d "
              "remote_debugger=%d\n",
              ModeName(mode), IsDebuggerPresent() ? 1 : 0,
              remote_query_ok ? 1 : 0, remote_debugger ? 1 : 0);
  std::fflush(stdout);

  PVOID veh = AddVectoredExceptionHandler(1u, ObserveException);
  if (veh == nullptr) {
    std::fprintf(stderr,
                 "WIN32_UEF_PROBE FAIL AddVectoredExceptionHandler error=%lu\n",
                 static_cast<unsigned long>(GetLastError()));
    return 1;
  }

  LPTOP_LEVEL_EXCEPTION_FILTER original = SetUnhandledExceptionFilter(FirstUef);
  if (mode == ProbeMode::kChain) {
    g_second_predecessor = SetUnhandledExceptionFilter(SecondUef);
  }

  if (mode == ProbeMode::kSeh) {
    __try {
      RaiseAccessViolation();
    } __except (CatchAccessViolation(GetExceptionCode())) {
      InterlockedExchange(&g_seh_caught_code, EXCEPTION_ACCESS_VIOLATION);
    }
    SetUnhandledExceptionFilter(original);
    if (RemoveVectoredExceptionHandler(veh) == 0u) {
      std::fprintf(
          stderr,
          "WIN32_UEF_PROBE FAIL RemoveVectoredExceptionHandler error=%lu\n",
          static_cast<unsigned long>(GetLastError()));
      return 1;
    }
    std::printf(
        "WIN32_UEF_PROBE seh caught=0x%08lx veh_calls=%ld first_uef_calls=%ld "
        "second_uef_calls=%ld\n",
        static_cast<unsigned long>(g_seh_caught_code), g_veh_calls,
        g_first_uef_calls, g_second_uef_calls);
    if (g_seh_caught_code != static_cast<LONG>(EXCEPTION_ACCESS_VIOLATION) ||
        g_veh_calls != 1 || g_first_uef_calls != 0 || g_second_uef_calls != 0) {
      std::puts("WIN32_UEF_PROBE FAIL seh");
      return 1;
    }
    std::puts("WIN32_UEF_PROBE PASS seh");
    return 0;
  }

  if (mode == ProbeMode::kThread) {
    unsigned int thread_id = 0u;
    uintptr_t raw_thread =
        _beginthreadex(nullptr, 1024u * 1024u, FaultingWorker, nullptr,
                       STACK_SIZE_PARAM_IS_A_RESERVATION, &thread_id);
    if (raw_thread == 0u) {
      std::fprintf(stderr, "WIN32_UEF_PROBE FAIL _beginthreadex error=%lu\n",
                   static_cast<unsigned long>(GetLastError()));
      return 1;
    }
    WaitForSingleObject(reinterpret_cast<HANDLE>(raw_thread), INFINITE);
    WriteMarker("WIN32_UEF_PROBE thread unexpected_process_survival=1\n");
    return 3;
  }

  WriteMarker("WIN32_UEF_PROBE main armed=1\n");
  RaiseAccessViolation();
  WriteMarker("WIN32_UEF_PROBE main unexpected_return=1\n");
  return 3;
}
