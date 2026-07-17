/* CRT-fd wrappers around Winsock for AOSP openjdk / libcore NIO sources.
 * Sockets are dual-represented as CRT fds via _open_osfhandle so existing
 * FileDescriptor.descriptor ints work (same model as win_net_natives).
 */
#define MDVM_SOCKET_NO_MACROS 1
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <io.h>
#include <fcntl.h>
#include <errno.h>
#include <stdint.h>
#ifndef _SSIZE_T_DEFINED
typedef intptr_t ssize_t;
#define _SSIZE_T_DEFINED
#endif
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

#include <sys/socket.h>
#include <sys/epoll.h>
#include <sys/uio.h>
#include <poll.h>

#ifndef INVALID_SOCKET
#define INVALID_SOCKET ((SOCKET)(~0))
#endif

static CRITICAL_SECTION g_wsa_lock;
static int g_wsa_lock_init = 0;
static int g_wsa_ready = 0;

static void ensure_wsa_lock(void) {
  if (!g_wsa_lock_init) {
    InitializeCriticalSection(&g_wsa_lock);
    g_wsa_lock_init = 1;
  }
}

static void ensure_wsa(void) {
  ensure_wsa_lock();
  EnterCriticalSection(&g_wsa_lock);
  if (!g_wsa_ready) {
    WSADATA wsa;
    if (WSAStartup(MAKEWORD(2, 2), &wsa) == 0) g_wsa_ready = 1;
  }
  LeaveCriticalSection(&g_wsa_lock);
}

static int map_wsa_errno(int wsa) {
  switch (wsa) {
    case 0: return 0;
    case WSAEWOULDBLOCK: return EAGAIN;
    case WSAEINPROGRESS: return EINPROGRESS;
    case WSAEALREADY: return EALREADY;
    case WSAENOTSOCK: return ENOTSOCK;
    case WSAEDESTADDRREQ: return EDESTADDRREQ;
    case WSAEMSGSIZE: return EMSGSIZE;
    case WSAEPROTOTYPE: return EPROTOTYPE;
    case WSAENOPROTOOPT: return ENOPROTOOPT;
    case WSAEPROTONOSUPPORT: return EPROTONOSUPPORT;
    case WSAESOCKTNOSUPPORT: return EINVAL;
    case WSAEOPNOTSUPP: return EOPNOTSUPP;
    case WSAEPFNOSUPPORT: return EINVAL;
    case WSAEAFNOSUPPORT: return EAFNOSUPPORT;
    case WSAEADDRINUSE: return EADDRINUSE;
    case WSAEADDRNOTAVAIL: return EADDRNOTAVAIL;
    case WSAENETDOWN: return ENETDOWN;
    case WSAENETUNREACH: return ENETUNREACH;
    case WSAENETRESET: return ENETRESET;
    case WSAECONNABORTED: return ECONNABORTED;
    case WSAECONNRESET: return ECONNRESET;
    case WSAENOBUFS: return ENOBUFS;
    case WSAEISCONN: return EISCONN;
    case WSAENOTCONN: return ENOTCONN;
    case WSAESHUTDOWN: return EINVAL;
    case WSAETIMEDOUT: return ETIMEDOUT;
    case WSAECONNREFUSED: return ECONNREFUSED;
    case WSAEHOSTUNREACH: return EHOSTUNREACH;
    case WSAEINVAL: return EINVAL;
    case WSAEBADF: return EBADF;
    case WSAEACCES: return EACCES;
    case WSAEINTR: return EINTR;
    default: return EINVAL;
  }
}

static void set_wsa_errno(void) {
  errno = map_wsa_errno(WSAGetLastError());
}

static SOCKET sock_from_fd(int fd) {
  if (fd < 0) return INVALID_SOCKET;
  intptr_t h = _get_osfhandle(fd);
  if (h == -1 || h == 0) return INVALID_SOCKET;
  return (SOCKET)h;
}

