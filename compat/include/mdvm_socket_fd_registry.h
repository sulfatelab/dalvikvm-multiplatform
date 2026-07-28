/* Explicit socket ownership for Windows x64 CRT file descriptors.
 *
 * Winsock SOCKET values and Win32 HANDLE values occupy independent namespaces.
 * A regular CRT fd's _get_osfhandle() value can therefore be numerically equal
 * to a live SOCKET.  Callers must use this registry instead of probing the
 * returned value with a Winsock API.
 */
#pragma once

#if defined(_WIN32) && defined(MDVM_SOCKET_FD_REGISTRY_EXPORTS)
#define MDVM_SOCKET_FD_REGISTRY_API __declspec(dllexport)
#else
#define MDVM_SOCKET_FD_REGISTRY_API
#endif

#ifdef __cplusplus
extern "C" {
#endif

MDVM_SOCKET_FD_REGISTRY_API int mdvm_socket_fd_register(int fd);
MDVM_SOCKET_FD_REGISTRY_API void mdvm_socket_fd_unregister(int fd);
MDVM_SOCKET_FD_REGISTRY_API int mdvm_socket_fd_is_socket(int fd);

/* Registry-aware CRT operations.  These work for both sockets and files. */
MDVM_SOCKET_FD_REGISTRY_API int mdvm_socket_fd_close(int fd);
MDVM_SOCKET_FD_REGISTRY_API int mdvm_socket_fd_dup(int fd);
MDVM_SOCKET_FD_REGISTRY_API int mdvm_socket_fd_dup2(int oldfd, int newfd);

#ifdef __cplusplus
}
#endif

#undef MDVM_SOCKET_FD_REGISTRY_API

/* Opt-in remapping for upstream C translation units.  Include this only after
 * the CRT headers have declared close/dup/dup2, otherwise their dllimport
 * declarations would be rewritten as imports of these local helpers. */
#if defined(MDVM_SOCKET_FD_TRACKING) && !defined(__cplusplus)
#ifndef close
#define close mdvm_socket_fd_close
#endif
#ifndef dup
#define dup mdvm_socket_fd_dup
#endif
#ifndef dup2
#define dup2 mdvm_socket_fd_dup2
#endif
#endif
