#include <windows.h>

#include <cstdint>
#include <cstdio>
#include <cwchar>
#include <string>

namespace {

std::wstring QuoteArgument(const wchar_t *argument) {
  if (*argument != L'\0' && std::wcspbrk(argument, L" \t\n\v\"") == nullptr) {
    return argument;
  }
  std::wstring quoted(1u, L'\"');
  size_t backslashes = 0u;
  for (const wchar_t *cursor = argument;; ++cursor) {
    if (*cursor == L'\\') {
      ++backslashes;
      continue;
    }
    if (*cursor == L'\"') {
      quoted.append(backslashes * 2u + 1u, L'\\');
      quoted.push_back(L'\"');
      backslashes = 0u;
      continue;
    }
    if (*cursor == L'\0') {
      quoted.append(backslashes * 2u, L'\\');
      quoted.push_back(L'\"');
      break;
    }
    quoted.append(backslashes, L'\\');
    backslashes = 0u;
    quoted.push_back(*cursor);
  }
  return quoted;
}

bool PrintLastError(const char *operation) {
  std::fprintf(stderr, "W025_POLICY_LAUNCHER_FAIL: %s error=%lu\n", operation,
               ::GetLastError());
  return false;
}

} // namespace

int wmain(int argc, wchar_t **argv) {
  if (argc < 5) {
    std::fprintf(stderr,
                 "usage: W025PolicyLauncher.exe <cfg|dynamic> <zero|nonzero> "
                 "<executable> [arguments...]\n");
    return 2;
  }

  const bool cfg_mode = std::wcscmp(argv[1], L"cfg") == 0;
  const bool dynamic_mode = std::wcscmp(argv[1], L"dynamic") == 0;
  const bool expect_zero = std::wcscmp(argv[2], L"zero") == 0;
  const bool expect_nonzero = std::wcscmp(argv[2], L"nonzero") == 0;
  if ((!cfg_mode && !dynamic_mode) || (!expect_zero && !expect_nonzero)) {
    std::fprintf(stderr,
                 "W025_POLICY_LAUNCHER_FAIL: invalid policy or expectation\n");
    return 2;
  }

  uint64_t mitigation =
      cfg_mode
          ? PROCESS_CREATION_MITIGATION_POLICY_CONTROL_FLOW_GUARD_ALWAYS_ON
          : PROCESS_CREATION_MITIGATION_POLICY_PROHIBIT_DYNAMIC_CODE_ALWAYS_ON;
  SIZE_T attribute_bytes = 0u;
  ::InitializeProcThreadAttributeList(nullptr, 1u, 0u, &attribute_bytes);
  auto *attributes = reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(
      ::HeapAlloc(::GetProcessHeap(), 0u, attribute_bytes));
  if (attributes == nullptr) {
    PrintLastError("HeapAlloc(attribute list)");
    return 1;
  }

  bool initialized = false;
  bool ok = true;
  if (!::InitializeProcThreadAttributeList(attributes, 1u, 0u,
                                           &attribute_bytes)) {
    ok = PrintLastError("InitializeProcThreadAttributeList");
  } else {
    initialized = true;
  }
  if (ok && !::UpdateProcThreadAttribute(
                attributes, 0u, PROC_THREAD_ATTRIBUTE_MITIGATION_POLICY,
                &mitigation, sizeof(mitigation), nullptr, nullptr)) {
    ok = PrintLastError("UpdateProcThreadAttribute(mitigation policy)");
  }

  std::wstring command_line;
  for (int index = 3; index < argc; ++index) {
    if (!command_line.empty()) {
      command_line.push_back(L' ');
    }
    command_line += QuoteArgument(argv[index]);
  }

  HANDLE job = nullptr;
  if (ok) {
    job = ::CreateJobObjectW(nullptr, nullptr);
    if (job == nullptr) {
      ok = PrintLastError("CreateJobObjectW");
    }
  }
  if (ok) {
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits = {};
    limits.BasicLimitInformation.LimitFlags =
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    if (!::SetInformationJobObject(job, JobObjectExtendedLimitInformation,
                                   &limits, sizeof(limits))) {
      ok = PrintLastError("SetInformationJobObject");
    }
  }

  STARTUPINFOEXW startup = {};
  startup.StartupInfo.cb = sizeof(startup);
  startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES;
  startup.StartupInfo.hStdInput = ::GetStdHandle(STD_INPUT_HANDLE);
  startup.StartupInfo.hStdOutput = ::GetStdHandle(STD_OUTPUT_HANDLE);
  startup.StartupInfo.hStdError = ::GetStdHandle(STD_ERROR_HANDLE);
  startup.lpAttributeList = attributes;
  PROCESS_INFORMATION process = {};
  if (ok &&
      !::CreateProcessW(argv[3], command_line.data(), nullptr, nullptr, TRUE,
                        EXTENDED_STARTUPINFO_PRESENT | CREATE_SUSPENDED,
                        nullptr, nullptr, &startup.StartupInfo, &process)) {
    ok = PrintLastError("CreateProcessW");
  }
  if (ok && !::AssignProcessToJobObject(job, process.hProcess)) {
    ok = PrintLastError("AssignProcessToJobObject");
  }

  PROCESS_MITIGATION_DYNAMIC_CODE_POLICY dynamic_code = {};
  PROCESS_MITIGATION_CONTROL_FLOW_GUARD_POLICY cfg = {};
  if (ok &&
      (!::GetProcessMitigationPolicy(process.hProcess, ProcessDynamicCodePolicy,
                                     &dynamic_code, sizeof(dynamic_code)) ||
       !::GetProcessMitigationPolicy(process.hProcess,
                                     ProcessControlFlowGuardPolicy, &cfg,
                                     sizeof(cfg)))) {
    ok = PrintLastError("GetProcessMitigationPolicy(child)");
  }
  if (ok && ((cfg_mode && cfg.EnableControlFlowGuard == 0u) ||
             (dynamic_mode && dynamic_code.ProhibitDynamicCode == 0u))) {
    std::fprintf(
        stderr,
        "W025_POLICY_LAUNCHER_FAIL: requested child policy is not effective\n");
    ok = false;
  }

  if (ok) {
    std::printf("W025_POLICY_CHILD policy=%s dynamic_prohibit=%u "
                "dynamic_thread_opt_out=%u cfg_enabled=%u cfg_strict=%u\n",
                cfg_mode ? "cfg" : "dynamic", dynamic_code.ProhibitDynamicCode,
                dynamic_code.AllowThreadOptOut, cfg.EnableControlFlowGuard,
                cfg.StrictMode);
    if (::ResumeThread(process.hThread) == static_cast<DWORD>(-1)) {
      ok = PrintLastError("ResumeThread");
    }
  }

  DWORD child_exit = static_cast<DWORD>(-1);
  if (ok) {
    const DWORD wait = ::WaitForSingleObject(process.hProcess, 300000u);
    if (wait != WAIT_OBJECT_0) {
      ok = PrintLastError(wait == WAIT_TIMEOUT ? "child timeout"
                                               : "WaitForSingleObject");
    } else if (!::GetExitCodeProcess(process.hProcess, &child_exit)) {
      ok = PrintLastError("GetExitCodeProcess");
    }
  }

  if (process.hThread != nullptr) {
    ::CloseHandle(process.hThread);
  }
  if (process.hProcess != nullptr) {
    ::CloseHandle(process.hProcess);
  }
  if (job != nullptr) {
    ::CloseHandle(job);
  }
  if (initialized) {
    ::DeleteProcThreadAttributeList(attributes);
  }
  ::HeapFree(::GetProcessHeap(), 0u, attributes);

  if (!ok) {
    return 1;
  }
  const bool exit_matches = expect_zero ? child_exit == 0u : child_exit != 0u;
  if (!exit_matches) {
    std::fprintf(stderr,
                 "W025_POLICY_LAUNCHER_FAIL: child exit=%lu expectation=%s\n",
                 child_exit, expect_zero ? "zero" : "nonzero");
    return 1;
  }
  std::printf(
      "W025_POLICY_LAUNCHER_PASS policy=%s child_exit=%lu expected=%s\n",
      cfg_mode ? "cfg" : "dynamic", child_exit,
      expect_zero ? "zero" : "nonzero");
  return 0;
}
