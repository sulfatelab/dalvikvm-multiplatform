/* Minimal classic sockets for Win64 ART Phase 3 (A7-oriented).
 * Maps Android/bionic OsConstants values to Winsock, dual-stack IPv6.
 * NIO.2 is intentionally out of scope.
 */
#include <jni.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <errno.h>
#include <fcntl.h>
#include <io.h>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>

#pragma comment(lib, "ws2_32.lib")

/* Android OsConstants (bionic) used by libcore */
enum {
  A_AF_UNIX = 1,
  A_AF_INET = 2,
  A_AF_INET6 = 10,
  A_SOCK_STREAM = 1,
  A_SOCK_DGRAM = 2,
  A_SOL_SOCKET = 1,
  A_SO_REUSEADDR = 2,
  A_SO_ERROR = 4,
  A_SO_LINGER = 13,
  A_SO_DOMAIN = 39,
  A_SO_PROTOCOL = 38,
  A_IPV6_V6ONLY = 26,
  A_F_GETFL = 3,
  A_F_SETFL = 4,
  A_O_NONBLOCK = 2048,
  A_POLLIN = 1,
  A_POLLOUT = 4,
  A_POLLERR = 8,
  A_EAGAIN = 11,
  A_EINPROGRESS = 115,
  A_ECONNREFUSED = 111,
  A_EADDRINUSE = 98,
  A_EINVAL = 22,
  A_EBADF = 9,
  A_EACCES = 13
};

static int g_wsa_ready = 0;
static jclass g_fd_class;
static jfieldID g_fd_descriptor;
static jmethodID g_fd_ctor;

static void ensure_wsa(void) {
  if (g_wsa_ready) return;
  WSADATA wsa;
  if (WSAStartup(MAKEWORD(2, 2), &wsa) == 0) g_wsa_ready = 1;
}

static void ensure_fd(JNIEnv* env) {
  if (g_fd_class) return;
  jclass c = (*env)->FindClass(env, "java/io/FileDescriptor");
  g_fd_class = (jclass)(*env)->NewGlobalRef(env, c);
  g_fd_descriptor = (*env)->GetFieldID(env, g_fd_class, "descriptor", "I");
  g_fd_ctor = (*env)->GetMethodID(env, g_fd_class, "<init>", "()V");
}

static jobject fd_from_int(JNIEnv* env, int fd) {
  ensure_fd(env);
  jobject o = g_fd_ctor ? (*env)->NewObject(env, g_fd_class, g_fd_ctor)
                        : (*env)->AllocObject(env, g_fd_class);
  if (o && g_fd_descriptor) (*env)->SetIntField(env, o, g_fd_descriptor, fd);
  return o;
}

static int fd_to_int(JNIEnv* env, jobject fdObj) {
  if (!fdObj) return -1;
  ensure_fd(env);
  return (*env)->GetIntField(env, fdObj, g_fd_descriptor);
}

static SOCKET socket_from_fd(int fd) {
  if (fd < 0) return INVALID_SOCKET;
  return (SOCKET)_get_osfhandle(fd);
}

static void throw_errno(JNIEnv* env, const char* function, int android_errno) {
  jclass c = (*env)->FindClass(env, "android/system/ErrnoException");
  if (!c) return;
  jmethodID ctor = (*env)->GetMethodID(env, c, "<init>", "(Ljava/lang/String;I)V");
  if (!ctor) return;
  jstring fn = (*env)->NewStringUTF(env, function ? function : "native");
  jobject ex = (*env)->NewObject(env, c, ctor, fn, (jint)android_errno);
  if (ex) (*env)->Throw(env, (jthrowable)ex);
}

static int map_wsa_to_android(int wsa) {
  switch (wsa) {
    case WSAEWOULDBLOCK: return A_EAGAIN;
    case WSAEINPROGRESS: return A_EINPROGRESS;
    case WSAECONNREFUSED: return A_ECONNREFUSED;
    case WSAEADDRINUSE: return A_EADDRINUSE;
    case WSAEINVAL: return A_EINVAL;
    case WSAEBADF: return A_EBADF;
    case WSAEACCES: return A_EACCES;
    case WSAECONNRESET: return 104; /* ECONNRESET-ish */
    case WSAETIMEDOUT: return 110;
    case WSAENOTCONN: return 107;
    default: return wsa ? wsa : A_EINVAL;
  }
}

static int map_domain(int a_domain) {
  if (a_domain == A_AF_INET) return AF_INET;
  if (a_domain == A_AF_INET6) return AF_INET6;
  if (a_domain == A_AF_UNIX) return AF_UNIX;
  return a_domain;
}

static int map_type(int a_type) {
  if (a_type == A_SOCK_STREAM) return SOCK_STREAM;
  if (a_type == A_SOCK_DGRAM) return SOCK_DGRAM;
  return a_type;
}

static int socket_family(SOCKET s) {
  struct sockaddr_storage ss; int len = sizeof(ss);
  if (getsockname(s, (struct sockaddr*)&ss, &len) == 0) return ss.ss_family;
  /* unbound IPv6 sockets may still report AF_INET6 */
  WSAPROTOCOL_INFOW info; int ilen = sizeof(info);
  if (getsockopt(s, SOL_SOCKET, SO_PROTOCOL_INFOW, (char*)&info, &ilen) == 0)
    return info.iAddressFamily;
  return AF_UNSPEC;
}

/* Convert Java InetAddress to sockaddr; if sock is AF_INET6 and addr is IPv4,
 * use IPv4-mapped IPv6 (::ffff:a.b.c.d) so dual-stack binds/connects work. */
static int java_addr_to_sockaddr_for_socket(JNIEnv* env, SOCKET sock, jobject inetAddress, jint port,
                                           struct sockaddr_storage* ss, int* len) {
  if (!inetAddress || !ss || !len) return -1;
  jclass c = (*env)->GetObjectClass(env, inetAddress);
  jmethodID mid = (*env)->GetMethodID(env, c, "getAddress", "()[B");
  if (!mid) return -1;
  jbyteArray arr = (jbyteArray)(*env)->CallObjectMethod(env, inetAddress, mid);
  if (!arr) return -1;
  jsize n = (*env)->GetArrayLength(env, arr);
  jbyte* bytes = (*env)->GetByteArrayElements(env, arr, 0);
  if (!bytes) return -1;
  memset(ss, 0, sizeof(*ss));
  int fam = (sock != INVALID_SOCKET) ? socket_family(sock) : AF_UNSPEC;
  if (n == 4) {
    if (fam == AF_INET6) {
      struct sockaddr_in6* in6 = (struct sockaddr_in6*)ss;
      in6->sin6_family = AF_INET6;
      in6->sin6_port = htons((u_short)port);
      /* ::ffff:IPv4 */
      memset(&in6->sin6_addr, 0, sizeof(in6->sin6_addr));
      {
        unsigned char* p = (unsigned char*)&in6->sin6_addr;
        p[10] = 0xff; p[11] = 0xff;
        memcpy(p + 12, bytes, 4);
      }
      *len = sizeof(*in6);
    } else {
      struct sockaddr_in* in = (struct sockaddr_in*)ss;
      in->sin_family = AF_INET;
      in->sin_port = htons((u_short)port);
      memcpy(&in->sin_addr, bytes, 4);
      *len = sizeof(*in);
    }
  } else if (n == 16) {
    struct sockaddr_in6* in6 = (struct sockaddr_in6*)ss;
    in6->sin6_family = AF_INET6;
    in6->sin6_port = htons((u_short)port);
    memcpy(&in6->sin6_addr, bytes, 16);
    *len = sizeof(*in6);
  } else {
    (*env)->ReleaseByteArrayElements(env, arr, bytes, JNI_ABORT);
    return -1;
  }
  (*env)->ReleaseByteArrayElements(env, arr, bytes, JNI_ABORT);
  return 0;
}