static int fd_from_socket(SOCKET s) {
  if (s == INVALID_SOCKET) return -1;
  int fd = _open_osfhandle((intptr_t)s, _O_RDWR | _O_BINARY);
  if (fd < 0) {
    closesocket(s);
    errno = EMFILE;
    return -1;
  }
  return fd;
}

static int strip_sock_flags(int* type) {
  int flags = 0;
  if (*type & SOCK_CLOEXEC) {
    flags |= SOCK_CLOEXEC;
    *type &= ~SOCK_CLOEXEC;
  }
  if (*type & SOCK_NONBLOCK) {
    flags |= SOCK_NONBLOCK;
    *type &= ~SOCK_NONBLOCK;
  }
  return flags;
}

int mdvm_socket(int domain, int type, int protocol) {
  ensure_wsa();
  int flags = strip_sock_flags(&type);
  SOCKET s = socket(domain, type, protocol);
  if (s == INVALID_SOCKET) {
    set_wsa_errno();
    return -1;
  }
  if (domain == AF_INET6) {
    int off = 0;
    setsockopt(s, IPPROTO_IPV6, IPV6_V6ONLY, (const char*)&off, sizeof(off));
  }
  if (flags & SOCK_NONBLOCK) {
    u_long nb = 1;
    ioctlsocket(s, FIONBIO, &nb);
  }
  return fd_from_socket(s);
}

int mdvm_bind(int fd, const struct sockaddr* addr, socklen_t len) {
  SOCKET s = sock_from_fd(fd);
  if (s == INVALID_SOCKET) { errno = EBADF; return -1; }
  if (bind(s, addr, (int)len) == SOCKET_ERROR) { set_wsa_errno(); return -1; }
  return 0;
}

int mdvm_connect(int fd, const struct sockaddr* addr, socklen_t len) {
  SOCKET s = sock_from_fd(fd);
  if (s == INVALID_SOCKET) { errno = EBADF; return -1; }
  if (connect(s, addr, (int)len) == SOCKET_ERROR) { set_wsa_errno(); return -1; }
  return 0;
}

int mdvm_listen(int fd, int backlog) {
  SOCKET s = sock_from_fd(fd);
  if (s == INVALID_SOCKET) { errno = EBADF; return -1; }
  if (listen(s, backlog) == SOCKET_ERROR) { set_wsa_errno(); return -1; }
  return 0;
}

int mdvm_accept(int fd, struct sockaddr* addr, socklen_t* len) {
  SOCKET s = sock_from_fd(fd);
  if (s == INVALID_SOCKET) { errno = EBADF; return -1; }
  int alen = len ? (int)*len : 0;
  SOCKET c = accept(s, addr, len ? &alen : NULL);
  if (c == INVALID_SOCKET) { set_wsa_errno(); return -1; }
  if (len) *len = (socklen_t)alen;
  return fd_from_socket(c);
}

int mdvm_shutdown(int fd, int how) {
  SOCKET s = sock_from_fd(fd);
  if (s == INVALID_SOCKET) { errno = EBADF; return -1; }
  if (shutdown(s, how) == SOCKET_ERROR) { set_wsa_errno(); return -1; }
  return 0;
}

ssize_t mdvm_send(int fd, const void* buf, size_t len, int flags) {
  SOCKET s = sock_from_fd(fd);
  if (s == INVALID_SOCKET) { errno = EBADF; return -1; }
  int r = send(s, (const char*)buf, (int)len, flags & ~MSG_NOSIGNAL);
  if (r == SOCKET_ERROR) { set_wsa_errno(); return -1; }
  return r;
}

ssize_t mdvm_recv(int fd, void* buf, size_t len, int flags) {
  SOCKET s = sock_from_fd(fd);
  if (s == INVALID_SOCKET) { errno = EBADF; return -1; }
  int r = recv(s, (char*)buf, (int)len, flags);
  if (r == SOCKET_ERROR) { set_wsa_errno(); return -1; }
  return r;
}

