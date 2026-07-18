/* WinNTFileSystem + Linux open/read/write/close/stat for Win64 ART Phase 3 */
#include <jni.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <errno.h>
#include <fcntl.h>
#include <io.h>
#include <unistd.h>
#include <sys/stat.h>
#include <winsock2.h>
#include <windows.h>
#pragma comment(lib, "ws2_32.lib")
#include "win_path.h"

/* Android errno values commonly used by IoBridge (bionic-compatible). */
enum {
  EPERM_A = 1,
  ENOENT_A = 2,
  EIO_A = 5,
  EBADF_A = 9,
  EACCES_A = 13,
  EEXIST_A = 17,
  ENOTDIR_A = 20,
  EISDIR_A = 21,
  EINVAL_A = 22,
  ENOSPC_A = 28,
  EROFS_A = 30
};

static int map_errno(int e) {
  switch (e) {
    case EPERM: return EPERM_A;
    case ENOENT: return ENOENT_A;
    case EIO: return EIO_A;
    case EBADF: return EBADF_A;
    case EACCES: return EACCES_A;
    case EEXIST: return EEXIST_A;
    case ENOTDIR: return ENOTDIR_A;
    case EISDIR: return EISDIR_A;
    case EINVAL: return EINVAL_A;
    case ENOSPC: return ENOSPC_A;
    case EROFS: return EROFS_A;
    default: return e > 0 ? e : EIO_A;
  }
}

static void throw_errno(JNIEnv* env, const char* function, int err) {
  jclass c = (*env)->FindClass(env, "android/system/ErrnoException");
  if (!c) return;
  jmethodID ctor = (*env)->GetMethodID(env, c, "<init>", "(Ljava/lang/String;I)V");
  if (!ctor) return;
  jstring fn = (*env)->NewStringUTF(env, function ? function : "native");
  jobject ex = (*env)->NewObject(env, c, ctor, fn, (jint)map_errno(err));
  if (ex) (*env)->Throw(env, (jthrowable)ex);
}


enum { BA_EXISTS = 0x01, BA_REGULAR = 0x02, BA_DIRECTORY = 0x04, BA_HIDDEN = 0x08 };
enum { ACCESS_EXECUTE = 0x01, ACCESS_WRITE = 0x02, ACCESS_READ = 0x04, ACCESS_OK = 0x08 };

static jclass g_fd_class;
static jfieldID g_fd_descriptor;
static jmethodID g_fd_ctor;
static jclass g_stat_class;
static jmethodID g_stat_ctor;

static void ensure_fd(JNIEnv* env) {
  if (g_fd_class) return;
  jclass c = (*env)->FindClass(env, "java/io/FileDescriptor");
  g_fd_class = (jclass)(*env)->NewGlobalRef(env, c);
  g_fd_descriptor = (*env)->GetFieldID(env, g_fd_class, "descriptor", "I");
  /* Must run <init>: final releaseLock is required by release$ / close paths. */
  g_fd_ctor = (*env)->GetMethodID(env, g_fd_class, "<init>", "()V");
}

static jobject fd_from_int(JNIEnv* env, int fd) {
  ensure_fd(env);
  jobject o = NULL;
  if (g_fd_ctor) {
    o = (*env)->NewObject(env, g_fd_class, g_fd_ctor);
  } else {
    o = (*env)->AllocObject(env, g_fd_class);
  }
  if (o && g_fd_descriptor) (*env)->SetIntField(env, o, g_fd_descriptor, fd);
  return o;
}

static int fd_to_int(JNIEnv* env, jobject fdObj) {
  if (!fdObj) return -1;
  ensure_fd(env);
  return (*env)->GetIntField(env, fdObj, g_fd_descriptor);
}

static int is_socket_fd(int fd) {
  if (fd < 0) return 0;
  SOCKET s = (SOCKET)_get_osfhandle(fd);
  if (s == INVALID_SOCKET || s == (SOCKET)(intptr_t)-1) return 0;
  int type = 0; int len = sizeof(type);
  if (getsockopt(s, SOL_SOCKET, SO_TYPE, (char*)&type, &len) != 0) return 0;
  /* Anonymous pipes must not be treated as sockets (wine SO_TYPE quirks). */
  return (type == SOCK_STREAM || type == SOCK_DGRAM || type == SOCK_RAW) ? 1 : 0;
}

/* ===== WinNTFileSystem natives ===== */
__declspec(dllexport) jint Java_java_io_WinNTFileSystem_getBooleanAttributes0(JNIEnv* env, jclass cls, jstring jpath) {
  (void)cls;
  if (!jpath) {
    fprintf(stderr, "Win64 getBooleanAttributes0: null path\n");
    fflush(stderr);
    return 0;
  }
  jsize jlen = (*env)->GetStringUTFLength(env, jpath);
  const char* p = (*env)->GetStringUTFChars(env, jpath, 0);
  if (!p) {
    fprintf(stderr, "Win64 getBooleanAttributes0: GetStringUTFChars failed jlen=%d\n", (int)jlen);
    fflush(stderr);
    return 0;
  }
  fprintf(stderr, "Win64 getBooleanAttributes0 jlen=%d raw_first=%02x\n", (int)jlen, (unsigned char)p[0]);
  fflush(stderr);

  wchar_t* w = win_path_to_wide(p);
  DWORD attr = w ? GetFileAttributesW(w) : INVALID_FILE_ATTRIBUTES;
  jint rv = 0;
  if (attr == INVALID_FILE_ATTRIBUTES) {
    rv = 0;
  } else {
    rv = BA_EXISTS;
    if (attr & FILE_ATTRIBUTE_DIRECTORY) rv |= BA_DIRECTORY;
    else rv |= BA_REGULAR;
    if (attr & FILE_ATTRIBUTE_HIDDEN) rv |= BA_HIDDEN;
  }
  fprintf(stderr, "Win64 getBooleanAttributes0 path='%s' attr=0x%lx rv=0x%x\n",
          p, (unsigned long)attr, (unsigned)rv);
  fflush(stderr);
  (*env)->ReleaseStringUTFChars(env, jpath, p);
  free(w);
  return rv;
}

__declspec(dllexport) jboolean Java_java_io_WinNTFileSystem_checkAccess0(JNIEnv* env, jclass cls, jstring jpath, jint access) {
  (void)cls; (void)access;
  return Java_java_io_WinNTFileSystem_getBooleanAttributes0(env, cls, jpath) & BA_EXISTS ? JNI_TRUE : JNI_FALSE;
}

__declspec(dllexport) jlong Java_java_io_WinNTFileSystem_getLastModifiedTime0(JNIEnv* env, jclass cls, jstring jpath) {
  (void)cls;
  const char* p = (*env)->GetStringUTFChars(env, jpath, 0);
  wchar_t* w = win_path_to_wide(p);
  (*env)->ReleaseStringUTFChars(env, jpath, p);
  if (!w) return 0;
  WIN32_FILE_ATTRIBUTE_DATA data;
  jlong ms = 0;
  if (GetFileAttributesExW(w, GetFileExInfoStandard, &data)) {
    ULARGE_INTEGER ull;
    ull.LowPart = data.ftLastWriteTime.dwLowDateTime;
    ull.HighPart = data.ftLastWriteTime.dwHighDateTime;
    /* Windows FILETIME to Unix ms */
    ms = (jlong)((ull.QuadPart - 116444736000000000ULL) / 10000ULL);
  }
  free(w);
  return ms;
}

