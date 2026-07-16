#pragma once
#if !defined(_WIN32)
#include_next <link.h>
#else
#include <elf.h>
#include <stddef.h>
struct dl_phdr_info {
  Elf64_Addr dlpi_addr;
  const char* dlpi_name;
  const Elf64_Phdr* dlpi_phdr;
  Elf64_Half dlpi_phnum;
};
#ifdef __cplusplus
extern "C" {
#endif
int dl_iterate_phdr(int (*callback)(struct dl_phdr_info*, size_t, void*), void* data);
#ifdef __cplusplus
}
#endif
#endif