ssize_t mdvm_sendto(int fd, const void* buf, size_t len, int flags,
                    const struct sockaddr* dest, socklen_t addrlen) {
  SOCKET s = sock_from_fd(fd);
  if (s == INVALID_SOCKET) { errno = EBADF; return -1; }
  int r = sendto(s, (const char*)buf, (int)len, flags & ~MSG_NOSIGNAL, dest, (int)addrlen);
  if (r == SOCKET_ERROR) { set_wsa_errno(); return -1; }
  return r;
}

ssize_t mdvm_recvfrom(int fd, void* buf, size_t len, int flags,
                      struct sockaddr* src, socklen_t* addrlen) {
  SOCKET s = sock_from_fd(fd);
  if (s == INVALID_SOCKET) { errno = EBADF; return -1; }
  int alen = addrlen ? (int)*addrlen : 0;
  int r = recvfrom(s, (char*)buf, (int)len, flags, src, addrlen ? &alen : NULL);
  if (r == SOCKET_ERROR) { set_wsa_errno(); return -1; }
  if (addrlen) *addrlen = (socklen_t)alen;
  return r;
}

ssize_t mdvm_sendmsg(int fd, const struct msghdr* msg, int flags) {
  if (!msg || !msg->msg_iov || msg->msg_iovlen == 0) { errno = EINVAL; return -1; }
  /* Flatten first iov only if multiple (best-effort). */
  if (msg->msg_iovlen == 1) {
    return mdvm_sendto(fd, msg->msg_iov[0].iov_base, msg->msg_iov[0].iov_len, flags,
                       (const struct sockaddr*)msg->msg_name, (socklen_t)msg->msg_namelen);
  }
  size_t total = 0;
  for (size_t i = 0; i < msg->msg_iovlen; i++) total += msg->msg_iov[i].iov_len;
  char* tmp = (char*)malloc(total ? total : 1);
  if (!tmp) { errno = ENOMEM; return -1; }
  size_t off = 0;
  for (size_t i = 0; i < msg->msg_iovlen; i++) {
    memcpy(tmp + off, msg->msg_iov[i].iov_base, msg->msg_iov[i].iov_len);
    off += msg->msg_iov[i].iov_len;
  }
  ssize_t r = mdvm_sendto(fd, tmp, total, flags,
                          (const struct sockaddr*)msg->msg_name, (socklen_t)msg->msg_namelen);
  free(tmp);
  return r;
}

ssize_t mdvm_recvmsg(int fd, struct msghdr* msg, int flags) {
  if (!msg || !msg->msg_iov || msg->msg_iovlen == 0) { errno = EINVAL; return -1; }
  if (msg->msg_iovlen == 1) {
    socklen_t nlen = (socklen_t)msg->msg_namelen;
    ssize_t r = mdvm_recvfrom(fd, msg->msg_iov[0].iov_base, msg->msg_iov[0].iov_len, flags,
                              (struct sockaddr*)msg->msg_name, msg->msg_name ? &nlen : NULL);
    if (msg->msg_name) msg->msg_namelen = nlen;
    return r;
  }
  size_t total = 0;
  for (size_t i = 0; i < msg->msg_iovlen; i++) total += msg->msg_iov[i].iov_len;
  char* tmp = (char*)malloc(total ? total : 1);
  if (!tmp) { errno = ENOMEM; return -1; }
  socklen_t nlen = (socklen_t)msg->msg_namelen;
  ssize_t r = mdvm_recvfrom(fd, tmp, total, flags,
                            (struct sockaddr*)msg->msg_name, msg->msg_name ? &nlen : NULL);
  if (msg->msg_name) msg->msg_namelen = nlen;
  if (r > 0) {
    size_t left = (size_t)r, off = 0;
    for (size_t i = 0; i < msg->msg_iovlen && left; i++) {
      size_t n = msg->msg_iov[i].iov_len;
      if (n > left) n = left;
      memcpy(msg->msg_iov[i].iov_base, tmp + off, n);
      off += n; left -= n;
    }
  }
  free(tmp);
  return r;
}

