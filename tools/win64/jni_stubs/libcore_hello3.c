#include <stdio.h>
#include <stddef.h>

#include <stdint.h>
#include <jni.h>
#include <windows.h>

__declspec(dllexport) jint JNI_OnLoad(JavaVM* vm, void* reserved) {
  (void)vm; (void)reserved; return JNI_VERSION_1_6;
}
__declspec(dllexport) void JNI_OnUnload(JavaVM* vm, void* reserved) {
  (void)vm; (void)reserved;
}

static int streq(const char* a, const char* b) {
  if (!a || !b) return 0;
  while (*a && *b) { if (*a != *b) return 0; ++a; ++b; }
  return *a == 0 && *b == 0;
}

static jobject makePasswd(JNIEnv* env, const char* name, jint uid, jint gid,
                          const char* dir, const char* shell) {
  if ((*env)->PushLocalFrame(env, 16) < 0) return NULL;
  jclass cls = (*env)->FindClass(env, "android/system/StructPasswd");
  if (!cls) { (*env)->PopLocalFrame(env, NULL); return NULL; }
  jmethodID ctor = (*env)->GetMethodID(env, cls, "<init>",
      "(Ljava/lang/String;IILjava/lang/String;Ljava/lang/String;)V");
  if (!ctor) { (*env)->PopLocalFrame(env, NULL); return NULL; }
  jstring jname = (*env)->NewStringUTF(env, name);
  jstring jdir = (*env)->NewStringUTF(env, dir);
  jstring jshell = (*env)->NewStringUTF(env, shell);
  jobject obj = (*env)->NewObject(env, cls, ctor, jname, uid, gid, jdir, jshell);
  return (*env)->PopLocalFrame(env, obj);
}

static jobject makeUtsname(JNIEnv* env) {
  if ((*env)->PushLocalFrame(env, 16) < 0) return NULL;
  jclass cls = (*env)->FindClass(env, "android/system/StructUtsname");
  if (!cls) { (*env)->PopLocalFrame(env, NULL); return NULL; }
  jmethodID ctor = (*env)->GetMethodID(env, cls, "<init>",
      "(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)V");
  if (!ctor) { (*env)->PopLocalFrame(env, NULL); return NULL; }
  jobject obj = (*env)->NewObject(env, cls, ctor,
      (*env)->NewStringUTF(env, "Windows"),
      (*env)->NewStringUTF(env, "agent01"),
      (*env)->NewStringUTF(env, "10.0"),
      (*env)->NewStringUTF(env, "Win64-ART-Phase2"),
      (*env)->NewStringUTF(env, "x86_64"));
  return (*env)->PopLocalFrame(env, obj);
}

#define ST_MODE_DIR 0040755
#define ST_MODE_REG 0100644
static jobject makeStructStatSimple(JNIEnv* env, jlong ino, jint mode, jlong size) {
  if ((*env)->PushLocalFrame(env, 8) < 0) return NULL;
  jclass cls = (*env)->FindClass(env, "android/system/StructStat");
  if (!cls) { (*env)->PopLocalFrame(env, NULL); return NULL; }
  jmethodID ctor = (*env)->GetMethodID(env, cls, "<init>", "(JJIJIIJJJJJJJ)V");
  if (!ctor) { (*env)->PopLocalFrame(env, NULL); return NULL; }
  jlong now = 1700000000LL;
  jobject obj = (*env)->NewObject(env, cls, ctor,
      (jlong)1, ino, mode, (jlong)1, (jint)1000, (jint)1000,
      (jlong)0, size, now, now, now, (jlong)4096, (jlong)((size+4095)/4096));
  return (*env)->PopLocalFrame(env, obj);
}

__declspec(dllexport) jobject Java_libcore_io_Linux_getpwuid(JNIEnv* env, jobject thiz, jint uid) {
  (void)thiz; return makePasswd(env, "agent", uid, 0, "/home/agent", "/bin/sh");
}
__declspec(dllexport) jobject Java_libcore_io_Linux_getpwuid__I(JNIEnv* env, jobject thiz, jint uid) {
  return Java_libcore_io_Linux_getpwuid(env, thiz, uid);
}
__declspec(dllexport) jobject Java_libcore_io_Linux_getpwnam(JNIEnv* env, jobject thiz, jstring name) {
  (void)thiz; (void)name; return makePasswd(env, "agent", 1000, 1000, "/home/agent", "/bin/sh");
}
__declspec(dllexport) jobject Java_libcore_io_Linux_getpwnam__Ljava_lang_String_2(JNIEnv* env, jobject thiz, jstring name) {
  return Java_libcore_io_Linux_getpwnam(env, thiz, name);
}
__declspec(dllexport) jobject Java_libcore_io_Linux_uname(JNIEnv* env, jobject thiz) {
  (void)thiz; return makeUtsname(env);
}
__declspec(dllexport) jobject Java_libcore_io_Linux_uname__(JNIEnv* env, jobject thiz) {
  return Java_libcore_io_Linux_uname(env, thiz);
}

