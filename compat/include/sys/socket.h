#pragma once
#if !defined(_WIN32)
#include_next <sys/socket.h>
#else
/* POSIX-ish sockets over Winsock, using CRT fds via _open_osfhandle. */
#include <winsock2.h>
#include <ws2tcpip.h>
#include <stdint.h>
#ifndef _SSIZE_T_DEFINED
typedef intptr_t ssize_t;
#define _SSIZE_T_DEFINED
#endif
#include <stddef.h>

#ifndef SHUT_RD
#define SHUT_RD SD_RECEIVE
#define SHUT_WR SD_SEND
#define SHUT_RDWR SD_BOTH
#endif

#ifndef MSG_NOSIGNAL
#define MSG_NOSIGNAL 0
#endif
#ifndef MSG_DONTWAIT
#define MSG_DONTWAIT 0x40
#endif
#ifndef SOCK_CLOEXEC
#define SOCK_CLOEXEC 02000000
#endif
#ifndef SOCK_NONBLOCK
#define SOCK_NONBLOCK 04000
#endif

/* SO_REUSEPORT is not meaningful on Windows; keep a value for compile. */
#ifndef SO_DOMAIN
#define SO_DOMAIN 39
#endif
#ifndef SO_PROTOCOL
#define SO_PROTOCOL 38
#endif
#ifndef SO_REUSEPORT
#define SO_REUSEPORT 15
#endif

/* Winsock maps CMSG_* to WSA_CMSG_* that expect WSAMSG.Control; force POSIX
 * msghdr-compatible macros for AOSP NetworkUtilities / sendmsg helpers. */
#ifdef CMSG_SPACE
#undef CMSG_SPACE
#endif
#ifdef CMSG_LEN
#undef CMSG_LEN
#endif
#ifdef CMSG_DATA
#undef CMSG_DATA
#endif
#ifdef CMSG_FIRSTHDR
#undef CMSG_FIRSTHDR
#endif
#ifdef CMSG_NXTHDR
#undef CMSG_NXTHDR
#endif
#ifdef CMSG_ALIGN
#undef CMSG_ALIGN
#endif
/* Minimal cmsg macros for compile; real sendmsg/recvmsg are limited. */
#define CMSG_ALIGN(len) (((len) + sizeof(size_t) - 1) & ~(sizeof(size_t) - 1))
#define CMSG_SPACE(len) (CMSG_ALIGN(sizeof(struct cmsghdr)) + CMSG_ALIGN(len))
#define CMSG_LEN(len) (CMSG_ALIGN(sizeof(struct cmsghdr)) + (len))
#define CMSG_DATA(cmsg) ((unsigned char*)(cmsg) + CMSG_ALIGN(sizeof(struct cmsghdr)))
#define CMSG_FIRSTHDR(mhdr) \
  ((mhdr)->msg_controllen >= sizeof(struct cmsghdr) ? (struct cmsghdr*)(mhdr)->msg_control : (struct cmsghdr*)0)
/* Single-header iteration is enough for current multipath use; full NXTHDR later. */
#define CMSG_NXTHDR(mhdr, cmsg) (struct cmsghdr*)0

#include <sys/uio.h>

/* Winsock (ws2def.h) may already typedef cmsghdr/WSAMSG. Provide msghdr only if needed. */
#ifndef _MDVM_MSGHDR_DEFINED
#define _MDVM_MSGHDR_DEFINED
#ifndef _WSAMSG
struct msghdr {
  void* msg_name;
  socklen_t msg_namelen;
  struct iovec* msg_iov;
  size_t msg_iovlen;
  void* msg_control;
  size_t msg_controllen;
  int msg_flags;
};
#endif
#endif

#ifdef __cplusplus
extern "C" {
#endif

int mdvm_socket(int domain, int type, int protocol);
int mdvm_bind(int fd, const struct sockaddr* addr, socklen_t len);
int mdvm_connect(int fd, const struct sockaddr* addr, socklen_t len);
int mdvm_listen(int fd, int backlog);
int mdvm_accept(int fd, struct sockaddr* addr, socklen_t* len);
int mdvm_shutdown(int fd, int how);
ssize_t mdvm_send(int fd, const void* buf, size_t len, int flags);
ssize_t mdvm_recv(int fd, void* buf, size_t len, int flags);
ssize_t mdvm_sendto(int fd, const void* buf, size_t len, int flags,
                    const struct sockaddr* dest, socklen_t addrlen);
ssize_t mdvm_recvfrom(int fd, void* buf, size_t len, int flags,
                      struct sockaddr* src, socklen_t* addrlen);
ssize_t mdvm_sendmsg(int fd, const struct msghdr* msg, int flags);
ssize_t mdvm_recvmsg(int fd, struct msghdr* msg, int flags);
int mdvm_getsockopt(int fd, int level, int optname, void* optval, socklen_t* optlen);
int mdvm_setsockopt(int fd, int level, int optname, const void* optval, socklen_t optlen);
int mdvm_getsockname(int fd, struct sockaddr* addr, socklen_t* len);
int mdvm_getpeername(int fd, struct sockaddr* addr, socklen_t* len);
int mdvm_socketpair(int domain, int type, int protocol, int sv[2]);
int mdvm_gethostname(char* name, size_t len);

/* Prefer POSIX names when not already provided by Winsock macros.
 * Implementation TU defines MDVM_SOCKET_NO_MACROS. */
#if !defined(MDVM_SOCKET_NO_MACROS)
#ifndef socket
#define socket mdvm_socket
#endif
#ifndef bind
#define bind mdvm_bind
#endif
#ifndef connect
#define connect mdvm_connect
#endif
#ifndef listen
#define listen mdvm_listen
#endif
#ifndef accept
#define accept mdvm_accept
#endif
#ifndef shutdown
#define shutdown mdvm_shutdown
#endif
#ifndef send
#define send mdvm_send
#endif
#ifndef recv
#define recv mdvm_recv
#endif
#ifndef sendto
#define sendto mdvm_sendto
#endif
#ifndef recvfrom
#define recvfrom mdvm_recvfrom
#endif
#ifndef sendmsg
#define sendmsg mdvm_sendmsg
#endif
#ifndef recvmsg
#define recvmsg mdvm_recvmsg
#endif
#ifndef getsockopt
#define getsockopt mdvm_getsockopt
#endif
#ifndef setsockopt
#define setsockopt mdvm_setsockopt
#endif
#ifndef getsockname
#define getsockname mdvm_getsockname
#endif
#ifndef getpeername
#define getpeername mdvm_getpeername
#endif
#ifndef socketpair
#define socketpair mdvm_socketpair
#endif
#ifndef gethostname
#define gethostname mdvm_gethostname
#endif
#endif /* !MDVM_SOCKET_NO_MACROS */

#ifdef __cplusplus
}
#endif
#endif
