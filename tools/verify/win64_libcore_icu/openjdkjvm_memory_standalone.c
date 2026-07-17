/* Standalone JVM_* exports for hybrid openjdk PE (no ART headers).
 * Memory helpers + POSIX/socket I/O used by ojluni natives.
 * Prefer real art openjdkjvm later (W-015).
 */
#include <jni.h>
#include <windows.h>
#include <psapi.h>
#include <math.h>
#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <io.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/types.h>

#define MDVM_SOCKET_NO_MACROS 1
#include <winsock2.h>
#include <ws2tcpip.h>
#include <sys/socket.h>
#include <unistd.h>
#include <poll.h>

#ifndef JVM_EEXIST
#define JVM_EEXIST -100
#endif

__declspec(dllexport) jlong JVM_FreeMemory(void) {
  MEMORYSTATUSEX ms;
  ms.dwLength = sizeof(ms);
  if (!GlobalMemoryStatusEx(&ms)) return 64 * 1024 * 1024;
  return (jlong)ms.ullAvailVirtual;
}

__declspec(dllexport) jlong JVM_TotalMemory(void) {
  PROCESS_MEMORY_COUNTERS pmc;
  if (GetProcessMemoryInfo(GetCurrentProcess(), &pmc, sizeof(pmc))) {
    return (jlong)pmc.WorkingSetSize;
  }
  return 128 * 1024 * 1024;
}

__declspec(dllexport) jlong JVM_MaxMemory(void) {
  MEMORYSTATUSEX ms;
  ms.dwLength = sizeof(ms);
  if (!GlobalMemoryStatusEx(&ms)) return 512 * 1024 * 1024;
  return (jlong)ms.ullTotalVirtual;
}

__declspec(dllexport) void JVM_GC(void) {}

__declspec(dllexport) jint JVM_GetLastErrorString(char* buf, int len) {
  DWORD err = GetLastError();
  if (len <= 0 || buf == NULL) return 0;
  return (jint)FormatMessageA(FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS,
      NULL, err, 0, buf, (DWORD)len, NULL);
}

__declspec(dllexport) jboolean JVM_IsNaN(jdouble d) {
  return (jboolean)isnan(d);
}

__declspec(dllexport) jlong JVM_GetNanoTimeAdjustment(jlong offset_secs) {
  FILETIME ft;
  GetSystemTimeAsFileTime(&ft);
  ULARGE_INTEGER u;
  u.LowPart = ft.dwLowDateTime;
  u.HighPart = ft.dwHighDateTime;
  jlong now100 = (jlong)u.QuadPart;
  jlong now_ns = now100 * 100;
  jlong offset_ns = offset_secs * 1000000000LL;
  return now_ns - offset_ns;
}

__declspec(dllexport) jlong JVM_CurrentTimeMillis(JNIEnv* env, jclass cls) {
  (void)env; (void)cls;
  FILETIME ft;
  GetSystemTimeAsFileTime(&ft);
  ULARGE_INTEGER u;
  u.LowPart = ft.dwLowDateTime;
  u.HighPart = ft.dwHighDateTime;
  /* 100ns since 1601 -> ms since 1970 */
  const jlong EPOCH_DIFF_100NS = 116444736000000000LL;
  return (jlong)((u.QuadPart - (ULONGLONG)EPOCH_DIFF_100NS) / 10000ULL);
}

__declspec(dllexport) jlong JVM_NanoTime(JNIEnv* env, jclass cls) {
  (void)env; (void)cls;
  static LARGE_INTEGER freq;
  static int init = 0;
  if (!init) { QueryPerformanceFrequency(&freq); init = 1; }
  LARGE_INTEGER c; QueryPerformanceCounter(&c);
  return (jlong)((c.QuadPart * 1000000000LL) / freq.QuadPart);
}

__declspec(dllexport) char* JVM_NativePath(char* path) { return path; }

