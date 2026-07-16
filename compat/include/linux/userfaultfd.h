#pragma once
#include <stdint.h>
#define UFFD_API 0xAA
#define UFFDIO_API 0xC018AA3F
#define UFFDIO_REGISTER 0xC020AA00
#define UFFDIO_UNREGISTER 0xC020AA01
#define UFFDIO_WAKE 0xC018AA02
#define UFFDIO_COPY 0xC028AA03
#define UFFDIO_ZEROPAGE 0xC020AA04
#define UFFDIO_MOVE 0xC028AA05
#define UFFDIO_WRITEPROTECT 0xC010AA06
#define UFFD_FEATURE_PAGEFAULT_FLAG_WP (1<<0)
#define UFFD_FEATURE_EVENT_FORK (1<<1)
#define UFFD_FEATURE_EVENT_REMAP (1<<2)
#define UFFD_FEATURE_EVENT_REMOVE (1<<3)
#define UFFD_FEATURE_MISSING_HUGETLBFS (1<<4)
#define UFFD_FEATURE_MISSING_SHMEM (1<<5)
#define UFFD_FEATURE_EVENT_UNMAP (1<<6)
#define UFFD_FEATURE_SIGBUS (1<<7)
#define UFFD_FEATURE_THREAD_ID (1<<8)
#define UFFD_FEATURE_MINOR_HUGETLBFS (1<<9)
#define UFFD_FEATURE_MINOR_SHMEM (1<<10)
#define UFFD_FEATURE_EXACT_ADDRESS (1<<11)
#define UFFD_FEATURE_WP_HUGETLBFS_SHMEM (1<<12)
#define UFFD_FEATURE_WP_UNPOPULATED (1<<13)
#define UFFD_FEATURE_POISON (1<<14)
#define UFFD_FEATURE_WP_ASYNC (1<<15)
#define UFFD_FEATURE_MOVE (1<<16)
#define UFFD_PAGEFAULT_FLAG_WRITE 1
#define UFFD_PAGEFAULT_FLAG_WP 2
#define UFFD_PAGEFAULT_FLAG_MINOR 4
#define UFFD_EVENT_PAGEFAULT 0x12
#define UFFD_EVENT_FORK 0x13
#define UFFD_EVENT_REMAP 0x14
#define UFFD_EVENT_REMOVE 0x15
#define UFFD_EVENT_UNMAP 0x16
#define UFFD_USER_MODE_ONLY 1
#define UFFDIO_REGISTER_MODE_MISSING 0x1
#define UFFDIO_REGISTER_MODE_WP 0x2
#define UFFDIO_REGISTER_MODE_MINOR 0x4
#define UFFDIO_COPY_MODE_DONTWAKE 1
#define UFFDIO_COPY_MODE_WP 2
#define UFFDIO_ZEROPAGE_MODE_DONTWAKE 1
#define UFFDIO_MOVE_MODE_DONTWAKE 1
#define UFFDIO_MOVE_MODE_ALLOW_SRC_HOLES 2
#define __NR_userfaultfd 323
struct uffdio_api { uint64_t api; uint64_t features; uint64_t ioctls; };
struct uffdio_range { uint64_t start; uint64_t len; };
struct uffdio_register { struct uffdio_range range; uint64_t mode; uint64_t ioctls; };
struct uffdio_copy { uint64_t dst; uint64_t src; uint64_t len; uint64_t mode; int64_t copy; };
struct uffdio_zeropage { struct uffdio_range range; uint64_t mode; int64_t zeropage; };
struct uffdio_move { uint64_t dst; uint64_t src; uint64_t len; uint64_t mode; int64_t move; };
struct uffdio_writeprotect { struct uffdio_range range; uint64_t mode; };
struct uffd_msg {
  uint8_t event;
  uint8_t reserved1;
  uint16_t reserved2;
  uint32_t reserved3;
  union {
    struct {
      uint64_t flags;
      uint64_t address;
      uint32_t ftid;
    } pagefault;
    struct { uint32_t ufd; } fork;
    struct { uint64_t from; uint64_t to; uint64_t len; } remap;
    struct { uint64_t start; uint64_t end; } remove;
    struct { /* reserved */ uint64_t reserved1; uint64_t reserved2; uint64_t reserved3; } reserved;
  } arg;
};