static int java_addr_to_sockaddr(JNIEnv* env, jobject inetAddress, jint port, struct sockaddr_storage* ss, int* len) {
  return java_addr_to_sockaddr_for_socket(env, INVALID_SOCKET, inetAddress, port, ss, len);
}

static jobject sockaddr_to_inet_socket_address(JNIEnv* env, const struct sockaddr_storage* ss) {
  char host[INET6_ADDRSTRLEN] = {0};
  int port = 0;
  if (ss->ss_family == AF_INET) {
    const struct sockaddr_in* in = (const struct sockaddr_in*)ss;
    inet_ntop(AF_INET, &in->sin_addr, host, sizeof(host));
    port = ntohs(in->sin_port);
  } else if (ss->ss_family == AF_INET6) {
    const struct sockaddr_in6* in6 = (const struct sockaddr_in6*)ss;
    /* IPv4-mapped */
    if (IN6_IS_ADDR_V4MAPPED(&in6->sin6_addr)) {
      struct in_addr a4;
      memcpy(&a4, ((const uint8_t*)&in6->sin6_addr) + 12, 4);
      inet_ntop(AF_INET, &a4, host, sizeof(host));
    } else {
      inet_ntop(AF_INET6, &in6->sin6_addr, host, sizeof(host));
    }
    port = ntohs(in6->sin6_port);
  } else {
    return NULL;
  }
  jclass c = (*env)->FindClass(env, "java/net/InetSocketAddress");
  if (!c) return NULL;
  jmethodID ctor = (*env)->GetMethodID(env, c, "<init>", "(Ljava/lang/String;I)V");
  if (!ctor) return NULL;
  jstring jhost = (*env)->NewStringUTF(env, host);
  return (*env)->NewObject(env, c, ctor, jhost, (jint)port);
}

/* ===== socket ===== */
__declspec(dllexport) jobject Java_libcore_io_Linux_socket(JNIEnv* env, jobject thiz, jint domain, jint type, jint protocol) {
  (void)thiz;
  ensure_wsa();
  int wdomain = map_domain(domain);
  int wtype = map_type(type);
  SOCKET s = socket(wdomain, wtype, protocol);
  if (s == INVALID_SOCKET) {
    throw_errno(env, "socket", map_wsa_to_android(WSAGetLastError()));
    return NULL;
  }
  /* Dual-stack: allow IPv4-mapped on IPv6 sockets */
  if (wdomain == AF_INET6) {
    int no = 0;
    setsockopt(s, IPPROTO_IPV6, IPV6_V6ONLY, (const char*)&no, sizeof(no));
  }
  int fd = _open_osfhandle((intptr_t)s, _O_RDWR | _O_BINARY);
  if (fd < 0) {
    closesocket(s);
    throw_errno(env, "socket", A_EINVAL);
    return NULL;
  }
  return fd_from_int(env, fd);
}
__declspec(dllexport) jobject Java_libcore_io_Linux_socket__III(JNIEnv* env, jobject thiz, jint domain, jint type, jint protocol) {
  return Java_libcore_io_Linux_socket(env, thiz, domain, type, protocol);
}

/* ===== bind(InetAddress, port) ===== */
__declspec(dllexport) void Java_libcore_io_Linux_bind__Ljava_io_FileDescriptor_2Ljava_net_InetAddress_2I(
    JNIEnv* env, jobject thiz, jobject fdObj, jobject addr, jint port) {
  (void)thiz;
  ensure_wsa();
  SOCKET s = socket_from_fd(fd_to_int(env, fdObj));
  if (s == INVALID_SOCKET) { throw_errno(env, "bind", A_EBADF); return; }
  struct sockaddr_storage ss; int len = 0;
  if (java_addr_to_sockaddr_for_socket(env, s, addr, port, &ss, &len) != 0) {
    throw_errno(env, "bind", A_EINVAL); return;
  }
  if (bind(s, (struct sockaddr*)&ss, len) != 0) {
    throw_errno(env, "bind", map_wsa_to_android(WSAGetLastError()));
  }
}
/* Overload used by some call sites: bind(fd, SocketAddress) — not implemented fully */
__declspec(dllexport) void Java_libcore_io_Linux_bind(JNIEnv* env, jobject thiz, jobject fdObj, jobject addrOrSa, jint port) {
  /* If port looks like a real port method, treat as InetAddress overload */
  Java_libcore_io_Linux_bind__Ljava_io_FileDescriptor_2Ljava_net_InetAddress_2I(env, thiz, fdObj, addrOrSa, port);
}

/* ===== connect(InetAddress, port) ===== */
__declspec(dllexport) void Java_libcore_io_Linux_connect__Ljava_io_FileDescriptor_2Ljava_net_InetAddress_2I(
    JNIEnv* env, jobject thiz, jobject fdObj, jobject addr, jint port) {
  (void)thiz;
  ensure_wsa();
  SOCKET s = socket_from_fd(fd_to_int(env, fdObj));
  if (s == INVALID_SOCKET) { throw_errno(env, "connect", A_EBADF); return; }
  struct sockaddr_storage ss; int len = 0;
  if (java_addr_to_sockaddr_for_socket(env, s, addr, port, &ss, &len) != 0) {
    throw_errno(env, "connect", A_EINVAL); return;
  }
  if (connect(s, (struct sockaddr*)&ss, len) != 0) {
    int werr = WSAGetLastError();
    /* Non-blocking connect in progress: Android expects EINPROGRESS, not EAGAIN. */
    if (werr == WSAEWOULDBLOCK || werr == WSAEINPROGRESS) {
      throw_errno(env, "connect", A_EINPROGRESS);
      return;
    }
    throw_errno(env, "connect", map_wsa_to_android(werr));
  }
}
__declspec(dllexport) void Java_libcore_io_Linux_connect(JNIEnv* env, jobject thiz, jobject fdObj, jobject addr, jint port) {
  Java_libcore_io_Linux_connect__Ljava_io_FileDescriptor_2Ljava_net_InetAddress_2I(env, thiz, fdObj, addr, port);
}

