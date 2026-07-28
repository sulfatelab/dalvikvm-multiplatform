#include <stdint.h>
#include <windows.h>

static void WriteResult(const char* text, DWORD length) {
  DWORD written;
  WriteFile(GetStdHandle(STD_OUTPUT_HANDLE), text, length, &written, NULL);
}

static int RunCase(SIZE_T capacity, SIZE_T blocked_low_bytes) {
  const SIZE_T divider = capacity / 2u;
  HANDLE section = NULL;
  void* blocker = NULL;
  void* primary = NULL;
  void* writable = NULL;
  int result = 1;

  if (blocked_low_bytes != 0u) {
    blocker = VirtualAlloc((void*)(uintptr_t)0x10000u,
                           blocked_low_bytes,
                           MEM_RESERVE,
                           PAGE_NOACCESS);
    if (blocker == NULL) {
      result = 10;
      goto cleanup;
    }
  }

  section = CreateFileMappingW(INVALID_HANDLE_VALUE,
                               NULL,
                               PAGE_EXECUTE_READWRITE,
                               (DWORD)(capacity >> 32),
                               (DWORD)capacity,
                               NULL);
  if (section == NULL) {
    result = 20;
    goto cleanup;
  }

  SYSTEM_INFO system_info;
  GetSystemInfo(&system_info);

  MEM_ADDRESS_REQUIREMENTS requirements = {0};
  requirements.LowestStartingAddress =
      (void*)(uintptr_t)system_info.dwAllocationGranularity;
  requirements.HighestEndingAddress = (void*)(uintptr_t)UINT32_MAX;
  requirements.Alignment = 0u;

  MEM_EXTENDED_PARAMETER parameter = {0};
  parameter.Type = MemExtendedParameterAddressRequirements;
  parameter.Pointer = &requirements;

  primary = MapViewOfFile3(section,
                           NULL,
                           NULL,
                           0u,
                           capacity,
                           0u,
                           PAGE_EXECUTE_READ,
                           &parameter,
                           1u);
  if (primary == NULL) {
    result = 30;
    goto cleanup;
  }
  if ((uintptr_t)primary + capacity >= UINT64_C(0x100000000)) {
    result = 31;
    goto cleanup;
  }
  if (blocker != NULL &&
      (uintptr_t)primary < (uintptr_t)blocker + blocked_low_bytes) {
    result = 32;
    goto cleanup;
  }

  DWORD old_protection;
  if (!VirtualProtect(primary, divider, PAGE_READONLY, &old_protection)) {
    result = 40;
    goto cleanup;
  }

  writable = MapViewOfFile3(section,
                            NULL,
                            NULL,
                            0u,
                            capacity,
                            0u,
                            PAGE_READWRITE,
                            NULL,
                            0u);
  if (writable == NULL) {
    result = 50;
    goto cleanup;
  }

  ((volatile uint8_t*)writable)[divider - 1u] = 0xa5u;
  ((volatile uint8_t*)writable)[divider] = 0x5au;
  if (((volatile uint8_t*)primary)[divider - 1u] != 0xa5u ||
      ((volatile uint8_t*)primary)[divider] != 0x5au) {
    result = 60;
    goto cleanup;
  }

  uint8_t* writable_code = (uint8_t*)writable + divider;
  writable_code[0] = 0xb8u;  // mov eax, 42
  writable_code[1] = 42u;
  writable_code[2] = 0u;
  writable_code[3] = 0u;
  writable_code[4] = 0u;
  writable_code[5] = 0xc3u;  // ret
  if (!FlushInstructionCache(GetCurrentProcess(), (uint8_t*)primary + divider, 6u)) {
    result = 70;
    goto cleanup;
  }

  typedef int (*ProbeFunction)(void);
  if (((ProbeFunction)((uint8_t*)primary + divider))() != 42) {
    result = 71;
    goto cleanup;
  }

  MEMORY_BASIC_INFORMATION data_info;
  MEMORY_BASIC_INFORMATION code_info;
  MEMORY_BASIC_INFORMATION writable_info;
  if (!VirtualQuery(primary, &data_info, sizeof(data_info)) ||
      !VirtualQuery((uint8_t*)primary + divider, &code_info, sizeof(code_info)) ||
      !VirtualQuery(writable, &writable_info, sizeof(writable_info))) {
    result = 80;
    goto cleanup;
  }
  if (data_info.Protect != PAGE_READONLY ||
      code_info.Protect != PAGE_EXECUTE_READ ||
      writable_info.Protect != PAGE_READWRITE) {
    result = 81;
    goto cleanup;
  }

  result = 0;

cleanup:
  if (writable != NULL) {
    UnmapViewOfFile(writable);
  }
  if (primary != NULL) {
    UnmapViewOfFile(primary);
  }
  if (section != NULL) {
    CloseHandle(section);
  }
  if (blocker != NULL) {
    VirtualFree(blocker, 0u, MEM_RELEASE);
  }
  return result;
}

void mainCRTStartup(void) {
  int result = RunCase(64u * 1024u * 1024u, 0u);
  if (result == 0) {
    result = RunCase(64u * 1024u * 1024u + 2u * 4096u,
                     256u * 1024u * 1024u);
  }

  if (result == 0) {
    static const char kPass[] = "JitSectionProbe PASS\r\n";
    WriteResult(kPass, (DWORD)(sizeof(kPass) - 1u));
  } else {
    static const char kFail[] = "JitSectionProbe FAIL\r\n";
    WriteResult(kFail, (DWORD)(sizeof(kFail) - 1u));
  }
  ExitProcess((UINT)result);
}