int mdvm_getsockopt(int fd, int level, int optname, void* optval, socklen_t* optlen) {
  SOCKET s = sock_from_fd(fd);
  if (s == INVALID_SOCKET) { errno = EBADF; return -1; }
  /* Linux SO_DOMAIN / SO_PROTOCOL not available; synthesize from PROTOCOL_INFO. */
  if (level == SOL_SOCKET && (optname == SO_DOMAIN || optname == 39)) {
    WSAPROTOCOL_INFOW info; int ilen = sizeof(info);
    if (getsockopt(s, SOL_SOCKET, SO_PROTOCOL_INFOW, (char*)&info, &ilen) == SOCKET_ERROR) {
      set_wsa_errno(); return -1;
    }
    if (optval && optlen && *optlen >= (socklen_t)sizeof(int)) {
      *(int*)optval = info.iAddressFamily;
      *optlen = sizeof(int);
    }
    return 0;
  }
  if (level == SOL_SOCKET && (optname == SO_PROTOCOL || optname == 38)) {
    WSAPROTOCOL_INFOW info; int ilen = sizeof(info);
    if (getsockopt(s, SOL_SOCKET, SO_PROTOCOL_INFOW, (char*)&info, &ilen) == SOCKET_ERROR) {
      set_wsa_errno(); return -1;
    }
    if (optval && optlen && *optlen >= (socklen_t)sizeof(int)) {
      *(int*)optval = info.iProtocol;
      *optlen = sizeof(int);
    }
    return 0;
  }
  int len = optlen ? (int)*optlen : 0;
  if (getsockopt(s, level, optname, (char*)optval, &len) == SOCKET_ERROR) {
    set_wsa_errno(); return -1;
  }
  if (optlen) *optlen = (socklen_t)len;
  return 0;
}

int mdvm_setsockopt(int fd, int level, int optname, const void* optval, socklen_t optlen) {
  SOCKET s = sock_from_fd(fd);
  if (s == INVALID_SOCKET) { errno = EBADF; return -1; }
  if (optname == SO_REUSEPORT) {
    /* Map to SO_REUSEADDR on Windows. */
    optname = SO_REUSEADDR;
  }
  if (setsockopt(s, level, optname, (const char*)optval, (int)optlen) == SOCKET_ERROR) {
    set_wsa_errno(); return -1;
  }
  return 0;
}

int mdvm_getsockname(int fd, struct sockaddr* addr, socklen_t* len) {
  SOCKET s = sock_from_fd(fd);
  if (s == INVALID_SOCKET) { errno = EBADF; return -1; }
  int alen = len ? (int)*len : 0;
  if (getsockname(s, addr, &alen) == SOCKET_ERROR) { set_wsa_errno(); return -1; }
  if (len) *len = (socklen_t)alen;
  return 0;
}

int mdvm_getpeername(int fd, struct sockaddr* addr, socklen_t* len) {
  SOCKET s = sock_from_fd(fd);
  if (s == INVALID_SOCKET) { errno = EBADF; return -1; }
  int alen = len ? (int)*len : 0;
  if (getpeername(s, addr, &alen) == SOCKET_ERROR) { set_wsa_errno(); return -1; }
  if (len) *len = (socklen_t)alen;
  return 0;
}