/* ===== listen ===== */
__declspec(dllexport) void Java_libcore_io_Linux_listen(JNIEnv* env, jobject thiz, jobject fdObj, jint backlog) {
  (void)thiz;
  ensure_wsa();
  SOCKET s = socket_from_fd(fd_to_int(env, fdObj));
  if (s == INVALID_SOCKET) { throw_errno(env, "listen", A_EBADF); return; }
  if (listen(s, backlog) != 0) throw_errno(env, "listen", map_wsa_to_android(WSAGetLastError()));
}
__declspec(dllexport) void Java_libcore_io_Linux_listen__Ljava_io_FileDescriptor_2I(JNIEnv* env, jobject thiz, jobject fdObj, jint backlog) {
  Java_libcore_io_Linux_listen(env, thiz, fdObj, backlog);
}

/* ===== accept(fd, InetSocketAddress peer) ===== */
__declspec(dllexport) jobject Java_libcore_io_Linux_accept(JNIEnv* env, jobject thiz, jobject fdObj, jobject peerAddress) {
  (void)thiz;
  ensure_wsa();
  SOCKET s = socket_from_fd(fd_to_int(env, fdObj));
  if (s == INVALID_SOCKET) { throw_errno(env, "accept", A_EBADF); return NULL; }
  struct sockaddr_storage ss; int len = sizeof(ss);
  SOCKET ns = accept(s, (struct sockaddr*)&ss, &len);
  if (ns == INVALID_SOCKET) {
    throw_errno(env, "accept", map_wsa_to_android(WSAGetLastError()));
    return NULL;
  }
  /* Winsock inherits non-blocking mode from listener; Android expects blocking accepted sockets. */
  {
    u_long nb = 0;
    ioctlsocket(ns, FIONBIO, &nb);
  }
  if (peerAddress) {
    /* Fill mutable InetSocketAddress if possible via reflection fields holder */
    jobject filled = sockaddr_to_inet_socket_address(env, &ss);
    if (filled) {
      /* InetSocketAddress is immutable; PlainSocketImpl uses peerAddress from accept return path.
         Android accept mutates a temporary InetSocketAddress via JNI in real libcore.
         We approximate by setting fields if present. */
      jclass pac = (*env)->GetObjectClass(env, peerAddress);
      jclass filledc = (*env)->GetObjectClass(env, filled);
      jmethodID getAddr = (*env)->GetMethodID(env, filledc, "getAddress", "()Ljava/net/InetAddress;");
      jmethodID getPort = (*env)->GetMethodID(env, filledc, "getPort", "()I");
      jobject ia = (*env)->CallObjectMethod(env, filled, getAddr);
      jint p = (*env)->CallIntMethod(env, filled, getPort);
      /* Try holder fields used by Android InetSocketAddress */
      jfieldID holder = (*env)->GetFieldID(env, pac, "holder", "Ljava/net/InetSocketAddress$InetSocketAddressHolder;");
      if (holder && !(*env)->ExceptionCheck(env)) {
        jobject h = (*env)->GetObjectField(env, peerAddress, holder);
        if (h) {
          jclass hc = (*env)->GetObjectClass(env, h);
          jfieldID addrF = (*env)->GetFieldID(env, hc, "addr", "Ljava/net/InetAddress;");
          jfieldID portF = (*env)->GetFieldID(env, hc, "port", "I");
          if (addrF) (*env)->SetObjectField(env, h, addrF, ia);
          if (portF) (*env)->SetIntField(env, h, portF, p);
        }
      } else {
        (*env)->ExceptionClear(env);
      }
    }
  }
  int fd = _open_osfhandle((intptr_t)ns, _O_RDWR | _O_BINARY);
  if (fd < 0) { closesocket(ns); throw_errno(env, "accept", A_EINVAL); return NULL; }
  return fd_from_int(env, fd);
}
__declspec(dllexport) jobject Java_libcore_io_Linux_accept__Ljava_io_FileDescriptor_2Ljava_net_SocketAddress_2(
    JNIEnv* env, jobject thiz, jobject fdObj, jobject peer) {
  return Java_libcore_io_Linux_accept(env, thiz, fdObj, peer);
}

/* ===== getsockname / getpeername ===== */
static jobject get_name(JNIEnv* env, jobject fdObj, int peer) {
  ensure_wsa();
  SOCKET s = socket_from_fd(fd_to_int(env, fdObj));
  if (s == INVALID_SOCKET) { throw_errno(env, peer ? "getpeername" : "getsockname", A_EBADF); return NULL; }
  struct sockaddr_storage ss; int len = sizeof(ss);
  int rc = peer ? getpeername(s, (struct sockaddr*)&ss, &len)
                : getsockname(s, (struct sockaddr*)&ss, &len);
  if (rc != 0) { throw_errno(env, peer ? "getpeername" : "getsockname", map_wsa_to_android(WSAGetLastError())); return NULL; }
  return sockaddr_to_inet_socket_address(env, &ss);
}
__declspec(dllexport) jobject Java_libcore_io_Linux_getsockname(JNIEnv* env, jobject thiz, jobject fdObj) {
  (void)thiz; return get_name(env, fdObj, 0);
}
__declspec(dllexport) jobject Java_libcore_io_Linux_getsockname__Ljava_io_FileDescriptor_2(JNIEnv* env, jobject thiz, jobject fdObj) {
  return Java_libcore_io_Linux_getsockname(env, thiz, fdObj);
}
__declspec(dllexport) jobject Java_libcore_io_Linux_getpeername(JNIEnv* env, jobject thiz, jobject fdObj) {
  (void)thiz; return get_name(env, fdObj, 1);
}
__declspec(dllexport) jobject Java_libcore_io_Linux_getpeername__Ljava_io_FileDescriptor_2(JNIEnv* env, jobject thiz, jobject fdObj) {
  return Java_libcore_io_Linux_getpeername(env, thiz, fdObj);
}