__declspec(dllexport) jlong Java_java_io_WinNTFileSystem_getLength0(JNIEnv* env, jclass cls, jstring jpath) {
  (void)cls;
  const char* p = (*env)->GetStringUTFChars(env, jpath, 0);
  wchar_t* w = win_path_to_wide(p);
  (*env)->ReleaseStringUTFChars(env, jpath, p);
  if (!w) return 0;
  WIN32_FILE_ATTRIBUTE_DATA data;
  jlong len = 0;
  if (GetFileAttributesExW(w, GetFileExInfoStandard, &data)) {
    ULARGE_INTEGER ull;
    ull.LowPart = data.nFileSizeLow;
    ull.HighPart = data.nFileSizeHigh;
    len = (jlong)ull.QuadPart;
  }
  free(w);
  return len;
}

__declspec(dllexport) jboolean Java_java_io_WinNTFileSystem_createFileExclusively0(JNIEnv* env, jclass cls, jstring jpath) {
  (void)cls;
  const char* p = (*env)->GetStringUTFChars(env, jpath, 0);
  wchar_t* w = win_path_to_wide(p);
  (*env)->ReleaseStringUTFChars(env, jpath, p);
  if (!w) return JNI_FALSE;
  HANDLE h = CreateFileW(w, GENERIC_WRITE, 0, NULL, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, NULL);
  free(w);
  if (h == INVALID_HANDLE_VALUE) return JNI_FALSE;
  CloseHandle(h);
  return JNI_TRUE;
}

__declspec(dllexport) jboolean Java_java_io_WinNTFileSystem_delete0(JNIEnv* env, jclass cls, jstring jpath) {
  (void)cls;
  const char* p = (*env)->GetStringUTFChars(env, jpath, 0);
  wchar_t* w = win_path_to_wide(p);
  (*env)->ReleaseStringUTFChars(env, jpath, p);
  if (!w) return JNI_FALSE;
  jboolean ok = DeleteFileW(w) || RemoveDirectoryW(w);
  free(w);
  return ok ? JNI_TRUE : JNI_FALSE;
}

__declspec(dllexport) jobjectArray Java_java_io_WinNTFileSystem_list0(JNIEnv* env, jclass cls, jstring jpath) {
  (void)cls;
  const char* p = (*env)->GetStringUTFChars(env, jpath, 0);
  char norm[4096];
  win_path_normalize(p, norm, sizeof(norm));
  (*env)->ReleaseStringUTFChars(env, jpath, p);
  char pattern[4200];
  snprintf(pattern, sizeof(pattern), "%s\\*", norm);
  wchar_t* w = win_path_to_wide(pattern);
  if (!w) return NULL;
  WIN32_FIND_DATAW fd;
  HANDLE h = FindFirstFileW(w, &fd);
  free(w);
  if (h == INVALID_HANDLE_VALUE) return NULL;
  char* names[4096];
  int n = 0;
  do {
    if (wcscmp(fd.cFileName, L".") == 0 || wcscmp(fd.cFileName, L"..") == 0) continue;
    char u8[MAX_PATH * 3];
    WideCharToMultiByte(CP_UTF8, 0, fd.cFileName, -1, u8, sizeof(u8), NULL, NULL);
    names[n] = _strdup(u8);
    if (names[n] && n < 4095) n++;
  } while (FindNextFileW(h, &fd));
  FindClose(h);
  jclass sc = (*env)->FindClass(env, "java/lang/String");
  jobjectArray arr = (*env)->NewObjectArray(env, n, sc, 0);
  for (int i = 0; i < n; i++) {
    (*env)->SetObjectArrayElement(env, arr, i, (*env)->NewStringUTF(env, names[i]));
    free(names[i]);
  }
  return arr;
}

__declspec(dllexport) jboolean Java_java_io_WinNTFileSystem_createDirectory0(JNIEnv* env, jclass cls, jstring jpath) {
  (void)cls;
  const char* p = (*env)->GetStringUTFChars(env, jpath, 0);
  wchar_t* w = win_path_to_wide(p);
  (*env)->ReleaseStringUTFChars(env, jpath, p);
  if (!w) return JNI_FALSE;
  jboolean ok = CreateDirectoryW(w, NULL) ? JNI_TRUE : JNI_FALSE;
  free(w);
  return ok;
}

__declspec(dllexport) jboolean Java_java_io_WinNTFileSystem_rename0(JNIEnv* env, jclass cls, jstring a, jstring b) {
  (void)cls;
  const char* pa = (*env)->GetStringUTFChars(env, a, 0);
  const char* pb = (*env)->GetStringUTFChars(env, b, 0);
  wchar_t* wa = win_path_to_wide(pa);
  wchar_t* wb = win_path_to_wide(pb);
  (*env)->ReleaseStringUTFChars(env, a, pa);
  (*env)->ReleaseStringUTFChars(env, b, pb);
  jboolean ok = (wa && wb && MoveFileW(wa, wb)) ? JNI_TRUE : JNI_FALSE;
  free(wa); free(wb);
  return ok;
}

__declspec(dllexport) jboolean Java_java_io_WinNTFileSystem_setLastModifiedTime0(JNIEnv* env, jclass cls, jstring jpath, jlong time) {
  (void)env; (void)cls; (void)jpath; (void)time; return JNI_FALSE;
}
__declspec(dllexport) jboolean Java_java_io_WinNTFileSystem_setReadOnly0(JNIEnv* env, jclass cls, jstring jpath) {
  (void)cls;
  const char* p = (*env)->GetStringUTFChars(env, jpath, 0);
  wchar_t* w = win_path_to_wide(p);
  (*env)->ReleaseStringUTFChars(env, jpath, p);
  if (!w) return JNI_FALSE;
  DWORD a = GetFileAttributesW(w);
  jboolean ok = JNI_FALSE;
  if (a != INVALID_FILE_ATTRIBUTES) {
    ok = SetFileAttributesW(w, a | FILE_ATTRIBUTE_READONLY) ? JNI_TRUE : JNI_FALSE;
  }
  free(w);
  return ok;
}
__declspec(dllexport) jlong Java_java_io_WinNTFileSystem_getSpace0(JNIEnv* env, jclass cls, jstring jpath, jint t) {
  (void)env; (void)cls; (void)jpath; (void)t; return 0;
}
__declspec(dllexport) jlong Java_java_io_WinNTFileSystem_getNameMax0(JNIEnv* env, jclass cls, jstring jpath) {
  (void)env; (void)cls; (void)jpath; return 255;
}


/* ===== Linux I/O ===== */
/* Android O_* roughly POSIX */
#ifndef O_BINARY
#define O_BINARY 0x8000
#endif