__declspec(dllexport) jint Java_libcore_io_Linux_nativeGetuid(void){return 1000;}
__declspec(dllexport) jint Java_libcore_io_Linux_nativeGeteuid(void){return 1000;}
__declspec(dllexport) jint Java_libcore_io_Linux_nativeGetgid(void){return 1000;}
__declspec(dllexport) jint Java_libcore_io_Linux_nativeGetegid(void){return 1000;}
__declspec(dllexport) jint Java_libcore_io_Linux_nativeGetpid(void){return 1;}
__declspec(dllexport) jint Java_libcore_io_Linux_nativeGetppid(void){return 0;}
__declspec(dllexport) jint Java_libcore_io_Linux_nativeGettid(void){return 1;}
__declspec(dllexport) jlong Java_libcore_io_Linux_sysconf(JNIEnv* env, jobject thiz, jint name){(void)env;(void)thiz;(void)name;return 4096;}
__declspec(dllexport) jlong Java_libcore_io_Linux_sysconf__I(JNIEnv* env, jobject thiz, jint name){return Java_libcore_io_Linux_sysconf(env,thiz,name);}

__declspec(dllexport) jstring Java_libcore_io_Linux_getenv(JNIEnv* env, jobject thiz, jstring jname) {
  (void)thiz;
  const char* val = "";
  if (jname) {
    const char* name = (*env)->GetStringUTFChars(env, jname, NULL);
    if (name) {
      if (streq(name, "ANDROID_ROOT") || streq(name, "ANDROID_ART_ROOT") || streq(name, "ANDROID_I18N_ROOT")) val = "run";
      else if (streq(name, "ANDROID_DATA")) val = "run/data";
      else if (streq(name, "HOME")) val = "/home/agent";
      else if (streq(name, "USER") || streq(name, "LOGNAME")) val = "agent";
      else if (streq(name, "PATH")) val = "/usr/bin";
      else if (streq(name, "TMPDIR") || streq(name, "TEMP") || streq(name, "TMP")) val = "/tmp";
      else if (streq(name, "LANG") || streq(name, "LC_ALL")) val = "C";
      (*env)->ReleaseStringUTFChars(env, jname, name);
    }
  }
  return (*env)->NewStringUTF(env, val);
}
__declspec(dllexport) jstring Java_libcore_io_Linux_getenv__Ljava_lang_String_2(JNIEnv* env, jobject thiz, jstring jname) {
  return Java_libcore_io_Linux_getenv(env, thiz, jname);
}

__declspec(dllexport) void Java_android_system_OsConstantsHolder_initConstants(JNIEnv* env, jclass cls){(void)env;(void)cls;}
__declspec(dllexport) void Java_android_system_OsConstantsHolder_initConstants__(JNIEnv* env, jclass cls){(void)env;(void)cls;}

__declspec(dllexport) jint Java_java_lang_Float_floatToRawIntBits(JNIEnv* e, jclass c, jfloat v){(void)e;(void)c;union{jfloat f;jint i;}u;u.f=v;return u.i;}
__declspec(dllexport) jint Java_java_lang_Float_floatToRawIntBits__F(JNIEnv* e, jclass c, jfloat v){return Java_java_lang_Float_floatToRawIntBits(e,c,v);}
__declspec(dllexport) jfloat Java_java_lang_Float_intBitsToFloat(JNIEnv* e, jclass c, jint v){(void)e;(void)c;union{jfloat f;jint i;}u;u.i=v;return u.f;}
__declspec(dllexport) jfloat Java_java_lang_Float_intBitsToFloat__I(JNIEnv* e, jclass c, jint v){return Java_java_lang_Float_intBitsToFloat(e,c,v);}
__declspec(dllexport) jlong Java_java_lang_Double_doubleToRawLongBits(JNIEnv* e, jclass c, jdouble v){(void)e;(void)c;union{jdouble d;jlong i;}u;u.d=v;return u.i;}
__declspec(dllexport) jlong Java_java_lang_Double_doubleToRawLongBits__D(JNIEnv* e, jclass c, jdouble v){return Java_java_lang_Double_doubleToRawLongBits(e,c,v);}
__declspec(dllexport) jdouble Java_java_lang_Double_longBitsToDouble(JNIEnv* e, jclass c, jlong v){(void)e;(void)c;union{jdouble d;jlong i;}u;u.i=v;return u.d;}
__declspec(dllexport) jdouble Java_java_lang_Double_longBitsToDouble__J(JNIEnv* e, jclass c, jlong v){return Java_java_lang_Double_longBitsToDouble(e,c,v);}