int mdvm_socketpair(int domain, int type, int protocol, int sv[2]) {
  (void)domain; (void)type; (void)protocol;
  if (!sv) { errno = EINVAL; return -1; }
  ensure_wsa();
  /* Connected TCP loopback pair (AF_UNIX not portable here). */
  SOCKET listener = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
  if (listener == INVALID_SOCKET) { set_wsa_errno(); return -1; }
  struct sockaddr_in addr;
  memset(&addr, 0, sizeof(addr));
  addr.sin_family = AF_INET;
  addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  addr.sin_port = 0;
  if (bind(listener, (struct sockaddr*)&addr, sizeof(addr)) == SOCKET_ERROR ||
      listen(listener, 1) == SOCKET_ERROR) {
    set_wsa_errno(); closesocket(listener); return -1;
  }
  int alen = sizeof(addr);
  if (getsockname(listener, (struct sockaddr*)&addr, &alen) == SOCKET_ERROR) {
    set_wsa_errno(); closesocket(listener); return -1;
  }
  SOCKET a = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
  if (a == INVALID_SOCKET) { set_wsa_errno(); closesocket(listener); return -1; }
  if (connect(a, (struct sockaddr*)&addr, sizeof(addr)) == SOCKET_ERROR) {
    set_wsa_errno(); closesocket(a); closesocket(listener); return -1;
  }
  SOCKET b = accept(listener, NULL, NULL);
  closesocket(listener);
  if (b == INVALID_SOCKET) { set_wsa_errno(); closesocket(a); return -1; }
  sv[0] = fd_from_socket(a);
  if (sv[0] < 0) { closesocket(b); return -1; }
  sv[1] = fd_from_socket(b);
  if (sv[1] < 0) { _close(sv[0]); return -1; }
  return 0;
}

int mdvm_gethostname(char* name, size_t len) {
  ensure_wsa();
  if (!name || len == 0) { errno = EINVAL; return -1; }
  if (gethostname(name, (int)len) == SOCKET_ERROR) { set_wsa_errno(); return -1; }
  return 0;
}

/* ---- epoll emulated with select (bounded FD_SETSIZE) ---- */

typedef struct {
  int fd;
  uint32_t events;
  epoll_data_t data;
} mdvm_ep_entry;

typedef struct {
  int magic;
  int capacity;
  int count;
  mdvm_ep_entry* entries;
} mdvm_ep_set;

#define MDVM_EP_MAGIC 0x45504f4c /* 'EPOL' */

static mdvm_ep_set* ep_from_fd(int epfd) {
  if (epfd < 0) return NULL;
  intptr_t h = _get_osfhandle(epfd);
  /* We store pointer in a pipe/read end isn't available; use a heap object
   * referenced by a private map keyed by epfd. Simple: store pointer bits in
   * a global table of open epfds. */
  (void)h;
  return NULL;
}

/* Global sparse map epfd -> set */
enum { MDVM_EP_MAX = 256 };
static mdvm_ep_set* g_ep_map[MDVM_EP_MAX];
static CRITICAL_SECTION g_ep_lock;
static int g_ep_lock_init = 0;

static void ensure_ep_lock(void) {
  if (!g_ep_lock_init) {
    InitializeCriticalSection(&g_ep_lock);
    g_ep_lock_init = 1;
  }
}

static int ep_register(mdvm_ep_set* set) {
  /* Create a dummy pipe fd as handle identity. */
  int fds[2];
  if (_pipe(fds, 256, _O_BINARY) != 0) return -1;
  _close(fds[1]);
  ensure_ep_lock();
  EnterCriticalSection(&g_ep_lock);
  if (fds[0] >= 0 && fds[0] < MDVM_EP_MAX) {
    g_ep_map[fds[0]] = set;
    LeaveCriticalSection(&g_ep_lock);
    return fds[0];
  }
  /* Fallback linear scan for free slot using duplicate dummy. */
  int slot = -1;
  for (int i = 3; i < MDVM_EP_MAX; i++) {
    if (!g_ep_map[i]) { slot = i; break; }
  }
  if (slot < 0) {
    LeaveCriticalSection(&g_ep_lock);
    _close(fds[0]);
    errno = EMFILE;
    return -1;
  }
  /* Can't rebind fd number easily; just use the pipe fd if in range else close. */
  if (fds[0] < MDVM_EP_MAX) {
    g_ep_map[fds[0]] = set;
    LeaveCriticalSection(&g_ep_lock);
    return fds[0];
  }
  LeaveCriticalSection(&g_ep_lock);
  _close(fds[0]);
  errno = EMFILE;
  return -1;
}