__declspec(dllexport) jobject Java_libcore_io_Linux_open(JNIEnv* env, jobject thiz, jstring jpath, jint flags, jint mode) {
  (void)thiz; (void)mode;
  if (!jpath) return NULL;
  const char* p = (*env)->GetStringUTFChars(env, jpath, 0);
  wchar_t* w = win_path_to_wide(p);
  (*env)->ReleaseStringUTFChars(env, jpath, p);
  if (!w) return NULL;
  int oflag = O_BINARY;
  int acc = flags & 3; /* O_ACCMODE */
  if (acc == 0) oflag |= O_RDONLY;
  else if (acc == 1) oflag |= O_WRONLY;
  else oflag |= O_RDWR;
  if (flags & 0x40) oflag |= O_CREAT; /* O_CREAT */
  if (flags & 0x80) oflag |= O_EXCL;
  if (flags & 0x200) oflag |= O_TRUNC;
  if (flags & 0x400) oflag |= O_APPEND;
  int fd = _wopen(w, oflag, _S_IREAD | _S_IWRITE);
  int err = errno;
  free(w);
  if (fd < 0) {
    throw_errno(env, "open", err ? err : ENOENT);
    return NULL;
  }
  return fd_from_int(env, fd);
}

__declspec(dllexport) void Java_libcore_io_Linux_close(JNIEnv* env, jobject thiz, jobject fdObj) {
  (void)thiz;
  int fd = fd_to_int(env, fdObj);
  if (fd >= 0) _close(fd);
}

__declspec(dllexport) jint Java_libcore_io_Linux_readBytes(JNIEnv* env, jobject thiz, jobject fdObj, jobject buffer, jint offset, jint byteCount) {
  (void)thiz;
  int fd = fd_to_int(env, fdObj);
  if (fd < 0) { throw_errno(env, "read", EBADF); return -1; }
  if (!buffer || byteCount <= 0) return 0;
  jbyte* bytes = (*env)->GetByteArrayElements(env, (jbyteArray)buffer, 0);
  if (!bytes) return 0;
  int n;
  if (is_socket_fd(fd)) {
    SOCKET s = (SOCKET)_get_osfhandle(fd);
    n = recv(s, (char*)(bytes + offset), byteCount, 0);
    if (n == SOCKET_ERROR) {
      int w = WSAGetLastError();
      (*env)->ReleaseByteArrayElements(env, (jbyteArray)buffer, bytes, 0);
      if (w == WSAEWOULDBLOCK) return 0;
      throw_errno(env, "read", w == WSAECONNRESET ? 104 : (w ? w : EIO));
      return -1;
    }
  } else {
    n = _read(fd, bytes + offset, (unsigned)byteCount);
    int err = errno;
    if (n < 0) {
      (*env)->ReleaseByteArrayElements(env, (jbyteArray)buffer, bytes, 0);
      throw_errno(env, "read", err);
      return -1;
    }
  }
  (*env)->ReleaseByteArrayElements(env, (jbyteArray)buffer, bytes, 0);
  return n; /* 0 means EOF for IoBridge */
}

__declspec(dllexport) jint Java_libcore_io_Linux_writeBytes(JNIEnv* env, jobject thiz, jobject fdObj, jobject buffer, jint offset, jint byteCount) {
  (void)thiz;
  int fd = fd_to_int(env, fdObj);
  if (!buffer || byteCount <= 0) return 0;
  jbyte* bytes = (*env)->GetByteArrayElements(env, (jbyteArray)buffer, 0);
  if (!bytes) return 0;
  int n = 0;
  if (fd == 1 || fd == 2) {
    HANDLE h = (fd == 2) ? GetStdHandle(STD_ERROR_HANDLE) : GetStdHandle(STD_OUTPUT_HANDLE);
    DWORD written = 0;
    if (h && h != INVALID_HANDLE_VALUE) {
      WriteFile(h, bytes + offset, (DWORD)byteCount, &written, NULL);
      n = (int)written;
    } else n = byteCount;
  } else if (fd >= 0 && is_socket_fd(fd)) {
    SOCKET s = (SOCKET)_get_osfhandle(fd);
    n = send(s, (const char*)(bytes + offset), byteCount, 0);
    if (n == SOCKET_ERROR) {
      int w = WSAGetLastError();
      (*env)->ReleaseByteArrayElements(env, (jbyteArray)buffer, bytes, JNI_ABORT);
      if (w == WSAEWOULDBLOCK) return 0;
      throw_errno(env, "write", w ? w : EIO);
      return -1;
    }
  } else if (fd >= 0) {
    n = _write(fd, bytes + offset, (unsigned)byteCount);
  }
  (*env)->ReleaseByteArrayElements(env, (jbyteArray)buffer, bytes, JNI_ABORT);
  return n < 0 ? 0 : n;
}

/* fstat / stat StructStat - use simplified constructor with timespec zeros via long ctor */
static jobject make_stat(JNIEnv* env, struct _stat64* st) {
  jclass c = (*env)->FindClass(env, "android/system/StructStat");
  if (!c) return NULL;
  /* StructStat(long,long,int,long,int,int,long,long,long,long,long,long,long) */
  jmethodID ctor = (*env)->GetMethodID(env, c, "<init>", "(JJIJIIJJJJJJJ)V");
  if (!ctor) {
    fprintf(stderr, "make_stat: GetMethodID failed\n");
    fflush(stderr);
    (*env)->ExceptionDescribe(env);
    (*env)->ExceptionClear(env);
    return NULL;
  }
  return (*env)->NewObject(env, c, ctor,
    (jlong)st->st_dev, (jlong)st->st_ino, (jint)st->st_mode, (jlong)st->st_nlink,
    (jint)st->st_uid, (jint)st->st_gid, (jlong)st->st_rdev, (jlong)st->st_size,
    (jlong)st->st_atime, (jlong)st->st_mtime, (jlong)st->st_ctime,
    (jlong)4096, (jlong)0);
}

__declspec(dllexport) jobject Java_libcore_io_Linux_stat(JNIEnv* env, jobject thiz, jstring jpath) {
  (void)thiz;
  if (!jpath) return NULL;
  const char* p = (*env)->GetStringUTFChars(env, jpath, 0);
  char norm[4096];
  win_path_normalize(p, norm, sizeof(norm));
  (*env)->ReleaseStringUTFChars(env, jpath, p);
  if (norm[0] == 0) { norm[0] = '.'; norm[1] = 0; }
  struct _stat64 st;
  if (_stat64(norm, &st) != 0) {
    fprintf(stderr, "Linux_stat fail path=[%s] err=%d\n", norm, errno);
    fflush(stderr);
    return NULL;
  }
  jobject o = make_stat(env, &st);
  if (!o) { fprintf(stderr, "make_stat null for [%s]\n", norm); fflush(stderr); }
  return o;
}
__declspec(dllexport) jobject Java_libcore_io_Linux_lstat(JNIEnv* env, jobject thiz, jstring jpath) {
  return Java_libcore_io_Linux_stat(env, thiz, jpath);
}
__declspec(dllexport) jobject Java_libcore_io_Linux_fstat(JNIEnv* env, jobject thiz, jobject fdObj) {
  (void)thiz;
  int fd = fd_to_int(env, fdObj);
  struct _stat64 st;
  if (_fstat64(fd, &st) != 0) return NULL;
  return make_stat(env, &st);
}