__declspec(dllexport) jstring Java_libcore_icu_ICU_getIcuVersion(JNIEnv* env, jclass cls){(void)cls;return (*env)->NewStringUTF(env,"72.1");}
__declspec(dllexport) jstring Java_libcore_icu_ICU_getUnicodeVersion(JNIEnv* env, jclass cls){(void)cls;return (*env)->NewStringUTF(env,"15.0");}
__declspec(dllexport) jstring Java_libcore_icu_ICU_getCldrVersion(JNIEnv* env, jclass cls){(void)cls;return (*env)->NewStringUTF(env,"42");}
__declspec(dllexport) jstring Java_libcore_icu_ICU_getIcuVersion__(JNIEnv* env, jclass cls){return Java_libcore_icu_ICU_getIcuVersion(env,cls);}
__declspec(dllexport) jstring Java_libcore_icu_ICU_getUnicodeVersion__(JNIEnv* env, jclass cls){return Java_libcore_icu_ICU_getUnicodeVersion(env,cls);}
__declspec(dllexport) jstring Java_libcore_icu_ICU_getCldrVersion__(JNIEnv* env, jclass cls){return Java_libcore_icu_ICU_getCldrVersion(env,cls);}

__declspec(dllexport) jobjectArray Java_java_lang_System_specialProperties(JNIEnv* env, jclass cls) {
  (void)cls;
  if ((*env)->PushLocalFrame(env, 48) < 0) return NULL;
  jclass stringClass = (*env)->FindClass(env, "java/lang/String");
  jobjectArray result = (*env)->NewObjectArray(env, 12, stringClass, 0);
  char cwd[MAX_PATH];
  if (!GetCurrentDirectoryA(sizeof(cwd), cwd)) {
    strcpy(cwd, "C:\\");
  }
  char home[MAX_PATH];
  DWORD n = GetEnvironmentVariableA("USERPROFILE", home, sizeof(home));
  if (n == 0 || n >= sizeof(home)) {
    if (!GetEnvironmentVariableA("HOME", home, sizeof(home)) || home[0] == 0) {
      strcpy(home, cwd);
    }
  }
  char user[256];
  n = GetEnvironmentVariableA("USERNAME", user, sizeof(user));
  if (n == 0 || n >= sizeof(user)) {
    if (!GetEnvironmentVariableA("USER", user, sizeof(user)) || user[0] == 0) {
      strcpy(user, "user");
    }
  }
  char buf[MAX_PATH + 32];
  snprintf(buf, sizeof(buf), "user.dir=%s", cwd);
  (*env)->SetObjectArrayElement(env, result, 0, (*env)->NewStringUTF(env, buf));
  (*env)->SetObjectArrayElement(env, result, 1, (*env)->NewStringUTF(env, "file.separator=\\"));
  (*env)->SetObjectArrayElement(env, result, 2, (*env)->NewStringUTF(env, "path.separator=;"));
  (*env)->SetObjectArrayElement(env, result, 3, (*env)->NewStringUTF(env, "line.separator=\r\n"));
  (*env)->SetObjectArrayElement(env, result, 4, (*env)->NewStringUTF(env, "java.library.path=."));
  (*env)->SetObjectArrayElement(env, result, 5, (*env)->NewStringUTF(env, "android.zlib.version=1.2.13"));
  (*env)->SetObjectArrayElement(env, result, 6, (*env)->NewStringUTF(env, "android.openssl.version=OpenSSL 1.1.1"));
  (*env)->SetObjectArrayElement(env, result, 7, (*env)->NewStringUTF(env, "os.name=Windows"));
  (*env)->SetObjectArrayElement(env, result, 8, (*env)->NewStringUTF(env, "os.arch=amd64"));
  (*env)->SetObjectArrayElement(env, result, 9, (*env)->NewStringUTF(env, "os.version=10.0"));
  snprintf(buf, sizeof(buf), "user.home=%s", home);
  (*env)->SetObjectArrayElement(env, result, 10, (*env)->NewStringUTF(env, buf));
  snprintf(buf, sizeof(buf), "user.name=%s", user);
  (*env)->SetObjectArrayElement(env, result, 11, (*env)->NewStringUTF(env, buf));
  return (jobjectArray)(*env)->PopLocalFrame(env, result);
}
__declspec(dllexport) jobjectArray Java_java_lang_System_specialProperties__(JNIEnv* env, jclass cls) {
  return Java_java_lang_System_specialProperties(env, cls);
}
/* Real wall/mono clocks — product apps and Thread.sleep rely on these. */
__declspec(dllexport) jlong Java_java_lang_System_currentTimeMillis(void) {
  FILETIME ft;
  ULARGE_INTEGER uli;
  GetSystemTimeAsFileTime(&ft);
  uli.LowPart = ft.dwLowDateTime;
  uli.HighPart = ft.dwHighDateTime;
  /* FILETIME is 100ns since 1601-01-01; convert to Unix ms since 1970. */
  return (jlong)((uli.QuadPart / 10000ULL) - 11644473600000ULL);
}
__declspec(dllexport) jlong Java_java_lang_System_nanoTime(void) {
  static LARGE_INTEGER freq;
  static int init = 0;
  LARGE_INTEGER now;
  if (!init) {
    QueryPerformanceFrequency(&freq);
    init = 1;
  }
  QueryPerformanceCounter(&now);
  /* Convert to nanoseconds. */
  if (freq.QuadPart == 0) return 0;
  return (jlong)((now.QuadPart * 1000000000ULL) / (unsigned long long)freq.QuadPart);
}