__declspec(dllexport) jint JVM_Open(const char* fname, jint flags, jint mode) {
  int fd = _open(fname, flags | _O_BINARY, mode);
  if (fd < 0) {
    if (errno == EEXIST) return JVM_EEXIST;
    return -1;
  }
  return fd;
}

__declspec(dllexport) jint JVM_Close(jint fd) { return _close(fd); }

__declspec(dllexport) jint JVM_Read(jint fd, char* buf, jint nbytes) {
  SOCKET s = (SOCKET)_get_osfhandle(fd);
  if (s != INVALID_SOCKET && s != (SOCKET)-1) {
    int n = recv(s, buf, nbytes, 0);
    if (n != SOCKET_ERROR) return n;
  }
  return _read(fd, buf, (unsigned)nbytes);
}

__declspec(dllexport) jint JVM_Write(jint fd, char* buf, jint nbytes) {
  SOCKET s = (SOCKET)_get_osfhandle(fd);
  if (s != INVALID_SOCKET && s != (SOCKET)-1) {
    int n = send(s, buf, nbytes, 0);
    if (n != SOCKET_ERROR) return n;
  }
  return _write(fd, buf, (unsigned)nbytes);
}

__declspec(dllexport) jlong JVM_Lseek(jint fd, jlong offset, jint whence) {
  return _lseeki64(fd, offset, whence);
}

__declspec(dllexport) jint JVM_SetLength(jint fd, jlong length) {
  return _chsize_s(fd, length) == 0 ? 0 : -1;
}

__declspec(dllexport) jint JVM_Sync(jint fd) { return _commit(fd); }

__declspec(dllexport) jint JVM_InitializeSocketLibrary(void) {
  WSADATA wsa;
  return WSAStartup(MAKEWORD(2, 2), &wsa) == 0 ? 0 : -1;
}

__declspec(dllexport) jint JVM_Socket(jint domain, jint type, jint protocol) {
  return mdvm_socket(domain, type, protocol);
}

__declspec(dllexport) jint JVM_SocketClose(jint fd) {
  SOCKET s = (SOCKET)_get_osfhandle(fd);
  if (s != INVALID_SOCKET && s != (SOCKET)-1) shutdown(s, SD_BOTH);
  return _close(fd);
}

__declspec(dllexport) jint JVM_SocketShutdown(jint fd, jint howto) {
  return mdvm_shutdown(fd, howto);
}

__declspec(dllexport) jint JVM_Recv(jint fd, char* buf, jint nBytes, jint flags) {
  return (jint)mdvm_recv(fd, buf, (size_t)nBytes, flags);
}

__declspec(dllexport) jint JVM_Send(jint fd, char* buf, jint nBytes, jint flags) {
  return (jint)mdvm_send(fd, buf, (size_t)nBytes, flags);
}

__declspec(dllexport) jint JVM_Timeout(int fd, long timeout) {
  struct pollfd pfd;
  pfd.fd = fd; pfd.events = POLLIN; pfd.revents = 0;
  return poll(&pfd, 1, (int)timeout);
}

__declspec(dllexport) jint JVM_Listen(jint fd, jint count) {
  return mdvm_listen(fd, count);
}

__declspec(dllexport) jint JVM_Connect(jint fd, struct sockaddr* addr, jint addrlen) {
  return mdvm_connect(fd, addr, (socklen_t)addrlen);
}

__declspec(dllexport) jint JVM_Bind(jint fd, struct sockaddr* addr, jint addrlen) {
  return mdvm_bind(fd, addr, (socklen_t)addrlen);
}

__declspec(dllexport) jint JVM_Accept(jint fd, struct sockaddr* addr, jint* addrlen) {
  socklen_t al = addrlen ? (socklen_t)*addrlen : 0;
  int n = mdvm_accept(fd, addr, addrlen ? &al : NULL);
  if (addrlen) *addrlen = (jint)al;
  return n;
}