/* ===== fcntl for nonblocking ===== */
__declspec(dllexport) jint Java_libcore_io_Linux_fcntlVoid(JNIEnv* env, jobject thiz, jobject fdObj, jint cmd) {
  (void)thiz;
  ensure_wsa();
  SOCKET s = socket_from_fd(fd_to_int(env, fdObj));
  if (s == INVALID_SOCKET) { throw_errno(env, "fcntl", A_EBADF); return -1; }
  if (cmd == A_F_GETFL) {
    u_long mode = 0;
    /* No portable get; track not available — return 0 (blocking) */
    (void)mode;
    return 0;
  }
  return 0;
}
__declspec(dllexport) jint Java_libcore_io_Linux_fcntlVoid__Ljava_io_FileDescriptor_2I(JNIEnv* env, jobject thiz, jobject fdObj, jint cmd) {
  return Java_libcore_io_Linux_fcntlVoid(env, thiz, fdObj, cmd);
}
__declspec(dllexport) jint Java_libcore_io_Linux_fcntlInt(JNIEnv* env, jobject thiz, jobject fdObj, jint cmd, jint arg) {
  (void)thiz;
  ensure_wsa();
  SOCKET s = socket_from_fd(fd_to_int(env, fdObj));
  if (s == INVALID_SOCKET) { throw_errno(env, "fcntl", A_EBADF); return -1; }
  if (cmd == A_F_SETFL) {
    u_long nonblock = (arg & A_O_NONBLOCK) ? 1 : 0;
    if (ioctlsocket(s, FIONBIO, &nonblock) != 0) {
      throw_errno(env, "fcntl", map_wsa_to_android(WSAGetLastError()));
      return -1;
    }
    return 0;
  }
  return 0;
}
__declspec(dllexport) jint Java_libcore_io_Linux_fcntlInt__Ljava_io_FileDescriptor_2II(JNIEnv* env, jobject thiz, jobject fdObj, jint cmd, jint arg) {
  return Java_libcore_io_Linux_fcntlInt(env, thiz, fdObj, cmd, arg);
}

/* ===== setsockoptInt / getsockoptInt (subset) ===== */
__declspec(dllexport) void Java_libcore_io_Linux_setsockoptInt(JNIEnv* env, jobject thiz, jobject fdObj, jint level, jint option, jint value) {
  (void)thiz;
  ensure_wsa();
  SOCKET s = socket_from_fd(fd_to_int(env, fdObj));
  if (s == INVALID_SOCKET) { throw_errno(env, "setsockopt", A_EBADF); return; }
  int wlevel = level, wopt = option, v = value;
  if (level == A_SOL_SOCKET) {
    wlevel = SOL_SOCKET;
    if (option == A_SO_REUSEADDR) wopt = SO_REUSEADDR;
  } else if (level == 41 /* IPPROTO_IPV6 android */) {
    wlevel = IPPROTO_IPV6;
    if (option == A_IPV6_V6ONLY) wopt = IPV6_V6ONLY;
  }
  if (setsockopt(s, wlevel, wopt, (const char*)&v, sizeof(v)) != 0) {
    int werr = WSAGetLastError();
    if (werr != WSAENOPROTOOPT) throw_errno(env, "setsockopt", map_wsa_to_android(werr));
  }
}
__declspec(dllexport) void Java_libcore_io_Linux_setsockoptInt__Ljava_io_FileDescriptor_2III(
    JNIEnv* env, jobject thiz, jobject fdObj, jint level, jint option, jint value) {
  Java_libcore_io_Linux_setsockoptInt(env, thiz, fdObj, level, option, value);
}
__declspec(dllexport) jint Java_libcore_io_Linux_getsockoptInt(JNIEnv* env, jobject thiz, jobject fdObj, jint level, jint option) {
  (void)thiz;
  ensure_wsa();
  SOCKET s = socket_from_fd(fd_to_int(env, fdObj));
  if (s == INVALID_SOCKET) { throw_errno(env, "getsockopt", A_EBADF); return -1; }
  /* Linux SO_DOMAIN / SO_PROTOCOL are not on Winsock; synthesize via protocol info. */
  if (level == A_SOL_SOCKET && (option == A_SO_DOMAIN || option == 39 || option == A_SO_PROTOCOL || option == 38)) {
    WSAPROTOCOL_INFOW info; int ilen = sizeof(info);
    if (getsockopt(s, SOL_SOCKET, SO_PROTOCOL_INFOW, (char*)&info, &ilen) != 0) {
      throw_errno(env, "getsockopt", map_wsa_to_android(WSAGetLastError()));
      return -1;
    }
    if (option == A_SO_DOMAIN || option == 39) {
      if (info.iAddressFamily == AF_INET) return A_AF_INET;
      if (info.iAddressFamily == AF_INET6) return A_AF_INET6;
      if (info.iAddressFamily == AF_UNIX) return A_AF_UNIX;
      return info.iAddressFamily;
    }
    /* SO_PROTOCOL */
    return info.iProtocol;
  }
  int wlevel = level, wopt = option, v = 0; int len = sizeof(v);
  if (level == A_SOL_SOCKET) {
    wlevel = SOL_SOCKET;
    if (option == A_SO_REUSEADDR) wopt = SO_REUSEADDR;
    if (option == A_SO_ERROR) wopt = SO_ERROR;
  }
  if (getsockopt(s, wlevel, wopt, (char*)&v, &len) != 0) {
    int werr = WSAGetLastError();
    /* ignore unsupported options softly with 0 for bootstrap */
    if (werr == WSAENOPROTOOPT) return 0;
    throw_errno(env, "getsockopt", map_wsa_to_android(werr));
    return -1;
  }
  return v;
}
__declspec(dllexport) jint Java_libcore_io_Linux_getsockoptInt__Ljava_io_FileDescriptor_2II(
    JNIEnv* env, jobject thiz, jobject fdObj, jint level, jint option) {
  return Java_libcore_io_Linux_getsockoptInt(env, thiz, fdObj, level, option);
}


/* ===== SO_LINGER (StructLinger) — required by BlockGuardOs.isLingerSocket on close ===== */
static jclass g_linger_class;
static jmethodID g_linger_ctor;
static jfieldID g_linger_onoff;
static jfieldID g_linger_linger;

static void ensure_linger(JNIEnv* env) {
  if (g_linger_class) return;
  jclass c = (*env)->FindClass(env, "android/system/StructLinger");
  if (!c) return;
  g_linger_class = (jclass)(*env)->NewGlobalRef(env, c);
  g_linger_ctor = (*env)->GetMethodID(env, g_linger_class, "<init>", "(II)V");
  g_linger_onoff = (*env)->GetFieldID(env, g_linger_class, "l_onoff", "I");
  g_linger_linger = (*env)->GetFieldID(env, g_linger_class, "l_linger", "I");
}