/* ART-WinNT: System.mapLibraryName -> libNAME.dll (product PE sonames). */
__declspec(dllexport) jstring Java_java_lang_System_mapLibraryName(JNIEnv* env, jclass cls, jstring libname) {
  (void)cls;
  if (libname == NULL) {
    jclass npe = (*env)->FindClass(env, "java/lang/NullPointerException");
    if (npe) (*env)->ThrowNew(env, npe, "libname == null");
    return NULL;
  }
  const char* name = (*env)->GetStringUTFChars(env, libname, NULL);
  if (!name) return NULL;
  char buf[320];
  /* leave room for "lib" + ".dll" + NUL */
  size_t n = 0;
  while (name[n] && n < 240) n++;
  if (n >= 240) {
    (*env)->ReleaseStringUTFChars(env, libname, name);
    jclass iae = (*env)->FindClass(env, "java/lang/IllegalArgumentException");
    if (iae) (*env)->ThrowNew(env, iae, "name too long");
    return NULL;
  }
  snprintf(buf, sizeof(buf), "lib%s.dll", name);
  (*env)->ReleaseStringUTFChars(env, libname, name);
  return (*env)->NewStringUTF(env, buf);
}
__declspec(dllexport) jstring Java_java_lang_System_mapLibraryName__Ljava_lang_String_2(JNIEnv* env, jclass cls, jstring libname) {
  return Java_java_lang_System_mapLibraryName(env, cls, libname);
}


/* FileDescriptor critical natives */
__declspec(dllexport) jboolean Java_java_io_FileDescriptor_getAppend(jint fd) {
  (void)fd; return JNI_FALSE;
}
__declspec(dllexport) jboolean Java_java_io_FileDescriptor_getAppend__I(jint fd) {
  (void)fd; return JNI_FALSE;
}
__declspec(dllexport) jboolean Java_java_io_FileDescriptor_isSocket(jint fd) {
  (void)fd; return JNI_FALSE;
}
__declspec(dllexport) jboolean Java_java_io_FileDescriptor_isSocket__I(jint fd) {
  (void)fd; return JNI_FALSE;
}


/* checkAccess(File, int) shorty ZLI — access bits: 1=execute,2=write,4=read typically */

/* canonicalize0(String, boolean) shorty LLZ — return path as-is for phase2 */