__declspec(dllexport) jint JVM_RecvFrom(jint fd, char* buf, int nBytes,
    int flags, struct sockaddr* from, int* fromlen) {
  socklen_t fl = fromlen ? (socklen_t)*fromlen : 0;
  int n = (int)mdvm_recvfrom(fd, buf, (size_t)nBytes, flags, from, fromlen ? &fl : NULL);
  if (fromlen) *fromlen = (int)fl;
  return n;
}

__declspec(dllexport) jint JVM_SendTo(jint fd, char* buf, int len,
    int flags, struct sockaddr* to, int tolen) {
  return (jint)mdvm_sendto(fd, buf, (size_t)len, flags, to, (socklen_t)tolen);
}

__declspec(dllexport) jint JVM_SocketAvailable(jint fd, jint* result) {
  SOCKET s = (SOCKET)_get_osfhandle(fd);
  if (s == INVALID_SOCKET || s == (SOCKET)-1) return JNI_FALSE;
  u_long n = 0;
  if (ioctlsocket(s, FIONREAD, &n) == SOCKET_ERROR) return JNI_FALSE;
  if (result) *result = (jint)n;
  return JNI_TRUE;
}

__declspec(dllexport) jint JVM_GetSockName(jint fd, struct sockaddr* him, int* len) {
  socklen_t l = len ? (socklen_t)*len : 0;
  int n = mdvm_getsockname(fd, him, len ? &l : NULL);
  if (len) *len = (int)l;
  return n;
}

__declspec(dllexport) jint JVM_GetSockOpt(jint fd, int level, int optname, char* optval, int* optlen) {
  socklen_t l = optlen ? (socklen_t)*optlen : 0;
  int n = mdvm_getsockopt(fd, level, optname, optval, optlen ? &l : NULL);
  if (optlen) *optlen = (int)l;
  return n;
}

__declspec(dllexport) jint JVM_SetSockOpt(jint fd, int level, int optname, const char* optval, int optlen) {
  return mdvm_setsockopt(fd, level, optname, optval, (socklen_t)optlen);
}

__declspec(dllexport) int JVM_GetHostName(char* name, int namelen) {
  return mdvm_gethostname(name, (size_t)namelen);
}

/* Raw monitors for ZipFile etc. */
typedef CRITICAL_SECTION raw_mutex;

__declspec(dllexport) void* JVM_RawMonitorCreate(void) {
  raw_mutex* m = (raw_mutex*)malloc(sizeof(raw_mutex));
  if (m) InitializeCriticalSection(m);
  return m;
}
__declspec(dllexport) void JVM_RawMonitorDestroy(void* mon) {
  if (!mon) return;
  DeleteCriticalSection((raw_mutex*)mon);
  free(mon);
}
__declspec(dllexport) jint JVM_RawMonitorEnter(void* mon) {
  if (!mon) return -1;
  EnterCriticalSection((raw_mutex*)mon);
  return 0;
}
__declspec(dllexport) void JVM_RawMonitorExit(void* mon) {
  if (mon) LeaveCriticalSection((raw_mutex*)mon);
}

__declspec(dllexport) void* JVM_FindLibraryEntry(void* handle, const char* name) {
  return (void*)GetProcAddress((HMODULE)handle, name);
}

__declspec(dllexport) int jio_vsnprintf(char* str, size_t count, const char* fmt, va_list args) {
  if ((intptr_t)count <= 0) return -1;
  return vsnprintf(str, count, fmt, args);
}
__declspec(dllexport) int jio_snprintf(char* str, size_t count, const char* fmt, ...) {
  va_list args; va_start(args, fmt);
  int n = jio_vsnprintf(str, count, fmt, args);
  va_end(args);
  return n;
}
__declspec(dllexport) int jio_fprintf(FILE* fp, const char* fmt, ...) {
  va_list args; va_start(args, fmt);
  int n = vfprintf(fp, fmt, args);
  va_end(args);
  return n;
}
__declspec(dllexport) int jio_vfprintf(FILE* fp, const char* fmt, va_list args) {
  return vfprintf(fp, fmt, args);
}