__declspec(dllexport) jboolean Java_libcore_io_Linux_access(JNIEnv* env, jobject thiz, jstring jpath, jint mode) {
  (void)thiz; (void)mode;
  const char* p = (*env)->GetStringUTFChars(env, jpath, 0);
  wchar_t* w = win_path_to_wide(p);
  (*env)->ReleaseStringUTFChars(env, jpath, p);
  if (!w) return JNI_FALSE;
  DWORD a = GetFileAttributesW(w);
  free(w);
  return a != INVALID_FILE_ATTRIBUTES;
}

/* Signature-mangled aliases (ART sometimes looks these up) */
__declspec(dllexport) jobject Java_libcore_io_Linux_stat__Ljava_lang_String_2(JNIEnv* env, jobject thiz, jstring jpath) {
  return Java_libcore_io_Linux_stat(env, thiz, jpath);
}
__declspec(dllexport) jobject Java_libcore_io_Linux_lstat__Ljava_lang_String_2(JNIEnv* env, jobject thiz, jstring jpath) {
  return Java_libcore_io_Linux_lstat(env, thiz, jpath);
}
__declspec(dllexport) jboolean Java_libcore_io_Linux_access__Ljava_lang_String_2I(JNIEnv* env, jobject thiz, jstring jpath, jint mode) {
  return Java_libcore_io_Linux_access(env, thiz, jpath, mode);
}
__declspec(dllexport) jobject Java_libcore_io_Linux_open__Ljava_lang_String_2II(JNIEnv* env, jobject thiz, jstring jpath, jint flags, jint mode) {
  return Java_libcore_io_Linux_open(env, thiz, jpath, flags, mode);
}
__declspec(dllexport) jobject Java_libcore_io_Linux_fstat__Ljava_io_FileDescriptor_2(JNIEnv* env, jobject thiz, jobject fd) {
  return Java_libcore_io_Linux_fstat(env, thiz, fd);
}
__declspec(dllexport) void Java_libcore_io_Linux_close__Ljava_io_FileDescriptor_2(JNIEnv* env, jobject thiz, jobject fd) {
  Java_libcore_io_Linux_close(env, thiz, fd);
}
__declspec(dllexport) jint Java_libcore_io_Linux_writeBytes__Ljava_io_FileDescriptor_2Ljava_lang_Object_2II(
    JNIEnv* env, jobject thiz, jobject fd, jobject buf, jint off, jint n) {
  return Java_libcore_io_Linux_writeBytes(env, thiz, fd, buf, off, n);
}
__declspec(dllexport) jint Java_libcore_io_Linux_readBytes__Ljava_io_FileDescriptor_2Ljava_lang_Object_2II(
    JNIEnv* env, jobject thiz, jobject fd, jobject buf, jint off, jint n) {
  return Java_libcore_io_Linux_readBytes(env, thiz, fd, buf, off, n);
}

/* ===== more Os file ops ===== */
__declspec(dllexport) void Java_libcore_io_Linux_mkdir(JNIEnv* env, jobject thiz, jstring jpath, jint mode) {
  (void)thiz; (void)mode;
  const char* p = (*env)->GetStringUTFChars(env, jpath, 0);
  wchar_t* w = win_path_to_wide(p);
  (*env)->ReleaseStringUTFChars(env, jpath, p);
  if (!w) return;
  CreateDirectoryW(w, NULL);
  free(w);
}
__declspec(dllexport) void Java_libcore_io_Linux_mkdir__Ljava_lang_String_2I(JNIEnv* env, jobject thiz, jstring jpath, jint mode) {
  Java_libcore_io_Linux_mkdir(env, thiz, jpath, mode);
}
__declspec(dllexport) void Java_libcore_io_Linux_remove(JNIEnv* env, jobject thiz, jstring jpath) {
  (void)thiz;
  const char* p = (*env)->GetStringUTFChars(env, jpath, 0);
  wchar_t* w = win_path_to_wide(p);
  (*env)->ReleaseStringUTFChars(env, jpath, p);
  if (!w) return;
  if (!DeleteFileW(w)) RemoveDirectoryW(w);
  free(w);
}
__declspec(dllexport) void Java_libcore_io_Linux_remove__Ljava_lang_String_2(JNIEnv* env, jobject thiz, jstring jpath) {
  Java_libcore_io_Linux_remove(env, thiz, jpath);
}
__declspec(dllexport) void Java_libcore_io_Linux_unlink(JNIEnv* env, jobject thiz, jstring jpath) {
  Java_libcore_io_Linux_remove(env, thiz, jpath);
}
__declspec(dllexport) void Java_libcore_io_Linux_unlink__Ljava_lang_String_2(JNIEnv* env, jobject thiz, jstring jpath) {
  Java_libcore_io_Linux_remove(env, thiz, jpath);
}
__declspec(dllexport) void Java_libcore_io_Linux_rename(JNIEnv* env, jobject thiz, jstring a, jstring b) {
  (void)thiz;
  const char* pa = (*env)->GetStringUTFChars(env, a, 0);
  const char* pb = (*env)->GetStringUTFChars(env, b, 0);
  wchar_t* wa = win_path_to_wide(pa);
  wchar_t* wb = win_path_to_wide(pb);
  (*env)->ReleaseStringUTFChars(env, a, pa);
  (*env)->ReleaseStringUTFChars(env, b, pb);
  if (wa && wb) MoveFileExW(wa, wb, MOVEFILE_REPLACE_EXISTING);
  free(wa); free(wb);
}
__declspec(dllexport) void Java_libcore_io_Linux_rename__Ljava_lang_String_2Ljava_lang_String_2(
    JNIEnv* env, jobject thiz, jstring a, jstring b) {
  Java_libcore_io_Linux_rename(env, thiz, a, b);
}
__declspec(dllexport) jstring Java_libcore_io_Linux_realpath(JNIEnv* env, jobject thiz, jstring jpath) {
  (void)thiz;
  if (!jpath) return NULL;
  const char* p = (*env)->GetStringUTFChars(env, jpath, 0);
  char norm[4096];
  win_path_normalize(p, norm, sizeof(norm));
  (*env)->ReleaseStringUTFChars(env, jpath, p);
  wchar_t* w = win_path_to_wide(norm);
  if (!w) return (*env)->NewStringUTF(env, norm);
  wchar_t full[MAX_PATH];
  DWORD n = GetFullPathNameW(w, MAX_PATH, full, NULL);
  free(w);
  if (n == 0 || n >= MAX_PATH) return (*env)->NewStringUTF(env, norm);
  char u8[MAX_PATH * 3];
  WideCharToMultiByte(CP_UTF8, 0, full, -1, u8, sizeof(u8), NULL, NULL);
  return (*env)->NewStringUTF(env, u8);
}
__declspec(dllexport) jstring Java_libcore_io_Linux_realpath__Ljava_lang_String_2(JNIEnv* env, jobject thiz, jstring jpath) {
  return Java_libcore_io_Linux_realpath(env, thiz, jpath);
}


