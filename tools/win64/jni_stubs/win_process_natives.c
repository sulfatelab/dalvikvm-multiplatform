/*
 * Win64 PE: java.lang.UNIXProcess natives via CreateProcess.
 * Replaces excluded UNIXProcess_md.c (fork/exec) for Runtime.exec / ProcessBuilder.
 *
 * Semantics match Android ProcessImpl → UNIXProcess.forkAndExec:
 *  - fds[i] == -1 → create pipe; on return parent-side fd is written back
 *  - fds[i] >= 0  → inherit/use that CRT fd for the child std handle
 *  - redirectErrorStream → child stderr redirected to stdout pipe
 */
#include <jni.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <errno.h>
#include <io.h>
#include <fcntl.h>
#include <process.h>
#include <windows.h>

static jfieldID g_exitcode_field;

static void throw_io(JNIEnv* env, const char* msg) {
  jclass c = (*env)->FindClass(env, "java/io/IOException");
  if (c) (*env)->ThrowNew(env, c, msg ? msg : "I/O error");
}

static void throw_io_win(JNIEnv* env, const char* what, DWORD err) {
  char buf[256];
  snprintf(buf, sizeof(buf), "%s failed (WinError %lu)", what ? what : "CreateProcess", (unsigned long)err);
  throw_io(env, buf);
}

static char* bytes_to_cstr(JNIEnv* env, jbyteArray arr) {
  if (!arr) return NULL;
  jsize n = (*env)->GetArrayLength(env, arr);
  jbyte* p = (*env)->GetByteArrayElements(env, arr, NULL);
  if (!p) return NULL;
  char* s = (char*)malloc((size_t)n + 1);
  if (!s) {
    (*env)->ReleaseByteArrayElements(env, arr, p, JNI_ABORT);
    return NULL;
  }
  memcpy(s, p, (size_t)n);
  s[n] = '\0';
  /* strip trailing NULs if present */
  while (n > 0 && s[n - 1] == '\0') {
    n--;
    s[n] = '\0';
  }
  (*env)->ReleaseByteArrayElements(env, arr, p, JNI_ABORT);
  return s;
}

/* Unix env block: concatenated "KEY=VAL\0" entries, envc of them.
 * Windows CreateProcessA needs "KEY=VAL\0KEY2=VAL2\0\0". */
static char* unix_env_to_win_block(const char* block, int envc, jsize block_len) {
  if (!block || envc <= 0 || block_len <= 0) return NULL;
  /* block already has NULs between entries; ensure double-NUL at end */
  size_t need = (size_t)block_len + 2;
  char* out = (char*)malloc(need);
  if (!out) return NULL;
  memcpy(out, block, (size_t)block_len);
  /* ensure trailing double null */
  if (block_len == 0 || out[block_len - 1] != '\0') {
    out[block_len] = '\0';
    out[block_len + 1] = '\0';
  } else {
    out[block_len] = '\0';
  }
  return out;
}

static int make_inheritable_pipe(HANDLE* read_h, HANDLE* write_h) {
  SECURITY_ATTRIBUTES sa;
  memset(&sa, 0, sizeof(sa));
  sa.nLength = sizeof(sa);
  sa.bInheritHandle = TRUE;
  if (!CreatePipe(read_h, write_h, &sa, 0)) return -1;
  return 0;
}

static int handle_to_crt_fd(HANDLE h, int flags) {
  if (!h || h == INVALID_HANDLE_VALUE) return -1;
  /* Duplicate so CRT owns a handle separate from CreateProcess usage if needed */
  int fd = _open_osfhandle((intptr_t)h, flags);
  return fd;
}

static HANDLE crt_fd_to_handle(int fd) {
  if (fd < 0) return INVALID_HANDLE_VALUE;
  HANDLE h = (HANDLE)_get_osfhandle(fd);
  return h;
}

