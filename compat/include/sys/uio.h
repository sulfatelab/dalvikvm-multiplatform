#pragma once
#if !defined(_WIN32)
#include_next <sys/uio.h>
#else
#include <stddef.h>
struct iovec { void* iov_base; size_t iov_len; };
#ifdef __cplusplus
extern "C" {
#endif
ssize_t readv(int fd, const struct iovec* iov, int iovcnt);
ssize_t writev(int fd, const struct iovec* iov, int iovcnt);
ssize_t process_vm_readv(int pid, const struct iovec* local_iov, unsigned long liovcnt,
                         const struct iovec* remote_iov, unsigned long riovcnt, unsigned long flags);
#ifdef __cplusplus
}
#endif
#endif
