#include <errno.h>
#include <io.h>
#include <stdint.h>
#include <stdlib.h>
#include <windows.h>

#include "mdvm_socket_fd_registry.h"

/*
 * Process-wide socket ownership shared by libjavacore, libopenjdk, and the
 * JVM_* bridge through libopenjdkjvm.  A regular Win32 HANDLE can be
 * numerically equal to a Winsock SOCKET, so probing _get_osfhandle(fd) with a
 * Winsock API is not a valid type test.
 */
static SRWLOCK g_socket_fd_lock = SRWLOCK_INIT;
static unsigned char* g_socket_fds = NULL;
static size_t g_socket_fds_capacity = 0;

static int ensure_socket_fd_capacity_locked(int fd) {
  if (fd < 0) {
    errno = EBADF;
    return -1;
  }
  size_t needed = (size_t)fd + 1u;
  if (needed <= g_socket_fds_capacity) return 0;

  size_t capacity = g_socket_fds_capacity != 0u ? g_socket_fds_capacity : 64u;
  while (capacity < needed) {
    if (capacity > SIZE_MAX / 2u) {
      errno = ENOMEM;
      return -1;
    }
    capacity *= 2u;
  }

  HANDLE heap = GetProcessHeap();
  unsigned char* replacement;
  if (g_socket_fds == NULL) {
    replacement = (unsigned char*)HeapAlloc(heap, HEAP_ZERO_MEMORY, capacity);
  } else {
    replacement = (unsigned char*)HeapReAlloc(
        heap, HEAP_ZERO_MEMORY, g_socket_fds, capacity);
  }
  if (replacement == NULL) {
    errno = ENOMEM;
    return -1;
  }
  g_socket_fds = replacement;
  g_socket_fds_capacity = capacity;
  return 0;
}

int mdvm_socket_fd_register(int fd) {
  AcquireSRWLockExclusive(&g_socket_fd_lock);
  int result = ensure_socket_fd_capacity_locked(fd);
  if (result == 0) g_socket_fds[fd] = 1u;
  ReleaseSRWLockExclusive(&g_socket_fd_lock);
  return result;
}

void mdvm_socket_fd_unregister(int fd) {
  if (fd < 0) return;
  AcquireSRWLockExclusive(&g_socket_fd_lock);
  if ((size_t)fd < g_socket_fds_capacity) g_socket_fds[fd] = 0u;
  ReleaseSRWLockExclusive(&g_socket_fd_lock);
}

int mdvm_socket_fd_is_socket(int fd) {
  if (fd < 0) return 0;
  AcquireSRWLockShared(&g_socket_fd_lock);
  int result = (size_t)fd < g_socket_fds_capacity && g_socket_fds[fd] != 0u;
  ReleaseSRWLockShared(&g_socket_fd_lock);
  return result;
}

int mdvm_socket_fd_close(int fd) {
  AcquireSRWLockExclusive(&g_socket_fd_lock);
  int was_socket =
      fd >= 0 && (size_t)fd < g_socket_fds_capacity && g_socket_fds[fd] != 0u;
  if (was_socket) g_socket_fds[fd] = 0u;

  /* Clear before _close(): a successful close can immediately recycle fd. */
  int result = _close(fd);
  if (result != 0 && was_socket) g_socket_fds[fd] = 1u;
  ReleaseSRWLockExclusive(&g_socket_fd_lock);
  return result;
}

int mdvm_socket_fd_dup(int fd) {
  AcquireSRWLockExclusive(&g_socket_fd_lock);
  int source_is_socket =
      fd >= 0 && (size_t)fd < g_socket_fds_capacity && g_socket_fds[fd] != 0u;
  int newfd = _dup(fd);
  if (newfd >= 0 && source_is_socket) {
    if (ensure_socket_fd_capacity_locked(newfd) != 0) {
      int saved_errno = errno;
      _close(newfd);
      newfd = -1;
      errno = saved_errno;
    } else {
      g_socket_fds[newfd] = 1u;
    }
  }
  ReleaseSRWLockExclusive(&g_socket_fd_lock);
  return newfd;
}

int mdvm_socket_fd_dup2(int oldfd, int newfd) {
  AcquireSRWLockExclusive(&g_socket_fd_lock);
  int source_is_socket =
      oldfd >= 0 && (size_t)oldfd < g_socket_fds_capacity && g_socket_fds[oldfd] != 0u;
  if (source_is_socket && ensure_socket_fd_capacity_locked(newfd) != 0) {
    ReleaseSRWLockExclusive(&g_socket_fd_lock);
    return -1;
  }

  int result = _dup2(oldfd, newfd);
  if (result >= 0 && newfd >= 0 && (size_t)newfd < g_socket_fds_capacity) {
    g_socket_fds[newfd] = source_is_socket ? 1u : 0u;
  }
  ReleaseSRWLockExclusive(&g_socket_fd_lock);
  return result;
}