__declspec(dllexport) jobject Java_libcore_io_Linux_getsockoptLinger(
    JNIEnv* env, jobject thiz, jobject fdObj, jint level, jint option) {
  (void)thiz; (void)level; (void)option;
  ensure_wsa();
  ensure_linger(env);
  SOCKET s = socket_from_fd(fd_to_int(env, fdObj));
  if (s == INVALID_SOCKET) {
    throw_errno(env, "getsockopt", A_EBADF);
    return NULL;
  }
  struct linger l;
  memset(&l, 0, sizeof(l));
  int len = (int)sizeof(l);
  if (getsockopt(s, SOL_SOCKET, SO_LINGER, (char*)&l, &len) != 0) {
    int werr = WSAGetLastError();
    if (werr == WSAENOPROTOOPT) {
      /* soft default: linger off */
      l.l_onoff = 0;
      l.l_linger = 0;
    } else {
      throw_errno(env, "getsockopt", map_wsa_to_android(werr));
      return NULL;
    }
  }
  if (!g_linger_class || !g_linger_ctor) {
    throw_errno(env, "getsockopt", A_EINVAL);
    return NULL;
  }
  return (*env)->NewObject(env, g_linger_class, g_linger_ctor, (jint)l.l_onoff, (jint)l.l_linger);
}
__declspec(dllexport) jobject Java_libcore_io_Linux_getsockoptLinger__Ljava_io_FileDescriptor_2II(
    JNIEnv* env, jobject thiz, jobject fdObj, jint level, jint option) {
  return Java_libcore_io_Linux_getsockoptLinger(env, thiz, fdObj, level, option);
}

__declspec(dllexport) void Java_libcore_io_Linux_setsockoptLinger(
    JNIEnv* env, jobject thiz, jobject fdObj, jint level, jint option, jobject javaLinger) {
  (void)thiz; (void)level; (void)option;
  ensure_wsa();
  ensure_linger(env);
  if (!javaLinger) {
    jclass npe = (*env)->FindClass(env, "java/lang/NullPointerException");
    if (npe) (*env)->ThrowNew(env, npe, "null StructLinger");
    return;
  }
  SOCKET s = socket_from_fd(fd_to_int(env, fdObj));
  if (s == INVALID_SOCKET) {
    throw_errno(env, "setsockopt", A_EBADF);
    return;
  }
  struct linger l;
  memset(&l, 0, sizeof(l));
  if (g_linger_onoff && g_linger_linger) {
    l.l_onoff = (*env)->GetIntField(env, javaLinger, g_linger_onoff);
    l.l_linger = (*env)->GetIntField(env, javaLinger, g_linger_linger);
  }
  if (setsockopt(s, SOL_SOCKET, SO_LINGER, (const char*)&l, (int)sizeof(l)) != 0) {
    int werr = WSAGetLastError();
    if (werr != WSAENOPROTOOPT) throw_errno(env, "setsockopt", map_wsa_to_android(werr));
  }
}
__declspec(dllexport) void Java_libcore_io_Linux_setsockoptLinger__Ljava_io_FileDescriptor_2IILandroid_system_StructLinger_2(
    JNIEnv* env, jobject thiz, jobject fdObj, jint level, jint option, jobject javaLinger) {
  Java_libcore_io_Linux_setsockoptLinger(env, thiz, fdObj, level, option, javaLinger);
}



/* Prefer select() over WSAPoll: real Win10 has produced WSAEINVAL from WSAPoll
 * on CRT-associated socket handles that still work for bind/listen/accept. */
static int socket_select_wait(SOCKET s, int want_read, int want_write, int timeout_ms) {
  if (s == INVALID_SOCKET || s == (SOCKET)(~0)) return SOCKET_ERROR;
  fd_set rfds, wfds, efds;
  FD_ZERO(&rfds); FD_ZERO(&wfds); FD_ZERO(&efds);
  if (want_read) FD_SET(s, &rfds);
  if (want_write) FD_SET(s, &wfds);
  FD_SET(s, &efds);
  struct timeval tv;
  struct timeval* ptv = NULL;
  if (timeout_ms >= 0) {
    tv.tv_sec = timeout_ms / 1000;
    tv.tv_usec = (timeout_ms % 1000) * 1000;
    ptv = &tv;
  }
  /* Windows select: nfds is ignored for sockets. */
  return select(0, want_read ? &rfds : NULL, want_write ? &wfds : NULL, &efds, ptv);
}

/* ===== poll ===== */
__declspec(dllexport) jint Java_libcore_io_Linux_poll(JNIEnv* env, jobject thiz, jobjectArray pollFds, jint timeoutMs) {
  (void)thiz;
  ensure_wsa();
  if (!pollFds) return 0;
  jsize n = (*env)->GetArrayLength(env, pollFds);
  if (n <= 0) return 0;

  SOCKET* socks = (SOCKET*)calloc((size_t)n, sizeof(SOCKET));
  short* events_arr = (short*)calloc((size_t)n, sizeof(short));
  if (!socks || !events_arr) {
    free(socks); free(events_arr);
    throw_errno(env, "poll", A_EINVAL);
    return -1;
  }

  jclass pclass = NULL;
  jfieldID fdF = NULL, eventsF = NULL, reventsF = NULL;
  fd_set rfds, wfds, efds;
  FD_ZERO(&rfds); FD_ZERO(&wfds); FD_ZERO(&efds);
  int any = 0;

  for (jsize i = 0; i < n; i++) {
    socks[i] = INVALID_SOCKET;
    events_arr[i] = 0;
    jobject p = (*env)->GetObjectArrayElement(env, pollFds, i);
    if (!p) continue;
    if (!pclass) {
      pclass = (*env)->GetObjectClass(env, p);
      fdF = (*env)->GetFieldID(env, pclass, "fd", "Ljava/io/FileDescriptor;");
      eventsF = (*env)->GetFieldID(env, pclass, "events", "S");
      reventsF = (*env)->GetFieldID(env, pclass, "revents", "S");
      if (!fdF || !eventsF || !reventsF) {
        free(socks); free(events_arr);
        throw_errno(env, "poll", A_EINVAL);
        return -1;
      }
    }
    jobject fdObj = (*env)->GetObjectField(env, p, fdF);
    short events = (*env)->GetShortField(env, p, eventsF);
    SOCKET s = socket_from_fd(fd_to_int(env, fdObj));
    if (s == INVALID_SOCKET || s == (SOCKET)(~0)) {
      /* mark invalid entry with POLLNVAL-like error on revents later */
      socks[i] = INVALID_SOCKET;
      events_arr[i] = events;
      continue;
    }
    socks[i] = s;
    events_arr[i] = events;
    if (events & A_POLLIN) FD_SET(s, &rfds);
    if (events & A_POLLOUT) FD_SET(s, &wfds);
    FD_SET(s, &efds);
    any = 1;
  }

  if (!any) {
    free(socks); free(events_arr);
    return 0;
  }

  struct timeval tv;
  struct timeval* ptv = NULL;
  if (timeoutMs >= 0) {
    tv.tv_sec = timeoutMs / 1000;
    tv.tv_usec = (timeoutMs % 1000) * 1000;
    ptv = &tv;
  }

  int rc = select(0, &rfds, &wfds, &efds, ptv);
  if (rc == SOCKET_ERROR) {
    int err = map_wsa_to_android(WSAGetLastError());
    free(socks); free(events_arr);
    throw_errno(env, "poll", err);
    return -1;
  }

  int ready = 0;
  for (jsize i = 0; i < n; i++) {
    jobject p = (*env)->GetObjectArrayElement(env, pollFds, i);
    if (!p || !reventsF) continue;
    short rev = 0;
    SOCKET s = socks[i];
    if (s == INVALID_SOCKET || s == (SOCKET)(~0)) {
      rev = A_POLLERR; /* invalid fd */
    } else {
      short events = events_arr[i];
      if ((events & A_POLLIN) && FD_ISSET(s, &rfds)) rev |= A_POLLIN;
      if ((events & A_POLLOUT) && FD_ISSET(s, &wfds)) rev |= A_POLLOUT;
      if (FD_ISSET(s, &efds)) rev |= A_POLLERR;
    }
    (*env)->SetShortField(env, p, reventsF, rev);
    if (rev) ready++;
  }
  free(socks);
  free(events_arr);
  /* Android poll returns number of fds with nonzero revents; select returns same idea. */
  return (timeoutMs >= 0 && rc == 0) ? 0 : ready;
}
__declspec(dllexport) jint Java_libcore_io_Linux_poll___3Landroid_system_StructPollfd_2I(
    JNIEnv* env, jobject thiz, jobjectArray pollFds, jint timeoutMs) {
  return Java_libcore_io_Linux_poll(env, thiz, pollFds, timeoutMs);
}

