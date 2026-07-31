#include <windows.h>

#include <cstdio>
#include <cstring>

namespace {

struct ExceptionCounts {
  unsigned first_access_violation = 0u;
  unsigned second_access_violation = 0u;
  unsigned first_stack_overflow = 0u;
  unsigned second_stack_overflow = 0u;
  unsigned first_guard_page = 0u;
  unsigned first_other_hardware = 0u;
  unsigned second_other = 0u;
};

bool IsOtherHardwareFault(DWORD code) {
  return code == EXCEPTION_ILLEGAL_INSTRUCTION ||
         code == EXCEPTION_INT_DIVIDE_BY_ZERO ||
         code == EXCEPTION_FLT_DIVIDE_BY_ZERO ||
         code == EXCEPTION_IN_PAGE_ERROR ||
         code == 0xc0000602u;  // STATUS_FAIL_FAST_EXCEPTION.
}

const char* ModeArgument(const char* mode) {
  if (std::strcmp(mode, "npe") == 0) {
    return "npe";
  }
  if (std::strcmp(mode, "so") == 0) {
    return "so";
  }
  return nullptr;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 2 || ModeArgument(argv[1]) == nullptr) {
    std::fputs("usage: win32_debugger_probe.exe <npe|so>\n", stderr);
    return 2;
  }

  char command_line[1024] = {};
  const int length = std::snprintf(
      command_line,
      sizeof(command_line),
      "dalvikvm.exe -Xbootclasspath:run\\boot.jar "
      "-Xbootclasspath-locations:run\\boot.jar "
      "-Ximage:/nonexistent-no-boot-image -XjdwpProvider:none "
      "-Xms64m -Xmx512m -verbose:jit -Xjitwarmupthreshold:0 "
      "-Xjitthreshold:0 "
      "-cp run\\w010managedfaultprobe.jar W010ManagedFaultProbe %s",
      ModeArgument(argv[1]));
  if (length <= 0 || static_cast<size_t>(length) >= sizeof(command_line)) {
    std::fputs("WIN32_DEBUGGER_PROBE FAIL command line overflow\n", stderr);
    return 1;
  }

  STARTUPINFOA startup = {};
  startup.cb = sizeof(startup);
  startup.dwFlags = STARTF_USESTDHANDLES;
  startup.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
  startup.hStdOutput = GetStdHandle(STD_OUTPUT_HANDLE);
  startup.hStdError = GetStdHandle(STD_ERROR_HANDLE);
  PROCESS_INFORMATION process = {};
  std::printf("WIN32_DEBUGGER_PROBE start mode=%s continue=DBG_EXCEPTION_NOT_HANDLED\n",
              argv[1]);
  std::fflush(stdout);
  if (!CreateProcessA("dalvikvm.exe",
                      command_line,
                      nullptr,
                      nullptr,
                      TRUE,
                      DEBUG_ONLY_THIS_PROCESS,
                      nullptr,
                      nullptr,
                      &startup,
                      &process)) {
    std::fprintf(stderr,
                 "WIN32_DEBUGGER_PROBE FAIL CreateProcess error=%lu\n",
                 static_cast<unsigned long>(GetLastError()));
    return 1;
  }