/* ===== fdsan ownership no-ops (required by IoUtils.setFdOwner) ===== */
__declspec(dllexport) void Java_libcore_io_Linux_android_1fdsan_1exchange_1owner_1tag(
    JNIEnv* env, jobject thiz, jobject fd, jlong prev, jlong next) {
  (void)env; (void)thiz; (void)fd; (void)prev; (void)next;
}
/* ART may look up either mangled name form */
__declspec(dllexport) void Java_libcore_io_Linux_android_fdsan_exchange_owner_tag(
    JNIEnv* env, jobject thiz, jobject fd, jlong prev, jlong next) {
  (void)env; (void)thiz; (void)fd; (void)prev; (void)next;
}
__declspec(dllexport) void Java_libcore_io_Linux_android_fdsan_exchange_owner_tag__Ljava_io_FileDescriptor_2JJ(
    JNIEnv* env, jobject thiz, jobject fd, jlong prev, jlong next) {
  (void)env; (void)thiz; (void)fd; (void)prev; (void)next;
}
__declspec(dllexport) jlong Java_libcore_io_Linux_android_fdsan_get_owner_tag(JNIEnv* env, jobject thiz, jobject fd) {
  (void)env; (void)thiz; (void)fd; return 0;
}
__declspec(dllexport) jstring Java_libcore_io_Linux_android_fdsan_get_tag_type(JNIEnv* env, jobject thiz, jlong tag) {
  (void)thiz; (void)tag; return (*env)->NewStringUTF(env, "unowned");
}
__declspec(dllexport) jlong Java_libcore_io_Linux_android_fdsan_get_tag_value(JNIEnv* env, jobject thiz, jlong tag) {
  (void)env; (void)thiz; return tag;
}

/* lseek used by FileInputStream.available / channel paths */
__declspec(dllexport) jlong Java_libcore_io_Linux_lseek(JNIEnv* env, jobject thiz, jobject fdObj, jlong offset, jint whence) {
  (void)thiz;
  int fd = fd_to_int(env, fdObj);
  if (fd < 0) { throw_errno(env, "lseek", EBADF); return -1; }
  int w = SEEK_SET;
  if (whence == 1) w = SEEK_CUR;
  else if (whence == 2) w = SEEK_END;
  __int64 pos = _lseeki64(fd, (__int64)offset, w);
  if (pos < 0) { throw_errno(env, "lseek", errno); return -1; }
  return (jlong)pos;
}
__declspec(dllexport) jlong Java_libcore_io_Linux_lseek__Ljava_io_FileDescriptor_2JI(
    JNIEnv* env, jobject thiz, jobject fdObj, jlong offset, jint whence) {
  return Java_libcore_io_Linux_lseek(env, thiz, fdObj, offset, whence);
}

__declspec(dllexport) void Java_libcore_io_Linux_fsync(JNIEnv* env, jobject thiz, jobject fdObj) {
  (void)thiz;
  int fd = fd_to_int(env, fdObj);
  if (fd < 0) { throw_errno(env, "fsync", EBADF); return; }
  if (_commit(fd) != 0) throw_errno(env, "fsync", errno);
}
__declspec(dllexport) void Java_libcore_io_Linux_fsync__Ljava_io_FileDescriptor_2(JNIEnv* env, jobject thiz, jobject fdObj) {
  Java_libcore_io_Linux_fsync(env, thiz, fdObj);
}
__declspec(dllexport) void Java_libcore_io_Linux_fdatasync(JNIEnv* env, jobject thiz, jobject fdObj) {
  Java_libcore_io_Linux_fsync(env, thiz, fdObj);
}
__declspec(dllexport) void Java_libcore_io_Linux_fdatasync__Ljava_io_FileDescriptor_2(JNIEnv* env, jobject thiz, jobject fdObj) {
  Java_libcore_io_Linux_fsync(env, thiz, fdObj);
}


/* ===== mmap / msync / munmap / madvise / ftruncate / isatty / strerror ===== */
#include <sys/mman.h>

__declspec(dllexport) jlong Java_libcore_io_Linux_mmap(
    JNIEnv* env, jobject thiz, jlong address, jlong byteCount, jint prot, jint flags,
    jobject fdObj, jlong offset) {
  (void)thiz;
  if (byteCount <= 0) { errno = EINVAL; throw_errno(env, "mmap", errno); return -1; }
  int fd = -1;
  if (fdObj) {
    ensure_fd(env);
    fd = (*env)->GetIntField(env, fdObj, g_fd_descriptor);
  }
  void* hint = (void*)(uintptr_t)address;
  void* p = mmap(hint, (size_t)byteCount, prot, flags, fd, offset);
  if (p == MAP_FAILED) {
    throw_errno(env, "mmap", map_errno(errno));
    return -1;
  }
  return (jlong)(uintptr_t)p;
}
__declspec(dllexport) jlong Java_libcore_io_Linux_mmap__JJIILjava_io_FileDescriptor_2J(
    JNIEnv* env, jobject thiz, jlong address, jlong byteCount, jint prot, jint flags,
    jobject fdObj, jlong offset) {
  return Java_libcore_io_Linux_mmap(env, thiz, address, byteCount, prot, flags, fdObj, offset);
}

__declspec(dllexport) void Java_libcore_io_Linux_munmap(JNIEnv* env, jobject thiz, jlong address, jlong byteCount) {
  (void)thiz;
  if (munmap((void*)(uintptr_t)address, (size_t)byteCount) != 0)
    throw_errno(env, "munmap", map_errno(errno));
}
__declspec(dllexport) void Java_libcore_io_Linux_munmap__JJ(JNIEnv* env, jobject thiz, jlong a, jlong b) {
  Java_libcore_io_Linux_munmap(env, thiz, a, b);
}

__declspec(dllexport) void Java_libcore_io_Linux_msync(JNIEnv* env, jobject thiz, jlong address, jlong byteCount, jint flags) {
  (void)thiz;
  if (msync((void*)(uintptr_t)address, (size_t)byteCount, flags) != 0)
    throw_errno(env, "msync", map_errno(errno));
}
__declspec(dllexport) void Java_libcore_io_Linux_msync__JJI(JNIEnv* env, jobject thiz, jlong a, jlong b, jint f) {
  Java_libcore_io_Linux_msync(env, thiz, a, b, f);
}

__declspec(dllexport) void Java_libcore_io_Linux_madvise(JNIEnv* env, jobject thiz, jlong address, jlong byteCount, jint advice) {
  (void)thiz;
  if (madvise((void*)(uintptr_t)address, (size_t)byteCount, advice) != 0)
    throw_errno(env, "madvise", map_errno(errno));
}
__declspec(dllexport) void Java_libcore_io_Linux_madvise__JJI(JNIEnv* env, jobject thiz, jlong a, jlong b, jint adv) {
  Java_libcore_io_Linux_madvise(env, thiz, a, b, adv);
}