/* ===== shutdown / socketpair soft-fail ===== */
__declspec(dllexport) void Java_libcore_io_Linux_shutdown(JNIEnv* env, jobject thiz, jobject fdObj, jint how) {
  (void)thiz;
  ensure_wsa();
  SOCKET s = socket_from_fd(fd_to_int(env, fdObj));
  if (s == INVALID_SOCKET) { throw_errno(env, "shutdown", A_EBADF); return; }
  int wh = SD_BOTH;
  if (how == 0) wh = SD_RECEIVE;
  else if (how == 1) wh = SD_SEND;
  if (shutdown(s, wh) != 0) throw_errno(env, "shutdown", map_wsa_to_android(WSAGetLastError()));
}
__declspec(dllexport) void Java_libcore_io_Linux_shutdown__Ljava_io_FileDescriptor_2I(JNIEnv* env, jobject thiz, jobject fdObj, jint how) {
  Java_libcore_io_Linux_shutdown(env, thiz, fdObj, how);
}

/* socketpair: AF_UNIX not available; implement connected TCP loopback pair for marker FD path. */
__declspec(dllexport) void Java_libcore_io_Linux_socketpair(JNIEnv* env, jobject thiz, jint domain, jint type, jint protocol, jobject fd1Obj, jobject fd2Obj) {
  (void)thiz; (void)domain; (void)type; (void)protocol;
  ensure_wsa();
  ensure_fd(env);
  SOCKET listener = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
  if (listener == INVALID_SOCKET) { throw_errno(env, "socketpair", map_wsa_to_android(WSAGetLastError())); return; }
  struct sockaddr_in addr; memset(&addr, 0, sizeof(addr));
  addr.sin_family = AF_INET;
  addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  addr.sin_port = 0;
  if (bind(listener, (struct sockaddr*)&addr, sizeof(addr)) != 0 || listen(listener, 1) != 0) {
    int e = map_wsa_to_android(WSAGetLastError());
    closesocket(listener);
    throw_errno(env, "socketpair", e);
    return;
  }
  int alen = sizeof(addr);
  if (getsockname(listener, (struct sockaddr*)&addr, &alen) != 0) {
    int e = map_wsa_to_android(WSAGetLastError());
    closesocket(listener);
    throw_errno(env, "socketpair", e);
    return;
  }
  SOCKET c = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
  if (c == INVALID_SOCKET) {
    int e = map_wsa_to_android(WSAGetLastError());
    closesocket(listener);
    throw_errno(env, "socketpair", e);
    return;
  }
  /* nonblocking connect */
  u_long nb = 1; ioctlsocket(c, FIONBIO, &nb);
  connect(c, (struct sockaddr*)&addr, sizeof(addr));
  SOCKET a = accept(listener, NULL, NULL);
  closesocket(listener);
  if (a == INVALID_SOCKET) {
    int e = map_wsa_to_android(WSAGetLastError());
    closesocket(c);
    throw_errno(env, "socketpair", e);
    return;
  }
  nb = 0; ioctlsocket(c, FIONBIO, &nb);
  int f1 = _open_osfhandle((intptr_t)c, _O_RDWR | _O_BINARY);
  int f2 = _open_osfhandle((intptr_t)a, _O_RDWR | _O_BINARY);
  if (f1 < 0 || f2 < 0) {
    if (f1 >= 0) _close(f1); else closesocket(c);
    if (f2 >= 0) _close(f2); else closesocket(a);
    throw_errno(env, "socketpair", A_EINVAL);
    return;
  }
  if (g_fd_descriptor) {
    (*env)->SetIntField(env, fd1Obj, g_fd_descriptor, f1);
    (*env)->SetIntField(env, fd2Obj, g_fd_descriptor, f2);
  }
}
__declspec(dllexport) void Java_libcore_io_Linux_socketpair__IIILjava_io_FileDescriptor_2Ljava_io_FileDescriptor_2(
    JNIEnv* env, jobject thiz, jint domain, jint type, jint protocol, jobject fd1, jobject fd2) {
  Java_libcore_io_Linux_socketpair(env, thiz, domain, type, protocol, fd1, fd2);
}

/* ioctl FIONREAD for available() */
__declspec(dllexport) jint Java_libcore_io_Linux_ioctlInt(JNIEnv* env, jobject thiz, jobject fdObj, jint cmd) {
  (void)thiz;
  ensure_wsa();
  SOCKET s = socket_from_fd(fd_to_int(env, fdObj));
  if (s == INVALID_SOCKET) { throw_errno(env, "ioctl", A_EBADF); return -1; }
  /* Android FIONREAD is 0x541B on Linux; IoBridge.available uses it. Accept any and use FIONREAD. */
  u_long n = 0;
  if (ioctlsocket(s, FIONREAD, &n) != 0) {
    /* not a socket? */
    return 0;
  }
  return (jint)n;
}
__declspec(dllexport) jint Java_libcore_io_Linux_ioctlInt__Ljava_io_FileDescriptor_2I(JNIEnv* env, jobject thiz, jobject fdObj, jint cmd) {
  return Java_libcore_io_Linux_ioctlInt(env, thiz, fdObj, cmd);
}