/* Quote Windows command-line argument if needed (simplified). */
static int append_quoted(char** buf, size_t* len, size_t* cap, const char* arg) {
  int need_quote = 0;
  for (const char* p = arg; *p; p++) {
    if (*p == ' ' || *p == '\t' || *p == '"') { need_quote = 1; break; }
  }
  size_t alen = strlen(arg);
  size_t add = alen + (need_quote ? 2 : 0) + 8;
  if (*len + add + 1 > *cap) {
    size_t ncap = (*cap ? *cap * 2 : 256) + add;
    char* nb = (char*)realloc(*buf, ncap);
    if (!nb) return -1;
    *buf = nb;
    *cap = ncap;
  }
  if (need_quote) (*buf)[(*len)++] = '"';
  for (const char* p = arg; *p; p++) {
    if (*p == '"') {
      (*buf)[(*len)++] = '\\';
    }
    (*buf)[(*len)++] = *p;
  }
  if (need_quote) (*buf)[(*len)++] = '"';
  (*buf)[*len] = '\0';
  return 0;
}

static char* build_cmdline(const char* prog, const char* argBlock, int argc) {
  char* buf = NULL;
  size_t len = 0, cap = 0;
  if (append_quoted(&buf, &len, &cap, prog ? prog : "") != 0) goto fail;
  const char* p = argBlock;
  for (int i = 0; i < argc; i++) {
    if (!p) break;
    if (len + 2 > cap) {
      size_t ncap = (cap ? cap * 2 : 256) + 16;
      char* nb = (char*)realloc(buf, ncap);
      if (!nb) goto fail;
      buf = nb;
      cap = ncap;
    }
    buf[len++] = ' ';
    buf[len] = '\0';
    if (append_quoted(&buf, &len, &cap, p) != 0) goto fail;
    p += strlen(p) + 1;
  }
  return buf;
fail:
  free(buf);
  return NULL;
}

JNIEXPORT void JNICALL
Java_java_lang_UNIXProcess_initIDs(JNIEnv* env, jclass clazz) {
  g_exitcode_field = (*env)->GetFieldID(env, clazz, "exitcode", "I");
}

/* Also register-style name without Java_ prefix used by NATIVE_METHOD macro paths */
JNIEXPORT void JNICALL UNIXProcess_initIDs(JNIEnv* env, jclass clazz) {
  Java_java_lang_UNIXProcess_initIDs(env, clazz);
}

JNIEXPORT jint JNICALL
Java_java_lang_UNIXProcess_waitForProcessExit(JNIEnv* env, jobject thiz, jint pid) {
  (void)thiz;
  if (pid <= 0) return -1;
  HANDLE h = OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_QUERY_INFORMATION, FALSE, (DWORD)pid);
  if (!h) {
    /* already gone */
    return 0;
  }
  DWORD wr = WaitForSingleObject(h, INFINITE);
  DWORD code = 1;
  if (wr == WAIT_OBJECT_0) {
    if (!GetExitCodeProcess(h, &code)) code = 1;
  }
  CloseHandle(h);
  return (jint)code;
}

JNIEXPORT jint JNICALL UNIXProcess_waitForProcessExit(JNIEnv* env, jobject thiz, jint pid) {
  return Java_java_lang_UNIXProcess_waitForProcessExit(env, thiz, pid);
}

JNIEXPORT void JNICALL
Java_java_lang_UNIXProcess_destroyProcess(JNIEnv* env, jclass clazz, jint pid) {
  (void)env; (void)clazz;
  if (pid <= 0) return;
  HANDLE h = OpenProcess(PROCESS_TERMINATE, FALSE, (DWORD)pid);
  if (!h) return;
  TerminateProcess(h, 1);
  CloseHandle(h);
}

JNIEXPORT void JNICALL UNIXProcess_destroyProcess(JNIEnv* env, jclass clazz, jint pid) {
  Java_java_lang_UNIXProcess_destroyProcess(env, clazz, pid);
}

