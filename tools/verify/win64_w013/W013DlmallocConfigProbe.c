#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>

#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef _WIN32
#error "W013DlmallocConfigProbe must be compiled for Windows"
#endif

#define HAVE_MMAP 0
#define HAVE_MREMAP 0
#define HAVE_MORECORE 1
#define MORECORE_CONTIGUOUS 1
#define USE_LOCKS 0
#define ONLY_MSPACES 1
#define MSPACES 1
#define NO_MALLINFO 1
#define MALLOC_INSPECT_ALL 1
#define MALLOC_FAILURE_ACTION errno = ENOMEM;

static unsigned char* g_base;
static unsigned char* g_end;
static unsigned char* g_limit;
static intptr_t g_last_positive_increment;

static void* probe_morecore(void* mspace, intptr_t increment) {
  unsigned char* old_end = g_end;
  (void)mspace;
  if (increment > 0) {
    if ((size_t)increment > (size_t)(g_limit - g_end)) {
      return (void*)(~(size_t)0);
    }
    g_end += increment;
    g_last_positive_increment = increment;
  } else if (increment < 0) {
    if ((size_t)(-increment) > (size_t)(g_end - g_base)) {
      return (void*)(~(size_t)0);
    }
    g_end += increment;
  }
  return old_end;
}

#define MORECORE(increment) probe_morecore(m, (increment))
#include "dlmalloc.c"

#ifndef WIN32
#error "dlmalloc lost Win32 platform detection"
#endif

#if HAVE_MMAP != 0 || HAVE_MORECORE != 1 || MORECORE_CONTIGUOUS != 1 || USE_LOCKS != 0
#error "embedded dlmalloc configuration drifted"
#endif

static int Fail(const char* message) {
  fprintf(stderr, "W013_DLMALLOC_CONFIG_FAIL: %s\n", message);
  return 1;
}

int main(void) {
  SYSTEM_INFO system_info;
  const size_t capacity = 1u << 20;
  size_t initial_size;
  mspace arena;
  void* allocation;

  GetSystemInfo(&system_info);
  initial_size = (size_t)system_info.dwPageSize;
  g_base = (unsigned char*)VirtualAlloc(
      NULL, capacity, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
  if (g_base == NULL) {
    return Fail("VirtualAlloc failed");
  }
  g_end = g_base + initial_size;
  g_limit = g_base + capacity;

  arena = create_mspace_with_base(g_base, initial_size, 0);
  if (arena == NULL) {
    VirtualFree(g_base, 0, MEM_RELEASE);
    return Fail("create_mspace_with_base failed");
  }
  if (mparams.page_size != (size_t)system_info.dwPageSize) {
    return Fail("dlmalloc page size does not match dwPageSize");
  }
  if (mparams.granularity != (size_t)system_info.dwPageSize) {
    return Fail("MoreCore granularity used Win32 allocation granularity");
  }

  mspace_set_footprint_limit(arena, capacity);
  allocation = mspace_malloc(arena, initial_size * 4u);
  if (allocation == NULL) {
    return Fail("mspace growth allocation failed");
  }
  if (g_last_positive_increment <= 0 ||
      ((size_t)g_last_positive_increment % (size_t)system_info.dwPageSize) != 0) {
    return Fail("MoreCore increment was not page granular");
  }
  if (system_info.dwPageSize < system_info.dwAllocationGranularity &&
      (size_t)g_last_positive_increment >= (size_t)system_info.dwAllocationGranularity) {
    return Fail("small MoreCore request was rounded to allocation granularity");
  }
  mspace_free(arena, allocation);

  errno = 0;
  if (mspace_malloc(arena, ~(size_t)0) != NULL || errno != ENOMEM) {
    return Fail("allocation failure did not set errno to ENOMEM");
  }

  (void)destroy_mspace(arena);
  if (!VirtualFree(g_base, 0, MEM_RELEASE)) {
    return Fail("VirtualFree failed");
  }

  printf("W013_DLMALLOC_CONFIG_PASS page=%zu granularity=%zu increment=%td\n",
         mparams.page_size,
         mparams.granularity,
         g_last_positive_increment);
  return 0;
}
