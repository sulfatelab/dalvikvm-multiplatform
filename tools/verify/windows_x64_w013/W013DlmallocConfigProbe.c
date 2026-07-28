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
static unsigned char* g_floor;
static unsigned char* g_limit;
static size_t g_zero_calls;
static size_t g_positive_calls;
static size_t g_negative_calls;
static size_t g_failed_positive_calls;
static intptr_t g_last_positive_increment;
static intptr_t g_last_negative_increment;

static void* probe_morecore(void* mspace, intptr_t increment) {
  unsigned char* old_end = g_end;
  (void)mspace;
  if (increment > 0) {
    ++g_positive_calls;
    if ((size_t)increment > (size_t)(g_limit - g_end)) {
      ++g_failed_positive_calls;
      return (void*)(~(size_t)0);
    }
    g_end += increment;
    g_last_positive_increment = increment;
  } else if (increment < 0) {
    ++g_negative_calls;
    if ((size_t)(-increment) > (size_t)(g_end - g_floor)) {
      return (void*)(~(size_t)0);
    }
    g_end += increment;
    g_last_negative_increment = increment;
  } else {
    ++g_zero_calls;
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
  size_t positive_calls_before_regrow;
  size_t negative_calls_before_trim;
  size_t failed_calls_before_limit;
  mspace arena;
  void* allocation;
  unsigned char* grown_end;
  unsigned char* trimmed_end;

  GetSystemInfo(&system_info);
  initial_size = (size_t)system_info.dwPageSize;
  g_base = (unsigned char*)VirtualAlloc(
      NULL, capacity, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
  if (g_base == NULL) {
    return Fail("VirtualAlloc failed");
  }
  g_end = g_base + initial_size;
  g_floor = g_end;
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
  if (g_zero_calls == 0 || g_positive_calls == 0) {
    return Fail("mspace growth did not query and advance MoreCore");
  }
  grown_end = g_end;
  mspace_free(arena, allocation);

  negative_calls_before_trim = g_negative_calls;
  if (mspace_trim(arena, 0) == 0) {
    return Fail("mspace_trim did not release the grown top segment");
  }
  if (g_negative_calls == negative_calls_before_trim ||
      g_last_negative_increment >= 0 ||
      ((size_t)(-g_last_negative_increment) % (size_t)system_info.dwPageSize) != 0) {
    return Fail("mspace trim did not issue page-granular negative MoreCore");
  }
  if (g_end >= grown_end || g_end < g_floor) {
    return Fail("mspace trim produced an invalid mock break");
  }
  trimmed_end = g_end;

  positive_calls_before_regrow = g_positive_calls;
  allocation = mspace_malloc(arena, initial_size * 4u);
  if (allocation == NULL) {
    return Fail("mspace regrowth allocation failed");
  }
  if (g_positive_calls == positive_calls_before_regrow || g_end <= trimmed_end) {
    return Fail("mspace allocation did not regrow after trim");
  }
  mspace_free(arena, allocation);

  if (mspace_trim(arena, 0) == 0) {
    return Fail("mspace did not trim before mock-owner failure test");
  }
  failed_calls_before_limit = g_failed_positive_calls;
  g_limit = g_end;
  mspace_set_footprint_limit(arena, capacity * 2u);
  errno = 0;
  if (mspace_malloc(arena, initial_size * 4u) != NULL || errno != ENOMEM) {
    g_limit = g_base + capacity;
    return Fail("mock-owner capacity failure did not return ENOMEM");
  }
  g_limit = g_base + capacity;
  if (g_failed_positive_calls == failed_calls_before_limit) {
    return Fail("capacity failure did not reach the mock MoreCore owner");
  }

  mspace_set_footprint_limit(arena, capacity);
  allocation = mspace_malloc(arena, initial_size);
  if (allocation == NULL) {
    return Fail("mspace was unusable after MoreCore failure");
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

  printf("W013_DLMALLOC_CONFIG_PASS page=%zu granularity=%zu positive=%zu negative=%zu "
         "queries=%zu failures=%zu last_positive=%td last_negative=%td\n",
         mparams.page_size,
         mparams.granularity,
         g_positive_calls,
         g_negative_calls,
         g_zero_calls,
         g_failed_positive_calls,
         g_last_positive_increment,
         g_last_negative_increment);
  return 0;
}