__declspec(dllexport) void Java_libcore_io_Linux_mlock(JNIEnv* env, jobject thiz, jlong address, jlong byteCount) {
  (void)env; (void)thiz; (void)address; (void)byteCount;
  /* VirtualLock optional; no-op success for PE bootstrap */
}
__declspec(dllexport) void Java_libcore_io_Linux_mlock__JJ(JNIEnv* env, jobject thiz, jlong a, jlong b) {
  Java_libcore_io_Linux_mlock(env, thiz, a, b);
}
__declspec(dllexport) void Java_libcore_io_Linux_munlock(JNIEnv* env, jobject thiz, jlong address, jlong byteCount) {
  (void)env; (void)thiz; (void)address; (void)byteCount;
}
__declspec(dllexport) void Java_libcore_io_Linux_munlock__JJ(JNIEnv* env, jobject thiz, jlong a, jlong b) {
  Java_libcore_io_Linux_munlock(env, thiz, a, b);
}

__declspec(dllexport) void Java_libcore_io_Linux_mincore(JNIEnv* env, jobject thiz, jlong address, jlong byteCount, jbyteArray vector) {
  (void)thiz;
  if (!vector) { errno = EINVAL; throw_errno(env, "mincore", errno); return; }
  jsize n = (*env)->GetArrayLength(env, vector);
  jbyte* vec = (*env)->GetByteArrayElements(env, vector, 0);
  if (!vec) return;
  int rc = mincore((void*)(uintptr_t)address, (size_t)byteCount, (unsigned char*)vec);
  (*env)->ReleaseByteArrayElements(env, vector, vec, 0);
  if (rc != 0) throw_errno(env, "mincore", map_errno(errno));
}
__declspec(dllexport) void Java_libcore_io_Linux_mincore__JJ_3B(JNIEnv* env, jobject thiz, jlong a, jlong b, jbyteArray v) {
  Java_libcore_io_Linux_mincore(env, thiz, a, b, v);
}

__declspec(dllexport) void Java_libcore_io_Linux_ftruncate(JNIEnv* env, jobject thiz, jobject fdObj, jlong length) {
  (void)thiz;
  ensure_fd(env);
  int fd = (*env)->GetIntField(env, fdObj, g_fd_descriptor);
  if (_chsize_s(fd, length) != 0) throw_errno(env, "ftruncate", map_errno(errno));
}
__declspec(dllexport) void Java_libcore_io_Linux_ftruncate__Ljava_io_FileDescriptor_2J(
    JNIEnv* env, jobject thiz, jobject fdObj, jlong length) {
  Java_libcore_io_Linux_ftruncate(env, thiz, fdObj, length);
}

__declspec(dllexport) jboolean Java_libcore_io_Linux_isatty(JNIEnv* env, jobject thiz, jobject fdObj) {
  (void)thiz;
  ensure_fd(env);
  int fd = (*env)->GetIntField(env, fdObj, g_fd_descriptor);
  return (jboolean)(_isatty(fd) ? JNI_TRUE : JNI_FALSE);
}
__declspec(dllexport) jboolean Java_libcore_io_Linux_isatty__Ljava_io_FileDescriptor_2(
    JNIEnv* env, jobject thiz, jobject fdObj) {
  return Java_libcore_io_Linux_isatty(env, thiz, fdObj);
}

__declspec(dllexport) jstring Java_libcore_io_Linux_strerror(JNIEnv* env, jobject thiz, jint errnum) {
  (void)thiz;
  char buf[256];
  if (strerror_s(buf, sizeof(buf), errnum) != 0) snprintf(buf, sizeof(buf), "errno %d", errnum);
  return (*env)->NewStringUTF(env, buf);
}
__declspec(dllexport) jstring Java_libcore_io_Linux_strerror__I(JNIEnv* env, jobject thiz, jint errnum) {
  return Java_libcore_io_Linux_strerror(env, thiz, errnum);
}

__declspec(dllexport) jstring Java_libcore_io_Linux_gai_strerror(JNIEnv* env, jobject thiz, jint error) {
  (void)thiz;
  char sys[128];
  DWORD n = FormatMessageA(FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS,
                           NULL, (DWORD)error, 0, sys, (DWORD)sizeof(sys), NULL);
  if (n > 0) {
    while (n > 0) {
      char c = sys[n - 1];
      if (c != 13 && c != 10 && c != 32) break;
      sys[--n] = 0;
    }
    return (*env)->NewStringUTF(env, sys);
  }
  char buf[64];
  snprintf(buf, sizeof(buf), "gai error %d", (int)error);
  return (*env)->NewStringUTF(env, buf);
}
__declspec(dllexport) jstring Java_libcore_io_Linux_gai_strerror__I(JNIEnv* env, jobject thiz, jint error) {
  return Java_libcore_io_Linux_gai_strerror(env, thiz, error);
}

__declspec(dllexport) jobjectArray Java_libcore_io_Linux_environ(JNIEnv* env, jobject thiz) {
  (void)thiz;
  extern char** _environ;
  int n = 0;
  if (_environ) while (_environ[n]) n++;
  jclass sc = (*env)->FindClass(env, "java/lang/String");
  jobjectArray arr = (*env)->NewObjectArray(env, n, sc, NULL);
  for (int i = 0; i < n; i++) {
    jstring s = (*env)->NewStringUTF(env, _environ[i]);
    (*env)->SetObjectArrayElement(env, arr, i, s);
  }
  return arr;
}
__declspec(dllexport) jobjectArray Java_libcore_io_Linux_environ__(JNIEnv* env, jobject thiz) {
  return Java_libcore_io_Linux_environ(env, thiz);
}

__declspec(dllexport) jstring Java_libcore_io_Linux_readlink(JNIEnv* env, jobject thiz, jstring jpath) {
  (void)thiz;
  /* Windows: no symlink readlink by default; return path as-is if exists */
  if (!jpath) { errno = EINVAL; throw_errno(env, "readlink", errno); return NULL; }
  const char* path = (*env)->GetStringUTFChars(env, jpath, 0);
  char buf[MAX_PATH];
  DWORD n = GetFullPathNameA(path, MAX_PATH, buf, NULL);
  (*env)->ReleaseStringUTFChars(env, jpath, path);
  if (n == 0 || n >= MAX_PATH) { errno = ENOENT; throw_errno(env, "readlink", errno); return NULL; }
  return (*env)->NewStringUTF(env, buf);
}
__declspec(dllexport) jstring Java_libcore_io_Linux_readlink__Ljava_lang_String_2(JNIEnv* env, jobject thiz, jstring jpath) {
  return Java_libcore_io_Linux_readlink(env, thiz, jpath);
}

__declspec(dllexport) void Java_libcore_io_Linux_posix_fallocate(JNIEnv* env, jobject thiz, jobject fdObj, jlong offset, jlong length) {
  (void)thiz;
  ensure_fd(env);
  int fd = (*env)->GetIntField(env, fdObj, g_fd_descriptor);
  /* Extend file if needed */
  __int64 end = offset + length;
  __int64 cur = _lseeki64(fd, 0, SEEK_END);
  if (cur >= 0 && end > cur) {
    if (_chsize_s(fd, end) != 0) throw_errno(env, "posix_fallocate", map_errno(errno));
  }
}
__declspec(dllexport) void Java_libcore_io_Linux_posix_fallocate__Ljava_io_FileDescriptor_2JJ(
    JNIEnv* env, jobject thiz, jobject fdObj, jlong offset, jlong length) {
  Java_libcore_io_Linux_posix_fallocate(env, thiz, fdObj, offset, length);
}


