#include <errno.h>
#include <fcntl.h>
#include <io.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/stat.h>

#include <winsock2.h>
#include <windows.h>

#include "mdvm_socket_fd_registry.h"

static void fail(const char* message) {
  fprintf(stderr, "W013_SOCKET_FD_REGISTRY_FAIL %s errno=%d wsa=%d\n",
          message, errno, WSAGetLastError());
  exit(1);
}

static int adopt_socket(SOCKET socket) {
  int fd = _open_osfhandle((intptr_t)socket, _O_RDWR | _O_BINARY);
  if (fd < 0) {
    closesocket(socket);
    fail("_open_osfhandle");
  }
  if (mdvm_socket_fd_register(fd) != 0) {
    mdvm_socket_fd_close(fd);
    fail("register");
  }
  return fd;
}

static int open_temp_file(const char* path) {
  int fd = _open(path, _O_CREAT | _O_TRUNC | _O_RDWR | _O_BINARY,
                 _S_IREAD | _S_IWRITE);
  if (fd < 0) fail("open temp file");
  if (mdvm_socket_fd_is_socket(fd)) fail("regular file classified as socket");
  return fd;
}

int main(void) {
  WSADATA wsa;
  if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) fail("WSAStartup");

  char temp_dir[MAX_PATH];
  char temp_path[MAX_PATH];
  if (GetTempPathA(MAX_PATH, temp_dir) == 0 ||
      GetTempFileNameA(temp_dir, "w13", 0, temp_path) == 0) {
    fail("temporary path");
  }

  int filefd = open_temp_file(temp_path);
  SOCKET socket1 = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
  if (socket1 == INVALID_SOCKET) fail("socket1");
  int socketfd = adopt_socket(socket1);
  if (!mdvm_socket_fd_is_socket(socketfd)) fail("socket not registered");

  int dupfd = mdvm_socket_fd_dup(socketfd);
  if (dupfd < 0 || !mdvm_socket_fd_is_socket(dupfd)) fail("socket dup");

  if (mdvm_socket_fd_dup2(socketfd, filefd) < 0 ||
      !mdvm_socket_fd_is_socket(filefd)) {
    fail("socket dup2 onto file");
  }
  if (mdvm_socket_fd_close(filefd) != 0 || mdvm_socket_fd_is_socket(filefd)) {
    fail("socket close unregister");
  }

  int reused = open_temp_file(temp_path);
  if (reused != filefd) {
    fprintf(stderr, "W013_SOCKET_FD_REGISTRY_NOTE expected_reuse=%d actual=%d\n",
            filefd, reused);
  }
  if (mdvm_socket_fd_is_socket(reused)) fail("reused file fd stale");

  SOCKET socket2 = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
  if (socket2 == INVALID_SOCKET) fail("socket2");
  int target = adopt_socket(socket2);
  if (mdvm_socket_fd_dup2(reused, target) < 0 ||
      mdvm_socket_fd_is_socket(target)) {
    fail("file dup2 did not clear socket target");
  }

  if (mdvm_socket_fd_close(target) != 0 ||
      mdvm_socket_fd_close(reused) != 0 ||
      mdvm_socket_fd_close(dupfd) != 0 ||
      mdvm_socket_fd_close(socketfd) != 0) {
    fail("cleanup close");
  }
  DeleteFileA(temp_path);
  WSACleanup();
  printf("W013_SOCKET_FD_REGISTRY_PASS socket=%d dup=%d reused=%d target=%d\n",
         socketfd, dupfd, reused, target);
  return 0;
}