  ExceptionCounts counts;
  DWORD child_exit = STILL_ACTIVE;
  bool wait_ok = true;
  bool saw_exit = false;
  while (!saw_exit) {
    DEBUG_EVENT event = {};
    if (!WaitForDebugEvent(&event, 120000u)) {
      std::fprintf(stderr,
                   "WIN32_DEBUGGER_PROBE FAIL WaitForDebugEvent error=%lu\n",
                   static_cast<unsigned long>(GetLastError()));
      wait_ok = false;
      TerminateProcess(process.hProcess, 0x7fu);
      break;
    }
    DWORD continue_status = DBG_CONTINUE;
    switch (event.dwDebugEventCode) {
      case CREATE_PROCESS_DEBUG_EVENT:
        if (event.u.CreateProcessInfo.hFile != nullptr) {
          CloseHandle(event.u.CreateProcessInfo.hFile);
        }
        break;
      case LOAD_DLL_DEBUG_EVENT:
        if (event.u.LoadDll.hFile != nullptr) {
          CloseHandle(event.u.LoadDll.hFile);
        }
        break;
      case EXCEPTION_DEBUG_EVENT: {
        const DWORD code = event.u.Exception.ExceptionRecord.ExceptionCode;
        const bool first = event.u.Exception.dwFirstChance != FALSE;
        if (code == EXCEPTION_BREAKPOINT || code == EXCEPTION_SINGLE_STEP) {
          continue_status = DBG_CONTINUE;
          break;
        }
        continue_status = DBG_EXCEPTION_NOT_HANDLED;
        if (code == EXCEPTION_ACCESS_VIOLATION) {
          if (first) {
            ++counts.first_access_violation;
            if (counts.first_access_violation == 1u) {
              std::puts("WIN32_DEBUGGER_PROBE first_chance_av stop=1 "
                        "continue=DBG_EXCEPTION_NOT_HANDLED");
              std::fflush(stdout);
            }
          } else {
            ++counts.second_access_violation;
          }
        } else if (code == EXCEPTION_STACK_OVERFLOW) {
          first ? ++counts.first_stack_overflow : ++counts.second_stack_overflow;
        } else if (code == STATUS_GUARD_PAGE_VIOLATION) {
          if (first) {
            ++counts.first_guard_page;
          } else {
            ++counts.second_other;
          }
        } else if (first && IsOtherHardwareFault(code)) {
          ++counts.first_other_hardware;
        } else if (!first) {
          ++counts.second_other;
        }
        break;
      }
      case EXIT_PROCESS_DEBUG_EVENT:
        child_exit = event.u.ExitProcess.dwExitCode;
        saw_exit = true;
        break;
      default:
        break;
    }
    if (!ContinueDebugEvent(event.dwProcessId, event.dwThreadId, continue_status)) {
      std::fprintf(stderr,
                   "WIN32_DEBUGGER_PROBE FAIL ContinueDebugEvent error=%lu\n",
                   static_cast<unsigned long>(GetLastError()));
      wait_ok = false;
      TerminateProcess(process.hProcess, 0x7fu);
      break;
    }
  }

  WaitForSingleObject(process.hProcess, 10000u);
  if (child_exit == STILL_ACTIVE) {
    GetExitCodeProcess(process.hProcess, &child_exit);
  }
  CloseHandle(process.hThread);
  CloseHandle(process.hProcess);

  const unsigned first_hardware = counts.first_access_violation +
      counts.first_stack_overflow + counts.first_other_hardware;
  const unsigned second_chance = counts.second_access_violation +
      counts.second_stack_overflow + counts.second_other;
  std::printf(
      "WIN32_DEBUGGER_PROBE result mode=%s child_exit=%lu first_av=%u "
      "first_stack_overflow=%u first_guard_page=%u first_other_hardware=%u "
      "first_hardware=%u second_chance=%u\n",
      argv[1],
      static_cast<unsigned long>(child_exit),
      counts.first_access_violation,
      counts.first_stack_overflow,
      counts.first_guard_page,
      counts.first_other_hardware,
      first_hardware,
      second_chance);

  const bool npe_ok = std::strcmp(argv[1], "npe") != 0 ||
      (counts.first_access_violation != 0u &&
       counts.first_stack_overflow == 0u &&
       counts.first_other_hardware == 0u);
  const bool so_ok = std::strcmp(argv[1], "so") != 0 || first_hardware == 0u;
  if (!wait_ok || child_exit != 0u || second_chance != 0u || !npe_ok || !so_ok) {
    std::puts("WIN32_DEBUGGER_PROBE FAIL");
    return 1;
  }
  std::printf("WIN32_DEBUGGER_PROBE PASS mode=%s\n", argv[1]);
  return 0;
}