/* ===== android_getaddrinfo (numeric + basic DNS via Winsock) ===== */
static jobject bytes_to_inet_address(JNIEnv* env, const char* host, const jbyte* bytes, jsize n) {
  jclass c = (*env)->FindClass(env, "java/net/InetAddress");
  if (!c) return NULL;
  jmethodID mid = (*env)->GetStaticMethodID(env, c, "getByAddress", "(Ljava/lang/String;[B)Ljava/net/InetAddress;");
  if (!mid) {
    /* fallback without hostname */
    mid = (*env)->GetStaticMethodID(env, c, "getByAddress", "([B)Ljava/net/InetAddress;");
    if (!mid) return NULL;
    jbyteArray arr = (*env)->NewByteArray(env, n);
    (*env)->SetByteArrayRegion(env, arr, 0, n, bytes);
    return (*env)->CallStaticObjectMethod(env, c, mid, arr);
  }
  jstring jhost = host ? (*env)->NewStringUTF(env, host) : NULL;
  jbyteArray arr = (*env)->NewByteArray(env, n);
  (*env)->SetByteArrayRegion(env, arr, 0, n, bytes);
  return (*env)->CallStaticObjectMethod(env, c, mid, jhost, arr);
}

static void throw_gai(JNIEnv* env, const char* function, int error) {
  jclass c = (*env)->FindClass(env, "android/system/GaiException");
  if (!c) {
    /* fallback */
    jclass re = (*env)->FindClass(env, "java/lang/RuntimeException");
    if (re) (*env)->ThrowNew(env, re, "getaddrinfo failed");
    return;
  }
  jmethodID ctor = (*env)->GetMethodID(env, c, "<init>", "(Ljava/lang/String;I)V");
  if (!ctor) return;
  jstring fn = (*env)->NewStringUTF(env, function ? function : "android_getaddrinfo");
  jobject ex = (*env)->NewObject(env, c, ctor, fn, (jint)error);
  if (ex) (*env)->Throw(env, (jthrowable)ex);
}

__declspec(dllexport) jobjectArray Java_libcore_io_Linux_android_1getaddrinfo(
    JNIEnv* env, jobject thiz, jstring jnode, jobject jhints, jint netId) {
  (void)thiz; (void)netId;
  ensure_wsa();
  if (!jnode) return NULL;
  const char* node = (*env)->GetStringUTFChars(env, jnode, 0);
  if (!node) return NULL;

  struct addrinfo hints; memset(&hints, 0, sizeof(hints));
  if (jhints) {
    jclass hc = (*env)->GetObjectClass(env, jhints);
    jfieldID flagsF = (*env)->GetFieldID(env, hc, "ai_flags", "I");
    jfieldID familyF = (*env)->GetFieldID(env, hc, "ai_family", "I");
    jfieldID sockF = (*env)->GetFieldID(env, hc, "ai_socktype", "I");
    jfieldID protoF = (*env)->GetFieldID(env, hc, "ai_protocol", "I");
    int aflags = flagsF ? (*env)->GetIntField(env, jhints, flagsF) : 0;
    int afamily = familyF ? (*env)->GetIntField(env, jhints, familyF) : 0;
    int asock = sockF ? (*env)->GetIntField(env, jhints, sockF) : 0;
    int aproto = protoF ? (*env)->GetIntField(env, jhints, protoF) : 0;
    /* AI_NUMERICHOST on Android is typically 0x4 */
    if (aflags & 0x4) hints.ai_flags |= AI_NUMERICHOST;
    if (aflags & 0x1) hints.ai_flags |= AI_PASSIVE;
    if (aflags & 0x20) hints.ai_flags |= AI_ADDRCONFIG;
    hints.ai_family = map_domain(afamily);
    if (afamily == 0) hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = map_type(asock);
    hints.ai_protocol = aproto;
  }

  struct addrinfo* res = NULL;
  int rc = getaddrinfo(node, NULL, &hints, &res);
  if (rc != 0) {
    (*env)->ReleaseStringUTFChars(env, jnode, node);
    throw_gai(env, "android_getaddrinfo", rc);
    return NULL;
  }

  int count = 0;
  for (struct addrinfo* ai = res; ai; ai = ai->ai_next) {
    if (ai->ai_family == AF_INET || ai->ai_family == AF_INET6) count++;
  }
  if (count == 0) {
    freeaddrinfo(res);
    (*env)->ReleaseStringUTFChars(env, jnode, node);
    return NULL;
  }
  jclass inetCls = (*env)->FindClass(env, "java/net/InetAddress");
  jobjectArray out = (*env)->NewObjectArray(env, count, inetCls, NULL);
  int idx = 0;
  for (struct addrinfo* ai = res; ai; ai = ai->ai_next) {
    jbyte bytes[16]; jsize n = 0;
    if (ai->ai_family == AF_INET) {
      struct sockaddr_in* in = (struct sockaddr_in*)ai->ai_addr;
      memcpy(bytes, &in->sin_addr, 4); n = 4;
    } else if (ai->ai_family == AF_INET6) {
      struct sockaddr_in6* in6 = (struct sockaddr_in6*)ai->ai_addr;
      memcpy(bytes, &in6->sin6_addr, 16); n = 16;
    } else continue;
    jobject ia = bytes_to_inet_address(env, node, bytes, n);
    if ((*env)->ExceptionCheck(env)) {
      freeaddrinfo(res);
      (*env)->ReleaseStringUTFChars(env, jnode, node);
      return NULL;
    }
    (*env)->SetObjectArrayElement(env, out, idx++, ia);
  }
  freeaddrinfo(res);
  (*env)->ReleaseStringUTFChars(env, jnode, node);
  return out;
}

/* ART mangling variants */
__declspec(dllexport) jobjectArray Java_libcore_io_Linux_android_getaddrinfo(
    JNIEnv* env, jobject thiz, jstring jnode, jobject jhints, jint netId) {
  return Java_libcore_io_Linux_android_1getaddrinfo(env, thiz, jnode, jhints, netId);
}
__declspec(dllexport) jobjectArray Java_libcore_io_Linux_android_getaddrinfo__Ljava_lang_String_2Landroid_system_StructAddrinfo_2I(
    JNIEnv* env, jobject thiz, jstring jnode, jobject jhints, jint netId) {
  return Java_libcore_io_Linux_android_1getaddrinfo(env, thiz, jnode, jhints, netId);
}

/* dup2: used by deferred socket close to replace live fd with marker fd. */
__declspec(dllexport) jobject Java_libcore_io_Linux_dup(JNIEnv* env, jobject thiz, jobject oldFd) {
  (void)thiz;
  int ofd = fd_to_int(env, oldFd);
  if (ofd < 0) { throw_errno(env, "dup", A_EBADF); return NULL; }
  int nfd = _dup(ofd);
  if (nfd < 0) { throw_errno(env, "dup", errno ? errno : A_EINVAL); return NULL; }
  return fd_from_int(env, nfd);
}
__declspec(dllexport) jobject Java_libcore_io_Linux_dup__Ljava_io_FileDescriptor_2(JNIEnv* env, jobject thiz, jobject oldFd) {
  return Java_libcore_io_Linux_dup(env, thiz, oldFd);
}
__declspec(dllexport) jobject Java_libcore_io_Linux_dup2(JNIEnv* env, jobject thiz, jobject oldFd, jint newFd) {
  (void)thiz;
  int ofd = fd_to_int(env, oldFd);
  if (ofd < 0) { throw_errno(env, "dup2", A_EBADF); return NULL; }
  int nfd = _dup2(ofd, newFd);
  if (nfd < 0) { throw_errno(env, "dup2", errno ? errno : A_EINVAL); return NULL; }
  /* Android returns the new FileDescriptor object describing newFd */
  return fd_from_int(env, newFd);
}
__declspec(dllexport) jobject Java_libcore_io_Linux_dup2__Ljava_io_FileDescriptor_2I(JNIEnv* env, jobject thiz, jobject oldFd, jint newFd) {
  return Java_libcore_io_Linux_dup2(env, thiz, oldFd, newFd);
}