/* ===== L-001 Needed: chmod/fchmod/pipe2/pread/pwrite/readv/writev/sendfile ===== */

__declspec(dllexport) void Java_libcore_io_Linux_chmod(JNIEnv* env, jobject thiz, jstring jpath, jint mode) {
  (void)thiz;
  if (!jpath) { errno = EINVAL; throw_errno(env, "chmod", errno); return; }
  const char* path = (*env)->GetStringUTFChars(env, jpath, 0);
  char npath[MAX_PATH];
  win_path_normalize(path, npath, sizeof(npath));
  (*env)->ReleaseStringUTFChars(env, jpath, path);
  DWORD attr = GetFileAttributesA(npath);
  if (attr == INVALID_FILE_ATTRIBUTES) { errno = ENOENT; throw_errno(env, "chmod", errno); return; }
  if ((mode & 0222) == 0) attr |= FILE_ATTRIBUTE_READONLY;
  else attr &= ~FILE_ATTRIBUTE_READONLY;
  if (!SetFileAttributesA(npath, attr)) {
    errno = EACCES;
    throw_errno(env, "chmod", errno);
  }
}
__declspec(dllexport) void Java_libcore_io_Linux_chmod__Ljava_lang_String_2I(JNIEnv* env, jobject thiz, jstring p, jint m) {
  Java_libcore_io_Linux_chmod(env, thiz, p, m);
}

__declspec(dllexport) void Java_libcore_io_Linux_fchmod(JNIEnv* env, jobject thiz, jobject fdObj, jint mode) {
  (void)thiz; (void)fdObj; (void)mode;
  /* CRT has no fchmod equivalent that is portable; succeed for PE bootstrap. */
}
__declspec(dllexport) void Java_libcore_io_Linux_fchmod__Ljava_io_FileDescriptor_2I(JNIEnv* env, jobject thiz, jobject fd, jint mode) {
  Java_libcore_io_Linux_fchmod(env, thiz, fd, mode);
}

__declspec(dllexport) jobjectArray Java_libcore_io_Linux_pipe2(JNIEnv* env, jobject thiz, jint flags) {
  (void)thiz; (void)flags;
  int fds[2];
  if (_pipe(fds, 4096, _O_BINARY) != 0) {
    throw_errno(env, "pipe2", map_errno(errno));
    return NULL;
  }
  ensure_fd(env);
  jclass fdc = (*env)->FindClass(env, "java/io/FileDescriptor");
  jobjectArray arr = (*env)->NewObjectArray(env, 2, fdc, NULL);
  jobject a = fd_from_int(env, fds[0]);
  jobject b = fd_from_int(env, fds[1]);
  (*env)->SetObjectArrayElement(env, arr, 0, a);
  (*env)->SetObjectArrayElement(env, arr, 1, b);
  return arr;
}
__declspec(dllexport) jobjectArray Java_libcore_io_Linux_pipe2__I(JNIEnv* env, jobject thiz, jint flags) {
  return Java_libcore_io_Linux_pipe2(env, thiz, flags);
}

static int buffer_is_byte_array(JNIEnv* env, jobject buffer) {
  if (!buffer) return 0;
  jclass ba = (*env)->FindClass(env, "[B");
  return (*env)->IsInstanceOf(env, buffer, ba);
}

static jbyte* buffer_ptr(JNIEnv* env, jobject buffer, jint offset, jboolean* isCopy, jboolean* isArray) {
  *isArray = JNI_FALSE;
  if (buffer_is_byte_array(env, buffer)) {
    *isArray = JNI_TRUE;
    jbyte* p = (*env)->GetByteArrayElements(env, (jbyteArray)buffer, isCopy);
    return p ? p + offset : NULL;
  }
  /* Direct ByteBuffer */
  void* p = (*env)->GetDirectBufferAddress(env, buffer);
  if (!p) return NULL;
  return (jbyte*)p + offset;
}

static void buffer_release(JNIEnv* env, jobject buffer, jbyte* base, jboolean isArray, jint mode) {
  if (isArray && base) {
    /* base was advanced by offset; recover array base not needed if we stored carefully */
  }
}

__declspec(dllexport) jint Java_libcore_io_Linux_preadBytes(
    JNIEnv* env, jobject thiz, jobject fdObj, jobject buffer, jint bufferOffset, jint byteCount, jlong offset) {
  (void)thiz;
  if (byteCount == 0) return 0;
  ensure_fd(env);
  int fd = (*env)->GetIntField(env, fdObj, g_fd_descriptor);
  jboolean isCopy = 0, isArray = 0;
  jbyte* p = NULL;
  jbyteArray arr = NULL;
  if (buffer_is_byte_array(env, buffer)) {
    arr = (jbyteArray)buffer;
    p = (*env)->GetByteArrayElements(env, arr, &isCopy);
    if (!p) return -1;
    p += bufferOffset;
    isArray = 1;
  } else {
    void* d = (*env)->GetDirectBufferAddress(env, buffer);
    if (!d) { errno = EINVAL; throw_errno(env, "pread", errno); return -1; }
    p = (jbyte*)d + bufferOffset;
  }
  int n = (int)pread(fd, p, (size_t)byteCount, offset);
  if (isArray) (*env)->ReleaseByteArrayElements(env, arr, p - bufferOffset, 0);
  if (n < 0) { throw_errno(env, "pread", map_errno(errno)); return -1; }
  return n;
}
__declspec(dllexport) jint Java_libcore_io_Linux_preadBytes__Ljava_io_FileDescriptor_2Ljava_lang_Object_2IIJ(
    JNIEnv* env, jobject thiz, jobject fd, jobject buf, jint off, jint cnt, jlong pos) {
  return Java_libcore_io_Linux_preadBytes(env, thiz, fd, buf, off, cnt, pos);
}

__declspec(dllexport) jint Java_libcore_io_Linux_pwriteBytes(
    JNIEnv* env, jobject thiz, jobject fdObj, jobject buffer, jint bufferOffset, jint byteCount, jlong offset) {
  (void)thiz;
  if (byteCount == 0) return 0;
  ensure_fd(env);
  int fd = (*env)->GetIntField(env, fdObj, g_fd_descriptor);
  jbyteArray arr = NULL;
  jbyte* p = NULL;
  if (buffer_is_byte_array(env, buffer)) {
    arr = (jbyteArray)buffer;
    p = (*env)->GetByteArrayElements(env, arr, NULL);
    if (!p) return -1;
    p += bufferOffset;
  } else {
    void* d = (*env)->GetDirectBufferAddress(env, buffer);
    if (!d) { errno = EINVAL; throw_errno(env, "pwrite", errno); return -1; }
    p = (jbyte*)d + bufferOffset;
  }
  int n = (int)pwrite(fd, p, (size_t)byteCount, offset);
  if (arr) (*env)->ReleaseByteArrayElements(env, arr, p - bufferOffset, JNI_ABORT);
  if (n < 0) { throw_errno(env, "pwrite", map_errno(errno)); return -1; }
  return n;
}
__declspec(dllexport) jint Java_libcore_io_Linux_pwriteBytes__Ljava_io_FileDescriptor_2Ljava_lang_Object_2IIJ(
    JNIEnv* env, jobject thiz, jobject fd, jobject buf, jint off, jint cnt, jlong pos) {
  return Java_libcore_io_Linux_pwriteBytes(env, thiz, fd, buf, off, cnt, pos);
}

