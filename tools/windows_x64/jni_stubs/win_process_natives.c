/*
 * Windows x64 PE: java.lang.UNIXProcess natives via CreateProcess.
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
#include <mdvm_windows_utf8.h>

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

static int compare_environment_entries(const void* left, const void* right) {
  const wchar_t* const* left_entry = (const wchar_t* const*)left;
  const wchar_t* const* right_entry = (const wchar_t* const*)right;
  int order = _wcsicmp(*left_entry, *right_entry);
  return order != 0 ? order : wcscmp(*left_entry, *right_entry);
}

/* Convert the Unix JNI block ("KEY=VAL\0" repeated envc times) to the
 * sorted, double-NUL-terminated UTF-16 block required by CreateProcessW. */
static wchar_t* unix_env_to_win_block(const char* block, int envc, jsize block_len) {
  if (envc < 0 || block_len < 0 || (envc > 0 && (block == NULL || block_len == 0))) {
    SetLastError(ERROR_INVALID_PARAMETER);
    return NULL;
  }
  if (envc == 0) {
    if (block_len != 0) {
      SetLastError(ERROR_INVALID_PARAMETER);
      return NULL;
    }
    return (wchar_t*)calloc(2u, sizeof(wchar_t));
  }

  wchar_t** entries = (wchar_t**)calloc((size_t)envc, sizeof(wchar_t*));
  if (entries == NULL) {
    SetLastError(ERROR_NOT_ENOUGH_MEMORY);
    return NULL;
  }
  size_t offset = 0u;
  size_t total = 1u;
  int converted = 0;
  for (; converted < envc; ++converted) {
    if (offset >= (size_t)block_len) {
      SetLastError(ERROR_INVALID_PARAMETER);
      goto fail;
    }
    const char* entry = block + offset;
    size_t remaining = (size_t)block_len - offset;
    const char* end = (const char*)memchr(entry, '\0', remaining);
    if (end == NULL) {
      SetLastError(ERROR_INVALID_PARAMETER);
      goto fail;
    }
    size_t byte_length = (size_t)(end - entry);
    if (byte_length > INT_MAX) {
      SetLastError(ERROR_INVALID_PARAMETER);
      goto fail;
    }
    int wide_length = MultiByteToWideChar(
        CP_UTF8, MB_ERR_INVALID_CHARS, entry, (int)byte_length, NULL, 0);
    if (wide_length == 0 || total > SIZE_MAX - (size_t)wide_length - 1u) {
      if (wide_length != 0) SetLastError(ERROR_NOT_ENOUGH_MEMORY);
      goto fail;
    }
    entries[converted] =
        (wchar_t*)malloc(((size_t)wide_length + 1u) * sizeof(wchar_t));
    if (entries[converted] == NULL) {
      SetLastError(ERROR_NOT_ENOUGH_MEMORY);
      goto fail;
    }
    if (MultiByteToWideChar(CP_UTF8,
                            MB_ERR_INVALID_CHARS,
                            entry,
                            (int)byte_length,
                            entries[converted],
                            wide_length) == 0) {
      goto fail;
    }
    entries[converted][wide_length] = L'\0';
    total += (size_t)wide_length + 1u;
    offset += byte_length + 1u;
  }
  while (offset < (size_t)block_len && block[offset] == '\0') ++offset;
  if (offset != (size_t)block_len || total > SIZE_MAX / sizeof(wchar_t)) {
    SetLastError(ERROR_INVALID_PARAMETER);
    goto fail;
  }

  qsort(entries, (size_t)envc, sizeof(entries[0]), compare_environment_entries);
  wchar_t* result = (wchar_t*)calloc(total, sizeof(wchar_t));
  if (result == NULL) {
    SetLastError(ERROR_NOT_ENOUGH_MEMORY);
    goto fail;
  }
  size_t result_offset = 0u;
  for (int index = 0; index < envc; ++index) {
    size_t length = wcslen(entries[index]);
    memcpy(result + result_offset, entries[index], (length + 1u) * sizeof(wchar_t));
    result_offset += length + 1u;
    free(entries[index]);
  }
  free(entries);
  return result;

fail:
  {
    DWORD error = GetLastError();
    for (int index = 0; index <= converted && index < envc; ++index) {
      free(entries[index]);
    }
    free(entries);
    SetLastError(error);
    return NULL;
  }
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

static int reserve_cmdline(wchar_t** buf, size_t len, size_t* cap, size_t add) {
  if (add > SIZE_MAX - len - 1u) return -1;
  size_t required = len + add + 1u;
  if (required <= *cap) return 0;
  size_t next = *cap != 0u ? *cap : 256u;
  while (next < required) {
    if (next > SIZE_MAX / 2u) {
      next = required;
      break;
    }
    next *= 2u;
  }
  if (next > SIZE_MAX / sizeof(wchar_t)) return -1;
  wchar_t* replacement = (wchar_t*)realloc(*buf, next * sizeof(wchar_t));
  if (replacement == NULL) return -1;
  *buf = replacement;
  *cap = next;
  return 0;
}

/* Apply the quoting and backslash rules consumed by CommandLineToArgvW. */
static int append_quoted(wchar_t** buf, size_t* len, size_t* cap, const wchar_t* arg) {
  size_t argument_length = wcslen(arg);
  int needs_quotes = argument_length == 0u;
  for (const wchar_t* cursor = arg; *cursor != L'\0' && !needs_quotes; ++cursor) {
    needs_quotes = *cursor == L' ' || *cursor == L'\t' || *cursor == L'"';
  }
  if (reserve_cmdline(buf, *len, cap, 2u * argument_length + 2u) != 0) return -1;
  if (!needs_quotes) {
    memcpy(*buf + *len, arg, argument_length * sizeof(wchar_t));
    *len += argument_length;
    (*buf)[*len] = L'\0';
    return 0;
  }

  (*buf)[(*len)++] = L'"';
  size_t backslashes = 0u;
  for (const wchar_t* cursor = arg;; ++cursor) {
    if (*cursor == L'\\') {
      ++backslashes;
      continue;
    }
    if (*cursor == L'"') {
      for (size_t index = 0u; index < 2u * backslashes + 1u; ++index) {
        (*buf)[(*len)++] = L'\\';
      }
      (*buf)[(*len)++] = L'"';
      backslashes = 0u;
      continue;
    }
    if (*cursor == L'\0') {
      for (size_t index = 0u; index < 2u * backslashes; ++index) {
        (*buf)[(*len)++] = L'\\';
      }
      break;
    }
    for (size_t index = 0u; index < backslashes; ++index) {
      (*buf)[(*len)++] = L'\\';
    }
    backslashes = 0u;
    (*buf)[(*len)++] = *cursor;
  }
  (*buf)[(*len)++] = L'"';
  (*buf)[*len] = L'\0';
  return 0;
}

static wchar_t* build_cmdline(const wchar_t* prog,
                              const char* arg_block,
                              size_t arg_block_len,
                              int argc) {
  wchar_t* buf = NULL;
  size_t len = 0, cap = 0;
  if (argc < 0 || append_quoted(&buf, &len, &cap, prog ? prog : L"") != 0) goto fail;
  size_t offset = 0u;
  for (int i = 0; i < argc; i++) {
    if (offset >= arg_block_len) goto fail;
    const char* argument = arg_block + offset;
    const char* end = (const char*)memchr(argument, '\0', arg_block_len - offset);
    if (end == NULL) goto fail;
    wchar_t* wide_argument = mdvm_utf8_to_utf16_alloc(argument);
    if (wide_argument == NULL) goto fail;
    if (reserve_cmdline(&buf, len, &cap, 1u) != 0) {
      free(wide_argument);
      goto fail;
    }
    buf[len++] = L' ';
    buf[len] = L'\0';
    if (append_quoted(&buf, &len, &cap, wide_argument) != 0) {
      free(wide_argument);
      goto fail;
    }
    free(wide_argument);
    offset = (size_t)(end - arg_block) + 1u;
  }
  return buf;
fail:
  SetLastError(ERROR_INVALID_PARAMETER);
  free(buf);
  return NULL;
}

static wchar_t* get_environment_variable(const wchar_t* name) {
  DWORD required = GetEnvironmentVariableW(name, NULL, 0u);
  if (required == 0u) return NULL;
  size_t required_chars = (size_t)required;
  if (required_chars > SIZE_MAX / sizeof(wchar_t)) return NULL;
  wchar_t* value = (wchar_t*)malloc(required_chars * sizeof(wchar_t));
  if (value == NULL) {
    SetLastError(ERROR_NOT_ENOUGH_MEMORY);
    return NULL;
  }
  DWORD length = GetEnvironmentVariableW(name, value, required);
  if (length == 0u || length >= required) {
    DWORD error = GetLastError();
    free(value);
    SetLastError(error);
    return NULL;
  }
  return value;
}

static wchar_t* get_command_interpreter(void) {
  wchar_t* comspec = get_environment_variable(L"ComSpec");
  if (comspec != NULL) return comspec;
  wchar_t* system_root = get_environment_variable(L"SystemRoot");
  const wchar_t* suffix = L"\\System32\\cmd.exe";
  if (system_root == NULL) {
    const wchar_t* fallback_root = L"C:\\Windows";
    size_t fallback_length = wcslen(fallback_root) + 1u;
    system_root = (wchar_t*)malloc(fallback_length * sizeof(wchar_t));
    if (system_root == NULL) return NULL;
    memcpy(system_root, fallback_root, fallback_length * sizeof(wchar_t));
  }
  size_t root_length = wcslen(system_root);
  size_t suffix_length = wcslen(suffix);
  if (root_length > SIZE_MAX - suffix_length - 1u ||
      root_length + suffix_length + 1u > SIZE_MAX / sizeof(wchar_t)) {
    free(system_root);
    SetLastError(ERROR_NOT_ENOUGH_MEMORY);
    return NULL;
  }
  wchar_t* result = (wchar_t*)malloc(
      (root_length + suffix_length + 1u) * sizeof(wchar_t));
  if (result == NULL) {
    free(system_root);
    SetLastError(ERROR_NOT_ENOUGH_MEMORY);
    return NULL;
  }
  memcpy(result, system_root, root_length * sizeof(wchar_t));
  memcpy(result + root_length, suffix, (suffix_length + 1u) * sizeof(wchar_t));
  free(system_root);
  return result;
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
  wchar_t* wprog = NULL;
  wchar_t* wdir = NULL;
  wchar_t* cmdline = NULL;
  wchar_t* winenv = NULL;
  jbyte* arg_bytes = NULL;
  jint* fds = NULL;
  HANDLE in_r = NULL, in_w = NULL, out_r = NULL, out_w = NULL, err_r = NULL, err_w = NULL;
  HANDLE child_in = NULL, child_out = NULL, child_err = NULL;
  int parent_in = -1, parent_out = -1, parent_err = -1;
  int created_in = 0, created_out = 0, created_err = 0;
  STARTUPINFOW si;
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
  if (pprog != NULL) wprog = mdvm_utf8_to_utf16_alloc(pprog);
  jsize arg_len = (*env)->GetArrayLength(env, argBlock);
  if (!pprog || !wprog) {
    throw_io(env, "forkAndExec: invalid UTF-8 or OOM");
    goto fail;
  }
  pargs = (char*)malloc((size_t)arg_len + 1);
  if (!pargs) { throw_io(env, "forkAndExec: OOM"); goto fail; }
  if (arg_len > 0) {
    arg_bytes = (*env)->GetByteArrayElements(env, argBlock, NULL);
    if (arg_bytes == NULL) { throw_io(env, "forkAndExec: OOM"); goto fail; }
    memcpy(pargs, arg_bytes, (size_t)arg_len);
    (*env)->ReleaseByteArrayElements(env, argBlock, arg_bytes, JNI_ABORT);
    arg_bytes = NULL;
  }
  pargs[arg_len] = '\0';

  cmdline = build_cmdline(wprog, pargs, (size_t)arg_len, argc);
  if (!cmdline) { throw_io(env, "forkAndExec: cmdline"); goto fail; }

  if (envBlock != NULL) {
    jsize elen = (*env)->GetArrayLength(env, envBlock);
    jbyte* eb = NULL;
    if (elen > 0) {
      eb = (*env)->GetByteArrayElements(env, envBlock, NULL);
      if (!eb) { throw_io(env, "forkAndExec: env"); goto fail; }
    }
    winenv = unix_env_to_win_block((const char*)eb, envc, elen);
    if (eb != NULL) {
      (*env)->ReleaseByteArrayElements(env, envBlock, eb, JNI_ABORT);
    }
    if (winenv == NULL) {
      throw_io(env, "forkAndExec: invalid UTF-8 environment or OOM");
      goto fail;
    }
  }

  if (dir != NULL) {
    char* dir_utf8 = bytes_to_cstr(env, dir);
    if (dir_utf8 != NULL) wdir = mdvm_utf8_to_utf16_alloc(dir_utf8);
    free(dir_utf8);
    if (wdir == NULL) {
      throw_io(env, "forkAndExec: invalid UTF-8 directory or OOM");
      goto fail;
    }
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
  DWORD flags = winenv != NULL ? CREATE_UNICODE_ENVIRONMENT : 0u;

  BOOL ok = CreateProcessW(
      /* lpApplicationName */ wprog,
      /* lpCommandLine */ cmdline,
      /* proc attrs */ NULL,
      /* thread attrs */ NULL,
      /* inherit handles */ TRUE,
      flags,
      /* env */ winenv,
      /* cwd */ wdir,
      &si,
      &pi);

  if (!ok) {
    DWORD err = GetLastError();
    /* wine/host: bare "cmd.exe" sometimes needs ComSpec expansion */
    if ((err == ERROR_FILE_NOT_FOUND || err == ERROR_PATH_NOT_FOUND) &&
        pprog && (_stricmp(pprog, "cmd.exe") == 0 || _stricmp(pprog, "cmd") == 0)) {
      wchar_t* comspec = get_command_interpreter();
      if (comspec == NULL) {
        throw_io(env, "forkAndExec: ComSpec");
        goto fail;
      }
      free(cmdline);
      cmdline = build_cmdline(comspec, pargs, (size_t)arg_len, argc);
      if (!cmdline) {
        free(comspec);
        throw_io(env, "forkAndExec: cmdline comspec");
        goto fail;
      }
      memset(&pi, 0, sizeof(pi));
      ok = CreateProcessW(
          comspec, cmdline, NULL, NULL, TRUE, flags, winenv, wdir, &si, &pi);
      err = ok ? 0 : GetLastError();
      free(comspec);
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
  free(wprog);
  free(wdir);
  free(cmdline);
  free(winenv);
  if (arg_bytes != NULL) {
    (*env)->ReleaseByteArrayElements(env, argBlock, arg_bytes, JNI_ABORT);
  }
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