JNIEXPORT jint JNICALL
Java_java_lang_UNIXProcess_forkAndExec(JNIEnv* env, jobject process,
                                       jbyteArray prog,
                                       jbyteArray argBlock, jint argc,
                                       jbyteArray envBlock, jint envc,
                                       jbyteArray dir,
                                       jintArray std_fds,
                                       jboolean redirectErrorStream) {
  (void)process;
  jint resultPid = -1;
  char* pprog = NULL;
  char* pargs = NULL;
  char* penv = NULL;
  char* pdir = NULL;
  char* cmdline = NULL;
  char* winenv = NULL;
  jint* fds = NULL;
  HANDLE in_r = NULL, in_w = NULL, out_r = NULL, out_w = NULL, err_r = NULL, err_w = NULL;
  HANDLE child_in = NULL, child_out = NULL, child_err = NULL;
  int parent_in = -1, parent_out = -1, parent_err = -1;
  int created_in = 0, created_out = 0, created_err = 0;
  STARTUPINFOA si;
  PROCESS_INFORMATION pi;
  memset(&si, 0, sizeof(si));
  memset(&pi, 0, sizeof(pi));
  si.cb = sizeof(si);
  si.dwFlags = STARTF_USESTDHANDLES;

  if (!prog || !argBlock || !std_fds) {
    throw_io(env, "forkAndExec: null argument");
    return -1;
  }

  pprog = bytes_to_cstr(env, prog);
  jsize arg_len = (*env)->GetArrayLength(env, argBlock);
  jbyte* arg_bytes = (*env)->GetByteArrayElements(env, argBlock, NULL);
  if (!pprog || !arg_bytes) { throw_io(env, "forkAndExec: OOM"); goto fail; }
  pargs = (char*)malloc((size_t)arg_len + 1);
  if (!pargs) { throw_io(env, "forkAndExec: OOM"); goto fail; }
  memcpy(pargs, arg_bytes, (size_t)arg_len);
  pargs[arg_len] = '\0';
  (*env)->ReleaseByteArrayElements(env, argBlock, arg_bytes, JNI_ABORT);
  arg_bytes = NULL;

  cmdline = build_cmdline(pprog, pargs, argc);
  if (!cmdline) { throw_io(env, "forkAndExec: cmdline"); goto fail; }

  if (envBlock != NULL && envc > 0) {
    jsize elen = (*env)->GetArrayLength(env, envBlock);
    jbyte* eb = (*env)->GetByteArrayElements(env, envBlock, NULL);
    if (!eb) { throw_io(env, "forkAndExec: env"); goto fail; }
    winenv = unix_env_to_win_block((const char*)eb, envc, elen);
    (*env)->ReleaseByteArrayElements(env, envBlock, eb, JNI_ABORT);
  }

  if (dir != NULL) {
    pdir = bytes_to_cstr(env, dir);
  }

  fds = (*env)->GetIntArrayElements(env, std_fds, NULL);
  if (!fds) { throw_io(env, "forkAndExec: fds"); goto fail; }

  /* stdin */
  if (fds[0] == -1) {
    if (make_inheritable_pipe(&in_r, &in_w) != 0) {
      throw_io_win(env, "CreatePipe(stdin)", GetLastError());
      goto fail;
    }
    created_in = 1;
    /* parent writes to in_w; child reads in_r */
    SetHandleInformation(in_w, HANDLE_FLAG_INHERIT, 0);
    child_in = in_r;
    parent_in = handle_to_crt_fd(in_w, _O_WRONLY | _O_BINARY);
    if (parent_in < 0) { throw_io(env, "stdin pipe fd"); goto fail; }
    /* CRT took ownership of in_w */
    in_w = NULL;
  } else if (fds[0] >= 0) {
    HANDLE h = crt_fd_to_handle(fds[0]);
    if (h == INVALID_HANDLE_VALUE) { throw_io(env, "bad stdin fd"); goto fail; }
    if (!DuplicateHandle(GetCurrentProcess(), h, GetCurrentProcess(), &child_in,
                         0, TRUE, DUPLICATE_SAME_ACCESS)) {
      throw_io_win(env, "DuplicateHandle(stdin)", GetLastError());
      goto fail;
    }
  } else {
    child_in = GetStdHandle(STD_INPUT_HANDLE);
  }

  /* stdout */
  if (fds[1] == -1) {
    if (make_inheritable_pipe(&out_r, &out_w) != 0) {
      throw_io_win(env, "CreatePipe(stdout)", GetLastError());
      goto fail;
    }
    created_out = 1;
    SetHandleInformation(out_r, HANDLE_FLAG_INHERIT, 0);
    child_out = out_w;
    parent_out = handle_to_crt_fd(out_r, _O_RDONLY | _O_BINARY);
    if (parent_out < 0) { throw_io(env, "stdout pipe fd"); goto fail; }
    out_r = NULL;
  } else if (fds[1] >= 0) {
    HANDLE h = crt_fd_to_handle(fds[1]);
    if (h == INVALID_HANDLE_VALUE) { throw_io(env, "bad stdout fd"); goto fail; }
    if (!DuplicateHandle(GetCurrentProcess(), h, GetCurrentProcess(), &child_out,
                         0, TRUE, DUPLICATE_SAME_ACCESS)) {
      throw_io_win(env, "DuplicateHandle(stdout)", GetLastError());
      goto fail;
    }
  } else {
    child_out = GetStdHandle(STD_OUTPUT_HANDLE);
  }

  /* stderr */
  if (redirectErrorStream) {
    child_err = child_out;
  } else if (fds[2] == -1) {
    if (make_inheritable_pipe(&err_r, &err_w) != 0) {
      throw_io_win(env, "CreatePipe(stderr)", GetLastError());
      goto fail;
    }
    created_err = 1;
    SetHandleInformation(err_r, HANDLE_FLAG_INHERIT, 0);
    child_err = err_w;
    parent_err = handle_to_crt_fd(err_r, _O_RDONLY | _O_BINARY);
    if (parent_err < 0) { throw_io(env, "stderr pipe fd"); goto fail; }
    err_r = NULL;
  } else if (fds[2] >= 0) {
    HANDLE h = crt_fd_to_handle(fds[2]);
    if (h == INVALID_HANDLE_VALUE) { throw_io(env, "bad stderr fd"); goto fail; }
    if (!DuplicateHandle(GetCurrentProcess(), h, GetCurrentProcess(), &child_err,
                         0, TRUE, DUPLICATE_SAME_ACCESS)) {
      throw_io_win(env, "DuplicateHandle(stderr)", GetLastError());
      goto fail;
    }
  } else {
    child_err = GetStdHandle(STD_ERROR_HANDLE);
  }

  si.hStdInput = child_in ? child_in : INVALID_HANDLE_VALUE;
  si.hStdOutput = child_out ? child_out : INVALID_HANDLE_VALUE;
  si.hStdError = child_err ? child_err : INVALID_HANDLE_VALUE;

  /* 0: inherit handles only. CREATE_NO_WINDOW broke stdout capture under wine. */
  DWORD flags = 0;

  BOOL ok = CreateProcessA(
      /* lpApplicationName */ NULL,
      /* lpCommandLine */ cmdline,
      /* proc attrs */ NULL,
      /* thread attrs */ NULL,
      /* inherit handles */ TRUE,
      flags,
      /* env */ winenv,
      /* cwd */ pdir,
      &si,
      &pi);

  if (!ok) {
    DWORD err = GetLastError();
    /* wine/host: bare "cmd.exe" sometimes needs ComSpec expansion */
    if ((err == ERROR_FILE_NOT_FOUND || err == ERROR_PATH_NOT_FOUND) &&
        pprog && (_stricmp(pprog, "cmd.exe") == 0 || _stricmp(pprog, "cmd") == 0)) {
      char comspec[MAX_PATH];
      DWORD n = GetEnvironmentVariableA("ComSpec", comspec, MAX_PATH);
      if (n == 0 || n >= MAX_PATH) {
        n = GetEnvironmentVariableA("SystemRoot", comspec, MAX_PATH);
        if (n > 0 && n < MAX_PATH - 20) {
          strncat(comspec, "\\System32\\cmd.exe", MAX_PATH - strlen(comspec) - 1);
        } else {
          strcpy(comspec, "C:\\Windows\\System32\\cmd.exe");
        }
      }
      free(cmdline);
      cmdline = build_cmdline(comspec, pargs, argc);
      if (!cmdline) { throw_io(env, "forkAndExec: cmdline comspec"); goto fail; }
      memset(&pi, 0, sizeof(pi));
      ok = CreateProcessA(NULL, cmdline, NULL, NULL, TRUE, flags, winenv, pdir, &si, &pi);
      err = ok ? 0 : GetLastError();
    }
    if (!ok) {
      throw_io_win(env, "CreateProcess", err);
      goto fail;
    }
  }

  resultPid = (jint)pi.dwProcessId;
  CloseHandle(pi.hThread);
  CloseHandle(pi.hProcess);

  /* Close child-side pipe ends in parent */
  if (created_in && in_r) { CloseHandle(in_r); in_r = NULL; }
  if (created_out && out_w) { CloseHandle(out_w); out_w = NULL; }
  if (created_err && err_w) { CloseHandle(err_w); err_w = NULL; }
  /* close duplicated inherit handles that are not CRT-owned */
  if (fds[0] >= 0 && child_in) { CloseHandle(child_in); child_in = NULL; }
  if (fds[1] >= 0 && child_out) { CloseHandle(child_out); child_out = NULL; }
  if (!redirectErrorStream && fds[2] >= 0 && child_err) { CloseHandle(child_err); child_err = NULL; }

  fds[0] = parent_in;
  fds[1] = parent_out;
  fds[2] = redirectErrorStream ? -1 : parent_err;

  (*env)->ReleaseIntArrayElements(env, std_fds, fds, 0);
  fds = NULL;

cleanup:
  free(pprog);
  free(pargs);
  free(penv);
  free(pdir);
  free(cmdline);
  free(winenv);
  if (in_r) CloseHandle(in_r);
  if (in_w) CloseHandle(in_w);
  if (out_r) CloseHandle(out_r);
  if (out_w) CloseHandle(out_w);
  if (err_r) CloseHandle(err_r);
  if (err_w) CloseHandle(err_w);
  return resultPid;

fail:
  if (parent_in >= 0) _close(parent_in);
  if (parent_out >= 0) _close(parent_out);
  if (parent_err >= 0) _close(parent_err);
  if (fds) {
    (*env)->ReleaseIntArrayElements(env, std_fds, fds, JNI_ABORT);
    fds = NULL;
  }
  resultPid = -1;
  goto cleanup;
}