__declspec(dllexport) jint Java_libcore_io_Linux_readv(
    JNIEnv* env, jobject thiz, jobject fdObj, jobjectArray buffers, jintArray offsets, jintArray byteCounts) {
  (void)thiz;
  ensure_fd(env);
  int fd = (*env)->GetIntField(env, fdObj, g_fd_descriptor);
  jsize n = (*env)->GetArrayLength(env, buffers);
  jint* offs = (*env)->GetIntArrayElements(env, offsets, NULL);
  jint* cnts = (*env)->GetIntArrayElements(env, byteCounts, NULL);
  int total = 0;
  for (jsize i = 0; i < n; i++) {
    jobject buf = (*env)->GetObjectArrayElement(env, buffers, i);
    int c = cnts[i];
    if (c <= 0) continue;
    int r = Java_libcore_io_Linux_readBytes(env, thiz, fdObj, buf, offs[i], c);
    if ((*env)->ExceptionCheck(env)) break;
    if (r < 0) { total = -1; break; }
    total += r;
    if (r < c) break;
  }
  (*env)->ReleaseIntArrayElements(env, offsets, offs, JNI_ABORT);
  (*env)->ReleaseIntArrayElements(env, byteCounts, cnts, JNI_ABORT);
  return total;
}
__declspec(dllexport) jint Java_libcore_io_Linux_readv__Ljava_io_FileDescriptor_2_3Ljava_lang_Object_2_3I_3I(
    JNIEnv* env, jobject thiz, jobject fd, jobjectArray buffers, jintArray offsets, jintArray byteCounts) {
  return Java_libcore_io_Linux_readv(env, thiz, fd, buffers, offsets, byteCounts);
}

__declspec(dllexport) jint Java_libcore_io_Linux_writev(
    JNIEnv* env, jobject thiz, jobject fdObj, jobjectArray buffers, jintArray offsets, jintArray byteCounts) {
  (void)thiz;
  ensure_fd(env);
  jsize n = (*env)->GetArrayLength(env, buffers);
  jint* offs = (*env)->GetIntArrayElements(env, offsets, NULL);
  jint* cnts = (*env)->GetIntArrayElements(env, byteCounts, NULL);
  int total = 0;
  for (jsize i = 0; i < n; i++) {
    jobject buf = (*env)->GetObjectArrayElement(env, buffers, i);
    int c = cnts[i];
    if (c <= 0) continue;
    int r = Java_libcore_io_Linux_writeBytes(env, thiz, fdObj, buf, offs[i], c);
    if ((*env)->ExceptionCheck(env)) break;
    if (r < 0) { total = -1; break; }
    total += r;
    if (r < c) break;
  }
  (*env)->ReleaseIntArrayElements(env, offsets, offs, JNI_ABORT);
  (*env)->ReleaseIntArrayElements(env, byteCounts, cnts, JNI_ABORT);
  return total;
}
__declspec(dllexport) jint Java_libcore_io_Linux_writev__Ljava_io_FileDescriptor_2_3Ljava_lang_Object_2_3I_3I(
    JNIEnv* env, jobject thiz, jobject fd, jobjectArray buffers, jintArray offsets, jintArray byteCounts) {
  return Java_libcore_io_Linux_writev(env, thiz, fd, buffers, offsets, byteCounts);
}

__declspec(dllexport) jlong Java_libcore_io_Linux_sendfile(
    JNIEnv* env, jobject thiz, jobject outFdObj, jobject inFdObj, jobject offsetRef, jlong byteCount) {
  (void)thiz;
  ensure_fd(env);
  int outfd = (*env)->GetIntField(env, outFdObj, g_fd_descriptor);
  int infd = (*env)->GetIntField(env, inFdObj, g_fd_descriptor);
  jlong off = 0;
  jfieldID valueFid = NULL;
  if (offsetRef) {
    jclass c = (*env)->GetObjectClass(env, offsetRef);
    valueFid = (*env)->GetFieldID(env, c, "value", "J");
    if (valueFid) off = (*env)->GetLongField(env, offsetRef, valueFid);
  } else {
    off = _lseeki64(infd, 0, SEEK_CUR);
  }
  char buf[64 * 1024];
  jlong remaining = byteCount;
  jlong transferred = 0;
  while (remaining > 0) {
    int chunk = remaining > (jlong)sizeof(buf) ? (int)sizeof(buf) : (int)remaining;
    int nr = (int)pread(infd, buf, (size_t)chunk, off);
    if (nr < 0) { throw_errno(env, "sendfile", map_errno(errno)); return -1; }
    if (nr == 0) break;
    int nw_total = 0;
    while (nw_total < nr) {
      int nw = _write(outfd, buf + nw_total, (unsigned)(nr - nw_total));
      if (nw < 0) {
        /* try as socket via writeBytes path - use send if handle is socket */
        SOCKET s = (SOCKET)_get_osfhandle(outfd);
        if (s != INVALID_SOCKET && s != (SOCKET)-1) {
          int sn = send(s, buf + nw_total, nr - nw_total, 0);
          if (sn == SOCKET_ERROR) { errno = EIO; throw_errno(env, "sendfile", map_errno(errno)); return -1; }
          nw = sn;
        } else {
          throw_errno(env, "sendfile", map_errno(errno));
          return -1;
        }
      }
      nw_total += nw;
    }
    off += nr;
    transferred += nr;
    remaining -= nr;
  }
  if (offsetRef && valueFid) (*env)->SetLongField(env, offsetRef, valueFid, off);
  return transferred;
}
__declspec(dllexport) jlong Java_libcore_io_Linux_sendfile__Ljava_io_FileDescriptor_2Ljava_io_FileDescriptor_2Landroid_system_Int64Ref_2J(
    JNIEnv* env, jobject thiz, jobject o, jobject i, jobject off, jlong n) {
  return Java_libcore_io_Linux_sendfile(env, thiz, o, i, off, n);
}

__declspec(dllexport) jint Java_libcore_io_Linux_umaskImpl(JNIEnv* env, jobject thiz, jint mask) {
  (void)env; (void)thiz;
  return mask & 0777; /* no process umask on Win CRT PE; echo sanitized mask */
}
__declspec(dllexport) jint Java_libcore_io_Linux_umaskImpl__I(JNIEnv* env, jobject thiz, jint mask) {
  return Java_libcore_io_Linux_umaskImpl(env, thiz, mask);
}