static mdvm_ep_set* ep_lookup(int epfd) {
  if (epfd < 0 || epfd >= MDVM_EP_MAX) return NULL;
  ensure_ep_lock();
  EnterCriticalSection(&g_ep_lock);
  mdvm_ep_set* s = g_ep_map[epfd];
  LeaveCriticalSection(&g_ep_lock);
  return s;
}

int epoll_create(int size) {
  (void)size;
  return epoll_create1(0);
}

int epoll_create1(int flags) {
  (void)flags;
  mdvm_ep_set* set = (mdvm_ep_set*)calloc(1, sizeof(*set));
  if (!set) { errno = ENOMEM; return -1; }
  set->magic = MDVM_EP_MAGIC;
  set->capacity = 64;
  set->entries = (mdvm_ep_entry*)calloc((size_t)set->capacity, sizeof(mdvm_ep_entry));
  if (!set->entries) { free(set); errno = ENOMEM; return -1; }
  int fd = ep_register(set);
  if (fd < 0) {
    free(set->entries);
    free(set);
    return -1;
  }
  return fd;
}

int epoll_ctl(int epfd, int op, int fd, struct epoll_event* event) {
  mdvm_ep_set* set = ep_lookup(epfd);
  if (!set || set->magic != MDVM_EP_MAGIC) { errno = EBADF; return -1; }
  ensure_ep_lock();
  EnterCriticalSection(&g_ep_lock);
  int idx = -1;
  for (int i = 0; i < set->count; i++) {
    if (set->entries[i].fd == fd) { idx = i; break; }
  }
  int rc = 0;
  if (op == EPOLL_CTL_ADD) {
    if (idx >= 0) { errno = EEXIST; rc = -1; goto out; }
    if (!event) { errno = EINVAL; rc = -1; goto out; }
    if (set->count >= set->capacity) {
      int nc = set->capacity * 2;
      mdvm_ep_entry* ne = (mdvm_ep_entry*)realloc(set->entries, (size_t)nc * sizeof(mdvm_ep_entry));
      if (!ne) { errno = ENOMEM; rc = -1; goto out; }
      set->entries = ne;
      set->capacity = nc;
    }
    set->entries[set->count].fd = fd;
    set->entries[set->count].events = event->events;
    set->entries[set->count].data = event->data;
    set->count++;
  } else if (op == EPOLL_CTL_MOD) {
    if (idx < 0 || !event) { errno = ENOENT; rc = -1; goto out; }
    set->entries[idx].events = event->events;
    set->entries[idx].data = event->data;
  } else if (op == EPOLL_CTL_DEL) {
    if (idx < 0) { errno = ENOENT; rc = -1; goto out; }
    set->entries[idx] = set->entries[set->count - 1];
    set->count--;
  } else {
    errno = EINVAL; rc = -1;
  }
out:
  LeaveCriticalSection(&g_ep_lock);
  return rc;
}