/* ===== java.net.SocketInputStream/OutputStream natives =====
 * Android Socket streams call these, not Libcore.os.read/write.
 * FD field is Android's "descriptor" (int).
 */

static int fd_obj_to_int(JNIEnv* env, jobject fdObj) {
  if (!fdObj) return -1;
  ensure_fd(env);
  return (*env)->GetIntField(env, fdObj, g_fd_descriptor);
}

static void throw_socket_ex(JNIEnv* env, const char* msg) {
  jclass c = (*env)->FindClass(env, "java/net/SocketException");
  if (c) (*env)->ThrowNew(env, c, msg ? msg : "Socket error");
}

static void throw_socket_timeout(JNIEnv* env, const char* msg) {
  jclass c = (*env)->FindClass(env, "java/net/SocketTimeoutException");
  if (c) (*env)->ThrowNew(env, c, msg ? msg : "Read timed out");
}

static SOCKET sock_from_fdobj(JNIEnv* env, jobject fdObj) {
  int fd = fd_obj_to_int(env, fdObj);
  if (fd < 0) return INVALID_SOCKET;
  SOCKET s = (SOCKET)_get_osfhandle(fd);
  return s;
}

__declspec(dllexport) jint Java_java_net_SocketInputStream_socketRead0(
    JNIEnv* env, jobject thiz, jobject fdObj, jbyteArray data, jint off, jint len, jint timeout) {
  (void)thiz;
  ensure_wsa();
  if (!fdObj || !data || len <= 0) {
    if (!fdObj) throw_socket_ex(env, "Socket closed");
    return -1;
  }
  SOCKET s = sock_from_fdobj(env, fdObj);
  if (s == INVALID_SOCKET || s == (SOCKET)-1) {
    throw_socket_ex(env, "Socket closed");
    return -1;
  }
  if (timeout > 0) {
    int pr = socket_select_wait(s, /*want_read*/1, /*want_write*/0, timeout);
    if (pr == 0) {
      throw_socket_timeout(env, "Read timed out");
      return -1;
    }
    if (pr == SOCKET_ERROR) {
      throw_socket_ex(env, "poll failed");
      return -1;
    }
  }
  /* Ensure blocking for timeout==0 path; accepted sockets already forced blocking. */
  char stackbuf[8192];
  char* buf = stackbuf;
  int buflen = len;
  if (buflen > (int)sizeof(stackbuf)) {
    buf = (char*)malloc((size_t)buflen);
    if (!buf) { buf = stackbuf; buflen = (int)sizeof(stackbuf); }
  } else {
    buflen = len;
  }
  int n = recv(s, buf, buflen, 0);
  if (n == SOCKET_ERROR) {
    int w = WSAGetLastError();
    if (buf != stackbuf) free(buf);
    if (w == WSAECONNRESET || w == WSAECONNABORTED) {
      jclass c = (*env)->FindClass(env, "sun/net/ConnectionResetException");
      if (c) (*env)->ThrowNew(env, c, "Connection reset");
      else throw_socket_ex(env, "Connection reset");
    } else if (w == WSAEWOULDBLOCK) {
      return 0; /* treat as no data; caller may loop */
    } else {
      throw_socket_ex(env, "Read failed");
    }
    return -1;
  }
  if (n > 0) {
    (*env)->SetByteArrayRegion(env, data, off, n, (jbyte*)buf);
  }
  if (buf != stackbuf) free(buf);
  return n; /* 0 => EOF for SocketInputStream */
}
__declspec(dllexport) jint Java_java_net_SocketInputStream_socketRead0__Ljava_io_FileDescriptor_2_3BIII(
    JNIEnv* env, jobject thiz, jobject fdObj, jbyteArray data, jint off, jint len, jint timeout) {
  return Java_java_net_SocketInputStream_socketRead0(env, thiz, fdObj, data, off, len, timeout);
}

__declspec(dllexport) void Java_java_net_SocketOutputStream_socketWrite0(
    JNIEnv* env, jobject thiz, jobject fdObj, jbyteArray data, jint off, jint len) {
  (void)thiz;
  ensure_wsa();
  if (!fdObj || !data) {
    throw_socket_ex(env, "Socket closed");
    return;
  }
  if (len <= 0) return;
  SOCKET s = sock_from_fdobj(env, fdObj);
  if (s == INVALID_SOCKET || s == (SOCKET)-1) {
    throw_socket_ex(env, "Socket closed");
    return;
  }
  char stackbuf[8192];
  int remaining = len;
  int pos = off;
  while (remaining > 0) {
    int chunk = remaining > (int)sizeof(stackbuf) ? (int)sizeof(stackbuf) : remaining;
    (*env)->GetByteArrayRegion(env, data, pos, chunk, (jbyte*)stackbuf);
    int sent_total = 0;
    while (sent_total < chunk) {
      int n = send(s, stackbuf + sent_total, chunk - sent_total, 0);
      if (n == SOCKET_ERROR) {
        int w = WSAGetLastError();
        if (w == WSAEWOULDBLOCK) {
          /* spin briefly / wait for writability */
          if (socket_select_wait(s, /*want_read*/0, /*want_write*/1, 1000) <= 0) {
            throw_socket_ex(env, "Write failed");
            return;
          }
          continue;
        }
        if (w == WSAECONNRESET || w == WSAECONNABORTED) {
          jclass c = (*env)->FindClass(env, "sun/net/ConnectionResetException");
          if (c) (*env)->ThrowNew(env, c, "Connection reset");
          else throw_socket_ex(env, "Connection reset");
        } else {
          throw_socket_ex(env, "Write failed");
        }
        return;
      }
      if (n == 0) {
        throw_socket_ex(env, "Write failed");
        return;
      }
      sent_total += n;
    }
    remaining -= chunk;
    pos += chunk;
  }
}
__declspec(dllexport) void Java_java_net_SocketOutputStream_socketWrite0__Ljava_io_FileDescriptor_2_3BII(
    JNIEnv* env, jobject thiz, jobject fdObj, jbyteArray data, jint off, jint len) {
  Java_java_net_SocketOutputStream_socketWrite0(env, thiz, fdObj, data, off, len);
}
