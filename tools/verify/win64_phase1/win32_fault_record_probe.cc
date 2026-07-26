#include <cstdint>
#include <cstdio>

#include "runtime/multiplatform/windows/fault_handler_windows.h"

namespace {

int g_failures = 0;

void Expect(const char* label, bool actual, bool expected) {
  if (actual != expected) {
    std::fprintf(stderr,
                 "FAIL %s actual=%d expected=%d\n",
                 label,
                 actual ? 1 : 0,
                 expected ? 1 : 0);
    ++g_failures;
  }
}

art::Win32FaultRecordView Valid(uintptr_t operation) {
  art::Win32FaultRecordView view = {};
  view.exception_code = art::kWin32ExceptionAccessViolation;
  view.number_parameters = 2u;
  view.exception_address = 0x140001234u;
  view.context_rip = view.exception_address;
  view.access_type = operation;
  view.fault_address = 0x20u;
  return view;
}

}  // namespace

int main() {
  Expect("valid-read", art::IsWin32ManagedFaultRecord(Valid(art::kWin32FaultRead)), true);
  Expect("valid-write", art::IsWin32ManagedFaultRecord(Valid(art::kWin32FaultWrite)), true);

  art::Win32FaultRecordView execute = Valid(art::kWin32FaultExecute);
  Expect("execute", art::IsWin32ManagedFaultRecord(execute), false);

  art::Win32FaultRecordView noncontinuable = Valid(art::kWin32FaultRead);
  noncontinuable.exception_flags = art::kWin32ExceptionNonContinuable;
  Expect("noncontinuable", art::IsWin32ManagedFaultRecord(noncontinuable), false);

  art::Win32FaultRecordView short_record = Valid(art::kWin32FaultRead);
  short_record.number_parameters = 1u;
  Expect("short-record", art::IsWin32ManagedFaultRecord(short_record), false);

  art::Win32FaultRecordView wrong_pc = Valid(art::kWin32FaultRead);
  wrong_pc.context_rip += 1u;
  Expect("wrong-pc", art::IsWin32ManagedFaultRecord(wrong_pc), false);

  art::Win32FaultRecordView wrong_code = Valid(art::kWin32FaultRead);
  wrong_code.exception_code = 0xC000001Du;
  Expect("wrong-code", art::IsWin32ManagedFaultRecord(wrong_code), false);

  art::Win32FaultRecordView missing_address = Valid(art::kWin32FaultRead);
  missing_address.exception_address = 0u;
  Expect("missing-address", art::IsWin32ManagedFaultRecord(missing_address), false);

  std::printf("win32_fault_record_probe failures=%d cases=8\n", g_failures);
  if (g_failures != 0) {
    return 1;
  }
  std::puts("win32_fault_record_probe OK");
  return 0;
}