int epoll_wait(int epfd, struct epoll_event* events, int maxevents, int timeout) {
  mdvm_ep_set* set = ep_lookup(epfd);
  if (!set || set->magic != MDVM_EP_MAGIC || !events || maxevents <= 0) {
    errno = EINVAL; return -1;
  }
  ensure_wsa();

  for (;;) {
    fd_set rfds, wfds, efds;
    FD_ZERO(&rfds); FD_ZERO(&wfds); FD_ZERO(&efds);
    SOCKET max_s = 0;
    int interested = 0;

    ensure_ep_lock();
    EnterCriticalSection(&g_ep_lock);
    int count = set->count;
    /* Snapshot small. */
    mdvm_ep_entry snap[FD_SETSIZE];
    if (count > FD_SETSIZE) count = FD_SETSIZE;
    for (int i = 0; i < count; i++) snap[i] = set->entries[i];
    LeaveCriticalSection(&g_ep_lock);

    for (int i = 0; i < count; i++) {
      SOCKET s = sock_from_fd(snap[i].fd);
      if (s == INVALID_SOCKET) continue;
      if (snap[i].events & (EPOLLIN | EPOLLRDNORM | EPOLLPRI | EPOLLRDHUP))
        FD_SET(s, &rfds);
      if (snap[i].events & (EPOLLOUT | EPOLLWRNORM))
        FD_SET(s, &wfds);
      FD_SET(s, &efds);
      if (s > max_s) max_s = s;
      interested++;
    }

    struct timeval tv, *ptv = NULL;
    if (timeout >= 0) {
      tv.tv_sec = timeout / 1000;
      tv.tv_usec = (timeout % 1000) * 1000;
      ptv = &tv;
    }

    int sr = 0;
    if (interested == 0) {
      if (timeout == 0) return 0;
      if (timeout > 0) Sleep((DWORD)timeout);
      else Sleep(10);
      if (timeout >= 0) return 0;
      continue;
    } else {
      sr = select((int)max_s + 1, &rfds, &wfds, &efds, ptv);
    }
    if (sr == SOCKET_ERROR) { set_wsa_errno(); return -1; }
    if (sr == 0) return 0;

    int out = 0;
    for (int i = 0; i < count && out < maxevents; i++) {
      SOCKET s = sock_from_fd(snap[i].fd);
      if (s == INVALID_SOCKET) continue;
      uint32_t ev = 0;
      if (FD_ISSET(s, &rfds)) ev |= EPOLLIN;
      if (FD_ISSET(s, &wfds)) ev |= EPOLLOUT;
      if (FD_ISSET(s, &efds)) ev |= EPOLLERR;
      if (ev) {
        events[out].events = ev;
        events[out].data = snap[i].data;
        out++;
      }
    }
    if (out > 0) return out;
    if (timeout == 0) return 0;
  }
}

/* Improved poll for socket CRT fds using select (replaces no-op stub when linked). */
int mdvm_poll_sockets(struct pollfd* fds, unsigned long nfds, int timeout) {
  ensure_wsa();
  if (!fds) { errno = EINVAL; return -1; }
  fd_set rfds, wfds, efds;
  FD_ZERO(&rfds); FD_ZERO(&wfds); FD_ZERO(&efds);
  SOCKET max_s = 0;
  int any = 0;
  for (unsigned long i = 0; i < nfds; i++) {
    fds[i].revents = 0;
    if (fds[i].fd < 0) continue;
    SOCKET s = sock_from_fd(fds[i].fd);
    if (s == INVALID_SOCKET) {
      fds[i].revents = POLLNVAL;
      any++;
      continue;
    }
    if (fds[i].events & (POLLIN | POLLRDNORM | POLLPRI)) FD_SET(s, &rfds);
    if (fds[i].events & (POLLOUT | POLLWRNORM)) FD_SET(s, &wfds);
    FD_SET(s, &efds);
    if (s > max_s) max_s = s;
  }
  struct timeval tv, *ptv = NULL;
  if (timeout >= 0) {
    tv.tv_sec = timeout / 1000;
    tv.tv_usec = (timeout % 1000) * 1000;
    ptv = &tv;
  }
  int sr = select((int)max_s + 1, &rfds, &wfds, &efds, ptv);
  if (sr == SOCKET_ERROR) { set_wsa_errno(); return -1; }
  if (sr == 0) return 0;
  int ready = 0;
  for (unsigned long i = 0; i < nfds; i++) {
    if (fds[i].fd < 0) continue;
    SOCKET s = sock_from_fd(fds[i].fd);
    if (s == INVALID_SOCKET) { ready++; continue; }
    short rev = 0;
    if (FD_ISSET(s, &rfds)) rev |= POLLIN;
    if (FD_ISSET(s, &wfds)) rev |= POLLOUT;
    if (FD_ISSET(s, &efds)) rev |= POLLERR;
    fds[i].revents = rev;
    if (rev) ready++;
  }
  return ready;
}