JNIEXPORT jint JNICALL
UNIXProcess_forkAndExec(JNIEnv* env, jobject process,
                        jbyteArray prog, jbyteArray argBlock, jint argc,
                        jbyteArray envBlock, jint envc, jbyteArray dir,
                        jintArray std_fds, jboolean redirectErrorStream) {
  return Java_java_lang_UNIXProcess_forkAndExec(env, process, prog, argBlock, argc,
                                                envBlock, envc, dir, std_fds, redirectErrorStream);
}

/* RegisterNatives entry used by openjdk OnLoad */
#include <nativehelper/JNIHelp.h>
#ifndef NELEM
#define NELEM(x) ((int)(sizeof(x) / sizeof((x)[0])))
#endif

static JNINativeMethod gMethods[] = {
  { "initIDs", "()V", (void*)Java_java_lang_UNIXProcess_initIDs },
  { "forkAndExec", "([B[BI[BI[B[IZ)I", (void*)Java_java_lang_UNIXProcess_forkAndExec },
  { "waitForProcessExit", "(I)I", (void*)Java_java_lang_UNIXProcess_waitForProcessExit },
  { "destroyProcess", "(I)V", (void*)Java_java_lang_UNIXProcess_destroyProcess },
};

void register_java_lang_UNIXProcess(JNIEnv* env) {
  jniRegisterNativeMethods(env, "java/lang/UNIXProcess", gMethods, NELEM(gMethods));
}
